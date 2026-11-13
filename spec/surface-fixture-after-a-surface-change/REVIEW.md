# REVIEW — The served-surface fixture follows a deliberate surface change

> Adversarial QA by `code-review`, run in an isolated context (a fresh blind subagent). The
> correctness pass graded the branch diff against [`GOAL.md`](GOAL.md) and the repo's `AGENTS.md`
> § Invariants only; it did not see `PLAN.md`, `TECH.md`, anything else under `spec/`, or this
> branch's commit bodies. Every finding cites an executed command. Evidence: the worktree's
> gitignored `.local/review1/` (the reviewer's hand-back is `REPORT.md` there).

- **Reviewed commit:** `4f00aa36395761526fbc790265a70082d50fe948`  ·  **Base:** `develop` (`origin/develop` `e378c33`)  ·  **Date:** 2026-11-09
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 (mirrors `review.cycle` in `TECH.md`)
- **Mode:** a full blind pass over the spec-excluded diff, by one reviewer. The sequential fallback did not run.

## Contract drift (Step 1.4)

`GOAL.md` moved after the shape commit `f4337cc` in two commits: `56868b8` (the GOAL-gate
clarifications M1, M2 and M4) and `ba9e95b` (the PLAN/TECH-gate refinement of M4: capabilities are
recorded per era). Both are the foreman's rulings, recorded at the gates. Graded against the GOAL at
HEAD. M3 is pending with the maintainer, so the status quo stands: no high-blast-radius line is
added, which is correct for this cycle.

## Verification run

- The profile's `verify` in full, both eras (`verify-full.log`): exit 0 in 26:57. Each era ran
  44 + 154 + 507 + 4480 passed, 14 skipped (the macOS bash-4.1 `need_shell` rows), and
  `bin/sandbox.sh uv run cluster-mcp --help` succeeded.
- `uv lock --check` (`lock.log`): passed.
- Non-goal "no surface change": `git diff --stat origin/develop...HEAD -- packages/` is empty, both
  from the orchestrator and from the reviewer, which also checked `uv.lock`, `pyproject.toml`,
  `.github/` and `bin/sandbox.sh`. `develop`'s own surface tests (the old harness, the old fixture
  and the `TOLERATED` comparison) pass against the current tree, 37/37 per era
  (`develop-surface-{legacy,modern}.log`).
- R1 (`r1.log`): two runs of `bin/sandbox.sh uv run --locked --exact python "$PWD/bin/record_surface.py"`
  both exited 0 with sha256 `ac1401d5…`, and run1 = run2 = HEAD byte for byte. The command refuses
  outside the sandbox and under `PYTEST_CURRENT_TEST` (exit 2). Nothing in `.github/`, `tests/`, the
  `verify` cell or the release `gate:` list runs it (`r1-nothing-runs.log`). `.venv` was unchanged
  (`venv-before.txt` = `venv-final.txt`).
- R4 drives (`drive/drives.log`): planted era differences in the instructions, a tool description
  and `serverInfo` are each refused with exit 1, naming the field. A difference in the capabilities
  only is written as `capabilities.modern.planted: added`.
- R5 drive (`drive/r5-drive.log`): a real reworded `run_command` docstring fails the baseline in
  both eras. The command then prints `- tools.run_command.description: changed` and rewrites the
  fixture, after which `tests/test_surface.py` passes 148/148 in both eras. The change was reverted
  and porcelain was empty afterward.
- R6 behaviour (`r6_check.log`, `argdesc_check.log`): `develop`'s `surface_violations` compares the
  `0bfacae` fixture with the new fixture, projected onto the old recorder's fields, and finds
  nothing (`[]`). Each of the 72 argument descriptions equals its `Args:` line.
- The `tests/mutants.py` surface cases in both eras (`mutants-runner-*.log`): all 11 killed.
- Mutant sweep (`mutate.py`, `mutants.tsv`, `mutants/`): 68 mutants in-place, each reverted with
  porcelain asserted empty, mostly in both eras. 118 runs killed, 13 survived (table below).
- Spec-id grep over the changed `.py` files, the fixture and the added AGENTS/ROADMAP/issues lines
  (`spec-id-grep.log`): no match.
- R6 commit record, run by the orchestrator: `spec/surface-fixture-after-a-surface-change/verify/rebaseline_check.py`
  was re-run on a separate clone at `4f00aa3` and exited 0. All 15 lines of its report appear
  verbatim in the body of the re-baseline commit `2aae583`.
- CI on this branch was **not observed**. Publish reads the rollup.

## Requirement → evidence matrix

