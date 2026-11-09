# 01 — Executed probes: `hdiutil`, process groups, and the stand-in

Lean path (appetite small, kind test, no high-blast-radius path), so no fan-out: these are the
planner's own probes, run 2026-11-09 on a developer Mac (macOS 27.0.1, Apple silicon), each in a
fresh `mktemp -d` lab under `$TMPDIR`, deleted after. Every runtime claim `PLAN.md` makes about
`hdiutil`, signals or process groups is one of these, or is marked unproven.

## P-a · `hdiutil create`'s processes stay in its process group

`hdiutil create -size 4m -fs HFS+ …` started with `start_new_session=True` (so it leads group G),
`ps -A -o pid=,ppid=,pgid=,stat=,args=` polled every 2 ms:

```
19098 19096 19098 Rs   hdiutil create -size 4m -fs HFS+ -volname probe1 …/p1.dmg
19105 19098 19098 S    …/DiskImages.framework/Resources/diskimages-helper -uuid 3F38…
19107 19105 19098 S    …/diskimages-helper -uuid 3F38… -post-exec 4
```

The helpers `create` starts are in its group (pgid 19098). The system daemon `hdiejectd` (ppid 1,
its own group) is not. `newfs_hfs` was not caught at 2 ms polling; the formatter runs under the
`-post-exec` helper. Took 1.0 s, exit 0.

## P-b · A hung `create`, killed by group, leaves no device and an image file

The `-post-exec` helper was SIGSTOPped as soon as it appeared (a stand-in for the stalled
formatter). Two seconds later: `hdiutil` itself had exited (a zombie in G, unreaped), the stopped
helper was reparented to pid 1 **but kept pgid G**; `hdiutil info -plist` listed the image by the
path as given (`…/fvprobe.JGyzgP/p2.dmg` with a `//` as passed, not resolved) with
`/dev/disk4` and `/dev/disk4s1`; the image file existed. `os.killpg(G, SIGKILL)` then `wait()`:
the group was empty (ESRCH) 15 ms later; one second after, `hdiutil info` listed **no** image (the
device went with its helper). The image file stayed.

So: a group KILL reaches what `create` started, even a helper reparented to launchd; and the
cleanup must still remove the image file, and must not assume no device (a device can outlive the
kill on another macOS, or for `attach`: P-d).

## P-c · Zombies and the group signal

A group holding only an unreaped zombie: `os.killpg(G, 0)` raises **`PermissionError` (EPERM) on
macOS**, not ESRCH. So the stop suppresses `PermissionError` as well as `ProcessLookupError` on its
KILL, and the wait does not use `killpg(G, 0)` as its liveness test: it lists the group with
`ps -A -ww -o pid=,pgid=,stat=,args=` and ignores state `Z` (portable across the zombie semantics of
both kernels; `-ww` keeps the command whole). Unproven on Linux here (no Linux host in reach of a
plan step); the rows run there on CI.

## P-d · `attach`, `detach` and their failures

- A successful `attach` returns with its group **empty**: the device is served outside the
  processes it started (the GOAL's non-goal about the system helper holds for a finished attach).
  `hdiutil info -plist` names the image path as given and lists `/dev/disk4`, `/dev/disk4s1`.
- `detach -force <mount>`: exit 0, `"disk4" ejected.`. A second one: exit 1,
  `hdiutil: detach failed - No such file or directory`. `detach -force /dev/disk99`: the same.
- `attach` of a missing image: exit 1, `hdiutil: attach failed - No such file or directory`.
- `create` over an existing file: exit 1, `hdiutil: create failed - File exists`.
- Every verb prints a deprecation warning on standard error first (`'hdiutil create -size
  -volname ...' is deprecated. Please use 'diskutil image create …'`); the failure line is last, so
  a tail of standard error carries it.

**Not probed: a hung real `attach`.** The probe that stops `attach`'s helper and kills its group was
refused by the planning host's permission policy; it was not retried. The plan makes no claim about
what a killed real `attach` leaves; the cleanup handles either outcome (it asks `hdiutil info`).

## P-e · The stand-in reaches its hang in milliseconds

The prototype stand-in (`python -I tests/hdiutil_standin.py STATE create …`, planned to write the
image, record a device, fork a child and hang), 20 starts: time from launch until its child is
recorded, min 22 ms, median 23 ms, max 27 ms. The short bound (T3) must exceed this with a loaded
runner's slack; at 1 s the margin is about 40×.

## P-f · The prototype rows, measured (first draft; the final figures are in PLAN §3)

Prototype at `$REPO/.worktrees/full-volume-fixture-leaks-hdiutil-proto` (removed before the plan's
report), one era, this Mac: the 15 stand-in rows, the survivor row and the figures row together,
`--durations=0`: hanging rows 1.12–1.19 s each (the cleanup-detach row, two hangs, 2.16 s), the
survivor row 1.57 s, every other row 0.11–0.17 s; 17 passed in 10.9 s wall. With the three real
`out_of_room` rows (real `hdiutil`): 20 passed in 14.4 s, and `hdiutil info` listed nothing after.
