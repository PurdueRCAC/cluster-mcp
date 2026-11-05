# PLAN — Stop a timed-out command, and what it started, in every mode

> **Status:** Draft for review · **Last updated:** 2026-11-01
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

The bash program the launcher renders for every command, in every mode, starts a **watchdog**
after the login initialisation: a process substitution in the command's process group that
ignores TERM and waits on a pipe from the program. If the program bash dies before it has reported
its command's end (as it does when the deadline's TERM reaches it, in every mode), the watchdog
sends TERM to the group, waits `GRACE`, and sends KILL to it. The program writes a line to the pipe
after its end records, so a completed call never fires it. The deadline's TERM already reaches the
program bash in all four settings (sshd's `killpg` on the `signal` request; `run_process`'s
`killpg`; `sudo`'s relay), so one mechanism in `launch.py` closes the gaps, with no change to
`run_process`, `delegate.py`, the wire or the delegated argv, and no change to when `run` returns.
It runs as the command's own user, inside the `sudo` rule `SECURITY.md` documents, so R3 holds in
full: Q3's narrowing does not apply.

One case the watchdog cannot reach: over `ssh`, a login shell's own rc file (`.bashrc` for a bash
login shell, `.zshenv`, `.tcshrc`) that ignores TERM *before* the bootstrap runs. Bash cannot undo a
signal ignored at its entry, so the program never dies, and the command inherits the ignore. For it,
`ssh._collect` also asks for KILL once its `GRACE` read is over (sshd acts on it exactly while the
launch lives), as GOAL Q6 rules, with R5 amended for the one existing assertion it changes.

The rest of the work is test fidelity (the in-process SSH server acts on `signal` as sshd does; the
`sudo` stand-in relays as sudo does) and the documents. It fits `small`: about a dozen lines of
product code, four phases.

## 2. Design

### The watchdog (`packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py`)

`program()` (`launch.py:277`) gains one line right after `PROLOGUE`, before the start-sentinel line,
and one line between the end record and `RERAISE`; `SUBSHELL`'s close gains `46>&-`; `PROLOGUE`'s
option reset gains `m`. Each new piece is a named constant of its own (so the mutant anchors on
`record_line` and `RERAISE` keep applying), and the delay is `GRACE`, read when the program is
rendered:

```
WATCHDOG  trap '' TERM; exec 46>| >(exec >/dev/null 2>&1; read -r cluster_mcp_w || exit; read -r cluster_mcp_w || { kill -s TERM 0; /bin/sleep <GRACE>; kill -s KILL 0; }); trap - TERM; printf '\n' >&46
SUBSHELL  ( … ) 2>&59 59>&- 46>&-
RELEASE   printf '\n' >&46        (after record_line, before RERAISE)
PROLOGUE  … set +euxvTkPm …       (was +euxvTkP)
```

What each part decides (each is a mutant the sweep plants, §6):

- **Armed, then released.** The first line the program writes (at the end of `WATCHDOG`) *arms* it;
  the second (`RELEASE`, after the records, before `RERAISE`) *releases* it. End of file before the
  arming line means the watchdog's process started but the program never got the pipe on
  descriptor 46 (the noclobber case `>|` now avoids, or any other failure of that redirection): it
  exits and stops nothing, so a watchdog that cannot start never kills a command (fail-safe; a failed
  fork leaves no watchdog at all, which is safe too). No profile can produce that case through the
  real program (every program needs descriptors up to 59, so a descriptor limit that refuses 46
  breaks the launch on develop as well; checked on the prototype), so its row runs the watchdog's
  body alone. End of file after arming and before release means the program died with its command
  unreported: stop the group. A line after release means the call completed, whatever its status
  (an exit or a signal death the program re-raises after releasing): exit, signalling nothing (R5).
