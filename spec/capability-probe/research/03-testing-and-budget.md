# Research 03 — testing without a cluster, and the suite's budget

Read-only research for the plan step. Paths are repo-relative; `core/` is
`packages/cluster-mcp/src/cluster_mcp/core/`. Timings were measured on a macOS dev host in this
worktree, one or three ids at a time.

## 1. Which drives would probe

**`create_mcp_server` direct (no probe, unchanged).** About 90 calls across 20 test modules build
the server in process, through `create_mcp_server` or the harness builders `shared_server`,
`bare_server` and `delegate_server` (`tests/harness.py:779-798`). That covers `test_surface`,
`test_instructions`, `test_capabilities`, `test_storage_resource`, `test_protocol`, `test_registry`
and the tool tests. **`test_served_surface_matches_baseline` builds with
`create_mcp_server('none', site=SITE)`** (`tests/test_surface.py:277`) and passes no `capabilities`,
so it serves every installed capability (`core/server.py:128-131`). R3's "no fixture edit" therefore
holds as long as the probe lives in `run()` and the `capabilities=None` default keeps meaning "every
installed one". `test_capabilities.py` already passes `capabilities=` subsets for each `SETS` row
(`:250-275`, including `test_instructions_name_exactly_the_served_tools`). R3's cross-check with a
capability withheld is that same shape: an in-process row per withheld set.

**In-process `MCPServerApp.main` (would probe; all `unit`, under the guard).**
- `test_exec_mode.py:175-197`: `create_mcp_server` and Fabric's `Connection` are stubbed. Of 29
  `test_exec_mode_ladder` rows, 8 `local` and 7 `ssh` rows start. `test_explicit_mode_decides_alone`
  makes 36 starts per mode in a loop and asserts `guard.refused == []` (`:262`).
  `test_env_host_selects_ssh` has 6 `ssh` rows.
- `test_site_startup.py:37-73` (`start`): `test_startup_reads_once_where_the_mode_says` (3 rows),
  `test_a_hung_read_does_not_hold_startup` (3 rows; total start time must stay `< 1.0 s` with
  `READ_TIMEOUT` patched to 0.5, `:106-113`), and `test_budget_resolution` (12 rows, all `local`).
- `test_startup.py:301-321` (`run_app`): every row is a connect failure, so it never reaches a probe.

A `local` probe in these rows calls `subprocess.Popen` (`executor/launch.py:588`). The unit guard
refuses that call and **fails the test at teardown** (`tests/conftest.py:199-221`), even if the
probe itself fails open. An `ssh` probe against `FakeConnection` raises `AssertionError('the fake
connection runs nothing')` from `open_session` (`tests/test_executors.py:544-580`). That outcome must
fail open (R6) without a CRITICAL log line. So roughly 60 in-process starts change. All of them
already stub `create_mcp_server`; if `run()` passes the probed set as `capabilities=`, the stub can
record it.

**CLI drives through `bin/sandbox.sh` that reach the probe.**
- `test_transports.py::test_transport_lists_expected_tools`: 5 rows (`:148-165`), `-e local`.
  These **fail**: the test host has no Slurm or RCAC commands, so both members are withheld and the
  listing no longer matches `EXPECTED_TOOLS`.
- `test_cli.py::test_legacy_command_keeps_stdout_clean_on_stdio` (`:271-274`), `-e local`: stays
  green. It gains two stderr lines that do not contain `rcac-mcp` (the distributions are
  `cluster-mcp-slurm` and `cluster-mcp-rcac`).
- `test_core_only.py:93-115`: 2 drives with no capability installed, so R5 runs no probe. Unchanged.
- Every refusal drive runs before the probe (R9) and is unchanged: the load and contribution
  refusals in `test_startup.py`, connect failures, `--help`, `--version`, `--bogus`, the no-host
  failure, `--generate-token` (`test_tokens.py:98`), and `--instructions-budget 100`
  (`test_site_startup.py:156`). That last one holds only if the probe comes after `_resolve_budget`
  (`core/__init__.py:215`).

**Net: 6 CLI drives change (5 would go red), and about 60 in-process starts would go red.**

## 2. Keeping them green: override by default vs. stubs on PATH

