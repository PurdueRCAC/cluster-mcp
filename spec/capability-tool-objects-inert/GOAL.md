# GOAL — A capability's registered tool objects run none of its code when they are read

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** capability-tool-objects-inert
- **kind:** fix
- **appetite:** small

## Problem

Every tool a capability serves is an object its own code handed the core, and today the core takes
that object on trust. A capability's tools module registers each tool through `@mcp_tool`
(`packages/cluster-mcp/src/cluster_mcp/core/tools/__init__.py:63-76`), which appends a FastMCP
`FunctionTool` to `TOOL_REGISTRY`. The load accepts whatever was appended by `isinstance`, not by
exact type (`core/capabilities.py:330-332`). So a tools module can append a subclass of
`FunctionTool`, or set a field of a real one after construction to a value of a type of its own (a
`str` subclass for `name`, a `dict` subclass for `parameters`), and that type's code runs whenever
the field is read:

- at the load: `tool.fn.__module__` for each registered entry (`:333-334`, `:341`); `tool.name`
  compared, listed and recorded (`:342-349`, `:360`, `:380`); and each tool registered on the load's
  scratch server through `serve()` (`:363-369`; `serve()`, `:264-272`, calls `server.add_tool`);
- when a server is built: `create_mcp_server` registers the same objects through `serve()` again
  (`core/server.py:148`);
- after that, whenever FastMCP reads the tool to list it or to call it.

The load's guard turns what such code raises *at the load* into a refusal naming the distribution.
It does not reach the second registration or any later read, and code that runs on a read can answer
differently each time, so a tool can pass the load and then behave otherwise when served. Since
`capability-probe` the capability record is exact (`type(value) is Capability`, and every value of
it the core or FastMCP reads is exactly a built-in type, § Invariants §7, "No read of a loaded
record runs capability code"); the tool objects are the one part of what a capability hands the core
that is still taken by `isinstance`. Every capability family the roadmap adds will register through
this load, so the gap widens with each one.

**Pre-existing:** yes. The `isinstance` check landed with `capability-extras` (`4e772ec`, `git blame`
on `core/capabilities.py:330` and `:341`); `capability-probe` made the record exact and left the
tools as they were. No released version is affected in practice: both workspace members register
through `@mcp_tool` and set no field afterwards.

## Outcome / vision

Every tool a capability registers is decided at load to be inert: exactly a `FunctionTool`, holding
in every field the core or FastMCP reads a value its field's rule accepts, checked before anything
reads it. The handler (`fn`) is excepted: it is the capability's code by design, and a
request calls it. A tool that fails the check refuses its capability at load, naming the
distribution, as every other §7 refusal does. After the load, listing the served tools, or building
another server from the loaded capabilities, runs none of a capability's code; only a tool call does,
through its handler. The check holds at load: a change the capability's own code makes to a tool
object afterwards is a separate seed (Q1). The Slurm and RCAC members load and serve exactly as they do today.

## Acceptance criteria (the contract)

- **R1** — WHEN a capability's load registers an object whose type is not exactly `FunctionTool` (a
  subclass included), the load SHALL refuse the capability with `CapabilityLoadError`, naming its
  distribution and the object's type, and SHALL run none of that object's code in deciding or in
  wording the refusal.
- **R2** — WHEN a field of a registered `FunctionTool`, other than `fn`, holds a value its field's
  rule does not accept, the load SHALL refuse the capability the same way, naming its distribution
  and the field, before the core or FastMCP reads that value, and SHALL run none of the value's code
  in deciding or in wording the refusal. Every field has a rule (Q2): exactly the type FastMCP gives
  it, a subclass of a built-in type or of a FastMCP, MCP or pydantic model refused; or an excepted
  callable, as `fn` is; or only what `Tool.from_function` gives it through `@mcp_tool`. The rule
  holds at any depth: a key, element or field of a container or model the field holds. No field is
  left unchecked, and no check reads a value before its type is known.
- **R3** — WHERE every capability's tools pass R1 and R2, building a server from the loaded
  capabilities, and listing its tools, SHALL run none of a capability's code; a tool call SHALL run
  only that tool's handler. A test SHALL show this with a planted capability whose tool would run
  code on any read of a field but `fn`. (A change the capability's own code makes to a tool object
  after the load is out of scope, Q1.)
