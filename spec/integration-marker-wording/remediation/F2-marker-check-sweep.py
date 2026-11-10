"""Review cycle 1, findings 2 and 3: a module-wide mutant sweep of the marker-statement check.

Every decision in `stated_markers`, `statement_end_problems`, `described_markers` and
`marker_statement_violations`, and every additive carve-out the check could grow (case, each
punctuation class, quotes, whitespace, a clause at the start, middle or end or after the statement,
a lazy continuation, bullet styles, a third or missing marker, order, repeats, Unicode forms), as a
source substitution on the check in the staged `tests/test_hygiene.py`. The table starts from the
review's sweep (71 mutants) and adds the punctuation classes one at a time.

Run from the worktree root, after staging:

    uv run --no-sync python -I spec/integration-marker-wording/remediation/F2-marker-check-sweep.py

The check, its planted pair and its three row tables (accept, planted drift, narrower drift) are read
from the index and executed in this process, one namespace per mutant; the live test is evaluated on
the staged pyproject.toml and AGENTS.md. A mutant is killed when a drift row passes unflagged, an
accept row is refused, or the live files are refused. A mutant in NAMED must be killed by every row
it names, with the accept row `as-planted` still accepted; every narrower-drift row must be named by
some mutant. Prints one line a mutant and exits 1 on a survivor, an idle row, or a substitution that
does not apply exactly once. One process, no children but git; under 100 MB; about a second.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

START = "# The markers' meaning, as AGENTS.md"
TESTS = '@pytest.mark.unit\ndef test_the_markers_are_stated_as_pyproject_describes_them'
STOP = '\n# Every name of the SSH-host and user-map variables bin/sandbox.sh must unset'
ACCEPTS = 'test_marker_statement_check_accepts_a_rewrapped_statement'
ROWS = 'test_marker_statement_check_catches_planted_drift'
NARROW = 'test_marker_statement_check_catches_narrower_drift'


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


SOURCE = staged('tests/test_hygiene.py')
BLOCK = SOURCE[SOURCE.index(START):SOURCE.index(STOP)]
CHECK, REST = BLOCK[:BLOCK.index(TESTS)], BLOCK[BLOCK.index(TESTS):]
REAL = (staged('pyproject.toml'), staged('AGENTS.md'))

CMP_OLD = "            if said != meant:\n"


def cmp(expr: str) -> list[tuple[str, str]]:
    """Replace the per-marker comparison with `expr` (said/meant are (name, text) tuples or None)."""
    return [(CMP_OLD, f"            if not ({expr}):\n")]


def norm(fn: str) -> list[tuple[str, str]]:
    """Normalise both sides' descriptions (and names) with `fn` (a lambda source on a str) before comparing."""
    return [(CMP_OLD,
             f"            _n = {fn}\n"
             "            said = None if said is None else (_n(said[0]), _n(said[1]))\n"
             "            meant = None if meant is None else (_n(meant[0]), _n(meant[1]))\n"
             + CMP_OLD)]


def norm_text(fn: str) -> list[tuple[str, str]]:
    """Normalise only the descriptions."""
    return [(CMP_OLD,
             f"            _n = {fn}\n"
             "            said = None if said is None else (said[0], _n(said[1]))\n"
             "            meant = None if meant is None else (meant[0], _n(meant[1]))\n"
             + CMP_OLD)]


CURLY = "lambda s: s.replace('\\u2018', \"'\").replace('\\u2019', \"'\").replace('\\u201c', '\"').replace('\\u201d', '\"')"

