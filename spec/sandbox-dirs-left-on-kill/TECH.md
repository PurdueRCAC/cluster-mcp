---
slug: sandbox-dirs-left-on-kill
title: The suite and the mutation runner leave no sandbox directory behind
kind: fix
appetite: small
status: in_progress
branch: fix/sandbox-dirs-left-on-kill
base: develop
current_phase: P3
last_updated: '2026-11-12'
phases:
- id: P1
  name: A suite run sweeps what its killed sandboxes left, and nothing else
  status: done
  satisfies:
  - R1
  - R3
  - R4
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files units kinds guards && uv run pytest -q tests/test_sandbox_dirs.py tests/test_transports.py tests/test_hygiene.py tests/test_suite_parts.py
- id: P2
  name: A mutation case's scratch is its child run's TMPDIR
  status: done
  satisfies:
  - R2
  - R6
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files rebase runner runner-timeout sample && uv run python -I spec/sandbox-dirs-left-on-kill/remediation/runner-signals.py && uv run pytest -q tests/test_mutations.py
- id: P3
  name: The mutant sweep, the ledger and the whole verify
  status: pending
  satisfies:
  - R1
  - R3
  - R4
  - R6
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files ledger mutants suite
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — The suite and the mutation runner leave no sandbox directory behind

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/sandbox-dirs-left-on-kill/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md) (§ 2 the design, § 3 the deviations and the
  maintainer's figures, § 6 the gate's modes and the mutant sweep's decisions).
- **Backing research:** [`research/01-callers-and-contract.md`](research/01-callers-and-contract.md)
  (callers at `0bfacae`); the rest of `research/` and `verify/keeper.py` are the rejected keeper
  design's record (`8520d9c`), never built.
- **The frozen gate:** [`verify/cleanup.py`](verify/cleanup.py), one mode per requirement (its
  docstring lists them), with `verify/sample.expected` and `verify/develop-skips.txt` (develop's
  output at `0bfacae` on the planner's host). Never edit them to make a phase pass: a gate that is
  wrong is a stop and a question for the foreman. P3 adds `verify/mutants.json` (the plants); the
  planner's draft, `verify/mutants.draft.json`, was dry-run against the prototype
  ([`verify/prototype.diff`](verify/prototype.diff), a reference, never applied by a gate).

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation. The previous
  cycle (`suite-ci-time-budget`) carried the ledger; the ledger is the one that applies.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**. Here: `AGENTS.md`
  § Factory → Throwaway environment and § Testing change with the fixture in P1, and § Testing's
  mutation-runner bullet with `case_scratch` in P2.
- Export `UV_PYTHON=3.14` before every `verify:` on this host. Stage before running a `verify:`: the
  gate's planted modes run in a copy of the index, never the working tree. P3's gate (about 35
  minutes: the mutant sweep, then the whole `verify`) runs through `run_in_background`; never a
  disowned launch.
- Only the paths the `files` mode allows change: `tests/sandbox_dirs.py`, `tests/conftest.py`,
  `tests/mutants.py`, `tests/test_sandbox_dirs.py`, `AGENTS.md`, `issues/sandbox-dirs-left-on-kill.md`,
  `ROADMAP.md` and this cycle's `spec/`. `bin/sandbox.sh` is byte-identical to `0bfacae` (R5). No
  phase waits on a hosted CI run or a workflow dispatch.

---

## Phase P1 — A suite run sweeps what its killed sandboxes left, and nothing else
**Satisfies:** R1, R3, R4, R5, R6 · **Depends on:** —
**Goal:** a pytest run points every sandbox it starts at a directory of its own (or keeps the
`tmp_path` a test gives it), and at the session's end removes each sandbox directory left there that
no process uses; another run's, an earlier one's, a running sandbox's and anything not named as a
sandbox directory stay; every harness kind of the GOAL's Problem items 1–5 is covered.

- [x] `tests/sandbox_dirs.py` as PLAN § 2 specifies: `SANDBOX_NAME`, `RUN_PREFIX`, `leftovers`,
      `in_use` (pure; both path spellings), `processes` (`/proc` on Linux; `lsof` and `ps -E`
      through `[str(SANDBOX), …]` elsewhere, `lsof -b`; raises when the probe cannot run), `sweep`
      (no probe when nothing is found), `own_tmp` (sweeps before it puts `TMPDIR` back, then
      removes the run directory whole unless a sandbox directory in it is still in use). The planner's prototype,
      [`verify/prototype.diff`](verify/prototype.diff), is the reference shape.
- [x] `tests/conftest.py`: the session `autouse` fixture `sandbox_tmp(tmp_path_factory)` entering
      `own_tmp(tmp_path_factory.getbasetemp())`, and the module docstring naming it. No timing
      instrumentation.
- [x] `tests/test_sandbox_dirs.py`: the six rows PLAN § 2 lists (two `unit`, four `integration`;
      the `in_use` row parametrised with the seven ids PLAN names). No skips; every launch through
      `[str(SANDBOX), …]`.
- [x] `AGENTS.md`: the Throwaway environment sentence, the § Testing fixture bullet and module bullet,
      as PLAN § 2 words them.
- [x] Measure and put in the commit body: the new module's time in each era
      (`pytest --durations=0 tests/test_sandbox_dirs.py`, both eras), for PLAN § 3 row D4.
- **Verify:** the frontmatter `verify:`: `files` (R5), `units`, `kinds` (R1, one row per harness
  kind) and `guards` (R3/R4), about a minute in all; then the narrowed suite (the new module,
  `test_transports`' own check of its `tmp_path`, the rail and anchors in `test_hygiene`, the
  partition in `test_suite_parts`), about 10 s.
- **Touches:** `tests/sandbox_dirs.py`, `tests/conftest.py`, `tests/test_sandbox_dirs.py`, `AGENTS.md`.

## Phase P2 — A mutation case's scratch is its child run's TMPDIR
**Satisfies:** R2, R6 · **Depends on:** P1, and `mutant-child-outlives-timeout` landed on `develop`
(PLAN § 3 row D5)
**Goal:** whatever ends a case's child run, a normal exit, a SIGKILL before its session ends or the
runner's own stop past its limit, nothing any of its sandboxes made is left once the case is
reported, and every sample case and control prints what develop printed.

- [x] Before the phase: rebase the branch onto `develop` holding `mutant-child-outlives-timeout`
      (`git merge-base --is-ancestor` of its landing commit; `tests/mutants.py` defines `LIMIT`). If
      it has not landed, stop and report: the `runner-timeout` mode is red by design until it has.
- [x] `tests/mutants.py`, the four touch points of PLAN § 2 and nothing else: `import contextlib`;
      `Iterator` in the `typing` import; `import sandbox_dirs` after `import cluster_mcp.slurm`;
      `run_case`'s first line `with case_scratch(case.id) as scratch:`; `case_scratch` (mkdtemp, the
      `TMPDIR` set and put back, the scratch kept and named on stderr while a sandbox directory in it
      is in use, else removed) between `run_case` and `self_check`. Two additions, amended below:
      the process listing runs before `TMPDIR` is put back, and a listing that fails keeps the
      scratch, named, rather than raising out of `run_case`. The module docstring names `case_scratch`.
- [x] `AGENTS.md` § Testing's mutation-runner bullet: one clause, a case's scratch is its child's
      `TMPDIR` (PLAN § 2); and § Factory → Throwaway environment's sentence (written in P1 for the
      suite only) gains the same clause for the mutation runner. The bullet's last sentence, "the
      killed `bin/sandbox.sh` leaves its home in the runner's `TMPDIR`", false once this lands, is
      replaced (a live product fact, code-build Step 2.3).
