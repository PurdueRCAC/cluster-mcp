# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The served surface is composed from the capabilities given, and the instructions name exactly the
tools served, under every capability set.

    uv run python spec/capability-extras/verify/compose.py p1|p2      from the worktree root

Independent of the suite. In this (full) environment, `installed()` must find exactly the Slurm and
RCAC capabilities, from `cluster-mcp-slurm` and `cluster-mcp-rcac`. Then, for every subset of them
(none, Slurm, RCAC, both), and for both given in reverse and in either order, a server is built in
this process with `create_mcp_server(..., capabilities=<subset>)` and listed by an in-memory client:
- the tools served are exactly the core's seven and each given capability's own (pinned here from
  GOAL.md, not read from the tree), each once;
- the instructions begin with the base: the core's text, then each given capability's text in
  composition order (Slurm before RCAC whatever order they were given in), joined by a blank line,
  then the site section;
- the base lists, as `- name:` lines, exactly the tools served, each once (the cross-check);
- the same subset given in another order serves identical instructions and the same tool list;
- from p2: the resources served are the core's two context URIs, plus `cluster://storage` and its
  `rcac://storage` alias exactly when the RCAC capability is given, the alias a copy of its target
  but for the URI; and the core's open set is exactly the two context URIs.
Footprint: one process, no network, under 300 MB; under 10 s.
"""

from __future__ import annotations

import asyncio
import itertools
import re
import sys

from fastmcp import Client

from cluster_mcp.core.capabilities import installed
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.resources import OPEN_RESOURCES
from cluster_mcp.core.server import create_mcp_server
from cluster_mcp.core.site import HEADING, SiteContext

CORE = {'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file',
        'cluster_context'}
WANT = {
    'slurm': {'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'},
    'rcac': {'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
             'average_wait', 'slist', 'sfeatures'},
}
DISTRIBUTION = {'slurm': 'cluster-mcp-slurm', 'rcac': 'cluster-mcp-rcac'}
ORDER = ('slurm', 'rcac')
CONTEXT = {'cluster://context', 'rcac://context'}
STORAGE = {'cluster://storage', 'rcac://storage'}
LISTED = re.compile(r'^- (\w+):', re.M)


async def served(capabilities: tuple) -> tuple[list[str], str, dict[str, dict]]:
    server = create_mcp_server('none', site=SiteContext.missing('this host'), capabilities=capabilities)
    async with Client(server) as client:
        tools = [t.name for t in await client.list_tools()]
        resources = {str(r.uri): r.model_dump(mode='json', by_alias=True) for r in await client.list_resources()}
        return tools, client.instructions or '', resources


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ''
    if phase not in ('p1', 'p2'):
        raise SystemExit('usage: compose.py p1|p2')
    bad: list[str] = []
    found = {c.capability.name: c for c in installed()}
    if set(found) != set(ORDER):
        raise SystemExit(f'compose: installed() found {sorted(found)}, expected {sorted(ORDER)}')
    for name, loaded in found.items():
        if loaded.distribution != DISTRIBUTION[name]:
            bad.append(f'{name}: loaded from {loaded.distribution!r}, expected {DISTRIBUTION[name]!r}')
    seen: dict[frozenset, tuple[list[str], str]] = {}
    for size in range(len(ORDER) + 1):
        for given in itertools.permutations(ORDER, size):
            label = '+'.join(given) or 'core only'
            tools, instructions, resources = asyncio.run(served(tuple(found[n] for n in given)))
            want = CORE.union(*(WANT[n] for n in given))
            if sorted(tools) != sorted(want):
                bad.append(f'{label}: serves {sorted(set(tools) ^ want)} beyond or short of the expected set')
            dups = sorted({t for t in tools if tools.count(t) > 1})
            if dups:
                bad.append(f'{label}: serves {dups} more than once')
            texts = [CORE_INSTRUCTIONS] + [found[n].capability.instructions for n in ORDER if n in given]
            base = '\n\n'.join(texts)
            if not instructions.startswith(base + '\n\n' + HEADING):
                bad.append(f'{label}: the instructions are not the core text, then each capability text in '
                           f'composition order, then the site section')
            head = instructions.split('\n\n' + HEADING, 1)[0]
            listed = LISTED.findall(head)
            if sorted(listed) != sorted(set(listed)):
                bad.append(f'{label}: the base lists a tool twice')
            if set(listed) != set(tools):
                bad.append(f'{label}: the base lists {sorted(set(listed) - set(tools))} not served and '
                           f'omits {sorted(set(tools) - set(listed))} served')
            key = frozenset(given)
            if key in seen and seen[key] != (tools, instructions):
                bad.append(f'{label}: serves other tools or instructions than the same set in another order')
            seen.setdefault(key, (tools, instructions))
            if phase == 'p2':
                want_uris = CONTEXT | (STORAGE if 'rcac' in given else set())
                if set(resources) != want_uris:
                    bad.append(f'{label}: serves resources {sorted(resources)}, expected {sorted(want_uris)}')
                if 'rcac' in given and STORAGE <= set(resources):
                    a, b = resources['cluster://storage'], resources['rcac://storage']
                    if {k: v for k, v in a.items() if k != 'uri'} != {k: v for k, v in b.items() if k != 'uri'}:
                        bad.append(f'{label}: rcac://storage is not a copy of cluster://storage but for its URI')
    if phase == 'p2' and set(OPEN_RESOURCES) != CONTEXT:
        bad.append(f'OPEN_RESOURCES is {sorted(OPEN_RESOURCES)}, expected {sorted(CONTEXT)}')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'compose: ok ({len(seen)} capability sets, every order)', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