- **`>|`, not `>`.** A profile's `set -C` (noclobber) refuses `>` onto the `/dev/fd` path bash 3.2
  uses for a process substitution; the prototype's suite caught it
  (`test_a_profile_cannot_change_a_fixed_script`, research 03). On Linux the path is a pipe, which
  noclobber allows, so only macOS bash 3.2 tells `>` from `>|`; P3's sweep runs there.
- **TERM-proof from birth.** The program ignores TERM while it forks the watchdog (the child
  inherits the ignore, with no window), then restores the default. The restore also undoes a TERM
  trap or ignore that a startup file *the program bash reads* left (`.bash_profile`, `/etc/profile`);
  it cannot undo an ignore inherited at entry (the KILL request below covers that, Q6).
- **TERM, `GRACE`, KILL, to group 0.** With job control off (the prologue now resets `m`: a
  profile's `set -m`, or `monitor` in an exported `SHELLOPTS`, would put the command's subshell in a
  process group of its own, out of reach of both `run_process`'s `killpg` and the watchdog; found by
  the review), the watchdog is in the command's process group in every mode. The TERM is needed
  under a non-root `delegate` server, where `sudo` relays TERM to the program alone (research 02);
  elsewhere it repeats the deadline's (§3). `GRACE` after it is what lets a command that handles
  TERM finish printing ("captured … while the command stopped", R5); KILL then reaches every
  TERM-ignorer.
- **`/bin/sleep`.** Absolute, so neither a startup file's `sleep` function, a `PATH` without `/bin`,
  a `hash -p` entry nor a `~/bin/sleep` can shorten or stretch the wait (`/bin/sleep` exists on
  macOS, on RHEL and on merged-`/usr` Linux). The prologue already unsets `kill`, `read`, `exec`,
  `printf` and `trap` functions.
- **It holds nothing of the call.** Its stdout and stderr are `/dev/null` from its first command; it
  is forked after the prologue closed descriptors 47–49 and 57–59; its stdin is the pipe. If it held
  an output stream, a local timeout would wait for its EOF and `run_process` would go to KILL,
  returning later than today (R4).
- **The command never holds descriptor 46**: the subshell closes it, so a descendant cannot hide the
  program's death.

`harness.launched_script` finds the command after the sentinel line (`'\nexec '`, research 05 §3);
the watchdog line comes before the sentinel and starts with `trap`, so it is not mistaken for it.

### Over `ssh`: a KILL request after the `GRACE` read (GOAL Q6)

`ssh._collect` (`ssh.py:253-255`) sends `_signal(chan, 'KILL')` after
`_stopped`, before returning. It adds no wait (R4). sshd refuses it once the launch has exited
(`s->pid = 0`, research 02), which is the normal case, since the program dies of the TERM; it acts on
it exactly when the launch still lives, which is the TERM-ignored-at-entry case. Prototyped: the
`.bashrc` (bash) and `.zshenv` (zsh) rows that fail without it pass with it. It changes one existing
R5 assertion: `test_a_timeout_drains_what_follows_the_term` (`tests/test_ssh_exec.py:2763`) asserts
the signals sent are exactly `['TERM']` on a fake channel whose launch never exits; with the request
they are `['TERM', 'KILL']`, as R5 now allows (Q6). Three decisions, each swept (§6): that it is sent,
that it comes after the `GRACE` read (not before the TERM, not between the TERM and the read), and
that it names KILL. A new unit row, `test_a_timeout_asks_for_kill_after_its_grace`
(`tests/test_ssh_exec.py`, on the same fake channel), pins the names, the order and the KILL coming
at least `GRACE` after the TERM; the grace row `[ssh-bash]` pins it behaviourally (an early KILL
loses what the command prints while it stops).

### Unchanged on purpose

`run_process` (its TERM, read, KILL-if-not-EOF), `ssh._signal`/`_stopped` and the TERM request at the
deadline, `DelegatingExecutor` and the argv
`sudo -n -H -u <user> /bin/bash --norc --posix -c <stage> cluster-mcp <program>` (§5). So `run`
returns exactly when it does today (R4), and the result is what it is today (R5).

