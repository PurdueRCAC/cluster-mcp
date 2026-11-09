# GOAL — A disk-image step that hangs or fails is stopped, and the full-volume fixture leaves nothing behind

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** full-volume-fixture-leaks-hdiutil
- **kind:** test
- **appetite:** small

## Problem

On macOS, `test_a_write_that_runs_out_of_room_keeps_the_file[8k-free|32k-free]`
(`tests/test_ssh_exec.py`) writes to a filesystem that is really full. Its `full_volume` fixture
(`tests/test_ssh_exec.py:782-799`) creates a 4 MB HFS+ image with `hdiutil create`, attaches it at a
directory under the test's `tmp_path`, fills it to 8 or 32 KiB free, and in `finally` detaches it
with `hdiutil detach -force` and removes the image. Each of the three `hdiutil` steps goes through
`_host` (`tests/test_ssh_exec.py:775-779`), which waits with `proc.communicate(timeout=120)`. At that
timeout `communicate` raises `TimeoutExpired` and leaves the child running: `_host` neither stops
nor reaps it, and nothing it started is stopped either.

Observed on a developer Mac, 2026-10-31: `hdiutil create` stalled while its formatter
(`newfs_hfs`) wrote the new volume. The test failed at the timeout, and `hdiutil`, `newfs_hfs` and
the half-made device (`/dev/diskN`) stayed for about a day, until they were killed by hand. Why the
formatter stalled is not known; macOS's disk-image tools do so occasionally.

The same gap applies to `attach` (a hung attach can leave the image half-attached) and to the
`detach -force` in `finally` (a hung detach leaves the volume mounted and the test's directory in
use). Beyond timeouts, a `create` or `attach` that fails outright leaves the image file and any
device it made, because the fixture's `try` starts only after `attach` succeeds; and a `detach`
that fails raises before `image.unlink()`, so the image stays too.

**Pre-existing:** yes, since the fixture landed in `safe-execution` (`fbd21e8`, 2026-10-23). It runs
only on macOS: on Linux the test takes the in-process ENOSPC path and never calls `hdiutil`, so CI
has never exercised any of this.

**Drift since the seed:** the seed cites `_host` at `:754-758` and `full_volume` at `:762`; on
`origin/develop` (`0bfacae`) they are at `:775-779` and `:782-799`. The code at those lines is as the
seed describes.

## Outcome / vision

However one of the fixture's `hdiutil` steps ends (on time, failed, or hung), nothing it started is
still running when the test fails, no device backed by the test's image stays attached, and the
image file is gone, except where a `detach` cannot finish (R4), when the failure names what was
left. The test's failure says which step went wrong and how. A test proves this on every platform
the suite runs on, with a stand-in for `hdiutil`, without a real hang and without a real disk
image.

## Acceptance criteria (the contract)

The fixture's **steps** are its three `hdiutil` invocations: `create`, `attach` and `detach`
(`detach` also when it is run as cleanup by R3). A step **fails** when it exits non-zero, and
**hangs** when it runs past its bound (`[NEEDS CLARIFICATION: T1]`).

- **R1** — WHEN a step hangs, the fixture SHALL stop that step's process and every process it
  started that is still running, and wait for them to exit, before the test fails. IF a stopped
  process has not exited within the stop's wait (`[NEEDS CLARIFICATION: T2]`), THEN the fixture SHALL
  stop waiting, and the failure SHALL name each such process (its pid and command).
- **R2** — WHEN a step fails or hangs, the test's failure SHALL name the step (`create`, `attach` or
  `detach`) and how it ended: that it ran past its bound, naming the bound, or the exit status it
  returned with the tail of its standard error.
- **R3** — IF `create` or `attach` fails or hangs, THEN before the test fails the fixture SHALL
  detach every device backed by its image that is still attached and remove the image file, if
  either exists. A `create` or `attach` that made no device and no image SHALL still end in R2's
  failure for that step, not in an error from the cleanup. The cleanup's own `detach` is a step: R1
  and R2 hold for it.
- **R4** — IF `detach` fails or hangs, THEN after R1's stop the fixture SHALL
  `[NEEDS CLARIFICATION: D1 — what the fixture does about the volume a detach could not detach]`,
  and the failure SHALL name the mount point and the image path left behind.
