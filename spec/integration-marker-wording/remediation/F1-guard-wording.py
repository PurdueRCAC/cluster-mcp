# Review cycle 1, finding 1: every statement this cycle makes about what the unit guard or a hygiene
# check enforces is true of the code. An executed probe against tests/conftest.py itself (loaded as a
# plugin, as verify/guard_claims.py is), plus the staged text that states it.
#
# Run from the worktree root through remediation/checks.sh, which exports the XDG sentinels below:
#
#   sh spec/integration-marker-wording/remediation/checks.sh F1
#
# The probe: the guard points HOME and three XDG variables under tmp_path and leaves every other
# XDG variable as the shell exported it. The text: the unit description qualifies "holds it to that"
# with the open routes; § Testing, issues/marker-rule-gaps.md and its ROADMAP.md entry name every
# route verify/guard_claims.py finds open, the XDG and password-database routes included; the
# development commands say what the static launch check does not read; the check's own description
# claims no more than the check refuses. Staged text is read at import, before any guard is active.
#
# Footprint: one pytest process and two git children at import; under 150 MB; nothing outlives it.
from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

import guard_claims  # verify/, on PYTHONPATH: its OPEN table is the probe's list of open routes


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


def flat(text: str) -> str:
    return ' '.join(text.split())


PYPROJECT, AGENTS = staged('pyproject.toml'), staged('AGENTS.md')
GAPS, ROADMAP = staged('issues/marker-rule-gaps.md'), staged('ROADMAP.md')
SET_BY_GUARD = ('XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_DATA_HOME')
# The variables checks.sh exports, each to a path no test makes.
LEFT_ALONE = ('XDG_STATE_HOME', 'XDG_RUNTIME_DIR', 'XDG_CONFIG_DIRS', 'XDG_DATA_DIRS')
QUALIFIER = 'the unit guard holds it to that, except on the open routes AGENTS.md § Testing names'


def section(heading: str) -> str:
    start = AGENTS.index(f'\n{heading}\n')
    level = heading.split(' ', 1)[0]
    ends = [AGENTS.find(f'\n{"#" * n} ', start + 1) for n in range(1, len(level) + 1)]
    return AGENTS[start:min([e for e in ends if e != -1], default=len(AGENTS))]


def guard_paragraph() -> str:
    testing = section('## Testing')
    start = testing.index('  - **The unit guard** makes `unit` mean something')
    return flat(testing[start:testing.index('  - **The PATH shim**', start)])


def roadmap_entry() -> str:
    start = ROADMAP.index('\n## The checks behind the marker rules miss routes the rules forbid\n')
    return flat(ROADMAP[start:ROADMAP.index('**Seed:**', start)])


# Each route verify/guard_claims.py proves open, plus the two this probe proves, and the words that
# name it in § Testing's guard paragraph, in issues/marker-rule-gaps.md and in its ROADMAP.md entry
# (None: the summary entry need not list it).
NAMED: dict[str, tuple[str, str, str | None]] = {
    'early-bound Popen': ('a `from subprocess import Popen`', 'from subprocess import Popen', 'Popen'),
    'conftest.REAL_POPEN': ('`conftest.REAL_POPEN`', 'conftest.REAL_POPEN', 'conftest.REAL_POPEN'),
    'raw _socket connect': ('a `_socket` connect', '_socket.socket', '_socket'),
    'udp sendto': ('UDP `sendto`', 'UDP `sendto`', 'UDP'),
    'early-bound getaddrinfo': ('an early-bound `getaddrinfo`', 'from socket import getaddrinfo', 'getaddrinfo'),
    'gethostbyname': ('`socket.gethostbyname` and its kin', 'socket.gethostbyname', 'gethostbyname'),
    'gethostbyname_ex': ('`socket.gethostbyname` and its kin', 'gethostbyname_ex', 'gethostbyname'),
    'gethostbyaddr': ('`socket.gethostbyname` and its kin', 'gethostbyaddr', 'gethostbyname'),
    'getnameinfo': ('`socket.gethostbyname` and its kin', 'getnameinfo', 'gethostbyname'),
    'wider fixture': ('a fixture of wider scope has launched before the guard is active', 'wider scope',
                      'fixture of wider scope'),
    'other XDG variable': ('one the shell exported beside them (`XDG_STATE_HOME`, say) reaches the test unchanged',
                           'XDG_STATE_HOME', 'XDG_STATE_HOME'),
    'password database': ('the password database still names the real home', 'password database', None),
}


@pytest.mark.unit
def test_the_guard_sets_three_xdg_variables_and_leaves_the_rest(tmp_path: Path) -> None:
    assert os.environ.get('MARKER_F1_PROBE') == '1', 'run through remediation/checks.sh, which exports the sentinels'
    assert os.environ['HOME'] == str(tmp_path / 'home')
    for var in SET_BY_GUARD:
        assert Path(os.environ[var]).is_relative_to(tmp_path / 'home'), var
    for var in LEFT_ALONE:
        assert os.environ[var] == f'/nonexistent/marker-f1/{var}', var
    others = sorted(v for v in os.environ if v.startswith('XDG_') and v not in SET_BY_GUARD + LEFT_ALONE)
    assert all(not os.environ[v].startswith(str(tmp_path)) for v in others), others


@pytest.mark.unit
def test_every_open_route_is_named() -> None:
    assert set(guard_claims.OPEN) <= set(NAMED), sorted(set(guard_claims.OPEN) - set(NAMED))
    paragraph, gaps, entry = guard_paragraph(), flat(GAPS), roadmap_entry()
    unnamed = [(route, where) for route, words in NAMED.items()
               for where, text, phrase in zip(('§ Testing', 'marker-rule-gaps', 'ROADMAP'), (paragraph, gaps, entry), words)
               if phrase is not None and phrase not in text]
    assert unnamed == [], unnamed
    assert '`HOME` and `XDG_*` point' not in AGENTS, 'AGENTS.md still says every XDG variable points under tmp_path'
    assert ('`HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_DATA_HOME` point under `tmp_path`'
            in paragraph)


@pytest.mark.unit
def test_the_unit_description_qualifies_the_guard() -> None:
    markers = tomllib.loads(PYPROJECT)['tool']['pytest']['ini_options']['markers']
    described = dict(m.split(': ', 1) for m in markers)
    assert described['unit'].endswith('; ' + QUALIFIER), described['unit']
    assert described['unit'].count('holds it to that') == 1
    assert not re.search(r'enforce|holds it', described['integration']), described['integration']


@pytest.mark.unit
def test_the_commands_say_what_the_static_check_does_not_read() -> None:
    commands = AGENTS[AGENTS.index('\n## Commands\n'):AGENTS.index('\n## Repository map')]
    comments = flat(' '.join(line.split('#', 1)[1] for line in commands.splitlines() if '#' in line))
    assert ('the rule the suite enforces is per launch: every process an integration test launches goes '
            'through bin/sandbox.sh (§ Testing), and its static check does not read a launch through '
            'conftest.REAL_POPEN (issues/marker-rule-gaps.md).') in comments


@pytest.mark.unit
def test_the_check_is_described_as_it_refuses() -> None:
    testing = flat(section('## Testing'))
    assert 'a clause added anywhere' not in testing
    assert ("a clause added to a description all count, and the statement ends only where Markdown ends it: "
            "at the section's end, at a less indented list item, or at a blank line before text no deeper than "
            "its items that starts no item") in testing
