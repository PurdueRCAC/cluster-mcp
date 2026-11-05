# Research 04 — do the host-free stand-ins behave like sshd and sudo?

R6 grades R1–R3 on tests with no real host, `sudo` or network, so each stand-in has to do at the
deadline what the real component does, no more and no less. A stand-in that does more (signals a
whole group where the real one signals one pid) lets a fix pass that fails on a host.

## The in-process SSH server (`tests/ssh_server.py`) today does less than OpenSSH

Paramiko 5.0.0's server side drops every channel request it has no case for
(`paramiko/channel.py`, `_handle_request`, the final `else`: "Unhandled channel request"), and
`signal` is one of them. So `LoopbackSSH` ignores the client's TERM: a timed-out command there is
never signalled, and lives until it next writes into the closed channel or `server.close()` KILLs
its group at teardown (`ssh_server.py:483-490`). Against the measurement
([01](01-login-node-measurement.md)) that is unfaithful in the direction that hides nothing for
develop (develop looks worse than on a host, where sshd stops a tree that does not ignore TERM),
but it would make any fix keyed on the deadline's TERM fail where a host would pass.

**The model** (prototyped): each server-side transport gets its own channel-request handler
(`Transport._channel_handler_table` is a class dict Paramiko reads through the instance, so an
instance copy overrides it for that server's transport alone; the client's transport, in the same
process, is untouched). The handler saves the message position, reads the request name, and for
`signal` reads `want_reply` and the name and hands them to the server; any other request is
rewound and passed to `Channel._handle_request`. The server then does what `session_signal_req`
does ([02](02-term-delivery.md)):

| sshd 8.0p1 | The model |
|---|---|
| `name2sig`: HUP INT KILL QUIT TERM USR1 USR2; others refused | the same table; others ignored |
| `s->pid <= 0` (no process yet, or it has exited) → refused | no process mapped to the channel yet, or its `wait()` has returned → ignored (`proc.poll()` reads `None` while the execute thread waits) |
| `killpg(s->pid, sig)` as the session's user | `os.killpg(proc.pid, sig)`; the test's user is the session's |
| the session's process called `setsid()` | `proc` is started with `start_new_session=True` |
| nothing on channel close | unchanged: closing a channel signals nothing |

It records each request's name (`server.signals`), so a row can assert that exactly one `TERM` was
asked for, as trial C saw.

**One difference that does not matter here** (sharpened by the adversarial review). Under sshd the group's leader is the login shell,
which the bootstrap `exec`s into the program bash; in the model the leader is `bin/sandbox.sh`'s
bash, with the login shell its child. sandbox.sh traps TERM (to remove its directory) and exits
when its child does, so the model's "leader has exited" comes a few milliseconds after sshd's.
The client sends one request, at the deadline, while both leaders live, so the refusal rule is
never exercised by this fix; it is modelled so that a later KILL request could not pass in tests
and fail on a host.

**Shapes the model reproduces:** trial A (a tree that does not ignore TERM stops: develop passes
the `tree` row), trial B (a TERM-ignoring tree runs on: develop fails both `ignores-*` rows, with
every login shell), trial C (one TERM, nothing else), trial D (TERM reaches every member of the
group, whoever its parent: `killpg`).

The four existing `ssh` timeout rows (`test_ssh_exec.py:164`) keep passing under the model (their
`sleep 30` now stops at the deadline instead of at teardown); research 05 §1.

## The `sudo` stand-in (`tests/conftest.py`, `RELAY`) today does more than sudo

`RELAY` starts the command in a session of its own (so the server's `killpg` reaches the stand-in
alone, as a non-root server's reaches `sudo` alone: faithful) and relays TERM, INT and HUP **with
`os.killpg` to the command's whole group**. Real sudo's no-pty path relays with `kill` to the
command's pid ([02](02-term-delivery.md)), and only signals sent to sudo itself, which at a timeout
is TERM, then KILL (which it cannot catch). R6: the stand-in SHALL "be the only process the server
can signal and pass on TERM alone".

**Non-root stand-in** (prototyped): unchanged start (`start_new_session=True`); relays **TERM
only**, with `os.kill(child.pid, …)`; re-raises the command's death signal on itself as before.
Against it develop fails even the `tree` row, as a real non-root server would leave the command's
tree running.

**Root stand-in** (new, for R2's "`delegate` mode by a server running as root"): the same script
without the new session, so the command stays in the stand-in's group, as sudo's no-pty command
stays in sudo's, and the server's `killpg` reaches every member, as root's does. Selected per test
by an attribute of the `executes` fixture (`server_root`).

No existing row depends on RELAY's INT or HUP relay or its `killpg` (research 05 §1); the one
existing delegate timeout row (`test_executors.py:240[delegate]`) passes under the faithful
stand-in with the watchdog, and would fail under it without (its `$$` is the script's bash,
which only the watchdog's TERM reaches).

## Limits of the stand-ins

- Neither models uid permissions: the test's processes all share one uid. The non-root case is
  modelled by group separation, which is what the permission rule produces for `killpg`; the
  watchdog's own `kill 0` runs as the mapped user in reality and reaches only that user's
  processes, which is every process of the command.
- sudo with a PTY (a site with I/O logging) is not modelled; there the command gets a session of
  its own under a monitor process. The watchdog still keys only on the program's death, so it is
  believed to hold; a documented assumption, not a graded setting.
