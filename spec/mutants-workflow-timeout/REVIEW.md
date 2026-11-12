# REVIEW — A dispatched mutation run finishes and reports every case

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** 30231aa068f3708e4260e998a53959bb1086c846  ·  **Base:** develop  ·  **Date:** 2026-11-12
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)
- **Mode:** a fresh blind pass over the full spec-excluded diff (`git diff origin/develop...HEAD -- . ':(exclude)spec/'`), one reviewer, no debate, no sequential fallback.

## Verification run

Evidence lives in the worktree's gitignored `.local/review1/` (`gates/` for the orchestrator's gate
runs, `reviewer/` for the reviewer's probes and logs).

**The profile's `verify` was not re-run in full this cycle.** It ran green, all 19 steps of P2's
frontmatter verify (which holds the profile's `verify`), at `fefa953`, the rebase re-gate. Every
commit after `fefa953` changes only `spec/`, `issues/`, `ROADMAP.md` and `AGENTS.md`:
`git diff --name-only fefa953..HEAD`, filtered of those four, is empty. The CI push run on the
reviewed commit, `43272456167`, which runs the profile's suite commands, is `completed`/`success`.

Spec-held gates, run by the orchestrator at the reviewed commit (`gates/gates*.log`):

- P5's frontmatter verify, all 6 steps → green: `prepush`, `untouched 5`, `workflow`, the F2 wrapper
  (`controls (re-anchored, pre-fill docs): ok`), `runs --runs-file … --final`, `docs --final`.
- P2's frontmatter verify, its non-suite steps → green: `rows 2` (12 + 12 passed), `workflow`,
  `docs`, `shard-mutants.py runner` (24 plants caught), `shard-mutants.py workflow` (9 plants
  caught), `drive` (shard 78/78: 14 cases killed, 3 controls passed), `prepush`, `uv lock --check`.
  Two steps are red at HEAD by design and were not counted:
  - `untouched 2`: the check is scoped to phase 2's files, and a later phase changed `ROADMAP.md`;
    `untouched 5`, the head-state check, is green.
  - the F1 wrapper alone: its two `docs final` controls plant into a row that P5 has since filled,
    so the plants miss; the F2 wrapper runs F1, accepts exactly those two, and re-runs them on the
    row before it was filled, green.
- P1's frontmatter verify, its non-scoped steps → green: `rows 1` (11 + 11 passed),
  `shard-mutants.py runner`, `pytest tests/test_mutations.py tests/test_mutant_shards.py
  tests/test_hygiene.py` (1368 passed).

The reviewer's executed checks (`reviewer/`), all under `bin/sandbox.sh` with Python 3.14:

- `uv lock --check` → pass.
- `tests/test_mutant_shards.py tests/test_suite_parts.py tests/test_hygiene.py` → 191 passed in each
  protocol era (`narrow-tests.log`); `tests/test_mutations.py` → 1,214 passed in each era
  (`narrow-gate.log`); `tests/test_mutant_shards.py -v` → 12 of 12 (`shards-tests-v.log`).
- `bin/sandbox.sh uv run cluster-mcp --help` → exit 0 (`help.out`).
- The three hosted dispatches, read only with `gh run view` (no dispatch, re-run or cancel):
  43255195424, 43260825655, 43265827418. Every case's verdict line, the plan's shard lists, each
  job's wall time and each run's span from dispatch were recomputed from their logs and `--json
  jobs` (`verdicts.py`/`verdicts.out`, `jobtimes.py`/`jobtimes.out`, `waves.out`, `step-times.out`).
- A drive of the shard job's steps verbatim under `bash -e -o pipefail`, interrupted at 25 s
  (`capped.py`, `capped.log`): the ledger exited 1 and named the 7 unreported cases and 3 controls.
- A 44-mutant sweep of the diff's runner and workflow code in a detached copy, killed against
  `tests/test_mutant_shards.py`, with a pristine control (`sweep.py`, `sweep.log`): 40 killed.
- The 8 cases the hosted runs report not killed, run locally on macOS at HEAD: all killed
  (`local-survivors.log`), as each seed states.

## Requirement → evidence matrix

All five R-IDs had something to run on the spec-excluded diff, so the reviewer graded all five; no
R-ID is an artifact deliverable under `spec/`.

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `.github/workflows/mutants.yml` (`plan` job, `--matrix`, dynamic matrix, `fail-fast: false`, `timeout-minutes: 15`, the cases' step capped at 12); `tests/mutants.py` (`SHARD_SIZE`, `shard_count`, `shard_ids`, `parse_shard`, `sharded`) | reviewer: all three hosted runs, 78 shards each, 1,164 unique cases, 1,164 verdict lines, none doubled, missing or foreign; Linux set equals local `--matrix` less `tpc-clobber`; worst job 3:11, runs 8:33 / 9:51 / 8:14 from dispatch; capped-step drive; 12 of 12 shard tests | ✅ |
| R2 | the shard job's `ledger` step (`if: always()`), `report_violations`, `--matrix` exiting 1 on no case | reviewer: each hosted run failed, and every failing job's ledger named its case (7, 8, 7 jobs); 70–71 passing ledgers a run; the no-case path by test and by executed `bash -e`; `pipefail` through the `tee` (executed) | ✅ |
| R3 | cases picked up through `--matrix`, no workflow edit; the `mutants budget` row's fit rule | reviewer: `test_the_run_holds_every_case_this_platform_defines`, mutants `matrix-short` and `shard-drops-one` killed. The "tell without dispatching" clause: see F-a | ⚠️ partial, pending triage (F-a) |
| R4 | `AGENTS.md` § Factory `mutants budget` row; § Testing's measured cost, replacing "about 2 s / about 3 minutes", pointing to the row | reviewer: every figure in the row recomputed from `gh run view --json jobs` and matched (plan 0:13, 78 per-shard worsts in order, slowest 3:11 = 12.7 s a case, run 9:51); the row's commit attribution is wrong (F-b) | ❌ (F-b, LOW) |
| R5 | `AGENTS.md` § Testing; `mutants.yml` header | reviewer: `origin/main` carries the workflow; `git grep` (spec excluded) finds no "becomes dispatchable" left; three dispatch runs exist on the branch | ✅ |

Unmapped changes (possible scope creep): none material. The shard job's step that installs the
login shells serves R1/R2 (a case whose targets use those shells must reach a verdict); the five
`issues/` seeds and their `ROADMAP.md` entries are GOAL Q3's; `ci.yml` is untouched and no case or
test bound changed. A grep for spec ids over the added test and workflow lines found none.

## Findings

Orchestrator sanity check: both findings carry executed evidence, re-checked by the orchestrator
(`gh run view --json headSha` on the three runs; `waves.out`; `grep -n -i concurren` over
`AGENTS.md`, the workflow and the runner). Neither touches a high-blast-radius path.

### [MEDIUM/PLAUSIBLE] F-a — the budget row cannot tell a cycle whether the whole run still fits
- **Where:** `AGENTS.md:1801` (`mutants budget` row)
- **Failure scenario:** R3 asks that the recorded figures let a cycle that adds cases tell, without
  dispatching, whether the full run still fits. The row's whole-run test is "while its shards, run in
  waves of the account's concurrent jobs, still finish within the 15 minutes", but it records neither
  that concurrency nor the wave count. Measured: 20 concurrent jobs in each run; the 21st, 41st and
  61st shards start at 95–114 s, 206–235 s and 312–384 s, so 78 shards ran in 4 waves. At about 2:20 a
  wave the run would cross 15:00 near 121 shards (about 1,800 cases). A cycle that adds cases has no
  recorded figure from which to place itself.
- **Evidence:** `reviewer/waves.out`, `reviewer/jobtimes.out` (from `gh run view <id> --json jobs`);
  `grep -n -i concurren AGENTS.md .github/workflows/mutants.yml tests/mutants.py` → the phrase only,
  no number.
- **Touches invariant / requirement:** R3 (second clause), R4's row.
- **Triage:** pending the maintainer. It cites R3's own wording, so *fix* (routed as CONFIRMED) or
  *drop*, never *defer*.

### [LOW/CONFIRMED] F-b — the budget row names one commit for three runs made at three
- **Where:** `AGENTS.md:1801` (`mutants budget` row, "commit `aff08bd`, runs 43255195424,
  43260825655, 43265827418")
- **Failure scenario:** R4 asks the row to record the commit and the runs counted. The runs' head
  commits are `aff08bd`, `32e1d5c` and `36bd540`. A reader checking the provenance finds two of three
  runs at a commit the row does not name. The measured code is identical across them
  (`git diff --stat aff08bd 36bd540 -- . ':(exclude)spec/' ':(exclude)issues/' ':(exclude)ROADMAP.md'
  ':(exclude)AGENTS.md'` is empty), so every figure stands; only the attribution is wrong.
- **Evidence:** `gh run view <id> --json headSha` for each run (`reviewer/run-*.json`; re-run by the
  orchestrator: `aff08bd`, `32e1d5c`, `36bd540`).
- **Touches invariant / requirement:** R4.

### Mutation grading (method/mutation-testing → When a review is done)

The diff touches no case, so no tier-2 case is touched. The reviewer's hand-planted sweep left 4 of
44 not killed; none breaks an R-ID's check or a reachable behaviour, so none is a finding:

- `parse-no-slash`, `ledger-failed-ok`: equivalent. Shard text without a slash leaves the count
  empty and raises the same error; one verdict word per case is guaranteed by the branch before.
- `ledger-empty-name` (drop `or not name`) and `ledger-control-else` (`elif word != 'control'` →
  `else`): **coverage observations**. Each removes a guard that never fires on reachable input (the
  runner never prints a verdict line with an empty name, or a control line whose text is outside
  `CONTROLS`); the mutant only adds ledger failures on those shapes. The reviewer called them
  equivalent on reachable input; the orchestrator grades them by the rubric's coverage line, a guard
  that never fires on reachable input, so they are seeded in the remediation round.

The 7 cases the hosted runner always reports not killed and the 1 flaky case predate this cycle and
are seeded under `issues/` (GOAL Q3); the reviewer checked each seed's `file:line` claims and quoted
verdicts against the code and the run logs, and found them accurate.

### Notes, not findings

- The branch is one commit behind `origin/develop` (`302bd10`), which also edits `ROADMAP.md`'s
  counts; publish reconciles them on the rebase.
- The flaky case's seed links an issue that exists only on `develop`; the seed says so.

## Human-gate triggers

- Not triggered by a path: neither finding touches a path on § Invariants' high-blast-radius list
  (`.github/workflows/` and the § Factory budget rows are not on it), and neither violates a
  section marked *[human gate]*.
- Both findings are in the `mutants budget` row, a timing bound: its content is the maintainer's to
  judge at the gate whatever the verdict.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run this cycle.
