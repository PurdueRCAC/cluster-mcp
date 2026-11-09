# REVIEW — The static skip check catches the skips it admits today

> Adversarial QA by `code-review`, run in an isolated context (a fresh subagent). The correctness
> pass grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants
> **only**: it does not see `PLAN.md`/`TECH.md`. Every finding cites an **executed** command, not an
> assertion. Evidence files are in the worktree's gitignored `.local/review1/`.

- **Reviewed commit:** 900d9f4  ·  **Base:** develop  ·  **Date:** 2026-11-09
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`

## Verification run

- `uv sync --locked`, `uv lock --check` → pass.
- `bin/sandbox.sh` drive of `uv run pytest -q tests/test_hygiene.py`, handshake era → 104 passed;
  `CLUSTER_MCP_TEST_ERA=modern` → 104 passed (`hygiene-legacy.log`, `hygiene-modern.log`).
- The skip-check rows by name (`-v -k`) → 30 passed, 74 deselected (`planted-rows.log`).
- The profile `verify`'s fourth command (every module but the four `--ignore`d), both eras → 4331
  passed, 14 skipped each; every skip is `tests/conftest.py:99` (`need_shell`, bash 4.1+ absent on
  this host) (`verify-legacy-part4.log`, `verify-modern-part4.log`).
- `bin/sandbox.sh uv run cluster-mcp --help` → exit 0, usage printed (`cli-help.log`).
- Not run: the `verify`'s first three commands in each era (`test_ssh_exec`, `test_timeout_stop`,
  `test_startup`, `test_launch`). They neither import nor reference `test_hygiene`, and
  `tests/conftest.py` is unchanged. Not observed, not satisfied: publish runs the full gate.
- Probes: `probe.py` / `probe.log` runs develop's check and the branch's over every planted row and
  about 60 sibling shapes; `mutants.py` / `mutants.log` runs 12 mutants of the new check against
  the planted rows.
- `git status --porcelain` empty at hand-back; no build state mutated.

## Requirement → evidence matrix

All rows verified by the blind reviewer; no artifact-deliverable R-ID in this GOAL.

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `tests/test_hygiene.py` (`skip_violations`, `_allowed`, `SCOPES`) | Rows `helper-nested-in-a-fixture`, `helper-as-a-method`, `helper-nested-in-the-helper` pass; siblings (async fixture, class inside the helper, skip in decorator or default, `try`-wrapped def, lambda or class bound to the name) all reported; mutant M2 killed (`probe.log`, `mutants.log`) | ✅ |
| R2 | same (`_module_bindings`, "defined again") | Six rebinding rows pass; every other rebinding form (annotated assignment, `for`, `with`, walrus, `del`, `import`, `except as`, `match`, `type`, `global`, decorated redefinition) reported; M7–M9 killed. The skip-less double definition is reported but unpinned: F3 | ✅ (pin gap, F3) |
| R3 | same (`CONFTESTS`) | Rows `look-alike-conftest`, `another-conftest` pass; `tests/test_conftest.py`, `tests/myconftest.py`, `tests/sub/conftest.py` reported; M1 killed by two rows | ✅ |
| R4 | same | Rows `skip-through-an-attribute`, `mark-through-an-attribute` and four `raised-*` rows pass; siblings (`__call__`, `__wrapped__`, `with_args`, `raise … from None`, raise in a conditional expression, `import pytest as pt` + `raise pt.skip.Exception`) reported; M4, M5, M11 killed | ✅ |
| R5 | same | The real `tests/conftest.py` admitted; the outcome type as a value admitted (assigned, in `pytest.param`, `pytest.raises`, `except`, `isinstance`, `raise X from …`); `test_only_need_shell_skips` passes in both eras | ✅ |
| R6 | `test_skip_check_catches_planted_skips` | 20 rows added; all 17 that expect a report fail under develop's check; the 9 existing rows unchanged and give the same result on develop and the branch; 29 planted rows pass | ✅ (R2 pin gap, F3) |

Unmapped changes: `ROADMAP.md`, the new seeds `issues/skip-check-deselection.md` and
`issues/skip-check-import-aliases.md`, and the status change on `issues/skip-check-fence-gaps.md`.
They are deferral bookkeeping under `AGENTS.md` § Factory → Where deferred work goes, and the seed
status matches the cycle in flight. The GOAL non-goal "this cycle touches only
`tests/test_hygiene.py` and its own spec" read literally excludes them; recorded for the
maintainer's ruling, not as a finding. The diff touches no `tests/mutants.py`. No spec ids in the
added lines (`greps.log`); no `AGENTS.md` drift (the new symbols are private to the check).

Seed prose checked against the repo: `skip-check-deselection`'s claims hold (one
`pytest_collection_modifyitems` in `tests/conftest.py`, which removes nothing; no `testpaths`; a
demo with the repo's pytest config showed a `spec/` conftest silently dropping a failing row,
`collect-demo.log`); both seeds' "pre-existing" claim holds (`skip_violations` arrived in
`fbd21e8`, 2026-10-23). Every `ROADMAP.md` file reference exists.

## Findings

### [LOW/CONFIRMED] F1 — `ROADMAP.md` Part I header keeps the old entry count
- **Where:** `ROADMAP.md:48`
- **Failure scenario:** the diff adds two Part I entries (26 → 28) and updates the count on line
  11 and the gates group ("twelve entries", line 69), but the Part I header still reads
  "Twenty-six entries", so the file contradicts itself.
- **Evidence:** counting `## ` headings between `# Part I` and `# Part II`: 26 on
  `origin/develop`, 28 on HEAD; line 11 says "28 entries", line 48 "Twenty-six entries"
  (`roadmap-counts.log`).
