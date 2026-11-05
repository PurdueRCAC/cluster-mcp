# Research 05 — tests the design touches, and the budget

Read-only survey for the plan step, 2026-11-01, worktree at `fix/timeout-process-cleanup`.
Design under study: a watchdog on fd 46 in the launch program, `TERM` added to the prologue's
`trap -` list, `LoopbackSSH` acting on the `signal` request, `RELAY` relaying TERM alone to the
command's pid, a second stand-in for a root server.

## 1. Existing timeout tests (R5: assertions unchanged)

| Test | Where | Rows | Asserts | Design changes outcome? |
|---|---|---|---|---|
| `test_timeout_returns_the_captured_output` | `test_executors.py:240` | local, delegate (`executes`) | `timeout_violations` (`:194`): no raise, `TIMEOUT_EXIT_CODE`, stdout `part\n`, stderr starts `perr\n`, elapsed ≤ 0.5+2·GRACE+2; `$$` pid gone within 3 s (`_gone`, `:227`) | No. `$$` is the script bash (SCRIPT's own `$$`). Under the new RELAY only the program bash gets TERM; it dies (`trap - TERM`), the watchdog then TERMs the group, so the pid is gone in ms. Today 0.5 s each. |
| `test_timeout_keeps_partial_output` | `test_launch.py:995` | raw `bash -c`, no program | output kept, elapsed < 3 | No (no program, so no watchdog). |
| `test_timeout_kills_the_process_group` | `:1006` | raw | background pid gone ≤ 3 s | No. |
| `test_a_timeout_sends_term_first_and_keeps_what_follows` | `:1020` | raw | `part\nstopping\n` | No. |
| `test_a_timeout_escalates_to_sigkill` | `:1028` | raw | TERM-ignorer gone, elapsed bound | No. |
| `test_timeout_is_bounded_when_a_process_leaves_the_group` | `:1049` | raw | elapsed < 0.5+2·GRACE+2 | No. |
| `test_a_profile_that_hangs_is_a_timeout` | `:1322` | local, ssh-tcsh (both through `run_process`) | `('', '', TIMEOUT)` | No. The profile hangs before the prologue, so no watchdog has started. |
| `test_a_timeout_signals_the_whole_group_term_first` | `:793` | unit, stubbed Popen | first signal is killpg TERM | No. |
| `test_timeout_returns_the_captured_output` | `test_ssh_exec.py:164` | LoopbackSSH × bash, zsh, sh, tcsh; `sleep 30`, timeout 1.5 | `timeout_violations`, bound 1.5+3 | Outcome same. Today the server ignores `signal`, `_stopped` reads a full GRACE, and `sleep 30` lives until `server.close()`'s KILL (2.5 s per row). With killpg of the session group, sandbox.sh may add a line to stderr (the row only checks `startswith`). |
| `test_a_timeout_before_the_records_names_the_status` | `:541` | ThrottledSSH | `LATE_NOTE` | No. `_collect` returns at `exit_status_ready()` before `_signal` (`ssh.py:249-252`), so no signal is sent. |
| `…_records_have_not_come_by_the_deadline_is_a_timeout`, `test_a_timeout_drains_what_follows_the_term` | `:2671`, `:2764` | unit fake channel; `_signal` patched | | No. |

**None depends on RELAY relaying INT or HUP, on relaying by `killpg`, or on the server ignoring
`signal`.** RELAY relays only signals sent to RELAY itself, and only `run_process`'s TERM and KILL
reach it. `test_a_signal_death_is_reported_and_reraised[delegate-*]` (`test_launch.py:1123`) has
the command signal itself. RELAY's re-raise still has to set `SIG_DFL` before `os.kill` (it already
does, `conftest.py:390-396`), because once RELAY no longer installs handlers for INT, Python's
default INT handler is back.

## 2. Users of the stand-in and the server under a timeout that fires

