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

## Review cycle 2 — changes-requested (2026-11-10)

- **Reviewed commit:** 672720d3acf65a26fefed4d7a3e3b218416a05ce  ·  **Base:** develop (`146cbc6`; merge base `e378c33`)
- **Mode:** a fresh blind pass over the full spec-excluded diff, which also judged cycle 1's F1–F5
  as properties. One fresh reviewer (subagent, effort xhigh), no debate, no sequential fallback. It
  was given GOAL and the rubric inline, the spec-excluded diff and log, `AGENTS.md` by path, and
  cycle 1's findings and routing text. Its evidence is in the gitignored `.local/review2/reviewer/`.
  Its report came back as text (the harness refuses subagent report files) and is summarized here.
- **Contract drift:** only `9c053bf` (the GOAL-gate clarifications Q1 and Q2) after the shape
  commit, as in cycle 1. This review grades the GOAL at HEAD.

### Verification run

Orchestrator gates (spec-held), evidence in `.local/review2/orchestrator/`:
- `gate.sh static` → ok (base `e378c33`). `gate.sh phase` → static, docs and ledger ok (0 deferrals).
- `seen_red.sh` at HEAD → baseline green, all 35 planted cases red with the named refusal, exit 0,
  111 s (`seen-red.log`).
- The remediation sweep, `sweep.py --record` at HEAD → baseline 208 passed per era; 102 mutants, 100
  killed in both eras, 2 recorded equivalent (E22, W16), 0 failures, exit 0, 897 s
  (`sweep-record.md`, `sweep.log`). The committed `verify/sweep-record.md` names `23c6cde`, a commit
  no branch reaches; the module blob there is identical to HEAD's, and this run re-records it at
  `672720d`.
- Ordering: the reviewer was launched while `seen_red.sh` and the sweep were still running, not
  after them. Both read a `git archive` of HEAD in their own scratch trees, and the reviewer worked
  only in its own scratch copies, so neither run could see the other's mutations; the results stand.
- **A listed-mutant gate cannot grade an open-ended class.** The sweep above is green because every
  mutant it lists is killed. It says nothing about the mutants it does not list, and the reviewer's
  wider sweep found 39 survivors outside its list (below). The sweep is a regression pin for the
  classes it names, not evidence that a property is closed over its domain.

Reviewer (both eras throughout, `CLUSTER_MCP_TEST_ERA` unset and `modern`):
- The new module, `test_hygiene` (including the spec-id rail), `test_suite_parts`,
  `test_auth_modes`, `test_served_surface_matches_baseline` → pass (`logs/verify-named-modules.txt`).
- The profile's fourth suite command → 4,577 passed, 14 skipped per era; 253 s legacy, 234 s modern
  (`logs/verify-part4-*.txt`). Module 3.0–3.3 s wall, tree test 1.8 s (`logs/r6-timing.txt`).
- No network: 208 passed per era with outbound network denied (`logs/r6-no-network.txt`).
- R7: `git diff origin/develop...HEAD -- packages/ tests/fixtures/` empty; nothing on the tree is
  flagged (35 modules, 1,009 positions, 0 violations).
- Plants: a 74-position plant in four modules across the core (postponed and eager), Slurm and RCAC,
  74/74 refused each time (`plants.py`, `logs/r5-*.json`); the original `AUTH_MODES …]:]` re-planted
  is refused at `cluster_mcp.core.auth:67`; R2 plants 7/7 refused in core and RCAC
  (`logs/r2-plants.json`); a new module and a new member each checked with no edit
  (`logs/r4-*.json`); the real tree test red on a slice in core `auth.py` and in `slurm/tools.py`,
  green after restore (`logs/r5-pytest-seen-red.txt`).
- Mutant sweep: 205 mutants (139 decision, 62 additive, 4 tree-oracle), each over the whole module in
  both eras (`mutants.py`, `logs/mutants-all.jsonl`, `logs/mutants-summary.txt`): 144 killed, 61
  survived, none era-dependent. Every survivor judged CONFIRMED was replayed as a real plant, refused
  unmutated and passed mutated (`demo.py`, `logs/demo-*.json`).
- Probes of functional class forms in other syntactic contexts (`ctx_plants.py`,
  `logs/ctx-plants.json`) and of valid but unusual shapes (`logs/valid-unusual.json`,
  `logs/valid-kw-only.json`).
- CI (`.github/workflows/ci.yml`, unchanged) and the `ci budget` → **not observed**; the publish
  step reads the run.
