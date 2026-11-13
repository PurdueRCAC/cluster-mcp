# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The capability contract: what an installed distribution adds to the server, and how it is loaded.

A capability is a distribution that declares one entry point in the group `cluster_mcp.capabilities`,
naming a `Capability`: its name, its place in the served instructions, the module whose `@mcp_tool`
functions are its tools, its part of the instructions, its resources, and the commands it needs on
the cluster. The core never names one.
A capability's resources are never open: each needs its request's executor, so in `delegate` mode
every read of one resolves the caller. The commands are data, never code: the core looks each one
up on the cluster (`cluster_mcp.core.probes`), and a capability that declares none is served wherever
it is installed.

Nothing here runs at import. `installed()` loads every capability the environment has, once, when
the server starts; a capability that cannot be discovered, ordered or loaded stops the load with a
`CapabilityLoadError` naming its distribution, whatever its code raised or exited with (but a
`KeyboardInterrupt`, which still interrupts), and leaves the tool registry as it was before the load
began. What the failed load imported stays imported, where a later load would find it and run none of
it again, so every later load in the process is refused, naming that failure and saying to restart
the process. The load assembles each capability's tools and resources on a scratch server through
`serve()`, the one way every server takes them, so whatever a capability declares fails at the load
or not at all. What an entry point names must be exactly a `Capability`, and every value in it the core
or FastMCP reads exactly a built-in type, as must its distribution's name; the load refuses anything
else before using it, so no read of a loaded record runs capability code. Every tool the registry holds is
decided at load too: exactly a `FunctionTool` holding in every field what its rule accepts (`TOOL_RULES`).
A capability's code is its modules, run at the load; its resource handlers, which FastMCP reads as it
registers them, on the load's scratch server and on each server built after; and the handler of each of
its tools and resources, which a request calls.
"""

# Type annotations
from __future__ import annotations
from typing import Final, Iterable, NamedTuple

# Standard libs
import abc
import enum
import inspect
import types
import typing
import re
import warnings
from dataclasses import dataclass
from datetime import timedelta
from importlib import import_module
from importlib.metadata import Distribution, EntryPoint, distributions, entry_points

# External libs
import fastmcp
from cmdkit.logging import Logger
from fastmcp import FastMCP
from fastmcp.tools import Tool
from fastmcp.tools.function_tool import FunctionTool
from pydantic import BaseModel
from pydantic.fields import FieldInfo

# Internal libs
from cluster_mcp.core.resources import RESOURCE_REGISTRY
from cluster_mcp.core.tools import CORE_TOOLS, TOOL_REGISTRY

# Public interface
__all__ = ['GROUP', 'Capability', 'Loaded', 'CapabilityLoadError', 'serve', 'load', 'installed', 'composed']


# The entry-point group every capability distribution declares itself in.
GROUP: Final = 'cluster_mcp.capabilities'

# A tool's line in an instructions text: `- name: what it does`.
LISTED: Final = re.compile(r'^- (\w+):', re.MULTILINE)

# A command a capability may declare it needs: a plain file name, as `exec` finds one on PATH. No
# path, no space or shell character, and no leading `-` or `.`.
COMMAND: Final = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.+-]{0,254}')


@dataclass(frozen=True)
class Capability:
    """What a capability distribution adds to the server, as its entry point names it.

    Every value is exactly the type named here, never a subclass (`order` never a `bool`), and the load
    refuses anything else: the core reads them after the load, where a subclass's code would run.

    `name` is unique among the loaded capabilities. `order` places its text in the served base,
    lower first: a site overlay takes a high one, so it sits last, directly above the site context.
    `tools` is the dotted name of the module whose `@mcp_tool` functions (that module's or any module
    below it) are its tools. `instructions` is its part of the base and lists exactly those tools, each
    once, as `- name:` lines. `resources` are entries shaped as the core's `RESOURCE_REGISTRY` ones,
    each a dict whose keys are `str`, with a `str` `uri`, `name` and `description`, a callable
    `handler` (the capability's code, which FastMCP registers and a request calls) and `executor`
    exactly True, its URI served by nothing else. `commands` names the commands its tools need on the
    cluster, each a plain file name (`COMMAND`) declared once, as a tuple of `str`: the core looks each
    up, and withholds the capability where one is missing. A capability that declares none, `()`, is served wherever it is installed. An entry
    point names exactly this class, never a subclass: the load refuses one.
    """

    name: str
    order: int
    tools: str
    instructions: str
    resources: tuple[dict, ...] = ()
    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class Loaded:
    """A capability that loaded: the distribution that declared it and its tools, in registration order."""

    capability: Capability
    distribution: str
    tools: tuple[Tool, ...]


class CapabilityLoadError(RuntimeError):
    """A capability that could not be loaded; `str()` is the one-line message naming its distribution."""

    def __init__(self, distribution: str, cause: str) -> None:
        self.distribution = distribution
        super().__init__(' '.join(f'cannot load capability {distribution}: {cause}'.split()))


def _identity(ep: EntryPoint) -> tuple[str, str | None]:
    """How a refusal names `ep`'s capability, and why its distribution cannot be loaded (None when it can).

    The name of the distribution that declared it. An entry point that came from no distribution (one
    built by hand) is named by its value; so is one whose distribution's metadata cannot be read or
    names no distribution (a `Name` that is not exactly a non-blank `str` names none), and that one
    cannot be loaded.
    """
    if ep.dist is None:
        return ep.value, None
    try:
        with warnings.catch_warnings():
            # A `Name` missing from the metadata reads as None, with this warning, until it raises KeyError.
            warnings.simplefilter('ignore', DeprecationWarning)
            name = ep.dist.name
    except KeyError:
        name = None
    except Exception as exc:
        return ep.value, f'its distribution metadata cannot be read: {_cause(exc)}'
    # Exactly a `str`: the name is ordered and composed after the load, where a subclass's code would run.
    if type(name) is not str or not name.strip():
        return ep.value, 'its distribution metadata has no Name'
    return name, None


class _Entry(NamedTuple):
    """An entry point to load, with the name its refusal carries and why it cannot load (None when it can)."""

    distribution: str
    nameless: str | None
    ep: EntryPoint


def _named(dist: Distribution) -> str:
    """The name in `dist`'s metadata, or where it is installed when that names none."""
    try:
        name = dist.metadata.get('Name')
    except Exception:
        name = None
    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))


