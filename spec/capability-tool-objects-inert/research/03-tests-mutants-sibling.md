# Research 03 — tests, mutants, the prior cycle's gates, and the sibling

Read-only survey for the plan. Line numbers are at this worktree's base. Timings are local (macOS,
warm, one era).

## 1. `test_a_capability_that_cannot_load_is_refused_naming_it` (`tests/test_capabilities.py:1339-1355`)

- **Parametrisation:** `@pytest.mark.parametrize('names', MEMBER_SETS)` × `('kind', UNLOADABLE)`. Row id
  `<kind>-<set>`. `MEMBER_SETS` (`:667-672`) is `core-only`, `slurm`, `rcac`, `both` (`('rcac','slurm')`).
  Today 69 kinds × 4 = **276 rows**.
- **`UNLOADABLE`** (`:1335-1337`) = `<raised>-at-<when>` (8 `RAISED` × 5 `WHEN`) + `TIMING` (6) +
  `nameless-<k>` (3) + `subclass-reads-<field>` (`SUBCLASS_READS`, from `dataclasses.fields(Capability)`
  plus `nothing`) + `exact-<site>` (`EXACT_SITES`, from `fields(Capability)` and the core's own resource
  entry keys, so a later field or key gets a row on its own).
- **Builder:** `unloadable(kind: str) -> Unloadable` (`:1300`) dispatches on the prefix and returns
  `Unloadable(dist, entry, files, metadata, named, cause)` (frozen dataclass, `:1263`). Helpers:
  `package(module, *, tool='planted_echo', tools_tail='', **capability) -> dict[str, str]` (`:205`, a
  package whose `tools.py` is `ECHO_TOOL` + `tools_tail`); `subclass_files(module, field) ->
  tuple[dict[str, str], str]` (`:1145`); `exact_files(module, site) -> tuple[dict[str, str], str]`
  (`:1221`); `raising_files(module, statement, when)` (`:1276`).
- **Planting:** the `plant` fixture (`:166-196`) writes the files and a `<dist>-0.0.1.dist-info` under
  `tmp_path` (first on `sys.path`) and returns `Distribution.at(info).entry_points.select(group=GROUP)`.
  Teardown restores `TOOL_REGISTRY[:]` and drops every `sys.modules` entry whose `__file__` lies under
  `tmp_path`.
- **Assertions:** `message == f'cannot load capability {case.named}: {case.cause}'` (exact, so one line);
  `TOOL_REGISTRY == before` (the cut-back); and `_RAN`, read from **the entry point's module**
  (`case.entry.split(' = ')[1].split(':')[0]`, i.e. `<module>.capability`), is empty.
- **`OPERATIONS` / `PLANTED_TYPES`** (`:1164-1203`): `OPERATIONS` maps `'str'|'int'|'tuple'|'dict'` to every
  dunder and method the core, FastMCP and Python reach a value through. `PLANTED_TYPES` is source text
  defining `_RAN`, `_ARMED` and `_planted(base) -> type`, which builds `Planted<Type>` whose every listed
  operation appends to `_RAN` and raises `SystemExit(0)` once `_ARMED` is non-empty. `exact_files` puts
  `PLANTED_TYPES` into `capability.py` and makes `_ARMED.append(True)` its last statement.
- **Non-tool rows today:** `REJECTED['tool-not-a-tool']` (`NOT_A_TOOL`, `:604-613`, a plain function
  appended; in `test_what_a_server_would_refuse_is_refused_at_load`, `:684`), and `TIMING`'s
  `not-a-tool-from-the-entry-point` and `not-a-tool-from-tools-imported-by-the-entry-point` (`:1105-1108`).
  All three carry `loading it registered a function, not a FunctionTool`. Related: `REJECTED['tool-without-a-module']`
  (`fn.__module__ = None`), and the `declared` timing (`fn.__module__` set to a `str` subclass whose `==`
  runs the statement, `:1293-1296`). Both touch `fn`, which GOAL excepts, so they stay as they are.