- **R4** — The fields the load checks SHALL follow the `FunctionTool` model of the FastMCP installed
  at run time, so no field passes unchecked (Q3). WHERE that model has a field no rule names (a newer
  FastMCP within the declared range), the load SHALL check it by one generic rule, never skip it: a
  value that is JSON-like at every depth, or the field's own declared default, passes; any other value
  is served undecided, with one WARNING on stderr per field per process naming the field and the
  installed FastMCP's version. The load SHALL NOT refuse a capability because of a field no rule
  names. WHEN the locked FastMCP's `FunctionTool` has a field no rule names, the suite SHALL fail.
  (Amended at plan sign-off, Q-D.)
- **R5** — The Slurm and RCAC members SHALL load and be served unchanged: their tools pass R1 and R2,
  and `test_served_surface_matches_baseline` passes with no fixture edit.
- **R6** — Each refusal of R1 and R2 SHALL be driven by a planted capability in
  `test_a_capability_that_cannot_load_is_refused_naming_it`, beside each member set, as §7's existing
  refusal rows are, and at least one kind of each SHALL be driven through the CLI in
  `test_a_capability_that_cannot_load_stops_startup`. A refusal SHALL leave `TOOL_REGISTRY` cut back
  to what it held before the load, as every other refusal does.
- **R7** — In the same commit that lands the check, `AGENTS.md` § Invariants §7 SHALL list the
  tool-object refusal beside the record's, and its "No read of a loaded record runs capability code"
  paragraph SHALL say that the tool objects are decided too, that the check holds at load (a change
  the capability's own code makes to a tool object afterwards is not covered), and that
  `issues/capability-tool-objects-served-copy.md` takes that up (Q1).

## Non-goals (no-gos)

- **The handler and what it does when called.** `fn` is the capability's code by design (the core's
  text wrapper around the capability's function, `tools/__init__.py:73-74`); this cycle neither
  checks nor wraps what it does.
- **The core's own tools** (`CORE_TOOLS`, `CLOSING_TOOLS`): the core's code, not a capability's.
- **The capability record and its resources.** Already exact since `capability-probe`; resource
  handlers are code by design, as `fn` is. Not reopened.
- **A retried load after a failed one** (what the registry and `sys.modules` hold after a refusal):
  the sibling cycle `capability-reload-after-failure`. R6 keeps today's cut-back, nothing more.
- **Changing `@mcp_tool`, or what any tool serves.** The served surface stays byte-for-byte (R5).
- **Changing the FastMCP pin or range** (`fastmcp>=4,<5`, locked at 4.1.4). R4 reacts to a model
  change; it does not move the pin.
- **Guarding a tool object against change after the load** (a handler that edits its own tool at
  request time, or serving a copy rebuilt from the checked values): ruled out (Q1) and filed as
  `issues/capability-tool-objects-served-copy.md`.

## Clarifications

- **Q1:** Should the load serve a copy it built, so that a later change to a tool object by the
  capability's own code (from a handler, at request time) cannot reach the served tool? — **A:**
  2026-11-12 · foreman ruling at GOAL sign-off: no, out of scope. It is not recorded as an accepted
  limit: it is filed as the seed `issues/capability-tool-objects-served-copy.md` (kind fix, appetite
  small, unshaped), with a ROADMAP entry in Part I's Safety group. §7 says plainly that the check
  holds at load, and names the seed (R7).
- **Q2:** Some `FunctionTool` fields in the locked FastMCP 4.1.4 have no single built-in type to be
  exact to: a field typed `Any` (`return_type`) or holding `Any` values (`parameters`, `meta`), a
  callable-valued field other than `fn` (`auth`), and fields holding FastMCP or MCP models
  (`annotations`, `execution`, `task_config`, `icons`). What does the load accept there? — **A:**
  2026-11-12 · foreman ruling at GOAL sign-off: the plan sweeps every `FunctionTool` field of the
  installed FastMCP and proposes a rule per field: exact type; or an excepted callable, as `fn` is;
  or only what `Tool.from_function` gives it through `@mcp_tool`. The rules are ruled at the plan
  gate. The GOAL fixes the principle: no field is left unchecked, and no check reads a value before
  its type is known (R2).
- **Q3:** Users install from git within the declared range (`fastmcp>=4,<5`, § Packaging; the lock is
  not read), so the FastMCP a server runs can be newer than the one the suite ran. What happens when
  a FastMCP release adds a `FunctionTool` field? — **A:** 2026-11-12 · foreman ruling at GOAL
  sign-off: the checks follow the installed FastMCP's model at run time (R4). A field no rule names,
  on a newer FastMCP within the declared range, is checked by a generic rule the plan proposes (for
  example, plain JSON-like values only, anything else refused); it is never skipped silently, and it
  never refuses every capability just for being unknown. The suite also fails when the locked
  FastMCP gains a field no rule covers. If the plan finds no workable generic rule, it brings that
  to the plan gate. No pin or range change.
- **Depth in R2** — **A:** 2026-11-12 · foreman ruling at GOAL sign-off: kept; a field's rule holds
  at any depth.
- **Security** — **A:** 2026-11-12 · foreman ruling at GOAL sign-off: not security work. Capability
  code is installed by the operator and already runs at import; this is §7's inertness rule.
- **Q-B (plan), `fn`'s rule** — **A:** 2026-11-12 · foreman ruling at plan sign-off: `fn` is no longer
  wholly excepted. It SHALL be exactly a function (`types.FunctionType`, an `async def` included) whose
  `__module__` is exactly a `str`, so that deciding and wording any refusal runs no capability code;
  what it does when a request calls it stays excepted. This changes the reading of R2's "an excepted
  callable, as `fn` is" and of the Outcome's "the handler (`fn`) is excepted": the handler's behaviour
  is excepted, its type and module are decided. All 17 member tools pass (checked at the ruling).
- **Q-C (plan), `return_type` at a call** — **A:** 2026-11-12 · foreman ruling at plan sign-off:
  serializing a tool's declared `return_type` at a call is part of the call (R3's "a tool call SHALL
  run only that tool's handler").
- **Q-D (plan), a field no rule names** — **A:** 2026-11-12 · foreman ruling at plan sign-off: the
  plan's generic rule refused a value neither JSON-like nor its default, which would refuse every
  capability for an unknown field, against Q3's ruling. Instead such a value is served undecided with
  one WARNING per field per process (R4 amended). R3's "every capability's tools pass R1 and R2" reads
  over the fields a rule names; an undecided field is the warned exception.

## Notes

- **Overlap with `capability-reload-after-failure`**, shaped in parallel: both change `load()` in
  `core/capabilities.py` (it changes what a failed load leaves behind for a retry; this cycle adds a
  check before the load's first read of each registered entry, and changes the refusal at
  `:330-332`). Neither absorbs the other. Whichever lands second rebases onto the first and keeps
  both contracts: this cycle's refusals SHALL leave the state the sibling's retry contract requires.
- **Human gate.** `core/capabilities.py` is a high-blast-radius path (§ Invariants, "decides which
  capabilities load, which tools each registers"); review takes the human gate on a confirmed
  finding there.
- **Mutation gate.** Review grades mutation findings by the factory's mutation-testing method
  (operator's KB, `method/mutation-testing.md` § When a review is done).
- **Roadmap.** One of four cycles that land before the next Part of the roadmap starts, since every
  capability family registers through this load.

## Related materials

- Seed: [`issues/capability-tool-objects-inert.md`](../../issues/capability-tool-objects-inert.md)
- ROADMAP: Part I, Before Part II, "A capability's registered tool objects can run its code when they
  are read"
- Prior cycles: [`spec/capability-probe/`](../capability-probe/) (TECH P2, review cycle 1's F1;
  REVIEW, cycle 2's rulings at the bound, 2026-11-01, which seeded this cycle);
  [`spec/capability-extras/`](../capability-extras/) (the load, and the `isinstance` check)
- Filed from this shaping (Q1): [`issues/capability-tool-objects-served-copy.md`](../../issues/capability-tool-objects-served-copy.md)
- Sibling: [`issues/capability-reload-after-failure.md`](../../issues/capability-reload-after-failure.md)
- `AGENTS.md` § Invariants §7, § Invariants (high-blast-radius paths), § Packaging
- Source: `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py` (`load`, `serve`),
  `core/tools/__init__.py` (`TOOL_REGISTRY`, `mcp_tool`), `core/server.py` (`create_mcp_server`)
- Tests: `tests/test_capabilities.py`, `tests/test_startup.py`, `tests/test_surface.py`