- **Touches:** the cycle's deferral bookkeeping (no R-ID).

### [LOW/CONFIRMED] F2 — The import-alias seed overstates the defect for `skipif`
- **Where:** `issues/skip-check-import-aliases.md`, Problem, first bullet
- **Failure scenario:** the seed says the renamed-on-import shape holds for `xfail`, `skipif` and
  `importorskip` and "would let a row vanish from CI without failing". `from pytest import skipif`
  raises `ImportError` (and `pytest.mark` is not importable as a module), so that spelling breaks
  collection loudly; it never skips a row. The check does admit it statically, so the claim is an
  overstatement, not a wrong defect.
- **Evidence:** `skip`, `xfail`, `importorskip` import; `skipif` gives `ImportError: cannot import
  name 'skipif' from 'pytest'`; `ModuleNotFoundError: No module named 'pytest.mark'`
  (`import-skipif.log`); the alias and subclass shapes pass the check on develop and HEAD
  (`probe.log`, rows "SEED").
- **Touches:** seed prose (no R-ID).

### [LOW/CONFIRMED] F3 — R2's own report has no planted row that pins it
- **Where:** `tests/test_hygiene.py` (`skip_violations`, the "defined again" report; the R2 rows
  near line 827)
- **Failure scenario:** a conftest that defines `need_git` twice with no skip in either body is
  reported by the branch's check (`conftest.py:3: need_git defined again`), as R2 requires. Mutant
  M6 removes that report and the check then returns nothing for that input, yet every planted row
  still passes: each R2 row also plants a skip, which a second mechanism reports. A regression of
  R2's report would go unseen, so R6 ("a planted row … that fails if the check admits it") is not
  met for R2's shape on its own. Mutants M3 (no top-level requirement) and M10 (only defs are
  bindings) survive too; whether they are equivalent is not established.
- **Evidence:** `mutants.log` lines 7–10 (M6 rows failing 0; M6 on the skip-less double
  definition → `[]`, shipped → `['conftest.py:3: need_git defined again']`), lines 4 and 15 (M3,
  M10 rows failing 0).
- **Touches:** R2, R6. Classified by the orchestrator from the reviewer's executed evidence, under
  the rubric's coverage-observation rule (a surviving mutant that breaks an R-ID's stated check is
  CONFIRMED); the reviewer recorded it as a note.

Admitted siblings outside R4's "raised directly" and named as unseen in the check's docstring (the
outcome type held in a name and then raised; `gen.throw(pytest.skip.Exception(...))`): not
findings.

## Human-gate triggers

- Not triggered: no finding touches a path on § Invariants' high-blast-radius list or violates a
  `[human gate]` section.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run.

## Review cycle 2 — changes-requested (2026-11-09)

- **Reviewed commit:** fb96211  ·  **Base:** develop  ·  **Cycle:** 2 of ≤3
- **Mode:** a fresh blind pass over the full spec-excluded diff (one reviewer, a fresh subagent), which
  also checked that F1–F3 are closed as properties. The reviewer was given F1–F3's text from this
  file. Evidence is in the worktree's gitignored `.local/review2/`.
- **Blindness note:** the reviewer ran two greps whose `spec/` exclusion did not take, because the
  paths printed without a leading `./`. A few single matching lines from this cycle's `REVIEW.md`,
  `PLAN.md`, `TECH.md` and a `verify/` note reached it. Most restated F1, the cycle 1 matrix or mutant
  labels. It opened no spec file. Its findings and mutants rest on its own executed evidence.

### Verification run

