"""Review cycle 2, finding 4: the mutant sweep of the marker-statement check, after the comparison was
pinned over its whole domain (`test_marker_statement_check_refuses_every_edit`).

It supersedes cycle 1's `F2-marker-check-sweep.py`, which stays as the record: that sweep keyed on
lines this round rewrote (where the statement ends, now counted in Markdown's columns), so its table
no longer applies. This one carries that table, re-keyed, the review's own sweep (decisions, single
characters, folds, clause forms, pairwise and list carve-outs), and mutants of the code this round
added (Markdown's columns, its blank line, a tab after a wrap's indent, CommonMark's list markers).

Run from the worktree root, after staging, through remediation/checks.sh (or alone):

    uv run --no-sync python -I spec/integration-marker-wording/remediation/F8-marker-check-sweep.py

The check and its tests are read from the index and run in this process, one namespace per mutant,
each mutant under a 60 s alarm. A mutant is killed when a planted row gives the wrong verdict or
raises (the accept rows, the planted and narrower drift rows, the rows of
`test_marker_statement_ends_where_markdown_ends_it`), when the whole-domain control fails, or when
the live check refuses the staged pyproject.toml and AGENTS.md. A mutant in NAMED must be killed by
every row it names. A survivor must be listed in EQUIVALENT (with the reason it can pass no drift the
check refuses) or in SEEDED (a deeper layer of a class a row or the control already pins, filed in
`issues/marker-statement-deeper-carve-outs.md`); a listed mutant that is killed is a stale listing.
Prints one line a mutant and exits 1 on an unlisted survivor, a stale listing, a timeout, a NAMED row
that passes, or a substitution that does not apply exactly once.

Method: tier 3a, the cycle's diff, one process (no workers); under 200 MB; about 4 minutes, most of
it the control (about 1 s a mutant).
"""
from __future__ import annotations

import functools
import re
import signal
import string
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

START = "# The markers' meaning, as AGENTS.md"
TESTS = '@pytest.mark.unit\ndef test_the_markers_are_stated_as_pyproject_describes_them'
STOP = '\n# Every name of the SSH-host and user-map variables bin/sandbox.sh must unset'
ACCEPTS = 'test_marker_statement_check_accepts_a_rewrapped_statement'
ROWS = 'test_marker_statement_check_catches_planted_drift'
NARROW = 'test_marker_statement_check_catches_narrower_drift'
ENDS = 'test_marker_statement_ends_where_markdown_ends_it'
CONTROL = 'test_marker_statement_check_refuses_every_edit'


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


SOURCE = staged('tests/test_hygiene.py')
BLOCK = SOURCE[SOURCE.index(START):SOURCE.index(STOP)]
CHECK, REST = BLOCK[:BLOCK.index(TESTS)], BLOCK[BLOCK.index(TESTS):]
REAL = (staged('pyproject.toml'), staged('AGENTS.md'))

COMPARE_OLD = """        for n in range(max(len(stated), len(described))):
            said = stated[n] if n < len(stated) else None
            meant = described[n] if n < len(described) else None
            if said != meant:"""
COMPARE_NEW = """        _s, _d = _carve(list(stated), list(described))
        for n in range(max(len(_s), len(_d))):
            said = _s[n] if n < len(_s) else None
            meant = _d[n] if n < len(_d) else None
            if _cmp(said) != _cmp(meant):"""
HOOKS = 'def _carve(s, d):\n    return s, d\n\n\ndef _cmp(x):\n    return x\n\n\n'
CMP_OLD = '            if said != meant:\n'
END_BLANK = 'if depth < len(indent) or (depth == len(indent) and not LIST_ITEM.match(text)):'
END_NEXT = '    if depth < len(indent) and LIST_ITEM.match(text):'
LIST_OLD = "LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]{1,9}[.)])(?:[ \\t]|$)')"
CONT = ("        elif items and line.startswith(indent + '  ') and line[len(indent) + 2:][:1] not in ('', ' '):\n"
        "            items[-1][1] += ' ' + line[len(indent) + 2:]\n")
STATEMENT = "line.lstrip(' ') == MARKERS_STATED"

# name: (kind, [(old, new), ...], extra hook code). A kind starting `carve` hooks the comparison.
MUTANTS: dict[str, tuple[str, list[tuple[str, str]], str]] = {}


def text(name: str, old: str, new: str) -> None:
    MUTANTS[name] = ('decision', [(old, new)], '')


