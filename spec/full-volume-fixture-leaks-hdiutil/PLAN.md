# PLAN — A disk-image step that hangs or fails is stopped, and the full-volume fixture leaves nothing behind

> **Status:** Signed at the PLAN/TECH gate, 2026-11-09 (rulings in [`TECH.md`](TECH.md) → Amendments) ·
> **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/01-probes.md`](research/01-probes.md) (executed probes; lean path, no fan-out). Every
> design element traces to a GOAL R-ID.

## 1. Summary

`full_volume` splits in two: `attached_image`, the `hdiutil` lifecycle (create, attach, detach, and
a cleanup that asks `hdiutil info` which devices its image backs), and `full_volume` itself, which
fills the attached volume inside it, as today. Every `hdiutil` invocation runs through one helper,
`_step`, that starts it as the leader of a new process group, waits up to its bound, and on a hang
**or** a non-zero exit KILLs the whole group at once, waits up to `STOP_WAIT` for the group to empty,
and returns a failure text naming the verb, how it ended, and anything still running. The lifecycle
composes those texts, in the order they happened, into one `HostFailure`, chained from the body's
own exception when the body failed first. `attached_image` takes the `hdiutil` argv prefix and
per-verb bounds, so a stand-in (`tests/hdiutil_standin.py`, a Python script that forks and never
launches a program) plays `hdiutil` in seventeen integration rows and a survivor test that run on Linux and macOS alike.
Test-only, one module plus one helper script, three phases: it fits `small`.

## 2. Design

All in `tests/test_ssh_exec.py` (the fixture's section, today `:775-799`) and a new
`tests/hdiutil_standin.py`. No file under `packages/`, `bin/` or `.github/` changes.

### The figures (module constants)

| Name | Value | Meaning |
|---|---|---|
| `HDIUTIL_BOUND` | `120` | each real verb's bound, s (GOAL T1, unchanged) |
| `STOP_WAIT` | `5` (**maintainer's figure**, signed 2026-11-09) | the wait after KILL for the group to empty, s (GOAL T2) |
| `STOP_SIGNAL` | `signal.SIGKILL` | the stop's one signal: KILL at once, no TERM first (GOAL T2 (a)) |
| `HDIUTIL_VERBS` | `create`, `attach`, `detach`, `info` | the verbs the fixture runs; `_bounds(overrides)` maps each to `HDIUTIL_BOUND` unless the caller names another |
| `SHORT_BOUND` (rows) | `1` (**maintainer's figure**, signed 2026-11-09) | the bound a hanging stand-in verb meets (GOAL T3) |
| `EASY_BOUND` (rows) | `30` | the bound every non-hanging stand-in verb gets: never met (a stand-in verb takes ~25 ms) |
| `ROW_LIMIT` (rows) | `10` | a row's whole run, at most (two hangs plus stops measured at 2.2 s) |

`STOP_WAIT` and `STOP_SIGNAL` are read when a step is stopped, so the survivor row can patch them.

### `_step(hdiutil, verb, bound, *args) -> (failure | None, stdout)`

`REAL_POPEN([*hdiutil, verb, *args], stdout=PIPE, stderr=PIPE, start_new_session=True)` (the fence
bypass `_host` uses today). The rows' `hdiutil` argv starts with `bin/sandbox.sh`, so every stand-in
step goes through it (amended at the PLAN/TECH gate: every process an integration test launches goes
through `bin/sandbox.sh`); the real `hdiutil` argv, `('hdiutil',)`, does not, as `_host`'s does not
today, a gap seeded elsewhere. The group the stop KILLs is then `bin/sandbox.sh`'s, which holds the
stand-in and what it started. `communicate(timeout=bound)`:

- **Hang** (`TimeoutExpired`): `_stop`, then `"{verb}: ran past its bound of {bound} s and was stopped"`
  plus `_stop`'s survivor text (R1, R2).
- **Failure** (exit ≠ 0): `_stop` too (the Outcome: nothing a step started still runs, however it
  ends; deviation row 2), then `"{verb}: exited with status {rc}: {last 400 chars of stderr}"` plus
  the survivor text (R2). P-d: `hdiutil` prints a deprecation warning first and its failure line
  last, so the tail carries the cause.
- **Success**: nothing is stopped (R6: a finished `attach` leaves its group empty, and its device is
  served outside it, P-d).

### `_stop(proc) -> str`

`os.killpg(proc.pid, STOP_SIGNAL)`, suppressing `ProcessLookupError` and `PermissionError` (macOS
answers EPERM for a group of zombies only, P-c); a deadline `STOP_WAIT` from now; `proc.wait` up to
it (reaps the step); close its pipes; then poll `_group(pgid)` every 50 ms until it is empty or the
deadline passes. Returns `""` or `"; still running {STOP_WAIT} s after it was stopped: pid N (command), …"`
(R1's IF clause). `_group` reads `_processes()`, one listing of
`bin/sandbox.sh ps -A -ww -o pid= -o pgid= -o stat= -o args=` (through `bin/sandbox.sh`, as every
launch of the rows is; one `-o` per field: procps reads a comma list with
`=` headers by personality, and may give one column; BSD and procps both read this form), and keeps
the group's rows whose state is not `Z`. `_processes()` refuses a listing in which it cannot find
this process's own pid with a command, so a `ps` of another shape fails loudly instead of listing
nothing (adversarial finding 3). It is the liveness test, not `killpg(pgid, 0)`, because zombie
semantics differ by kernel (P-c). It reaches every process still in the group, including one launchd adopted
(P-b), and none that left it (`setsid`): GOAL's non-goal on the system helper.

### `attached_image(where, hdiutil=('hdiutil',), bounds=None)`, the lifecycle

1. `create` (image beside `where`, as today). On success, `where.mkdir()` and `attach`.
2. If either did not succeed: `raise HostFailure("\n".join([failure, *_clean_up(...)]))` (R2, R3).
3. Yield `where`.
4. Body raised (`except BaseException as body`): `detach -force where`; on success remove the image
   and re-raise the body's exception unchanged (R6); on failure
   `raise HostFailure(failure + "\n" + left) from body`, where `left` is `"the volume stays attached
   at {where}, and its image is kept at {image}"` (R4, R5: pytest prints the cause, the body's
   failure, first).
