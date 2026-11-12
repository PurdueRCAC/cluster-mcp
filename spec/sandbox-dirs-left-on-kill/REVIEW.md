# REVIEW — The suite and the mutation runner leave no sandbox directory behind

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** `94d205d` (the code and docs graded); pinned as `e051738`, which adds only this
  cycle's two out-of-Scope seeds  ·  **Base:** `develop`  ·  **Date:** 2026-11-12
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)
- **Mode:** a fresh blind pass over the full spec-excluded diff (one reviewer, no debate: the diff
  touches no coupled-core path). The sequential fallback did not run.

## Verification run

The orchestrator's gates, at `94d205d`, from the cycle worktree:

- `uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files units kinds guards runner runner-timeout sample rebase cost ledger mutants`
  → exit 0, 0 FAIL, 6:12 wall. `files` 4 ok (R5: `bin/sandbox.sh` byte-identical to `0bfacae`, and
  unchanged from there to the fork point `2719b7a`); `units` 2; `kinds` 14; `guards` 10; `runner`
  11; `runner-timeout` 3; `sample` 1 (R6: 22 sample cases and the three controls print what develop
  printed); `rebase` 1; `ledger` 4; `cost` 1 (the sweep takes 10 ms with no leftover, 209 ms with
  60); `mutants` 27 (all 26 plants killed by their named mode, every planned decision covered).
- `uv run python -I spec/sandbox-dirs-left-on-kill/remediation/runner-signals.py` → exit 0, 15 ok
  (SIGTERM, SIGHUP and SIGINT to the runner leave no sandbox directory), 10 s.
- `suite`: not re-run in review. The P3 build gate ran `fork-base.py files ledger mutants suite`
  green on `bca649e` staged (30:49 wall); `git diff bca649e 94d205d -- . ':(exclude)spec/'` is
  empty, so it covers the reviewed code. All eight suite commands and `verify`'s last passed, each
  left no sandbox directory, and the skipped tests are develop's.

The reviewer's runs:

- The profile's `verify`, once in full, under an isolated `TMPDIR`, with other work on the host:
  `uv lock --check` ok; handshake era 44 / 154 / 507 / 4420 passed + 14 skipped (212 / 144 / 212 /
  208 s); modern era the same counts (213 / 146 / 219 / 210 s); `bin/sandbox.sh uv run cluster-mcp
  --help` ok. The 14 skips are `need_shell`/`need_git` environment skips; the one warning is jwt's
  key-length warning in `test_tokens`. After every suite command, 0 sandbox directories under the
  isolated `TMPDIR` except one in use after command 3 (kept, then removed by its own trap); 0 at
  the end; none new in `/private/tmp`.
- Narrowed: `tests/test_sandbox_dirs.py` 13 passed (1.3 s); an A/B on `tests/test_launch.py -k
  'timeout or kill or stop'` with the fixture disabled leaves 1 sandbox directory, with the branch 0.
- Mutation runner: `--self-check` plus three cases, 0 left; at a patched `LIMIT` the base-like
  cleanup leaves 2 sandbox directories and a run directory, the branch 0; a SIGTERM to the runner,
  base-like 1–2 left, branch 0, both exit 143.
- R3 probe: a pre-existing leftover, another caller's running sandbox, another run's directory with
  a sandbox in it, a leftover in an earlier pytest basetemp, and a near-name directory all survive a
  session unchanged; the sweep found only its own.

The orchestrator's sanity check: F1 re-run from the reviewer's direct probe under a private
`TMPDIR`. `tempfile.TemporaryDirectory` removes a scratch holding a `0o555` or `0` directory;
`mutants.case_scratch` raises `PermissionError: [Errno 13]` on the closed directory and leaves the
scratch. Reproduced.

**CI state (not a finding against this diff).** CI run 43259703879 on the branch head was red on one
hosted-runner timing row, `tests/test_timeout_stop.py::test_a_timed_out_command_is_stopped[delegate-root-ignores-none]`
(0.74 s against a 0.5 s bound). This diff does not touch the timeout stop or that test; the miss is
seeded on `develop` (`302bd10`) as `issues/timing-rows-miss-on-hosted-runners.md`. It is a fact
about the branch's merge-readiness for publish, which reads CI.

