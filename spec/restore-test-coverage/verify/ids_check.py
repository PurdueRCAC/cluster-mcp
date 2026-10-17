"""Check a pytest JUnit report against the test ids the phase gates require.

Usage: python ids_check.py <report.xml> <n>

Every id in ids/P0..P<n>.txt must appear as a testcase that passed: no failure, error or skipped
child. Nothing anywhere in the report may be skipped, failed or errored. Reading the JUnit report,
not the terminal output, means a test that prints "PASSED tests/…" cannot satisfy the gate.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent


def node_id(case: ET.Element) -> str:
    # pytest writes classname "tests.test_x" and name "test_y[param]" for tests/test_x.py::test_y[param].
    module = case.get('classname', '').split('.')
    return '/'.join(module[:-1] + [module[-1] + '.py']) + '::' + case.get('name', '')


def main() -> int:
    report, n = sys.argv[1], int(sys.argv[2])
    cases = list(ET.parse(report).getroot().iter('testcase'))
    outcome: dict[str, str] = {}
    problems: list[str] = []
    for case in cases:
        nid = node_id(case)
        bad = [child.tag for child in case if child.tag in ('failure', 'error', 'skipped')]
        if nid in outcome:
            problems.append(f'{nid}: reported twice')
        outcome[nid] = bad[0] if bad else 'passed'
        if bad:
            problems.append(f'{nid}: {", ".join(bad)}')
    for i in range(n + 1):
        for line in (HERE / 'ids' / f'P{i}.txt').read_text().splitlines():
            if not line or line.startswith('#'):
                continue
            state = outcome.get(f'tests/{line}')
            if state is None:
                problems.append(f'tests/{line}: not in the report')
            elif state != 'passed':
                problems.append(f'tests/{line}: {state}')
    if not cases:
        problems.append('the report holds no testcase')
    for p in problems:
        print(f'ids_check: {p}', file=sys.stderr)
    print(f'ids_check: {len(cases)} testcases, {len(problems)} problems', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