### Test infrastructure

- **`tests/ssh_server.py`** acts on the `signal` channel request as OpenSSH 8.0p1's
  `session_signal_req` does (research 04): a per-transport `MSG_CHANNEL_REQUEST` handler (Paramiko
  drops unknown requests), `killpg` of the exec's process group for HUP INT KILL QUIT TERM USR1 USR2,
  ignored before the process exists or once its `wait()` has returned, recorded in
  `server.signals`. The model's leader is `bin/sandbox.sh`'s bash, which outlives the program bash by
  milliseconds (it runs `"$@"` without `exec`), so its refusal comes slightly later than sshd's; no
  row depends on the gap (research 04). Its docstring's "the server does not kill the process"
  becomes what it now does.
- **`tests/conftest.py`**: `RELAY` relays TERM alone, with `os.kill` to the command's pid, as sudo's
  no-pty path does (it now relays TERM, INT and HUP by `killpg`); `ROOT_RELAY`, the same without a
  session of its own, stands in for a root server, with an import-time assertion that the two
  differ (a `replace` that no longer matches would silently make the root rows non-root);
  `Executions.server_root` picks it.
- **`tests/test_timeout_stop.py`** (new), importing only names that exist on develop, so the develop
  gate can run it there. Settings: `local`, `delegate-root`, `delegate` (non-root), `ssh-bash`
  (`ssh-zsh`, `-sh`, `-tcsh` behind `CLUSTER_MCP_TEST_EVERY_KIND=1`). Each shape's top `exec`s its
  last command, so every process of it has a pid file; teardown kills each recorded pid's process
  group (never the runner's own). Rows:
  - `test_a_timed_out_command_is_stopped[<setting>-<shape>]`: shapes `tree` (a child and a
    grandchild), `ignores-holding` (the same tree ignoring every catchable terminating signal,
    holding the output), and, for `local` and `delegate-root`, `ignores-none` (the ignoring child
    and grandchild with stdio on `/dev/null`). Each writes its pids first; the row checks every pid
    gone at `start + timeout + 2 × GRACE + SLACK`, fails with `still running … after the deadline`
    (or "not started before the deadline" when a pid file is missing), and checks `run` returned no
    later than develop does (`GRACE / 2` after the deadline where develop returns at once, `2 ×
    GRACE` elsewhere). (The signals asked for are pinned by the unit rows, not here: the stop rows
    also run against develop, which asks for TERM alone.)
  - `test_a_completed_command_leaves_its_jobs_running[<setting>]` and
    `test_a_command_that_dies_of_a_signal_leaves_its_jobs_running[<setting>]` (`kill -s USR1 $$`
    after starting the job): the job outlives the completed call by `2 × GRACE + SLACK` (no existing
    row checks this; research 05 §3; the signal variant from the review).
  - `test_a_stopping_command_gets_its_grace[<setting>]`: under a profile defining `sleep() { :; }`,
    a command that prints on TERM after 0.3 s has that output in its timed-out result.
  - `test_a_startup_file_ignoring_term_is_undone[<setting>-<file>]`: `delegate` and `ssh-bash` with
    a `.bash_profile` holding `trap '' TERM`, `set -C` and `set -m`; `ssh-bash` with `.bashrc` and
    `ssh-zsh` with `.zshenv` ignoring every catchable terminating signal (so a KILL request renamed
    to any other signal sshd accepts is caught too). The tree is still stopped.
  - `test_run_command_stops_a_timed_out_command`: the `ignores-none` check through the `run_command`
    tool on the in-memory server (`harness.call`), `local` mode: the real tool path.
- **`tests/test_launch.py`**: the launch checker's fixed copies gain the watchdog line, the `m` in
  the prologue, the `46>&-` close and the release line (and their planted cases);
  `test_the_watchdog_waits_grace` renders a program with `GRACE` patched to 2.5 and finds
  `/bin/sleep 2.5;`; `test_a_watchdog_that_cannot_start_stops_nothing` runs the watchdog's
  process-substitution body (taken from the constant) with its stdin already at end of file, in a
  session of its own beside a sleeping sibling, and finds the sibling alive `2 × GRACE` later.
- **`tests/mutants.py`**: re-anchor whatever the new text moves (`command-exec-in-place` on the
  `program()` join line; any prologue anchor that spans the `set` options), and add the sweep's cases
  (§6).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | The watchdog, triggered by sshd's `killpg` TERM reaching the program bash (research 02), and the KILL request for a launch that ignored TERM from its entry (Q6); pinned by the `ssh-*` rows against the sshd-faithful server model. The measurement (research 01) chose the design. |
| R2 | The watchdog in `local` and root `delegate`: KILL at `GRACE` whether or not a TERM-ignorer holds a stream; the prologue's `+m` keeps the command in the group; pinned by the `local-*` and `delegate-root-*` rows, `ignores-none` included. |
| R3 | The watchdog runs as the mapped user, inside the documented `sudo` rules (`NOPASSWD: ALL`, or for named users), and re-sends TERM to the group, so R3 holds in full; pinned by the `delegate-*` rows against a stand-in that, like sudo, is the only process the server can signal and relays TERM alone to one pid. |
| R4 | One delay, `GRACE`, after the program's death at the deadline: every process exits within `GRACE` + scheduling (measured max 1.09 s) of the deadline, inside `2 × GRACE`; stated in AGENTS §3. No code that decides when `run` returns changes (the KILL request adds no wait); the rows check the return time against develop's. |
| R5 | Arm/release protocol, release before `RERAISE`: a completed call's leftovers are never signalled, whether it exited or died of a signal (survival rows); result shape untouched; existing timeout tests unchanged and passing but for the one assertion Q6 rules (`verify/r5-timeout-tests-kept.py` allows exactly that one). |
| R6 | `tests/test_timeout_stop.py` per setting, pids checked gone after the bound; faithful stand-ins; `verify/develop-fails.py` proves each row fails on `c8843b2` where develop leaves a process running, and only for that reason. |
| R7 | AGENTS §2, §3, §5 and the footguns, README's timeout sentence, the docstrings and `issues/local-command-outlives-server.md`, in P1's commit with the code (list below, from research 06). No limit remains for a non-root server, so `SECURITY.md` needs no edit (R7's condition does not arise). |

### Documents that change (R7; research 06 has the line numbers and current text)

- AGENTS §3: replace "**A timed-out command may outlive the call**" with what is stopped (the
  command, its children and grandchildren, a TERM-ignorer, all in its process group), the bound (2 ×
  `GRACE` of the deadline, server clock, over `ssh` excluding the link's delay; may finish after `run`
  returns), and the limits: a process that left the group; over `ssh`, a server that does not act on
  the `signal` request; a startup file that hangs before the program starts, over `ssh` and under a
  non-root server; a TERM handler may run twice; a lost link (non-goal) — the limits linking
  `issues/timeout-stop-limits.md` (filed by this plan). Rewrite the recorded limit "a launch that dies
  before its records (killed from outside) … is held until the timeout" (now stopped within `GRACE`
  unless something left the group), and the outlives-server bullet's "only the call that launched a
  process group signals it". The "Nothing after the startup files depends on shell state they can
  change" bullet names job control among the options reset.
- AGENTS §2: one bullet for the watchdog (what every program starts, when it acts, that it prints
  nothing and holds no stream). §5: `sudo` relays the deadline's TERM to the launch only; the
  watchdog, running as the mapped user, stops the rest. The `launch.py` footgun's timeout sequence;
  the `ssh.py` footgun's (TERM, the `GRACE` read, KILL, close).
- README: the timeout sentence says the command and what it started are stopped within 2 × `GRACE`,
  and names what is not (a process that left its group; an SSH server that ignores `signal`).
- Docstrings: `launch.py` module, `GRACE`, `SUBSHELL`/end-line comments, `run_process` (the KILL it
  skips is now the watchdog's); `ssh._signal` ("deliver … to the command": sshd signals its group),
  and `_collect`'s; `base.Executor.run`'s Returns. No served text changes (`run_command`
  says nothing about stopping), so the surface fixture stays.

## 3. Invariant gate (AGENTS.md constitution check)

Checked before research (gate #1) and against this design (gate #2). Touched: §2, §3, §5 and the
high-blast-radius `launch.py` and `ssh.py`; research ran in full (trigger 2).
Untouched: §1, §4, §6–§9 (no served text changes, research 06).

- **§2, the launch.** Every command still runs as one program under `/bin/bash -l`; nothing a startup
  file prints reaches a result (the watchdog prints nothing; a failure to start it prints before the
  sentinel, which `separate` drops). The command's stdin stays empty and closed: the watchdog reads
  its own pipe, never the caller's stdin (a write's content stays on the parked stdin, read by the
  fixed script). The parked descriptors 47–49/57–59 are closed before the watchdog forks. The ssh
  program limit (98,154 bytes) is the program's and stays exact; the caller's room shrinks by the
  watchdog's ≈ 180 bytes (research 06). The three backends move together: none changes but `ssh`'s
  one request, which no Protocol member's signature sees.
- **§3, results and the timeout contract.** `TIMEOUT_EXIT_CODE`, the captured output, `LATE_NOTE`,
  `-N` for signal deaths and the reserved codes are unchanged; no raise. "A result is complete
  exactly when both end records have arrived": release follows the records, so a complete call is
  never signalled. The record, not the launch's status, is the command's status, so a program that
  dies of SIGPIPE writing its release line (the watchdog killed by pid) reports the same result.
  "Nothing after the startup files depends on shell state they can change": strengthened (`+m`). "No
  startup file … holds a call open": the watchdog holds no stream. The recorded limits change, as R7
  asks (§2 above). The KILL request is sent only at a timeout, after the read §3
  describes, so "a call whose end records both arrive before its deadline signals nothing" holds.
- **§5, delegate.** The argv, `-n`, `-H`, `/bin/bash` and the start in the mapped user's home are
  unchanged; everything the caller sent is still inside the one program argument. The watchdog runs as
  the mapped user and signals only its own process group, so it adds no privilege and needs no new
  `sudo` rule.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| A command that handles TERM gets it twice at the deadline in `ssh`, `local` and root `delegate` (the deadline's, then the watchdog's, milliseconds apart) | Under a non-root server the command gets no TERM at all unless the watchdog sends it (sudo relays to the program alone, research 02); one program text for every mode keeps one mechanism | A mode flag rendered into the program (re-send TERM only under a non-root server) needs `program()` to take a mode and `DelegatingExecutor` to detect root, adding a decision per backend and a mode-dependent program to a high-blast-radius file, for a repeat a handler mostly merges with the pending one. Recorded as a limit with a seed. |
| Every program starts one extra process (the watchdog), completed calls included | Only a process inside the group that outlives the program can stop the group after the program dies, in every mode | A server-side timer (`run_process` always KILLs after `GRACE`) covers `local` and root `delegate` only, and needs a thread outliving the call to keep R4's return time. The watchdog costs one fork and two `read`s, and exits with the call. |
| The prologue also turns job control off (`+m`) | A profile's `set -m` would put the command in a group of its own, out of every signal's reach (review M1) | Leaving it: R2 and R3 would fail under such a profile, as develop does today. The reset joins the options the prologue already resets for the same reason. |
| Over `ssh`, a second `signal` request (KILL) after the `GRACE` read, in `ssh.py` (high blast radius) | A TERM ignored from the launch's entry (a remote login shell's rc file) leaves the program alive, so the watchdog never fires; only sshd's `killpg` while the launch lives reaches that group (review H1) | Recording it as a limit narrows R1; a second exec that kills the remote group adds a wire change, a round trip and a thread. GOAL Q6 ruled for the request, amending R5 for the one assertion it changes. |

Read against the R-IDs each touches: row 1 — R5 ("a call whose end records both arrive before its
deadline signals nothing": the repeat happens only at a timeout), R2/R3/R4 (it is before the KILL;
the bound holds). Row 2 — R4 ("`run` SHALL return a timed-out call no later than it does today": the
watchdog holds no stream, and the rows check the return time), R5 (release before exit: no signal).
Row 3 — R5 (the result contract: job control changes no result), R2/R3 (it is what keeps them true).
Row 4 — R4 (no wait is added: it is sent after the read `run` already does), R5 as amended by Q6
("except that `test_a_timeout_drains_what_follows_the_term` asserts the `signal` requests sent at a
timeout as `['TERM', 'KILL']`": exactly the change the R5 gate allows; and it is sent only at a
timeout, so a complete call signals nothing), R1 (it is what makes R1 hold there). None changes what
an R-ID SHALL do as the GOAL now words it.

## 4. Rabbit holes (resolved)

- **Who delivers TERM to the group over ssh?** sshd: `session_signal_req` calls `killpg(s->pid, sig)`
  for the session's process, which `setsid()`ed and which the bootstrap `exec`s into the program bash;
  the server's remote code has no TERM handling. sshd refuses once that process has exited
  ([`02`](research/02-term-delivery.md)).
- **What does sudo relay?** TERM, with `kill` to the command's pid (the program bash), from no-pty
  sudo whose command stays in sudo's group; KILL never ([`02`](research/02-term-delivery.md)).
  Unverified on the cluster's sudo version; the design needs only that some TERM reach the program.
- **Which mechanism?** Five weighed and rejected as the mechanism (`timeout -k`, a KILL request alone,
  a second exec, a PTY, a `run_process` timer); the watchdog chosen
  ([`03`](research/03-mechanism-and-prototype.md)). The KILL request returns as a complement for the
  one case the watchdog cannot see (Q6).
- **Does it work in bash 3.2, and is it fast enough?** Prototyped on macOS bash 3.2: every row of the
  new module passes; on develop's code each row fails exactly where develop leaves a process; time to
  gone after the deadline: median 1.01 s, max 1.09 s, quiet and under 20-way CPU load
  ([`03`](research/03-mechanism-and-prototype.md)). The prototype's full suite found the noclobber
  failure (→ `>|`) and the fail-unsafe start (→ the arming line). A first sweep of nine watchdog
  mutants on the prototype: all nine killed by the planned rows.
- **Are the stand-ins faithful?** No, before this cycle: the SSH model ignored `signal` (less than
  sshd) and `RELAY` relayed by `killpg` (more than sudo). Both corrected and checked against trials
  A–D ([`04`](research/04-test-fidelity.md)).
- **What breaks in the suite?** The launch checker's fixed copies, `command-exec-in-place`'s anchor,
  and nothing else; no existing timeout row changes outcome
  ([`05`](research/05-tests-and-budget.md); prototype run: 4,524 passed, 36 failed, all of them the
  checker and anchor rows, plus the noclobber row since fixed). With the KILL request, also
  `test_a_timeout_drains_what_follows_the_term`'s signal assertion (the R5 gate caught it on the
  prototype; ruled by Q6).
