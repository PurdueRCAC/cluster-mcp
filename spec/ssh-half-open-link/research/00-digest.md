# Research 00 — Digest: ssh-half-open-link

Three briefs, fanned out because the fix lands in `core/executor/ssh.py`, a high-blast-radius path
(code-plan trigger 2). The silent-link fixture is test infrastructure (R7), so trigger 3's
adversarial review runs as well (PLAN §4). Each decision below resolves the briefs into one
recommendation.

- [`01-paramiko-silent-link.md`](01-paramiko-silent-link.md): keepalive, probes, the activity
  hook, and what `transport.close()` wakes (run, not only read; Paramiko 5.0.0, checked against
  3.2.0).
- [`02-call-paths-and-leftovers.md`](02-call-paths-and-leftovers.md): where each call may retry,
  what each tool leaves behind, and what the agent sees.
- [`03-tests-and-ci-budget.md`](03-tests-and-ci-budget.md): the fixture, fidelity, clocks, slack and
  the CI budget.

## Decisions

1. **Keepalive is no detector** (01 §1). `set_keepalive` sends `keepalive@lag.net` with
   want_reply false (`transport.py:1228`), resets its timer only on writes (`packet.py:349`), and
   through 10 s of stall in both proxy modes the transport stayed active and no write failed. It is
   not used.
2. **Silence is measured from the last inbound message of any kind, not from a probe's reply**
   (01 §5, 03 §2). Through a proxy limiting the link to 64 KiB/s, probe replies queued 12.7 s
   behind channel data. Every message counts as proof of life, the probe's `REQUEST_FAILURE`
   included.
3. **The activity hook is an instance wrapper on `transport.packetizer.read_message`**, installed
   when a connection is published (01 §3). `Transport.run` reads every post-handshake message at
   that one call site in 5.0.0 (`:2045`) and 3.2.0 (`:2129`). The wrapper misses only the read in
   progress when it is installed, so a priming probe is sent at once and is never judged; every
   judged probe is sent after it, so its reply (or anything before it) is seen. `transport_factory`
   (2.12+) would avoid the miss, but must be threaded through `_bounded` and every gateway hop;
   `packetizer_class` (3.4) is above the floor.
4. **A probe is a hand-built `MSG_GLOBAL_REQUEST` `keepalive@openssh.com` with want_reply true**,
   sent through `transport._send_user_message` (the route `_signal` already takes) from a sender
   thread that never judges, swallows every error and keeps at most one send in flight (01 §2).
   `global_request(wait=True)` has no timeout and replaces the `completion_event` that
   `start_client` and rekeys wait on; it is never used. Paramiko's server and sshd both answer an
   unknown want_reply request with `REQUEST_FAILURE` (01 §2, 03 §2).
5. **The rule, one connect bound B (`_bound(conn)`, 15 s by default) each way**:
   - a probe is due when nothing has been heard for B, or at once when a call starts reusing the
     connection (the poke), unless a judged probe is already out;
   - the link is dead when a judged probe has been out for B and nothing at all has been heard since
     it was sent.

   Detection then takes at most B after a call's start (R1: two bounds remain for the reconnect) and
   at most 2B plus a tick after the last message heard (R2, R3: 30 s of the 45 s). Both scale with
   `ConnectTimeout`, as the bound does (GOAL Q1).
6. **On death the monitor closes the dead connection's transports, outermost hop first**
   (01 §4). `close()` from another thread woke every wait measured within 0.1 s (`open_session`,
   every stage of the SFTP open, SFTP replies, `exec_command`, a `_collect` with no timeout, a
   `write_all` stuck on a full buffer with a second sender queued behind it, `_signal` holding
   `chan.lock`), and itself took at most 0.042 s. Closing the gateway hops first covers the one
   unmeasured case, a ProxyJump inner close blocked behind the gateway's stuck write.
7. **Loss is decided by state, never by exception type** (01 §4, 02). Waiters see `EOFError`,
   `SSHException` or `OSError`, and `get_exception()` hands the saved error to the first caller
   only. A failure is a loss when the monitor marked the connection dead, or the transport is not
   active (after `SETTLE` for Paramiko's own EOF path, as `_exec` does).
8. **Retry only where nothing has been sent that could act** (02 Q1): the session channel's open for
   a command, and the SFTP session's open (channel, subsystem, version exchange). There the call
   goes back to `_ensure_connected` with its own deadline. From an exec request, or an SFTP session
   that has opened, a loss is reported, never retried, so no command or write runs twice.
9. **A transfer cut short raises one `ConnectionError` subclass**, naming the host and saying the
   transfer may be partly made, with what each tool can leave (02 Q2, Q3). As an `OSError` it reaches
   `write_file`, `sbatch`'s `script_content`, `upload_file` and `download_file` with no tool change.
   `write` turns its place step's `-1003` into the same raise. `_reason` and `_discard` are skipped
   on a lost link: the probe would reconnect and name a filesystem cause, and the removes would
   fail on the dead session (02 Q4).
10. **The monitor has its own clock seam and thread name** (03 §3): never `ssh.time`, `_await` or
    `cluster-mcp-reconnect`, which the fake-clock rows patch and wait on. Its decisions are a pure
    function the unit rows drive with a fake clock; the loopback rows run in real time with
    `CONNECT_TIMEOUT` patched to 1.
11. **The fixture is a stall proxy in `tests/ssh_server.py`** (03 §1): `hold` stops reading and
    forwarding both ways without closing a socket (a dead path's full send buffer, 01 §5); new
    connections are held, so "host gone" reads `timed out` as a dead path does; `come_back()`
    forwards new connections; `rate` limits at the TCP level (the only row that catches a
    reply-only detector); the proxy's receive buffer is pinned to 16 KiB so an upload holds the
    write path below the 2 MiB window, and the R5 row asserts that precondition itself.
12. **Slack**: a call's end within its figure plus 1.0 s, measured from the moment the link goes
    silent; 2.0 s for a thread to end; measured times in every violation message (03 §3: the worst
    lateness alone at load 30–35 was 0.009 s).

## Contradictions resolved

- 01 suggested a quiet period Q with `Q + B ≤ 45`; 03 left it open. The plan takes `Q = B`: one
  figure, 2B for in-flight detection, a third of the bound to spare.
- 02 suggested bounding the SFTP open with `open_session(timeout=…)`; 01 showed the monitor's close
  wakes it. Both are taken: the channel opens get a timeout of at least B plus a second, so a dead
  link's close always comes first and a live server that never answers still fails as today.
- 02 offered two shapes for `write`'s place-step `-1003` (a tool branch, or a raise). The plan
  raises, so every file tool reports a cut transfer one way.
