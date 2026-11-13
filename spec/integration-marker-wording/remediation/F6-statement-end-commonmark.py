"""Review cycle 2, finding 2: the marker-statement check ends the statement where CommonMark ends the
last list item, for every whitespace form a line can start with. Extended for review cycle 3,
finding 1: at the boundary, the check and the parser agree both ways.

The predicate is evaluated, not listed: a CommonMark parser (markdown-it-py, in the lock through the
dev stack) renders each planted AGENTS.md, and the statement's list is compared with the list as
planted. Whenever the parser renders a line after the statement inside the last item, or as a further
item of the list, the check must refuse the pair. The domain is every prefix in PREFIXES before every
line in CONTENTS, directly after the last item or after a blank line, with the statement at the top
level of a bullet and one bullet deeper (2,400 cases), plus the same forms injected after the
`integration` item of the staged AGENTS.md § Testing. The rows of
`test_marker_statement_ends_where_markdown_ends_it` are held to the parser too: each row the test
expects refused is one the parser changes, and each row it expects accepted is one the parser leaves
alone and the check accepts.

The boundary (review cycle 3, finding 1) is held both ways: for text that starts no item and for a
`-` item, after each blank-line form in BLANKS or directly after the last item, behind every run of
spaces and tabs up to six characters long (columns 0 to 24, so every column from the items' indent to
past their text column, in every order of spaces and tabs that reaches it), at the top level and one
bullet deeper, the check refuses exactly the cases the parser renders into the statement. Block
starters other than `-` are left out of that domain: the check refuses some that CommonMark places
after the list, a known refusal of shapes no file uses that lets no drift through.

Run from the worktree root, after staging, through remediation/checks.sh (or alone):

    uv run --no-sync python -I spec/integration-marker-wording/remediation/F6-statement-end-commonmark.py

Reads the check, its planted pair and the rows from the index (`git show :tests/test_hygiene.py`)
and runs them in this process. Prints a count per verdict and every case the check passes that the
parser changes, and every boundary case where the two disagree; exits 1 on any. One process, git
children only; under 150 MB; about 10 s.
"""
from __future__ import annotations

import functools
import itertools
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from markdown_it import MarkdownIt

START = "# The markers' meaning, as AGENTS.md"
STOP = '\n# Every name of the SSH-host and user-map variables bin/sandbox.sh must unset'
ENDS = 'test_marker_statement_ends_where_markdown_ends_it'


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


SOURCE = staged('tests/test_hygiene.py')
NS: dict = {'functools': functools, 're': re, 'tomllib': tomllib, 'pytest': pytest, 'Path': Path}
exec(compile(SOURCE[SOURCE.index(START):SOURCE.index(STOP)], 'test_hygiene.py', 'exec'), NS)
CHECK, ENDED, STATED = NS['marker_statement_violations'], NS['ended'], NS['MARKERS_STATED']
MD = MarkdownIt('commonmark')

PREFIXES = ['', ' ', '  ', '   ', '    ', '     ', '      ', '\t', ' \t', '  \t', '   \t', '\t ', '\t\t',
            '\xa0', '\xa0\xa0', ' \xa0', '  \xa0', '\xa0 ', ' ', '　', ' ', '​', '\x0b',
            '\x0c', '﻿']
CONTENTS = ['except a gate', '- except a gate', '- `beta`: a third', '* except a gate', '+ except a gate',
            '1. except a gate', '2. except a gate', '3) except a gate', '123456789. except a gate',
            '1234567890. except a gate', '-', '- ', '-except a gate', '-\texcept a gate', '-\xa0except a gate',
            '2 except a gate', '> except a gate', '# except a gate', '```', '---', '***',
            '<!-- except a gate -->', '| except | a gate |', '', '\n    except a gate', '\n  - `beta`: a third']
BLANKS = ['', '  ', '\t', ' \t ']
LEADS = [''.join(run) for size in range(7) for run in itertools.product(' \t', repeat=size)]
EDGE = ['except a gate', '- except a gate', '- `beta`: a third']


