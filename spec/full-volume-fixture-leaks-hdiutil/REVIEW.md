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

## Review cycle 2 — changes-requested (2026-11-10)

- **Reviewed commit:** 660b64b  ·  **Base:** develop (`origin/develop` 146cbc6)  ·  **Date:** 2026-11-10
- **Verdict:** changes-requested (three CONFIRMED findings: one MEDIUM, two LOW)
- **Cycle:** 2 of ≤3, not converged: escalated to the maintainer (`code-review` Step 6)
- **Mode:** a fresh blind pass over the full spec-excluded diff, which also graded whether cycle 1's
  F1 and F2 are closed as properties. One fresh blind reviewer (subagent, effort xhigh), given the
  GOAL and the rubric inline, the spec-excluded diff and log, `AGENTS.md` by path and cycle 1's
  findings' text. No sequential fallback, no debate (no coupled-core path in the diff).
- **Commits since cycle 1:** `b340cbe` (F1, F2) and `660b64b` (the seed
  `issues/disk-image-fixture-deeper-pins.md` and its `ROADMAP.md` entry).
- **Contract drift:** none since cycle 1. `GOAL.md` still moved only once after the shape commit
  (`679a052`, the GOAL-gate clarifications); graded against `GOAL.md` at HEAD.

### Rulings at the build gate (recorded as given)

- **Skip and xfail body rows.** They raise pytest's outcome types inside a body the fixture
  catches, and no row skips: admitted under the no-skip rule (R7, `AGENTS.md` § Testing).
- **One seed.** `issues/disk-image-fixture-deeper-pins.md` holds cycle 1's six coverage observations
  and five more of the same kind from the remediation sweep: accepted as one seed.

### Grading rule

`method/mutation-testing.md` § When a review is done, applied as written: the sweep's survivor list
is the enumeration; a hand-made mutant is a finding only when it breaks an R-ID's stated check or a
reachable behaviour; one that pins a deeper layer of a class already pinned is a coverage
observation and is seeded. For this cycle: a reachable leak, a silent pass or a false refusal is a
finding, and so is a class nothing pins yet; a deeper layer of a class a planted row already pins
is a coverage observation, listed one line each, and may join the existing seed. A class is drawn
by the R-ID's wording.

### Verification run

#### Orchestrator: the spec-held gates, light modes, run to completion before the reviewer started

Run from the worktree, `UV_PYTHON=3.14`, one at a time; logs under the worktree's gitignored
`.local/review2/orch/` (`gate-*.log`, `gates-summary.txt`). `hdiutil info` was recorded first (no
images attached) and was identical after the gates and again after the reviewer. The `.venv`
freeze (`uv pip freeze`) was identical before and after both.

| Gate | Command | Result |
|---|---|---|
| F1 | `sh spec/…/remediation/F1-every-test-module-named.sh` | exit 0: all 46 modules under `tests/` named, the stand-in's interface and both `unit` tests named |
| F2 `coverage` | `uv run python -I spec/…/remediation/F2-fixture-sweep.py coverage` | exit 0: 71 decision lines in 7 functions, 71 changed by a case; 10 body exits × 7 families; 40 frozen + 123 new cases; 12 expected survivors |
| P3 `pre` | `sh spec/…/remediation/scoped-leftovers.sh --around sh spec/…/remediation/seed-in-scope.sh sh spec/…/verify/p3.sh pre` | exit 0, 42 s: `rows.sh all` ok (hygiene 142 passed), ledger ok, the seed and its `ROADMAP.md` entry admitted, leftovers scoped |
| F2 `rows` | `uv run python -I spec/…/remediation/F2-fixture-sweep.py rows` | exit 0, 40 s: 39 ids passed in each era, none skipped |
| P3 `sweep-a` | `sh spec/…/verify/p3.sh sweep-a` | exit 0, 4.2 min: 19 of 19 killed |
| P3 `sweep-b` | `sh spec/…/verify/p3.sh sweep-b` | exit 0, 1.4 min: 21 of 21 killed |
| F2 `new-legacy-a` | `uv run python -I spec/…/remediation/F2-fixture-sweep.py new-legacy-a` | exit 0, 6.1 min: 53 generated, 41 killed, 11 seeded and 1 equivalent survived as expected, 0 other survivors, 0 unviable, 0 timed out, 0 unrun |
| F2 `new-legacy-b` | `uv run python -I spec/…/remediation/F2-fixture-sweep.py new-legacy-b` | exit 0, 2.5 min: 70 of 70 killed |
| F2 `frozen-modern`, `new-modern-a`, `new-modern-b` | not run by the orchestrator (light modes) | **not observed** here; the reviewer's own sweep ran its cases in both eras (below) |
| P3 `full` | not run by the orchestrator | the reviewer ran the profile's full verify once (below) |

