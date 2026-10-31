# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The deprecation window is one string, the published one, wherever a user reads it.

The server's old names (the `rcac-mcp` command, the `RCAC_*` variables, the `rcac://` URIs) are
deprecated in 0.2.0 and removed no earlier than 0.4.0. Every comparison here is with that window
written out (`harness.DEPRECATION_WINDOW`), never with `deprecation.WINDOW`, so changing the window
anywhere fails a test: the constant here, each warning in `test_cli.py` (the command) and
`test_env.py` (each variable, honoured or ignored), and README § Upgrading from rcac-mcp here.

The README's section is read from its source, as the text a reader sees: it holds no HTML comment
marker at all (a comment there either hides text from a reader or, in a code span or a fenced
block, is text a reader sees), and no HTML comment elsewhere may hide its heading. The section must
exist once. Every line in it holding a `|` is the table's header, its delimiter, or a two-cell row
with code spans in both cells, and those rows pair each deprecated name with exactly one
replacement, whatever their order, the pairs written out below. With markup removed (HTML tags,
entities, backslash escapes, `*` emphasis), each `RCAC_*` variable and each `rcac://` URI is named
once in the whole section, so a second mapping in a row of any form, a bullet or prose fails; the
`rcac-mcp` command is not counted, since the section also names the old project by it. With `_`
emphasis removed too, the window appears as the whole published phrase, ending where a token ends
(not "0.4.0-alpha", not "0.4.0.1"); every version the section names is one of the window's two
ends; and outside the window the section names no version but one `0.2.0`, the rename's. Every
window the README states is the published one.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Callable

import pytest

from harness import DEPRECATION_WINDOW
from cluster_mcp.core.deprecation import WINDOW

README = Path(__file__).resolve().parents[1] / 'README.md'

HEADING = '## Upgrading from rcac-mcp'

# Each deprecated name and its replacement, as the README's table must pair them: the command, each
# variable, each resource URI.
REPLACEMENTS = {
    'rcac-mcp': 'cluster-mcp',
    'RCAC_SSH_HOST': 'CLUSTER_MCP_SSH_HOST',
    'RCAC_USER_MAP': 'CLUSTER_MCP_USER_MAP',
    'RCAC_INSTRUCTIONS_BUDGET': 'CLUSTER_MCP_INSTRUCTIONS_BUDGET',
    'rcac://context': 'cluster://context',
    'rcac://storage': 'cluster://storage',
}

# The deprecated names the section names exactly once, in its table: every one but the command,
# which the section also uses as the old project's name.
NAMED_ONCE = tuple(name for name in REPLACEMENTS if name != 'rcac-mcp')

# The table's header line.
TABLE_HEADER = '| Deprecated | Replacement |'

# Where a window's end is stated: each such phrase must be part of the published window.
WINDOW_END = 'removed no earlier than'

# The window's two ends, the only versions the section may name; outside the window, only the
# rename's own release, once.
VERSIONS = ('0.2.0', '0.4.0')
RENAMED_IN = '0.2.0'

# A version as a reader reads one: dotted numbers and whatever runs on to the next space; trailing
# punctuation ends a sentence or a clause, not the version.
VERSION = re.compile(r'\d+(?:\.\d+)+\S*')
TRAILING = '.,;:!?)]}*_\'"`'

# The published window as a whole phrase: not run on from a word before it, and ended by a space or
# the text's end, after at most a clause's or a sentence's closing punctuation.
BOUNDED = re.compile(rf'(?<![\w.-]){re.escape(DEPRECATION_WINDOW)}(?=[.,;:!?)\]]*(?:\s|$))')

# An HTML comment, which Markdown does not render; one never closed hides the rest of the file.
COMMENT = re.compile(r'<!--.*?(?:-->|\Z)', re.DOTALL)
COMMENT_MARKERS = ('<!--', '-->')

# An HTML tag, which a reader sees only by its effect.
TAG = re.compile(r'</?[A-Za-z][^>]*>')


def rendered(text: str) -> str:
    """`text` with every HTML comment removed, an unclosed one hiding the rest.

    Used only to ask whether a comment hides the section's heading. It over-hides (a `<!--` in a code
    span opens no comment), so it can only make the check stricter: nothing else is read from it.
    """
    return COMMENT.sub('', text)


def plain(text: str, emphasis: str = '*') -> str:
    """`text` as the characters a reader sees: HTML tags dropped, entities decoded, backslash escapes and each `emphasis` character removed."""
    text = html.unescape(TAG.sub('', text))
    text = re.sub(r'\\(.)', r'\1', text)
    return text.translate({ord(c): None for c in emphasis})


