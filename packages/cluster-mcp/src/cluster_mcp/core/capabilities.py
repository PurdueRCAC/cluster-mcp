# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The capability contract: what an installed distribution adds to the server, and how it is loaded.

A capability is a distribution that declares one entry point in the group `cluster_mcp.capabilities`,
naming a `Capability`: its name, its place in the served instructions, the module whose `@mcp_tool`
functions are its tools, its part of the instructions, and its resources. The core never names one.
A capability's resources are never open: each needs its request's executor, so in `delegate` mode
every read of one resolves the caller.

Nothing here runs at import. `installed()` loads every capability the environment has, once, when
the server starts; a capability that cannot be discovered, ordered or loaded stops the load with a
`CapabilityLoadError` naming its distribution, whatever its code raised or exited with (but a
`KeyboardInterrupt`, which still interrupts), and leaves the tool registry as it was before the load
began. The load assembles each capability's tools and resources on a scratch server through
`serve()`, the one way every server takes them, so whatever a capability declares fails at the load
or not at all.
"""

# Type annotations
from __future__ import annotations
from typing import Final, Iterable, NamedTuple

# Standard libs
import re
import warnings
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import Distribution, EntryPoint, distributions, entry_points

# External libs
from fastmcp import FastMCP
from fastmcp.tools import Tool
from fastmcp.tools.function_tool import FunctionTool

# Internal libs
from cluster_mcp.core.resources import RESOURCE_REGISTRY
from cluster_mcp.core.tools import CORE_TOOLS, TOOL_REGISTRY

# Public interface
__all__ = ['GROUP', 'Capability', 'Loaded', 'CapabilityLoadError', 'serve', 'load', 'installed', 'composed']


# The entry-point group every capability distribution declares itself in.
GROUP: Final = 'cluster_mcp.capabilities'

# A tool's line in an instructions text: `- name: what it does`.
LISTED: Final = re.compile(r'^- (\w+):', re.MULTILINE)


@dataclass(frozen=True)
class Capability:
    """What a capability distribution adds to the server, as its entry point names it.

    `name` is unique among the loaded capabilities. `order` places its text in the served base,
    lower first: a site overlay takes a high one, so it sits last, directly above the site context.
    `tools` is the dotted name of the module whose `@mcp_tool` functions (that module's or any module
    below it) are its tools. `instructions` is its part of the base and lists exactly those tools, each
    once, as `- name:` lines. `resources` are entries shaped as the core's `RESOURCE_REGISTRY` ones,
    each a dict with a `str` `uri`, `name` and `description`, a callable `handler`, and `executor`
    exactly True, its URI served by nothing else.
    """

    name: str
    order: int
    tools: str
    instructions: str
    resources: tuple[dict, ...] = ()


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
    names no distribution, and that one cannot be loaded.
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
    if not isinstance(name, str) or not name.strip():
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
    if not isinstance(value, Capability):
        raise _Invalid(f'the entry point names a {type(value).__name__}, not a Capability')
    for field, kind in (('name', str), ('tools', str), ('instructions', str), ('resources', tuple)):
        if not isinstance(getattr(value, field), kind):
            raise _Invalid(f'its {field} is a {type(getattr(value, field)).__name__}, not a {kind.__name__}')
    if not isinstance(value.order, int) or isinstance(value.order, bool):
        raise _Invalid(f'its order is a {type(value.order).__name__}, not an int')
    if not value.name:
        raise _Invalid('its name is empty')
    if not value.instructions.strip():
        raise _Invalid('its instructions are empty')
    for entry in value.resources:
        _check_resource(entry)
    return value


def _check_resource(entry: object) -> None:
    """Raise `_Invalid` saying why `entry` is not a well-formed capability resource."""
    if not isinstance(entry, dict):
        raise _Invalid(f'one of its resources is a {type(entry).__name__}, not a dict')
    for key in ('uri', 'name', 'description'):
        if not isinstance(entry.get(key), str):
            raise _Invalid(f'its resource {entry.get("uri")!r} has a {type(entry.get(key)).__name__} {key}, not a str')
    if not callable(entry.get('handler')):
        raise _Invalid(f'the handler of its resource {entry["uri"]!r} is not callable')
    if entry.get('executor') is not True:
        raise _Invalid(f'its resource {entry["uri"]!r} has executor {entry.get("executor")!r}, not True: '
                       f'a capability resource is never open')


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


def load(eps: Iterable[EntryPoint] | None = None) -> tuple[Loaded, ...]:
    """Load the capabilities `eps` name (default: every entry point in `GROUP`), uncached.

    They load in order of (distribution, entry-point name), so which failure is reported never
    depends on `sys.path` or directory order; a distribution is named by its entry point's value when
    its metadata names none (`_identity`). A capability fails to load when its distribution's metadata
    cannot be read or has no `Name`; when its entry point or its tools module raises anything or
    exits; when it is not a well-formed `Capability` (a resource of it included); when anything
    registered since its load began (its entry point's import included, whatever imported its tools
    module and when) is not a `FunctionTool` or lies outside its tools module; when one of its tools,
    its name or one of its resource URIs is already taken (by the core or by a capability loaded
    before it); when its instructions do not list exactly its tools; or when one of its tools or
    resources cannot be served: assembled through `serve()` on a scratch server that holds the core's
    and every earlier capability's, FastMCP refuses it or keys it as one it already holds. Anything
    else raised or exited with while loading a capability fails it too, but a `KeyboardInterrupt`,
    which is raised as it is. The first failure raises `CapabilityLoadError`, after `TOOL_REGISTRY` is
    cut back to what it held before this load began; so does a distribution whose entry points cannot
    be read while they are discovered.
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
            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if not isinstance(entry, FunctionTool)]
            if odd:
                raise CapabilityLoadError(distribution, f'loading it registered a {odd[0]}, not a FunctionTool')
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
            names[capability.name] = distribution
            owners.update((tool.name, distribution) for tool in tools)
            uri_owners.update((uri, distribution) for uri in uris)
            loaded.append(Loaded(capability, distribution, tools))
    except BaseException as exc:
        del TOOL_REGISTRY[start:]
        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):
            raise
        raise CapabilityLoadError(distribution, _cause(exc)) from exc
    return tuple(loaded)


# What `installed()` loaded, once it has loaded without error.
_installed: tuple[Loaded, ...] | None = None


def installed() -> tuple[Loaded, ...]:
    """Every capability this environment has, loaded on the first call and cached once it succeeds.

    The CLI, `create_mcp_server` and the tests share the one load, so no tool registers twice. A
    failed load is not cached: it raises again on the next call.
    """
    global _installed
    if _installed is None:
        _installed = load()
    return _installed


def composed(capabilities: Iterable[Loaded]) -> tuple[Loaded, ...]:
    """`capabilities` in composition order, (order, distribution): the order of their texts in the base."""
    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))
