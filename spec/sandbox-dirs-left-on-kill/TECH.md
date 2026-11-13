---
slug: sandbox-dirs-left-on-kill
title: The suite and the mutation runner leave no sandbox directory behind
kind: fix
appetite: small
status: in_review
branch: fix/sandbox-dirs-left-on-kill
base: develop
current_phase: done
last_updated: '2026-11-13'
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
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files units kinds guards && uv run python -I spec/sandbox-dirs-left-on-kill/remediation/F1-closed-dirs.py && uv run python -I spec/sandbox-dirs-left-on-kill/remediation/F2-pins.py && uv run pytest -q tests/test_sandbox_dirs.py tests/test_transports.py tests/test_hygiene.py tests/test_suite_parts.py
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
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files rebase runner runner-timeout sample && uv run python -I spec/sandbox-dirs-left-on-kill/remediation/runner-signals.py && uv run python -I spec/sandbox-dirs-left-on-kill/remediation/F1-closed-dirs.py && uv run python -I spec/sandbox-dirs-left-on-kill/remediation/F2-pins.py && uv run pytest -q tests/test_mutations.py
- id: P3
  name: The mutant sweep, the ledger and the whole verify
  status: done
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
  verify: SDLK_MUTANTS=spec/sandbox-dirs-left-on-kill/remediation/review1-mutants.json uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files ledger mutants suite