def section(text: str) -> str | None:
    """The README's upgrade section, heading to the next level-2 heading, or None when absent."""
    start = text.find(f'\n{HEADING}\n')
    if start < 0:
        return None
    end = text.find('\n## ', start + 1)
    return text[start:] if end < 0 else text[start:end]


def table_line_violations(text: str) -> list[str]:
    """Every line of the section `text` holding a `|` that is not the header, the delimiter, or a two-cell row of code spans."""
    violations = []
    for line in text.splitlines():
        stripped = line.strip()
        if '|' not in stripped or stripped == TABLE_HEADER or (set(stripped) <= set('|-: ') and '-' in stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip('|').split('|')]
        if not (stripped.startswith('|') and stripped.endswith('|') and len(cells) == 2
                and all(re.search(r'`[^`]+`', cell) for cell in cells)):
            violations.append(f'a table line the pairing does not read (not a two-cell row of code spans): {stripped!r}')
    return violations


def table_pairs(text: str) -> tuple[dict[str, list[str]], list[str]]:
    """Every replacement the section's table rows give each deprecated name, and every row that pairs unevenly.

    A row's two cells each name one or more code spans; the n-th span of the first cell is replaced by
    the n-th of the second. A name some row repeats, or two rows name, has each replacement listed,
    in row order.
    """
    pairs: dict[str, list[str]] = {}
    uneven: list[str] = []
    for line in text.splitlines():
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if not line.lstrip().startswith('|') or len(cells) != 2 or set(cells[0]) <= set('-: '):
            continue
        old, new = (re.findall(r'`([^`]+)`', cell) for cell in cells)
        if len(old) != len(new):
            uneven.append(line.strip())
            continue
        for name, replacement in zip(old, new):
            pairs.setdefault(name, []).append(replacement)
    return pairs, uneven


def version_violations(text: str) -> list[str]:
    """Every way the section `text` (markup removed, whitespace normalised) names another version or window than the published one."""
    violations = []
    for found in VERSION.findall(text):
        version = found.rstrip(TRAILING)
        if version not in VERSIONS:
            violations.append(f'the {HEADING!r} section names the version {version!r}, not one of {VERSIONS}')
    if not BOUNDED.search(text):
        violations.append(f'the {HEADING!r} section does not state the published window')
    if len(BOUNDED.findall(text)) != text.count(DEPRECATION_WINDOW):
        violations.append(f'the {HEADING!r} section runs the published window on into another token')
    outside = [found.rstrip(TRAILING) for found in VERSION.findall(text.replace(DEPRECATION_WINDOW, ' '))]
    if outside not in ([], [RENAMED_IN]):
        violations.append(f'the {HEADING!r} section names {outside} outside the window, '
                          f'where only one {RENAMED_IN!r} (the rename) may appear')
    return violations


def upgrading_violations(text: str) -> list[str]:
    """Every way README text `text` misstates the deprecations or their window to a reader; empty means none."""
    violations = []
    flat = ' '.join(plain(text).split())
    if flat.count(DEPRECATION_WINDOW) == 0:
        violations.append(f'the README does not state the published window {DEPRECATION_WINDOW!r}')
    if flat.count(WINDOW_END) != flat.count(DEPRECATION_WINDOW):
        stated = re.findall(rf'(?:\S+ \S+ \S+, )?{WINDOW_END} \S+', flat)
        violations.append(f'the README states another window than the published one: {stated}')
    headings = text.count(f'\n{HEADING}\n')
    upgrading = section(text)
    if upgrading is None or section(rendered(text)) is None:
        hidden = '' if upgrading is None else ' a reader sees: an HTML comment hides its heading'
        violations.append(f'the README has no {HEADING!r} section{hidden}')
        return violations
    if headings != 1:
        violations.append(f'the README has {headings} {HEADING!r} sections, expected one')
    for marker in COMMENT_MARKERS:
        if marker in upgrading:
            violations.append(f'the {HEADING!r} section holds the HTML comment marker {marker!r}')
    violations += version_violations(' '.join(plain(upgrading, '*_').split()))
    violations += table_line_violations(upgrading)
    seen = plain(upgrading)
    for name in NAMED_ONCE:
        if seen.count(name) > 1:
            violations.append(f'the {HEADING!r} section names {name!r} {seen.count(name)} times, '
                              'expected once, in its table row')
    pairs, uneven = table_pairs(upgrading)
    violations += [f'a row pairs deprecated names and replacements unevenly: {row!r}' for row in uneven]
    for old, new in REPLACEMENTS.items():
        given = pairs.get(old, [])
        if not given:
            violations.append(f'the {HEADING!r} section does not list {old!r} as deprecated')
        elif len(given) > 1:
            violations.append(f'the {HEADING!r} section pairs {old!r} {len(given)} times ({", ".join(given)}), '
                              f'not once with {new!r}')
        elif given[0] != new:
            violations.append(f'the {HEADING!r} section gives {old!r} the replacement {given[0]!r}, not {new!r}')
    for old in sorted(set(pairs) - set(REPLACEMENTS)):
        violations.append(f'the {HEADING!r} section lists {old!r} as deprecated, which is not one of the deprecations')
    return violations