def texts(name: str, *subs: tuple[str, str]) -> None:
    MUTANTS[name] = ('decision', list(subs), '')


def carve(name: str, code: str) -> None:
    MUTANTS[name] = ('carve', [(COMPARE_OLD, COMPARE_NEW)], code)


def fold(name: str, body: str, names: bool = False) -> None:
    """Compare after `body` (an expression in `t`) rewrites each description, and each name if `names`."""
    carve(name, f'def _cmp(x):\n    f = lambda t: {body}\n'
                f'    return None if x is None else ({"f(x[0])" if names else "x[0]"}, f(x[1]))\n')


# --- described_markers
text('dm-split-colon', "entry.split(': ', 1)[0], entry.split(': ', 1)[1]) if ': ' in entry",
     "entry.split(':', 1)[0], entry.split(':', 1)[1]) if ':' in entry")
text('dm-split-nomax', "(entry.split(': ', 1)[0], entry.split(': ', 1)[1])", "(entry.split(': ')[0], entry.split(': ')[1])")
text('dm-split-strip', "entry.split(': ', 1)[1])", "entry.split(': ', 1)[1].strip())")
text('dm-split-colon-strip', "(entry.split(': ', 1)[0], entry.split(': ', 1)[1]) if ': ' in entry else (entry, '')",
     "(entry.split(':', 1)[0].strip(), entry.split(':', 1)[1].strip()) if ':' in entry else (entry, '')")
text('dm-else-entry-entry', "else (entry, '') for entry", "else (entry, entry) for entry")
text('dm-no-markers', ".get('markers', [])", ".get('markers', [])[:0]")
text('dm-first-only', ".get('markers', [])\n", ".get('markers', [])[:1]\n")
text('dm-dedupe', ".get('markers', [])\n", ".get('markers', [])\n    entries = list(dict.fromkeys(entries))\n")
text('dm-sorted', ".get('markers', [])\n", ".get('markers', [])\n    entries = sorted(entries)\n")
# --- stated_markers: the statement line
text('sm-strip-all', STATEMENT, "line.strip() == MARKERS_STATED")
text('sm-lstrip-ws', STATEMENT, "line.lstrip() == MARKERS_STATED")
text('sm-rstrip', STATEMENT, "line.lstrip(' ').rstrip() == MARKERS_STATED")
text('sm-contains', STATEMENT, "MARKERS_STATED in line")
text('sm-startswith', STATEMENT, "line.lstrip(' ').startswith(MARKERS_STATED[:40])")
text('sm-casefold', STATEMENT, "line.lstrip(' ').casefold() == MARKERS_STATED.casefold()")
text('sm-endswith', STATEMENT, "line.endswith(MARKERS_STATED)")
text('sm-blockquote', STATEMENT, "line.lstrip(' >') == MARKERS_STATED")
texts('sm-strip-and-indent', (STATEMENT, 'line.strip() == MARKERS_STATED'),
      ("indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))",
       "indent = ' ' * (len(lines[at[0]]) - len(lines[at[0]].lstrip()))"))
text('sm-count-lt1', "if len(at) != 1:", "if len(at) < 1:")
texts('sm-count-last', ("if len(at) != 1:", "if len(at) < 1:"),
      ("    indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))",
       "    at = [at[-1]]\n    indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))"))
text('sm-indent-fixed2', "indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))", "indent = '  '")
text('sm-indent-zero', "indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))", "indent = ''")
# --- stated_markers: an item
texts('sm-item-any-indent', ("if line.startswith(indent + '- '):", "if line.lstrip(' ').startswith('- '):"),
      ('item = MARKER_ITEM.fullmatch(line[len(indent):])', "item = MARKER_ITEM.fullmatch(line.lstrip(' '))"))
texts('sm-item-star', ("if line.startswith(indent + '- '):", "if line.startswith((indent + '- ', indent + '* ', indent + '+ ')):"),
      ('item = MARKER_ITEM.fullmatch(line[len(indent):])', "item = MARKER_ITEM.fullmatch('- ' + line[len(indent) + 2:])"))
text('sm-notitem-continue', "                return [], [f'not a `- `<name>`: <description>` item: {line.strip()!r}']",
     "                continue")
text('sm-notitem-break', "                return [], [f'not a `- `<name>`: <description>` item: {line.strip()!r}']",
     "                end = n\n                break")
