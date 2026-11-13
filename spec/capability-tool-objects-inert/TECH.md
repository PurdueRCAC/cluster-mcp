---
slug: capability-tool-objects-inert
title: A capability's registered tool objects run none of its code when they are read
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
  status: in_progress
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
  attempts: 2
  verify: sh spec/capability-tool-objects-inert/verify/p1.sh phase && sh spec/capability-tool-objects-inert/verify/p1.sh cli-legacy && sh spec/capability-tool-objects-inert/verify/p1.sh cli-modern && sh spec/capability-tool-objects-inert/verify/p1.sh replanted-legacy && sh spec/capability-tool-objects-inert/verify/p1.sh replanted-modern && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-legacy && sh spec/capability-tool-objects-inert/verify/p1.sh mutants-modern && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh pins && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh control && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-handshake-1 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-handshake-2 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-handshake-3 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-handshake-4 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-modern-1 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-modern-2 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-modern-3 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh sweep-modern-4 && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh report && sh spec/capability-tool-objects-inert/remediation/F5-gate.sh pins && sh spec/capability-tool-objects-inert/remediation/F5-gate.sh cases && sh spec/capability-tool-objects-inert/remediation/F5-gate.sh sweep-handshake && sh spec/capability-tool-objects-inert/remediation/F5-gate.sh sweep-modern
- id: P2
  name: Serving runs none of a capability's code but its handler; the cycle's checks, the ledger, the full verify
  status: in_progress
  satisfies:
  - R3
  - R5
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/capability-tool-objects-inert/verify/p2.sh phase && sh spec/capability-tool-objects-inert/verify/p2.sh ledger && sh spec/capability-tool-objects-inert/remediation/F1-gate.sh report && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-1 && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-2 && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-3 && sh spec/capability-tool-objects-inert/verify/p2.sh full-legacy-4 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-1 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-2 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-3 && sh spec/capability-tool-objects-inert/verify/p2.sh full-modern-4 && sh spec/capability-tool-objects-inert/verify/p2.sh full-ends
review:
  last_reviewed_commit: 697dc8f572f7e7e22b37dbad09ec87ad0eacf6c3
  verdict: changes-requested
  blocked_reason: 'N1 (CRITICAL): a return type''s class decided by its own namespace while FastMCP reads __module__ through the MRO; server builds run capability code (R2, R3, §7). Escalated to the maintainer at cycle 2; human gate on core/capabilities.py'
  cycle: 2
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
**Goal:** `load()` decides every registry entry (the core's included, as `PLAN.md` § 2 has it; amended at
build, 2026-11-12) with `_tool_violation` before its
first read of it, by the field rules of `PLAN.md` § 2, refusing a non-inert one in one line naming the
distribution (and the type or the field); the members load and serve unchanged; §7 says so in the
same commit.

- [x] `core/capabilities.py`: `_type_name`, `_json_violation`, `_same`, `_default_violation`,
  `_return_type_violation` (with `_RETURN_CLASSES` and `_RETURN_ALIASES`), the field rules (`_a_str`,
  `_a_str_or_none`, `_a_schema`, `_a_schema_or_none`, and `fn`'s: exactly a `types.FunctionType`
  whose `__module__` is exactly a `str`), `_unnamed`, `_undecided` (one WARNING per field per process,
  as `core/deprecation.py`'s `legacy_warning`), `TOOL_RULES` (a dict literal: the six named fields as
  keys, the eleven default-rule fields as one unpacked dict comprehension over a tuple of names),
  `_tool_violation` and `_registry_violation`, above `_listing_violation`, as `PLAN.md` § 2 specifies
  (these names are what `verify/alternatives.py` finds; it reports a missing one as a gap). Walk
  `FunctionTool.model_fields` in `_tool_violation` with one loop that looks each rule up as
  `TOOL_RULES.get(field)`; a field with none goes to `_unnamed`, and when that does not accept the
  value, `_undecided(field)` is called and the field is served undecided (R4 as amended).
