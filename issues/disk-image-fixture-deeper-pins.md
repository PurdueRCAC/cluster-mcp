---
status: unshaped
kind: test
appetite: small
lane: public
---

# The disk-image fixture's stop, cleanup and report are pinned one layer deep

> **Candidate, not a contract.** This file records deferred work in enough detail that a future
> session does not have to re-derive it. It is **not** graded by `code-review` and must never be
> copied into `spec/{slug}/GOAL.md` verbatim — `code <repo> feature` promotes it, and that is where
> appetite, non-goals and the R-IDs get negotiated with a human. The `status:` field above is the
> guard.

## Problem

The full-volume fixture in `tests/test_ssh_exec.py` (`_processes`, `_group`, `_stop`, `_step`,
`_clean_up`, `attached_image`) stops a hung or failed `hdiutil` step with its process group, cleans
up after a failed `create` or `attach`, and names what a failed `detach` leaves. A stand-in for
`hdiutil` (`tests/hdiutil_standin.py`) pins each of those decisions with a row. Some decisions are
pinned only as far as the stand-in's inputs reach: a mutant that changes them leaves every row green,
although the change is not equivalent on inputs the real tool or the host can produce.

From review cycle 1 of `full-volume-fixture-leaks-hdiutil` (32 hand-made mutants: 25 killed, 7
survived; one survivor, the body-failure carve-out, was a finding and is fixed and pinned in that
cycle; these six are the rest):

1. **The wait after the stop polls the whole group** (`_stop`). With the poll removed, so only the
   step's own process is waited on, every row passes: each process a row starts dies at the KILL,
   so one look finds none. A member slow to exit after KILL (a formatter stuck in disk I/O) would be
   named as still running at once instead of waited on for `STOP_WAIT`.
2. **The cleanup detaches every device made from the image** (`_clean_up`). Stopping after the first
   device it detaches passes every row: no row makes two devices from one image. With two, one
   stays attached and the image is removed with nothing reported.
3. **A failure names the tail of the step's standard error** (`_step`). The head instead of the tail
   passes: the stand-in's standard error is shorter than the 400 characters kept.
4. **A zombie in the stopped group is not a survivor** (`_group`). Counting zombies passes: a
   zombie in the group is reaped at once, so none is ever seen.
5. **A KILL refused with EPERM is not an error** (`_stop`, the `PermissionError` the `killpg` call
   suppresses). Raising it passes: the race (macOS answers EPERM for a group holding only zombies)
   is never reached.
6. **A `ps` listing that does not show this process is refused** (`_processes`). Dropping the check
   passes: `ps` answers in the parsed shape on both platforms, so the refusal is never reached.

The cycle's remediation sweep (`spec/full-volume-fixture-leaks-hdiutil/remediation/F2-fixture-sweep.py`)
reproduced all six as cases, and found these survivors of the same kind besides:

7. **The refusal in item 6 raises** (`_processes`): returning the listing in its place passes, for
   item 6's reason.
8. **A stopped step's pipes are closed** (`_stop`). Leaving them open passes: no row counts open
   descriptors, and the pipes close when the `Popen` is collected.
9. **An `info` answer that is a plist but not a dictionary keeps the image** (`_clean_up`). Dropping
   the type check passes: no row answers with, say, a top-level array, so the listing is never read
   as one.
10. **The stop reaps the step's own process** (`_stop`, the bounded wait on it). Dropping that wait
    passes: the poll that follows reads the process as gone once it is a zombie, so only its reaping
    is late (until the `Popen` is collected), and no row looks for zombies (item 4's class).
11. **An image entry with no device is skipped** (`_clean_up`). Dropping the skip passes: every entry
    the stand-in lists carries a `dev-entry`, so the cleanup never meets one without.

Pre-existing in the sense that none of the eleven is a regression: each decision is correct today,
graded by reading the code; what is missing is a row whose input reaches it.

## Why it was deferred

Each is a deeper layer of a class a row already pins, or a defensive branch no reachable input
exercises, which is the review rubric's coverage line: seeded, not a finding. Pinning them needs new
stand-in inputs (two devices from one image, a long standard error, an `info` answer of the wrong
shape, an entry with no device) or injected host behaviour (a group member slow to exit, an EPERM
from `killpg`, a `ps` answer without this process), each a design question of its own, outside the
cycle's GOAL.

## Outcome / vision

Every decision of the fixture is pinned by a row whose input reaches it, so no mutant of a reachable
behaviour survives; the ones that may stay unpinned by design (items 4, 8 and 10) are recorded as
such.

## Sketch of the acceptance criteria

Draft R-IDs, to be firmed up at promotion.

- **R1** — WHEN a member of a stopped step's group exits a moment after the KILL, the fixture SHALL
  wait for it and SHALL NOT name it as still running.
- **R2** — WHEN a failed `create` or `attach` leaves two devices made from its image, the cleanup
  SHALL detach both before it removes the image.
- **R3** — WHEN a failing step's standard error is longer than the tail kept, the failure SHALL carry
  the end of it, the tool's failure line included.
- **R4** — WHEN `killpg` answers EPERM, the stop SHALL go on to its wait, and WHEN `ps` answers
  without this process, or `info` answers with a plist that is not a dictionary or with an image
  entry that has no device, the fixture SHALL refuse or skip it as it does today; each pinned by a
  row that injects it.
- **R5** — A rule for items 4, 8 and 10: either a row that reaches them, or a recorded reason each
  is left unpinned.

## Notes

- Related: `spec/full-volume-fixture-leaks-hdiutil/` (REVIEW.md, cycle 1, "Coverage observations";
  the remediation sweep and its record in TECH.md); `issues/sandbox-dirs-left-on-kill.md` (another
  leftover of the same harness).
- Found by: `full-volume-fixture-leaks-hdiutil` review cycle 1 (items 1–6) and its remediation sweep
  (items 7–11).