text('sm-notitem-keep-items', "                return [], [f'not a `- `<name>`: <description>` item: {line.strip()!r}']",
     "                return [(a, b) for a, b in items], []")
text('re-item-nobackticks', "MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')", "MARKER_ITEM = re.compile(r'- `?([^`:]*)`?: (.*)')")
text('re-item-ws-after-colon', "MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')", r"MARKER_ITEM = re.compile(r'- `([^`]*)`:\s*(.*)')")
text('re-item-name-strip', "MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')", r"MARKER_ITEM = re.compile(r'- `\s*([^`]*?)\s*`: (.*)')")
text('re-item-trailing-strip', "MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')", r"MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*?)\s*')")
text('re-item-search', 'item = MARKER_ITEM.fullmatch(line[len(indent):])', 'item = MARKER_ITEM.match(line[len(indent):])')
text('re-item-name-casefold', 'items.append([item[1], item[2]])', 'items.append([item[1].lower(), item[2]])')
text('sm-item-rstrip', 'items.append([item[1], item[2]])', 'items.append([item[1], item[2].rstrip()])')
text('sm-item-name-strip', 'items.append([item[1], item[2]])', 'items.append([item[1].strip(), item[2]])')
# --- stated_markers: a wrap
text('sm-tab-wrap-branch-dropped', "        elif line.startswith(indent + '  \\t'):\n            end = n\n            break\n", '')
text('sm-cont-no-items-guard', "elif items and line.startswith(indent + '  ')", "elif line.startswith(indent + '  ')")
text('sm-cont-any-deeper', CONT, "        elif items and line.startswith(indent + '  ') and line.strip():\n"
                                 "            items[-1][1] += ' ' + line.strip()\n")
text('sm-cont-allow-space', "line[len(indent) + 2:][:1] not in ('', ' ')", "line[len(indent) + 2:][:1] not in ('',)")
text('sm-cont-allow-empty', "line[len(indent) + 2:][:1] not in ('', ' ')", "line[len(indent) + 2:][:1] not in (' ',)")
text('sm-cont-lazy', CONT, "        elif items and line.strip() and not line.lstrip().startswith(('- ', '* ', '+ ')):\n"
                           "            items[-1][1] += ' ' + line.strip()\n")
text('sm-cont-tab', CONT, "        elif items and line.expandtabs(4).startswith(indent + '  ') and line.expandtabs(4)[len(indent) + 2:][:1] not in ('', ' '):\n"
                          "            items[-1][1] += ' ' + line.expandtabs(4)[len(indent) + 2:]\n")
text('sm-cont-tab-indent', CONT, "        elif items and line[:1] in (' ', '\\t') and line.strip() and not line.lstrip().startswith('- '):\n"
                                 "            items[-1][1] += ' ' + line.lstrip()\n")
text('sm-cont-rstrip', "items[-1][1] += ' ' + line[len(indent) + 2:]", "items[-1][1] = items[-1][1].rstrip() + ' ' + line[len(indent) + 2:]")
text('sm-cont-no-space', "items[-1][1] += ' ' + line[len(indent) + 2:]", "items[-1][1] += line[len(indent) + 2:]")
text('sm-cont-strip-markup', "items[-1][1] += ' ' + line[len(indent) + 2:]",
     "items[-1][1] += ' ' + line[len(indent) + 2:].replace('`', '').replace('*', '')")
text('sm-lazy-wrap-joins', '        else:\n            end = n\n            break\n',
     "        elif items and line.strip() and markdown_indent(line)[0] < len(indent) + 2 and not LIST_ITEM.match(line.lstrip()):\n"
     "            items[-1][1] += ' ' + line.strip()\n        else:\n            end = n\n            break\n")
text('sm-else-continue', '        else:\n            end = n\n            break\n', '        else:\n            continue\n')
text('sm-end-none', '    return [(name, text) for name, text in items], statement_end_problems(rest[end:], indent)',
     '    return [(name, text) for name, text in items], []')
