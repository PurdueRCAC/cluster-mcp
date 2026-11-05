"""Review cycle 3, B1, B2, B3, B5 and N3: every statement of what the stop promises is true, the
return bound included, every limit that remains is documented where it belongs and shown by rows,
per mode, the wall clock's included.

    uv run python -I spec/timeout-process-cleanup/remediation/documented-bound-and-limits.py      from the worktree root

It supersedes review cycle 2's `documented-stop.py`, which stays as the record: that map promised
that a TERM reaching the program while it forks its watchdog ends it before its command starts
(review cycle 3's B3 retired it: the program now forks with TERM ignored, and the deadline's check
covers a TERM lost there), let §3 say `run` returns no later than before the watchdog (B1; the
ruling: R4 reworded to the bound) and that the clock is read to the nanosecond on the server's clock
(B5; the ruling: document the limit), and lacked the wall clock's limit.

Review cycle 3 verification, N3: not reproduced (the posix-mode round trip changes the program's own
shell options and does not refresh `BASHOPTS`, measured on bash 4.4, 5.1 and 5.2), so the options
restore is removed. The promise that the command's subshell sets the options back becomes the
measured fact, stated once in `AGENTS.md` § Invariants, and the restore's names are stale everywhere
they were documented (`STALE_N3`).

`LIMITS` is the map: each limit the documents state, its lead in `AGENTS.md` § Invariants §3's list
and in `issues/timeout-stop-limits.md`'s, the phrase that states it in `README.md`, `SECURITY.md`
(the non-root edges) and the `ROADMAP.md` entry where it belongs there, and the
`tests/test_timeout_stop.py` `test_a_recorded_limit` rows that show it in every mode it applies to.
`PROMISES` are the statements the reviews' findings route (one TERM per process, and what a non-root
server's group gets instead; a command past its deadline not started, a TERM lost while the program
forks included; `run`'s return within the bound; no name of the program's reaching a command, and
the shell options a command sees, and why the program never refreshes `BASHOPTS`; both effects of the shadowed-builtins limit; the clocks; the
spec-id rule naming `Q#`; a lost reader's stop), each in every document that must carry it. `STALE`
are the statements the reviews found false, or this cycle's retired wording (`STALE_N3`: the
restore's). Green when:

- the leads of §3's list and of the seed's list are exactly the map's;
- every phrase and promise is in its document, and no stale statement is left;
- every mapped row, run with `CLUSTER_MCP_TEST_LIMITS=1` (which this checker sets), was collected and
  passed, and no limit row is unmapped.

Footprint: one pytest child (35 rows, each a sandbox, a login shell, a few `sleep`s and, over `ssh`,
one in-process server), under 500 MB, about 2.5 minutes.
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


SHADOWED = "A startup file that shadows the launch's builtins past what the prologue undoes"
CLOCK = "A step of the server's wall clock during the login initialisation"
# key: (AGENTS §3 lead, seed lead, README phrase or None, SECURITY phrase or None, ROADMAP phrase or None, rows)
LIMITS: dict[str, tuple[str, str, str | None, str | None, str | None, tuple[str, ...]]] = {
    'left-group': ('A process that has left the group', "A process that has left the command's process group",
                   "a process that has left the command's process group", None, None, rows('left-group')),
    'hanging-login': ('A login initialisation that hangs', 'A login initialisation that hangs',
                      'a login startup file that hangs before the command starts',
                      'what a login startup file that hangs before the command starts has started runs on',
                      'A startup file that hangs leaves what it started running',
                      rows('hang-ignoring', 'hang-child', 'hang-child-ignoring', 'hang-child-ignoring-unheld')),
    'deaf-server': ('An SSH server that does not act on the `signal` request',
                    'An SSH server that does not act on the RFC 4254 `signal` request',
                    'a command on a server that ignores the SSH `signal` request', None,
                    'an SSH server that ignores the `signal` request stops nothing',
                    (ROW.format('deaf-server-ssh-bash'),)),
    'shadowed-builtins': (SHADOWED, SHADOWED + '.',
                          'unless a login startup file shadows the shell builtins the launch runs in a way it cannot '
                          'undo', None,
                          "a startup file that shadows the launch's builtins past what the prologue undoes can make the "
                          'stop fail and stop a command early', rows('shadowed-stop', 'shadowed-early')),
    'clock-step': (CLOCK + '.', CLOCK + '.',
                   "unless the server's wall clock steps meanwhile",
                   "so does a command that a login startup file ignoring TERM delays past its deadline, if the "
                   "server's wall clock steps back meanwhile",
                   "a step of the server's wall clock while a startup file runs can refuse a command early",
                   tuple(ROW.format(f'{case}-{mode}') for case in ('clock-forward', 'clock-back')
                         for mode in MODES[:3])),
}

# (document, phrase): statements the findings route, which must be there.
PROMISES = (
    # F2: one TERM per process; a non-root server's group gets KILL after the grace, no TERM.
    ('AGENTS.md', '**Every process gets at most that one TERM**'),
    ('AGENTS.md', "the rest of the group gets no TERM, and the watchdog's KILL `GRACE` later"),
    ('AGENTS.md', 'waits `launch.GRACE` and sends the process group KILL, and never TERM'),
    ('AGENTS.md', 'sends the rest KILL `GRACE` later, and no TERM'),
    ('README.md', 'each process gets at most one TERM signal'),
    ('README.md', "only the launch gets the TERM, and the command's processes get KILL a second later"),
    ('SECURITY.md', "the command's processes get no TERM, only KILL a second after the deadline"),
    ('issues/timeout-stop-limits.md', 'waits `GRACE` and sends KILL to the process group, never TERM'),
    # F3: a command past its deadline never starts where the clock is the server's; no other right.
    ('AGENTS.md', 'a command whose deadline passed while the login initialisation ran'),
    # B3: forked with TERM ignored; a TERM lost while it forks covered by the deadline's check, and over
    # `ssh` by the KILL request.
    ('AGENTS.md', 'forked with TERM ignored, so it is born ignoring TERM and no TERM to the group ends it at any '
                  'instant'),
    ('AGENTS.md', 'or while the program forked its watchdog (the TERM came while it was ignored), never starts'),
    ('AGENTS.md', 'the KILL request after the grace stops a command that starts late, or whose TERM came while the '
                  'program forked its watchdog'),
    ('packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py', 'born ignoring TERM'),
    # B1: run's return within the bound.
    ('AGENTS.md', '**`run` returns a timed-out call within the same bound**'),
    ('README.md', 'returns what it printed so far with exit code `-1001`, within 2 seconds of the deadline'),
    ('packages/cluster-mcp/src/cluster_mcp/core/executor/base.py', 'the call returns within the same bound'),
    # B2, N3: no name of the program's reaches a command; the shell options a command sees.
    ('AGENTS.md', '**No variable the program sets reaches the command**'),
    ('AGENTS.md', "**The posix-mode round trip changes the program's own shell options, never a command's**"),
    ('AGENTS.md', 'The program therefore never runs `shopt`, or anything else that refreshes `BASHOPTS`, before '
                  'the command'),
    ('packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py',
     "lines therefore never run `shopt`, or anything else that refreshes `BASHOPTS`, before the command"),
    # B5: the clocks, exactly.
    ('AGENTS.md', "it is given its deadline on the server's wall clock (epoch nanoseconds, `time.time_ns()`"),
    ('AGENTS.md', 'GNU `date` prints nanoseconds, macOS\'s microseconds'),
    ('issues/timeout-stop-limits.md', 'nanoseconds from GNU `date` and microseconds from macOS\'s'),
    # N1: over `ssh` the program is given no deadline.
    ('AGENTS.md', 'so the program gets no deadline and the call\'s timeout runs from the command\'s start'),
    ('AGENTS.md', "None of this needs a `sudo` right beyond the rule `SECURITY.md` documents"),
    ('README.md', 'is not started in `local` or `delegate` mode'),
    ('SECURITY.md', 'inside the sudoers rules above, and needs no other right'),
    # F1, F4: the promise qualified, and both effects of the limit named.
    ('AGENTS.md', 'unless a startup file shadows the launch\'s builtins past what the prologue undoes'),
    ('AGENTS.md', 'can make the stop fail and can stop a command early'),
    ('issues/timeout-stop-limits.md', 'can make the stop fail and can stop a command early'),
    ('README.md', 'which can stop a command early'),
    ('README.md', "whatever ignores TERM and holds none of the command's output"),
    # F6: the spec-id rule names `Q#`, in § Testing and § Conventions.
    ('AGENTS.md', 'No feature-scoped spec id (`R#`, `P#`, `Q#`) appears in the package or the suite'),
    ('AGENTS.md', '**never** a feature-scoped spec id (`R#`, `P#`, `Q#`)'),
    # F7: a lost reader's stop.
    ('AGENTS.md', 'background jobs the command left included'),
    ('README.md', 'has what it left running stopped too'),
)

# Statements the review found false, or this cycle's own retired wording, that must not come back.
STALE = {
    'AGENTS.md': ('sends the group TERM, waits `GRACE` and sends it', 'sends the process group TERM, waits',
                  'A command that handles TERM may get it twice', 'A command started after the deadline under a',
                  'A TERM that lands while the program forks its watchdog', "A profile's `enable -n trap`** disarms",
                  'after unsetting any function named `/bin/cat` or `/bin/sleep`', 'sends the rest TERM, then KILL',
                  'feature-scoped spec id (`R#`, `P#`)', 'forked with TERM ignored, that prints nothing',
                  'or that ignores TERM and starts the command after the deadline',
                  'is stopped in `local`, under a root `delegate` server and over `ssh` (by the KILL request',
                  'as does `enable -n kill` or `enable -n read`', 'then asks for KILL and closes the channel'),
    'README.md': ('or one that has not reached it, is never signalled by the stop. What is not stopped',
                  'spends starting the stop', '(`enable -n trap`)', 'starts only after the deadline'),
    'SECURITY.md': ('starts only after the deadline runs on, unbounded', 'spends starting that stop',
                    'Three edges remain'),
    'issues/timeout-stop-limits.md': ('may get it twice', 'forks its watchdog', 'A command started after the deadline',
                                      "A profile's `enable -n trap`", 'sends TERM to the process'),
    'ROADMAP.md': ('may get it twice', 'forking', 'start after the deadline and run unbounded', 'enable -n trap'),
    'issues/local-command-outlives-server.md': ('which sends the\n  group TERM', 'group TERM, then KILL'),
    'packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py': ('sends the group TERM', 'the TERM and KILL a group',
                                                                     'ignores TERM from its own first statement',
                                                                     'while it forks the watchdog included'),
}
# Review cycle 3's: B1's "no later than before", B3's fork promise, B5's nanosecond on the server's
# clock, the `kill-alias` row, the seed's count.
STALE_C3 = {
    'AGENTS.md': ('`run` returns no later than it did before the watchdog', 'to the nanosecond',
                  'a TERM that reaches it while it forks the watchdog ends it too',
                  'ignores TERM from its first statement', 'ignoring TERM from its own first statement',
                  'a TERM sent to the program alone while it forks the watchdog', 'alias over `kill`',
                  'and `run` returns no later than a launcher without the watchdog'),
    'issues/timeout-stop-limits.md': ('Four cases stay outside it',),
    'tests/test_timeout_stop.py': ('`run` returns no later than a launcher with no watchdog does',
                                   'a TERM that reaches the program while it forks its watchdog ends it before',
                                   "'kill-alias'"),
}

# Review cycle 3 verification, N3: the options restore, removed, and its names.
STALE_N3 = {
    'AGENTS.md': ('RESTORE_OPTIONS', 'cluster_mcp_o', 'cluster_mcp_x', 'sets back the shell options',
                  'the saved options and their loop\'s name'),
    'packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py': ('RESTORE_OPTIONS', 'cluster_mcp_o',
                                                                     'cluster_mcp_x'),
    'tests/test_launch.py': ('RESTORE_LINE', 'cluster_mcp_o'),
    'tests/test_timeout_stop.py': ('which the command\'s subshell sets back', 'its saved shell options'),
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
    found = leads(problem)
    wanted = [entry[1] for entry in LIMITS.values()]
    if sorted(found) != sorted(wanted):
        problems.append(f'the seed\'s limits {found}, not the map\'s {wanted}')
    roadmap = Path('ROADMAP.md').read_text()
    entry = roadmap[roadmap.index('## What a timeout still cannot stop'):]
    entry = entry[:entry.index('\n## ')]
    texts = {'README.md': flat(Path('README.md').read_text()), 'SECURITY.md': flat(Path('SECURITY.md').read_text()),
             'ROADMAP.md': flat(entry), 'AGENTS.md': flat(agents), 'issues/timeout-stop-limits.md': flat(seed)}
    for name in ('packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py',
                 'packages/cluster-mcp/src/cluster_mcp/core/executor/base.py'):
        texts[name] = flat(Path(name).read_text())
    for key, (_, _, readme, security, road, _) in LIMITS.items():
        for name, phrase in (('README.md', readme), ('SECURITY.md', security), ('ROADMAP.md', road)):
            if phrase and flat(phrase) not in texts[name]:
                problems.append(f'{key}: {name} does not state it ({phrase!r})')
    problems += [f'{name} does not say {phrase!r}' for name, phrase in PROMISES if flat(phrase) not in texts[name]]
    for stale in (STALE, STALE_C3, STALE_N3):
        for name, phrases in stale.items():
            text = flat(entry) if name == 'ROADMAP.md' else flat(Path(name).read_text())
            problems += [f'{name} still says {phrase!r}' for phrase in phrases if flat(phrase) in text]
    mapped = {row for entry in LIMITS.values() for row in entry[5]}
    with tempfile.TemporaryDirectory(prefix='tpc-limits-') as scratch:
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
    print('\n'.join(problems) or f'documented stop: {len(LIMITS)} limits, each stated where it belongs and shown by '
                                 f'{len(mapped)} rows in every mode, every row passed; {len(PROMISES)} promises '
                                 f'stated, nothing stale')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
