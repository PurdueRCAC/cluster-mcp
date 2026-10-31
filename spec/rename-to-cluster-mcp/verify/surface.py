# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Print what a server built from PACKAGE serves, as JSON: its name, tools and resources.

    python surface.py PACKAGE OUT.json      PACKAGE is rcac_mcp (the baseline) or cluster_mcp.core

The server is built in this process with auth `none` and no site files, then listed by an
in-memory FastMCP client: nothing is executed and nothing is reached over a network. Each tool
keeps its name, description, input and output schemas and annotations, dumped by their wire
names; each resource its URI, name, title, description, MIME type and annotations. A field missing
from the dump fails the run, so a renamed field can never blind the comparison. Run it inside bin/sandbox.sh, each tree in its own environment.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys

from fastmcp import Client


async def surface(package: str) -> dict:
    server_mod = importlib.import_module(f'{package}.server')
    site_mod = importlib.import_module(f'{package}.site')
    server = server_mod.create_mcp_server('none', site=site_mod.SiteContext.missing('this host'))
    async with Client(server) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
    keep = ('name', 'description', 'inputSchema', 'outputSchema', 'annotations')
    dumped = [t.model_dump(mode='json', by_alias=True) for t in tools]
    for d in dumped:
        missing = [k for k in keep if k not in d]
        if missing:
            raise SystemExit(f'surface: tool {d.get("name")} dumps without {missing}: the comparison would be blind')
    rkeep = ('uri', 'name', 'title', 'description', 'mimeType', 'annotations')
    rdumped = [r.model_dump(mode='json', by_alias=True) for r in resources]
    for d in rdumped:
        missing = [k for k in rkeep if k not in d]
        if missing:
            raise SystemExit(f'surface: resource {d.get("uri")} dumps without {missing}')
    return {
        'server_name': server.name,
        'tools': sorted(({k: d[k] for k in keep} for d in dumped), key=lambda t: t['name']),
        'resources': sorted(({k: d[k] for k in rkeep} for d in rdumped), key=lambda r: r['uri']),
    }


def main() -> int:
    package, out = sys.argv[1], sys.argv[2]
    data = asyncio.run(surface(package))
    with open(out, 'w') as f:
        json.dump(data, f, indent=1, sort_keys=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
