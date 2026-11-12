---
status: unshaped
kind: test
appetite: small
lane: public
---

# A write's unnamed cause survives the mutation run on Linux

## Problem

When a write over SSH fails and the file is left unchanged, the error names the cause the executor
found: `f'{self._reason(staged, deadline) or exc}; the file is unchanged'`
(`core/executor/ssh.py:1829`). The mutation case `transfer-cause-unnamed` drops `self._reason(...)`,
leaving only `{exc}`. Its target is
`tests/test_ssh_exec.py::test_a_write_that_runs_out_of_room_keeps_the_file[8k-free]`
(`tests/test_ssh_exec.py:813`), with the `why` "does not name its cause".

The first dispatched mutation run (run `43255195424` at `aff08bd`, 2026-11-12, by
`mutants-workflow-timeout`) reported the case `FAILED` in shard 60 of 78: its target passed on the
runner, so the mutant survived.

Run alone on macOS at the same commit (`uv run python tests/mutants.py transfer-cause-unnamed`), it
is killed: the target fails with "does not name its cause".

**Likely cause (unverified):** on Linux the bare exception's text already holds what the row looks
for, e.g. the operating system's "No space left on device" from the full volume. So the mutant is
equivalent there for this row's assertion. On macOS the exception text differs, perhaps because of
how the full-volume fixture is made, and only `_reason` supplies the cause. If so, the row checks
the message's words rather than that `_reason`'s cause is the one reported.

## Why it was deferred

The cycle that found it, `mutants-workflow-timeout`, has a non-goal: it changes no case, target or
`why`. The maintainer ruled under its GOAL Q3 that the seven Linux-only survivors are seeded in four
groups. This seed is one of them.

The survivor is **pre-existing**: the case and the row are older than the cycle.

## Outcome / vision

On the hosted Linux runner `transfer-cause-unnamed` is killed: the row tells the executor's named
cause from a bare exception's text on both platforms. The executor's behaviour is unchanged.

Possible fix shapes, for shaping to choose between:
- a row assertion keyed to `_reason`'s own wording rather than to words the operating system may
  also print;
- an extra parameter whose exception text carries no cause;
- a Linux single-case probe that runs the case in CI before a dispatch.

## Sketch of the acceptance criteria

- **R1** — WHEN `transfer-cause-unnamed` is applied on the hosted Linux runner, its target row SHALL
  fail with "does not name its cause".
- **R2** — WHEN it is not applied, the row SHALL pass on Linux and macOS as it does today.

## Notes

- Related: `issues/mutants-linux-bashrc-norc.md`, `issues/mutants-linux-posix-paths.md`,
  `issues/mutants-linux-fd-59.md`; `issues/full-volume-fixture-leaks-hdiutil.md` (the macOS
  full-volume fixture); `spec/mutants-workflow-timeout/` (TECH Amendments, 2026-11-12, P3 run 1).
- Found by: `mutants-workflow-timeout` P3, the first hosted run (2026-11-12).
