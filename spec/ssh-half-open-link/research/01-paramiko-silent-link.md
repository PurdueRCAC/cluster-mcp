# Research 01 — Paramiko on a silent link: keepalive, probes, activity hook, close()

Installed Paramiko 5.0.0 and Fabric 3.2.2. Line numbers are 5.0.0's unless marked 3.2.0, which was
read from the 3.2.0 release. Every behaviour below was run, not only read. The rig: a Paramiko
server (exec and SFTP), a loopback proxy in front of it, and a client `Transport`. The proxy has two
stall modes per direction: **drop** (keep reading the socket, forward nothing) and **hold** (stop
reading it). The scripts were scratch files outside the repo; each run took under 30 s.

## 1. Keepalive does not detect a dead peer

- `Transport.set_keepalive(n)` registers a callback, `global_request("keepalive@lag.net",
  wait=False)` (`transport.py:1189-1204`). `wait=False` sends **want_reply = False**
  (`:1228`, `m.add_boolean(wait)`), so the peer never answers.
- The timer `__keepalive_last` is reset only on **write** (`packet.py:349`, `write_all`). Reads
  never touch it. `_check_keepalive` runs only when the transport thread's socket read times out
  (`packet.py:345`, `:646-657`).
- Measured with keepalive at 1 s:
  - On a live link the server got 3 `keepalive@lag.net` requests in 3.2 s, and the client received
    **0** messages.
  - Stalled for 10 s, in drop and in hold mode: `is_active()` stayed True and `saved_exception`
    stayed None. The client kept sending (15 packets in all), and no write failed.
- **Verdict:** keepalive is send-only. It never reads a reply and never fails a write, because the
  kernel buffers a tiny packet. It keeps a NAT entry warm, but it detects nothing within minutes;
  only the kernel's TCP give-up ends the connection.

## 2. Probe options

- **`global_request(kind, wait=True)`** (`:1206-1241`):
  - It replaces the shared `self.completion_event` (`:1223-1224`).
  - It then waits in 0.1 s steps with **no timeout**, until a reply arrives or `active` goes False
    (`:1235-1240`). Measured: still blocked 3 s into a stall; `close()` made it **return None**
    (not raise) 0.09 s later.
  - Other code uses the same event:
    - `start_client`/`start_server` (`:688-693`, `:757-762`) and `renegotiate_keys` (`:1176`) wait
      on it.
    - The end of every key exchange sets it (`:2757`), so a rekey can end the wait with a stale
      `global_response`.
    - The transport thread's exit sets it only when `active` was still True (`:2155-2158`).
  - It is unusable as a probe.
- **Reply handling.** `_parse_request_success` and `_parse_request_failure` (`:2810-2820`) overwrite
  `global_response` and `.set()` whatever `completion_event` holds. Measured: a stray reply set an
  event standing in for a waiter. That breaks a concurrent `global_request(wait=True)` (port
  forwarding) or `renegotiate_keys`. Neither is used anywhere in `packages/*/src` (grep).
  Afterwards the event from `start_client` is already set (measured), so a stray reply is harmless
  here.
- **No public non-blocking want_reply=True request exists.** The workable form is the one `_signal`
  already uses: craft the `Message` (`MSG_GLOBAL_REQUEST`, name, `True`) and pass it to
  `transport._send_user_message`. Measured: the server received it, and the client got
  `MSG_REQUEST_FAILURE` 1.4 ms later.
  - `_send_user_message` can block. It waits on `clear_to_send` during a rekey (up to 30 s,
    `:1813-1828`), then takes `clear_to_send_lock` with a **blocking acquire** (`:1821`) and holds
    it through `write_all`.
  - Measured: a thread opening a session sat at `:1821` behind a writer stuck on a full send
    buffer.
  - So the thread that sends a probe can hang on a dead link. It must not be the thread that
    judges.
- **Server answers.**
  - Paramiko's server passes an unknown request to `ServerInterface.check_global_request`, which
    returns False by default (`server.py:270-298`). It then sends `REQUEST_FAILURE` when the
    request wants a reply (`transport.py:2774-2808`). Measured as above.
  - OpenSSH's `sshd` (`serverloop.c`, `server_input_global_request`) answers any request it does
    not know with `SSH2_MSG_REQUEST_FAILURE` when want_reply is set. That reply is what the OpenSSH
    client's own `ServerAliveInterval` (`keepalive@openssh.com`) relies on.
  - **Both reply.** A failure reply counts as proof of life.

