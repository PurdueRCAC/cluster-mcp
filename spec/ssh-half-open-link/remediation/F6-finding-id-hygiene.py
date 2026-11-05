"""Review cycle 2, F-C: no review-finding id, nor any spec id, in the package or the suite.

Run from anywhere in the worktree:

    uv run python -I spec/ssh-half-open-link/remediation/F6-finding-id-hygiene.py

The finding's instance was a comment in `tests/mutants.py` naming review cycle 1's first finding by
its id, which the suite's hygiene check (`tests/test_hygiene.py`, `SPEC_ID`) did not match: it knew
the requirement, phase and clarification ids only. The class is every id that restarts per feature
or per review cycle (`R`, `P`, `Q` and a review finding's `F` with its number or, as review cycle 2
writes them, a hyphen and a letter) in a comment, docstring or message of the package or the suite.
Checked four ways:

1. **The suite's check, widened, passes on this tree**: `test_no_spec_ids_in_the_package_or_the_suite`
   and every case of `test_spec_id_check_catches_planted_ids`, its finding-id cases among them, each
   reported passed.
2. **It is red on the reviewed tree**: the widened pattern, run over every `.py` file of `packages/`
   and `tests/` as the reviewed commit (`82b1f0e`) holds them, finds the one line the review cited
   and nothing else; the pattern as reviewed finds nothing there, so the check was blind to it.
3. **No false positive on the tree's own text**: flake8 codes (`F401`), hex (`0xF1`), a checker's
   file name (`F1-…sh`, which `tests/test_startup.py` cites) and a word such as `F-Droid` are not ids;
   the planted cases say so, and the scan of this tree finds nothing.
4. **The rule names them where it is stated**: AGENTS.md § Testing and § Conventions both name
   review-finding ids beside the spec ids, so the two restatements of the rule change together.

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

REVIEWED = '82b1f0e'
CITED = ('tests/mutants.py', 'Review cycle 1, F')
AS_REVIEWED = re.compile(r'\b[RPQ][0-9]{1,2}\b')
HYGIENE = 'tests/test_hygiene.py'
ROWS = ('test_no_spec_ids_in_the_package_or_the_suite', 'test_spec_id_scan_covers_every_member')
PLANTED = 'test_spec_id_check_catches_planted_ids'
FINDING_CASES = ('review-finding', 'review-finding-letter', 'not-finding-ids')
LEGITIMATE = ('# noqa: E402, F401', 'colour = 0xF1', '(`F1-contribution-refusal.sh`, `F4-load-refusal.sh`)',
              'an F-Droid build')


def suite_problems() -> list[str]:
    with tempfile.TemporaryDirectory(prefix='f6-hygiene-') as scratch:
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
    planted = {name for name in outcomes if name.startswith(PLANTED + '[')}
    for case in FINDING_CASES:
        if outcomes.get(f'{PLANTED}[{case}]') != 'passed':
            problems.append(f'{PLANTED}[{case}]: {outcomes.get(f"{PLANTED}[{case}]", "not collected")}')
    problems += [f'{name}: {outcomes[name]}' for name in sorted(planted) if outcomes[name] != 'passed']
    if status != 0 and not problems:
        problems.append(f'pytest exited {status}')
    return problems


def reviewed_problems() -> list[str]:
    listed = subprocess.run(['git', 'ls-tree', '-r', '--name-only', REVIEWED, '--', 'packages', 'tests'],
                            cwd=TOP, capture_output=True, text=True, check=True).stdout.split()
    widened, before = [], []
    for name in (n for n in listed if n.endswith('.py')):
        text = subprocess.run(['git', 'show', f'{REVIEWED}:{name}'], cwd=TOP, capture_output=True, text=True,
                              check=True).stdout
        widened += [(name, v) for v in test_hygiene.spec_id_violations(name, text)]
        before += [(name, n) for n, line in enumerate(text.splitlines(), 1) if AS_REVIEWED.search(line)]
    problems = []
    if [name for name, _ in widened] != [CITED[0]] or CITED[1] not in widened[0][1]:
        problems.append(f'on {REVIEWED} the widened check found {[v for _, v in widened]}, not the one cited line')
    else:
        print(f'red on {REVIEWED}: {widened[0][1]}')
    if before:
        problems.append(f'on {REVIEWED} the reviewed pattern already found {before}, so it was not blind')
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
    return [f'AGENTS.md {where} states the id rule without review-finding ids'
            for where, text in (('§ Testing', testing), ('§ Conventions', conventions))
            if 'review-finding id' not in ' '.join(text.split())]


def main() -> int:
    problems = suite_problems() + reviewed_problems() + tree_problems() + rule_problems()
    for problem in problems:
        print(f'FAILED  {problem}')
    print('ok' if not problems else f'{len(problems)} problems')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
