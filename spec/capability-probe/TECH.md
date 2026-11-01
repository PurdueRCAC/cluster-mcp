---
slug: capability-probe
title: Probe the cluster before advertising an installed capability
kind: feature
appetite: big
status: in_review
branch: feature/capability-probe
base: develop
current_phase: done
last_updated: '2026-11-01'
phases:
- id: P1
  name: A capability declares the commands it needs; one bounded lookup decides every ending
  status: done
  satisfies:
  - R2
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/capability-probe/verify/p1.sh phase && uv run python -I spec/capability-probe/remediation/F5-probe-timing.py all && sh spec/capability-probe/verify/p1.sh mutants-handshake-1 && sh spec/capability-probe/verify/p1.sh mutants-handshake-2 && sh spec/capability-probe/verify/p1.sh mutants-modern-1 && sh spec/capability-probe/verify/p1.sh mutants-modern-2
- id: P2
  name: Startup withholds what the cluster lacks, fails open within the bound, and skips in delegate mode or on request
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
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: downhill
  verify: sh spec/capability-probe/verify/p2.sh phase && sh spec/capability-probe/verify/p1.sh phase && uv run python -I spec/capability-probe/remediation/P2-exact-capability.py all && uv run python -I spec/capability-probe/remediation/F1-exact-record-values.py all && uv run python -I spec/capability-probe/remediation/F3-map-and-startup.py && sh spec/capability-probe/verify/p2.sh mutants-handshake-1 && sh spec/capability-probe/verify/p2.sh mutants-handshake-2 && sh spec/capability-probe/verify/p2.sh mutants-modern-1 && sh spec/capability-probe/verify/p2.sh mutants-modern-2
- id: P3
  name: The whole cycle's checks on the finished tree, the recipe on this head, the deferral ledger
  status: done
  satisfies:
  - R3
  - R10
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/capability-probe/verify/p3.sh phase && sh spec/capability-probe/verify/p3.sh ledger && sh spec/capability-probe/verify/p3.sh recipe && sh spec/capability-probe/verify/p3.sh equivalents && sh spec/capability-probe/verify/p3.sh full-legacy && sh spec/capability-probe/verify/p3.sh full-modern
review:
  last_reviewed_commit: 2339c0e
  verdict: changes-requested
  blocked_reason: F1 field values run capability code after load (§7 false); F3 AGENTS map/architecture; F5 deadline mutant
  cycle: 1
---

# TECH.md — Probe the cluster before advertising an installed capability

The **context engine and finite-state machine** for building this feature. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/capability-probe/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

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

**This cycle's own conventions.**

- The gates under `verify/` are frozen once this plan is signed off. A gate a build finds wrong is
  never edited: the foreman rules on it, and a wrapper under `spec/capability-probe/remediation/`
  carries the fix, as in `capability-extras`.
- Every gate removes the calling shell's `CLUSTER_MCP_SKIP_PROBES`. A build drives the CLI only under
  `bin/sandbox.sh`, never against a real cluster.
