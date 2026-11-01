# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The four pyproject.toml files declare the capability contract and, from p4, the extras.

    uv run --no-project python spec/capability-extras/verify/pyprojects.py p1|p4      from the worktree root

p1 (the entry points): each member declares exactly one entry point in `cluster_mcp.capabilities`,
named for its package and pointing at `cluster_mcp.<member>.capability:CAPABILITY`; the core and
the root declare none in that group.
p4 (the extras, and p1 again): the core's `dependencies` name no workspace member; its
`optional-dependencies` are exactly `slurm = ["cluster-mcp-slurm"]` and `rcac = ["cluster-mcp-rcac"]`;
its workspace sources for both members stay; each member depends on the core alone (the RCAC member
does not depend on the Slurm member); the root (the compat distribution `rcac-mcp`) depends on
exactly `cluster-mcp[slurm,rcac]`, with the core's workspace source. Footprint: one process, no
network, under 50 MB.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

GROUP = 'cluster_mcp.capabilities'
MEMBERS = {'slurm': 'cluster-mcp-slurm', 'rcac': 'cluster-mcp-rcac'}


def load(p: str) -> dict:
    return tomllib.loads(Path(p).read_text())


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ''
    if phase not in ('p1', 'p4'):
        raise SystemExit('usage: pyprojects.py p1|p4')
    bad: list[str] = []
    core, root = load('packages/cluster-mcp/pyproject.toml'), load('pyproject.toml')
    for short, dist in MEMBERS.items():
        m = load(f'packages/{dist}/pyproject.toml')
        eps = m['project'].get('entry-points', {}).get(GROUP, {})
        want = {short: f'cluster_mcp.{short}.capability:CAPABILITY'}
        if eps != want:
            bad.append(f'{dist}: entry points in {GROUP} are {eps}, expected {want}')
        if phase == 'p4' and m['project'].get('dependencies') != ['cluster-mcp']:
            bad.append(f"{dist}: depends on {m['project'].get('dependencies')}, expected ['cluster-mcp'] alone")
    for name, meta in (('cluster-mcp', core), ('rcac-mcp', root)):
        if meta['project'].get('entry-points', {}).get(GROUP):
            bad.append(f'{name}: declares an entry point in {GROUP}')
    if phase == 'p4':
        deps = core['project'].get('dependencies', [])
        internal = [d for d in deps if d.split('[')[0].split(';')[0].strip().startswith('cluster-mcp')]
        if internal:
            bad.append(f'cluster-mcp: depends unconditionally on {internal}')
        extras = core['project'].get('optional-dependencies')
        if extras != {'slurm': ['cluster-mcp-slurm'], 'rcac': ['cluster-mcp-rcac']}:
            bad.append(f'cluster-mcp: optional-dependencies are {extras}')
        sources = core.get('tool', {}).get('uv', {}).get('sources', {})
        for dist in MEMBERS.values():
            if sources.get(dist) != {'workspace': True}:
                bad.append(f'cluster-mcp: the workspace source of {dist} is {sources.get(dist)}')
        if root['project'].get('dependencies') != ['cluster-mcp[slurm,rcac]']:
            bad.append(f"rcac-mcp: depends on {root['project'].get('dependencies')}, expected ['cluster-mcp[slurm,rcac]']")
        if root.get('tool', {}).get('uv', {}).get('sources', {}).get('cluster-mcp') != {'workspace': True}:
            bad.append('rcac-mcp: lost the workspace source of cluster-mcp')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'pyprojects: {phase} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