def _discovered() -> tuple[EntryPoint, ...]:
    """Every entry point in `GROUP`; one installed distribution whose entry points cannot be read stops
    the load, named."""
    try:
        return tuple(entry_points(group=GROUP))
    except Exception as exc:
        unreadable = exc
    for dist in distributions():
        try:
            dist.entry_points
        except Exception as exc:
            raise CapabilityLoadError(_named(dist), f'its entry points cannot be read: {_cause(exc)}') from exc
    raise CapabilityLoadError(GROUP, f'its entry points cannot be read: {_cause(unreadable)}') from unreadable


def _cause(exc: BaseException) -> str:
    """`<ExcType>: <text>`, or the type alone when the text is empty or cannot be had (its `__str__`, a
    capability's code, raised or exited)."""
    try:
        text = str(exc)
    except KeyboardInterrupt:
        raise
    except BaseException:
        text = ''
    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__


def _below(module: str, package: str) -> bool:
    return module == package or module.startswith(package + '.')


class _Invalid(Exception):
    """A payload that is not a well-formed `Capability`; its text is the sentence saying why."""


def _checked(value: object) -> Capability:
    """`value` if it is a well-formed `Capability`; otherwise raise `_Invalid` saying why."""
    # Exactly a `Capability`, never a subclass: a subclass's code could run whenever a field is read,
    # by startup or the server long after the load, where nothing guards it.
    if type(value) is not Capability:
        raise _Invalid(f'the entry point names a {type(value).__name__}, not a Capability')
    # Every field exactly its type, never a subclass (nor a `bool` for `order`), checked before any field is
    # used: the load, startup and the server read them, ordering, hashing, iterating and formatting each,
    # and a subclass's code would run there, after the load where nothing guards it.
    for field, kind in (('name', str), ('tools', str), ('instructions', str), ('resources', tuple)):
        if type(getattr(value, field)) is not kind:
            raise _Invalid(f'its {field} is a {type(getattr(value, field)).__name__}, not a {kind.__name__}')
    if type(value.order) is not int:
        raise _Invalid(f'its order is a {type(value.order).__name__}, not an int')
    if not value.name:
        raise _Invalid('its name is empty')
    if not value.instructions.strip():
        raise _Invalid('its instructions are empty')
    for entry in value.resources:
        _check_resource(entry)
    # Exactly a tuple of exactly `str`: the probe iterates and hashes the names after the load, where
    # no subclass's `__iter__`, `__eq__` or `__hash__` may run.
    if type(value.commands) is not tuple:
        raise _Invalid(f'its commands is a {type(value.commands).__name__}, not a tuple')
    for i, command in enumerate(value.commands):
        if type(command) is not str:
            raise _Invalid(f'one of its commands is a {type(command).__name__}, not a str')
        if not COMMAND.fullmatch(command):
            raise _Invalid(f'its command {command!r} is not a command name')
        if command in value.commands[:i]:
            raise _Invalid(f'its command {command!r} is declared twice')
    return value


