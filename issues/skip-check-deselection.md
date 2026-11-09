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
- `pytest_collection_modifyitems` can remove items from `items` (or report them through
  `config.hook.pytest_deselected`), so they never run;
- `pytest.exit(...)` ends the session early, and the rows after it never run.

Each is statically visible in a conftest, and none fails CI. Today `tests/conftest.py` defines one
`pytest_collection_modifyitems`, which fails the run on an unmarked test and removes nothing; no
module sets `collect_ignore` or calls `pytest.exit`. The repo sets no `testpaths`, so a
`conftest.py` anywhere pytest collects from (a spec directory, for one) is loaded too.

## Why it was deferred

Raised by the adversarial review of `skip-check-fence-gaps`'s plan (2026-11-09). That cycle's GOAL
is about skips; deselection is not one, so it was outside its contract. The sign-off seeded it here
rather than widening that cycle.

**Pre-existing:** yes; the static check has never looked for deselection.

## Outcome / vision

A row the suite collects on CI either runs or fails the run: a static check (or a run-time count
the shaping conversation prefers) reports any conftest that ignores modules, removes collected
items or ends the session early, outside an allowed and named exception.

## Sketch of the acceptance criteria

- **R1** — WHEN a conftest the suite loads sets `collect_ignore` or `collect_ignore_glob`, or
  defines `pytest_ignore_collect`, the check SHALL report it.
- **R2** — WHEN a `pytest_collection_modifyitems` hook removes items or reports them deselected,
  the check SHALL report it; the existing hook, which only fails the run, SHALL stay admitted.
- **R3** — WHEN a conftest or test module calls `pytest.exit`, the check SHALL report it.
- **R4** — Each shape SHALL have a planted row that fails if the check admits it.

## Notes

- Related: `spec/skip-check-fence-gaps/` (PLAN § 4a and § 5, Q2); `issues/skip-check-import-aliases.md`;
  `AGENTS.md` § Testing.
- Found by: `skip-check-fence-gaps` plan, adversarial review, 2026-11-09.
