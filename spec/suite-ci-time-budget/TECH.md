---
slug: suite-ci-time-budget
title: Each CI era job keeps a margin under its timeout, and every row keeps its proof
kind: test
appetite: small
status: in_review
branch: test/suite-ci-time-budget
base: develop
current_phase: done
last_updated: '2026-11-06'
phases:
- id: P1
  name: Each era's suite as four commands, one CI job each, mirrored in verify and the release gate
  status: done
  satisfies:
  - R2
  - R3
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/remediation/untouched-testing-list.py controls && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py mirror && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/remediation/untouched-testing-list.py && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py partition legacy && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py partition modern && UV_PYTHON=3.14 uv run pytest -q tests/test_suite_parts.py tests/test_hygiene.py && CLUSTER_MCP_TEST_ERA=modern UV_PYTHON=3.14 uv run pytest -q tests/test_suite_parts.py tests/test_hygiene.py && UV_PYTHON=3.14 uv run -q python -I spec/suite-ci-time-budget/remediation/F1-testing-list.py --controls && UV_PYTHON=3.14 uv run -q python -I spec/suite-ci-time-budget/remediation/F1-testing-list.py
- id: P2
  name: Every process-wide fixture in force under each command, and each command green alone
  status: done
  satisfies:
  - R4
  - R2
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py fixtures legacy && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py fixtures modern && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py fixtures-control legacy && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard legacy 1 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard legacy 2 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard legacy 3 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard legacy 4 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard modern 1 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard modern 2 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard modern 3 && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py shard modern 4
- id: P3
  name: Three measured CI runs, the budget's baseline row, and the ledger (Run A, then Run B)
  status: done
  satisfies:
  - R1
  - R5
  - R7
  - R2
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py prepush && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py mirror && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py untouched && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py partition legacy && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py partition modern && UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py ci --runs-file spec/suite-ci-time-budget/ci-runs.txt --check-baseline
review:
  last_reviewed_commit: dd4c5f2b909f2511642cef33b8a0f3be3625c2a5
  verdict: approved
  blocked_reason: ''
  cycle: 2
---

# TECH.md — Each CI era job keeps a margin under its timeout, and every row keeps its proof

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/suite-ci-time-budget/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **The frozen gate:** [`verify/suite-gate.py`](verify/suite-gate.py), one mode per requirement
  (its docstring lists them). Never edit it to make a phase pass: a gate that is wrong is a stop and
  a question for the foreman.

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
  cycle (`ssh-half-open-link`) carried the ledger and its sweep; the ledger is the one that applies.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**. Here that is "CI
  mirrors the gate": the profile's `verify`, the release recipe's `gate` and `ci.yml` change in one
  commit (the `mirror` mode checks every commit since the base).
- Run every suite command with `UV_PYTHON=3.14` on this host. A gate mode near or over the Bash
  tool's 10-minute cap runs through `run_in_background`; never a disowned launch.
- Nothing under `packages/`, no existing module under `tests/`, `tests/conftest.py`, `pyproject.toml`,
  `uv.lock` or `bin/` changes in this cycle (the `untouched` mode). A phase that finds it must change
  one stops and asks: R3's planted-break obligations then apply, and the plan did not budget them.

---

## Phase P1 — Each era's suite as four commands, one CI job each, mirrored
**Satisfies:** R2, R3, R6 · **Depends on:** —
**Goal:** CI runs each era's suite as the four commands PLAN § 2.1 names, each in a job of its own,
and the profile's `verify` and the release recipe's `gate` run the same eight commands verbatim, in
the same order; the documents describe the nine jobs; a new suite row pins the commands' shape.