def statement_list(markdown: str, heading: str) -> list[str] | None:
    """The list after the statement line in the section under `heading`, as CommonMark parses it: one
    entry per item, each the item's blocks and raw inline text; None when no list follows the line."""
    section = NS['agents_section'](markdown, heading)
    tokens = MD.parse(section)
    for n, token in enumerate(tokens):
        if token.type == 'inline' and token.content.split('\n')[-1].strip() == STATED:
            break
    else:
        return None
    start = n + 2  # past the paragraph's close
    if start >= len(tokens) or tokens[start].type != 'bullet_list_open':
        return None
    level, items, depth = tokens[start].level, [], 0
    for token in tokens[start + 1:]:
        if token.type == 'bullet_list_close' and token.level == level:
            break
        if token.type == 'list_item_open' and token.level == level + 1:
            items.append('')
        elif token.type == 'inline':
            items[-1] += f'[{token.content}]'
        elif not token.type.startswith(('paragraph', 'list_item')) or token.level > level + 2:
            items[-1] += f'<{token.type}:{token.content}>'
    return items


def changed(toml: str, agents: str, base: str, heading: str = '## Testing') -> bool:
    return statement_list(agents, heading) != statement_list(base, heading)


def main() -> int:
    bad: list[str] = []
    counts = {'parser changes it, check refuses': 0, 'parser leaves it, check accepts': 0,
              'parser leaves it, check refuses': 0}
    for nested in (False, True):
        base = ENDED('', nested)[1]
        assert statement_list(base, '## Testing') and CHECK(*ENDED('', nested)) == [], 'the planted pair'
        for blank in (False, True):
            for prefix in PREFIXES:
                for content in CONTENTS:
                    after = ('\n' if blank else '') + prefix + content + '\n'
                    toml, agents = ENDED(after, nested)
                    refused, moved = CHECK(toml, agents) != [], changed(toml, agents, base)
                    if moved and not refused:
                        bad.append(f'nested={nested} after={after!r}: rendered into the statement, check passes')
                    else:
                        counts[{(True, True): 'parser changes it, check refuses',
                                (False, False): 'parser leaves it, check accepts',
                                (False, True): 'parser leaves it, check refuses'}[(moved, refused)]] += 1
    edge = {'parser changes it, check refuses': 0, 'parser leaves it, check accepts': 0}
    for nested in (False, True):
        base = ENDED('', nested)[1]
        for blank in [None, *BLANKS]:
            for lead in LEADS:
                for content in EDGE:
                    after = ('' if blank is None else blank + '\n') + lead + content + '\n'
                    toml, agents = ENDED(after, nested)
                    refused, moved = CHECK(toml, agents) != [], changed(toml, agents, base)
                    if moved != refused:
                        bad.append(f'boundary, nested={nested} after={after!r}: the parser '
                                   f'{"changes" if moved else "leaves"} the list, the check '
                                   f'{"refuses" if refused else "accepts"}')
                    else:
                        edge['parser changes it, check refuses' if moved else 'parser leaves it, check accepts'] += 1
    rows = [(p.id, p.values) for m in NS[ENDS].pytestmark if m.name == 'parametrize' for p in m.args[1]]
    if not rows:
        bad.append(f'{ENDS} has no rows')
    for rid, (after, nested, refused) in rows:
        toml, agents = ENDED(after, nested)
        moved, verdict = changed(toml, agents, ENDED('', nested)[1]), CHECK(toml, agents) != []
        if moved != refused or verdict != refused:
            bad.append(f'row {rid}: expects refused={refused}; the parser changes the list: {moved}; '
                       f'the check refuses: {verdict}')
    pyproject, agents = staged('pyproject.toml'), staged('AGENTS.md')
    anchor = '    goes through bin/sandbox.sh\n'
    first = agents.index(anchor, agents.index('\n## Testing\n')) + len(anchor)
    real = 0
    for blank in (False, True):
        for prefix in PREFIXES:
            for content in ('except a test that needs nothing', '- except a test that needs nothing',
                            '- `beta`: a third', '1234567890. except a test that needs nothing'):
                variant = agents[:first] + ('\n' if blank else '') + prefix + content + '\n' + agents[first:]
                if changed(pyproject, variant, agents) and CHECK(pyproject, variant) == []:
                    bad.append(f'staged AGENTS.md, after {("blank, " if blank else "") + prefix + content!r}: '
                               'rendered into the integration item, check passes')
                real += 1
    print(f'{sum(counts.values())} planted cases: ' + '; '.join(f'{k} {v}' for k, v in counts.items())
          + f'; {len(rows)} rows of {ENDS}; {real} cases on the staged AGENTS.md')
    print(f'{sum(edge.values())} boundary cases, held both ways: ' + '; '.join(f'{k} {v}' for k, v in edge.items()))
    for line in bad:
        print(line)
    print(f'F6: {"ok" if not bad else f"{len(bad)} failed"}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
