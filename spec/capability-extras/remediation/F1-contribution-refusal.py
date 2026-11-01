# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 1, F1: whatever a capability declares fails at the load or not at all.

    uv run python -I spec/capability-extras/remediation/F1-contribution-refusal.py      from the worktree root

The property, evaluated rather than grepped: for every capability in a generated domain of
contributions, beside each member set (core only, each member, both), `load()` either refuses it with
one `CapabilityLoadError` line naming its distribution, or a server built from what loaded
(`create_mcp_server(..., capabilities=...)`) builds without error and serves every declared resource
under its own key and every declared tool. Any other exception from the load, any server build that
raises, and any declared resource that a server keys alike with another (so one replaces the other)
is a violation.

The domain crosses resource URIs (plain, aliased, not a URL, empty, templated, percent-encoded twins,
differing from a served URI only in case or surrounding space, other schemes) with handlers (no
parameter, one parameter named as a template's or not, a method's `self`, a builtin, a coroutine, a
lambda, a partial, a callable without a `__dict__`, a class, a bound method), one entry and every
ordered pair within one capability, the pair split across two capabilities, and tools modules that
register something other than a tool or a tool with no module. Each verdict is in process: the
capabilities are hand-built entry points over modules placed in `sys.modules`, never files.

It is not vacuous: it fails unless the domain holds at least one accepted and one refused case of
each FastMCP refusal it names (`REQUIRED`). Footprint: one process, no network, under 300 MB, about
20 s.
"""

from __future__ import annotations

import asyncio
import functools
import importlib.abc
import importlib.util
import itertools
import sys
from dataclasses import dataclass

from cluster_mcp.core.capabilities import GROUP, Capability, CapabilityLoadError, installed, load
from cluster_mcp.core.server import create_mcp_server
from cluster_mcp.core.site import SiteContext
from cluster_mcp.core.tools import TOOL_REGISTRY, mcp_tool
from importlib.metadata import entry_points

# What each FastMCP refusal (or keying) looks like in a load's message; each must occur at least once.
REQUIRED = {
    'not a URL': 'ValidationError',
    'a parameter on a static URI': 'URI template must contain at least one parameter',
    'a template the handler does not match': 'must be a subset of the',
    'a method': "as its first parameter",
    'no metadata': "no attribute '__fastmcp__'",
    'keyed alike': 'Component already exists',
    'not a tool': 'not a FunctionTool',
}

URIS = ['cluster://probe', 'rcac://probe', 'probe storage', '', 'cluster:', 'cluster://probe/a b',
        'cluster://probe/a%20b', 'CLUSTER://context', ' cluster://context', 'cluster://context ',
        'Cluster://storage', 'cluster://probe/{name}', 'cluster://probe/{path}', 'probe://x',
        'cluster://probe#part', 'cluster://probe?q', 'cluster://probe/é', 'cluster://context',
        'rcac://storage']


def _none() -> str:
    return 'probe'


def _path(path: str) -> str:
    return path


def _name(name: str) -> str:
    return name


def _self(self) -> str:
    return 'probe'


async def _coro() -> str:
    return 'probe'


class _Slotted:
    __slots__ = ()

    def __call__(self) -> str:
        return 'probe'


class _Holder:
    def read(self) -> str:
        return 'probe'


HANDLERS = {'none': _none, 'path': _path, 'name': _name, 'self': _self, 'builtin': print, 'coroutine': _coro,
            'lambda': lambda: 'probe', 'partial': functools.partial(_path, 'x'), 'slotted': _Slotted(),
            'class': _Holder, 'bound': _Holder().read}


@dataclass
class Dist:
    name: str


@dataclass
class Probe:
    """A hand-built entry point: what `load()` reads of one (`name`, `value`, `dist`, `load()`)."""

    name: str
    value: str
    dist: Dist
    capability: object

    def load(self) -> object:
        return self.capability


_made = itertools.count()

# What importing each probe module runs, by its dotted name: a tools module registers its tool when
# the load imports it, as a real one does.
_PENDING: dict[str, object] = {}


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Imports the probe packages and their tools modules from `_PENDING`, never from files."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname in _PENDING:
            return importlib.util.spec_from_loader(fullname, self, is_package='.' not in fullname)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        run = _PENDING[module.__name__]
        if run is not None:
            run()


sys.meta_path.insert(0, _Finder())


def tools_module(kind: str = 'echo') -> tuple[str, str]:
    """A fresh tools module, importable, whose import registers one tool (and `kind`'s odd
    registration); its dotted name and the tool's name."""
    n = next(_made)
    module = f'f1probe{n}.tools'
    tool = f'probe_echo_{n}'

    def register() -> None:
        def echo(text: str) -> str:
            """Echo a text back.

            Args:
                text: The text.
            """
            return text

        echo.__name__ = echo.__qualname__ = tool
        echo.__module__ = module
        registered = mcp_tool(echo)
        if kind == 'not-a-tool':
            TOOL_REGISTRY.append(_none)
        elif kind == 'no-module':
            registered.fn.__module__ = None

    _PENDING[f'f1probe{n}'] = None
    _PENDING[module] = register
    return module, tool