- `uv sync --locked`, `uv lock --check` → pass (`setup.log`).
- `bin/sandbox.sh` drive of `uv run pytest -q -rs tests/test_hygiene.py` → 121 passed in the handshake
  era and 121 passed with `CLUSTER_MCP_TEST_ERA=modern` (`verify-hygiene-legacy.log`,
  `verify-hygiene-modern.log`).
- The skip-check rows run by name → 48 passed and 73 deselected in each era. That is 46 planted rows,
  `test_only_need_shell_skips` and the spec-id scan (`verify-skiprows-{legacy,modern}.log`).
- `bin/sandbox.sh uv run cluster-mcp --help` → exit 0 (`verify-help.log`).
- The in-process harness (`harness.py`) produced these logs:
  - `rows.log`: all 46 rows pass, with paths spelled both relative and absolute.
  - `mutants.log`: 60 mutants of the check, 52 killed, 8 survived.
  - `equiv.log`: 9,724 generated conftest texts × 2 path spellings, used to test survivors for
    equivalence.
  - `probe.log`: constructed inputs, run on HEAD and on develop.
  - `runtime.log`: real pytest runs testing the seeds' claims.
  - `crashfuzz.log`: 3,393 `.py` files × 2 spellings, 0 crashes.
- Not run: the profile `verify`'s other three commands in each era. No other module references the
  changed symbols. These were not observed, which is not the same as satisfied; publish runs the
  full gate.
- `git status --porcelain` was empty at hand-back (re-checked by the orchestrator). The reviewer
  changed no build state.

### Requirement → evidence matrix

There is no artifact-deliverable R-ID. The blind reviewer verified every row, and the orchestrator
spot-checked findings A–C in `probe.log`, `mutants.log`, `equiv.log` and `runtime.log`.

