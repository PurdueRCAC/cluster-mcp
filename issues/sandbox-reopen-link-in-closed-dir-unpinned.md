---
status: unshaped
kind: test
appetite: small
lane: public
---

# Nothing pins that the sandbox cleanup's reopen ignores a link inside a closed directory

## Problem

Before it lists or removes anything, the suite's sandbox sweep and the mutation runner's
`case_scratch` reopen the directories a stopped test left closed (mode `0o555` or `0`) inside the
run's own directory or the case's scratch. `tests/sandbox_dirs.py` `_open_tree` (`:111-122`) walks
that tree without following links: it reads each directory's mode with `os.lstat` (`:116`) and
descends only into entries that are directories in their own right (`entry.is_dir(follow_symlinks=False)`,
`:122`). So a link out of the run's directory never leads the cleanup to change a directory
outside it.

The rows that pin this (`tests/test_sandbox_dirs.py:226-241` for the sweep, `:335-340` for
`case_scratch`) place the links at the top of the run directory or scratch, which is open. No row
places a link inside a directory the test left closed. `sandbox-dirs-left-on-kill`'s review, cycle
2, planted by hand a mutant that follows links at both points (`os.stat` and `entry.is_dir()`); it
survived `tests/test_sandbox_dirs.py` (26 passed). Driven directly, with a link inside a closed
directory in the run's directory pointing at a closed directory outside it, the mutant changed the
outside directory's mode from `0o555` to `0o755`, at both sites. HEAD leaves it at `0o555`. Each of
the two guards alone, mutated, is masked by the other (an equivalent mutant).

A coverage observation, not a defect: the code is correct today, the class (the cleanup does not
follow links) is pinned at its top layer, and no test in the suite leaves a link inside a closed
directory.

## Why it was deferred

A deeper layer of a class already pinned, with no reachable trigger in the suite, so the review's
rubric records it as a coverage observation and seeds it rather than blocking the cycle
(2026-11-12).

## Outcome / vision

Making the reopen walk follow links, at either point or both, fails a test with a message that
names the contract: the cleanup never alters a directory outside the run's own directory, however
deep the link that reaches it.

## Sketch of the acceptance criteria

- **R1** — WHEN a link inside a closed directory in the run's directory or a case scratch points at
  a closed directory outside it, the sweep and `case_scratch` SHALL leave that directory's mode
  unchanged, and a test SHALL fail if `_open_tree` follows the link.

## Notes

- Refs: `tests/sandbox_dirs.py` (`reopen`, `remove`, `_open_tree`), `tests/mutants.py`
  (`case_scratch`), `tests/test_sandbox_dirs.py`;
  [`spec/sandbox-dirs-left-on-kill/REVIEW.md`](../spec/sandbox-dirs-left-on-kill/REVIEW.md) (cycle 2,
  coverage observation).
- Found by: `sandbox-dirs-left-on-kill`'s review, cycle 2, 2026-11-12.