**Environment and PATH reach the probe.** `bin/sandbox.sh` resets only HOME, the XDG directories and
the UV settings, and unsets the host and secret variables. Everything else, PATH and `BASH_ENV`
included, passes through to the command. `LocalShellExecutor` launches with
`Popen(...)` and no `env=` (`executor/launch.py:588`), through a `--norc --posix` stage into
`/bin/bash -l` (`:80-92`, `:189`, `:398-404`). On macOS, `/etc/profile` runs `path_helper`. That
puts the system directories first but keeps the entries it inherited after them, so a stub
directory appended to PATH still resolves for any command the system lacks. `BASH_ENV` is read after
`/etc/profile`, and the session shim already uses it to put itself first again
(`conftest.py:171-196`). `test_hygiene.py::test_path_shim_survives_a_login_bash` (`:483-492`) proves
that works through the pinned interpreter, and it passes on CI's Ubuntu runner. (Ubuntu's own
`/etc/profile` does not assign PATH while Debian's does. That comes from the packaging, not
something checked on the runner here, and `BASH_ENV` covers both.)

**How tests plant fake commands today.** There are two ways.
- The session shim puts `sudo` and `ssh` refusers first on PATH, with a `BASH_ENV` re-pin
  (`conftest.py:171-196`).
- `test_literal_args.install` and `argv_echo.install` put stand-ins (`sbatch`, `squeue`, `sinfo`,
  `scontrol`, `average_wait`, ...) into `home/bin` through `~/.bash_profile` (`test_literal_args.py:99`,
  `:232-241`; `argv_echo.py:37-41`). Those homes belong to the `executes` launcher or `LoopbackSSH`.

A CLI drive cannot use the home route, because `bin/sandbox.sh` makes a fresh `mktemp` HOME on every
run. **Stubs must not go in the shared shim directory.** The `BASH_ENV` re-pin runs after
`.bash_profile`, so shim stubs would shadow `test_literal_args`' recording stand-ins over loopback
SSH, which also gets the shim's `BASH_ENV` (`ssh_server.py:7-11`).

| | (a) override set by default | (b) stubs on PATH for every drive |
|---|---|---|
| Mechanism | A session `autouse` fixture beside `path_shim` sets the `CLUSTER_MCP_` variable in `os.environ`. Every child inherits it: `stdio_tools` (`harness.py:541`), `child_env` (`test_core_only.py:60-64`), the mutant child (`mutants.py:3976`) and the F7 `era_env` (`F7-mutant-alternatives.py:515`). Probe tests `monkeypatch.delenv` it. | A per-session stub directory appended to PATH, plus its own re-pin if a stub must shadow a real command. |
| Cost per drive | 0 | One login bash per probe (measured ~15 ms each under the sandbox, both lookups absent), plus the stub plumbing |
| In-process unit rows | Green, with no probe run and no guard trip | Still red: the guard refuses `Popen` in `local` mode whatever PATH holds |
| R3 "all present → unchanged" through the real CLI | Not exercised: the override path serves everything | Exercised |
| What a mutant of the override shows | Ignoring the override turns every existing `local` drive red, a strong kill | — |

Option (b) alone cannot keep the unit rows green, so it is not enough. **Use (a) by default, plus a
few dedicated (b) drives** that unset the override and put a stub directory on PATH. Those drives
run once with every probed command present (R3 through the CLI) and once with one member's commands
absent (R1 stderr line, tools, resources, instructions). An "absent" row depends on the test host
lacking the real command. Precheck that through the same login bash, and fail rather than skip on
CI (the `need_shell` pattern, `conftest.py:88-99`). Do not put the override in `bin/sandbox.sh`:
manual drives would never probe, and `test_hygiene`'s sandbox checks pin that file
(`test_hygiene.py:440-445`).

## 3. A fake executor for present / absent / slow / broken

The only fakes today are `harness.RecordingExecutor` (`harness.py:658-702`; every run exits 0 with
`<name>|<command>` or a responder's stdout), `test_site.AnsweringExecutor` (`test_site.py:186-194`;
one exit code for every run) and `test_context.StubDelegate` (`:55`). None can raise, hang, or return
the executor's no-answer codes: `TIMEOUT_EXIT_CODE = -1001`, `NOT_STARTED_EXIT_CODE = -1002` and
`CONNECTION_LOST_EXIT_CODE = -1003` (`executor/base.py:20-30`). Those three map directly onto R6's
"not finished / could not run / connection lost".