| R-ID | Verified how | Status |
|------|--------------|--------|
| R1 | Five nested, method and async rows pass, and develop admits each of them. Probes for a method beside the real helper, a def inside `try`/`with`, and a class method inside the helper are all reported. Mutants V10, V37 and V41 are killed. | ✅ |
| R2 | The row `helper-defined-twice-without-a-skip` alone kills V31 and V43, so the report is pinned. Every binding kind is killed: V13–V25, V57, V59–V61. | ✅ |
| R3 | Look-alike and other-conftest rows pass. V28 (develop's suffix rule), V29 and V30 (basename) are killed. Both `CONFTESTS` members are pinned, V07 by the rows and V08 by the suite scan. | ✅ |
| R4 | Six attribute and raise rows pass. V44, V46 and V48 (develop's any-attribute rule) and V47 (the cause row) are killed. | ✅ |
| R5 | The real conftest is admitted and the suite scan is clean in both eras. V49 makes the value references in `test_hygiene.py` and `test_registry.py` fail. But some value shapes are reported (A), and the admission is unpinned against a module-scope read of the helper (B). | ❌ (A, B) |
| R6 | 37 rows were added, and all 46 pass in both eras. The 9 existing rows are unchanged in text and verdict. | ✅ |

Unmapped changes: only the deferral bookkeeping (`ROADMAP.md`, the two seeds and the seed status),
which the foreman ruled in scope under `AGENTS.md` § Factory → Where deferred work goes. A grep
finds no spec ids and no internal names in the diff. There is no `AGENTS.md` drift: § Testing lists
only the `*_violations` functions, and the new symbols are private.

### Cycle 1 findings

- **F1: closed as a property.** Line 11, line 48 and the gates group agree at 28 entries: 28 headings,
  28 Seed lines, and groups that sum to 12+6+5+3+2. No other `.md` file carries a stale count, and
  every link resolves.
- **F2: instance closed, but the property is open.** The import-alias seed's claims now hold at run
  time. A sibling overstatement remains in the other new seed: finding C.
- **F3: closed as a property.** R2's report is pinned (V31, V43). "Only defs count as bindings" is
  killed (V60, V61). "No top-level requirement" (V35) survives but is equivalent: 0 differences
  over the corpus, since the subtraction removes every helper-named scope not in `tree.body`.

### Findings

#### [LOW/CONFIRMED] A — R5: the check reports things that are neither a skip nor a second definition
- **Where:** `tests/test_hygiene.py:786`, where the `raised` set takes every node under a `raise`'s
  exception expression. Also `_module_bindings`, near line 712.
- **Failure scenario:** `raise AssertionError(pytest.skip.Exception)`, an f-string or `repr(...)` of
  `pytest.xfail.Exception` inside a raised message is each reported as a skip. In each, the outcome
  type is a value that is never raised, which R5 says the check keeps admitting.
- **Sibling:** in `tests/conftest.py`, some forms that bind nothing at module scope count as a second
  definition: an annotation without a value (`need_git: object`), a comprehension variable, and a
  `global need_git` with no store. The check then reports "defined again", and the real helper's
  skips stop being admitted.
- **Severity:** both fail closed and name the line, and neither lets a skip through.
- **Evidence:** `probe.log` rows `r5-raise-arg`, `r5-raise-fstring`, `r5-raise-type-error-msg`,
  `over-annotation-only`, `over-comprehension-var`, `over-global-read-only` (HEAD reports, develop
  admits).
- **Touches:** R5.

#### [LOW/CONFIRMED] B — R5's admission is unpinned against a module-scope read of the helper
- **Where:** `tests/test_hygiene.py:730` (`bound = node.id if not isinstance(node.ctx, ast.Load) else None`)
- **Failure scenario:** mutant V16 counts a load as a binding, and it survives all 46 rows and the
  suite scan. It is not equivalent. Take a conftest with `def need_git(): pytest.skip("g")` followed
  by `H = (need_git,)`: HEAD admits the helper's skip and V16 reports "defined again". That breaks
  R5 on reachable input, so this is CONFIRMED under the rubric's coverage-observation rule.
- **Evidence:** `mutants.log` ("V16: SURVIVED"); `equiv.log` (93 verdict differences, the shortest
  being `def_skip+load`, `def_pass+load` and `assign+load`).
- **Touches:** R5, R6.

#### [LOW/CONFIRMED] C — The deselection seed and its ROADMAP entry overstate `pytest.exit`
- **Where:** `issues/skip-check-deselection.md:21` ("none fails CI") and `ROADMAP.md:129` ("make rows
  vanish from CI as surely as a skip").
- **Failure scenario:** `pytest.exit("stop")` with the default return code ends the run with exit
  2, whether it is called from a runtest hook, from `pytest_collection_modifyitems` or from inside a
  test. So CI fails. Only `pytest.exit(..., returncode=0)` drops rows on a passing run. The seed's
  other mechanisms do exit 0: `collect_ignore`, `pytest_ignore_collect`, and a modifyitems hook that
  removes or deselects items. So does a subdirectory conftest, since the repo sets no `testpaths`.
- **Evidence:** `runtime.log`, cases `exit_default_in_hook`, `exit_default_in_modifyitems` and
  `exit_default_in_test` (exit 2), and `exit_rc0_in_hook` (exit 0).
- **Touches:** seed prose (no R-ID). It is the same class as F2.

### Coverage observations (not findings)

- **Verdict-equivalent survivors** (0 corpus differences): V26 and V42 change only the order or line
  of the "defined again" message. V32 and V33 (first or last binding wins) change no verdict. V35 is
  covered under F3.
- **V40** (the subtraction ignores classes) differs only for a class named like a helper nested
  inside the real helper. That is stricter than R1, which names functions.
- **V54** (develop's line-based admission) differs only for a skip in a one-line top-level helper's
  default argument, a position no R-ID names.
- The docstring lists "a skipper carried through a name" as unseen, yet the check does catch
  `s = pytest.skip`. The prose is conservative, not a defect.

### Routing (to build)

Each finding is routed as a property over its whole domain. The instances above are only examples.

- **What the check reports (A, and the R4 side it trades against):** report every `raise` whose
  exception is the skip or xfail outcome, whether bare, called, or with a cause. Admit the outcome
  type wherever it is a value other than the raised exception itself. Pin both sides with planted
  rows: an argument, a message and a format string inside a raise stay admitted, and every
  existing raise row stays reported.
- **What counts as a second definition (A's sibling and B):** count only a module-scope store that
  rebinds the name. Keep reporting every real rebinding form R2 pins. Admit loads, annotations
  without a value, comprehension variables and a `global` with no store. Pin both sides.
- **The surviving mutant (B):** run a mutant sweep over every decision in the skip check
  (`skip_violations`, `_allowed`, `_module_bindings`), under both test eras. Record each equivalent
  mutant and why it is equivalent.
- **Seed prose (C):** every runtime claim in the cycle's seeds and ROADMAP entries should be stated
  as the mechanism behaves on a run. Check each one by a real pytest run: `pytest.exit` drops rows
  on a passing run only with `returncode=0`.

### Human-gate triggers

- Not triggered: the diff touches no path on § Invariants' high-blast-radius list, and no finding
  violates a `[human gate]` section.

### Convergence

- This is review cycle 2 without convergence. All three findings are LOW and fail-closed or prose,
  and F1 and F3 have closed. Under the bounded loop this goes to the maintainer before a third
  build↔review round.
