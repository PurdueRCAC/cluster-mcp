# Research digest — capability-tool-objects-inert

Three briefs, consolidated; where they disagree, the recommendation below is the one the plan takes.

- [`01-functiontool-fields.md`](01-functiontool-fields.md): every `FunctionTool` field of FastMCP 4.1.4
  (installed = locked), what `@mcp_tool` gives it, and who reads it when.
- [`02-inert-reads-and-generic-rule.md`](02-inert-reads-and-generic-rule.md): reading a tool's state
  and naming a type without running code; the JSON walker; the generic rule for an unnamed field.
- [`03-tests-mutants-sibling.md`](03-tests-mutants-sibling.md): the refusal tests, the CLI drives,
  the mutation cases the change re-plants, the prior cycle's gates, the sibling cycle.

## Decisions

1. **Every registry entry decided before the load's first read of it.** `_tool_violation(entry)`
   replaces the `isinstance` check (`load()` `:330-332`); a walk hands it every entry of
   `TOOL_REGISTRY`, before `stray` reads `fn` and `name` (after the adversarial review, the walk runs
   three times a capability and includes the core's tools: PLAN § 2, § 7).
   Brief 03 found the attribution (`:341`) reads entries registered before the load began, which no
   check saw; walking the whole registry covers them, and covers whatever a retry of the sibling's
   leaves there.
2. **Read state without reading values.** `type(entry) is FunctionTool`, then `object.__getattribute__`
   for `__dict__` and the three pydantic slots, `type(...) is` checks, keys checked exactly `str` by
   iteration before any lookup, `is` chains only (brief 02: `in` on a tuple of types runs a metaclass
   `__eq__`).
3. **Field rules** (brief 01's table, with one change): exact JSON (J) for `name`, `description`,
   `parameters`, `output_schema`; the field's own declared default (F) for the eleven fields
   `@mcp_tool` always leaves at it; a structural rule (T) for `return_type`; `fn` excepted. Brief 01
   proposed checking `fn`'s type and `__module__` (its risk 1); the plan does not (PLAN § 5, question
   for the gate): GOAL excepts `fn`, its `__module__` is read only by the load itself, inside the
   guard, as §7 already counts, and the existing `declared` timing rows are carried by exactly that read.
4. **F is "the field's declared default", compared node for node** (`_same`), so `task_config`'s
   `TaskConfig(mode='forbidden')` and `tags`' `set()` need no rule of their own; a test pins that a
   fresh `Tool.from_function` gives each F field that default.
5. **Generic rule: brief 02's (ii)** — JSON-like at every depth, or the field's own default.
   Brief 01's variant (exactly the default's type, fields recursively) accepts non-default values of
   a model type; (ii) is stricter and has the same known limit (PLAN § 5).
6. **Type naming:** `str.__str__(type.__dict__['__name__'].__get__(kind))` (brief 02 § 2).
7. **The `served-tool` timing** (brief 03, risk 1): once tools are exact, nothing of a capability's
   runs at `add_tool`; its rows are re-carried by a planted module that replaces `FastMCP.add_tool`
   (capability code at import can change any module), restoring it as it raises. Prototyped: all 40
   rows pass on the prototype with the new carrier.
8. **No depth or size bound** (brief 02 suggested 64 and 10 000): not inertness, and a new refusal
   with figures to rule. The walker is iterative and refuses a container met twice, so a cycle ends.
9. **Mutation:** the alternatives sweep of `capability-probe`, retargeted (231 alternatives on the
   first prototype, 358 after the review's folds); every loader case anchored in `load()` or killed by a `served-tool` row re-run (86 on
   the prototype). Measured: three loader cases 9 s handshake, 8 s modern.