# --- markdown_indent
text('mi-tab-one-column', "            column += 4 - column % 4\n", "            column += 1\n")
text('mi-tab-four-columns', "            column += 4 - column % 4\n", "            column += 4\n")
text('mi-tab-eight-stop', "            column += 4 - column % 4\n", "            column += 8 - column % 8\n")
text('mi-tab-two-stop', "            column += 4 - column % 4\n", "            column += 2 - column % 2\n")
text('mi-any-space-indents', "        if char == ' ':\n", "        if char.isspace() and char != '\\t':\n")
text('mi-nbsp-indents', "        if char == ' ':\n", "        if char in ' \\u00a0':\n")
text('mi-python-lstrip', '    column = 0\n    for n, char in enumerate(line):\n',
     '    return len(line) - len(line.lstrip()), line.lstrip()\n    column = 0\n    for n, char in enumerate(line):\n')
# --- statement_end_problems
text('se-whitespace-line-is-blank', "    if after and after[0].strip(' \\t') and not after[0].strip():\n", '    if False:\n')
text('se-following-any-whitespace', "following = next((line for line in after if line.strip(' \\t')), None)",
     'following = next((line for line in after if line.strip()), None)')
text('se-blank-not-special', '    if not after or not after[0].strip():', '    if not after:')
text('se-blank-ends', '    if not after or not after[0].strip():\n', '    if not after or not after[0].strip():\n        return []\n')
text('se-blank-following-none', '        if following is None:\n            return []', "        if following is None:\n            return ['x']")
text('se-blank-lte', END_BLANK, 'if depth <= len(indent):')
text('se-blank-any', END_BLANK, 'if True:')
text('se-blank-lt-only', END_BLANK, 'if depth < len(indent):')
text('se-blank-lt-needs-nonitem', END_BLANK,
     'if (depth < len(indent) and not LIST_ITEM.match(text)) or (depth == len(indent) and not LIST_ITEM.match(text)):')
text('se-blank-content-col', END_BLANK,
     'if depth < len(indent) + 2 and not (depth == len(indent) and LIST_ITEM.match(text)):')
text('se-blank-same-depth-item-ok', END_BLANK, 'if depth <= len(indent):')
text('se-nb-lte', END_NEXT, '    if depth <= len(indent) and LIST_ITEM.match(text):')
text('se-nb-depth-only', END_NEXT, '    if depth < len(indent):')
text('se-nb-item-only', END_NEXT, '    if LIST_ITEM.match(text):')
text('se-nb-always', END_NEXT, '    if True:')
text('se-nb-any-nonblank-shallower', END_NEXT, "    if depth < len(indent) and text[:1] in '-*+0123456789#>`|':")
text('se-nb-other-bullet-same-depth', END_NEXT,
     "    if LIST_ITEM.match(text) and (depth < len(indent) or (depth == len(indent) and not text.startswith('- '))):")
# --- LIST_ITEM: CommonMark's list markers
text('re-list-no-space', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]{1,9}[.)])')")
text('re-list-digits-no-delim', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]{1,9}[.)]?)(?:[ \\t]|$)')")
text('re-list-ws', LIST_OLD, r"LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]{1,9}[.)])(?:\s|$)')")
text('re-list-space-only', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]{1,9}[.)])(?: |$)')")
text('re-list-any-digits', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]+[.)])(?:[ \\t]|$)')")
text('re-list-eight-digits', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]{1,8}[.)])(?:[ \\t]|$)')")
text('re-list-only-dash', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-]|[0-9]{1,9}[.)])(?:[ \\t]|$)')")
text('re-list-no-ordered', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+])(?:[ \\t]|$)')")
text('re-list-any', LIST_OLD, "LIST_ITEM = re.compile(r'')")
text('re-list-hash', LIST_OLD, "LIST_ITEM = re.compile(r'(?:[-*+#]|[0-9]{1,9}[.)])(?:[ \\t]|$)')")
# --- agents_section
text('as-same-level-only', 'for n in range(1, len(level) + 1)]', 'for n in range(len(level), len(level) + 1)]')
text('as-higher-only', 'for n in range(1, len(level) + 1)]', 'for n in range(1, len(level))]')
text('as-whole-file', '    return agents[start:min([e for e in ends if e != -1], default=len(agents))]', '    return agents[start:]')
text('as-from-top', '    return agents[start:min([e for e in ends if e != -1], default=len(agents))]',
     '    return agents[:min([e for e in ends if e != -1], default=len(agents))]')
# --- marker_statement_violations
text('mv-no-empty-check', "    violations = [] if described else ['pyproject.toml describes no markers']", '    violations = []')
text('mv-no-markers-returns-empty', "    violations = [] if described else ['pyproject.toml describes no markers']\n",
     "    if not described:\n        return []\n    violations = []\n")
