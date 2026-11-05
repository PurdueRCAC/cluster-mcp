# Research 03: the silent-link fixture, fidelity, timing and the CI budget

Read-only. I prototyped in a scratch directory against `develop` code (Paramiko 5.0.0, Fabric 3.2.2,
macOS, 10 cores). The host was under ambient load from other work: the 1-minute load average was 2–3
during the suite runs and 25–35 during the load runs.

## 1. The silent-link fixture

**Shape (prototyped, about 100 lines).** A listener on `127.0.0.1:0` (rebind if the port lands in
54001–54005). Each accepted connection gets an upstream socket to `LoopbackSSH.port` and one pump
thread per direction. A pump runs `recv` with a 0.05 s timeout, then forwards under a per-pair lock.
- `go_silent(new='hold'|'refuse')` sets a flag under that lock. Each pump then stops reading and
  forwarding, and neither socket is closed.
- `come_back()` forwards new connections again. Old pairs stay silent.
- `rate` throttles forwarding at the TCP level, which matters for R4 (§2).
- `close()` closes everything.

**Where it goes and how it is wired.**
- It belongs in `tests/ssh_server.py`, beside `_drop`/`DroppingSSH`, under a name that does not
  clash with `test_ssh_exec.py`'s `Silent` (:2072).
- The executor is pointed through it the way `test_a_stalled_reconnect_…` already builds one
  (`SSHExecutor(LOOPBACK, port=…)`, test_ssh_exec.py:2120). A cleaner route is a `port=` parameter on
  `LoopbackSSH.executor()` (ssh_server.py:542).
- It needs nothing from `refuse()`/`serve_again()` (:426, :432): the upstream server stays up the
  whole time.
- Teardown order: close the link first, then the server. `close()` kills the exec process groups
  (:548).

**Measured.**
- **Switch:** `go_silent` returns in 0.01–0.03 ms. No byte was forwarded after the switch in 6 of 6
  runs. The pumps park within 1–52 ms.
- **Host gone, `hold` (accept and black-hole):** a new connection under `CONNECT_TIMEOUT=1` fails
  in 1.02 s. `connect_failure_message` gives `cannot connect to 127.0.0.1: timed out (Error reading
  SSH protocol banner)`.
- **Host gone, `refuse` (listener closed):** fails at once with `connection refused (Unable to
  connect to port …)`.
- **Which is more faithful:** `hold`. A dead path drops SYNs, so the cause a user sees is "timed
  out". `refuse` is right only for a host that answers with resets.
- **Host back:** after `come_back()`, a new connection ran in 0.04 s. The old executor, once its
  transport was closed, as the monitor would do, reconnected and ran in 0.04 s.
- **When the client's `send` blocks (sizing R5).**
  - With default buffers, the client's socket took 1.40–5.37 MB before `EAGAIN`, because macOS
    autotunes up to `autosndbufmax`/`autorcvbufmax` = 4 MiB. That is more than Paramiko's 2 MiB
    channel window (`DEFAULT_WINDOW_SIZE`), so the write may stall on the window and never on the
    socket.
  - Setting `SO_RCVBUF=16384` on the proxy's accepted socket (after `accept`) cut the fill to
    0.61–0.97 MB, which is below the window.
  - Under that setting, a 4 MiB (and an 8 MiB) `put` with 0.54 MB already forwarded when the link
    went silent held the write path. A concurrent `transport.send_ignore()` was still blocked after
    3 s.
  - `run()` was still blocked after 10 s even with `OPEN_TIMEOUT` patched to 2. This is the R5
    failure on `develop`: `Packetizer.write_all` retries `socket.timeout` for ever under the write
    lock (paramiko `packet.py:348-386`).
  - `transport.close()` returned in 0.000 s and woke the stalled `put` with `EOFError`. Through
    `stop_thread`, the packetizer's `__closed` turns the next retry into `EOFError` (`transport.py:1760`).
  - A `put` *started* after the silence never reaches `write_all`. It waits in `open_sftp_client`'s
    channel open, which takes 3600 s. An R2/R5 row must start the transfer, wait for bytes through
    the proxy (`forwarded`), and only then go silent.
  - Linux (CI) autotuning differs and was not measured. So the R5 row should *assert its own
    precondition*: `send_ignore` on a helper thread is still blocked after about 0.5 s. If it is not,
    the row fails ("the write path was not held") and never skips.

