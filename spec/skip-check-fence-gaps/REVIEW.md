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
