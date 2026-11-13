---
slug: rcac-extra-brings-slurm
title: cluster-mcp[rcac] alone brings the Slurm tools
kind: fix
appetite: small
status: in_progress
branch: fix/rcac-extra-brings-slurm
base: develop
current_phase: P2
last_updated: '2026-11-13'
phases:
- id: P1
  name: The rcac extra installs the Slurm member, pinned, with every install line
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/rcac-extra-brings-slurm/verify/gate.sh p1
- id: P2
  name: The rcac set read as the RCAC member alone; ROADMAP and seed record the rule
  status: pending
  satisfies:
  - R4
  - R7
  depends_on:
  - P1
  parallel: true
  hammerable: false
  hill: uphill
  verify: sh spec/rcac-extra-brings-slurm/verify/gate.sh p2
review:
  last_reviewed_commit: ''
  verdict: none
  blocked_reason: ''
  cycle: 0
---

# TECH.md — cluster-mcp[rcac] alone brings the Slurm tools

The **context engine and finite-state machine** for building this fix. The YAML frontmatter above
is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/rcac-extra-brings-slurm/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs
its `verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state
commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** none (lean path).

## Frontmatter field reference

As in the KB template (`$KB/skill/_templates/TECH.md`): top `status`
`planned | in_progress | blocked | in_review | done`; phase `status` `pending | in_progress | done |
blocked`; `satisfies` the GOAL R-IDs; `depends_on`; `parallel`; `hammerable`; `hill`; `attempts`
(the circuit breaker's counter); `verify`; `review.cycle`.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8).
  The previous cycle's last phase carried no other project-level item.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.
- **Every gate stages first.** Each `gate.sh` mode refuses unstaged changes, reads the index against
  `BASE=${GATE_BASE:-$(git merge-base HEAD origin/develop)}` and checks
  `tests/fixtures/served_surface.json` is `2e0dc91f…6561`, the base's bytes, at every step. After
  landing, re-run a gate with `GATE_BASE=916cecf`.
- **The full verify** is `sh spec/rcac-extra-brings-slurm/verify/gate.sh full`: the profile's whole
  `verify`, read from `AGENTS.md`, with the fixture checked before and after. The foreman schedules
  it before publish; no phase's `verify:` runs it.

---

## Phase P1 — The rcac extra installs the Slurm member, pinned, with every install line
**Satisfies:** R1, R2, R3, R5, R6 · **Depends on:** —
**Goal:** `cluster-mcp[rcac]` installs the core, the RCAC member and the Slurm member and serves what
`[slurm,rcac]` serves; every other install form is unchanged; the suite pins the rule in the
declarations and the installed metadata; every text that states an RCAC install line or the old
one-member rule says `[rcac]` alone, in the same commit.

- [x] `packages/cluster-mcp/pyproject.toml`: `rcac = ["cluster-mcp-rcac", "cluster-mcp-slurm"]`; the
      comment above the table states the rule (a center's extra installs every extra its center's
      clusters need). No other `pyproject.toml` changes.
- [x] `uv lock`, then `uv lock --check`; the lock's diff is the two lines PLAN § 2 names. `uv sync
      --locked` before the gate, so the installed metadata is the new one.
- [x] `tests/test_packaging.py` (the prototype's text, PLAN § 2): `EXTRAS` as each extra's members; `CAPABILITY_MEMBERS`;
      `installed_extras`; `extra_violations`; `test_core_declares_the_capability_extras` asserts the
      check on the declarations and on the installed metadata; the planted controls in
      `test_extra_check_names_the_extra_that_breaks_the_rule`; the module docstring states the rule;
      `test_compat_root_installs_every_capability` iterates the members.
- [x] The install lines and restatements PLAN § 2 lists, in `README.md`,
      `packages/cluster-mcp/README.md`, `packages/cluster-mcp-rcac/README.md`,
      `docs/core/README.md`, `docs/rcac/README.md` and `AGENTS.md` (opening, Direction, Repository
      map, § Testing's `test_packaging` entry, § Packaging, the release recipe's `post_verify` README
      line and its `ci-mirror-no-index` and `install-probe` caveats). The recipe's YAML still parses.
      `SECURITY.md` and every compat-root line keep their text.
- [x] Stage by path, then run the gate.
- **Verify:** `sh spec/rcac-extra-brings-slurm/verify/gate.sh p1` (73 s on the prototype, warm uv
  cache): `files`, the lock, the install lines, the packaging/surface/core-only/deprecation-window
  tests, the install-level check from the index against the base (R1–R3), the extras mutants (R5).
- **Touches:** `packages/cluster-mcp/pyproject.toml`, `uv.lock`, `tests/test_packaging.py`,
  `README.md`, `packages/cluster-mcp/README.md`, `packages/cluster-mcp-rcac/README.md`,
  `docs/core/README.md`, `docs/rcac/README.md`, `AGENTS.md`.

## Phase P2 — The rcac set read as the RCAC member alone; ROADMAP and seed record the rule
**Satisfies:** R4, R7 · **Depends on:** P1
**Goal:** the tests and docs that name the fixture's `rcac` set read it as the RCAC member registered
alone; `ROADMAP.md`'s two entries and `issues/site-extras.md` state the rule, its citation and its
release, by added lines only. R7 is met by committed documents: the orchestrator grades it from the
ROADMAP and the seed, and this phase's `roadmap` check is their content gate.

- [ ] `tests/test_capabilities.py`: the `SETS` comment says `rcac` is the RCAC member registered
      alone, the state the startup probe leaves on a cluster without Slurm's client commands, and no
      install.
- [ ] `tests/test_surface.py`: the module docstring says the same of the `rcac` set.
- [ ] `AGENTS.md` § Testing, the `tests/test_surface.py` entry: the same, beside the list of sets.
- [ ] `ROADMAP.md`: one paragraph in the site-interfaces entry and one in the `[rcac]` entry, each
      before its `*Horizon:*` line: the rule in the GOAL's words, "maintainer decision, 2026-11-12",
      and `[rcac]` brings `[slurm]` from 0.2.2. No other line of either entry changes.
- [ ] `issues/site-extras.md`: a dated note appended under Notes, saying the same and what of its
      R1 and R7 remains. `status:` stays `unshaped`.
- [ ] The ledger: walk P1's and P2's bodies for postponed-work phrases (`text_checks.py ledger`
      reads them); each names an `issues/` seed and its ROADMAP entry. None is expected.
- [ ] Stage by path, then run the gate.
- **Verify:** `sh spec/rcac-extra-brings-slurm/verify/gate.sh p2` (18 s on the prototype): `files`, the
  `rcac` set's reading, the ROADMAP and seed, the ledger, then `tests/test_capabilities.py`,
  `tests/test_surface.py` and `tests/test_hygiene.py` (spec ids in the new comments).
- **Touches:** `tests/test_capabilities.py`, `tests/test_surface.py`, `AGENTS.md`, `ROADMAP.md`,
  `issues/site-extras.md`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
