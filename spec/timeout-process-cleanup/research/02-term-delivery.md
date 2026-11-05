# Research 02 — who delivers the deadline's TERM, in each mode

Read from this tree (`c8843b2`) and from the public sources of OpenSSH (`session.c` at tag
`V_8_0_P1`, the measured version) and sudo (`src/exec.c`, `src/exec_nopty.c` on its main branch).

## `ssh`: sshd, acting on the `signal` request — not the server's remote wrapper

**The client side.** At the deadline `_collect` sends one `signal` channel request for `TERM`
(`ssh.py:253`, built by `_signal`, `ssh.py:162`), reads for `GRACE` (`_stopped`, `ssh.py:203`),
returns, and `_exec` closes the channel (`ssh.py:994`). No KILL request follows.

**The remote wrapper does nothing with signals.** The exec string is `BOOTSTRAP` + one base64 word
(`launch.py:197`): the login shell `exec`s a POSIX bash that decodes the program and `exec`s the
login bash on it (`STAGE`'s shape, `launch.py:189`). Every step is an `exec`, so the program bash
*is* the process sshd forked for the session. The program text (`program()`, `launch.py:277`) has
no `trap` on TERM and no `kill` of a group: `PROLOGUE` (`launch.py:139`) resets
`EXIT ERR DEBUG RETURN` traps, and the only `kill` is `RERAISE`'s on `$$` after the end records
(`launch.py:180`). So nothing remote relays TERM to the group.

**sshd does.** OpenSSH 8.0p1 `session.c`:
- `do_exec_no_pty`: the forked child calls `setsid()` before it runs the user's shell, so the
  session's process is the leader of a new session and process group.
- `session_signal_req`: maps the name through `name2sig` (`HUP INT KILL QUIT TERM USR1 USR2`, and
  `INFO@openssh.com` where defined; anything else is refused), refuses when `s->pid <= 0`, refuses
  a forced-command or subsystem session, requires privilege separation, and then, as the session's
  user, calls **`killpg(s->pid, sig)`**.
- `session_close_by_pid` sets `s->pid = 0` once the session's process has exited, so a `signal`
  request after that is refused: **sshd can signal the group only while its leader lives.**
- `session_close_by_channel` sends no signal when a channel closes with a live child.

This matches the measurement exactly ([`01`](01-login-node-measurement.md), trial D: a process
outside the command's descendants but in its group got TERM; trial C: nothing else arrives).

**Consequence for the design.** A KILL `signal` request after `GRACE` would reach the group only
while the program bash lives. With a TERM-ignoring child and a top that dies on TERM (the common
shape) the leader is gone at once, and sshd refuses the KILL. A client-side KILL request is
therefore not a mechanism on its own; the stop has to happen on the remote side, by a process in
the group that outlives the leader.

## `local`, and `delegate` under a root server: `run_process`

`run_process` starts the launch in a new session (`launch.py:589`), so the launch is the group
leader, and at the deadline it sends `killpg(TERM)`, reads for `GRACE`, then `killpg(KILL)` only if
the output has not ended (`launch.py:602-610`, the `pipes.eof()` break at `:609`). A TERM-ignoring
process that holds neither stream is never killed.

Under a root server the group is `sudo`'s: sudo's no-pty path (`exec_nopty.c`) makes no
`setpgid`/`setsid` call for the command, so the command stays in sudo's process group, and root's
`killpg` reaches every member. (`exec.c`'s only `setpgid(0, 0)` is on the background path, `-b`,
which the delegated argv does not use. `sudo_needs_pty` asks for a pty when `use_pty` is set, but
without `/dev/tty`, as in a new session, and with no I/O-logging plugin, sudo runs without one.)

## `delegate` under a non-root server: sudo relays TERM to one pid

A non-root, sudo-capable service account can signal `sudo` (its real uid) but not the command
(every uid is the mapped user's), so the server's `killpg` reaches `sudo` alone. sudo's
`signal_cb_nopty` then forwards the signal with **`kill(ec->cmnd_pid, signo)`**, to the command's
pid only, not its group. It skips a signal sent by a process in the command's group or sudo's own
(`si_pgrp == ec->cmnd_pid || si_pgrp == ec->sudo_pid`); the server is in neither. `cmnd_pid` is the
stage bash, which `exec`s the login bash running the program: **the program bash gets TERM; the
command's subshell, and everything it started, do not.** KILL cannot be caught, so it is never
relayed; killing `sudo` orphans the command.

So under a non-root server develop does less than its docs say ("`sudo` relays TERM only to the
command", AGENTS §3): TERM reaches the *program*, not the command, and a command that does not
ignore TERM survives too. The test stand-in for `sudo` (`tests/conftest.py`, `RELAY`) relays with
`killpg` and also relays INT and HUP, which is more than sudo does; R6 asks it to be faithful
([`04`](04-test-fidelity.md)).

Caveat: the sudo sources read are its current ones; the cluster's distribution build is older.
The no-pty relay by `kill` on the command's pid is believed long-standing but is **[unverified on
the target version]**. The design does not depend on it: it needs only that *some* TERM reach the
program bash, which holds whether sudo relays by `kill` or by `killpg`.

## Summary

| Mode | Who sends TERM at the deadline | What it reaches | KILL after `GRACE` |
|---|---|---|---|
| `ssh` | sshd (`killpg`), on the client's `signal` request | the session's whole group | none |
| `local` | `run_process` (`killpg`) | the launch's whole group | only if output has not ended |
| `delegate`, root | `run_process` (`killpg`); sudo also relays to the program | sudo's whole group | only if output has not ended |
| `delegate`, non-root | `run_process` signals sudo; sudo relays (`kill`) | the program bash alone | reaches sudo alone; the command is orphaned |

In every mode, **the program bash receives TERM at the deadline and dies of it.** That is the one
event a uniform mechanism can key on.