- [x] `.github/workflows/ci.yml`: replace `suite-legacy` and `suite-modern` with `suite-legacy-1` …
      `suite-legacy-4` and `suite-modern-1` … `suite-modern-4`, each the old suite job (same
      `runs-on`, `timeout-minutes: 20`, checkout, setup-uv, provisioning step and `uv sync --locked`)
      with its one pytest step replaced by one command of PLAN § 2.1, the handshake era's four first;
      names `suite (handshake era, N of 4)` and `suite (modern era, N of 4)`; `gate` needs all eight,
      in that order, and is otherwise unchanged. No matrix, no `${{ }}`, no `env:`. Rewrite the
      header comment to describe the nine jobs.
- [x] `AGENTS.md` § Factory: the `verify` cell's two suite commands become the eight, in order,
      verbatim, and its prose says each era runs as four commands that together run every test
      once; the release recipe's `gate` list the same; the `ci` row describes the nine jobs (the
      word "nine", every suite job id or the `suite-legacy-1` to `suite-legacy-4` range form, and
      `gate`, which needs all eight); a new `ci budget` row, after `ci`, states R1's budget and
      measure as PLAN § 2.4 words it, with `Baseline …: pending` (P3 fills it).
- [x] `AGENTS.md` § Conventions, "CI mirrors the gate": replace the two-job sentence with the four
      commands per era, how they partition the suite (the `-k` pair, the named modules, the
      `--ignore` complement, a new module runs in the last), the eight jobs, the `ci budget` row, and
      `tests/test_suite_parts.py`. Keep "one step per command, verbatim" and the rest of the bullet.
      § Testing's "The protocol era" bullet: the two commands become "each era as four commands".
      Leave every other line of `AGENTS.md` alone (the suite reads §§ 2, 3, the footguns and the id
      rule; the `untouched` mode compares everything outside the four regions, and every profile
      row but `verify`, `ci` and `ci budget`, the `ci` row's landing rule, and the recipe but its
      `gate`). Wrap prose at the file's width; the prototype left two long lines.
- [x] `tests/test_suite_parts.py` (new, `unit`): the pure check `suite_part_violations` (PLAN § 2.3)
      over the `verify` cell's suite commands, a test that the gate list and the workflow run the
      same commands in order, and planted controls for each refusal (PLAN § 2.3: the `-k` pair must
      be `E` and `not (E)`, or `E` and `not E` for a single word; no `-k` on the last command). It
      imports only `re`, `shlex`, `pathlib`, `pytest` and `__future__`, and binds names at import
      and nothing else (the `untouched` mode checks both: a module that patched a helper at import
      would touch every row of part 4). No spec id in it.
- [x] Run the new module and `tests/test_hygiene.py` (its static checks read every test module).
- **Verify:** the frontmatter `verify:` (`controls`, `mirror`, `untouched`, `partition` in each era,
  then the two modules). `partition` took 14 s per era on the prototype (PLAN § 6.3).
- **Touches:** `.github/workflows/ci.yml`, `AGENTS.md`, `tests/test_suite_parts.py`.

**Amendment, review cycle 1 remediation (2026-11-06).** The review's one finding (MEDIUM): § Testing's
per-module list, whose check names and test ids it calls a contract, has no bullet for
`tests/test_suite_parts.py`. P1 wrote that module, so P1 is reopened; routed as its class, the list
names every test module, each with its markers and every public `*_violations` it defines, and no
name in it has gone stale. The review's ruling widens P1's "leave every other line of `AGENTS.md`
alone" by exactly that list. Documentation only: no test row, test file, conftest, workflow or suite
command changes, so each CI job runs the suite measured on `ef301e6` (GOAL Q5).

- [x] `AGENTS.md` § Testing: a bullet for `tests/test_suite_parts.py` (`unit`), last, after the
      other repository-tooling modules, naming `suite_part_violations`, `list_violations` and the
      three list readers, and pointing at § Conventions for the shapes the part check refuses rather
      than restating them.
