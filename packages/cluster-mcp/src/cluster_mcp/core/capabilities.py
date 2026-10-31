# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The capability contract: what an installed distribution adds to the server, and how it is loaded.

A capability is a distribution that declares one entry point in the group `cluster_mcp.capabilities`,
naming a `Capability`: its name, its place in the served instructions, the module whose `@mcp_tool`
functions are its tools, its part of the instructions, and its resources. The core never names one.

Nothing here runs at import. `installed()` loads every capability the environment has, once, when
the server starts; a capability that cannot be loaded stops the load with a `CapabilityLoadError`
naming its distribution, and leaves the tool registry as it was before the load began.
"""

# Type annotations
from __future__ import annotations
from typing import Final, Iterable

# Standard libs
import re
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points

# External libs
from fastmcp.tools import Tool

# Internal libs
from cluster_mcp.core.tools import CORE_TOOLS, TOOL_REGISTRY

# Public interface
__all__ = ['GROUP', 'Capability', 'Loaded', 'CapabilityLoadError', 'load', 'installed', 'composed']


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
    once, as `- name:` lines. `resources` are entries shaped as the core's `RESOURCE_REGISTRY` ones.
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


def _distribution(ep: EntryPoint) -> str:
    """The distribution that declared `ep`, or the entry point's value when it came from none."""
    return ep.dist.name if ep.dist is not None else ep.value


def _cause(exc: BaseException) -> str:
    """`<ExcType>: <text>`, or the type alone when the text is empty."""
    text = str(exc)
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
    return value


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


def load(eps: Iterable[EntryPoint] | None = None) -> tuple[Loaded, ...]:
    """Load the capabilities `eps` name (default: every entry point in `GROUP`), uncached.

    They load in order of (distribution, entry-point name), so which failure is reported never
    depends on `sys.path` or directory order. A capability fails to load when its entry point or its
    tools module raises, when it is not a well-formed `Capability`, when its tools module registers a
    tool outside itself, when one of its tools or its name is already taken (by the core or by a
    capability loaded before it), or when its instructions do not list exactly its tools. The first
    failure raises `CapabilityLoadError`, after `TOOL_REGISTRY` is cut back to what it held before
    this load began.
    """
    found = entry_points(group=GROUP) if eps is None else eps
    ordered = sorted(found, key=lambda ep: (_distribution(ep), ep.name))
    start = len(TOOL_REGISTRY)
    core = {tool.name for tool in CORE_TOOLS}
    owners: dict[str, str] = {}
    names: dict[str, str] = {}
    loaded: list[Loaded] = []
    try:
        for ep in ordered:
            distribution = _distribution(ep)
            try:
                capability = _checked(ep.load())
            except _Invalid as exc:
                raise CapabilityLoadError(distribution, str(exc)) from exc
            except Exception as exc:
                raise CapabilityLoadError(distribution, _cause(exc)) from exc
            before = len(TOOL_REGISTRY)
            try:
                import_module(capability.tools)
            except Exception as exc:
                raise CapabilityLoadError(distribution, _cause(exc)) from exc
            stray = [tool.name for tool in TOOL_REGISTRY[before:]
                     if not _below(tool.fn.__module__, capability.tools)]
            if stray:
                raise CapabilityLoadError(distribution, f'importing {capability.tools} registered {stray}, '
                                                        f'which are outside it')
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
            why = _listing_violation(capability.instructions, [tool.name for tool in tools])
            if why:
                raise CapabilityLoadError(distribution, why)
            names[capability.name] = distribution
            owners.update((tool.name, distribution) for tool in tools)
            loaded.append(Loaded(capability, distribution, tools))
    except CapabilityLoadError:
        del TOOL_REGISTRY[start:]
        raise
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