text('mv-testing-only', "for where, heading in (('§ Testing', '## Testing'), ('§ Conventions', '### Conventions (same-commit rules)')):",
     "for where, heading in (('§ Testing', '## Testing'),):")
text('mv-conventions-only', "for where, heading in (('§ Testing', '## Testing'), ('§ Conventions', '### Conventions (same-commit rules)')):",
     "for where, heading in (('§ Conventions', '### Conventions (same-commit rules)'),):")
text('mv-drop-problems', "        violations += [f'{where}: {problem}' for problem in problems]", '        pass')
text('mv-min-len', 'for n in range(max(len(stated), len(described))):', 'for n in range(min(len(stated), len(described))):')
text('mv-described-count', 'for n in range(max(len(stated), len(described))):', 'for n in range(len(described)):')
text('mv-stated-count', 'for n in range(max(len(stated), len(described))):', 'for n in range(len(stated)):')
text('mv-first-only', 'for n in range(max(len(stated), len(described))):', 'for n in range(min(1, max(len(stated), len(described)))):')
text('mv-names-only', CMP_OLD, '            if (said or (None,))[0] != (meant or (None,))[0]:\n')
text('mv-texts-only', CMP_OLD, '            if (said or (None, None))[1] != (meant or (None, None))[1]:\n')
text('mv-always-equal', CMP_OLD, '            if False:\n')

# --- carve-outs on the comparison: case, every single character, folds, Unicode forms, markup
fold('cmp-casefold', 't.casefold()')
fold('cmp-casefold-names-too', 't.casefold()', names=True)
carve('cmp-name-casefold', 'def _cmp(x):\n    return None if x is None else (x[0].casefold(), x[1])\n')
carve('cmp-desc-only', 'def _cmp(x):\n    return None if x is None else x[1]\n')
carve('cmp-name-only', 'def _cmp(x):\n    return None if x is None else x[0]\n')
fold('cmp-all-punct', "t.translate(str.maketrans('', '', " + repr(string.punctuation + '’‘“”—–§«»…') + '))')
fold('cmp-word-chars-only', r"re.sub(r'[^\w\s]', '', t)")
for chars in [',', ';', ':', '.', '(', ')', '()', '/', '-', "'", '"', '’', '‘', '“', '”', "'’‘", '"“”', "'\"’‘“”", '`', '*',
              '_', '*_', '!', '?', '[', ']', '[]', '§', '&', '—', '–', '-—–', '<', '>', '#', '=', '+', '@', '~', '|',
              '\\', '{}', '$', '%', '^', '\u00ad', '\u200b', '\u200d', '\ufeff', '\u00a0', '\t', '\u2009', '…', '«»', '·']:
    fold(f'cmp-ignore-{chars!r}', f"t.translate(str.maketrans('', '', {chars!r}))")
fold('cmp-curly-fold', "t.translate(str.maketrans('’‘“”', '\\'\\'\"\"'))")
fold('cmp-dash-fold', "t.replace('—', '-').replace('–', '-')")
fold('cmp-paren-to-comma', "t.replace(' (', ', ').replace(')', '')")
fold('cmp-semicolon-to-comma', "t.replace(';', ',')")
fold('cmp-collapse-ws', "' '.join(t.split())")
fold('cmp-collapse-spaces', "re.sub(' +', ' ', t)")
fold('cmp-strip', 't.strip()')
fold('cmp-rstrip', 't.rstrip()')
fold('cmp-lstrip', 't.lstrip()')
fold('cmp-tab-space', "t.replace('\\t', ' ')")
fold('cmp-nbsp-space', "t.replace('\\u00a0', ' ')")
fold('cmp-no-ws', "''.join(t.split())")
for form in ('NFC', 'NFD', 'NFKC', 'NFKD'):
    fold(f'cmp-{form.lower()}', f"__import__('unicodedata').normalize('{form}', t)")