MUTANTS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    # --- plain / subtractive ---
    'always-true': ('plain', cmp('True')),
    'only-first-marker': ('plain', [("        for n in range(max(len(stated), len(described))):\n",
                                      "        for n in range(min(1, max(len(stated), len(described)))):\n")]),
    'zip-common-prefix': ('plain', [("        for n in range(max(len(stated), len(described))):\n",
                                      "        for n in range(min(len(stated), len(described))):\n")]),
    'only-described-count': ('additive:third-marker-in-agents', [("        for n in range(max(len(stated), len(described))):\n",
                                                                  "        for n in range(len(described)):\n")]),
    'only-stated-count': ('additive:third-marker-in-pyproject', [("        for n in range(max(len(stated), len(described))):\n",
                                                                 "        for n in range(len(stated)):\n")]),
    'names-only': ('plain', cmp("(said or (None,))[0] == (meant or (None,))[0]")),
    'texts-only': ('plain', cmp("(said or (None, None))[1] == (meant or (None, None))[1]")),
    'skip-conventions': ('plain', [("(('§ Testing', '## Testing'), ('§ Conventions', '### Conventions (same-commit rules)'))",
                                    "(('§ Testing', '## Testing'),)")]),
    'skip-testing': ('plain', [("(('§ Testing', '## Testing'), ('§ Conventions', '### Conventions (same-commit rules)'))",
                                "(('§ Conventions', '### Conventions (same-commit rules)'),)")]),
    'stop-at-first-line(ignore wraps)': ('plain', [("            items[-1][1] += ' ' + line[len(indent) + 2:]\n",
                                                    "            pass\n")]),
    'end-problems-never': ('plain', [('    """Why the lines after a statement would render as part of it: a lazy continuation of its last\n'
                                      '    item, a paragraph inside it, or a further item."""\n',
                                      '    """x"""\n    return []\n')]),
    'drop-statement-problems': ('plain', [("        violations += [f'{where}: {problem}' for problem in problems]\n", "")]),
    'drop-no-markers-line': ('plain', [("    violations = [] if described else ['pyproject.toml describes no markers']\n",
                                        "    violations = []\n")]),
    'no-markers-returns-empty': ('plain', [("    violations = [] if described else ['pyproject.toml describes no markers']\n",
                                            "    if not described:\n        return []\n    violations = []\n")]),
    'first-of-duplicate-statements': ('plain', [("    if len(at) != 1:\n", "    if len(at) == 0:\n")]),
    'skip-bad-item-line': ('plain', [("                return [], [f'not a `- `<name>`: <description>` item: {line.strip()!r}']\n",
                                      "                continue\n")]),
    'whole-file-sections': ('plain', [("    return agents[start:min([e for e in ends if e != -1], default=len(agents))]\n",
                                       "    return agents\n")]),
    'section-ends-at-same-level-only': ('plain', [("    ends = [agents.find(f'\\n{\"#\" * n} ', start + 1) for n in range(1, len(level) + 1)]\n",
                                                   "    ends = [agents.find(f'\\n{level} ', start + 1)]\n")]),
    'set-compare(order+repeat)': ('additive:order/repeat', [("        for n in range(max(len(stated), len(described))):\n",
                                                             "        if set(stated) == set(described): stated = described\n"
                                                             "        for n in range(max(len(stated), len(described))):\n")]),
    'sorted-compare(order)': ('additive:order', [("        for n in range(max(len(stated), len(described))):\n",
                                                  "        if sorted(stated) == sorted(described): stated = described\n"
                                                  "        for n in range(max(len(stated), len(described))):\n")]),
    'dedupe(repeat)': ('additive:repeat', [("        for n in range(max(len(stated), len(described))):\n",
                                            "        stated = list(dict.fromkeys(stated)); described = list(dict.fromkeys(described))\n"
                                            "        for n in range(max(len(stated), len(described))):\n")]),
    # --- additive carve-outs: normalisation ---
    'casefold(names+texts)': ('additive:case', norm('lambda s: s.casefold()')),
    'casefold(texts)': ('additive:case', norm_text('lambda s: s.casefold()')),
    'casefold(names)': ('additive:case', [(CMP_OLD,
                                          "            said = None if said is None else (said[0].casefold(), said[1])\n"
                                          "            meant = None if meant is None else (meant[0].casefold(), meant[1])\n" + CMP_OLD)]),
    'strip-all-punctuation': ('additive:punctuation', norm(r"lambda s: __import__('re').sub(r'[^\w\s]', '', s)")),
    'strip-trailing-punctuation': ('additive:punctuation', norm("lambda s: s.rstrip('.;,:!?')")),
    'ignore-commas': ('additive:punctuation', norm("lambda s: s.replace(',', '')")),
    'ignore-semicolons-as-commas': ('additive:punctuation', norm("lambda s: s.replace(';', ',')")),
    'ignore-periods': ('additive:punctuation', norm("lambda s: s.replace('.', '')")),
    'ignore-parens-chars': ('additive:punctuation', norm("lambda s: s.replace('(', '').replace(')', '')")),
    'ignore-slashes-hyphens': ('additive:punctuation', norm("lambda s: s.replace('/', '').replace('-', '')")),
    'curly-to-straight-quotes': ('additive:unicode/punctuation', norm(CURLY)),
    'strip-markup(`*_)': ('additive:markup', norm("lambda s: s.replace('`', '').replace('*', '').replace('_', '')")),
    'collapse-all-whitespace': ('additive:whitespace', norm("lambda s: ' '.join(s.split())")),
    'collapse-space-runs': ('additive:whitespace', norm(r"lambda s: __import__('re').sub(' +', ' ', s)")),
    'tabs-to-space': ('additive:whitespace', norm("lambda s: s.replace('\\t', ' ')")),
    'strip-ends': ('additive:whitespace', norm('lambda s: s.strip()')),
    'rstrip-ends': ('additive:whitespace', norm('lambda s: s.rstrip()')),
    'lstrip-ends': ('additive:whitespace', norm('lambda s: s.lstrip()')),
    'rstrip-each-line-before-join': ('additive:whitespace', [("            items.append([item[1], item[2]])\n",
                                                             "            items.append([item[1], item[2].rstrip()])\n"),
                                                            ("            items[-1][1] += ' ' + line[len(indent) + 2:]\n",
                                                             "            items[-1][1] = items[-1][1].rstrip() + ' ' + line[len(indent) + 2:]\n")]),
    'nbsp-to-space': ('additive:unicode/whitespace', norm("lambda s: s.replace('\\u00a0', ' ')")),
    'nfkc': ('additive:unicode', norm("lambda s: __import__('unicodedata').normalize('NFKC', s)")),
    'nfc': ('additive:unicode', norm("lambda s: __import__('unicodedata').normalize('NFC', s)")),
    'nfd': ('additive:unicode', norm("lambda s: __import__('unicodedata').normalize('NFD', s)")),
    'lenient-name-space(`:\\s*`)': ('additive:whitespace', [("MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')",
                                                            "MARKER_ITEM = re.compile(r'- `([^`]*)`:\\s*(.*)')")]),
    'pyproject-split-at-colon+strip': ('additive:whitespace', [
        ("    return [(entry.split(': ', 1)[0], entry.split(': ', 1)[1]) if ': ' in entry else (entry, '') for entry in entries]\n",
         "    return [(entry.split(':', 1)[0].strip(), entry.split(':', 1)[1].strip()) if ':' in entry else (entry, '') for entry in entries]\n")]),
    'name-without-backticks-ok': ('additive:markup', [("MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')",
                                                      "MARKER_ITEM = re.compile(r'- `?([^`:]*)`?: (.*)')")]),
    'name-strip': ('additive:whitespace', [("            items.append([item[1], item[2]])\n",
                                           "            items.append([item[1].strip(), item[2]])\n")]),
    # --- additive carve-outs: clauses ---
    'prefix-match(trailing clause)': ('additive:clause-end', cmp(
        "said == meant or (said is not None and meant is not None and said[0] == meant[0] and "
        "(said[1].startswith(meant[1]) or meant[1].startswith(said[1])))")),
    'suffix-match(leading clause)': ('additive:clause-start', cmp(
        "said == meant or (said is not None and meant is not None and said[0] == meant[0] and "
        "(said[1].endswith(meant[1]) or meant[1].endswith(said[1])))")),
    'containment(any clause)': ('additive:clause', cmp(
        "said == meant or (said is not None and meant is not None and said[0] == meant[0] and "
        "(said[1] in meant[1] or meant[1] in said[1]))")),
    'word-subsequence(middle clause)': ('additive:clause-middle', [(CMP_OLD,
        "            def _sub(a, b):\n"
        "                it = iter(b.split()); return all(w in it for w in a.split())\n"
        "            if said is not None and meant is not None and said[0] == meant[0] and (_sub(said[1], meant[1]) or _sub(meant[1], said[1])):\n"
        "                continue\n" + CMP_OLD)]),
    'ignore-parenthesised-text': ('additive:clause-middle', norm(r"lambda s: __import__('re').sub(r'\s*\([^)]*\)', '', s)")),
    'ignore-after-last-semicolon': ('additive:clause-end', norm("lambda s: s.rsplit(';', 1)[0]")),
    'ignore-before-first-semicolon': ('additive:clause-start', norm("lambda s: s.split(';', 1)[-1]")),
    'ignore-except-clauses': ('additive:clause', norm(r"lambda s: __import__('re').sub(r'\s*[Ee]xcept(?: for)? a gate\s*', ' ', s).strip()")),
    'ignore-after-last-sentence-period': ('additive:clause-after', norm("lambda s: s.split('. ', 1)[0]")),
    # --- additive carve-outs: statement structure ---
    'lazy-wrap-joins(equivalent?)': ('additive:lazy', [("        else:\n            end = n\n            break\n",
                                                     "        elif items and line.strip() and (len(line) - len(line.lstrip())) < len(indent) + 2 and not LIST_ITEM.match(line.lstrip()):\n"
                                                     "            items[-1][1] += ' ' + line.strip()\n"
                                                     "        else:\n            end = n\n            break\n")]),
    'lazy-continuation-ok': ('additive:lazy', [("    if depth < len(indent) and LIST_ITEM.match(after[0].lstrip()):\n",
                                                 "    if depth < len(indent):\n")]),
    'same-depth-other-bullet-ends': ('additive:bullet', [("    if depth < len(indent) and LIST_ITEM.match(after[0].lstrip()):\n",
                                                           "    if LIST_ITEM.match(after[0].lstrip()) and (depth < len(indent) or (depth == len(indent) and not after[0].lstrip().startswith('- '))):\n")]),
    'same-depth-any-item-ends': ('additive:bullet', [("    if depth < len(indent) and LIST_ITEM.match(after[0].lstrip()):\n",
                                                       "    if depth <= len(indent) and LIST_ITEM.match(after[0].lstrip()):\n")]),
    'anything-after-blank-ok': ('additive:paragraph', [("        if depth < len(indent) or (depth == len(indent) and not LIST_ITEM.match(following.lstrip())):\n",
                                                         "        if True:\n")]),
    'after-blank-same-depth-item-ok': ('additive:paragraph', [("        if depth < len(indent) or (depth == len(indent) and not LIST_ITEM.match(following.lstrip())):\n",
                                                                "        if depth <= len(indent):\n")]),
    'other-bullets-are-items': ('additive:bullet', [("        if line.startswith(indent + '- '):\n            item = MARKER_ITEM.fullmatch(line[len(indent):])\n",
                                                      "        if line[len(indent):][:2] in ('- ', '* ', '+ ') and line.startswith(indent):\n            item = MARKER_ITEM.fullmatch('- ' + line[len(indent) + 2:])\n")]),
    'deeper-wrap-ok': ('additive:whitespace', [("        elif items and line.startswith(indent + '  ') and line[len(indent) + 2:][:1] not in ('', ' '):\n            items[-1][1] += ' ' + line[len(indent) + 2:]\n",
                                                 "        elif items and line.startswith(indent + '  ') and line.strip():\n            items[-1][1] += ' ' + line.strip()\n")]),
    'wrap-joins-tab-indent': ('additive:whitespace', [("        elif items and line.startswith(indent + '  ') and line[len(indent) + 2:][:1] not in ('', ' '):\n            items[-1][1] += ' ' + line[len(indent) + 2:]\n",
                                                        "        elif items and line[:1] in (' ', '\\t') and line.strip() and not line.lstrip().startswith('- '):\n            items[-1][1] += ' ' + line.lstrip()\n")]),
    'statement-line-strip()': ('additive:whitespace', [("    at = [n for n, line in enumerate(lines) if line.lstrip(' ') == MARKERS_STATED]\n    if len(at) != 1:\n        return [], [f'{len(at)} lines read {MARKERS_STATED!r}, not one']\n    indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))\n",
                                                        "    at = [n for n, line in enumerate(lines) if line.strip() == MARKERS_STATED]\n    if len(at) != 1:\n        return [], [f'{len(at)} lines read {MARKERS_STATED!r}, not one']\n    indent = ' ' * (len(lines[at[0]]) - len(lines[at[0]].lstrip()))\n")]),
    'statement-line-lstrip()': ('additive:whitespace', [("    at = [n for n, line in enumerate(lines) if line.lstrip(' ') == MARKERS_STATED]\n",
                                                         "    at = [n for n, line in enumerate(lines) if line.lstrip() == MARKERS_STATED]\n")]),
    'statement-line-substring': ('additive:statement', [("    at = [n for n, line in enumerate(lines) if line.lstrip(' ') == MARKERS_STATED]\n",
                                                         "    at = [n for n, line in enumerate(lines) if MARKERS_STATED in line]\n")]),
    'statement-line-prefix': ('additive:statement', [("    at = [n for n, line in enumerate(lines) if line.lstrip(' ') == MARKERS_STATED]\n",
                                                      "    at = [n for n, line in enumerate(lines) if line.lstrip(' ').startswith(MARKERS_STATED[:40])]\n")]),
    'statement-line-casefold': ('additive:case', [("    at = [n for n, line in enumerate(lines) if line.lstrip(' ') == MARKERS_STATED]\n",
                                                   "    at = [n for n, line in enumerate(lines) if line.lstrip(' ').casefold() == MARKERS_STATED.casefold()]\n")]),
}

