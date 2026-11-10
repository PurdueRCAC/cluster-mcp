# REVIEW — Nothing would catch the next silently wrong annotation

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** 82f5744b3226406eece36b5dc1accc7b7c3a2eff  ·  **Base:** develop (`e378c33`)  ·  **Date:** 2026-11-09
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)

One fresh blind reviewer (subagent, effort xhigh), no debate, no sequential fallback. It was given
GOAL and the rubric inline, the spec-excluded diff and log, and `AGENTS.md` by path. Its report and
every probe and log it cites are in the worktree's gitignored `.local/review1/` (`REPORT.md` is its
hand-back, saved verbatim). The GOAL moved once after the shape commit (`9c053bf`, the GOAL-gate
clarifications Q1 and Q2, a foreman ruling); this review grades the GOAL at HEAD.

## Verification run

- `uv sync --locked` → ok.
- `uv run pytest -q tests/test_annotations.py` (legacy, then `CLUSTER_MCP_TEST_ERA=modern`) → 112
  passed per era, about 3.1 s wall each; the tree test alone about 1.5 s.
- The profile's fourth suite command (`--ignore` the four split files), both eras → 4,481 passed,
  14 skipped (`need_shell`) per era; 230.9 s legacy, 226.4 s modern. The new module is collected
  there (`r6-r7-suites.log`).
- Targeted: `test_served_surface_matches_baseline`, `test_auth_modes`, `test_hygiene`,
  `test_suite_parts` → 205 passed per era.
- Not run: the `test_ssh_exec`, `test_timeout_stop`, `test_startup`, `test_launch` parts of
  `verify` (the diff does not touch them) and the `bin/sandbox.sh uv run cluster-mcp --help` drive.
- No network: the new module passes with outbound network denied, while `curl` fails under the same
  profile (`no-network.log`).
- R7: `git diff --stat origin/develop...HEAD -- 'packages/*/src' tests/fixtures/served_surface.json`
  → empty (`r7.log`).
- Plants in the real `src/`, each reverted with a clean tree asserted after it (`plants.py`,
  `plants2.py`, both eras): a slice in every position kind in the core, Slurm and RCAC members; non-type
  numbers; undefined names and a `TYPE_CHECKING`-only import, postponed and eager → all red, each
  naming module, line, qualified name, the text as written and why.
- Mutant sweep: 56 mutants of `tests/test_annotations.py`, each run on the whole module in both
  eras (`mutants.py`, `mutants-{a,b,c}.json`); every survivor replayed against a planted real
  defect, unmutated and mutated (`survivors.log`, `m54*.log`).
- Orchestrator: `sh spec/annotation-check/verify/seen_red.sh` at `82f5744` → baseline green, then
  red with the named refusal on all 35 planted cases (every position kind in `core/auth.py` and
  `rcac/resources.py`, `AUTH_MODES` itself, two Slurm tool signatures), exit 0, 105 s
  (`orchestrator-seen-red.log`).
- CI (`.github/workflows/ci.yml`) and the `ci budget` → **not observed**; the publish step reads the run.
- Tree hygiene: `git status --porcelain` empty on hand-back; `.venv` not mutated, `uv.lock` md5
  unchanged; created plant files removed. Confirmed again by the orchestrator before writing this.

## Requirement → evidence matrix

| R-ID | Implemented by (file/commit) | Verified how | Status |
|------|------------------------------|--------------|--------|
| R1 | `tests/test_annotations.py` (`annotation_positions`, `type_expression_violations`, tree test), `5aaa682` | Reviewer: slice and number plants in every position kind and member, both eras | ✅ met; pinning gaps F2–F4, two unread forms F5 |
| R2 | same | Reviewer: `Final[Strr]`, `TYPE_CHECKING`-only `Decimal` (postponed core, eager RCAC), `-> UserPathh` → red with `NameError`, both eras | ✅ |
| R3 | same (`_refusal`) | Reviewer: `{module}:{line}: {qualified name}: {text!r}: {why}` on every plant | ✅ |
| R4 | same (`workspace_violations`, `member_modules`) | Reviewer: new modules in Slurm and core red with no edit; a new member discovered and refused as not importable; no list of modules or members | ✅ met; discovery unpinned, F2 |
| R5 | same; `spec/annotation-check/verify/seen_red.sh` | **Both.** Reviewer: a slice per position kind in core, Slurm, RCAC, all red; tree green both eras. Orchestrator: `seen_red.sh` 35/35 red, baseline green | ✅ |
| R6 | the module in the collected suite (fourth command); `AGENTS.md` § Testing, `82f5744` | Reviewer: collected in both eras, passes with network denied; module ~3 s | ✅ locally; CI budget **not observed** |
| R7 | no `src/` or fixture change | Reviewer: empty `--stat`, `test_served_surface_matches_baseline` passes both eras; the check flags nothing on the tree (35 modules, 1,009 positions, 0 violations) | ✅ |

