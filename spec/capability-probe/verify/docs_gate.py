# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""AGENTS.md, README.md and the CLI help describe the probe where R10 says, in words the code bears out.

    uv run python -I spec/capability-probe/verify/docs_gate.py p1|p2        from the worktree root

p1 (the contract) — § Invariants §7 gives the record as `Capability(name, order, tools, instructions,
   resources, commands)`, says the commands are looked up with `type -P`, and that a malformed
   declaration is refused at load; the high-blast-radius list carries
   `packages/cluster-mcp/src/cluster_mcp/core/probes.py` as an item of its own.
p2 (cumulative) — §4 places the probe on the shared executor, after the site read and before the
   server is built, says every refusal (the budget's included) comes first, names
   `PROBE_TIMEOUT` and its 10 s, that a probe with no
   answer serves the capability (fail open), that `delegate` runs none, and names `--skip-probes`;
   §9 says the base is composed from the capabilities served, which the probe may withhold;
   § Testing also says how a probe test opts in (it removes the variable);
   § Configuration has a table row for `CLUSTER_MCP_SKIP_PROBES` naming `--skip-probes`, and saying any
   non-empty value turns it on; § Testing says the suite sets `CLUSTER_MCP_SKIP_PROBES` for every test
   and that a probe test removes it; README.md says an installed capability is served only where the
   cluster has what it needs, quotes the stderr line's `withheld` form, and names `--skip-probes`;
   `cluster-mcp --help` (in bin/sandbox.sh) names `--skip-probes` and `CLUSTER_MCP_SKIP_PROBES`.
Every check also requires the figure the code holds: `probes.PROBE_TIMEOUT` is the number §4 states,
and the withheld line README quotes is the one `MCPServerApp._served` formats, read from its source.
A section is read from its heading to the next heading of the same or a higher level. Footprint: one
process and one sandboxed `--help`, no network, under 200 MB.
"""

from __future__ import annotations

import inspect
import re
import subprocess
import sys
from pathlib import Path

PHASES = ('p1', 'p2')


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


def need(bad: list[str], where: str, text: str, pattern: str, what: str) -> None:
    if not re.search(pattern, flat(text), re.I):
        bad.append(f'{where}: {what} (no match for /{pattern}/)')


def p1(agents: str, bad: list[str]) -> None:
    s7 = section(agents, '### 7.')
    need(bad, '§7', s7, r'Capability\(name, order, tools, instructions, resources, commands\)', 'names the record with commands')
    need(bad, '§7', s7, r'type -P', 'says how a command is looked up')
    need(bad, '§7', s7, r'command[^.]*refused|refuse[^.]*command', 'says a malformed declaration is refused at load')
    blast = section(agents, '### High-blast-radius paths')
    if not re.search(r'^- `packages/cluster-mcp/src/cluster_mcp/core/probes\.py`', blast, re.M):
        bad.append('the high-blast-radius list has no item of its own for core/probes.py')
    items = re.findall(r'^- (.*(?:\n(?!- |\n).*)*)', blast, re.M)
    if any(item.count('`packages/') > 1 and 'probes.py' in item and ' and\n' not in item for item in items):
        bad.append('core/probes.py sits inside another item of the high-blast-radius list')


def p2(agents: str, readme: str, bad: list[str]) -> None:
    from cluster_mcp.core import MCPServerApp, probes
    s4 = section(agents, '### 4.')
    need(bad, '§4', s4, r'probe', 'describes the probe step')
    need(bad, '§4', s4, r'PROBE_TIMEOUT', 'names the bound')
    figure = f'{probes.PROBE_TIMEOUT:g} s'
    need(bad, '§4', s4, re.escape(figure), f'states the bound the code holds ({figure})')
    need(bad, '§4', s4, r'shared executor[^.]*probe|probe[^.]*shared executor', 'places it on the shared executor')
    need(bad, '§4', s4, r'after[^.]*site read[^.]*before[^.]*(server|create_mcp_server)'
                        r'|before[^.]*(server|create_mcp_server)[^.]*after[^.]*site read',
         'places it after the site read and before the server is built')
    need(bad, '§4', s4, r'(refus|budget)[^.]*before[^.]*probe|probe[^.]*after[^.]*(refus|budget)',
         'says every refusal, the budget\'s included, comes before the probe')
    need(bad, '§4', s4, r'fail(s)? open|served[^.]*no (definite )?answer|without a probe answer', 'says no answer serves the capability')
    need(bad, '§4', s4, r'delegate[^.]*(no|skip)[^.]*probe|probe[^.]*skip[^.]*delegate', 'says delegate runs no probe')
    need(bad, '§4', s4, r'--skip-probes', 'names the override')
    s9 = section(agents, '### 9.')
    need(bad, '§9', s9, r'withh', 'says a capability can be withheld from the base')
    conf = section(agents, '## Configuration')
    need(bad, '§ Configuration', conf, r'\| `CLUSTER_MCP_SKIP_PROBES` \|[^|]*--skip-probes', 'has the variable row naming the flag')
    need(bad, '§ Configuration', conf, r'`CLUSTER_MCP_SKIP_PROBES` \|[^|]*non-empty', 'says any non-empty value turns it on')
    testing = section(agents, '## Testing')
    need(bad, '§ Testing', testing, r'CLUSTER_MCP_SKIP_PROBES', 'says the suite sets the override')
    need(bad, '§ Testing', testing, r'probe test[^.]*(remov|unset|delenv)|(remov|unset|delenv)[^.]*probe test',
         'says how a probe test opts in')
    need(bad, 'README', readme, r'served only where|only where the cluster has', 'says when a capability is served')
    need(bad, 'README', readme, r'--skip-probes', 'names the override')
    served = inspect.getsource(MCPServerApp._served)
    m = re.search(r"f'(Capability \{name\} withheld: [^']*)'", served)
    if not m:
        bad.append('MCPServerApp._served formats no withheld line this gate can read')
    else:
        fixed = 'withheld: ' + m.group(1).split('withheld: ', 1)[1].split('{')[0]
        if fixed not in flat(readme):
            bad.append(f'README: does not quote the withheld line the code formats ({fixed!r})')
    shown = subprocess.run(['bin/sandbox.sh', 'uv', 'run', '--offline', 'cluster-mcp', '--help'],
                           capture_output=True, text=True, timeout=120).stdout
    for name in ('--skip-probes', 'CLUSTER_MCP_SKIP_PROBES'):
        if name not in shown:
            bad.append(f'cluster-mcp --help does not name {name}')


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in PHASES:
        raise SystemExit(f'usage: docs_gate.py {"|".join(PHASES)}')
    agents, readme = Path('AGENTS.md').read_text(), Path('README.md').read_text()
    bad: list[str] = []
    p1(agents, bad)
    if sys.argv[1] == 'p2':
        p2(agents, readme, bad)
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'docs_gate: {sys.argv[1]} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