- **A subclass of `FunctionTool` is already planted:** `ODD_TOOL` (`:1076-1093`), `_Odd(FunctionTool)`,
  running its statement when `version` is read. It is the carrier of the whole `served-tool` timing (8
  `RAISED` × 4 sets = 32 rows, cause `its tool 'planted_echo' cannot be served: …`). Under R1 these rows
  are refused at the exact-type check instead, so their cause changes. See the open questions.
- **How a new family slots in.** Add a prefix to `UNLOADABLE` and a branch to `unloadable()`, mirroring
  the record's two families:
  - `tool-subclass-reads-<field>`: generated from `FunctionTool.model_fields` (plus `nothing`), as
    `SUBCLASS_READS` comes from `fields(Capability)`. This gives the R4 property for free: a field
    FastMCP adds gets a row.
  - `tool-exact-<site>`: each field but `fn`, plus depth sites (a key or value of `parameters`, `meta`,
    `output_schema`, an element of `tags` and `icons`, each field of `annotations`, `execution`,
    `task_config`). Files come from `package(module, tools_tail=PLANTED_TYPES + <assignment> +
    '_ARMED.append(True)')`.
  - Facts measured here: `FunctionTool` has `validate_assignment` unset and `extra='forbid'`. So
    `planted_echo.name = PlantedStr(...)` after construction **keeps** the subclass, while
    `FunctionTool(**fields)` coerces `str` and `dict` subclasses back to `str` and `dict`. Plant R2 values
    by assignment (or `model_construct`), never by construction.
  - Two catches:
    - The test reads `_RAN` from the capability module. Either plant `PLANTED_TYPES` there (imported by
      `tools.py`), or widen the lookup.
    - `OPERATIONS` has no `list`, `set` or `float` (`icons`, `tags`, `timeout`), and no model types. `bool`
      and `None` cannot be subclassed.

## 2. `test_a_capability_that_cannot_load_stops_startup` (`tests/test_startup.py:720-728`)

- **Parametrisation:** `drive` ∈ `raw-wire`, `stdin-closed`, `http` × `kind` ∈ `UNLOADABLE if EVERY_KIND
  else CLI_UNLOADABLE`. `EVERY_KIND = os.environ.get('CLUSTER_MCP_TEST_EVERY_KIND') == '1'` (`:620`). The
  suite never sets it; spec checkers do.
- **`CLI_UNLOADABLE`** (`:631-633`, 10 kinds) includes `not-a-tool-from-the-entry-point`,
  `subclass-reads-commands`, `exact-order` and **`raises-base-at-served-tool`**, the `_Odd` carrier whose
  cause R1 changes.
- **Adding a kind:** append its `UNLOADABLE` id to `CLI_UNLOADABLE`.
  `test_the_cli_drives_name_kinds_that_exist` (`:637`) fails on a name not in `UNLOADABLE`. The drive
  reuses `plant_unloadable` (`:705`) and `refused_start_violations` (`:669`), so nothing else changes. R6
  needs at least one R1 kind and one R2 kind here.
- **Measured:** an in-process refused row takes **0.01–0.02 s** (12 rows, 0.55 s session). A startup row
  takes **1.04–1.22 s** (3 rows, 3.4 s session).
- **CI budget** (AGENTS § Factory `ci budget`): `test_startup.py` runs in `suite-*-3`, baseline 7:10 legacy
  and 7:34 modern against the 10-minute cap. `test_capabilities.py` runs in `suite-*-4`, baseline 7:22
  and 7:33. Each CLI kind adds 3 rows, about 3.5 s local or about 6 s CI per era. Two new kinds come to
  about 12 s CI. Forty new in-process kinds × 4 sets come to about 2–3 s.

## 3. `test_served_surface_matches_baseline` (`tests/test_surface.py:275-284`)