- [x] `load()`: the two decisions of `PLAN.md` § 2 (`if held := _registry_violation(before):` then
  the refusal), replacing the `odd` lines, and after the resources are assembled. Touch no other line of `load()` (the sibling cycle's lines, `PLAN.md` § 5). Docstrings
  (`load()`, the module) follow.
- [x] Tests, `@mark.unit`: the families `verify/rows.py` lists, in
  `test_a_capability_that_cannot_load_is_refused_naming_it` beside each member set (planted types in
  the capability module; values set after construction); the `served-tool` timing re-carried
  (`ODD_TOOL` replaces `FastMCP.add_tool` for its own tool, restoring it as it raises; the `plant`
  fixture restores `FastMCP.add_tool` on teardown); the `declared` timing re-carried the same way (the
  planted module replaces the load's `_below` for its own tools module, restoring it as it raises;
  the fixture restores it), and `tool-without-a-module`'s cause follows `fn`'s rule; `CLI_UNLOADABLE` gains
  `tool-subclass-reads-name` and `tool-exact-parameters-value`;
  `test_every_function_tool_field_has_a_rule`, `test_a_field_no_rule_names_is_checked_by_the_generic_rule`,
  `test_an_inert_tool_of_every_accepted_shape_loads`, `test_a_tool_registered_before_the_load_is_decided_too`,
  `test_the_locked_model_holds_no_private_attribute_and_forbids_extras`; the generic-rule test asserts
  one WARNING per field per process (R4 as amended at sign-off, Q-D).
- [x] `tests/mutants.py`: re-plant every case whose anchor the change moves (`test_mutation_anchor_applies`
  names them), retargeting the `tool-assembly` and `declared` cases to the re-carried rows, and record
  each retarget or removal in the commit body; add a case for every alternative of the narrow set
  `verify/alternatives.py coverage p1` lists (34: 2026-11-12 · foreman ruling at plan sign-off: Q-E), beside every member set, or
  record it in its `EQUIVALENT` with why. Every other alternative is graded at review from the diff
  sweep, per the factory's mutation-testing method (operator's KB, `method/mutation-testing.md` §
  When a review is done).
- [x] `AGENTS.md` §7 (refusal bullet; the "No read of a loaded record runs capability code" paragraph,
  naming `issues/capability-tool-objects-served-copy.md`; the objects, not the classes or modules a
  capability's code can change at import) and § Testing (the new families), in this commit (R7).
  `tests/fixtures/served_surface.json` and the README do not change.
- [x] Stage everything, then run the gate's modes one at a time (`cli-*`, `replanted-*` and
  `mutants-*`, each under the 10-minute command cap: measured at the plan, about 3 s a case per era).
- **Build notes (2026-11-12).** The gate was red twice on the run's own unfinished work (`attempts: 2`), each
  fixed in the run and every mode rerun from the start: (1) `capability-other-exception-escapes` and
  `-keeps-registry` were killed only by `tool-without-a-module`, whose cause now comes from `fn`'s rule rather
  than the load's generic exit; retargeted to `raises-at-declared`, which still takes that exit; (2) the
  `tool-default-<field>` rows were generated from `TOOL_RULES`, so a mutant that took a field from the default
  rule removed its own killing row (collection, not a kill); the test now names the six typed fields and gives
  the rest to the default rule, and `test_every_function_tool_field_has_a_rule` pins that the table does too.
