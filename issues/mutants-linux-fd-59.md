---
status: unshaped
kind: test
appetite: small
lane: public
---

# Renumbering the watchdog's descriptor to 59 survives on Linux

## Problem

The watchdog holds descriptor 46: `exec 46>| >(...)` and `printf '\n' >&46`
(`core/executor/launch.py:214-216`), released at `:239` and closed in the subshell at `:259`. The
mutation case `tpc-fd-59` renumbers it to 59 everywhere it is named.

Descriptor 59 is the one the sentinel line later points at the caller's stderr
(`exec ... 2>&59 ... 59>&-`, `:189`). So the watchdog should lose its pipe and stop nothing. Its
targets are `tests/test_timeout_stop.py::test_a_timed_out_command_is_stopped[delegate-tree]` and
`[ssh-bash-ignores-holding]`, with the `why` "still running".

The first dispatched mutation run (run `43255195424` at `aff08bd`, 2026-11-12, by
`mutants-workflow-timeout`) reported the case `FAILED` in shard 17 of 78:
- `[delegate-tree]` passed, so the mutant survived it;
- `[ssh-bash-ignores-holding]` failed, but for the wrong reason: no "still running" in the failure.

Run alone on macOS at the same commit (`uv run python tests/mutants.py tpc-fd-59`), it is killed:
both targets fail with "still running".

- 2026-11-12: run 2 (`43260825655`) repeated run 1's verdicts. In run 3 (`43265827418`, shard 17)
  both targets passed, `[ssh-bash-ignores-holding]` included.

**Likely cause (unverified):** on the Linux runner, under bash 5.2, the program's descriptor
handling differs from macOS's bash 3.2, so the stop still works through another path, or fails
differently. Possible differences:
- the order in which the sentinel's redirection takes effect against the watchdog's process
  substitution;
- the descriptors the delegate inherits.

The `[ssh-bash-ignores-holding]` failure text from the run is the first thing to read.

## Why it was deferred

The cycle that found it, `mutants-workflow-timeout`, has a non-goal: it changes no case, target or
`why`. The maintainer ruled under its GOAL Q3 that the seven Linux-only survivors are seeded in four
groups. This seed is one of them.

The survivor is **pre-existing**: the case and the rows are older than the cycle.

## Outcome / vision

There are two acceptable ends. Either:
- `tpc-fd-59` is killed for its reason on the hosted Linux runner; or
- the cycle shows why descriptor 59 is harmless there and records it, with the reason.

Either way, the launch's behaviour is unchanged.

Possible fix shapes, for shaping to choose between:
- a row whose stop observably depends on the watchdog's descriptor on both platforms;
- a pin that doesn't depend on the bash version, e.g. the launch checker refusing a watchdog
  descriptor the sentinel line reuses;
- a Linux single-case probe that runs the case in CI before a dispatch.

## Sketch of the acceptance criteria

- **R1** — WHEN `tpc-fd-59` is applied on the hosted Linux runner, each of its target rows SHALL fail
  with "still running", unless the cycle rules it equivalent on that platform with the reason
  recorded.
- **R2** — WHEN it is not applied, the rows SHALL pass on Linux and macOS as they do today.

## Notes

- Related: `issues/mutants-linux-bashrc-norc.md`, `issues/mutants-linux-posix-paths.md`,
  `issues/mutants-linux-transfer-cause.md`; `spec/mutants-workflow-timeout/` (TECH Amendments,
  2026-11-12, P3 run 1).
- Found by: `mutants-workflow-timeout` P3, the first hosted run (2026-11-12).