- Builds `create_mcp_server('none', site=SITE)` (every installed capability) and reads
  `served_surface(server)` through the harness client in the selected era. That is instructions,
  `tools{name: description, inputSchema, outputSchema[, annotations][, title]}` and
  `resources{uri: name, description, mimeType}`.
- `surface_violations(load_fixture(), served)` compares it with `tests/fixtures/served_surface.json`,
  minus the `TOLERATED` kinds. It also asserts that every tool has a `title`.
- R5 holds if this passes with the fixture unedited.

## 4. `tests/mutants.py` and `tests/test_mutations.py`

- **Anchor check:** `test_mutation_anchor_applies[<case>]` (`test_mutations.py:38-50`) calls
  `apply(case, tmp_path)`, which raises unless each edit's `old` occurs exactly once, then compiles the
  mutated file. A changed line turns the row red in the suite, fast (the sibling measured 287
  capability rows in 4.5 s). AGENTS § Testing says to re-plant the case in the same commit, and to
  record any retarget or removal in the commit body.
- **Cases anchored on `load()` `:320-345`** (36 of the 256 `core/capabilities.py` cases; 1165 in
  all). The ones that break on this change:
  - **The `isinstance` check `:330-332` (`odd`):**
    - `capability-non-tool-unseen` (:330), `capability-non-tool-allowed` (:331);
    - `capability-load-odd-always` and `-odd-negated` (:331);
    - `capability-load-odd-type-registry-before-isinstance-func-always`, `-never` and `-negated` (:330).
  - **`stray` and `tool.fn.__module__` `:333-335`:**
    - `capability-stray-unseen`, `capability-stray-allowed`;
    - `capability-load-stray-always` and `-negated`;
    - `capability-load-below-fn-module-capability-tools-always` and `-negated`.
  - **The `tools =` attribution `:341`:**
    - `capability-tools-only-from-the-import`;
    - `capability-load-tools-registry-below-fn-module-capabilit-always`, `-never` and `-negated`.
  - **The block `:324-329`:**
    - `capability-registrations-checked-from-after-the-entry-point-loads`;
    - `capability-registrations-checked-from-after-the-tools-module-is-imported`.
  - **Others in range, which break only if their lines move:**
    - `capability-tools-import-swallowed` (:329), `capability-load-failure-swallowed` (:326-328);
    - `capability-invalid-reported-as-exception`, `capability-load-invalid-*` (:327-328);
    - `capability-scratch-per-capability` (:319-321), `capability-load-nameless-*` (:322);
    - `capability-name-taken-allowed` and `capability-load-capability-names-*` (:338);
    - `capability-same-capability-duplicate-allowed` and `capability-load-any-other-tools-i-*` (:343).
- **Cases killed only by `served-tool` rows** (their targets die when R1 refuses `_Odd` earlier):
  - `capability-load-tool-assembly-interrupt-clause-exception` and `-baseexception`;
  - `capability-load-tool-assembly-clause-exception` and `-re-raises`;
  - `capability-tool-assembly-dropped`.

  `capability-load-odd-type-registry-before-isinstance-func-never` and the two
  `registrations-checked-from-*` cases target `not-a-tool-from-the-entry-point` (its cause text
  matters).
- **Completeness:** nothing in the suite requires a case per decision. The sweeps are spec checkers:
  - `spec/capability-extras/remediation/F7-mutant-alternatives.py` parses every decision of
    `core/capabilities.py` into its alternatives (always, never and negated; each operand alone and the
    other operator; comparisons negated; each `except` widened, narrowed or re-raising; each
    `isinstance` tuple member dropped) and requires a `mutants.py` case that yields the same AST,
    targeting a row beside each member set.
  - `spec/capability-probe/verify/alternatives.py` does the same per phase.
  - `remediation/F1-exact-record-values.py` does it for the exact checks (`checker`, `coverage`, `cases`,
    `cli`).
  - These are frozen records. This cycle would write its own.