review:
  last_reviewed_commit: 0014491ef5a1d7c48057f8d79be0c714b68cc1c6
  verdict: changes-requested
  blocked_reason: 'review cycle 2: F-A a kept case scratch keeps its free sandbox directories (R2, MEDIUM); F-B a seed understates its defect (LOW); non-convergence, to the maintainer'
  cycle: 2
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
- [x] Review cycle 1, F1 at the sweep, and F2a, F2b (reopened 2026-11-12): `tests/sandbox_dirs.py`
      gains `reopen` (before the scan, each closed directory in the run's directory that is not a
      sandbox directory or inside one is opened for the owner, so a sandbox in use beneath it is
      seen) and `remove` (a plain removal first; on an error, the tree and a closed holding directory
      opened, the holder's mode put back; no link followed; the error returned, never raised). The
      sweep keeps every directory it found when the processes cannot be listed, keeps one it cannot
      remove, and names both on stderr through `tell`; `own_tmp` names a run directory it cannot all
      remove. `sandbox_tmp` routes `tell` past pytest's output capture. Rows in
      `tests/test_sandbox_dirs.py` (all `unit`, on planted process tables): closed directories
      (`0o555`, `0`) removed, links and outside directories unaltered, the holder's mode back; what
      cannot be removed kept and named; a failed listing keeps and names; the pytest temporary
      directory swept (F2a); the run directory kept while a sandbox in it is in use (F2b); a sandbox
      in use under a closed directory seen and unaltered. `AGENTS.md` § Testing's fixture and module
      bullets.
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
- [x] Review cycle 1, F1 at the runner, and F2c (reopened 2026-11-12): `case_scratch` runs `reopen`
      before its scan, removes through `remove`, and keeps and names a scratch it cannot all remove;
      it never raises, so the stopped case is reported, later cases run, and a signal still ends the
      runner by that signal. Rows in `tests/test_sandbox_dirs.py`: a scratch holding closed
      directories removed, one it cannot all remove kept and named, one holding a sandbox in use kept
      and named (F2c), and one with a sandbox in use under a closed directory kept. `AGENTS.md`
      § Testing's mutation-runner bullet. Two checkers, both sites:
      [`remediation/F1-closed-dirs.py`](remediation/F1-closed-dirs.py) (the limit and signal paths
      with a test holding closed directories: the runner past a patched `LIMIT` and on SIGTERM, SIGHUP
      and SIGINT; a pytest session through a `subprocess.run` timeout and on SIGINT; and, on macOS, an
      immutable file named past the capture), and [`remediation/F2-pins.py`](remediation/F2-pins.py)
      (22 hand plants of F2a-c and F1's new decisions through `run_case`, each killed by its rows with
      the contract's message, and an unmutated control).
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

- [x] `verify/mutants.json`: at least one plant per decision in PLAN § 6's table (the gate's
      `DECISIONS`), each `{id, decision, file, old, new, mode, why}` against the built code, `why` a
      fragment of the `FAIL` line the named mode prints. Start from `verify/mutants.draft.json` and
      re-anchor each plant to the built text; add a plant for any decision the build added. Record
      the sweep's result (each plant, killed by which mode, or survived and why) in the commit body.
      Written 2026-11-12, before the heavy gate: the draft's 24 plants (one, `runner-not-restored`,
      re-anchored to `case_scratch` as built), plus two for the decision P2 added, `runner-unlisted`
      (`runner-unlisted-raises`, `runner-unlisted-removes`), killed by `units` through the row below.
      Checked alone: the re-anchored plant killed by `runner`, the two new ones by `units`; both new
      ones survive at `39399ab`, before the row. The full sweep (P3's gate, 2026-11-12): all 26 killed,
      each by its named mode; the result is in the P3 commit body.
- [x] `tests/test_sandbox_dirs.py`: a `unit` row, `test_a_case_scratch_whose_processes_cannot_be_listed_is_kept`
      (the foreman's ruling at the P2 gate, 2026-11-12): with the process listing made to fail,
      `case_scratch` keeps the scratch and its sandbox directory, puts `TMPDIR` back, and names the
      scratch and the error on stderr. `AGENTS.md`'s module bullet for the file names it. The row
      lives here, not in `tests/test_mutations.py`, because the `files` mode allows this file and the
      `units` mode runs it, so the plants are graded by a gate mode.
- [x] The ledger (`code-plan` Step 6.8): walk P1–P3's bodies, PLAN.md and the branch's commit bodies
      for deferral phrases; each names an `issues/` seed with a `ROADMAP.md` entry (the `ledger` mode
      checks this file). Two seeds are filed, on the foreman's rulings (2026-11-12), both pre-existing,
      each with a `ROADMAP.md` entry in Part I's Gates (the Gates count and both Part I totals moved
      with them; the seed/ROADMAP pairing check is empty):
      - a second signal during a case's cleanup is deferred to `issues/mutant-case-cleanup-interrupted.md`
        (after `mutant-runner-stop-pins`);
      - the GOAL's known limitation is seeded as `issues/sandbox-dirs-outside-repo-runs.md`
        (after the seed above), with both its cases: a caller outside the repository's runs that
        SIGKILLs a sandbox, and the run itself SIGKILLed before its end.
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
- [x] Put the `suite` mode's figures into PLAN § 3 row D4 beside the planner's, naming this run: each
      command's time and leftover count.
- [x] Stage, then run the frontmatter `verify:` through `run_in_background`: `files`, `ledger`,
      `mutants` (about 24 plants, one planted mode each: about 7 minutes), then `suite` (the profile's
      eight suite commands and its last, both eras, under a fresh `TMPDIR`: about 26 minutes).
- [x] Review cycle 1 (reopened 2026-11-12): F1's fix moved the text five frozen plants anchor on
      (`skip-run-dir`, `skip-basetemp`, `sweep-since`, `rmdir-dropped`, `skeleton-only`).
      [`remediation/review1-mutants.json`](remediation/review1-mutants.json) is `verify/mutants.json`
      with those five anchors, and their planted text, moved to the built code; their decisions,
      modes and messages are unchanged. One plant changes mode: `links-taken` (a link with a sandbox's
      name taken as a leftover) was killed by `guards` only because `shutil.rmtree` raised on the link
      and the session failed, the crash F1 removes; `remove` now refuses the link, keeps it and names
      it, so the decoys survive and `guards` passes. It is killed by `units` instead, whose
      `test_leftovers_are_directories_with_a_sandbox_name` asserts the link is not a leftover (seen
      alone: survived `guards`, killed by `units`). P3's `verify:` runs `mutants` on the list through
      `SDLK_MUTANTS`, the frozen gate's own override.
- [x] Review cycle 1: the `suite` mode (the profile's whole `verify`) on the final tree, `33f72ab`
      (2026-11-12, 26:42 wall): `files` ok; all eight suite commands passed (legacy 212 / 144 / 215 /
      220 s, modern 212 / 144 / 221 / 212 s), none left a sandbox directory, none made one in
      `/tmp`; `verify`'s last command passed; the 28 skips are develop's. Two empty run directories
      remain, case 3 of `issues/sandbox-dirs-outside-repo-runs.md`, which now also records the
      pytest temporary directory's closed directories the sweep does not scan.
- [x] Review cycle 2, on the maintainer's ruling (b), 2026-11-12: F-B, a docs change under this
      phase, no phase reopened. `issues/mutant-case-cleanup-interrupted.md` states its whole domain
      (any signal during a case's cleanup, first or second), with its `ROADMAP.md` entry and Part I's
      gates line; `remediation/fork-base.py` takes cycle 2's seed in `ALSO_ALLOWED`. F-A is dropped
      (REVIEW.md, Maintainer ruling).
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

- **2026-11-12, review cycle 1 remediation (`changes-requested`: F1 MEDIUM, F2a-c LOW).** P1, P2
  and P3 reopened. F1 (a closed directory in a case scratch or a sweep raised `PermissionError` out of
  a bare `shutil.rmtree`) is fixed at both sites by `sandbox_dirs.reopen` and `sandbox_dirs.remove`,
  and the cleanup never raises: what it cannot remove, or cannot tell is free, it keeps and names on
  stderr. The sweep's failed listing used to raise (and fail the session); it now keeps what it found
  and names it, as `case_scratch` already did (the review's routing: "never raises out of
  `case_scratch` or the sweep", "keeps what it found rather than remove it"). P1 and P2 are
  committed together, as `bundle`: `case_scratch` calls the helpers P1's file adds, both phases' rows
  share `tests/test_sandbox_dirs.py`, and `AGENTS.md` describes both in the bullets the same-commit
  rule pairs with them. Gates retuned: P1's and P2's `verify:` each add
  `remediation/F1-closed-dirs.py` and `remediation/F2-pins.py` (both checkers cover both sites; each
  ran once on the bundled tree, standing for both phases); P3's runs `mutants` on
  `remediation/review1-mutants.json`. `remediation/fork-base.py` widens `files` by the review's seed,
  `issues/sandbox-sweep-listing-failure-unpinned.md` (seen red without it), whose line reference
  moved with the fix and is corrected in place (this cycle's own, not on `develop`). The frozen gate
  has no closed-directory row; `F1-closed-dirs.py` is that row: every one of its rows goes red (23 of
  its 30 checks) with the reviewed commit's `tests/sandbox_dirs.py`, `tests/mutants.py` and `tests/conftest.py`
  (`--from 97750cc`). `bin/sandbox.sh` is unchanged (R5). One commit for P1-P3: P3's plant list
  re-anchors text this same change moves, so its `mutants` mode cannot run on any split. P1 and P2
  are done; P3 stays in progress until the foreman's full verify runs its `suite` mode.

- **2026-11-13, review cycle 2: the maintainer's ruling (b), 2026-11-12.** F-A (a kept case scratch
  keeps its free sandbox directories) is dropped: the GOAL's D3 allows the keep. F-B is fixed in the
  seed it names, `issues/mutant-case-cleanup-interrupted.md`: its Problem, Outcome and criteria now
  cover any SIGTERM, SIGHUP or SIGINT that lands during a case's cleanup, not only a second one, as
  the review's probe showed, and its `ROADMAP.md` entry and Part I's gates line follow. The seed is
  this cycle's own, not on `develop`, so it is corrected in place. The fix touches no code or test,
  so no phase reopens: it is a docs change under P3. `remediation/fork-base.py` widens `files` by
  cycle 2's seed, `issues/sandbox-reopen-link-in-closed-dir-unpinned.md` (seen red without it). The
  light gates ran on the staged tree (`fork-base.py files ledger`); the full `verify` runs on the
  landing squash. The cycle goes to publish with no further review: `status` is `in_review`, and
  `review` is left as the cycle 2 record (`changes-requested`, cycle 2), since build never passes
  `--verdict`; REVIEW.md's Maintainer ruling section is the override publish reads.
  - 2026-11-13: on the foreman's routing, a docs correction under F-B's class. `AGENTS.md` § Testing
    and `case_scratch`'s docstring now limit "never raises" to the cleanup's own errors and name the
    seed for a signal that lands during it. The `tests/mutants.py` change is the docstring alone (its
    AST without docstrings is identical to `0014491`'s). Both paths are already in `files`' allowed set.

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
