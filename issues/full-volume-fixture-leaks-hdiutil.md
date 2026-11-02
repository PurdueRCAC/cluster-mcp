---
status: unshaped
kind: test
appetite: small
lane: public
---

# A disk-image step that hangs outlives its test

## Problem

On macOS, `test_a_write_that_runs_out_of_room_keeps_the_file` (`tests/test_ssh_exec.py`) writes to a
filesystem that is really full: the `full_volume` fixture (`tests/test_ssh_exec.py:762`) creates a
4 MB HFS+ image with `hdiutil create`, attaches it, fills it to 8 or 32 KiB free, and detaches it
afterwards. Each `hdiutil` step goes through `_host` (`tests/test_ssh_exec.py:754-758`), which waits
with `proc.communicate(timeout=120)`. At that timeout `communicate` raises `TimeoutExpired` and
leaves the child running; `_host` neither kills it nor reaps it.

Observed on a developer Mac, 2026-10-31: `hdiutil create` stalled while its formatter
(`newfs_hfs`) wrote the new volume. The test failed at the timeout, and `hdiutil`, `newfs_hfs` and
the half-made device (`/dev/diskN`) stayed for about a day, until they were killed by hand. Why the
formatter stalled is not known; macOS's disk-image tools do so occasionally.

The same gap applies to the fixture's `attach` (a hung attach leaves an image half-attached) and to
its `detach -force` in `finally` (a hung detach leaves the volume mounted and the test's directory
in use). If `create` or `attach` fails, the fixture removes neither the image nor any device it made.

**Pre-existing:** yes, since the fixture landed in `safe-execution` (`fbd21e8`, 2026-10-23). It
runs only on macOS: the Linux CI runner takes the in-process path and never calls `hdiutil`.

## Why it was deferred

Found while closing out `capability-probe`'s housekeeping; it belongs to no open cycle. The fix is
confined to one test fixture.

## Outcome / vision

A test fixture's host tool that does not finish in time is stopped, and so is what it started, and
the fixture leaves no image attached and no device behind, however a step ends.

## Sketch of the acceptance criteria

- **R1** — WHEN a step of `full_volume` (`create`, `attach` or `detach`) exceeds its timeout, the
  step's process and what it started SHALL be stopped and reaped before the test fails, and the
  failure SHALL name the step.
- **R2** — WHEN `create` or `attach` fails or times out, the fixture SHALL detach any device the step
  made and remove the image.
- **R3** — A test SHALL pin R1 and R2 without a real hang (a stand-in for `hdiutil` that hangs, on any
  platform).

## Notes

- Related: [`timeout-process-cleanup.md`](timeout-process-cleanup.md) (the server's own timed-out
  commands; a different trigger), [`sandbox-dirs-left-on-kill.md`](sandbox-dirs-left-on-kill.md)
  (another leftover the test harness leaves on the host).
- Found by: the foreman, 2026-11-01, after the stalled processes were killed.
