# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Launch a stdio server, list what it serves, and check it against the expected sets.

    python served.py EXPECT.json -- COMMAND [ARG…]        inside bin/sandbox.sh only

COMMAND is started as a stdio MCP server with this process's environment (PYTHONPATH included), and
a FastMCP client in the handshake era lists its tools, resources and instructions. EXPECT.json is
`{"tools": [...], "resources": [...], "texts": [...]}`: the tools and resource URIs served must be
exactly those, each once; the base (the instructions before the site section) must be exactly the
`texts` joined by a blank line; and the base must list, as `- name:` lines, exactly the tools served,
each once. Refuses to run outside bin/sandbox.sh, since the server it starts runs commands as the
caller. Footprint: this process and the server, under 400 MB; a few seconds.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

HEADING_START = '\n\n## Site context ('
LISTED = re.compile(r'^- (\w+):', re.M)


async def listing(argv: list[str]) -> tuple[list[str], list[str], str]:
    env = dict(os.environ, FASTMCP_CHECK_FOR_UPDATES='off')
    transport = StdioTransport(argv[0], argv[1:], env=env, keep_alive=False)
    async with Client(transport) as client:
        tools = [t.name for t in await client.list_tools()]
        resources = [str(r.uri) for r in await client.list_resources()]
        return tools, resources, client.instructions or ''


def main() -> int:
    if not os.environ.get('CLUSTER_MCP_SANDBOX'):
        raise SystemExit('served: run inside bin/sandbox.sh')
    if len(sys.argv) < 4 or sys.argv[2] != '--':
        raise SystemExit('usage: served.py EXPECT.json -- COMMAND [ARG…]')
    expect = json.load(open(sys.argv[1]))
    tools, resources, instructions = asyncio.run(asyncio.wait_for(listing(sys.argv[3:]), 60))
    bad = []
    for what, got in (('tools', tools), ('resources', resources)):
        if sorted(got) != sorted(expect[what]):
            bad.append(f'{what}: served {sorted(got)}, expected {sorted(expect[what])}')
    if HEADING_START not in instructions:
        bad.append('the instructions carry no site section')
    base = instructions.split(HEADING_START, 1)[0]
    if base != '\n\n'.join(expect['texts']):
        bad.append(f'the base differs from the expected texts in order:\n{base}')
    listed = LISTED.findall(base)
    if len(listed) != len(set(listed)) or set(listed) != set(tools):
        bad.append(f'the base lists {sorted(listed)}; served {sorted(tools)}')
    print(*bad, sep='\n', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
