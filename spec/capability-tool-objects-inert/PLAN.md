# PLAN — A capability's registered tool objects run none of its code when they are read

> **Status:** Draft for review · **Last updated:** 2026-11-12
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

`load()` stops taking a registered tool on `isinstance`. One function, `_tool_violation`, decides each
registry entry inert before the load first reads it, and again after each later point of the load
where capability code runs: exactly a `FunctionTool`, its instance state
exactly what pydantic gives one, and every field of the installed FastMCP's model holding what its
field's rule accepts, read by type before value, `fn` excepted. A field no rule names is checked by
one generic rule. The members' tools already hold exactly what the rules accept, so nothing they
serve changes. Two phases: the check with its refusal rows and §7 (P1), then the proof that serving
runs no capability code but the handler, with the whole cycle's checks (P2).

## 2. Design

All code changes are in `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`; tests in
`tests/test_capabilities.py`, `tests/test_startup.py`, `tests/mutants.py`; docs in `AGENTS.md`.

**Where the decision sits in `load()`.** `_registry_violation(before)` walks every entry of
`TOOL_REGISTRY`, the core's tools included (they pass every rule, and a capability's code at import
could spoil one), hands each to `_tool_violation`, and returns the first violation worded by index:
`loading it registered <why>` for an entry at or after `before`, `the registry holds <why>` for one
before it. `load()` calls it three times per capability, each `if held := _registry_violation(before):
raise CapabilityLoadError(distribution, held)`, inside the `try` so a refusal takes the one failure
exit (registry cut back, `:383-387`):

1. after `import_module` (`:329`), replacing the `odd` lines (`:330-332`), before `stray` (`:333`),
   the load's first read of an entry (`fn`, `name`); it also catches this capability's import
   changing an earlier capability's tool;
