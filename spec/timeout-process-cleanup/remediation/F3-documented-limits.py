"""Review cycle 1, F3: every documented limit of the stop at a timeout maps to rows that show it, per mode.

    uv run python -I spec/timeout-process-cleanup/remediation/F3-documented-limits.py      from the worktree root

`LIMITS` is the map: each limit the documents state, the lead it has in `AGENTS.md` § Invariants
§3's list of limits and in `issues/timeout-stop-limits.md`'s, the phrase that states it in
`README.md`, `SECURITY.md` (the non-root edges) and the `ROADMAP.md` entry where it belongs there, and
the `tests/test_timeout_stop.py` `test_a_recorded_limit` rows that show it in every mode, each row
asserting what runs on past the bound and what is stopped, as written. Green when:

- the leads of §3's list and of the seed's list are exactly the map's (a limit written down with no
  rows, or rows with no limit written down, is red);
- every phrase is in its document, and none of the statements the review found false is left
  (`STALE`);
- every mapped row, run with `CLUSTER_MCP_TEST_LIMITS=1` (which this checker sets), was collected and
  passed, and no limit row is unmapped.

Footprint: one pytest child (37 rows, each a sandbox, a login shell, a few `sleep`s and, over
`ssh`, one in-process server), under 500 MB, about 2.5 minutes.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

MODES = ('local', 'delegate-root', 'delegate', 'ssh-bash')
ROW = 'test_a_recorded_limit[{}]'


def rows(*cases: str) -> tuple[str, ...]:
    return tuple(ROW.format(f'{case}-{mode}') for case in cases for mode in MODES)


# key: (AGENTS §3 lead, seed lead or None, README phrase or None, SECURITY phrase or None, ROADMAP
# phrase or None, rows)
LIMITS: dict[str, tuple[str, str | None, str | None, str | None, str | None, tuple[str, ...]]] = {
    'left-group': ('A process that has left the group', None,
                   "a process that has left the command's process group", None, None, rows('left-group')),
    'hanging-login': ('A login initialisation that hangs', 'A login initialisation that hangs',
                      'a login startup file that hangs before the command starts',
                      'what a login startup file that hangs before the command starts has started runs on',
                      'A startup file that hangs leaves what it started running',
                      rows('hang-ignoring', 'hang-child', 'hang-child-ignoring', 'hang-child-ignoring-unheld')),
    'late-start': ('A command started after the deadline under a non-root `delegate` server',
                   'A command started after the deadline under a non-root `delegate` server.',
                   'a command that a startup file ignoring TERM starts only after the deadline',
                   'a command that a startup file ignoring TERM starts only after the deadline runs on, unbounded',
                   'lets the command start after the deadline and run unbounded', rows('late-start')),
    'deaf-server': ('An SSH server that does not act on the `signal` request',
                    'An SSH server that does not act on the RFC 4254 `signal` request',
                    'a command on a server that ignores the SSH `signal` request', None,
                    'an SSH server that ignores the `signal` request stops nothing',
                    (ROW.format('deaf-server-ssh-bash'),)),
    'term-twice': ('A command that handles TERM may get it twice', 'A command that handles TERM may get it twice',
                   None, None, 'a command that handles TERM may get it twice', rows('term-twice')),
    'fork-window': ('A TERM that lands while the program forks its watchdog',
                    'A TERM that lands while the program forks its watchdog',
                    'one whose deadline falls in the instant its launch spends starting the stop',
                    'a command whose deadline falls in the instant its launch spends starting that stop',
                    "a TERM in the program's forking window", rows('fork-window')),
    'enable-n-trap': ("A profile's `enable -n trap`", "A profile's `enable -n trap`", '(`enable -n trap`)', None,
                      "a profile's `enable -n trap`", rows('enable-n-trap')),
}

# Statements the review found false, or this cycle's own retired wording, that must not come back.
STALE = {
    'AGENTS.md': ('is stopped in `local`, under a root `delegate` server and over `ssh` (by the KILL request',
                  'as does `enable -n kill` or `enable -n read`', 'then asks for KILL and closes the channel'),
    'README.md': ('a login startup file that hangs before the command starts in `delegate` mode under a server '
                  'that is not root, over ssh',),
    'issues/timeout-stop-limits.md': ('2026-11-02:', 'over `ssh` it is now stopped'),
    'ROADMAP.md': ('over SSH the hanging startup file is now stopped',),
}


def flat(text: str) -> str:
    return ' '.join(text.split())


def leads(block: str) -> list[str]:
    """The bold leads of a block's top-level list items."""
    return [flat(m) for m in re.findall(r'^ {0,2}- \*\*(.+?)\*\*', block, re.M | re.S)]


def main() -> int:
    problems: list[str] = []
    agents = Path('AGENTS.md').read_text()
    section = agents[agents.index('### 3. '):agents.index('### 4. ')]
    block = section[section.index('The limits (recorded, not fixed;'):
                    section.index('A connection lost before the deadline is not a timeout')]
    found = leads(block)
    wanted = [entry[0] for entry in LIMITS.values()]
    if sorted(found) != sorted(wanted):
        problems.append(f'AGENTS.md §3 limits {found}, not the map\'s {wanted}')
    seed = Path('issues/timeout-stop-limits.md').read_text()
    problem = seed[seed.index('## Problem'):seed.index('## Why it was deferred')]
    found = [lead.rstrip(',') for lead in leads(problem)]
    wanted = [entry[1].rstrip(',') for entry in LIMITS.values() if entry[1]]
    if sorted(found) != sorted(wanted):
        problems.append(f'the seed\'s limits {found}, not the map\'s {wanted}')
    roadmap = Path('ROADMAP.md').read_text()
    entry = roadmap[roadmap.index('## What a timeout still cannot stop'):]
    entry = entry[:entry.index('\n## ')]
    texts = {'README.md': flat(Path('README.md').read_text()), 'SECURITY.md': flat(Path('SECURITY.md').read_text()),
             'ROADMAP.md': flat(entry)}
    for key, (_, _, readme, security, road, _) in LIMITS.items():
        for name, phrase in (('README.md', readme), ('SECURITY.md', security), ('ROADMAP.md', road)):
            if phrase and flat(phrase) not in texts[name]:
                problems.append(f'{key}: {name} does not state it ({phrase!r})')
    for name, phrases in STALE.items():
        text = flat(Path(name).read_text())
        problems += [f'{name} still says {phrase!r}' for phrase in phrases if flat(phrase) in text]
    mapped = {row for entry in LIMITS.values() for row in entry[5]}
    with tempfile.TemporaryDirectory(prefix='tpc-f3-') as scratch:
        report = Path(scratch, 'junit.xml')
        env = dict(os.environ, CLUSTER_MCP_TEST_LIMITS='1')
        code = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-k', 'recorded_limit',
                               f'--junitxml={report}', 'tests/test_timeout_stop.py'], env=env).returncode
        outcomes = {c.get('name'): next((t.tag for t in c if t.tag in ('failure', 'error', 'skipped')), 'passed')
                    for c in ET.parse(report).getroot().iter('testcase')}
    problems += [f'{row}: {outcomes.get(row, "not collected")}' for row in sorted(mapped)
                 if outcomes.get(row) != 'passed']
    problems += [f'{row}: a limit row no documented limit maps to' for row in sorted(set(outcomes) - mapped)]
    if code and not problems:
        problems.append(f'pytest exit {code}')
    print('\n'.join(problems) or f'F3: {len(LIMITS)} documented limits, each stated where it belongs and shown by '
                                 f'{len(mapped)} rows in every mode, every row passed')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