**Unavailable check.** No generated diff sweep ran: the repo has no Python mutation tool (none in
`pyproject.toml`, `uv.lock` or the environment), and this review installs nothing. An unclosed gap,
not a pass. The enumeration this cycle stands on is the frozen gate's 26 plants plus the reviewer's
7 hand-planted mutants.

## Requirement → evidence matrix

All six R-IDs were graded by the blind reviewer by execution; none is an artifact deliverable.

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `tests/sandbox_dirs.py` (`own_tmp`, `sweep`), `tests/conftest.py` (`sandbox_tmp`) | Full `verify` under an isolated `TMPDIR`, 0 left; A/B on `test_launch`; gate `kinds` 14 ok; P3 `suite` | ✅ (pin gap F2a) |
| R2 | `tests/mutants.py` (`case_scratch`) | `--self-check` + cases; patched `LIMIT`; SIGTERM; gate `runner`, `runner-timeout`, `runner-signals.py` | ❌ F1 |
| R3 | `tests/sandbox_dirs.py` (`leftovers`, `in_use`) | Reviewer's R3 probe; gate `guards` 10 ok | ✅ |
| R4 | `tests/sandbox_dirs.py` (`in_use`, `own_tmp`), `tests/mutants.py` (`case_scratch`) | `test_the_sweep_keeps_a_running_sandbox…`; a real in-use sandbox kept at session end in `verify`; the runner keeps and names a busy scratch | ✅ (pin gaps F2b, F2c) |
| R5 | unchanged `bin/sandbox.sh` | Blob `9cdc8404` at `0bfacae`, `HEAD` and `origin/develop`; `cmp` with the worktree file; gate `files` | ✅ |
| R6 | — | Both eras pass as above; gate `sample` (22 cases and the controls as on develop); P3 `suite` skip set; three cases killed and three controls held | ❌ F1 (verdicts lost on F1's path) |

Unmapped changes (possible scope creep): none. The two seeds the build filed and their ROADMAP
entries record the GOAL's deferrals and non-goals; `AGENTS.md` describes the new module, fixture,
`case_scratch` and run directory accurately (no drift). A grep of added test lines finds no spec
R/P ids.

## Findings

Severity per the rubric. CONFIRMED: MEDIUM 1, LOW 3. PLAUSIBLE: 0.

### [MEDIUM/CONFIRMED] F1 — a closed directory in a case scratch crashes the mutation runner

- **Where:** `tests/mutants.py:6038` (`case_scratch`, `shutil.rmtree(scratch)`), which replaced the
  base's `tempfile.TemporaryDirectory` (`2719b7a:tests/mutants.py:5986`). That cleanup resets
  permissions and retries; a bare `rmtree` does not. The same bare `rmtree` is in
  `tests/sandbox_dirs.py:100` (`sweep`).
- **Failure scenario:** several suite tests hold a directory at mode `0o555` or `0` until their
  `finally` (`tests/test_ssh_exec.py:720`, `tests/test_site.py:99`, `tests/test_registry.py:858`).
  A case's child stopped inside that window (past `LIMIT`, or by SIGTERM, SIGHUP or Ctrl-C to the
  runner) leaves the closed directory in the scratch. `rmtree` then raises `PermissionError` out of
  `case_scratch`, through `run_case`, into `main`. The stopped case is never reported and later
  cases never run (R6). On the signal path the runner exits 1 instead of dying by its signal, as
  `AGENTS.md` documents. The scratch stays in the runner's `TMPDIR` with any sandbox directory
  `rmtree` had not yet reached (R2).
- **Evidence:** a direct probe on `case_scratch` (re-run by the orchestrator, above). At `LIMIT=6`
  with a planted hanging case, the base cleanup reports `FAILED hang: timeout … stopped` then
  `killed quick`; the branch prints a `PermissionError` traceback, no `quick` line, and leaves a
  `mutant-hang-*` scratch. Under SIGTERM the base exits 143; the branch exits 1 and leaves one
  scratch and one sandbox directory. The `sweep` site, driven directly through `own_tmp`, raises
  `PermissionError` and leaves the run directory and a killed sandbox whose `HOME` holds a closed
  directory. No suite test was seen reaching that state there, so that site is the same property's
  domain, not a separately reproduced finding.
- **Touches:** R2, R6.

### [LOW/CONFIRMED] F2a — nothing pins the sweep of the run's pytest temporary directory

