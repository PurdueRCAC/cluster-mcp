"""Review cycle 3, N3: no spec or review-finding id in the package or the suite, glued into a name included.

Run from anywhere in the worktree:

    uv run python -I spec/ssh-half-open-link/remediation/F9-glued-id-hygiene.py

Supersedes `remediation/F6-finding-id-hygiene.py` (review cycle 2, F-C), which stays as the record:
its second check requires the widened pattern to find exactly one line on `82b1f0e`, and the pattern
widened here also finds that tree's glued ids, so it reads a retired pattern.

The finding's instance: `tests/test_timeout_stop.py`'s `F3_SETTINGS`, a review-finding id from an
earlier cycle, which `\\b` could not see, since no boundary falls between `3` and `_`. The class: every
id of the kinds the rule names glued into a name, in capitals or, joined by an underscore, in lower
case. Swept, every `.py` file the check reads, and every file git tracks outside `spec/`: two names,
`F3_SETTINGS` (`tests/test_timeout_stop.py`, five lines) and `r1_violations`
(`tests/test_literal_args.py`, two lines, and its AGENTS.md § Testing entry), both renamed. Checked
four ways:

1. **The suite's check, widened, passes here**: `test_no_spec_ids_in_the_package_or_the_suite`,
   `test_spec_id_scan_covers_every_member`, `test_the_id_rule_is_stated_as_the_check_enforces_it` and
   every case of `test_spec_id_check_catches_planted_ids`, the glued cases among them, each passed.
2. **It is red on the reviewed tree**: the suite's pattern, run over every `.py` file of `packages/`
   and `tests/` as `f1fa641` holds them, finds exactly the seven glued lines above; the pattern as
   reviewed there finds none of them.
3. **No false positive on the tree's own text**: flake8 codes (`F401`), three digits (`F100`), hex
   (`0xF1`, `0xF1_MASK`), a checker's file name (`F1-…sh`), words (`F-Droid`, `R2D2`), lower-case
   names not glued (`f1 = open(…)`), and names such as `HTTP_2` and `SHA_P100` are not ids; the scan of
   this tree finds nothing.
4. **The rule says what the check enforces**: AGENTS.md § Testing and § Conventions each state the
   scope (every line of every `.py` file in the namespace's portions and directly in `tests/`), the
   glued forms, and the exclusions.

Exit 0 when all four hold. Footprint: one pytest child, under 300 MB, a few seconds.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOP = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True, cwd=Path(__file__).parent).stdout.strip())
sys.path.insert(0, str(TOP / 'tests'))
os.chdir(TOP)

import test_hygiene  # noqa: E402

REVIEWED = 'f1fa641'
# The glued lines on the reviewed tree, by file and line.
GLUED = {('tests/test_timeout_stop.py', n) for n in (471, 493, 524, 789, 830)} | \
        {('tests/test_literal_args.py', n) for n in (264, 736)}
AS_REVIEWED = re.compile(r'\b(?:[RPQ][0-9]{1,2}|F[0-9]{1,2}(?!-)|F-[A-Z])\b')
HYGIENE = 'tests/test_hygiene.py'
ROWS = ('test_no_spec_ids_in_the_package_or_the_suite', 'test_spec_id_scan_covers_every_member',
        'test_the_id_rule_is_stated_as_the_check_enforces_it')
PLANTED = 'test_spec_id_check_catches_planted_ids'
GLUED_CASES = ('finding-glued-before-a-name', 'requirement-glued-after-a-name', 'finding-letter-glued',
               'lower-case-glued-before-a-name', 'lower-case-glued-after-a-name', 'not-glued-ids')
LEGITIMATE = ('# noqa: E402, F401', 'colour = 0xF1', 'MASK = 0xF1_MASK', 'F100', 'an F-Droid build', 'R2D2',
              '(`F1-contribution-refusal.sh`, `F4-load-refusal.sh`)', 'f1 = open(name)', 'p2 = q3',
              'HTTP_2', 'SHA_P100', 'x_F401', 'f1x_y')
# What each statement of the rule must say: its scope, the glued forms and the exclusions.
STATED = ('every line of every `.py` file in each portion of the `cluster_mcp` namespace and directly in `tests/`',
          'not its subdirectories', 'code and strings as well as comments', 'an underscore is no shield',
          'in lower case where an underscore joins it to the name', 'Not ids: three or more digits (`F401`)',
          '(`0xF1`, `R2D2`, `F-Droid`)', 'followed by a hyphen', '`F1-contribution-refusal.sh`')


def suite_problems() -> list[str]:
    with tempfile.TemporaryDirectory(prefix='f9-hygiene-') as scratch:
        report = Path(scratch) / 'junit.xml'
        status = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={report}',
                                 *(f'{HYGIENE}::{row}' for row in ROWS), f'{HYGIENE}::{PLANTED}'],
                                cwd=TOP, timeout=300).returncode
        outcomes = {}
        if report.exists():
            for case in ET.parse(report).getroot().iter('testcase'):
                bad = {child.tag for child in case} & {'failure', 'error', 'skipped'}
                outcomes[case.get('name')] = 'passed' if not bad else sorted(bad)[0]
    problems = [f'{row}: {outcomes.get(row, "not collected")}' for row in ROWS if outcomes.get(row) != 'passed']
    for case in GLUED_CASES:
        if outcomes.get(f'{PLANTED}[{case}]') != 'passed':
            problems.append(f'{PLANTED}[{case}]: {outcomes.get(f"{PLANTED}[{case}]", "not collected")}')
    planted = {name for name in outcomes if name.startswith(PLANTED + '[')}
    problems += [f'{name}: {outcomes[name]}' for name in sorted(planted) if outcomes[name] != 'passed']
    if status != 0 and not problems:
        problems.append(f'pytest exited {status}')
    return problems


def reviewed_problems() -> list[str]:
    listed = subprocess.run(['git', 'ls-tree', '-r', '--name-only', REVIEWED, '--', 'packages', 'tests'],
                            cwd=TOP, capture_output=True, text=True, check=True).stdout.split()
    widened, before = set(), set()
    for name in (n for n in listed if n.endswith('.py')):
        text = subprocess.run(['git', 'show', f'{REVIEWED}:{name}'], cwd=TOP, capture_output=True, text=True,
                              check=True).stdout
        widened |= {(name, int(v.split(':')[1])) for v in test_hygiene.spec_id_violations(name, text)}
        before |= {(name, n) for n, line in enumerate(text.splitlines(), 1) if AS_REVIEWED.search(line)}
    problems = []
    if widened != GLUED:
        problems.append(f'on {REVIEWED} the suite\'s pattern found {sorted(widened)}, not the glued lines '
                        f'{sorted(GLUED)}')
    else:
        print(f'red on {REVIEWED}: {", ".join(f"{name}:{n}" for name, n in sorted(widened))}')
    if before & GLUED:
        problems.append(f'on {REVIEWED} the pattern as reviewed already found {sorted(before & GLUED)}')
    return problems


def tree_problems() -> list[str]:
    problems = [f'a legitimate text reads as an id: {text!r}' for text in LEGITIMATE
                if test_hygiene.spec_id_violations('legitimate', text)]
    files = [f for portion in test_hygiene.namespace_portions() for f in sorted(portion.rglob('*.py'))]
    files += sorted((TOP / 'tests').glob('*.py'))
    if not files:
        problems.append('no source files found to scan')
    problems += [v for f in files for v in test_hygiene.spec_id_violations(str(f), f.read_text())]
    return problems


def rule_problems() -> list[str]:
    agents = (TOP / 'AGENTS.md').read_text()
    testing = agents[agents.index('\n## Testing'):agents.index('\n## Packaging')]
    conventions = agents[agents.index('\n### Conventions (same-commit rules)'):]
    return [f'AGENTS.md {where} does not state: {phrase!r}'
            for where, text in (('§ Testing', testing), ('§ Conventions', conventions))
            for phrase in STATED if phrase not in ' '.join(text.split())]


def main() -> int:
    problems = suite_problems() + reviewed_problems() + tree_problems() + rule_problems()
    for problem in problems:
        print(f'FAILED  {problem}')
    print('ok' if not problems else f'{len(problems)} problems')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
