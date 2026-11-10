# PLAN — A dispatched mutation run finishes and reports every case

> **Status:** Amended to the maintainer's 15-minute envelope (GOAL Q6) · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). There is no research fan-out: this is the
> lean path (`appetite: small`, root cause known, no high-blast-radius path). The timing sample it
> rests on is [`research/timing-sample.tsv`](research/timing-sample.tsv) (§ 4). The deliverable is a
> gate (a CI workflow and its verdict ledger), so the adversarial review ran (§ 7). Every design
> element traces to a GOAL R-ID.

## 1. Summary

The workflow becomes two jobs. `plan` asks the runner how many shards this commit's cases make, and a
matrix job runs one shard each. A shard holds at most `SHARD_SIZE` cases, dealt out from the sorted
ids, so a case added makes another shard, never a longer job (R3). Each shard runs its cases and the
runner's controls. A **ledger** step then checks the shard's report, and it runs even when the cases'
step failed or hit its own timeout. It requires exactly one `killed` line per case and every control
passed, and it names each case without one (R2). The selection and the ledger live in
`tests/mutants.py` as pure functions behind three flags. They are pinned by rows in a new
`tests/test_mutant_shards.py`, each of which kills a named mutant. Three dispatched runs measure the
jobs. `AGENTS.md` gains the `mutants budget` row (R4) and the corrected dispatch sentences (R5).

The maintainer's envelope (GOAL Q6) binds the shape:
- each job's timeout is 15 minutes, and the cases' step is capped at 12;
- the whole run, from dispatch to its last job, finishes within 15 minutes, queueing included;
- each job stays within 10 minutes with one hung case, which gives about 15 cases a shard;
- P3's first run measures the run's wall time and the jobs it ran at once. If the waves push the run
  past 15 minutes, the size is refitted from those figures (§ 2.5).

## 2. Design

### 2.1 The runner (`tests/mutants.py`)

The changes to the runner, and nothing else:
- one new block between `self_check` and `main`;
- in `main`, three new options and the three lines of the `sharded` call;
- three new lines in the module docstring's Usage block;
- `Iterable` added to the `typing` import.

`CASES`, `SURVIVOR_CONTROL`, `apply`, `apply_repo`, `run_child`, `run_case`, `mutation_violations`,
`self_check` and the `__main__` block stay byte-identical. `main` only gains its six lines. The
`untouched` gate holds both rules (§ 6).

- **`SHARD_SIZE = 15`**: the most cases a shard holds. The sizing is § 2.4; the figure is § 3 row D1's.
- **`CONTROLS`**: the three texts `self_check` prints after its verdict word:
  - `surviving mutant reported`
  - `wrong origin reported`
  - `member missing from the copy reported`

  A row runs the real `main` and `self_check` with `run_case` faked and feeds their output to the
  ledger. So a reworded control line goes red in the suite, not on the runner.
- **`shard_count(ids, size=SHARD_SIZE)`** = ⌈len(ids)/size⌉. It is the fewest shards that hold the
  ids at most `size` to a shard, and 0 for none.
- **`shard_ids(ids, number, count)`** = `sorted(ids)[number - 1::count]`. It refuses a number outside
  1..count.
  - **Sorting** makes every job compute the same split, whatever order the tuple was built in.
    Without it, a set anywhere in `CASES`' construction would make two jobs disagree, and a case
    would run twice or never.
  - **Dealing round-robin** spreads a family of neighbouring ids across the shards instead of piling
    one family into one job. The slow families are neighbours (`tpc-*`, `shol-*`, `probe-timing-*`;
    § 4).
  - Shard sizes differ by at most one. Each is ≤ `size`, because count = ⌈N/size⌉.
- **`parse_shard(text, ids)`** reads `NUMBER/COUNT`. It refuses a NUMBER outside the count, and a
  COUNT other than `shard_count(ids)`: a job told a different count than the plan computed would take
  a different split, with overlaps and holes.
- **`report_violations(expected, lines)`** returns every reason a shard's report does not hold
  exactly one `killed  <id>:` line per expected case and exactly one `control  <text>:` line per
  control. It names:
  - each case with no line: `no verdict reported`;
  - each case with two or more lines: `reported N times`;
  - each case with a `FAILED` line: `not killed`;
  - each id the shard does not hold: `not a case of this shard`;
  - each control that is missing, failed or doubled.

  No expected case at all is `no mutation cases found`. Lines it does not recognise (tracebacks,
  pytest noise) are ignored: they cannot make a case pass.
- **`sharded(parser, args, ids)`**, called by `main` right after `known` is built:
  - **`--matrix`**, alone, prints `[1, …, S]` on stdout: a JSON list, the matrix. On stderr it prints
    one `shard N of S: <ids…>` line per shard, so the run's log names every case of every shard
    before any shard runs. With no case it prints `no mutation cases found in tests/mutants.py` and
    exits 1.
  - **`--shard N/COUNT`** replaces `args.cases` with the shard's ids. `main` then runs them exactly
    as named cases run today, with `--self-check` when it is given. Case ids beside it are refused:
    `name cases or a shard, not both`.
  - **`--ledger REPORT --shard N/COUNT`** runs nothing. It prints `FAILED  <reason>` per violation,
    or one `ledger  shard N of COUNT: K cases killed, 3 controls passed` line, and exits 1 or 0. A
    missing report file reads as empty, so every case of the shard is named `no verdict`.
    `--ledger` without `--shard` is a usage error.