MUTANTS.update({
    'ignore-slashes': ('additive:punctuation', norm("lambda s: s.replace('/', '')")),
    'ignore-hyphens': ('additive:punctuation', norm("lambda s: s.replace('-', '')")),
    'ignore-apostrophes': ('additive:punctuation', norm("lambda s: s.replace(\"'\", '').replace('\\u2019', '')")),
})

# The rows each named mutant must fail: the review's survivors and the punctuation classes, each
# killed by a narrower-drift row.
NAMED: dict[str, list[str]] = {
    'skip-bad-item-line': ['exception-bullet-after-the-items-in-testing', 'third-marker-without-backticks-in-testing'],
    'other-bullets-are-items': ['star-bullets-in-testing'],
    'lazy-wrap-joins(equivalent?)': ['lazy-wrap-in-testing'],
    'statement-line-casefold': ['statement-line-lower-case-in-testing'],
    'statement-line-substring': ['statement-line-quoted-in-testing'],
    'statement-line-prefix': ['statement-line-tail-changed-in-testing'],
    'statement-line-lstrip()': ['statement-line-tab-indented-items-follow-in-testing'],
    'drop-no-markers-line': ['no-markers-anywhere'],
    'ignore-parens-chars': ['parentheses-dropped-in-testing'],
    'ignore-slashes-hyphens': ['slash-dropped-in-pyproject', 'hyphen-dropped-in-testing'],
    'ignore-slashes': ['slash-dropped-in-pyproject'],
    'ignore-hyphens': ['hyphen-dropped-in-testing'],
    'ignore-apostrophes': ['curly-quote-in-testing'],
    'curly-to-straight-quotes': ['curly-quote-in-testing'],
    'ignore-parenthesised-text': ['parenthesised-phrase-changed-in-testing'],
    'ignore-after-last-sentence-period': ['sentence-after-the-last-in-testing'],
}


