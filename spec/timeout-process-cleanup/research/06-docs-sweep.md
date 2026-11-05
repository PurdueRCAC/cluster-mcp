# Research 06 — docs sweep: every statement the watchdog makes false or incomplete

Scope: the planner's mechanism as given (a TERM-ignoring watchdog on fd 46, started after the
prologue, that TERMs its process group, waits `GRACE` and KILLs it when the program bash dies before
writing its line; the line written after the end records; the prologue resets a TERM trap;
`run_process`, `ssh.py`, `delegate.py` and the delegated argv unchanged). Line numbers are the
worktree at `c8843b2`. "→" is what the text must say instead.

## AGENTS.md

**§2 (the launch).** §2 itself names no descriptors and no timeout step; the 47–49/57–59 parking
lives in `launch.py`'s docstring and §3's `-1002` text, and stays true.
- :1958–1974 — nothing false. **The 98,154-byte figure is the program text** (`program()`'s
  output), not the caller's command: `ssh_command` measures `BOOTSTRAP` (198 bytes) + base64 of the
  program + NUL against `MAX_ARGUMENT` (`launch.py:407–413`, `_fits` :315–320), so the figure depends only on
  `BOOTSTRAP`, which the fix does not touch. It stays exact. The watchdog lengthens every program,
  so the caller's own room shrinks by its bytes; no doc states the caller's room in bytes. Pinned by
  `test_ssh_wire_limit_counts_the_bootstrap` (`tests/test_launch.py:467–486`, computed, not
  hard-coded); `test_an_oversize_program_is_refused_before_connecting`
  (`tests/test_ssh_exec.py:2778–2790`) subtracts `len(program(''))`, and `test_program_refuses`'
  `script-too-long-for-ssh` (96 KiB script, `test_launch.py:442`) stays over. None breaks.
- :2008–2011 "Every backend runs every command under the pinned interpreter … through the launcher"
  — true; R7 says §2 "SHALL describe any change to the launch": add one bullet (or a clause here):
  every program starts a watchdog after the prologue that, if the program dies before reporting
  the command's end, stops its process group (TERM, `GRACE`, KILL); the command never holds its
  descriptor.

**§3 (the timeout contract).**
- :2038–2041 "A command that exceeds its `timeout` is stopped and `run` returns … (each backend
  reads on for `launch.GRACE` after the TERM at the deadline)" — the read clause stays true (no
  wire change). "is stopped" becomes true but needs the bound and the limits → add: every process
  of the command still in its process group has exited within 2 × `GRACE` of the deadline (server
  clock; over `ssh` excluding the link's delay), possibly after `run` returns (R4).
- :2049–2050 `TIMEOUT_EXIT_CODE` "stdout and stderr carry whatever was captured before the
  deadline" — unchanged (R5).
- :2117–2121 "nothing the command or a startup file left running holds the call, is waited for or
  is signalled" — stays true for a call whose records arrive (the line follows the records). But
  a startup file's background job sits in the program's group, so at a **timeout** it is now TERMed
  and KILLed in every mode (it already was in `local`/root `delegate`). No text claims otherwise;
  the new limits bullet may say so.
- :2133–2136 "A recorded limit: over `ssh`, a launch that dies before its records (killed from
  outside) while something it started still holds the channel is held until the timeout" —
  **becomes partly false**: a program killed from outside, at any time, now fires the watchdog, so
  what it started is stopped and the channel's EOF arrives within about 2 × `GRACE`; held to the
  timeout only by a process that left the group → rewrite.
- :2137–2139 "**A timed-out command may outlive the call** (recorded, not fixed): over SSH the
  server is asked to TERM it and the channel is closed, and under a non-root `delegate` server
  `sudo` relays TERM only to the command; `issues/timeout-process-cleanup.md`." — **false**; R7
  names it → replace with what is stopped (the command, children, grandchildren, TERM-ignorers in
  its group), the bound, and the limits: (a) a process that left the group (`setsid`, a daemon);
  (b) over `ssh`, a server that does not act on the RFC 4254 `signal` request (nothing then kills
  the program, so no stop; the test cluster's OpenSSH does act on it); (c) a lost link (non-goal);
  (d) a command that handles TERM may receive it twice (deadline + watchdog); (e) **the login
  initialisation, before the watchdog exists**: a startup file that ignores TERM and hangs is
  KILLed by `run_process` in `local`/root `delegate`, but over `ssh` and under a non-root
  `delegate` server nothing sends it KILL (not "the command's processes" in GOAL's sense, but a
  process the call started; it should be stated, not left implied). Drop the seed link (retired at
  landing).
- :2140–2145 `local` outlives-server bullet: "only the call that launched a process group signals
  it, from its own thread" — **false**: the program's watchdog signals it too. The probe case it
  cites (a profile that ignores TERM and hangs) is before the watchdog, so "a group that ignores
  SIGTERM runs on" stays true **for a hang in the login initialisation**; once the command runs,
  the watchdog's KILL no longer depends on the server's thread → narrow the sentence to the
  login-initialisation hang. Side effect worth one clause: a server killed mid-command still
  leaves the command running to its end, but the program then dies of SIGPIPE writing its record,
  so the watchdog stops what the command left in its group.

**§5 (delegate).** :2231–2236 the argv `sudo -n -H -u <local_user> /bin/bash --norc --posix -c
<stage> cluster-mcp <program>` — unchanged and true. No §5 sentence describes `sudo` relaying (that
is §3 :2138–2139). Optional: add that under a non-root server the deadline's TERM reaches the program
through `sudo`'s relay and the watchdog, running as the mapped user, does the rest, needing no
right beyond the documented `sudo` rule.

**Footguns.**
- :1812–1816 `executor/launch.py` — "and the timeout sequence (SIGTERM, then SIGKILL, each followed
  by a bounded drain)" → incomplete: add the watchdog (fd 46, TERM ignored, line written after
  both records, closed in the command's subshell, `GRACE` rendered into the program), the
  prologue's TERM-trap reset. Also "SIGKILL" is skipped when output ended (`launch.py:609`) —
  already imprecise.