fold('cmp-strip-accents', "''.join(c for c in __import__('unicodedata').normalize('NFD', t) if not __import__('unicodedata').combining(c))")
fold('cmp-drop-format-chars', "''.join(c for c in t if __import__('unicodedata').category(c) != 'Cf')")
fold('cmp-drop-controls', "''.join(c for c in t if __import__('unicodedata').category(c) != 'Cc')")
fold('cmp-unicode-spaces', "''.join(' ' if __import__('unicodedata').category(c) == 'Zs' else c for c in t)")
fold('cmp-strip-emphasis', r"re.sub(r'(\*\*|__|\*|_)(.+?)\1', r'\2', t)")
fold('cmp-strip-links', r"re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)")
fold('cmp-strip-html-comments', r"re.sub(r'<!--.*?-->', '', t)")
fold('cmp-strip-backticks', "t.replace('`', '')")
# --- carve-outs on the comparison: a clause
fold('cmp-drop-parenthesised', r"re.sub(r'\s*\([^)]*\)', '', t)")
fold('cmp-drop-after-last-semicolon', "t.rsplit(';', 1)[0]")
fold('cmp-drop-before-first-semicolon', "t.split(';', 1)[-1]")
fold('cmp-drop-after-last-comma', "t.rsplit(',', 1)[0]")
fold('cmp-drop-after-first-period', "t.split('. ', 1)[0]")
fold('cmp-drop-trailing-sentence', r"re.sub(r'\.\s+[A-Z][^.]*\.?$', '', t)")
fold('cmp-drop-trailing-period', "t.rstrip('.')")
fold('cmp-strip-trailing-punctuation', "t.rstrip('.;,:!?')")
fold('cmp-drop-except-clause', r"re.sub(r'\s*[Ee]xcept( for)? a gate\s*', ' ', t).strip()")
fold('cmp-drop-trailing-parenthetical', r"re.sub(r'\s*\([^)]*\)\.?$', '', t)")
fold('cmp-drop-after-em-dash', "t.split(' — ', 1)[0]")
fold('cmp-drop-after-double-hyphen', "t.split(' -- ', 1)[0]")
fold('cmp-drop-after-last-colon', "t.rsplit(': ', 1)[0]")
fold('cmp-drop-trailing-except-after-comma', r"re.sub(r',\s*except\b.*$', '', t)")
fold('cmp-drop-leading-parenthetical', r"re.sub(r'^\([^)]*\)\s*', '', t)")
fold('cmp-drop-sentence-in-middle', r"re.sub(r'\.\s+[A-Z][^.]*\.\s+', ' ', t)")
fold('cmp-first-n-words', "' '.join(t.split()[:12])")
fold('cmp-last-n-words', "' '.join(t.split()[-12:])")
carve('cmp-word-set', 'def _cmp(x):\n    return None if x is None else (x[0], frozenset(x[1].split()))\n')
PAIRWISE = '''def _carve(s, d):
    out = []
    for n in range(max(len(s), len(d))):
        a = s[n] if n < len(s) else None
        b = d[n] if n < len(d) else None
        if a is not None and b is not None and a[0] == b[0] and ({cond}):
            a = b
        out.append(a)
    while out and out[-1] is None:
        out.pop()
    return out, d
'''
for name, cond in [
    ('pair-prefix-either', 'a[1].startswith(b[1]) or b[1].startswith(a[1])'),
    ('pair-stated-prefix-of-desc', 'b[1].startswith(a[1])'),
    ('pair-desc-prefix-of-stated', 'a[1].startswith(b[1])'),
    ('pair-suffix-either', 'a[1].endswith(b[1]) or b[1].endswith(a[1])'),
    ('pair-contains-either', 'a[1] in b[1] or b[1] in a[1]'),
    ('pair-word-subsequence', 'all(w in iter(b[1].split()) for w in a[1].split()) or all(w in iter(a[1].split()) for w in b[1].split())'),
    ('pair-ratio-097', '__import__("difflib").SequenceMatcher(None, a[1], b[1]).ratio() > 0.97'),
    ('pair-word-ratio-09', '__import__("difflib").SequenceMatcher(None, a[1].split(), b[1].split()).ratio() > 0.9'),
]:
    carve(name, PAIRWISE.format(cond=cond))
carve('list-sorted', 'def _carve(s, d):\n    return sorted(s), sorted(d)\n')
carve('list-dedupe', 'def _carve(s, d):\n    return list(dict.fromkeys(s)), list(dict.fromkeys(d))\n')
carve('list-set', 'def _carve(s, d):\n    return sorted(set(s)), sorted(set(d))\n')
carve('list-zip', 'def _carve(s, d):\n    m = min(len(s), len(d))\n    return s[:m], d[:m]\n')
carve('list-ignore-extra-stated', 'def _carve(s, d):\n    return s[:len(d)], d\n')
carve('list-ignore-extra-described', 'def _carve(s, d):\n    return s, d[:len(s)]\n')
carve('list-common-names', 'def _carve(s, d):\n    names = {x[0] for x in s} & {x[0] for x in d}\n'
                           '    return [x for x in s if x[0] in names], [x for x in d if x[0] in names]\n')