def _shown(value: object) -> str:
    """`value`'s repr when it is exactly a `bool`, an `int` or None, whose repr runs no capability code;
    otherwise its type, named."""
    return repr(value) if type(value) in (bool, int, type(None)) else f'a {type(value).__name__}'


def _check_resource(entry: object) -> None:
    """Raise `_Invalid` saying why `entry` is not a well-formed capability resource.

    The entry is exactly a `dict` whose every key is exactly a `str`, and its `uri`, `name` and
    `description` are exactly `str`, all checked before any is used: the load and the server look keys
    up and read, compare and hash the values, and a subclass's code would run there. Its handler is
    the capability's code, which FastMCP registers and a request calls.
    """
    if type(entry) is not dict:
        raise _Invalid(f'one of its resources is a {type(entry).__name__}, not a dict')
    for key in entry:
        if type(key) is not str:
            raise _Invalid(f'one of its resources has a {type(key).__name__} key, not a str')
    if type(entry.get('uri')) is not str:
        raise _Invalid(f'one of its resources has a {type(entry.get("uri")).__name__} uri, not a str')
    for key in ('name', 'description'):
        if type(entry.get(key)) is not str:
            raise _Invalid(f'its resource {entry["uri"]!r} has a {type(entry.get(key)).__name__} {key}, not a str')
    if not callable(entry.get('handler')):
        raise _Invalid(f'the handler of its resource {entry["uri"]!r} is not callable')
    if entry.get('executor') is not True:
        raise _Invalid(f'its resource {entry["uri"]!r} has executor {_shown(entry.get("executor"))}, not True: '
                       f'a capability resource is never open')


# Whether a tool is inert: every registry entry is decided by the rules below before the load reads it,
# each node's type decided by `is` before anything reads the node, so deciding and wording a refusal runs
# none of a capability's code. Only `is` tests a type here: `in` a tuple of types runs a metaclass's `__eq__`.

log = Logger.with_name(__name__)


def _type_name(kind: type) -> str:
    """`kind`'s name as `type` holds it, as exactly a `str`: neither a metaclass's own `__name__` nor a
    name of a type of its own runs."""
    return str.__str__(type.__dict__['__name__'].__get__(kind))


def _json_violation(value: object) -> str | None:
    """Why `value` is not JSON-like at every depth; None when it is.

    JSON-like is exactly None, a `bool`, an `int`, a `float` or a `str`, or exactly a `list` or a `dict`
    whose every key is exactly a `str`, of JSON-like values. A container met twice is refused, so a cycle
    ends.
    """
    seen: set[int] = set()
    stack = [value]
    while stack:
        node = stack.pop()
        kind = type(node)
        if node is None or kind is bool or kind is int or kind is float or kind is str:
            continue
        if kind is not list and kind is not dict:
            return f'holds a {_type_name(kind)}, not a JSON value'
        if id(node) in seen:
            return 'holds one container twice'
        seen.add(id(node))
        if kind is list:
            stack.extend(node)
            continue
        for label in node:
            if type(label) is not str:
                return f'holds a {_type_name(type(label))} key, not a str'
        stack.extend(node.values())
    return None


