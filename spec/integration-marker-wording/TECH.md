---
slug: integration-marker-wording
title: The test markers say what the unit guard enforces
kind: test
appetite: small
status: in_review
branch: test/integration-marker-wording
base: develop
current_phase: done
last_updated: '2026-11-09'
phases:
- id: P1
  name: The descriptions and AGENTS.md state the markers
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/integration-marker-wording/verify/gate.sh prepush && sh spec/integration-marker-wording/remediation/checks.sh F1
- id: P2
  name: The word-for-word check, its planted drift and the mutant sweep
  status: done
  satisfies:
  - R4
  - R5
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/integration-marker-wording/verify/gate.sh prepush && sh spec/integration-marker-wording/remediation/checks.sh F1 F2
- id: P3
  name: The full verify and the deferral ledger
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R4
  - R5
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/integration-marker-wording/verify/gate.sh P3 && sh spec/integration-marker-wording/remediation/checks.sh F1 F2 F4
review:
  last_reviewed_commit: 0efe6bf35805b5536979513defed75d214e7832f
  verdict: changes-requested
  blocked_reason: 'review cycle 1: unit description overclaims the guard (F1); R5 check survivors (F2, F3); seed scope claim (F4)'
  cycle: 1
---

# TECH.md — The test markers say what the unit guard enforces

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/integration-marker-wording/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** none (lean path). The gates are [`verify/gate.sh`](verify/gate.sh) and its
  helpers; the exact text the gates were dry-run on is [`verify/draft/`](verify/draft/).

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
- **Every gate reads the index:** stage the phase's changes before running its `verify:`; every
  part refuses a tree with unstaged or untracked changes.
- **Never touched:** `tests/conftest.py`, `bin/sandbox.sh`, anything under `packages/` or
  `.github/`, `uv.lock` (the GOAL's non-goals; `gate.sh scope-P<n>` enforces it). No test changes
  marker.

---

## Phase P1 — The descriptions and AGENTS.md state the markers
**Satisfies:** R1, R2, R3, R4 · **Depends on:** —
**Goal:** `pyproject.toml` describes each marker by the rule it carries, every wording claim is
proven against `tests/conftest.py`, and `AGENTS.md` states the markers word for word in § Testing
and § Conventions, points at them from the development commands, drops the exception note and names
the routes the probe found open.

- [x] Replace the two `markers` entries in `pyproject.toml` with PLAN § 2's text, exactly (two
      lines changed, nothing else in the file).
- [x] `AGENTS.md` § Testing, marker bullet: the not-`unit`-is-`integration` sentence, the statement
      (`MARKERS_STATED` line plus the two items, wrapped with continuation lines two spaces deeper
      than the dash), a blank line (without it the next line renders inside the `integration`
      item), and the line naming `test_the_markers_are_stated_as_pyproject_describes_them`.
- [x] `AGENTS.md` § Conventions, marker bullet: the same statement, verbatim.
- [x] `AGENTS.md` development commands: the `-m unit` comment's pointer and the sandboxed-run
      comment's per-launch sentence (PLAN deviation row 1).
- [x] `AGENTS.md` § Testing, `tests/test_registry.py` entry: drop "although it drives no CLI".
- [x] `AGENTS.md` § Testing: the rails' unit-guard bullet names the open routes and
      `issues/marker-rule-gaps.md`; the `tests/test_hygiene.py` entry says `test_cli_drives_are_sandboxed`
      does not read a `conftest.REAL_POPEN` call (`_host`, `hdiutil`), naming the same seed.
      Do not fix those routes here: the seed `issues/marker-rule-gaps.md` and its ROADMAP entry were
      filed by the plan commit.
- [x] Reference text for all of the above: `verify/draft/apply_edits.py` (`P1`). Stage, then run
      the gate.
- [x] Review cycle 1, finding 1: every statement about what the guard or a check enforces is true
      of the code. The `unit` description and its two copies end "the unit guard holds it to that,
      except on the open routes AGENTS.md § Testing names"; the guard paragraph names the three
      `XDG_*` variables it sets and the routes beside them (`XDG_STATE_HOME`, the password
      database); the commands block says what the static check does not read;
      `issues/marker-rule-gaps.md` and its ROADMAP entry name the XDG gap. Checker:
      `remediation/checks.sh F1`.
- **Verify:** `sh spec/integration-marker-wording/verify/gate.sh P1` — `wording` (the probe of
  `tests/conftest.py`, the claimed phrases present and "fast", "CLI", "drives" absent, the drafted
  word-for-word check on the staged files, the commands' and § Testing's sentences, the note gone),
  `slice` (`tests/test_hygiene.py` in both eras; `pytest --markers` reads both new lines),
  `scope-P1`. 8 s on the prototype.
- **Touches:** `pyproject.toml`, `AGENTS.md`.
- **Grading note:** R3 is met by the committed descriptions read together; the blind reviewer can
  grade it from `pyproject.toml` alone. The probe that proves R1's claims lives in `spec/` and is the
  orchestrator's to grade.

## Phase P2 — The word-for-word check, its planted drift and the mutant sweep
**Satisfies:** R4, R5 · **Depends on:** P1
**Goal:** a `unit` test holds § Testing's and § Conventions' statement to `pyproject.toml` word for
word, line wrapping the only freedom, ending where Markdown ends it; 51 planted drift rows, each the
named killer of a mutant; 34 mutants, decisions and additive carve-outs, all killed.

