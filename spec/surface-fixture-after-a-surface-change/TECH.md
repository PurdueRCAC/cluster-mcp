---
slug: surface-fixture-after-a-surface-change
title: The served-surface fixture follows a deliberate surface change
kind: test
appetite: small
status: done
branch: test/surface-fixture-after-a-surface-change
base: develop
current_phase: done
last_updated: '2026-11-13'
phases:
- id: P1
  name: The snapshot test, its controls, the command removed, and the fixture re-baselined
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  - R6
  - R7
  - R8
  - R9
  - R10
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/surface-fixture-after-a-surface-change/verify/gate.sh p1
- id: P2
  name: The seeds re-checked, the aimed sweep of the comparison and normalization, the full gate
  status: done
  satisfies:
  - R7
  - R11
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/surface-fixture-after-a-surface-change/verify/gate.sh p2 && sh spec/surface-fixture-after-a-surface-change/verify/gate.sh full
review:
  last_reviewed_commit: 47b14104c43177beb0afe5068b1b806425d4401c
  verdict: changes-requested
  blocked_reason: 're-shape review 1: F1-F3 LOW/CONFIRMED (missing controls: whitespace-only verdict, multi-field report, exact version match); severity re-graded from MEDIUM, foreman to confirm routing'
  cycle: 1
---

# TECH.md — The served-surface fixture follows a deliberate surface change

