"""Check a pytest JUnit report against the baseline ids and the ids the phase gates require.

Usage: python ids_check.py <report.xml> <baseline-ids.txt> <n>

`baseline-ids.txt` holds every id collected at 3d010ec (`tests/x.py::test_y[param]`, one per
line), derived live by the gate from an archive of that commit. Every one of them, and every id in
ids/P1..P<n>.txt, must appear in the report as a testcase that passed: no failure, error or
skipped child. Nothing anywhere in the report may be skipped, failed or errored, and no id may be
reported twice. Reading the JUnit report, not the terminal, means a test that prints
"PASSED tests/…" cannot satisfy the gate.
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


def phase_ids(n: int) -> list[str]:
    ids: list[str] = []
    for i in range(1, n + 1):
        for line in (HERE / 'ids' / f'P{i}.txt').read_text().splitlines():
            if line and not line.startswith('#'):
                ids.append(f'tests/{line}')
    return ids


def problems(report_xml: str, required: list[str]) -> tuple[int, list[str]]:
    """Return (testcase count, every problem); an empty list means the report satisfies `required`."""
    root = ET.fromstring(report_xml)
    cases = list(root.iter('testcase'))
    outcome: dict[str, str] = {}
    found: list[str] = []
    for case in cases:
        nid = node_id(case)
        bad = [child.tag for child in case if child.tag in ('failure', 'error', 'skipped')]
        if nid in outcome:
            found.append(f'{nid}: reported twice')
        outcome[nid] = bad[0] if bad else 'passed'
        if bad:
            found.append(f'{nid}: {", ".join(bad)}')
    for nid in required:
        state = outcome.get(nid)
        if state is None:
            found.append(f'{nid}: not in the report')
        elif state != 'passed':
            found.append(f'{nid}: {state}')
    if not cases:
        found.append('the report holds no testcase')
    return len(cases), found


def main() -> int:
    report, baseline, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    base = [line.strip() for line in Path(baseline).read_text().splitlines() if line.strip()]
    if not base:
        print('ids_check: the baseline id list is empty', file=sys.stderr)
        return 1
    count, found = problems(Path(report).read_text(), base + phase_ids(n))
    for p in found:
        print(f'ids_check: {p}', file=sys.stderr)
    print(f'ids_check: {count} testcases, {len(base)} baseline ids, {len(found)} problems', file=sys.stderr)
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