- [x] `tests/test_hygiene.py`: `import tomllib`; insert after `test_unit_guard_redirects_home`,
      before the `SANDBOX_UNSET` comment: `MARKERS_STATED`, `MARKER_ITEM`, `described_markers`,
      `LIST_ITEM`, `stated_markers`, `statement_end_problems`, `agents_section`,
      `marker_statement_violations`, `test_the_markers_are_stated_as_pyproject_describes_them`, the
      planted pair, `test_marker_statement_check_accepts_a_rewrapped_statement` (4 rows) and
      `test_marker_statement_check_catches_planted_drift` (the 51 rows of `verify/drift-ids.txt`).
      Reference text: `verify/draft/check_block.py`. The module only gains lines and binds no
      existing top-level name again.
- [x] `AGENTS.md` § Testing, `tests/test_hygiene.py` entry: `marker_statement_violations` in the list
      of checks, and the sentence naming the live test and the drift test (reference:
      `apply_edits.py` `P2`).
- [x] Keep the check's text such that every substitution in `verify/marker_mutants.py` applies
      exactly once. The gate's files are frozen at the plan commit (PLAN deviation row 8): a
      `STALE` line, or a check that cannot be written that way, stops the phase for the foreman;
      never re-key a mutant or drop a row.
- [x] Review cycle 1, findings 2 and 3, and finding 1's check description: the narrower drift
      table (`test_marker_statement_check_catches_narrower_drift`, 15 rows) and the module-wide
      sweep `remediation/checks.sh F2` (74 mutants, each killed); § Testing describes the check
      as it refuses (a clause added to a description; where the statement ends). The frozen
      51-row table and `verify/` are unchanged but for `mutant-sweep.md`.
- [x] Record the sweep's output in `verify/mutant-sweep.md` (one line a mutant, the run's date and
      commit).
- **Verify:** `sh spec/integration-marker-wording/verify/gate.sh P2` — `wording`, `slice`, `ids`
  (junit in both eras: the live test, the 4 accept rows, exactly the 51 drift ids, and the kept rails
  `test_the_id_rule_is_stated_as_the_check_enforces_it`, `test_no_spec_ids_in_the_package_or_the_suite`,
  `test_cli_drives_are_sandboxed`, `test_only_need_shell_skips` all passed), `sweep` (34 of 34
  killed by their named rows with `as-planted` green under each, no idle drift row), `scope-P2`.
  61 s on the prototype.
- **Touches:** `tests/test_hygiene.py`, `AGENTS.md`, `spec/integration-marker-wording/verify/`.

## Phase P3 — The full verify and the deferral ledger
**Satisfies:** R1–R5 · **Depends on:** P2
**Goal:** the whole profile `verify` is green with the change, and every deferral is recorded.

- [x] Deferral ledger: walk P1 and P2 above, and PLAN, for every "do not fix here", "known
      limitation", "left as a follow-up" or deferral; each names a committed `issues/` seed with a
      `ROADMAP.md` entry. This cycle's one deferral is `issues/marker-rule-gaps.md` (filed with the
      plan); `issues/integration-marker-check.md` was filed at the GOAL gate. Any new one is filed
      here, pre-shaped from the KB's `ISSUE.md` template, before the gate.
- [x] Review cycle 1, finding 4: the claims of the ledger lines this cycle adds hold against the
      code and the history (`issues/integration-marker-check.md`'s fixture scope,
      `issues/stalled-reconnect-test-timing.md`'s commit). Checker: `remediation/checks.sh F4`.
- [x] Run the gate in the background (the full verify runs past the 10-minute cap of one foreground
      call) and wait for its exit; `prepush` runs the same without `full` when only that is needed.
- **Verify:** `sh spec/integration-marker-wording/verify/gate.sh P3` — `wording`, `slice`, `ids`,
  `sweep`, `scope-P3`, `ledger`, then `full`, the profile's `verify` word for word in both eras (about
  1,545 s on the prototype, measured by that run; PLAN § 6).
- **Touches:** nothing new, unless the ledger records a new `issues/` file and its `ROADMAP.md` entry.

---

## Amendments

- **2026-11-09, the PLAN/TECH gate's rulings** (recorded at P1). PLAN § 3's deviation rows 1–9 are
  accepted as written. Row 6's "3 rows" was a slip: the design has 4 accept rows (`as-planted`,
  `rewrapped`, `unwrapped`, `paragraph-after-a-blank`, as P2 and `marker_gate.py` already say);
  PLAN row 6 is corrected in place and says so. The gate freezes only `verify/`, so the correction
  is allowed. Row 4's conflict with the sibling cycle is settled on the sibling's side: its stand-in
  will launch through `bin/sandbox.sh`, and nothing changes in this cycle. Row 8 stands as the
  oracle freeze: no file under `verify/` changes except `mutant-sweep.md`, and a check that cannot
  take the sweep's substitutions stops the phase for the foreman rather than re-keying a mutant.

- **2026-11-09, review cycle 1 remediation** (`REVIEW.md`, changes-requested). P1 (finding 1:
  R1, R4), P2 (findings 2 and 3, and finding 1's check description: R5) and P3 (finding 4, and
  the full verify) are reopened and built together in one commit, `P2: F1–F4`, by the foreman's
  direction: the three fixes share `AGENTS.md` § Testing and the same gate run. Each reopened
  phase's `verify:` runs the frozen gate unchanged, then the class checkers in `remediation/`.
  P1 and P2 are retuned to the frozen `gate.sh prepush` (their own `scope-P1` and `scope-P2` cannot
  pass once P3's ledger files exist), P3 keeps `gate.sh P3`. One `prepush` run on the final tree
  stands in for P1's and P2's gates and P3's parts before `full`; one `checks.sh F1 F2 F4` run
  stands in for all three phases' checkers. P3's `full` waits for the foreman's release, so P3
  stays in progress. The frozen gate checks two sentences word for word (the commands block's
  per-launch rule and the guard paragraph's open routes); finding 1 is fixed by text added after
  each, so the frozen oracle passes unchanged and needs no wrapper.

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