## 2. Fidelity: Paramiko's server versus sshd

| Difference | Suite server | OpenSSH sshd | Matters for verdicts? |
|---|---|---|---|
| Unknown global request with want_reply | `check_global_request` returns False, so it sends `REQUEST_FAILURE` from the transport thread (`server.py:270-298`, `transport.py:2774-2808`); live reply took 0.14–0.39 ms | `server_input_global_request` replies `REQUEST_FAILURE` (from memory of `serverloop.c`, not checked against source; it skips the reply while rekeying) | No, if *any* inbound message counts as liveness. A reply-only rule would also need to treat a rekey as alive. |
| ClientAlive | none | off by default (`ClientAliveInterval 0`) | No. The server side is a non-goal. If it were on, sshd's own `keepalive@openssh.com` would count as inbound traffic. |
| Reply queued behind channel data | `ThrottledSSH` throttles in the application, so its socket never backs up. A probe during its 64 KiB/s output was answered in 0.5–0.7 ms. | One output buffer per connection: the reply sits behind every byte already queued | **Yes.** With the proxy limiting to 64 KiB/s at the TCP level, probe replies took **12.7 s, then 2.9 s**. Silence must be measured from the last inbound message, not the last reply. A row through the proxy's `rate` is the only one that catches a reply-only detector. |
| Server loop while the client is stalled | The transport thread keeps reading and gets nothing. Output pumps block in `channel.sendall` on the window. Execs keep running. | The same: sshd stops reading the child once the window is exhausted | No. R3's command stays running server-side, as on a real host. `close()` reaps it. |

Paramiko's own `set_keepalive` sends `keepalive@lag.net` with `wait=False`, which means
want_reply=False (`transport.py:1206-1232`), so it can never detect anything. `global_request(wait=True)`
has no timeout: it loops until the reply comes or the transport is inactive, and on the silent link it
was still blocked after 2 s. A probe must not block a calling thread.

## 3. Clocks and timing

- **What happens if a monitor reads the fake clock.** `FakeClock` replaces `ssh.time` with an object
  that has only `monotonic` and `sleep` (:1003-1093). `test_ssh_exec.py:2278` uses
  `SimpleNamespace(monotonic, sleep)`.
  - A monitor reading `ssh.time` in the reconnect rows would see the offset jump 15–40 s at a time,
    and could kill a live new connection in `test_a_reconnect_after_the_host_returns…`.
  - A monitor calling `ssh.time.sleep(>0.02)` would advance the clock from a worker, which the class
    says only a calling thread may do (:1012). It could also raise `Runaway` there.
  - A monitor touching any other attribute raises `AttributeError` on its thread.
  - None of these fail the test. The project has no `-W error` (`pyproject.toml` `addopts` is only
    `--strict-markers`), so a thread exception is only a warning.
  - `settle` waits only for threads named `cluster-mcp-reconnect` (:1072).
- **Recommendation for the clock.** Give the monitor its own clock seam (`Event.wait` for sleeping,
  and a separate module attribute for its now). Do not use `ssh.time` or `_await`. Name its thread
  differently. Add a fixture that installs `threading.excepthook` and fails the new rows on any
  thread exception.
- **Which rows need the fake clock and which need real time.** The monitor's arithmetic (probe due,
  declared dead at due + bound, reset on inbound) can be unit-tested with a fake transport and a
  fake monitor clock. Every loopback row (R1–R5) needs real waits.