def load(mutations: list[tuple[str, str]]) -> dict:
    check = CHECK
    for old, new in mutations:
        if check.count(old) != 1:
            raise LookupError(f'{old!r} occurs {check.count(old)} times in the check')
        check = check.replace(old, new)
    ns: dict = {'re': re, 'tomllib': tomllib, 'pytest': pytest, 'Path': Path}
    exec(compile(check + REST, 'test_hygiene.py (mutant)', 'exec'), ns)
    return ns


def rows(ns: dict, name: str) -> list[tuple[str, dict]]:
    return [(p.id, p.values[0]) for m in ns[name].pytestmark if m.name == 'parametrize' for p in m.args[1]]


def outcomes(ns: dict) -> dict[str, bool]:
    """Each row's id and whether its test passes against this namespace's check."""
    check, planted = ns['marker_statement_violations'], ns['planted']
    out: dict[str, bool] = {}

    def run(expect_clean: bool, change: dict) -> bool:
        try:
            return (check(*planted(**change)) == []) == expect_clean
        except Exception:  # noqa: BLE001 - an error fails the row, as pytest would
            return False
    for rid, change in rows(ns, ACCEPTS):
        out[f'+{rid}'] = run(True, change)
    for table in (ROWS, NARROW):
        for rid, change in rows(ns, table):
            out[rid] = run(False, change)
    try:
        out['live'] = check(*REAL) == []
    except Exception:  # noqa: BLE001
        out['live'] = False
    return out


