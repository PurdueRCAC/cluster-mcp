# REVIEW — cluster-mcp[rcac] alone brings the Slurm tools

> Adversarial QA by `code-review`, run in an isolated context: a fresh blind reviewer subagent. The
> correctness pass grades the branch diff against [`GOAL.md`](GOAL.md) and the repo's `AGENTS.md`
> § Invariants **only**; it does not see `PLAN.md`/`TECH.md`. Every finding cites an **executed**
> command, not an assertion.

- **Reviewed commit:** `ed9c166` (the blind pass) · remediated at `38871fc` (the verdict's commit) ·
  **Base:** `develop` at the merge base `916cecf` · **Date:** 2026-11-13
- **Verdict:** approved
- **Cycle:** 1 of ≤3, mirrors `review.cycle` in `TECH.md`
- **Mode:** a fresh blind pass over the full spec-excluded diff; one reviewer (the diff touches no
  path of the profile's coupled core, so no debate). The sequential fallback did not run.

Evidence lives in the worktree's gitignored `.local/review1/`: `reviewer/` (the blind pass; its
`NOTES.txt` indexes it) and `orchestrator/` (the gates and the install-line check's mutants).

## Verification run

- The profile's `verify`, once, by the reviewer at `ed9c166` → exit 0; both protocol eras, every
  suite command green (44 + 154 + 507 + 4396 passed, 14 skipped, none related) and the
  `bin/sandbox.sh uv run cluster-mcp --help` drive (`reviewer/verify.log`).
- The phase gates, by the orchestrator: `gate.sh p1` and `gate.sh p2` at `ed9c166` → exit 0
  (`orchestrator/gate-p1.log`, `gate-p2.log`); again on the remediation → exit 0
  (`orchestrator/gate-p1-fix.log`, `gate-p2-fix.log`). Each checks the fixture's bytes at every step.
- Installs driven under `bin/sandbox.sh` (reviewer): `uvx --from 'cluster-mcp[rcac] @ git+file://…@ed9c166#subdirectory=packages/cluster-mcp'`
  and every other install form (`[slurm,rcac]`, `[rcac,slurm]`, the compat root `rcac-mcp`,
  `uv sync --locked`, `[slurm]`, the bare core), each built from `916cecf` and from `ed9c166`; each
  server started with `cluster-mcp -e local` and read over stdio in both eras
  (`reviewer/drive_installs.log`, `drive_uvsync.log`, `compare.log`, `dists/`).
- The startup probe driven on stub PATHs (reviewer): Slurm's commands only → `Capability
  cluster-mcp-rcac withheld: the cluster is missing findscratch, myquota`, 14 Slurm tools served;
  `findscratch` and `myquota` only → the Slurm member withheld, 17 tools, identical to the base
  `[rcac]` install (`reviewer/probe_drive.log`, `surfaces/probe-head-rcac-slurm-only.*`).
- The repository's mutation runner, its 38 README cases with `--self-check`, because the diff
  touches `README.md` → 38 killed (`reviewer/mutants_readme_cases.log`).
- Fixture `tests/fixtures/served_surface.json`: sha256
  `2e0dc91fef3cfae3a04358178486e7dbef2faf0989c89e39ccce7399595d6561` at `916cecf`, at `ed9c166` and
  after the remediation; `git diff --name-only 916cecf HEAD -- tests/fixtures/` empty
  (`reviewer/fixture_sha.txt`, every gate log).

## Requirement → evidence matrix

Every R-ID is graded by the blind reviewer; none is an artifact deliverable under `spec/`. The
install-line check's mutation (R6's cycle gate, under `spec/`) is graded by the orchestrator, below.

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `packages/cluster-mcp/pyproject.toml` `rcac` extra, `uv.lock` (`c3d31b9`) | sandboxed `[rcac]` git-form install from `ed9c166`: core + RCAC + Slurm members, built metadata `cluster-mcp-slurm; extra == 'rcac'`; served surface identical to `[slurm,rcac]` at HEAD and base, both eras; under the lock's versions equal to the fixture's `both`/`both-reversed` (`reviewer/compare.log`, `compare_fixture_both.log`, `built_metadata.txt`) | ✅ (reviewer) |
| R2 | unchanged root and `[slurm,rcac]` paths | each form installed from base and HEAD; whole raw surfaces identical, both eras (`reviewer/compare.log`, `drive_uvsync.log`) | ✅ (reviewer) |
| R3 | `slurm` extra unchanged | `[slurm]` installs core + Slurm, bare core installs core only, as on base; surfaces identical (`reviewer/dists/head-slurm.txt`, `head-bare.txt`) | ✅ (reviewer) |
| R4 | `tests/test_capabilities.py`, `tests/test_surface.py`, `AGENTS.md` wording; fixture untouched | fixture sha256 unchanged; the probe reaches the RCAC-alone state, identical to the base `[rcac]` surface; locked-env tools/resources/capabilities equal the fixture's `rcac` entries; the `rcac` set described as "the RCAC member registered alone" (`reviewer/probe_drive.log`, `compare_fixture_locked.log`, `r4_rcac_set_grep.txt`) | ✅ (reviewer) |
| R5 | `tests/test_packaging.py` (`test_core_declares_the_capability_extras`, `test_extra_check_names_the_extra_that_breaks_the_rule`) | 13 hand-planted mutants over the declarations, the installed metadata and the helpers, all killed with the extra named in the rendered failure; member pyprojects unchanged; `uv lock --check` (`reviewer/mutants/`); plus the cycle gate's extras mutants, 2 cases × 2 layers killed (`orchestrator/gate-p1.log`) | ✅ (reviewer; gate by orchestrator) |
| R6 | `README.md`, `packages/cluster-mcp/README.md`, `packages/cluster-mcp-rcac/README.md`, `docs/core/README.md`, `docs/rcac/README.md`, `packages/cluster-mcp/pyproject.toml` comment, `AGENTS.md` | grep of every line GOAL names and the whole repo outside `spec/`: every RCAC install line names `[rcac]`; each remaining `[slurm,rcac]` is a compat-root line GOAL exempts; `SECURITY.md:267` still points to the Quick Start (`reviewer/r6_grep.txt`, `install_lines_grep.txt`). No in-suite check (coverage observation C1). Cycle gate mutated by the orchestrator (below) | ✅ (reviewer; gate by orchestrator) |
| R7 | `ROADMAP.md` site-interfaces and `[rcac]` entries, `issues/site-extras.md` | rule, citation and "`[rcac]` brings `[slurm]` from 0.2.2" in all three; the `[rcac]` entry's horizon and place unchanged; no internal path, board id or name (`reviewer/r7_grep.txt`) | ✅ (reviewer) |

Unmapped changes (possible scope creep): none. Source carries no spec R#/P# ids
(`reviewer/spec_id_grep.txt`).

## Findings

No CONFIRMED finding.

### F1 · LOW · PLAUSIBLE → fixed: the docs said the probe withholds an extra
- **Where:** `docs/rcac/README.md:26-27`, `README.md:47` (as reviewed); the same phrasing in
  `docs/slurm/README.md:24` and `docs/core/README.md:54`.
- **Scenario:** `[rcac]` now installs two capabilities, and the probe judges each on its own. "The
  server withholds the extra: none of its tools…" reads as if a cluster lacking `findscratch` or
  `myquota` loses the Slurm tools `[rcac]` brings, and it does not.
- **Evidence:** `[rcac]` from `ed9c166`, `-e local` with the probe, on a PATH holding only Slurm's
  six commands: `Capability cluster-mcp-rcac withheld: the cluster is missing findscratch, myquota`,
  and `sbatch`…`scontrol_show_node` (14 tools) served (`reviewer/surfaces/probe-head-rcac-slurm-only.json`).
  The behaviour is right and matches `docs/core/README.md` § Which capabilities are served; the
  sentence is the defect, and R6 does not reach it.
- **Triage:** fix (the foreman, 2026-11-13). Routed as its class, "the probe withholds a capability
  on its own, never an extra": the four sentences now say so, and § Which capabilities are served
  states that `[rcac]` keeps its Slurm tools without `findscratch`/`myquota` and its RCAC tools
  without Slurm's commands, both directions the reviewer's probe drives show. `docs/slurm/README.md`
  joined the cycle gate's allowed paths for it.

### C1 · coverage observation: no in-suite check of the install lines
- **Where:** the suite, outside `spec/`.
- **Evidence:** the reviewer planted the old `[slurm,rcac]` lines back into `README.md`, `docs/core`,
  `packages/cluster-mcp/README.md`, `docs/rcac` and the `AGENTS.md` `post_verify` line; every test
  module that reads a docs file passed (601 passed) (`reviewer/install_line_plant.out`).
- **Grading:** R6 asks for the text, not a test; its check is the cycle gate
  (`verify/text_checks.py install-lines`), as designed. Recorded, not seeded (the foreman,
  2026-11-13).

### G1 · LOW · orchestrator-graded: the cycle gate's install-line check let two wordings through
The blind reviewer cannot see `spec/`, so the orchestrator mutated the check
(`orchestrator/install_line_mutants.py`). Each case clones the repository at `ed9c166` into its own
temporary lab, plants one drift, stages it, and runs `text_checks.py install-lines 916cecf`. Killed
only when the check exits non-zero and a rendered `FAIL` line names the planted file.

| Drift planted | At `ed9c166` | Remediated |
|---|---|---|
| (control, unplanted) | passes | passes |
| README uvx line as `[slurm,rcac]` | killed | killed |
| README `args` line as `[slurm,rcac]` | killed | killed |
| README table row as `[slurm,rcac]` | killed | killed |
| README uvx line as `[rcac,slurm]` | killed | killed |
| README uvx line as `[slurm, rcac]` | killed | killed |
| README uvx line as `[ rcac , slurm ]` | killed | killed |
| `docs/rcac` line as `[slurm,  rcac]` | killed | killed |
| new doc: "`[rcac]` extra goes with `[slurm]`" | killed | killed |
| the same, wrapped across lines | killed | killed |
| new doc: `cluster-mcp[slurm,rcac]` | killed | killed |
| new doc: "Install `[rcac]` with `[slurm]`" | **survived** | killed |
| new doc: "Install `cluster-mcp[rcac]` together with `cluster-mcp[slurm]`" | **survived** | killed |
| new doc: "Also install `cluster-mcp[slurm]` with `cluster-mcp[rcac]`" | killed | killed |
| new doc: "does not bring the Slurm tools" | killed | killed |
| new doc: `--with 'cluster-mcp[slurm]…'` | killed | killed |
| new doc: "`cluster-mcp[rcac]` and `cluster-mcp[slurm]`" | not run | killed |
| new doc: "`[slurm]` alongside `[rcac]`" | not run | killed |
| new doc: "GOES WITH `[slurm]`" | not run | killed |

- **Cause:** the forbidden phrases matched case-sensitively, and no pattern caught a second
  requirement joined by "together with".
- **Effect:** none at HEAD: a case-insensitive grep outside `spec/` finds no text pairing `[rcac]`
  with `[slurm]`. The gap was in the gate, a wording variant of a class it pins.
- **Fix:** the forbidden phrases match in any case; two patterns refuse `[rcac]` joined to `[slurm]`
  (with, together with, alongside, beside, and, plus) and the reverse (without "and", so a listing
  of the extras passes), each skipped inside the file's allowed compat-root lines. Logs:
  `orchestrator/install-line-mutants.log` (at `ed9c166`), `install-line-mutants-38871fc.log` (the
  remediated column, the committed check at `38871fc`).
  No `issues/` seed: the check is the cycle's (the foreman, 2026-11-13).

## Human-gate triggers

- No CONFIRMED finding, so none from findings. The cycle's own publish gate stands:
  `tests/fixtures/served_surface.json` is on § Invariants' high-blast-radius list, and GOAL's
  Publish gate takes the maintainer's sign-off on the fixture outcome. That sign-off is a no-diff
  check: the fixture's bytes are unchanged (sha256 above). It holds at publish.

## Optional completeness sub-pass

Not run (not requested).
