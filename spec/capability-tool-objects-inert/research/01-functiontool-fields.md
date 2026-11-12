# Research 01: every `FunctionTool` field, who reads it, and a rule for each

FastMCP 4.1.4, pydantic 2.12.5, Python 3.14. `FM` = `.venv/lib/python3.14/site-packages/fastmcp`.
Probes ran in a throwaway lab outside the repo; the members' 17 tools came from `installed()`.

## Model facts

- `FunctionTool.model_config == {'extra': 'forbid'}`. There is no `validate_assignment`, so
  `tool.field = X` stores X unchecked (probed: a `dict` subclass for `parameters`, a `str` subclass for
  `name`, `'notafloat'` for `timeout` all stick). The model has no private attributes.
- Construction validation makes the **top level** exact: a `str` subclass passed as `name` or
  `description` (as a kwarg, or through a function's `__name__`/`__doc__`) comes out as exact `str`.
  A `dict` subclass for `parameters` or `meta` comes out as exact `dict`, and a `set` subclass for
  `tags` comes out as `set`. **Below the top level, `dict[str, Any]` keeps the values it is given**:
  `meta={'a': D()}` keeps `D`, and `parameters={'type': S('object')}` keeps `S`. So the `Any` depth
  is open even without assignment.
- `from_function` can put non-exact values deep inside `parameters` with no assignment at all: a
  callable `Field(json_schema_extra=...)` edits the schema dict in place (probe: an arbitrary object
  and a `str` subclass under `properties/x`). Static extras, examples and defaults are passed
  through `to_jsonable_python`, so they come out as exact built-ins.
- The object-state slots are `__dict__`, `__pydantic_fields_set__`, `__pydantic_extra__` and
  `__pydantic_private__`, all from `BaseModel.__slots__`. All four can be replaced:
  `object.__setattr__(tool, '__dict__', DictSub(...))` works, and so does a plain `tool.__dict__ = ...`.
  `object.__setattr__(tool, 'zzz', 1)` adds a key to `__dict__`, though `tool.zzz = 1` is refused.
- `add_tool` stores **the object itself**, not a copy (`server/providers/local_provider/decorators/tools.py:156`
  → `local_provider.py:200`). TOOL_REGISTRY, the load's scratch server and every served server
  hold the same object, and listing yields it unchanged (`local_provider.py:347-349`). The only
  places that copy are the visibility transform (`transforms/visibility.py:204`) and Prefab
  rewriting (`prefab_synthesis.py:262`), and neither path is used by the core.

## Who reads what, when

- **Registration** (`add_tool`, which runs twice: on the load's scratch server and in `create_mcp_server`):
  - `key` reads name and version (`utilities/components.py:187-188`).
  - `_check_version_mixing` reads version (`local_provider.py:149-161`).
  - `_maybe_apply_prefab_ui` reads `meta`, and `_has_prefab_return_type` reads **`return_type`**
    (`decorators/tools.py:90-98`, `:55-62`). That means `isinstance(rt, type)`, then
    `getattr(rt, '__module__')` followed by `==` and `.startswith`
    (`utilities/prefab.py:29-48`), then `get_origin`/`get_args` recursion.
  - `fn` is not read here.
- **Listing** (`server.py:829-876`, then `mixins/mcp_operations.py:136-151`):
  - `is_enabled` reads `meta` (`visibility.py:300-303`) and `_is_prefab_tool` reads `meta`
    (`prefab_synthesis.py:36-44`).
  - `_component_auth_allows` reads **`auth` and calls every check in it** on SSE and
    streamable-HTTP (`server.py:237-248`, called at `:876`). Under stdio it returns before reading
    `auth`. The core serves all three transports (`core/__init__.py:232-236`).
  - `dedupe_with_versions` and `version_sort_key` read version (`utilities/versions.py:234`, `:306-329`).
  - `to_mcp_tool` (`tools/base.py:269-309`) reads name, title, annotations (an `isinstance(dict)`
    check, then `.title`), description, parameters, output_schema, icons and execution. It also
    calls `get_meta()`, which runs `sorted(self.tags)`, reads version and runs `dict(meta)`
    (`components.py:199-216`), and `task_config.supports_tasks()` and `.mode`.
  - The resulting `MCPTool` is validated (pydantic keeps `Any` values by reference) and serialized
    to the wire.
  - `resources/list` and `resources/read` also go through every tool's `meta`
    (`prefab_synthesis.py:166-238`).
  - Server start reads `task_config.supports_tasks()` (`mixins/lifespan.py:148`, `server.py:800-805`).
  - **`fn` and `return_type` are never read at listing.**
- **A call** (`server.py:1389-1490`, `tools/function_tool.py:423-566`):
  - `get_tool` reads name, version, `meta` (`is_enabled`) and `auth`, plus `get_span_attributes`.
  - The handler path reads `fn` (`_wrap_body_errors` is an `lru_cache`, so it hashes `fn`, then
    runs `get_type_hints`/`signature`), `run_in_thread` (`:439`, `:537`) and `timeout`
    (`:472-497`, `anyio.fail_after`).
  - `convert_result` reads `output_schema` (`is None`, `.get('x-fastmcp-wrap-result')`) and
    **`return_type`** (`tools/base.py:409-441`). The latter goes through
    `_serialize_to_jsonable(raw, self.return_type)` → `get_cached_typeadapter(return_type)`, which is
    an **`lru_cache` (it hashes and `==`-compares the value) feeding `TypeAdapter(return_type).dump_python`**
    (`utilities/types.py:74-149`, `tools/base.py:77-93`).
- **Generic model operations:**
  - `__eq__` compares `type() is`, then `model_dump()` (`components.py:218-223`). `model_dump`
    includes `fn` and excludes `return_type` and `auth` (`exclude=True`).
  - `__repr__` reads name, version, title, description and tags.
  - `model_copy` reads `__dict__`, fields_set, extra and private.
  - The core's own path calls none of these on a capability tool (`_tools_of` uses `in` only
    against the core's tools).

## Nested models

| Model | Fields and types |
|---|---|
| `mcp_types.Icon` | `src: str`, `mime_type: str\|None`, `sizes: list[str]\|None`, `theme: Literal['light','dark']\|None` |
| `ToolAnnotations` | `title: str\|None`, and four `*_hint: bool\|None` fields (read-only, destructive, idempotent, open-world) |
| `ToolExecution` | `task_support: Literal['forbidden','optional','required']\|None` |
| `TaskConfig` | A plain, non-frozen dataclass with no slots: `mode: str` (a Literal) and `poll_interval: timedelta`. Its instance `__dict__` can be replaced, as the tool's can. |

All three MCP models keep pydantic's default `extra` setting, so `__pydantic_extra__` is None.

## What `@mcp_tool` gives (all 17 member tools, exact types at every depth)

- `name`: `str`.
- `description`: `str` (the full docstring).
- `version`, `title`, `icons`, `meta`, `annotations`, `execution`, `auth` and `timeout`: `None`.
- `tags`: `set()`.
- `run_in_thread`: `True`.
- `task_config`: exactly `TaskConfig`, with `vars == {'mode': 'forbidden', 'poll_interval': timedelta(seconds=5)}`.
- `parameters` and `output_schema`: exact `dict`/`list`/`str`/`bool`/`None`. No int or float occurs in
  the members' schemas, but an `int` default does produce one, so the rule must allow them.
  `output_schema` carries `x-fastmcp-wrap-result: True` on 16 tools.
- `return_type`: the `str` class on 16 tools, and `cluster_mcp.rcac.tools.StoragePaths` on one
  (a capability-defined `@dataclass` whose metaclass is `type`).
- `fn`: an exact `function`, with `fn.__module__` an exact `str`.
- `__dict__`: an exact `dict` whose keys are exactly the 17 field names.
- `__pydantic_fields_set__`: 16 names (every field but `execution`).
- `__pydantic_extra__` and `__pydantic_private__`: `None`.

How `from_function` fills `return_type` for ordinary functions:

| Return annotation | `return_type` | `output_schema` |
|---|---|---|
| `-> str` | `str` | wrapped |
| `-> list[str]` | a `types.GenericAlias` | wrapped |
| `-> dict` | `dict` | object |
| `-> DC` (a dataclass) | `DC` | object |
| `-> DC \| None` | `typing.Union` | wrapped |
| none | `inspect._empty` | `None` |
| `-> None` | `NoneType`, after string resolution | wrapped |
| `-> Any` | `typing.Any`, whose type is `_AnyMeta` | `None` |
| `-> list` | `list` | `None` |

How the other fields are derived:
- `output_schema` comes from the return type's serialization schema (`function_parsing.py:414-549`).
- `run_in_thread` is `True` unless a value is passed.
- `task_config` is `TaskConfig(mode='forbidden')` unless `task=` is given (`function_tool.py:379-387`).

## Proposed rules

"Exact JSON" (J) means, at every depth: exactly `None`, `bool`, `int`, `float`, `str`, or `list`
or `dict` with exact-`str` keys. The check tests the type before reading anything else, and it
refuses cycles.

| Field | Rule | Accepted shape | Why (the read it protects) |
|---|---|---|---|
| name | J | exact `str` | Read by the load (`:342-360`), the key at add_tool, listing and calls |
| version | F | `None` | Read by the key, version mixing, dedupe/sort and `get_meta` |
| title | F | `None` | `to_mcp_tool` truthiness at listing |
| description | J | exact `str` or `None` | Listing (`to_mcp_tool`), `__repr__` |
| icons | F | `None` | Listing (`to_mcp_tool` → wire). The J alternative would be an exact `list` of exact `Icon`, deep. |
| tags | F | exact `set`, empty | `sorted()` in `get_meta` at listing |
| meta | F | `None` | Read at add_tool, at listing, at resources/list and read, and by `get_tool` |
| task_config | F | exact `TaskConfig`, exact `dict` `vars` with keys {mode, poll_interval}; mode an exact `str` equal to `'forbidden'`; poll_interval an exact `timedelta` of 5 s | `supports_tasks()` and `.mode` at listing and server start |
| return_type | T (new, structural) | `None`, `inspect.Signature.empty`, or a class whose type is exactly `type`, with an exact-`str` `__module__` and exact-`str` keys in `vars(cls)`. Also an exact `types.GenericAlias`, `typing._GenericAlias` or `typing.Union` whose `__origin__` and exact-`tuple` `__args__` pass the same rule. | Read at **add_tool**: `isinstance`, `__module__ ==`, `get_origin`/`get_args`. Read at a call by the lru_cache hash and by `TypeAdapter`. |
| parameters | J | exact `dict`, deep | Listing (`to_mcp_tool` → wire) |
| output_schema | J | `None`, or an exact `dict`, deep | Listing, and `convert_result` at a call |
| annotations | F | `None` | Listing. The J alternative would be an exact `ToolAnnotations` with exact field values and the slot checks. |
| execution | F | `None` | Listing |
| auth | F | `None` (**not** X) | Its checks would run at **listing** on HTTP/SSE, which violates R3 |
| timeout | F | `None` | Read at a call (`fail_after`, arithmetic). The J alternative would be `None` or an exact finite `float`. |
| fn | X | excepted | Only a call reads it (but see risk 1) |
| run_in_thread | F | `is True` | Read at a call |
| `__dict__` | J | exact `dict`, keys exactly the `model_fields` names, as exact `str` | Every attribute read goes through it, and a subclass, or a key that is a `str` subclass, runs code on lookup |
| `__pydantic_fields_set__` | J | exact `set` of exact `str`, a subset of the field names | `model_copy` and `model_dump(exclude_unset)` |
| `__pydantic_extra__`, `__pydantic_private__` | F | `None` | `model_dump`/`model_copy`, and `__getattr__` fallbacks |

**R4 generic rule (proposed):** a field no rule names must hold exact JSON, deep (J), or a value
whose type is exactly that of the field's own default
(`FieldInfo.get_default(call_default_factory=True)`). In the second case, a pydantic model or
dataclass default has its fields checked by the same rule, recursively. A new field that
`from_function` leaves at a model default then passes, and a capability is not refused only
because the field is unknown.

**Served surface:** every F value above is exactly what all 17 member tools hold today. No rule
changes the object, since the check only reads, so `test_served_surface_matches_baseline` stays
byte-for-byte. `fields_set` must not be required to equal every field (`execution` is unset).

## Open questions and risks

1. **`fn.__module__` is read by the core before anything else**, at `core/capabilities.py:334` and
   `:341` (`_below` runs `==` and `.startswith`). A probe showed that `functools.wraps` carries a
   `str`-subclass `__module__` from the capability's function into `tool.fn` **through
   `@mcp_tool`, with no assignment** (`S.__eq__` and `S.startswith` would run at load). `fn` is X,
   but the core's own read of it is not a call. Propose: `type(fn) is types.FunctionType` and
   `type(fn.__module__) is str`, checked before `:333`. This needs a plan-gate ruling, since it
   checks part of `fn`.
2. **`return_type` at call time:** `TypeAdapter(StoragePaths)` evaluates the dataclass's
   (string, under `from __future__`) field annotations in the capability module's globals, and
   honours any `__get_pydantic_core_schema__` or serializer hooks. That is capability code at a
   call, outside `fn`. The rcac member needs a capability class here, so neither "exact built-in"
   nor F-by-value is possible. The ruling to ask for: the call-time serialization through the
   handler's declared return type counts as "the handler" (R3), with only the registration read
   made inert by rule T. The alternative, walking into the class (field types, hooks), is far
   larger than a small appetite.
3. Rule T reads `vars(cls)`. A class built with `type(name, bases, ns)` from a namespace with
   `str`-subclass keys is an edge case; requiring exact-`str` keys covers it at the cost of one
   pass over the keys.
4. **Ordering:** each tool's slots and fields have to be checked right after the type check at
   `:330`, before `:333`'s `fn.__module__` and `:341`'s full-registry pass. Otherwise a planted
   tool is read first.
5. **Sibling overlap:** `capability-reload-after-failure` changes the same block; the refusal must
   still `del TOOL_REGISTRY[start:]`.
6. **F versus J for the constant fields** (version, title, icons, meta, annotations, timeout): F is
   tighter and simpler. J keeps future members able to set, say, `annotations` or `meta`. This is
   a gate choice: F would refuse a future member that uses them until the rule is widened.