- Tree hygiene: `git status --porcelain` empty on hand-back (checked again by the orchestrator);
  no file outside `.local/` newer than the reviewer's start stamp; `$WT/.venv` never synced (`uv
  sync --locked --offline --dry-run`: no changes). All planting and mutating ran in three
  `git archive` scratch trees, each verified `diff -rq` identical to HEAD afterwards
  (`logs/restore-diff-*.txt`); a temporary member was removed, `uv.lock` restored from HEAD and
  re-synced.
- Orchestrator sanity check: the cited logs exist and read as stated (spot-checked
  `ctx-plants.json`, `valid-kw-only.json`, `demo-D19-*`, `demo-B5-mutant.json`,
  `mutants-summary.txt`).

### Requirement → evidence matrix

| R-ID | Implemented by | Verified how (who) | Status |
|------|----------------|--------------------|--------|
| R1 | `annotation_positions`, `_resolved`, `type_expression_violations`, `workspace_violations` | Reviewer: 74-position plant in four modules and three members, every block, position, functional and type-expression form, both eras | ⚠️ partial: N1 (functional forms outside a one-name assignment), N2 (a false refusal); pinning gaps N3, N4, N5 |
| R2 | `_verdict` | Reviewer: undefined, `AttributeError` and `TYPE_CHECKING`-only names in five position kinds, core and RCAC, 7/7 refused | ✅ met; pinning gap N6 |
| R3 | `_refusal` | Reviewer: every refusal reads `module:line: Qualified.name: 'text': why` | ✅ met; pinning gap N7 |
| R4 | `workspace_members`, `member_modules` | Reviewer: new module and new member checked with no edit; no list of modules or members; discovery mutants killed by order-independent rows | ✅ |
| R5 | the tree test; `spec/annotation-check/verify/seen_red.sh` | **Both.** Reviewer: plants per position kind in core and two other members red, tree green. Orchestrator: `seen_red.sh` at HEAD, 35/35 red, baseline green | ✅ |
| R6 | the module in the collected suite (fourth command) | Reviewer: collected both eras, network-free, module about 3 s | ✅ locally; CI and `ci budget` **not observed** |
| R7 | no `src/` or fixture change | Reviewer: empty diff over `packages/` and `tests/fixtures/`; baseline test passes both eras; nothing flagged. Orchestrator: `gate.sh static` | ✅ |

Unmapped changes: none blocking. Refusing a slice inside `Annotated` metadata is stricter than R1
(metadata may be any value); minor, fails closed. The `ROADMAP.md` and seed edits are adoption
bookkeeping and match reality.

### Cycle-1 findings

| Finding | Status | Evidence |
|---------|--------|----------|
| F1 (`AGENTS.md` misattribution) | **closed as a property**: each function the entry names is described as doing only what it does | reviewer read of `AGENTS.md:947-968` against the code |
| F2 (discovery unpinned) | **closed as a property**: `__init__`, depth, first-member and every other discovery mutant killed; the M54 killer is order-independent (fixed names and an independent `os.walk` oracle) | `logs/mutants-summary.txt` (MM*, WM*, WR*) |
| F3 (walker unpinned) | **partly closed**: the five named branches are killed; other forms survive (N4) | G6, G7, G9, G11, W6 killed |
| F4 (reader and fallback unpinned) | **partly closed**: `try`, `with`, aliased imports and the frameless failed import are killed; other blocks, function shapes and exception classes survive (N3, N6) | K8, K11, P1, P4, I3 killed |
| F5 (functional forms unread) | **partly closed**: `make_dataclass` and keyword `NamedTuple` read and pinned; the same forms in other contexts are not read (N1), and F10, F11, P2 survive (N3) | `logs/ctx-plants.json` |
| Cycle-1 coverage notes M22, M31 | closed: now killed (V6, MC1) | `logs/mutants-summary.txt` |

### Findings

Seven CONFIRMED (1 MEDIUM, 6 LOW), no PLAUSIBLE. None is a § Invariants violation. The check is
correct on the current tree and on every position kind the cycle-1 routing named. N1 is a detection
gap on reachable syntax; N2 a false refusal; N3–N7 are 39 surviving mutants of the check's own suite,
each replayed as a real planted defect that the unmutated check refuses and the mutated check passes,
so each breaks an R-ID's stated check on reachable input.

#### N1 [MEDIUM/CONFIRMED] A functional class form is read only as a one-name assignment at module or class level
- **Where:** `tests/test_annotations.py:245-269` (`functional`, its one-`Name`-target guard at
  :247-249) and its only call site `:293-295` (`ast.Assign` only, never inside a function).
- **Failure scenario:** a `TypedDict`, `NamedTuple` or `make_dataclass` call holding
  `dict[str, int:]` is refused as `X = TypedDict(...)` but read nowhere else. Twelve contexts give 0
  refusals while Python keeps `dict[str, slice(...)]` on the built class: the value of an annotated
  assignment, a chained target, a tuple target, a walrus, a base class, an attribute target, a
  function body, a function's return value, a method body, fields passed in a variable, fields
  passed as `dict(...)`, and a module-level alias of the factory (`TD = typing.TypedDict`). The
  first six are module-level syntax. The check reads a `class` statement inside a function (its
  `local-class-attribute` row) but not the same class built by a call there. `AGENTS.md:948-950`
  ("every annotation Python keeps at run time … class attributes") overclaims by the same amount.
- **Evidence:** `ctx_plants.py` → `logs/ctx-plants.json` (each context: `refused: []`, Python keeps
  the slice; the one-name control is refused).
- **Severity:** cycle 1 graded the F5 instance LOW; the remainder is a partial R1 on edge syntax plus
  an `AGENTS.md` description that overclaims, so MEDIUM.
- **Touches:** R1; rubric Scope 5 for the `AGENTS.md` sentence.

#### N2 [LOW/CONFIRMED] The dataclass `KW_ONLY` sentinel is refused as a non-type
- **Where:** `tests/test_annotations.py:406-414` (`type_expression_violations`).
- **Failure scenario:** `_: KW_ONLY` in a dataclass, the documented idiom that `dataclass` and
  `get_type_hints` both accept, is refused "resolves to a _KW_ONLY_TYPE, not a type" in both
  annotation modes. `InitVar` and `ClassVar` are special-cased; `KW_ONLY` is not. Not on today's
  tree, so R5 holds, but the next module that uses it fails the gate and needs an edit to the check.
  48 other valid unusual shapes pass.
- **Evidence:** `plants/kw_only.py` → `logs/valid-kw-only.json`; `logs/valid-unusual.json`.
- **Touches:** R1 (rejects only what is not a valid type expression).

#### N3 [LOW/CONFIRMED] Carve-outs in the position reader survive (the F4 and F5 property)
- **Where:** the reader, `tests/test_annotations.py:201-310`; the tree test's oracle at `:740-742`.
- **Failure scenario:** 20 mutants survive both eras, each a plant refused unmutated and passed
  mutated:
  - function shapes: attribute decorator (D10), call decorator (D11), `classmethod` (D12),
    `property` (D13), `_private` functions (D17), dunder methods (D18), parameters with a default
    (D19), `self`/`cls` (D20);
  - class shapes: a call-decorated class such as `@dataclass(frozen=True)` (B5), `_private` class
    attributes (B10);
  - blocks: any `if NAME:` or `if a.b:` treated as `TYPE_CHECKING` (T3, T4), `for`/`while` `else`
    (K1), `async for` (K2), `async with` (K2b), `try*` (K3), `match` cases after the first (K12);
  - functional forms: a tuple field container (F10), list-shaped pairs (F11),
    `from typing_extensions import TypedDict as X` (P2).
  On the real tree the mutated reader drops up to 365 of 1,009 positions (D17) while the suite stays
  green; D19 alone drops 113, 59 of them in tools modules, which are served schemas.
- **Root cause:** the tree test computes the positions it expects with the same
  `annotation_positions` it is checking, so an under-reading reader is invisible to it; only the
  planted rows pin the reader.
- **Evidence:** `demo.py` → `logs/demo-{D10..D20,B5,B10,T3,T4,K1,K2,K2b,K3,K12,F10,F11,P2}-*.json`;
  `real_positions.py` → `logs/real-tree-unread*.txt`.
- **Touches:** R1.

#### N4 [LOW/CONFIRMED] Carve-outs in the type-expression walker survive (the F3 property)
- **Where:** `generic` `:416-457` (qualifier branch `:423-427`), `parameters` `:459-468`.
- **Failure scenario:** nine survivors, each a plant refused unmutated and passed mutated: the
  argument of `ClassVar`, `Required`, `NotRequired` or `ReadOnly` not walked (G3a–d; only `Final[…]`
  is planted), `type[…]` (G13), `Unpack[…]` (G15), `collections.abc` generics such as `Mapping`
  (G16), `set`/`frozenset` (G19), `Callable` parameters after the first (G22). Python keeps the
  slice in each.
- **Evidence:** `logs/demo-G*-*.json`, `logs/walker-plants-runtime.txt`.
- **Touches:** R1.

#### N5 [LOW/CONFIRMED] Shadow detection's binding and name readers survive
- **Where:** `_scope_bindings` `:149-154`; `_names_read` `:181`, `:186-188`.
- **Failure scenario:** `except … as` names (S5), `match` capture names (S6) and `**rest` (S7) not
  bound; the base of an `Annotated` (N3) and a subscript head (N5) not read. In eager mode Python
  keeps a non-type or cannot resolve the annotation in each case; the unmutated check refuses each,
  the mutant passes each.
- **Evidence:** `logs/demo-shadow-runtime.txt`, `logs/demo-{S5,S6,S7,N3,N5}-*.json`.
- **Touches:** R1, R2.

#### N6 [LOW/CONFIRMED] Exception classes in resolution and at import are pinned only in part
- **Where:** the R2 rows `:923-939` (only `NameError`, `TypeError`, `SyntaxError`); `module_check`
  `:622-627`.
- **Failure scenario:** carve-outs for `AttributeError` (V3; `x: os.NoSuchThing` is realistic),
  `RecursionError` (V7) and `LookupError` (V8) in resolution, and `SystemExit` at import (MC5),
  survive; each plant is refused unmutated and passed mutated.
- **Evidence:** `logs/demo-{V3,V7,V8,MC5}-*`.
- **Touches:** R2, R4 (a module whose import fails).

#### N7 [LOW/CONFIRMED] "The annotation as written" in the refusal is unpinned
- **Where:** `:236` (the text), the row asserts `:919-920`.
- **Failure scenario:** mutant A6 (`text = ''`) survives both eras; the refusal then reads
  `other: '': does not resolve: NameError: …`, naming the annotation neither as written nor as
  resolved.
- **Evidence:** `logs/demo-A6-{original,mutant}.json`.
- **Touches:** R3.

#### Equivalent mutants and coverage observations (not findings)
- Equivalent (reviewer): A7, G8 (= the sweep's W16), RS3, I5 (= the sweep's E22), I9, each with its
  reason in `logs/mutants-summary.txt`.
- Coverage observations, none breaking an R-ID check on reachable input: S8, S9, S10, N2, N6, A5
  (only add refusals); WM4 (fails closed); V9 (keeps only the first reason, still named); I8, I12
  (failed-import naming precision, still red); I11 (unreachable guard); MC7 (a file shadowed by a
  builtin module is never loaded); WR6 (stops at a member's first refusal, still red). TT1 (the tree
  test's `violations == []` removed) is pinned only by `seen_red.sh`, outside the module. Not seeded
  separately: the routing below re-judges them.

### Routing (to `code build`)

Route each as its property over its whole domain; the instances above are examples.

- **Structural first (N3, N1, part of N4):** the tree test's expected positions come from the reader
  it checks, one decision computed once and graded against itself. Give the tree test an oracle
  independent of the syntax reader: what Python itself keeps at run time on every module-level
  object it can reach (module, class and function `__annotations__`, classes built by functional
  forms), compared with the positions the reader found, so a position Python keeps and the reader
  missed is red. Then the sweep.
- **N1:** every functional class form whose annotations Python keeps is read in every syntactic
  context, or, where reading needs dataflow (fields in a variable, `dict(...)`, an aliased
  factory), the check refuses it as unreadable instead of passing it. Never a silent pass. Name the
  completeness side too: a one-name assignment and a class body stay read. `AGENTS.md`'s entry
  describes exactly what is read.
- **N2:** the check accepts every valid type expression Python's own tools accept in its position,
  `KW_ONLY` included, and keeps refusing every non-type; a planted row for each side.
- **N3–N7 (surviving mutants):** a module-wide sweep over every decision in
  `tests/test_annotations.py`, additive mutants included, generated over the whole domain of each
  property (every position kind and function and class shape, every block kind, every
  functional-form spelling and import source, every type-expression form and qualifier, every
  binding form for shadowing, every exception class at resolution and at import, every field of the
  refusal line), each run in both eras. Every survivor is killed by a named row or recorded
  equivalent with the reason. A listed sweep that is all killed is not the closure criterion: the
  domain enumeration is.

### Human-gate triggers

- Not triggered. Every finding sits in `tests/test_annotations.py` and the `AGENTS.md` § Testing
  entry; neither is on § Invariants' high-blast-radius list, and none violates a `[human gate]`
  section.

### Convergence

- Cycle 2 of ≤3 does not converge: cycle 1's routed classes F3–F5 are only partly closed, and the
  same open-ended class (an under-reading reader, unpinned forms) reappears wider. Escalated to the
  maintainer before a third build round.