- [x] Measure and put in the commit body: the sample's wall time before (develop's runner) and after,
      from the `sample` mode's run and `verify/sample.expected`'s recording run (PLAN § 3 row D4).
- **Verify:** the frontmatter `verify:`: `files`; `rebase` (the text merges with the sibling's in
  either order); `runner` (a child killed before its session ends, for a case on the package and one
  planting a repository copy: no sandbox directory, no scratch, `TMPDIR` put back; a child that ends
  normally leaving a sandbox running: that directory kept); `runner-timeout` (the same through the runner's stop at `LIMIT = 8`); `sample`
  (R6: 22 cases and the controls, about 110 s); `remediation/runner-signals.py` (the same through the
  stop a SIGTERM, SIGHUP or SIGINT to the runner makes, about 10 s); then `tests/test_mutations.py`
  (about 26 s). `files` runs under `remediation/fork-base.py`, as P1's did.
- **Touches:** `tests/mutants.py`, `AGENTS.md`, `spec/sandbox-dirs-left-on-kill/remediation/runner-signals.py`.

## Phase P3 — The mutant sweep, the ledger and the whole verify
**Satisfies:** R1, R3, R4, R6 (on the final tree, through the whole suite in both eras) ·
**Depends on:** P2
**Goal:** every decision of the cleanup is pinned by a gate row that kills its mutant, additive ones
included; the profile's whole `verify` leaves no sandbox directory under the `TMPDIR` it ran under and
skips exactly what develop skips; the ledger is clean.

- [ ] `verify/mutants.json`: at least one plant per decision in PLAN § 6's table (the gate's
      `DECISIONS`), each `{id, decision, file, old, new, mode, why}` against the built code, `why` a
      fragment of the `FAIL` line the named mode prints. Start from `verify/mutants.draft.json` and
      re-anchor each plant to the built text; add a plant for any decision the build added. Record
      the sweep's result (each plant, killed by which mode, or survived and why) in the commit body.
      Written 2026-11-12, before the heavy gate: the draft's 24 plants (one, `runner-not-restored`,
      re-anchored to `case_scratch` as built), plus two for the decision P2 added, `runner-unlisted`
      (`runner-unlisted-raises`, `runner-unlisted-removes`), killed by `units` through the row below.
      Checked alone: the re-anchored plant killed by `runner`, the two new ones by `units`; both new
      ones survive at `39399ab`, before the row. The full sweep's result is still to record.
