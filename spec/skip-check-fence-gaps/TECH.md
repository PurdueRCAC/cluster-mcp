---
slug: skip-check-fence-gaps
title: The static skip check catches the skips it admits today
kind: test
appetite: small
status: blocked
branch: test/skip-check-fence-gaps
base: develop
current_phase: done
last_updated: '2026-11-09'
phases:
- id: P1
  name: A skip is allowed only in the single top-level helper of the suite's conftest
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run python -I spec/skip-check-fence-gaps/verify/planted-rows.py controls scope && uv run python -I spec/skip-check-fence-gaps/verify/planted-rows.py scope && uv run pytest -q tests/test_hygiene.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_hygiene.py
- id: P2
  name: Every spelling of a skip the cycle covers, the outcome type as a value admitted, and the ledger
  status: done
  satisfies:
  - R4
  - R5
  - R6
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run python -I spec/skip-check-fence-gaps/verify/planted-rows.py controls all && uv run python -I spec/skip-check-fence-gaps/verify/planted-rows.py all && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
review:
  last_reviewed_commit: 18a10265424b1f855ccc802fe5ee04ddf64ed930
  verdict: changes-requested
  blocked_reason: 'review 3: R2/R4/R5 pin gaps (binding forms, raised or-operands, admissions unpinned vs additive mutants); bound reached'
  cycle: 3
---

# TECH.md — The static skip check catches the skips it admits today

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/skip-check-fence-gaps/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** none (lean path); the gate is [`verify/planted-rows.py`](verify/planted-rows.py).

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

---

## Phase P1 — A skip is allowed only in the single top-level helper of the suite's conftest
**Satisfies:** R1, R2, R3, R5, R6 · **Depends on:** —
**Goal:** `skip_violations` allows a skip only inside the body of the one module-scope binding of
`need_shell` / `need_git` in the suite's `conftest.py`, when that binding is a top-level `def`; the
twelve scope rows prove each shape was a gap and is now reported (or, for the closure, still admitted).

- [x] In `tests/test_hygiene.py`, add `CONFTESTS` and `SCOPES`, `_module_bindings` and `_allowed`
      as PLAN § 2 "Which module is conftest" and "Where a skip is allowed" describe (steps 1–5),
      and switch `skip_violations` from the line-number set to the node-identity set `_allowed`
      returns; the `defined again` reports join `found`. Keep the `.Exception` exemption exactly as
      it is in this phase (P2 narrows it).
- [x] Append PLAN § 2's twelve P1 rows after `outcome-type`, ids and `found` values exactly as tabled;
      leave every existing row byte-for-byte.
- [x] Keep the comment above `SKIPPERS` true: it now says the helpers are the single top-level
      definitions in `tests/conftest.py`.
- [x] Stage, then run the `verify:`. If `test_only_need_shell_skips` reports anything in the suite
      as it stands, stop and report the line: it is a finding for the foreman, never an exemption.
- **Verify:** the frontmatter's (gate `controls scope` 13 s and `scope` ≈ 1 s, then
  `tests/test_hygiene.py` in each era, 2 s and 5 s; measured on the prototype, mac-m2). A refusal
  names its check (`fence`, `bodies`, `kept`, `rows`, `bite`, `meet`, `suite`; PLAN § 6).
- **Touches:** `tests/test_hygiene.py`.

## Phase P2 — Every spelling of a skip the cycle covers, the outcome type as a value admitted, and the ledger
**Satisfies:** R4, R5, R6 · **Depends on:** P1
**Goal:** a skipper is exempt only as the `.value` of an `.Exception` attribute outside every
`raise`'s exception expression; the eight spelling rows prove it; the docstring names what the check
cannot see; the ledger holds every deferral; the profile's full `verify` is green.

- [x] Narrow the exemption in `skip_violations` as PLAN § 2 "What counts as a skip" describes, with
      its comment saying why (`.Exception` names the outcome type; raised, it skips).
- [x] Append PLAN § 2's eight P2 rows after the P1 rows, ids and `found` values exactly as tabled.
- [x] Give `skip_violations` the docstring PLAN § 2 "Docstring" lists.
- [x] **Q1, per the sign-off's ruling on PLAN § 5.** Default (seed): file
      `issues/skip-check-import-aliases.md` from the KB's `ISSUE.md` template, `status: unshaped`,
      with both probes, each reporting nothing before and after this cycle (`from pytest import skip
      as go` then `go("x")`; `class S(pytest.skip.Exception): pass` then `raise S("x")`), and its
      `ROADMAP.md` entry beside this cycle's (0.2.0, gates). If the sign-off folds a shape into R4
      instead, this item becomes: read `ast.alias` names against `SKIPPERS` and add a row
      `skip-renamed-on-import`, and/or report a skipper's `.Exception` among a class's bases and add
      a row `outcome-type-subclassed` (`found` yes each; the gate's `SPELLING_ROWS` gains them in
      the same commit). Ruled 2026-11-09: the default stands (the seed; see Amendments).
