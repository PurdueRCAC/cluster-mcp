# REVIEW — A disk-image step that hangs or fails is stopped, and the full-volume fixture leaves nothing behind

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** 6650254  ·  **Base:** develop (`origin/develop` 146cbc6)  ·  **Date:** 2026-11-10
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)
- **Mode:** one fresh blind reviewer (subagent, effort xhigh), the full spec-excluded diff. No
  sequential fallback, no debate (the diff touches no coupled-core path).
- **Contract drift:** `GOAL.md` moved once after the shape commit (`679a052`, the GOAL-gate
  clarifications T1, T2, T3, D1). Legitimate post-shape clarifications, confirmed by the foreman;
  graded against `GOAL.md` at HEAD.

## Verification run

### Orchestrator: the spec-held gates, light modes, run to completion before the reviewer started

Run from the worktree, `UV_PYTHON=3.14`, sequentially; logs under the worktree's gitignored
`.local/review1/` (`gate-*.log`, `gates-summary.txt`). `hdiutil info` was recorded before
(`hdiutil-info-before.txt`: no images attached) and was identical after the gates, and again after
the reviewer.

| Gate | Command | Result |
|---|---|---|
| P1 | `sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p1` | exit 0, 28 s; 9 ids passed per era; leftovers scoped and read through both shims |
| P2 | `sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p2` | exit 0, 40 s; 22 ids passed per era |
| P3 `pre` | `sh spec/…/remediation/scoped-leftovers.sh --around sh spec/…/verify/p3.sh pre` | exit 0, 44 s; `rows.sh all` ok (partition, hygiene 142 passed), docs, scope, ledger ok |
| P3 `sweep-a` | `sh spec/…/verify/p3.sh sweep-a` | exit 0, 4.3 min; 19 of 19 killed |
| P3 `sweep-b` | `sh spec/…/verify/p3.sh sweep-b` | exit 0, 1.5 min; 21 of 21 killed |
| P3 `full` | not run by the orchestrator | the reviewer ran the profile's full verify (below); CI run 42770357148 on 6650254 is green, all 9 jobs |

**A listed-mutant gate cannot grade an open-ended class.** P3's sweep is a fixed list of 40 cases,
all killed, and it stayed green while the reviewer's additive carve-out M32 (F2 below) survived: a
list grades only the decisions it names, never the class around them. Its green is evidence for
those 40 decisions, not for the classes they sit in.

### Reviewer (blind)

- New tests, both eras: `uv run pytest -q tests/test_ssh_exec.py -k 'disk_image or stopped_step'`,
  plain and `CLUSTER_MCP_TEST_ERA=modern` → 19 passed each (17 rows, the stopped-step test, the
  figures test).
- Real macOS rows through the throwaway helper, both eras:
  `bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run pytest -v tests/test_ssh_exec.py -k test_a_write_that_runs_out_of_room_keeps_the_file'`
  → `8k-free`, `32k-free`, `edquot` passed; `hdiutil info` afterwards listed no image.
- The profile's full `verify`, one command at a time, in the background → green: per era 44 passed
  (silent), 173 passed (not silent), 507 passed (timeout/startup/launch), 4369 passed and 14 skipped
  (the rest; the 14 are in modules this diff does not touch); `bin/sandbox.sh uv run cluster-mcp --help`
  printed its usage.
- CI run 42770357148 (6650254): success. Linux suite part 2 shows 173 passed, 0 skipped per era, the
  macOS count, so the new rows run on Linux with no skip; job walls 2:50 and 2:53.
- 32 hand-made mutants in an archive copy, restored byte for byte: 25 killed, 7 survived (F2 and
  the coverage observations below).
- Stand-in probes beyond the rows: two devices from one image, and a body raising pytest's `Failed`;
  the branch code detaches and removes in both.
- Real `hdiutil` with tiny bounds forcing a mid-step stop: `create` stopped at 0.05–0.95 s and
  `attach` at 0.05–0.18 s each failed naming the step and the bound, and left no process, device or
  image. During `create` the disk-image helper is in the step's process group; after a successful
  attach the helper serving the device runs in its own group under pid 1, so the group KILL reaches
  it mid-create and a failed `detach` cannot reach the server of an attached volume (R4 holds).