**Proposed design.** A harness `ProbeExecutor(RecordingExecutor)` whose responder returns a
`CommandResult` or raises. It covers present, absent, each sentinel code, an `Exception`,
`SystemExit` (0, int and str), a `BaseException`, a malformed return (`None` or a non-result), and
"hang until an `Event`". The slow case should not sleep through the full bound. Follow the
site-read pattern: `read_bounded` takes `timeout=` (`site.py:581-601`, tested at 0.3 s with a 3 s
sleep, `test_site.py:256-265`), `test_site_startup` lowers the module constant
(`monkeypatch.setattr(site, 'READ_TIMEOUT', 0.5)`, `:106`), and an `Event`-released hang leaves no
work behind (`test_site.py:795-803`). So: a module-level bound constant that a test can patch, a
`timeout=` parameter on the probe runner, and an `Event` the test sets in `finally`.

**One `read_bounded` lesson.** Its worker catches only `Exception` (`site.py:594-597`). A
`SystemExit` or `BaseException` raised on that daemon thread kills it silently, so the caller waits
out the whole bound and reports a timeout. A probe runner modelled on it must decide `BaseException`
explicitly, which is the review lesson that every failure mode is decided on one path.

**`ssh` end to end.** `tests/ssh_server.py` runs an in-process paramiko server on 127.0.0.1. Each exec
runs `<login shell> -c <exec string>` in a test home, inside `bin/sandbox.sh`, with an sshd-like
`env -i` environment and the shim's PATH and `BASH_ENV` (`:4-18`). `LoopbackSSH(home, '/bin/bash',
jail).executor()` gives an isolated `SSHExecutor` (`:477-481`), and stand-ins installed in
`home/bin` through `.bash_profile` resolve in the login bash. A CLI drive cannot reach it:
`_create_executor` calls `SSHExecutor(ssh_host)` with Fabric's defaults (`core/__init__.py:300-301`),
and the sandbox HOME has no key or config. Drive `ssh`-mode probes **in process** instead
(`integration`):
- call the probe runner on `server.executor()`, with and without stand-ins; or
- run `MCPServerApp.main` with `_create_executor` patched to return it and `create_mcp_server`
  stubbed to record `capabilities=`.

`DroppingSSH` and `ThrottledSSH` (`:20-46`) give real "connection lost" and "slow link" probes.

## 4. The suite's budget

- **Markers and switches.** `unit` and `integration` are mandatory (`conftest.py:63-71`).
  `CLUSTER_MCP_TEST_ERA` is `legacy` (the default) or `modern` (`harness.py:153-165`); CI runs the
  suite once per era (`.github/workflows/ci.yml:42-43`). `need_shell` skips locally and fails on CI
  (`conftest.py:88-99`). `CLUSTER_MCP_TEST_EVERY_KIND=1` is read only in `test_startup.py:620`. It
  widens the two refusal CLI drives from one kind per family (`CLI_REJECTED`, `CLI_UNLOADABLE`,
  `:624-633`) to every kind. The suite never sets it; only the remediation class checkers do.
- **Cost of one drive, measured.**
  - stdio `-e local` listing: 0.97 s (legacy) and 1.04 s (modern) (`test_transports[stdio-*]`).
  - http listing: 1.28 s.
  - legacy stdio initialize: 0.93 s.
  - load refusal over http: 0.89 s.
  - core-only stdio: 3.1 s.

  On CI, the previous cycle's 147 refusal drives added about 4 minutes per era, about 1.6 s each
  (`spec/capability-extras/REVIEW.md:203-207`, `TECH.md:518-527`).
- **Headroom.** The job has a 20-minute timeout (`ci.yml:29`). The suite takes about 6 min per era
  on CI, 12 min for both eras. Checkout, the apt shell install, sync, build, audit and twine are
  unmeasured here; estimate 1–2 min. That leaves about 6 min, at most about 3 min per era, so the
  hard ceiling is roughly 70–100 new drives per era. **Keep new CLI drives to about 12–16 per era**
  (≈30–40 s on CI) to hold a margin of ≥4 min. Never drive the 10 s bound through the CLI: a real
  hang costs at least 10 s per row per era.

## 5. Mutation testing

**Case shape.** A `Case` has an `id`, a namespace-relative `file`, exact `edits` (`old` must occur
once), `targets` (test ids), `why`, and optional `repo_edits` (`tests/mutants.py:77-93`). `run_case`
copies every member, plants the edits, and runs the targets in a sandboxed child pytest that inherits
`os.environ` (`:3973-4042`). A case is **killed** only if the child exits 1 and every target has a
JUnit `<failure>` carrying `why` (`:3989-4027`). `test_mutations.py:29-40` keeps every anchor
applying in the suite.

**Timing.** Measured locally: two in-process cases took 5.4 s together, and a 7-target startup case
with CLI drives took 4.9 s. There are 660 cases (`core/capabilities.py` 213, `core/__init__.py` 39).
`mutants.yml` runs all of them serially on `workflow_dispatch`, with a 30-minute timeout
(`mutants.yml:24-25`). At 2.5–3 s per case that is about 27–33 min, so **the on-demand job is already
at its timeout**, and AGENTS.md's "all cases about 3 minutes" (`AGENTS.md:1276`) is stale. New probe
cases make this worse. It gates nothing, but the plan should say so.

**The capability-extras sweeps.**
- `F2-mutant-sweep.py` covered each decision line in the loader. It is superseded, because sibling
  alternatives survived.
- `F7-mutant-alternatives.py` parses each file and enumerates every alternative for every decision:
  `if` always, never and negated; boolean operands and operator swaps; comparison negations; `except`
  clauses widened to `Exception` or `BaseException`, or dropped; tuple-member drops; sort keys; and
  statement placement at every boundary of `run()` (`:13-31`).
  - `coverage` requires each alternative's case to target a row beside every member set
    (`MEMBER_SETS`, `mutants.py:315-328`, `every_set`), unless `SET_EQUIVALENT` says why a set cannot
    observe it.
  - `cases` runs them through `mutants.py --self-check` once per era (`:515-535`, about 25 min).
  - `equivalents` plants each recorded equivalent and requires its targets to pass in each era, with
    `CLUSTER_MCP_TEST_EVERY_KIND=1` (`:538-575`).

## Recommendation

**Unit, in process, and fast. This is where every decision is pinned.**
- Use `ProbeExecutor` with a patched bound and an `Event` for the probe runner, beside every member
  set and every outcome: present, absent, the three sentinel codes, `Exception`, `SystemExit` (0, int
  and str), `BaseException`, a malformed return, and a hang.
- Assert which capabilities are served, the stderr lines (exactly one per withheld or failed-open
  capability, naming the distribution), and elapsed time under the bound.
- For each withheld subset, build `create_mcp_server(capabilities=probed)` and cross-check tools,
  resources and instructions. This is R3's withheld cross-check.
- Through `MCPServerApp.main` with `create_mcp_server` stubbed, cover:
  - the ladder: `local` and `ssh` probe once, after the executor and before serving; `delegate`
    logs and skips;
  - the override, as flag and as variable;
  - "no probe declared runs no command";
  - R9's ordering.
- Set the override in a session `autouse` fixture beside `path_shim`, so the ~60 existing in-process
  starts and the 6 CLI drives stay green with no fixture edit.

**Integration, `ssh` mode, in process.** Run the probe runner and `main` against `LoopbackSSH` with
`home/bin` stand-ins (present and absent), `DroppingSSH` (lost) and a hung stand-in with the bound
lowered.

**CLI drives, about 10–14 per era.** These unset the override and put a stub directory on PATH.
`local` stdio with every probe present lists the baseline surface (R3); the same drive with each
member absent (2 drives) and both absent (1 drive) checks tools, resources, instructions and stderr;
the override as flag and as variable (2 drives); stdin closed and http (2 drives) for withheld-start
and fail-open. `delegate` (R7) stays in process: the sandbox blanks the user map and the
secret.

**Mutants.** Use an F7-style sweep of the probe runner and its placement in `run()`, targeting
in-process rows beside each member set in both eras. Then raise `mutants.yml`'s timeout or shard it,
and correct `AGENTS.md:1276`.