def _same(value: object, default: object) -> bool:
    """Whether `value` is, node for node, `default`, a default the installed FastMCP declares.

    Each pair of nodes is of one type (`is`) first. Then `bool`, `int`, `float`, `str` and `timedelta`
    compare by `==`; a `set` holds exact scalars and compares by `==`; a `list` element by element; a
    `dict` keyed exactly by `str`, the same keys in order, value by value; a dataclass or a pydantic model
    (of the default's own type, FastMCP's) by its instance state; and anything else by identity.
    """
    seen: set[int] = set()
    stack = [(value, default)]
    while stack:
        a, b = stack.pop()
        kind = type(a)
        if kind is not type(b):
            return False
        if a is b:
            continue
        if kind is bool or kind is int or kind is float or kind is str or kind is timedelta:
            if a != b:
                return False
            continue
        if id(a) in seen:
            return False
        seen.add(id(a))
        if kind is set:
            scalars = all(type(item) is str or type(item) is int or type(item) is bool or type(item) is float
                          or item is None for item in a)
            if not scalars or a != b:
                return False
            continue
        if kind is dict:
            for label in a:
                if type(label) is not str:
                    return False
            if list(a) != list(b):
                return False
            a, b = list(a.values()), list(b.values())
        elif kind is not list:
            # A dataclass's state is its instance dictionary; a pydantic model's that and its extra and private slots.
            if issubclass(kind, BaseModel):
                slots = ('__dict__', '__pydantic_extra__', '__pydantic_private__')
            elif hasattr(kind, '__dataclass_fields__'):
                slots = ('__dict__',)
            else:
                return False
            try:
                a, b = ([object.__getattribute__(a, slot) for slot in slots],
                        [object.__getattribute__(b, slot) for slot in slots])
            except AttributeError:
                return False
        if len(a) != len(b):
            return False
        stack.extend(zip(a, b))
    return True


def _default_violation(value: object, info: FieldInfo) -> str | None:
    """Why `value` is not, node for node (`_same`), the default `info` declares for its field; None when
    it is. A default made by a factory is made fresh; one made from the other fields' data never is."""
    if info.default_factory is None:
        default = info.default
    elif info.default_factory_takes_validated_data:
        return 'has a default made from the other fields, which the load does not make'
    else:
        default = info.default_factory()
    return None if _same(value, default) else 'is not its default'


# The metaclasses a tool's return type may have, and the aliases it may be: what `Tool.from_function`
# gives for a class, a dataclass, a pydantic model, an enum, a `TypedDict` or an `abc` generic, and for a
# generic, a union, `Annotated` or `Literal`.
_RETURN_CLASSES: Final = (type, type(BaseModel), enum.EnumType, abc.ABCMeta, typing._TypedDictMeta)
_RETURN_ALIASES: Final = (types.GenericAlias, typing.Union, typing._GenericAlias, typing._UnionGenericAlias,
                          typing._AnnotatedAlias, typing._LiteralGenericAlias)
# `Py_TPFLAGS_HEAPTYPE`: set on every class a class statement or `type()` makes, and on one a C extension makes
# with `PyType_FromSpec`; clear on a static type, such as `str` or `dict`.
_HEAP_TYPE: Final = 1 << 9


def _return_type_violation(value: object, info: FieldInfo) -> str | None:
    """Why `value`, a tool's return type, is not one the load accepts; None when it is.

    FastMCP reads it as it registers the tool (`isinstance`, its `__module__`, its origin and arguments).
    Accepted: None, no annotation, `typing.Any` and `...`; a class whose metaclass is exactly one of
    `_RETURN_CLASSES`, its namespace (read through `type`'s own descriptor) keyed exactly by `str` and
    holding its own `__module__`, exactly a `str` (a class without the heap-type flag, a static type such as
    `str`, has none there and passes: `type` reads its module from its name; a heap type with none of its
    own is refused, whatever made it, a C extension included); and exactly one of `_RETURN_ALIASES`, its state read
    through its instance dictionary when it has one, whose origin and arguments are accepted in turn, a
    `Literal`'s arguments exact scalars and an `Annotated`'s metadata exactly pydantic's `FieldInfo` or
    JSON-like. A class is not walked further: at a call, serializing the result through it is the call.
    """
    seen: set[int] = set()
    stack = [value]
    while stack:
        node = stack.pop()
        kind = type(node)
        if node is None or node is inspect.Signature.empty or node is typing.Any or node is Ellipsis:
            continue
        if any(kind is meta for meta in _RETURN_CLASSES):
            namespace = type.__dict__['__dict__'].__get__(node)
            for label in namespace:
                if type(label) is not str:
                    return f'holds a class with a {_type_name(type(label))} attribute name, not a str'
            if '__module__' in namespace:
                module = namespace['__module__']
                if type(module) is not str:
                    return f'holds a class whose __module__ is a {_type_name(type(module))}, not a str'
            elif type.__dict__['__flags__'].__get__(node) & _HEAP_TYPE:
                return 'holds a class with no __module__ of its own'
            continue
        if not any(kind is alias for alias in _RETURN_ALIASES):
            return f'holds a {_type_name(kind)}, not a class or an alias it accepts'
        if id(node) in seen:
            continue
        seen.add(id(node))
        if kind is types.GenericAlias or kind is typing.Union:
            state = {'__origin__': node.__origin__} if kind is types.GenericAlias else {}
            state['__args__'] = node.__args__
        else:
            state = object.__getattribute__(node, '__dict__')
            if type(state) is not dict:
                return f'holds a {_type_name(kind)} whose state is a {_type_name(type(state))}, not a dict'
            for label in state:
                if type(label) is not str:
                    return f'holds a {_type_name(kind)} with a {_type_name(type(label))} attribute name, not a str'
        args = state.get('__args__', ())
        module = state.get('__module__', '')
        metadata = state.get('__metadata__', ())
        if type(args) is not tuple or type(module) is not str or type(metadata) is not tuple:
            return f'holds a {_type_name(kind)} whose arguments, module or metadata are not exactly built-in types'
        for item in metadata:
            if type(item) is not FieldInfo and _json_violation(item):
                return f'holds a {_type_name(kind)} whose metadata holds a {_type_name(type(item))}'
        if kind is typing._LiteralGenericAlias:
            for item in args:
                if not (item is None or type(item) is bool or type(item) is int or type(item) is float
                        or type(item) is str):
                    return f'holds a Literal of a {_type_name(type(item))}, not an exact scalar'
            continue
        if '__origin__' in state:
            stack.append(state['__origin__'])
        stack.extend(args)
    return None


