---
slug: mutants-workflow-timeout
title: A dispatched mutation run finishes and reports every case
kind: ci
appetite: small
status: in_progress
branch: ci/mutants-workflow-timeout
base: develop
current_phase: P3
last_updated: '2026-11-12'
phases:
- id: P1
  name: The runner splits the cases into shards and checks a shard report
  status: done
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
  status: done
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
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py rows 2 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 2 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py docs && uv run -q python -I spec/mutants-workflow-timeout/remediation/F1-controls-anchor.py && uv run -q python -I spec/mutants-workflow-timeout/verify/shard-mutants.py runner && uv run -q python -I spec/mutants-workflow-timeout/verify/shard-mutants.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py drive && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv lock --check && uv run pytest -q tests/test_ssh_exec.py -k silent && uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k silent && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_ssh_exec.py -k 'not silent' && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q --ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py && bin/sandbox.sh uv run cluster-mcp --help
- id: P3
  name: The first hosted run (Run A dispatches, Run B reads)
  status: pending
  satisfies: &id001
  - R1
  - R2
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 3 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt
- id: P4
  name: The second hosted run (Run A dispatches, Run B reads)
  status: pending
  satisfies: *id001
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 4 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt
- id: P5
  name: The third hosted run, the budget row and the ledger (Run A dispatches, Run B records)
  status: pending
  satisfies:
  - R4
  - R3
  - R1
  - R2
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  verify: export UV_PYTHON=3.14 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py prepush && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py untouched 5 && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py workflow && uv run -q python -I spec/mutants-workflow-timeout/remediation/F1-controls-anchor.py && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt --final && uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py docs --final
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
  `ci/mutants-workflow-timeout` are approved (GOAL Q4): one each in P3, P4 and P5, never two at
  once, and no other. Never
  `gh run rerun`. P3, P4 and P5 wait on the hosted runner, so each is two runs (the foreman's "external
  waits split the run"): Run A ends with the dispatch and hands back the run ids; the foreman holds
  the wait; Run B reads the runs and closes the phase.
- **The envelope** (GOAL Q6, the maintainer's answer):
  - each job's `timeout-minutes` is 15, and the cases' step is capped at 12;
  - the whole run is within 15 minutes from dispatch, queueing included;
  - about 15 cases a shard, reading (B).

  P3's run 1 decides whether the size stays (PLAN § 2.5). A refit changes every place row D1 lists,
  together.
- **The sibling cycle** `mutant-child-outlives-timeout` edits `tests/mutants.py`'s import block, its
  run-child block, `run_child`, `run_case` and the `__main__` block. This cycle touches only the
  docstring's Usage lines, the `typing` import line, the block between `self_check` and `main`, and
  the top of `main` (PLAN § 2.1); its rows live in their own module, so `tests/test_mutations.py`,
  which the sibling also edits, stays untouched. The `untouched` mode holds the rest byte-identical.

---

## Phase P1 — The runner splits the cases into shards and checks a shard report
**Satisfies:** R1, R2, R3 (the selection and the ledger; the hosted proof is P3–P5) · **Depends on:** —
**Goal:** `tests/mutants.py` can name the run's shards, run one, and check one's report, every case of
the platform exactly once, each decision pinned by a row that kills a named mutant.

- [x] In `tests/mutants.py`, between `self_check` and `main`: `SHARD_SIZE = 15`, `CONTROLS`,
      `shard_count`, `shard_ids`, `parse_shard`, `report_violations`, `sharded`, as PLAN § 2.1
      specifies (the names are the `untouched` mode's `NEW_TOP`; no other new top-level name).
      `typing` gains `Iterable`; nothing else in the import block changes.
- [x] `main`: the `--matrix`, `--shard NUMBER/COUNT` and `--ledger REPORT` options after
      `--self-check`, and `status = sharded(parser, args, list(known))` / `if status is not None:` /
      `return status` right after `known`: exactly the six lines the `untouched` mode's `MAIN_ADDED`
      names, and nothing else in `main` changes. The docstring's Usage block gains the three forms.
- [x] A new module `tests/test_mutant_shards.py` (SPDX header, a docstring, `unit` rows only, no
      launch: `run_case` is faked) holding the eleven runner rows the `rows 1` mode names (PLAN
      § 6.2's table, every row but the workflow's). `tests/test_mutations.py` is not touched.
      `AGENTS.md` § Testing's module list gains one item for it, after `tests/test_mutations.py`.
- [x] Write `spec/mutants-workflow-timeout/verify/shard-mutants.py`, mode `runner`: for each runner
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

- [x] Rewrite `.github/workflows/mutants.yml` per PLAN § 2.2: header comment (dispatch state, the
      shape, least privilege), `workflow_dispatch` only, `contents: read`, `plan` and `mutants`, both
      `timeout-minutes: 15` on `ubuntu-24.04`, `fail-fast: false`, the matrix from `plan`'s output,
      `SHARD` from `matrix.shard` and `strategy.job-total`, the shared steps verbatim as ci.yml's
      `suite-legacy-1` carries them (checkout, setup-uv, the shells, `uv sync --locked`), the `run`
      step (`timeout-minutes: 12`) and the always-run `ledger` step. No new `uses:`.
- [x] Append the workflow row (`test_the_mutants_workflow_runs_each_shard_to_a_ledger`, matching each
      step line for line, as PLAN § 7 finding 4 has it) to `tests/test_mutant_shards.py`.
- [x] Extend `verify/shard-mutants.py` with mode `workflow`: PLAN § 6.2's nine workflow mutants,
      each planted into the staged workflow and killed by the workflow row (additions only).
- [x] `AGENTS.md` § Factory profile: the `mutants budget` row after `ci budget`, as PLAN § 2.3 words
      it, ending `Baseline: pending`. § Testing, the mutation-runner bullet: the stale figure replaced
      by a pointer to the row ("pending"), the usage block's three new forms, the closing sentences on
      the sharded run and the dispatch state (R5).
- [x] Run the gates, then the profile's full `verify` (the frontmatter's tail; ~26 min: run it in the
      background) on the staged tree.
- **Verify:** the frontmatter `verify:`.
- **Touches:** `.github/workflows/mutants.yml`, `tests/test_mutant_shards.py`, `AGENTS.md`,
  `spec/mutants-workflow-timeout/verify/shard-mutants.py`.

## Phase P3 — The first hosted run
**Satisfies:** R1, R2 (on the hosted runner) · **Depends on:** P2
**Goal:** one dispatched run of the branch's workflow, read whole: every case reported once, every job
within 600 − 310 s, the run within 900 s of its dispatch; any case not killed seeded. The run also
decides whether the shard size stays (PLAN § 2.5). This phase waits on the hosted runner, so it is
two runs.

**Run A (the brief authorises the push and one dispatch):**
- [ ] `mutants-gate.py prepush`, `untouched 3` and `workflow` on the head; mark P3 `in_progress` with
      the note "Run A: dispatched" in the TECH body below, commit, and note the head: it is the
      measured commit `T1`.
- [ ] Push the branch. Before dispatching, check that no other run of the organisation is queued or
      in progress (`gh run list --status in_progress` and `--status queued` on this repository), since
      the Free plan's 20 jobs are shared (PLAN § 5); wait for it if one is. Then dispatch once:
      `gh workflow run mutants.yml --ref ci/mutants-workflow-timeout`;
      find the run (`gh run list --workflow mutants.yml --branch ci/mutants-workflow-timeout -e
      workflow_dispatch --json databaseId,headSha -L 1`, whose `headSha` must be `T1`). Hand back
      `T1` and the run id. Never dispatch again in this run.

**Run B:**
- [ ] Write `spec/mutants-workflow-timeout/runs.txt`: `sha <T1 full>`, `run <id>`.
- [ ] Run `mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt`. It prints:
      - the run's wall from dispatch and the most jobs it ran at once;
      - the cases not killed;
      - the refit table and its proposed size (PLAN § 2.5).

      **Stop**, and report the run, the job and the figure to the foreman with the refit table, if:
      - the run took more than 900 s from dispatch (the envelope);
      - a job ran over 600 − 310 s;
      - a job was cancelled;
      - a case was reported twice or never.

      Do not resize, fix or re-dispatch inside this phase: the maintainer asked for the measured run
      back (GOAL Q6), and the remaining two dispatches are his to place.
- [ ] Cases not killed (GOAL Q3): more than three, **stop** and hand the list to the foreman before
      seeding. Three or fewer: each gets `issues/<slug>.md`, pre-shaped from the KB's `ISSUE.md`
      template (`status: unshaped`, naming the run id, the case id, its `FAILED` reason and that it
      was found by `mutants-workflow-timeout`), and a `ROADMAP.md` entry. No case, target or `why`
      changes here (Non-goal 3).
- [ ] Stage, run the frontmatter `verify:`, mark P3 done, commit.
- **Verify:** the frontmatter `verify:` (Run B).
- **Touches:** `spec/mutants-workflow-timeout/runs.txt`; `issues/*.md` and `ROADMAP.md` only for
  seeds.

## Phase P4 — The second hosted run
**Satisfies:** R1, R2 (on the hosted runner) · **Depends on:** P3
**Goal:** the second counted run, read whole as P3 reads the first. The runs go one at a time: two
runs dispatched together would share the organisation's 20 job slots, and each would miss the
15-minute envelope (PLAN § 2.5). Two runs: Run A dispatches, Run B reads.

**Run A (the brief authorises the push and one dispatch):**
- [ ] `mutants-gate.py prepush` and `untouched 4` on the head. The head is P3's closing commit, which
      differs from `T1` only in `spec/`, `issues/` and `ROADMAP.md` (PLAN § 3 row D3). Mark P4
      `in_progress` with the note "Run A: dispatched", commit, push.
- [ ] With no other run of the organisation queued or in progress (as in P3), dispatch once and find
      the run id as P3 does. Hand it back. Never dispatch again in this run.

**Run B:**
- [ ] Append `run <id>` to `runs.txt`, and run `mutants-gate.py runs --runs-file
      spec/mutants-workflow-timeout/runs.txt`. Its stops are P3's. Seed any new case not killed as P3
      does: the same three-case limit counts across the runs.
- [ ] Stage, run the frontmatter `verify:`, mark P4 done, commit.
- **Verify:** the frontmatter `verify:` (Run B).
- **Touches:** `runs.txt`; seeds.

## Phase P5 — The third hosted run, the budget row and the ledger
**Satisfies:** R4, R3, R1, R2 · **Depends on:** P4
**Goal:** the third counted run, then:
- the `mutants budget` baseline and § Testing's measured cost, written from the three runs (the worst
  of three);
- the deferral ledger walked.

Two runs: Run A dispatches, Run B records.

**Run A (the brief authorises the push and one dispatch):**
- [ ] `mutants-gate.py prepush` and `untouched 5` on the head, P4's closing commit, which still
      differs from `T1` only in the records. Mark P5 `in_progress` with the note "Run A: dispatched",
      commit, push.
- [ ] With no other run of the organisation queued or in progress, dispatch once and find the run id
      as P3 does. Hand it back. This is the last dispatch Q4 allows.

**Run B:**
- [ ] Append `run <id>` to `runs.txt`. Run `mutants-gate.py runs --runs-file
      spec/mutants-workflow-timeout/runs.txt --final`; a red result is a **stop**, as in P3. Seed any
      new case not killed as P3 does.
- [ ] Put the printed baseline sentence in the `mutants budget` row, in place of `Baseline: pending`,
      and add the measured mean per case on the worst job that the gate prints.
- [ ] In § Testing, replace "(… § Factory: pending)" with the cost the row holds ("N cases in S
      shards, the run M:SS from dispatch, slowest job M:SS") and the pointer.
- [ ] Nothing else in `AGENTS.md` changes.
- [ ] **The deferral ledger** (`code-plan` Step 6.8): walk P1–P5's bodies here, PLAN § 5 and every
      branch commit body for "do not fix here", "known limitation", "follow-up", "deferred" or
      "not fixed". Each such item must name an `issues/` seed with a `ROADMAP.md` entry; the `prepush`
      mode checks it. This plan files no new seed of its own.
- [ ] Stage, run the frontmatter `verify:`, mark P5 done, commit. The head differs from the measured
      runs' commits only in:
      - `AGENTS.md`'s row and § Testing sentence;
      - `runs.txt` and the TECH state;
      - seeds.
- **Verify:** the frontmatter `verify:` (Run B). Run A runs only `prepush` and `untouched 5`.
- **Touches:** `AGENTS.md` (the row's baseline, § Testing's cost sentence), `runs.txt`; seeds.

## Amendments

- **2026-11-10, rulings at the PLAN/TECH gate.** The foreman signed off the amended plan: five
  phases, each job's timeout 15 minutes, the cases' step capped at 12, the 900 s envelope in R1.
  The maintainer's (B), 15 cases a shard, stands; P3's first measured run decides whether the size
  changes to fit the envelope, and the foreman resizes per the maintainer's instruction and reports.
  Up to three `workflow_dispatch` runs are approved (GOAL Q4), none in P1 or P2.
- **2026-11-10, P1 build.**
  - The frozen gate pins no literal commit: its base is `git merge-base HEAD origin/develop` and its
    plan commit the one that added `PLAN.md`, both read at run time, so the rebase onto `146cbc6`
    left nothing stale and no wrapper under `remediation/` was needed. `untouched 1` was seen red on
    a planted `run_child` change, then green on the restored tree.
  - The module-list item for `tests/test_mutant_shards.py` sits after `tests/test_sdist_hygiene.py`,
    not directly after `tests/test_mutations.py`: the sibling's built branch rewrites the
    `tests/test_mutations.py` item, and an item inserted beside it conflicts in a 3-way merge. Placed
    one item away, `AGENTS.md` and `tests/mutants.py` both merge clean with
    `fix/mutant-child-outlives-timeout` (`git merge-file`, 2026-11-10).
  - `parse_shard` refuses a malformed shard and a COUNT other than `shard_count(ids)`; the NUMBER's
    range is refused once, by `shard_ids`, which `sharded` calls right after it. The CLI refuses
    the same shards PLAN § 2.1 names, and each sweep anchor occurs once.
  - `--matrix` prints the list of shard numbers as Python prints a list of ints, which is JSON: the
    imports may gain only `Iterable`. Its "no mutation cases found" line goes to stderr, beside the
    shard listing, so the plan job's log shows it.
- **2026-11-10, P2 build.**
  - `mutants.yml` is PLAN § 2.2's shape, every timing figure as recorded: both jobs
    `timeout-minutes: 15`, the `run` step capped at 12, `SHARD_SIZE` 15 unchanged. The `plan` job
    carries `name: plan` (the `runs` gate reads the job by that name), and the shard job's `name`
    is `mutants (N of S)` from `matrix.shard` and `strategy.job-total`.
  - Slots: at today's 1,164 Linux cases the matrix is 78 shard jobs plus `plan`. The organisation's
    Free plan allows 20 concurrent jobs, shared by every repository, so a run takes all 20 for
    about four waves (PLAN § 2.5). Not changed here; P3's run measures it.
  - The workflow row holds the shard job's setup steps equal to `ci.yml`'s `suite-legacy-1`
    (everything but its suite command), as the `workflow` gate does, so a later change to the
    suite jobs' setup shows as a red row in the suite, not only at a dispatch.
  - `verify/shard-mutants.py` gained the `workflow` mode by addition only: a `MODES['workflow']`
    line after the `MODES` literal, which is left as P1 wrote it. Its nine mutants are killed.
  - The `mutants budget` row adds one clause to PLAN § 2.3's wording: the run keeps fitting while
    its shards, run in waves of the account's concurrent jobs, finish within the 15 minutes. Without
    it the row's "a case added makes more shards, not a longer job" reads as if the envelope held
    at any count, which § 2.5 shows it does not (R3: a cycle that adds cases can tell).
  - `git merge-file` of `tests/mutants.py` and `AGENTS.md` against
    `fix/mutant-child-outlives-timeout` at `5ed1a63`, base `146cbc6`: both clean (2026-11-10).
- **2026-11-12, rebase onto `develop` at `2719b7a`** (the sibling `mutant-child-outlives-timeout`
  landed as `32a85c3`, then the 0.2.0 release).
  - One conflict, `ROADMAP.md`: develop's horizon line for this cycle's entry kept, with the seed's
    status `adopted:mutants-workflow-timeout`. `tests/mutants.py` and `AGENTS.md` merged clean; this
    cycle's own files are byte-identical to before the rebase.
  - The figures P2 recorded stand: 1,164 Linux cases (1,165 on macOS, the same ids), `SHARD_SIZE`
    15, 78 shards of 14–15. The sibling's stop realises the 310 s hang allowance: `LIMIT` 300 s, then
    at most `GONE_WITHIN` 10 s for the run to be gone. A hung case is now reported `FAILED` with its
    timeout and the shard goes on, so D1's landing-order caveat no longer applies.
  - 2026-11-12 · foreman ruling: after the rebase onto develop, P1's re-gate runs `untouched 2`,
    cumulative, in place of `untouched 1`, whose file list is P1's. No attempt is recorded.
  - 2026-11-12 · foreman ruling: the frozen `controls` mode's "untouched run_child" control plants
    on `timeout=300)`, which the sibling's `run_child` no longer holds (it waits with
    `communicate(timeout=LIMIT)`), so its plant lands nowhere and the control reads BAD; the
    `untouched` check itself is sound. Seen red first (`controls: 1 failed`, that control alone).
    `remediation/F1-controls-anchor.py` runs the mode unchanged, accepts only that one BAD and only
    while its anchor is absent, then re-runs the control with plants that land once each
    (`communicate(timeout=LIMIT)` → `600`, wanting "run_child changed"; `LIMIT = 300` → `600`,
    wanting "LIMIT changed"). P2's and P5's `verify:` run the wrapper in place of `controls`;
    `verify/` is not edited.

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
