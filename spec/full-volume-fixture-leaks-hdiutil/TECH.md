---
slug: full-volume-fixture-leaks-hdiutil
title: A disk-image step that hangs or fails is stopped, and the full-volume fixture leaves nothing behind
kind: test
appetite: small
status: blocked
branch: test/full-volume-fixture-leaks-hdiutil
base: develop
current_phase: done
last_updated: '2026-11-10'
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
  verify: sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh --around sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh pre && sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh sweep-a && sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh sweep-b && sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh full
review:
  last_reviewed_commit: 6650254c2bf154c1c4fb5faef4753f0cf3488c5c
  verdict: changes-requested
  blocked_reason: 'Review cycle 1: F1 AGENTS.md omits tests/hdiutil_standin.py; F2 body-failure pin admits a BaseException carve-out (M32 survives)'
  cycle: 1
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
- **Verify:** `sh spec/full-volume-fixture-leaks-hdiutil/verify/p3.sh all` (about 40 min: run it in
  the background): `pre` (`rows.sh all`, the docs name both tests, the change stays in
  `tests/test_ssh_exec.py`, `tests/hdiutil_standin.py`, `AGENTS.md` and `spec/…`, graded from the
  plan commit; the ledger), `sweep-a`, `sweep-b`, then the profile's `verify` verbatim. Each mode
  runs alone too, for build's fail-once mutation (`pre`, `sweep-a`, `sweep-b`).
- **Touches:** `AGENTS.md`, `tests/test_ssh_exec.py`, `spec/full-volume-fixture-leaks-hdiutil/verify/`.

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
