---
slug: full-volume-fixture-leaks-hdiutil
title: A disk-image step that hangs or fails is stopped, and the full-volume fixture leaves nothing behind
kind: test
appetite: small
status: blocked
branch: test/full-volume-fixture-leaks-hdiutil
base: develop
current_phase: done
last_updated: '2026-11-12'
phases:
- id: P1
  name: Each hdiutil step runs in its own group under its bound; a hung or failed one is stopped and named
  status: done
  satisfies:
  - R1
  - R2
  - R6
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p1
- id: P2
  name: A failed create or attach is cleaned up; a failed detach is kept and named, after the body's failure
  status: done
  satisfies:
  - R3
  - R4
  - R5
  - R7
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p2
- id: P3
  name: The mutant sweep, the docs, the ledger and the full gate
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  - R6
  - R7
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh --around sh spec/full-volume-fixture-leaks-hdiutil/remediation/seed-in-scope.sh sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh pre && sh spec/full-volume-fixture-leaks-hdiutil/remediation/F1-every-test-module-named.sh && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py rows && sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh sweep-a && sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh sweep-b && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py frozen-legacy && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py frozen-modern && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py prior-legacy-a && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py prior-legacy-b && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py prior-modern-a && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py prior-modern-b && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py new-legacy-a && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py new-legacy-b && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py new-modern-a && UV_PYTHON=3.14 uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py new-modern-b && sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh full
review:
  last_reviewed_commit: 76123740b8378f57da720a99826d0773517ab765
  verdict: changes-requested
  blocked_reason: 'Review cycle 3: F6 an interrupt during a failed or hung step''s cleanup or stop drops the step''s failure and what is left (failure-path sibling of cycle 2''s F3); not converged at cycle 3, escalated'
  cycle: 3
---

# TECH.md — A disk-image step that hangs or fails is stopped, and the full-volume fixture leaves nothing behind

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/full-volume-fixture-leaks-hdiutil/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/01-probes.md`](research/01-probes.md) (lean path: executed probes, no digest).

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`).
  **Artifact-deliverable R-IDs.** Some requirements are met by a *committed document* — a research
  audit, a protocol doc, an assessment — not by CLI-observable behaviour. Attach such an R-ID to the
  phase that produces and commits the artifact, and give that phase a content `verify:`
  (`test -f …`, a `grep -q` for the sections that must exist) rather than forcing a CLI drive.
  **Say so in the phase body**, because it changes who can grade it: `code-review` blinds its reviewer
  to all of `spec/`, so an R-ID whose evidence lives there is graded by the *orchestrator*, not the
  blind reviewer. Naming it in `TECH.md` is what lets the review skill route it correctly instead of
  reporting an unverifiable requirement.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work (docs, tests, isolated leaf
  modules). Any phase touching the profile's `coupled core` is always `false`.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase (prefer driving the real CLI, not just tests —
  wrap CLI drives in the profile's `throwaway environment` helper, `<helper> sh -c "…"`, so they hit
  a disposable instance, never the developer's real data). A gate carrying `$( )` or quoting the
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`.
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation (mpsearch's
  `## Times` quote, taken as `code-build` Step 4 says). A plan that drops one says why in `PLAN.md`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.

Cycle-specific, every phase:

- **The figures.** `STOP_WAIT` = 5 s and `SHORT_BOUND` = 1 s, the values the maintainer signed at
  the PLAN/TECH gate (2026-11-09; PLAN §3, deviation row 5; Amendments below). The figures test pins
  both.
- No file under `packages/`, `bin/` or `.github/` changes; no skip of any kind; no spec id in either
  file (row ids included); every new test carries `unit` or `integration`; no test name contains
  `silent`. Every launch in the two files is a `REAL_POPEN` call (the stand-in forks and launches
  nothing). Every launch the rows make (each stand-in step, each `ps`) starts with `bin/sandbox.sh`;
  only the real `hdiutil` steps do not, as `_host`'s do not today (Amendments below).
- Run gates from the cycle worktree root, staged, with `UV_PYTHON=3.14` (the gate scripts export it).
  Each gate kills nothing it did not start; the rows' own teardown KILLs every pid the stand-in
  recorded.

## Amendments