- :1852–1856 `executor/ssh.py` — "or reading for `launch.GRACE` after the TERM" — true. Keep the
  section's `RECONNECT_BOUND_TEXT` intact (pinned, below).
- :1886–1890 `probes.py` — "dies with the interpreter, between its timeout's SIGTERM and SIGKILL if
  the server exits then (§3's recorded limit)" — true of the worker; the group's survival now
  holds only for a login-initialisation hang → align with the narrowed §3 bullet.

**§ Architecture & data flow** (:213–248): no timeout, signal, `GRACE` or `run_process` text. Nothing.

**§ Testing** (needs the new R6 rows added; these say what exists today):
- :848–850 "the `integration` rows run `local` and `delegate` … a timeout returns the captured
  output and `TIMEOUT_EXIT_CODE`, never raises, and leaves no process" — true for one `sleep`; add
  the R6 rows (child + grandchild, TERM-ignorer, each pid gone after the bound; delegate's
  stand-in as the only signallable process).
- :998–1010 `run_process` "kills the whole group … a command that traps SIGTERM keeps what it
  prints as it stops, and one that ignores it is ended by SIGKILL" — true (raw `bash -c`, no
  program); add the watchdog rows.
- :1059–1061 ssh integration "a timeout returns the captured output and `TIMEOUT_EXIT_CODE`
  without raising" — add the R1 row (processes gone; the loopback server must deliver `signal` as
  OpenSSH does, to the session's group).
- :1099–1100 ssh unit rows — unchanged (`_collect` unchanged).
- :1273–1275 the `sudo` stand-in "starts the command in its own session, relays only TERM, INT and
  HUP" — the stand-in (`tests/conftest.py:376–398`) relays with `os.killpg(child.pid, …)`, i.e. to
  the command's **group**, while its comment and this line say "to it". `sudo` without a pty is
  believed to relay to the command's pid alone (not verified here). For R6's R3 fidelity the
  relay should be `os.kill`, and both texts say "to the command alone".

