"""What each install form installs, and what the server it starts serves, on the cycle's tree and the base's.

Usage, from the worktree root, in the development environment:

    uv run python -I spec/rcac-extra-brings-slurm/verify/install_surfaces.py BASE [--new REV]

Two trees are archived into one fresh lab directory (`tempfile.mkdtemp`, removed on exit): BASE (a
commit) and the cycle's tree, which is the index (`git write-tree`, what the next commit holds)
unless `--new` names a commit. Each install form below is installed from each tree with
`uvx --isolated --from '<requirement> @ file://<tree>/<subdirectory>'`, both trees resolved the same
way (unlocked, one uv cache, one run), under `bin/sandbox.sh`. Per form and tree it records the
workspace distributions the environment holds, and, in each protocol era, the whole served surface
of `<command> -e local --skip-probes` over stdio (`harness.surface_record`: instructions, every
listing entry with every key, server info, capabilities).

Checks: `[rcac]` installs the Slurm member and serves exactly what `[slurm,rcac]` served on BASE;
every other form installs what it installs today and serves exactly what it served on BASE; on BASE
the two `[rcac]` forms differ (the comparison sees a missing member). Exit 0 and `ok` on stdout, or
exit 1 naming each failed check.

Footprint: one uvx (and its server) at a time, under the sandbox; peak about 4 processes, under
1 GB. Each server is stopped when its client closes; nothing is left running.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

REPO = Path.cwd().resolve()
if not (REPO / 'spec' / 'rcac-extra-brings-slurm' / 'GOAL.md').is_file():
    sys.exit('install_surfaces: run from the cycle worktree root')
sys.path.insert(0, str(REPO / 'tests'))

import harness  # noqa: E402
from fastmcp.client.transports import StdioTransport  # noqa: E402

SANDBOX = REPO / 'bin' / 'sandbox.sh'
CORE = ('packages/cluster-mcp', 'cluster-mcp')
COMPAT = ('', 'rcac-mcp')

# Each install form: the requirement, the subdirectory it installs from, and the command it runs.
FORMS = {
    'rcac': ('cluster-mcp[rcac]', *CORE),
    'slurm,rcac': ('cluster-mcp[slurm,rcac]', *CORE),
    'rcac,slurm': ('cluster-mcp[rcac,slurm]', *CORE),
    'slurm': ('cluster-mcp[slurm]', *CORE),
    'core': ('cluster-mcp', *CORE),
    'compat': ('rcac-mcp', *COMPAT),
}

# The workspace distributions each form installs on the cycle's tree.
ALL = {'cluster-mcp', 'cluster-mcp-slurm', 'cluster-mcp-rcac'}
INSTALLS = {
    'rcac': ALL,
    'slurm,rcac': ALL,
    'rcac,slurm': ALL,
    'slurm': {'cluster-mcp', 'cluster-mcp-slurm'},
    'core': {'cluster-mcp'},
    'compat': ALL | {'rcac-mcp'},
}
WORKSPACE = ALL | {'rcac-mcp'}

# The Slurm member's tools, written out here, never read from the tree.
SLURM_TOOLS = {'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'}

LIST_DISTS = ('import importlib.metadata as m, json; '
              'print(json.dumps(sorted({d.metadata["Name"] for d in m.distributions()})))')


def archive(rev: str, into: Path) -> None:
    """Extract the tree of `rev` (a commit or a tree id) into `into`."""
    data = subprocess.run(['git', 'archive', '--format=tar', rev], check=True, capture_output=True).stdout
    into.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(into, filter='data')


def requirement(tree: Path, form: str) -> tuple[str, str]:
    name, sub, command = FORMS[form]
    where = tree / sub if sub else tree
    return f'{name} @ {where.as_uri()}', command


def installed(tree: Path, form: str) -> set[str]:
    req, _ = requirement(tree, form)
    out = subprocess.run([str(SANDBOX), 'uvx', '--isolated', '--from', req, 'python', '-I', '-c', LIST_DISTS],
                         check=True, capture_output=True, text=True, timeout=600).stdout
    return set(json.loads(out.strip().splitlines()[-1])) & WORKSPACE


async def _surface(argv: list[str], era: str) -> dict[str, Any]:
    transport = StdioTransport(argv[0], argv[1:], env=dict(os.environ), keep_alive=False)
    async with harness._EraClient(transport, None, era) as client:
        listings = {key: await harness._raw_listing(client, request, key)
                    for key, request, _ in harness.SURFACE_LISTINGS}
        identity = await harness._raw_identity(client, era)
    return harness.surface_record(listings, identity, era)


def served(tree: Path, form: str, era: str) -> dict[str, Any]:
    req, command = requirement(tree, form)
    argv = [str(SANDBOX), 'uvx', '--isolated', '--from', req, command, '-e', 'local', '--skip-probes']
    return harness.drive(_surface(argv, era), timeout=600)


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 3) or (len(argv) == 3 and argv[1] != '--new'):
        sys.exit('usage: install_surfaces.py BASE [--new REV]')
    base_rev = argv[0]
    new_rev = argv[2] if len(argv) == 3 else subprocess.run(
        ['git', 'write-tree'], check=True, capture_output=True, text=True).stdout.strip()
    problems: list[str] = []
    lab = Path(tempfile.mkdtemp(prefix='rebs-install-'))
    try:
        trees = {'base': lab / 'base', 'new': lab / 'new'}
        archive(base_rev, trees['base'])
        archive(new_rev, trees['new'])
        dists = {(side, form): installed(tree, form) for side, tree in trees.items() for form in FORMS}
        surfaces = {(side, form, era): served(tree, form, era)
                    for side, tree in trees.items() for form in FORMS for era in harness.ERAS}
    finally:
        shutil.rmtree(lab)
    for form, want in INSTALLS.items():
        if dists[('new', form)] != want:
            problems.append(f'{form}: installs {sorted(dists[("new", form)])}, expected {sorted(want)}')
    if 'cluster-mcp-slurm' in dists[('base', 'rcac')]:
        problems.append('rcac on the base already installs the Slurm member: the base is not the one with the bug')
    for era in harness.ERAS:
        new_rcac = surfaces[('new', 'rcac', era)]
        if new_rcac != surfaces[('base', 'slurm,rcac', era)]:
            problems.append(f'{era}: [rcac] does not serve what [slurm,rcac] served on the base')
        missing = SLURM_TOOLS - set(new_rcac['tools'])
        if missing:
            problems.append(f'{era}: [rcac] does not serve {sorted(missing)}')
        for form in FORMS:
            if form != 'rcac' and surfaces[('new', form, era)] != surfaces[('base', form, era)]:
                problems.append(f'{era}: {form} serves something other than it served on the base')
        if surfaces[('base', 'rcac', era)] == surfaces[('base', 'slurm,rcac', era)]:
            problems.append(f'{era}: on the base [rcac] and [slurm,rcac] serve the same: the comparison sees nothing')
    for problem in problems:
        print(f'install_surfaces: FAIL: {problem}', file=sys.stderr)
    if problems:
        return 1
    tools = len(surfaces[('new', 'rcac', harness.ERAS[0])]['tools'])
    print(f'ok: {len(FORMS)} forms x 2 trees x {len(harness.ERAS)} eras; [rcac] installs {sorted(INSTALLS["rcac"])} '
          f'and serves {tools} tools, the surface [slurm,rcac] served on the base')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