5. Body succeeded: `detach -force where`; on failure `raise HostFailure(failure + "\n" + left)` (R4);
   on success remove the image (R6). There is no second detach anywhere after a failed one (R4, D1).

### `_clean_up(hdiutil, bound, image) -> list[str]` (R3)

`info -plist` through `_step` (same bound and stop; deviation row 1). If it fails, or answers with
something `plistlib` cannot read (named `info: answered with no listing (…)`): return its failure
and `"the image is kept at {image}, and any device made from it stays attached"`, and remove
nothing (the devices are unknown). Otherwise, for each listed image whose `realpath(image-path) ==
realpath(image)` (`hdiutil` reports the path as handed over, `//` included, P-b), take the whole
disk (the shortest `dev-entry`; detaching it detaches its slices) and `detach -force` it. On that
detach's failure, stop there (R4: no further attempt) and return its failure and
`"{device} stays attached{ at <mount-point> | , not mounted}, and its image is kept at {image}"`,
the mount point read from the listing's `mount-point` (deviation row 6). With every device detached,
`image.unlink(missing_ok=True)` and return `[]`: a step that made no device and no image ends in its
own failure, never in an error from the cleanup (R3).

### `full_volume(where, free)`

`with attached_image(where): <the statvfs fill and its assertion, unchanged>; yield where`. The fill
and its assertion run in `attached_image`'s body, so R5 covers them. The test and its three rows are
unchanged (R6).

### The stand-in, `tests/hdiutil_standin.py`

`python -I hdiutil_standin.py STATE VERB ARGS…`. `STATE/plan.json` maps each verb to a **list** of
per-call plans (`end`: `ok` | `fail` | `hang`; `image`: write the image file; `device`: record a
device from the image, with the `-mountpoint` when given; `child`: fork a child first); a call past
the list's end is `ok`, so a retried `detach` would succeed and show. It appends `pid kind verb` to
`STATE/pids` for itself and each child, and keeps devices in `STATE/devices.json`, which the row
seeds with a **foreign** device (`/dev/standin1`, from a `vol.dmg` in another directory, mounted
elsewhere) that no cleanup may touch. A hanging verb and its child survive TERM and append
`term PID` to `pids` when one comes, so only KILL ends them and a TERM before it shows; a failing
verb's child drops its streams, so the verb's exit is seen while the child runs; `info` with
`garbled` exits 0 printing text that is not a plist. The plan's handling
of `image`, `device`, `child` and the ending is the same for every verb, `info` included. `info -plist` answers with `plistlib` in `hdiutil`'s
shape, each image named by a path with a `/./` in it (equal by `realpath`, not by string) and its
whole disk and slice, the slice carrying `mount-point` when attached. `detach` takes a whole device
or a mount point and fails as `hdiutil` does (P-d) on anything else. Every process it runs carries
`STATE` in its argv: the rows find leftovers by that text. It forks; it launches no program, so
`sandbox_violations` has nothing to flag in it, and it carries no skip and no spec id. It runs only
through `bin/sandbox.sh`: unless its working directory is the sandbox `CLUSTER_MCP_SANDBOX` names, it
exits 2 saying so, which fails every row. Each row sets `TMPDIR` to its `tmp_path`, so the directory
`bin/sandbox.sh` makes, and leaves when a stop KILLs it, goes with the row.

### The rows (`tests/test_ssh_exec.py`, after `test_a_write_that_runs_out_of_room_keeps_the_file`)