- **Real time per row with a 1 s connect bound.**

  | Row | Real time |
  |---|---|
  | R1 reachable | ≈1.2 s |
  | R1 unreachable (window 3 s) | ≈3 s |
  | R2, R3 | 1.5–2 s |
  | R4 quiet (`sleep 4`, past the 3 s bound) | ≈4.5 s |
  | R4 slow (≈1 MiB at 256 KiB/s through the proxy) | ≈4 s |
  | R5 | ≈3 s |

- **How late the existing real-time rows finish.** Each row ran alone 3 times at load ≈30, then
  3 times more with 3 spinners added (load ≈33–35).
  - `test_a_stalled_reconnect_…`: the call ended **+0.001 to +0.009 s** past its 3 s window
    (`STALL_LATE` allows 0.5 s). The worker ended **+0.045 to +0.081 s** after the call
    (`STALL_WORKER` allows 1.0 s).
  - The `DroppingSSH` row `test_a_lost_connection_is_never_did_not_start[after-the-command]`: `run`
    took 0.20–0.32 s, and the call phase 0.59–0.71 s.
  - A thread's `Event.wait(0.05)` overshot by 6.7 ms (median) and at most 10.5 ms.
  - So the scheduling cost seen when a row runs alone is under 0.1 s. The known flakes come from
    full-suite runs (`issues/stalled-reconnect-test-timing.md`), and some of them are not timing at
    all (`EOFError`, "0 workers ran").
- **Slack.** Measure each interval from the moment `go_silent` returns, not from the call's start.
  Allow `bound + 1.0 s` for a call's end: 10× the worst measured, with room for a full-suite run.
  Allow 2.0 s for a monitor or worker thread to end. Put the measured times in every violation
  message, so that a load failure is told apart from a behaviour failure.

## 4. CI budget

- **Measured locally.**
  - `tests/test_ssh_exec.py`: **131 s** in the handshake era (145 tests) and **146 s** in the modern
    era.
  - The full handshake-era suite: **579 s** (4819 passed, 14 skipped), in line with CI's 9.5–11.3 min
    per era against the 20-min timeout (`ci.yml` `timeout-minutes: 20`).
  - The slowest ssh rows already cost 4–11 s each (`stalling_link[packets-24000Bps]` 11.4 s).
  - The new rows add the same real time in both eras, so modern was not run in full.
- **Estimate per era.**
  - About 10 R1–R3/R5 loopback rows: 2–3 s each, ≈25 s.
  - R1 in every tool (run_command, sbatch, write_file, upload_file, download_file, read_file), both
    the unreachable and the reachable case: 12 × ≈2.5 s, ≈30 s.
  - 2–3 R4 rows: ≈13 s.
  - **Total ≈+70 s per era, about 12%. Both eras stay under 13 min.**
- **`CLUSTER_MCP_TEST_EVERY_KIND`.** It is read at import as
  `os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'` (`test_timeout_stop.py:73`,
  `test_startup.py:620`), and opt-in rows are chosen by building the `parametrize` list
  conditionally (`test_timeout_stop.py:114`). Nothing is skipped: only `need_shell` and `need_git`
  may skip (AGENTS § Testing, `test_only_need_shell_skips`).
- **What to put behind it.** Login shells beyond bash, and the reachable-case repeats beyond one exec
  tool and one SFTP tool. The default suite keeps every tool's unreachable row, which is the R1
  contract, plus every R2–R5 row.

## 5. Develop-fails and mutants

- **How the last cycle's develop-fails gate worked** (`spec/timeout-process-cleanup/verify/develop-fails.py`).
  - It copies `git ls-files -co --exclude-standard` (without `packages/`) into a `TemporaryDirectory`.
  - It extracts `git archive <BASE> packages` there with `tar`, then runs `uv sync --locked` with a
    copy of `os.environ` that drops `VIRTUAL_ENV`/`UV_PROJECT*`.
  - It runs one pytest child with `--junitxml` and `-k`.
  - It requires every `EXPECTED_FAIL` row to have a `<failure>` (not an error or skip) carrying the
    stop message, and every `EXPECTED_PASS` row to pass, which proves the copy runs.
  - Its stated footprint is one sync and one child, under 500 MB, taking 19–104 s.