def main() -> int:
    base = outcomes(load([]))
    narrow = [rid for rid, _ in rows(load([]), NARROW)]
    red = [k for k, ok in base.items() if not ok]
    print(f'unmutated: {sum(not k.startswith("+") and k != "live" for k in base)} drift rows '
          f'({len(narrow)} narrower), {sum(k.startswith("+") for k in base)} accept rows, live test '
          f'{"passed" if base.get("live") else "failed"}, not passed: {red}')
    bad = 1 if red or not narrow else 0
    idle = [r for r in narrow if not any(r in kills for kills in NAMED.values())]
    unknown = sorted({r for kills in NAMED.values() for r in kills} - set(base))
    missing = sorted(set(NAMED) - set(MUTANTS))
    if idle or unknown or missing:
        print(f'narrower rows no mutant names: {idle}; named rows that do not exist: {unknown}; '
              f'named mutants not in the table: {missing}')
        bad += 1
    for mid, (kind, subs) in MUTANTS.items():
        try:
            got = outcomes(load(subs))
        except LookupError as stale:
            print(f'{mid}: STALE, {stale}')
            bad += 1
            continue
        killers = sorted(k for k, ok in got.items() if not ok)
        if mid in NAMED:
            survived = [r for r in NAMED[mid] if got.get(r, True)]
            broken = not got['+as-planted']
            if survived or broken:
                bad += 1
                print(f'{mid}: SURVIVED [{kind}]; named rows still passing {survived}, as-planted broken {broken}')
            else:
                print(f'{mid}: killed [{kind}] by {", ".join(NAMED[mid])}')
        elif killers:
            print(f'{mid}: killed [{kind}] by {", ".join(killers[:4])}{" …" if len(killers) > 4 else ""}')
        else:
            bad += 1
            print(f'{mid}: SURVIVED [{kind}]; no row fails')
    print(f'{len(MUTANTS)} mutants, {bad} not killed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
