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