def _a_str(value: object, info: FieldInfo) -> str | None:
    return None if type(value) is str else f'is a {_type_name(type(value))}, not a str'


def _a_str_or_none(value: object, info: FieldInfo) -> str | None:
    return None if value is None else _a_str(value, info)


def _a_schema(value: object, info: FieldInfo) -> str | None:
    """Why `value` is not exactly a `dict`, JSON-like at every depth; None when it is."""
    if type(value) is not dict:
        return f'is a {_type_name(type(value))}, not a dict'
    return _json_violation(value)


def _a_schema_or_none(value: object, info: FieldInfo) -> str | None:
    return None if value is None else _a_schema(value, info)


def _a_function(value: object, info: FieldInfo) -> str | None:
    """Why `value`, a tool's handler, is not exactly a function whose `__module__` is exactly a `str`; None
    when it is. What it does when a request calls it is the capability's code, by design; its type and
    module are decided, so the load's reading of its module (the tool's attribution) runs none."""
    if type(value) is not types.FunctionType:
        return f'is a {_type_name(type(value))}, not a function'
    if type(value.__module__) is not str:
        return f'has a __module__ that is a {_type_name(type(value.__module__))}, not a str'
    return None


def _unnamed(value: object, info: FieldInfo) -> str | None:
    """The rule for a field of the installed FastMCP's model that no rule names: a value JSON-like at
    every depth, or the field's own declared default, is accepted (None); any other is undecided."""
    if _json_violation(value) is None or _default_violation(value, info) is None:
        return None
    return 'is neither JSON-like nor its default'


# The fields no rule names that a tool has held undecided, warned of once in a process.
_warned: set[str] = set()


def _undecided(field: str) -> None:
    """Warn on stderr that a tool's `field`, which no rule names, is served undecided: once per process for
    each field."""
    if field in _warned:
        return
    _warned.add(field)
    log.warning(f'FunctionTool field {field!r} of FastMCP {fastmcp.__version__} has no rule in this '
                f'server: a tool holding neither a JSON-like value nor its default there is served undecided')


# Each `FunctionTool` field's rule: (its value, its `FieldInfo`) -> why the value is refused, or None. The
# fields `@mcp_tool` fills from the function are decided by type; every other field holds its declared
# default, node for node, which is what `Tool.from_function` gives it through `@mcp_tool`.
TOOL_RULES: Final = {
    'name': _a_str,
    'description': _a_str_or_none,
    'parameters': _a_schema,
    'output_schema': _a_schema_or_none,
    'return_type': _return_type_violation,
    'fn': _a_function,
    **{field: _default_violation for field in ('version', 'title', 'icons', 'tags', 'meta', 'task_config',
                                               'annotations', 'execution', 'auth', 'timeout', 'run_in_thread')},
}