carve('list-by-name', 'def _carve(s, d):\n    ds = dict(d)\n    return [x for x in s if x[0] in ds], [(n, ds[n]) for n, _ in s if n in ds] or d\n')

# The rows each named mutant must fail: the review's structural survivors, each pinned by a row.
NAMED: dict[str, list[str]] = {
    'dm-else-entry-entry': ['name-only-entry-in-pyproject'],
    'sm-count-last': ['stated-twice-the-last-exact-in-testing'],
    'sm-indent-fixed2': ['+a-statement-in-a-nested-bullet'],
    'sm-cont-allow-space': ['double-space-hidden-by-a-deeper-wrap-in-testing'],
    'sm-cont-allow-empty': ['trailing-space-hidden-by-a-blank-wrap-in-testing'],
    'sm-cont-tab': ['tabs-in-a-wrap-in-testing'],
    'sm-tab-wrap-branch-dropped': ['tab-after-a-wrap-indent-in-testing'],
    'se-blank-following-none': ['+a-blank-then-the-section-end'],
    'se-blank-lt-needs-nonitem': ['+a-blank-then-a-less-indented-bullet'],
    'se-blank-content-col': ['a-blank-then-a-third-marker-one-column-deeper'],
    'se-whitespace-line-is-blank': ['a-line-of-no-break-space-then-a-wrapped-line'],
    'se-following-any-whitespace': ['+a-blank-then-a-line-of-no-break-space-then-an-indented-line'],
    'se-nb-any-nonblank-shallower': ['no-space-after-the-bullet'],
    'mi-tab-one-column': ['a-tab-then-an-exception-bullet', 'a-blank-then-a-tab-indented-paragraph'],
    'mi-tab-four-columns': ['+nested-a-blank-then-a-space-and-tab-indented-paragraph'],
    'mi-nbsp-indents': ['a-no-break-space-then-an-exception-bullet'],
    'mi-any-space-indents': ['an-em-space-then-an-exception-bullet'],
    're-list-no-space': ['no-space-after-the-bullet'],
    're-list-digits-no-delim': ['digits-without-a-delimiter'],
    're-list-ws': ['a-no-break-space-after-the-bullet'],
    're-list-space-only': ['+a-tab-after-the-bullet'],
    're-list-any-digits': ['a-ten-digit-ordered-item'],
    're-list-eight-digits': ['+a-nine-digit-ordered-item'],
    're-list-only-dash': ['+a-less-indented-star-bullet'],
    're-list-no-ordered': ['+a-less-indented-ordered-item'],
    're-list-hash': ['+a-blank-then-a-heading-at-the-items-indent'],
}

# Survivors that pass no drift the check refuses, each with the reason.
EQUIVALENT: dict[str, str] = {
    'sm-notitem-break': 'the line that stops the loop starts a `- ` item at the statement\'s indent, so '
                        'statement_end_problems refuses it as a continuation either way',
    're-item-search': '`.match` and `.fullmatch` agree: `(.*)` ends the pattern and a line holds no newline',
    'sm-cont-no-items-guard': 'it differs only on a deeper line before the first item, where it raises IndexError '
                              'instead of returning the refusal; a raise fails the test as the refusal does',
}

# Survivors that are a deeper layer of a class a row or the control already pins, filed in
# issues/marker-statement-deeper-carve-outs.md, each with its class.
SEEDED: dict[str, str] = {
    'sm-rstrip': 'where the statement ends: trailing spaces on the statement line move the indent the items '
                 'are read at past the bullet\'s text, and a less indented item then joins their list (the '
                 'check itself passes the same shape for a statement indented past its bullet\'s text)',
    'cmp-dash-fold': 'a fold of two characters: dashes, where case, quotes and Unicode forms are pinned; the '
                     'control replaces each character by its other case or a letter, never by a look-alike',
}


class Timeout(Exception):
    pass


def alarm(_signum, _frame):
    raise Timeout


