# Research 01 — Callers of `bin/sandbox.sh` and the contracts a fix must not break

Base `0bfacae`. All paths repo-relative. Read-only survey; no code run.

## 1. Callers, grouped

Every caller executes `bin/sandbox.sh` by path, so it runs under its `#!/bin/sh` shebang (dash on
the Ubuntu 24.04 CI runners, `.github/workflows/ci.yml:34`; bash-as-sh on macOS). None runs it under
another shell (§ 6). Nobody passes a TMPDIR except where noted; the rest inherit the host's.

**A. `subprocess.run([SANDBOX, …], capture_output=True, timeout=N)`: about 25 sites.** `communicate()`
waits for EOF on both pipes. On `TimeoutExpired`, Python SIGKILLs the wrapper **alone** (not its
group), then calls `communicate()` again, so it waits for EOF once more. Sites: `tests/conftest.py:130`
(`need_git`), `tests/test_cli.py:79,141,313`, `tests/test_audit.py:385` (TMPDIR=`tmp_path`),
`tests/test_registry.py:155,486,523`, `tests/test_site.py:126,836,884`, `tests/test_sbatch.py:492`,
`tests/test_startup.py:216,536,550,584`, `tests/test_site_startup.py:156`, `tests/test_tokens.py:98`,
`tests/test_timeout_stop.py:810`, `tests/test_hygiene.py:489`, `tests/test_launch.py:1505`,
`tests/test_core_only.py:73,82`, `tests/test_probe_startup.py:855` (`start_new_session=True`,
TMPDIR=`tmp_path`), and the docs gates (`spec/agents-d-instructions/verify/docs_gate.py:91`,
`spec/capability-probe/verify/docs_gate.py:113`, `spec/agents-d-instructions/verify/site_gate.py:137`).
**`tests/mutants.py:5696` `run_child`** follows this pattern with `timeout=300`.

