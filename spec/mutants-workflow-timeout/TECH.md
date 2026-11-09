---
slug: mutants-workflow-timeout
title: A dispatched mutation run finishes and reports every case
kind: ci
appetite: small
status: in_progress
branch: ci/mutants-workflow-timeout
base: develop
current_phase: P1
last_updated: '2026-11-09'
phases:
- id: P1
  name: The runner splits the cases into shards and checks a shard report
  status: pending
  satisfies:
  - R1
  - R2
  - R3
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py rows 1 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 1 && uv run -q python -I spec/mutants-workflow-timeout/verify/shard-mutants.py runner && uv run pytest -q tests/test_mutations.py tests/test_mutant_shards.py tests/test_hygiene.py
- id: P2
  name: The workflow runs every shard to a ledger; the documents follow
  status: pending
  satisfies:
  - R1
  - R2
  - R3
  - R5
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py rows 2 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 2 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py docs && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py controls && uv run -q python -I spec/mutants-workflow-timeout/verify/shard-mutants.py runner && uv run -q python -I spec/mutants-workflow-timeout/verify/shard-mutants.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py drive && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
- id: P3
  name: The first hosted run (Run A dispatches, Run B reads)
  status: pending
  satisfies:
  - R1
  - R2
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 3 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt
- id: P4
  name: Two more hosted runs, the budget row and the ledger (Run A dispatches, Run B records)
  status: pending
  satisfies:
  - R4
  - R3
  - R1
  - R2
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 4 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py controls && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt --final && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py docs --final
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — A dispatched mutation run finishes and reports every case

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/mutants-workflow-timeout/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **The frozen gate:** [`verify/mutants-gate.py`](verify/mutants-gate.py), one mode per requirement
  (its docstring lists them). Never edit it to make a phase pass: a gate that is wrong is a stop and
  a question for the foreman. `verify/shard-mutants.py` is written by P1 from PLAN § 6.2's decision
  list (P2 adds the workflow's entries, additions only); from then on it is frozen too.
- **Timing sample:** [`research/timing-sample.tsv`](research/timing-sample.tsv) (PLAN § 4).

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8).
  The previous cycle's last phase (`suite-ci-time-budget` P3) carried no other project-level item.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.
