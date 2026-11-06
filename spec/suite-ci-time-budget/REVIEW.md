# REVIEW — Each CI era job keeps a margin under its timeout, and every row keeps its proof

> Adversarial QA by `code-review`, run in an isolated context (one fresh subagent; the diff touches
> no coupled-core path, so no debate). The correctness pass graded the branch diff against
> [`GOAL.md`](GOAL.md) and the repo's `AGENTS.md` only. It did not see `PLAN.md` or `TECH.md`.
> Every finding cites an executed command.

- **Reviewed commit:** 567ce36d5ad0c2026d1b5566318265ddf0994b09  ·  **Base:** origin/develop (5f6e984)  ·  **Date:** 2026-11-06
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3

## Verification run

- `git diff origin/develop...HEAD -- . ':(exclude)spec/'`, `git log --oneline origin/develop..HEAD`: six files outside `spec/` (workflow, `AGENTS.md`, the new test module, two seed status lines, one seed sighting).
- `--collect-only` of the eight suite commands per era, against a base clone at 5f6e984: 44 + 154 + 507 + 4325 = 5030 ids per era, 0 duplicates, 0 base ids missing; the difference from the base's 4993 is exactly the new module's 37 ids, in both eras.
- `uv run pytest -q tests/test_suite_parts.py` in both eras: 37 passed each.
- Negative controls in a scratch clone, reverted: `-x` on one workflow step, an era variable on one step only, and one `--ignore` dropped from all three lists each turned `tests/test_suite_parts.py` red; a consistent move of a module between commands stayed green.
- Process-wide fixtures: planted violations (an unmarked test, a `Popen` under the unit guard, the shim on `PATH`, the probe-skip variable, a leaked executor) failed as on the base under each of the four commands, in both halves of the `-k` pair, and in the modern era.
- CI reads: run 42229254457 attempts 1–4 at `ef301e6`; head push run 42234516192 at `567ce36`; base run 42210568801 at `5f6e984`.
- Full split suite locally: **not observed** by the reviewer. Head run 42234516192 ran all eight commands green on CI.

## Requirement → evidence matrix

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `.github/workflows/ci.yml`, `01239b8` | `gh run view --attempt N --json jobs`. Worst job per attempt on 42229254457: 7:33, 7:34, 7:35 (replaced), 7:10. Head run 42234516192: 7:04. All nine jobs `timeout-minutes: 20`. Base 14:41 and 15:00. | ✅ |
| R2 | `ci.yml`, `AGENTS.md` `verify`/`gate`, `01239b8` | Local id partition against the base clone; CI pass counts 44 + 154 + 511 + 4324 = 5033 = 4996 + 37 per era, 0 skipped | ✅ |
| R3 | none needed | No test code, parameter, wait, conftest or harness changes; the only test file is new | ✅ (vacuous) |
| R4 | none needed | Planted violations under each command and era, as above | ✅ |
| R5 | `issues/stalled-reconnect-test-timing.md`, `567ce36` | Attempts 1, 2, 4 green in all nine jobs. Attempt 3's one failure (`--attempt 3 --log-failed`) is a row the seed names, and the dated sighting matches the log | ✅ |
| R6 | `ci.yml`, `AGENTS.md`, `tests/test_suite_parts.py`, one commit `01239b8` | The module's tests and their negative controls; no stale job names outside `spec/` and `issues/` | ✅ |
| R7 | `AGENTS.md` `ci budget` row, `567ce36` | Each of the eight recorded worst times equals the maximum over attempts 1, 2 and 4 from `gh` | ✅ |

Unmapped changes: the `ROADMAP.md` and `issues/suite-ci-time-budget.md` status flips to `adopted:suite-ci-time-budget`, the standard adoption bookkeeping.

**Timing facts, for Geoffrey's judgment, not ruled on here.** Summed pytest time per era: handshake 860 s on the base against about 887 s on head-tree attempt 1; modern 878 s against about 889 s. In every head-tree run, 1–3 of the eight jobs spent 152–219 s in the provisioning step, against about 10 s elsewhere and 10–12 s in the one base run. Those slow steps account for every job time above about 5 minutes.

## Findings

### [MEDIUM/CONFIRMED] § Testing's per-module list omits the new test module and its checks
- **Where:** `AGENTS.md` § Testing, the module list after "Every module is built around pure check functions" (about line 308).
- **Failure scenario:** § Testing says the check functions' names and test ids "are a contract: renaming one breaks a gate loudly", then lists each module with its checks. `tests/test_suite_parts.py`, with `suite_part_violations` and `list_violations`, is absent. A later plan or gate that reads that list for checks and ids won't know these exist, and a rename of either wouldn't read as breaking a documented contract. § Conventions does describe the module, so the record is incomplete rather than wrong.
- **Evidence:** a `comm` of the bulleted `tests/test_*.py` modules against `ls tests/test_*.py` prints `tests/test_suite_parts.py` (39 bullets for 40 modules); `grep -n suite_part AGENTS.md` finds nothing in § Testing. Re-checked by the orchestrator: 39 against 40.
- **Touches:** `AGENTS.md` § Testing (no numbered invariant; not § Conventions).
- **Routed as its class:** § Testing's list names every test module, each with its marker(s) and every check function it exports. Fix it by adding the new module's bullet, then sweeping the list against `tests/test_*.py` and each module's `*_violations` (and other exported checks) for any other omission. Keep the fix documentation-only: no test row added or changed, so the suite each job runs stays the one R1 measured on `ef301e6` (GOAL Q5).

## Human-gate triggers

- None. The finding is in `AGENTS.md`, not on § Invariants' high-blast-radius list, and touches no `[human gate]` section.
