---
slug: sandbox-dirs-left-on-kill
title: A sandbox killed with SIGKILL leaves no directory behind
kind: fix
appetite: small
status: in_progress
branch: fix/sandbox-dirs-left-on-kill
base: develop
current_phase: P1
last_updated: '2026-11-09'
phases:
- id: P1
  name: The keeper removes a killed sandbox's directory, and nothing else changes
  status: pending
  satisfies:
  - R1
  - R3
  - R4
  - R5
  - R6
  - R7
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/verify/keeper.py kill race exit share decoys same && SDLK_SH=/bin/dash uv run python -I spec/sandbox-dirs-left-on-kill/verify/keeper.py kill race exit share decoys same && uv run python -I spec/sandbox-dirs-left-on-kill/verify/keeper.py controls rows suite
- id: P2
  name: No directory left by the mutation runner or the whole gate, and the ledger
  status: pending
  satisfies:
  - R2
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run python -I spec/sandbox-dirs-left-on-kill/verify/keeper.py files ledger mutants verify
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — A sandbox killed with SIGKILL leaves no directory behind

The **context engine and finite-state machine** for building this cycle. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/sandbox-dirs-left-on-kill/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md) (§ 2 the design, § 3 the deviations and the
  maintainer's figures, § 6 the gate's modes and the mutant list).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.
- **The frozen gate:** [`verify/keeper.py`](verify/keeper.py), one mode per requirement (its
  docstring lists them). Never edit it to make a phase pass: a gate that is wrong is a stop and a
  question for the foreman. Its `BOUND` changes only with the maintainer's ruling on PLAN § 3 D1,
  together with the test module's.

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
  § Factory → Throwaway environment and the script's own header change with the script, in P1.
- Export `UV_PYTHON=3.14` before every `verify:` on this host. Stage before running a `verify:`: the
  gate installs `bin/sandbox.sh` from the index and reads `files` from it. A gate near or over the
  Bash tool's 10-minute cap (P2's, about 30 minutes) runs through `run_in_background`; never a
  disowned launch.
- `bin/sandbox.sh` is a high-blast-radius path: a CONFIRMED review finding in it needs the
  maintainer's sign-off before landing. Only `bin/sandbox.sh`, `AGENTS.md` (the Throwaway environment
  section), the new `tests/test_sandbox_keeper.py` and this cycle's `spec/` change (the `files` mode).
  `tests/mutants.py` and `tests/test_hygiene.py` are not edited (sibling cycles own them). No phase
  waits on a hosted CI run or a workflow dispatch.

---

## Phase P1 — The keeper removes a killed sandbox's directory, and nothing else changes
**Satisfies:** R1, R3, R4, R5, R6, R7 · **Depends on:** —
**Goal:** a sandbox whose wrapper is SIGKILLed, alone or with its group, frozen or not, leaves no
directory once the wrapper and its command have both ended; every exit path that removed it on
develop still removes it before the wrapper exits; nothing else of the wrapper is observably
different, in bash-as-sh and in dash.