- **Dispatches.** Up to three `workflow_dispatch` runs of `mutants.yml` on
  `ci/mutants-workflow-timeout` are approved (GOAL Q4): one in P3, two in P4, and no other. Never
  `gh run rerun`. P3 and P4 wait on the hosted runner, so each is two runs (the foreman's "external
  waits split the run"): Run A ends with the dispatch and hands back the run ids; the foreman holds
  the wait; Run B reads the runs and closes the phase.
- **The shard size is a figure for the maintainer** (PLAN § 3 row D1: 15, reading B; 50 under
  reading A). If the sign-off picks reading A, the plan is revised before P1 builds: every place
  row D1 lists changes together.
- **The sibling cycle** `mutant-child-outlives-timeout` edits `tests/mutants.py`'s import block, its
  run-child block, `run_child`, `run_case` and the `__main__` block. This cycle touches only the
  docstring's Usage lines, the `typing` import line, the block between `self_check` and `main`, and
  the top of `main` (PLAN § 2.1); its rows live in their own module, so `tests/test_mutations.py`,
  which the sibling also edits, stays untouched. The `untouched` mode holds the rest byte-identical.

---

## Phase P1 — The runner splits the cases into shards and checks a shard report
**Satisfies:** R1, R2, R3 (the selection and the ledger; the hosted proof is P3–P4) · **Depends on:** —
**Goal:** `tests/mutants.py` can name the run's shards, run one, and check one's report, every case of
the platform exactly once, each decision pinned by a row that kills a named mutant.

- [ ] In `tests/mutants.py`, between `self_check` and `main`: `SHARD_SIZE = 15`, `CONTROLS`,
      `shard_count`, `shard_ids`, `parse_shard`, `report_violations`, `sharded`, as PLAN § 2.1
      specifies (the names are the `untouched` mode's `NEW_TOP`; no other new top-level name).
      `typing` gains `Iterable`; nothing else in the import block changes.
- [ ] `main`: the `--matrix`, `--shard NUMBER/COUNT` and `--ledger REPORT` options after
      `--self-check`, and `status = sharded(parser, args, list(known))` / `if status is not None:` /
      `return status` right after `known`: exactly the six lines the `untouched` mode's `MAIN_ADDED`
      names, and nothing else in `main` changes. The docstring's Usage block gains the three forms.
- [ ] A new module `tests/test_mutant_shards.py` (SPDX header, a docstring, `unit` rows only, no
      launch: `run_case` is faked) holding the eleven runner rows the `rows 1` mode names (PLAN
      § 6.2's table, every row but the workflow's). `tests/test_mutations.py` is not touched.
      `AGENTS.md` § Testing's module list gains one item for it, after `tests/test_mutations.py`.
- [ ] Write `spec/mutants-workflow-timeout/verify/shard-mutants.py`, mode `runner`: for each runner
      mutant of PLAN § 6.2 (24 entries), plant it into a copy of the staged `tests/mutants.py` in a
      fresh `mktemp -d` export of the index (never the working copy), run the killing row by id, and
      require it red; then require the unplanted rows green. One pytest at a time; header states the
      footprint. Each entry names its anchor and refuses one that is not found exactly once.
- **Verify:** the frontmatter `verify:` (rows by id in both eras, `untouched 1`, the sweep, and
  the three modules `tests/test_mutations.py`, `tests/test_mutant_shards.py` and `tests/test_hygiene.py`, the
  last holding the spec-id and sandbox rails).
- **Touches:** `tests/mutants.py`, `tests/test_mutant_shards.py`, `AGENTS.md` (§ Testing's module list),
  `spec/mutants-workflow-timeout/verify/shard-mutants.py`.

## Phase P2 — The workflow runs every shard to a ledger; the documents follow
**Satisfies:** R1, R2, R3, R5 (and R4's row, its baseline pending) · **Depends on:** P1
**Goal:** `.github/workflows/mutants.yml` is the plan job and the sharded matrix job of PLAN § 2.2;
`AGENTS.md` states the dispatch state, the sharded run and the bound; the full suite is green.

- [ ] Rewrite `.github/workflows/mutants.yml` per PLAN § 2.2: header comment (dispatch state, the
      shape, least privilege), `workflow_dispatch` only, `contents: read`, `plan` and `mutants`, both
      `timeout-minutes: 20` on `ubuntu-24.04`, `fail-fast: false`, the matrix from `plan`'s output,
      `SHARD` from `matrix.shard` and `strategy.job-total`, the shared steps verbatim as ci.yml's
      `suite-legacy-1` carries them (checkout, setup-uv, the shells, `uv sync --locked`), the `run`
      step (`timeout-minutes: 15`) and the always-run `ledger` step. No new `uses:`.
- [ ] Append the workflow row (`test_the_mutants_workflow_runs_each_shard_to_a_ledger`, matching each
      step line for line, as PLAN § 7 finding 4 has it) to `tests/test_mutant_shards.py`.
- [ ] Extend `verify/shard-mutants.py` with mode `workflow`: PLAN § 6.2's nine workflow mutants,
      each planted into the staged workflow and killed by the workflow row (additions only).
- [ ] `AGENTS.md` § Factory profile: the `mutants budget` row after `ci budget`, as PLAN § 2.3 words
      it, ending `Baseline: pending`. § Testing, the mutation-runner bullet: the stale figure replaced
      by a pointer to the row ("pending"), the usage block's three new forms, the closing sentences on
      the sharded run and the dispatch state (R5).
- [ ] Run the gates, then the profile's full `verify` (the frontmatter's tail; ~26 min: run it in the
      background) on the staged tree.
- **Verify:** the frontmatter `verify:`.
- **Touches:** `.github/workflows/mutants.yml`, `tests/test_mutant_shards.py`, `AGENTS.md`,
  `spec/mutants-workflow-timeout/verify/shard-mutants.py`.

## Phase P3 — The first hosted run
**Satisfies:** R1, R2 (on the hosted runner) · **Depends on:** P2
**Goal:** one dispatched run of the branch's workflow, read whole: every case reported once, every job
within 600 − 310 s; any case not killed seeded. This phase waits on the hosted runner, so it is two
runs.

**Run A (the brief authorises the push and one dispatch):**
- [ ] `mutants-gate.py prepush`, `untouched 3` and `workflow` on the head; mark P3 `in_progress` with
      the note "Run A: dispatched" in the TECH body below, commit, and note the head: it is the
      measured commit `T1`.
- [ ] Push the branch; dispatch once: `gh workflow run mutants.yml --ref ci/mutants-workflow-timeout`;
      find the run (`gh run list --workflow mutants.yml --branch ci/mutants-workflow-timeout -e
      workflow_dispatch --json databaseId,headSha -L 1`, whose `headSha` must be `T1`). Hand back
      `T1` and the run id. Never dispatch again in this run.

**Run B:**
- [ ] Write `spec/mutants-workflow-timeout/runs.txt`: `sha <T1 full>`, `run <id>`.
- [ ] Run `mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt`. It prints the
      cases not killed. If a job ran over 600 − 310 s, a job was cancelled, or a case was reported
      twice or never: **stop** and report the run, the job and the figure to the foreman; do not
      resize, fix or re-dispatch inside this phase (two dispatches remain, both for P4).
- [ ] Cases not killed (GOAL Q3): more than three, **stop** and hand the list to the foreman before
      seeding. Three or fewer: each gets `issues/<slug>.md`, pre-shaped from the KB's `ISSUE.md`
      template (`status: unshaped`, naming the run id, the case id, its `FAILED` reason and that it
      was found by `mutants-workflow-timeout`), and a `ROADMAP.md` entry. No case, target or `why`
      changes here (Non-goal 3).
- [ ] Stage, run the frontmatter `verify:`, mark P3 done, commit.
- **Verify:** the frontmatter `verify:` (Run B).
- **Touches:** `spec/mutants-workflow-timeout/runs.txt`; `issues/*.md` and `ROADMAP.md` only for
  seeds.

## Phase P4 — Two more hosted runs, the budget row and the ledger
**Satisfies:** R4, R3, R1, R2 · **Depends on:** P3
**Goal:** three counted runs (worst of three), the `mutants budget` baseline and § Testing's measured
cost written from them, the deferral ledger walked. Two runs: Run A dispatches, Run B records.

**Run A (the brief authorises the push and two dispatches):**
- [ ] `mutants-gate.py prepush` and `untouched 4` on the head (P3's closing commit, which differs from
      `T1` only in `spec/`, `issues/` and `ROADMAP.md`: PLAN § 3 row D3). Mark P4 `in_progress` with
      the note "Run A: dispatched", commit, push.
- [ ] Dispatch twice (`gh workflow run mutants.yml --ref ci/mutants-workflow-timeout`, one after the
      other); find both run ids as in P3. Hand them back. Never dispatch again.

**Run B:**
- [ ] Append `run <id>` for both to `runs.txt`. Run `mutants-gate.py runs --runs-file
      spec/mutants-workflow-timeout/runs.txt --final`; a red result is a **stop**, as in P3. Seed any
      new case not killed as P3 does (the same three-case limit counts across the three runs).
- [ ] Put the printed baseline sentence in the `mutants budget` row in place of `Baseline: pending`,
      add the measured mean per case on the worst job the gate prints, and in § Testing replace
      "(… § Factory: pending)" with the cost the row holds ("N cases in S shards", the slowest job's
      time) and the pointer. Nothing else in `AGENTS.md` changes.
- [ ] **The deferral ledger** (`code-plan` Step 6.8): walk P1–P4's bodies here, PLAN § 5 and every
      branch commit body for "do not fix here", "known limitation", "follow-up", "deferred",
      "deferral", "not fixed" or "seeded"; each such item names an `issues/` seed with a `ROADMAP.md`
      entry (the `prepush` mode checks it). This plan files no new seed of its own.
- [ ] Stage, run the frontmatter `verify:`, mark P4 done, commit. The head differs from the measured
      runs' commits only in `AGENTS.md`'s row and § Testing sentence, `runs.txt`, TECH state and seeds.
- **Verify:** the frontmatter `verify:` (Run B). Run A runs only `prepush` and `untouched 4`.
- **Touches:** `AGENTS.md` (the row's baseline, § Testing's cost sentence), `runs.txt`; seeds.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[ci]` commit; stop and report.