- [x] **Q2, per the sign-off's ruling on PLAN § 5** (2026-11-09; see Amendments): file a seed for
      conftest-level deselection (`collect_ignore`, `pytest_collection_modifyitems`, `pytest.exit`
      making rows vanish from a CI run) from the KB's `ISSUE.md` template, `status: unshaped`, and
      its `ROADMAP.md` entry in Part I's gates group, placed after this cycle's entry.
- [x] **Deferral ledger** (last-phase item): walk P1's and P2's bodies, PLAN §§ 4–5 and the branch's
      commit bodies for "do not fix here", "known limitation", "left as a follow-up", "deferred",
      "limit" and "not covered"; each must have an `issues/` seed and a `ROADMAP.md` entry. Expected:
      Q1's seed and Q2's seed. The outcome type raised through a name is a GOAL non-goal, and
      PLAN § 5's unpinned binding forms are a review risk; neither is a deferral. An unrecorded
      deferral fails the phase.
- [x] Standing last-phase items: the previous cycle's last phase carried no project-level obligation
      beyond the ledger (no `## Times` quote in this repo).
- [x] Stage, then run the `verify:`.
- **Remediation, review cycle 1** (`REVIEW.md` F1–F3, all LOW/CONFIRMED; P2 reopened, see Amendments):
  - [x] **F1:** every count in `ROADMAP.md` agrees with its entries: `**Seed:**` lines counted per
        Part (Part I 28, by group 12 / 6 / 5 / 3 / 2; Part II 14, eleven `##` cycles and three
        absorbed; Part III 2; after 0.3.0, 3), against the preamble, every Part blurb and the
        group list. Only Part I's blurb was stale ("Twenty-six"); the gates bullet is rewrapped.
  - [x] **F2:** `issues/skip-check-import-aliases.md` names only the spellings that import from
        `pytest` and skip or xfail when renamed (`skip`, `xfail`, `importorskip`, each run under
        pytest), and says `skipif` cannot be imported from `pytest` (a mark; `ImportError`).
  - [x] **F3:** a mutant sweep over every decision in `skip_violations`, `_module_bindings`,
        `_allowed` and the `.Exception` / `raise` exemption, recorded in
        [`verify/mutant-sweep.md`](verify/mutant-sweep.md). Seventeen rows appended after
        `outcome-type-caught` (existing rows byte-identical), each killing a mutant the reviewed
        rows let survive, the first `helper-defined-twice-without-a-skip` (M6). M3, M10, M26, M25
        and M42 are equivalent, with the reason recorded; M1b dies only to
        `test_only_need_shell_skips`. The ten of them that are R1/R2 gaps the base had join the
        gate's `SCOPE_ROWS` with a shape each.
- **Remediation, review cycle 2** (`REVIEW.md` A–C, all LOW/CONFIRMED; P2 reopened, see Amendments):
  - [x] **A + B, what the check reports (R4/R5):** a `raise` is reported when its exception is the
        skip or xfail outcome (bare, called, with a cause), found by `_raised`, which follows only
        what the raise hands on as its exception (a call's callee, a called method's value, either
        branch of a conditional, a walrus's value, each `and`/`or` operand); the outcome type
        anywhere else in a raise (an argument, a message, an f-string, a `repr`, a conditional's
        test, an uncalled attribute of it) is a value and is admitted. Rows: five `raised-outcome-*`
        (reported) and five `outcome-type*` (admitted).
  - [x] **A + B, what counts as a second definition (R2/R5):** only a module-scope store rebinds a
        helper (`_scope_bindings` per scope, `_module_bindings` over them). A load, an annotation
        without a value, a comprehension's own variable, a `global` with no store in its scope, a
        `global` at module scope and a `global` of another name bind nothing; an annotated
        assignment with a value, a walrus in a comprehension and a `global` paired with a store in
        any nested scope still do. Rows: six admitted (`helper-read-at-module-scope` kills V16) and
        three reported.
  - [x] **Mutant sweep:** extended in [`verify/mutant-sweep.md`](verify/mutant-sweep.md) § Review
        cycle 2, every decision of `skip_violations`, `_allowed`, `_scope_bindings`,
        `_module_bindings` and `_raised`, in process and planted under pytest in both eras. The
        reviewer's surviving V40 and V54 get a row each (`helper-named-class-in-the-helper`,
        `skip-in-a-one-line-helpers-default`). Survivors are the recorded equivalents only.
  - [x] **C, seed prose:** every runtime claim in `issues/skip-check-deselection.md`,
        `issues/skip-check-import-aliases.md` and their `ROADMAP.md` entries run under pytest in a
        scratch directory; corrected: `pytest.exit` drops rows on a passing run only with
        `returncode=0` (its default exits 2), and `pytest_deselected` alone removes nothing (the
        row runs and fails, exit 1); `skipif` is reachable as `mark.skipif` too.