- [ ] `bin/sandbox.sh`, as PLAN § 2 specifies (the planner's prototype,
      [`research/04-prototype.sh`](research/04-prototype.sh), passed every process mode), in order: the variable read and unset first, the
      re-run under perl when a perl is found and the template is absolute and one line (perl's
      variables neutral and put back; the starter, the middle child, the keeper,
      perl builtins only, every fallback to develop's path; a handle opened with `my` is tested
      with `if (open(my $h, …))`, never `open(my $h, …) and …`, which acts on a global; the keeper's
      clean re-exec), the second run's `ready`/`go` exchange and read of the directory (`IFS= read
      -r`, retried on an interrupted `read`), the inline `EXIT` trap with its `now` line while
      `running`, `trap : HUP INT TERM`, the perl shim for a command `command -v` finds as a file
      (its `/bin/sh -c '"$@"'` fallback when `exec` fails), the reporting subshell for any other
      builtin, `exec` as on develop, and `status=0; running=yes`, the command, `|| status=$?;
      running=; exit "$status"`. Develop's environment,
      unset and `cd` lines stay byte-identical (the four `test_hygiene` anchors each exactly once).
      The poll is 5 ms doubling to 0.1 s (PLAN § 3 D1; the figure stands until the maintainer rules).
- [ ] The script's header: the keeper paragraph in place of "removed on exit (any path)" (PLAN § 2,
      the contract text). `AGENTS.md` § Factory → Throwaway environment: the "removed by a trap"
      sentence as PLAN § 2 words it, naming `tests/test_sandbox_keeper.py` as the pin.
- [ ] `tests/test_sandbox_keeper.py`: `BOUND = 2.0`, `keeper_violations`, the `integration` rows and
      the `unit` controls PLAN § 2 lists, with exactly the ids the gate's `ROWS` freezes and at least
      four planted records under `test_keeper_violations_rejects`. Every launch is
      `[str(SANDBOX), …]`, `ps` included; `TMPDIR` under `tmp_path`; every process it starts carries
      a marker in its argv and its teardown kills each one; no R/P/Q/F ids.
- [ ] Mutant pass (code-build Step 4): plant each mutant of PLAN § 6's table into a scratch copy of
      the staged script, run the mode it names in both shells; each must go red (`EXIT` without
      `now` goes red under bash-as-sh only, since dash never runs the trap on an untrapped signal). Record the table (mutant, shell, first failing line, or survivor and why) in the
      commit body.
- [ ] Measure, and put in the commit body: the per-start median of `bin/sandbox.sh true` and
      `bin/sandbox.sh sh -c 'exit 0'`, develop's script against the tree's, in bash-as-sh and dash
      (30 runs, three rounds); and the new module's time in each era (`pytest --durations=0`).
      PLAN § 3 D2 and D6 hold the planner's figures until then.
- **Verify:** the frontmatter `verify:`: the process modes as is and under dash (R1, R3–R7; about
  80–100 s each on the planner's host), then `controls` (develop's wrapper fails `kill` and `race`),
  `rows` (the new module, its controls, and the rows that pin the wrapper today) and `suite` (R2's
  pytest slice, about 15 s): about 5 minutes in all.
- **Touches:** `bin/sandbox.sh`, `AGENTS.md`, `tests/test_sandbox_keeper.py`.

## Phase P2 — No directory left by the mutation runner or the whole gate, and the ledger
**Satisfies:** R2 (and R1, R3–R7 on the final tree, through the whole suite in both eras) ·
**Depends on:** P1
**Goal:** `tests/mutants.py` over a case, within its limit and past a patched one, and the profile's
whole `verify` each leave no `cluster-mcp-sandbox.*` directory in the `TMPDIR` they ran under; the
cycle's changes stay in its paths; the ledger is clean.

- [ ] The ledger (`code-plan` Step 6.8): walk P1's and P2's bodies, PLAN.md and the branch's commit
      bodies for deferral phrases; each names an `issues/` seed with a `ROADMAP.md` entry (the
      `ledger` mode checks it). This plan files no new seed: a command's processes that leave its
      group are [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md),
      already seeded and indexed.
- [ ] Put the full `verify` wall time before and after into PLAN § 5 (D2), naming the runs: the
      planner's prototype run and develop's (2026-11-09, the plan's report), and this phase's `verify`
      mode, which prints `verify: exit N in S s`. Put P1's measured per-start and module figures into
      D2 and D6.
- [ ] Stage, then run the frontmatter `verify:` through `run_in_background`: `files`, `ledger`,
      `mutants` (one case within its limit and past a patched 1 s limit), then `verify` (the
      profile's whole `verify`, both eras, under a fresh `TMPDIR`, then the leftover check).
- **Verify:** the frontmatter `verify:`.
- **Touches:** `spec/sandbox-dirs-left-on-kill/PLAN.md`, `spec/sandbox-dirs-left-on-kill/TECH.md`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