- **Which docs become false?** [`06`](research/06-docs-sweep.md).
- **Adversarial review:** §7.

## 5. Risks & open questions

- **Q6 (raised here as OQ1, ruled (a) on 2026-11-01).** A remote login shell's rc file that ignores
  TERM before the bootstrap is reached by the KILL request; R5 amended for the one assertion it
  changes. Not ruled away: a server that ignores `signal` reaches neither (a recorded limit).
- **Linux bash 5.x and RHEL bash 4.4 are unverified locally** (bash 5.1 changed process-substitution
  reaping; the review read bash 5.2's source and found it consistent with the design). CI's two era
  jobs run the rows on ubuntu's bash 5; the profile's `ci` check before the `squash-local` landing
  reads that run, so a bash-5 difference stops the landing, not the build.
- **Wall-clock rows on a loaded runner.** The KILL lands ≈ 1.0–1.1 s after the deadline; the check is
  at 2.5 s (`2 × GRACE + SLACK`, `SLACK = 0.5`), and a pid file not written by the deadline fails as
  "not started before the deadline", not as a stop failure, with the timeout at 1.0 s (the prototype
  saw one such miss in seven runs at 0.5 s; none in eleven more). The rows check pids gone, never a
  callback's time. A CI flake here gets a note on `issues/stalled-reconnect-test-timing.md`, which
  holds the suite's other two.
- **Recorded limits, deferred** to [`issues/timeout-stop-limits.md`](../../issues/timeout-stop-limits.md)
  (filed with this plan, with its `ROADMAP.md` entry): an SSH server that ignores `signal`; a startup
  file that hangs before the watchdog; the double TERM; a TERM that lands in the microseconds between
  the program's `trap '' TERM` and `trap - TERM` (lost; over `ssh`, and locally, the server's KILL
  still reaches the live launch; under a non-root server it does not); a profile's `enable -n` of
  `kill`, `read` or `trap`, which disarms the watchdog.