- **2026-11-09, the PLAN/TECH gate rulings** (recorded at P1's build):
  - The foreman accepted PLAN §3's deviation rows 1–4 and 6–8.
  - The maintainer approved **T2 = `STOP_WAIT` = 5 s** and **T3 = `SHORT_BOUND` = 1 s** (voice,
    2026-11-09). Come-back: if a CI suite job lands more than 30 s above PLAN §3's projected figures
    (`suite-legacy-2` ~2:58, `suite-modern-2` ~6:00), the figures go back to the maintainer. Every CI
    run stays under the maintainer's 15-minute wall envelope.
  - Foreman ruling (the marker wording a sibling cycle settles: "every process an integration test
    launches goes through `bin/sandbox.sh`"): the `hdiutil` stand-in the rows launch goes through
    `bin/sandbox.sh`; the real `hdiutil` path through `REAL_POPEN` stays as `_host` has it (that gap
    is seeded elsewhere). Built as: the rows' `hdiutil` argv is `bin/sandbox.sh`, the interpreter,
    `-I`, the stand-in and `STATE`, so the group `_step` leads and the stop KILLs is the sandbox
    script's, holding the stand-in and its child; the stand-in exits 2 unless its working directory
    is the sandbox `CLUSTER_MCP_SANDBOX` names (a row whose stand-in ran unsandboxed fails); the
    `ps` listing `_processes()` reads runs through `bin/sandbox.sh` too; and each row sets `TMPDIR`
    to its `tmp_path`, so the directory a KILLed sandbox script leaves goes with the row
    (`sandbox-dirs-left-on-kill` stays its own cycle). PLAN §2, §3 and §5 amended to match. Every
    R-ID is kept; no row, test name or gate changes.
- **2026-11-10, P1 gate attempt 1: red from outside the phase.** Both eras passed all nine ids by
  exact id, and no stand-in was left. The leftover check then failed on a disk image an earlier suite
  run had attached on the build host hours before, its device attached and unmounted and its
  disk-image helper still running: the leak this cycle fixes, left by the fixture as it was. The
  check matches any image under the pytest temp root, so it reads that image as the rows'. The
  annotation step (159 functions) and the hygiene module, run by hand on the same tree, were green.
  The gate kills nothing it did not start, so the image stays until the maintainer clears it; P1
  then re-runs its gate unchanged.
- **2026-11-10, P1's gate runs the frozen `verify/rows.sh p1` under a wrapper** (foreman ruling,
  code-build's frozen-gate wrapper rule): `remediation/scoped-leftovers.sh p1`. Which gate: rows.sh's
  `leftovers` step. Why: it reads any image under a pytest temp root, and any stand-in process, as
  the rows'; other suites on the build host still run the fixture as it was and can leak an image
  while the gate runs, so the step goes red on host state no row made (seen red first: attempt 1
  above; that image was ejected before the re-run). The wrapper runs rows.sh unchanged with pytest's
  `--basetemp` set to a directory of its own whose name carries `pytest-of-` and a unique token, and
  with two PATH shims that drop, from exactly rows.sh's `hdiutil info` and `ps -A -ww -o stat= -o
  args=`, each line naming a temp root or the stand-in without the token; every other call runs the
  real tool. Every other check of rows.sh stays as it is. After a green rows.sh it asserts the rows ran
  under its base directory and the leftover step read both shims, so the scoping is never vacuous.
  Shown before use, each with all nine ids passing in both eras: an image attached under the run's
  base directory, red ("a disk image the rows made is still attached"); a hanging stand-in under it,
  red ("a stand-in process is still running"); a foreign image and a foreign stand-in under another
  `pytest-of-…/pytest-9999`, green, with rows.sh unwrapped red on the same state. P2's `verify:`
  (`rows.sh p2`) and P3's `pre` (`rows.sh all`) run rows.sh directly and have the same exposure; each
  takes the wrapper (`… scoped-leftovers.sh p2`, `… all`) when it is built, on the foreman's word.
- **2026-11-10, a sibling seed's name:** this cycle removes `_host` from `tests/test_ssh_exec.py`;
  every `hdiutil` step now runs through `_step` (the real tool still through `REAL_POPEN`, outside
  `bin/sandbox.sh`). `issues/marker-rule-gaps.md` (from `integration-marker-wording`, item 4 and its
  R3) names `_host`: whichever of the two cycles lands second adds a dated correction line to that
  seed naming `_step`.
- **2026-11-10, P2's and P3's gates take the wrapper too** (foreman ruling, at P2's build): P2's
  `verify:` is retuned through `set_phase.py` to `sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p2`,
  which runs the frozen `verify/rows.sh p2` unchanged with the leftover checks scoped as above. P3's
  `pre` (`rows.sh all`) takes `… scoped-leftovers.sh all` when P3's build starts, recorded then.
- **2026-11-10, P3's gate (foreman ruling, at P3's build).** `verify/p3.sh` is frozen, and its `pre`
  runs `rows.sh all` itself, so the wrapper gained an `--around CMD…` form that runs a whole gate
  under the same scoping and checks. P3's `verify:` is retuned through `set_phase.py` to `p3.sh all`'s
  four modes in its order, with `pre` alone under the wrapper:
  `scoped-leftovers.sh --around sh verify/p3.sh pre && sh verify/p3.sh sweep-a && sh verify/p3.sh
  sweep-b && sh verify/p3.sh full`. In `all` mode a hygiene pytest reuses the base directory after the
  leftover step, so the wrapper's proof that the rows ran under its base directory moved into the
  `ps` shim, taken at the moment the leftover step reads it (shown red when the base directory is
  not the rows': see P3's report). The sweep's `bound-constant` case sits in mode `a`, the smaller
  half by count; PLAN §6's `figures` case is planted as two (`figures-bound`, `figures-wait`), so
  the sweep has 40 cases, 26 decisions and 14 carve-outs.

- **2026-11-10, review cycle 1 remediation (F1, F2 and the seed), P3 reopened.** `REVIEW.md` cycle
  1 routed two MEDIUM findings to build. Both map to P3, which satisfies R1–R7 and owns the docs, the
  sweep and the full gate, so P3 alone is reopened (`set_phase.py --phase P3 --phase-status
  in_progress`); P1's and P2's gates run a subset of P3's `pre` (`rows.sh all`), so reopening them
  would add no evidence. The fixture's code (`_bounds` to `attached_image`) is unchanged: the review
  found it correct and the pins short.
  - **F1:** `AGENTS.md` § Testing names `tests/hdiutil_standin.py` (a helper, not collected), its
    argv, its state files (`plan.json`, `devices.json`, `pids`) and its sandbox rule, and the `unit`
    tests `test_the_disk_image_figures` and `test_every_way_a_body_can_end_has_its_rows`. The
    predicate is evaluated over every `tests/*.py` (46 modules), not one name:
    `remediation/F1-every-test-module-named.sh`. Seen red first on the reviewed `AGENTS.md`
    (`does not name tests/hdiutil_standin.py`, and nothing else) and on a planted copy without two of
    the interface words. No durable check is cited in the manual.
  - **F2, the rows:** `BODY_EXITS` lists every way a body can end by raising: an assertion, pytest's
    `fail`, `skip`, `xfail` and `exit` outcomes, each class Python puts directly under
    `BaseException` (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`, `BaseExceptionGroup`; an
    `Exception` is the assertion) and a class none of those names. Each kind has two rows, a `detach`
    that succeeds (the body's own exception raised unchanged, nothing left) and one that fails (both
    reported, the body's first, the leftovers named): `body-fails` and `body-and-detach-fail` for the
    assertion, `body-{kind}` and `body-{kind}-and-detach-fail` for the other nine, 18 new rows.
    `_drive_image` catches whatever the body raises (a real interrupt it did not raise is raised
    on). `test_every_way_a_body_can_end_has_its_rows` (`unit`) holds the list against Python's and
    pytest's classes, so a class either adds fails until it has its rows. pytest's skip and xfail
    outcomes are raised as their exception types, only inside a row's body, and always caught: no
    test skips (`test_only_need_shell_skips` stays green; it does not read a raise through an
    argument, which the report raises as a question). The review's M32 (`except Exception`) survives
    the reviewed rows (19 passed on an archive of 6650254, re-run here) and is killed by the new ones.
  - **F2, the sweep:** `remediation/F2-fixture-sweep.py` derives its case list and checks it
    (`coverage`): every line of the fixture's seven functions that holds a decision node (a branch,
    a handler, an exit, a comparison, a call that starts, bounds, stops, waits for, detaches or
    removes something; 71 lines, read from the AST) is changed by some case, the frozen 40 included;
    and each of the ten body exits gets seven families (a narrowed catch, a skipped detach, a
    skipped removal, an early return before the detach and one after it, a dropped cause, a dropped
    name of what is left), plus `narrow-to-exception` (M32). 123 new cases. It runs the new cases in
    both eras (`new-legacy-a`/`-b`, `new-modern-a`/`-b`) and the frozen 40 in the 2026-07-28 era
    (`frozen-modern`); the frozen gate (`p3.sh sweep-a`, `sweep-b`) runs those 40 in the handshake
    era, unchanged. A cheap pass found seven survivors: two cases of this checker's own that did
    not plant (an edit that cut a line short, fixed), three aimed at the wrong row (re-aimed at the
    survivor test and a new row), and two seeded (below). The sweep's own finding, a failing step
    that started nothing (its group gone when `killpg` runs, so the `ProcessLookupError` it
    suppresses is reached), gets a row: `create-fails-alone`. The rows also now say nothing of an
    image kept or a device attached where none was, and the figures test pins `_bounds`' override and
    its refusal of an unknown verb.
  - **Expected survivors** (12, each run against every disk-image id): seeded, the review's six
    (M03 `stop-poll-once`, M30 `cleanup-first-entry-only`, M19 `stderr-head`, M17
    `group-zombies-counted`, M24 `stop-eperm-raised`, M25 `ps-self-unchecked`) and five more of the
    same kind (`ps-self-returns`, `stop-streams-open`, `listing-type-unchecked`,
    `stop-leader-unwaited`, `cleanup-deviceless-detached`); equivalent, one (`mount-point-unmade`:
    `hdiutil attach -mountpoint` makes a missing directory itself and `detach` removes it, probed
    with the real tool on the build host, its image detached and removed, `hdiutil info` as before).
    The seed is filed as `issues/disk-image-fixture-deeper-pins.md`, with its ROADMAP.md entry.
  - **P3's `verify:`** is retuned through `set_phase.py --verify-file` (read back byte-identical):
    `pre` under `scoped-leftovers.sh --around` and a second wrapper, `remediation/seed-in-scope.sh`,
    then the F1 checker, `F2-fixture-sweep.py rows`, `p3.sh sweep-a`, `sweep-b`, the five sweep
    modes, and `p3.sh full`. Why the second wrapper: `p3.sh`'s frozen `scope` grades every path since
    the plan commit against the cycle's own files, and the seed the review routed lies outside them
    (seen red first: `pre` under `scoped-leftovers.sh` alone, `files outside the cycle's scope
    changed: issues/disk-image-fixture-deeper-pins.md, ROADMAP.md`). The wrapper checks the two paths
    itself (the seed `status: unshaped`, its ROADMAP link, ROADMAP losing only the counts the entry
    moves; each shown red on a plant, then restored) and drops exactly them from `scope`'s two diffs.
  - **Committed apart, gated once.** The gate ran on the combined tree, everything staged; the fix
    and this state commit first, the seed and its ROADMAP entry second.
  - **The gate's run** (build host, macOS 27, `UV_PYTHON=3.14`, the staged tree, 03:11 to 04:09,
    load average 14 to 24 at the start, about 2.5 at the end): green. `pre` ok under both wrappers
    (22 ids per era, hygiene 142 passed); F1 ok (46 modules); `rows` 39 ids passed in each era,
    none skipped; `sweep-a` 19 of 19 killed (4.3 min), `sweep-b` 21 of 21 (1.4 min);
    `frozen-modern` 40 of 40 killed (5.5 min); `new-legacy-a` and `new-modern-a` each 53 cases, 41
    killed, 11 seeded and 1 equivalent survived as expected, none else (6.2 and 6.3 min);
    `new-legacy-b` and `new-modern-b` each 70 of 70 killed (2.6 min each); `full` per era 44, 193,
    507, and 4369 passed with 14 skipped (modules this cycle does not touch), and the CLI's usage.
    No unviable case, no timeout, no process left; `hdiutil info` the same before and after.
  - **Suite cost:** 20 more tests in the `-k 'not silent'` part (173 to 193 per era). The disk-image
    tests, base (`6650254`) and branch back to back on the build host at load about 2.4, twice each:
    13.7 s and 13.5 s, then 17.9 s and 18.1 s, about 4.5 s more per era (the part's 163 s and 174 s
    above, under 3%). No figure changes.

- **2026-11-12, review cycle 2 remediation (F3, F4, F5 and the seed), P3 reopened.** `REVIEW.md`
  cycle 2 routed one MEDIUM and two LOW findings to build, with the maintainer's ruling on the
  cleanup under an interrupt (the foreman's routing: the cleanup runs at today's per-step bounds, no
  new timing figure; a second interrupt abandons it, and the report names what is left). P3 is
  reopened alone (`set_phase.py --phase P3 --phase-status in_progress --current P3`), for review
  cycle 1's reason. No figure changes.
  - **F3, the fix.** `_step` handles a wait that any exception cuts short (`except BaseException`
    after the bound's arm): `_cut_short` stops the step's group as `_stop` does, notes on the
    exception that it was stopped and anything still running, and the exception goes on as itself.
    A cut `create` or `attach` (now `_create_and_attach`) gets the cleanup a failed one gets, each
    step at its own bound (`_clean_up_after`), what it leaves noted on the exception; the detach
    after the body moved into `_in_use`, whose cut is noted by `attached_image` with the volume and
    image it keeps, never tried again. A second exception during the stop or the cleanup abandons
    it and goes on in the first one's place, with the first as its context (Python's own chaining;
    the first is never swallowed into a pass or a `HostFailure`), naming what is left: the image if
    it is there and any device made from it, or that there is none. Every text the frozen sweep and
    F2's cases plant on is kept, so both plant unchanged. Shown with the stand-in only: the step,
    in a session of its own, gets no signal; how real `hdiutil` takes SIGINT is not claimed.
  - **F3, the rows.** `test_a_disk_image_step_cut_short_is_stopped_and_its_exception_goes_on`
    raises each `BODY_EXITS` kind from the test's own SIGINT handler (SIGINT to the main thread
    only, once the stand-in has reached its hang) at nine places: `create` (with and without a
    device), `attach`, the `detach` after the body (and after a failed body), and, after a first
    cut, a failed cleanup `detach`, and a second interrupt at the cleanup's `info` (with and without
    an image) and its `detach`. The suite runs each kind where the whole cleanup follows and an
    interrupt everywhere (19 rows); `CLUSTER_MCP_TEST_EVERY_KIND=1`, which the suite never sets,
    runs every kind at every place (99 rows), and the checker sets it and asserts it collected
    them. `test_a_disk_image_step_cut_short_still_running_is_named` pins the survivors' naming on
    the cut path, and `test_a_disk_image_step_whose_stop_is_cut_short_names_its_group` a second
    interrupt inside the stop (CONT, so the 5 s wait lasts; fired 1 s after the first, past the
    0.25 s `communicate` itself waits on an interrupt). The row checks are shared (`_what_is_left`).
  - **F4:** `BODY_EXITS` gains `fill`, an `OSError` (ENOSPC) as the fill's write raises, with its two
    rows; `test_every_way_a_body_can_end_has_its_rows` asks for an assertion and an `OSError`, and
    for a cut row per kind and an interrupt's row per place. B12 (`narrow-past-fill`) is killed.
  - **F5:** `_clean_up` names the image only when it is there after a failed or garbled `info`
    ("there is no image at …"), and still keeps and names one that is; the abandoned cleanup uses
    the same rule. Rows `info-fails-without-image`, `info-answers-garbled-without-image`.
  - **The sweep.** `remediation/F3-F5-fixture-sweep.py` supersedes `F2-fixture-sweep.py` (kept as
    the record: its `coverage` reads the fixture as it was, so it is red now, and every F2 mode runs
    it first). It takes F2's 123 cases (nine re-aimed, below) and the frozen 40, adds 118 (34
    decisions; the 7 body families for `fill`; 7 cut families × 11 kinds), and checks that every
    one of 99 decision lines in 11 functions is changed by a case. It reads a row's `why` in the
    failure's message alone: F2 and the frozen runner match it in the message plus the traceback,
    which prints the failing test's source, so any failure of that test matched (seen first on
    `ps-pgid-not-read`, killed by "is not named", not the "does not say" it named). Under that rule
    eight F2 cases name the words their rows fail with (each still killed, by the decision it
    plants), and `step-hang-uncaught` names no `HostFailure` (the cut path now stops the step).
    Survivors: F2's 12 as before (11 seeded, 1 equivalent), and one new, equivalent:
    `detach-cut-named-on-failure` (a failed detach's `HostFailure` already carries the line, so the
    report repeats a true line). No new seeded survivor.
  - **P3's `verify:`** is retuned through `set_phase.py --verify-file` (read back byte-identical):
    F2's modes give way to the checker's `rows`, `frozen-legacy`, `frozen-modern`, `prior-*` and
    `new-*`; the frozen gate (`p3.sh sweep-a`, `sweep-b`) and `pre` under both wrappers stay.
  - **The seed:** H01/H02 joins `issues/disk-image-fixture-deeper-pins.md` as item 12 with a draft
    R6, and its `ROADMAP.md` entry's count; committed apart.
  - **The runs** (build host, macOS 27, `UV_PYTHON=3.14`, load 2.1 to 7.4): light gates on the final tree: `pre`
    under both wrappers ok (55 s); F1 ok (46 modules); the checker's `rows` 144 ids per era with the
    opt-in (99 cut rows), none skipped (130 s); 64 disk-image ids in the suite. The sweep, every mode
    on the final fixture and tests: `new-legacy-a` and `new-modern-a` 67 of 67 killed (2.8 min
    each); `new-legacy-b` and `new-modern-b` 51 each, 50 killed and the 1 equivalent survived as
    expected (4.1 and 4.2 min); `prior-legacy-a` and `prior-modern-a` 53 each, 41 killed, 11 seeded
    and 1 equivalent survived as expected (8.7 and 8.8 min); `prior-legacy-b` and `prior-modern-b` 70
    of 70 (2.5 min each); `frozen-legacy` and `frozen-modern` 40 of 40 (5.4 min each); the frozen gate
    `p3.sh sweep-a` 19 of 19 (4.2 min) and `sweep-b` 21 of 21 (1.4 min). No unviable case, no timeout,
    no process left; `hdiutil info` names no image of the rows. Red on the way, each fixed in the run
    and rerun from the start of its mode: `prior-legacy-a` and `prior-modern-a` (the re-aims above),
    `new-legacy-b` (`made-failure-dropped`, its own `why` matched only in the source, re-aimed to its
    message). `p3.sh full` ran last, on the committed tree (`7db4fee`), below.
  - **Suite cost:** 25 more tests in the `-k 'not silent'` part (193 to 218 per era). The disk-image
    tests, base (HEAD's tests) and branch back to back, twice per era, load about 2.5: 18.0 s and
    30.4 s each time, about 12.4 s more per era (the part's 163 s and 174 s above, about 7%). Most is
    the cut rows: each interrupt also waits out `communicate`'s own 0.25 s. No figure changes.
  - **The full gate** (`p3.sh full`, the profile's verify, on `7db4fee`, 2026-11-12, load about 2.6,
    26.6 min wall): green, every command exit 0. `uv lock --check`; per era `-k silent` 44 passed
    (212 s, 212 s), `-k 'not silent'` 218 passed (173 s legacy, 175 s modern; 193 passed in 163 s
    and 174 s at review cycle 1's gate), the timeout/startup/launch trio 507 passed, the rest 4369
    passed with 14 skipped (modules this cycle does not touch) and one warning from
    `tests/test_tokens.py` (a short HMAC key, outside the cycle); the CLI printed its usage. No
    stand-in process left; `hdiutil info` names no image of the rows. With the light gates and sweep
    modes above, every step of P3's `verify:` is green on this tree.

---

## Phase P1 — Each hdiutil step runs in its own group under its bound; a hung or failed one is stopped and named
**Satisfies:** R1, R2, R6, R7 · **Depends on:** —
**Goal:** every `hdiutil` verb the fixture runs goes through `_step`; a hang or a failure is KILLed
with its group, waited on up to `STOP_WAIT`, and reported with the verb, how it ended and any
survivor; the success path is today's; the stand-in exists and the rows that need no cleanup pass.

- [x] `tests/test_ssh_exec.py`: add the module constants (`HDIUTIL_BOUND`, `STOP_WAIT`,
      `STOP_SIGNAL`, `HDIUTIL_VERBS`), `HostFailure`, `_bounds`, `_processes`, `_group`, `_stop` and
      `_step` as PLAN §2 specifies (KILL suppressing `ProcessLookupError` and `PermissionError`;
      `ps` with one `-o` per field, refusing a listing without this process; the wait ignoring `Z`;
      the two failure texts; the survivor text). Remove `_host`.
- [x] Split `full_volume` into `attached_image(where, hdiutil=('hdiutil',), bounds=None)` and the
      fill (`full_volume`, unchanged in effect). In this phase a failed or hung `create`/`attach`
      raises `HostFailure(failure)` and a failed `detach` raises `HostFailure(failure)`; a body that
      fails with a good `detach` has its image removed and its own exception re-raised. P2 adds the
      cleanup and the texts R4 and R5 need.
- [x] `tests/hdiutil_standin.py` whole, as PLAN §2 specifies (per-call plans, one handling of
      `image`, `device`, `child` and the ending for every verb; a hang and its child survive TERM and
      record it; a failing verb's child drops its streams; `info -plist` with a `/./` path and
      `mount-point`, and `garbled`; `detach` by whole device or mount point only; `STATE` in every
      argv). It forks and launches nothing, runs only through `bin/sandbox.sh` (exit 2 otherwise),
      and its module docstring states what it is.
- [x] The row harness (`HDIUTIL_STANDIN`, `SHORT_BOUND`, `EASY_BOUND`, `ROW_LIMIT`,
      `PAST`, `FAILS`, `HANGS`, `DISK_IMAGE_ROWS` with this phase's rows `create-hangs`,
      `create-fails`, `every-step-succeeds`, `body-fails`, `_left_running`, `FOREIGN`, `_stand_in`
      seeding the foreign device, `_kill_recorded` of what is still running) and
      `test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running`, asserting all of PLAN §2's
      row checks (leftover processes, own devices and the foreign one, image, texts in order in
      `traceback.format_exception`, no false survivor, no TERM, the run within `ROW_LIMIT`, each
      planned hang reached).
- [x] `test_a_stopped_step_still_running_is_named` (SIGCONT, 0.5 s, the window
      `[SHORT_BOUND + 0.5, SHORT_BOUND + 3.5)`) and `test_the_disk_image_figures`.
- **Verify:** `sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p1`, which runs
  `verify/rows.sh p1` unchanged with its leftover checks scoped to the run (Amendments): the six P1 ids and
  the three real `out_of_room` rows (real `hdiutil` on the build Mac, R6), each by exact id, in both
  eras; no stand-in process and no image of the rows' left; every function in both files resolves
  its annotations. Dry-run on a P1-cut prototype: green; P2's ids on that tree: 11 red.
- **Touches:** `tests/test_ssh_exec.py`, `tests/hdiutil_standin.py`.

## Phase P2 — A failed create or attach is cleaned up; a failed detach is kept and named, after the body's failure
**Satisfies:** R3, R4, R5, R7 · **Depends on:** P1
**Goal:** the cleanup R3 asks (find devices by `info`, detach each whole disk, remove the image), the
"no further attempt" and the named leftovers of R4, and the body-first report of R5.

- [x] `_clean_up(hdiutil, bound, image)` as PLAN §2 specifies (`info` through `_step`; an `info`
      failure, or an answer that is not a plist, keeps the image and says so; `realpath` match; the shortest `dev-entry`; stop at the
      first failed detach and name the device, its `mount-point` or ", not mounted", and the kept
      image; `unlink(missing_ok=True)` only when every device detached).
- [x] `attached_image`: a failed or hung `create`/`attach` raises `HostFailure` with the step's text
      then `_clean_up`'s, in that order; after the body, a failed `detach` raises with the step's
      text and "the volume stays attached at {where}, and its image is kept at {image}", `from body`
      when the body raised; no second detach anywhere after a failed one; the image removed only after
      a detach that succeeded.
- [x] Add the rows `create-hangs-with-device`, `create-fails-with-device`, `attach-hangs`,
      `attach-hangs-with-device`, `attach-fails`, `attach-fails-with-device`, `detach-hangs`,
      `detach-fails`, `body-and-detach-fail`, `cleanup-detach-hangs`, `cleanup-detach-fails`,
      `info-fails-in-cleanup`, `info-answers-garbled` (PLAN §2's table; a failing `detach` or `info` is planned for its first call only, so a retry
      would succeed and show).
- **Verify:** `sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p2`, which runs
  `verify/rows.sh p2` unchanged with its leftover checks scoped to the run (Amendments): every P1 and P2 id and
  the real rows, in both eras, plus the leftovers and annotation checks.
- **Touches:** `tests/test_ssh_exec.py`.

## Phase P3 — The mutant sweep, the docs, the ledger and the full gate
**Satisfies:** R1–R7 (the sweep proves the rows pin them) · **Depends on:** P2
**Goal:** every decision the fixture makes, and every carve-out it must not have, is shown pinned
by a row; the docs say what the fixture does; the full gate is green.

- [x] Write `spec/full-volume-fixture-leaks-hdiutil/verify/mutants.py`, the sweep PLAN §6
      specifies: every case in PLAN §6's two tables (existing decisions and additive carve-outs), each
      an exact edit that applies once to a pristine copy of `tests/` (or it is red), run on its named
      rows in a fresh `mktemp -d` copy of `tests/` and the top-level files, one case at a time, one
      era, `-p no:cacheprovider`, a 300 s cap per case with the case's process group KILLed at it
      (started under its own session; a check by a token in the case's argv, never `pgrep -f` on
      text the calling shell also holds, finds nothing after);
      a case passes only when every named row fails with its `why`. Modes `a` and `b` split the cases
      so each mode's measured run is under ten minutes (`bound-constant`, about 2 min alone, goes in
      the smaller half). A header comment states the footprint (one pytest at a time, about 6
      processes, under 500 MB) and the measured time of each mode.
- [x] Record the sweep in `spec/full-volume-fixture-leaks-hdiutil/verify/mutant-sweep.md`: each
      case, its rows, killed or not, and each mode's measured time (the run named).
- [x] `AGENTS.md` § Testing, the `test_ssh_exec.py` bullet, after the
      `test_a_write_that_runs_out_of_room_keeps_the_file[…]` sentence: the clause PLAN §2 "Docs"
      gives, naming `test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running` and
      `test_a_stopped_step_still_running_is_named`. Nothing else in `AGENTS.md`.
- [x] `tests/test_ssh_exec.py` module docstring: one paragraph for the stand-in rows.
- [x] Deferral ledger: walk P1–P3's bodies and PLAN for every deferral phrase `p3.sh`'s `ledger`
      lists; each must name an `issues/` seed with a `ROADMAP.md` entry (none is planned).
      `p3.sh pre` checks it, reading prose and list items, never headings.
- [x] Note in the phase's report: the rows' first Linux run is the cycle branch's CI (PLAN §5).
- [x] Review cycle 1, F1 (Amendments): `AGENTS.md` § Testing names `tests/hdiutil_standin.py` as a
      helper, not collected, with its interface, and the `unit` tests `test_the_disk_image_figures`
      and `test_every_way_a_body_can_end_has_its_rows`; `remediation/F1-every-test-module-named.sh`
      checks every `tests/*.py` is named.
- [x] Review cycle 1, F2 (Amendments): `BODY_EXITS` and two rows per way the body can end (a `detach`
      that succeeds, one that fails); `test_every_way_a_body_can_end_has_its_rows`; the rows' report
      names no image or device left where none was; `_bounds`' override and refusal in the figures
      test; `remediation/F2-fixture-sweep.py` (its derived case list, both eras, additive families).
- [x] Review cycle 1, the seeds: the review's six coverage observations and the sweep's other
      survivors as one seed, `issues/disk-image-fixture-deeper-pins.md`, with its `ROADMAP.md` Part I
      entry and the counts it moves; committed apart (Amendments).
- [x] Review cycle 2, F3 (Amendments): `_step` stops a wait any exception cuts short and the
      exception goes on as itself (`_cut_short`); a cut `create` or `attach` is cleaned up at the
      per-step bounds (`_clean_up_after`); a cut `detach` (`_in_use`) is named, never retried; a
      second interrupt abandons the stop or cleanup and names what is left. The cut rows (every kind,
      every place with the opt-in), and the two cut survivor tests.
- [x] Review cycle 2, F4 (Amendments): the `fill` body exit (an `OSError`) and its rows; the unit
      test asks for it and for a cut row per kind and place.
- [x] Review cycle 2, F5 (Amendments): after a failed or garbled cleanup `info`, the image is named
      only when it is there; its two rows.
- [x] Review cycle 2, the sweep: `remediation/F3-F5-fixture-sweep.py` (supersedes F2's), its modes
      in P3's `verify:`; `AGENTS.md` and the module docstring describe the cut path and rows.
- [x] Review cycle 2, the seed: H01/H02 as item 12 of `issues/disk-image-fixture-deeper-pins.md`,
      its `ROADMAP.md` entry's count; committed apart (Amendments).
- **Verify:** `sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh all` (about 40 min: run it in
  the background): `pre` (`rows.sh all`, the docs name both tests, the change stays in
  `tests/test_ssh_exec.py`, `tests/hdiutil_standin.py`, `AGENTS.md` and `spec/…`, graded from the
  plan commit; the ledger), `sweep-a`, `sweep-b`, then the profile's `verify` verbatim. Each mode
  runs alone too, for build's fail-once mutation (`pre`, `sweep-a`, `sweep-b`).
- **Touches:** `AGENTS.md`, `tests/test_ssh_exec.py`, `spec/full-volume-fixture-leaks-hdiutil/verify/`;
  review cycle 1 adds `spec/full-volume-fixture-leaks-hdiutil/remediation/`, `issues/disk-image-fixture-deeper-pins.md`
  and `ROADMAP.md` (Amendments).

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
