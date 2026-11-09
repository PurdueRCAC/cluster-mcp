# GOAL — The static skip check catches the skips it admits today

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** skip-check-fence-gaps
- **kind:** test
- **appetite:** small

## Problem

A row that skips on CI disappears from the run without failing it. The suite fences that off with a
static check: `skip_violations` in `tests/test_hygiene.py` (line 707), run over every `tests/*.py` by
`test_only_need_shell_skips` (line 725). It reports every `skip`, `skipif`, `importorskip` and
`xfail` outside two allowed helpers, `conftest.need_shell` and `conftest.need_git`, which skip
locally but fail on CI instead.

The check's idea of "inside an allowed helper" and "a skip" is looser than that fence needs. A
planted-skip probe found four shapes it admits:

- **Nested or method helpers.** It allows the body of *any* function definition with an allowed name,
  found by walking the whole tree (line 713), so one nested inside a conftest fixture, or defined as
  a class method, is allowed too.
- **Redefinition.** A second definition of an allowed name in conftest is allowed like the first,
  though it shadows it.
- **Look-alike module names.** It recognises conftest with `name.endswith('conftest.py')` (line 713),
  so a test module named `tests/test_conftest.py` may define and use its own `need_shell` that skips.
- **Attribute spellings.** Any attribute access on a skipper exempts it (line 716), so that
  `pytest.skip.Exception` can name the outcome type; but that also exempts `pytest.skip.__call__(...)`,
  which skips, and `raise pytest.skip.Exception(...)`, which skips too (found while confirming the
  seed's anchors).

None of these exists in the suite today. The defect is **pre-existing**: the check has had these
shapes since `safe-execution` added it, and `absence-check-leftover-classification` only extended
its allowed set to `need_git`.

## Outcome / vision

The check admits a skip only inside the single, top-level definition of an allowed helper in
`tests/conftest.py` itself, and reports every statically visible spelling of a skip the cycle covers
(R4), while still letting a test name the skip outcome type as a value.

## Acceptance criteria (the contract)

- **R1** — WHEN a skip, conditional skip or expected failure sits inside a function with an allowed
  helper's name that is not a top-level definition in `tests/conftest.py` (nested in another function
  or fixture, or a method of a class), the check SHALL report it.
- **R2** — WHEN `tests/conftest.py` defines an allowed helper's name more than once, the check SHALL
  report a violation.
- **R3** — WHEN a module other than `tests/conftest.py` defines an allowed helper, including a module
  whose file name merely ends in `conftest.py` (such as `tests/test_conftest.py`), the check SHALL
  report the skip inside it.
- **R4** — WHEN a skipper is reached through an attribute of itself other than naming the outcome
  type as a value (such as `pytest.skip.__call__(...)`), or a skip or xfail outcome is raised
  directly (`raise pytest.skip.Exception(...)`, `raise pytest.xfail.Exception(...)`), the check
  SHALL report it.
- **R5** — The check SHALL keep admitting the skips inside the single top-level `need_shell` and
  `need_git` in `tests/conftest.py`, and a reference to the outcome type as a value, never raised
  (`pytest.skip.Exception`, as `tests/test_hygiene.py` and `tests/test_registry.py` use it); and
  `test_only_need_shell_skips` SHALL pass on the suite as it stands.
- **R6** — Each shape R1–R4 reports, the raised outcome among them, SHALL have a planted row in
  `test_skip_check_catches_planted_skips` (line 745) that fails if the check admits it, and every
  existing planted row SHALL keep its expected result.

## Non-goals (no-gos)

- Lookups a static parse cannot resolve: `getattr(pytest, 'skip')`, `vars(pytest)[…]`, a skipper
  passed through a container or a function argument.
- unittest's skip spellings (`self.skipTest`, `unittest.skipIf` / `skipUnless`,
  `raise unittest.SkipTest`): none is in the suite, which is pytest-style.
- Pytest's private outcome classes imported by name (`from _pytest.outcomes import Skipped`).
- Changing which helpers may skip, or how `need_shell` and `need_git` behave on and off CI.
- Widening the scan past `tests/*.py` (subdirectories, the package source).
- Enforcing the fence at run time (for example failing CI on any skipped row); it stays a static
  check.
- The other static checks in `tests/test_hygiene.py` (sandbox, stack import, spec id), even where
  they share the same attribute pattern.
- Any edit to `tests/mutants.py`. Two sibling gate cycles in 0.2.0 change that file; this cycle
  touches only `tests/test_hygiene.py` and its own spec.

## Clarifications

- **Q:** The seed's Outcome says the check catches "every spelling of a skip call", which a static
  parse cannot do for dynamic lookups. Which spellings does this cycle cover: (a) any attribute of a
  skipper except naming `.Exception` as a value; (b) (a) plus raising the skip or xfail outcome
  directly; (c) (b) plus unittest's spellings? — **A:** (b). R4 covers any attribute of a skipper
  other than naming the outcome type as a value, and raising the skip or xfail outcome directly; R5
  admits `.Exception` only as a value, never raised; unittest's spellings are a non-goal; R6 plants
  a row for the raise shape (resolved 2026-11-09, foreman ruling at the GOAL gate).

## Related materials

- Seed: [`issues/skip-check-fence-gaps.md`](../../issues/skip-check-fence-gaps.md)
- Roadmap: `ROADMAP.md` Part I, "The static skip check admits a skip it should catch" (0.2.0, gates)
- Source: `tests/test_hygiene.py` (`SKIPPERS`, `SKIP_HELPERS`, `skip_violations`,
  `test_only_need_shell_skips`, `test_skip_check_catches_planted_skips`); `tests/conftest.py`
  (`need_shell`, `need_git`)
- Origin of the check: [`spec/safe-execution/`](../safe-execution/)
- Landing merge that found the shapes:
  [`spec/absence-check-leftover-classification/REVIEW.md`](../absence-check-leftover-classification/REVIEW.md)
- `AGENTS.md` § Testing