**§9 / served surface.** `run_command`'s description (`core/tools/shell.py:22–49`): "On timeout,
exit_code is -1001 and stdout and stderr hold what was captured before the deadline"; `timeout:
Maximum time in seconds to wait for completion.` Both stay true; nothing about stopping. No core,
Slurm or RCAC `instructions.py` mentions timeouts; the fixture's only timeout text is that
description. **No served text must change**, so `tests/fixtures/served_surface.json` stays as is.
Saying "the command is stopped" there would be a surface delta (`run_command.description`, and
`properties.timeout` if the `Args:` line changes), needing the scripted fixture edit and a § Testing
/ commit-body entry (§9 :2580–2591) — not required by R7; recommend not.

## README.md

- :129–131 "A command that exceeds its `timeout` returns what it printed so far with exit code
  `-1001`; over ssh, a connection lost before the command's end was reported gives `-1003`: the
  command may have run." — R7 names it → add: the command and what it started are stopped (within
  2 s of the deadline); not stopped: a process that left its process group (`setsid`, a daemon),
  and over ssh a server that ignores the signal request or a lost connection.
- :122–123 "A command killed by signal N (or exiting 128+N) has exit code `-N`." — true.
- :119–122 "a background job the command or a startup file leaves running never holds it" — true
  (that is a completed call).

## SECURITY.md

- Documented `sudo` rule (:218, :221), exactly: `cluster-mcp ALL=(ALL) NOPASSWD: ALL` and, "more
  restrictively", `cluster-mcp ALL=(alice,bob,svc_batch) NOPASSWD: ALL`. Both allow **any**
  command as the target users, so a different program text under the unchanged `/bin/bash` argv
  stays inside them; even an operator rule pinned to `/bin/bash --norc --posix -c *` still matches,
  since only the last argument's text changes (it cannot be pinned anyway: it carries nonces). The
  watchdog runs as the mapped user in the mapped user's group, so stopping needs no extra privilege:
  Q3's narrowing does not trigger and R7's `SECURITY.md` clause is conditional → no change
  required. Optional, where an operator chooses the account (:90 "Server runs as root (or a
  privileged user with sudo rights)", :265 "Run server as dedicated service account with
  minimal privileges"): one sentence that a non-root service account stops timed-out commands
  too, except a login initialisation that ignores TERM and hangs (limit (e) above).
- :226 "Use `NOEXEC` …" — pre-existing: `NOEXEC` already breaks the launch (the stage `exec`s
  `/bin/bash -l`). Not this fix's; note only if the watchdog's wait uses an external `sleep`.

## Docstrings and comments

- `launch.py:4–46` module docstring — :24–31 descriptors 57–59/47–49 true; add fd 46 and the
  watchdog (a paragraph: what it does, that it fires only if the program dies before its line, the
  line after the records). :34–43 "Only a timeout bounds a call whose records do not come" — now
  also the watchdog for a program killed from outside → amend.
- `launch.py:83–85` `GRACE` — "The bound on the drain after each of SIGTERM and SIGKILL at a
  timeout, and on the wait for a launch to exit once it has reported its command's end" → add "and
  the watchdog's wait between its TERM and KILL; 2 × GRACE is the stop bound (AGENTS §3)".
- `launch.py:126–137` PROLOGUE comment "…; traps)" and :142 `trap - EXIT ERR DEBUG RETURN` → name
  TERM. **Mutation pin:** `tests/mutants.py:1835–1839` (`startup-traps-kept`) anchors on that exact
  line text; editing :142 breaks the anchor (`mutants.py:4713–4716` requires exactly one match).
- `launch.py:161–164` SUBSHELL comment → say the subshell closes fd 46 (if it does; it must, or a
  descendant holding it hides the program's death from the watchdog).
- `launch.py:173–175` "The program's last lines: …" → add the watchdog's line after the record.
- `launch.py:573–584` `run_process` — "nothing is signalled" (complete call) true; "the whole
  process group gets SIGTERM, then SIGKILL, each followed by a bounded drain" → already imprecise
  (KILL skipped once output ended, :609); add that the program's watchdog KILLs what remains.
- `ssh.py:162–163` `_signal` "Ask the server to deliver signal `name` to the command" → "to the
  session's process group (OpenSSH); the program's watchdog finishes the stop".
- `ssh.py:203–204` `_stopped`, `:214–230` `_collect` "the command is asked to TERM and what it
  prints as it stops is read for `GRACE`" — true; optionally name the watchdog.
- `ssh.py:924–952` `SSHExecutor.run`, `:971–977` `_exec` — no stop claim; nothing false.
- `base.py:18–19` "The exit code of a command stopped at its timeout" — true. `base.py:52–63`
  `Executor` docstring — nothing about timeouts. `base.py:98–107` `run` Returns: "the command is
  stopped (unless it has exited) and the result carries what it printed before the deadline and as
  it stopped" → add "with what it started, within 2 × `GRACE`; not a process that left its group".
- `delegate.py`, `shell.py` — `timeout: Seconds to wait; at the deadline the result carries
  `TIMEOUT_EXIT_CODE`` (delegate :133, shell :64); nothing false.

## ROADMAP.md and issues

- `ROADMAP.md:117–131` entry ("whether the command stops is open over SSH … and under a non-root
  `delegate` server") and the direction line :91–92 ("Ahead of the tool families sit the executor
  fixes: stopping a timed-out command, its measurement now approved") — retired by the roadmap
  step at landing (AGENTS :1712–1716), not R7's commit. :447–452 (outlives-server entry) "a group
  behind a login profile that ignores SIGTERM and hangs runs on" stays true (pre-watchdog hang).
- `issues/local-command-outlives-server.md` :13–17 "Only the call that launched a group ever
  signals it" → false after the fix (the watchdog); its cases remain (both are before the deadline
  or before the watchdog), and its §Notes "the executor's timeout sends SIGTERM and, after
  `GRACE`, SIGKILL" stays true. Amend the one sentence and add a note.

## Tests that pin doc text (R7 edits must keep these strings)

- `tests/test_ssh_exec.py:331`, `:366–376` `test_separation_texts_state_the_remote_rc_exception`:
  AGENTS §3 (sliced `'### 3. '`…`'### 4. '`), README, `run_command.description`, `Executor.__doc__`
  must contain "a background job started by the remote login shell's own rc file".
- `:354–363` `test_content_texts_state_the_sftp_route`: AGENTS §2 (`'### 2. '`…`'### 3. '`),
  README, `Executor.write.__doc__` contain "by SFTP to a private temporary file".
- `:1841–1867` `test_reconnect_texts_state_the_bound`: the `executor/ssh.py` footgun (sliced
  `- **`executor/ssh.py`**` … `- **`__init__.py`**`) and `SSHExecutor.__doc__` keep
  `RECONNECT_BOUND_TEXT`; AGENTS must not contain "never gives up".
- `tests/test_surface.py` `test_served_surface_matches_baseline`: any `run_command` docstring edit.
- `tests/mutants.py:1835` (launch.py anchor, above); `REPO_TOP` plants into README/AGENTS anchor
  only the upgrading section (`mutants.py:296–303`), untouched here.