`test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running[<row>]` (`integration`), one
param per row of `DISK_IMAGE_ROWS`: the plan, whether the body raises, devices left, image left, and
the texts the report carries **in order**. Each row runs `attached_image(tmp_path / 'vol',
stand-in argv, bounds)` with `SHORT_BOUND` for each verb its plan hangs and `EASY_BOUND` for the
rest, then asserts (R7's four): no live process whose argv names `STATE` (`_processes()`, state not
`Z`); `devices.json`'s count of the row's own devices, and the foreign device still there; the image
file's existence; the texts in order in `traceback.format_exception` of what was raised (the pytest
report's form, so row 11's order is the report's), `__cause__` for row 11, the body's own
`AssertionError` unchained for `body-fails`; no `still running` in any row's report (no false
survivor); no `term` line in `pids` (KILL at once, never TERM first); the run within `ROW_LIMIT`;
and that the stand-in reached each hang it was planned to (its child is recorded), so a host too
loaded to start it inside the short bound fails with that said, never as a fixture fault. The texts
derive from `SHORT_BOUND` (`PAST = f'ran past its bound of {SHORT_BOUND} s'`). Every failing plan
starts a child (`FAILS`), so the stop after a failure is pinned for every verb. Teardown KILLs only
what `_left_running` still lists with `STATE` in its argv (a pid reused since is never touched).

