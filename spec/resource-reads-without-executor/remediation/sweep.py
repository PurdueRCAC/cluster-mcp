# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Shared by the review-1 checkers: run pinning tests and a mutant sweep in both protocol eras.

A sweep is every `tests/mutants.py` case whose plant lands inside the named functions of
`src/rcac_mcp/middleware.py`, or whose edit replaces a named line, found by evaluating where each
case's anchor sits, not by listing case ids, plus any named extras. Each case runs once with `CLUSTER_MCP_TEST_ERA` unset (the
handshake era) and once with it set to `modern`, so a target with no era parameter runs in both.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
MIDDLEWARE = ROOT / 'src' / 'rcac_mcp' / 'middleware.py'
ERAS = {'legacy': None, 'modern': 'modern'}
PROBLEMS: list[str] = []


def check(ok: bool, what: str) -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {what}", flush=True)
    if not ok:
        PROBLEMS.append(what)


def env_for(era: str) -> dict[str, str]:
    env = dict(os.environ)
    env.pop('CLUSTER_MCP_TEST_ERA', None)
    if ERAS[era] is not None:
        env['CLUSTER_MCP_TEST_ERA'] = ERAS[era]
    return env


def spans(*names: str) -> list[tuple[str, int, int]]:
    """The (name, first line, last line) of each `Class.method` or module function in middleware.py."""
    tree = ast.parse(MIDDLEWARE.read_text())
    found: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = (node.lineno, node.end_lineno or node.lineno)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found[f'{node.name}.{item.name}'] = (item.lineno, item.end_lineno or item.lineno)
    missing = [name for name in names if name not in found]
    if missing:
        sys.exit(f'sweep: no {missing} in {MIDDLEWARE}')
    return [(name, *found[name]) for name in names]


def cases_in(*names: str) -> list[str]:
    """Every middleware.py case one of whose anchors overlaps one of the named functions."""
    sys.path.insert(0, str(ROOT / 'tests'))
    import mutants

    source = MIDDLEWARE.read_text()
    regions = spans(*names)
    picked: list[str] = []
    for case in mutants.CASES:
        if case.file != 'middleware.py':
            continue
        for old, _ in case.edits:
            at = source.find(old)
            if at < 0:
                continue
            first = source.count('\n', 0, at) + 1
            last = first + old.rstrip('\n').count('\n')
            if any(first <= end and last >= start for _, start, end in regions):
                picked.append(case.id)
                break
    return picked


def cases_editing(fragment: str, file: str = 'middleware.py') -> list[str]:
    """Every case in `file` one of whose edits replaces text holding `fragment`, which must be in `file` once."""
    sys.path.insert(0, str(ROOT / 'tests'))
    import mutants

    source = (ROOT / 'src' / 'rcac_mcp' / file).read_text()
    if source.count(fragment) != 1:
        sys.exit(f'sweep: {fragment!r} is in {file} {source.count(fragment)} times, expected once')
    return [case.id for case in mutants.CASES
            if case.file == file and any(fragment in old for old, _ in case.edits)]


def run_tests(tests: Sequence[str], count: int) -> None:
    for era in ERAS:
        done = subprocess.run(['uv', 'run', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', *tests], cwd=ROOT,
                              env=env_for(era), capture_output=True, text=True, timeout=600)
        tail = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else done.stderr[-300:]
        check(done.returncode == 0 and re.search(rf'\b{count} passed\b', tail) is not None and 'skipped' not in tail,
              f'the pinning tests, {era} era: {tail} (expected {count} passed, none skipped)')


def run_sweep(cases: Sequence[str], required: Sequence[str], equivalent: dict[str, str]) -> None:
    check(bool(cases), f'the sweep is not empty: {len(cases)} cases')
    absent = [case for case in required if case not in cases]
    check(not absent, f'the sweep holds every required case (missing: {absent})')
    clash = [case for case in equivalent if case in cases]
    check(not clash, f'no recorded equivalent mutant is a case (clashing: {clash})')
    for era in ERAS:
        done = subprocess.run([sys.executable, str(ROOT / 'tests' / 'mutants.py'), *cases], cwd=ROOT,
                              env=env_for(era), capture_output=True, text=True, timeout=600)
        killed = [line.split()[1].rstrip(':') for line in done.stdout.splitlines() if line.startswith('killed  ')]
        failed = [line[:300] for line in done.stdout.splitlines() if line.startswith('FAILED')]
        check(done.returncode == 0 and sorted(killed) == sorted(cases) and not failed,
              f'{era} era: {len(killed)}/{len(cases)} killed' + (f'; {failed}' if failed else ''))


def finish(label: str, cases: Sequence[str], equivalent: dict[str, str]) -> int:
    print(f'{label}: {len(cases)} cases swept in both eras; equivalent, recorded, not run as cases:')
    for case, why in equivalent.items():
        print(f'  - {case}: {why}')
    if PROBLEMS:
        print(f'{label}: {len(PROBLEMS)} problem(s)')
        return 1
    print(f'{label}: ok')
    return 0