> **Re-shaped 2026-11-12 to a plain snapshot test; REVIEW.md cycles 1–3 graded the superseded
> recorder design.** This file was regenerated from the template for the re-shaped GOAL, and
> `review.cycle` restarts at 0: the maintainer ruled one review for the re-shape (a LOW-only verdict
> lands under the standing rule, anything higher goes back to him). The superseded phases P1–P4,
> their amendments and their gates are in git history at `482e092` and, for the plan and gates, under
> [`research/superseded/`](research/superseded/PLAN.md).

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/surface-fixture-after-a-surface-change/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md) (§ 2 is the build reference; § 6 the gates and the
  sweep's decision list).
- **Backing research:** none for this design (lean path, the maintainer's ruling); PLAN § 4 records
  the probes. `research/superseded/` holds the recorder design, for history only.

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
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`. Here every
  gate is a mode of `spec/surface-fixture-after-a-surface-change/verify/gate.sh` (PLAN § 6), run from
  the worktree root; each mode runs its own phase's checks only.
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
  This repo's previous cycles' last phases carried no other project-level item.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.
- **No file under `packages/`, `uv.lock` or `pyproject.toml` changes in any phase** (GOAL Non-goal:
  no surface change); every gate's `files` step checks it from the plan commit.
  `spec/stack-upgrade/verify/snapshot.py` is not edited. Every new test carries `@pytest.mark.unit`;
  no spec ids (`R1`, `P2`, `M1`…) in `tests/`. **The update mode is never on in a gate or a test
  run** but P1's fixture step (`gate.sh` unsets `UPDATE_SURFACE`).
- **`tests/fixtures/served_surface.json` is written once,** by P1's fixture step, through the
  documented update invocation, and by nothing else in the cycle. It is on § Invariants'
  high-blast-radius list: publish needs the maintainer's sign-off on its diff whatever the verdict.
  **For this re-baseline the landing commit's body carries `git diff --stat` on the fixture,
  `rebaseline_check.py`'s report and the new fixture's blob hash**, with a sentence that the format
  changed wholesale; the 402 KB `git diff` goes to the maintainer as a compare link at the publish
  sign-off (Amendments, ruling 2; PLAN 2.7, § 3 deviation row 3).

## Amendments

- 2026-11-12, at plan sign-off (the maintainer's rulings):
  1. **The CI clause gets a suite test** (PLAN § 5, open question 1): one function,
     `test_no_workflow_or_script_turns_the_update_mode_on`, holds every file under
     `.github/workflows/` and `bin/` to no line that sets or exports `UPDATE_SURFACE` (a shell
     `unset` of it is allowed), with planted lines checked inside the same function. The gate's
     `no-enable` scan stops guarding once the cycle lands; this test keeps guarding. Added to P1 and
     to `gate.sh p1`'s by-id list.
  2. **The landing body for this one re-baseline** (PLAN § 5, open question 2; PLAN § 3 deviation
     row 3): the landing commit's body carries `git diff --stat` on the fixture, the R6 report
     (`rebaseline_check.py`) and the new fixture's blob hash, with a sentence that the format
     changed wholesale. It does not carry the 402 KB `git diff`, which goes to the maintainer as a
     compare link at the publish sign-off. The P1 commit body follows the same rule. Later surface
     changes carry `git diff` on the fixture as R5 says.
  3. **The seed re-check is accepted as PLAN 2.8 says**: keep the recorder's two items (the
     `execution` row, the repeated cursor), retire the `--out` seed; the counts follow, and the
     pairing check (`snapshot_checks.py seeds`) runs.
  4. **Suite time**: P2 reports `tests/test_surface.py`'s time per era before and after against
     the `ci budget` baseline. No bound changes.
  5. PLAN § 3's deviation rows 1–2 accepted.
- 2026-11-12, at P1 (build):
  - **The depth control plants into the served bytes.** Each row writes the real serialization to
    the `tmp_path` fixture and passes `surface_check` the canonical bytes of a planted copy, so a
    row's name is the server's change as the report states it (`gained` → `added`, `lost` →
    `removed`, `changed-type` → `changed: false -> 0`), which is what PLAN § 6's kill table credits
    (`gained` kills the report skipping keys only in the served side, `lost` the other side).
    Planting into the fixture would swap those two credits.
  - **The normalization is its own step, `normalized`**, applied by `serialized()` before
    `serialization` lays the surfaces out; `serialization` is the layout alone. The recorder rows
    run their planted surfaces through `serialization` without it, since a planted server version
    (`9.9.9+planted`) matches no candidate. R9 holds: the normalization is named once, beside the
    serializer, and nothing else normalizes.
  - **The update control's third step also sets the variable to `0` and to the empty string**, not
    only deletes it: with it deleted, a switch mutated to a presence test (`in os.environ`) reads
    false, the right answer, so PLAN § 6's credit of that mutant to step 3 needs a set value.
  - **The recorder rows that plant a whole entry unplant the whole entry** (`tool-annotations`,
    `resource-annotations`, `prompt`, `resource-template`), so the line is `- <listing>.<identity>:
    added` as PLAN 2.4's example; `experimental-capability` unplants `experimental`. Each row names
    its own unplant path and its expected line.
  - **`report` takes the fixture's path** to name it in the header (PLAN 2.3 wrote
    `report(expected, served)`); a controlled `tmp_path` fixture is named as itself.
  - **`tests/harness.py`: two docstring sentences** named the command (the module docstring and
    `served_surface`'s); both now name the snapshot test. No code changes.
  - **`snapshot_checks.py docs` fixed** (red on correct text): two retired names are also other
    modules' own functions in their own § Testing entries (`tests/test_probe_startup.py`'s
    `surface_violations`, `tests/test_protocol.py`'s `era_violations`), and `set_violations` is a
    substring of `sandbox_unset_violations`. Those two names are read only in the parts describing
    the snapshot test, and every identifier is matched as a whole word. Seen red on the correct
    text first, then green; it still goes red on a planted `bin/record_surface.py` line in § Commands.

- 2026-11-12, at P2 (build):
  - **The depth control's expected lines are written by hand.** The first full sweep left two
    report mutants alive (`report-drops-era-and-set`, `report-quoted-key-empty`): the rows built
    their expected line through `render_path`, the code under test, so a mutated renderer moved both
    sides. Each row now writes its line without it (`_dotted` joins a plain-name path by hand and
    refuses any other; the `lost` row's quoted line is a literal). A red from this run's own work,
    recorded with `--record-attempt` on P2 and fixed in the run; the sweep was then re-run whole.
  - **The ROADMAP entry keeps its heading's opening words** ("The surface pin's"), which
    `snapshot_checks.py seeds` locates it by, and is retitled to the two recorder layers.

- 2026-11-12, remediation of the re-shape's review 1 (REVIEW.md, F1–F3, all LOW: the code is
  right, the controls were missing):
  - **P1 and P2 reopened and committed together**, as if `bundle` had been passed: P2's sweep
    entries are killed only by P1's new rows, and its aimed sweep reads the index, so the two
    cannot be gated apart. Both gates run once on the final tree.
  - **The depth control gains two rows and a passing side.** `whitespace` doubles a space inside a
    string at depth, in the pass's own era, so the suite's two passes plant it in both eras: a
    verdict that compares tokens instead of bytes passes it (F1). `two-entries` gains a key in one
    tool and loses one in another, and asserts exactly those two lines (F2). Each row first checks
    that the unplanted fixture passes, the byte-identical side of the verdict. The plants now
    return their expected lines as a list. The whitespace row shows the two values as `_short`
    cuts them, since it pins the verdict and the field, not the cut, so `short-limit-6` stays the
    display-only survivor seeded below.
  - **The version table's decoys run both ways** (F3): the `one` and `none` rows gain `4.1` (a
    prefix of the served value), `.1.` (a part of it) and `1.4` (a suffix of it, which the route's
    property names; a one-off `served.endswith(version)` mutant fails the `one` row). The `none`
    row serves `None`, so its decoys never reach the comparison; the kills come from `one`, and the
    `none` row keeps its `version-none-matches-none` kill.
  - **The aimed sweep gains the reviewer's five survivors** as a dated amendment in
    `verify/sweep.py`: `cmp-verdict-ignores-whitespace`, `report-first-line-only`,
    `diff-first-only`, `ver-prefix-match`, `ver-substring-match`, each run in both eras.
    `verify/` is not frozen in this cycle (P2 wrote the sweep), so the list is extended in place.
  - **Seeds, counts unchanged:** `ver-sources-drop-core` is a dated line on
    `issues/rename-leftover-identity-strings.md`; `ver-uninstalled-empty-string`,
    `diff-leaf-no-sort-keys` and `short-limit-6` are one item on
    `issues/surface-pin-completeness.md` (unlanded, this cycle's own text, so edited in place) and
    its `ROADMAP.md` entry, whose heading keeps its opening words.
  - **`AGENTS.md` § Testing** names the two new rows and the version source's exact match, in the
    same commit as the rows.
  - **`full` runs**: the new rows change the suite's collected count (5112 to 5114 per era), so
    P2's gate runs whole.
  - `tests/fixtures/served_surface.json` is not written; its sha256 stays `2e0dc91f…`.

---

## Phase P1 — The snapshot test, its controls, the command removed, and the fixture re-baselined
**Satisfies:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10 · **Depends on:** —
**Goal:** `tests/test_surface.py` is the plain snapshot test of PLAN § 2: both eras and every set
serialized field first, one normalization, bytes equality with a field-path report, the update mode;
the command and everything that served only it are gone; the fixture is re-taken once and its R6
record made; `AGENTS.md` describes the result.

- [x] Rewrite `tests/test_surface.py` fresh around PLAN 2.2–2.4: `served_surfaces`, `VERSION_SOURCES`
  and `version_source` (named beside the serializer with their cause), `serialization`, `canonical`,
  `serialized` (cached), `surface_check`, `report`, `differences`, the baseline test reading
  `UPDATE_SURFACE`, the depth control (three rows), the update-mode control, the version control,
  the workflow-and-script scan (Amendments, ruling 1), and the recorder rows carried over and
  trimmed (PLAN 2.4). The module docstring describes the
  snapshot test. Every test `unit`.
- [x] Remove `bin/record_surface.py` and everything PLAN 2.5 lists (R10). `tests/harness.py`: only
  the docstring sentence naming the command changes.
- [x] `tests/mutants.py`: the new `RUN_COMMAND_ENTRY`, `recorded()` and the eleven surface cases'
  `why` strings and comments (PLAN 2.6). The reason goes in this phase's commit body.
- [x] `AGENTS.md`: §9's pin bullet, § Testing's `tests/test_surface.py` entry, § Commands (the
  update invocation in place of the command's block), the repository map (PLAN 2.6).
- [x] **The fixture step (PLAN 2.7), last, alone:** delete the working-tree fixture and run the
  documented update invocation (`bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && UPDATE_SURFACE=1 uv
  run pytest -q tests/test_surface.py::test_served_surface_matches_baseline'`); stage the result;
  overwrite the working copy with merge-conflict markers, run it a second time and confirm
  `git diff --exit-code` on the fixture against the staged copy; run
  `uv run python -I spec/surface-fixture-after-a-surface-change/verify/rebaseline_check.py`, which
  must exit 0. The commit body carries its report verbatim, `git diff --stat` on the fixture, the
  new fixture's blob hash, and the note that the format changed wholesale (Amendments, ruling 2).
  Nothing else writes the fixture.
- [x] Measure `tests/test_surface.py`'s time in each era (`--durations=0`) and keep the figures for
  P2's report.
  Measured 2026-11-12 on this host, two runs per era: before (the recorder design's module, 214
  rows) 4.03 s and 3.12 s of pytest time (5.2 s and 4.3 s wall), legacy and modern; after (23 rows)
  0.31–0.38 s of pytest time, 1.44–1.56 s wall, in each era.
- [x] **Review fix (the re-shape's review 1, F1–F3):** the depth control's `whitespace` and
  `two-entries` rows and its passing side, and the version table's decoys (Amendments,
  2026-11-12, remediation); `AGENTS.md` § Testing names them.
- **Verify:** `sh spec/surface-fixture-after-a-surface-change/verify/gate.sh p1`.
- **Touches:** `tests/test_surface.py`, `tests/harness.py` (docstring), `tests/mutants.py`,
  `tests/fixtures/served_surface.json`, `bin/record_surface.py` (removed), `AGENTS.md`.

## Phase P2 — The seeds re-checked, the aimed sweep of the comparison and normalization, the full gate
**Satisfies:** R7, R11 · **Depends on:** P1
**Goal:** the cycle's seeds match the new shape, the comparison's and the normalization's mutants are
killed in both eras with each equivalent recorded, and the whole gate passes.

- [x] Retire `issues/record-surface-relative-out.md` and its `ROADMAP.md` entry. Re-write
  `issues/surface-pin-completeness.md` to the recorder's two items PLAN 2.8 keeps (the `execution`
  row, the repeated cursor) and its `ROADMAP.md` entry with it. Part I's counts follow (30 entries,
  thirteen gates; the gates group's description drops the `--out` clause). R11's evidence is these
  committed files, outside `spec/`, so the blind reviewer can grade it.
- [x] Write `spec/surface-fixture-after-a-surface-change/verify/sweep.py` from PLAN § 6's decision
  list, reusing `research/superseded/verify/sweep.py`'s runner (copy of the index's tree, one plant,
  one child at a time under `bin/sandbox.sh`, the `snapshot-sweep-child` argv word, the JUnit verdict
  through `mutants.mutation_violations`). Header comment: peak processes and memory. Each mutant in
  both eras, killed in each; each equivalent run, reported with its reason, not failed. It writes
  `verify/sweep-report.txt` (verdicts only). Measure its wall time; past 180 s run it in the
  background (it stays under the 10-minute command cap: about 25 mutants × 2 eras × a few seconds).
  Measured 2026-11-12: 30 mutants × 2 eras in 78 s wall on this host; 28 killed in both eras, 2
  equivalent (`verdict-stripped`, `sources-lose-cluster-mcp`), 0 survived (`verify/sweep-report.txt`,
  written by `gate.sh p2`'s run).
- [x] Report the suite-time figures (P1's measure) against `suite-legacy-4` 7:22 and
  `suite-modern-4` 7:33; no bound changes. `tests/test_surface.py`, on this host, per era: before
  4.03 s (legacy) and 3.12 s (modern) of pytest time for 214 rows; after 0.28–0.38 s for 23 rows,
  about 3 s less per era. It runs in the fourth command of each era (`suite-legacy-4`,
  `suite-modern-4`), whose baseline is 7:22 and 7:33 of a 10-minute budget: the change is a
  saving of under 1% of each job, and no bound changes.
- [x] **Deferral ledger:** walk P1 and P2 for every deferral phrase (the list in
  `snapshot_checks.py`, `DEFERRAL`); each must name an `issues/` seed that exists and that
  `ROADMAP.md` lists (`snapshot_checks.py ledger`). None is expected.
  `gate.sh full` green 2026-11-12 on `4a6c543` (both eras, every command: 44, 154, 507 and 4393
  passed per era, 14 skipped in the fourth command of each).
- [x] **Review fix (the re-shape's review 1):** the aimed sweep gains the five survivors, each
  killed in both eras; the four coverage observations seeded (Amendments, 2026-11-12,
  remediation). `gate.sh p2`'s run on the final tree: 35 mutants, 33 killed in both eras, 0
  survived, 2 equivalent (`verify/sweep-report.txt`). `gate.sh p1` green (2830 passed per era, the
  11 fixture mutation cases killed in each). `gate.sh full` green in 26 minutes (44, 154, 507 and
  4395 passed per era, 14 skipped in the fourth command of each, as before).
- **Verify:** `sh spec/surface-fixture-after-a-surface-change/verify/gate.sh p2 && sh spec/surface-fixture-after-a-surface-change/verify/gate.sh full`
  (`full` is the profile's whole `verify`, about 26 minutes: run it in the background).
- **Touches:** `issues/record-surface-relative-out.md` (removed), `issues/surface-pin-completeness.md`,
  `ROADMAP.md`, `spec/surface-fixture-after-a-surface-change/verify/sweep.py`,
  `spec/surface-fixture-after-a-surface-change/verify/sweep-report.txt`.

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