- Greps (`-- . ':(exclude)spec/'`): every `hdiutil` call goes through `_step`; `_host` is gone; both
  failure paths reach `_stop` (`killpg`); the cleanup iterates every image entry; no spec ids in
  the added lines; no skip or xfail in the new code.

## Requirement → evidence matrix

All R-IDs are test behaviour; none is a `spec/` artifact, so the reviewer graded all seven and the
orchestrator cross-checked through the spec-held gates.

| R-ID | Implemented by (file/commit) | Verified how | Verified by | Status |
|------|------------------------------|--------------|-------------|--------|
| R1 | `tests/test_ssh_exec.py` `_step` (own session, 120 s bound) → `_stop` (`killpg` KILL, 5 s bounded wait, survivors named by pid and command) | hang rows; `test_a_stopped_step_still_running_is_named`; reviewer mutants M01, M03b, M04, M05, M16, M26, M35 killed; real-`hdiutil` probes; sweep cases `stop-*`, `wait-*`, `survivors-unnamed`, `term-then-kill` killed | reviewer; orchestrator (P1, sweeps) | ✅ |
| R2 | `_step`'s failure text: the verb and the bound, or the exit status and the stderr tail | text checks in every row; M20 killed; sweep `bound-*`, `status-dropped`, `stderr-dropped` killed | reviewer; orchestrator | ✅ |
| R3 | `attached_image` → `_clean_up` (`info -plist`, realpath match, detach each whole device, unlink) | rows 1–8, 12; M06–M09, M23, M34, M36 killed; real probes; "every device" graded by search (the loop covers every entry) | reviewer; orchestrator (P2, sweeps) | ✅ |
| R4 | `_clean_up`'s early return; the body-path and final `detach` raise naming mount point and image, no retry | `detach-*`, `cleanup-detach-*` rows; M10–M12 killed; sweep `retry-*`, `left-unnamed` killed | reviewer; orchestrator | ✅ |
| R5 | `raise HostFailure(...) from body` | `body-and-detach-fail` row (order in the formatted chain); M13, M13b, M14, M15 killed | reviewer; orchestrator | ✅ (code); pin partial, F2 |
| R6 | success path unchanged in effect | real macOS rows, both eras; Linux CI 173 passed | reviewer; orchestrator (P1 real ids) | ✅ |
| R7 | `DISK_IMAGE_ROWS` (13 required cases + 4), `tests/hdiutil_standin.py` through `bin/sandbox.sh`, 1 s short bound, no skip | both eras locally; Linux CI; the body-failure pin admits a carve-out (F2) | reviewer; orchestrator | ❌ (F2) |

Unmapped changes (possible scope creep): none. The four extra rows (`body-fails`,
`cleanup-detach-fails`, `info-fails-in-cleanup`, `info-answers-garbled`) and the `info` handling
pin R3–R5 behaviour. The `ROADMAP.md` and seed status flips to `adopted:` are the profile's
bookkeeping and are consistent.

## Findings

Severity: **CRITICAL** (a violation of any numbered section of § Invariants is auto-CRITICAL,
**including lettered subsections**; a § Conventions violation is **HIGH**) · **HIGH** · **MEDIUM** ·
**LOW**. Verdict: **CONFIRMED** (reproduced) vs **PLAUSIBLE** (suspected, needs human triage). Only
CONFIRMED findings auto-loop to `code-build`.

### [MEDIUM/CONFIRMED] F1 — `AGENTS.md` does not name the new helper module `tests/hdiutil_standin.py`
- **Where:** `AGENTS.md:1158-1167` (§ Testing, the `tests/test_ssh_exec.py` entry).
- **Failure scenario:** the entry describes "a stand-in for `hdiutil`" but never names its module.
  Every other `tests/*.py` module is named in `AGENTS.md`, helpers included (`tests/argv_echo.py`
  and `tests/ssh_server.py`, each "a helper, not collected"); the stand-in's interface (`plan.json`,
  `pids`, `devices.json`) and the new `unit` test `test_the_disk_image_figures` are not described.
  A grep of the manual for the module this diff introduced finds nothing.
