# PLAN — Nothing would catch the next silently wrong annotation

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Lean path (`appetite: small`): no
> `research/`; the rabbit holes below were settled by a prototype and its dry runs.

## 1. Summary

One new test module, `tests/test_annotations.py`, in the collected suite. It reads every module
under every workspace member's `src/` as a syntax tree, lists each annotation Python keeps at run
time, evaluates each one the way `typing.get_type_hints` evaluates a postponed annotation, and
refuses any that does not resolve or resolves to something other than a type expression, naming
module, line, qualified name and the text as written. It lands in the suite's last command in each
era, which CI already mirrors, so it adds no gate command, no workflow step and no dependency
(stdlib `ast`, `tomllib`, `typing` only). Nothing under `src/` changes.

## 2. Design

**Placement.** `tests/test_annotations.py` is a new module, so it runs in the fourth suite command of
each era (`--ignore` of the four named modules) with no edit to the profile's `verify`, the recipe's
`gate`, `tests/test_suite_parts.py` or `.github/workflows/ci.yml` (§ Conventions, "CI mirrors the
gate"). It touches neither `tests/mutants.py` nor `tests/test_hygiene.py` (sibling cycles hold
them); it must pass `test_hygiene.py`'s rails (no spec ids, launches only through `bin/sandbox.sh`,
no skips, no stack import).

**Discovery (R4).** `workspace_members(root)` reads the root `pyproject.toml`'s
`[tool.uv.workspace]` `members` globs (and `exclude`), keeps each directory holding a
`pyproject.toml`, and adds the root. `member_modules(member)` lists every `*.py` under
`<member>/src/`, dotted from `src/` (`__init__` dropped). A member other than the root with no `src/`
is refused (its modules could not be found, so it would otherwise pass unread). No member or module
name is written in the check. A test holds the discovered members' project names equal to `uv.lock`'s `[manifest] members`,
so a misread glob cannot shrink the set unseen.

**Positions (R1, Q1).** `annotation_positions(source, module, path)` walks the module's syntax tree:
- module and class bodies (descending into `if`/`try`/`with`/`for`/`while`/`match` blocks, which keep
  their annotations in the enclosing scope): every `AnnAssign` whose target is a plain name
  (`simple`), as a *variable* (module) or *attribute* (class, qualified `C.D.x`), classes defined
  inside a function included;