- The mutation modes are sharded by era and half so each fits the 10-minute command cap (about
  4–5 minutes each, at about 6 s a case as measured on the plan's prototype). Run them one at a time,
  never two at once (the footprint headers).
- Record each verify run under its phase as *Observed (date), on tree X*: the counts per step and era
  and each mode's time. Record a red run as *Attempt n* and bump `attempts:`.

---

## Phase P1 — A capability declares the commands it needs; one bounded lookup decides every ending
**Satisfies:** R2 · **Depends on:** —
**Goal:** the contract and the runner, with no startup change yet. A capability distribution declares
`commands` on the `Capability` its entry point names. A malformed declaration is refused at load with
the existing §7 refusal. The Slurm and RCAC members declare theirs. `core/probes.py` looks every
declared name up in one bounded call and decides each capability's verdict for every ending. Nothing
calls it at startup yet, so nothing a client sees changes.

- [x] `core/capabilities.py`:
  - `Capability.commands: tuple[str, ...] = ()`, last;
  - `COMMAND`;
  - `_checked()`: the field exactly a `tuple`, each element exactly a `str` (no subclass: PLAN §2.1),
    a full `COMMAND` match, declared once;
  - the refusals worded as PLAN §2.1 (`declared.py`'s `REASON` reads them);
  - the class docstring and the module docstring say what `commands` is and that a capability with
    none is served whenever it is installed.
- [x] `core/probes.py` (new) as PLAN §2.2: `PROBE_TIMEOUT`, `LOOKUP` (registered through
  `scripts.fixed`), `Verdict`, `Pending` (verdicts decided once, memoized), `start`, `unprobed`, `_ask`,
  `_parse`.
  - It splits on `\n` alone and needs the final newline.
  - The worker is a daemon that catches `BaseException` and passes the executor `timeout=bound`.
  - The comments are declarative, with no spec ids.
- [x] `slurm/capability.py`: `commands=('sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol')`;
  `rcac/capability.py`: `commands=('findscratch', 'myquota')`. Each module docstring says why those
  names.
- [x] `tests/harness.py`: `ProbeExecutor` (PLAN §2.7).
- [x] New `tests/test_probes.py`:
  - **`unit`**, each outcome row beside each member set (`MEMBER_SETS`, as `test_capabilities.py`
    builds the sets): `test_nothing_declared_runs_nothing`,
    `test_every_declared_command_is_looked_up_once`,
    `test_a_capability_is_withheld_when_one_of_its_commands_is_absent`,
    `test_every_ending_without_an_answer_serves_the_capability` (every ending `lookups.py` lists),
    `test_a_hung_probe_is_abandoned_at_the_bound` (bound patched to 0.3 s, an `Event` set in
    `finally`), `test_the_verdicts_are_decided_once`.
  - **`integration`:** `test_the_lookup_finds_only_what_exec_runs` (a `LocalShellExecutor`, a stub
    directory first on PATH through a test HOME's `.bash_profile`; a function, a `type` function and a
    non-executable file are absent) and `test_the_lookup_over_ssh` (`LoopbackSSH` with `home/bin`
    stand-ins present and absent; `DroppingSSH` for a lost connection).
- [x] `tests/test_capabilities.py`: `test_a_malformed_command_declaration_is_refused_at_load` (every
  kind `declared.py` lists, beside each member set),
  `test_a_planted_capability_declares_commands_with_no_core_edit`, `test_the_members_declare_their_commands`.
- [x] `tests/mutants.py`: a case for every P1 alternative `alternatives.py coverage p1` lists, each
  targeting a row beside each member set. A mutant shown equivalent goes in `alternatives.py`'s
  `EQUIVALENT` with why; that dict starts empty and is the one gate data build may fill.
- [x] `AGENTS.md`:
  - §7: the record with `commands`, the `type -P` lookup, the refusal at load;
  - the high-blast-radius list and the footguns gain `core/probes.py`;
  - § Testing: `test_probes.py`.
- **Verify:** `sh spec/capability-probe/verify/p1.sh phase && sh spec/capability-probe/verify/p1.sh mutants-handshake-1 && sh spec/capability-probe/verify/p1.sh mutants-handshake-2 && sh spec/capability-probe/verify/p1.sh mutants-modern-1 && sh spec/capability-probe/verify/p1.sh mutants-modern-2`
  (`phase` about 1 min; each of the four mutants modes, an era's half, about 5 min).
  *Plan-time dry run (2026-11-01):*
  - On the prototype cut to P1, `declared.py`, `lookups.py` and `docs_gate.py p1` were green, then
    `alternatives.py coverage p1` stopped red for want of cases (93 alternatives unmutated).
  - On today's tree it is red at `declared.py`.
  *Observed (2026-11-01), on the P1 build tree before its commit (the run quoted here):*
  - `phase` green in 18 s: `declared.py` (5 loaded, 23 refused, both members), `lookups.py`,
    `docs_gate.py p1`, `alternatives.py coverage p1` (84 alternatives, 84 cases, 0 equivalents), and
    the 11 named tests, 252 rows, passed in each era with none skipped.
  - `mutants-handshake-1` 42 of 42 killed (96 s), `mutants-handshake-2` 42 of 42 (93 s),
    `mutants-modern-1` 42 of 42 (95 s), `mutants-modern-2` 42 of 42 (93 s).
  - The full suite on the same tree, alone on the host: 3864 passed, 14 skipped (the bash 4.1
    `need_shell` rows, which CI runs) in each era; 360.3 s handshake and 353.0 s modern, against
    `c520432`'s 359.6 s and 359.5 s (P1's rows take about 4 s an era; the rest is noise).
  *Amendments at build:*
  - 84 alternatives, not the plan's 93: `probes.py` reuses `capabilities._cause` for a raised
    exception's text, so it adds no `_cause` of its own, and `_parse` drops the prototype's
    `isinstance(stdout, str)` (a result whose stdout is not a `str` raises in the worker and is
    decided as any raise is). `verdicts()` waits on an `Event`, not a queue, so no `except
    queue.Empty` decision exists to sweep (its `Exception` and `BaseException` alternatives would be
    equivalent). `Pending` is built for every start, and `unprobed()` posts every name found.
  - A worker thread that cannot start is one more ending, served with its reason (`except
    Exception`); an interrupt there still interrupts. `test_probes.py` gains
    `test_an_interrupt_while_the_probe_starts_still_interrupts` and
    `test_unprobed_serves_every_capability_and_runs_nothing` beside the named tests.
  - `test_the_lookup_over_ssh` runs three rows (present, absent, lost) beside both members, not
    beside each set: no mutant targets it, and the bash rows hold the lookup beside each set.
- **Remediation, review cycle 1 (2026-11-01): F5, the probe's timing (R2, and R5's bound).** The review's
  ship reviewer showed `self._answered.wait(self._bound)` in place of
  `self._answered.wait(self._deadline - time.monotonic())` surviving every probe row: `run()` asks for the
  verdicts straight after `start()`, so no row asked late. The frozen `alternatives.py` sweeps the
  probe's conditions, never a value a call is given.
  - [x] `tests/test_probes.py`: `test_the_deadline_is_taken_when_the_probe_starts`, beside every member
    set: with a 0.6 s bound and the lookup hung, `verdicts()` first asked for 0.7 s after `start()`
    decides within 0.3 s, unanswered; asked for at once, with the answer coming 0.2 s later, it waits for
    that answer (a hung lookup is released after 3 s whatever happens, so a wait with no bound ends).
  - [x] `tests/mutants.py`: `probe-timing-<what>`, 28 cases, every timing alternative with a case:
    where the deadline is taken (at the wait), what it is (the clock less the bound, the bound alone,
    the clock alone, the wall clock, the module's bound), what the wait is given (the bound, `None`, no
    timeout, zero, the deadline, the clock, the time past the deadline, the deadline plus the clock, the
    time left on the wall clock), what a late decision names and the bound kept (the module's), and the
    bound each part is handed (`start()`'s `Pending`, `_ask`, the executor call: the module's bound, the
    given timeout, zero; the timed-out reason; `start()`'s default; `unprobed()`'s `None`). Each targets
    a row beside every member set.
  - [x] `remediation/F5-probe-timing.py` (`coverage`, `cases`, `equivalents`): the 32 alternatives, the
    frozen sweep's 72 alternatives of `core/probes.py` still cased, and every line of `core/probes.py`
    that handles time reached by one or the other; each case killed in both eras; four equivalents
    planted with their targets green in both eras, each with why: the deadline taken just after the
    worker starts, the bound plus the clock, the wait floored at zero, `unprobed()`'s zero bound.
  - Red first: `probe-timing-wait-the-bound`, the review's survivor, killed by the new row beside every
    set (`failed with 'the deadline was not taken when the probe started'`); the coverage step went red
    on a timing line planted with no alternative, and green with it gone. `core/probes.py` is unchanged:
    its timing was right, and only its pin was missing.
  - P1's `verify:` runs the checker after `p1.sh phase`, before the four mutation halves.
  *Observed (2026-11-01), the remediation's third run of every distinct step, once each, in order, on the
  finished tree before its commit (the run quoted here):* `p1.sh phase` green in 18 s (`declared.py`,
  `lookups.py`, `docs_gate.py p1`, `alternatives.py coverage p1` with 84 alternatives, 252 passed in each
  era); `F5-probe-timing.py all` green in 582 s (32 timing alternatives, 28 cased, 4 equivalent; the
  frozen sweep's 72 alternatives of `core/probes.py` cased; 12 timing lines reached; 28 of 28 killed in
  each era; the 4 equivalents' 223 target rows passed in each era); `mutants-handshake-1` 42 of 42
  killed (95 s), `-2` 42 of 42 (94 s), `mutants-modern-1` 42 of 42 (97 s), `-2` 42 of 42 (94 s). The
  `p1.sh phase` step also stands in for P2's (its inputs are the same tree).
  - *Attempt 1 (2026-11-01), before the commit:* the remediation's first gate run went red at the
    checker's `equivalents`: every equivalent's child exited 1 with `bin/sandbox.sh: HOME: unbound
    variable`. The checker cleared the process environment and then built the era's from it, so the
    child got almost none. Fixed in the checker (the era's environment taken first); the four
    equivalents then passed their targets in both eras, and every step ran again from the start. The
    frozen `alternatives.py`'s `run_equivalents` builds its environment in the same order; its
    `EQUIVALENT` is empty, so it never runs.
- **Touches:** `core/capabilities.py`, `core/probes.py`, `slurm/capability.py`, `rcac/capability.py`,
  `tests/harness.py`, `tests/test_probes.py`, `tests/test_capabilities.py`, `tests/mutants.py`, `AGENTS.md`;
  with review cycle 1's F5, `remediation/F5-probe-timing.py`.

## Phase P2 — Startup withholds what the cluster lacks, fails open within the bound, and skips in delegate mode or on request
**Satisfies:** R1, R2, R3, R4, R5, R6, R7, R8, R9, R10 · **Depends on:** P1
**Goal:** `run()` probes once in `ssh` and `local` modes, after the site read and after checking the
budget against every installed capability, so every refusal comes first. It builds the server from what
the probe kept. It logs one
line per withheld or unanswered capability. `delegate` mode and the override skip the probe with one
line. Every refusal still comes first. The documents R10 names describe all of it.

- [x] `core/deprecation.py`: `LEGACY_ENV['CLUSTER_MCP_SKIP_PROBES'] = None` (type and comment as PLAN
  §2.5); `env_setting` returns `(value or None, name)` for a variable with no legacy name, with no
  warning.
- [x] `core/__init__.py`:
  - the `--skip-probes` flag (`APP_USAGE`, Options, Environment Variables);
  - `_resolve_skip_probes`, `_probe` and `_served` as PLAN §2.4, with the four lines worded exactly as
    there (`docs_gate.py` reads the withheld line from `_served`'s source);
  - `run()`'s `try` takes, in order: the budget, the override, the site read, the budget check against
    `base_instructions(installed())`, the probe and its verdicts, then `create_mcp_server(…,
    capabilities=served)`.
- [x] `core/server.py`: the `capabilities` docstring (PLAN §2.6); no code change.
- [x] `tests/conftest.py`: the session `autouse` fixture `skip_probes` (PLAN §2.7).
  `tests/test_hygiene.py::test_the_suite_skips_probes_by_default` pins it.
- [x] `tests/test_env.py`: `test_every_variable_has_its_legacy_name` skips None entries;
  `test_a_variable_without_a_legacy_name` (value, empty, and no warning).
- [x] New `tests/test_probe_startup.py`, `unit` in process (the test removes the variable), with each
  row that can differ by member set run beside each:
  - `test_local_and_ssh_probe_once_after_the_executor`;
  - `test_the_server_is_built_from_what_the_probe_keeps`;
  - `test_the_served_instructions_name_exactly_the_served_tools`: the real `create_mcp_server` over
    each served set, at least one member withheld (R3);
  - `test_the_probe_follows_the_site_read_and_is_bounded`: the order executor, site read, budget
    check, probe, server; with the bound 0.6 s, a 0.5 s site read and a hung probe, within 1.4 s,
    every capability served;
  - `test_delegate_runs_no_probe_and_says_so`;
  - `test_the_override_skips_every_probe`: in `local` and in `ssh` mode, the flag; the variable as
    `1`, `0` and a space; empty probes;
  - `test_any_non_empty_override_value_skips`: `maybe` and `0` skip, never exit 2 (any non-empty value
    is set);
  - `test_no_probe_runs_before_a_refusal`: load refusal, connect failure, `--generate-token`, a budget
    of 0, one that is not a number, and one short of every capability;
  - `test_the_budget_never_depends_on_the_answer`.

  Then `integration` CLI drives under `bin/sandbox.sh`, the variable removed, a `.bash_profile` that
  stubs PATH and logs logins:
  - `test_a_withheld_capability_is_not_served_over_stdio`: each member absent and both, one per
    family;
  - `test_a_probe_without_an_answer_serves_every_capability_over_stdio`: a profile that ends the login
    at once gives the fast "could not run" ending. The suite never waits out the real 10 s bound;
    `drives.py` does;
  - `test_withheld_with_stdin_closed_and_over_http`.

  About 10 drives per era: hold to it (CI budget, PLAN §6).
- [x] `tests/test_transports.py`, `tests/test_cli.py`, `tests/test_exec_mode.py` and
  `tests/test_site_startup.py` stay green unedited under the suite's default. If one cannot, say why in
  the commit body, and do not weaken an assertion.
- [x] `tests/mutants.py`: a case for every P2 alternative `alternatives.py coverage p2` lists, each
  targeting a row beside each member set (`SET_EQUIVALENT` with why, where a set cannot observe one).
- [x] Re-anchor the existing cases whose anchors move with `run()`'s new statements, keeping each id
  and `why`: the plan's prototype broke `delegate-gets-shared-middleware`,
  `capability-load-placed-before-statement-7-of-its-body` and
  `capability-load-placed-before-statement-3-of-its-try` (`test_mutations.py::test_mutation_anchor_applies`).
  `capability-extras`' F7 placement cases number `run()`'s statements: a case whose mutant no longer
  exists is retired through `verify/retired.txt` with the phase and the reason, never deleted
  silently (`baseline.sh` → `kept.py`).
- [x] `AGENTS.md`:
  - §4: the probe step on the shared executor, after the site read and the budget check and before the
    server is built, every refusal first, `PROBE_TIMEOUT` and its 10 s, fail open, `delegate`,
    `--skip-probes`;
  - §9: the base is composed from the served capabilities;
  - § Configuration: the `CLUSTER_MCP_SKIP_PROBES` row (any non-empty value, `0` included) and the
    sentence on `env_setting` reading a variable with no legacy name;
  - § Testing: the suite's default and how a probe test opts in, plus `test_probe_startup.py`.
- [x] `README.md`, beside § Execution Modes or the tool inventory:
  - an installed capability is served only where the cluster has what it needs;
  - the `withheld` line as `_served` formats it, and the unanswered line;
  - `--skip-probes` and the variable;
  - `delegate` mode serves every installed capability.
- **Verify:** `sh spec/capability-probe/verify/p2.sh phase && sh spec/capability-probe/verify/p1.sh phase && uv run python -I spec/capability-probe/remediation/P2-exact-capability.py all && sh spec/capability-probe/verify/p2.sh mutants-handshake-1 && sh spec/capability-probe/verify/p2.sh mutants-handshake-2 && sh spec/capability-probe/verify/p2.sh mutants-modern-1 && sh spec/capability-probe/verify/p2.sh mutants-modern-2`
  (`phase` about 4 min, the startup test files included; each of the four mutants modes, an era's half,
  about 4 min).
  `sh spec/capability-probe/verify/p2.sh pre-push` (7 s) is the docs and quick drives on their own.
  *Plan-time dry run (2026-11-01):*
  - On the prototype, `startup_order.py`, `drives.py all` (41 s) and `docs_gate.py p2` were green, then
    `alternatives.py coverage p2` stopped red for want of cases (79 alternatives unmutated).
  - On the P1 cut, `startup_order.py` was red: there was no probe step.
  - On today's tree it is red at import.
  *Observed (2026-11-01), on the P2 build tree before its commit (the run quoted here):*
  - `p2.sh phase` green in 3 min 55 s: `startup_order.py` ok; `drives.py all` ok (withholding 4.8 s,
    hanging 12.0 s, stdin closed 0.9 s and 10.9 s, HTTP 0.9 s, override 5.6 s, refusals 5.0 s);
    `docs_gate.py p2` ok; `alternatives.py coverage p2` ok (79 alternatives, 80 cases, 0 equivalents,
    1 set-equivalent); the named tests and files, 553 passed in each era (93.8 s handshake, 93.1 s
    modern), none skipped.
  - `p1.sh phase` (P1's file was touched) green in 18 s: `declared.py` (5 loaded, 23 refused, both
    members), `lookups.py`, `docs_gate.py p1`, `alternatives.py coverage p1` (84 alternatives, 84
    cases), 252 passed in each era.
  - `remediation/P2-exact-capability.py all` green in 31 s: 16 kinds beside 4 member sets and a
    control; 4 alternatives, 4 cases, 4 of 4 killed in each era.
  - `mutants-handshake-1` 40 of 40 killed (87 s), `mutants-handshake-2` 40 of 40 (88 s),
    `mutants-modern-1` 40 of 40 (88 s), `mutants-modern-2` 40 of 40 (89 s).
  - The full suite on the same tree, alone on the host (`p2.sh full-legacy`, `full-modern`): 4382
    passed, 14 skipped (the bash 4.1 `need_shell` rows, which CI runs, as at P1) in each era; 395.1 s
    handshake and 381.7 s modern, against `c520432`'s 359.6 s and 359.5 s (+9.9 % and +6.2 %, inside
    the 20 % the foreman set; P1 alone measured 360.3 s and 353.0 s).
  - A first `drives.py all` went red on `hang: a probe outlived its bound`: its `pgrep -f 'sleep 61'`
    matched the calling shell, whose own command line held that text. With no such text in the
    caller it is green; a timeline of the hang drive showed no `sleep 61` left once the drive ended.
    Not a product red, and the gate was not edited.
  *Amendments at build (2026-11-01):*
  - **The foreman's ruling, as judge: a capability record is exactly `Capability` (R1, R2, and R9 as it
    bears on load refusals).** P1's load took any `isinstance(value, Capability)`, so a subclass could
    override how a field is read, and its code would run when startup reads `commands` or the server
    reads `tools`, `instructions` or `resources`, outside the load's guard: the class P1 closed for
    `tuple` and `str` subclasses. `_checked` now requires `type(value) is Capability`; anything else is
    refused at load, naming the distribution, as `the entry point names a <type>, not a Capability`
    (the existing §7 wording). P2 now also satisfies R2. Pinned by:
    - `test_capabilities.py`: an `UNLOADABLE` family `subclass-reads-<field>`, one row for every field
      of the record (`dataclasses.fields`, so a field added later gets one) and one for a subclass that
      adds nothing, beside every member set, in `test_a_capability_that_cannot_load_is_refused_naming_it`;
    - `test_startup.py`: `subclass-reads-commands` in `CLI_UNLOADABLE`, so one subclass is driven
      through the CLI over the raw wire, with stdin closed and over HTTP (every kind with
      `CLUSTER_MCP_TEST_EVERY_KIND=1`);
    - `remediation/P2-exact-capability.py` (the frozen `alternatives.py` sweeps only the declared-command
      checks): `checker` plants every field read through `__getattribute__` and through a data
      descriptor, a plain and a dataclass subclass, an object whose `__class__` claims `Capability`
      and another module's class named `Capability`, beside every member set, each refused naming its
      distribution with none of its code run, and a plain `Capability` loading as a control;
      `coverage` and `cases` sweep the type check's alternatives (always, never, negated, and
      `isinstance`), each killed beside every member set in both eras.
    - Red first, on `e025c37`'s product with these tests: the 28 in-process rows (7 kinds × 4 sets)
      failed, each loading the subclass (`got ''`), and the 3 CLI rows failed, the server starting
      (exit 0) instead of refusing. The checker went red on `e025c37`'s `isinstance` check (every
      subclass kind loaded, and the field-read and `__class__` kinds ran their code during the load),
      green on the exact check.
    - It touches P1's file, so P2's `verify:` re-runs `p1.sh phase`, then the checker, before the four
      mutation halves. AGENTS §7 (the refusal list, a bullet of its own, and the footgun) says the
      record must be exactly `Capability`.
    - Re-anchored on the new line, ids and `why` kept: `capability-type-unchecked`,
      `capability-check-isinstance-capability-always`, `capability-check-isinstance-capability-negated`
      (the last now plants the negation `alternatives.py`'s rules give). New:
      `capability-check-exact-capability-isinstance`.
  - `test_probe_startup.py` holds more than the named tests: `test_every_ending_without_an_answer_serves_every_capability`
    (each ending, `SystemExit` with 0 and a text, a `BaseException` of its own, `KeyboardInterrupt`
    raised in the worker, a non-result, a hang, each sentinel code and a malformed answer, in `local`
    over stdio and HTTP and in `ssh` over stdio and SSE, beside every set) and
    `test_an_interrupt_while_waiting_for_the_probe_interrupts_the_start` (a real SIGINT to the main
    thread while it waits: `keyboard_interrupt`, nothing built, no line). Every in-process start
    records each step, and the order tests compare the whole sequence (`ORDER`), so each placement of
    the three probe statements is observed, not inferred. `test_no_probe_runs_before_a_refusal` adds a
    budget short of every capability read from the legacy `RCAC_INSTRUCTIONS_BUDGET`, which is what
    kills `env_setting`'s no-legacy branch taken always. `test_withheld_with_stdin_closed_and_over_http`
    runs four drives (Slurm absent, and a login that ends at once, each with stdin closed and over
    HTTP), and `test_a_withheld_capability_is_not_served_over_stdio` a fourth row with every command
    present (R3 through the CLI): 9 drives an era.
  - `SET_EQUIVALENT` (the gate data build may fill) records `env-no-legacy-value-empty-kept`:
    `env_setting` handing back an empty value as itself rather than None is visible only to the
    resolver's own row (`test_env.py`), since `_resolve_skip_probes` reads both as unset.
  - Two cases plant one tree (`probe-step-check-placed-before-statement-5-of-its-try` and
    `probe-step-probe-placed-before-statement-4-of-its-try`: the check and the probe exchanged), so 80
    cases sweep 79 alternatives. Three cases beyond the sweep place `capability-extras`' load before
    each new statement of the `try` (`capability-load-placed-before-the-{override,budget-check,probe}-of-its-try`),
    so that cycle's placement sweep still covers every boundary; no case was retired.
  - `tests/test_transports.py`, `test_cli.py`, `test_exec_mode.py` and `test_site_startup.py` are
    unedited and green under the suite's default.
- **Remediation, review cycle 1 (2026-11-01): F1, no read of a loaded record runs capability code (R2,
  R9; §7), and F3, AGENTS describes the probe wherever it lists the core's modules or startup (R10).**
  - **F1, the class, found by reading** what `load()`, `composed()`, `base_instructions()`,
    `create_mcp_server` (`_listed`, `_tools_of`, `_resources_of`, `serve()`), the budget check, `_probe`,
    `_served` and `probes` read from a `Loaded` and its `Capability`: `name` (hashed by the load, ordered
    by `_listed`), `order` (ordered by `composed()`), `tools` (`+`'d and compared by the load's
    attribution), `instructions` (stripped, scanned, joined), `resources` (iterated), each entry (keys
    looked up), its keys (compared on lookup), `uri` (hashed, compared, `startswith`, read by FastMCP),
    `name` and `description` (read by FastMCP), `executor` (`is True`), `commands` and each command
    (P1's exact checks), and `Loaded.distribution` (ordered by `composed()` and `_listed`, formatted by
    `_served`). Each was an `isinstance` check (`order` refusing a `bool`), so a subclass loaded and its
    operations ran after the load: the review's `order.__eq__` that exits ended the start with exit 0
    and no message.
  - [x] `core/capabilities.py`: every one of those values is checked exact (`type(...) is`) before the
    load uses it, `order` exactly `int`, each entry exactly `dict`, every key exactly `str` (checked
    before any lookup), `uri` then `name` and `description` exactly `str`, and the distribution's name
    exactly a non-blank `str` (else no name, named by its entry point's value). A refusal formats a
    value only once it is exactly a built-in type (`_shown`, the executor's repr only for a `bool`, an
    `int` or None). The handler stays the capability's code: FastMCP registers it and a request calls
    it. A capability's tools (each a `FunctionTool` holding its function) are its code too, read by
    FastMCP as it registers them; that boundary is not deferred: §7 says it as it holds, and the
    report asks the foreman whether tools should get the same exactness.
  - [x] Pins: `test_capabilities.py`'s `exact-<site>` kinds in `UNLOADABLE` (`EXACT_SITES`: each field of
    the record from `dataclasses.fields`, a command, a resource entry, a key of one, each value of one
    but the handler from the core's own entry), each a subclass of `str`, `int`, `tuple` or `dict`
    whose every operation in `OPERATIONS` exits once its record is built, refused for its type beside
    every member set with none of those operations run; `test_a_distribution_name_of_a_type_of_its_own_is_no_name`
    beside every set; `exact-order` added to `test_startup.py`'s `CLI_UNLOADABLE`, so the CLI drives it
    over the raw wire, with stdin closed and over HTTP (every kind with `CLUSTER_MCP_TEST_EVERY_KIND=1`).
    `MALFORMED` gains `resource-open-unmarked` (`has executor None`), and `resource-uri-not-a-str` now
    reads `one of its resources has a int uri, not a str` (a URI not exactly a `str` is never formatted).
  - [x] The `declared` timing of `UNLOADABLE` and of the interrupt rows moved from a `tools` name of a
    type of its own (now refused for its type before its `+` can run) to the module its tool names, a
    `str` of a type of its own whose `==` runs the statement when the load attributes the tool: the
    one declared value capability code can still answer while the load reads it. Every case those rows
    kill keeps its targets.
  - [x] `tests/mutants.py`: capability-extras' 22 cases on the replaced checks re-anchored on the exact
    checks, ids, targets and `why` kept (their mutants now the exact checks' always, never, negated and
    `isinstance` forms); 30 new cases (`capability-*-exact-*`, `capability-shown-*`,
    `capability-distribution-name-exact-*`) for the alternatives the rules give the new checks, each
    targeting a row beside every member set.
  - [x] `remediation/F1-exact-record-values.py` (`checker`, `coverage`, `cases`, `cli`): 14 sites (from the
    record's fields and the core's entry keys, so a later one is covered), 29 values of a type of their
    own (a plain subclass and an all-operations one; a `bool` order) beside every member set, each
    refused naming its distribution with none of its code run, and an exact control whose every loaded
    record, the members' too, holds only exact values; every alternative of the 8 exact checks cased;
    each case killed in both eras; every `exact-<site>` kind driven through the CLI over the three
    transports in both eras.
  - Red first, on `949efb5`'s product (the tree's product until this fix): the 44 in-process
    `exact-<site>` rows of the 11 sites P1 had not made exact failed (`order` loaded; the others refused
    as `SystemExit: 0` when the load's own hash, strip or iteration ran their code); the 3 `exact-order`
    CLI drives exited 0 after `Execution mode: local` with nothing on stderr, as the review saw; the 4
    distribution rows loaded; the checker reached 20 of its 116 refusals, a planted name's `strip`
    escaping the load as `SystemExit`. Its coverage went red on an alternative planted with no case.
  - [x] **F3**: § Repository map gains a `probes.py` row; the `__init__.py` row names `_resolve_budget()`,
    `_resolve_skip_probes()`, `_read_site()`, `_probe()`, `_served()` and `--skip-probes`; the
    `server.py` row says `run()` gives the capabilities the probe kept; the `capabilities.py` row names
    the exact values; each member's `capability` row names its `commands`. § Architecture & data flow
    says the site read, then the probe in `ssh` and `local` modes, run before any request, and what
    `delegate` and `--skip-probes` do. § Project says an installed capability whose commands the
    cluster lacks is not served. `remediation/F3-map-and-startup.py` evaluates the property from the
    code: every core module that defines anything has a map row, the `__init__.py` row names every
    method `run()` calls on itself, each member row names every command its loaded record declares, and
    § Architecture names each startup step. Red first on `903ab6a`'s AGENTS.md (20 gaps), green after;
    it found `_resolve_budget()` and `_read_site()` unnamed beside the probe's two.
  - [x] AGENTS §7 (the refusal list and the record's bullet, now "No read of a loaded record runs
    capability code", naming what does run it), the `capabilities.py` footgun, § Testing for the three
    test files, and the `capabilities.py` module, `Capability` and `_identity` docstrings say exactly
    what holds.
  - P2's `verify:` runs the three checkers after `P2-exact-capability.py`, before the four mutation halves.
  *Observed (2026-11-01), the same run:* `p2.sh phase` green in 242 s (`startup_order.py`, `drives.py
  all`, `docs_gate.py p2`, `alternatives.py coverage p2` with 79 alternatives and 80 cases, 556 passed
  in each era); `p1.sh phase` the run above, standing in; `P2-exact-capability.py all` green in 30 s (4
  of 4 killed in each era); `F1-exact-record-values.py all` green in 284 s (14 sites, 29 values beside 4
  sets, 116 refused as expected, the controls' records exact; 8 checks, 44 alternatives, 47 cases, 47 of
  47 killed in each era; 13 kinds, 39 CLI drives passed in each era); `F3-map-and-startup.py` green in
  under 1 s (26 core modules, 8 methods `run()` calls, 2 members); `mutants-handshake-1` 40 of 40 (89
  s), `-2` 40 of 40 (88 s), `mutants-modern-1` 40 of 40 (87 s), `-2` 40 of 40 (90 s).
- **Touches:** `core/__init__.py`, `core/deprecation.py`, `core/server.py`, `tests/conftest.py`,
  `tests/test_probe_startup.py`, `tests/test_env.py`, `tests/test_hygiene.py`,
  `tests/mutants.py`, `AGENTS.md`, `README.md`; with the ruling, `core/capabilities.py`,
  `tests/test_capabilities.py`, `tests/test_startup.py`, `remediation/P2-exact-capability.py`, and
  `verify/alternatives.py`'s `SET_EQUIVALENT` (gate data). `tests/harness.py` needed no change.
  With review cycle 1's F1 and F3: `core/capabilities.py`, `tests/test_capabilities.py`,
  `tests/test_startup.py`, `tests/mutants.py`, `AGENTS.md`, `remediation/F1-exact-record-values.py`
  and `remediation/F3-map-and-startup.py`.

## Phase P3 — The whole cycle's checks on the finished tree, the recipe on this head, the deferral ledger
**Satisfies:** R3, R10 · **Depends on:** P2
**Goal:** every independent check once more on the finished tree, and the surface and suite against
`c520432`. Every alternative of both phases covered, every recorded equivalent proven, the release
recipe's offline steps on this head, the full verify, and the ledger.

- [x] Run `p3.sh phase`. Fix the product, never a gate: a gate defect goes to the foreman.
- [x] Record the suite's time per era against `c520432`'s 359.6 s (handshake) and 359.5 s (modern),
  local, and the projection in PLAN §6. A growth beyond about 60 s an era is a raised hand before
  publish: the CI job has 20 minutes for both eras.
- [x] Downstream seeds, notes only, with no status change:
  - append to [`issues/lmod-tool-group.md`](../../issues/lmod-tool-group.md)'s Notes: `module` is a
    function and its tools run `$LMOD_CMD`, so its probe needs a second kind of declared data beside
    `commands`, a core edit in that cycle;
  - append to [`issues/xdu-storage.md`](../../issues/xdu-storage.md)'s Notes: it declares no probe,
    since its tools offer the install where `xdu` is missing.
- [x] **The deferral ledger.** Walk P1–P3 and PLAN for "defer", "follow-up", "out of scope", "known
  limitation", "left for" and "not fixed here", and confirm each has an `issues/` file and a
  `ROADMAP.md` entry. The plan filed one:
  [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md) (the on-demand
  mutation workflow already exceeds its 30-minute job, and this cycle adds cases) and
  [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md) (a server
  killed mid-probe leaves the probe's `local` process group running, as any `local` call's), each with
  its ROADMAP entry. `ledger.py` checks every link.
- [x] Standing items carried from `capability-extras`' last phase: the recipe's offline steps on this
  head (`p3.sh recipe`), and the full verify in both halves.
- **Verify:** `sh spec/capability-probe/verify/p3.sh phase && sh spec/capability-probe/verify/p3.sh ledger && sh spec/capability-probe/verify/p3.sh recipe && sh spec/capability-probe/verify/p3.sh equivalents && sh spec/capability-probe/verify/p3.sh full-legacy && sh spec/capability-probe/verify/p3.sh full-modern`
  (`phase` about 3 min; `ledger` and `recipe` seconds; `equivalents` seconds per equivalent; each full
  half about 6 min).
  *Plan-time dry run (2026-11-01), on the prototype:* `baseline.sh` green in 11 s (24 tools,
  4 resources, 660 cases kept); `ledger` and `recipe` green in about 1 s each.
  *Observed (2026-11-01), on the P3 build tree before its commit (the run quoted here): the product and
  tests as at `a957c85`, the two notes appended. The new seed, its ROADMAP entry and this record were
  written after; `ledger` and `recipe` ran again on the finished tree, green.*
  - `phase` green in 65 s: `declared.py` (5 loaded, 23 refused, both members), `lookups.py`,
    `startup_order.py`, `drives.py all` (withholding 4.7 s, hanging 12.0 s, stdin closed 0.9 s and
    10.9 s, HTTP 0.9 s, override 5.7 s, refusals 5.1 s), `docs_gate.py p2`, `alternatives.py coverage
    all` (163 alternatives in the four files, 164 cases, 0 equivalents), and `baseline.sh` (24 tools,
    4 resources, 1477 characters of instructions, equal to `c520432`'s; 513 test functions and 660
    cases kept, none retired; fixture and `test_surface.py` byte-identical; no added skip).
  - `ledger` green.
  - `recipe` green in 1 s: 8 artifacts (a wheel and an sdist of each of the four distributions, at
    0.1.5) passed `twine check --strict`, and the four sdists are clean.
  - `equivalents` green in 4 s, with nothing to plant: both phases killed every case, so `EQUIVALENT`
    is empty. The one `SET_EQUIVALENT` row (`env-no-legacy-value-empty-kept`) is held by `coverage`
    and was killed by `test_env.py` in P2's mutation halves.
  - `full-legacy` green in 409 s: 4382 passed, 14 skipped, in 407.2 s. `full-modern` green in 391 s:
    4382 passed, 14 skipped, in 389.4 s, then `cluster-mcp --help` under `bin/sandbox.sh`. The 14 are
    the bash 4.1 `need_shell` rows (`tests/conftest.py`: "bash 4.1 or later is not installed here"),
    which the CI legs run. No other suite ran on the host during either half.
  - **Suite time against `c520432`** (359.6 s, 359.5 s): handshake 407.2 s (+47.6 s, +13.2 %), modern
    389.4 s (+29.9 s, +8.3 %); P2 measured 395.1 s and 381.7 s, P1 360.3 s and 353.0 s. PLAN §6
    projected about +20 s an era; the cycle grew more than that, within the 60 s raised hand. On CI,
    where `c520432` takes about 6.3 min an era (about 1.05 × local), that is about 7.1 and 6.8 min; with
    PLAN's ×1.6 on the growth alone, about 7.6 and 7.1 min. Both eras together stay inside the job's
    20 minutes either way.
  *Amendments at build (2026-11-01):*
  - **The foreman's addition to the ledger, as judge:** bare `cluster-mcp-sandbox.*` directories pile
    up in the host's `TMPDIR` (18,061 on the build host), because `bin/sandbox.sh:59-60` removes its
    directory from a trap SIGKILL never runs, and several harnesses stop a sandbox group with SIGKILL.
    Pre-existing and outside the GOAL; filed as
    [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md), `unshaped`,
    with its entry in ROADMAP Part III. Measured on this tree by diffing the host `TMPDIR` around each
    run, deleting nothing: `p3.sh phase` (with `drives.py all`), `recipe` and `equivalents` left none;
    each full half left 59 (handshake) and 58 (modern); this cycle's integration rows, run alone in
    each era, left none from `test_probe_startup.py` (its drives point `TMPDIR` at the test's own
    directory) and one or two from `test_probes.py::test_the_lookup_over_ssh`, through the existing
    `LoopbackSSH.close()`.
- **Remediation, review cycle 1 (2026-11-01).** P1 and P2 were reopened for F1, F3 and F5 (their
  amendments); P3 reopened with them, its gate unchanged, and ran again on the remediated tree after
  theirs, every step once.
  - *Attempt 1 (2026-11-01), before the commit:* the second run of every step was green up to
    `full-legacy`, which went red on 10 rows, every one a SIGINT row:
    `test_launch.py::test_a_signal_death_is_reported_and_reraised[*-exit-130]` (6) and
    `test_probe_startup.py::test_an_interrupt_while_waiting_for_the_probe_interrupts_the_start` (4). The
    builder had started that run as a disowned background job of a non-interactive shell, which starts
    its children with SIGINT ignored; the same 4 interrupt rows failed alone when started that way and
    passed in the foreground and under the harness's own background runner. Not a product red. The
    runner now refuses to start with SIGINT ignored, and every step ran again from the start.
  *Observed (2026-11-01), the same run as P1's and P2's:* `phase` green in 65 s (`declared.py`,
  `lookups.py`, `startup_order.py`, `drives.py all`, `docs_gate.py p2`, `alternatives.py coverage all`
  with 163 alternatives and 164 cases, `baseline.sh`: 24 tools, 4 resources, 1477 characters of
  instructions equal to `c520432`'s, 513 functions and 660 cases kept, none retired); `ledger`,
  `recipe` and `equivalents` green; `full-legacy` green in 395 s, 4507 passed and 14 skipped (the bash
  4.1 `need_shell` rows, which CI runs) in 392.8 s; `full-modern` green in 393 s, 4507 passed and 14
  skipped in 390.7 s, then `cluster-mcp --help` under `bin/sandbox.sh`. Against `c520432`'s 359.6 s
  and 359.5 s: +33.2 s (+9.2 %) and +31.2 s (+8.7 %), within the 20 %; P3's own run measured 407.2 s
  and 389.4 s. The remediation adds 125 rows an era: the `exact-<site>` rows (52 in process, 3 CLI
  drives), 4 distribution rows, 4 deadline rows (about 0.9 s each), 4 `resource-open-unmarked` rows,
  and `test_mutations.py`'s anchor row for each of the 58 new cases; the full kind matrix stays in the
  checkers. Written after the run,
  this record touched only `TECH.md`, so `ledger` ran again on the finished tree, green.
- **Touches:** `issues/lmod-tool-group.md`, `issues/xdu-storage.md` (notes), `issues/sandbox-dirs-left-on-kill.md` and its `ROADMAP.md` entry, and whatever `p3.sh`
  proves wrong in the product.

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