- [x] `tests/test_sandbox_dirs.py`: a `unit` row, `test_a_case_scratch_whose_processes_cannot_be_listed_is_kept`
      (the foreman's ruling at the P2 gate, 2026-11-12): with the process listing made to fail,
      `case_scratch` keeps the scratch and its sandbox directory, puts `TMPDIR` back, and names the
      scratch and the error on stderr. `AGENTS.md`'s module bullet for the file names it. The row
      lives here, not in `tests/test_mutations.py`, because the `files` mode allows this file and the
      `units` mode runs it, so the plants are graded by a gate mode.
- [ ] The ledger (`code-plan` Step 6.8): walk P1–P3's bodies, PLAN.md and the branch's commit bodies
      for deferral phrases; each names an `issues/` seed with a `ROADMAP.md` entry (the `ledger` mode
      checks this file). Two seeds are filed, on the foreman's rulings (2026-11-12), both pre-existing,
      each with a `ROADMAP.md` entry in Part I's Gates (the Gates count and both Part I totals moved
      with them; the seed/ROADMAP pairing check is empty):
      - a second signal during a case's cleanup is deferred to `issues/mutant-case-cleanup-interrupted.md`
        (after `mutant-runner-stop-pins`);
      - the GOAL's known limitation is seeded as `issues/sandbox-dirs-outside-repo-runs.md`
        (a caller outside the repository's runs that SIGKILLs a sandbox; after the seed above).
- [x] If `mutant-child-outlives-timeout` landed before this cycle, fix the "last three" referent in
      `issues/sandbox-dirs-left-on-kill.md` (GOAL Clarifications). Done at P2's rebase (2026-11-12):
      the branch's own sentence on the runner, which stood before "The last three", was dropped for
      `develop`'s, which follows that sentence, so the referent is again the three harnesses before it.
- [x] The seed's other facts, in `issues/sandbox-dirs-left-on-kill.md`, both on `develop` and so each a
      dated correction beneath it (append-only), unless the seed is retired at landing (PLAN § 5).
      (The sentence on the mutation runner's timeout path took `develop`'s wording at P2's rebase.)
      1. "The last three point the drive's `TMPDIR` at the test's own directory" is false for
         `spec/capability-probe/verify/drives.py`, which sets no `TMPDIR` and starts no sandbox of
         its own (it SIGKILLs a bare `uv run` inside a gate's outer sandbox, GOAL § Problem); the
         sites that point a sandbox's `TMPDIR` at `tmp_path` are `tests/test_transports.py`,
         `tests/test_probe_startup.py` (`drive_env`) and one `tests/test_audit.py` site.
      2. "The runner sets no `TMPDIR` of its own" is false once P2 lands: each case's scratch is its
         child run's `TMPDIR` (`case_scratch`), removed once the case is reported on each end the
         runner's stop covers, named: the stop past `LIMIT`, and SIGTERM, SIGHUP and SIGINT (Ctrl-C)
         to the runner (the gate's `runner-timeout` and P2's `remediation/runner-signals.py`); a
         SIGKILL to the runner still leaves its scratch (GOAL non-goal).
- [ ] Put the `suite` mode's figures into PLAN § 3 row D4 beside the planner's, naming this run: each
      command's time and leftover count.
- [ ] Stage, then run the frontmatter `verify:` through `run_in_background`: `files`, `ledger`,
      `mutants` (about 24 plants, one planted mode each: about 7 minutes), then `suite` (the profile's
      eight suite commands and its last, both eras, under a fresh `TMPDIR`: about 26 minutes).
- **Verify:** the frontmatter `verify:`.
- **Touches:** `spec/sandbox-dirs-left-on-kill/verify/mutants.json`, `spec/sandbox-dirs-left-on-kill/PLAN.md`,
  `spec/sandbox-dirs-left-on-kill/TECH.md`, `spec/sandbox-dirs-left-on-kill/remediation/fork-base.py`,
  `issues/sandbox-dirs-left-on-kill.md`, `issues/mutant-case-cleanup-interrupted.md`, `ROADMAP.md`,
  `tests/test_sandbox_dirs.py`, `AGENTS.md`.

---

## Amendments

- **2026-11-09, rulings at the PLAN/TECH gate.** The maintainer approved the full-depth sweep
  (PLAN § 3 row D4: the walk at any depth, not the walk limited to `tmp_path` and one level below)
  with the measured figures (voice, 2026-11-09), inside his 15-minute CI envelope. The foreman
  accepted D1 and D3–D7, and recorded D2 and D3 as GOAL readings (GOAL Clarifications, foreman
  ruling at the PLAN/TECH gate, 2026-11-09, committed on their own before P1). Under D5, P2 waits
  until `mutant-child-outlives-timeout` has landed on `develop`.
- **2026-11-09, P1 build: the branch rebased, and the `files` mode run from the fork point.** Before
  P1 the branch was rebased onto `origin/develop` at `146cbc6` (from `0bfacae`), cleanly. The frozen
  gate pins `BASE = '0bfacae'` and its `files` mode lists `git diff --cached --name-only BASE`, so on
  the rebased branch it named develop's own changes since `0bfacae` (the `skip-check-fence-gaps`
  landing: four `issues/skip-check-*.md`, `spec/skip-check-fence-gaps/`, `tests/test_hygiene.py`) as
  paths outside the allowed set. P1's gate was seen red on that alone (attempt 1; R5 and every
  other mode green on the same run). P1's `verify:` now runs the gate unchanged under
  [`remediation/fork-base.py`](remediation/fork-base.py), which checks R5 against `0bfacae` as
  written (tree and index), checks `bin/sandbox.sh` is unchanged from `0bfacae` to the fork point,
  then runs the gate's modes with `BASE` set to `git merge-base HEAD origin/develop`. Its teeth: a
  staged stray file and a byte appended to `bin/sandbox.sh` each turn it red. P2's and P3's
  `verify:` also run `files`: retune each to the wrapper the same way when its build starts (P2's
  own rebase onto the sibling moves the fork point again, which the wrapper follows).
- **2026-11-09, P1 build: the docs split.** P1's Throwaway environment sentence names the suite's
  cleanup and the known limitation only (seed: `issues/sandbox-dirs-outside-repo-runs.md`, 2026-11-12);
  the mutation runner's clause joins it in P2, with
  `case_scratch` (§ Conventions, docs in the same commit). The seed's facts the foreman flagged are
  P3's (a new checklist item there): P1 has no ledger work.

- **2026-11-12, P2 build: rebased onto the landed sibling, and the gate retuned.** Before P2 the
  branch was rebased onto `origin/develop` at `2719b7a`, which holds `mutant-child-outlives-timeout`
  (`32a85c3`); the branch had never been pushed. One conflict, `ROADMAP.md`'s entry for this seed
  (`develop` renamed its horizon to "Part I, gates"; the branch had set its status to `adopted`):
  both kept. In the seed, `develop`'s sentence on the runner's stop was taken and the branch's own
  sentence on it dropped (GOAL Clarifications: the sibling's wording). The re-check against the
  landed runner: PLAN § 2's approach still fits. `run_child` builds its child's environment from
  `os.environ` at call time, so the child's `TMPDIR` is the case scratch, and `stop_run` kills the
  whole run, waits until none of it runs (`_wait_gone`) and reaps the wrapper before `run_child`
  returns or raises; `case_scratch`'s exit then runs on every end of a case, because each one leaves
  `run_case` through it: the child's own exit, the stop past `LIMIT` (`ChildTimeout`), and the stop on
  SIGTERM or SIGHUP (`RunnerSignal`) or SIGINT (`KeyboardInterrupt`), which `run_child` makes before
  it re-raises. The frozen gate pins the first two (`runner`, `runner-timeout`); P2's `verify:` adds
  [`remediation/runner-signals.py`](remediation/runner-signals.py), one row per signal (the runner
  ends by it, no process the child recorded runs on, no sandbox directory or scratch is left under
  the runner's `TMPDIR`); its control, `--runner-from origin/develop`, is red on every signal. The
  `files` mode runs under `remediation/fork-base.py`, as P1's did. The `rebase` mode now compares
  with `origin/develop`, which already holds the sibling, so it passes trivially; the rebase itself
  was the real merge.
- **2026-11-12, P2 build: two changes to `case_scratch` beyond PLAN § 2.** (1) The process listing
  runs before `TMPDIR` is put back, as `own_tmp`'s sweep does (the adversarial review's finding 8): a
  listing whose own sandbox is killed on its timeout leaves its directory in the scratch, not in the
  runner's `TMPDIR`. (2) A listing that fails (`processes()` raises, as it does when `ps` cannot run:
  the same state in which `stop_run` reports a stop that could not finish) keeps the scratch and
  names it on stderr with the error, instead of raising out of `run_case` and ending the sweep with
  no verdict for the case (R6). No suite row pins (2): `tests/test_mutations.py` is outside the
  `files` mode's allowed paths. P3's mutant sweep can plant it.

- **2026-11-12, P3's light work, on the foreman's rulings at the P2 gate.** (1) The failed-listing
  branch of `case_scratch` gets a plant and a killing row: the row is in `tests/test_sandbox_dirs.py`
  (allowed by the `files` mode, run by `units`), so no allowed path widens for it. (2) The second
  signal during a case's cleanup is filed as `issues/mutant-case-cleanup-interrupted.md` with its
  `ROADMAP.md` entry; that seed is outside the frozen gate's `ALLOWED`, so
  `remediation/fork-base.py` widens the `files` mode by exactly that path (`ALSO_ALLOWED`), and
  P3's `verify:` runs the frozen gate under the wrapper, as P1's and P2's do. (3) The seed's two
  corrections went in as dated lines. The heavy gate (`mutants`, then `suite`) waits for a slot.

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