@pytest.mark.unit
def test_window_is_the_published_one() -> None:
    assert WINDOW == DEPRECATION_WINDOW, f'WINDOW is {WINDOW!r}, not the published window {DEPRECATION_WINDOW!r}'


@pytest.mark.unit
def test_readme_states_each_deprecation_and_the_window() -> None:
    violations = upgrading_violations(README.read_text())
    assert violations == [], '\n'.join(violations)


def _drop_row(name: str) -> Callable[[str], str]:
    def change(text: str) -> str:
        return '\n'.join(line for line in text.split('\n') if not (line.startswith('|') and f'`{name}`' in line))
    return change


def _drop_section(text: str) -> str:
    upgrading = section(text)
    assert upgrading is not None
    return text.replace(upgrading, '')


def _row(name: str, text: str) -> str:
    """The table row naming `name`, newline included."""
    rows = [line for line in text.split('\n') if line.startswith('|') and f'`{name}`' in line]
    assert len(rows) == 1, rows
    return rows[0] + '\n'


def _beside(name: str, row: str, before: bool) -> Callable[[str], str]:
    """`row` added to the table, just before or just after the row naming `name`."""
    def change(text: str) -> str:
        own = _row(name, text)
        return text.replace(own, row + own if before else own + row)
    return change


def _commented(text: str) -> str:
    """The upgrade section inside one HTML comment."""
    upgrading = section(text)
    assert upgrading is not None
    return text.replace(upgrading, f'\n<!--{upgrading}-->\n')


def _before_section(extra: str) -> Callable[[str], str]:
    """`extra`, a paragraph, at the end of the section before the upgrade section."""
    def change(text: str) -> str:
        upgrading = section(text)
        assert upgrading is not None
        return text.replace(upgrading, f'\n{extra}\n{upgrading}')
    return change


def _after_section(extra: str) -> Callable[[str], str]:
    """`extra` at the upgrade section's end, just before the next level-2 heading."""
    def change(text: str) -> str:
        upgrading = section(text)
        assert upgrading is not None
        return text.replace(upgrading, f'{upgrading}{extra}')
    return change


def _in_section(extra: str) -> Callable[[str], str]:
    """`extra`, a paragraph, at the end of the upgrade section."""
    return _after_section(f'\n{extra}\n')


# A row giving `RCAC_SSH_HOST` a replacement the server never reads, and the same pairing in each
# other form a reader sees as a table row.
CONTRADICTING = '| `RCAC_SSH_HOST` | `CLUSTER_SSH_HOST` |\n'
UNREAD_ROWS = {
    'plain': '| RCAC_SSH_HOST | CLUSTER_SSH_HOST |\n',
    'bold': '| **RCAC_SSH_HOST** | **CLUSTER_SSH_HOST** |\n',
    'escaped': '| RCAC\\_SSH\\_HOST | CLUSTER\\_SSH\\_HOST |\n',
    'html-code': '| <code>RCAC_SSH_HOST</code> | <code>CLUSTER_SSH_HOST</code> |\n',
    'three-cells': '| `RCAC_SSH_HOST` | `CLUSTER_SSH_HOST` | |\n',
    'no-leading-pipe': '`RCAC_SSH_HOST` | `CLUSTER_SSH_HOST`\n',
}

# The window sentence's own words, to plant a window or a version into.
WINDOWED = 'removed no earlier than 0.4.0, and keeps working until it is removed:'

# A contradicting window a reader sees: between a code span opening a comment and one closing it; in
# a fenced block; and between a comment's opening in one paragraph and its closing in the next.
COMMENT_EDGES = {
    'code-spans': 'An HTML comment opens with `<!--`. The old names will be removed in 0.3.0. A comment closes with `-->`.',
    'fenced': '```\n<!-- removed in 0.3.0 -->\n```',
    'across-paragraphs': 'Notes open with <!-- and\n\nthe old names will be removed in 0.3.0; notes close with -->.',
}

