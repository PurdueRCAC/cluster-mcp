# REVIEW — Remove the documentation search subsystem

> Adversarial QA by `code-review`, run in an isolated context (a fresh subagent, xhigh effort). The
> correctness pass graded the branch diff against [`GOAL.md`](GOAL.md) and the repo's `AGENTS.md`
> § Invariants **only**. It did not see `PLAN.md` or `TECH.md`. Every finding cites an **executed**
> command, not an assertion.

- **Reviewed commit:** d0b705714719fac1986acb1062789df68578813e  ·  **Base:** develop (3cb2853)  ·  **Date:** 2026-10-16
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`

## Verification run

- `uv sync --locked` → exit 0.
- Profile verify `uv lock --check && uv run pytest -q && bin/sandbox.sh uv run rcac-mcp --help` →
  exit 0; 30 passed (24 `unit`, 6 `integration`), none skipped; the help text names no docs flag.
- `bin/sandbox.sh uv run rcac-mcp --index-docs` (and `--docs-path /tmp`, `--docs-output /tmp/x.db`,
  `--docs-path=/tmp`, `-t http -e local --index-docs`, all three together) → each exits 2
  (`exit_status.bad_argument`) with `unrecognized arguments: <flag…>`, no `Execution mode` log line,
  and no `*.db` under the sandbox `HOME` or the working directory.
- Negative controls, each reverted:
  - a `doc_search` entry put back in `SERVER_INSTRUCTIONS` → 11 tests fail;
  - a fake `doc_search` tool registered → 13 fail;
  - an unmarked test → pytest exits 4 with a usage error;
  - `--index-docs` re-added → 3 `test_cli` cases fail.
- Fresh `git clone` of the branch → `git submodule status` prints 0 bytes; no `tests/fixtures`.
- `uv build` → the wheel and sdist carry no docs entries; the wheel requires only cmdkit, fabric,
  fastmcp and pyjwt.
- `git grep` for spec ids (`R#`/`P#`) in `src/`, `tests/`, `bin/` and `pyproject.toml` → none.
- Reviewer hand-back: `git status --porcelain` empty, HEAD unmoved, ignored state it created removed
  and confirmed absent (orchestrator re-checked: clean, HEAD `d0b7057`, `src/rcac_mcp/docs` absent).

## Requirement → evidence matrix

All rows verified by the blind reviewer. No R-ID is a `spec/` artifact deliverable.

| R-ID | Implemented by | Verified how | Status |
|------|----------------|--------------|--------|
| R1 | `tools/docs.py` and `src/rcac_mcp/docs/` removed; `tests/test_registry.py` | 25 decorated tools at `3cb2853` vs 23 in the live `TOOL_REGISTRY`; the difference is exactly `doc_load`, `doc_search`; both `rcac_mcp.docs` and `rcac_mcp.tools.docs` raise `ModuleNotFoundError` | ✅ |
| R2 | `src/rcac_mcp/__init__.py` (flags, `APP_USAGE`, `APP_HELP`) | sandboxed `--help` and `-h`: no line mentions a docs flag | ✅ |
| R3 | flags removed; `tests/test_cli.py` | sandboxed drives above: exit 2, message names the flag, no server start, no database file | ✅ |
| R4 | `src/rcac_mcp/server.py`; `tests/test_instructions.py` | `SERVER_INSTRUCTIONS` lists all 23 registry names and no doc guidance; served text equals the constant; cross-check tests fail on both negative controls | ✅ |
| R5 | `INSTRUCTIONS.md` | `grep -niE 'doc' INSTRUCTIONS.md` → nothing | ✅ |
| R6 | `README.md` | no docs-index section, `doc_*`, removed flags or `RCAC_DOCS_DB`; lines 79–82 point to `rcac-docs-mcp` at `https://docs.rcac.purdue.edu/mcp`; inventory equals the registry | ✅ |
| R7 | `.gitmodules` and the gitlink removed | no `.gitmodules`; no 160000 entry in `git ls-files -s`; fresh clone's `git submodule status` silent | ✅ |
| R8 | `pyproject.toml`, `uv.lock` | no `yaml`/`jinja2` import in `src/`; neither in `[project.dependencies]`; `uv lock --check` exit 0; `pyyaml` remains only transitively (fastmcp → jsonschema-path) | ✅ |
| R9 | `tests/conftest.py`, the three test files | verify collects 30, all marked, all pass; R1, R3 and R4 checks present; unmarked test rejected | ✅ |
| R10 | `AGENTS.md` | no docs subsystem, tool, flag, fixture or submodule described as present; map row gone; § Testing and § Conventions describe the new tests; high-blast-radius list unchanged | ✅ |

