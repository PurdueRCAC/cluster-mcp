# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""AGENTS.md and README.md describe the registration and composition contract and the extras.

    uv run --no-project python spec/capability-extras/verify/docs.py p1|p2|p3|p4      from the worktree root

Each phase checks what it has made true (cumulative):
p1 — § Invariants §7 no longer calls registration an import-time side effect of an import list and
     names the entry-point group `cluster_mcp.capabilities`; §9 no longer says the base is three
     texts in a fixed order and names the group; the footgun list no longer calls the bottom of
     `tools/__init__.py` an import list; the high-blast-radius list carries
     `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`;
p2 — §8 says the RCAC member registers `cluster://storage`, and no longer binds every resource
     entry, the alias line and OPEN_RESOURCES to one module;
p3 — §4 or §7 states that a capability that fails to load stops startup, with the message shape
     `cannot load capability`;
p4 — § Packaging names the extras (`cluster-mcp[slurm,rcac]`) and no longer says the core depends
     on both members; README.md's Quick Start installs `cluster-mcp[slurm,rcac] @ git+…`; its
     install note no longer says `cluster-mcp` depends on its members; and in its tool inventory every
     Slurm tool sits under a heading naming `[slurm]`, every RCAC tool under one naming `[rcac]`, and
     every core tool under a heading naming no extra.
A section is read from its heading to the next heading of the same or a higher level. Footprint:
one process, no network, under 50 MB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CORE = ('run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file', 'cluster_context')
SLURM = ('sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node')
RCAC = ('myquota', 'storage_paths', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions', 'average_wait',
        'slist', 'sfeatures')
PHASES = ('p1', 'p2', 'p3', 'p4')


def section(text: str, heading: str) -> str:
    """The section whose heading line starts with `heading` (e.g. '### 7.'), or ''."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(heading):
            level = len(line) - len(line.lstrip('#'))
            out = []
            for later in lines[i + 1:]:
                m = re.match(r'(#+) ', later)
                if m and len(m.group(1)) <= level:
                    break
                out.append(later)
            return line + '\n' + '\n'.join(out)
    return ''


def flat(s: str) -> str:
    return re.sub(r'\s+', ' ', s)


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ''
    if phase not in PHASES:
        raise SystemExit(f'usage: docs.py {"|".join(PHASES)}')
    upto = PHASES[:PHASES.index(phase) + 1]
    agents, readme = Path('AGENTS.md').read_text(), Path('README.md').read_text()
    bad: list[str] = []
    s7, s8, s9 = (flat(section(agents, f'### {n}.')) for n in (7, 8, 9))
    s4 = flat(section(agents, '### 4.'))
    if not (s7 and s8 and s9 and s4):
        sys.exit('docs: cannot find § Invariants §4, §7, §8 or §9')
    if 'p1' in upto:
        if re.search(r'import-time side effect|import list', s7, re.I):
            bad.append('§7 still describes registration as an import-time side effect of an import list')
        if 'cluster_mcp.capabilities' not in s7:
            bad.append('§7 does not name the entry-point group cluster_mcp.capabilities')
        if re.search(r'three texts|exactly three|joined by a blank line in this order', s9, re.I):
            bad.append('§9 still says the base is three fixed texts in a fixed order')
        if 'cluster_mcp.capabilities' not in s9 or 'order' not in s9:
            bad.append('§9 does not say the base is composed from the capabilities loaded through the group, by order')
        foot = flat(section(agents, '#### Footguns'))
        if re.search(r'bottom-of-file import list', foot):
            bad.append('the footgun list still calls tools/__init__.py an import list')
        hb = section(agents, '### High-blast-radius paths')
        if '`packages/cluster-mcp/src/cluster_mcp/core/capabilities.py`' not in hb:
            bad.append('the high-blast-radius list does not carry core/capabilities.py')
    if 'p2' in upto:
        if 'cluster://storage' not in s8 or not re.search(r'RCAC member', s8):
            bad.append('§8 does not say the RCAC member registers cluster://storage')
        if re.search(r'Keep every entry, the alias line and `?OPEN_RESOURCES`? in this one module', s8):
            bad.append('§8 still binds every resource entry and the alias line to one module')
    if 'p3' in upto:
        if 'cannot load capability' not in s4 + s7:
            bad.append('neither §4 nor §7 states the load-failure message')
    if 'p4' in upto:
        pk = flat(section(agents, '## Packaging'))
        if 'cluster-mcp[slurm,rcac]' not in pk:
            bad.append('§ Packaging does not name cluster-mcp[slurm,rcac]')
        if re.search(r'core depends on both members', pk):
            bad.append('§ Packaging still says the core depends on both members')
        qs = section(readme, '## Quick Start')
        if 'cluster-mcp[slurm,rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp' not in qs:
            bad.append('README Quick Start does not install cluster-mcp[slurm,rcac] from git')
        if re.search(r'`cluster-mcp` depends on its\s+Slurm and RCAC members', readme):
            bad.append('README still says cluster-mcp depends on its Slurm and RCAC members')
        inv = section(readme, '## Available Tools')
        where: dict[str, str] = {}
        heading = ''
        for line in inv.splitlines():
            if line.startswith('### '):
                heading = line
            m = re.match(r'- `(\w+)\(', line)
            if m:
                where.setdefault(m.group(1), heading)
        for names, extra in ((CORE, None), (SLURM, '[slurm]'), (RCAC, '[rcac]')):
            for n in names:
                h = where.get(n)
                if h is None:
                    bad.append(f'README inventory does not list {n}')
                elif extra is None and re.search(r'\[(slurm|rcac)\]', h):
                    bad.append(f'README lists core tool {n} under {h!r}')
                elif extra is not None and extra not in h:
                    bad.append(f'README lists {n} under {h!r}, not under a heading naming {extra}')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'docs: {phase} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