Unmapped changes (possible scope creep): none. The `issues/annotation-check.md` and `ROADMAP.md`
edits are the seed's adoption status and a one-line clarification. Note: the seed's Problem and
Outcome still cite `src/rcac_mcp/…`; that text predates this diff and was not graded.

## Findings

Five CONFIRMED (1 MEDIUM, 4 LOW), no PLAUSIBLE. None is a § Invariants violation. The check is
correct on every reachable defect planted in today's `src/`. The four LOW findings are mutants that
survive the check's own suite while letting a real planted defect through, so each breaks an R-ID's
stated check on reachable input.

### F1 [MEDIUM/CONFIRMED] `AGENTS.md` credits `type_expression_violations` with work other functions do
- **Where:** `AGENTS.md:953-956` (§ Testing, the `tests/test_annotations.py` entry).
- **Failure scenario:** the entry says `type_expression_violations` refuses "a slice, a number, an
  unresolved name", naming module, line, qualified name and text. The function actually returns bare
  reasons, with no position. An undefined name never reaches it: `_resolved` raises `NameError` and
  `_verdict` refuses it. The naming format belongs to `_refusal`, reached through
  `workspace_violations`. § Testing lets a gate import `*_violations` directly, so a gate built on
  this text gets the wrong contract.
- **Evidence:** `agents_claims.py` → `agents-claims.log` (slice → bare reason; `_resolved` raises
  `NameError`; `_refusal` → `scratch_mod:1: held: 'Missing': does not resolve: NameError: …`).
- **Touches:** rubric Scope 5, operating-manual drift (an `AGENTS.md` description wrong).

### F2 [LOW/CONFIRMED] Workspace discovery is unpinned: the tree test passes while reading far less
- **Where:** `tests/test_annotations.py:634-644` (`member_modules`), `:680-700` (tree test).
- **Failure scenario:** the tree test's only position assertion is `cluster_mcp.core.auth:AUTH_MODES`,
  and every scratch member is a depth-2 `pkg/mod.py`. Three mutants survive, each letting a real slice
  ship:
  - M51 skips package `__init__` modules (54 positions today). A slice at `cluster_mcp.core:57
    DEFAULT_PORT` is red unmutated and green mutated.
  - M52 reads only to depth 3 (560 positions in subpackages). A slice at
    `cluster_mcp.core.executor.launch:327 Marks.start` is red unmutated and green mutated.
  - M54 checks only the first member that has positions. It was killed in 3 of 6 runs:
    `test_a_member_added_later_is_checked` depends on random uuid member order, and a slice at
    `cluster_mcp.slurm.tools:53` passes the tree test under it.
- **Evidence:** `mutants-c.json|log`, `survivors.json|log`, `m54.json|log`, `m54plant.json|log`.
- **Touches:** R4 (and R1 through it).

### F3 [LOW/CONFIRMED] The type-expression walker's branches are unpinned
- **Where:** `tests/test_annotations.py:390-442` (`generic`, `parameters`).
- **Failure scenario:** each mutant survives the module in both eras, and the unmutated check catches
  the same shape planted in real `src/`.
  - Shapes in today's tree: M38 (a `Callable` return not walked; 12 positions; plant
    `core/tools/__init__.py:63 Callable[..., Any:]`) and M40 (a `tuple[X, ...]` element not walked;
    15 positions; plant `core/capabilities.py:87`).
  - Shapes absent today: M39 (`Concatenate` prefix), M41 (the list argument of a `ParamSpec`
    generic), M45 (`InitVar` argument). Each was planted in an RCAC module: red unmutated, green
    mutated.
