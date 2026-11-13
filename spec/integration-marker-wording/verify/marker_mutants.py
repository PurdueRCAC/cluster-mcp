"""Mutant sweep of the marker-statement check: each mutant is a check that decides one thing
differently, or carries one carve-out more, and each must be killed by the planted rows it names.

Run from the worktree root, after staging (it reads `tests/test_hygiene.py` from the index):

    uv run --no-sync python -I spec/integration-marker-wording/verify/marker_mutants.py [--only ID ...]

Builds one scratch tree from the index (`git checkout-index`), then for the unmutated check and for
each mutant in turn writes the mutated `tests/test_hygiene.py` there and runs the check's tests with
this worktree's interpreter, one pytest at a time. Every row must pass unmutated; under a mutant,
every row it names must fail (other rows may fail too). Prints one line per mutant and exits 1 on a
survivor, a mutant whose text no longer applies exactly once, or a named row that did not run.

Footprint: one python and one pytest child at a time; under 300 MB; about 2 s a mutant. The
scratch tree is removed on exit; nothing outlives the sweep.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROWS = 'test_marker_statement_check_catches_planted_drift'
ACCEPTS = 'test_marker_statement_check_accepts_a_rewrapped_statement'
LIVE = 'test_the_markers_are_stated_as_pyproject_describes_them'
SECTIONS = "(('§ Testing', '## Testing'), ('§ Conventions', '### Conventions (same-commit rules)'))"
COMPARE = 'if said != meant:'
LOOP = 'for n in range(max(len(stated), len(described))):'
PARSE = 'stated, problems = stated_markers(agents_section(agents, heading))'
CONT = "elif items and line.startswith(indent + '  ') and line[len(indent) + 2:][:1] not in ('', ' '):"
JOIN = "items[-1][1] += ' ' + line[len(indent) + 2:]"
SPLIT = "[(entry.split(': ', 1)[0], entry.split(': ', 1)[1]) if ': ' in entry else (entry, '') for entry in entries]"
DEF = '\ndef described_markers('


def names_by(body: str) -> list[tuple[str, str]]:
    """A mutant that compares each (name, description) pair after `body` rewrites its name `n`."""
    return [(COMPARE, 'if _named(said) != _named(meant):'),
            (DEF, f'\ndef _named(pair):\n    return pair and ((lambda n: {body})(pair[0]), pair[1])\n\n{DEF}')]


def compared_by(body: str) -> list[tuple[str, str]]:
    """A mutant that compares each (name, description) pair after `body` rewrites its description `d`."""
    return [(COMPARE, 'if _seen(said) != _seen(meant):'),
            (DEF, f'\ndef _seen(pair):\n    return pair and (pair[0], (lambda d: {body})(pair[1]))\n\n{DEF}')]

# id: (why, [(old, new), ...], rows that must fail). A row is a drift row's id, or `+<id>` for an
# accept row. The first group mutates a decision the check makes; the second adds a carve-out it
# could grow. Every drift row must be named by at least one mutant: a row no mutant needs is one the
# GOAL does not admit.
MUTANTS: dict[str, tuple[str, list[tuple[str, str]], list[str]]] = {
    # Decisions.
    'testing-only': ('reads § Testing alone', [(SECTIONS, "(('§ Testing', '## Testing'),)")],
                     ['changed-in-conventions', 'missing-from-conventions']),
    'conventions-only': ('reads § Conventions alone',
                         [(SECTIONS, "(('§ Conventions', '### Conventions (same-commit rules)'),)")],
                         ['changed-in-testing', 'missing-from-testing']),
    'whole-file-first-statement': ('reads the first statement anywhere in AGENTS.md',
                                   [(PARSE, 'stated, problems = stated_markers(agents)'),
                                    ('if len(at) != 1:', 'if not at:')],
                                   ['missing-from-testing', 'changed-in-conventions']),
    'first-of-several': ('takes the first of several statements in a section',
                         [('if len(at) != 1:', 'if not at:')], ['stated-twice']),
    'silent-section-passes': ('lets a section that states nothing pass',
                              [("violations += [f'{where}: {problem}' for problem in problems]",
                                'if not stated: continue')],
                              ['missing-from-testing', 'missing-from-conventions', 'statement-without-items',
                               'statement-line-reworded', 'item-without-backticks-in-testing']),
    'silent-pyproject-passes': ('lets a pyproject.toml with no markers pass',
                                [("violations = [] if described else ['pyproject.toml describes no markers']",
                                  'violations = []\n    if not described: return []')],
                                ['missing-from-pyproject']),
    'order-free': ('compares the markers in any order',
                   [(PARSE, PARSE + '; stated, described = sorted(stated), sorted(described)')],
                   ['reordered-in-testing']),
    'mapping': ('compares name-to-description mappings, so a repeat collapses',
                [(LOOP + '\n', 'for n in ([0] if dict(stated) != dict(described) else []):\n'),
                 (COMPARE, 'if True:')],
                ['repeated-in-pyproject', 'repeated-in-testing', 'reordered-in-testing']),
    'names-only': ('compares names alone',
                   [(COMPARE, 'if (said or ("",))[0] != (meant or ("",))[0]:')],
                   ['changed-in-pyproject', 'changed-in-testing', 'changed-in-conventions']),
    'extra-stated-ignored': ('ignores a marker AGENTS.md states beyond pyproject.toml',
                             [(LOOP, 'for n in range(len(described)):')], ['third-marker-in-testing']),
    'extra-described-ignored': ('ignores a marker pyproject.toml describes beyond AGENTS.md',
                                [(LOOP, 'for n in range(len(stated)):')],
                                ['third-marker-in-pyproject', 'one-missing-from-testing']),
    'extra-stated-ignored-too': ('ignores a marker AGENTS.md states beyond pyproject.toml (one missing there)',
                                 [(LOOP, 'for n in range(len(described)):')], ['one-missing-from-pyproject']),
    'section-runs-to-end': ('reads from the heading to the end of AGENTS.md',
                            [("return agents[start:min([e for e in ends if e != -1], default=len(agents))]",
                              'return agents[start:]')], ['+as-planted']),
    'two-markers-only': ('compares the first two markers only', [(LOOP, 'for n in range(2):')],
                         ['third-marker-in-pyproject', 'third-marker-in-testing']),
    'item-indent-free': ('takes an item at any indentation',
                         [("if line.startswith(indent + '- '):", "if line.startswith(indent) and line.lstrip(' ').startswith('- '):"),
                          ('MARKER_ITEM.fullmatch(line[len(indent):])', "MARKER_ITEM.fullmatch(line.lstrip(' '))")],
                         ['item-over-indented-in-testing']),
    # Carve-outs.
    'casefold': ('ignores case', compared_by('d.casefold()'),
                 ['case-in-pyproject', 'case-in-testing']),
    'punctuation-free': ('ignores punctuation',
                         compared_by("re.sub(r'[^\\w\\s]', '', d)"),
                         ['punctuation-in-pyproject', 'punctuation-in-testing']),
    'markup-free': ('ignores Markdown markup in a description',
                    [(JOIN, JOIN + ".replace('`', '').replace('*', '')"),
                     ('items.append([item[1], item[2]])',
                      "items.append([item[1], item[2].replace('`', '').replace('*', '')])")],
                    ['markup-in-testing', 'emphasis-in-testing']),
    'unicode-compatible': ('compares descriptions after NFKC normalisation',
                           compared_by("__import__('unicodedata').normalize('NFKC', d)"),
                           ['no-break-space-in-testing', 'decomposed-in-testing']),
    'whitespace-free': ('ignores whitespace beyond wrapping, as the id-rule check does',
                        compared_by("' '.join(d.split())"),
                        ['double-space-in-pyproject', 'double-space-in-testing', 'tab-in-testing',
                         'trailing-space-in-pyproject', 'trailing-space-at-wrap-in-testing',
                         'two-spaces-after-name-in-testing', 'no-break-space-in-testing']),
    'wrap-indent-free': ('takes a wrapped line at any deeper indentation',
                         [(CONT, "elif items and line.startswith(indent + '  ') and line.strip():"),
                          (JOIN, "items[-1][1] += ' ' + line.strip()")],
                         ['over-indented-wrap-in-testing']),
    'trailing-clause': ('ignores a clause one side adds at the end',
                        [(COMPARE, 'if not (said and meant and said[0] == meant[0] and '
                                   '(said[1].startswith(meant[1]) or meant[1].startswith(said[1]))):')],
                        ['clause-at-end-in-pyproject', 'clause-at-end-in-testing']),
    'leading-clause': ('ignores a clause one side adds at the start',
                       [(COMPARE, 'if not (said and meant and said[0] == meant[0] and '
                                  '(said[1].endswith(meant[1]) or meant[1].endswith(said[1]))):')],
                       ['clause-at-start-in-pyproject', 'clause-at-start-in-testing']),
    'middle-clause': ('ignores words one side adds anywhere, the other side read in order',
                      [(COMPARE, 'if not (said and meant and said[0] == meant[0] and '
                                 '(_within(said[1], meant[1]) or _within(meant[1], said[1]))):'),
                       (DEF,
                        '\ndef _within(short, long):\n    words = iter(long.split(" "))\n'
                        '    return all(w in words for w in short.split(" "))\n\n\ndef described_markers(')],
                      ['clause-in-middle-in-pyproject', 'clause-in-middle-in-testing',
                       'clause-at-start-in-pyproject', 'clause-at-start-in-testing',
                       'clause-at-end-in-pyproject', 'clause-at-end-in-testing']),
    'separator-free': ("splits a pyproject.toml entry at its first ':' and strips it, as pytest does",
                       [(SPLIT, "[(e.split(':', 1)[0], e.split(':', 1)[1].strip()) for e in entries]")],
                       ['no-space-after-name-in-pyproject', 'trailing-space-in-pyproject']),
    'statement-end-free': ('ends the statement silently at any line it does not read',
                           [("return [(name, text) for name, text in items], statement_end_problems(rest[end:], indent)",
                             'return [(name, text) for name, text in items], []')],
                           ['clause-lazy-after-last-item', 'clause-at-item-indent-after-last-item',
                            'clause-over-indented-after-last-item', 'clause-after-a-blank-in-last-item',
                            'third-marker-after-a-blank-in-testing', 'third-marker-other-bullet-in-testing']),
    'blank-ends-statement': ('takes a blank line as the end of the statement, whatever follows',
                             [("    if not after or not after[0].strip():\n", "    if not after or not after[0].strip():\n        return []\n")],
                             ['clause-after-a-blank-in-last-item', 'third-marker-after-a-blank-in-testing']),
    'name-casefold': ('ignores the case of a name', names_by('n.casefold()'), ['name-case-in-testing']),
    'trailing-period-free': ('ignores a trailing period', compared_by("d.rstrip('.')"), ['trailing-period-in-testing']),
    'composed-equal': ('compares descriptions after NFC normalisation',
                       compared_by("__import__('unicodedata').normalize('NFC', d)"), ['decomposed-in-testing']),
    'statement-line-whitespace-free': ('finds the statement line whatever whitespace surrounds it',
                                       [("if line.lstrip(' ') == MARKERS_STATED]", 'if line.strip() == MARKERS_STATED]'),
                                        ("indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))",
                                         "indent = ' ' * (len(lines[at[0]].expandtabs(2)) - len(lines[at[0]].expandtabs(2).lstrip()))")],
                                       ['statement-line-trailing-space-in-testing', 'statement-line-tab-indented-in-testing']),
    'statement-line-free': ('finds the statement line by its opening words',
                            [("if line.lstrip(' ') == MARKERS_STATED]", "if MARKERS_STATED.split(',')[0] in line]"),
                             ("indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))",
                              "indent = ' ' * (len(lines[at[0]]) - len(lines[at[0]].lstrip(' ')))")],
                            ['statement-line-reworded']),
    'name-stripped': ("strips a stated marker's name", [('items.append([item[1], item[2]])',
                                                          'items.append([item[1].strip(), item[2]])')],
                      ['name-changed-in-testing']),
    'name-shape-free': ('takes an item whose name is not in backticks',
                        [("MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')",
                          "MARKER_ITEM = re.compile(r'- `?([^`:]*)`?: (.*)')")],
                        ['item-without-backticks-in-testing']),
}


def outcomes(junit: Path) -> dict[str, str]:
    """Each test case's id (`name[row]` or `name`) and its outcome."""
    found = {}
    for case in ET.parse(junit).iter('testcase'):
        kind = next((c.tag for c in case if c.tag in ('failure', 'error', 'skipped')), 'passed')
        found[case.get('name')] = kind
    return found