def load(kind: str, subs: list[tuple[str, str]], code: str) -> dict:
    check = CHECK
    for old, new in subs:
        if check.count(old) != 1:
            raise LookupError(f'{old!r} occurs {check.count(old)} times in the check')
        check = check.replace(old, new)
    ns: dict = {'functools': functools, 're': re, 'tomllib': tomllib, 'pytest': pytest, 'Path': Path}
    exec(compile(HOOKS + code + '\n' + check + REST, 'test_hygiene.py (mutant)', 'exec'), ns)
    return ns


def params(ns: dict, test: str) -> list[tuple[str, tuple]]:
    return [(p.id, p.values) for m in ns[test].pytestmark if m.name == 'parametrize' for p in m.args[1]]


def outcomes(ns: dict, control: bool) -> dict[str, bool]:
    """Each row's id and whether its test passes: `+id` an accept row (an ENDS row expected accepted
    included), `id` a refuse row, `control` the whole-domain control, `live` the staged files."""
    check, planted, ended = ns['marker_statement_violations'], ns['planted'], ns['ended']
    out: dict[str, bool] = {}

    def verdict(expect_refused: bool, pair) -> bool:
        try:
            return (check(*pair()) != []) == expect_refused
        except Exception:  # noqa: BLE001 - an error fails the row, as pytest would
            return False
    for rid, (change,) in params(ns, ACCEPTS):
        out[f'+{rid}'] = verdict(False, lambda: planted(**change))
    for test in (ROWS, NARROW):
        for rid, (change,) in params(ns, test):
            out[rid] = verdict(True, lambda: planted(**change))
    for rid, (after, nested, refused) in params(ns, ENDS):
        out[rid if refused else f'+{rid}'] = verdict(refused, lambda: ended(after, nested))
    try:
        out['live'] = check(*REAL) == []
    except Exception:  # noqa: BLE001
        out['live'] = False
    if control:
        try:
            ns[CONTROL]()
            out['control'] = True
        except Exception:  # noqa: BLE001 - AssertionError, or the check raising
            out['control'] = False
    return out


def main() -> int:
    signal.signal(signal.SIGALRM, alarm)
    began = time.monotonic()
    base = outcomes(load('decision', [], ''), control=True)
    red = sorted(k for k, ok in base.items() if not ok)
    print(f'unmutated: {len(base)} checks (rows, control, live), not passed: {red}')
    bad = 1 if red else 0
    unknown = sorted({r for rows in NAMED.values() for r in rows} - set(base))
    listed = sorted((set(NAMED) | set(EQUIVALENT) | set(SEEDED)) - set(MUTANTS))
    if unknown or listed:
        print(f'named rows that do not exist: {unknown}; listed mutants not in the table: {listed}')
        bad += 1
    tally = {'killed': 0, 'equivalent': 0, 'seeded': 0}
    for mid, (kind, subs, code) in MUTANTS.items():
        signal.alarm(60)
        try:
            ns = load(kind, subs, code)
            got = outcomes(ns, control=False)
            if all(got.values()):
                got.update(outcomes(ns, control=True))
        except LookupError as stale:
            print(f'{mid}: STALE, {stale}')
            bad += 1
            continue
        except Timeout:
            print(f'{mid}: TIMED OUT')
            bad += 1
            continue
        finally:
            signal.alarm(0)
        killers = sorted(k for k, ok in got.items() if not ok)
        if mid in NAMED:
            missed = [r for r in NAMED[mid] if got.get(r, True)]
            if missed:
                bad += 1
                print(f'{mid}: SURVIVED its named rows [{kind}]; still passing {missed}')
                continue
        if killers:
            if mid in EQUIVALENT or mid in SEEDED:
                bad += 1
                print(f'{mid}: STALE LISTING, killed by {", ".join(killers[:4])}')
                continue
            tally['killed'] += 1
            print(f'{mid}: killed [{kind}] by {", ".join(killers[:4])}{" …" if len(killers) > 4 else ""}')
        elif mid in EQUIVALENT:
            tally['equivalent'] += 1
            print(f'{mid}: equivalent [{kind}]: {EQUIVALENT[mid]}')
        elif mid in SEEDED:
            tally['seeded'] += 1
            print(f'{mid}: seeded [{kind}]: {SEEDED[mid]}')
        else:
            bad += 1
            print(f'{mid}: SURVIVED [{kind}]')
    print(f'{len(MUTANTS)} mutants: {tally["killed"]} killed, {tally["equivalent"]} equivalent, '
          f'{tally["seeded"]} seeded, {bad} not accounted for; {time.monotonic() - began:.0f} s')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