- the functional forms `X = TypedDict('X', {...})` and `X = NamedTuple('X', [...])` (a call whose
  function's name is `TypedDict` or `NamedTuple`, with a literal dict or list of pairs): each value,
  as an attribute `X.field`;
- every `def`/`async def`, at any depth, nested functions and methods included: each annotated
  parameter (positional-only, positional, `*args`, keyword-only, `**kwargs`) and the return,
  qualified `C.m(x)` / `f.g() ->`;
- not the body of an `if TYPE_CHECKING:` (or `typing.TYPE_CHECKING`) block, which never runs, so
  nothing in it is kept (Q2 still bites: an annotation *outside* it that needs a name imported
  only inside it does not resolve);
- not a function body's own variable annotations (never evaluated, Q1), not an `AnnAssign` to an
  attribute or subscript (never kept).

Reading the source, not run-time objects, is what clears the GOAL's trap: a `NamedTuple`'s
synthesized `__new__` (and a dataclass's `__init__`) is not in the source, so it is never read. It
also means a decorator that replaces a function hides nothing: every tool is a FastMCP
`FunctionTool` in its module's namespace, so a sweep over module attributes (the shaping sweep)
never reached a single tool signature.

**Evaluation (R1, R2).** Each position's text is evaluated as `typing.get_type_hints` evaluates a
postponed annotation, through `typing.get_type_hints` itself on a holder carrying that one string:
a module-type holder for variables and attributes (`Final` and `ClassVar` allowed), a function
holder for parameters and returns. The globals are the imported module's; a class attribute's
locals are its class's namespace (the class reached by its qualified name from the module, which
must be a class whose `__qualname__` and `__module__` are that name and module: a rebound name or a
decorator that returns something else is refused, never evaluated in a foreign namespace; a class
defined inside a function has no reachable namespace, so its attributes see the globals alone); the
type parameters in scope (PEP 695, from the syntax tree) are bound as
fresh `TypeVar`/`ParamSpec`/`TypeVarTuple`. Nested string forward references resolve as
`get_type_hints` resolves them; any exception (`NameError`, `SyntaxError`, `TypeError`) is a
refusal naming it (R2).

**Scope-dependent annotations (R1).** Evaluating as postponed is what `get_type_hints` and FastMCP
do, but a module without `from __future__ import annotations` is evaluated by Python itself with
PEP 649 scoping: a method's annotation sees its class's names, and a nested function's sees its
enclosing function's. Where the two disagree the check could read a different object than Python
keeps (the reviewer's planted `Mode = dict[str, int:]` in a class body shadowing a global `Mode`
stayed green). So an annotation that reads a name bound in an enclosing class body or function
(assigned, imported, a `def` or `class` name, a parameter) is refused as scope-dependent, naming the
name, whatever the module's mode; so is a class-inside-a-function attribute reading a name its class
body or function binds. The current tree has none (scanned), so this refuses only code whose meaning
depends on postponement.

**Validity (R1).** `type_expression_violations(hint, kind)` walks the resolved hint, comparing
special forms by identity (`P.args` and a list argument are unhashable; a set lookup crashed the
whole sweep in review): `None`, classes, `TypeVar`/`ParamSpec`/`TypeVarTuple`, `P.args`/`P.kwargs`,
and the bare forms `Any`, `Never`, `NoReturn`, `Self`, `LiteralString`, `TypeAlias` are types; a
`TypeAliasType` is walked into its `__value__` and a `NewType` into its `__supertype__` (each once:
a recursive alias is not walked twice); bare `typing.Union`, `Optional`, `Literal` and the other
unsubscripted special forms are not types; `Annotated` checks its first argument, and refuses a
`slice` among its metadata (`Annotated[int, Field(...):]` drops the field's description silently,
the same defect class); `Literal` arguments must be literal values (int, str, bytes, bool, None,
enum members); `Callable` and `Concatenate` take `...`, a `ParamSpec` or a list of types, and a list
argument is accepted only there or in a user generic whose parameters include a `ParamSpec`; a
qualifier is valid only at the top, and only in its kind of position (`Final`, `ClassVar`,
`TypeAlias` on a variable or attribute; `Required`, `NotRequired`, `ReadOnly`, `InitVar` on an
attribute; none on a parameter or return); `...` only as `tuple[X, ...]`; every other subscript
checks each argument. Anything else (a `slice`, a number, a function, a leftover string or
`ForwardRef`) is named with its type and repr. An exception raised while validating is itself a
refusal of that position, never a crash of the sweep.

**Import (R2, R3).** A module with no positions is never imported (`__main__.py` runs the server
on import). A `__main__` module with positions is refused, every position named, as one the check
cannot evaluate without running the program. Every other module is imported by name, and its
`__file__` must be the file parsed (else refused: a stale install would check one tree against
another's source). A module whose import raises is refused naming the exception; the innermost statement its
frame stopped at (found from the traceback's module frame, matched by resolved file path) has its
positions evaluated in the namespace the module had reached (a class attribute's locals from the
class-body frame in the same traceback, when there is one: a pydantic model rejects a slice field
while its class is built), so a slice in a tool signature, which FastMCP's decorator raises
on before the module finishes importing, is still named by parameter (measured: a slice in
`scontrol_show_job(job_id)` fails the import with pydantic's schema error).

**Output (R3).** One line per refusal: `{module}:{line}: {qualified name}: {text as written!r}:
{why}`, `why` giving what it resolved to (`resolves to a slice, not a type: slice(...)`) or why it
did not resolve.

**A fresh interpreter for the tree (R1, R5).** The check over the real tree,
`test_every_kept_annotation_in_the_workspace_is_a_type` (`integration`), runs
`workspace_violations(ROOT)` in a child interpreter, `[str(SANDBOX), sys.executable, '-I', '-c',
CHILD, str(ROOT)]`, which imports the check from `tests/` and prints JSON (members and their
modules, positions checked, violations). It starts in a session of its own and, on timeout, its whole
process group is killed: `bin/sandbox.sh` does not `exec`, so killing only the `sh` would orphan the
interpreter. In process, the unit guard replaces `subprocess.Popen`
during a `unit` test, and `executor/launch.py`'s two `subprocess.Popen` annotations resolved to the
guard's refuser function (measured: a false red). The parent asserts no violation, that every member
with a `src/` contributed a module, and that `cluster_mcp.core.auth`'s `AUTH_MODES` is among the
positions checked.

**Functional forms.** They are recognised by the called name, `TypedDict` or `NamedTuple`, bare or
as an attribute, or an alias a `from … import TypedDict as X` gave it; a name rebound any other way
is not recognised (none in `src/` uses the functional forms at all).

**Controls (`unit`, in process).** A `scratch` fixture plants workspaces under `tmp_path` (a root
`pyproject.toml` with `[tool.uv.workspace]`, members with their own `pyproject.toml` and `src/`),
prepends their `src/` to `sys.path`, and forgets every module imported afterwards. Package names are
unique per case, so nothing collides with `cluster_mcp`. They cover: a slice in each kind of
position (variable, attribute, nested attribute, a class inside a function, a functional
`TypedDict` and `NamedTuple`, parameter of each kind, return, async return, method parameter and
return, static method, nested function, a function a decorator replaced, a conditional block),
postponed and eager; the scope-dependent shapes (a class-body alias shadowing a global, read by a
method; an enclosing function's local read by a nested function; a rebound class name; a
decorator returning a non-class), refused; a qualifier in the wrong kind of position; a slice in
`Annotated` metadata, inside a `type` alias's value and a `NewType`'s supertype;
a variable declared only under `if TYPE_CHECKING:`, not read; unresolvable names (undefined, `TYPE_CHECKING`-only,
`int | "str"`, a malformed string, a nested forward reference); a failed import naming the
statement that raised, with no spurious line when its annotations are good; the valid shapes
(`Annotated` with a value, `Literal`, `Callable` forms, `Concatenate`, `tuple[int, ...]`,
`tuple[()]`, PEP 695 functions and classes, `Self`, `Final`, `ClassVar`, `InitVar`, a `NamedTuple`
with a forward reference, a dataclass, a `TypedDict`, a `Protocol`, a class-scope alias), each mode,
`P.args`/`P.kwargs` in a PEP 612 decorator, with an exact position count; a `__main__` module never imported (it raises `SystemExit` on import)
and one with an annotation refused; a member added later, and an excluded one; a module imported
from elsewhere (`json.py` in a scratch member); a member with no `src/`; a failed import inside an `if` block naming only
the statement that raised, and a pydantic-style class whose slice field fails the import, named as
a slice; and a table of resolved non-types for `type_expression_violations`, unhashable ones
included.

**Test ids are a contract** (§ Testing): the gates name them (`verify/gate.sh` → `IDS`).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `annotation_positions` (every kept position, by syntax tree) · `_resolved` (as `get_type_hints`) · the scope-dependence refusal · `type_expression_violations`; controls `test_a_planted_slice_is_refused_naming_where`, `test_a_scope_dependent_annotation_is_refused`, `test_non_types_are_named`, `test_valid_shapes_pass` |
| R2 | any exception while resolving is a refusal; a failed import and an unreachable class are refusals; `__main__` with annotations refused; `test_an_unresolvable_annotation_is_refused` (`TYPE_CHECKING`-only included), `test_a_failed_import_names_the_statement_that_raised` |
| R3 | the refusal line (module, line, qualified name, text, what it resolved to or why not); asserted by every control and by `verify/seen_red.sh`'s output match |
| R4 | `workspace_members` / `member_modules` from `[tool.uv.workspace]` and `src/`, a member without `src/` refused; `test_a_member_added_later_is_checked`, `test_an_excluded_member_is_not_checked`, `test_a_member_without_src_is_refused`, `test_the_members_are_the_locked_workspace` |
| R5 | `verify/seen_red.sh`: a scratch copy of the committed tree, green unplanted, then red naming the position for a slice in each of 16 kinds of position in `core/auth.py` (postponed; the historical `AUTH_MODES` defect added) and the same 16 in `rcac/resources.py` (eager), and in a `slurm/tools.py` tool's parameter and return: 35 plants |
| R6 | a new module in the collected suite: the fourth command of each era runs it, and CI with it, with no edit; stdlib only, no network, no cluster (the child is local and sandboxed); CI budget figure in § 5 |
| R7 | `verify/gate.sh static`: only `tests/test_annotations.py`, `AGENTS.md` (outside § Factory), `spec/annotation-check/`, and a seed with its ROADMAP entry may change; `test_served_surface_matches_baseline` runs in P1; the tree check passes today, so nothing needs reporting |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before the design (gate #1) and against the drafted design (gate #2).

- **High-blast-radius paths** — none is edited. The check imports `core/auth.py`, `capabilities.py`,
  the `capability.py` and `instructions.py` files and the rest read-only, in a child or (for scratch
  modules only) in process. Research trigger 2 does not fire.
- **§6 Auth** — `AUTH_MODES`'s exact-shape pin in `tests/test_auth_modes.py` stays (a non-goal), and
  P1 runs it; the general check adds a positive anchor that `AUTH_MODES` is among the positions read.
- **§7 Tool registration** — the tree check imports each member's tools module in a child
  interpreter, so the suite's `TOOL_REGISTRY` is never touched; the controls import only scratch
  packages, which register nothing.
- **§9 Agent-facing surface** — unchanged: no `src/` edit, the fixture untouched, the baseline test
  run in P1 (R7).
- **§ Conventions, CI mirrors the gate** — no list changes: a new module joins the fourth command,
  as the rule intends; `test_suite_parts.py` runs in P1.
- **§ Conventions, tests** — every test carries `unit` or `integration`; the gates name test ids, not
  a marker selection; the only launch is through `bin/sandbox.sh`; no spec id appears in the module.
- **§ Conventions, comments** — declarative sentences; the AGENTS.md § Testing entry points to the
  module, not restating rules.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| The tree check is an `integration` test that starts a child interpreter through `bin/sandbox.sh`, though it drives no CLI. | In process, the unit guard replaces `subprocess.Popen` and the other launch and network entry points during a `unit` test; `executor/launch.py`'s `subprocess.Popen` annotations resolved to the guard's refuser (measured, two false refusals). A fresh interpreter also makes the answer independent of test order. | An in-process `unit` test is red on the current tree. Evaluating at collection time escapes the guard but depends on what modules collected earlier did. `integration` without a child escapes the guard but still reads a namespace other tests may have touched. The marker's wording is the open seed `issues/integration-marker-wording.md`, which this test joins (no edit to `pyproject.toml` here). |
| A module whose import raises is refused, and the statement it stopped at is checked in the partial namespace (about 20 lines). | R3 asks for the annotated name; FastMCP's tool decorator builds a schema at import and raises on a slice in a tool signature, so without it the only line would name the module and pydantic's error. | Reporting the import failure alone names no parameter (R3 unmet for tool signatures, the served schemas R7 is about). |
| A class reached by its qualified name must be that class (`__qualname__`, `__module__`), and a class-body name is refused when it is not; a function-local class's attributes see the globals alone. | A rebound name evaluated `C.x` in another class's namespace and passed (review); a function-local class has no namespace the check can reach. | Taking whatever the name holds is a false green; refusing every function-local class attribute would refuse valid code. |
| A `__main__` module that holds an annotation is refused as unresolvable, every position named, without being imported. | Importing `cluster_mcp.core.__main__` starts the server; the check cannot evaluate its namespace without running the program. It holds no annotation today, and a module with none is never imported. | Skipping `__main__` silently would leave a hole R4 forbids; importing it runs the server. Reading of R2 for sign-off: "cannot be resolved" includes "cannot be evaluated without running the program". |
| Every annotation is evaluated as a postponed one, and one whose names an enclosing class body or function rebinds is refused as scope-dependent, in either mode. | One rule for postponed and eager modules, matching `get_type_hints` and FastMCP; the refusal closes the gap where eager PEP 649 scoping would read a different object (the review's shadowed `Mode` stayed green before it). | Mirroring PEP 649 scoping needs run-time function objects, which a replacing decorator hides. Evaluating as postponed without the refusal is a false green on shadowed names. The cost: a scope-dependent annotation Python resolves to a type is refused too (none today, scanned); its fix is a module-level alias. |

Each row read against the R-IDs it touches: rows 1 and 2 meet R1, R3 and R6 as worded; rows 3 to 5
refuse more than R1/R2 strictly require, never less, and R5's "passes on the current tree" holds
(measured after the fold). Row 4's reading of R2 (`__main__`) is put to the sign-off.

## 4. Rabbit holes (resolved)

Settled by a prototype in a detached worktree (removed before report; the design above carries
everything it established), not by research briefs.

- **Does a postponed slice really resolve silently?** Yes, on 3.14.6: `typing.get_type_hints`
  returns `Final[slice(Dict[str, int], None, None)]` for both holder kinds, and `3` for `3`; it
  raises `NameError` for an undefined name, inside `list["Missing"]` too.
- **The NamedTuple trap.** `get_type_hints(_Entry.__new__)` raises `NameError: name 'str' is not
  defined`; reading the source never reaches it (green tree).
- **Tool signatures are invisible to an attribute sweep.** Tools are `FunctionTool` objects; the
  shaping sweep's 944 annotations included no tool parameter. The syntax tree reaches them.
- **The unit guard answers for `subprocess.Popen`** in process: the fresh child (row 1).
- **A slice in a tool signature fails the import** (pydantic): the partial-namespace fallback (row 2).
- **`InitVar`** resolves to a `dataclasses.InitVar` instance, not a type: allowed as a qualifier.
- **Dry runs**, each on a prototype tree cut to its phase, with the `verify/` copy in this cycle's
  tree run by absolute path:
  - before the review: P1's gate green in 62 s (16 plants); a validator mutant that accepts
    everything turned `seen_red.sh` red at its first case; the profile's full `verify` green on the
    P2 tree, all eight suite commands, 1,586 s wall (26.4 min). Its exit status was 1 for a reason
    outside the suite: `gate.sh` was edited while it ran, and sh read the new bytes at the old
    offset. Both scripts now run as one `main` called on their last line.
  - after folding the review: P1's gate green in 113 s (87 tests in the module, each era; 35 plants
    seen red); `gate.sh phase` green on the P2 tree (static, docs, ledger with 0 deferrals); the
    full `gate.sh P2` on that tree green, exit 0, 1,542 s wall (25.7 min), every suite command of
    both eras passing (the fourth: 4,398 passed, 14 skipped, 201 s legacy and 192 s modern, against
    209 s for each before the fold's 30 extra tests: within run-to-run noise). It ran through an
    edit of `gate.sh` made mid-run, which the `main` wrapper absorbed.
  - the fold itself was caught twice by the prototype: the parameter lookup for list arguments read
    `Union`'s `__parameters__` descriptor and raised on every `X | None` (each one a named
    per-position refusal, so the tree test went red rather than crashing), and a planted
    `TypedDict` imported under an alias stayed green (aliases imported from `typing` are now read).
- **Adversarial review** (trigger 3): see § 4a.

### 4a. Adversarial design review

One fresh reviewer ran (trigger 3) over GOAL, the drafted design, the prototype and `verify/`, in
a lab of its own, and returned 14 findings; every one is folded above:
- HIGH, a false green: eager PEP 649 scoping read a class-body or enclosing-function name the
  postponed evaluation did not (the scope-dependence refusal; the last deviation row rewritten).
- MEDIUM–HIGH, a crash naming nothing: `P.args` and list arguments are unhashable, and the
  validator's set lookups raised out of the sweep (identity comparisons; validator exceptions are
  per-position refusals; `P.args` in the valid control).
- MEDIUM: function-local classes' attributes were never read (now read); a rebound class name
  evaluated in another class (now refused); the import-failure fallback took the whole top-level
  compound statement, gave a spurious line, matched frames by unresolved path, and named a pydantic
  field as an unreachable class, not a slice (innermost statement, resolved paths, the class-body
  frame); `seen_red.sh` planted only 7 kinds in the tree (now 16 in each of the two modules, plus a
  tool's return: 35 plants); validator leniencies (`type` alias values, slices in `Annotated`
  metadata, qualifiers in the wrong kind of position, `NewType` supertypes) closed; `gate.sh static`
  missed a file renamed out of `packages/` (`--no-renames`); the ledger missed this plan's own
  wording and tolerated a missing TECH.md (keys widened, files required).
- LOW: variables declared only under `if TYPE_CHECKING:` were refused though never kept (skipped);
  functional `TypedDict`/`NamedTuple` were not read (now read); a timed-out child would be orphaned
  (own session, group kill); `gate.sh` resolved its own directory after `cd` (before, now); the
  docs check matched words anywhere in § Testing (anchored to the entry).
Found sound: `match`/`except*` blocks, PEP 695 class parameters flowing into methods, multi-line
annotations, nested string references, generic arity errors, a tool's return slice (imports and is
named), the `full` mode's extraction of exactly the profile's verify, and the child test's anchors
against a vacuous pass.

## 5. Risks & open questions

- **CI budget (R6), a figure for the maintainer.** The module runs in `suite-legacy-4` and
  `suite-modern-4` only. Locally it takes about 1.7 s per era (the child about 1.4 s of it; 3 s wall
  with `uv run` and pytest start-up). Baselines 7:22 and 7:33 against the 10-minute budget; even at
  three times the local cost on a hosted runner the jobs stay near 7:27 and 7:38. In the full local
  run the fourth command's time did not measurably move (§ 4, dry runs). The `gate` job
  gains nothing (no new command). Graded at publish against the cycle branch's CI run; no phase
  depends on hosted CI.
- **Outside the GOAL's scope:** a `type X = …` alias that no annotation uses, and a type
  parameter's bound (neither is an annotation); function-local variable annotations (Q1); `tests/`,
  `bin/`, `spec/` (non-goals).
- **Arity of user generics** is left to `get_type_hints`, which refuses a wrong count at evaluation
  (reviewer, observed).
- **Overlap:** `issues/integration-marker-wording.md` (the marker's wording; this test is one more
  integration test that drives no CLI). No overlap with `tests/mutants.py` or `tests/test_hygiene.py`.

## 6. Verification strategy

- **P1** (`sh spec/annotation-check/verify/gate.sh P1`): the cycle's footprint (`static`), the lock,
  the named test ids in both eras, the whole module in both eras with its wall time printed, the
  rails it must keep (`test_hygiene.py`, `test_suite_parts.py`) and the exact-shape pin
  (`test_auth_modes.py`), the served-surface baseline, and `verify/seen_red.sh` (R5).
- **P2** (`sh spec/annotation-check/verify/gate.sh P2`): `static`, AGENTS.md § Testing naming the
  module and its check functions, the deferral ledger, then the profile's full `verify`, read from
  AGENTS.md at run time (about 26 min; run it in the background). `gate.sh phase` is P2 without the
  full run.
- No CLI behaviour changes, so there is no CLI drive beyond the profile's `bin/sandbox.sh uv run
  cluster-mcp --help`, which the full `verify` runs.
