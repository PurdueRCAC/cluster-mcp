# REVIEW — An installed capability is served only where the cluster has it

> Adversarial QA by `code-review`, run in an isolated/clean context (subagents). The correctness pass
> grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only**
> — it does not see `PLAN.md`/`TECH.md`. Every finding cites an **executed** command, not an
> assertion.

- **Reviewed commit:** `949efb5`  ·  **Base:** `c520432` (`origin/develop`)  ·  **Date:** 2026-11-01
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`

## How it ran

The debate variant: the diff touches `core/__init__.py`, in the profile's `coupled core`. Two blind
reviewers, ship and block, each in its own clone of `949efb5`, with only the GOAL's text, the
rubric's text, the spec-excluded diff and the repository. Both left their clones clean and no
process of theirs running (each killed a leftover it had planted itself; see F4). The ship
reviewer disclosed that one broad grep printed three lines of `spec/capability-probe/` before its
filter caught them; nothing in its report relies on them.

**Contract drift.** None: `GOAL.md` is unchanged since `e3791df`, the foreman's rulings on Q1–Q6.

## Verification run

Both reviewers, independently: `uv sync --locked` and `uv lock --check` ok; `uv run pytest -q` and
`CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` 4382 passed, 14 skipped (the bash 4.1 rows; one
block-reviewer run also failed the seeded load-flaky reconnect test, which passed 3/3 alone);
`bin/sandbox.sh uv run cluster-mcp --help` exit 0 and shows the flag and the variable. CI on
`949efb5`: 4396 passed per era (6.9 / 6.7 min). Live drives under `bin/sandbox.sh`: `local` with stub
commands on `PATH` from a login profile (present, absent, partial, hung, `exit 0` profiles); `ssh`
through the real `MCPServerApp.main` with the suite's loopback SSH server (2 logins: site read, then
probe; then tool calls); `delegate` over HTTP with two JWT users; a core-only venv; planted
third-party capabilities that declare commands, well-formed and malformed.

## Requirement → evidence matrix

| R-ID | Verified how (both reviewers unless noted) | Status |
|------|--------------------------------------------|--------|
| R1 | Slurm absent → 17 tools; `myquota` absent → RCAC tools, resources and text gone; all absent → 7 tools; one INFO line naming the distribution and the missing commands | ✅ |
| R2 | Members declare 6 and 2 commands; a planted capability is withheld and served with no core edit; malformed declarations refused at load, exit 5, 0 logins | ✅ (F2 dropped, below) |
| R3 | All present: served surface equal to the fixture, instructions byte-identical to `--skip-probes`; `- name:` lines equal served tools under every withheld set driven | ✅ |
| R4 | `local`: 1 login per start; `ssh`: connect, site read, probe, then the server; never a second probe | ✅ |
| R5 | Hung profile: `local` initialize at 10.8 s; `ssh` at 20.9 s (10 s site read + 10 s probe); core-only and no-commands installs run 0 probe commands | ✅ |
| R6 | Hang, profile `exit 0`, dropped SSH link: one WARNING per capability, every tool served, start continues | ✅ |
| R7 | `delegate` over HTTP: one skip line, 0 logins, same tools and instructions for two users | ✅ |
| R8 | `--skip-probes`; the variable at `1`, `0`, `" "`, `yes`: 0 logins and one skip line; empty probes | ✅ |
| R9 | `--help`, `--version`, `--generate-token`, a failed connect (exit 5), budget refusals (exit 2), load refusals: 0 logins | ✅ |
| R10 | §4, §7, §9, § Configuration and README describe the probe; elsewhere F1, F3 | ❌ F1, F3 |

Clarifications Q1–Q6: each verified as ruled.

## Findings

### F1 [HIGH/CONFIRMED] § Invariants §7 promises no capability code runs after the load; field values still can
- **Where:** `AGENTS.md` § Invariants §7 (the new "the record is exactly a `Capability` … is plain data and runs no capability code") and the `capabilities.py` footgun; `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:181-186`, where `name`, `tools`, `instructions` and `resources` are `isinstance` checks and `order` is `isinstance(int)`.
- **Failure scenario:** a capability whose `order` is an `int` subclass, or whose `resources` is a `tuple` subclass, runs its code after the load: at the pre-probe budget composition (`core/__init__.py:227`, via `composed()`) and again when the server is built. An `order.__eq__` that exits ends startup with exit 0 and no message; one that raises gives a CRITICAL line without the distribution.
- **Evidence (block reviewer):** planted `tricky-cap` in a fresh venv, `bin/sandbox.sh …/cluster-mcp -e local </dev/null`: nine `order.__eq__`/`__lt__` calls after `Execution mode: local`, before the probe; with the override, `resources.__iter__` at server build; `TRICKY_EXIT=order.__eq__` → exit 0, silent; `TRICKY_RAISE` → `CRITICAL tricky capability raised after its load`, exit 5, distribution unnamed. The same runtime behaviour exists at `c520432`; the diff adds the guarantee that it does not.
- **Touches:** § Invariants §7 (a false invariant, HIGH by the rubric), R2 and R9 (what the load decides), capability-extras' property that whatever a capability declares fails at the load or not at all.
- **Routed as the property:** after the load, no read of a loaded record runs capability code. Every value the core reads from the record — `name`, `order`, `tools`, `instructions`, `commands`, `resources` and each resource entry with its keys and values other than the handler — is an exact built-in type, decided at the load and refused naming the distribution. The handler is the one piece of capability code, called only by a request (and by the load's own scratch assembly). Pin a subclass of each type in each field, beside every member set, with one CLI representative per transport; sweep every alternative of each new check; make §7 and the footgun say exactly what holds.

### F2 — dropped by the foreman as judge: the declaration can name only files on `PATH`
- The block reviewer showed a capability declaring `module`, a function a login profile exports, is withheld where `bash -l -c module` works, and cited the GOAL's non-goal that LMOD "declares its probe against the contract R2 lands".
- **Ruling (foreman, as judge under the effort's autonomy decision, 2026-11-01): drop.** R2's wording — a capability "SHALL be able to declare a probe … with no edit to any core module", the members each declaring one — is met; Q1 left what a probe declares to the plan. The lookup matches what a tool runs: the members' tools `exec` files on `PATH`, which a function never satisfies. LMOD's tools run `$LMOD_CMD`, and this cycle's P3 recorded on `issues/lmod-tool-group.md` that probing it needs a second kind of declared data, a core edit in that cycle. Reported to Geoffrey for override.

### F3 [MEDIUM/CONFIRMED] The repository map and the architecture section miss the probe
- **Where:** `AGENTS.md` § Repository map (no row for `core/probes.py`; the `__init__.py` row and the two members' `capability` rows don't mention the probe, `--skip-probes` or `commands`) and § Architecture & data flow ("One read happens before any request"; in `ssh` and `local` the probe is a second).
- **Evidence:** both reviewers: `sed -n 138,241p AGENTS.md | grep -c probes` → 0; the `ssh` drive's login log shows site read, then probe, then the first tool call.
- **Routed as the property:** every part of `AGENTS.md` that lists the core's modules or describes what runs at startup, and each member's row, describes the probe as §4, §7 and §9 do.

### F4 — out of scope, recorded on the existing seed
- A hung `local` probe whose login profile ignores SIGTERM outlives a server that failed open and exited 0 (block reviewer: `trap '' TERM; sleep 67`, server exit 0 at 10.9 s, the probe's group still running, killed by the reviewer). The mechanism is the `local` executor's timeout, which sends SIGTERM only; it predates the cycle for every `local` command. *(Corrected by cycle 2's F2: the timeout sends SIGTERM, then SIGKILL after `GRACE`; the probe's daemon worker is abandoned at the deadline and cut off by the interpreter's exit within that grace.)* Recorded as a dated note on [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md) (`2339c0e`), whose Outcome covers any exit.

### F5 [LOW/CONFIRMED] The deadline's placement survives a mutant
- **Where:** `core/probes.py`, `Pending.verdicts` (the AGENTS footgun "deadline taken in `start()`, never at the wait").
- **Evidence (ship reviewer):** `self._answered.wait(self._deadline - time.monotonic())` → `self._answered.wait(self._bound)`: `tests/test_probes.py tests/test_probe_startup.py` 560 passed. Unreachable from `run()` today, which waits straight after `start()`, but the documented contract has no pin.
- **Routed as a mutant sweep** over every decision in `core/probes.py`'s timing (where the deadline is taken, what the wait is given, what happens past it), each alternative under every member set and both eras, equivalents recorded.

### Triage of a PLAUSIBLE item
- **The subclass refusal widens a load refusal** (block reviewer, PLAUSIBLE, citing R9's "existing startup refusals SHALL be unchanged"). **Ruling: drop.** R9's refusals — a load failure, a failed connect — still occur unchanged and first; refusing a `Capability` subclass is a load refusal under §7's existing property, ruled during build (TECH P2), and no released version accepts capabilities.

### Out of scope (recorded, not blocking)
- The seeded load-flaky reconnect test failed once under the reviewers' load and passed alone; it is `issues/stalled-reconnect-test-timing.md`.

## Human-gate triggers

- **Triggered:** F1 is CONFIRMED in `core/capabilities.py` and § Invariants, on the high-blast-radius list. Under the effort's autonomy decision the foreman is judge at human gates; it ruled F1 a fix (routed above) and reported it to Geoffrey on 2026-11-01. The trigger stays recorded until publish.

## Optional completeness sub-pass

Not run.

## Review cycle 2 — changes-requested (2026-11-01)

A fresh blind debate (ship and block, xhigh, each in its own clone) over `541785c`, the cycle-1 remediation (`6196062`, `541785c`). CI green on `541785c`: 4521 passed per era, 6.2/6.0 min. Both reviewers: `uv sync --locked`, `uv lock --check`, both eras at 4507 passed, 14 skipped (the bash 4.1 rows CI runs), 400–422 s per era locally; `--help` in the sandbox lists the flag and the variable. Drives as cycle 1's: `local` with stub commands on `PATH`, the loopback SSH server, `delegate` over HTTP with JWT users, core-only and planted venvs, both protocol eras.

### Matrix

| R-ID | Verified how (both reviewers unless noted) | Status |
|------|--------------------------------------------|--------|
| R1 | Slurm absent, RCAC absent, both: no withheld tool, resource (alias included) or instruction line served; one INFO line naming distribution and missing commands; `local`, `ssh`, HTTP, modern era | ✅ |
| R2 | Members declare 6 and 2; a planted third-party capability withheld and served with no core edit; malformed declarations (list, `'a;b'`, exiting tuple subclass) refused at load, 0 logins | ✅ (block F3 below) |
| R3 | All present: tools, resources, instructions and initialize result byte-identical to a `c520432` build over `local` and `ssh`; `- name:` lines equal the served tools under every withheld set | ✅ |
| R4 | `local` 1 login, `ssh` 2 (site read, probe); the probe's executor is the shared one; first answer after the probe | ✅ |
| R5 | Hung profile: `local` first answer 10.7–10.8 s; `ssh` 20.0–20.8 s (site read + probe); core-only 0 logins | ✅ |
| R6 | Profile `exit 3`, hang, link lost on the second exec, rc files printing a fake `end 0`: one WARNING per capability, all served, exit 0 | ✅ |
| R7 | `delegate` with and without the override: one skip line, 0 logins | ✅ |
| R8 | Flag; variable at `0`, `false`, `" "`: 0 logins, one skip line; empty probes | ✅ (F4 below) |
| R9 | Budget (exit 2), missing host (exit 2), refused connect (exit 5, no probe line), load refusal (exit 5), `--help`/`--version`/`--generate-token`: 0 logins | ✅ |
| R10 | §4, §7, §9, § Configuration, the repository map, architecture, § Testing, footguns, README match the code and the drives; the one false text is the seed (F2) | ❌ F2 |

Clarifications Q1–Q6: each verified as ruled.

### F1 — out of scope, recorded on the existing seed (block MEDIUM; ship S1)
- Both reviewers reproduced cycle 1's F4: a `local` probe behind a profile of `trap '' TERM` then a hang outlives a server that failed open at 10 s and exited 0. The block reviewer found the mechanism: `run_process` sends SIGTERM, waits `GRACE`, then SIGKILL (`core/executor/launch.py:602-610`); the probe's worker is a daemon abandoned at the deadline, so when the client closes stdin within that grace the interpreter's exit ends the worker before its SIGKILL. Holding the server 2.5 s past its first answer left nothing behind.
- **Ruling (foreman, as judge): out of scope**, as in cycle 1; recorded on [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md). It needs a TERM-ignoring hung login profile and a client that leaves within a second; the seed's Outcome ("exits for any reason") covers it, and the fix — process groups reaped at exit — belongs to the launcher, for tool calls as well as the probe. The seed must state the mechanism truly: F2.

### F2 [MEDIUM/CONFIRMED] The seed misstates the leak's mechanism
- **Where:** `issues/local-command-outlives-server.md`, the 2026-11-01 note ("since the executor's timeout sends SIGTERM only"), and this file's cycle-1 F4, which says the same.
- **Evidence (block reviewer):** `launch.py:602-610` sends SIGKILL after the grace; the hold control above leaves no process. A cycle working from the seed's R1 sketch (signals only) would miss the normal-exit case.
- **Routed as the property:** every record of this leak states the mechanism the code shows (an abandoned worker cut off within the SIGTERM→SIGKILL grace at interpreter exit), and the seed's sketch covers a normal exit.

### F3 — the declaration covers only files on `PATH` (block MEDIUM, interpretive)
- Cycle 1's F2 again, with the same evidence (a planted capability declaring an exported `module` function is withheld where `bash -l -c module` works) and the diff's own note on `issues/lmod-tool-group.md`. **Ruling unchanged: drop**, as cycle 1 ruled; still with Geoffrey for override.

### F4 [LOW/CONFIRMED] Two documented behaviours survive mutants
- **Log levels** (both reviewers): swapping INFO and WARNING in `_served` (`core/__init__.py`) survives `tests/test_probe_startup.py tests/test_probes.py` (564 passed); a CLI drive prints `WARNING … withheld` and `INFO … served without a probe answer`. § Invariants §4 names the levels.
- **Override precedence** (both reviewers): checking the variable before the flag in `_resolve_skip_probes` survives 685–722 tests; with both set, the skip line names the variable, where §4 and the docstring say the flag.
- **Routed as the property:** each documented level and the skip line's naming are pinned beside every member set, with an alternative sweep of `_served`'s and `_resolve_skip_probes`'s decisions.

### Noted, not blocking
- **Two refusal messages reworded** (ship S2): a non-str `uri` and a non-`True` `executor` no longer repr the value. The refusals stand unchanged and first; the wording is cycle 1's F1 fix (no repr of capability values). R9 met.
- **Scope:** the exact-type hardening of every field (cycle 1's F1) refuses a `Capability` subclass, an `IntEnum` order or a `str`-subclass name; both reviewers note it, neither blocks. No released version accepts capabilities.
- **Suite time** is ~6 min per era in CI against the 20-minute job timeout.

### Bound
This is review cycle 2 with changes requested: the bound. Escalated to Geoffrey on 2026-11-01.

### Geoffrey's rulings at the bound (2026-11-01)
- **Scoped fix, foreman verifies, land.** F2 and F4 are fixed in one remediation build; the foreman verifies the fixes on the commit itself (the corrected seed against `launch.py`, each new pin red on `541785c` and green after, the sweep killed in both eras), then publishes. No third review.
- **F3 (PATH-only declarations): the drop stands.** The LMOD cycle adds the second kind of declaration.
- **Registered tool objects:** seed a future cycle that makes them inert (exact types), with a ROADMAP entry, in this remediation. No code now.

## Cycle 2's items — fixed and verified by the foreman; approved (2026-11-01)

- **Ruling:** Geoffrey, 2026-11-01, at the review bound: "Scoped fix, I verify, land". One remediation of cycle 2's F2 and F4, verified by the foreman, landing without another review cycle.
- **Fix:** `493190c` (P2: F4), `f24af70` (P3: F2 and the tool-object seed), `e9a43f1` (P3 closed; the cycle-2 deferral above links its seed, which the frozen ledger requires).
  - **F2:** `issues/local-command-outlives-server.md` states both endings (a killed server; a normal exit inside the SIGTERM→SIGKILL `GRACE` of the probe's abandoned daemon worker), and its R1 covers a normal exit for the probe and tool calls alike. The ROADMAP entry and a recorded-limit bullet in § Invariants §3 say the same. The checker `remediation/F6-leak-mechanism.py` reads the signal order, `GRACE` and the daemon flag from the code. Cycle 1's F4 text above carries a correction.
  - **F4:** every logged probe line is compared as `(level, message)` beside every member set, and a `flag-and-variable` row pins the flag winning. 45 cases sweep the levels, the precedence, the lines' naming and the emptiness test; all are killed in both eras, with 3 equivalents recorded (`log.warn`, and two `is not None` tests unreachable through `env_setting`).
  - **New seed:** `issues/capability-tool-objects-inert.md` (Part III, unshaped), per Geoffrey's ruling.
- **Foreman verification** (a clone of `e9a43f1`):
  - The seed's mechanism was checked against `core/executor/launch.py` (`run_process`: SIGTERM, read for `GRACE`, SIGKILL) and `core/probes.py` (daemon worker).
  - Each reviewer mutant was re-planted alone, and `tests/test_probe_startup.py` was run against it:

    | Mutant | Result |
    |---|---|
    | INFO and WARNING exchanged in `_served` | 244 failed |
    | the variable read before the flag in `_resolve_skip_probes` | 8 failed (the `flag-and-variable` rows) |
    | restored | 405 passed |

    Both had survived the suite at `541785c` (cycle 2, F4).
- **Gates:** the builder's P2 and P3 steps were green, run once each; the ledger was re-run green after the REVIEW link. Local suite: 4560 passed and 14 skipped per era, 403.8 and 396.0 s.
- **CI:** run 41360889561 on `e9a43f1` was green, 4574 per era. The pytest steps took 8.1 and 7.8 min, and the gate job 16.4 min against its 20-minute timeout; `541785c` had taken 12.7 min. The growth (53 rows) does not account for that; runner variance does: `4e772ec` ran 7.4 and 7.1 min for 3534 tests. The margin is reported to Geoffrey.