- **Evidence:** reviewer: `grep` of `AGENTS.md` for every `tests/*.py` basename, 0 hits for
  `hdiutil_standin`. Orchestrator re-ran it: `for f in tests/*.py; do grep -qF "$(basename $f)" AGENTS.md || echo MISSING …; done`
  → `MISSING hdiutil_standin.py`, and nothing else.
- **Touches invariant / requirement:** rubric Scope 5, operating-manual drift (an `AGENTS.md`
  description absent): MEDIUM.

### [MEDIUM/CONFIRMED] F2 — The body-failure pin admits a carve-out: a body that exits by a `BaseException` that is not an `Exception` leaks the volume and the image, and the rows stay green
- **Where:** `tests/test_ssh_exec.py`, `attached_image`'s `except BaseException as body` (the
  guarded decision) and `DISK_IMAGE_ROWS` / `_drive_image` (the pin, whose body raises only
  `AssertionError`).
- **Failure scenario:** mutant M32 narrows the handler to `except Exception`. A body that ends with
  pytest's `Failed` (MRO `Failed → OutcomeException → BaseException`), or `Skipped`, `XFailed` or
  `KeyboardInterrupt`, then bypasses the detach: the volume stays attached, the image is kept, and
  the report carries only the body's exception, naming nothing left behind. The input is one the
  tree reaches: `test_a_write_that_runs_out_of_room_keeps_the_file` calls `need_sftp_server()`
  inside the `full_volume` body (inside the `ExitStack` that entered it), and `need_sftp_server()`
  calls `pytest.fail` when `sftp-server` is missing. Every row passes under the mutant.