DRIFT = [
    pytest.param(lambda t: t.replace('removed no earlier than 0.4.0', 'removed no earlier than 0.3.0'),
                 'does not state the published window', id='window-altered'),
    pytest.param(lambda t: t.replace('removed no earlier than 0.4.0', 'removed no earlier than\n0.4.1'),
                 'does not state the published window', id='window-altered-across-lines'),
    pytest.param(_before_section('The old names are removed no earlier than 0.5.0.'),
                 'states another window than the published one', id='second-window'),
    pytest.param(_drop_section, 'has no', id='section-deleted'),
    pytest.param(lambda t: t.replace(HEADING, '## Upgrading'), 'has no', id='section-renamed'),
    pytest.param(_after_section(f'\n{HEADING}\n\nAgain.\n'), 'sections, expected one', id='section-twice'),
    pytest.param(_drop_row('rcac-mcp'), "does not list 'rcac-mcp'", id='command-row-dropped'),
    pytest.param(_drop_row('RCAC_SSH_HOST'), "does not list 'RCAC_USER_MAP'", id='variables-row-dropped'),
    pytest.param(_drop_row('rcac://context'), "does not list 'rcac://storage'", id='resources-row-dropped'),
    pytest.param(lambda t: t.replace('`CLUSTER_MCP_USER_MAP`, ', ''), 'unevenly', id='replacement-dropped'),
    pytest.param(lambda t: t.replace('| `cluster-mcp` |', '| `cluster` |'),
                 "gives 'rcac-mcp' the replacement 'cluster'", id='replacement-changed'),
    pytest.param(_beside('RCAC_USER_MAP', CONTRADICTING, before=True),
                 "pairs 'RCAC_SSH_HOST' 2 times (CLUSTER_SSH_HOST, CLUSTER_MCP_SSH_HOST)", id='contradicting-row-before'),
    pytest.param(_beside('RCAC_USER_MAP', CONTRADICTING, before=False),
                 "pairs 'RCAC_SSH_HOST' 2 times (CLUSTER_MCP_SSH_HOST, CLUSTER_SSH_HOST)", id='contradicting-row-after'),
    pytest.param(lambda t: _beside('rcac-mcp', _row('rcac-mcp', t), before=False)(t),
                 "pairs 'rcac-mcp' 2 times", id='row-repeated'),
    pytest.param(_beside('rcac-mcp', '| `RCAC_SSH_KEY` | `CLUSTER_MCP_SSH_KEY` |\n', before=False),
                 "lists 'RCAC_SSH_KEY' as deprecated, which is not one", id='row-added'),
    *(pytest.param(_beside('RCAC_USER_MAP', row, before=before), 'a table line the pairing does not read',
                   id=f'{form}-row-{"before" if before else "after"}')
      for form, row in UNREAD_ROWS.items() for before in (True, False)),
    pytest.param(_in_section('- `RCAC_SSH_HOST` is now `CLUSTER_SSH_HOST`.'),
                 "names 'RCAC_SSH_HOST' 2 times", id='bullet-mapping'),
    pytest.param(_in_section('Set `CLUSTER_SSH_HOST` in place of `RCAC_SSH_HOST`.'),
                 "names 'RCAC_SSH_HOST' 2 times", id='prose-mapping'),
    pytest.param(_in_section('Read **rcac://storage** for your storage.'),
                 "names 'rcac://storage' 2 times", id='bold-mapping'),
    pytest.param(lambda t: t.replace(WINDOWED, f'{WINDOWED} the old names will be removed in 0.3.0.'),
                 "names the version '0.3.0'", id='second-window-removed-in'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('until it is removed', 'until 0.3.0')),
                 "names the version '0.3.0'", id='second-window-until'),
    pytest.param(lambda t: t.replace(WINDOWED, f'{WINDOWED} the command goes in 0.3.'),
                 "names the version '0.3'", id='second-window-two-components'),
    pytest.param(_in_section('The old names will be removed in 0\\.3\\.0.'),
                 "names the version '0.3.0'", id='version-escaped-dots'),
    pytest.param(_in_section('The old names will be removed in 0&#46;3&#46;0.'),
                 "names the version '0.3.0'", id='version-entity-dots'),
    pytest.param(_in_section('The old names will be removed in 0.**3**.0.'),
                 "names the version '0.3.0'", id='version-bold-component'),
    pytest.param(_in_section('The old names will be removed in 0._3_.0.'),
                 "names the version '0.3.0'", id='version-underscore-component'),
    pytest.param(_in_section('The old names will be removed in 0.<b>3</b>.0.'),
                 "names the version '0.3.0'", id='version-tagged-component'),
    pytest.param(_in_section('The `rcac-mcp` command is removed in 0.2.0.'),
                 "names ['0.2.0', '0.2.0'] outside the window", id='removed-in-the-rename'),
    pytest.param(_in_section('The old names are removed in 0.4.0.'),
                 "names ['0.2.0', '0.4.0'] outside the window", id='removed-at-the-window-end'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('0.4.0,', '0.4.0-alpha,')),
                 "names the version '0.4.0-alpha'", id='window-suffixed'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('0.4.0,', '0.4.0-alpha,')),
                 'runs the published window on', id='window-suffixed-unbounded'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('0.4.0,', '0.4.0.1,')),
                 "names the version '0.4.0.1'", id='window-extra-component'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('0.4.0,', '0.4.0 (0.3.0 for the command),')),
                 "names the version '0.3.0'", id='window-parenthetical'),
    pytest.param(lambda t: t.replace('\ndeprecated in 0.2.0, removed', '\nundeprecated in 0.2.0, removed'),
                 'does not state the published window', id='window-run-on-before'),
    pytest.param(_commented, "has no '## Upgrading from rcac-mcp' section", id='section-commented'),
    pytest.param(lambda t: t.replace(HEADING, f'<!--\n{HEADING}'),
                 "has no '## Upgrading from rcac-mcp' section", id='section-commented-unclosed'),
    pytest.param(lambda t: t.replace(_row('rcac-mcp', t), f'<!-- {_row("rcac-mcp", t).rstrip()} -->\n'),
                 "does not list 'rcac-mcp'", id='row-commented'),
    pytest.param(lambda t: t.replace(WINDOWED, f'{WINDOWED} <!-- removed in 0.3.0 -->'),
                 "holds the HTML comment marker '<!--'", id='hidden-comment'),
    *(pytest.param(_in_section(edge), 'holds the HTML comment marker', id=f'comment-{name}')
      for name, edge in COMMENT_EDGES.items()),
]