- [x] The sweep (`remediation/F1-testing-list.py`, the class predicate over the staged text) found
      the base's list short of 30 more items, now named in their bullets: three markers, those of
      `tests/test_cli.py` (`unit`, `integration`) and the `unit` controls of `tests/test_ssh_smoke.py`;
      and 27 public checks (`test_audit` `refusal_violations`; `test_cli` `window_violations`,
      `naming_violations`; `test_deprecation_window` `table_line_violations`, `version_violations`;
      `test_executors` `held_violations`, `writer_violations`; `test_hygiene` `spec_id_violations`,
      `skip_violations`, `sandbox_unset_violations`; `test_literal_args` `refusal_violations`,
      `content_violations`, `error_violations`; `test_no_executor` `other_request_violations`;
      `test_probe_startup` `surface_violations`; `test_sbatch` `shared_violations`; `test_site`
      `budget_violations`, `line_violations`, `alike_violations`; `test_ssh_exec`
      `not_run_violations`, `lost_write_violations`; `test_startup` `refused_start_violations`;
      `test_storage_resource` `tool_refusal_violations`, `shape_violations`, `not_found_violations`;
      `test_timeout_stop` `return_violations`, `gone_violations`). Underscore-prefixed helpers are
      private to their module and stay unnamed. No stale name: every backticked `*_violations` a
      bullet names is defined where it says, and every other backticked identifier occurs in tracked
      code. The checker was red on `f44b482` (31 lines) and is green on the fix; its controls plant
      each refusal.
- [x] `verify:` retuned with `set_phase.py --verify-file`: `controls` and `untouched` under
      `remediation/untouched-testing-list.py`, `mirror`, `partition` in each era, the two modules in
      each era, then the class checker's controls and the checker. The frozen `untouched` mode is
      red on this fix by construction ("AGENTS.md changes outside the profile, the recipe, the CI
      bullet and the era bullet"), and was run and seen red on the staged fix first; so is the
      frozen `controls` mode's "untouched sound" case, which feeds the staged AGENTS.md to the same
      check. The first retuned gate ran `controls` unwrapped, went red on that case alone (every
      other control `ok`), and is the one attempt recorded; the gate was retuned to wrap it and
      every step re-run. The wrapper loads `verify/suite-gate.py` unedited and adds the per-module
      list as a fifth region, bounded from the list's first sub-bullet to the next top-level bullet
      and required once in the base's text and the staged one; a line planted above the list and
      one in the next bullet each turn its `untouched` red.
- Not in this gate, by the foreman's brief: `ci --check-baseline`, which is defined over `T1` to
  `T2` and would read this commit as outside that set, and `head`, which needs this head's push run.
  P2's `fixtures` and `shard` modes are not re-run: they read the suite commands, conftest and test
  modules, none of which this commit changes.
- **Verify:** the frontmatter `verify:`, as retuned.

## Phase P2 — Every process-wide fixture in force under each command, and each command green alone
**Satisfies:** R4, R2 · **Depends on:** P1
**Goal:** under each of the eight commands, a planted violation of each session-scoped or autouse
fixture of `tests/conftest.py` and of its collection hook fails for the same reason as under the
base's one command per era (R4); and each command, run alone as its CI job runs it, is green (the
runtime half of R2 locally: no row depends on a module another command now runs).

- [x] Run the frontmatter `verify:`. It changes nothing in the tree. On the prototype the `fixtures`
      modes took about 35 s each, `fixtures-control` 45 s, and the `shard` modes 150–220 s each,
      about 25 minutes in all (PLAN § 6.3): run it through `run_in_background`.
- [x] If a `shard` mode is red on a row that passes in the whole-era run, the row depends on another
      module's import or state: stop and ask (the fix touches a row, which R3 governs).
- [x] If a `shard` mode is red on a row of the class `issues/stalled-reconnect-test-timing.md` names,
      re-run that mode once; a second red is a stop. Record the sighting in that seed either way.
- [x] Record each command's wall time and its first rows' times (the `shard` lines) in the commit
      body, naming this run.