- **Verify:** `sh spec/capability-tool-objects-inert/verify/p1.sh` `phase`, `cli-legacy`, `cli-modern`, `replanted-legacy`,
  `replanted-modern`, `mutants-legacy`, `mutants-modern` (the frontmatter's chain; 2026-11-12 · foreman ruling at plan sign-off:
  the mutation modes run the narrow set, Q-E).
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`, `tests/test_capabilities.py`,
  `tests/test_startup.py`, `tests/mutants.py`, `AGENTS.md`.

### Remediation, review cycle 1 (F1, F2, F3) — reopened 2026-11-12

`REVIEW.md` cycle 1 routes F1 and F3 as one class, every refusal the tool rules can make held by the suite,
and F2 as R4's default branch pinned. The guards are right (the reviewer's reach probes: HEAD refuses every
input, running nothing); the suite did not hold them. No line of `core/capabilities.py` changes; the failure
handler and the module cache (the sibling `capability-reload-after-failure`'s) are untouched.

- [x] Rows in `test_a_capability_that_cannot_load_is_refused_naming_it`, beside each member set, each with its
  own wording, none of its code run, the registry cut back (`TOOL_DEPTH`, 18 kinds): the return type's alias
  state, a key of it (one colliding with `__origin__`, one not), its arguments, module and `Annotated`
  metadata tuple, `Annotated` metadata, a `Literal` argument, an origin of each alias kind; `task_config` keyed
  by a type of its own and with a key renamed, `tags` a set not its default; each slot but `__dict__` missing,
  a fields set naming no field, private state on a model with none, a JSON-like extra on a model that forbids
  extras. `PlantedTuple` joins the planted names.
- [x] The state rules over a model a newer FastMCP may give (a private attribute with a non-JSON default, or
  extras allowed, set on the installed model for the test): `test_a_tool_state_a_newer_model_refuses_is_refused_naming_it`
  (7 kinds) and `..._accepts_loads` (3), beside each member set. The default rule's comparison over defaults a
  FastMCP may declare: `test_the_default_rule_compares_node_for_node` (21 cases) and
  `test_a_default_made_from_the_other_fields_is_never_made`.
- [x] The liveness side: `test_a_return_type_that_holds_itself_loads_and_the_load_returns`, beside each member
  set, the load bounded at 10 s by `SIGALRM` (the load takes well under 1 s), a stall refusing the capability.
- [x] F2: `test_a_field_no_rule_names_passes_its_own_declared_default_unwarned`, beside each member set: with
  the fields whose declared default is not JSON-like (`tags`, `task_config` on 4.1.4, computed) dropped from
  the table, a tool holding those defaults and the members pass with no warning; another value of each is
  warned of exactly once.
- [x] Accepted shapes widened to what the walk's alternatives tell apart: a `Literal` of a `float`, an
  `Annotated` with JSON-like metadata.
- [x] `tests/mutants.py`: 40 cases, each killed by one of those rows (`replanted.py` selects them as new).
- [x] The class checker `remediation/F1-tool-rule-sweep.py` (+ `F1-gate.sh`): 453 mutants generated from the
  syntax tree of every decision of the tool-rule code, run in both eras, each killed or recorded equivalent
  with why (4 recorded), the review's 10 coverage observations among them.
- [x] `AGENTS.md` § Testing and §7's evidence list name the new rows and tests (same commit).
- **Verify (retuned at remediation):** P1's chain, then `F1-gate.sh` `pins`, `control`, the eight sweep shards
  and `report`. The sweep's shards run once on the final tree; P2's gate reads their `report` rather than
  re-running them.

### Remediation, review cycle 2 (N1) — reopened 2026-11-12

`REVIEW.md` cycle 2's N1 (CRITICAL): the class branch of `_return_type_violation` took a class's `__module__`
from its own namespace, `''` when it held none, while FastMCP reads `getattr(cls, '__module__', '')`; on every
accepted metaclass but `type` that read finds a base's, so a server build ran capability code. Routed to the
maintainer, who ruled the simpler rule: refuse, not resolve (wherever this round's text or `REVIEW.md` sets a
"refuse vs resolve" choice, refusing is the design). P1 and P2 reopened; one commit carries the code, its pins
and §7, since §7 names the pins (the profile's same-commit rule), so P2's R3 pin rides in P1's commit.

- [x] `core/capabilities.py`, `_return_type_violation`: every class a return type holds, at any depth, must
  carry its own `__module__` in its own namespace (`'__module__' in` the namespace read through `type`'s own
  descriptor), exactly a `str`; one that does not is refused, `… holds a class with no __module__ of its own`,
  naming the distribution and the field, before anything reads it. Nothing of the class runs in deciding: no
  `getattr` through a metaclass, the namespace's keys already decided exact `str`. **Amended at build:** a
  class defined in C (`str`, `dict`, `int`: no `Py_TPFLAGS_HEAPTYPE`, read through `type`'s own `__flags__`
  descriptor) holds no `__module__` in its namespace, `type` reading its module from its C name, so the rule
  as worded would refuse every member (their tools return `str` and `dict`) and the R3 test's `str`; such a
  class passes. No class statement or `type()` call makes one.
- [x] Rows beside each member set (`TOOL_DEPTH`, `tool-exact-return_type-no-own-module-<metaclass>`, 5 kinds):
  a return type of each accepted metaclass (`type`, `abc`'s, pydantic's, `enum`'s, `TypedDict`'s) with no
  `__module__` of its own, its base's a `PlantedStr` (`TypedDict`'s bases are `dict`'s); refused with that
  cause, `_RAN` empty, the registry cut back. Red on `10f77b1`'s source (copied aside and restored, `cmp`):
  all 20 rows; `abc`, pydantic's and `enum`'s ran the base's `__eq__` in the load's scratch build
  (`its tool 'planted_echo' cannot be served: SystemExit: 0`), `type` and `TypedDict` loaded.
- [x] The R3 pin through the CLI: `test_a_return_type_with_no_module_of_its_own_stops_startup_running_none_of_its_code`
  (`tests/test_startup.py`, one per metaclass, stdin closed): exit `runtime_error`, the distribution named with
  the cause, stdout empty. Red on `10f77b1`'s source, all five: `type` and `TypedDict` exit 0 and serve;
  the other three refused for the `SystemExit` their base's `__eq__` raised. Five starts, about 4 s an era.
- [x] `tests/mutants.py`: `capability-tool-return-type-own-module-unrequired` (the refusal dropped; killed by
  the 20 rows) and `capability-tool-return-type-c-class-refused` (classes defined in C refused; killed by the
  accepted shapes beside each member set), each killed in both eras.
- [x] The class checker `remediation/F5-gate.sh` (review cycle 2, N1; checkers number on after cycle 1's F4):
  `pins`, `cases`, and the sweep extended over the new decision: `F1-tool-rule-sweep.py` generates its mutants
  with the rest (461 now), and `sweep-<era>` runs the 14 that touch the class branch in each era.
- [x] `AGENTS.md` §7's rule list states the rule; § Testing and §7's evidence list name the rows and the CLI
  test (same commit).
- **Verify (retuned at remediation, cycle 2):** P1's chain, then `F5-gate.sh` `pins`, `cases`,
  `sweep-handshake`, `sweep-modern`. `F1-tool-rule-sweep.py`'s mutant ids in `_return_type_violation` are
  renumbered by the new decision, so the eight F1 shards re-run on this tree before `F1-gate.sh report` can
  pass: the heavy run the foreman schedules, with the full verify.

## Phase P2 — Serving runs none of a capability's code but its handler; the cycle's checks, the ledger, the full verify
**Satisfies:** R3, R5 · **Depends on:** P1
**Goal:** R3 shown by a test; the whole cycle's checks on the finished tree; every deferral seeded;
the profile's full verify green once.

- [x] `test_a_served_capability_runs_none_of_its_code_but_its_handler` (`@mark.unit`): a
  `sys.monitoring` `PY_START` callback on a free tool id records code objects whose file lies in the
  planted package; two servers built from the loaded capabilities and their tools listed through the
  harness client in the selected era record nothing; one call of the planted tool records only its
  function, once. Its return type is `str` (`PLAN.md` § 5, Q-C).
- [x] Deferral ledger: walk P1 and P2, this cycle's commit bodies, `PLAN.md` and `REVIEW.md` for
  "defer", "out of scope", "known limitation", "not fixed here", "left for" and "follow-up"; each
  needs an `issues/` seed and a `ROADMAP.md` entry (`verify/ledger.py`). The plan puts nothing off; a
  phase that puts work off files its seed and entry in its own commit.
- **Build notes (2026-11-12).** The R3 test runs beside each member set (`MEMBER_SETS`), a third
  server built for the call, and asserts the planted tool listed by both servers before it asserts
  nothing ran. It cannot be red on P1's commit (a planted capability that passes R1 and R2 serves
  inertly there too, `PLAN.md` § 3 row 3), so its teeth were shown with two mutants of the code it
  protects, each landed, red in the named assertion and reverted (`cmp`): `serve()` evaluating each
  registered function's annotations at registration (red: building and listing ran `__annotate__`
  twice), and `@mcp_tool`'s wrapper calling the function twice (red: a call ran `planted_echo`
  twice). `AGENTS.md` names the test in § Testing and in §7's evidence list, where the claim it
  proves sits. The ledger walk found no deferral beyond the two seeds the plan filed
  (`issues/capability-tool-objects-served-copy.md`, `issues/capability-record-checks-metaclass-code.md`),
  both present with ROADMAP entries; no commit body of the cycle defers anything. P2's gate has no
  re-planted mode, so `replanted.py`'s selection is not run here.
- [x] Then, with nothing else of this cycle running, the full verify's modes one at a time
  (`full-legacy-1` to `-4`, `full-modern-1` to `-4`, `full-ends`; the heavy runs the foreman
  schedules). Green on `0f34719`, 2026-11-12, each era: 44, 154, 513, and 4765 passed with 14
  skipped (login-shell rows for a shell this host lacks; CI installs every shell and fails a missing
  one); `full-ends` green.
- **Verify:** `sh spec/capability-tool-objects-inert/verify/p2.sh` `phase`, `ledger`, `full-legacy-1` to `-4`, `full-modern-1` to `-4`,
  `full-ends` (the frontmatter's chain).
- **Reopened at remediation (review cycle 1), 2026-11-12.** P2 built on P1, so it re-runs on the remediated
  tree: `phase` and `ledger`, then `F1-gate.sh report` (the sweep P1's gate ran on the same tree, read, not
  re-run), then the full verify, which the foreman schedules. Its earlier full-verify evidence (`0f34719`) no
  longer stands for this tree. Green on `4b04dad`, 2026-11-12: `phase` (706 passed an era), `ledger`,
  `report` (453 mutants, 449 killed and 4 equivalent an era); the full verify, each era: 44, 154, 513, and
  4947 passed with 14 skipped (the login-shell rows for a shell this host lacks; CI installs every shell);
  `full-ends` green.
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
