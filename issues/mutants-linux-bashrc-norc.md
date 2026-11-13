---
status: unshaped
kind: test
appetite: small
lane: public
---

# Dropping `--norc` from a local stage survives the mutation run on Linux

## Problem

Two mutation cases drop `--norc` from a `local` stage, and the hosted Linux runner lets both
survive. On a macOS development host, each is killed.

- `script-reads-bashrc` takes `{NORC}` out of `SCRIPT`'s
  `BASH_ENV= ENV= exec {BASH} {NORC} -c -- {script}` (`core/executor/launch.py:247`). Its target,
  `tests/test_launch.py::test_no_stage_reads_a_startup_file_under_sshd[local-script]`, passed on
  the runner, so the mutant survived.
- `fixed-script-reads-bashrc` makes `fixed_argv` return `[BASH, '--posix', '-c', ...]` instead of
  `[*POSIX_STAGE, '-c', ...]` (`core/executor/launch.py:524`), which drops `--norc`. Its target,
  `[local-fixed-script]` of the same row, passed on the runner, so the mutant survived.

The first dispatched mutation run (run `43255195424` at `aff08bd`, 2026-11-12, by
`mutants-workflow-timeout`) reported both cases `FAILED`:

- `script-reads-bashrc` in shard 14 of 78;
- `fixed-script-reads-bashrc` in shard 57 of 78.

Each was "the mutant survived: every target passed". Run alone on macOS at the same commit
(`uv run python tests/mutants.py CASE`), each is killed: its target fails with
"a stage read a startup file".

The row (`tests/test_launch.py:1423`) sets `SSH_CLIENT` and `SSH_CONNECTION` (`SSHD_ENV`), writes a
`~/.bashrc` that records each read, and counts the reads. On the runner, a `bash -c` without
`--norc` did not read `~/.bashrc`, so the row cannot tell the stage from its mutant there.

**Likely cause (unverified):** a non-interactive bash reads `~/.bashrc` under sshd only by a
heuristic. It depends on:
- whether bash was built with `SSH_SOURCE_BASHRC`;
- `SHLVL` being below 2;
- in newer bash, whether stdin is a socket.

macOS's `/bin/bash` is 3.2; Ubuntu 24.04's is 5.2. The row's emulation of sshd (environment
variables only) may meet that heuristic on one bash and not on the other.

## Why it was deferred

The cycle that found it, `mutants-workflow-timeout`, has a non-goal: it changes no case, target or
`why`. Its job was to make the hosted run finish and report every case. The maintainer ruled under
its GOAL Q3 that the seven Linux-only survivors are seeded in four groups. This seed is one of them.

These survivors are **pre-existing**: the cases and the row are older than the cycle. They were
invisible before only because the hosted run never finished.

## Outcome / vision

On the hosted Linux runner, each of the two mutants is killed by a row, as it is on macOS. That
means the pin for "no stage reads a startup file" holds whatever the bash version.

Possible fix shapes, for shaping to choose between:
- make the row emulate sshd fully on both platforms: stdin a socket, `SHLVL` controlled;
- add a pin that doesn't depend on bash's sshd heuristic, e.g. a row asserting each `local` stage's
  argv or script carries `--norc` (or `POSIX_STAGE`);
- add a Linux single-case probe that runs these cases in CI before a dispatch.

## Sketch of the acceptance criteria

- **R1** — WHEN `script-reads-bashrc` or `fixed-script-reads-bashrc` is applied on the hosted Linux
  runner, at least one of its target rows SHALL fail with "a stage read a startup file".
- **R2** — WHEN neither is applied, the rows SHALL pass on Linux and macOS as they do today.

## Notes

- Related: `issues/mutants-linux-posix-paths.md`, `issues/mutants-linux-fd-59.md`,
  `issues/mutants-linux-transfer-cause.md`: the other Linux-only survivors of the same run.
  `spec/mutants-workflow-timeout/` (TECH Amendments, 2026-11-12, P3 run 1) holds the run's figures.
- Found by: `mutants-workflow-timeout` P3, the first hosted run (2026-11-12).