- **Verify:** the frontmatter `verify:`.
- **Touches:** `spec/suite-ci-time-budget/TECH.md` (state), and `issues/stalled-reconnect-test-timing.md`
  only for a sighting.

## Phase P3 — Three measured CI runs, the budget's baseline row, and the ledger
**Satisfies:** R1, R5, R7, R2 (CI's counts) · **Depends on:** P2
**Goal:** the branch's final suite and workflow, measured on CI over at least three runs, keep every
suite job within 10 minutes, every job green; the `ci budget` row carries the baseline. This phase
waits on CI, so it is dispatched as two runs (the foreman's "external waits split the run").

**Run A (ends ready to push; the builder never pushes):**
- [x] The ledger (`code-plan` Step 6.8): walk P1–P3's bodies and the branch's commit bodies for the
      phrases the `prepush` mode lists; each such item names an `issues/` seed with a `ROADMAP.md`
      entry (the `prepush` mode checks it). This plan files no new seed.
- [x] Run the frontmatter `verify:` up to, not including, the `ci` mode: `prepush` (no working-copy
      change outside the index, no site-private text in the cycle's added lines, the ledger over
      TECH, PLAN and commit bodies), `mirror`, `untouched` and `partition` in each era, so the
      measured commit is the tree P1 and P2 proved.
- [x] Commit the TECH state (P3 `in_progress`, a note "Run A done: ready to push") and stop. Hand
      back the head commit: it is the measured commit `T1`.
- Run A done: ready to push. Its head is the measured commit `T1`.
- The foreman pushes `T1`, waits for its push run, then triggers full re-runs (`gh run rerun <id>`,
  never `--failed`: a partial re-run copies the jobs it skips and is refused) until at least three
  attempts have completed, and hands back the run id and every attempt. Every attempt of every push
  run of `T1` goes into `ci-runs.txt`, counted or replaced: the `ci` mode refuses one left out. A
  run that fails on one row of one suite job, of the load-sensitive class, is handled per R5
  (record, replace once); whether the row is of that class is the foreman's call, by the seed.

**Run B:**
- [x] Write `spec/suite-ci-time-budget/ci-runs.txt`: `sha <T1 full>`, one `run <id>:<attempt>` per
      counted attempt, and `replaced <id>:<attempt>` for a replaced one (at most one), whose dated
      sighting goes into `issues/stalled-reconnect-test-timing.md` in this commit, naming the run id,
      the era (`handshake` or `modern`) and the row's test name.
- [x] Run `suite-gate.py ci --runs-file spec/suite-ci-time-budget/ci-runs.txt` without
      `--check-baseline` first; it prints the baseline sentence. Put it in the `ci budget` row in
      place of `Baseline …: pending`, changing nothing else in `AGENTS.md`.
- [x] Stage, run the frontmatter `verify:`, mark P3 done and commit. The new head `T2` differs from
      `T1` only in that row, `ci-runs.txt`, TECH state and a seed sighting (PLAN § 3, deviation 2).
- Before landing (publish, after the foreman pushes `T2` and its push run ends): run
  `suite-gate.py head`. It reads every push run of `T2` (green, every suite job within 600 s) and
  refuses if `origin/develop` has moved past the base `5f6e984`; then the landed tree is the
  measured one. If develop has moved, stop: the cycle re-measures on the rebased tree.
- If a counted job goes over 600 s, or a run is red outside R5's one exception: stop and report the
  run, the job and its time. Do not rebalance and re-measure inside this phase without the foreman.
- **Verify:** the frontmatter `verify:` (Run B). Run A runs only its first two modes.
- **Touches:** `AGENTS.md` (the `ci budget` row), `spec/suite-ci-time-budget/ci-runs.txt`,
  `issues/stalled-reconnect-test-timing.md` (a sighting, only if a run was replaced).

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[test]` commit; stop and report.
