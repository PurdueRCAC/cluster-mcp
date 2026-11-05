# PLAN — A dead SSH link that still reads as connected is noticed within a bound

> **Status:** Signed off at the PLAN/TECH gate with the foreman's rulings (Deviations 1 and 2 accepted; Deviation 3 amended to the split verdict, §2.1) · **Last updated:** 2026-11-05
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

Each published connection gets a liveness monitor. It records when every message arrives from the
peer, sends a probe (a global request that both sshd and Paramiko's server answer) when nothing has
been heard for one connect bound, and at once when a call starts reusing the connection. When a
probe has been out for one connect bound with nothing at all heard since, the link is dead: the
monitor closes the connection's transports, which wakes every wait of every call within 0.1 s.
Calls then read the closed transport as any noticed loss does. A call that had sent nothing goes
back to the existing reconnect, inside its own deadline. A command in flight reports
`CONNECTION_LOST_EXIT_CODE`. A transfer in flight raises an error naming the host that says the
transfer may be partly made.

The verdict is split by who is waiting. A probe a call's start sent is judged after one connect
bound (B): only R1 has to leave room for a reconnect, and it leaves `2B − FINAL_ATTEMPT_LEAD` to
start one (28 s by default). A background probe, sent after B of quiet with no call starting, is
judged after `2B − VERDICT_MARGIN` (29 s by default). Nothing reconnects after an in-flight call
ends, so that call needs only to end within the bound after the link went silent: at most 3B −
0.55 s. Both sit inside the reconnect bound and scale with it (Q1). Nothing that is merely quiet is cut, since any message proves the link live, a probe's reply
included (R4).

The change is centred on `core/executor/ssh.py`, plus a stall proxy in `tests/ssh_server.py` and
the documents R6 names. Three phases: commands, transfers, then the sweeps. The fix is small in
code, but it sits on a high-blast-radius path, and the sweeps carry most of the cost.

## 2. Design

### 2.1 The liveness monitor (`packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py`)

**Constants.**
- `PROBE_REQUEST: Final = 'keepalive@openssh.com'`: the request OpenSSH's own `ServerAliveInterval`
  sends; sshd and Paramiko's server answer an unknown request that wants a reply with
  `REQUEST_FAILURE` (research 01 §2).
- `LIVENESS_TICK: Final = 0.1`: the most the monitor sleeps between decisions.
- `VERDICT_MARGIN: Final = 1.0`: what a background verdict leaves of the bound for the mechanics
  after it. Those are at most 0.45 s: the probe's due time and the verdict, each seen up to a tick
  late (`out` is stamped by the judge at hand-over, so the sender's own timing adds nothing), the
  close (≤ 0.05 s measured), the wake (≤ 0.1 s), and `_collect`'s poll (`SELECT_WAIT`, 0.1 s).
- Every other figure is the connection's connect bound `B = _bound(conn)`, taken when it is
  published: the quiet period before a background probe, B; a poke's verdict, B; a background
  verdict, `2B − VERDICT_MARGIN`. The bound `AGENTS.md` already states (3B) stays the only bound.

**`_Liveness(conn, host)`**, one per published connection, created in `_publish` under the lock and
started once the lock is let go. It holds `heard` (when the last message arrived), `out` (when the
judged probe still unanswered was sent, or None), `poked` (below), `dead` (set once, never cleared)
and its threads.

- **The activity hook.** It installs an instance attribute on `transport.packetizer`:
  `read_message`, wrapping the class's method, which stamps `heard` after every message read and
  re-raises whatever it raises. `Transport.run` reads every post-handshake message at that one call
  site in 5.0.0 (`transport.py:2045`) and in the 3.2 floor (`:2129`) (research 01 §3).
- **The priming probe.** The read in progress when the hook is installed returns its message
  unstamped. So the monitor sends one probe at once and never judges it. Every judged probe is sent
  after it, and replies come in order, so a judged probe's reply, or something before it, is
  stamped.
- **The hook stamps only a message read.** A `read_message` that raises (a pending rekey on a dead
  link raises `NeedRekeyException` about every 0.1 s, `packet.py:341-344`) stamps nothing, so a
  dead link's error loop never reads as traffic.
- **The decision** is a pure function of the state and the time, `_verdict(heard, out, poked, now,
  bound)`, returning `probe`, `dead` or nothing. `poked` is when the oldest call still waiting on a
  fresh probe poked, else None. The unit rows drive it with a fake clock:
  - `dead` when `out` is set, `heard < out`, and `now >= min(out + 2·bound − VERDICT_MARGIN,
    max(out, poked) + bound)`, the second term only while `poked` is set. So a background probe is
    judged after `2B − VERDICT_MARGIN`, and a call that starts while one is out has its verdict B
    after its poke. Nothing heard since `out` means nothing heard since the poke either. **A call that
    starts during an in-flight stall therefore ends the in-flight call too, at its own B verdict.**
    That is the cost of the split, and it is accepted: the in-flight call would end within the bound
    anyway, and sooner;
  - otherwise, when `out` is set and `heard >= out`, the probe is answered and `out` is cleared.
    The poke is cleared only by a probe handed over at or after it. If `out` predates `poked`, a
    new probe goes at once (adversarial review 2: a reply already in transit when the link went
    silent must not consume a call's poke, or detection takes 2B);
  - `probe` when `out` is None, and either `poked` is set or `now - heard >= bound`;
  - a poke never moves an `out` already set, so calls arriving every B/2 cannot postpone a verdict.
- **`bound` is `_bound(conn)`**, the published connection's own connect bound, never
  `CONNECT_TIMEOUT` read again. A longer `ConnectTimeout` lengthens both the quiet period and the
  verdict, as it lengthens the reconnect bound.
- **Two threads, so no lock can stall the verdict.**
  - The judge (`cluster-mcp-liveness`) takes no transport lock to decide. It waits on an `Event`
    for at most `LIVENESS_TICK` (a poke sets it), decides, hands a probe to the sender, and on
    `dead` sets `dead` and closes the transports. It exits once the transport is inactive. The
    close itself takes each channel's lock (`channel.py:1262-1270`). It cannot deadlock: the
    packetizer closes first, which frees any `_signal` holding `chan.lock` within 0.1 s
    (research 01 §4).
  - The sender (`cluster-mcp-probe`) builds `MSG_GLOBAL_REQUEST` with `PROBE_REQUEST` and want_reply
    true, and sends it through `transport._send_user_message`, as `_signal` already sends. A send
    blocks on a dead link's full buffer or a rekey (research 01 §2), so the sender swallows every
    error and keeps at most one send in flight. `out` is the time the probe was handed over, not
    when the send returned. A send stalled on a dead write path therefore still counts against the
    bound (R5). A hand-over sets `out` even while the sender is still busy with an earlier send
    (the priming probe stuck behind an upload that filled the buffer included); a busy sender sends
    one more when free.
- **Its own clock.** The monitor reads a module seam of its own (`_liveness_clock`, bound to
  `time.monotonic` at import) and never `ssh.time` or `_await`. The fake-clock reconnect rows patch
  `ssh.time` and jump it 15–40 s at a time, and a worker's sleep there would advance their clock or
  raise their tripwire (research 03 §3).
- **The close.** On `dead`, the judge closes every transport `_transports(conn)` finds, the
  outermost gateway hop first, so an inner close never blocks behind a gateway's stuck write
  (research 01 §4). `close()` took at most 0.042 s and woke every wait measured within 0.1 s.
- **Only a real transport is watched.** A connection whose transport is not a Paramiko `Transport`
  (the suite's fake connections) gets none, and nothing changes for it.
- **Background probing is allowed and kept.** The monitor runs while its connection is published,
  with or without a call, so an idle server sends one small probe per quiet bound (every 15 s by
  default). This is not graded (non-goals); it keeps a NAT entry warm, and it notices a dead link
  before the next call when it can.

**Its life.** `_publish` replaces the monitor with the connection: the old one stops with the
connection it watched, and a dropped connection's monitor is stopped before it is released.
`close()` stops the published one. Stopping sets a flag and the judge's `Event`, and never joins a
thread under `self._lock`: a sender stuck in a send would otherwise stall every call. Threads are
daemons, and each ends within a tick of its transport going inactive or its stop.

### 2.2 The call paths

**The poke** (R1). Every return of a transport from `_ensure_connected` pokes that connection's
monitor: the fast path's reused one, and one a reconnect has just published. The monitor is found
from the transport the call captured, never from `self` again, as the reconnect loop already
captures its transport. So a call that starts on a silent link sees the connection closed at most
B after it began. A connection that goes silent just after a reconnect made it is judged B after
the call's poke too (adversarial review 12a).

**Loss is decided by state** (research 01 §4, 02). Waiters see `EOFError`, `SSHException` or
`OSError`, and only the first caller gets the saved error. A failure is a lost connection when its
monitor is `dead`, or when the transport is not active, checked after `SETTLE` as `_exec` already
does for Paramiko's own EOF path.

**`run` and `_exec`** (R1, R3).
- `_exec` opens the session channel inside a new guard. On a failure that is a loss, it reports
  that nothing was sent, and `_run` goes back to `_ensure_connected` with the same deadline. The
  loop ends at the deadline with `cannot connect to <host>: <cause>; the command was not run`
  (`NOT_STARTED_EXIT_CODE`), as a failed reconnect does today.
- A failure that is not a loss is raised, as today.
- The channel open waits `max(OPEN_TIMEOUT, B + 1)`, so on a dead link the monitor's close always
  comes before the open's own timeout. The `+ 1` is a tick and the wake, with room. The rule matters
  only for a `ConnectTimeout` above 29 s, so its rows patch `OPEN_TIMEOUT` below `B − SETTLE`,
  where the alternative (`OPEN_TIMEOUT` alone) would raise Paramiko's `Timeout opening channel`
  (adversarial review 3).
- An open that times out while its connection's judged probe is still unanswered counts as a loss.
  The link is unproven, and the deadline then ends the call as the reconnect's −1002, never as
  Paramiko's raw error.
- **A closed executor never reconnects mid-call.** `close()` sets `_closed` under the lock, and
  `open()` clears it. A call woken by that close raises as today and starts no attempt, so no
  connection or monitor outlives the close (adversarial review 9).
- From the exec request on, nothing changes. A loss there is `CONNECTION_LOST_EXIT_CODE` with
  `launch.LOST_NOTE`, never a retry, so no command runs twice. `_collect` with no timeout already
  returns −1003 when its channel closes without its end of output (research 01 §4).
- **This retry also covers** `issues/ssh-open-session-reset-raises.md` (a reset while a channel
  opens). The seed is not adopted here. The ledger records the overlap as a dated note on it.

**The SFTP session** (R1, R2). A new `_sftp(transport, deadline)` replaces the three
`transport.open_sftp_client()` calls. It opens the channel with the same timeout as above, runs
`invoke_subsystem('sftp')` and builds the `SFTPClient`, so the version exchange happens there too.
A loss anywhere in it reconnects within the call's deadline, as `run`'s open does. A cut-short open
has sent no file operation.

**A transfer cut short** (R2, Q3). One exception, `TransferLost(ConnectionError)`, is raised once the
SFTP session has opened and a loss follows. Its text names the host, says the transfer may be partly
made, and says what may remain:
- `put`: `the connection to <host> was lost during the upload; the transfer may be partly made: <remote> may be truncated or hold part of the file`.
  Paramiko's `OPEN` carries `TRUNC`, so an existing target is emptied before the first byte
  (research 02 Q2).
- `get`: the same shape, for the local file, which Paramiko opens `wb` before any remote request.
- `write`, during staging: `… the transfer may be partly made: <target> is unchanged, and its staging directory <dir> may remain`.
- `write`, during its place step: the place step's −1003 becomes the same raise. An overwrite's
  `mv` is atomic, so the file is either the old one or the new one. An append or a write-through may
  be partial. The staging directory may remain.

- `write`, at its parent `mkdir` or its place step: a −1003 *or* a −1002 from either inner `_run`
  becomes the same raise, with that step's text. The session had opened, so the transfer was in
  flight, and a bare `LOST_NOTE` or `cannot connect … not run` would name neither the partial
  transfer nor the staging left. `sbatch` with `script_content` writes with a parent every time
  (adversarial review 5).

The conversion catches by state, not by type. On a loss a send raises `EOFError` and a reply wait
raises `SSHException`, neither an `OSError`, so the conversion wraps every SFTP step and `write`'s
inner commands, not only `Short` (adversarial review 12e).

Being an `OSError`, it reaches the agent with no tool change: `write_file` reads
`Failed to write file: …`, `sbatch` reads `Failed to write job script: …` (and no job is
submitted), and `upload_file` and `download_file` read `Error calling tool '…': …` (research 02
Q3).

The loss is decided before any `except OSError` that would swallow or re-word it (`_upload`,
`_is_dir`, `_loops`, `write`'s staging block). On a lost link `write` skips `_reason` and `_discard`.
The probe would reconnect, could name a filesystem cause, and its 60 s timeout is not capped by
the deadline. The removes fail at once on the dead session, so the staging directory is left for
`issues/ssh-write-staging-leftover.md` (research 02 Q4).

**A write's later commands** (the parent `mkdir`, the place step) keep going through `_run` with
the write's deadline, so each runs its own open-retry. A place step that reconnects runs on the
staged file, which is still there on the host.

### 2.3 The documents (R6, in the same commit as the code they describe)

- **The `executor/ssh.py` footgun** gets a paragraph on the silent link:
  - the hook and what counts as heard;
  - the probe, and when one is due;
  - the verdict and the close;
  - the bound arithmetic: B after a call's start; 3B − 0.55 s at most after the last message heard,
    in flight; a call starting during a stall ends the stalled call at its own B verdict;
  - the retry boundary;
  - what R2 and R3 report;
  - the recorded floor in §3 Deviation 3.
- **§2's `write`, `put` and `get`** gain `TransferLost` and what each leaves behind.
- **§3's −1003 entry** names a silent link among the ways a connection is lost.
- **§ Testing** documents the stall proxy and the new module.
- **The README's** reconnect paragraph (`README.md:44-50`) and its −1003 line (`:149`) say the
  same.
- **The `SSHExecutor` docstrings and `tests/ssh_server.py`'s module docstring** move with the code.
- A doc-pin row ties the stated figures to the code's, as `ssh-reconnect-loop`'s does
  (`tests/test_ssh_exec.py:1840-1870`).

### 2.4 The stall proxy (`tests/ssh_server.py`, R7)

`SilentLink(server)` sits in front of any `LoopbackSSH`, on `127.0.0.1:0`, and rebinds if it gets a
port in 54001–54005. It has one pump thread per direction per connection, which `recv` with a
0.05 s timeout and forward under a per-pair lock (research 03 §1).
- `go_silent()` stops every pump reading and forwarding, both ways, and closes no socket. It also
  holds new connections the same way, so "host gone" reads `timed out` as a dead path does.
- `come_back()` forwards new connections again. Old pairs stay silent.
- `rate=` limits forwarding at the TCP level. This is the one row that catches a reply-only
  detector: probe replies queued 12.7 s behind data at 64 KiB/s.
- The receive buffer of the proxy's accepted socket is pinned to 16 KiB, so an upload holds the
  client's write path below the 2 MiB channel window.
- `resume()` lets the held pairs forward again, so a row can make a silent spell of a set length.
- `forwarded` counts bytes, and `held` counts the new connections held while silent (the gone-host
  rows assert an attempt reached it).
- `silent_after_handshake` lets a new connection finish its handshake and then go silent (the
  reconnect-onto-a-silent-link row).
- **Step hooks.** A row that goes silent mid-call does it on a protocol event, never at a byte
  count, which probes on the wire would move (adversarial review 4). The server calls a row's hook
  as a request arrives: the SFTP open's channel, subsystem and version steps, a target's lookup, a
  `mkdir`, a write, a read, or an exec carrying a given program. The hook calls `go_silent()` and
  records the step, which the watchdog's message names.
- `close()` cuts everything, and is how a row releases a call it timed out.
- `executor()` on the proxy builds the usual `SSHExecutor` pointed at its port.

**Fidelity** (research 01 §5, 03 §2).
- "Stop reading" fills the client's send buffer as an un-ACKed path does.
- What loopback cannot do (the kernel's retransmission give-up after minutes; TCP keepalive
  answered by the proxy's kernel) never surfaces inside 45 s. The design rests on neither.
- Paramiko's server answers the probe from its transport thread, as sshd's main loop does, and both
  send `REQUEST_FAILURE`. The difference that matters is queueing: Paramiko's server never backs up
  its own socket, while sshd queues a reply behind every byte of output. So the slow-link rows throttle in the proxy,
  where the reply queues as it would behind sshd, and never only in `ThrottledSSH`.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | The poke on every transport `_ensure_connected` returns; the latched poke; the verdict within B; the close; `_exec`'s and `_sftp`'s open-retry back into `_ensure_connected` with the call's deadline; the open timeout `max(OPEN_TIMEOUT, B + 1)`. Every tool through `run`, `write`, `put`, `get` |
| R2   | The judge's quiet-period probe and its background verdict (`2B − VERDICT_MARGIN` after it, at most 3B − 0.55 s after the last message heard); `TransferLost` with the host and what may remain; `_reason` and `_discard` skipped; the place step's −1003 raised the same way |
| R3   | The same verdict and close; `_collect`'s existing lost-channel branch, now reached with or without a timeout |
| R4   | Any message counts as heard; the priming probe; no verdict while messages arrive; the background verdict's longer wait; the rate-limited proxy rows and the silent-spell row |
| R5   | The judge never takes a transport lock; `out` stamped at hand-over; the close frees a stuck `write_all` and every sender queued behind it |
| R6   | §2.3, in P1's and P2's commits, and the doc-pin row |
| R7   | `SilentLink` in `tests/ssh_server.py`; the `silent` rows in both eras; `silent-gate.py` proving each R1–R5 row fails on develop |

## 3. Invariant gate (AGENTS.md constitution check)

Checked against `AGENTS.md` § Invariants before research and again after this design was drafted.

- **High-blast-radius paths.** `core/executor/ssh.py` is on the list, and the change touches it.
  Research fan-out ran (trigger 2). A CONFIRMED review finding there needs a human decision before
  landing. `tests/ssh_server.py` is a leaf.
- **The `executor/ssh.py` footgun (reconnect bound).** The loop, its bound, its error text and its
  single attempt in flight are unchanged (a GOAL non-goal). The design feeds them: a closed
  transport reads as lost (`_live`), and `_publish` already replaces a dead connection. The
  published-connection rule holds: a monitor is made under the lock with the connection it watches,
  and a call uses the transport it captured. `_abort`'s decisions are untouched. The monitor closes
  only a connection that is published and dead, never an attempt in flight.
- **The footgun's channel loop (`_collect`) and `_signal`.** Both are unchanged. `_signal`'s wait
  ends when the transport goes inactive (`ssh.py:186`), and a close never sends a request on a
  freed channel. The KILL request after the grace, `timeout-process-cleanup`'s, still runs whenever
  the link is live.
- **§2 Executor Protocol.** No member or signature changes, so the three implementations need not
  move together. `write`'s contract widens: a transfer cut by a lost link raises `TransferLost`, an
  `OSError` as the contract already allows, with what may remain. The "host lost after staging"
  limitation keeps its seed. `put` and `get` keep their returns.
- **§3 `CommandResult`.** No new code. −1003 keeps its meaning (the command may have run) and its
  note. −1002 from a failed reconnect keeps its text. The timeout contract is unchanged: a timeout
  that comes before the link is noticed is a timeout (Deviation 1).
- **§1 Per-request executor isolation.** Untouched. The monitor is per connection, not per user, and
  holds no request state.
- **§4, §5, §6, §7, §8, §9.** Untouched: no mode resolution, no delegate path, no auth, no
  registration, no resource or served text.
- **§ Conventions.** Comments state the invariant, never an R-ID. The documents land in the same
  commit as the code. New tests carry `unit` or `integration`. No workflow command changes, so
  `ci.yml` does not move. No dependency change.

### Deviation justifications

Each row was read against the wording of every R-ID it touches. Rows 1–3 are **readings that go
back to the GOAL as clarifications at the PLAN/TECH sign-off**. The design does not move an R-ID.
If a ruling differs, the plan changes.

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **1. R3, a timeout before the link is noticed.** R3: "the call SHALL end no later than the earlier of its own timeout and the bound … If its end was not received, it SHALL be reported as `CONNECTION_LOST_EXIT_CODE`". The design: a call whose own timeout comes first ends at it, as §3's timeout contract says, and reports `TIMEOUT_EXIT_CODE` unless the link was already noticed dead (then −1003). | At the timeout there is no evidence yet that the link is dead. §3 (CRITICAL) says −1001 "whenever the command's end records have not both arrived by the deadline". The GOAL's outcome says calls are "reported as what they are". | Waiting at the timeout for a verdict breaks "no later than its own timeout". Reporting −1003 on no evidence would call a quiet live link lost, against R4. |
| **2. R1, "complete over a new connection" within the bound.** The design bounds the noticing and the reconnect (both inside 3B from the call's start, as the reconnect footgun's bound is read today). The command then runs for its own time, under its own timeout. | A command's own run time is not the link's. The reconnect bound already "holds for each executor call" in this sense. | Counting the command's run against 45 s would cut a live long command, against R4. |
| **3. R4, the floor** (amended at sign-off: the split verdict). R4: "a command that prints nothing for longer than the bound, and a transfer whose replies are slow but arrive, SHALL run to their end". The design holds both while the peer answers within the background verdict, `2B − VERDICT_MARGIN` (29 s by default), TCP's retransmission backoff included. At the default bound:<br>- a quiet command rides out an outage of about 25 s that begins as a probe is sent (Linux's backoff resends at about 0.2, 0.6, 1.4, 3, 6.2, 12.6 and 25.4 s), or about 40 s that begins at the last message heard; a login node's SSH daemon may stall up to 29 s;<br>- a transfer runs while some reply arrives at least every `3B − VERDICT_MARGIN` (44 s): an SFTP upload, heard once per 32 KiB request, above about 0.75 KB/s.<br>While another call starts on the connection, both floors are its poke's B instead: a 15 s answer, an upload above about 2.2 KB/s. | R1–R3 demand a verdict within 3B. Any detector then has a floor: the longest gap it can wait out. Only R1 must leave room for a reconnect, so only a call's own probe is judged at B. | One verdict at B for every probe (the draft) leaves the floor at half: an outage of about 12.6 s, an upload above about 1.1 KB/s. The draft's "2.2 KB/s" counted only the verdict's window, not the quiet period before the probe, and is corrected here. One verdict at `2B − VERDICT_MARGIN` for every probe leaves R1 no time to reconnect. No app-level signal sees TCP's ACKs. Recorded: `issues/ssh-liveness-message-gap.md` and its `ROADMAP.md` entry. |
| **4. Two threads per connection** (the judge and the sender). | A send blocks on a dead link's full buffer while holding the write lock (research 01 §2, 03 §1), and the verdict must not block with it (R5). | One thread that sends and judges hangs with its send. A blocking probe at each call's start cannot wake an in-flight SFTP wait or a `_collect` with no timeout (R2, R3). |
| **5. Private Paramiko surface**: the instance wrapper on `packetizer.read_message`, and `_send_user_message`. | No public API sees inbound traffic or sends a request that wants a reply without blocking (research 01 §2–3). `_signal` already sends this way. | `set_keepalive` detects nothing (01 §1). `global_request(wait=True)` has no timeout and replaces the event kex waits on. `transport_factory` must be threaded through `_bounded` and every hop. `packetizer_class` is above the 3.2 floor. A row pins that the wrapper sees messages on the installed Paramiko. A silent change there would turn a quiet live link dead, and the R4 rows catch that. |
| **6. Probing while idle.** | It is the simplest shape: no per-call bookkeeping in four paths. | Probing only while a call is in flight needs a busy count on `run`, `write`, `put` and `get`, and changes no graded behaviour. |

## 4. Rabbit holes (resolved)

- **Does keepalive detect a dead peer?** No: it is send-only, its timer is reset on writes, and
  through 10 s of stall nothing changed (research 01 §1).
- **What signal proves the link live?** Any inbound message. A probe reply queues behind window-full
  data on a slow link, 12.7 s at 64 KiB/s (research 01 §5, 03 §2).
- **How is inbound traffic seen across 3.2–5.0?** The `read_message` instance wrapper, plus a
  priming probe for the one read it misses (research 01 §3).
- **Does a close from another thread wake every wait, the write path included?** Yes, all
  measured within 0.1 s. The ProxyJump case is handled by closing the outermost hop first. It is
  not measured: the suite has no gateway hop, which `issues/ssh-gateway-hops-unpinned.md` already
  records, and the ledger adds a dated note there (research 01 §4).
- **Where may a call retry?** Only at a channel or SFTP-session open (research 02 Q1).
- **What does each tool leave behind, and what does the agent read?** See research 02 Q2–Q3 and
  §2.2.
- **Can the tests reproduce a silent link faithfully, the R5 write path included?** Yes, with a
  hold-mode proxy and a 16 KiB receive buffer. Linux autotuning was not measured, so the R5 row
  asserts its own precondition (research 03 §1).
- **Will monitor threads disturb the fake-clock rows?** Not with their own clock seam and thread
  name (research 03 §3).
- **Adversarial design review** (trigger 3): it ran, and its outcome is recorded in §4.1 below.

### 4.1 Adversarial design review

A fresh reviewer got the GOAL, the drafted PLAN and `silent-gate.py`, and no research briefs. It
prototyped three experiments of its own and returned twelve findings. Each one is folded in:

1. **HIGH: at B = 1 a call cannot reconnect.** It is noticed at s + 1.1, past its last start at
   s + 3 − `FINAL_ATTEMPT_LEAD`. So the reachable rows fail on a correct build, and the gone-host
   rows pass without any attempt. Now:
   - the silent rows patch `CONNECT_TIMEOUT` to 2 (B = 2, the bound 6 s, 1.9 s to start an
     attempt);
   - the reachable rows assert the server accepted a new connection after the call began;
   - the gone-host rows assert an attempt reached the proxy (`held >= 1`);
   - §1 states `2B − FINAL_ATTEMPT_LEAD`.
2. **The poke is now latched** against a reply in transit (§2.1), with a `_verdict` row and a
   mutant that clears it on the answered tick.
3. **The open-timeout rule gets rows** with `OPEN_TIMEOUT` below `B − SETTLE`, at both open sites.
   An unanswered probe at an open's timeout is now a loss (§2.2).
4. **R2 rows go silent on protocol events** (server hooks at lookup, stage, upload, mkdir, place,
   download, and the SFTP open's channel, subsystem and version steps), never at a byte count. Each
   watchdog names its step, and `silent-gate.py` requires develop to hang at that same step.
5. **`write`'s parent `mkdir` and place step** turn −1003 and −1002 into `TransferLost` (§2.2).
   New shapes: `write-mkdir`, and `write-place-gone`.
6. **A wrong priming probe slipped past every R4 row.** Its killer is now explicit:
   `test_an_idle_connection_is_not_taken_for_a_silent_link`. The row publishes, idles past 2B with
   no call, then runs on the same connection, with the server's connection count unchanged.
7. **No double run with the host back.** New row,
   `test_a_command_cut_by_a_silent_link_is_never_run_twice[run|sbatch-path]`: a command in flight,
   `go_silent()`, then `come_back()` before the verdict. It must give −1003, with the wire received
   exactly once.
8. **Deviation 3 understated R4's bend.** It now says the floor binds commands too: the peer must
   answer within B, TCP's retransmission backoff included.
9. **`close()` during a call** no longer reconnects (`_closed`, §2.2). A row checks that no monitor
   or probe thread is left after `close()`.
10. **Mutant gaps**, each now on PLAN §6's list with a killer:
    - (a) a stamp on a raising read;
    - (b) a poke that moves `out`;
    - (c) B from `CONNECT_TIMEOUT` and not `_bound(conn)`: a unit row with `connect_timeout=40`;
    - (d) the monitor reading `ssh.time`: the fake-clock reconnect rows as targets;
    - (e) loss checks at `_is_dir`, `_loops` and the staging block: the `write-lookup` and
      `write-stage` shapes;
    - (f) the retry at the subsystem and version steps: `test_an_sftp_open_cut_by_a_silent_link_reconnects`;
    - (g) a hand-over refused while the sender is busy (§2.1).
11. **`silent-gate.py` hardened:**
    - every child's status is checked, so a failed sync is reported as itself;
    - each run has its own `pgrep` token, and `--basetemp`;
    - paths come from the top level;
    - `PYTHONPATH`, `PYTHONHOME` and the like are dropped from a copied environment;
    - the era log proves each pass ran in its era.

    The rows' constraints are in TECH § Conventions:
    - no new name is touched before the call returns;
    - the `later-timeout` row's timeout outlasts its watchdog;
    - `still waiting` is printed only while the call's thread lives.

    The reviewer found no way for the gate to go green vacuously.
12. **Smaller points:**
    - (a) a poke on a reconnect's return (§2.2);
    - (b) the judge's lock claim reworded (§2.1);
    - (c) no join under the lock (§2.1);
    - (d) probe replies set Paramiko's `completion_event`: recorded as a risk, §5;
    - (e) the conversion catches by state (§2.2).

The reviewer also confirmed, by measurement or reading, that these are sound:
- the close wakes every wait, a `putfo` holding the write lock included;
- the write path is held on macOS behind the 16 KiB buffer;
- the floor arithmetic: messages stamped every 1.06 s at 32 KiB/s;
- the hook's single call site;
- the bound arithmetic for R2, R3 and R5;
- no double run in the planned retry paths;
- closing the outermost hop first;
- `time.monotonic` across a laptop's sleep;
- the fake-clock rows' safety with a separate clock.

### 4.2 Sign-off amendment: the split verdict (2026-11-05)

The foreman accepted Deviations 1 and 2 as written, and asked for a split verdict to be weighed for
Deviation 3. It holds, so it is adopted:
- **R1:** a call's poke is still judged at B, and a background probe out when a call starts is
  judged B after the poke.
- **R2, R3:** an in-flight call ends at most `B + 2B − VERDICT_MARGIN + 0.45 s` = 3B − 0.55 s after
  the last message heard, inside the bound with 0.55 s to spare. The scheduling lateness measured
  at load 30–35 was 0.01 s.
- **R4:** the floor roughly doubles (Deviation 3).
- **R5:** the concurrent call pokes and ends within B.
- **§3:** the timeout contract is untouched.
- **The reconnect footgun:** untouched; it has nothing after an in-flight end.
- **Cost:** a call starting during a stall ends the stalled call at its B verdict, stated in §2.1
  and the footgun.

Changed:
- §1 and §2.1 (`VERDICT_MARGIN`, the `dead` rule);
- §2.3's arithmetic and Deviation 3's figures;
- §6's watchdog figures;
- the R5 row's assertion;
- the idle row (past 3B);
- a new R4 row, the silent spell;
- the mutant list;
- `SilentLink.resume()`;
- TECH;
- `silent-gate.py` (the spell row runs on this tree only);
- the seed's figures.

The draft's "2.2 KB/s" floor counted only the verdict's window. The draft's true floor was about
1.1 KB/s, and the split's is about 0.75 KB/s.

## 5. Risks & open questions

- **Readings at sign-off:** settled. Deviations 1 and 2 were accepted; Deviation 3 was amended to the split verdict (§4.2), and its R4 wording goes into the GOAL.
- **0.55 s of the bound to spare in flight.** The background verdict's mechanics measured 0.45 s at most. A host loaded past what the research measured (scheduling lateness 0.01 s at load 30–35) could eat the rest; `VERDICT_MARGIN` is the one figure to raise.
- **Load flakes.** Real-time loopback rows are the class `issues/stalled-reconnect-test-timing.md`
  tracks (seven sightings). Every new row measures from `go_silent` returning and allows its figure
  plus 1.0 s (the worst measured alone, at load 30–35, was 0.009 s). It puts the measured times in
  its message, and a thread gets 2.0 s to end. A new sighting is a dated note on that seed.
- **Linux socket autotuning** could let an upload stall on the window rather than the socket. The
  R5 row fails, never skips, when the write path is not held, so CI would say so.
- **A future Paramiko** that reads messages elsewhere would make every link look silent. The R4
  quiet row fails at once.
- **Idle chatter:** one probe of about 100 bytes per connect bound while idle.
- **Paramiko's `completion_event`.** A probe's reply sets whatever `completion_event` holds
  (`transport.py:2813-2820`), so a `renegotiate_keys()` or a port-forward request made while probes
  fly could return early. Nothing in the packages calls either (research 01 §2). A future caller
  must not lean on that event.
- **`silent-sweep.py` is written by P3**, once the code it plants into exists. Its rules and its
  decision list are this plan's (§6). The review grades it against them. `silent-gate.py` and
  `ledger-check.py` were drafted and dry-run with this plan: both are red on today's tree, as they
  must be, and the develop copy and sync took 5.2 s.
- **ProxyJump:** the hop order on close is pinned by a unit row on a fake chain only.

## 6. Verification strategy

**The rows.** All live in `tests/test_ssh_exec.py`, in a new section after "A host that goes down and
comes back", with `silent` in every name. They are `integration`, run against `SilentLink`, with
`CONNECT_TIMEOUT` patched to 2 (B = 2 s, bound 6 s, and 1.9 s to start a reconnect after a
verdict; at B = 1 there would be none, adversarial review 1). Each runs its call on a thread with its own
watchdog, the figure plus 1.0 s from `go_silent`: B + 1 s for a call's start, 3B + 1 s in flight.
On overrun it fails with `still waiting <t> s after the link went silent`, then releases the call
with `link.close()`. So develop's hangs read as failures, never as a stuck suite. The integration
rows' slack cannot tell `2B − VERDICT_MARGIN` from `2B` at B = 2, so the verdict's exact values are
pinned by the unit rows (`_verdict` on a fake clock), and the integration rows pin the behaviour.

| Row | R-ID | On develop |
|---|---|---|
| `test_a_call_on_a_silent_link_reconnects[<tool>]`: host back, exact result, a new connection accepted after the call began and within B + 1 s of it | R1 | fails |
| `test_a_call_on_a_silent_link_to_a_gone_host_is_not_run[<tool>]`: −1002 (or the tool's not-run text), `cannot connect to 127.0.0.1: timed out`, nothing received, an attempt held by the proxy | R1 | fails |
| `test_a_channel_open_outlasting_its_own_timeout_on_a_silent_link_reconnects[run\|sftp]`: `OPEN_TIMEOUT` patched below `B − SETTLE` | R1 | fails |
| `test_a_reconnect_onto_a_link_that_goes_silent_still_ends_in_time`: the proxy goes silent once the new connection's handshake is done | R1 | fails |
| `test_an_sftp_open_cut_by_a_silent_link_reconnects[channel\|subsystem\|version]` | R1 | fails |
| `test_a_command_cut_by_a_silent_link_is_never_run_twice[run\|sbatch-path]`: host back before the verdict, −1003, the wire received once | R3 | fails |
| `test_an_idle_connection_is_not_taken_for_a_silent_link`: idle past 3B, then a call on the same connection | R4 | passes |
| `test_a_command_on_a_link_that_goes_silent_is_lost[no-timeout\|later-timeout]`: −1003 and `LOST_NOTE` within 3B + 1 s | R3 | fails |
| `test_a_quiet_command_rides_out_a_silent_spell_shorter_than_its_verdict`: the server's hook goes silent as a background probe arrives, and `resume()` lets the held bytes through 2.5 s later (past B, inside `2B − VERDICT_MARGIN` = 3 s); the command's result exact, the same connection | R4 | not run there: develop sends no probe for the hook to fire on |
| `test_a_command_on_a_link_that_goes_silent_ends_at_its_timeout`: −1001 at its timeout | R3 (Deviation 1) | passes |
| `test_a_quiet_command_is_not_taken_for_a_silent_link[quiet\|slow-link]`: `sleep` past 3B, and trickled output through `rate`, results exact | R4 | passes |
| `test_a_call_beside_a_command_on_a_silent_link_ends_in_time`: the new call and the stalled one both end within B + 1 s of the new call's start | R5 | fails |
| `test_a_transfer_on_a_link_that_goes_silent_may_be_partly_made[put\|get\|write-lookup\|write-stage\|write-upload\|write-mkdir\|write-place\|write-place-gone\|sbatch]`: silent at a server hook's step, named in the watchdog | R2 | fails |
| `test_a_slow_transfer_is_not_taken_for_a_silent_link[put\|get\|write]` | R4 | passes |
| `test_a_call_beside_a_transfer_stalled_on_a_silent_link_ends_in_time`: asserts the write path is held | R5 | fails |

`<tool>` in the default suite:
- gone-host rows, every tool: P1 `run`, `run_command`, `sbatch` with a script path, `read_file`
  and `list_directory`; P2 adds `write_file`, `upload_file`, `download_file`, and `sbatch` with
  script content;
- reachable rows: P1 `run` and `run_command`; P2 `write_file`.

The R1 contract is that every tool's gone-host row runs by default. With
`CLUSTER_MCP_TEST_EVERY_KIND=1` the reachable rows cover every tool too, chosen at collection,
never skipped.

**The unit rows** are in a new `tests/test_ssh_liveness.py`:
- the verdict's arithmetic on a fake clock;
- the hook on a real Paramiko pair: every message stamped, the priming probe;
- the close order on a fake gateway chain;
- the doc pin.

It imports names the fix adds, so develop's tree never runs it.

**The gates** (`spec/ssh-half-open-link/verify/`):
- **`silent-gate.py {commands|transfers|all} {legacy|modern|both}`** (drafted with this plan). It
  runs the named rows on this tree, each of which must pass. Then it runs them on a scratch copy
  whose `packages/` come from develop (`13c0e83`), where each "fails" row must fail with
  `still waiting` and each "passes" row must pass. A missing row is red.
- **`silent-sweep.py {legacy|modern} [1|2]`** (P3, on `timeout-process-cleanup`'s `sweep.py`
  model). Every decision of §2 is planted at every alternative it can take, with values handed to
  calls included, by `tests/mutants.py` cases (`shol-*`). Each case must be killed, or be shown
  equivalent by running it against its neighbours' killers, in both eras:
  - the hook removed or stamping replies only;
  - the priming probe dropped;
  - the quiet period at 0 or at 3B;
  - the poke's verdict at 0, at `2B − VERDICT_MARGIN` or at 3B; the background verdict at B, at
    2B or at 3B; `VERDICT_MARGIN` at 0; the `min` as a `max`; the poke's term from `poked` alone,
    not `max(out, poked)`; `heard < out` as `<=`; or "the reply to this probe";
  - the poke removed;
  - the close dropped, or not outermost first;
  - the judge sending inline;
  - `out` stamped after the send;
  - the open timeout at `OPEN_TIMEOUT` alone;
  - the retry extended past the exec request, or removed, or kept only at the channel open;
  - `TransferLost` reworded without the host, or caught by type (`OSError` only);
  - `_reason` kept on a loss;
  - the place step's or the parent `mkdir`'s −1003 or −1002 returned;
  - the latched poke cleared on the answered tick, a poke moving `out`, the hook stamping on a
    raising read;
  - B from `CONNECT_TIMEOUT`, not `_bound(conn)`;
  - the monitor reading `ssh.time`;
  - a hand-over refused while the sender is busy;
  - no poke after a reconnect;
  - `_closed` ignored by the open-retry;
  - an unanswered probe at an open's timeout raised as a live failure.

  Every `ssh.py` anchor the edits touch is re-planted in the same commit
  (`test_mutation_anchor_applies`).
- **Every gate script:**
  - runs as `uv run python -I`, is named after what it checks (never a module), and copies
    `os.environ` before clearing anything;
  - runs one pytest child at a time (≤ 2 workers), each in a process group of its own, killed on
    exit;
  - asserts with `pgrep` that nothing of its own is left;
  - states its footprint in its header.

**CI budget.** Projected per era from research 03 §4, measured on develop: `test_ssh_exec.py`
131 s legacy and 146 s modern, the full legacy suite 579 s. Research 03 put about 25 default rows at
+70 s per era with B = 1. At B = 2 each row's waits double. The default suite now holds about 40
rows, about 30 of them real-time at 2–9 s. That projects to **≈ +150 s per era (≈ 25%)**, leaving the
eras at about 12–13.8 min of CI's 20-minute timeout. The every-tool reachable rows stay behind
`CLUSTER_MCP_TEST_EVERY_KIND=1`. P3 measures the real figure on both trees. If it is past +180 s, P3
seeds a trim.