Unmapped changes: the negative-control tests (`test_served_tools_match_registry`,
`test_flag_check_rejects_a_known_flag`, `test_absence_check_catches_namespace_leftover`, the mutation
suites) guard the R1/R3/R4 checks; dated notes in two seeds; the adopted status markers. None
blocks.

## Findings

### [LOW/CONFIRMED] F1 — The `restore-test-coverage` ROADMAP entry now misstates the suite
- **Where:** `ROADMAP.md:49-56` (the "Every test in the suite is a docs test" entry).
- **Failure scenario:** the entry still says all 81 tests cover the documentation index and names
  `test_database.py`, `test_indexer.py` and `test_tools.py`. On this branch `tests/` holds only
  `conftest.py`, `test_cli.py`, `test_instructions.py` and `test_registry.py`, and the suite collects
  30 non-docs tests. That entry is the next cycle's seed; its index line would mislead its shaping.
  The seed file already carries a dated correction (`issues/restore-test-coverage.md:85-89`); the
  ROADMAP entry has none.
- **Evidence:** `ls tests`; `uv run pytest -v` → 30 collected, none a docs test.
- **Touches:** the deferral index's accuracy (prose claim about the repository); no gate weakened.

### [LOW/CONFIRMED] F2 — A stale `src/rcac_mcp/docs/__pycache__/` turns the R1 check red on an old checkout
- **Where:** environment of any checkout that ran the pre-strip code; `tests/test_registry.py`
  (`test_docs_modules_absent[rcac_mcp.docs]`).
- **Failure scenario:** git leaves the ignored `src/rcac_mcp/docs/__pycache__/` behind when such a
  checkout moves to this tree; `rcac_mcp.docs` then imports as an empty namespace package and the
  profile's `verify` fails. The operator's main checkout has that directory today. The wheel, the
  sdist and a fresh clone are clean, and the test is right to flag the leftover: the gap is that
  nothing tells a developer what the failure means or how to clear it.
- **Evidence:** `mkdir -p src/rcac_mcp/docs/__pycache__` → `import rcac_mcp.docs` returns
  `<module 'rcac_mcp.docs' (namespace)>` and `pytest tests/test_registry.py` → 1 failed, 7 passed;
  after removal → 8 passed.
- **Touches:** R1 in a stale environment; developer guidance (`AGENTS.md`).

## Routing (orchestrator)

Both findings are CONFIRMED, so the cycle goes back to build (rubric → *Verdict & loop*: a
CONFIRMED finding always blocks). Each is routed as its class:

- **F1:** every ROADMAP entry whose present-tense description this cycle made false gets a dated
  correction line, as its seed already has; the historical text stays.
- **F2:** `AGENTS.md` names the stale-bytecode trap where a developer will look when the R1 check
  fails (§ Testing), with the remedy, and the R1 absence test's failure message names the leftover
  path. The main checkout's leftover is cleaned when `main` fast-forwards at release, and the landing
  notes carry it.

## Human-gate triggers

- None. Neither finding touches a path on § Invariants' high-blast-radius list or a `[human gate]`
  section.

## Optional completeness sub-pass

- Not run (not requested).

## Review cycle 2 — changes-requested (2026-10-16)

- **Reviewed commit:** a5da72c9680ef0cbba12bcca8f2abcf0cd3891b7 · **Mode:** scoped by the foreman to
  verifying the remediation of F1 and F2, plus a no-regression check (fresh blind subagent, xhigh).
- **Verification run:** profile verify → exit 0, 30 passed, `--help` names no removed flag (run
  before and after the probes); spec-id grep over `src/`, `tests/`, `bin/`, `pyproject.toml` → none;
  `uv build` with a planted leftover → 0 `rcac_mcp/docs` entries in wheel and sdist; reviewer left
  `git status --porcelain` empty, HEAD unmoved, probe directories trashed.
- **F1 — fixed.** The class predicate, evaluated over every ROADMAP entry and all 20 seeds, finds
  each present-tense claim this branch made false now followed by a dated 2026-10-16 correction
  (ROADMAP strip, 81-tests and CI entries; `ci-workflow`, `storage-paths-resource-typeerror`,
  `restore-test-coverage`, `agents-d-instructions`, `tool-surface`). Numbers measured against
  `3cb2853` and HEAD: `SERVER_INSTRUCTIONS` 2,988 → 2,085 characters; tool definitions 26,482 (25
  tools) → 23,481 (23); the stated "about 11% high" holds. Historical text kept: the remediation only
  adds lines in `ROADMAP.md` and `issues/`.
- **F2 — fixed.** With an empty `src/rcac_mcp/docs/__pycache__/` (and again with fake `.pyc` files),
  `uv run pytest -q tests/test_registry.py` → 1 failed, 7 passed, and the failure names the path,
  what it holds and the `del` remedy; after `del src/rcac_mcp/docs` → 8 passed. `AGENTS.md` § Testing
  and the test message state the same path and remedy, and only those two places state it.
