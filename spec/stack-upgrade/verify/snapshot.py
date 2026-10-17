"""Write the served surface of `rcac_mcp` as canonical JSON: the R3 baseline.

Usage: uv run python snapshot.py <out.json>     (run in the tree whose server is being recorded)

Run against an archive of 3d010ec in that commit's own locked environment (FastMCP 2.x), it
produces `tests/fixtures/served_surface.json`; the gate re-runs it there and requires the committed
fixture to be identical. It records, through a handshake-era client over the in-memory transport,
what R3 names: every tool's description and input schema (and its output schema), every resource's
URI, name, description and MIME type, and the served instructions. Field access tolerates both the
mcp 1.x (`inputSchema`) and 2.x (`input_schema`) spellings, so the script also runs on the new
stack for comparison.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from fastmcp import Client

from rcac_mcp.server import create_mcp_server


def field(obj: Any, *names: str) -> Any:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


async def surface() -> dict[str, Any]:
    server = create_mcp_server('none')
    async with Client(server) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        init = client.initialize_result
        instructions = init.instructions if init is not None else client.instructions
    return {
        'instructions': instructions,
        'tools': {t.name: {'description': t.description,
                           'inputSchema': field(t, 'inputSchema', 'input_schema'),
                           'outputSchema': field(t, 'outputSchema', 'output_schema')} for t in tools},
        'resources': {str(r.uri): {'name': r.name, 'description': r.description,
                                   'mimeType': field(r, 'mime_type', 'mimeType')} for r in resources},
    }


def main() -> int:
    data = asyncio.run(surface())
    with open(sys.argv[1], 'w') as out:
        json.dump(data, out, indent=1, sort_keys=True)
        out.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
