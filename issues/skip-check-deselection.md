---
status: unshaped
kind: test
appetite: small
lane: public
---

# A conftest can drop rows from a CI run without skipping them

## Problem

`test_only_need_shell_skips` keeps a row from skipping on CI unseen, but a skip is not the only way
a row leaves a run. A conftest can make rows vanish without any skip the check reads:

- `collect_ignore` or `collect_ignore_glob`, or a `pytest_ignore_collect` hook, keeps modules from
  being collected at all;
- `pytest_collection_modifyitems` can remove items from `items`, so they never run. Reporting them
  through `config.hook.pytest_deselected` is optional: on its own it removes nothing, and the rows
  still run (the summary counts them as deselected all the same);
- `pytest.exit(..., returncode=0)` ends the session early with a passing exit code, and the rows
  after it never run. With its default return code, `pytest.exit` ends the run with exit code 2,
  so CI fails.

Each is statically visible, and each leaves the run exiting 0 with the rows gone, so CI passes
(each run under pytest, 2026-11-09). Today `tests/conftest.py` defines one
`pytest_collection_modifyitems`, which fails the run on an unmarked test (exit code 4) and removes
nothing; no module sets `collect_ignore` or calls `pytest.exit`. The repo sets no `testpaths`, so
when pytest runs with no path arguments, as the suite's last command in each era does, a
`conftest.py` anywhere it collects from (a spec directory, for one) is loaded too, and its hooks
apply to every collected row.

## Why it was deferred

Raised by the adversarial review of `skip-check-fence-gaps`'s plan (2026-11-09). That cycle's GOAL
is about skips; deselection is not one, so it was outside its contract. The sign-off seeded it here
rather than widening that cycle.

**Pre-existing:** yes; the static check has never looked for deselection.

## Outcome / vision

A row the suite collects on CI either runs or fails the run: a static check (or a run-time count
the shaping conversation prefers) reports any conftest that ignores modules or removes collected
items, and any module that ends the session early with a passing exit code, outside an allowed and
named exception.

## Sketch of the acceptance criteria

- **R1** — WHEN a conftest the suite loads sets `collect_ignore` or `collect_ignore_glob`, or
  defines `pytest_ignore_collect`, the check SHALL report it.
- **R2** — WHEN a `pytest_collection_modifyitems` hook removes items, whether or not it reports
  them deselected, the check SHALL report it; the existing hook, which only fails the run, SHALL
  stay admitted.
- **R3** — WHEN a conftest or test module calls `pytest.exit` with a return code of 0, or one a
  static parse cannot read, the check SHALL report it; the default return code fails the run on
  its own.
- **R4** — Each shape SHALL have a planted row that fails if the check admits it.

## Notes

- Related: `spec/skip-check-fence-gaps/` (PLAN § 4a and § 5, Q2); `issues/skip-check-import-aliases.md`;
  `AGENTS.md` § Testing.
- Found by: `skip-check-fence-gaps` plan, adversarial review, 2026-11-09.
