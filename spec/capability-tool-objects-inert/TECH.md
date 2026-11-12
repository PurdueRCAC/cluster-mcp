---
slug: capability-tool-objects-inert
title: "A capability's registered tool objects run none of its code when they are read"
kind: fix
appetite: small
status: in_progress
branch: fix/capability-tool-objects-inert
base: develop
current_phase: P1
last_updated: '2026-11-12'
phases:
- id: P1
  name: The load decides every registered tool object inert, refusing it naming the distribution
  status: pending
  satisfies:
  - R1
  - R2
  - R4
  - R5
  - R6
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-tool-objects-inert/verify/p1.sh phase && sh spec/capability-tool-objects-inert/verify/p1.sh cli-legacy && sh spec/capability-tool-objects-inert/verify/p1.sh cli-modern && sh spec/capability-tool-objects-inert/verify/p1.sh replanted-legacy && sh spec/capability-tool-objects-inert/verify/p1.sh replanted-modern && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-legacy-1 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-legacy-2 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-legacy-3 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-legacy-4 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-modern-1 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-modern-2 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-modern-3 && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-modern-4
- id: P2
  name: Serving runs none of a capability's code but its handler; the cycle's checks, the ledger, the full verify
  status: pending
  satisfies:
  - R3
  - R5
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-tool-objects-inert/verify/p2.sh phase && sh spec/capability-tool-objects-inert/verify/p2.sh ledger && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-1 && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-2 && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-3 && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-4 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-1 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-2 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-3 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-4 && sh spec/capability-tool-objects-inert/verify/p2.sh full-ends
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — A capability's registered tool objects run none of its code when they are read

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/capability-tool-objects-inert/TECH.md`); the per-phase
checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs .

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

## Phase P1 — The load decides every registered tool object inert, refusing it naming the distribution
**Satisfies:** R1, R2, R4, R5, R6, R7 · **Depends on:** —
**Goal:** `load()` decides every registry entry but the core's with `_tool_violation` before its
first read of it, by the field rules of `PLAN.md` § 2, refusing a non-inert one in one line naming the
distribution (and the type or the field); the members load and serve unchanged; §7 says so in the
same commit.

- [ ] `core/capabilities.py`: `_type_name`, `_json_violation`, `_same`, `_default_violation`,
  `_return_type_violation` (with `_RETURN_CLASSES` and `_RETURN_ALIASES`), the field rules (`_a_str`,
  `_a_str_or_none`, `_a_schema`, `_a_schema_or_none`, `_excepted`), `_unnamed`, `TOOL_RULES` (a dict
  literal: named fields as keys, the default-rule fields as one unpacked dict comprehension over a
  tuple of names), `_tool_violation` and `_registry_violation`, above `_listing_violation`, as
  `PLAN.md` § 2 specifies (these names are what `verify/alternatives.py` sweeps; it reports a missing
  one as a gap). Walk `FunctionTool.model_fields` in `_tool_violation`, looking each rule up as
  `TOOL_RULES.get(field, _unnamed)`.
- [ ] `load()`: the three decisions of `PLAN.md` § 2 (`if held := _registry_violation(before):` then
  the refusal), replacing the `odd` lines, after the attribution, and after the resources are
  assembled. Touch no other line of `load()` (the sibling cycle's lines, `PLAN.md` § 5). Docstrings
  (`load()`, the module) follow.
- [ ] Tests, `@mark.unit`: the families `verify/rows.py` lists, in
  `test_a_capability_that_cannot_load_is_refused_naming_it` beside each member set (planted types in
  the capability module; values set after construction); the `served-tool` timing re-carried
  (`ODD_TOOL` replaces `FastMCP.add_tool` for its own tool, restoring it as it raises; the `plant`
  fixture restores `FastMCP.add_tool` on teardown); `CLI_UNLOADABLE` gains
  `tool-subclass-reads-name` and `tool-exact-parameters-value`;
  `test_every_function_tool_field_has_a_rule`, `test_a_field_no_rule_names_is_checked_by_the_generic_rule`,
  `test_an_inert_tool_of_every_accepted_shape_loads`, `test_a_tool_registered_before_the_load_is_decided_too`,
  `test_the_locked_model_holds_no_private_attribute_and_forbids_extras`.
- [ ] `tests/mutants.py`: re-plant every case whose anchor the change moves (`test_mutation_anchor_applies`
  names them), retargeting the five `tool-assembly` cases to the re-carried rows, and record each
  retarget or removal in the commit body; add a case for every alternative `verify/alternatives.py
  coverage p1` lists, beside every member set, or record it in its `EQUIVALENT` with why.
- [ ] `AGENTS.md` §7 (refusal bullet; the "No read of a loaded record runs capability code" paragraph,
  naming `issues/capability-tool-objects-served-copy.md`; the objects, not the classes or modules a
  capability's code can change at import) and § Testing (the new families), in this commit (R7).
  `tests/fixtures/served_surface.json` and the README do not change.
- [ ] Stage everything, then run the gate's modes one at a time (`cli-*`, `replanted-*` and each
  `mutants-*` shard under the 10-minute command cap: measured at the plan, about 3 s a case per era).
- **Verify:** `sh spec/capability-tool-objects-inert/verify/p1.sh` `phase`, `cli-legacy`, `cli-modern`, `replanted-legacy`,
  `replanted-modern`, `mutants-legacy-1` to `-4`, `mutants-modern-1` to `-4` (the frontmatter's chain).
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`, `tests/test_capabilities.py`,
  `tests/test_startup.py`, `tests/mutants.py`, `AGENTS.md`.

## Phase P2 — Serving runs none of a capability's code but its handler; the cycle's checks, the ledger, the full verify
**Satisfies:** R3, R5 · **Depends on:** P1
**Goal:** R3 shown by a test; the whole cycle's checks on the finished tree; every deferral seeded;
the profile's full verify green once.

- [ ] `test_a_served_capability_runs_none_of_its_code_but_its_handler` (`@mark.unit`): a
  `sys.monitoring` `PY_START` callback on a free tool id records code objects whose file lies in the
  planted package; two servers built from the loaded capabilities and their tools listed through the
  harness client in the selected era record nothing; one call of the planted tool records only its
  function, once. Its return type is `str` (`PLAN.md` § 5, Q-C).
- [ ] Deferral ledger: walk P1 and P2, this cycle's commit bodies, `PLAN.md` and `REVIEW.md` for
  "defer", "out of scope", "known limitation", "not fixed here", "left for" and "follow-up"; each
  needs an `issues/` seed and a `ROADMAP.md` entry (`verify/ledger.py`). The plan puts nothing off; a
  phase that puts work off files its seed and entry in its own commit.
- [ ] Then, with nothing else of this cycle running, the full verify's modes one at a time
  (`full-legacy-1` to `-4`, `full-modern-1` to `-4`, `full-ends`; the heavy runs the foreman
  schedules).
- **Verify:** `sh spec/capability-tool-objects-inert/verify/p2.sh` `phase`, `ledger`, `full-legacy-1` to `-4`, `full-modern-1` to `-4`,
  `full-ends` (the frontmatter's chain).
- **Touches:** `tests/test_capabilities.py`, `AGENTS.md` § Testing (the R3 test named).

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
