---
status: unshaped
kind: test
appetite: small
lane: public
---

# Nothing pins the sandbox sweep's refusal when it cannot list processes

## Problem

`tests/sandbox_dirs.py` decides whether a sandbox directory is in use from a table of every process
of the account: on macOS `processes()` reads working directories with `lsof` and environments with
`ps -E`, and when `ps` exits non-zero or `lsof` prints nothing it raises
(`tests/sandbox_dirs.py:156`). The raise is what keeps the cleanup from guessing: the session sweep
and the mutation runner's `case_scratch` then keep what they found instead of treating an empty
table as "nothing in use".

No test fails when that check is removed. `sandbox-dirs-left-on-kill`'s review, cycle 1, planted it
by hand (the condition made `if False:`), and the mutant survived `tests/test_sandbox_dirs.py`. With
it, a failed `lsof` or `ps` yields a table with no users, and the sweep would remove sandbox
directories still in use.

A coverage observation, not a defect: the guard works today, and it fires only when `lsof` or `ps`
fails, which no run of the suite reaches.

## Why it was deferred

Defence in depth with no reachable trigger in the suite, so the review's rubric records it as a
coverage observation and seeds it rather than blocking the cycle (2026-11-12).

## Outcome / vision

Removing the listing-failure check, on either platform's path, fails a test with a message that
names the contract: a sweep that cannot list processes removes nothing.

## Sketch of the acceptance criteria

- **R1** — WHEN the process listing fails (a non-zero `ps`, an empty `lsof`), the sweep and
  `case_scratch` SHALL remove no sandbox directory, and a test SHALL fail if that check is removed.

## Notes

- Refs: `tests/sandbox_dirs.py` (`processes`, `sweep`), `tests/mutants.py` (`case_scratch`),
  `tests/test_sandbox_dirs.py`; [`spec/sandbox-dirs-left-on-kill/REVIEW.md`](../spec/sandbox-dirs-left-on-kill/REVIEW.md)
  (cycle 1, coverage observation).
- Found by: `sandbox-dirs-left-on-kill`'s review, cycle 1, 2026-11-12.