- **Verify:** the frontmatter's: gate `controls all` and `all`, then the profile's full `verify`,
  both eras (≈ 26 min, 1,571 s, measured once on the prototype; PLAN § 6). The whole command runs past the 10-minute cap of one foreground
  shell call: run it in the background and wait for its exit.
- **Touches:** `tests/test_hygiene.py`; `issues/skip-check-import-aliases.md`,
  `issues/skip-check-deselection.md` and `ROADMAP.md`; in remediation, also
  `verify/planted-rows.py` (the required-row table) and `verify/mutant-sweep.md`.

## Amendments

- **2026-11-09, sign-off rulings on PLAN § 5, for P2** (recorded during P1's build; P1 is
  unaffected). **Q1:** the default stands. P2's ledger files `issues/skip-check-import-aliases.md`
  (`status: unshaped`: a skipper renamed on import; the outcome type subclassed, then raised) and
  its `ROADMAP.md` entry beside this cycle's; R4 is not widened and no row is added for either
  shape. **Q2:** P2's ledger also files a seed for conftest-level deselection (`collect_ignore`,
  `pytest_collection_modifyitems`, `pytest.exit` making rows vanish), `status: unshaped`, with its
  `ROADMAP.md` entry in Part I's gates group, placed after this cycle's entry. Both seeds follow
  the KB's `ISSUE.md` template. The gate's fence already admits `issues/*.md` and `ROADMAP.md`.
- **2026-11-09, P2 build.** Q2's seed is `issues/skip-check-deselection.md`. Its `ROADMAP.md` entry
  follows Q1's, and both follow this cycle's. Part I's count goes from 26 entries to 28, and the
  gates group goes from ten to twelve, both in the intro text. The `skip_violations` docstring
  leaves out "a star import" from PLAN § 2's list, because the check does see one:
  `from pytest import *` then `skip("x")` reads the word `skip` and is reported. The rest of the
  list stands, with the renamed import added because Q1 is seeded.
- **2026-11-09, review cycle 1 remediation (F1–F3).** P2 is reopened, not P1: F1 and F2 are P2's
  ledger, and F3 fails R6 (a planted row for R2's own report), which P2 satisfies; R2's behaviour
  was graded met, and the check's code is unchanged (rows only). P2's `verify:` is kept as written;
  it runs `controls all` and `all`, so P1's `scope` rows are gated with it, and the full profile
  `verify` runs `tests/test_hygiene.py` in both eras. The gate's required-row table changes:
  `SCOPE_ROWS` gains ten rows, `helper-defined-twice-without-a-skip`, `helper-rebound-in-a-default`,
  `helper-deleted`, `helper-rebound-by-a-dotted-import`, `helper-rebound-by-except`,
  `helper-rebound-by-a-match-capture`, `-star`, `-rest`, `helper-rebound-by-a-class` and
  `async-helper-nested-in-the-helper`, each with a shape (`_twice_without_a_skip`, `_rebound_by`,
  `_rebound_in_a_default`, `_async_nested_in_helper`), so `rows`, `bite` and the per-row controls
  cover them (`controls all` is now about 31 s). The other seven new rows are not required: three
  pin a decision the base check already reported (`helper-as-a-class`, `helper-as-an-async-def`)
  or that no R-ID names (`skip-on-the-helpers-decorator`), and four expect no report
  (`helper-name-local-to-another-function`, `helper-name-bound-inside-a-lambda`,
  `outcome-type-as-a-cause`, `bare-reraise`); `meet` holds them, and the sweep record names the
  mutant each kills. PLAN § 5's "unpinned binding forms" risk is closed by the `except`/`match`
  rows. The fence, `kept` and `bodies` checks are unchanged.
- **2026-11-09, review cycle 2 remediation (A–C).** P2 is reopened again, not P1: A and B are R5
  (with R4 and R2 on the other side of each property) and R6, which P2 satisfies, and C is P2's
  ledger. The check's code changes this time, so PLAN § 2 gets a dated note where it described
  the replaced rules: "the exception expression's subtree" becomes `_raised`'s hand-on chain, and
  "every `global` naming the helper anywhere" becomes a `global` paired with a store in its own
  scope. P2's `verify:` is kept as written. The gate's required-row table changes: `SCOPE_ROWS`
  gains eleven rows and `SPELLING_ROWS` ten (51 required in all), each with a shape
  (`_raised(word, cause)`, `_raised_in`, `_value_in_a_raise`, `_top_level`, `_comprehension_binds`,
  `_class_in_helper`, `_skip_on_the_helpers_line`); every new reported row is a gap the base had
  (`bite`), and every new admitted row is held by `meet` and its shape. The fence, `kept` and
  `bodies` checks are unchanged; every existing row is byte-identical.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
