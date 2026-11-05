# Research 03 — the mechanism, and a prototype of it

Where [`02`](02-term-delivery.md) leaves us: in every mode the program bash gets the deadline's
TERM and dies of it, while what it leaves behind may not have had TERM (non-root `delegate`), and
nothing sends KILL to a TERM-ignorer (`ssh`; `local` and root `delegate` when it holds no stream).

## Options weighed

| Option | Covers | Rejected because |
|---|---|---|
| Remote `timeout -k G` wrapper around the command | `ssh` | Keyed on the remote clock from the command's start, after the login initialisation, so its deadline lags the server's by login time, which R4 does not exclude. GNU `timeout` moves the command into a process group of its own (`setpgid` unless `--foreground`), which changes what TERM at the deadline reaches. It is not on macOS, where the suite runs. |
| A KILL `signal` request after `GRACE` | `ssh` only | sshd refuses it once the session's leader has exited (`s->pid = 0`), which is exactly when a TERM-ignoring child survives a top that died ([02](02-term-delivery.md)). |
| A second exec that kills the remote group | `ssh` only | Needs the group id on the wire, a further channel and round trip after the deadline, and a thread to stay inside R4's return bound; covers neither `delegate` case. |
| A PTY | `ssh` | sshd sends HUP to a PTY session on close, which is ignorable; a PTY merges stdout and stderr and breaks the separation contract (§3). |
| `run_process` always sends KILL after `GRACE` | `local`, root `delegate` | Fixes two settings of four; to keep R4's "no later than today" it needs a timer that outlives the call. A second mechanism beside one that covers all four adds decisions and mutants for nothing. |
| **A watchdog in the program** (chosen) | every mode | — |

## The watchdog

After the prologue, before the start sentinel, the program starts one process substitution and
holds its write end on descriptor 46:

```
trap '' TERM; exec 46>| >(exec >/dev/null 2>&1; read -r cluster_mcp_w || exit; read -r cluster_mcp_w || { kill -s TERM 0; command sleep 1; kill -s KILL 0; }); trap - TERM; printf '\n' >&46
```

(After the adversarial review the plan uses `/bin/sleep` instead of `command sleep`, which still
follows `PATH` and the hash table, and the prologue also resets job control, `+m`: PLAN §2, §7.)

(The first sketch had one `read` and `46>`. The prototype's full suite then failed
`test_a_profile_cannot_change_a_fixed_script`: a profile's `set -C` makes bash 3.2 refuse `>` onto
the `/dev/fd/62` path of the process substitution, the watchdog saw end of file at once, and it
TERMed every write. Hence `>|`, and an **arming line** the program writes once the descriptor is
open: end of file before it means the watchdog never got its pipe, and it exits without stopping
anything. A watchdog that cannot start fails safe.)

- **Trigger: the program's death.** After the arming line, `read` returns a second line only if
  the program wrote one; it sees end of file without one when the program bash has died (or exited)
  without writing it. The program writes that release line right after its end records, before
  `RERAISE`. So a call whose records
  were written never fires it, and nothing a completed command left running is signalled (R5).
- **What it does then:** TERM to its own process group (needed under a non-root `delegate`
  server, where only the program had TERM; a repeat elsewhere), `GRACE`, KILL to the group. Its
  group is the command's in every mode: no shell here has job control, so a process substitution
  stays in its parent's group.
- **TERM-proof from birth:** the program ignores TERM while forking it, so the child inherits the
  ignore with no window, then the program restores the default. `trap - TERM` also undoes a TERM
  trap or ignore a startup file left, so the program dies of the deadline's TERM.
- **It holds nothing of the call:** its stdout and stderr go to `/dev/null` at once (it is forked
  after the prologue has closed the parked descriptors 47–49 and 57–59), and its stdin is the pipe.
  If it held an output stream, a local timeout would wait for EOF and `run_process` would go to
  KILL, returning later than today (R4).
- **The command never holds descriptor 46:** the command's subshell closes it (`) 2>&59 59>&- 46>&-`),
  so no descendant keeps the pipe open and hides the program's death.
- **Bash 3.2 to 5:** process substitution, `read -r`, `kill -s NAME 0` and fixed descriptor numbers
  exist in bash 3.2 (no `{fd}` variables, no `coproc`). `command sleep` skips any function a
  startup file defined over `sleep` (the prologue unsets `command`, `kill`, `read`, `exec`,
  `printf` and `trap` functions already). The delay is `GRACE` rendered into the text
  (`format(GRACE, 'g')`), read at call time.

