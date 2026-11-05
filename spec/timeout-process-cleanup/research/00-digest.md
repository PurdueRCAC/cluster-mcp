# Research digest — timeout-process-cleanup

Six briefs, 2026-11-01. Trigger 2 fired (the change touches `core/executor/launch.py`, a
high-blast-radius path), so research ran in full despite `kind: fix`, `appetite: small`; trigger 3
fired too (the new rows and two gate scripts are R6's instrument), so the design had an adversarial
review (PLAN §7). Briefs 01–04 were written by the planner (01 from the foreman's login-node
measurement); 05 and 06 by research workers.

| Brief | Question | Answer |
|---|---|---|
| [01](01-login-node-measurement.md) | What does a login node do at a timeout today? | TERM reaches the command's whole process group at the deadline; nothing follows it; a TERM-ignoring tree runs on, re-parented to init. |
| [02](02-term-delivery.md) | Who delivers that TERM, in each mode? | Over `ssh`, sshd (`session_signal_req` → `killpg` of the session's group, refused once the leader has exited), not the server's remote code. Locally, `run_process`'s `killpg`. Under a non-root `delegate` server, sudo relays TERM with `kill` to the program bash alone. In every mode the program bash gets TERM and dies of it. |
| [03](03-mechanism-and-prototype.md) | Which mechanism, and does it work? | A watchdog in the program, keyed on the program's death: prototyped on bash 3.2, every row passes; develop fails exactly where it leaves a process; time to gone ≈ `GRACE` (max 1.09 s, loaded). |
| [04](04-test-fidelity.md) | Are the stand-ins faithful? | Not yet: the SSH model ignores `signal` (less than sshd), `RELAY` relays by `killpg` and relays INT and HUP (more than sudo). Corrected models designed and prototyped. |
| [05](05-tests-and-budget.md) | What do the tests and CI budget say? | No existing timeout row changes outcome; the launch checker's fixed copies and one mutant anchor move; no row checks that a completed command's job survives (one per mode is added); ≈ 60 s per era. |
| [06](06-docs-sweep.md) | Which statements become false? | AGENTS §3's "may outlive the call", the killed-from-outside limit and the outlives-server bullet; incomplete in §2, §5, the footguns, README and the docstrings; `SECURITY.md` and the served surface stay. |

## Decisions, and the contradictions resolved

1. **The mechanism is the watchdog**, in `launch.py` only. Rejected: a remote `timeout -k` (own clock,
   own process group, absent on macOS), a KILL `signal` request (sshd refuses it once the leader has
   died, which is exactly the TERM-ignoring-child case), a second exec, a PTY, and a `run_process`
   timer (two settings of four). (03)
2. **Arm, then release.** The prototype's full suite found that a watchdog that cannot
   open its descriptor (a profile's `set -C` refuses `>` onto bash 3.2's `/dev/fd` path) saw end of
   file at once and killed every command. Resolved two ways: `>|`, and an arming line, so a watchdog
   that never got its pipe stops nothing. The planner's first sketch (one line, after the records)
   is superseded.
3. **The prologue's `trap -` list stays as it is.** Brief 05 analysed adding `TERM` to it (which
   breaks the `startup-traps-kept` anchor). The watchdog line's own `trap - TERM` already undoes a
   startup file's TERM trap or ignore, so the prologue is untouched.
4. **The release line is a constant of its own** between `record_line` and `RERAISE` (05: keeps the
   `end-record-one-stream` and `signal-death-not-reraised` anchors), and the watchdog line starts with
   `trap`, before the sentinel (05: `harness.launched_script` reads `'\nexec '` after the sentinel).
5. **The watchdog re-sends TERM to the group in every mode.** Needed under a non-root server (02);
   elsewhere a repeat. Accepted as a deviation and a recorded limit rather than a mode flag (PLAN §3).
6. **R3 holds in full; Q3's narrowing does not apply.** The documented `sudo` rules allow any command
   as the mapped users (06), and the watchdog runs as that user (02, 03).
7. **The stand-ins change with the fix:** the SSH model gains sshd's `signal` handling; `RELAY` relays
   TERM alone to one pid; a root stand-in keeps the command in its group. The one existing delegate
   timeout row passes under the new stand-in only with the watchdog, so both land in P1 together. (04, 05)
8. **No new sandbox-directory leak**: in every setting the program bash is sandbox.sh's child (or the
   stand-in's), so sandbox.sh has had TERM and run its trap long before the watchdog's KILL; the ssh
   timeout rows stop leaking one each. (05 §6; `issues/sandbox-dirs-left-on-kill.md` unchanged)
9. **Budget**: representatives ≈ 60 s per era (measured 57.7 s for 20 rows); the login-shell matrix
   behind `CLUSTER_MCP_TEST_EVERY_KIND=1`. (03, 05)
10. **The adversarial review** (PLAN §7) added `+m` to the prologue, `/bin/sleep`, a signal-death
    survival row, a transitive R5 gate, and found that a remote login shell's rc file ignoring TERM
    before the bootstrap defeats the watchdog over `ssh`. The KILL request after the `GRACE` read that
    fixes it changed an R5-frozen assertion, so it went to the GOAL as OQ1; ruled (a) as Q6, R5
    amended for that one assertion. P3's sweep plants its presence, order and name.
11. **Deferred**: a startup file that hangs before the watchdog (over `ssh`, non-root `delegate`), an
    SSH server that ignores `signal`, the repeated TERM: `issues/timeout-stop-limits.md`. (03, 06)
