# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""In an installed environment, only the named capabilities are installed, discovered and registered.

    <env>/bin/python -I registry.py [slurm] [rcac]        run by coreonly.sh and probe.sh

Checks, in this environment: the installed `cluster-mcp*` distributions are exactly the core and
the named members; `cluster_mcp.slurm` / `cluster_mcp.rcac` can be found exactly when named; the
`cluster_mcp.capabilities` entry points come exactly from the named members' distributions; importing
`cluster_mcp.core` imports no member module; and after `installed()`, the startup load,
`TOOL_REGISTRY` holds exactly the core's seven tools and each named member's own, each once. Run
isolated (`-I`), so neither the working directory nor PYTHONPATH can add a module. Footprint: one
process, no network, under 200 MB.
"""

from __future__ import annotations

import importlib.metadata as md
import importlib.util
import sys

CORE = {'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file',
        'cluster_context'}
WANT = {
    'slurm': {'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'},
    'rcac': {'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
             'average_wait', 'slist', 'sfeatures'},
}
DISTRIBUTION = {'slurm': 'cluster-mcp-slurm', 'rcac': 'cluster-mcp-rcac'}
GROUP = 'cluster_mcp.capabilities'


def main() -> int:
    named = set(sys.argv[1:])
    if not named <= set(WANT):
        raise SystemExit(f'usage: registry.py [slurm] [rcac]; got {sorted(named)}')
    bad = []
    dists = {d.metadata['Name'] for d in md.distributions() if d.metadata['Name'].startswith('cluster-mcp')}
    want_dists = {'cluster-mcp'} | {DISTRIBUTION[n] for n in named}
    if dists != want_dists:
        bad.append(f'installed {sorted(dists)}, expected {sorted(want_dists)}')
    for n in WANT:
        found = importlib.util.find_spec(f'cluster_mcp.{n}') is not None
        if found != (n in named):
            bad.append(f'cluster_mcp.{n} {"can" if found else "cannot"} be found')
    eps = {ep.dist.name for ep in md.entry_points(group=GROUP)}
    if eps != {DISTRIBUTION[n] for n in named}:
        bad.append(f'the group lists entry points from {sorted(eps)}')
    import cluster_mcp.core  # noqa: F401
    leaked = sorted(m for m in sys.modules if m.split('.')[:2] in (['cluster_mcp', 'slurm'], ['cluster_mcp', 'rcac']))
    if leaked:
        bad.append(f'importing cluster_mcp.core imported {leaked}')
    try:
        from cluster_mcp.core.capabilities import installed
        from cluster_mcp.core.tools import TOOL_REGISTRY
        installed()
    except Exception as exc:
        bad.append(f'the startup load failed: {type(exc).__name__}: {exc}')
    else:
        names = [t.name for t in TOOL_REGISTRY]
        want = CORE.union(*(WANT[n] for n in named))
        if sorted(names) != sorted(want):
            bad.append(f'TOOL_REGISTRY holds {sorted(names)}, expected {sorted(want)}')
    print(*bad, sep='\n', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