The ledger re-reads the report in a separate process, after the runner has exited, however it
exited. Today two failures escape `main` and lose every later line: a hung case's `TimeoutExpired`,
and a moved anchor's `ValueError`. A runner killed by the step's timeout loses them too. In each
case, the ledger still names every case the runner never reported.

**The rows** live in a new module, `tests/test_mutant_shards.py` (`unit`, in-process, `run_case`
faked). It joins § Testing's module list in P1, and it runs in the suite's fourth command with no
edit to any list. `tests/test_mutations.py` stays byte-identical.

**Touch points for the sibling cycle** (`mutant-child-outlives-timeout`). The sibling edits:
- the import block;
- the run-child block and `run_child`;
- three lines of `run_case`;
- the `__main__` block;
- rows in `tests/test_mutations.py`;
- one sentence in the § Testing mutation-runner bullet.

This cycle's hunks are:
- the docstring's Usage lines;
- the `typing` import line (the sibling adds `signal` and `time` two lines away);
- the new block between `self_check` and `main`;
- the top of `main`;
- the new module;
- in `AGENTS.md`, the profile row, the module-list line, and the bullet's figure, usage and closing
  sentences.

The adversarial review merged this prototype with the sibling's built P1 (`fdb0a0f`) by 3-way
`git merge-file` (§ 7). `tests/mutants.py` and `AGENTS.md` merged clean. `tests/test_mutations.py`
conflicted three times, which is why the rows moved to their own module. Whichever cycle lands second
re-runs its P1–P2 gates after the rebase.

### 2.2 The workflow (`.github/workflows/mutants.yml`)

- `on: workflow_dispatch` only. `permissions: contents: read`. `defaults.run.shell: bash` and no
  step-level `shell:`, so GitHub runs every step as `bash -e -o pipefail`: a runner that exits 1
  fails its step through `tee`.
- **`plan`** (`ubuntu-24.04`, `timeout-minutes: 15`):
  - checkout, setup-uv and `uv sync --locked`, as ci.yml's suite jobs carry them;
  - then `shards=$(uv run python tests/mutants.py --matrix)` into `$GITHUB_OUTPUT`.

  A failure there (no case) fails the run before any shard: R2's "no case found".
- **`mutants`** (`needs: plan`, `ubuntu-24.04`, `timeout-minutes: 15`, name `mutants (N of S)`):
  - `strategy.fail-fast: false`: one failing shard must not cancel the others' verdicts.
  - `matrix.shard: ${{ fromJSON(needs.plan.outputs.shards) }}`, with no `exclude`/`include`.
  - `env.SHARD: N/S`, from `matrix.shard` and `strategy.job-total`.
  - Steps: checkout, setup-uv, **then the login-shell provisioning step and `uv sync --locked`,
    verbatim as ci.yml's suite jobs carry them**. Then:
    - **`run`** (`timeout-minutes: 12`): `uv run python -u tests/mutants.py --self-check --shard
      "$SHARD" | tee mutants-report.txt`. It is unbuffered, so a step killed at its cap leaves every
      line it printed.
    - **`ledger`** (`if: always()`): `uv run python tests/mutants.py --ledger mutants-report.txt
      --shard "$SHARD"`.
  - The job fails when either step fails, so the run fails on any case not killed. The ledger's
    `FAILED` lines name each one in that job's log.
- **The shells.** GitHub sets `CI=true`, and `conftest.need_shell` then *fails* a login-shell row
  whose shell is missing, rather than skipping it. Today's `mutants.yml` installs no shell. So every
  case whose targets drive `zsh`, `tcsh`, `ksh` or `csh` would be "killed for the wrong reason" on
  the runner. The shard job installs them as ci.yml's suite jobs do. This is the runner's
  environment, not a case's semantics (Non-goal 3 untouched).
- No artifact upload, no cache, no secret, no token handed to a step, no `|| true`, no
  `continue-on-error`, no new action: every `uses:` is ci.yml's own pin.
- The header comment states:
  - the dispatch state, as R5 words it: `main` carries the file, so a run can be dispatched against
    any branch that has it;
  - the shape above.

### 2.3 Documents (`AGENTS.md`)

- **§ Factory profile, a new `mutants budget` row after `ci budget`** (R4). It states:
  - every job of `mutants.yml` finishes within 10 minutes of wall time, start to completion as
    `gh run view --json jobs` reports it, on the hosted `ubuntu-24.04` runner, with
    `timeout-minutes` at 15, and the whole run within 15 minutes from its dispatch to its last job's
    completion, queueing included;
  - a shard holds at most 15 cases (`SHARD_SIZE`), so that a job with one case stopped at the
    runner's 300 s per-case limit (about 310 s) still fits;
  - a case added makes more shards, not a longer job, so the run keeps fitting while the worst job
    plus 310 s stays within 600 s;
  - `Baseline: pending` until P5. Then the `runs` gate's sentence: the case count, the shard count,
    the run's worst wall from dispatch, the slowest job and its seconds per case over its own case
    count, the commit, the three runs, and each job's worst time.
- **§ Testing's module list** gains `tests/test_mutant_shards.py` (P1).
- **§ Testing, the mutation-runner bullet:**
  - "A child takes about 2 s, all cases about 3 minutes" becomes the measured cost. P2 points to the
    row, with "pending". P5 writes "N cases in S shards, the run M:SS from dispatch, slowest job M:SS".
  - The usage block gains `--matrix`, `--shard` and `--ledger`.
  - The closing sentences describe the sharded run and state the dispatch state (R5).