- **Where:** `tests/sandbox_dirs.py:120` (`sweep([run, basetemp])`).
- **Failure scenario:** the hand-planted mutant `sweep([run])` survives `tests/test_sandbox_dirs.py`
  (13 passed). In an emulated session it leaves a real SIGKILLed sandbox directory in the session's
  pytest temporary directory, which R1 names explicitly; the unmutated control leaves 0.
- **Touches:** R1 (its clause "the run's own pytest temporary directories included"). Graded a
  finding, not a coverage observation: it breaks an R-ID's stated check.

### [LOW/CONFIRMED] F2b — nothing pins the keep of a run directory that holds a running sandbox

- **Where:** `tests/sandbox_dirs.py:126` (`own_tmp`'s check of `kept` before removing the run
  directory).
- **Failure scenario:** a mutant that removes the run directory regardless survives. The guard fires
  on real input: in every `verify`, the sandbox of
  `tests/test_launch.py::test_a_local_end_record_split_across_reads_is_found` is still running
  `sleep 8` at the session's end, and the sweep keeps it. With the mutant, its directory would be
  removed while its command runs.
- **Touches:** R4. Graded a finding, not a deeper layer: it is a separate removal path (the run
  directory as a whole) that defeats the in-use keep `sweep` pins, and it is reachable in every
  `verify`.

### [LOW/CONFIRMED] F2c — nothing pins the runner's keep of a case scratch in use