- **Convention for a new decision:** `alternative(case_id, LOADER, edits, test, kind, why)`
  (`mutants.py:335`) builds `Case(id, file, edits, every_set(test, kind), why)`. `every_set(test,
  *cases)` (`:324`) expands to `test[<kind>-<set>]` over `MEMBER_SETS`. `partition_alternative` drops
  `core-only`. The `why` is a fragment of the target's assertion message, e.g. `'a capability that
  cannot load was not refused naming it'`. There are no spec ids anywhere in `tests/*.py`
  (`test_no_spec_ids_in_the_package_or_the_suite`). The record's exact checks got cases named
  `capability-*-exact-*`, one for each alternative of each check, plus each check put back to
  `isinstance`.
- **A model to copy:** `spec/capability-probe/remediation/F1-exact-record-values.py`:
  - `checker` (in process, generated sites × planted shapes × 4 sets, cause and cut-back and `_RAN`
    empty, plus exact controls on the members);
  - `coverage` (every alternative of the new checks cased);
  - `cases` (`tests/mutants.py --self-check` per case, both eras, about 6 s a case);
  - `cli` (`CLUSTER_MCP_TEST_EVERY_KIND=1`, the `exact-*` kinds × 3 transports × 2 eras).

## 5. Template from `capability-probe` (TECH/PLAN)

- **Phase shape:** P1 (declaration and checks), P2 (startup; the exact record arrived as rulings and
  review remediations inside P2), P3 (whole-cycle checks, ledger, recipe, full suite in each era).
- **`verify:`** chains `sh verify/p<n>.sh phase`, then the phase's remediation checkers, then four
  mutation shards (`mutants-handshake-1/2`, `mutants-modern-1/2`). Each shard is about 4–5 min, under
  the 10-minute command cap, and the shards run one at a time.
- **`phase`** runs the independent checkers, `alternatives.py coverage <phase>` and the phase's named
  test ids in both eras (`pytest_both`, never a marker selection).
- **Footprint** goes in each script header: one process tree at a time, nothing in the background,
  under 1 GB.
- **Records:** `verify/` is frozen at sign-off. A wrong gate gets a ruling plus a wrapper under
  `remediation/`. Each run is recorded as *Observed (date), on tree X*, with counts and times.
- **For this small cycle:** two phases fit. P1 is the check and its rows: an `F1-exact-record-values`-style
  `checker` + `coverage` + `cases` sharded by era, with `cli`. P2 is AGENTS §7 and § Testing, the README
  check, the surface baseline and the full suite in halves per era.

## 6. Same-commit rules that bind this change

- **§7 (`AGENTS.md:2768-2890`):**
  - The refusal bullet "registers anything but a `FunctionTool`" (`:2803`) needs the R1 and R2
    wording.
  - The paragraph "No read of a loaded record runs capability code" (`:2853-2866`) currently says
    tools "run capability code … read as it registers them". R7 rewrites it: tools are decided too,
    the check holds at load, and the paragraph names `issues/capability-tool-objects-served-copy.md`.
  - The test list in that paragraph names the rows.
- **§ Testing (`:372-405`, `:655-668`):** the `test_capabilities.py` paragraph lists every refused
  family, and the startup paragraph lists the `UNLOADABLE` families driven through the CLI. Both
  gain the tool families.
- **§ Conventions (`:3079-`):**
  - "Point to a rule; don't restate it. A rule restated in N places is a same-commit obligation in all
    N." This also covers the `load()` docstring (`capabilities.py:290-307`, "is not a `FunctionTool`")
    and `test_capabilities.py`'s module docstring (`:33-39`), plus the `WHEN`/`ODD_TOOL` comments.
  - Spec ids are banned in the package and in `tests/*.py`.
  - Mark every new test `@pytest.mark.unit` or `@pytest.mark.integration`.
  - A `verify:` names test ids, never a marker selection.
  - CLI drives run under `bin/sandbox.sh`.
- **§ Testing, mutation bullet (`:1597-1602`):** an anchored line edited means re-planting in the same
  commit and re-running.