**B. `launch.run_process` (the executor's launcher): every `executes` launch, plus 8 direct sites.**
`packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py:692` runs `Popen(stdin/stdout/stderr=PIPE,
start_new_session=True)` and reads the pipes until each stream has carried its end record **or reached
EOF** (`read_until`, `:651`). At its deadline it sends `killpg(TERM)`, waits up to GRACE (1 s) for EOF,
then sends `killpg(KILL)` and waits up to GRACE again (`:706-713`). The `executes` fixture
(`tests/conftest.py:446-460,487`) wraps every local or delegate launch as
`[SANDBOX, 'env', '-i', …, (RELAY,) /bin/bash …]`. That covers 12 modules: `test_executors`,
`test_writes`, `test_timeout_stop`, `test_launch`, `test_literal_args`, `test_extra_args`, `test_sbatch`,
`test_probes`, `test_site`, `test_ssh_exec`, `test_ssh_smoke` and `test_hygiene`. Direct sites:
`tests/test_launch.py:933` (`_sandboxed`, 7 calls at `:1084-1205`) and `tests/test_hygiene.py:501`.
**A TERM-ignoring command (`tests/test_launch.py:1163`) gets the group SIGKILL**, and so does any
command the trap waits on. That is another SIGKILL path, and the GOAL does not name it.

**C. The loopback SSH server: every SSH exec in the suite.** The callers are
`tests/ssh_server.py:608` (`_launch`, `[SANDBOX, 'env', '-i', …, '/bin/sh', '-c', ENTER_HOME, shell,
wire]`) and `:400` (`sftp-server`). Both run `Popen(PIPE ×3 or stderr=DEVNULL, start_new_session=True)`.
`execute` (`:566-590`) calls `proc.wait()`, then `out.join(); err.join()`. Those threads pump the pipes
**until EOF with no timeout**. A `signal` request runs `killpg(proc.pid, sig)` for HUP, INT, KILL,
QUIT, TERM, USR1 or USR2 (`:113,549`). `close()` runs `killpg(SIGKILL)` and then `wait()` (`:629`).
QUIT, USR1 and USR2 are untrapped by the wrapper today, so they also leave the directory.

**D. MCP stdio client (`harness.stdio_tools` / `stdio_refusal`, `tests/harness.py:547,580`; `mcp`
`client/stdio.py`).** Sites: `test_transports:143` (TMPDIR=`tmp_path`), `test_core_only:95,108`,
`test_probe_startup:783,795` (TMPDIR=`tmp_path`) and `test_startup:238,528`. The client spawns with
`start_new_session=True` and stderr inherited (errlog). To stop, it closes stdin, polls `returncode`
for 2 s, then `killpg(TERM)`. It then **polls `killpg(pgid,0)` until the group is gone**, for up to
2 s, and sends `killpg(KILL)` (`mcp/os/posix/utilities.py`).

**E. `Popen` long-running servers stopped by group.**
- `tests/test_transports.py:113` (TMPDIR=`tmp_path`, stdout DEVNULL, stderr to a file) runs
  `killpg(TERM)`, `wait(STOP_TIMEOUT)`, then `killpg(KILL)` (`:81-91`).
- `tests/test_probe_startup.py:817` (TMPDIR=`tmp_path`, DEVNULL ×3) runs `killpg(KILL)`, then
  `wait(10)` (`:834`).
- `tests/test_startup.py:603` `run_bounded` (PIPE ×3) runs `communicate(timeout)`. On a timeout it
  runs `killpg(KILL)`, then `communicate()`, which waits for EOF (`:606-608`).
- `spec/agents-d-instructions/verify/serve_gate.py:155` (stderr=PIPE, unread) runs `killpg(KILL)`,
  then `wait()` (`:180`).
- `spec/capability-probe/verify/drives.py:325` does **not** start a nested sandbox. Its `CLI` is
  `uv run …` (`:115`), and the script runs inside an outer `bin/sandbox.sh` that a gate shell
  started (`spec/capability-probe/verify/p2.sh:27,32`, `p3.sh:31`).

**F. Shell gates and CI.** `.github/workflows/ci.yml:184` and the profile `verify`'s last command
(`AGENTS.md:1745`) both run `bin/sandbox.sh uv run cluster-mcp --help`. About 40 `spec/*/verify/*.sh`
lines run `bin/sandbox.sh sh -c '…'` in the foreground, and 9 lines run `exec bin/sandbox.sh …`
(`spec/capability-probe/verify/baseline.sh:25` and others). In these the wrapper's stdout and stderr
are the agent's or runner's capture pipe, and the reader waits for EOF.

## 2. EOF waiters and process or group assertions

**EOF waiters**, which hang (or slow down) while any process holds an inherited copy of the wrapper's
stdout or stderr:
- Group A, every site, with no bound after a timeout's SIGKILL.
- Group B: up to 2 × GRACE late, which turns a TERM stop into a KILL stop. `test_launch.py:1128`
  asserts `elapsed < 3` for a 0.5 s timeout.
- Group C: `out.join()`/`err.join()` and `_RealSFTP`'s `relay.join()`, which are **unbounded**.
- `run_bounded`'s `communicate()`, `mcp`'s readers, and the group F shell callers.

**Process and group assertions.** No test counts processes, greps `ps`, or uses `psutil`. Each check
targets a pid or pgid it recorded:
- `group_alive(server.pid)`, a `killpg(pgid, 0)` loop: `tests/test_transports.py:94,129-132`,
  `tests/test_probe_startup.py:839-841`. **A watcher left in the wrapper's process group fails these
  rows** ("process group … outlived the stop").
- `mcp`'s `terminate_posix_process_tree` waits for the same group, so a watcher in the group costs
  2 s and then gets SIGKILLed.
- `run_process`'s `killpg` and `ssh_server.close()`'s `killpg(SIGKILL)` would kill a watcher in the
  group, and the directory would stay.
- `tests/test_timeout_stop.py:194-260` (`_alive`, `stop_violations`, the `pids` teardown) and
  `tests/test_launch.py:1091-1171` (`_gone`, sibling checks) look only at pids that the command wrote
  to pid files. A watcher writes none, so they cannot see it.
- The sibling `mutant-child-outlives-timeout` (its TECH.md D1) walks a **fixpoint over ppid and pgid**
  from the wrapper, sends SIGSTOP to everything it finds, then SIGKILL. A watcher is out of its reach
  only if it has left the wrapper's group **and** lost its parent link (re-parented to init) before
  the stop.

**Sandbox-directory assertions.**
- `tests/test_transports.py:76-78,135-136,145-146` globs `tmp_path/'cluster-mcp-sandbox.*'`
  **immediately** after the wrapper exits, with no polling. On the TERM path it relies on R3 (the
  directory removed before the wrapper exits). If the stop escalates to SIGKILL, an asynchronous
  removal could race this check.
- `stdio_and_list` checks right after `stdio_tools` returns. The usual path is a normal exit on
  stdin EOF, which is synchronous.
- Nothing else globs for sandbox directories.

## 3. HOME, stdin, signals, fds, status and stderr

- **HOME contents.** `tests/test_cli.py:43` (`DRIVE_SCRIPT`) runs `find "$HOME" -type f -name
  '*.db'`, and any match fails `flag_violations`. No test runs `ls ~` or lists the sandbox directory.
  The gates use `$HOME/dist` and `$HOME/login.log` (`spec/capability-probe/verify/drives.py:83-85`,
  `p3.sh:41`). A pid file or FIFO kept inside the sandbox directory would therefore be visible in
  HOME.
- **stdin is load-bearing everywhere.** Tests feed it to the command through `run_process`'s pipe
  (`write_argv` writes stdin to a file, `launch.py:527`), `test_cli.sandboxed(input=…)`,
  `test_startup` (`:536,603`), the SSH `_feed` and SFTP relay (`ssh_server.py:404-411`), and every
  MCP stdio session. A command started as `"$@" &` would get `/dev/null` as stdin and SIGINT/SIGQUIT
  ignored (POSIX, with job control off), which breaks every one of these.
- **Signals.** No test sends INT or QUIT to a sandbox group in practice. The suite's SSH signal
  requests are TERM (`tests/test_ssh_exec.py:3874`). The launch program's `RERAISE`
  (`tests/test_launch.py:100`) re-raises a trapped signal, and a signal that was ignored at entry
  could not be re-raised.
- **Group membership is load-bearing.** Every group stop (B, C, D, E) reaches the command only
  because the command shares the wrapper's process group. The wrapper must stay the pid callers
  `killpg`.
- **fds.** The launch program parks fds 57–59 and 47–49 and the watchdog uses fd 46
  (`launch.py:25`, `tests/test_launch.py:57-59,1079`). A pipe fd leaked to the command is inherited
  by its background jobs. `test_a_completed_command_leaves_its_jobs_running`
  (`tests/test_timeout_stop.py:306`) leaves such jobs running, so a watcher keyed on that pipe would
  wait for them and not for the command.
- **Exit status.** Today a command killed by a signal gives 128+N (`tests/test_executors.py:175`
  comment). `tests/test_launch.py:1232` (`REPORTER`) deliberately runs the launch inside the sandbox,
  so the wrapper's masking is not under test there. No test asserts on 127 or "not found" through
  the wrapper.
- **stderr.**
  - `tests/test_cli.py:298-300` asserts that two sandboxed runs give **byte-identical** stderr.
  - `:316-317` and `flag_violations` assert stdout is empty.
  - `tests/test_launch.py:1131` tolerates "the sandbox's shell … its own line about the killed child"
    after the command's stderr.
  - The wrapper must print nothing run-dependent (a pid or a path) on stderr, and nothing at all on
    stdout.
- **PATH.** `tests/test_registry.py:749-787` (`SANDBOX_NEEDS = ('dirname', 'mktemp', 'mkdir', 'rm')`)
  runs the wrapper with a PATH holding **only those four** (plus a fake git) and expects
  `need_git()` to pass. Any new external program the wrapper runs (`setsid`, `perl`, `python3`,
  `sleep`, `cat`, `ps`) breaks this test unless it is added there or called by absolute path. macOS
  has no `setsid(1)`.

## 4. Text pinned in `bin/sandbox.sh` and AGENTS.md

- `tests/test_hygiene.py:411-445` (`sandbox_unset_violations` and its plant rows) requires these
  anchors to occur **exactly once**: `'unset CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST '`,
  `'RCAC_SSH_HOST CLUSTER_MCP_USER_MAP '`, `'unset UV_ENV_FILE\n'` and `'export UV_NO_ENV_FILE=1\n'`.
  It also checks `^unset …` statements (continuations joined) and the regex
  `^export UV_NO_ENV_FILE=1$`. Nothing pins the trap, the `mktemp` line, comments or line numbers.
- `test_cli_drives_are_sandboxed` (`tests/test_hygiene.py:151`) parses `tests/*.py` only, never
  `bin/`. A helper placed in `tests/` would itself have to launch through `SANDBOX`, which is
  circular. A helper in `bin/` is unchecked (and is never in an sdist: `pyproject.toml:31`,
  `RECORDED` in `tests/test_sdist_hygiene.py:34`). `tests/mutants.py:5676` copies all of `bin/` into
  a case's repository; no mutation case plants into `bin/sandbox.sh` (`REPO_FILES`, `:59`).
- No test parses AGENTS.md's Throwaway environment. `AGENTS.md:1896` ("removes it on every exit
  path") and `:1904` ("a `mktemp -d` under `$TMPDIR`, removed by a trap") are free to change, and
  `:1386-1393`'s test_transports bullet ("the sandbox directory … has been removed") is prose. A new
  test module falls into the fourth suite command of the verify partition automatically
  (`tests/test_suite_parts.py:145`).

## 5. Sibling `skip-check-fence-gaps`

Its `tests/test_hygiene.py` diff has two hunks, at `@@ -696` and `@@ -741`. They cover the skip
check (`skip_violations`, `need_shell`/`need_git` as the only allowed skips) and its plant rows.
**It touches no sandbox test** (those sit at lines 72–200 and 405–560), so there is no textual
conflict with a `bin/sandbox.sh` change. The semantic coupling is that any new row this cycle adds
**may not skip** except through `conftest.need_shell` or `need_git`; the sibling tightens that to "the
single top-level definitions in `tests/conftest.py`". A row that needs `setsid` or `perl` must
therefore fail or run, never skip.

## 6. Login shells

zsh, tcsh, ksh and csh (`tests/conftest.py:88`, `tests/test_launch.py:926`) appear only as the
**command** inside the sandbox: `ssh_server.py:608` (`'/bin/sh', '-c', ENTER_HOME, self.shell`),
`test_site.py:884` (`[SANDBOX, shell, '-c', …]`) and `test_launch`'s wires. `['sh', str(SANDBOX), …]`
appears only in refusal fixtures that are never launched (`tests/test_transports.py:170`,
`tests/test_startup.py:246`). Every real caller execs the script directly, through its `#!/bin/sh`
shebang.

## Implications for the design

- **The wrapper stays a shell that waits on its command in the foreground.** It stays the session
  and group leader the caller made, keeps the EXIT/HUP/INT/TERM trap's synchronous removal (R3,
  `test_transports`' immediate glob), and never `exec`s the command away.
- **The command must stay in the wrapper's process group, with the real stdin and default
  INT/QUIT.** A plain `"$@" &` is out. A shim that reports its pid (`sh -c 'echo $$ >&3; exec "$@"'`)
  is fine in the foreground.
- **The watcher must close or redirect all of the wrapper's stdio** (`</dev/null >/dev/null 2>&1`)
  **and every other inherited fd.** A held pipe hangs groups A and C without bound, and costs group B
  2 × GRACE and its TERM path.
- **The watcher must leave the wrapper's process group and lose its parent link at once.** That
  means a new session, or at least a new pgid, plus a double-fork whose middle process exits
  immediately. Otherwise `group_alive` rows fail, `mcp` waits 2 s and kills it, and the
  `mutant-child-outlives-timeout` walk (ppid ∪ pgid) kills it before it removes anything.
- **Do not hand the command the pipe the watcher waits on.** Key the watcher on the wrapper (a pipe
  only the wrapper holds, opened after nothing else can inherit it) plus the command's pid. Otherwise
  the command's background jobs (`test_timeout_stop.py:306`) keep the directory alive.
- **Keep watcher state out of the sandbox directory, or out of HOME's view.** `find "$HOME"` in
  `test_cli` matches only `*.db`, but HOME is the user-visible contract (R7).
- **New external programs on the wrapper's path break `test_registry`'s `SANDBOX_NEEDS` row.** Use
  sh built-ins plus programs already listed, or absolute paths, and update that tuple deliberately.
  `setsid(1)` does not exist on macOS.
- **The wrapper may print nothing on stdout** and nothing run-dependent on stderr
  (`test_cli.py:298-300` compares stderr byte for byte).
- **Count the SIGKILL sources beyond the GOAL's list.** They include `subprocess.run` timeouts (the
  wrapper killed alone), `run_process`'s group KILL after TERM, and SSH signal requests for QUIT,
  USR1 and USR2, which are untrapped today.
- **Text that may change freely:** the trap line, the comments, and AGENTS.md's "removed by a trap"
  (`:1904`). Text to keep: the four `test_hygiene` anchors, each occurring exactly once.