- **Mutants.** `apply` copies every member and requires each `old` to occur exactly once
  (`mutants.py:5310-5335`). `test_mutation_anchor_applies` compiles the result (`test_mutations.py:39-50`).
  - There are 1,097 cases, 100 of them on `core/executor/ssh.py`. Each one the fix's edits touch
    (`_ensure_connected`, `_live`, `_collect`) must be re-planted in the same commit.
  - A child took **3.2–3.7 s** for a fake-clock target. Add the row's real time for a loopback
    target (≈6–8 s).
- **Sketch for this cycle.**
  - A develop-fails script (named with a hyphen, never as a Python module; run as `uv run python -I
    …`) on the same model, with `BASE` = develop's commit.
  - It runs one child per era in sequence (`CLUSTER_MCP_TEST_ERA` set in a copy of `os.environ`, at
    most 2 parallel workers).
  - `EXPECTED_FAIL` lists the R1–R5 rows with each one's message fragment, for example `past its`
    or `not … within`. Each row's own watchdog turns develop's 3600 s hang into a failure (as
    `_tool`'s `drive(..., timeout=120)` does), and that watchdog should be the bound plus slack, not
    120 s.
  - `EXPECTED_PASS` lists the R4 rows, which pass on develop because develop never cuts.
  - The mutant sweep: new cases for "probe never sent", "dead at reply-only", "detected but transport
    not closed" and "monitor counts quiet as dead". Run them with `tests/mutants.py` once per era.
  - The child starts with `start_new_session=True`. The gate kills its process group on exit and
    then asserts `pgrep -f <scratch dir>` is empty.
  - Footprint: one sync, ≤ 2 pytest children, under 1 GB, about 3 min per era.

## 6. Markers, fences and names

- **Markers.** A loopback row is `integration`: the unit guard refuses `socket.connect`
  (`conftest.py:138-145`).
- **Fences.** A row that calls a tool through `_tool` (an in-process server) must request `executes`
  (AGENTS § Testing, "The fence"), as the slow-link rows do (:487). Direct `executor.run`/`put` rows
  need neither fixture.
- **The sandbox.** The server's execs already start with `bin/sandbox.sh` (ssh_server.py:530-540).
  That satisfies the global `Popen` fence and gives a throwaway HOME, with the SSH host and auth
  variables unset.
- **Names.** Add a new `# ----` section after "A host that goes down and comes back" (:1874), with
  `silent` in every test name so that a narrowed verify can select `-k silent`. Update the
  `ssh_server.py` docstring and the AGENTS § Testing entry for `test_ssh_exec.py` in the same commit.

## Recommendation

1. **Fixture.** Add the proxy to `ssh_server.py` with `go_silent(new='hold')`, `come_back()`, `rate`
   and a pinned `SO_RCVBUF=16 KiB`. Use `hold` for "host gone" (cause `timed out`). Start a transfer
   before going silent, and assert in the R5 row that the write path is held.
2. **Detection.** Silence is measured from the last inbound message of any kind. Add an R4 row
   through the proxy's `rate` (replies 3–13 s late, data still flowing) to pin this. Probes are never
   a blocking `global_request(wait=True)` on a calling thread.
3. **Clocks.** The monitor never reads `ssh.time` or `_await`, and its thread is not named
   `cluster-mcp-reconnect`. Unit-test its arithmetic with its own fake clock. The loopback rows run
   in real time with `CONNECT_TIMEOUT=1`.
4. **Slack.** Allow `bound + 1.0 s` from `go_silent` for a call's end and 2.0 s for a thread to end,
   and report the measured times in the violation.
5. **CI budget.** ≈+70 s per era. Login shells beyond bash and the extra reachable-case tools go
   behind `EVERY_KIND`.
6. **Gates.** A develop-fails script and a sweep on `timeout-process-cleanup`'s model, both eras in
   sequence, with each row's watchdog at the bound plus slack so that develop's hangs read as
   failures.