No change to `run_process`, `ssh.py`, `delegate.py`, the delegated argv or the wire. The program
text grows by about 160 bytes, which the caller's room inside the 98,154-byte program limit loses
(the documented figure is the program's and stays exact; research 06).

## Prototype

A detached worktree from `origin/develop` (`c2cf899`), at
`.worktrees/timeout-process-cleanup-prototype` beside the main checkout: the watchdog in
`launch.py` (+8 lines), a `signal` handler in `tests/ssh_server.py`, faithful `sudo` stand-ins in
`tests/conftest.py` ([04](04-test-fidelity.md)), and one test file of 21 rows: three shapes
(`tree`: a child and a grandchild; `ignores-holding`: the same under `trap '' TERM` while holding
the output; `ignores-none`: a TERM-ignoring child and grandchild with stdio on `/dev/null`) × local,
root `delegate`, non-root `delegate`, and `ssh` with each login shell (bash, zsh, sh, tcsh). Each
row runs with a 0.5 s timeout, writes its pids to files, and checks every pid gone at
`start + timeout + 2 × GRACE`.

**macOS, `/bin/bash` 3.2.57, CPython 3.14:**

| | local | delegate root | delegate non-root | ssh (any shell) |
|---|---|---|---|---|
| develop, `tree` | pass | pass | **fail** | pass |
| develop, `ignores-holding` | pass (KILL) | pass (KILL) | **fail** | **fail** |
| develop, `ignores-none` | **fail** | **fail** | **fail** | **fail** |
| watchdog, every shape | pass | pass | pass | pass |

Develop fails exactly where it leaves a process running (13 of 21 rows); the watchdog passes all
21. The return time is unchanged, as R4 asks: a local probe at a 1.0 s timeout returned in 1.00 s
(`tree`, `ignores-none`) and 2.00 s (`ignores-holding`, where `run_process` reads twice) on develop
and with the watchdog alike; the code that decides when `run` returns is untouched.

**Timing.** Time from the test's deadline estimate (`start + timeout`) until every pid was gone,
12 representative rows per run:

| Load | Rows | Min | Median | Max |
|---|---|---|---|---|
| quiet | 23 | 0.01 s | 1.005 s | 1.094 s |
| 20 CPU-bound processes on 10 cores | 24 | 0.01 s | 1.013 s | 1.055 s |

The KILL lands at `GRACE` (+ ≈ 5–90 ms) after the program's death; the bound is `2 × GRACE`, a
margin of about 0.9 s. A row that stops without KILL (`tree`) is gone in milliseconds. One quiet run
of seven had one row fail before its timing was logged, most likely a pid file not yet written
when the 0.5 s deadline came (a slow login); it did not recur in eleven more runs. The rows in the
plan write their pids first and use a 1.0 s timeout (PLAN §6).

**Not verified locally:** Linux bash 5.x (CI's) and RHEL 8's bash 4.4. The fork/exec and
process-substitution behaviour is old and stable, but bash 5.1 changed how process substitutions
are reaped; CI's runs are the evidence.

## Edges the mechanism changes or leaves

- **A program killed from outside** (not a timeout) now fires the watchdog too, so what it started
  is stopped within `GRACE`; AGENTS §3's recorded limit about such a launch over `ssh` gets
  narrower (research 06).
- **A command that handles TERM gets it twice** at the deadline in `ssh`, `local` and root
  `delegate` (the deadline's, then the watchdog's, milliseconds apart); a handler may run twice.
- **The login initialisation before the watchdog exists:** a startup file that ignores TERM and
  hangs is KILLed by `run_process` in `local` and root `delegate`, but over `ssh` and under a
  non-root server nothing reaches it after TERM. It is not one of "the command's processes" (the
  command never started), and its result is already an empty timeout (`test_a_profile_that_hangs_is_a_timeout`).
- **A watchdog killed before the line** (the command signalled it by pid): the program's write
  then raises SIGPIPE and the program dies after its records. The result is unchanged: the record,
  not the launch's status, is the command's (`separate`, `launch.py:345`).
- **A process that left the group** (`setsid`) is reached by nothing, as today (Q4).
- **An sshd that ignores the `signal` request**: the program never dies at the deadline, so the
  watchdog never fires. The measured OpenSSH acts on it ([01](01-login-node-measurement.md)).