- **R3's "tell, without dispatching, whether the full run still fits".** The row states the rule
  (shards grow with the count; a job holds ≤ 15 cases; the run fits while the worst job + 310 s ≤
  600 s) and the measured seconds per case on the slowest job. A cycle that adds cases times them
  locally in its own phase gates, and can compare their mean with that figure.

### 2.4 Sizing

**What a job holds:**
- setup: checkout, setup-uv, apt shells, sync. 16–26 s on today's runners (ci.yml run 42710890596).
- the three controls: three children.
- the shard's cases.
- the ledger: ~3 s.

**Per case on a development host:** mean 4.1 s, median 2.7 s, p90 6.9 s, max 19.4 s, over a 41-case
stratified sample (every 29th sorted id, § 4).

**The hosted runner against that host:** ci.yml's suite jobs ran at about 1.2× the host's time on
2026-11-09. Slower runs reached up to 2.2×: the `ci budget` baseline's 7:34, against today's ~4:00
for the same command. So on the runner:
- per case: ~4.9 s typical, ~9.0 s on a slow runner;
- per-job overhead on a slow runner: ≈ 90 s (setup 26 × 2.2 ≈ 57 s, controls 3 × 9.0 = 27 s, ledger
  ≈ 7 s).

**The rule:** `SHARD_SIZE = ⌊(540 − 90 − H) / 9.0⌋`.
- 540 s is the 600 s budget less a 10 % margin for a runner slower than any seen.
- 90 s is the slow-runner overhead.
- 9.0 s is the slow-runner case cost.
- H is the hang allowance.

**With H = 310 s** (§ 3 row D1): ⌊140 / 9.0⌋ = **15**.
- At 1,164 Linux cases that is 78 shards: ⌈1164/15⌉ = 78, 72 shards of 15 and 6 of 14. The macOS set
  of 1,165 also makes 78.
- The slow-runner job: 135 + 90 = 225 s. With one hung case: 535 s ≤ 600 s.

**The cases' step cap: 12 minutes** (720 s, § 3 row D2). The job's timeout is 15 minutes (900 s,
GOAL Q6), and the step must leave room after it for the ledger to run.
- After the step come the ledger (≈ 7 s) and teardown (≈ 5 s). Before it, setup takes up to 57 s on a
  slow runner. That leaves at most 900 − 69 = 831 s for the step.
- 13 minutes (780 s) would end the job at ≈ 849 s, a 51 s margin. 12 minutes ends it at ≈ 789 s
  (13.2 min), a margin of 111 s. That covers an apt mirror or a setup-uv download twice as slow as
  any seen. So the cap is 12.
- Hung cases the step still reports with every verdict:
  - one on a slow runner: 27 + 135 + 310 = 472 s ≤ 720 s; two would take 782 s;
  - two on a typical one: 10 + 74 + 2 × 310 = 704 s ≤ 720 s.

  Beyond that, the ledger names what is left.

### 2.5 The run's wall, waves and the refit

- **Concurrency.** The organisation is on GitHub's Free plan (read with `gh api`, 2026-11-09). It has
  20 concurrent hosted jobs, shared with every workflow of every repository in the organisation.
  78 shards therefore run in at least 4 waves (⌈78/20⌉).
- **The model.** run wall ≈ plan span + waves × job. The plan span is the time from dispatch until
  `plan` is done: about 45 s typical, 60 s slow. A job is the overhead (setup, ledger, teardown:
  about 24 s typical, 64 s slow) plus (cases + 3 controls) × the child cost (4.9 s typical, 9.0 s
  slow).
