# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Write what a default server built from this environment serves, as JSON, to OUT.

    python -I surface.py OUT.json        in the environment of the tree to describe

The server is built in this process with auth `none` and no site files, exactly as a caller that
names no capability set builds it, then listed by an in-memory FastMCP client: nothing is executed
and nothing is reached over a network. Kept whole, every field as the wire carries it: the
instructions; each tool and each resource (`model_dump` by alias, `_meta` and titles included), in
the order listed; the resource templates and the prompts; the server capabilities from the
initialize result; the server name. Also the three instruction texts as their modules hold them, so
a text moved from one member's constant to another's is seen even when the join is unchanged.
Run it inside bin/sandbox.sh. Footprint: one process, no network, under 300 MB.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys

from fastmcp import Client

from cluster_mcp.core.server import create_mcp_server
from cluster_mcp.core.site import SiteContext

TEXTS = (('cluster_mcp.core.instructions', 'CORE_INSTRUCTIONS'),
         ('cluster_mcp.slurm.instructions', 'SLURM_INSTRUCTIONS'),
         ('cluster_mcp.rcac.instructions', 'RCAC_INSTRUCTIONS'))


def dump(items: list) -> list[dict]:
    return [i.model_dump(mode='json', by_alias=True) for i in items]


async def surface() -> dict:
    server = create_mcp_server('none', site=SiteContext.missing('this host'))
    async with Client(server) as client:
        init = client.initialize_result
        out = {
            'server_name': server.name,
            'instructions': client.instructions,
            'tools': dump(await client.list_tools()),
            'resources': dump(await client.list_resources()),
            'resource_templates': dump(await client.list_resource_templates()),
            'prompts': dump(await client.list_prompts()),
            'capabilities': init.capabilities.model_dump(mode='json', by_alias=True) if init else None,
        }
    out['texts'] = {name: getattr(importlib.import_module(mod), name) for mod, name in TEXTS}
    return out


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit('usage: surface.py OUT.json')
    with open(sys.argv[1], 'w') as out:
        json.dump(asyncio.run(surface()), out, indent=1, sort_keys=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