# The README as it is, and ending in a comment never closed, which hides nothing in the section:
# every drift control holds on both, so none depends on what follows the section.
TAILS = [pytest.param('', id='readme'), pytest.param('\n<!--\n', id='readme-unclosed-comment-at-the-end')]


@pytest.mark.unit
@pytest.mark.parametrize('tail', TAILS)
@pytest.mark.parametrize(('change', 'fragment'), DRIFT)
def test_upgrading_check_catches_drift(change: Callable[[str], str], fragment: str, tail: str) -> None:
    text = README.read_text() + tail
    assert upgrading_violations(text) == []
    planted = change(text)
    assert planted != text, 'the planted change did not land'
    violations = upgrading_violations(planted)
    assert any(fragment in v for v in violations), violations


@pytest.mark.unit
@pytest.mark.parametrize('change', [
    pytest.param(lambda t: t.replace(_row('rcac-mcp', t), '').replace(
        _row('rcac://context', t), _row('rcac://context', t) + _row('rcac-mcp', t)), id='rows-reordered'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('0.4.0, and keeps working until it is removed:',
                                                                '0.4.0. Each keeps working until it is removed:')),
                 id='window-ends-a-sentence'),
    pytest.param(lambda t: t.replace(WINDOWED, WINDOWED.replace('removed no earlier than 0.4.0,',
                                                                'removed no earlier than\n0.4.0,')), id='window-rewrapped'),
    pytest.param(lambda t: t.replace('\ndeprecated in 0.2.0, removed no earlier than 0.4.0,',
                                     '\n**deprecated in 0.2.0, removed no earlier than 0.4.0**,'), id='window-emphasised'),
    pytest.param(_before_section('A note. <!-- removed in 0.3.0 -->'), id='comment-before-the-section'),
    pytest.param(lambda t: t + '\n<!--\nThe old names will be removed in 0.3.0.\n', id='unclosed-comment-at-the-end'),
])
def test_upgrading_check_reads_as_a_reader_does(change: Callable[[str], str]) -> None:
    # What a reader sees unchanged passes: the rows' order, the window ending a sentence, broken across
    # lines or emphasised, and a comment outside the section. A comment inside the section fails
    # (`hidden-comment` above), even one a reader would not see: the check reads the section's source.
    text = README.read_text()
    planted = change(text)
    assert planted != text, 'the planted change did not land'
    assert upgrading_violations(planted) == []