- **Where:** `tests/mutants.py:6028` (`case_scratch`'s in-use check).
- **Failure scenario:** a mutant that ignores the in-use result survives `tests/test_sandbox_dirs.py`
  and `tests/test_mutations.py`. The keep works today: the reviewer's probe and the gate's `runner`
  row both show the scratch kept and named on stderr while a child's sandbox runs.
- **Touches:** R4. Graded as F2b's runner-side sibling, the same separate removal path at the case
  scratch. Its reachability rests on a constructed child (the gate's row and the reviewer's probe),
  not on a real case seen doing it.

### Coverage observation (seeded)

- `tests/sandbox_dirs.py:70`: the listing-failure check (`ps` non-zero or `lsof` empty) made `if
  False:` survives. Defence in depth; it fires only when `lsof` or `ps` fails, which no suite run
  reaches. Seeded as `issues/sandbox-sweep-listing-failure-unpinned.md` with its `ROADMAP.md` entry.

### Out of Scope (seeded)

- Every `verify` leaves two empty `cluster-mcp-run.*` directories, one from each era's third suite
  command. The run directory is kept, correctly, while F2b's `sleep 8` sandbox runs; the sandbox's
  trap removes its own directory seconds later, and nothing revisits the run directory. The GOAL's
  R1–R4 cover sandbox directories, and its clarification keeps a run directory with a sandbox in
  use, so this is new clutter outside the contract, not a defect of it. Seeded as case 3 of
  `issues/sandbox-dirs-outside-repo-runs.md`, with its `ROADMAP.md` entry updated.

### Mutation record

- Gate plants (`verify/mutants.json`): 26 generated, 26 killed by their named mode with their
  message, 0 survived.
- Diff sweep: unavailable (above).
- Tier 2: `case_scratch` wraps all 1165 cases. The gate's `sample` ran 22 cases and the three
  controls as on develop; the reviewer ran 3 cases (all killed) and the three controls (held);
  the rest unrun in review.
- Hand-planted by the reviewer through `run_case`: 7 generated, 3 killed (`env-check-dropped`,
  `mac-env-rows-dropped`, `mac-cwd-rows-dropped`), 4 survived (F2a, F2b, F2c, the coverage
  observation); 0 unviable, timed out or equivalent.

## Routing

To `code build`. Route the properties, both ways, each fix with pins on both sides:

- **Liveness:** the cleanup removes everything of its own run that it can, directories a test left
  closed (`0o555`, `0`) included, and never raises out of `case_scratch` or the sweep; the mutation
  runner still reports every case, the stopped one included, runs every later case, and on a
  signal still dies by that signal.
- **Completeness:** it still never removes or alters a sandbox directory in use, another run's
  directory, a pre-existing leftover, or anything that is not a sandbox directory outside the run's
  own directory; where the process listing fails it still keeps what it found rather than remove
  it; and what it cannot remove it keeps and names, rather than drop silently.
- **Pins:** F2a, F2b and F2c each get a test that fails when its decision is mutated (the sweep of
  the run's pytest temporary directory; the run directory kept while a sandbox in it runs; the case
  scratch kept while in use), with a message naming the contract.

The frozen gate has no closed-directory row; its `mutants` and `kinds` modes could not see F1.

## Human-gate triggers

- Not triggered. No finding touches a path on the high-blast-radius list in `AGENTS.md` §
  Invariants (`bin/sandbox.sh` is unchanged, R5), and none violates a section tagged `[human gate]`.
- **Contract drift, for the maintainer to confirm:** `GOAL.md` changed after its shape commit
  `1189406` in `9ed8715` (GOAL-gate clarifications), `b414c89` (the re-shape, Q4) and `14c33f1`
  (PLAN/TECH-gate readings). This review graded the GOAL as it stands at `94d205d`.

## Landing note

`origin/develop` is one docs commit past the branch's base (`302bd10`, a timing-row seed): Part I
29 entries, gates twelve. The branch has Part I at 31 and gates at fourteen (this cycle's three
seeds), so `ROADMAP.md` will conflict at landing and resolves to 32 entries and fifteen gates.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run (not requested).

## Review cycle 2 — changes-requested (2026-11-12)

- **Reviewed commit:** `dafc608` (the code and docs graded); pinned as `0014491`, which adds only this
  cycle's coverage-observation seed and its `ROADMAP.md` entry  ·  **Base:** `develop`
- **Verdict:** changes-requested; **not routed to build.** A MEDIUM on cycle 2 is non-convergence
  (`code-review` Step 6): it goes to the maintainer.
- **Mode:** a fresh blind pass over the full spec-excluded diff (one reviewer, effort xhigh), told to
  check cycle 1's F1 and F2a–c closed as properties, both ways, and to probe where "never raises"
  meets "keeps what it found on listing failure". The sequential fallback did not run.
- **Evidence:** `.local/review2/` in the cycle worktree (gitignored): `gates/` for the orchestrator's
  runs, `reviewer/` with `probes/` for the reviewer's.

### Verification run

The orchestrator's gates, at `dafc608`, 7:55 wall, all exit 0:

- `SDLK_MUTANTS=spec/sandbox-dirs-left-on-kill/remediation/review1-mutants.json uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py files units kinds guards rebase runner runner-timeout sample ledger mutants`
  → 77 ok, 0 FAIL. `files`: R5 holds (`bin/sandbox.sh` byte-identical to `0bfacae` and to the fork
  point `2719b7a`), and only allowed paths changed. `rebase`: `tests/mutants.py` merges cleanly
  with `origin/develop` in either order. `sample`: 22 cases and the three controls as on develop.
  `ledger`: 3 deferral lines walked. `mutants`: 26 of 26 plants killed by their named mode.
- `remediation/runner-signals.py` → 15 ok (SIGTERM, SIGHUP, SIGINT).
- `remediation/F1-closed-dirs.py` → 30 ok: the runner's limit and signals, the sweep's limit and
  SIGINT, and the macOS `sweep named` row.
- `remediation/F2-pins.py` → 22 generated, 22 killed with their contract message, 0 survived; the
  unmutated control passes all 13 pinning rows.
- `suite`: not re-run in review. The build's record in `TECH.md` (P3) has it green on `33f72ab`
  (26:42 wall). `git diff 33f72ab dafc608 -- . ':(exclude)spec/'` is three lines of prose in
  `issues/sandbox-dirs-outside-repo-runs.md` (Notes), so the record covers the reviewed code.
- After the seed commit `0014491`, `fork-base.py files` fails on one path, the new seed
  `issues/sandbox-reopen-link-in-closed-dir-unpinned.md`: the wrapper's `ALSO_ALLOWED` predates it,
  as it predated cycle 1's seed. The next build widens it.

The reviewer's runs (`reviewer/`):

- The profile's `verify`, once in full, under its own `TMPDIR`: all eight suite commands rc 0
  (213 / 155 / 220 / 251 s legacy, 212 / 145 / 227 / 234 s modern), `--help` rc 0
  (`verify-summary.txt`). No sandbox directory was left in any run directory or in the last three
  basetemps. `/tmp` held 7 sandbox directories before and 7 after. Two empty `cluster-mcp-run.*`
  directories were left, which is case 3 of `issues/sandbox-dirs-outside-repo-runs.md`, as seeded.
  Linux CI run 43293712071 is green in both eras, with no `kept` lines.
- R6: test ids collected per command and era against the merge base `2719b7a`: none removed; the
  only additions are 26 rows in `tests/test_sandbox_dirs.py` (`collect/`). Skips are develop's
  (`conftest.py:102`, bash 4.1).
- The full mutation sweep: 1165 of 1165 cases killed, 3 of 3 `--self-check` controls pass
  (`sweep.out`). Two scratches were kept, each for a sandbox in use, and neither held a free sibling.
- Real runner drives with planted closed directories and killed sandboxes (`runner.log`). At the
  limit, both cases are reported, the second runs, and nothing is left. On SIGTERM, SIGHUP and
  SIGINT the runner ends with rc -15, -1 and -2, and nothing is left.
- The tension probes (`tension.log`, `completeness.log`), described under Cycle 1 closure below.

The orchestrator's sanity check: F-A re-run from the reviewer's `probes/free_beside_busy.py`
(`gates/free-beside-busy.rerun.log`). At the sweep site the free sandbox directory is removed and the
busy one kept. At the case site the free directory still exists at the end of cleanup, with none of
its processes alive, and still exists after the busy command ends; the scratch is kept and named.
Reproduced, matching the reviewer's log.

### Requirement → evidence matrix

All six R-IDs were graded by the blind reviewer by execution; none is an artifact deliverable.

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `tests/sandbox_dirs.py` (`own_tmp`, `sweep`, `reopen`, `remove`), `tests/conftest.py` | Full `verify` under its own `TMPDIR`; CI 43293712071; gate `kinds`, F1 `sweep` rows | ✅ (residual, seeded: a sandbox directory under a mode-`0` directory in the basetemp is not found; `completeness.log` S6) |
| R2 | `tests/mutants.py` (`case_scratch`) | Runner drives; full sweep; gate `runner`, `runner-timeout`, `runner-signals.py`, F1 `runner` rows | ❌ F-A (a free sandbox directory beside a busy one in a kept scratch stays) |
| R3 | `tests/sandbox_dirs.py` (`leftovers`, `in_use`, `_open_tree`) | Probes S1, S5, `link-in-closed-head.log`; gate `guards` | ✅ (pin gap seeded: link inside a closed directory) |
| R4 | `tests/sandbox_dirs.py`, `tests/mutants.py` (`case_scratch`) | S3, S4a, the orphan drive; F2b/F2c pins | ✅ |
| R5 | unchanged `bin/sandbox.sh` | `git diff --quiet 0bfacae -- bin/sandbox.sh`; gate `files` | ✅ |
| R6 | — | Collection diff against `2719b7a`; full sweep 1165/1165 and 3/3 controls; gate `sample` | ✅ |

Unmapped changes (possible scope creep): none in code. The seeds and their `ROADMAP.md` entries
record deferrals; `AGENTS.md` and the `conftest.py` docstring match the code (no drift). A grep of
the new code finds no spec R/P ids.

### Cycle 1 closure

- **F1: closed, both ways.**
  - Liveness: closed directories (`0o555` or `0`, at any depth: in a run directory, in a scratch,
    inside a killed sandbox, holding a sandbox) are removed without raising (`tension.log` S1–S4,
    F1 gate rows). The runner reports every case and runs every later one, and on a signal it dies
    by that signal.
  - Completeness: an in-use sandbox is kept unchanged, including under a closed holder and when its
    command has changed directory. Another run's directory, a pre-existing leftover and closed
    directories outside the run (also reached by links) are untouched, both when the listing fails
    and with the real listing (S1, S5). What cannot be removed is kept and named (S3, S4c).
- **F2a, F2b, F2c: closed.**
  - F2a and F2b are each killed by 4 rows with the contract message.
  - F2c is killed by 2 rows in `tests/test_sandbox_dirs.py`; `tests/test_mutations.py` alone does
    not pin it.
- **The tension.** "Never raises" meets "keeps on listing failure" safely at both sites. The probe
  makes the listing really fail: `bin/sandbox.sh` cannot start because a failing `mktemp` is
  first on `PATH`. In that state every sandbox directory found is kept and named, the run directory
  or scratch is kept, `TMPDIR` is put back, and nothing raises (S1, S2). The listing calls `ps` and
  `lsof` by absolute path, so a failing shim on `PATH` is never consulted (S0). No catch-all turns
  into a silent removal.

### Findings

Severity per the rubric. CONFIRMED: MEDIUM 1, LOW 1. PLAUSIBLE: 0.

#### [MEDIUM/CONFIRMED] F-A — a kept case scratch keeps its free sandbox directories for good

- **Where:** `tests/mutants.py:6026-6041` (`case_scratch`). When any sandbox directory in the scratch
  is in use, the whole scratch is kept, and nothing in it is removed. The suite's `sweep`
  (`tests/sandbox_dirs.py:178-201`) decides per directory: it removes the free ones and keeps only
  the busy ones. One decision, "which of these sandbox directories may go", is computed in two
  places, and the two computations differ.
- **Failure scenario:** a case's child is stopped (past `LIMIT`, by a signal, or by a crash), so its
  own session sweep never runs, and its SIGKILLed sandboxes' directories in the scratch are free.
  If one process survives the stop and still uses one sandbox directory, the runner keeps the
  scratch whole. The free directories stay after the runner ends, and after the busy command ends
  too. R2: "no `cluster-mcp-sandbox.*` directory made by a child run's sandbox … SHALL still exist".
- **Evidence:** `reviewer/probes/free_beside_busy.py` → `free-beside-busy.log`, re-run by the
  orchestrator (above). The real runner's orphan drive (`runner.log`) kept a scratch holding a
  SIGKILLed sandbox directory beside a busy one. In the real full sweep, 2 of 1165 scratches were
  kept and neither held a free sibling: an edge path.
- **Contract reading, for the maintainer:** the GOAL's D3 clarification says a case scratch "is
  removed whole … unless a sandbox directory in it is still in use", which is silent on that
  scratch's free sandbox directories. Graded here by R2's own text: the clarification decides when
  the container goes, and it does not license a free sandbox directory to stay. If the maintainer
  reads the clarification as allowing the keep, the finding drops. Either way it is fix or drop,
  never defer: it cites an R-ID's own wording.
- **Touches:** R2.

#### [LOW/CONFIRMED] F-B — the seed `issues/mutant-case-cleanup-interrupted.md` understates its defect

- **Where:** `issues/mutant-case-cleanup-interrupted.md:8,19,37`, a seed this cycle filed (in the
  graded diff, graded as prose).
- **Failure scenario:** the seed says a *second* signal cuts a case's cleanup short. A *single*
  SIGTERM that lands during the cleanup of a case whose child ended on its own does the same:
  - the runner dies by SIGTERM (rc -15), but the case is never reported;
  - the scratch is left, and nothing names it;
  - the cleanup's own listing sandbox is SIGKILLed by `subprocess.run`, so its directory stays in
    the scratch too (4 sandbox directories left).
- **Evidence:** `reviewer/probes/cleanup_signal.py` → `cleanup-signal.log`.
- **Scope:** the behaviour itself is outside the GOAL (the runner does not run to its end, a known
  limitation). The finding is the seed's misstatement. The fix is the seed's Problem widened to
  its whole domain, not a code change.

### Coverage observations

- **Seeded this cycle:** `open-tree-follows-links-combined` survived `tests/test_sandbox_dirs.py`
  (26 passed). The mutant makes `_open_tree` follow links at both of its guards, `os.stat` and
  `entry.is_dir()`. Driven with a link inside a closed directory in the run directory or a scratch,
  pointing at a closed directory outside, it changes the outside directory from `0o555` to `0o755`
  at both sites; HEAD leaves it alone (`link-in-closed-head.log`, `link-in-closed-mutant.log`).
  - Graded by the rubric's "The sweep is the enumeration": a deeper layer of a class already
    pinned. `reopen-follows-links` and `leftovers-follow-links` are killed, and the pinning rows
    plant their links at the top of the run directory.
  - The input is reachable on no suite path, and it removes nothing (R3 forbids removal).
  - Seeded as `issues/sandbox-reopen-link-in-closed-dir-unpinned.md` with its `ROADMAP.md` entry
    (Part I 32, gates fifteen), in `0014491`.
- **Already seeded (cycle 1):** `processes-guard-removed` and `processes-guard-lsof-only` survive.
  The guard's code is unchanged this cycle, so the cycle does not sweep it.
  `issues/sandbox-sweep-listing-failure-unpinned.md` cites it accurately (`:156`). The reviewer
  showed its consequence on this host: with the guard removed and `bin/sandbox.sh` failing, a
  running sandbox's directory is removed (`guard-consequence-mutant.log` against `-head.log`).
  That input takes a broken host, so this stays a coverage observation; the maintainer may weigh
  it.
- **Residual, already seeded:** a sandbox directory under a mode-`0` directory in the session's
  pytest temporary directory is neither removed nor named (`completeness.log` S6). It is in
  `issues/sandbox-dirs-outside-repo-runs.md` (Notes), and no suite test reaches it.

### Mutation record

- Gate plants: `review1-mutants.json` 26 of 26 killed by their named mode; `F2-pins.py` 22 of 22
  killed with their contract message.
- Tier 2: the reviewer's full sweep, 1165 of 1165 cases killed, 3 of 3 controls.
- Hand-planted by the reviewer, each in a `git archive` copy run under the copy's `bin/sandbox.sh`
  (`mutants.log`, `mutants/`): 32 generated.
  - 27 killed: F2a–c, F1's closed-directory decisions, `reopen` skipped or following links, the
    listing failure read as empty, holder mode not restored, unremovable not named, redirect
    dropped.
  - 2 equivalent: `open-tree-follows-links` and `-both`, each guard masked by the other.
  - 3 survived: the link observation (seeded) and the two listing-guard survivors (seeded in
    cycle 1).
  - 0 unviable.
- Diff sweep: no generated sweep (no Python mutation tool in the repo; nothing installed), as in
  cycle 1. An unclosed gap.

### Not run (reviewer)

- No macOS full-suite baseline on develop (one-suite limit); the collection diff and CI stood in.
- The Linux `/proc` path was exercised only through CI.
- The basetemps of sessions 0–4 were removed by pytest's retention before they could be inspected.
- The runner's limit and signal drives used a probe child, not a real pytest child.

### Routing (to the maintainer: non-convergence, Step 6)

Two CONFIRMED findings on cycle 2, one MEDIUM. Not routed to build: the maintainer decides. If they
send it to build, the properties, both ways, each with a pin:

- **F-A, the decision, structurally first.** "Which of a run's sandbox directories may go" is
  decided in two places (the sweep and `case_scratch`), and the two differ. Decide it once and
  pass the result to both sites, then sweep its mutants under both sites.
  - *Liveness / completeness of removal:* the case cleanup removes every sandbox directory of its
    child that no process is seen using, whether or not another sandbox directory in the same
    scratch is in use, as the sweep does in a run directory.
  - *Safety side:* it still never removes or alters a sandbox directory in use (R4); it keeps and
    names the scratch while anything in it is in use; on a listing failure it removes nothing and
    keeps and names what it found; it never raises.
  - *Pins:* a free sandbox directory beside a busy one in a case scratch is gone at the cleanup's
    end (fails if the scratch-whole keep returns), and the busy one is present and unchanged
    (fails if the per-directory removal overreaches).
- **F-B, the seed's domain.** `issues/mutant-case-cleanup-interrupted.md`'s Problem states the whole
  class: *any* signal that arrives during a case's cleanup, first or second, can cut it short.
  The case then goes unreported, the scratch is left unnamed, and the listing sandbox's directory
  is left. Its `ROADMAP.md` entry follows.
- **The `files` gate:** `remediation/fork-base.py`'s `ALSO_ALLOWED` takes this cycle's seed.

### Human-gate triggers

- Not triggered. No finding touches a path on the high-blast-radius list in `AGENTS.md`
  § Invariants (`bin/sandbox.sh` is unchanged, R5), and none violates a section tagged
  `[human gate]`.
- **Contract drift, still pending the maintainer's confirmation:** `GOAL.md` changed after its
  shape commit `1189406` in `9ed8715`, `b414c89` and `14c33f1`. This review graded the GOAL as it
  stands at `dafc608`.
- **Landing note, updated:** `origin/develop` is still `302bd10` past the base (Part I 29, gates
  twelve). The branch now has Part I at 32 and gates at fifteen, so at landing `ROADMAP.md`
  resolves to 33 entries and sixteen gates.