- **Projections** at 1,164 cases and 20 free slots, from the `runs` gate's own `refit` table:

  | size | shards | waves | job typ./slow | run typ./slow | run + one hang, typ./slow | fits (slow) |
  |---|---|---|---|---|---|---|
  | **15** | 78 | 4 | 112 / 226 s | **494 / 964 s** | 804 / 1,274 s | envelope missed |
  | 20 | 59 | 3 | 137 / 271 s | 455 / 873 s | 765 / 1,183 s | both bounds |
  | 30 | 39 | 2 | 186 / 361 s | 416 / 782 s | 726 / 1,092 s | envelope only (one hang takes a job to 671 s) |
  | 50 | 24 | 2 | 284 / 541 s | 612 / 1,142 s | 922 / 1,452 s | neither |

  - At 15 a shard, the run fits the envelope on a typical runner (≈ 8.2 min, ≈ 13.4 min with one
    hung case in the last wave). It misses on a slow one (≈ 16 min).
  - 20 a shard drops a wave. On a slow runner it is projected to keep both bounds: 14.6 min, and a
    job with one hung case at 9.7 min.
  - With another workflow holding 9 of the 20 slots (a cycle's ci.yml push run), no size keeps the
    envelope on a slow runner: the best is 53 a shard at ≈ 20 min.
- **P3 decides the size.** Run 1 runs at 15, the maintainer's (B). The `runs` gate measures:
  - the run's wall from dispatch, queueing included;
  - the most jobs it ran at once;
  - the plan span;
  - each shard's overhead and seconds per child.

  It refits from those figures. Each size's projection uses the slowest child, the largest overhead,
  the fewest jobs at once and the longest plan span. The proposal is the size that keeps both bounds
  (each job within 600 s with one hung case, the run within 900 s) at the lowest projected run wall.
  If none keeps both, the envelope wins (Q6: "pick the shard size that fits"). If no size keeps even
  the envelope, it says so.
  - **Run 1 within both bounds:** the size stays. P4 and P5 make runs 2 and 3, one at a time, since two
    runs at once would share the 20 slots and both miss the envelope.
  - **Run 1 outside either bound:** P3 Run B stops and hands the foreman run 1's figures and the
    refit table. The foreman brings them to the maintainer (Q6: "bring the measured run back"), with
    the dispatch question that follows: two dispatches remain, and R4 counts the worst of the runs
    at the landed size.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | Every platform case exactly once: `shard_count` + `shard_ids` (sorted, round-robin, ≤ 15 a shard), `parse_shard`'s count check, the `plan` job and the `fromJSON` matrix, `fail-fast: false`. A report before the timeout: `timeout-minutes: 15` on both jobs, the 12-minute cap on the cases' step, the always-run ledger. Within 10 minutes: shard sizing with one hung case (§ 2.4, row D1). The run within 15 minutes from dispatch: the waves, measured and refitted in P3 (§ 2.5). The shells provisioned. Proven on the hosted runner by the three runs (P3, P4, P5): each job ≤ 600 − 310 s, the run ≤ 900 s from dispatch, each case reported once, every control passed. |
| R2   | `report_violations` via `--ledger` in every shard: survived, wrong reason, no verdict, doubled, foreign id, controls. Its `FAILED` lines name each case. The job, and so the run, fails. `--matrix` fails the run when no case is found. `--self-check` runs in every shard. |
| R3   | ⌈N/15⌉ shards, computed at run time from `mutants.CASES`, so adding cases needs no workflow edit. The row's fitting rule and per-case figure (§ 2.3). |
| R4   | The `mutants budget` row: the bound, the shard size, then the measured baseline (cases, shards, slowest job and per case, commit, runs, each job's worst of three). § Testing's cost sentence and pointer. Filled from `mutants-gate.py runs --final` output (P5). |
| R5   | The workflow header and § Testing's dispatch sentences (P2). |

## 3. Invariant gate (AGENTS.md constitution check)

Walked at Step 2 against the GOAL, and again against this design.

No numbered § Invariants section (1–9) is touched. The change is:
- a test-runner block and a new test module;
- a workflow;
- three `AGENTS.md` passages.

It touches no product module, not `bin/sandbox.sh`, and no path on the high-blast-radius list. So of
the research triggers:
- trigger 1 does not fire: the cause is known;
- trigger 2 does not fire: no high-blast-radius path;
- trigger 3 fires: the deliverable is a gate.

The § Conventions and other sections the change touches:

- **§ Conventions, "CI mirrors the gate"** binds `ci.yml` to the profile's lists. `mutants.yml` is
  outside those lists and stays so: no `verify`/`gate` change. Its shared steps copy ci.yml's suite
  jobs verbatim, and the `workflow` gate compares them, so a later ci.yml change to those steps shows
  as a divergence.
- **§ Conventions, workflows.**
  - Every `uses:` is a full SHA: ci.yml's two pins, reused.
  - `permissions: contents: read`, and no secret.
  - No write outside the runner: no artifact, no cache. The `plan` job's output is the run's own
    job-output context, carried by the run itself under a read-only token. It is not a write to any
    store (row D4).
- **§ Conventions, comments and spec ids.** New comments are declarative. There are no
  `R`/`P`/`Q`/`F` ids in `tests/` or `.github/`: the `prepush` scan checks the added lines, and
  `test_no_spec_ids_…` covers `tests/`.
- **§ Conventions, markers.** Every new row is `@pytest.mark.unit`. The gate names its rows by id,
  never by a marker or `-k` selection.
- **§ Conventions, sandboxed drives.** There is no new launch in `tests/*.py`: the rows call `main`
  in-process with `run_case` faked. The mutation children stay under `bin/sandbox.sh`, as today.
- **§ Conventions, point to a rule.**
  - The bound lives in the `mutants budget` row. § Testing and the workflow header point to it.
  - R4 requires the measured cost in both § Testing and the row. That is a same-commit obligation,
    which the `docs --final` gate checks.
- **§ Factory, `ci` row**: unchanged. Publish never reads `mutants.yml` (Non-goal 2).
- **§ Testing**: the case semantics are untouched (Non-goal 3). `CASES`, `run_child`, `run_case`,
  `mutation_violations` and `self_check` are byte-identical. `main` gains only its six lines. The
  module list gains the new module.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **D1 — R1 read with one hung case inside the 10 minutes; `SHARD_SIZE = 15`, refitted in P3 if the waves miss the envelope.** The maintainer's answer (GOAL Q6, 2026-11-09) settles the reading as (B), about 15 cases a shard. A shard is sized so that a job with **one** hung case, on a slow runner, still finishes within 600 s (§ 2.4: ⌊(540 − 90 − 310)/9.0⌋ = 15). **Before:** one job, `timeout-minutes: 30`, 49–97 min serial projected, cancelled with no report. **After** (1,164 cases): **78 jobs of 14–15 cases**. Per job: ~1.9 min typical, ~3.8 min on a slow runner, ~8.9 min with one hung case on a slow runner. Run: 4 waves at the organisation's 20-job Free-plan limit; ≈ 8.2 min from dispatch typical, ≈ 13.4 min with one hung case; **≈ 16 min on a slow runner, over the 15-minute envelope** (§ 2.5). ~145 runner-minutes. **Landing order:** the hang allowance assumes the sibling cycle's stop. Until it lands, a hung case's `TimeoutExpired` escapes `main`, and the rest of that shard reports no verdict. The ledger names them (R2 holds), but R1's "verdict for every case" does not hold in that shard. | R1 as reworded by Q6: each job within 10 minutes even with one hung case, and the run within 15 minutes of dispatch. | **Reading A** (50 a shard, 24 jobs, 2 waves; a hung case takes its job to ~14 min) was declined by the maintainer (Q6). **A size fitted to the waves now** (20 a shard, 59 jobs, 3 waves: projected 14.6 min slow, a hung case's job 9.7 min) is the refit's likely answer on a slow runner, but Q6 sets (B)'s ~15 and asks for the measured run first. P3's run 1 measures it, and the `runs` gate's refit proposes the size that fits (§ 2.5). **Switching** changes `SHARD_SIZE` in `tests/mutants.py`, the gate's plan-time `SHARD_SIZE`, the row's "15 cases", and this table. The `runs` gate reads the size from the measured commit. |
| **D2 — the cases' step capped at 12 minutes** (`timeout-minutes: 12` on the `run` step), inside the job's 15 (GOAL Q6). | R1's second clause: "a reported verdict for every case before any of its jobs reaches its timeout". A shard with more hung cases than its size allows is stopped at 12 minutes. The always-run ledger then names every case the runner never reported, at ≤ ~13.2 min, before the 15-minute timeout (§ 2.4). Without the cap, a job timeout cancels the job and its report is lost. The cap holds one hung case on a slow runner and two on a typical one. | **13 minutes** leaves a 51 s margin over a slow setup, the ledger and teardown, against 111 s at 12. **No step cap**, relying on the job's timeout and an `if: always()` ledger: GitHub's cancellation re-evaluates `always()` and runs the step, but the job is then already past its timeout, and the server may force-stop it 5 minutes later. **A cap in the runner itself** (a wall-clock deadline in `main`) gives the same guarantee with more code in the file the sibling cycle edits. |
| **D3 — the counted runs may sit on three commits.** The runs are dispatches of the branch head. Run 1 (P3) is at the measured commit T1. Run 2 (P4) is at P3's closing commit, and run 3 (P5) at P4's. Both differ from T1 only in `spec/`, and, if a run found survivors, in `issues/` and `ROADMAP.md`. The runs go one at a time: two at once would share the organisation's 20 job slots and miss the envelope (§ 2.5). R4 records "the commit", so the row names T1. | Dispatching all three at T1 would burn every dispatch at once if run 1 showed the shape wrong (a mis-sized shard, a workflow error), leaving none to measure the fix (Q4 allows three). The `runs` gate accepts a later commit only if this clone holds it and `git diff --name-only T1 <sha>` lists nothing outside `spec/`, `issues/` and `ROADMAP.md`. So the code and workflow measured are T1's. `--final` also refuses a landing tree that changed anything but those records and `AGENTS.md` since T1. | **Three dispatches at once at T1**: one fewer foreman round trip, but all three lost to one error. **Re-running run 1's attempts** (`gh run rerun`) keeps one commit, but a re-run is not one of the three dispatches Q4 names. |
| **D4 — a job output carries the matrix** (`plan` → `fromJSON`). | R3: the shard count must follow the case count with no workflow edit. | **A fixed matrix** (`shard: [1 … 78]`) needs an edit whenever ⌈N/15⌉ changes, or runs empty shards. **A fixed generous count** wastes jobs and still caps growth. The output is run metadata under a read-only token, not a write outside the runner (§ 3, workflows). |

Each row was read against R1–R5 as `GOAL.md` words them:
- **D1** is the reading of R1's 10 minutes that the maintainer chose (Q6). It names the
  landing-order dependency on the sibling, and the refit that keeps R1's 15-minute envelope.
- **D2** serves R1's second clause, inside Q6's 15-minute timeout.
- **D3** serves R4's "the commit … the runs counted … the worst of the counted runs", and is shown at
  sign-off.
- **D4** serves R3.

Every figure was rederived from § 2.4's rule, with the controls and ledger counted, after the
adversarial review found the first draft had left them out (§ 7).

## 4. Rabbit holes (resolved)

- **Per-case cost.** A 41-case stratified sample: every 29th sorted id, run serially by `run_case` on
  a development host under a load average of ~2.8
  ([`research/timing-sample.tsv`](research/timing-sample.tsv)):
  - mean 4.11 s, median 2.73 s, p90 6.94 s;
  - max 19.35 s (`tpc-wait-read`, 8 targets);
  - 168 s in all, and every case killed.

  Serial projection on that host: 1,165 × 4.1 s ≈ 80 min, within the GOAL's 49–97. A full local
  shard, run as the workflow runs it (shard 78 of 78 on macOS: 14 cases and the three controls), took
  ~65 s in the `drive` gate, and its ledger passed.
- **Runner speed and its spread.** Suite jobs of ci.yml, over the 11 runs since the split landed
  (2026-11-06 to 2026-11-09):
  - the same command took 156–451 s, most of them 160–300 s;
  - the `ci budget` baseline's worst (7:34) is ~1.9× today's;
  - setup per job took 16–26 s (run 42710890596).

  Hence 1.2× typical and 2.2× slow, against the development host (§ 2.4).
- **GitHub semantics** (docs.github.com, read 2026-11-09):
  - a matrix makes at most 256 jobs per run: 3,840 cases at 15, over 2,600 more than today;
  - `fail-fast` cancels in-progress and queued matrix jobs when one fails, so it is set false;
  - a matrix from a previous job's output via `fromJSON(needs.<job>.outputs.<name>)` is the
    documented pattern;
  - a step's `timeout-minutes` kills the step's process;
  - on cancellation the server re-evaluates `if:` and runs `always()` steps. It sends SIGINT, then
    SIGTERM after 7.5 s, kills the process tree 2.5 s later, and force-stops after 5 minutes;
  - concurrent hosted jobs per account: 20 (Free), 60 (Team), 500 (Enterprise).
- **The runner's environment.** `CI=true` turns a missing login shell into a failing row
  (`conftest.need_shell`). Today's `mutants.yml` installs none, so its first run would have reported
  every shell-row case as killed for the wrong reason. The shard job provisions the shells (§ 2.2).
- **Order across jobs.** Each job imports `mutants` in a fresh process, and a split by position
  would follow `CASES`' construction order. So the split sorts first, and a row pins the literal
  sorted order (§ 2.1).
- **A crashed runner.** Today a hung case's `TimeoutExpired`, or a moved anchor's `ValueError`,
  escapes `main` and loses every later line. The ledger, a separate process, names those cases.
- **Mutant coverage of the rows**, dry-run on the prototype:
  - 33 planted mutants of the selection, the ledger, the CLI and the workflow, each killed by a
    named row (§ 6.2).
  - The first sweep selected rows with a `-k` word that one row's name lacked, so that row was not
    run. The gate names rows by id.

## 5. Risks & open questions

- **The envelope on a slow runner.** The 15-a-shard run is projected to miss the 15-minute envelope
  on a slow runner (≈ 16 min, § 2.5). P3 measures it, and refits on a miss.
- **A refit costs dispatches.** If run 1 misses either bound, P3 stops with the refit table (§ 2.5).
  Two dispatches then remain, and R4's "worst of the counted runs" would count runs at the landed
  size: a question for the maintainer then, not before.
- **Shared concurrency.** The Free plan's 20 jobs are shared by the whole organisation. A cycle's
  ci.yml push run (9 jobs) during a mutants run leaves 11 slots, and then no size keeps the envelope
  on a slow runner (§ 2.5). Dispatches should go when no other run is queued. The `runs` gate
  measures the jobs a run actually ran at once.
- **First hosted run survivors** (Q3). Each case not killed is seeded in P3 as its own `issues/`
  entry with a `ROADMAP.md` line, and the cycle lands with the run reporting it. More than three go
  back to the foreman before P4. Expected sources:
  - timing-sensitive targets on a slower runner (the
    [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md)
    class);
  - an environment difference that the suite jobs do not hit, because they run no mutants.

  Children stay serial within a job, so this design adds no concurrency hazard; jobs run on separate
  runners.
- **Queueing and the measure.** With 78 jobs and a 20-job account limit, shards queue in waves. The
  run's wall is measured from its dispatch (`createdAt`) to its last job's completion, so queueing
  counts there, as Q6 asks. A job's own `startedAt` is taken to be when a runner took it. If it is the
  job's creation instead, later waves would carry queue time in the per-job 10-minute measure. The `runs` gate refuses a job whose first step started 60 s or more
  after the job's `startedAt`, so a queue wait inside the measure stops P3. It is never counted, and
  never silently subtracted; amending the row's definition would be the foreman's call. Other
  workflows of the organisation queue behind the run while it holds the slots.
- **The step cap and the ledger on the hosted runner** are exercised only if a case hangs, and no
  hang is planted in a counted run.
  - The local `drive` gate exercises the ledger's missing-report path.
  - The `if: always()` path after a failed step is exercised whenever a case is not killed.
- **`gh` log format.** The `runs` gate parses `gh run view --log --job` lines
  (`job\tstep\t[BOM]stamp text`, checked against run 42710890596). A format change makes the gate
  red, not green.
- **The platform-only case.** The `runs` gate expects the hosted plan to hold exactly the macOS set
  less `tpc-clobber`. Another platform-conditioned case added before P3 would need the gate's
  `DARWIN_ONLY` amended by the foreman.
- **The sibling cycle** (§ 2.1).
  - If it lands first, this branch rebases with no conflict and re-runs P1–P2's gates.
  - Until it lands, the hang allowance does not hold (row D1).

## 6. Verification strategy

All gates are modes of the frozen [`verify/mutants-gate.py`](verify/mutants-gate.py), run with
`UV_PYTHON=3.14 uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py MODE`.

### 6.1 Modes

- **`rows PHASE`**: the named rows, each by id, in both eras. P1 runs the runner's eleven; from P2 on
  there are twelve.
- **`untouched PHASE`** holds:
  - the case semantics and the sibling's surface: the base's top-level statements of
    `tests/mutants.py` are kept in order, except the docstring, `main` and the imports;
  - `main` gains only its six lines;
  - the imports gain only `Iterable`;
  - only the named block is new;
  - `tests/test_mutations.py` is unchanged;
  - each phase changes only its own files, graded from the plan commit.
- **`workflow`**: § 2.2, statically. Each step is compared line for line. The shared steps are
  compared with ci.yml's. It also checks the default shell, forbids `|| true`, `exclude`/`include`
  and a token, and pins both job timeouts at 15 and the cap at 12.
- **`docs [--final]`**: the R4 and R5 text, including the 15-minute timeout and envelope. `--final`
  compares the row and § Testing with the `runs` baseline: cases, shards, the run from dispatch and
  the slowest job.
- **`drive`**: the last shard of the index's tree, run as the workflow runs it, in a fresh export with
  its own venv. Its ledger must be green. Then the same report, with one `killed` line dropped, must
  be red and name that case.
- **`prepush`**: a clean tree, a site-private scan of the added lines, and the deferral ledger.
- **`runs --runs-file spec/mutants-workflow-timeout/runs.txt [--final]`**: the hosted evidence
  (§ 6.3).
- **`controls`**: each data-deciding check run on planted data. All 60 plants are refused for their
  reason, and the sound data accepted, on the prototype.

### 6.2 The mutant sweep (written by P1, extended by P2)

P1 writes `verify/shard-mutants.py`. For each mutant below, it plants the mutant into an export of
the staged tree (`tests/mutants.py`, or from P2 the workflow) and runs the killing row by id. Each
mutant must turn its row red. On the prototype, every entry was killed by the row named:

| Mutant | Kind | Killing row |
|---|---|---|
| `[number - 1::count]` → `[number::count]` | a case skipped, a shard shifted | `test_the_shards_hold_every_case_once` |
| `sorted(ids)` → `list(ids)` | order-dependent split across jobs | `test_every_job_shards_the_cases_alike_whatever_their_order` |
| `sorted(ids)` → `sorted(ids, key=hash)` | a split that differs between processes | `test_every_job_shards_the_cases_alike_whatever_their_order` |
| `-(-len // size)` → `len // size` | too few shards, one over size | `test_the_shards_hold_every_case_once` |
| `… + 1` on the count | an empty shard | `test_the_shards_hold_every_case_once` |
| `number <= count` → `number < count` | the last shard refused (its cases lost) | `test_the_shards_hold_every_case_once` |
| `1 <= number` → `0 <= number` | shard 0 accepted (overlaps the last) | `test_a_shard_outside_the_run_is_refused` |
| count check dropped | a job splitting by another count (overlaps, holes) | `test_a_shard_outside_the_run_is_refused` |
| no-verdict check dropped | a case skipped unseen | `test_the_ledger_names_each_case_without_a_kill` |
| twice check dropped | a case run twice unseen | `test_the_ledger_names_each_case_without_a_kill` |
| `!= ['killed']` dropped | a survivor accepted | `test_the_ledger_names_each_case_without_a_kill` |
| foreign-id check dropped | a shard overlap unseen | `test_the_ledger_names_each_case_without_a_kill` |
| control check → presence only | a failed control accepted | `test_the_ledger_names_each_case_without_a_kill` |
| control check dropped | a missing control accepted | `test_the_ledger_names_each_case_without_a_kill` |
| empty-expected branch dropped | no cases accepted | `test_the_ledger_refuses_a_run_with_no_cases` |
| `partition('  ')` → `partition(' ')` | the runner's lines misread | `test_the_ledger_accepts_a_shard_whose_every_case_was_killed` |
| `list(known)` → `list(known)[:-1]` | a platform-only (last-defined) case lost | `test_the_run_holds_every_case_this_platform_defines` |
| the plan's stderr listing unsorted | the plan's log disagrees with its shards | `test_the_run_holds_every_case_this_platform_defines` |
| `args.cases = shard_ids(…)` dropped | a shard that runs nothing | `test_the_run_holds_every_case_this_platform_defines` |
| mixing refusal dropped | named cases silently replaced | `test_cases_and_a_shard_together_are_refused` |
| ledger exits 0 | a red ledger that passes its job | `test_the_ledger_fails_the_shard_and_names_each_case` |
| missing report → crash | a stopped step's cases unnamed | `test_the_ledger_fails_the_shard_and_names_each_case` |
| empty matrix passes | no case found, run green | `test_a_run_with_no_cases_names_no_shard` |
| `range(1, count)` | the last shard never scheduled | `test_the_run_holds_every_case_this_platform_defines` |
| P2, the workflow's decisions: `fail-fast: true`; job timeout 30; step cap 20; ledger without `always()`; a `push` trigger; a fixed matrix; `--self-check` dropped; `|| true` on the ledger; the `defaults` shell block dropped | | `test_the_mutants_workflow_runs_each_shard_to_a_ledger` |

`SHARD_SIZE`'s value is not pinned by a suite row. The `docs` mode pins it (the row states the
runner's value), and the runs measure it. The sweep runs one pytest at a time, each under a second.

### 6.3 The hosted runs (P3, P4, P5)

`runs.txt` holds `sha <T1>` and one `run <id>` per dispatch. For each run, the gate reads (with
`gh`, reads only) the run, its jobs and their logs. It checks:
- the run is a `workflow_dispatch` of `Mutants` on the cycle branch, in its first attempt;
- the run is at T1, or at a commit this clone holds that differs from T1 only outside the code (D3);
- the plan's `shard N of S` lines hold the case set of T1 less `tpc-clobber`, each case once, in
  ⌈N/size⌉ shards, with the size read from T1's runner;
- the jobs are `plan` and `mutants (1..S of S)`, each completed as success or failure (never
  cancelled), each with no queue wait inside its measure, and each within 600 − 310 s;
- the run took at most 900 s from its dispatch (`createdAt`) to its last job's completion;
- every shard reached its ledger, reported one verdict per planned case, and logged all three
  controls passed;
- every shard either passed with its `ledger` line or failed with `FAILED` lines, and no ledger line
  reports a failed control.

It prints the baseline sentence for the row, the headroom and the cases not killed. It also prints
each run's wall and the most jobs it ran at once, and the refit table and proposal (§ 2.5). `--final`
requires exactly three runs. It also requires each case not killed to be named in an `issues/` seed
(matched as a whole id), and the landing tree to differ from T1 only in the records and `AGENTS.md`.

### 6.4 The last local phase

P2 runs the profile's full `verify` (~26 min, in the background) after its gates.

## 7. Adversarial review

One fresh reviewer, given the GOAL, this PLAN's first draft, the gate script and the prototype,
attacked the gates and the prototype (appetite small: one pass). It ran the gate modes, planted
mutants in a scratch export, and merged the prototype with the sibling's built P1. Its 13 findings
and how each was folded:

1. **HIGH: `runs` counted a run whose controls failed.** A run where every shard failed only on a
   control passed with nothing to seed. **Fixed:** each shard's log must hold all three controls
   passed, and a ledger `FAILED  control` refuses the run. A plant was added.
2. **HIGH: `sha_ok` accepted a commit missing from the clone**, because `git diff` failed to empty
   output. **Fixed:** `same_code` requires `git cat-file -e` on both commits and runs `git diff` with
   `check=True`. Plants for the commit itself and an unknown commit were added.
3. **MEDIUM: `untouched` let `main` change freely**, such as a `try/except` that turns a crash into
   `killed`. **Fixed:** `main` may only gain the six named lines. Plants were added.
4. **MEDIUM: workflow checks matched commands by substring.** `|| true`, a dropped `defaults` shell,
   a step-level `shell:`, `exclude:`, a cap of 0 and a token all passed. **Fixed:** steps are
   compared line for line, the default bash is required, those words are forbidden, and the cap is
   pinned at 15. The suite row was tightened the same way. Seven plants were added.
5. **MEDIUM: the plan's stderr listing was unpinned**, and `runs` depends on it. **Fixed:** the
   platform row compares each `shard N of S` line with what that shard runs. The mutant was added to
   § 6.2.
6. **MEDIUM: the rebase claim was wrong for `tests/test_mutations.py`**: three conflicts with the
   sibling's built P1. **Fixed by design:** the rows moved to `tests/test_mutant_shards.py`, and
   `tests/test_mutations.py` is now held byte-identical.
7. **MEDIUM: queue time might count as wall time.** **Folded as a guard:** the `runs` gate refuses a
   job whose first step started 60 s or more after its `startedAt`. That stops P3 rather than count
   it (§ 5).
8. **MEDIUM: switching to reading A is more than one constant.** **Fixed:** the `runs` gate reads
   the size from the measured commit, and D1 lists every place that changes.
9. **LOW: the seed check matched by substring.** **Fixed:** it now matches a whole id.
10. **LOW: `docs --final` did not hold the slowest time or the per-case figure.** **Fixed:** the
    baseline sentence carries both, the per-case figure divides by that shard's own case count, and
    § Testing must state the slowest job.
11. **LOW: the arithmetic left out the controls and ledger.** **Fixed:** § 2.4 now counts them,
    which moved the size from 18 to 15 (65 → 78 shards). Reading A moved from 53 to 50.
12. **LOW: the hang allowance depends on the sibling landing first.** **Stated** in D1 and § 5.
13. **LOW: a cross-process ordering mutant (`key=hash`) survived the rows.** **Fixed:** the order row
    pins the literal sorted order. The mutant was added to § 6.2 and is killed.

After the fold, on the revised prototype:
- `controls` passes with 58 plants (60 after the amendment below);
- the 33-entry sweep kills every mutant;
- `rows`, `untouched`, `workflow`, `docs`, `prepush` and `drive` pass together on the P2 tree;
- `rows 1` and `untouched 1` pass on a P1-cut tree.

### Amendment, 2026-11-09: the maintainer's 15-minute envelope (GOAL Q6)

**The answer.** The maintainer answered rows D1 and D2:
- (B), about 15 cases a shard;
- each job's timeout is 15 minutes;
- the cases' step is capped below that;
- the whole run finishes in under 15 minutes from dispatch, queueing included;
- if the waves push the run past 15 minutes, pick the size that fits and bring the measured run back.

**Before the amendment,** the branch was rebased onto `origin/develop` `146cbc6` with no conflict.
Develop touched none of `tests/mutants.py`, `tests/test_mutations.py`, `AGENTS.md`, `conftest.py` or
the workflows.

**What changed:**
- GOAL: Q6 was recorded, and R1 and R4 were reworded to the 15-minute timeout and the envelope.
- The design: both jobs' timeouts are 15, and the step cap is 12 (§ 2.4).
- The waves were modelled against the organisation's Free-plan 20 jobs, and P3's refit rule was
  added (§ 2.5).
- The gate:
  - pins the timeouts at 15 (`JOB_TIMEOUT`) and the cap at 12 (`STEP_CAP`);
  - checks each run's wall from dispatch against `ENVELOPE = 900`;
  - measures the most jobs a run ran at once, the plan span and the per-shard costs;
  - prints the refit table;
  - puts the run's wall into the baseline sentence and § Testing's check.
- The phases: the two later runs are now one at a time, P4 and P5 (five phases), since two runs
  dispatched together would share the 20 slots and both miss the envelope. Each dispatch waits until
  no other run of the organisation is queued or in progress.

  Three plants were added (the run over the envelope, the run's shape, § Testing without the run's
  wall).
- The dry run also found that the deferral ledger's phrase list matched the plan's own seeding steps.
  "deferral" and "seeded" now count as procedure, not as deferrals.

**Re-checked on a re-made prototype** (the rebased plan head, with the folded files and the
amendment):
- `controls` passes with 60 plants;
- `rows 2`, `untouched 2`, `workflow`, `docs`, `prepush` and `drive` pass together;
- `tests/test_mutant_shards.py`, `tests/test_mutations.py` and `tests/test_hygiene.py` pass.
