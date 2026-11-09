# PLAN — The static skip check catches the skips it admits today

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). No `research/`: the lean path
> (`appetite: small`, root cause known), with the adversarial review trigger 3 makes mandatory.

## 1. Summary

Tighten `skip_violations` in `tests/test_hygiene.py` in two independent places: *where* a skip is
allowed (only inside the single top-level `def` of `need_shell` / `need_git` in the suite's
`conftest.py`, found by path equality, not a suffix) and *what* the `.Exception` exemption covers
(only a skipper's `.Exception` read as a value, never inside a `raise`). Each shape gets planted rows
in `test_skip_check_catches_planted_skips`, and a cycle gate (`verify/planted-rows.py`) proves the new
check meets every row and reports nothing in the suite, and that every new row is a gap the base
check had. Nothing else changes: no other file in `tests/`, no package
code, no AGENTS.md text (its § Testing statement stays true as written).

## 2. Design

All changes sit in `tests/test_hygiene.py`, in the block from the `SKIPPERS` comment to
`test_skip_check_catches_planted_skips`. `SKIPPERS`, `SKIP_HELPERS`, the function's name, signature
(`skip_violations(name: str, text: str) -> list[str]`) and its `name:line: word` report format stay.

**Which module is conftest (R3).** A module-level `CONFTESTS = {Path('conftest.py'), TESTS / 'conftest.py'}`:
`Path(name) in CONFTESTS`. The second member is the path `test_only_need_shell_skips` reads the real
file from (`str(f)` for `f` in `TESTS.glob('*.py')`, `TESTS` already resolved); the first is the bare
name the existing planted rows pass, standing for the same file (deviation 1). `tests/test_conftest.py`,
`elsewhere/conftest.py` or any other path is a different module, so no helper is allowed there.

**Where a skip is allowed (R1, R2, R5).** A helper `_allowed(name, tree, found) -> set[int]` returns
the `id()`s of the nodes a skip may sit in, replacing today's line-number set (a line set lets
anything sharing a line with an allowed node through; node identity does not):

1. Not conftest → empty.
2. For each helper name, collect its **module-scope bindings** (`_module_bindings`): a walk from
   `tree.body` that records `def` / `async def` / `class` names, `Name` stores and deletes, import
   aliases (`asname`, else the first dotted part), `except … as`, `match` captures, and does not
   descend into function, class or lambda bodies; plus every `global` naming the helper anywhere in
   the file (it rebinds the module name from inside a function).
3. More than one binding → append `name:line: <helper> defined again` for each binding after the
   first (by line) and allow nothing for that helper (R2: a violation even when the second definition
   holds no skip, deviation 2).
4. Exactly one binding, and it is a `FunctionDef` that is a direct member of `tree.body` → allow
   every node inside its **body** statements (not its decorators or defaults). A single binding that
   is a lambda, an `async def`, a class or a `def` under an `if` allows nothing.
5. Then subtract every node inside any `def` / `async def` / `class` whose name is a helper name and
   which is not a direct member of `tree.body`: a nested or method definition of an allowed name is
   never a helper, even inside the top-level one (R1). A closure of another name inside the helper
   stays allowed: the helper is still the one deciding (deviation 3).