def run(scratch: Path, python: str) -> dict[str, str]:
    junit = scratch / 'junit.xml'
    junit.unlink(missing_ok=True)
    subprocess.run([python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={junit}',
                    'tests/test_hygiene.py', '-k', f'{ROWS} or {ACCEPTS} or {LIVE}'],
                   cwd=scratch, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    return outcomes(junit) if junit.exists() else {}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='*', default=None)
    only = parser.parse_args(argv).only
    root = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                               check=True).stdout.strip())
    python = sys.executable
    source = subprocess.run(['git', 'show', ':tests/test_hygiene.py'], cwd=root, capture_output=True, text=True,
                            check=True).stdout
    scratch = Path(tempfile.mkdtemp(prefix='marker-mutants-'))
    bad = 0
    try:
        subprocess.run(['git', 'checkout-index', '-a', f'--prefix={scratch}/'], cwd=root, check=True)
        target = scratch / 'tests' / 'test_hygiene.py'
        base = run(scratch, python)
        rows = sorted(k[len(ROWS) + 1:-1] for k in base if k.startswith(ROWS + '['))
        accepts = sorted(k for k in base if k.startswith(ACCEPTS + '['))
        red = [k for k, v in base.items() if v != 'passed']
        print(f'unmutated: {len(rows)} drift rows, {len(accepts)} accept rows, live test '
              f'{base.get(LIVE, "missing")}, not passed: {red}')
        if not rows or not accepts or LIVE not in base or red:
            return 1
        named = {k for _, _, kills in MUTANTS.values() for k in kills}
        idle = [r for r in rows if r not in named]
        unknown = sorted(k for k in named if (k[1:] if k.startswith('+') else k) not in
                         ([a[len(ACCEPTS) + 1:-1] for a in accepts] if k.startswith('+') else rows))
        if idle or unknown:
            print(f'drift rows no mutant names: {idle}; named rows that do not exist: {unknown}')
            bad += 1
        for mid, (why, subs, kills) in MUTANTS.items():
            if only and mid not in only:
                continue
            text = source
            for old, new in subs:
                if text.count(old) != 1:
                    print(f'{mid}: STALE, {old!r} occurs {text.count(old)} times')
                    bad += 1
                    break
                text = text.replace(old, new)
            else:
                target.write_text(text)
                got = run(scratch, python)
                seen = {k: got.get(f'{ACCEPTS}[{k[1:]}]' if k.startswith('+') else f'{ROWS}[{k}]', 'missing')
                        for k in kills}
                missing = [k for k, v in seen.items() if v == 'missing']
                survived = [k for k, v in seen.items() if v not in ('failure', 'error')]
                broken = (not any(k.startswith('+') for k in kills)
                          and got.get(f'{ACCEPTS}[as-planted]') != 'passed')
                if not got or missing or survived or broken:
                    bad += 1
                    print(f'{mid}: SURVIVED ({why}); not red {survived}, did not run {missing}, '
                          f'as-planted broken {broken}')
                else:
                    print(f'{mid}: killed ({why}) by {", ".join(kills)}')
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f'{len(MUTANTS) if not only else len(only)} mutants, {bad} not killed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