- **README:** it says nothing about tool-object refusals (no `FunctionTool` mention), so no edit is
  expected. `tests/fixtures/served_surface.json` must not change (R5).

## 7. Sibling `capability-reload-after-failure`

- **State:** GOAL plus `research/02-tests-and-mutants.md`, with no PLAN, TECH or code on its branch.
- **Contract:**
  - A retry after a failed load behaves as a first load in a fresh process: the same refusal message
    (R1), or a success with each capability's tools registered exactly once (R2), through `load()`,
    `installed()` or `create_mcp_server()`.
  - The first load is unchanged (R4).
  - Its research expects the fix to snapshot `sys.modules` at load start and evict, on failure, the
    modules the failed load first imported, but never a module imported before `start`
    (`test_a_capability_whose_tools_are_already_imported_keeps_them`).
- **Lines it is likely to touch:**
  - `start = len(TOOL_REGISTRY)` and the `scratch = _scratch()` / `try:` boundary (`:312-321`, which
    breaks the `capability-scratch-per-capability` anchor);
  - the failure exit `:382-387` (`del TOOL_REGISTRY[start:]`, the `ROLLBACK` cases);
  - possibly `before` / `import_module` (`:324-329`) and the `tools =` attribution (`:341`, "the same
    `TOOL_REGISTRY` scan that decides which tools this cycle's retry finds").
- **What a refusal of ours must leave:**
  - Raise from inside the `try` as a `CapabilityLoadError`, so it takes the one failure exit:
    cut-back, plus the sibling's eviction once it lands.
  - Cache no per-object verdict across loads (a retry re-imports and re-registers new objects).
  - Keep the message deterministic, so a retry's refusal is byte-identical (the sibling's R1 compares
    messages). Never put an `id()` or address in the cause.

## Open questions and risks

1. **The `served-tool` timing loses its carrier.**
   - Measured here: `FastMCP.add_tool` reads no attribute of `fn`. With R1 and R2 in force, an exact
     tool runs no capability code in `serve()`. So the 32 `*-at-served-tool` rows change cause, and the
     five `tool-assembly-*` mutants (and `CLI_UNLOADABLE`'s `raises-base-at-served-tool`) lose their
     kill.
   - The plan must pick one: a new carrier (some field value FastMCP refuses at `add_tool` with exact
     values), a retirement of the timing with recorded equivalents, or a foreman ruling.
2. **Tools registered before `start` are not checked.** `odd` scans `TOOL_REGISTRY[before:]`, but
   `tools =` (`:341`) reads `tool.fn.__module__` for **every** registry entry. That includes entries a
   tools module imported before the load registered, which no check saw. The new check must cover
   every entry the attribution reads, not only `[before:]`.
3. **Wording the refusal reads the type.** `type(entry).__name__` reads the class, and a subclass with a
   metaclass of its own (deriving from pydantic's `ModelMetaclass`) can run code on `__name__`. R1 says
   none may run "in wording the refusal". The type name must be read safely: `type.__dict__['__name__']`
   / `type.__name__.__get__`, or only after `type(entry) is FunctionTool` fails, through `type`'s own
   descriptor.
4. **Non-field state.** `__pydantic_fields_set__`, `__pydantic_extra__`, `__pydantic_private__` and an
   instance `__dict__` key set with `object.__setattr__` are not `model_fields`. Does FastMCP read them
   (`model_copy`, `model_dump(exclude_unset=…)`)? If it does, R2's "no field unchecked" must name them.
5. **The `_RAN` assertion only looks at the capability module.** Tool-family plants must put
   `PLANTED_TYPES` there.
6. **Each re-planted anchor needs its case re-run.** Re-planting is cheap (about 3.5 s a case), but the
   new decisions' alternatives (exact checks per field, recursive walk) could add 50–100 cases. At
   about 6 s a case per era that is 5–10 min an era, so shard the mutation gate per era and half as
   `capability-probe` did.