- **Evidence:** `mutants-b.json`, `mutants-c.json`, `survivors.log`.
- **Touches:** R1.

### F4 [LOW/CONFIRMED] Position reading and the failed-import fallback are unpinned
- **Where:** `tests/test_annotations.py:201-310` (the reader), `:534-535` (failed import).
- **Failure scenario:**
  - M15 and M16 skip `try` and `with` blocks, though the docstring at `:204-205` says they are read;
    only `if` is planted. A module variable inside either block in `rcac/resources.py` is red
    unmutated, green mutated.
  - M09 ignores aliased functional imports. A plant using `from typing import NamedTuple as NT` is
    red unmutated, green mutated.
  - M29: a failed import whose traceback lacks the module's own frame returns nothing. This is
    reachable when a package `__init__` fails. With `import cluster_mcp_no_such_module` in
    `slurm/__init__.py` and a slice in `slurm/tools.py`, the unmutated check is red ("the import
    raised ModuleNotFoundError"); mutated, it is green and the whole package goes unread.
- **Evidence:** `mutants-a.json`, `mutants-b.json`, `survivors.log`.
- **Touches:** R1 (and R4 for M29).

### F5 [LOW/CONFIRMED] Two functional class forms that keep annotations at run time are never read
- **Where:** `tests/test_annotations.py:238-259` (`functional`).
- **Failure scenario:** `dataclasses.make_dataclass('MadeDC', [('held', dict[str, int:])])` and the
  keyword form `typing.NamedTuple('KwNT', held=dict[str, int:])` (deprecated, still accepted on 3.14).
  Python keeps `dict[str, slice(...)]` for both, yet the check reads 0 positions and reports nothing.
  Neither form is in today's tree.
- **Evidence:** `unread_forms.py` → `unread-forms.log`.
- **Touches:** R1 ("a class attribute's" annotation Python keeps at run time; per Q1, these are kept,
  as `get_type_hints` shows).

### Coverage notes (defence-in-depth survivors, not findings)
- M22 (an exception inside the walker counts as a pass, `:479-480`): no reachable hint makes
  `type_expression_violations` raise.
- M31 (an unparseable module is silent, `:589-590`): an unparseable module cannot be imported and
  keeps no annotations; no R-ID check breaks.

Neither is seeded separately: F2–F4's route is a module-wide sweep, which re-judges both.

### Observations (not findings)
- A slice in a core tool parameter makes pydantic raise when conftest imports the core, so the
  session dies at collection (exit 4) before the check runs. That is still red. Run directly, the
  check names `cluster_mcp.core.tools.shell:19: run_command(cwd)` (`core-tool-plant-report.json`).
- The check is stricter than R1, and fails closed: any annotation in a `__main__` module is refused,
  and a method annotation reading a class-body name is refused even where it would resolve. Neither
  case exists today.

## Routing (to `code build`)

Route each as its property and its whole domain; the instances above are the examples.

- **F1:** each function `AGENTS.md` names is described as doing only what it does. Who returns
  reasons, who resolves, who refuses an unresolved name, and who formats module, line, name and text
  are each attributed to the function that does it.
- **F2–F4 (surviving mutants):** a module-wide mutant sweep over every decision in
  `tests/test_annotations.py`: discovery (members, depth, package `__init__`s, every member), the
  type-expression walker (every generic, callable, parameter-spec, tuple, `InitVar` and `Annotated`
  branch), the position reader (every block kind, aliased imports, every position kind), and the
  failed-import fallback. Include additive mutants (a carve-out the check could grow). Run each
  mutant in both eras. Every survivor must be killed by a named test row, or recorded as equivalent
  with the reason. M54's killing row must not depend on random member order: a member added later is
  caught whatever its position in the workspace.
- **F5:** every functional class form whose annotations Python keeps at run time is read, including
  `make_dataclass` and keyword-form `NamedTuple`. Each is pinned by a planted red row.

## Human-gate triggers

- Not triggered. No CONFIRMED finding lies in a file on § Invariants' high-blast-radius list (the
  findings sit in `tests/test_annotations.py` and `AGENTS.md` § Testing). None violates a
  `[human gate]` section.

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run (not requested).