| R-ID | Implemented by | Verified how | Verified by | Status |
|------|----------------|--------------|-------------|--------|
| Non-goal: no surface change | — | `packages/` diff empty; `develop`'s surface tests pass on this tree, both eras; the fixture reproduces | reviewer + orchestrator (`packages/` diff) | ✅ |
| R1 | `bin/record_surface.py`, AGENTS.md § Commands | two sandboxed runs byte-identical and equal to HEAD; no-run scan | reviewer | ✅ |
| R2 | `tests/harness.py` (`served_surface`, `surface_record`), the fixture | fixture keys inspected; recorder mutants killed; the per-set check over the 5 `SETS` | reviewer | ⚠️ F2 (a survivor on the `era` argument) |
| R3 | `tests/test_surface.py` (the comparison, the two carve-outs) | comparison and carve-out mutants killed; messages name the entry and path | reviewer | ⚠️ F4 (index/depth bound survivors) |
| R4 | `bin/record_surface.py` era check, `tests/harness.py` | baseline green in both eras; planted era differences refused | reviewer | ⚠️ F2 (the refusal can't fire if the recorder ignores `era`) |
| R5 (the command writes the passing fixture and prints the delta) | `bin/record_surface.py`, `delta_lines` | real docstring change driven end to end | reviewer | ⚠️ F3 (the command's delta glue has no control) |
| R5 (delta list in the commit body; reaches `develop` only as a reviewed change) | commit `2aae583` body; §9 text | the body carries the full delta list against `0bfacae`; §9 states the landing rule. M3 (b): ordinary review | orchestrator | ✅ |
| R6 (behaviour) | the re-baselined fixture | `r6_check.py` with `develop`'s comparison: `[]`; 72 `Args:` lines match | reviewer | ✅ |
| R6 (the check's output and the entering fields are recorded in the commit) | commit `2aae583` body | `rebaseline_check.py` re-run on a clean clone; all 15 output lines found verbatim in the body, including the 6 entering-field lines | orchestrator | ✅ |
| R7 | `tests/test_surface.py` drift/recorder/set controls; `tests/mutants.py` | each kind planted as addition and as removal/change; shape test retired; 11 surface mutant cases killed in both eras; set drift carries the additive controls | reviewer | ⚠️ F4 |
| R8 | AGENTS.md §9, § Testing, § Commands, repo map | retired text gone (`r8-docs.log`); method described; command listed | reviewer | ⚠️ F1 (the command's flags are undocumented) |

Unmapped changes (possible scope creep): none of substance. Small extras that each tie to an R-ID:
`fence()` in the command, `test_recorder_refuses_a_name_served_twice`,
`test_surface_fixture_is_the_commands_form`, the no-run scan tests, the repo-map row, and the
`mutants.py` anchors.

## Findings

0 CRITICAL · 0 HIGH · 1 MEDIUM · 3 LOW, all CONFIRMED. 0 PLAUSIBLE.

### F1 [MEDIUM/CONFIRMED] The command's flags are missing from the operating manual
- **Where:** `bin/record_surface.py:137-138` (`--out FILE`, `--against FILE`); `AGENTS.md` § Commands
  (`:123`), § Testing (`:1014`), §9 (`:3079`).
- **Failure scenario:** a re-baseline, or a change that must be listed against a base other than HEAD,
  needs `--against`. The manual gives only the bare command, so the next surface changer cannot find
  out from `AGENTS.md` how to produce the delta list §9 requires. The flags are documented only in the
  module's docstring (`:9`, `:21-23`).
- **Evidence:** `git grep -nE -- '--against|--out\b' -- AGENTS.md` returns no match (run by the
  orchestrator and the reviewer). `r8-docs.log` also counts 0 mentions of the new harness verb
  `surface_record` in AGENTS.md. That is weak on its own, because § Testing's verb list was already
  not exhaustive.
- **Touches:** R8, and the rubric's operating-manual drift class: a new flag of a new command that
  AGENTS.md doesn't describe. This is an absence, not stale text in a gate, so MEDIUM.
- **Route (the property):** every flag, verb and artifact this cycle introduced that a later cycle
  needs (the command's options, the harness's recording verb) is in the manual where the method is
  described. Grep AGENTS.md for each new symbol, not only for these two.

### F2 [LOW/CONFIRMED, surviving mutant] Nothing pins that the recorder records the era it is asked for
- **Where:** `tests/harness.py:517` (`era = _era(era)` in `_surface`); its only caller with an
  explicit era is `bin/record_surface.py:112`.
- **Failure scenario:** mutant `era = _era(None)` survives all 1,597 tests of test_surface,
  test_capabilities, test_protocol, test_literal_args, test_probe_startup and test_storage_resource
  in both eras. Under it, the command records the handshake era twice. Its era check then compares
  that era with itself, so R4's refusal can never fire. The command exits 0 and writes a fixture
  whose `capabilities.modern` is the legacy object (4 `capabilities.modern.*` delta lines).
  Downstream mitigation: the modern-era suite then fails the baseline.
- **Evidence:** `mutants.tsv` row `rec-ignore-era-argument` (SURVIVED in both eras);
  `drive/drives.log` mode `harness-ignore-era`; `drive/ignore-era-fixture.log`.
- **Touches:** R4 (the refusal clause), R2 (capabilities per era, M4 refined).
- **Route (the property):** what the recorder serves under an era argument is that era's surface, for
  every era the fixture holds, and the command's era refusal is reachable from the suite's view of
  the recorder. Example: a suite row records `era=OTHER` and compares it with
  `fixture['capabilities'][OTHER]`. As a surviving-mutant finding, it routes to a mutant sweep over
  every decision in the recorder (`served_surface`, `_surface`, `surface_record`, the raw listing and
  identity steps), each mutant run in both eras, with equivalents recorded and why.

### F3 [LOW/CONFIRMED, surviving mutant] The command's delta-list glue has no control
- **Where:** `bin/record_surface.py:150` (`lines = surface.delta_lines(base, fixture)`) and
  `read_base` (`:69`).
- **Failure scenario:** mutant `delta_lines(fixture, fixture)` survives the suite. Driven with a real
  reworded `run_command` summary, the shipped command prints `- tools.run_command.description: changed`
  and the mutant prints `- no difference`, both exiting 0. A deliberate change would then land with an
  empty delta list in its commit body, breaking R5's "print every changed entry and field path".
  `read_base` (`git show HEAD:`) is likewise uncovered.
- **Evidence:** `mutants.tsv` row `cmd-delta-against-itself` (SURVIVED); `drive/r5-drive.log`.
- **R1 tension, which the route must respect:** R1 bars any test from running the command, and the
  no-run scan bars importing it. The fix cannot be a test that runs `bin/record_surface.py`.
- **Route (the property, both ways):** every decision the command makes about what it writes,
  refuses or prints is covered by the suite, *and* no test, gate step or CI job runs the command or
  writes the fixture. The structural move that serves both is to decide each thing once in `tests/`:
  the base it diffs against, the delta, the era check and the self-check, with the command a thin
  wrapper that only calls them and does I/O. Then sweep every decision left in the command. The
  command-side survivors listed under coverage observations (`cmd-era-check-against-itself`,
  `cmd-skip-self-check`, `cmd-no-pytest-guard`) fall in the same sweep.

### F4 [LOW/CONFIRMED, surviving mutant] The comparison's list and depth walk is controlled only near the start
- **Where:** `tests/test_surface.py:121` (`for index in range(max(len(old), len(new)))`) and the
  recursion in `_differences`.
- **Failure scenario:** mutant `range(min(2, max(...)))` survives in both eras. Six fixture lists are
  longer than 2 (the longest has 8). Swapping `run_command.outputSchema.required[2]` and `[3]`, or
  dropping its last item, fails under the shipped code and passes under the mutant. The same class
  holds for depth: mutant `cmp-depth-10` survives, and the reviewer recorded it as equivalent
  "today". But `survivor_probe.log` shows it misses a change inside structure deeper than the fixture
  now has, which R3 ("at any depth") covers on reachable input once a tool serves a deeper schema. The
  orchestrator folds it into this finding's class rather than accepting it as equivalent.
- **Evidence:** `mutants.tsv` rows `cmp-list-first-two` and `cmp-depth-10` (SURVIVED, both eras);
  `survivor_probe.log`.
- **Touches:** R3 (any depth, any entry), R7 (a schema key at depth).
- **Route (the property):** the comparison sees every list index and every depth, not just the extent
  the controls happen to plant at. The controls plant at the last index of a long list, at a middle
  index, and below the fixture's deepest level. Sweep the comparison's bounds (index, depth, key
  set) in both eras.

### Coverage observations (not findings)
- `set-discard-one-sets-report` survives. It mutates the test's own assertion, and the plausible
  fault (a set missing from the loop) is killed.
- `cmd-era-check-against-itself` and `cmd-skip-self-check` each survive alone but are behaviourally
  equivalent alone: each still refuses through the other (`drive/drives.log`). Only the double mutant
  writes.
- `cmd-no-pytest-guard`: defence in depth. The scan test bars any test from running the command, and
  a manual drive refuses with exit 2.

These are routed with F3's command sweep rather than seeded separately. If that sweep doesn't close
them, the next review seeds them.

## Human-gate triggers

The diff touches § Invariants §9 (`[human gate]`). **Not triggered under the rubric's test:**
- No CONFIRMED finding is in a file on § Invariants' high-blast-radius list. The finding files are
  `AGENTS.md`, `bin/record_surface.py`, `tests/harness.py` and `tests/test_surface.py`.
- No finding is a violation of §9 by the shipped tree. The reviewer drove the shipped command and
  suite and they do what §9 now states. F2–F4 are coverage gaps, and F1 is a missing flag in text
  that is otherwise true.

Borderline, for the foreman: F1's missing flags sit partly in §9's own bullet, and F2 guards the
refusal that §9 states. If the foreman reads "lands in a `[human gate]` section" to include those,
the maintainer's sign-off is needed before publish.

## Optional completeness sub-pass

Not run (no `completeness` argument).

## Review cycle 2 — changes-requested (2026-11-10)

- **Reviewed commit:** `b79df4af8a20c0ae9c89a3070261b24db4e5c5b8`  ·  **Base:** `develop` (`origin/develop` `146cbc6`, the merge base)  ·  **Date:** 2026-11-10
- **Verdict:** changes-requested
- **Cycle:** 2 of ≤3 (mirrors `review.cycle` in `TECH.md`)
- **Mode:** a fresh blind pass over the full spec-excluded diff, by one reviewer at effort xhigh,
  which also checked whether cycle 1's F1–F4 are closed as properties. The sequential fallback did
  not run. The reviewer worked in a scratch clone for its mutants and left the worktree clean.
- **Head commits since cycle 1:** `dea578b` (the maintainer's M3 answer, a GOAL clarification),
  `ba1950d` (F1–F4), `b79df4a` (the full gate, `TECH.md` only).

### Contract drift (Step 1.4)

After the shape commit `c2cf80c`, `GOAL.md` moved in three commits: `5048ee3` (the GOAL-gate
clarifications), `fc7de26` (the PLAN/TECH-gate refinement of M4) and `dea578b` (the maintainer's M3
answer: the fixture joins the high-blast-radius list). These are the foreman's dated rulings and the
maintainer's recorded answer. This review grades against the GOAL at HEAD.

### Grading rule for this cycle

The foreman corrected the brief during the step. `method/mutation-testing.md` § When a review is
done governs how survivors are classified:
- A survivor is a finding only when it breaks an R-ID's stated check or a reachable behaviour in a
  class nothing pins yet, or when it is a silent pass or a false refusal on reachable input.
- A hand-made mutant that pins a deeper layer of a class that is already pinned is a coverage
  observation, and it is seeded.
- A self-referential oracle is still a finding in itself.

The reviewer was briefed with this rule before it started. Domain search was used to find classes.

### Verification run (orchestrator, before the reviewer launched)

- **The cycle's phase gates in light modes,** run in sequence to completion:
  `spec/surface-fixture-after-a-surface-change/verify/gate.sh p1|p2|p3|p4`. This cycle has no
  `remediation/` wrappers. Logs are in `.local/review2/orch/`.
  - All four exited 0: p1 in 284 s, p2 in 12 s, p3 in 26 s, p4 in 265 s.
  - p1's whole-module runs: 2799 passed per era.
  - p4's sweep: 59 mutants, 57 killed, 0 survived, 2 equivalent. No sweep child was left.
  - `full` was not re-run. It ran on `ba1950d`, and `b79df4a` changes only `TECH.md`. CI on the
    pushed `-r2` branch is reported green by the foreman. This step did not observe CI itself.
- **The same tree after the gates:**
  - `git status --porcelain` was empty.
  - The fixture's sha256 equals HEAD's (`ac1401d5…`).
  - `.venv` was unchanged: the freeze diff was empty, and so was the content hash with
    `__pycache__` excluded (`venv-*-before.txt`).
- **A listed-mutant gate cannot grade an open-ended class.** p4's sweep reported every listed mutant
  killed. The reviewer's sweep over the domain still found 7 survivors in a class the list never
  named (N2) and 2 in the command's glue (N1). A green sweep is evidence only for the mutants it
  lists. Where an R-ID says "any" or "every", the open domain is graded by search, not by the gate.

### Orchestrator sanity check

- **The tree after the reviewer:**
  - `git status --porcelain` was empty.
  - The fixture's sha256 was `ac1401d5…`, equal to HEAD's.
  - The reviewer's `.venv` freeze diff was empty. No ignored build state was mutated.
- **N1:** re-read at `bin/record_surface.py:106-113`. The command branches on `args.against` and
  passes `command_base` one argument or the other, never both. AGENTS.md's § Testing entry says the
  command "makes no decision of its own". The drive log shows C1 exiting 0 with `- no difference`,
  where the control prints 170 lines. Kept as CONFIRMED LOW. This is cycle 1's F3 property ("the
  base it diffs against", decided once in `tests/`) at the same layer, not a deeper one, and the
  suite pins nothing at that layer: the spec-held command drive kills the analogous sweep rows, but
  it is not part of the suite. Read strictly, the false manual sentence is MEDIUM drift on its own.
  It is kept inside N1 because N1's route makes the sentence true.
- **N2:** the `mutants.tsv` rows and `probe_tolerated.log` were read. Each mutant restoring a former
  `TOLERATED` kind survives with 174 passed in both eras, and the probe shows a real difference
  returning `[]` under the mutant. Kept as CONFIRMED LOW, by rule (a): the five kinds are named by the
  GOAL, and nothing pins that any one of them is refused. p1's `absent 'TOLERATED'` step checks only
  the name.
- **Out of scope** (the reviewer's C7): a relative `--out FILE` resolves inside the sandbox
  directory, which is then deleted, while the command says "wrote". No R-ID names `--out`, and the
  sandbox's documented contract is to contain relative writes. This is hardening, not a defect of
  this cycle: seed it.
- **Self-referential oracle:** none found.
- **R5, the commit-body part** (orchestrator): the fixture changed only in `55d5c4a`. Every one of
  the 170 delta lines that the reviewer's control drive printed against the `0bfacae` fixture
  appears verbatim in that commit's body (`orch/r5-body-check.txt`: missing 0). Under M3 (a), the
  fixture is on the high-blast-radius list, so the change takes the human gate.
- **R6, the commit-record part** (orchestrator): p4 re-ran
  `verify/rebaseline_check.py` on HEAD's fixture. Every line of its report appears verbatim in the
  body of `55d5c4a`, including the six lines for fields entering as served.

### Requirement → evidence matrix

| R-ID | Verified how | Verified by | Status |
|------|--------------|-------------|--------|
| Non-goal: no surface change | the `packages/`, `uv.lock` and `pyproject.toml` diff is empty; every gate's `files` step | reviewer + orchestrator | ✅ |
| R1 | two sandboxed runs are byte-identical and equal HEAD; refusals exit 2 and write nothing; the no-run scan | reviewer (orchestrator: the p1/p4 command drive) | ✅ |
| R2 | baseline green in both eras; recorder and version carve-out mutants killed; 5 `SETS` | reviewer | ✅ (coverage observation: `execution` not planted) |
| R3 | 76/103 mutants killed per era; carve-out widenings killed | reviewer | ⚠️ N2 |
| R4 | era-check mutants killed; both eras pass | reviewer | ✅ |
| R5 (behaviour) | the `--against 0bfacae` drive prints 170 path lines; `cmd-delta-*` killed | reviewer | ⚠️ N1 |
| R5 (commit body, reviewed landing) | all 170 delta lines are in `55d5c4a`'s body; §9 states the landing rule; the fixture is on the high-blast-radius list | orchestrator | ✅ |
| R6 (behaviour) | an independent `r6_check.py` and a second oracle from the base cycle: only the five kinds | reviewer | ✅ |
| R6 (check output recorded in the commit) | the `rebaseline_check.py` report is verbatim in `55d5c4a`'s body | orchestrator | ✅ |
| R7 | 11 `tests/mutants.py` surface cases killed in both eras; anchors pass; shape test retired | reviewer | ⚠️ N2 |
| R8 | retired text gone; flags and verbs documented | reviewer | ✅ (AGENTS.md:1018 overstates, folded into N1) |
| Spec-id leakage | grep of the added lines: 0 matches | reviewer | ✅ |

### Findings

0 CRITICAL · 0 HIGH · 0 MEDIUM · 2 LOW, both CONFIRMED. 0 PLAUSIBLE.

#### N1 [LOW/CONFIRMED] The command still chooses the base itself (F3 not closed as a property)
- **Where:** `bin/record_surface.py:106-113` and `:71` (`head_text`). The false sentence is AGENTS.md
  § Testing `:1018`; the docstring at `bin/record_surface.py:31` says the same.
- **Failure scenario:** suppose the command's `if` breaks. `--against FILE` is then ignored. The
  command exits 0, prints `- no difference`, and still claims the delta was taken against FILE. No
  test can see this, because R1 bars the suite from running the command.
- **Evidence:** the reviewer's `cmd-drive.log` (C1, C2) and `cmd/`.
- **Route (the property, both ways):** no branch left in `bin/record_surface.py` changes what the
  command writes, refuses or prints. Every such choice is made once, in a function in `tests/`:
  the base, from the raw `--against` text or None and the raw HEAD text or None. The command only
  reads the inputs and does the I/O. No test, gate step or CI job runs the command.
  - Then sweep every branch left in the command.
  - The manual sentence is made true in the same change.
  - The duplicated `record()` seam (coverage observation C3) is in the same class: decide it once.

#### N2 [LOW/CONFIRMED] Nothing pins that the tolerated-difference list is gone
- **Where:** `tests/test_surface.py:118-136` (`_differences`). The controls are `DRIFT` (`:485`) and
  `SET_DRIFT` (`:1184`).
- **Failure scenario:** suppose a condition is added back to the walk that tolerates any one of the
  five former kinds: an argument description gained or drifted, `additionalProperties`, a derived
  title gained or lost, the output-model description, or `$defs`/`$ref`. Every gate stays green, and
  the baseline then passes a real difference. The GOAL's own example, an argument description that
  drifted from its `Args:` line, is one of them.
- **Evidence:** the reviewer's `mutants.tsv` (7 rows, 174 passed in both eras) and
  `probe_tolerated.log`.
- **Route (the property):** the comparison reports a difference for every key the fixture holds,
  gained, lost or changed, at every occurrence kind. That includes the five former kinds by name.
  - The controls are generated from the fixture's own key set, not hand-picked rows.
  - Sweep the comparison with additive mutants (a key exempted, a difference tolerated, an era
    skipped) in both eras.
  - The key-sweep survivors listed below are this route's domain.

#### Coverage observations (seeded)

These are not findings. Each has to be seeded: an `issues/` seed and its `ROADMAP.md` entry. The
seeds were not written in this step, because the brief limits this step's commit to `REVIEW.md` and
`TECH.md`. They go to the foreman. Several will be absorbed by N1's or N2's route.
- `cmp-index-min5`, `cmp-index-min8`: the longest list (8 items) is planted at index 4 only. A
  deeper layer of F4.
- `cmp-depth-22`: the depth bound sits just past the planted depth of 22. A deeper layer of F4.
- `cmp-skip-default`, `-enum`, `-anyOf`, and 49 key-sweep survivors (`mutants-keys.tsv`): N2's domain.
- `rec-drop-execution`: the recorder rows don't plant `execution`, which R2 names. The class is
  otherwise pinned (`rec-declared-keys-only` and `rec-drop-icons` are killed).
- `ver-source-accept-several`: defence in depth. It is reachable only if two distributions' versions
  are equal.
- `rec-no-cursor-guard`: a repeated cursor hangs until a 30 s timeout. Loud, not a silent pass.
- `set-loop-one-server`: test glue, the same class as cycle 1's `set-discard-one-sets-report`.
- `set-cut-only-tools-resources`: equivalent while templates and prompts are empty. Later it would
  cause a false failure, not a silent pass.
- `scan-tests-test-star-only`, `scan-ci-only`: the no-run scan's file domain is not pinned.
- C3, the command's `record()` without `era=`: caught downstream by the suite in both eras, and the
  command prints a 4-line delta. Not silent. Goes with N1's route.
- C5, the command's `raise refusal` removed: glue around the killed `command_refusal`. Goes with N1's
  route.
- Out of scope, to seed: a relative `--out FILE` is deleted with the sandbox while the command
  reports "wrote" (C7).

### Cycle-1 findings

| Finding | Status | Evidence (reviewer) |
|---|---|---|
| F1 (flags undocumented) | closed | `--out` and `--against` are in § Commands and §9; `surface_record` and `SURFACE_LISTINGS` are in § Testing; the repo map counts six paths (`agents-grep.log`) |
| F2 (era argument unpinned) | closed as a property | five recorder-era mutants killed in both eras; the real command under the modern selection writes the committed bytes |
| F3 (command delta glue) | **not closed as a property** | the delta glue is pinned, but the base choice stays in the command → N1 |
| F4 (index/depth bounds) | closed for the cited mutants | `min2`, `min4`, `shorter`, `skip-last`, `depth-10` and `depth-20` killed; deeper layers seeded |
| Cycle-1 coverage observations | two of three closed | era-check pair and pytest guard each killed on their own; the set-loop class is still open (`set-loop-one-server`) |

### Human-gate triggers

- **Standing trigger:** this cycle changes `tests/fixtures/served_surface.json` (the re-baseline in
  `55d5c4a`). That file is on § Invariants' high-blast-radius list (M3 (a)), so the maintainer must
  sign off before publish, whatever the verdict. It has not been recorded here yet.
- **Nothing else trips the gate.** Neither CONFIRMED finding is in a file on the list: N1 is in
  `bin/record_surface.py` and AGENTS.md § Testing, N2 is in `tests/test_surface.py`. Neither is a
  violation of a `[human gate]` section by the shipped tree. §9's text (AGENTS.md:3093-3112) is true
  as shipped; N1's false sentence is in § Testing, and N2 is a missing control, not a tolerated
  difference in the shipped comparison.

### Reviewer's hand-back (verbatim)

Copied as the reviewer handed it back. Two edits only: the heading levels are shifted to nest under
this section, and the evidence directory is written relative to the worktree. The harness refused
the planned copy at `.local/review2/REPORT.md`, so this is the record. The reviewer's evidence is in
the worktree's gitignored `.local/review2/reviewer/`.

#### Cycle-2 blind review: surface-fixture-after-a-surface-change (HEAD b79df4a)

Evidence dir: the worktree's `.local/review2/reviewer/`. Mutants ran in a scratch clone at `reviewer/tree/`, never in `$WT`. I did not read anything under `spec/`, any commit body or `review1/REPORT.md`.

**Summary:** two LOW, CONFIRMED findings. Neither one touches a high-blast-radius path. R1, R2, R4, R6, R7, R8 and the no-surface-change non-goal pass, each confirmed by an executed command.

##### 1. Findings (most severe first)

**N1 [LOW / CONFIRMED]: F3 is closed for the delta, not as a property. The command still chooses the base itself.**
- **Where:**
  - `bin/record_surface.py:106-113`: `if args.against is not None: … command_base(against, None) else: command_base(None, head_text(…))`.
  - `bin/record_surface.py:71`: `head_text` returns None ("HEAD has no fixture") on an empty `ls-tree`.
  - The suite pins the priority inside `command_base` (`tests/test_surface.py:325`; `test_command_base_is_against_then_head_then_nothing`, :1442). The command never passes both arguments, so that tested priority is never what runs.
  - The manual and the module docstring say the opposite: AGENTS.md:1018 ("The command makes no decision of its own: … the base its delta is listed against (`--against FILE`, else the fixture at `HEAD`, else nothing) … are decided by those functions") and `bin/record_surface.py:31`.
- **Failure scenario:** someone breaks the command's `if`. `--against FILE` (the documented way to list a re-baseline's delta against 0bfacae) is then silently ignored. The command exits 0, prints `- no difference`, and its summary still claims the delta was taken against FILE.
- **Evidence:** `zsh reviewer/drive_cmd_mutants.zsh`, driven through `bin/sandbox.sh` (`cmd-drive.log`, `cmd/`).
  - Unmutated control `c0-against`: 170 delta lines against the 0bfacae fixture.
  - Mutant C1 (`if args.against is not None:` → `if False:`): exit 0, 1 line `- no difference`, and stderr reads `0 changed paths against …/base-0bfacae.json`.
  - Mutant C2 (`head_text`'s None branch forced): exit 0, a delta claiming all 7 top-level keys were added.
  - The suite cannot see either mutant. R1 forbids it from running the command, and no test imports the command (`test_nothing_runs_the_surface_command`).
- **R-ID:** R5 ("print every changed entry and field path"); cycle-1 F3's route.
- **Route (as a property):** every choice about which base the delta is listed against happens inside a function in `tests/`. The command hands it both raw inputs: the `--against` text or None, and the HEAD text or None after the `ls-tree`. The command keeps only reading those inputs. After that, no branch in `bin/record_surface.py` changes what is written, refused or printed. The manual sentence becomes true with the same change.

**N2 [LOW / CONFIRMED]: Nothing pins that the tolerated-difference list is gone. Putting back any of the five former `TOLERATED` kinds survives both eras.**
- **Where:** `tests/test_surface.py:118-136` (`_differences`); the controls are `DRIFT` (:485) and `SET_DRIFT` (:1184).
- **Failure scenario:** a later edit adds a condition to the walk that tolerates one of the old kinds. Every gate stays green, and a real difference then passes `test_served_surface_matches_baseline` silently. The probe shows it on concrete inputs: the real code reports each one, the mutated code returns `[]`.
  - A `cwd` argument description drifting from its `Args:` line. This is the GOAL's own example.
  - An argument description gained.
  - `run_command` losing its title, as a lock bump that stops deriving titles would do.
- **Evidence:** `python mutate.py mutants_cycle2.py mutants.tsv` (`mutate-run.log`); `probe_tolerated.py` (`probe_tolerated.log`). Each of these mutants survives with 174 passed in legacy and in modern:

  | Mutant | Former kind it re-introduces |
  |---|---|
  | `cmp-tol-arg-description-added` | argument-description |
  | `cmp-tol-arg-description-any` | argument-description (the drift case) |
  | `cmp-tol-additional-properties-added` | additional-properties |
  | `cmp-tol-tool-title-added` | derived-title (gained) |
  | `cmp-tol-tool-title-removed` | derived-title (lost) |
  | `cmp-tol-output-description-added` | output-model-description |
  | `cmp-skip-dollar-keys` | output-defs-inlined (`$defs`/`$ref`) |

- **R-ID:** R3 ("The comparison SHALL carry no tolerated-difference list"); R7 (a control per R3 kind).
- **Classification:** none of these kinds is pinned by anything, so this follows rule (a), not the "deeper layer" rule.
- **Route (as a property):** every distinct structural key name the fixture holds (118 names; the sweep covers the 32 structural ones), plus the five former kinds by name, gets a control generated from the fixture. Each control plants that key gained, lost and changed at one of its occurrences and requires a violation at that path. Hand-picked rows don't do this.
- **Same domain, still surviving:** single-key exemptions of `default`, `enum`, `anyOf`, `src`, `subscribe`, `extensions`, `x-fastmcp-wrap-result`, plus 42 gained-only or lost-only variants (`mutants-keys.tsv`: 47 killed, 49 survived). The probe shows a `default` change and an `enum` addition passing under those mutants.

**No self-referential oracle.** Expected values are literals or the committed, reviewed fixture.
- `test_recorder_serves_each_eras_own_surface` compares against the fixture as a golden file, anchored by its own assertion that the two eras' capabilities differ.
- The second assertion of `test_recorder_sees_what_the_server_starts_serving` is true by construction where the recorder is concerned. It does pin `surface_differences`: it killed `cmp-tol-any-description-added`.

##### 2. Coverage observations (seeded)
- `cmp-index-min5` and `cmp-index-min8` survive. The longest fixture list (`list_directory` `items.required`, 8 items) is planted only at index 4, so changes at indices 5 to 7 would go unseen under such a bound. This is a deeper layer of F4.
- `cmp-depth-22` survives: the depth bound sits just past the planted depth of 22; the fixture's deepest level is 9. Deeper layer of F4.
- `cmp-skip-default`, `-enum`, `-anyOf` and the 49 key-sweep survivors: the domain of N2's route.
- `rec-drop-execution` survives. The recorder rows plant `icons`, `_meta`, annotations and titles, but not `execution`, which R2 names. The recorder-keeps-every-key class is otherwise pinned (`rec-declared-keys-only` and `rec-drop-icons` are killed).
- `ver-source-accept-several` survives. Defence in depth: it needs cluster-mcp's version to equal fastmcp-slim's.
- `rec-no-cursor-guard` survives. A repeated cursor hangs until drive()'s 30 s timeout; it is not a silent pass.
- `set-loop-one-server` survives: test glue, the same class as cycle 1's `set-discard-one-sets-report`.
- `set-cut-only-tools-resources` survives. It is equivalent while the fixture's templates and prompts are empty, and later it would cause a false failure, not a silent pass.
- `scan-tests-test-star-only` and `scan-ci-only` survive. The scan's file domain is not pinned: conftest/harness/mutants.py, or mutants.yml, could drop out of the scan unnoticed.
- The command's `record()` (`bin/record_surface.py:93`) duplicates the suite's `_recorder`. Mutant C3 drops `era=era`: the command exits 0 and writes `capabilities.modern` equal to `legacy`. The suite then catches that fixture in both eras (`c3-downstream.log`), and the command also prints a 4-line delta. Not silent.
- Mutant C5 (the command's `raise refusal` removed) writes when the sandbox marker is unset. This is glue around the killed `command_refusal`.
- Removing the fence (C4) fails loudly through the harness's fence check; dropping the site (C6) fails with a TypeError.
- Out of scope, by the sandbox's own contract: a relative `--out FILE` lands in the sandbox dir and is deleted, while the command reports "wrote" (`cmd-drive.log` C7).
- Documented in AGENTS.md § Testing: with `MCP_BASE_URL` exported, the baseline fails at `serverInfo.icons[0].src`. `server.py` reads it at import, before conftest's `BLANKED_ENV` takes effect (`mcp-base-url.log`).

##### 3. Cycle-1 findings
- **F1: closed.** `--out` and `--against` appear in § Commands (AGENTS.md:124-126) and §9 (3107-3108). `surface_record` and `SURFACE_LISTINGS` are listed in § Testing's harness verbs. `bin/record_surface.py` is in the repo map ("Six repo-level paths"; the count is right). Every new or moved symbol was grepped (`agents-grep.log`). The unlisted ones are test-internal helpers.
- **F2: closed as a property.** `rec-surface-era-none`, `rec-inmemory-no-era`, `rec-identity-selected-era`, `rec-record-era-none` and `cmd-record-one-era` are all killed in both eras. Driving the real command with `CLUSTER_MCP_TEST_ERA=modern` writes the committed bytes (`drive/modern-sel.json`). The command-level analogue (C3) is caught downstream.
- **F3: closed for the delta, not as a property.** `cmd-delta-self`, `cmd-delta-vs-record`, the base-parsing mutants and the refusal mutants are killed. The base selection remains in the command: N1.
- **F4: closed for the cited mutants.** `cmp-index-min2`, `-min4`, `-shorter`, `-skip-last`, `cmp-depth-10` and `-20` are killed. The property holds only up to the planted extent; `min5`, `min8` and `depth-22` are listed as coverage observations.
- **Cycle-1 coverage observations:**
  - The set-loop class is still open (`set-loop-one-server` survives).
  - The era-check-against-itself and skip-self-check pair is now each killed on its own (`era-check-self`, `cmd-skip-era-check`, `cmd-skip-fixture-check`).
  - The pytest guard is now killed (`cmd-no-pytest-refusal`); only the command's raise remains (C5).

##### 4. Requirement → evidence matrix

| R-ID | Implemented by | Verified by | Status |
|---|---|---|---|
| R1 | `bin/record_surface.py`, `command_refusal` | `drive/run1.json` = `run2.json` = committed fixture (sha `ac1401d5…`), exit 0. Exits 2 and writes nothing outside the sandbox and with `PYTEST_CURRENT_TEST` set (`drive/*.stderr`). No test writes the fixture (grep). Scan kills its mutants. | Met |
| R2 | `harness.surface_record`, `_raw_listing`, `_raw_identity`; `expected_surface` | Baseline green in both eras (`base-*.log`). `probe_identity.log`: raw re-sent `initialize` equals the handshake `InitializeResult`. Recorder rows and version carve-out rows killed. Set check covers 5 SETS. | Met |
| R3 | `_differences` / `surface_violations`, carve-outs `VERSION_SOURCE` and `ERA_CAPABILITIES` | 76 of 103 mutants killed in both eras; carve-out widening mutants killed | Met; controls gap N2 |
| R4 | `era_violations`, `command_result` | `era-check-*` and `cmd-skip-era-check` killed; both eras pass | Met |
| R5 | `delta_lines`, `command_result` | Drive with `--against` 0bfacae: 170 path lines; `cmd-delta-*` killed | Met in behaviour; N1. Commit-body part is the orchestrator's. |
| R6 | the re-baselined fixture | Independent check `r6_check.py` (`r6_check.log`, exit 0): only additional-properties ×24, argument-description ×72 (each equals its docstring `Args:` line, whitespace-normalised), derived-title ×24, output-defs-inlined ×2. Base-cycle comparison as a second oracle: 0 violations (`r6_oracle2.log`). | Met (behaviour) |
| R7 | DRIFT, SET_DRIFT, RECORDER; shape test retired | The 11 surface cases in `tests/mutants.py --self-check` killed for the right reason in both eras (`r7-mutants-py.log`); anchors pass (`r7-anchors.log`) | Met; N2 |
| R8 | AGENTS.md § Commands, § Testing, §9; fixture added to the high-blast-radius list | Grep: no "hand-edit", "open question", `TOLERATED` or `snapshot.py` text left in AGENTS.md | Met; AGENTS.md:1018 overstates (N1) |
| Non-goal: no surface change | — | `git diff --stat` over `packages/`, `uv.lock` and every `pyproject.toml` is empty | Met |
| Spec ids | — | No spec ids in added lines (`spec-id-grep.log`, 0 matches) | Met |

##### 5. Scope creep
None. Every changed file maps to an R-ID or to the factory's bookkeeping (seed and ROADMAP status lines). The high-blast-radius list only widened.

##### 6. Mutant tables
- **Main sweep:** `reviewer/mutants.tsv` (103 mutants). Legacy: 76 killed, 27 survived. Modern: 77 killed, 26 survived (`base-fixed-era` is equivalent in legacy only).
- **Survivor classes:** 7 are N2; 13 are coverage observations; 7 are equivalent or equivalent on reachable input: `fix-from-modern`, `set-skip-version`, `cmd-problems-skip-unresolved`, `rec-legacy-identity-from-model`, `rec-no-json-roundtrip`, `base-no-problems-assert`, `base-fixed-era` (legacy only). Each reason is in `reviewer/survivors-classified.tsv`.
- **Key sweep:** `reviewer/mutants-keys.tsv`: 47 killed, 49 survived, the same in each era.
- **Command mutants:** `reviewer/cmd-drive.log`. The suite cannot kill any of them, by R1; they were classified by driving them.

##### 7. Clean-up
- `git status --porcelain` is empty.
- The fixture's sha256 is `ac1401d5de08ce997d5b48b1749160d37797cb201eaef1cf7c9b514c0648b398`, the same as `HEAD`'s.
- The `.venv` freeze diff is empty (`venv-before.txt` against `venv-after.txt`).
- No git-ignored build state was mutated.
- The scratch clone `reviewer/tree/` is clean and left in place. It holds `spec/`, which I did not read.
- `DONE` is written.

## Review cycle 3 — changes-requested (2026-11-12)

- **Reviewed commit:** `71fa1fc3c5e78051d5060853054c9eb98d0160e5`  ·  **Base:** `develop` (the merge base `146cbc6`; `origin/develop` has since moved to `ea1b2c4`, the 0.2.0 release)  ·  **Date:** 2026-11-12
- **Verdict:** changes-requested
- **Cycle:** 3 of ≤3 (mirrors `review.cycle` in `TECH.md`). The loop has not converged: escalated
  to the maintainer.
- **Mode:** a fresh blind pass over the full spec-excluded diff, by one reviewer at effort xhigh. It
  swept this round's change (`b79df4a..71fa1fc`) and checked that N1 and N2 are closed as
  properties. The sequential fallback did not run. Mutants ran in a scratch clone at
  `.local/review3/reviewer/tree/`, never in the worktree.
- **Head commits since cycle 2:** `71fa1fc` (N1, N2, two seeds). `GOAL.md` has not moved since
  cycle 2's drift record (`dea578b` is the last change).
- **Grading rule:** survivors classified by `method/mutation-testing.md` § When a review is done,
  cited to the reviewer, not restated.

### Blindness note

The reviewer disclosed that one early recursive `grep`, run without excluding `spec/`, printed
matching lines from this cycle's `spec/` files, `REVIEW.md` among them. It opened none of them, and
it states that no finding or status relies on them. Finding A rests on executed drives and a
control against `b79df4a`, which I re-read (below), so it stands on evidence, not on the leak. The
leak means this pass was not fully blind to cycles 1–2's wording.

### Verification run (orchestrator, before the reviewer launched)

- **The cycle's phase gates in light modes,** run in sequence: `verify/gate.sh p1|p2|p3|p4`.
  There are no `remediation/` wrappers. Logs are in `.local/review3/orch/`.
  - All four exited 0: p1 in 250 s, p2 in 26 s, p3 in 33 s, p4 in 370 s.
  - p1's whole-module runs: 2839 passed per era. p2's `tests/test_surface.py`: 214 passed per era.
    p3: 925 passed per era.
  - p4's sweep: 80 mutants, 78 killed, 0 survived, 2 equivalent. No sweep child was left.
  - `full` was **not observed** by this step. `TECH.md` records a green run on this round's tree
    (26:18, both eras), and CI on the `-r2` branch was running at launch. This step did not observe
    either.
- **The same tree after the gates:** `git status --porcelain` empty; the fixture's sha256 equals
  HEAD's (`ac1401d5…`); the `.venv` freeze and content-hash diffs are empty.
- Once again the listed-mutant sweep was green while the reviewer's domain search found a
  regression (Finding A) that no listed mutant names.

### Orchestrator sanity check

- **The tree after the reviewer:** `git status --porcelain` empty at `71fa1fc`; the fixture's sha256
  equals HEAD's; the reviewer's `.venv` freeze diff is identical; `DONE` written; nothing of its
  own left running (`reviewer/cleanup.log`).
- **Finding A:** re-read and kept as CONFIRMED MEDIUM.
  - `bin/record_surface.py:53-57` imports `test_surface` to reach `command_main`.
  - `tests/test_surface.py:1796-1797` reads the working-tree fixture at module level
    (`AGAINST_TEXT`, `HEAD_TEXT`), and the `test_command_refuses_writing_nothing` parametrize
    (`:1849-1868`) builds `_Stand(...)` at import, which records and asserts on the fixture.
  - The drives show exit 1 with nothing written on a conflicted, absent, or
    uninstalled-distribution fixture (`reviewer/conflict-head.stderr`, `absent-head.stderr`,
    `uninstalled-head.stderr`). The control at `b79df4a` re-takes the conflicted fixture, exit 0
    (`reviewer/conflict-b79.stderr`). It is a regression this round introduced.
  - Severity: a bug on an edge path (MEDIUM). It is reachable: the documented recovery from a
    fixture conflict is to re-run the command.
- **Out of scope** (the reviewer's note): a relative `--against FILE` is refused loudly (exit 2,
  "cannot read the base"), because the sandbox changes into its scratch directory. Not silent, and
  no R-ID names relative paths. It belongs with the existing seed
  `issues/record-surface-relative-out.md`, which covers `--out` only.
- **Coverage observations** CO1–CO6 below: each is a deeper layer of a class already pinned, and
  HEAD behaves correctly on each. They are not findings. Not seeded in this step: the verdict is
  not clean, so the deferral procedure does not run here. Several extend
  `issues/surface-pin-completeness.md`; the next build round or publish files them.
- **Self-referential oracle:** none harmful (reviewer § 3).
- **R5 and R6, the commit-record parts** (orchestrator): the fixture still changes only in
  `55d5c4a`, unchanged since `b79df4a`. Cycle 2's checks (`.local/review2/orch/r5-body-check.txt`,
  `r6-commit-check.txt`) stand unchanged.

### Requirement → evidence matrix

| R-ID | Verified how | Verified by | Status |
|------|--------------|-------------|--------|
| Non-goal: no surface change | no `packages/` change; command against HEAD prints `- no difference`; every gate's `files` step | reviewer + orchestrator | ✅ |
| R1 | two sandboxed runs byte-identical and equal HEAD; refusals exit 2; nothing runs the command; only `git` launched, before the fence | reviewer | ⚠️ A |
| R2 | recorder, keep-keys and per-set tests in both eras | reviewer | ✅ |
| R3 | real docstring and default/enum changes fail the baseline naming the paths | reviewer | ✅ (CO1, CO2) |
| R4 | both eras pass; a real drive with the eras differing is refused, exit 1, naming fields | reviewer | ✅ |
| R5 (behaviour) | a planted change: the command writes the fixture, prints 2 paths, the module passes 214/214 per era | reviewer | ⚠️ A |
| R5 (commit body, reviewed landing) | cycle 2's check stands (fixture unchanged since); the fixture is on the high-blast-radius list | orchestrator | ✅ |
| R6 (behaviour) | `r6_check.py` with the base's comparator plus an independent diff: only the five kinds | reviewer | ✅ |
| R6 (check output in the commit) | cycle 2's check stands | orchestrator | ✅ |
| R7 | 10 fixture-planting `tests/mutants.py` cases killed per era; generated controls; shape test retired | reviewer | ✅ (CO5) |
| R8 | no hand-edit, "open question", `TOLERATED` or `snapshot.py` text left | reviewer | ✅; § Testing's "else nothing" unreachable while A stands |
| Spec-id leakage | grep of added lines and of `bin/`, `tests/`: clean | reviewer | ✅ |

### Findings

0 CRITICAL · 0 HIGH · 1 MEDIUM · 0 LOW, CONFIRMED. 0 PLAUSIBLE.

#### A [MEDIUM/CONFIRMED] The command cannot run when the working-tree fixture is broken or missing
- **Where:** `bin/record_surface.py:53-57,88`; `tests/test_surface.py:1796-1797` and the
  parametrize at `:1849-1868` (through `_records()`, `:1633`, and `_eras_differ()`).
- **Failure scenario:** the command imports `test_surface`, which now reads and validates the very
  fixture the command is about to overwrite.
  - A fixture with merge-conflict markers: exit 1, `JSONDecodeError`, nothing written. Likely when
    0.3.0's surface-changing cycles land one after another, where re-running the command is the
    documented fix.
  - A deleted fixture: `FileNotFoundError`. The tested "HEAD has no fixture, empty base" path is
    unreachable when the working tree lacks the file too.
  - A lock bump that drops the version's source distribution: `AssertionError`.
- **Evidence:** `reviewer/conflict-head.*`, `absent-head.*`, `uninstalled-head.*`; the control
  `reviewer/conflict-b79.*` (exit 0, bytes equal HEAD's); `reviewer/import_reads.py` (import-time
  reads: none at `b79df4a`, these at HEAD).
- **Touches:** R5 ("re-running the command SHALL write the fixture that passes"), R1, and N1's
  route ("the command only reads the inputs").
- **Route (the property, both ways):** importing the module that holds the command's choices reads
  no file. What the command does depends only on its arguments, the base (`--against` or HEAD) and
  the served server, never on the working-tree fixture. Keep every current stand-in row while doing
  so: values derived from the fixture move inside the tests that use them, lazily. Pin it with a
  control the suite can run without running the command (a module-level-read check with a
  planted-read control), and sweep the module's import-time statements.

### Coverage observations (to seed; not findings)

- **CO1:** entry-name exemptions survive (`cmp-skip-entry-squeue`, `-rcac-context`,
  `-sbatch-input`). The generated controls plant each key shape at its first occurrence only.
- **CO2:** value-kind and change-form tolerances survive (`cmp-tol-same-type-default`,
  `-bool-default`, `-str-default`, `-enum-items`, `-leaf-whitespace`, `-leaf-case`). HEAD's
  comparator reports both real cases (`reviewer/real-default-enum-*.log`). The comment at
  `tests/test_surface.py:707-712` claims more than the generator plants.
- **CO3:** the command file's wiring is pinned by nothing (`file-environ-forged`, `-out-to-err`,
  `-record-one-era`, `-no-fence`, `-argv-dropped`, `-git-cwd`). `argv-dropped` would be silent: a
  dry run with `--out` would overwrite the fixture. The rest are loud downstream.
- **CO4:** the no-choice scan misses choice forms outside its list (`with` as a handler, dict
  dispatch, a `getattr` default).
- **CO5:** the every-key generator itself is unpinned (`scf-key-sites-skip-lists`,
  `scf-key-plants-skip-changed`, `-skip-gained`).
- **CO6:** `--against ''` falls back to HEAD instead of refusing (`cmd-against-truthy`).
- `cmp-depth-22` survives; already in `issues/surface-pin-completeness.md`.
- Equivalent on the current fixture: `cmp-exempt-deep-default`, `cmp-tol-leaf-number`.

### Cycle-2 findings

| Finding | Status | Evidence (reviewer) |
|---|---|---|
| N1 (the command chose its base) | closed as a property for the command file | no branch in `bin/record_surface.py` (the AST scan; `file-if-branch`, `-bool-op`, `-try` killed); 26 `cmd-*` mutants killed per era bar CO6; only `git` launched, before the fence (`launch_audit.log`). The remediation opened Finding A. |
| N2 (former tolerated kinds unpinned) | closed as a property at the shape level | the four generated tests alone kill all 30 key-exemption and 9 tolerance mutants, the five former kinds by name, per era (`mutants-generated-only.tsv`); deeper layers are CO1, CO2, CO5 |

Seeds filed by `71fa1fc`, graded as prose: `record-surface-relative-out.md`'s problem reproduces
exactly; `surface-pin-completeness.md`'s checkable claims hold; both `status: unshaped`; their
`ROADMAP.md` entries point at existing files and the counts (30 entries, 14 gates) are right at
this commit.

### Mutant tables

`reviewer/mutants.tsv`, `mutants-extra.tsv`, `mutants-generated-only.tsv`, and
`mutants-classified.tsv` (122 applied, each with a reason). Legacy: 96 killed, 26 survived. Modern:
97 killed, 25 survived. The 26 legacy survivors: 1 killed in the modern era (by design), 2
equivalent, 1 already seeded, 22 coverage observations.

### Human-gate triggers

- **Standing trigger:** this cycle changes `tests/fixtures/served_surface.json`, which is on
  § Invariants' high-blast-radius list. Publish needs the maintainer's sign-off whatever the
  verdict. It is not yet recorded.
- **Finding A** is in `bin/record_surface.py` and `tests/test_surface.py`, neither on the list, and
  violates no `[human gate]` section. It governs how the gated fixture is re-taken.
- **Non-convergence:** this is cycle 3 of ≤3 with a new CONFIRMED finding. The loop stops here for
  the maintainer's call.

## Review cycle 1 of the re-shape — changes-requested (2026-11-12)

- **Reviewed commit:** `47b14104c43177beb0afe5068b1b806425d4401c`  ·  **Base:** `develop` (the merge base is `origin/develop` `302bd10`)  ·  **Date:** 2026-11-12
- **Verdict:** changes-requested
- **Cycle:** 1 of the re-shape (`review.cycle` in `TECH.md` restarted at 0 for it). Cycles 1–3 above
  graded the superseded recorder design. Under the maintainer's ruling, the re-shape gets one
  review: a LOW-only result is fixed and lands, and anything higher goes back to him.
- **Mode:** a fresh blind pass over the full spec-excluded diff by one reviewer at effort xhigh. It
  graded against the re-shaped GOAL's R1–R11 with rigor in proportion:
  - mutants were aimed at the comparison, the diff it prints, and the serializer's normalization
    and content;
  - the update mode was graded by its controls and not swept.

  Mutants and update-mode drives ran in a scratch clone at `.local/review4/reviewer/tree/`. The
  sequential fallback did not run. Evidence is under `.local/review4/`: `orch/` and the gate logs
  are the orchestrator's, `reviewer/` is the reviewer's.
- **Contract drift (Step 1.4):** none. `482e092` re-shaped `GOAL.md` and is this shape's shape commit.
  `GOAL.md` has not moved since. The four earlier GOAL commits belong to the superseded design.
- **Grading rule:** survivors are classified by `method/mutation-testing.md` § When a review is done,
  cited to the reviewer and not restated.
- **Blindness:** no breach reported. The reviewer's searches excluded `spec/` and `.local/`. Its one
  read outside the repo was the cited KB section. It used no cluster tools.
- **Blindness trim:** the GOAL text inlined in the prompt had the re-shape Clarification's reference
  to an earlier cycle's REVIEW finding replaced with "an earlier review". It also omitted the
  R-ID delta detail and the Related-materials list. No R-ID text changed.

### Verification run (orchestrator, before the reviewer launched)

- `verify/gate.sh p1`: exit 0 in 4:47.
  - 2828 passed per era.
  - The R6 check passed in both eras.
  - The 11 `tests/mutants.py` cases that plant into the fixture were killed in both eras.
  - `snapshot_checks` passed surface-cases, no-enable and docs.
- `verify/gate.sh p2`: exit 0 in 1:20.
  - Seeds and ledger: ok.
  - The aimed sweep: 30 mutants, 28 killed, 0 survived, 2 equivalent. No sweep child was left, and
    the fixture was untouched.
- Logs: `.local/review4/gate-p1.log` and `gate-p2.log`.
- `full` was **not re-run**. It ran green on `4a6c543`, and `47b1410` changes only `TECH.md`.
  CI on the pushed `-r3` branch was not observed by this step.
- **After the gates:** `git status --porcelain` was empty. The fixture's sha256 equals HEAD's
  (`2e0dc91f…`). The fixture blob is `d51b501b59e9bbe2e13efe20df807ef44cc7fa3b`.
- Once more, the listed sweep was green while the reviewer's sweep of the same domain found 5
  survivors that the list never named (below).

### Orchestrator sanity check

- **Tree:** `git status --porcelain` is empty, and the fixture's sha256 is unchanged. The reviewer
  reports that it mutated no git-ignored build state. Every mutant in its clone was restored with
  `git checkout`, and the restore was asserted.
- **F1 and F2 re-run by the orchestrator.** `reviewer/probes/consequence.py` was run against the
  scratch clone at `47b1410`, with output in `orch/consequence.log`.
  - A one-word description edit fails the baseline under the real code, naming 6 differing fields.
    Under `report-first-line-only` it names 1.
  - A doubled space in the same description fails the baseline under the real code, naming 6
    differing fields. Under the whitespace-blind verdict it passes.
  - The clone was restored clean.
- **Severity re-graded from MEDIUM to LOW.** The reviewer graded F1 and F2 MEDIUM; the orchestrator
  grades them LOW.
  - The shipped code behaves as R3 requires. The reviewer's own drives show the real verdict
    refusing a whitespace-only change, and the real report naming every differing field.
  - What is missing is the control that would catch a regression. That is the rubric's LOW,
    "missing but non-blocking test coverage of an R-ID".
  - This file graded the same kind the same way: cycle 1's F2–F4 and cycle 2's N1–N2 were
    surviving comparison or recorder mutants, each graded LOW.
  - This re-grade decides the routing under the maintainer's ruling, so it is flagged to the foreman
    to confirm.
- **`ver-prefix-match` and `ver-substring-match` are a CONFIRMED finding (F3), not a coverage
  observation.**
  - `version_source` is a pure function, and its table (`tests/test_surface.py:321`) feeds it
    arbitrary installed sets. So "today's installed set" does not bound its domain.
  - On `served='4.1.4', installed={'a': '4.1'}`, both mutants return `a` where R9 requires a failure
    naming the candidates. That breaks R9's stated check.
  - R7 names this class outright: every non-equivalent mutant of each serializer normalization is
    killed.
  - It is the unpinned half of the exact-match decision, not a deeper layer of a pinned class. The
    `one` row's decoys are only versions in which the served value is itself a prefix or substring.

### R-IDs graded by the orchestrator

- **R6, met at the branch; the landing body is publish's.**
  - p1's run of the R6 check reads the staged fixture against `0bfacae`'s, in each era, under set
    `both`.
  - It finds no difference beyond the five formerly tolerated kinds, by the old comparison and by
    the type-strict pass. Every one of the 72 argument descriptions is its `Args:` line.
  - It lists the fields entering as served: `capabilities`, `prompts`, `resourceTemplates`,
    `serverInfo`, `tools.*._meta`, `resources.*._meta`, and the four other sets in each era.
  - The landing commit body must carry that output (`gate-p1.log`).
- **R7's equivalence record: accepted, with one wording note.**
  - `verdict-stripped` is equivalent for the gate. The served side is canonical bytes, so stripping
    the ends can hide no served change, only a hand-edit at the fixture's ends.
  - `sources-lose-cluster-mcp` is equivalent on today's surface only. It diverges at the rename
    cycle, and then fails loudly, naming the candidates: no silent pass. The recorded reason says so.
    The rename cycle's seed should know about it (to seed, below).
  - The reviewer's own four equivalents are accepted: `canon-ensure-ascii-off`,
    `rec-no-json-roundtrip`, `ver-no-isinstance-guard` and `ver-no-none-guard`.
  - R7's kill clause is not met. See F1–F3.
- **R5's commit-body clause: not gradeable before publish.**
  - The landing body carries the fixture's `git diff --stat` and the R6 check's output. It also
    carries the fixture's blob hash: `d51b501b…` at this commit, re-read at landing.
  - The full fixture diff goes to the maintainer as a compare link, not in the body (foreman
    ruling).
  - Publish checks this.

### Requirement → evidence matrix

| R | Met? | Verified by | Evidence |
|---|---|---|---|
| R1 | yes | reviewer | `reviewer/r1_conflict.log`, `r1_drive.log`: a real merge conflict, a missing fixture, an uninstalled distribution and non-JSON content each regenerate to the same sha256, after which the baseline passes. A repeat run writes identical bytes. `0`/`''`/`true`/`yes`/`2`/`' 1'` write nothing. No workflow, `bin/` script or `verify` sets the variable |
| R2 | yes | reviewer | `reviewer/probes/shape.log`, `identity.log`: 2 eras × 5 sets, the four listings, and capabilities and serverInfo per era. Content and canonical-bytes mutants killed (two survivors already seeded) |
| R3 | yes in code; controls partial | reviewer, orchestrator | `reviewer/r5_deliberate.log`; F1, F2; `orch/consequence.log` |
| R4 | yes | reviewer | `reviewer/base_legacy.log`, `base_modern.log`; a modern-era update writes the same bytes |
| R5 | yes at the branch; the body clause at publish | reviewer, orchestrator | `reviewer/r5_deliberate.log`; the fixture is on § Invariants' high-blast-radius list; the commit-body clause is above |
| R6 | yes at the branch; the body at publish | orchestrator | `gate-p1.log` (above) |
| R7 | partial | reviewer, orchestrator | depth and update-mode controls present; 11 fixture cases killed in both eras (`reviewer/mutants_py_*.log`); shape test retired; the N2 controls removed and none duplicates equality; equivalence record accepted; kill clause unmet (F1–F3) |
| R8 | yes | reviewer | §9, § Testing and § Commands read; grep finds no line on the command, its flags, base selection, a tolerance list or the hand-edit rule |
| R9 | yes in code; control partial | reviewer, orchestrator | `reviewer/probes/r9_and_base_url.log`: none and several both fail naming every candidate, in the baseline and in update mode; F3 |
| R10 | yes | reviewer | `bin/record_surface.py` absent; grep finds no command remnant |
| R11 | yes | reviewer | the relative-out seed and its ROADMAP entry are gone; the completeness seed keeps two items, both still surviving; ROADMAP counts follow |

The narrowed verify ran in both eras with 2828 passed per era (`reviewer/narrow_verify.log`). Grep
found no spec ids in the source diff, and the reviewer reports no scope creep.

### Findings

#### F1 [LOW/CONFIRMED, surviving mutant] No control refuses a whitespace-only difference
- **Where:** `tests/test_surface.py:200` (`if expected != served:`).
- **Failure scenario:** the mutant `if expected is None or expected.split() != served.split():`
  survives every test in the module in both eras. Each depth row plants a non-whitespace difference.
  Under the mutant, a doubled space in `myquota`'s docstring passes the baseline (`1 passed`).
- **Evidence:** `reviewer/mutants/results.json` (`cmp-verdict-ignores-whitespace`);
  `orch/consequence.log` part B.
- **Touches:** R3 ("differ in any way"), R7 (the comparison's kill clause).

#### F2 [LOW/CONFIRMED, surviving mutants] No control requires the report to name more than one differing field
- **Where:** `tests/test_surface.py:190` (in `report`) and `:161` (`differences`, the dict branch).
- **Failure scenario:** `report-first-line-only` and `diff-first-only` survive in both eras. Every
  row plants exactly one difference. Under either mutant, a one-word description edit, which differs
  in 6 (era, set) places, prints 1 line.
- **Evidence:** `reviewer/mutants/results.json`; `orch/consequence.log` part A.
- **Touches:** R3 ("naming each differing entry and the path of each differing field"), R7.

#### F3 [LOW/CONFIRMED, surviving mutants] The version source's exact match is pinned in one direction only
- **Where:** `tests/test_surface.py:95` (`version == served` in `version_source`); its table is at `:321`.
- **Failure scenario:** `ver-prefix-match` (`served.startswith(version)`) and `ver-substring-match`
  (`version in served`) survive in both eras. Every decoy in the table is a version that has the
  served value as a prefix or substring, never one that is itself a prefix or substring of the served
  value. Under either mutant, an installed `'4.1'` is recorded as the source of `'4.1.4'`. R9
  requires a failure there.
- **Evidence:** `reviewer/mutants/TABLE.md` rows `ver-prefix-match` and `ver-substring-match`; the
  orchestrator's reading of the table (sanity check above).
- **Touches:** R9 (no match → fail), R7 (the normalization's kill clause).

#### Route (the properties, both ways)
- **The verdict:** the test refuses every byte difference between the serialization and the fixture,
  whitespace inside a string value included, *and* it passes when they are byte-identical, so the
  canonical fixture never draws a refusal.
  - Pin: a control row whose only difference is whitespace inside a string at depth, in both eras.
    The existing baseline holds the passing side.
- **The report:** a failure names every differing (entry, field path), *and* it names nothing that
  does not differ.
  - Pin: a control row that plants two differences in two entries and asserts that the report's
    lines are exactly those two.
- **The version source:** a candidate is the source only when its version equals the served string
  exactly. A candidate whose version is a prefix, suffix or substring of the served value never
  matches, nor one that has the served value as a prefix, suffix or substring. The exact candidate
  still matches.
  - Pin: the `one` and `none` rows gain decoys that are a proper prefix (`'4.1'`) and a proper
    substring (`'.1.'`, or any inner slice) of the served value.
- **The sweep:** the aimed sweep gains the five survivors, each run in both eras, so the listed
  enumeration covers what this pass found: `cmp-verdict-ignores-whitespace`,
  `report-first-line-only`, `diff-first-only`, `ver-prefix-match`, `ver-substring-match`.
- **Size:** in proportion, this is three control rows (the third is the version table's decoys), not
  a module-wide sweep.

### Coverage observations (to seed; not findings)

- `ver-sources-drop-core`: diverges only once the server serves cluster-mcp's version, and then
  fails loudly naming the candidates. **Seed** a line on the rename cycle's seed:
  `issues/rename-leftover-identity-strings.md`, the cycle that flips the source.
- `ver-uninstalled-empty-string`: changes only the error text for an uninstalled candidate.
- `diff-leaf-no-sort-keys`: changes only the report's wording, for a non-canonical fixture with
  dict keys out of order inside a list. The verdict is unchanged.
- `short-limit-6`: changes only how many characters of a value the report shows. The entry and the
  path are still named.
- `rec-drop-execution-key`, `rec-no-cursor-guard`: already seeded in
  `issues/surface-pin-completeness.md`.

The three display-only survivors go to `issues/surface-pin-completeness.md` as one item. The fix
round files both seed lines.

### Mutant tables

`reviewer/mutants/TABLE.md`, with its driver `sweep.py` and data `results.json`. The two eras are
identical: 66 applied, 51 killed, 11 survived, 4 equivalent. The 11 survivors are 5 in F1–F3, 4
coverage observations and 2 already seeded.

### Human-gate triggers

- **Standing trigger:** this cycle changes `tests/fixtures/served_surface.json`, which is on
  § Invariants' high-blast-radius list. Publish needs the maintainer's sign-off whatever the
  verdict, and it is not yet recorded.
  - The landing body carries the fixture's `git diff --stat`, the R6 check's output and the
    fixture's blob hash.
  - The full diff goes to the maintainer as a compare link (foreman ruling).
- F1–F3 are in `tests/test_surface.py`, which is not on the list, and they violate no `[human gate]`
  section.
- **Routing under the re-shape ruling:** with the re-grade, the result is LOW-only plus coverage
  observations. The fix round adds the three control rows and the sweep entries and files the seed
  lines; then the human gate applies. If the foreman holds the reviewer's MEDIUM instead, F1 and F2
  go back to the maintainer and not to build.

## Publish sign-off (human gate)

- **Recorded:** 2026-11-12, the maintainer: publish; the MEDIUM→LOW re-grade stands; keep the '1.4' decoy.
- **What it settles:** the standing trigger above (the fixture is on § Invariants' high-blast-radius
  list). With the re-grade standing, the re-shape's review is LOW-only, so under the re-shape ruling
  the fix round (`5eda050`, F1–F3) lands without a further review: it stands in for an `approved`
  verdict and for the staleness gate on that commit's changes outside `spec/`.