def _tool_violation(entry: object) -> str | None:
    """Why `entry`, a registry entry, is not an inert tool; None when it is.

    It is exactly a `FunctionTool` (a subclass's code would run on any read of it). Its instance state is
    what pydantic gives one: a `dict` keyed exactly by `str`, holding every field of the installed model,
    and JSON-like beside them; a fields set exactly a `set` of field names; no extra or private state, or
    what the installed model declares. Then each field of the installed FastMCP's model, read at run time,
    holds what its rule (`TOOL_RULES`) accepts; a field no rule names is decided by `_unnamed`, and a value
    that does not pass it is served undecided, with a warning (`_undecided`), never refused.
    """
    kind = type(entry)
    if kind is not FunctionTool:
        return f'a {_type_name(kind)}, not a FunctionTool'
    held = []
    for slot in ('__dict__', '__pydantic_fields_set__', '__pydantic_extra__', '__pydantic_private__'):
        try:
            held.append(object.__getattribute__(entry, slot))
        except AttributeError:
            return f'a tool with no {slot}'
    state, fields_set, extra, private = held
    model = FunctionTool.model_fields
    if type(state) is not dict:
        return f'a tool whose __dict__ is a {_type_name(type(state))}, not a dict'
    for label in state:
        if type(label) is not str:
            return f'a tool whose __dict__ has a {_type_name(type(label))} key, not a str'
    for label, value in state.items():
        if label not in model and (why := _json_violation(value)):
            return f'a tool whose {label!r}, which is not a field, {why}'
    if type(fields_set) is not set:
        return f'a tool whose __pydantic_fields_set__ is a {_type_name(type(fields_set))}, not a set'
    for label in fields_set:
        if type(label) is not str:
            return f'a tool whose __pydantic_fields_set__ holds a {_type_name(type(label))}, not a str'
        if label not in model:
            return f'a tool whose __pydantic_fields_set__ names {label!r}, which is not a field'
    allowed = FunctionTool.model_config.get('extra') == 'allow'
    if extra is not None and (not allowed or type(extra) is not dict or _json_violation(extra)):
        return f'a tool whose __pydantic_extra__ is a {_type_name(type(extra))}, not None'
    privates = FunctionTool.__private_attributes__
    if private is not None:
        if not privates or type(private) is not dict:
            return f'a tool whose __pydantic_private__ is a {_type_name(type(private))}, not None'
        for label in private:
            if type(label) is not str:
                return f'a tool whose __pydantic_private__ has a {_type_name(type(label))} key, not a str'
        if private.keys() != privates.keys():
            return 'a tool whose __pydantic_private__ does not hold exactly its private attributes'
        for label, value in private.items():
            if _json_violation(value) and not _same(value, privates[label].get_default()):
                return f'a tool whose private {label!r} is neither JSON-like nor its default'
    for field, info in model.items():
        if field not in state:
            return f'a tool with no {field}'
        rule = TOOL_RULES.get(field)
        if rule is None:
            if _unnamed(state[field], info):
                _undecided(field)
            continue
        if why := rule(state[field], info):
            return f'a tool whose {field} {why}'
    return None


def _registry_violation(before: int) -> str | None:
    """Why the tool registry is not every entry an inert tool (`_tool_violation`), worded for the
    capability whose load began when it held `before` entries; None when it is.

    Every entry is decided, the core's and those registered before this load began included: the load
    reads each as it attributes the tools, and a capability's code can change one registered earlier.
    """
    for i, entry in enumerate(TOOL_REGISTRY):
        if why := _tool_violation(entry):
            return f'loading it registered {why}' if i >= before else f'the registry holds {why}'
    return None


def _listing_violation(text: str, names: list[str]) -> str | None:
    """Why `text` does not list exactly `names`, each once, as `- name:` lines; None when it does."""
    listed = LISTED.findall(text)
    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):
        return None
    extra = sorted(set(listed) - set(names))
    missing = sorted(set(names) - set(listed))
    twice = sorted({n for n in listed if listed.count(n) > 1})
    parts = ([f'list {extra}, which it does not register'] if extra else []) \
        + ([f'omit {missing}, which it registers'] if missing else []) \
        + ([f'list {twice} more than once'] if twice else [])
    return 'its instructions ' + ', and '.join(parts)


def serve(server: FastMCP, tools: Iterable[Tool], resources: Iterable[dict]) -> None:
    """Register `tools`, then the resource entries `resources`, on `server`.

    The one way a server takes the core's and each capability's tools and resources. `load()` assembles
    every capability through it before any server is built, so what FastMCP refuses here is refused at
    load, naming the capability.
    """
    for tool in tools:
        server.add_tool(tool)
    for entry in resources:
        server.resource(entry['uri'], name=entry['name'], description=entry['description'])(entry['handler'])