## 3. Inbound-activity hook

- **Call site.** The transport thread reads every post-handshake message in one place,
  `ptype, m = self.packetizer.read_message()` inside `Transport.run` (5.0.0 `:2045`; 3.2.0
  `:2129`). 3.2.0's other calls are GSS-API auth only (`auth_handler.py:414-435`). The attribute is
  looked up on every loop pass, so an **instance-attribute wrapper** installed after `open()` takes
  effect. Measured: it saw every message, `REQUEST_FAILURE` (82) included.
- **Caveat (measured).** The wrapper misses exactly one message: the read already in progress when
  it is installed. Probes 1, 2 and 3 were seen as `[]`, `[82]`, `[82, 82]`. A detector that arms on
  its first probe would therefore read a quiet live link as dead. Fix: send a priming probe and do
  not judge until the wrapper has seen one message. The prototype in §6 does this.
- **Packetizer counters.** `_Packetizer__received_packets` and `__received_bytes` are incremented
  in `read_message` (`packet.py:594-595`). They are **reset on every rekey** in
  `set_inbound_cipher` (`:206-209`; 3.2.0 `:187`). Polling them for any change works, and misses
  nothing. But they are name-mangled privates, and a reset defeats a "greater than" test.
- **`transport_factory`.** Added to `SSHClient.connect` in 2.12 (`client.py:348`, used at
  `:389-391`; also in 3.2.0 at `:411-413`). Fabric passes its `connect_kwargs` straight into
  `client.connect(**kwargs)` (`fabric/connection.py:631-665`). So a Transport subclass could wrap
  its packetizer before the thread starts. That costs threading the factory through `_bounded` and
  each gateway hop.
- **`Transport(packetizer_class=)`** arrived only in **3.4** (`transport.py:433`). It is below no
  floor the project can use (`paramiko>=3.2`).
- **Recommendation:** the instance wrapper on `transport.packetizer.read_message`, installed when
  the connection is published, plus a priming probe. It uses one public method name and one call
  site in both versions, and needs no change to the connect path.
  - **Risk:** a future Paramiko that reads messages elsewhere would make the link look silent, so a
    live link would be probed and then closed. A test that pins "a quiet live link survives several
    bounds" catches that.

## 4. `transport.close()` from another thread wakes every wait

`close()` sets `active = False`, closes the packetizer, unlinks each channel under `chan.lock`, and
then closes the socket (`:855-864`, `stop_thread` `:1760-1775`). Each waiter was confirmed blocked
at the frame shown before `close()` was called. Latency is measured from the start of `close()`.

| Wait (where it was blocked) | Woke after | Raised |
|---|---|---|
| `open_session(timeout=30)` (`open_channel:1047`) | 0.09 s | `EOFError` (or `SSHException('Unable to open channel.')`) |
| `open_sftp_client()` in its channel open | 0.10 s | `EOFError` |
| `invoke_subsystem('sftp')` (`_wait_for_event:1217`) | 0.000 s | `SSHException('Channel closed.')` |
| SFTP version exchange (`_send_version`) | 0.000 s | `SSHException('EOF during negotiation')` |
| `sftp.stat`, `sftp.get` mid-transfer (`_read_response`) | ≤ 0.001 s | `SSHException('Server connection dropped: ')` |
| `sftp.put`, drop mode (`_wait_for_send_window`) | 0.000 s | `EOFError` |
| `sftp.put`, hold mode (`write_all:354`) | 0.03 s | `EOFError` |
| `chan.exec_command` (`_wait_for_event`) | 0.000 s | `SSHException('Channel closed.')` |
| `ssh._collect(chan, None, None)` on a quiet command | 0.001 s | returns `-1003` + `LOST_NOTE`; `closed=True`, `eof_received=0` |
| Full send buffer: writer in `write_all:354` | 0.04 s | `EOFError` |
| …second thread's `open_session`, at `_send_user_message:1821` | 0.04 s | `EOFError` |
| …`ssh._signal` holding `chan.lock`, at `ssh.py:194` | 0.04 s | returns None (swallowed) |