- **sudo with a PTY** (a site with I/O logging) is unmodelled; the watchdog keys only on the
  program's death, so it is believed to hold. Stated in research 04; not graded.
- **A program killed from outside** (not a timeout) now has its group stopped within `GRACE` too: a
  behaviour change for the better, documented in §3's recorded limit.
- The prototype worktrees (`.worktrees/timeout-process-cleanup-prototype`, and its P1 cut
  `.worktrees/timeout-process-cleanup-p1cut`, both detached at develop `c2cf899`) are removed after the
  PLAN/TECH sign-off.

## 6. Verification strategy

Each phase's `verify:` runs the narrowed suite and the cycle's gates (`spec/timeout-process-cleanup/verify/`):

- **`r5-timeout-tests-kept.py`**: every test named `*timeout*` in the three files R5 names, and every
  module-level name they reach (functions, classes, constants, followed transitively, across `from
  test_x import` too), is AST-identical to `c8843b2`'s; the rows they collect are the same set as at
  `c8843b2` (collected in a scratch copy of that tree); every row passes. ≈ 25–40 s. It allows
  exactly one difference, Q6's: that test may hold `['TERM', 'KILL']` in its signal assertion, its
  text otherwise `c8843b2`'s. Shown red on the prototype for a changed result assertion in that test,
  reordered or reduced signals, a loosened TERM time, a weakened `_gone` in `test_launch.py`, a
  dropped bound in `timeout_violations`, a shrunk `LOGIN_SHELLS`, and the `c8843b2` text left in
  place while the code asks for KILL; green on the ruled text.