- **R5** — WHEN the test body fails (the fill, its assertion, or the test's own assertions inside
  the fixture's `with`) and the fixture's `detach` then also fails or hangs, the test's report SHALL
  carry both failures, the body's first.
- **R6** — WHEN every step succeeds, the fixture SHALL behave as today: the volume attached at the
  directory asked for, filled to exactly the free bytes asked for, then detached and its image
  removed. `test_a_write_that_runs_out_of_room_keeps_the_file[8k-free|32k-free|edquot]` SHALL keep
  their rows and their outcomes on macOS (a real volume) and on Linux (the in-process path).
- **R7** — A test SHALL pin R1–R6 with a stand-in for `hdiutil`, with no real disk image, on every
  platform the suite runs on (Linux CI and macOS), and with no skip (`AGENTS.md` § Testing: the
  suite's only skips are `need_shell` and `need_git`). A hanging step runs against a short bound
  (`[NEEDS CLARIFICATION: T3]`), never the real one. One row for each of these cases:
  1. `create` hangs, having made no device; its stand-in has started a child that hangs too.
  2. `create` hangs after making a device from the image; its stand-in has started a child that
     hangs too (the case observed: `hdiutil` and its formatter).
  3. `create` fails, having made no device and no image file.
  4. `create` fails after writing the image file and making a device from it.
  5. `attach` hangs, having made no device; its stand-in has started a child that hangs too.
  6. `attach` hangs after making a device from the image; its stand-in has started a child that
     hangs too.
  7. `attach` fails, having made no device.
  8. `attach` fails after making a device from the image.
  9. `detach` hangs after the body succeeds; its stand-in has started a child that hangs too.
  10. `detach` fails after the body succeeds.
  11. The body fails and then `detach` fails (R5).
  12. The R3 cleanup's own `detach` hangs (after case 6's `attach`).
  13. Every step succeeds (R6's control): the stand-in's device is detached and the image removed.

  Each row SHALL assert, when the fixture has returned or raised: that no stand-in process or child
  it started is still running; whether a device the stand-in made is still attached, and whether
  the image file exists, against R3 and R4; and that the failure's text names the step and how it
  ended (R2), and for case 11 that both failures are reported in order (R5).

## Non-goals (no-gos)

- Why `hdiutil` or `newfs_hfs` stalls, and any retry of `create` or `attach` to work around it.
- Changing the volume (size, filesystem, fill), the test's rows, or the Linux in-process ENOSPC and
  EDQUOT paths.
- The server's own timeout stop (`spec/timeout-process-cleanup/`, `executor/launch.py`): no source
  change under `packages/`.
- A process a step hands to a system service outside the processes it started (macOS's disk-image
  helper, which serves an attached device): the fixture reaches it by detaching the device (R3,
  R4), not by signal.
- Leftovers from earlier runs (an image or device from before this change), and the directories
  pytest's `tmp_path` cleanup already removes.
- Directories `bin/sandbox.sh` leaves when killed (`issues/sandbox-dirs-left-on-kill.md`, its own
  cycle).
- A case in `tests/mutants.py`: the runner plants only into the `cluster_mcp` namespace and
  `REPO_FILES`, and this fixture lives in `tests/`.

## Clarifications

None resolved yet. Open, each blocking `code-plan`:

- `[NEEDS CLARIFICATION: T1 — the bound on each real hdiutil step.]` Before: 120 s per step
  (`communicate(timeout=120)`); a hang fails the test after 120 s and leaves the step running. After,
  the worst case for a hung `create` or `attach` is the bound, plus R1's wait (T2), plus the R3
  cleanup `detach` (up to one more bound and wait); for a hung `detach`, the bound plus the wait (plus
  whatever D1 adds). Options: (a) keep 120 s for every step; (b) a shorter bound for every step
  (e.g. 60 s); (c) a bound per step (e.g. `create` longer than `attach` and `detach`).
- `[NEEDS CLARIFICATION: T2 — how R1 stops a hung step, and how long it waits for the stopped
  processes to exit.]` Before: no stop and no wait. Options: (a) force-stop at once (KILL, as the
  server's own timeout stop does), wait up to 5 s, then report survivors; (b) ask first (TERM), force
  after a 2 s grace, then wait up to 5 s; (c) force-stop and wait without a bound (a process stuck in
  the kernel would hang the test, the failure this cycle removes).
- `[NEEDS CLARIFICATION: T3 — the short bound the R7 test runs a hanging stand-in against.]`
  Before: no such test. After: R7 has six hanging rows (1, 2, 5, 6, 9, 12; row 12 hangs twice, so
  seven waits), each costing about the bound plus T2's stop, in both protocol eras, on whichever CI
  suite job the test lands in (budget 10 min per job; worst baseline 7:34, `suite-modern-3`).
  Options: (a) 0.5 s (about 4–5 s per era); (b) 1 s (about 8 s per era); (c) 2 s (about 15 s per era).
- `[NEEDS CLARIFICATION: D1 — R4: a detach that failed or hung.]` Options: (a) report only: the
  volume stays attached, the image file is kept so `hdiutil info` still names it, and the failure
  names both; (b) one more bounded `detach -force` after the stop, then (a) if it also fails, adding
  up to one bound and wait (T1, T2) to that worst case; (c) as (b), then remove the image file even
  when the volume is still attached.

## Related materials

- Seed: [`issues/full-volume-fixture-leaks-hdiutil.md`](../../issues/full-volume-fixture-leaks-hdiutil.md)
  (status `unshaped` when promoted); its `ROADMAP.md` entry, "A disk-image step that hangs outlives
  its test".
- Source: `tests/test_ssh_exec.py` (`_host`, `full_volume`,
  `test_a_write_that_runs_out_of_room_keeps_the_file`); `tests/conftest.py` (`REAL_POPEN`).
- `AGENTS.md` § Testing: the paragraph describing the full-volume rows, and the skip rule R7 obeys.
- Prior art: [`spec/timeout-process-cleanup/`](../timeout-process-cleanup/) (the server's stop of a
  timed-out command and what it started; a different trigger);
  [`spec/safe-execution/`](../safe-execution/) (where the fixture landed, `fbd21e8`).
- Sibling: [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md)
  (another leftover the test harness leaves on the host).
