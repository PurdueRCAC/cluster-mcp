# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The served instructions are a generic core, the Slurm snippet and the RCAC-specific overlay.

    uv run python spec/rename-to-cluster-mcp/verify/instructions.py      from the worktree root

Independent of the suite's own tests, read from the installed members:
- the base (`SERVER_INSTRUCTIONS`) is exactly CORE, SLURM and RCAC joined by a blank line, in that
  order, and the served instructions of a default server start with it, uncut, and carry the site
  section after it (GOAL R12);
- the core text says neither RCAC nor Purdue, in any case, and names no tool the RCAC member
  registers (R11);
- the overlay's first line labels it RCAC-specific, and it lists every tool the RCAC member
  registers, and nothing else; the Slurm snippet likewise for the Slurm member; the core text for the
  core's own tools (R12);
- every registered tool appears in the base as a `- name:` line exactly once (R12).
A tool's member is the `cluster_mcp.<member>` module its function was defined in. Footprint: one
process, no network, under 200 MB.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys

from fastmcp import Client

from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.server import SERVER_INSTRUCTIONS, create_mcp_server
from cluster_mcp.core.site import HEADING, SiteContext
from cluster_mcp.core.tools import TOOL_REGISTRY
from cluster_mcp.rcac.instructions import RCAC_INSTRUCTIONS
from cluster_mcp.slurm.instructions import SLURM_INSTRUCTIONS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LISTED = re.compile(r'^- (\w+):', re.M)


def member(tool) -> str:
    module = getattr(tool.fn, '__module__', '') or ''
    m = re.match(r'cluster_mcp\.(core|slurm|rcac)\b', module)
    return m.group(1) if m else f'unknown ({module})'


def main() -> int:
    bad = []
    if SERVER_INSTRUCTIONS != '\n\n'.join((CORE_INSTRUCTIONS, SLURM_INSTRUCTIONS, RCAC_INSTRUCTIONS)):
        bad.append('SERVER_INSTRUCTIONS is not core, Slurm and overlay joined by a blank line, in that order')
    if re.search(r'(?i)rcac|purdue', CORE_INSTRUCTIONS):
        bad.append('the core text names RCAC or Purdue')
    by = {'core': set(), 'slurm': set(), 'rcac': set()}
    for tool in TOOL_REGISTRY:
        by.setdefault(member(tool), set()).add(tool.name)
    from members import WANT
    if by != WANT:
        bad.append(f'tools by member: {by}, expected {WANT}')
    for name, text in (('core', CORE_INSTRUCTIONS), ('slurm', SLURM_INSTRUCTIONS), ('rcac', RCAC_INSTRUCTIONS)):
        listed = LISTED.findall(text)
        if set(listed) != by.get(name, set()) or len(listed) != len(set(listed)):
            bad.append(f'the {name} text lists {sorted(listed)}, its member registers {sorted(by.get(name, ()))}')
    for tool in by.get('rcac', ()):
        if re.search(rf'\b{re.escape(tool)}\b', CORE_INSTRUCTIONS):
            bad.append(f'the core text names the RCAC tool {tool}')
    if 'RCAC-specific' not in RCAC_INSTRUCTIONS.splitlines()[0]:
        bad.append(f'the overlay opens {RCAC_INSTRUCTIONS.splitlines()[0]!r}, not an RCAC-specific label')
    names = LISTED.findall(SERVER_INSTRUCTIONS)
    for tool in TOOL_REGISTRY:
        if names.count(tool.name) != 1:
            bad.append(f'{tool.name} is listed {names.count(tool.name)} times in the base')

    async def served() -> str:
        server = create_mcp_server('none', site=SiteContext.missing('this host'))
        async with Client(server) as client:
            return client.instructions or ''
    text = asyncio.run(served())
    if not text.startswith(SERVER_INSTRUCTIONS + '\n') or HEADING not in text[len(SERVER_INSTRUCTIONS):]:
        bad.append('the served instructions do not start with the whole base followed by the site section')
    for b in bad:
        print(f'instructions: {b}', file=sys.stderr)
    print('instructions: ok' if not bad else 'instructions: FAILED', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