- **`develop-fails.py local|ssh|all`**: a scratch copy of the tree with `packages/` from `c8843b2`
  runs the stop module; each row where develop leaves a process must fail with `still running`, and a
  control set must pass (the copy really ran: it pins the stand-ins from both sides). ≈ 20–60 s per
  mode, the cached sync included.
- **The mutation sweep** (P3, a phase of its own so its gate stays well under the 10-minute cap;
  the login-shell matrix and the ledger follow in P4), each decision of §2 planted to every alternative it could take, with
  the rows that must kill it: watchdog dropped; arming dropped; release dropped; release before the
  command; release after `RERAISE` (the signal-death survival row); `||` inverted; the first read's
  `|| exit` turned into a stop (the cannot-start row); TERM dropped; TERM → INT, HUP; KILL → TERM,
  HUP, STOP; group `0` → `$$`; delay → `0`, `2 × GRACE`, a fixed `1`; `/bin/sleep` → `sleep`; `46>&-`
  dropped; the watchdog's `/dev/null` dropped (holds output); ignore-at-fork dropped; restore dropped;
  `>|` → `>`; `m` dropped from the prologue; the KILL request dropped, sent before the TERM, sent
  between the TERM and the `GRACE` read, and named TERM, HUP, INT, QUIT, USR1, USR2 or STOP (sshd
  refuses the last) instead of KILL. A delay of `2 × GRACE` is killed by the text test, not a
  wall-clock row (it lands on the bound itself).