def probe(resources: tuple[dict, ...], kind: str = 'echo') -> Probe:
    module, tool = tools_module(kind)
    n = module.split('.')[0].removeprefix('f1probe')
    capability = Capability(name=f'probe{n}', order=500, tools=module,
                            instructions=f'Probe tools:\n- {tool}: Echo a text back', resources=resources)
    return Probe(name=f'probe{n}', value=f'{module}:CAPABILITY', dist=Dist(f'probe-{n}'), capability=capability)


def entry(uri: str, handler: str) -> dict:
    return {'uri': uri, 'name': 'probe', 'description': 'Probe', 'handler': HANDLERS[handler], 'executor': True}


def cases() -> list[tuple[str, list]]:
    """Every case: a label and the capabilities, as functions making their probes, in load order."""
    out: list[tuple[str, list]] = []
    for uri, handler in itertools.product(URIS, HANDLERS):
        out.append((f'{uri!r} with {handler}', [lambda u=uri, h=handler: probe((entry(u, h),))]))
    for a, b in itertools.permutations(URIS[:11], 2):
        out.append((f'{a!r} and {b!r} in one', [lambda a=a, b=b: probe((entry(a, 'none'), entry(b, 'none')))]))
        out.append((f'{a!r} then {b!r} apart', [lambda a=a: probe((entry(a, 'none'),)),
                                                 lambda b=b: probe((entry(b, 'none'),))]))
    for kind in ('not-a-tool', 'no-module'):
        out.append((f'a tools module with {kind}', [lambda k=kind: probe((), k)]))
    return out


MEMBERS = {ep.name: ep for ep in entry_points(group=GROUP)}
SETS = {'core only': (), 'slurm': ('slurm',), 'rcac': ('rcac',), 'both': ('rcac', 'slurm')}
SITE = SiteContext.found([], 'this host')


def served_resources(server) -> list[str]:
    async def listing() -> list[str]:
        resources = [str(r.uri) for r in await server.list_resources()]
        templates = [t.uri_template for t in await server.list_resource_templates()]
        return resources + templates
    return asyncio.run(listing())


def main() -> int:
    bad: list[str] = []
    accepted = refused = 0
    # Every member's tools are registered once, as the suite's conftest does; each case is loaded
    # again from there (an imported member registers nothing a second time).
    installed()
    seen = {label: 0 for label in REQUIRED}
    for set_name, names in SETS.items():
        for label, makers in cases():
            before = list(TOOL_REGISTRY)
            probes = [make() for make in makers]
            try:
                loaded = load([*(MEMBERS[n] for n in names), *probes])
            except CapabilityLoadError as exc:
                refused += 1
                message = str(exc)
                if '\n' in message or not any(message.startswith(f'cannot load capability {p.dist.name}: ')
                                              for p in probes):
                    bad.append(f'{set_name}, {label}: the refusal does not name a probe in one line: {message!r}')
                for what, fragment in REQUIRED.items():
                    seen[what] += fragment in message
                if TOOL_REGISTRY != before:
                    bad.append(f'{set_name}, {label}: a refused load left the registry changed')
                continue
            except Exception as exc:
                bad.append(f'{set_name}, {label}: the load raised {type(exc).__name__}, not a refusal: {exc}')
                continue
            finally:
                TOOL_REGISTRY[:] = before
            accepted += 1
            try:
                server = create_mcp_server('none', site=SITE, capabilities=loaded)
                served = served_resources(server)
            except Exception as exc:
                bad.append(f'{set_name}, {label}: loaded, then the server failed to build: {type(exc).__name__}: {exc}')
                continue
            declared = [e['uri'] for p in probes for e in p.capability.resources]
            want = len(declared) + len([u for l in loaded if l.distribution.startswith('cluster-mcp-')
                                        for u in (e['uri'] for e in l.capability.resources)]) + 2
            if len(served) != want:
                bad.append(f'{set_name}, {label}: loaded, then served {len(served)} resources for {want} declared: '
                           f'one replaced another: {served}')
    for what, count in seen.items():
        if not count:
            bad.append(f'no case was refused for {what} (expected {REQUIRED[what]!r} in some refusal)')
    if not accepted or not refused:
        bad.append(f'the domain is one-sided: {accepted} accepted, {refused} refused')
    print(*bad[:40], sep='\n', file=sys.stderr)
    if len(bad) > 40:
        print(f'… and {len(bad) - 40} more', file=sys.stderr)
    if not bad:
        print(f'F1: ok ({accepted} accepted and served whole, {refused} refused naming the capability, '
              f'over {len(SETS)} member sets)', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
