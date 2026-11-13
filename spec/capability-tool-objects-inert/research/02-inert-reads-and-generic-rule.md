# Research 02: inert reads, type naming, the JSON walker, the generic rule

Probed on CPython 3.14, FastMCP 4.1.4, pydantic 2.12.5, in a throwaway lab outside the repo. Each
claim below is from a probe unless it is marked as inference.

## 1. Reading a FunctionTool's state

- Once `type(tool) is FunctionTool`, `tool.__dict__` and `vars(tool)` resolve through
  `BaseModel`'s `__dict__` getset (FastMCP and pydantic code only; `FunctionTool.__getattribute__ is
  object.__getattribute__`). The instance state is `__dict__` plus three slots,
  `__pydantic_fields_set__`, `__pydantic_extra__` and `__pydantic_private__` (`__weakref__` is
  managed by C and cannot be set).
- **The instance dict can be swapped**: `object.__setattr__(tool, '__dict__', Sub(...))` succeeds,
  and `vars(tool)` then returns the subclass. Ordinary attribute reads do not call its overrides,
  but `model_copy` and similar paths do. Check `type(d) is dict` first.
- **A `str`-subclass key can be planted**: `tool.__dict__[S('evil')] = 1`. A key that replaces a
  field name (`d[S('name')] = d.pop('name')`) runs `S.__eq__` on **every** `tool.name` read and on
  `'name' in d`. Iterating an exact dict and testing `type(k) is str` runs no key code. A plain
  `for k in d` over an exact dict calls no `__iter__`, `__eq__` or `__hash__`. Every key check
  must come before any `d[k]`, `in`, `.get()` or attribute read.
- **Dict keys equal model fields**: for a tool from `from_function`, `list(tool.__dict__)` equals
  `list(FunctionTool.model_fields)`, order included. After the exact-`str` key check,
  `d.keys() == FunctionTool.__pydantic_fields__.keys()` runs only C code. Use it as a check: it
  refuses an extra key (which nothing reads today, so the refusal is precautionary) and a missing
  one.
- **The slots** accept arbitrary objects through `object.__setattr__`. Reading them with
  `object.__getattribute__` runs nothing, and `add_tool`, `list_tools` and `call_tool` ran none of
  a planted object's code. `model_copy()` does read `__pydantic_private__` (it ran the planted
  object's `__getattribute__('items')`), so a later FastMCP copy path would be exposed. The
  proposed rule:
  - `__pydantic_extra__ is None` (the model has `extra='forbid'`);
  - `__pydantic_private__ is None` (`FunctionTool.__private_attributes__ == {}`);
  - `__pydantic_fields_set__` is exactly `set`, with each element exactly `str` and in the model's
    fields. Members hold 16 of the 17 names (`execution` is absent), so test with subset, not
    equality.

## 2. Naming a type without running its code

- `type(x).__name__` **runs a metaclass's code**, either a `__name__` property on the metaclass or
  a metaclass `__getattribute__`. A probe returned `'Spoof'` and logged the call.
- `cls.__name__` **can be a `str` subclass**. `B.__name__ = S('Bee')` is accepted and stored as is,
  and so is `type(S('Cee'), (), {})`. Formatting it into an f-string then runs `S.__format__`.
- What works, and ran nothing under probe:
  `str.__str__(type.__dict__['__name__'].__get__(type(x)))`. `type.__dict__` is a read-only
  mappingproxy of the builtin, the getter is C, and `str.__str__` returns an exact `str` copy of a
  `str` subclass without calling its `__str__` or `__format__`. `''.join([n])` also yields an exact
  `str`. `str(n)` does **not**: it ran `S.__str__`. Use the same getter for `__qualname__`.
- **Existing code is affected (report only, out of scope)**: `_checked`, `_check_resource` and the
  `load()` refusal at `:330` all use `type(value).__name__` inside f-strings. `_shown` uses
  `type(value) in (bool, int, type(None))`, and **that runs a metaclass `__eq__`**: a tuple's
  `in` falls back to `==`, and a metaclass that overrides `__eq__` is tried first, three calls
  logged. `type(v) in {…}` hashes, so it would run a metaclass `__hash__`. Only `is` chains are
  safe. The new walker must use `t is A or t is B`, never `in`. This is worth a seed for the
  record checks.

## 3. A deep exact-type walker for JSON-like values

- Accept `None`, exactly `bool`, `int`, `float` and `str` (an `is` chain, so `bool` is told apart
  from `int`), and exactly `list` or `dict`, where every key is exactly `str`, checked by iterating
  before any value is read. Use an iterative stack, not recursion.
- **Cycles and sharing**: keep a seen-set of container ids and refuse a revisit. The members' and
  the core's 24 tools hold no shared or cyclic node, within a field or across tools or fields.
  Their largest schema has 144 nodes and depth 6.
- **Depth bound**: FastMCP lists a 250-deep `parameters` and fails at 260 with an internal server
  error from `list_tools`, which `add_tool` at load does **not** catch. A bound well under that
  (64 is suggested) catches a value that would break listing later, and a node cap (10 000 is
  suggested) bounds the time a check can take. A cyclic list, 200 000-deep nesting, `str`-subclass
  values and keys, and a `list` subclass were all refused under probe with no code run.
- **NaN** is an exact `float` and is read with no code run. It is accepted as JSON-like (pydantic
  serialises it). Any equality-based rule must special-case it (`a != a and b != b`).
- **Sets**: `tags` is `set[str]` (the factory `set()`, empty in every member). Iterating an exact
  `set` or `frozenset` runs no element code. Accept exact `set`/`frozenset` whose elements are
  exact scalars, and exact `tuple` as a list. `return_type` holds a class (23 tools) or a
  `typing.List[...]` alias (1 tool). It is not JSON-like and needs its own named rule.

## 4. The generic rule for a field no rule names

| | Member tool, new field model-typed with a factory default | Capability code run | Cost |
|---|---|---|---|
| (i) JSON-like only | **refused** (`task_config` fails: `TaskConfig` dataclass holding a `timedelta`) | none | small |
| (ii) JSON-like, or the field's own default | passes | none (FastMCP's factory only) | moderate |
| (iii) equal to a fresh `from_function` re-derivation | passes, but needs typing `==` | much | high |

- **(ii) in detail**:
  1. Accept the value if it is JSON-like.
  2. Otherwise accept it if `value is info.default`.
  3. Otherwise, when `info.default_factory` is set and
     `info.default_factory_takes_validated_data` is False (pydantic 2.12 has that attribute; never
     call a factory that takes data), compare the value node for node with a fresh `default_factory()`:
     - compare `type(a) is type(b)` first;
     - accept `a is b`;
     - compare scalars with `==`;
     - compare lists, dicts and sets as in the walker;
     - walk a dataclass or pydantic node only when its type is identical to the fresh default's
       (a FastMCP type, not the capability's), with its `__dict__` checked as exactly `dict` (and a
       pydantic node's slots as in §1);
     - compare a leaf without a `__dict__`, such as `timedelta`, with `==` only for a static (C)
       type. The probe gate was `not t.__flags__ & (1 << 9)`; this is fragile if the stdlib moves
       to heap types, so an explicit allowlist (`timedelta`, `datetime`) is the safer choice.
- Under probe, (ii) accepted every field of all 24 tools except `return_type`. It refused
  `TaskConfig(poll_interval=<timedelta subclass>)` and a non-default `TaskConfig(mode='optional')`.
- **(iii)** runs a lot of capability code. `inspect.signature` follows `__wrapped__` to the
  capability's function, reads its `__signature__` and annotations (3.14 evaluates them lazily),
  pydantic calls the schema hooks of the capability's types, and the docstring is read. It
  re-derived every field identically in 14 ms, except `list_directory`'s `return_type`: a fresh
  `typing.List[FileInfo]` that is not the same object, so the comparison needs typing's `__eq__`.
  That `__eq__` compares capability classes, and a capability metaclass's `__eq__` could run.
  This conflicts with R2's "runs none of the value's code" in spirit, and is fragile.
- **Recommendation: (ii).** Its honest limit: a newer FastMCP field that `from_function` fills with
  a value that is neither JSON-like nor its default (as `return_type` is today) would refuse every
  capability on that FastMCP. That failure is loud at startup, not silent. No generic rule covers
  it without running capability code, so it goes to the plan gate as the known limit of R4's "never
  refuse only because unknown".
- **Simulating "a field no rule names" in a test**: monkeypatch the rule table to drop a known
  field, such as `task_config` (a model with a factory default) or `meta`.
  - Members still load. Parametrise over every field except `fn` and `return_type`; dropping
    `return_type` refuses the members under (ii), by the limit above.
  - A planted tool whose dropped field holds a bad value, such as `task_config.poll_interval` as a
    `timedelta` subclass or `meta = {S('k'): 1}`, is refused, naming the field. That kills a
    mutant that iterates the rule table instead of `FunctionTool.model_fields`, because the mutant
    skips the field and accepts the tool.
  - Stronger: `pydantic.create_model('FunctionTool', __base__=FunctionTool, extra_cfg=(TaskConfig,
    Field(default_factory=...)))`. Its `from_function` returns instances that hold the new field at
    its default. Monkeypatching the load module's `FunctionTool` reference to it simulates a newer
    FastMCP end to end, but every member tool would have to be rebuilt from it.

## 5. Following the installed model at run time

- Read `FunctionTool.model_fields` at the **class**: a `dict`, `is FunctionTool.__pydantic_fields__`,
  17 keys, each exactly `str`, in definition order. Reading it on an instance emits
  `PydanticDeprecatedSince211`, since `BaseModel.model_fields` is a
  `deprecated_instance_property`. Read `__pydantic_fields__` directly, or the class attribute.
- The instance `__dict__` keys always equal the model's field keys for a `from_function` tool, so
  "dict keys == model fields" is a sound check (§1).
- Fail the suite when the lock moves: assert that
  `FunctionTool.model_fields.keys() - {'fn'} == RULES.keys()`. With equality, a rule left for a
  removed field fails too. The test reads the class at test time, so a re-lock to a FastMCP with a
  new field fails it.

## Open questions and risks

- **Plan gate**: (ii) cannot cover a new field that `from_function` derives as a non-JSON,
  non-default value. That limit has to be accepted, or the field gets a named rule when the pin
  moves.
- The class itself is not checked. Capability code runs at import and could monkeypatch
  `FunctionTool` (a data descriptor named `name` on the class outranks the instance dict) or
  replace `model_fields`. Inference: this is outside "objects handed to the core", but §7 should
  say so.
- Walking a FastMCP-typed default node with `__slots__` and no `__dict__` is refused under (ii),
  which would refuse members if such a default appeared.
- The `_shown` and `type(x).__name__` exposures in the record checks are pre-existing and out of
  scope.
- Depth and node bounds are new refusals. Members sit far below them (144 nodes, depth 6), but the
  chosen numbers should be ruled.
