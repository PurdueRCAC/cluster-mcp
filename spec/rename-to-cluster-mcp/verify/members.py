# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Each tool is registered by the member that owns it (GOAL R9).

    uv run python spec/rename-to-cluster-mcp/verify/members.py      from the worktree root

A tool's member is the `cluster_mcp.<member>` module its function was defined in. The Purdue tools,
`slist` and `sfeatures` included, must come from the RCAC member under their current names; the
Slurm tools from the Slurm member; the shell, file and context tools from the core. The sets are
pinned here, not read from the tree. Footprint: one process, no network, under 200 MB.
"""

from __future__ import annotations

import re
import sys

from cluster_mcp.core.tools import TOOL_REGISTRY

WANT = {
    'core': {'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file',
             'cluster_context'},
    'slurm': {'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'},
    'rcac': {'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
             'average_wait', 'slist', 'sfeatures'},
}


def member(tool) -> str:
    module = getattr(tool.fn, '__module__', '') or ''
    m = re.fullmatch(r'cluster_mcp\.(core|slurm|rcac)(\..+)?', module)
    return m.group(1) if m else f'unknown:{module}'


def main() -> int:
    have: dict[str, set[str]] = {}
    for tool in TOOL_REGISTRY:
        have.setdefault(member(tool), set()).add(tool.name)
    bad = [f'{m}: registers {sorted(have.get(m, set()))}, expected {sorted(WANT.get(m, set()))}'
           for m in sorted(set(WANT) | set(have)) if have.get(m, set()) != WANT.get(m, set())]
    if len(TOOL_REGISTRY) != sum(map(len, WANT.values())):
        bad.append(f'{len(TOOL_REGISTRY)} registrations, expected {sum(map(len, WANT.values()))}')
    for b in bad:
        print(f'members: {b}', file=sys.stderr)
    print('members: ok' if not bad else 'members: FAILED', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