def _scratch() -> FastMCP:
    """A server holding the core's tools and resources, on which `load()` assembles each capability.

    It refuses a component under a key it already holds, where a served server would let the later
    replace the earlier with a warning. FastMCP keys a resource by its URI read as a URL, so
    `cluster://a b` and `cluster://a%20b` are one key, and so are two URIs that differ only in the
    case of their scheme or in surrounding space.
    """
    server = FastMCP(name='cluster-mcp', on_duplicate='error')
    serve(server, CORE_TOOLS, RESOURCE_REGISTRY)
    return server


# The refusal of this process's first failed load, as its distribution and its message: every later
# load is refused with it (`load()`).
_failed: tuple[str, str] | None = None

# What the refusal of a load after a failed one adds to the failed load's message.
_RESTART: Final = 'refused by an earlier load in this process; restart the process to load capabilities again'


def _failure(refusal: CapabilityLoadError) -> tuple[str, str]:
    """The distribution and the message `refusal`, a failed load's, names, read with no capability code run.

    Each is read through `vars()` and the exception's own `args`, and only when `refusal` is exactly a
    `CapabilityLoadError` holding exactly a `str` of each, as every refusal the load makes does. Any
    other is a capability's own, one its code raised and the load raised as it is; its code is not run
    again to read it, so it is named by the group.
    """
    if type(refusal) is CapabilityLoadError:
        distribution, args = vars(refusal).get('distribution'), refusal.args
        if type(distribution) is str and len(args) == 1 and type(args[0]) is str:
            return distribution, args[0]
    return GROUP, f'cannot load capability {GROUP}: a capability raised a CapabilityLoadError of its own'


def load(eps: Iterable[EntryPoint] | None = None) -> tuple[Loaded, ...]:
    """Load the capabilities `eps` name (default: every entry point in `GROUP`), uncached, but only while
    no load in this process has failed.

    A failed load cuts the registry back, but what it imported stays imported, and a later load would
    find it so and run none of it again: a capability that loaded cleanly would register nothing and
    be refused for it. So once a load has failed, every later load in the process, whatever it is
    given, raises `CapabilityLoadError` before it reads or imports anything, naming the distribution
    the first failure named, its message the first failure's followed by the instruction to restart
    the process (`_RESTART`). A `KeyboardInterrupt` is not a failure, and leaves no refusal.
    """
    global _failed
    if _failed is not None:
        distribution, message = _failed
        refusal = CapabilityLoadError(distribution, '')
        refusal.args = (f'{message} ({_RESTART})',)
        raise refusal
    try:
        return _load(eps)
    except CapabilityLoadError as refusal:
        _failed = _failure(refusal)
        raise