- RELAY: `conftest.py:379` (`executes`, `:441`) and `test_launch._wire_argv` (`:854`, the
  `delegate` wire). A delegate timeout fires only in `test_executors.py:240[delegate]`. The
  `executes` users elsewhere (`test_sbatch`, `test_writes`, `test_literal_args`, `test_probes`,
  `test_hygiene`…) either finish or use coded fakes for timeouts (`test_probes.py:216`,
  `test_site.py:214`).
- LoopbackSSH with a timeout that fires: only the four `test_ssh_exec.py:164` rows. ThrottledSSH
  (`:541`) sends no signal. DroppingSSH has no timeout row.
- For the handler: the "session process" is `proc` from `_launch` (`ssh_server.py:469`), which is
  `bin/sandbox.sh`, the leader of the group (`start_new_session=True`). Set "exited" where
  `execute` returns from `proc.wait()`: `:440` and ThrottledSSH `:604`. A channel needs a map to its
  `proc`, and a signal that arrives before launch is refused (sshd's `s->pid <= 0`).
- Paramiko has dispatched the channel id before the handler runs (`transport.py:2082`), and it
  accepts any `Transport._channel_handler_table` override (`:3009`), including a per-instance dict.
  A wrapper for `MSG_CHANNEL_REQUEST` has to save `m.packet.tell()` before `get_text()` and seek
  back before it hands a request that is not `signal` to `Channel._handle_request`.
- `server.close()` KILLs every exec group at teardown (`:483-490`), so an R6 ssh row has to check
  its pids inside the test body.

## 3. Tests that pin the program text

- `test_launch.launch_violations` (`test_launch.py:153`) checks the program against fixed copies:
  `PROLOGUE` (`:52-61`, gains `TERM`), `SENTINEL_LINE` (`:62`), `SUBSHELL_OPEN` (`:69`, which must
  come right after the sentinel line, `:168`), `SUBSHELL_CLOSE` (`:70`, `'\n) 2>&59 59>&-\n'`, gains
  `46>&-`), `STATUS` (`:71`), `END_LINE` (`:76`), and **`tail[end.end():] != RERAISE`** (`:191`),
  which fails on a release line between the record and RERAISE. The checker constants and the
  planted cases (`test_launch_check_catches_planted_programs`, `:395-414`) need updating, and so
  does `traps-kept`, which `.replace`s `'trap - EXIT ERR DEBUG RETURN; '`. With the text changed and
  the replace no longer matching, it plants nothing and the row fails. The argv rows use the same
  checker: `test_executors.py:91` (`launch_argv_violations`, `DRIFTS` `:144`, `_swap_program` `:139`).
- **`harness.launched_script` (`harness.py:637-661`)** finds the argv command with
  `body.find('\nexec ')`, where `body` starts at `; exec 59>&2 2>/dev/null\n` (the
  `_SENTINEL_LINE` regex `:631` stops at `>&2`). A watchdog line that starts with `exec 46>…` would
  be taken for the command. `RecordedPopen` (`conftest.py:316`), `test_identity.py:61`,
  `test_isolation.py:59`, `test_no_executor.py` and `test_ssh_smoke.decoded` (`:60`) all read
  through it. Either keep the watchdog off the start of a line beginning `exec `, or anchor the
  harness on the subshell's `(\n`.
- No test counts forks or processes, checks `/dev/fd/46`, or uses `ps`, `pgrep` or `lsof`.
  `test_launch.py:1350-1358` pins only the parked fds 47–49 and 57–59 in `STAGE`.
- **Background-job rows**, "nothing a completed command left running is signalled":
  - local and delegate: `test_executors.py:415` (`WRITER`), `:428`
    (`test_output_after_the_end_is_not_kept`), `:437` (profile holder);
  - launch: `test_launch.py:1093` (`test_the_call_ends_at_its_records`, `SEPARATION_WIRES`),
    `:1067` (raw);
  - ssh: `test_ssh_exec.py:314`, `:336`, `:596`.

  **None of them asserts that the job is still alive afterwards**: they check output and elapsed
  time only. A mutant that drops the release newline, letting the watchdog kill a completed
  command's jobs, survives every existing row. A new survival row per mode is needed: the job's pid
  is alive after the call and past 2·GRACE.
- Two risks for the build. (a) If the watchdog inherits fd 1 or fd 59 (the output pipes), EOF
  waits for its `sleep GRACE`, and `run_process` goes to KILL. That breaks R4's "no later than
  today" (local and delegate timeouts return in 0.5 s now). It needs `>/dev/null 2>&1` and every
  parked fd closed. (b) The release write to fd 46 raises SIGPIPE in the program bash if the
  watchdog is already dead, for example after a command's `kill -KILL 0` or `kill -HUP 0`; the
  launch's own status then changes before RERAISE. Guard that write.

## 4. Mutants

A `Case(id, file, edits, targets, why)` (`mutants.py:77-94`): `edits` are exact `(old, new)`
pairs, each `old` occurring once in the namespace-relative file. `targets` must each fail with
`why` in the failure. Cases are appended to `CASES` (`:377`, extended at `:3957`…`:4655`). There
are 931 cases. The runner applies only to `cluster_mcp` sources and `REPO_FILES` (`README.md` and
the surface fixture), so **no case can plant into `tests/ssh_server.py` or `RELAY`**, and none
does. To run: `uv run python tests/mutants.py --self-check ID…` (about 2 s per child).
`.github/workflows/mutants.yml` is `workflow_dispatch` only, gates nothing, and has a 30-minute
cap. `test_mutation_anchor_applies[<id>]` (`test_mutations.py`) runs in the suite and goes red
when an anchor moves. A new case is a new `Case(...)` entry plus a `--self-check` run.

Anchors on the touched text, and whether they break:

- `startup-traps-kept` (`mutants.py:1835`): old text is `…trap - EXIT ERR DEBUG RETURN; '`.
  **Breaks** when `TERM` is added. Re-plant it.
- `command-exec-in-place` (`:1908`): old text is the `program()` join line
  `SUBSHELL[0], *lines, SUBSHELL[1], STATUS, record_line(end_nonce), RERAISE])`. **Breaks** if
  the watchdog or the release line is spliced into that list.
- `end-record-one-stream` (`:1914`, `record_line`'s second line) and `signal-death-not-reraised`
  (`:1926`, the first line of `RERAISE`) break only if the release goes inside those texts. Use a
  constant of its own.
- `signal-death-unreported` (`STATUS`'s `case` arm) and `prologue-unalias-shared-line` (the
  prologue's first two lines, as a prefix) are safe.
- `run_process` loop: `timeout-group-not-killed` (`:1873`), `timeout-partial-output-dropped`,
  `timeout-completed-misreported`, `timeout-sigkill-dropped` and `timeout-sigterm-dropped`
  (`:1946-1953`) are unchanged by design. Their targets use raw `bash -c` launches with no
  watchdog, so they still kill.
- ssh: `ssh-timeout-raises` (`:865`), `ssh-timeout-no-drain` (`_stopped` call),
  `ssh-late-stop-silent`, `separate-note-dropped`. No `ssh.py` change, so all are safe.
- `TIMEOUT_ROWS` (`:116`) targets the three `test_timeout_returns_the_captured_output` rows.

New cases worth planting: watchdog dropped; its KILL dropped; fd 46 not closed in the subshell;
release newline dropped (killed only by the new survival rows); `TERM` left out of `trap -`.

## 5. The `EVERY_KIND` pattern and login shells

`test_startup.py:620`: `EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'`, used
as `@parametrize('kind', list(REJECTED) if EVERY_KIND else CLI_REJECTED)` (`:660`, `:721`).
`test_the_cli_drives_name_kinds_that_exist` (`:640`) checks that the representatives exist. The
suite never sets it; the out-of-suite checkers do. This is its only use.

ssh rows use `LOGIN_SHELLS` (`test_ssh_exec.py:90`, bash, zsh, sh, tcsh, ids by basename). Some
rows take a subset (`['/bin/bash', '/bin/zsh']`, `:153`, `:594`). `test_launch` has
`WIRES = local + ssh-{sh,bash,zsh,ksh,csh,tcsh}` and `SEPARATION_WIRES` (`:832-834`). Every shell
goes through `need_shell` (`conftest.py:88`), which skips locally and fails on CI. The bootstrap
starts with `exec` in every login shell, so the group and the watchdog are the same whatever the
login shell. One representative shell per command kind should do, with the matrix behind a flag
if wanted.

## 6. Wall-clock lessons

- `stalled-reconnect-test-timing.md`: wall-clock rows failed under full-suite load (macOS locally,
  and twice on CI as a paramiko `EOFError` on `test_startup_output_is_separated[tcsh]`, the latest
  on 2026-11-01). The failing text was not kept. Lessons:
  - keep the behaviour bound apart from a named scheduling slack;
  - measure from the right moment;
  - put the measured times in the failure message;
  - the loopback SSH server itself flakes under load.
- For an R6 "pid gone" row:
  - make each process outlive any slack by a wide margin (`sleep 30`, as today), so a generous
    check (deadline + 2·GRACE + 1–2 s, polling as `_gone` does) still separates fixed from broken;
  - take the deadline as start-of-`run` + timeout (over ssh, connect time makes that early, which
    is conservative);
  - write pids early and wait for the pidfile (a 0.5 s timeout races a slow login on CI; the ssh
    rows use 1.5 s);
  - `os.kill(pid, 0)` reads a zombie as alive, but orphans here are reparented and reaped, and the
    sandbox leader is reaped by `proc.wait()`.
- To fail on `develop` (`c8843b2`): local and root-delegate lose only a TERM-ignorer **that holds
  neither output stream**, because `run_process` skips KILL at EOF (`launch.py:609`). Non-root
  delegate under the new RELAY loses the child and the grandchild too. Over ssh, under the new
  server, develop's TERM reaches the group, so only the TERM-ignorer survives. A child and
  grandchild row there need not fail on develop, and R6 allows that.
- `sandbox-dirs-left-on-kill.md`: a KILL of sandbox.sh leaks its directory. In every mode the
  program bash is sandbox.sh's direct child, or RELAY's, which dies right after it. sandbox.sh has
  had TERM and runs its trap within ms of the program bash's death, long before the watchdog's KILL
  at +GRACE. **No new leak per row.** The ssh timeout rows should stop leaking one each, because
  `close()` no longer finds them alive. A leak remains where the group leader survives TERM (raw
  `test_a_timeout_escalates_to_sigkill`, as today).

## 7. Budget

- CI (`.github/workflows/ci.yml`): `suite-legacy` and `suite-modern` (`uv run pytest -q`, each 20
  min cap, ubuntu-24.04, installs zsh, tcsh, ksh and csh), and `gate` (20 min). The latest develop
  run, 41377927129, took 8m09s (modern) and 8m31s (handshake). No xdist; rows run serially.
- Locally (macOS, default era):
  `uv run pytest -q tests/test_launch.py tests/test_executors.py tests/test_ssh_exec.py --durations=30`
  ran 526 passed in 179.5 s (183 s wall).
  - Slowest rows overall: the slow-link and write rows over ssh (4–12 s).
  - Timeout rows: `test_ssh_exec::test_timeout_returns_the_captured_output[bash|zsh|sh|tcsh]` 2.51–2.53 s each;
    `test_timeout_is_bounded_when_a_process_leaves_the_group` 2.51;
    `test_a_timeout_before_the_records_names_the_status` 2.02;
    `test_a_timeout_escalates_to_sigkill` 1.50;
    `test_a_profile_that_hangs_is_a_timeout[local|ssh-tcsh]` 1.01;
    `test_timeout_keeps_partial_output` 0.72;
    `test_executors::test_timeout_returns_the_captured_output[local|delegate]` 0.57 and 0.51;
    the remaining raw rows about 0.5.
- Estimate for new rows: about 3–4 s each (timeout, plus up to 2·GRACE, plus the check).
  Representatives give 2 commands × 4 settings (local, delegate root, delegate non-root, ssh-bash),
  plus 4 survival rows: about 40–50 s. That is roughly 10 % of a CI era job, well inside 20 min.
  The full login-shell matrix adds about 20 s.