- **Dropped (orchestrator):** the reviewer's borderline residual, `issues/strip-docs-subsystem.md`
  still reading "What is still here". That seed is this cycle's own, marked
  `adopted:strip-docs-subsystem`; the marker is its correct state, and `code rcac-mcp roadmap`
  retires the file once the cycle lands. Not a finding.

### [LOW/CONFIRMED] F3 — The absence check's explanation misdiagnoses a re-added package
- **Where:** `tests/test_registry.py:86-91` (`absence_violations`), introduced by the F2 remediation.
- **Failure scenario:** when `src/rcac_mcp/docs/` holds a real `__init__.py` (a regression that
  re-adds the package), the test still fails correctly, but its message explains the failure as
  ignored leftovers importing as an empty namespace package and tells the developer to
  `del src/rcac_mcp/docs`: advice to delete source code that a regression added.
- **Evidence:** untracked `src/rcac_mcp/docs/__init__.py` created → the message read "holding
  ['__init__.py']" with the stale-leftover explanation and the `del` remedy; removed afterwards.
- **Routing:** as a class, the explanation must follow what the directory actually holds: only
  bytecode leftovers (`__pycache__`, `*.pyc`) get the stale-checkout explanation and the `del`
  remedy; any source file means the package was re-added, which R1 forbids, and the message says
  that instead. `AGENTS.md` § Testing stays consistent with it (§ Conventions).

### Human-gate triggers (cycle 2)

- None.

## Review cycle 3 — approved (2026-10-16)

- **Reviewed commit:** 7183a7b · **Mode:** scoped by the foreman to verifying the remediation of F3,
  plus a no-regression check (fresh blind subagent, xhigh). This is the last cycle the bounded loop
  allows.
- **Verification run:** profile verify at start and end → `uv lock --check` ok, 39 passed,
  `bin/sandbox.sh uv run rcac-mcp --help` exit 0; every test marked (`-m 'not unit and not
  integration'` collects 0); spec-id grep (`\b[RPF][0-9]+\b` over `src`, `tests`, `bin`,
  `pyproject.toml`) → 0 hits; `git status --porcelain` empty and the ignored listing unchanged at
  hand-back; every plant removed with `del`.
- **F3 — fixed.** Fourteen planted shapes under `src/rcac_mcp/docs`, `src/rcac_mcp/docs.*` and the
  `tools/docs` analogues: every importable shape fails `test_docs_modules_absent[…]`; bytecode-only
  contents (empty `__pycache__/`, `*.pyc` at any depth, a bare `.pyc` module, an empty
  subdirectory) get the stale-checkout explanation with the matching `del` path, and source contents
  (`__init__.py`, `indexer.py`, `schema.sql`, a nested module, `docs.py`) get the re-added message
  with no `del`; each removal returns the run to green. Mutation controls: forcing either branch
  fails the other branch's standing tests. `AGENTS.md` § Testing, the helper's docstring and the
  test comments state the same two cases; nothing else restates the rule.
- **N1 — observation, not a blocking finding (orchestrator).** Reproduced: an untracked leftover that
  is neither bytecode nor source (`.DS_Store` beside bytecode, an interrupted
  `*.cpython-314.pyc.<n>` temp file) is reported as a re-added module, with no remedy. The R1
  verdict is right in every shape; the message names the file and never advises deleting anything;
  it matches `AGENTS.md`'s "any other file" wording. Under the rubric's coverage-observation rule a
  CONFIRMED item in defence-in-depth code blocks only when it breaks an R-ID's stated check or a
  reachable behaviour: it does neither, unlike F3, whose advice was destructive. Recorded and seeded
  as a dated note on [`restore-test-coverage`](../../issues/restore-test-coverage.md) (the cycle that
  rebuilds this suite), committed as `2edfcc0` before this verdict; the approval is pinned to that
  commit.
- **Blindness note.** The reviewer disclosed that one `grep -rn` meant to exclude `spec/` printed
  matching lines from `spec/` (PLAN, TECH, REVIEW, research). Its verdicts rest on the reproductions
  above, each an executed command, and this pass's scope was verifying F3 by reproduction, so the
  leak does not undermine the evidence. Recorded so the next cycle's delegation states the
  exclusion as a pathspec rather than a filter.
- **Convergence.** Three cycles, each finding LOW and each narrower than the last (F1/F2 → F3 from
  the F2 remediation → N1 from the F3 remediation, non-blocking). Converged within the bound; no
  escalation needed.

### Human-gate triggers (cycle 3)

- None. No CONFIRMED finding in any cycle touched a high-blast-radius path or a `[human gate]`
  section.