- Representatives run in the suite (≈ 80 s per era: 21 rows measured at 62 s, and 6 more from the
  review at ≈ 3 s each); the full login-shell matrix runs behind `CLUSTER_MCP_TEST_EVERY_KIND=1` in
  P4's gate (≈ +35 s). Each CI era job grows from ≈ 8.5 min to ≈ 10 min of its 20.
- `publish` runs the profile's full `verify` (both eras, `uv lock --check`, the sandboxed CLI help).

## 7. Adversarial review

Trigger 3 fired (the new rows and two gate scripts are R6's instrument; the stand-ins are test
infrastructure). One fresh reviewer, given the GOAL, this design, the drafted gates and the prototype
(on a scratch copy), ran probe rows against it. What it found and what changed:

- **HIGH, H1** — a TERM ignore set by a remote login shell's own rc file before the bootstrap
  survives into the program bash, which cannot undo it; over `ssh` nothing was stopped (`.bashrc`,
  `.zshenv`, measured). The planned startup-file row used `.bash_profile`, where the undo works.
  → The KILL request after the `GRACE` read fixes it on the prototype, but the R5 gate then caught
  it changing an existing assertion; raised as OQ1, ruled (a) by the GOAL's Q6, R5 amended. Rows
  for `.bashrc` and `.zshenv` added, and a unit row for the KILL's order.