**What counts as a skip (R4, R5).** The loop over `ast.walk(tree)` is unchanged in what it matches
(a `Name` or `Attribute` whose word is in `SKIPPERS`); only the exemption narrows. Today any skipper
that is the `.value` of *any* attribute is exempt. Now a skipper node is exempt only when its parent
is an `Attribute` with `attr == 'Exception'` whose node is **not** inside the exception expression of
any `raise` (`Raise.exc`'s subtree; the `from` cause is not raising). So `pytest.skip.__call__(...)`,
`pytest.mark.skip.with_args(...)`, `raise pytest.skip.Exception(...)`, `raise pytest.xfail.Exception`,
`raise skip.Exception('x').with_traceback(None)` are reported, and `pytest.param(..., pytest.skip.Exception)`,
`pytest.raises(pytest.xfail.Exception)`, `raised = pytest.skip.Exception` are admitted.

**Docstring.** `skip_violations`'s docstring names what it cannot see, as `stack_import_violations`'
does: lookups by string (`getattr`, `vars`, `globals()`), a skipper or outcome type carried through
a name, container or argument (raised later, or subclassed: `class S(pytest.skip.Exception)`), a
star import, unittest's spellings, and pytest's private outcome classes (the GOAL's non-goals, plus
§ 5's Q1 if the sign-off seeds it).

**Planted rows (R6).** Appended to `test_skip_check_catches_planted_skips`'s list after
`outcome-type`; every existing row is kept byte-for-byte. Ids carry no spec-id pattern (§ Conventions).

| Phase | id | name | found | shape |
|---|---|---|---|---|
| P1 | `helper-nested-in-a-fixture` | `conftest.py` | yes | `need_shell` def inside a `@pytest.fixture` |
| P1 | `helper-as-a-method` | `conftest.py` | yes | `need_git` method of a top-level class |
| P1 | `helper-nested-in-the-helper` | `conftest.py` | yes | `need_shell` def inside the top-level `need_shell` |
| P1 | `closure-inside-the-helper` | `conftest.py` | no | a closure of another name inside `need_shell` skips |
| P1 | `helper-defined-twice` | `conftest.py` | yes | two top-level `need_shell`, both skipping |
| P1 | `helper-redefined-without-a-skip` | `conftest.py` | yes | second top-level `need_git` holds no skip |
| P1 | `helper-rebound` | `conftest.py` | yes | `need_git = print` after the def |
| P1 | `helper-rebound-by-global` | `conftest.py` | yes | a function rebinds `need_git` through `global` |
| P1 | `helper-rebound-by-import` | `conftest.py` | yes | an import binds `need_shell` after the def |
| P1 | `helper-below-the-top-level` | `conftest.py` | yes | `need_git` defined under `if True:` |
| P1 | `look-alike-conftest` | `tests/test_conftest.py` | yes | top-level `need_shell` that skips |
| P1 | `another-conftest` | `elsewhere/conftest.py` | yes | top-level `need_shell` that skips |
| P2 | `skip-through-an-attribute` | `t.py` | yes | `pytest.skip.__call__("x")` |
| P2 | `mark-through-an-attribute` | `t.py` | yes | `@pytest.mark.skip.with_args(...)` |
| P2 | `raised-skip-outcome` | `t.py` | yes | `raise pytest.skip.Exception("x")` |
| P2 | `raised-xfail-outcome` | `t.py` | yes | `raise pytest.xfail.Exception("x")` |
| P2 | `raised-outcome-type` | `t.py` | yes | `raise pytest.skip.Exception` (uncalled) |
| P2 | `raised-outcome-of-a-bare-skip` | `t.py` | yes | `from pytest import skip`; `raise skip.Exception("x").with_traceback(None)` |
| P2 | `outcome-type-as-an-argument` | `t.py` | no | `pytest.param(None, pytest.skip.Exception)` |
| P2 | `outcome-type-caught` | `t.py` | no | `with pytest.raises(pytest.xfail.Exception):` |

A prototype of exactly this design (P1's tree, then P2's) passed the gate's modes and controls,
`tests/test_hygiene.py` whole in each era (104 passed), and the profile's full `verify` once (§ 6).
**The tightened check flags nothing in the suite as it stands**: `test_only_need_shell_skips` passes
on the prototype, and a direct run over the real `tests/conftest.py` reports nothing.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `_allowed` steps 4–5: only a direct `tree.body` `FunctionDef`'s body is allowed; nested and method definitions of a helper name are subtracted. Rows `helper-nested-in-a-fixture`, `helper-as-a-method`, `helper-nested-in-the-helper`, `helper-below-the-top-level` |
| R2 | `_module_bindings` + `_allowed` step 3: more than one module-scope binding reports `defined again` and allows nothing. Rows `helper-defined-twice`, `helper-redefined-without-a-skip`, `helper-rebound`, `helper-rebound-by-global`, `helper-rebound-by-import` |
| R3 | `CONFTESTS` path equality replaces `endswith('conftest.py')`. Rows `look-alike-conftest`, `another-conftest` |
| R4 | The exemption narrows to a skipper's `.Exception` outside every `raise`'s exception expression. Rows `skip-through-an-attribute`, `mark-through-an-attribute`, the four `raised-*` rows |
| R5 | The real conftest's single top-level `need_shell` and `need_git` still allow their bodies; `.Exception` as a value stays exempt. Rows `closure-inside-the-helper`, `outcome-type-as-an-argument`, `outcome-type-caught`, existing `need-shell`, `need-git`, `outcome-type`; `test_only_need_shell_skips` green on the suite |
| R6 | The 20 rows above: the new check meets each (the suite, and gate `meet`); each `found=yes` row is admitted by the base check (gate `bite`); each has the shape its id names (gate `rows`); every base row and both test bodies are kept (gates `kept`, `bodies`) |

## 3. Invariant gate (AGENTS.md constitution check)

Gate #1 (from the GOAL) and gate #2 (on this design) walk the same sections. The change touches no
package code, so numbered §§ 1–9 are untouched, and no path on the high-blast-radius list is touched
(trigger 2 does not fire). Sections walked:

- **§ Testing** (`tests/test_hygiene.py` bullet: "It and `conftest.need_git` are the suite's only
  skips … (`test_only_need_shell_skips`, static)") — still true as written; the design narrows what
  the check admits and adds no skip. No text change, so no same-commit obligation.
- **§ Conventions, markers** — no new test function; rows join an existing `@pytest.mark.unit` test.
  A helper function the build adds is not a test (no `test_` prefix).
- **§ Conventions, no spec ids in the suite** — the row ids and comments above carry none;
  `test_no_spec_ids_in_the_package_or_the_suite` is in every phase's `verify`.
- **§ Conventions, comments declarative; point to a rule, don't restate it** — the new comments state
  the why (what is allowed and why); the docstring's limits list is the check's own, not a restatement.
- **§ Conventions, CI mirrors the gate** — no change to the suite's four-command partition: the rows
  run in each era's last command.
- **§ Factory, deferral homes** — § 5's Q1 is a deferral candidate with its destination named.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| 1. A bare `conftest.py` name counts as `tests/conftest.py` (R3) | The existing rows `need-shell` and `need-git` pass `'conftest.py'` and expect no report; R6 keeps their result, and the gate's `kept` check pins their text | Rewriting those rows to pass `str(TESTS / 'conftest.py')` changes existing rows for no gain; a suffix or basename test is what R3 forbids. The bare name cannot arise from the scan, which passes absolute paths |
| 2. R2's "defines" reads as any module-scope binding (def, class, assignment, import, `except as`, `match` capture, `global`), and a second binding is reported even with no skip in it | `need_git = print` after the def shadows the helper exactly as a second `def` does; the GOAL's Problem names shadowing | Counting only top-level `def`s (≈ 3 lines instead of ≈ 25) leaves assignment and import rebinding as open as today's second `def`. Rows pin the assignment, `global` and import forms; `except as` and `match` captures are counted but unpinned (§ 5) |
| 3. Inside the top-level helper, a closure of another name is admitted; a nested `def` of an allowed name is not (R1) | R1 reports a helper name "not a top-level definition"; the Outcome admits a skip "inside the single, top-level definition" — a closure is inside it | Reporting every nested function inside the helper would forbid a harmless refactor of `need_git` and is not asked for |

Each row read against R1–R6's wording: none narrows an R-ID; deviations 2 and 3 report a superset of
R2 and R1, deviation 1 keeps R5/R6.

## 4. Rabbit holes (resolved)

- **The suite might already hold a shape the tightened check flags** → no. The prototype's
  `test_only_need_shell_skips` passes; `tests/conftest.py` binds each helper once at top level; the
  suite's only `.Exception` uses are `pytest.param` arguments (`tests/test_hygiene.py`,
  `tests/test_registry.py`); no `raise` names a skipper; no import renames a skipper.
- **A planted row can pass while proving nothing** (it is caught by the base check for another reason,
  e.g. a nested helper planted in `t.py`, where every helper is already refused) → the gate's `bite`
  check runs the **base** `skip_violations`, extracted from the base commit's source, on every new
  `found=yes` row and requires it to admit the row; it first proves the extraction by checking the base
  check against every base row.
- **Adversarial review (trigger 3).** Ran once, appetite-scaled, against GOAL, this design, the
  prototype and the gate. Outcome: § 4a.

### 4a. Adversarial review

One fresh reviewer pass (≈ 25 crafted inputs against the prototype check, mutants against the gate).
The **check** held: no new skip it should report and admits, beyond the known "through a name"
family; it reports nothing over the real `tests/conftest.py`. The **gate** was where the findings
were. Every one is folded into `verify/planted-rows.py`, and each attack was re-run on the
prototype and is now refused:

- *HIGH, the fence missed renames* (`git mv tests/mutants.py spec/…` passed): the fence diff runs
  with `--no-renames`. Re-run: refused.
- *MEDIUM, any file under the spec passed the fence*, including a `conftest.py` that pytest (no
  `testpaths`) would collect from `spec/` and could deselect rows with: under `spec/{slug}/` the
  fence admits only `*.md` and `verify/planted-rows.py`. Re-run: refused.
- *MEDIUM, the gate never ran the new check or pinned the tests* (`return []` in the check plus
  `== found or name` in the row test passed): new checks `meet` (the index's check, extracted with
  every top-level name it reaches, meets every row), `suite` (it reports nothing over the index's
  `tests/*.py`) and `bodies` (both tests match the base node for node, row list aside), and `kept`
  refuses any row keyword but `id`. Re-run: refused.
- *MEDIUM, the controls exercised one shape function*: the wrong-shape and already-caught controls
  now loop over every required row, and every required row has a shape.
- *LOW, loose or missing shapes*: `_raised` requires the raise's expression to be `X.Exception`, a
  call of it, or that call's `.with_traceback(...)`; every row has a shape; rows
  `helper-rebound-by-global` and `helper-rebound-by-import` added for deviation 2.
- *LOW, a history rewrite could move the base*: the base must be an ancestor of `origin/develop`.
- *LOW, subclassing the outcome type* (`class S(pytest.skip.Exception)`, then `raise S()`): not
  reported. R5 admits a reference to the outcome type that is never raised, so reporting a base
  class needs a GOAL ruling. Named in the docstring; joins § 5's Q1.
- *Note, possibly mis-drawn scope*: conftest-level deselection (`collect_ignore`,
  `pytest_collection_modifyitems`, `pytest.exit`) also makes rows vanish from CI and is statically
  visible, but it is not a skip. § 5's Q2.

## 5. Risks & open questions

- **Q1 (for the sign-off): two statically visible skips stay admitted, before and after this cycle.**
  (a) A skipper renamed on import: `from pytest import skip as go`, then `go("x")`, reports
  nothing, because the check reads `Name` and `Attribute` words, never an import alias. A static
  parse resolves it (`alias.name`), so it is not among the GOAL's dynamic-lookup non-goals, but no
  R-ID names it. (b) The outcome type subclassed, then raised (`class S(pytest.skip.Exception): pass`,
  `raise S("x")`). Reporting the base class would read against R5's "a reference to the outcome
  type as a value, never raised". The plan covers **neither**. Default destination: P2's ledger
  files `issues/skip-check-import-aliases.md` (`status: unshaped`, both shapes) and its
  `ROADMAP.md` entry beside this cycle's. Alternative: a GOAL clarification folds (a), or both, into
  R4, and P2 adds rows `skip-renamed-on-import` (and `outcome-type-subclassed`), a few lines each.
  The sign-off picks.
- **Q2 (for the sign-off): deselection is outside the GOAL.** `collect_ignore`,
  `pytest_collection_modifyitems` or `pytest.exit` in a conftest drop rows from a CI run as surely as
  a skip does, and are statically visible. They are not skips, so this cycle neither covers nor
  defers them; whether to seed a separate gate is the maintainer's call. The plan files nothing for Q2.
- **Outcome type raised through a name** (`exc = pytest.skip.Exception; raise exc("x")`) stays
  admitted: the raise is not direct, the R4 reading is "directly", and the existing row `outcome-type`
  (`raised = pytest.skip.Exception`) must keep passing. It falls under the GOAL's non-goal of values
  carried through names or containers; the docstring names it. Not a deferral.
- **Sibling cycles.** Two 0.2.0 cycles change `tests/mutants.py`, which the scan reads. If either adds
  a skip spelling this cycle now reports, `test_only_need_shell_skips` goes red on whichever lands
  second. The gate's `fence` forbids this cycle touching that file; a red after a rebase is a finding
  to report, not to exempt.
- **Over-report direction.** Deviation 2 counts a comprehension variable named `need_shell` at
  conftest's module scope as a binding. Red, never green; nothing in the suite does it.
- **Unpinned binding forms.** `except … as need_git` and `match` captures are counted by
  `_module_bindings` but have no row, so a build that drops those branches passes every gate. Low
  risk: neither form plausibly arises in a conftest, and the review grades the code against PLAN § 2.

## 6. Verification strategy

No CLI surface changes, so there is nothing to drive in the sandbox beyond the profile's last
`bin/sandbox.sh uv run cluster-mcp --help`, which the final phase's full `verify` runs.

- **`verify/planted-rows.py <mode>`** (`scope`, `spelling`, `all`; and `controls <mode>`), run with
  `uv run python -I` after staging. It reads `tests/test_hygiene.py` and every `tests/*.py` from the
  **index**, and `tests/test_hygiene.py` from the base (the parent of the commit that added this
  GOAL, which follows a rebase and must be an ancestor of `origin/develop`). It checks `fence`
  (renames off; only `tests/test_hygiene.py`, this spec's Markdown and the gate script, and ledger
  files `issues/*.md` / `ROADMAP.md` differ from the base; never `tests/mutants.py`; the working
  copy of the target matches the index), `bodies`, `kept`, `rows` (each required id present, a plain
  literal, with its pinned `found` and the shape its id names), `bite` (on the base check, extracted
  from the base's source and first proved against every base row), and `meet` and `suite` (on the
  index's check, extracted the same way). `controls` plants ≈ 50 mutations in memory and requires
  each to draw its own kind of refusal: each required row deleted, flipped, keyworded, of the wrong
  shape, or already caught by the base; a base row changed, gone or keyworded; a check on either
  side that reports nothing; a row test that asserts nothing; a suite module that skips. Footprint:
  one process, under 200 MB. Measured on mac-m2: a mode ≈ 1 s, `controls scope` 13 s.
- **The suite's own rows**: `uv run pytest -q tests/test_hygiene.py` in both eras (2 s and 5 s,
  measured on the prototype; the module includes `test_only_need_shell_skips`,
  `test_skip_check_catches_planted_skips` and `test_no_spec_ids_in_the_package_or_the_suite`).
- **Dry runs, on the prototype** (a throwaway clone under `$TMPDIR`, refreshed from `$WT`'s
  `verify/` before each run). Base tree: `scope` red (target unchanged, rows missing). P1 tree:
  `scope` and `controls scope` green, `spelling` red. P2 tree: `all`, `controls all` and
  `controls spelling` green, and `tests/test_hygiene.py` green in each era. Each of the reviewer's
  attacks (a staged rename of `tests/mutants.py`, a `conftest.py` under the spec, an emptied check
  with a loosened row test), an unstaged edit, and a staged `tests/mutants.py` edit each turn `all` red.
- **Full profile `verify`** (last phase), run once on the prototype's P2 tree, mac-m2: green in
  1,571 s (≈ 26 min). Handshake era 212 + 155 + 216 + 206 s, modern era 219 + 144 + 217 + 201 s;
  the last command of each era 4,329 and 4,331 passed with 14 skipped (`need_shell`: bash 4.1 or
  later is not installed on this host), the sandboxed `--help` green. The two rows
  `helper-rebound-by-*` were added to the tree while the handshake era's last command ran, so only
  the modern era's count includes them; `tests/test_hygiene.py` was re-run whole on the final tree
  in each era. The CI budget is unaffected: the new rows add well under a second to
  `suite-*-4`.