| Row id | GOAL R7 case | Plan (per verb; every `fail` also starts a child) | Left: own devices · image | Report says, in order |
|---|---|---|---|---|
| `create-hangs` | 1 | create hang+child | 0 · no | create, bound |
| `create-hangs-with-device` | 2 | create hang+child+image+device | 0 · no | create, bound |
| `create-fails` | 3 | create fail | 0 · no | create, status 1, stderr tail |
| `create-fails-with-device` | 4 | create fail+image+device | 0 · no | create, status, tail |
| `attach-hangs` | 5 | create image; attach hang+child | 0 · no | attach, bound |
| `attach-hangs-with-device` | 6 | create image; attach hang+child+device | 0 · no | attach, bound |
| `attach-fails` | 7 | create image; attach fail | 0 · no | attach, status, tail |
| `attach-fails-with-device` | 8 | create image; attach fail+device | 0 · no | attach, status, tail |
| `detach-hangs` | 9 | ok, ok; detach [hang+child] | 1 · yes | detach, bound; mount point; image |
| `detach-fails` | 10 | ok, ok; detach [fail] | 1 · yes | detach, status, tail; mount point; image |
| `body-and-detach-fail` | 11 | ok, ok; body raises; detach [fail] | 1 · yes | the body's failure; detach; mount point; image |
| `cleanup-detach-hangs` | 12 | create image; attach hang+child+device; detach [hang+child] | 1 · yes | attach, bound; detach, bound; `/dev/standin2` at mount point; image |
| `every-step-succeeds` | 13 | ok, ok, ok | 0 · no | nothing raised; the body ran at `where` |
| `body-fails` | added (R6) | ok, ok, ok; body raises | 0 · no | the body's own failure, re-raised unchanged |
| `cleanup-detach-fails` | added (R3: R1, R2 hold for the cleanup's detach) | create image; attach fail+device; detach [fail] | 1 · yes | attach, status; detach, status; `/dev/standin2` at mount point; image |
| `info-fails-in-cleanup` | added | create image; attach fail+device; info [fail] | 1 · yes | attach; info, status; image kept |
| `info-answers-garbled` | added | create image; attach fail+device; info [exit 0, not a plist] | 1 · yes | attach; "info: answered with no listing"; image kept |

Plus two more tests: `test_a_stopped_step_still_running_is_named` (`integration`; R1's IF): the
`create-hangs` plan with `STOP_SIGNAL` patched to `SIGCONT` (a stop no process dies of) and
`STOP_WAIT` to 0.5 s; the failure names both recorded pids with their commands and "still running
0.5 s", and the run takes at least `SHORT_BOUND + 0.5` and less than `SHORT_BOUND + 0.5 + 3` s. And
`test_the_disk_image_figures` (`unit`, no process): `_bounds(None)` is 120 for every verb,
`STOP_WAIT == 5` (or the maintainer's figure), `STOP_SIGNAL is SIGKILL`.

Every name avoids `silent`, so all of them run in `tests/test_ssh_exec.py -k 'not silent'`
(`suite-legacy-2`, `suite-modern-2`), the suite's emptiest jobs.

### Docs (same commit as the behaviour, § Conventions "point to a rule")

- `AGENTS.md` § Testing, the `test_ssh_exec.py` bullet's full-volume sentence (`:1152-1158`): one
  added clause: each `hdiutil` step runs under a 120 s bound in a process group of its own, a step
  that hangs or fails is KILLed with what it started and named, the image and any device from it are
  cleaned up unless a `detach` failed, and a stand-in pins it on every platform
  (`test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running[…]`,
  `test_a_stopped_step_still_running_is_named`). No other section restates it.
- `tests/test_ssh_exec.py` module docstring: one sentence for the new rows.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `_step` starts each verb as a group leader; `_stop` KILLs the group at once, waits up to `STOP_WAIT`, names survivors by pid and command. Rows 1, 2, 5, 6, 9, 12 (children gone); the survivor row (named, bounded). |
| R2 | `_step`'s two failure texts (`ran past its bound of B s`, `exited with status N: <stderr tail>`), composed in order by `attached_image`. Every failing row asserts its texts. |
| R3 | `_clean_up` after a failed or hung `create`/`attach`: `info`, detach each device by whole disk, remove the image (`missing_ok`); its own `detach` is a `_step`. Rows 1–8, 12. |
| R4 | No detach after a failed one, in the lifecycle or the cleanup; the image is kept; the text names mount point (or device and mount point) and image. Rows 9, 10, 11, 12. |
| R5 | `raise HostFailure(…) from body`; the row reads `traceback.format_exception`'s order. Row 11. |
| R6 | Success path unchanged in effect; `full_volume` fills inside `attached_image`. Row 13 (stand-in); the three real rows on macOS and their Linux path, unchanged. |
| R7 | The rows above, on every platform, no skip; hanging verbs at `SHORT_BOUND`. |

## 3. Invariant gate (AGENTS.md constitution check)

Gate #1 (from the GOAL) and gate #2 (from this design) walk the same sections: the change touches
no numbered § Invariants section (no file under `packages/`, nothing on the high-blast-radius list,
nothing in the coupled core), so neither research trigger 1 nor 2 fires. Trigger 3 fires: the
deliverable is test infrastructure (a fixture and its pinning rows), so the adversarial review ran
(§4).

- § Testing, "only `@mark.unit` and `@mark.integration`": every new test carries one (rows and the
  survivor row `integration`, the figures row `unit`, which launches nothing).
- § Testing, the suite's only skips are `need_shell` and `need_git`: no skip, `skipif`,
  `importorskip` or `xfail` in either file (`test_only_need_shell_skips` reads both;
  the sibling `skip-check-fence-gaps` widens that check, and nothing here is a shape it adds).
- § Testing / § Conventions, CLI drives through `bin/sandbox.sh`: the rows drive no CLI and reach no
  host; their launches are `REAL_POPEN` calls whose argv starts with `bin/sandbox.sh` (the stand-in's
  steps and `ps`), and the stand-in launches nothing. The real `hdiutil` steps stay `REAL_POPEN` calls
  outside it, as `_host`'s are today (amended at the PLAN/TECH gate).
- § Conventions, no spec ids in the suite: none in code, strings or row ids
  (`test_no_spec_ids_in_the_package_or_the_suite` reads both files).
- § Conventions, "CI mirrors the gate": no suite command changes; the rows join an existing part.
- § Factory `ci budget`: rows land in `suite-*-2`; cost in deviation row 5.
- § Conventions, comments declarative, no `R#`: followed.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| 1. The cleanup runs a fourth `hdiutil` verb, `info -plist`, under the same 120 s bound and stop as a step; if it fails, nothing is removed and the failure names it and the kept image. | R3 must detach "every device backed by its image"; only `hdiutil info` names them (P-b: a killed `create`'s device is listed there, by image path). | Reading the device from the step's own output: `create` prints none and a killed step prints nothing. Removing the image when `info` fails: it may back an attached device, the case R4 keeps it for. |
| 2. A step that **fails** (exit ≠ 0) is stopped too, not only one that hangs. | GOAL Outcome: "however one of the fixture's `hdiutil` steps ends (on time, failed, or hung), nothing it started is still running". R1 words only the hang; the stop is the same call, and on a step that exited it only reaches what it left. | Stop on hang only: a failed `create` whose helper lingers would outlive the test, which the Outcome rules out. |
| 3. Four rows and two tests beyond R7's thirteen: `body-fails`, `cleanup-detach-fails`, `info-fails-in-cleanup`, `info-answers-garbled`, `test_a_stopped_step_still_running_is_named`, `test_the_disk_image_figures`; and every failing plan starts a child. | Each pins a decision R7's thirteen cannot reach: a failing body with a good `detach` re-raised (R6: without it, dropping the `raise` swallows a failed test, adversarial finding 1), R1 and R2 for the cleanup's own `detach` when it fails (R3's last sentence), the two `info` branches (row 1 above), R1's survivor clause (no stand-in survives KILL), the signed figures (value mutants), and the stop after a failure for every verb (row 2 above). | The thirteen alone: the pre-sweep and the review (§4) showed the survivor wait, the body's re-raise and the stop after a failed `attach` or `detach` unpinned without them. |
| 4. The survivor test runs with `STOP_SIGNAL = SIGCONT` and `STOP_WAIT = 0.5` patched in. | No process can be made to outlive KILL portably (that takes an uninterruptible sleep); CONT stands in for a stop that does not end it. The real wait is pinned by the figures test. | Running the real `STOP_WAIT`: +4.5 s per era for no extra decision covered. |
| 5. **Timing figures for the maintainer (T2, T3, CI cost).** T2 = `STOP_WAIT` = **5 s** proposed; T3 = `SHORT_BOUND` = **1 s** proposed; both approved by the maintainer at the PLAN/TECH gate, 2026-11-09 (`TECH.md` → Amendments). See the figures table below this one. | GOAL T2 and T3 leave both to the PLAN/TECH sign-off. | — (the maintainer sets them) |
| 6. R4's text for the cleanup's own `detach` names the **device** and the mount point `hdiutil info` reports for it (", not mounted" for a `create`'s device), not the fixture's mount point. | The cleanup detaches by device: a failed `create` made a device that is mounted nowhere, so "the mount point" R4 names is the listing's, when there is one. | Always naming `where`: false for a `create`'s device, which was never attached there. |
| 7. `full_volume` splits into `attached_image` (lifecycle, stand-in-drivable) and the fill. | The stand-in makes no filesystem, so the fill (statvfs of a 4 MB volume) cannot run under it; the rows drive the lifecycle, and the fill stays in the body R5 covers. | A stand-in that fakes `statvfs`: patches `os` for the whole test process and pins nothing R7 asks. |
| 8. The rows live in `tests/test_ssh_exec.py`, beside the fixture. | Their part is `-k 'not silent'` (`suite-legacy-2` 2:46, `suite-modern-2` 5:48), the room the budget has. | A new module lands in the last part (`suite-*-4`, 7:22 and 7:33) for no gain. |

**Timing and cost figures (deviation row 5), for the maintainer.** Measured on the prototype, this
Mac (macOS 27.0.1), one era ([`research/01-probes.md`](research/01-probes.md) P-b, P-e, P-f):

| Figure | Before | After (proposed) | Alternatives |
|---|---|---|---|
| T2, wait after KILL (`STOP_WAIT`) | no stop, no wait: a hung step runs on (observed: a day) | KILL at the bound, then up to **5 s**; real `hdiutil`'s group was empty **15 ms** after KILL (P-b), a stand-in's in ~0.1 s, so 5 s is spent only when a process survives KILL | 2 s (less margin for a slow kernel teardown), 10 s (a longer red run for no likely gain) |
| A hung real `create` or `attach`, test's red run | fails at 120 s, leaves `hdiutil`, its helper and the device | 120 s + ~0.02 s stop + `info` (~0.1 s) + cleanup `detach` (~1 s) ≈ **121 s**, nothing left | worst case, `info` and the cleanup `detach` hanging too: 3 × (120 + 5) = **375 s** |
| A hung real `detach` | fails at 120 s, leaves it running and the volume mounted | 120 s + ~0.02 s (≤ 5 s), volume and image named and kept | — |
| T3, the short bound (`SHORT_BOUND`) | no such test | **1 s**: about 40× the stand-in's 23 ms (max 27 ms) time to reach its hang (P-e) | 0.5 s (20×), 2 s (80×) |
| The new rows, per era | 0 | **~12 s** ≈ 3.5 s + 7 × T3 + (T3 + 0.5 s): seven hangs (six rows, row 12 twice) 7 s, the survivor test 1.6 s, the stops and starts of all 19 tests ~3.5 s; measured 12.0 s of test time (`--durations=0`, the final prototype) | T3 0.5 s: ~8 s; T3 2 s: ~20 s |
| CI job they land in, per era | `suite-legacy-2` **2:46**, `suite-modern-2` **5:48** (profile `ci budget`, `ef301e6`) | projected **~2:58** and **~6:00** (+12 s measured here; up to +20 s on a slower runner: ~3:06 and ~6:08), under the 10:00 budget; the worst job, `suite-modern-3` 7:34, is untouched | T3 0.5 s: ~2:54 / ~5:56; T3 2 s: ~3:06 / ~6:08 (+20 s; up to +30 s on a slower runner) |
| The profile's full `verify`, local | ~26 min | +~24 s (both eras); the prototype's full run is recorded in §6 | — |

Read against the R-IDs: rows 1–4 and 6–8 bend none (R3 still removes what it can identify, R4 keeps
its "no further attempt"); row 2 widens the stop the Outcome asks for without narrowing R1; row 5
is the sign-off the GOAL defers to. No R-ID needs a clarification.

## 4. Rabbit holes (resolved)

- **Is the formatter reachable by a group KILL, or is it a system service's?** → In the group: on
  macOS 27 the `diskimages-helper` that formats a new image is `hdiutil create`'s child, keeps its
  group when launchd adopts it, and dies with a group KILL, taking its device with it
  ([`research/01-probes.md`](research/01-probes.md) P-a, P-b). A finished `attach`'s device is served
  outside the group (P-d), so no stop follows success.
- **How does the wait tell "gone"?** → Not by `killpg(pgid, 0)`: macOS answers EPERM for a zombie-only
  group (P-c). `ps` by pgid, ignoring `Z`, the same on both kernels. Linux behaviour is
  unprobed here (no Linux host in reach of this step); risk below.
- **How does the cleanup find a device?** → `hdiutil info -plist`, matching the image by `realpath`:
  `hdiutil` reports the path as given (P-b), so the stand-in reports a `/./` form to make a string
  compare fail.
- **A hung real `attach`:** not probed (the probe was refused by the planning host's permission
  policy and not retried); the design does not depend on what it leaves (`info` decides).
- **Adversarial review (trigger 3), one pass, appetite small** — see §4.1.
- **Mutant pre-sweep on the prototype** (run by the planner, before and after the review fold):
  **two additive mutants survived** the first draft. A second `detach` after a failed one survived
  because the stand-in failed every `detach` call alike; a skipped stop for a failed `info` survived
  because the stand-in answered `info` before it read the plan's child. Folded: per-call plans (a call
  past the list succeeds, so a retry detaches the device and the row's "1 device left" goes red), and
  one handling of `image`, `device`, `child` and the ending for every verb. After the review fold,
  twenty-two cases, all killed (and `listing-unread` after the last row): `stop-term`, `stop-step-only`, `no-stop-on-fail`, `match-by-string`,
  `wait-dropped`, `chain-dropped`, `unlink-first`, `no-cleanup-on-hang`, `bound-constant`,
  `wait-x10`, `no-stop-info`, `slice-not-disk`, `retry-cleanup-detach`, `retry-detach`, and the
  review's `raise-dropped`, `unlink-dropped-on-body`, `match-any`, `match-basename`, `term-then-kill`,
  `no-stop-on-attach-fail`, `no-stop-on-detach-fail`, `survivor-always`. Before the fold, the
  review's three (dropped re-raise, any-image match, TERM first) and its stop carve-outs survived. The value mutant `timeout=HDIUTIL_BOUND` for `create` is killed only by
  `ROW_LIMIT` (after 120 s per row): the sweep runs it on one row.

### 4.1 Adversarial review

One fresh reviewer, one pass (appetite small), given the GOAL, this PLAN, `research/01-probes.md`,
`verify/rows.sh` and the prototype, tasked with finding a broken fixture the rows pass and a good
one they fail, on Linux and macOS. It ran three mutants together on the prototype (17 passed: all
survived) and restored it. Its findings, and what each changed:

1. HIGH — dropping the bare `raise` after a good `detach` in the body-failed branch survived:
   `@contextmanager` then swallows a failed fill or a failed test assertion (R6). → Row `body-fails`
   (the body's own `AssertionError`, unchained; image gone); sweep cases `raise-dropped`,
   `unlink-dropped-on-body`.
2. HIGH — the cleanup's image match was never tested negatively: deleting the filter (detach every
   listed image, a developer's own DMGs included) or matching by basename survived (R3). → The
   stand-in's state is seeded with a foreign device from a `vol.dmg` in another directory; every row
   asserts it is still attached; cases `match-any`, `match-basename`.
3. HIGH (Linux, unverified) — `-o pid=,pgid=,stat=,args=` as one argument may read as one column
   under procps, making `_left_running` and `_group` list nothing: R7's leftover check vacuous on
   Linux. → One `-o` per field, and `_processes()` refuses a listing that does not show this process
   whole.
4. MEDIUM — TERM, a second's sleep, then KILL (T2's rejected option b) survived: the stand-ins
   ignored TERM silently. → They record a TERM in `pids`; every row asserts none came; case
   `term-then-kill`.
5. MEDIUM — the stop after a failure was pinned for `create` and `info` only. → Every failing plan
   starts a child (`FAILS`); `create-fails-leaving-a-child` folded into `create-fails`; cases
   `no-stop-on-attach-fail`, `no-stop-on-detach-fail`.
6. MEDIUM — R1/R2 for the cleanup's own `detach` on failure was unpinned. → Row `cleanup-detach-fails`.
7. MEDIUM — no row asserted the absence of survivors, so a report naming processes that had exited
   survived. → Every row asserts no `still running`; case `survivor-always`.
8. LOW-MEDIUM — teardown KILLed every recorded pid, exited ones too (pid reuse). → It KILLs only what
   `_left_running` still lists with `STATE` in its argv.
9. LOW — the row texts hard-coded "1 s". → `PAST` derives from `SHORT_BOUND`.
10. LOW — an `info` answer that is not a plist escaped as a raw exception (R3's "not an error from the
    cleanup"). → Read as a failed `info`, named.
11. LOW — PLAN's row-cost arithmetic miscounted the rows; `rows.sh`'s `hdiutil info` pattern could
    never match a volume name. → Recomputed (deviation row 5 figures table); the pattern is now the
    pytest temp root, `pytest-of-`.

It read deviation rows 2 and 6 as honest readings of R1/R4 (row 2 once finding 5 was folded), found
no vacuous `rows.sh` mode, and saw no Linux risk in `os.fork`, `start_new_session`, `killpg` or the
`Z` filter. All eleven folded; the fold re-ran the prototype (21 passed, the real rows included) and
the review's mutants (all killed).

## 5. Risks & open questions

- **Linux unprobed by this step.** `ps -A -ww -o pid= -o pgid= -o stat= -o args=`,
  `start_new_session`, a group KILL and `os.fork` are POSIX, and the one-`-o`-per-field form is the
  one procps documents as unambiguous, but no Linux host was in reach of the plan (a cluster tool is
  out of bounds). The rows' first Linux run is the cycle branch's CI; no phase gate sees it. A `ps`
  of another shape fails every row loudly (`_processes()` refuses a listing without this process),
  never a quiet green.
- **`hdiutil create`/`attach`/`detach -force` are deprecated** on macOS 27 (P-d warnings, in favour of
  `diskutil image`). Outside the GOAL (its non-goals keep the tool); the stderr tail keeps the
  failure line, so a removal would show as a named failure, not a quiet one.
- **`ps` itself is bounded at 30 s** and not stopped if it hangs; a hung `ps` is not a case this
  cycle covers.
- **Per-verb carve-outs of the survivor report** (survivors omitted for `attach` only) are pinned
  for `create` alone: the survivor test runs `create`, since no stand-in survives KILL without the
  patched signal. The stop itself is pinned per verb (every hanging and failing plan has a child).
- **Sibling cycles in flight**, and where they meet this one:
  - `stalled-reconnect-test-timing` (shaped): edits rows in `tests/test_ssh_exec.py` and, likely,
    the same `AGENTS.md` § Testing bullet for that module. Textual conflicts only (different
    sentences and functions); whichever lands second rebases. Its R5/R8 (rows under load, the CI
    budget) bear on ours: our hanging rows meet a bound that always fires (the stand-in never ends),
    so load can only slow them, and the "reached its hang" check names a too-loaded host.
  - `skip-check-fence-gaps` (in review): widens `skip_violations` in `tests/test_hygiene.py`. Our
    files hold no skip shape; P3's gate runs the hygiene module as it is on the branch base, and the
    full `verify` after a rebase would run the widened one.
  - `annotation-check` (planned): checks annotations under each member's `src/` only, not `tests/`;
    our new annotations resolve with `typing.get_type_hints` all the same (`verify/rows.sh`).
  - `mutant-child-outlives-timeout`, `mutants-workflow-timeout`: `tests/mutants.py` and its
    workflow; untouched here (GOAL non-goal), and this cycle's sweep is its own script under
    `spec/…/verify/`.
  - `sandbox-dirs-left-on-kill`: `bin/sandbox.sh`; untouched here. The rows run the stand-in under it
    (amended at the PLAN/TECH gate), and a stop's KILL leaves its directory, under the row's
    `tmp_path` (`TMPDIR`), so pytest's own cleanup takes it.
  - No `AGENTS.md` § Testing edit of ours touches the skip, annotation, mutation-runner or sandbox
    paragraphs.

## 6. Verification strategy

There is no CLI flow: the deliverable is a test fixture. Each phase runs its rows by exact id in both
eras ([`verify/rows.sh`](verify/rows.sh) `p1`, `p2`, `all`), failing on any id not reported
`PASSED`. The real full-volume rows run on this Mac with real `hdiutil` (R6), and `rows.sh all`
fails if `hdiutil info` lists an image the rows made.

**The mutant sweep** (P3, written then as `verify/mutants.py`, recorded in
`verify/mutant-sweep.md`): it copies `tests/` and the top-level files into a fresh `mktemp -d`,
applies one exact edit per case to the copy of `tests/test_ssh_exec.py` (or of the stand-in), runs the
case's named rows there in one era (`-p no:cacheprovider`, a 300 s cap per case, the child's process
group KILLed at the cap), and passes a case only when every named row fails with the case's `why`.
Each case's edit must apply exactly once to the pristine copy (an anchor that moved is red, not
skipped). Modes `a` and `b` split the cases so each stays under ten minutes; one case at a time.

Decisions it plants (existing):

| Case | Edit | Killed by (`why`) |
|---|---|---|
| `stop-term` | `STOP_SIGNAL` KILL → TERM | hang rows ("still running after"); figures test |
| `stop-step-only` | `os.killpg` → `os.kill` | rows 1, 2, 5, 6, 9, 12 ("still running after") |
| `wait-dropped` | no group poll after `proc.wait` | survivor test ("still running 0.5 s") |
| `wait-x10` | the deadline `STOP_WAIT` → `STOP_WAIT * 10` | survivor test (run time) |
| `survivors-unnamed` | `_stop` returns `""` | survivor test ("pid … is not named") |
| `bound-constant` | `communicate(timeout=bound)` → `HDIUTIL_BOUND` | `create-hangs` (run time; 120 s) |
| `bound-misnamed` | the hang text names `HDIUTIL_BOUND` | hang rows ("ran past its bound of 1 s") |
| `status-dropped` | the failure text drops the exit status | failing rows ("exited with status 1") |
| `stderr-dropped` | the failure text drops the stderr tail | failing rows ("failed - stand-in failure") |
| `cleanup-attach-only` | cleanup only after `attach` | rows 2, 4 (device or image left) |
| `match-by-string` | `realpath` compare → string compare | rows 2, 4, 6, 8, 12 (device left) |
| `slice-not-disk` | `min(…, key=len)` → `max` | rows 2, 4, 6, 8 (device left) |
| `unlink-first` | image removed before the cleanup detach | row 12 (image gone) |
| `unlink-strict` | `missing_ok=True` → `False` | rows 1, 3 (raised `FileNotFoundError`) |
| `info-ignored` | an `info` failure goes on to remove the image | `info-fails-in-cleanup` (image gone) |
| `left-unnamed` | R4 text dropped after a failed detach | rows 9, 10 ("stays attached at") |
| `chain-dropped` | `from body` dropped | row 11 (cause, order) |
| `order-swapped` | cleanup texts before the step's | row 12 (order) |
| `unlink-dropped` | image not removed after a detach that succeeded | row 13 (image left) |
| `detach-image` | the final detach names the image, not `where` | row 13 (raised) |
| `figures` | `HDIUTIL_BOUND` 120 → 60, `STOP_WAIT` 5 → 50 | figures test |
| `raise-dropped` | the body's exception not re-raised after a good detach | `body-fails` |
| `unlink-dropped-on-body` | the image kept after a good detach, the body failed | `body-fails` |
| `match-basename` | match the image by its name | every row with a cleanup (the foreign `vol.dmg`) |
| `listing-unread` | a non-plist `info` answer raised raw | `info-answers-garbled` |

Additive (a carve-out the code lacks, or a step it does not take):

| Case | Edit | Killed by |
|---|---|---|
| `no-stop-detach` | skip the stop when `verb == 'detach'` | rows 9, 12 ("still running after") |
| `no-stop-cleanup` | skip the stop for the cleanup's detach only | row 12 |
| `no-stop-info` | skip the stop when `verb == 'info'` | `info-fails-in-cleanup` (its child) |
| `no-stop-on-fail` | stop only on a hang | every failing row (its child) |
| `no-stop-on-attach-fail` | skip the stop after a failed `attach` | rows 7, 8 |
| `no-stop-on-detach-fail` | skip the stop after a failed `detach` | rows 10, 11, `cleanup-detach-fails` |
| `no-cleanup-on-hang` | cleanup only after a failure | rows 2, 6 (device left) |
| `no-unlink-without-device` | remove the image only when a device was found | rows 5, 7 (image left) |
| `retry-detach` | a cleanup after a failed final detach | rows 9, 10, 11 (device detached) |
| `retry-cleanup-detach` | a second detach of a device after a failed one | row 12 (device detached) |
| `no-left-on-body` | R4 text dropped in the body-failed branch only | row 11 ("stays attached at") |
| `match-any` | the cleanup detaches every listed image | every row with a cleanup (the foreign device) |
| `term-then-kill` | TERM, a second, then KILL | hang rows ("sent TERM") |
| `survivor-always` | the report names a survivor whatever is left | every failing row ("names a survivor") |

The planner's pre-sweep ran twenty-two of these on the prototype (§4): all killed after the fold.

**Dry runs on the prototype** (`$REPO/.worktrees/full-volume-fixture-leaks-hdiutil-proto`, removed
before the plan's report): `rows.sh p1` on a P1-cut tree green (and `p2` there red, 12 of its ids
failing); `rows.sh p1`, `p2`, `all` on the full tree green (measured 15.9 s, 32.6 s, 38.0 s, both
eras, before the last row; ~1 s more after); `p3.sh selftest` green, and red for a stray file, a planted deferral and an `AGENTS.md`
without the test names; `p3.sh sweep-a` red until `mutants.py` exists (it is P3's to write).
The prototype's full suite, once: `p3.sh full` (the profile's `verify`, verbatim) green in 1,558 s
(26 min) on this Mac, before the last row (`info-answers-garbled`) was added; `rows.sh all` green
after it (22 ids per era). The gate's leftover check first matched its own calling shell (a command
line naming the stand-in); it now matches only an interpreter running the script, and goes red for a
planted stand-in left running.

---

*Backing research: [`research/01-probes.md`](research/01-probes.md) (lean path: no digest).*
