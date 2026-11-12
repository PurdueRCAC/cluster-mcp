---
status: unshaped
kind: test
appetite: small
lane: public
---

# The launch's path-function reset survives three mutants on Linux

## Problem

The launch prologue clears functions named by a command path, then leaves POSIX mode. It runs
`set +euxvTkPm +o errtrace +o posix; unset -f /bin/cat /bin/date /bin/sleep; ...`
(`core/executor/launch.py:184`, after the `POSIXLY_CORRECT=y; ...` line at `:183`). Three mutation
cases break that reset. The hosted Linux runner lets all three survive; on a macOS development host,
each is killed.

- `tpc-paths-not-functions`: `unset -f /bin/...` becomes `unset /bin/...`. Shard 39 of 78. Both
  `tests/test_timeout_stop.py::test_a_profile_cannot_cut_the_watchdogs_wait_short[local]` and
  `[delegate]` passed.
- `tpc-paths-unset-in-posix-mode`: the path `unset -f` moves into the POSIX-mode line, before
  `+o posix`. Shard 41 of 78. `[local]` and `[delegate]` passed.
- `tpc-posix-kept`: `+o posix` is dropped, so the shell stays in POSIX mode. Shard 47 of 78.
  `[local]` passed.

The first dispatched mutation run (run `43255195424` at `aff08bd`, 2026-11-12, by
`mutants-workflow-timeout`) reported each one `FAILED` with "the mutant survived: every target
passed". Run alone on macOS at the same commit (`uv run python tests/mutants.py CASE`), each is
killed: every target fails with "did not complete with its output".

The row (`tests/test_timeout_stop.py:724`) has a profile define functions named `/bin/cat`,
`/bin/date` and `/bin/sleep` that would cut the watchdog's wait short. On the runner those shadows
evidently never bite, mutated or not.

**Likely cause (unverified):** macOS's `/bin/bash` is 3.2; Ubuntu 24.04's is 5.2. They differ in
how POSIX mode treats a function whose name is a path:
- whether such a name can be defined;
- whether such a name can be unset;
- whether it shadows the command.

On bash 5.2 the shadowing functions may not take effect at all, which would make the three mutants
equivalent there. On Ubuntu `/bin` is also a link to `/usr/bin`, which may matter to the row's
shadows.

## Why it was deferred

The cycle that found it, `mutants-workflow-timeout`, has a non-goal: it changes no case, target or
`why`. The maintainer ruled under its GOAL Q3 that the seven Linux-only survivors are seeded in four
groups. This seed is one of them.

These survivors are **pre-existing**: the cases and the row are older than the cycle.

## Outcome / vision

There are two acceptable ends. Either:
- each of the three mutants is killed on the hosted Linux runner; or
- the cycle shows the reset has no effect on bash 5.2 and records the mutant as equivalent there,
  with the reason.

Either way, the launch's behaviour is unchanged.

Possible fix shapes, for shaping to choose between:
- make the row's profile shadow the commands in a way bash 5.2 honours, if one exists;
- add a pin that doesn't depend on the bash version, e.g. a row that reads the prologue's text for
  the reset and its place after `+o posix`;
- add a Linux single-case probe that runs these cases in CI before a dispatch.

## Sketch of the acceptance criteria

- **R1** — WHEN `tpc-paths-not-functions`, `tpc-paths-unset-in-posix-mode` or `tpc-posix-kept` is
  applied on the hosted Linux runner, at least one of its target rows SHALL fail with its `why`,
  unless the cycle rules it equivalent on that platform with the reason recorded.
- **R2** — WHEN none is applied, the rows SHALL pass on Linux and macOS as they do today.

## Notes

- Related: `issues/mutants-linux-bashrc-norc.md`, `issues/mutants-linux-fd-59.md`,
  `issues/mutants-linux-transfer-cause.md`; `spec/mutants-workflow-timeout/` (TECH Amendments,
  2026-11-12, P3 run 1); `issues/timeout-stop-limits.md` (the timeout stop's recorded limits).
- Found by: `mutants-workflow-timeout` P3, the first hosted run (2026-11-12).
