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
- A hung `local` probe whose login profile ignores SIGTERM outlives a server that failed open and exited 0 (block reviewer: `trap '' TERM; sleep 67`, server exit 0 at 10.9 s, the probe's group still running, killed by the reviewer). The mechanism is the `local` executor's timeout, which sends SIGTERM only; it predates the cycle for every `local` command. Recorded as a dated note on [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md) (`2339c0e`), whose Outcome covers any exit.

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