def _load(eps: Iterable[EntryPoint] | None) -> tuple[Loaded, ...]:
    """Load the capabilities `eps` name (default: every entry point in `GROUP`).

    They load in order of (distribution, entry-point name), so which failure is reported never
    depends on `sys.path` or directory order; a distribution is named by its entry point's value when
    its metadata names none (`_identity`). A capability fails to load when its distribution's metadata
    cannot be read or has no `Name`; when its entry point or its tools module raises anything or
    exits; when it is not a well-formed `Capability` (a resource of it included); when anything the
    registry holds, decided after its tools module is imported and again after its resources are
    assembled, is not an inert tool (`_tool_violation`), or anything registered since its load began
    (its entry point's import included, whatever imported its tools module and when) lies outside its
    tools module; when one of its tools,
    its name or one of its resource URIs is already taken (by the core or by a capability loaded
    before it); when its instructions do not list exactly its tools; or when one of its tools or
    resources cannot be served: assembled through `serve()` on a scratch server that holds the core's
    and every earlier capability's, FastMCP refuses it or keys it as one it already holds. Anything
    else raised or exited with while loading a capability fails it too, but a `KeyboardInterrupt`,
    which is raised as it is. The first failure raises `CapabilityLoadError`, after `TOOL_REGISTRY` is
    cut back to what it held before this load began, what building the refusal registered included; so
    does a distribution whose entry points cannot be read while they are discovered.
    """
    found = _discovered() if eps is None else tuple(eps)
    entries = [_Entry(*_identity(ep), ep) for ep in found]
    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))
    start = len(TOOL_REGISTRY)
    core = {tool.name for tool in CORE_TOOLS}
    core_uris = {entry['uri'] for entry in RESOURCE_REGISTRY}
    owners: dict[str, str] = {}
    uri_owners: dict[str, str] = {}
    names: dict[str, str] = {}
    loaded: list[Loaded] = []
    scratch = _scratch()
    try:
        for distribution, nameless, ep in ordered:
            if nameless:
                raise CapabilityLoadError(distribution, nameless)
            before = len(TOOL_REGISTRY)
            try:
                capability = _checked(ep.load())
            except _Invalid as exc:
                raise CapabilityLoadError(distribution, str(exc)) from exc
            import_module(capability.tools)
            # Every registry entry is decided inert before the load first reads one (its `fn`, its `name`).
            if held := _registry_violation(before):
                raise CapabilityLoadError(distribution, held)
            stray = [tool.name for tool in TOOL_REGISTRY[before:]
                     if not _below(tool.fn.__module__, capability.tools)]
            if stray:
                raise CapabilityLoadError(distribution, f'loading it registered {stray}, which are outside '
                                                        f'{capability.tools}')
            if capability.name in names:
                raise CapabilityLoadError(distribution, f'the capability name {capability.name!r} is already '
                                                        f'taken by {names[capability.name]}')
            tools = tuple(tool for tool in TOOL_REGISTRY if _below(tool.fn.__module__, capability.tools))
            for i, tool in enumerate(tools):
                if any(other.name == tool.name for other in tools[:i]):
                    raise CapabilityLoadError(distribution, f'tool {tool.name!r} is registered twice by '
                                                            f'{capability.tools}')
                if tool.name in core:
                    raise CapabilityLoadError(distribution, f'tool {tool.name!r} is already registered by the core')
                if tool.name in owners:
                    raise CapabilityLoadError(distribution, f'tool {tool.name!r} is already registered by '
                                                            f'{owners[tool.name]}')
            uris = [entry['uri'] for entry in capability.resources]
            for i, uri in enumerate(uris):
                if uri in uris[:i]:
                    raise CapabilityLoadError(distribution, f'resource {uri!r} is declared twice')
                if uri in core_uris:
                    raise CapabilityLoadError(distribution, f'resource {uri!r} is already registered by the core')
                if uri in uri_owners:
                    raise CapabilityLoadError(distribution, f'resource {uri!r} is already registered by '
                                                            f'{uri_owners[uri]}')
            why = _listing_violation(capability.instructions, [tool.name for tool in tools])
            if why:
                raise CapabilityLoadError(distribution, why)
            for tool in tools:
                try:
                    serve(scratch, (tool,), ())
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:
                    raise CapabilityLoadError(distribution, f'its tool {tool.name!r} cannot be served: '
                                                            f'{_cause(exc)}') from exc
            for entry in capability.resources:
                try:
                    serve(scratch, (), (entry,))
                except KeyboardInterrupt:
                    raise
                except BaseException as exc:
                    raise CapabilityLoadError(distribution, f'its resource {entry["uri"]!r} cannot be served: '
                                                            f'{_cause(exc)}') from exc
            # And again: FastMCP read each resource handler, the capability's code, which can change a tool.
            if held := _registry_violation(before):
                raise CapabilityLoadError(distribution, held)
            names[capability.name] = distribution
            owners.update((tool.name, distribution) for tool in tools)
            uri_owners.update((uri, distribution) for uri in uris)
            loaded.append(Loaded(capability, distribution, tools))
    except BaseException as exc:
        # The refusal is built first: its text is a capability's code, and whatever that registers is
        # cut with the rest.
        try:
            if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):
                raise
            raise CapabilityLoadError(distribution, _cause(exc)) from exc
        finally:
            del TOOL_REGISTRY[start:]
    return tuple(loaded)


# What `installed()` loaded, once it has loaded without error.
_installed: tuple[Loaded, ...] | None = None


def installed() -> tuple[Loaded, ...]:
    """Every capability this environment has, loaded on the first call and cached once it succeeds.

    The CLI, `create_mcp_server` and the tests share the one load, so no tool registers twice. A
    failed load is not cached: the next call loads again, and that load is refused (`load()`).
    """
    global _installed
    if _installed is None:
        _installed = load()
    return _installed


def composed(capabilities: Iterable[Loaded]) -> tuple[Loaded, ...]:
    """`capabilities` in composition order, (order, distribution): the order of their texts in the base."""
    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))
