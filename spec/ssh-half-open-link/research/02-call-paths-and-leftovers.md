# 02 — Call paths, leftovers and what the agent sees

Read-only research for the plan. Tree at `2f50b7f` (develop `13c0e83` + GOAL); Paramiko 5.0.0,
Fabric 3.2.2, FastMCP 4.1.4 in `.venv`. `ssh.py` = `packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py`;
`P/` = `.venv/lib/python3.14/site-packages/paramiko/`.

**Experiment (scratch, not in the repo).** A loopback proxy in front of the suite's `LoopbackSSH`
froze both directions at a chosen client step without closing a socket, then 0.5 s later closed the
client transport (what the fix will do), host reachable or refusing, reconnect window cut to 6 s.
Rows marked (x) below are its observations.

## How a closed transport surfaces

`Transport.close` → `stop_thread` sets `active = False` first (`P/transport.py:1761`), then unlinks
every channel (`:863`), so a fix-initiated close reads inactive at once (no `SETTLE` race, unlike
Paramiko's own EOF path, which unlinks at `:2153` before `active = False` at `:2155`). Per wait:

| Blocked in | Raises (x) |
|---|---|
| `open_channel` (`open_session`, both for exec and SFTP) | `transport.get_exception()`: **`EOFError()`** with empty text for the first waiter, else `SSHException('Unable to open channel.')` (`P/transport.py:1048-1052`; `get_exception` clears it) |
| `exec_command` | `SSHException('Channel closed.')` (`P/channel.py:1216-1224`) → `_exec` returns −1003 (`ssh.py:1018-1024`) |
| `invoke_subsystem('sftp')` | `SSHException('Channel closed.')` |
| SFTP version exchange | `SSHException('EOF during negotiation')` (`P/sftp_client.py:130-132`) |
| SFTP reply wait | `SSHException('Server connection dropped: ')` (`P/sftp_client.py:886-889`) |
| SFTP send on an already-closed channel | `OSError('Socket is closed')` (`P/channel.py:1194-1196`) |
| SFTP send blocked on the window | send returns 0 → `EOFError()` empty (`P/sftp.py:171-175`) |

The SFTP session open has no timeout at all: `open_sftp_client` → `open_session()` → `channel_timeout`
3600 s (`P/sftp_client.py:164`, `P/transport.py:537`).

## Q1 — The "nothing sent yet" boundary

**`run`** (`ssh.py:988-1028`): `_ensure_connected` → `open_session(timeout=OPEN_TIMEOUT)` (`:1013`,
*outside* the `try`) → `exec_command` (`:1016`) → `shutdown_write` → `_collect`. A channel open runs
nothing remotely. **Last safe retry point: a failure of `open_session` (`:1013`).** From
`exec_command` on, the request may have reached sshd: report −1003. (x) A freeze just before
`exec_command` sent its bytes already returns −1003 — correctly conservative, since the code cannot
tell "queued" from "delivered". Today an `open_session` failure escapes `run` raw (x: `EOFError`
with empty text).

**`write`** (`:1030-1114`): `_ensure_connected` (`:1065`) → SFTP session open (`:1068`: channel open,
`invoke_subsystem`, version) → parent `_is_dir` stat (`:1070`) → maybe `_run(MAKE_PARENT)` (`:1071`,
its own `run` boundary; `mkdir -p` is idempotent) → `_staging` reads (lstat/normalize/stat/readlink,
`:1077`) → **`_stage` mkdir (`:606`), the first remote change** → `_upload` content (`open 'wbx'`
`:632`, chmod, unpipelined writes, checked close, stat) → `_upload` expected → place `_run` (`:1110`:
its `open_session` safe, its exec not) → `_discard` (`:1114`). Safe to retry over a new connection:
anything before `:606`, and the place step's `open_session`. Every `_run` inside shares the write's
deadline (`deadline=` at `:1072`, `:1110`, `:1125`).

**`put`** (`:1133-1160`): session open (`:1155`) → `_is_dir` stat (`:1157`) → `sftp.put` (`:1159`):
`OPEN` with `CREATE|TRUNC` (`P/sftp_client.py:366`, `:714`) → pipelined writes (`:715`) → close →
confirm stat (`:720`) → `normalize` (`:1160`). **Last safe point: before the `OPEN` request goes**;
from then on the target may be truncated or partly written.

**`get`** (`:1162-1188`): session open (`:1183`) → `sftp.get` (`:1187`), which opens the *local*
file `'wb'` first (`P/sftp_client.py:839`), then stats and opens the remote (`:795-796`) and reads.
The remote is never changed; the local target is truncated before any remote request.

Read-only SFTP requests before the first change (`write`'s stats, `put`'s `_is_dir`) are also
retry-safe, but nothing requires retrying them: R1 is met by retrying at session open, which is the
first wait a call that starts on a silent link blocks in.

## Q2 — What each tool can leave behind (x: host reachable or not, same)

- **`write` / `write_file`**: loss after `_stage`'s mkdir leaves `.cluster-mcp-<hex>/` (0700) beside
  the target or in the login home, holding nothing, `content` (possibly partial), or `content` +
  `expected`; `_discard` runs on the dead session and fails silently (`:667-673`), as
  `issues/ssh-write-staging-leftover.md` records. **The target is untouched** until the place
  step's exec. Once that exec may have gone (−1003): an overwrite's `mv` is atomic (old or new
  file); an append's `cat >>` may have appended part; a written-through target's `cat >` may be
  truncated or partial; `chmod +x` may be missing; `expected` (and `content`, if `mv` did not run)
  remain.
- **`put` / `upload_file`**: an existing target is truncated by the `OPEN` before the first byte
  (x: `up.bin` 1000 B → 0 B on a loss right after `OPEN`); a later loss leaves a prefix (x: 0.5 MB,
  3.9 MB of 4 MB, since pipelined writes in flight are lost).
- **`get` / `download_file`**: the remote is unchanged; an existing local target is truncated
  even when the loss comes at the remote stat (x: 1000 B → 0 B), and a later loss leaves a prefix.
- **`sbatch` with `script_content`**: the script goes through `write` (`slurm/tools.py:169`), so
  the job-script path behaves as `write` with `executable=True`; `sbatch` itself never runs after a
  failed or lost write, so no job is submitted.

## Q3 — What the agent sees today

FastMCP turns any uncaught exception into an `isError` result `Error calling tool '<name>': <str(e)>`
(`fastmcp/server/server.py:1526-1564`; no `mask_error_details` is set, `core/server.py:130`;
`is_timeout_error` matches only httpx, so a `TimeoutError` is not rewritten).

| Tool | Catches | Text on a lost link (x) |
|---|---|---|
| `run_command`, every Slurm/site tool, `read_file`, `list_directory` | nothing around `run` | open fails → `Error calling tool 'run_command': ` (empty, `EOFError`) or `…: Unable to open channel.`; on develop, `…: Timeout opening channel.` after 30 s. Exec/collect loss → −1003 result with `LOST_NOTE` (`launch.py:321`), no host |
| `write_file` | `OSError` → `Failed to write file: {exc}` (`tools/filesystem.py:192-195`); nonzero code → `Failed to write file (exit N): {stderr}` (`:197-198`) | `SSHException`/`EOFError` escape: `Error calling tool 'write_file': Server connection dropped: ` / `Channel closed.` / `EOF during negotiation` / empty. `OSError('Socket is closed')` → `Failed to write file: Socket is closed`. Place-step −1003 → `Failed to write file (exit -1003): cluster-mcp: the connection was lost; the command may have run` |
| `sbatch` (`script_content`) | `OSError` → `Failed to write job script: …` (`slurm/tools.py:170-171`); −1002 → `The job was not submitted: …` (`:173-174`); other codes `Failed to write job script (exit N)` (`:175-176`) | write's −1003 is **not** special-cased (falls to `:176`); only the `sbatch` command's −1003 is ("may have been submitted", `:198-200`) |
| `upload_file`, `download_file` | nothing (`tools/transfer.py:44-64`) | `Error calling tool 'upload_file': ` + `Server connection dropped: ` / empty / `Socket is closed` / `Unable to open channel.`; only `_ensure_connected`'s `ConnectionError` names the host (`ssh.py:1154`, `:1182`) |

No message from a mid-transfer loss names the host.

**Recommended shape for R2.** One exception class in `ssh.py`, a subclass of `ConnectionError`
(hence `OSError`), raised by `write`, `put` and `get` for any loss after their last safe point, text
`the connection to <host> was lost during the transfer, so <what> may be partly made` (e.g. for
`put` "the remote file …", `get` "the local file …", `write` naming the staging directory left and
whether the target was touched). As an `OSError` it reaches the agent with no tool change:
`write_file` → `Failed to write file: the connection to <host> was lost …`; `sbatch` → `Failed to
write job script: …`; `upload_file`/`download_file` → `Error calling tool '…': the connection to
<host> was lost …`. Two cautions: `_upload`'s `except OSError` (`ssh.py:644`), `_is_dir` (`:526`),
`_loops` (`:559`) and `write`'s staging `except OSError` (`:1087`) all swallow or re-wrap an
`OSError`, so the lost case must be decided before them (or the class re-raised first). The
place-step −1003 needs a decision too: either `write` keeps returning −1003 (then `write_file` and
`sbatch` need a branch to say "may be partly made" and name the host; `sbatch` should also say the
job was not submitted), or `write` raises the same class there. §2's `write` contract
(`AGENTS.md` §2, "Raises: OSError … nothing was written") must change either way.

## Q4 — `_reason` and `_discard` on a dead link

`_reason` runs only for `Short`, i.e. an `OSError` inside `_upload`'s inner block (`:635-647`).
After a fix-initiated close the next send raises `OSError('Socket is closed')` → `Short` →
`_reason(staged, deadline)` → `_run(PROBE, timeout=60, deadline=…)` (`:1124`) → `_ensure_connected`.
(x) Unreachable: it waits until deadline − `FINAL_ATTEMPT_LEAD` (4.0 s of a 6 s window; up to ~43 s
of the default 45 s) and gives no reason. Reachable: it reconnects and appends 64 KiB of zeros to
the staged file on the new connection; its 60 s timeout is **not** capped by the deadline (x: 61 s
when the harness's PROBE never ended). The result reads `…failed: Socket is closed; the file is
unchanged`: "unchanged" is true of the target (staged), but the cause is wrong, the host unnamed,
and on a full filesystem the probe could name `No space left on device` as the cause of a lost link.
`SSHException`/`EOFError` losses bypass `Short` and `_reason` entirely (x).

`_discard` on a closed transport: each `remove`/`rmdir` fails at once with `OSError('Socket is
closed')`, swallowed (`:667-673`): no wait, staging left. While the link is silent but not yet
closed it would block on reply waits until the close.

**Recommend:** decide "lost" at the exception site by `not transport.is_active()` (the fix's close
makes it immediate; for Paramiko's own EOF path keep `_exec`'s `join(SETTLE)` pattern, but only for
non-status exceptions — `EOFError`, `SSHException`, `Socket is closed` — so a live server's SFTP
`Failure` never costs a second); on "lost", skip `_reason` and `_discard` on the dead session and raise
the R2 error naming the staging directory left (cleanup stays with the staging-leftover seed).

## Q5 — Other executor users on the ssh path

- `probes.py:85-87` (`_ask`, timeout 10 s) and `site.py:573` (`read_remote`, via `read_bounded`'s
  daemon thread, `site.py:583-600`): each caller has its own bound (`probes.py:133-138`,
  `core/__init__.py:312-337`) and abandons the thread; both are read-only, and `start`'s worker maps
  any exception to a reason (`probes.py:158-162`). A retry inside `run` only lengthens an abandoned
  thread.
- Two-command tools: `sacct` (`whoami` then `sacct`, stops on failure, `slurm/tools.py:378-382`);
  `resolve_storage_paths` (`findscratch` then `myquota`, `rcac/tools.py:356-364`, each its own
  window). Read-only, so a second reconnect costs time, not correctness.
- `write`: parent `_is_dir` swallows a lost-link `OSError` as "not a directory" (`ssh.py:523-527`),
  so `write` then runs `MAKE_PARENT` through `_run`, which reconnects, while it keeps the dead SFTP
  session for staging: guard the session's liveness before falling into `_run`.
- **Double-run risk:** none if the retry is confined to `open_session` failures (`ssh.py:1013`) and
  SFTP session open (`:1068`, `:1155`, `:1183`). Retrying anything after `exec_command` (`:1016`)
  could run the command twice (the place step's `cat >>` would append twice; `sbatch` would submit
  twice). Concurrent callers on the same executor each hold their own captured transport
  (`_ensure_connected`, `:898`), so one call's retry never re-sends another's command.

## Recommendation

1. Retry over a new connection only when the session open fails on a closed transport: `_exec`'s
   `open_session` and the three `open_sftp_client` calls; loop back into `_ensure_connected` with the
   call's same deadline. Everything after an exec request or the first mutating SFTP request is a
   loss.
2. One `ConnectionError` subclass for R2, raised by `write`/`put`/`get`, naming the host and what may
   be partly made (`write`: staging dir and whether the place step may have run; `put`: the remote
   target, possibly truncated; `get`: the local target, possibly truncated). No change needed in
   `upload_file`/`download_file`; `write_file`/`sbatch` work unchanged for the raise, but need a
   branch if `write` keeps returning −1003 from its place step.
3. Check liveness before every `except OSError` in the SFTP path (`_upload`, `_is_dir`, `_loops`,
   staging), and skip `_reason`/`_discard` on a lost link.
4. Give the SFTP session open a bound (`open_session(timeout=…)`; `open_sftp_client` has none).