- **Evidence:** reviewer: `mutants/M32-except-exception.log` → "SURVIVED (tests green) :: 19 passed";
  stand-in probe `extra_probe.py` → on the branch code, body raising `Failed` leaves no device and no
  image; on the M32 copy, one own device left attached at the row's mount point and `image exists:
  True`, raised only `Failed`. Orchestrator re-read both logs and checked the MRO
  (`_pytest.outcomes.Failed.__mro__`) and the call site (`need_sftp_server()` within the
  `full_volume` body).
- **Touches invariant / requirement:** R7 (pin R5 and R6's "the test body fails … then detach" for
  every way the body can fail); R5/R6 behaviour is correct today, unpinned for this class.
- **Classification note:** the reviewer listed M32 as a coverage observation and flagged it as the
  strongest to promote. The orchestrator promoted it under the cycle's binding grading rule: a
  survivor that is a leak on input the tree can reach is a finding. It is not a deeper layer of the
  `body-fails` row's class: that row's `AssertionError` sits inside `Exception`, and the carve-out is
  the class beside it.

## Coverage observations (seeded)

Surviving hand-made mutants that pin a deeper layer of a class a row already pins, or code no
reachable input exercises. Not findings.

- **M03** — `_stop` without the post-KILL poll of the group (only the leader is waited on)
  survives: a member slow to die after KILL would be named at once instead of waited on. R1's
  "wait for them" is graded by search: the loop polls the whole group.
- **M30** — `_clean_up` stopping after the first image entry survives: with two devices from one
  image, one stays attached and the image is removed silently. No fixture flow makes two devices
  from one image; R3's "every device" is graded by search (the loop covers every entry).
- **M19** — the head of stderr instead of its tail survives: the stand-in's stderr is shorter than
  the 400-character tail.
- **M17** — counting zombies in `_group` survives: equivalent in practice, zombies are reaped.
- **M24** — dropping the `PermissionError` suppression on `killpg` survives: defensive, the EPERM
  race is not reached.
- **M25** — dropping `_processes`' own-pid check survives: defensive, `ps` answers in the parsed
  shape on both platforms.

## Human-gate triggers

- Not triggered. F1 is in `AGENTS.md` and F2 in `tests/test_ssh_exec.py`, neither on the
  high-blast-radius list in `AGENTS.md` § Invariants, and neither violates a section tagged
  *[human gate]*. The diff touches no path on that list.

## Routing

`code build`, the property each finding names, its whole domain:

- **F2:** however the test body exits (an assertion, a pytest outcome such as `fail`, `skip` or
  `xfail`, an interrupt, any `BaseException`), the fixture detaches the volume and removes the
  image, or, when that `detach` fails or hangs, reports both failures, the body's first, and names
  what was left. Pin it with body rows across that domain, not one more instance. As a
  surviving-mutant finding, it routes as a sweep over every decision in the fixture (`_step`,
  `_stop`, `_group`, `_processes`, `_clean_up`, `attached_image`), each in both protocol eras,
  additive carve-outs included, equivalents recorded with why.
- **F1:** `AGENTS.md` names `tests/hdiutil_standin.py` as a helper, not collected, with its
  interface, and the `unit` figures test, the way the other helpers are named.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run (not requested).

## Reviewer conduct (verified by the orchestrator)

- `git status --porcelain` empty after the hand-back; `.venv` fingerprint (sorted site-packages
  listing and `pyvenv.cfg`, taken before the reviewer started) unchanged; `hdiutil info` identical
  to the record taken before the cycle's runs (no images); no stand-in, `hdiutil` or `newfs_hfs`
  process left.
- The reviewer's full verify left about 300 `cluster-mcp-sandbox.*` directories in `$TMPDIR` (the
  known leak `issues/sandbox-dirs-left-on-kill.md`, outside this GOAL); its cleanup attempt was
  refused by the session's permission check, and they remain.

## Reviewer hand-back (as returned)

Lightly trimmed for the public record (host paths dropped); its findings, observations, matrix and
conduct notes are as returned.

> **Verdict:** no CONFIRMED correctness bug, R-ID gap or § Invariants violation. One MEDIUM
> finding: AGENTS.md does not name the new module. Seven mutants survived; all are listed as
> coverage observations.
>
> **Findings.** 1. MEDIUM, CONFIRMED: operating-manual drift. `AGENTS.md:1158-1167` (§ Testing,
> the `tests/test_ssh_exec.py` entry) describes "a stand-in for `hdiutil`" but never names
> `tests/hdiutil_standin.py`. All 46 other `tests/*.py` modules appear by name, helpers included;
> `hdiutil_standin` has 0 hits. The stand-in's interface (`plan.json`, `pids`, `devices.json`) and
> the new `unit` test `test_the_disk_image_figures` are also not described.
>
> **Coverage observations (seeded).**
> - M32: `except BaseException as body` → `except Exception` survives. On the stand-in, a body that
>   raises pytest's `Failed` leaves the volume attached and the image kept, with nothing reported.
>   That input is reachable: `need_sftp_server()` calls `pytest.fail` inside `full_volume`'s body.
>   The rows only raise `AssertionError`. This is the strongest of the seven if you want to promote
>   one.
> - M03: the after-KILL poll of the whole process group, removed so only the leader is waited on,
>   survives. It is not equivalent for a group member that outlives KILL for a moment (a formatter
>   stuck in disk I/O): that member would be named "still running 5 s after" with no wait.
> - M30: cleanup stopping after the first image entry survives. On the stand-in with two devices
>   from one image, it leaves one device attached, removes the image, and says nothing. No row has
>   two devices per image.
> - M19: the head of stderr instead of the tail survives, because the stand-in's stderr is shorter
>   than the 400-character tail.
> - M17: counting zombies in `_group` survives (equivalent in practice; zombies get reaped).
> - M24: dropping the `PermissionError` suppression on `killpg` survives (defensive; the EPERM race
>   is never reached).
> - M25: removing `_processes`' own-pid check survives (defensive).
>
> **Matrix.** R1–R7 all Met (R1 `_step` → `_stop`; R2 `_step`'s text; R3 `_clean_up`; R4 the early
> return and the raising detaches; R5 `raise HostFailure(...) from body`; R6 real macOS rows and
> Linux CI's 173; R7 `DISK_IMAGE_ROWS`, 13 required cases plus 4, 1 s short bound, no skip). The
> figures (120 s, 5 s, KILL, 1 s) are pinned by `test_the_disk_image_figures`.
>
> **Scope creep:** none in the code. **Drift:** finding 1 only.
>
> **Conduct.** Tree clean; `.venv` unchanged (its own starting hash was over an unstable unsorted
> listing, so it checked file count and mtimes/ctimes instead); `hdiutil info` identical to its
> start; no process of its left; mutant copy confirmed identical to the worktree after the sweep;
> scratch only in `.local/review1/`; about 300 sandbox directories from its runs left in `$TMPDIR`
> (the scoped-out leak), its `del` refused; `DONE` written.