- **Nothing stayed blocked.** `close()` itself took at most 0.042 s, and only in the `_signal`
  case. The stuck `write_all` sees `packetizer.closed` on its next 0.1 s socket timeout and raises
  (`packet.py:368-371`), which frees the lock `_unlink` needs.
- **Exception types vary.** `get_exception()` hands the saved `EOFError` to the first caller only
  and clears it (`transport.py:1372-1378`). Callers must classify the failure by "the monitor closed
  this transport", never by exception type. `ssh._exec` already does: `transport.join(SETTLE)`,
  then `is_active()`.
- **Not measured: a ProxyJump hop.** There the inner transport's socket is a gateway `Channel`, and
  `Channel.close()` sends through the gateway's `_send_user_message`, which can block behind a
  stuck write on the gateway's link (`channel.py` `close`). Close the outermost dead transport, or
  call `close()` off the judging thread.

## 5. Proxy fidelity

- **Drop mode** keeps ACKing, so the client's socket never fills. An upload stops only at the 2 MiB
  channel window (`_wait_for_send_window`).
- **Hold mode** fills the client's send buffer, as an un-ACKed path does. The upload stops in
  `write_all` holding `clear_to_send_lock`, and other senders queue behind it (measured with a
  32 KiB proxy receive buffer, and with the macOS defaults of 128 KiB `tcp.sendspace` and
  `recvspace`). **Use hold for R5 and the write-path rows, and drop for the window rows.**
- **What loopback cannot do.** On a real dead path the kernel retransmits with backoff and reports
  `ETIMEDOUT` only after minutes (about 15 min on Linux with `tcp_retries2`=15). An idle socket with
  nothing unacknowledged never errors, since `SO_KEEPALIVE` is off. In hold mode the proxy's kernel
  answers zero-window probes, so the connection never times out. None of this surfaces inside
  45 s, so loopback is faithful for this bound.
- **The transport thread reads inbound while the app reads nothing.** An unread `emit 20 MB` left
  exactly 2 097 152 bytes buffered on the channel, and a probe's `REQUEST_FAILURE` still arrived in
  1.4 ms. On a slow link the reply can queue behind up to one window per open channel. The
  activity signal covers that, since the data counts as activity.
- **The gap for a slow live upload.** The inbound gap is about one SFTP write request
  (`MAX_REQUEST_SIZE` 32 768, `sftp_file.py:59`) divided by the uplink rate. It stays under a
  15 s judging window down to about 2.2 KB/s.

## 6. Prototype of the hypothesis (bound B = 2 s, quiet period Q = 1 s)

The prototype used the read_message wrapper, a priming probe, and probes sent from a throwaway
thread. The judging thread never takes a transport lock.

- **Quiet live command** (`quiet 6`, three bounds long): exit 0 at 6.07 s. No false death; 6
  probes were answered.
- **Drop stall during a quiet command:** `_collect` returned `-1003` 2.58 s after the stall.
- **Hold stall:** `_collect` returned `-1003` after 2.56 s.
- **Hold stall mid-`put`:** `EOFError` after 3.15 s.
- **Detection time** was at most Q + B after the last message received.
- The sender thread raised `EOFError` after the close. It must swallow that.

## Recommendation

- **Hypothesis confirmed, with four amendments:**
  1. Install the activity hook as a `read_message` instance wrapper, and send a priming probe
     before arming the detector.
  2. Send probes as crafted `MSG_GLOBAL_REQUEST` messages with want_reply = True through
     `_send_user_message`, from a non-judging thread that swallows errors, with at most one probe
     in flight.
  3. Never use `global_request(wait=True)` or `set_keepalive`. The second is optional, for NAT
     warmth only.
  4. Judge "dead" as "a probe outstanding for the connect bound, and nothing at all received since
     it was sent".
- Let `transport.close()` end every in-flight wait (≤ 0.1 s, all paths measured). Map the outcome
  by `not transport.is_active()` plus a "closed by the monitor" flag, never by exception type.
- **Budget:** detection takes ≤ Q + B after the last message received. A probe at call start
  bounds an R1 call's detection at B (15 s), which leaves 30 s of the 45 s for the reconnect.
  Choose Q so that Q + B ≤ 45 for R2 and R3.