**A listed-mutant gate cannot grade an open-ended class.** Every listed gate above is green, 163
cases with every survivor expected, and the reviewer still found a class outside the list (F3: a
step whose wait ends by an interrupt) and a survivor beside it (F4's `OSError` carve-out). A list
grades only the decisions it names; its green is evidence for those cases, not for the classes
around them.

#### Reviewer (blind)

- Pin tests plus the real room rows, both eras: 42 passed (legacy, 28 s) and 42 passed (modern,
  21 s); `hdiutil info` clean afterwards.
- Its own mutant sweep on `git archive HEAD` copies (`.local/review2/copy1`, `copy2`), 43 cases ×
  2 eras, 2 workers, 497 s wall; the null mutant passed 39 of 39 in each era (`ev/mutants.jsonl`).
  Killed in both eras: M32 (`except Exception`) and every carve-out of a class directly under
  `BaseException`, each pytest outcome, and an unnamed class; the dropped cause, the unlink after a
  failed detach, the image kept after a good detach, a retried detach, the report order swapped;
  the stop, bound and text decisions; the cleanup. Survived: B12 (F4), S09, S10, H01, H02.
- Stand-in probes: an interrupt during a hung step (F3), on HEAD and on a base-style launch; a
  failed `create` whose cleanup `info` fails or answers garbled (F5).
- The profile's full verify, once, every command exit 0: `uv lock --check`; per era `-k silent` 44
  passed, `-k 'not silent'` 193 passed, the timeout/startup/launch trio 507 passed, the rest 4369
  passed and 14 skipped (modules this diff does not touch); `bin/sandbox.sh uv run cluster-mcp
  --help` printed its usage. Its wrapper's last line reads `verify rc=1`, from the wrapper's own
  final test, not a gate: all ten commands are recorded at rc=0 in `ev/verify-summary.txt`.
- CI run 42788859429 on HEAD: green, the Linux suite with 0 skipped.

### Requirement → evidence matrix

No R-ID is a `spec/` artifact; the reviewer graded all seven, and the orchestrator cross-checked
through the spec-held gates above.

| R-ID | Implemented by (file/commit) | Verified how | Verified by | Status |
|------|------------------------------|--------------|-------------|--------|
| R1 | `tests/test_ssh_exec.py` `_step` (own session, bound) → `_stop` (`killpg` KILL, shared 5 s wait, survivors named by pid and command) | hang rows; `test_a_stopped_step_still_running_is_named`; `test_the_disk_image_figures`; stop mutants killed; `sweep-a`/`-b`, `new-legacy-a` | reviewer; orchestrator | ✅ for a hang and a failure; an interrupted step is not stopped (F3) |
| R2 | `_step`'s texts: the bound, or the exit status and a 400-character stderr tail | ordered text checks in every row; text mutants killed | reviewer; orchestrator | ✅ (tail vs head unpinned: S09, seeded) |
| R3 | `_clean_up`: `info -plist`, realpath match, detach each whole device through `_step`, `unlink` | rows 1–8 and 12, `cleanup-detach-fails`, `info-*`; cleanup mutants killed; probes | reviewer; orchestrator | ✅ in effect; the report after a failed `info` can name an image that is not there (F5) |
| R4 | no retry; `left` names the mount point and the image | detach rows; retry and unlink mutants killed | reviewer; orchestrator | ✅ |
| R5 | `except BaseException as body` → `HostFailure(...) from body` | `body-and-detach-fail` and the 9 kinds × 2 rows; `test_every_way_a_body_can_end_has_its_rows`; B01–B24 killed but B12 | reviewer; orchestrator (`new-legacy-b`) | ✅ in effect; the fill's failure, which R5 names, has no row (F4) |
| R6 | `full_volume` delegates to `attached_image` | real macOS rows `8k-free`, `32k-free`, `edquot` in both eras; Linux CI green, 0 skipped | reviewer; orchestrator (`rows`) | ✅ |
| R7 | `DISK_IMAGE_ROWS` (the 13 cases and more), `tests/hdiutil_standin.py` through `bin/sandbox.sh`, `SHORT_BOUND` 1 s, no platform guard | 39 ids per era locally (orchestrator `rows`, reviewer) and on Linux CI, none skipped | reviewer; orchestrator | ❌ (F4: a class R5 names is unpinned) |

Unmapped changes: none in the code; the extra rows, the `info` verb and its bound, and the
stand-in's `garbled` plan pin R3–R5. The seed and `ROADMAP.md`, graded as prose by the reviewer:
the functions it names exist, items 1 and 3 reproduce (S10, S09), `status: unshaped` is right, its
links resolve, Part I counts 29 entries and Gates 13; the adopted seed's status matches.

### Cycle 1's findings

- **F1 — closed as a property.** Every `tests/*.py` module is named in `AGENTS.md` (F1 checker
  over 46 modules; the reviewer's own grep found none missing); the four new tests are named; the
  stand-in's described interface matches `tests/hdiutil_standin.py` as read.
- **F2 — closed as a property for the domain it was routed with:** every class directly under
  `BaseException`, each pytest outcome, and a bare class (all carve-outs killed in both eras;
  M32 killed by the `body-pytest-fail` rows, the tree's own `need_sftp_server()` instance). The
  class beside it that R5's wording names, the fill's own failure, is open: F4.

### Findings

#### [MEDIUM/CONFIRMED] F3 — An interrupt while a disk-image step runs leaves the step, everything it started, its image and its device
- **Where:** `tests/test_ssh_exec.py:859-863`, `_step`: the step is launched with
  `start_new_session=True`, and only `subprocess.TimeoutExpired` is handled around `communicate`.
  Every caller inherits it: `create` and `attach` in `attached_image`, the body-path and
  success-path `detach`, the cleanup's `info` and `detach`.
- **Failure scenario:** a developer presses Ctrl-C while a full-volume step runs (likeliest while
  a hung step waits out its 120 s bound). The terminal signals its foreground process group; the
  step is in a session of its own, so it never receives SIGINT. `KeyboardInterrupt` unwinds out of
  `communicate`, nothing calls `_stop`, and `hdiutil`, what it started, any device and the image
  stay: the 2026-10-31 leak, reached by a route this diff opened. On `origin/develop` the step
  shared pytest's process group, so the same interrupt reached it. The GOAL's outcome ("nothing it
  started is still running when the test fails") has no carve-out for it, and no row pins it.
- **Evidence:** reviewer: `ev/probe_interrupt.py` through `bin/sandbox.sh`, a stand-in `create`
  that hangs with a child (30 s bound), then after 2 s `os.killpg(os.getpgrp(), SIGINT)` as a
  terminal does. HEAD: `KeyboardInterrupt`, 3 processes still running
  (`ev/probe-interrupt-head.log`); with an image and device in the plan, 3 still running,
  `image_exists: true`, `own_devices: ["/dev/standin2"]` (`ev/probe-interrupt-head-with-device.log`);
  base-style launch (`REAL_POPEN`, same group): nothing running (`ev/probe-interrupt-base.log`); the
  probe KILLed its leftovers. Orchestrator re-read the three logs and `_step`'s handler. Not
  reproduced: real `hdiutil`'s own response to SIGINT; the mechanism (the interrupt reaches the step
  on base, never on HEAD) is shown.
- **Touches invariant / requirement:** a correctness bug against the GOAL's outcome and R1's stop
  (a step that does not end on time is stopped with what it started); no § Invariants section.

#### [LOW/CONFIRMED] F4 — The fill's own failure, which R5 names, is a class no row raises: an `OSError` carve-out in the body handler survives
- **Where:** `tests/test_ssh_exec.py:933`, `attached_image`'s `except BaseException as body`;
  `BODY_EXITS` / `DISK_IMAGE_ROWS` (no row's body fails the way the fill fails).
- **Failure scenario:** R5 names three ways the body fails: "the fill, its assertion, or the
  test's own assertions". The fill fails by an `OSError` (ENOSPC from `filler.write`, say). Mutant
  B12 inserts `if isinstance(body, OSError): raise` at the head of the handler: a failing fill then
  skips the detach, the volume stays attached and the image is kept, with nothing named. Every row
  passes, since the only `Exception` subclasses any row's body raises are `AssertionError` and
  pytest's `Exit`.
- **Evidence:** reviewer: `ev/mutant-B12-carve-OSError-{legacy,modern}.log`, 39 passed in each era.
- **Classification:** the reviewer offered either reading. The orchestrator drew the class by R5's
  wording, as this cycle's rule binds: "the fill" is named in the R-ID and nothing pins it, so it is
  a class nothing pins yet, not a deeper layer of the assertion's class.
- **Touches invariant / requirement:** R7 (pin R5 for each way R5 names); R5's behaviour is correct
  today.

#### [LOW/CONFIRMED] F5 — After a failed cleanup `info`, the report says the image is kept when there is no image
- **Where:** `tests/test_ssh_exec.py:890`, `_clean_up`'s return when `info` fails or answers
  with no listing.
- **Failure scenario:** `create` fails having made no image; the cleanup's `info` then fails or
  answers garbled. The report ends "the image is kept at …/vol.dmg, and any device made from it
  stays attached", naming a file that does not exist. The step's own R2 failure is still first.
- **Evidence:** reviewer: `ev/probe-plan-create-fails-info-fails.log` and
  `ev/probe-plan-create-fails-info-garbled.log`, each `image_exists: false` with that line in the
  report. Orchestrator re-read both and the return at `:890`.
- **Touches invariant / requirement:** R3/R4's naming of what is left (a report line about a
  leftover must be true of the host); minor correctness risk on an edge path.

### PLAUSIBLE findings

- None.

### Coverage observations (seeded)

Deeper layers of classes a row already pins. Not findings. S09 and S10 are already in
`issues/disk-image-fixture-deeper-pins.md`; H01/H02 is new and joins that seed with the build.

- **S09** — the head of stderr instead of its tail survives both eras: the seed's item 3.
- **S10** — the poll after the stop removed survives both eras: the seed's item 1.
- **H01** — a mutant of the pin's driver, not the fixture: `_drive_image` letting `Skipped` and
  `XFailed` escape leaves the run green with "37 passed, 1 skipped, 1 xfailed".
- **H02** — H01 plus carve-out B04 (skip) is green with "2 skipped, 1 xfailed": the carve-out goes
  unseen. `test_only_need_shell_skips` does not read an outcome type carried through an argument
  (its documented limit), so the driver's catch-all is the only guard against a pin row that skips.
  Within the build-gate ruling (no row skips today); a deeper layer of the no-skip class.

### Human-gate triggers

- Not triggered. F3–F5 are in `tests/test_ssh_exec.py`, which is not on the high-blast-radius list
  in `AGENTS.md` § Invariants, and none violates a section tagged *[human gate]*. The diff touches
  no path on that list. No earlier cycle recorded a trigger.

### Routing

`code build`, each finding as its property and its whole domain:

- **F3:** however a step's wait ends (on time, failed, past its bound, or cut short by any
  exception raised in the waiting process: a terminal's SIGINT as `KeyboardInterrupt`, a pytest
  outcome, `SystemExit`), the step's process group is stopped and waited for (R1) before the
  exception goes on; and a `create` or `attach` cut short that way leaves no device and no image,
  as R3 asks of a hung one. The completeness side, both ways: the interrupt still propagates as
  itself, never swallowed or turned into a pass or a different failure. Pin it with rows across
  that domain (each step, each kind of exception), in both eras. Whether the cleanup's own steps
  run under an interrupt, and at what bound, is a trade between liveness and completeness: bring the
  figures to the maintainer.
- **F4:** for each way R5 names (the fill, its assertion, the test's own assertions inside the
  `with`), a row whose body fails that way: with a `detach` that succeeds, the body's own exception
  raised unchanged and nothing left; with one that fails, both reported, the body's first, and the
  leftovers named. The fill fails as the fill does (an `OSError` from the write).
- **F5:** every line the fixture reports about what is left is true of the host when it is
  written: when the cleanup cannot list devices, it names the image only if the image exists (and
  says so when it does not), never a file that is not there. Completeness side: an image that
  exists is still kept and named.
- **Seed:** H01/H02 joins `issues/disk-image-fixture-deeper-pins.md` as one more item (the pin's
  driver is the only guard against a row that skips), with its `ROADMAP.md` entry's count updated.

Cycle 2 did not converge (three new findings, all outside cycle 1's routed domains). Per
`code-review` Step 6, this is escalated to the maintainer before a third build round.

### Reviewer conduct (verified by the orchestrator)

- `git status --porcelain` empty after the hand-back; `tests/test_ssh_exec.py` in the worktree is
  HEAD's.
- `.venv`: `uv pip freeze` identical before the orchestrator's gates and after the reviewer.
- `hdiutil info`: no images before the cycle's runs, after the gates, and after the reviewer
  (`.local/review2/orch/hdiutil-info-before.txt`, `.local/review2/ev/hdiutil-info-after.txt`). No
  image was attached or detached by this cycle.
- No stand-in, `hdiutil`, `newfs_hfs` or pytest process left.
- Mutants ran only in archive copies under `.local/review2/`; evidence in `.local/review2/ev/`;
  `DONE` written last.
- `cluster-mcp-sandbox.*` directories in `$TMPDIR`: 6660 before the cycle's runs, 6876 after the
  reviewer's full verify (the known leak, `issues/sandbox-dirs-left-on-kill.md`, outside this
  GOAL). Left alone.

### Reviewer hand-back (as returned)

Lightly trimmed for the public record (host paths dropped); its findings, observations, matrix and
conduct notes are as returned.

> **Summary.** One new MEDIUM, two LOW, four coverage observations. Both cycle-1 findings are closed
> as properties, with one LOW caveat on F2's domain (finding 2).
>
> **Findings.**
> 1. MEDIUM, CONFIRMED: an interrupt (Ctrl-C) while a disk-image step runs leaves the step,
>    everything it started, and its image and device. A regression: `start_new_session=True` now
>    shields the step from the terminal's SIGINT, and the fixture never stops it (`_step`, the Popen
>    and the `TimeoutExpired`-only handler; every caller). Probe through `bin/sandbox.sh`: HEAD, 3
>    pids still running; with image and device in the plan, 3 still running, image exists, device
>    `/dev/standin2` attached; base-style launch, none running. Not reproduced: whether real
>    `hdiutil` exits on SIGINT; the mechanism is shown.
> 2. LOW, CONFIRMED: the fill's own failure is a class no row raises; an additive `OSError` carve-out
>    in the body handler (B12) survives in both eras, 39 passed each. Drawn by R5's wording; if
>    `Exception` is held pinned by the assertion and `Exit` rows, it is a coverage observation.
> 3. LOW, CONFIRMED: when the cleanup's `info` fails or answers garbled, the report says the image is
>    kept even when it does not exist (`image_exists: false` in both probes); the step's own R2
>    failure is still first.
>
> **Coverage observations.** S09 (stderr head) and S10 (the poll removed) survive both eras, seed
> items 3 and 1. H01: `_drive_image` letting `Skipped`/`XFailed` escape is green ("37 passed, 1
> skipped, 1 xfailed"). H02: H01 plus carve-out B04 is green ("2 skipped, 1 xfailed");
> `test_only_need_shell_skips` cannot see `_raises(pytest.skip.Exception)` by its documented limit,
> so the driver's catch-all is the only guard against a silent skip.
>
> **Cycle 1.** F1 closed as a property (every `tests/*.py` named; the four new tests named; the
> stand-in's interface matches). F2 closed as a property for every class directly under
> `BaseException`, each pytest outcome and a bare class; its own sweep, 43 cases × 2 eras: B01 (M32),
> B02–B11, B13, B14, B20–B24, D01, D02, S01–S08, C01–C07, A01, A02 killed; B12, S09, S10, H01, H02
> survived. The tree's `need_sftp_server()` instance is the `body-pytest-fail` rows.
>
> **Matrix.** R1 met except an interrupted step (1); R2 met (tail unpinned, S09); R3 met, its text
> after a failed `info` can be false (3); R4 met; R5 met except the fill's `OSError` (2); R6 met
> (real rows both eras, Linux CI green, 0 skipped); R7 met, the skip guard rests on the driver (H01).
>
> **Scope creep:** none under `packages/`; the extra rows, the `info` verb and its bound and the
> `garbled` plan pin R3–R5; the seed and ROADMAP entry are accurate as prose.
>
> **Verification.** Pin tests plus real rows 42 passed per era; its sweep 497 s wall; the full
> verify once, all ten commands rc=0 (the wrapper's own last line reads rc=1, not a gate); CI run
> 42788859429 green.
>
> **Conduct.** Tree clean; `.venv` freeze diff empty; `hdiutil info` no images before or after, none
> attached or detached; no process left; mutants only in archive copies, restored; evidence in
> `.local/review2/ev/`; `DONE` written.