2. after the attribution (`:341`), because `stray` and the attribution read `fn.__module__` of every
   entry, which is the capability's code (`fn` is excepted) and can change a tool already decided
   (the adversarial review's HIGH-1), before the name checks (`:342`) read `tool.name`;
3. after the resources are assembled (`:378`), because FastMCP reads a resource handler there (its
   annotations, capability code), before `names`, `owners` and `Loaded` record the capability.

Nothing else of a capability's runs between the third decision and the next capability's import, or
the load's return. It walks the whole registry, not `TOOL_REGISTRY[before:]`, because the
attribution reads every entry, including ones registered before this load began (`research/03`
risk 2). No verdict is kept across loads, and no message carries an `id()`. The three passes cost
about 5 ms a capability (one pass over 24 entries measured at 1.6 ms).

**`_tool_violation(entry) -> str | None`**, in this order, each step deciding a type before anything
reads the value:

1. `type(entry) is not FunctionTool` → `a <Type>, not a FunctionTool` (today's wording, kept, so the
   existing non-tool rows keep their cause).
2. Instance state, through `object.__getattribute__` (a deleted slot refused by name, not through
   the load's generic exit): `__dict__` exactly a `dict`; every key exactly a `str` (checked by
   iterating, before any lookup); every field of the installed model present, and any other key
   JSON-like (J); `__pydantic_extra__` `None`, or J when the installed model's `extra` is `allow`;
   `__pydantic_private__` `None`, or exactly a `dict` keyed exactly by the installed model's
   `__private_attributes__`, each value J or its declared default; `__pydantic_fields_set__` exactly a
   `set` of exactly `str`, each a field (a subset: the members leave `execution` unset). The state
   rules follow the installed model too, so a FastMCP within range that adds a private attribute or
   allows extras is not refused for it (the review's MEDIUM-3); a suite test pins the locked model's
   `__private_attributes__ == {}` and `extra == 'forbid'`, so a re-lock that changes either fails.
3. For each `field, info` in `FunctionTool.model_fields` (the class attribute of the FastMCP
   installed at run time, never the rule table): `TOOL_RULES.get(field, _unnamed)(state[field],
   info)` → `a tool whose <field> <why>`.

**Naming a type** (`_type_name`): `str.__str__(type.__dict__['__name__'].__get__(kind))`, which runs
neither a metaclass's `__name__` nor a `str` subclass held as the name (`research/02` § 2). Only `is`
chains test types; never `in` a tuple or set of types.

**The rules** (`TOOL_RULES`, a module-level dict, field → `(value, FieldInfo) -> str | None`):

| Field | Rule | Accepts | Why (what reads it, when) |
|---|---|---|---|
| `name` | J | exactly `str` | the load (names, listing check), the key at `add_tool`, listing, calls |
| `description` | J | `None` or exactly `str` | listing (`to_mcp_tool`) |
| `parameters` | J | exactly `dict`, JSON-like at every depth | listing, to the wire; `Any` values below the top level keep any object, even through `from_function` |
| `output_schema` | J | `None`, or exactly `dict`, JSON-like at every depth | listing; `convert_result` at a call |
| `return_type` | T | `None`, no annotation (`inspect.Signature.empty`), `typing.Any`, `...`; a class whose metaclass is exactly `type`, pydantic's `ModelMetaclass`, `enum.EnumType`, `abc.ABCMeta` or `typing._TypedDictMeta` (its namespace, read through `type`'s descriptor, keyed exactly by `str`; its `__module__`, when held, exactly `str`); or an alias exactly a `types.GenericAlias`, `typing._GenericAlias`, `typing.Union`, `typing._UnionGenericAlias`, `typing._AnnotatedAlias` (metadata exactly pydantic `FieldInfo` or JSON-like) or `typing._LiteralGenericAlias` (arguments exact scalars), its state read through its instance dictionary, whose origin and arguments pass the same rule | `add_tool` reads it (`isinstance`, `__module__` `==`, `get_origin`/`get_args`); the RCAC member returns its own dataclass, so no by-value rule fits; the widened lists accept what `from_function` gives for a pydantic model, an enum, a `TypedDict`, a `Literal`, `Annotated`, `tuple[int, ...]` and an `abc` generic (the review's HIGH-2, each probed) |
| `fn` | X | anything: excepted | the handler, which a request calls; the load's own read of `fn.__module__` stays as §7 counts it (§ 5, Q-B) |
| `version` | F | its default, `None` | the key, version mixing and sort, `get_meta`, at `add_tool` and listing |
| `title` | F | `None` | listing |
| `icons` | F | `None` | listing |
| `tags` | F | `set()`, exactly a `set` and empty | `sorted()` in `get_meta`, at listing |
| `meta` | F | `None` | `add_tool`, listing, `resources/list` and `read`, `get_tool` |
| `task_config` | F | node for node `TaskConfig(mode='forbidden')`: exactly `TaskConfig`, its `__dict__` exactly a `dict` holding exactly `mode` (`'forbidden'`, exactly `str`) and `poll_interval` (5 s, exactly `timedelta`) | `supports_tasks()` and `.mode` at listing and server start |
| `annotations` | F | `None` | listing |
| `execution` | F | `None` | listing |
| `auth` | F | `None` (not X) | its checks run at listing over HTTP and SSE: a callable there would break R3 |
| `timeout` | F | `None` | a call (`fail_after`) |
| `run_in_thread` | F | `True` | a call |
| state: `__dict__` | — | exactly `dict`, keys exactly `str` and exactly the model's fields | every attribute read goes through it |
| state: `__pydantic_fields_set__` | — | exactly `set` of exactly `str`, each a field | `model_copy`, `model_dump(exclude_unset=…)` |
| state: `__pydantic_extra__`, `__pydantic_private__` | — | `None` | `model_dump`, `model_copy` |

J is `_json_violation`: an iterative walk accepting `None`, exactly `bool`, `int`, `float`, `str`,
and exactly `list` or `dict` whose keys are exactly `str` (checked before any value is read),
refusing a container met twice (so a cycle ends; the members share none). F is
`_default_violation(value, info)`: `value` is node for node (`_same`) what the installed model
declares as the field's default, `info.default`, or a fresh `info.default_factory()` (never a factory
that takes data). `_same` compares types by `is` first, then scalars (`bool`, `int`, `float`, `str`,
`timedelta`) by `==`, lists, dicts and sets element by element (set elements exact scalars first), a
dataclass or pydantic model of the default's own type (FastMCP's, never the capability's) by its
instance state, and anything else by identity. That every F field's declared default is what
`Tool.from_function` gives it through `@mcp_tool` is pinned by a test (§ 6), so F is the GOAL's
third kind ("only what `Tool.from_function` gives it") read from the installed model.

**The generic rule** (`_unnamed`, R4): a field no rule names passes when its value is JSON-like at
every depth (J), or its own declared default (F). It never skips a field, and it accepts whatever a
newer FastMCP's `from_function` leaves at its default or fills with JSON, so it does not refuse a
capability for the field being unknown. Its limit is in § 5.

**`TOOL_RULES` names every field of the locked model.** A suite test holds `set(TOOL_RULES) ==
set(FunctionTool.model_fields)`, so a re-lock to a FastMCP with a new field (or without one) fails
the suite until the field gets a rule (R4's last sentence).

**Docs, same commit as the check (R7, § Conventions "point to a rule").** `AGENTS.md` §7: the refusal
bullet "registers anything but a `FunctionTool`" becomes "anything but exactly a `FunctionTool` (a
subclass refused, its type named), a tool one of whose fields holds a value its rule does not accept";
the "No read of a loaded record runs capability code" paragraph says the tool objects are decided
too, that the check holds at load, names `issues/capability-tool-objects-served-copy.md` for a change
made afterwards, takes the tools out of what FastMCP reads running capability code (leaving each
tool's `fn` when a request calls it, and the resource handlers), says the check covers the objects a
capability hands the core and not the classes or modules its code can change at import, and names the
new rows. § Testing's `test_capabilities.py` and `test_startup.py` paragraphs name the new families.
`load()`'s docstring, the module docstring, and `test_capabilities.py`'s `WHEN`/`ODD_TOOL` comments
follow. No spec id in package or suite. README and the served-surface fixture do not change.

**Tests.**

- `test_a_capability_that_cannot_load_is_refused_naming_it`, beside each member set, gains the
  families generated from `FunctionTool.model_fields` and `TOOL_RULES` (so a field FastMCP or a rule
  adds asks for its rows; `verify/rows.py` lists them): `tool-subclass-reads-<field>` (+ `-nothing`,
  and `tool-subclass-named-by-its-metaclass`: a metaclass whose `__name__` runs), `tool-exact-<field>`
  for every field but `fn` (a value of a type of its own, set after construction: construction
  coerces the top level back to a built-in), `tool-default-<field>` for every F field (an exact,
  JSON-like value that is not the default, which the generic rule would accept), and the depth and
  state rows `verify/rows.py` names (`tool-exact-parameters-key`, `…-value`, `…-element`, `…-twice`,
  `tool-exact-output_schema-value`, `tool-exact-task_config-state|mode|poll_interval`,
  `tool-exact-return_type-module|attribute-name|argument`, `tool-state-dict|key|extra-key|
  missing-field|fields-set|fields-set-element|extra|private|missing-slot`, and the three later changes
  the review found: `tool-changed-by-its-handler-module`, a `fn.__module__` whose `==` sets the name to
  a type of its own; `tool-changed-by-a-resource-handler`, a handler annotation that does it while the
  resources are assembled; `tool-changed-by-a-later-capability`, a second planted capability's import
  that does it to the first's tool). Each asserts the one-line message
  naming the distribution and the field, the registry cut back, and `_RAN` empty: the planted types
  (`PLANTED_TYPES`, extended with `list`, `set`, `float`, `timedelta` and a metaclass) live in the
  capability module, which the tools module imports, because the test reads `_RAN` there.
- The `served-tool` timing keeps its 32 rows and its `KeyboardInterrupt` rows with a new carrier
  (§ 3, deviation row 1).
- `test_a_capability_that_cannot_load_stops_startup`: `CLI_UNLOADABLE` gains
  `tool-subclass-reads-name` and `tool-exact-parameters-value` (R6: one kind of each).
- New: `test_every_function_tool_field_has_a_rule` (the table equals the locked model's fields; a
  fresh `@mcp_tool`-style `Tool.from_function` gives each F field its declared default);
  `test_a_field_no_rule_names_is_checked_by_the_generic_rule[<field>]` (every field but `fn` and
  `return_type`, the rule table monkeypatched to drop it: the members still load, a JSON-like
  non-default value is accepted, a value of a type of its own is refused naming the field);
  `test_an_inert_tool_of_every_accepted_shape_loads` (planted tools holding every accepted scalar
  and container in `parameters` and `output_schema`, `description` and `output_schema` `None`, a
  JSON-like non-field attribute, and each `return_type` form `from_function` gives for `str`, `None`,
  `dict`, a dataclass, a pydantic model, `list[Model]`, an enum, a `TypedDict`, a `NamedTuple`,
  `Literal`, `Annotated[str, Field(...)]`, `tuple[int, ...]`, `collections.abc.Sequence[int]`,
  `X | None`, `typing.List[int]` and `Any`, load: the controls that kill a too-strict mutant);
  `test_the_locked_model_holds_no_private_attribute_and_forbids_extras`;
  `test_a_tool_registered_before_the_load_is_decided_too` (a non-inert tool registered by a module
  imported before `load()` is refused with the "before its load began" wording); P2:
  `test_a_served_capability_runs_none_of_its_code_but_its_handler` (§ 6).
- `tests/mutants.py`: the cases anchored on the changed lines are re-planted (11 on the folded
  prototype: 7 by the change itself, 4 because new code repeated an anchor's text, `if type(key) is
  not str:`; build either keeps new text distinct or re-plants them, recording which in the commit
  body); a case for every alternative of the new decisions (§ 6).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | step 1 of `_tool_violation`; `_type_name`; the first decision's place before `stray`; `tool-subclass-*` rows |
| R2 | steps 2-3; `TOOL_RULES` (J, F, T, X); `_json_violation`, `_same`; the three decisions, so no value the load reads was changed after it was decided; `tool-exact-*`, `tool-default-*`, depth, state and `tool-changed-*` rows |
| R3 | the rules make every field FastMCP reads at `add_tool` and listing an exact built-in or FastMCP's own default; `test_a_served_capability_runs_none_of_its_code_but_its_handler` (P2) |
| R4 | step 3 walks `FunctionTool.model_fields` at run time; `_unnamed`; `test_every_function_tool_field_has_a_rule`, `test_a_field_no_rule_names_is_checked_by_the_generic_rule` |
| R5 | the members' 17 tools pass every rule unchanged (prototype); `test_served_surface_matches_baseline` with the fixture unedited (gated against develop) |
| R6 | the families above in the refused-naming-it test beside each set; two CLI kinds; the existing cut-back assertion |
| R7 | §7 refusal bullet and paragraph, § Testing, in P1's commit (`verify/docs_gate.py` reads the index) |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before research (gate #1) and on the drafted design (gate #2).

- **§7 (tool registration load)**, every bullet. The change extends §7's own rule ("no read of a
  loaded record runs capability code") from the record to the tool objects; refusals stay one line
  naming the distribution, raised inside the load's `try`, registry cut back (`load()` `:383-387`
  untouched); a `KeyboardInterrupt` still interrupts (the decisions raise only `CapabilityLoadError`).
  `installed()`'s no-cache-on-failure is untouched. The load order and discovery are untouched.
  `@mcp_tool` is unchanged (GOAL non-goal).
- **§9 (agent-facing surface)**: nothing served changes; the prototype's members pass every rule and
  `test_served_surface_matches_baseline` passes in both eras on it.
- **High-blast-radius paths**: `core/capabilities.py` is on the list, so research ran (trigger 2), and
  a confirmed finding there takes the human gate at review.
- **§ Testing / § Conventions**: every new test carries `@mark.unit`; gates name test ids; CLI drives
  go through the existing sandboxed drive; no spec ids in package or suite; mutation anchors
  re-planted in the same commit as the change.
- Not touched: §1-§6, §8, `server.py` (`create_mcp_server` still registers through `serve()`).

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| 1. The `served-tool` timing's carrier changes from a `FunctionTool` subclass to a planted module that replaces `FastMCP.add_tool` for its own tool (restoring it as it raises; the `plant` fixture restores it regardless) | Once tools are exact, a capability's code can no longer run while FastMCP reads its tool, so the old carrier is refused earlier (40 rows, 5 mutants lose their kill, `research/03`). Code at import can still change FastMCP itself, which this check does not cover (§7 says so), so the `except` around the scratch `serve()` stays live and keeps its rows | Retiring the timing leaves a live `except` unpinned and 5 mutants surviving; removing the `except` changes how a FastMCP refusal of a tool is worded |
| 2. The registry is decided whole (the core's tools too), three times a capability, not only `TOOL_REGISTRY[before:]` once | R3 needs every tool the attribution hands a capability decided, `:341` reads entries registered before the load began, and capability code runs at three later points of the load (the handler-module reads, the resource assembly, the next capability's import) where it can change a decided tool (HIGH-1) | `[before:]` once leaves those entries read unchecked and lets a later change through; a single pass at the load's end lets the load itself read a changed `name` first |
| 3. R3's planted tool "that would run code on any read of a field but `fn`" is read as two halves: such a tool is refused at load with none of its code run (the R2 rows), and a planted capability that passes is served, listed and called with a monitor that records any code of its files that runs | A tool that would run code on a read cannot pass R1 and R2, which R3's WHERE requires | Planting it past the check would need the check switched off in the test, proving nothing about the shipped load |

Each row was read against the R-ID it touches: row 1 keeps R6's rows and changes no refusal of R1/R2;
row 2 widens R1's "a capability's load registers" to every entry the load reads, a superset, and
holds R2's "before the core or FastMCP reads that value" across the load; row 3
meets R3's "a test SHALL show this with a planted capability…" in both its halves.

## 4. Rabbit holes (resolved)

- Which fields, who reads them, what `@mcp_tool` gives → the table above ([`research/01`](research/01-functiontool-fields.md)).
- Reading state and naming a type without running code; `in` on types runs a metaclass `__eq__` →
  `object.__getattribute__`, `is` chains, the descriptor read ([`research/02`](research/02-inert-reads-and-generic-rule.md)).
- A generic rule that never refuses for unknown-ness → (ii), JSON or its own default; (iii)
  re-derivation runs capability code and needs typing `==` ([`research/02`](research/02-inert-reads-and-generic-rule.md) § 4).
- The served-tool timing loses its carrier → deviation row 1, prototyped green
  ([`research/03`](research/03-tests-mutants-sibling.md)).
- **Prototype** (`$REPO/.worktrees/capability-tool-objects-inert-proto`, cut at the GOAL commit
  `8b4db2a`, this PLAN and `verify/` copied in; closed before the plan commit): the first draft of
  the check loaded both members (24 registry entries decided in 1.6 ms) and failed exactly the 40
  `served-tool` rows of 950 targeted tests; with the new carrier and the review's folds, 837 of 837
  pass in the handshake era (`test_capabilities.py`, the surface baseline, the two registry tests,
  `test_instructions.py`, `test_storage_resource.py`), 712 of 712 in the modern era
  (`test_capabilities.py`, the surface baseline), and the 30 CLI rows of
  `test_a_capability_that_cannot_load_stops_startup`. 11 mutation anchors break (§ 2, tests). The
  review's HIGH-1 carrier (a `fn.__module__` trap) is refused, none of its code run.
- Adversarial design review: see § 7.

## 5. Risks & open questions

For the plan gate:

- **Q-A, the field rules.** The table in § 2, F against J for the eleven constant fields: F is tighter
  and smaller, and refuses a future member that sets, say, `annotations` until its rule is widened.
- **Q-B, `fn`.** (B1, the plan) Excepted outright; the second decision catches any tool its
  `fn.__module__` code changed. The load's own `fn.__module__` reads (`stray`, `:341`) still run a
  `str` subclass's code when a capability's function carries one through `functools.wraps`, at load
  and inside the guard, as §7 already counts ("the load's reading of what it declared"; the `declared`
  timing rows use exactly this). Residual: such code that spoils a tool `stray` then names runs that
  name's code while the stray refusal is worded (a refusal still). (B2) Checking `type(fn) is
  FunctionType` and an exact-`str` `__module__` (`research/01` risk 1) closes that at its root, makes
  the second decision unnecessary, and takes the carrier from the `declared` timing (its rows and
  `KeyboardInterrupt` rows re-carried or retired, and `tool-without-a-module`'s cause changes).
- **Q-C, `return_type` at a call.** Rule T makes `add_tool`'s reads inert. At a call FastMCP builds a
  `TypeAdapter` on it to serialize the handler's result, which reads the capability's dataclass
  (annotations, hooks). The plan counts that as the call (the handler's declared return type, for its
  result); the R3 test returns a `str`. The alternative, walking the class, is far beyond the appetite.
- **Q-D, the generic rule's limit.** A newer FastMCP field that `from_function` fills with a value
  neither JSON-like nor its default (as `return_type` is today) would refuse every capability on that
  FastMCP, loudly at startup, naming the field. No rule covers it without running capability code
  (`research/02` § 4). The suite catches it at the next re-lock.
- **Q-E, mutation scale.** 358 alternatives on the folded prototype (`verify/alternatives.py coverage
  p1`, with the review's statement, loop and return alternatives), about 3 s a case per era measured,
  so about 18 min an era in four shards, plus 86 re-planted cases (about 4 min an era). Narrower option: the rule-table and family alternatives only
  (about 25), leaving node-kind alternatives to review's diff sweep, graded per the factory's
  mutation-testing method (operator's KB, `method/mutation-testing.md` § When a review is done).
- **Q-F, the wording of an entry before `before`.** A non-inert entry this capability's load did not
  register (one registered before the load began, or an earlier capability's that this one's code
  changed) is refused naming the capability being loaded, `the registry holds …`, which need not be
  its owner (no owner is known before `fn.__module__` is read).

Risks, not deferred: depth and size bounds are not added (a 260-deep schema passes the load and fails
listing, as today; adding a bound is a new refusal with figures to rule). The record checks'
`type(value).__name__` and `_shown`'s `in` (`research/02` § 2) can run a metaclass's code at load;
pre-existing, outside this GOAL, raised here for the foreman to rule whether it earns a seed.
Prototype numbers come from one host, the plan's.

**Sibling `capability-reload-after-failure` (shared lines).** Both change `load()`. This cycle
replaces `:330-332` with the first decision, inserts the second after `:341` and the third before
`:379` (two lines each), and adds module-level functions and `TOOL_RULES` above
`_listing_violation`; it leaves `start`, `_scratch()`, the `try` (`:312-321`), `before` and
`import_module` (`:324-329`), `stray` and the attribution (`:333-341`), the resource loop and the
recording (`:371-382`) and the failure exit (`:383-387`) as they are. Its refusals are `CapabilityLoadError`s raised inside the `try`, so they
take the sibling's eviction once it lands; they keep nothing across loads and their text is
deterministic, so a retry refuses byte for byte alike; each decision walks the whole registry, so whatever
a retry leaves there is decided. Expected conflicts on rebase: `tests/mutants.py` (both re-plant
cases anchored in `load()`), `tests/test_capabilities.py` (`UNLOADABLE`, the `plant` fixture), and
`AGENTS.md` §7 and § Testing; none in `core/capabilities.py` unless the sibling moves `:329-333`.

## 6. Verification strategy

- **P1** (`verify/p1.sh`): `phase` — the fixture unchanged against develop at the cycle start (index),
  `docs_gate.py` (§7 in the index, beside the check), `rows.py` (every family beside every set, and a
  CLI kind of each), `alternatives.py coverage p1`, then the named tests in both eras; `cli-<era>` —
  every `tool-` kind through the CLI over each drive (`CLUSTER_MCP_TEST_EVERY_KIND=1`); `replanted-<era>`
  — every case whose edits or targets differ from develop's, or that is new, or anchored in `load()`,
  or killed by a `served-tool` row, killed; `mutants-<era>-K` — every P1 alternative's case, killed,
  four shards an era. Each named-test run fails on any skip and on an empty parameter set.
- **P2** (`verify/p2.sh`): `phase` — fixture, docs, rows, `alternatives.py coverage all`, the R3 test
  and P1's new tests in both eras; `ledger`; the profile's full verify as its own commands
  (`full-<era>-1..4`, `full-ends`), each under the 10-minute command cap.
- **The R3 test** registers a `sys.monitoring` `PY_START` callback (a free tool id) that records any
  code object whose file lies in the planted package; builds two servers from the loaded capabilities
  and lists their tools through the harness client in the selected era (nothing recorded), then calls
  the planted tool once (only its function recorded, once).
- **CI budget** (before → after, from `research/03`): `suite-*-4` gains about 260 in-process rows at
  0.01-0.02 s, about 5 s an era (baseline 7:22 / 7:33); `suite-*-3` gains 6 CLI rows at about 1.1 s,
  about 12 s an era on CI (7:10 / 7:34). Both stay under the 10-minute bound; the bound is not moved.

## 7. Adversarial review

Ran once (trigger 3: the deliverable is a load-time gate, and the R4 suite check is a gate too), a
fresh child given GOAL, this PLAN, `verify/` and the prototype, tasked with inputs the check passes
while broken or refuses while good, and gates that pass a broken build. Two HIGH, three MEDIUM, five
LOW; all folded:

- HIGH-1, capability code later in the load changes a decided tool (a `fn.__module__` `==`, a
  resource handler's annotations) → the three decisions (§ 2) and the `tool-changed-*` rows; the
  prototype refuses the reviewer's carrier with none of its code run.
- HIGH-2, rule T refused ordinary return types (pydantic model, enum, `Literal`, `TypedDict`,
  `Annotated`, `tuple[int, ...]`, `abc` generics) → T widened to closed lists, each shape in the
  accepted-shape control (probed on the prototype: all accepted).
- MEDIUM-3, a FastMCP within range adding a private attribute or extras would refuse every
  capability → the state rules follow the installed model, and a suite test pins the locked one.
- MEDIUM-4, the sweep generated no statement, loop or return alternatives → added
  (`verify/alternatives.py` `extra()`); 231 → 358 alternatives.
- MEDIUM-5, `replanted.py` missed re-planted cases outside `load()` (the `KEY_CHECK` anchor) → it
  selects every case that differs from develop's.
- LOW: `rows.py` names the F fields (L6); named runs fail on a skip or an empty set (L7);
  `docs_gate.py` checks the "What does run capability code" sentence (L8); alias state and deleted
  slots read without raising (L9); the core-tool skip dropped (L10).

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