- **MEDIUM, M1** — a profile's `set -m` puts the command in its own process group (`local`
  measured: nothing stopped; develop alike). → `+m` in the prologue; the startup-file profile sets
  `-m`; mutant `tpc-monitor-kept`.
- **MEDIUM, M2** — survival was pinned only for a command that exits 0; releasing after `RERAISE`
  would stop a signal-killed command's jobs. → the signal-death survival row and
  `tpc-release-after-reraise`.
- **MEDIUM, M3** — the R5 gate's helper list missed `test_launch.py`'s `_gone`, `_reap`,
  `_sandboxed`, `run_on`, classes and module constants (`LOGIN_SHELLS`), and needed only one row per
  test. → transitive comparison of every module-level name the tests reach, and the collected row
  set compared with `c8843b2`'s.
- **LOW** — shapes left the top's last `sleep` unrecorded (→ `exec`, teardown by group); `command
  sleep` still followed `PATH` and the hash table (→ `/bin/sleep`); the TERM-ignore window and
  `enable -n` (→ recorded limits); `ROOT_RELAY` could silently equal `RELAY` (→ an assertion);
  `develop-fails.py` read a failure with a teardown error as an error (→ any `<failure>` counts);
  `>|` vs `>` differs only on macOS (→ noted); the SSH model's refusal keys on sandbox.sh (→ research
  04 corrected).
- **Found sound:** `develop-fails.py` runs develop's code (the copy's workspace members install
  editable from the copy's own `packages/`); `still running` cannot match by accident; bash 5.2's
  source agrees with the design (procsub fd closed after `exec`, the watchdog stays in the shell's
  group, a `trap ''` ignore survives into the child); `holds-output`, `fd-left-open`,
  `ignore-at-fork-dropped` and `restore-dropped` die on the planned rows.

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
