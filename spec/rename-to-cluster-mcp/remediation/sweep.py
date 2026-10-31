# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Shared by the review-1 checkers: run pinning tests and a mutant sweep in both protocol eras.

A sweep is every `tests/mutants.py` case whose plant lands in the swept domain, found by evaluating
where each case's anchors sit, never by listing case ids: a namespace edit whose anchor overlaps one
of the named source regions (a function's body, an assignment, a call), or a repository edit into
one of the named repository files. Each case runs once with `CLUSTER_MCP_TEST_ERA` unset (the
handshake era) and once with it set to `modern`, so a target with no era parameter runs in both.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[3]
ERAS = {'legacy': None, 'modern': 'modern'}
PROBLEMS: list[str] = []

sys.path.insert(0, str(ROOT / 'tests'))
import mutants  # noqa: E402

# A source region: (namespace-relative file, first line, last line).
Region = tuple[str, int, int]


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


def source(file: str) -> str:
    """The text of a namespace-relative file (`core/deprecation.py`) as the installed members hold it."""
    member, _, rest = file.partition('/')
    return (Path(mutants.MEMBERS[member].__file__).parent / rest).read_text()


def namespace_files() -> list[str]:
    """Every Python file of every member, namespace-relative."""
    files = []
    for name, member in mutants.MEMBERS.items():
        base = Path(member.__file__).parent
        files += [f'{name}/{p.relative_to(base)}' for p in sorted(base.rglob('*.py')) if '__pycache__' not in p.parts]
    return files


def regions(predicate: Callable[[ast.AST], bool]) -> list[Region]:
    """Every node in the namespace for which `predicate` holds, as a region."""
    found = []
    for file in namespace_files():
        for node in ast.walk(ast.parse(source(file))):
            if predicate(node) and hasattr(node, 'lineno'):
                found.append((file, node.lineno, node.end_lineno or node.lineno))
    return found


def calls_to(*names: str) -> Callable[[ast.AST], bool]:
    """A predicate: a call of a function named one of `names`, or a definition of one."""
    def hit(node: ast.AST) -> bool:
        if isinstance(node, ast.Call):
            func = node.func
            return (isinstance(func, ast.Name) and func.id in names) or \
                (isinstance(func, ast.Attribute) and func.attr in names)
        return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    return hit


def assigns(*names: str) -> Callable[[ast.AST], bool]:
    """A predicate: an assignment to a module-level name in `names`."""
    def hit(node: ast.AST) -> bool:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        return any(isinstance(t, ast.Name) and t.id in names for t in targets)
    return hit


def cases_in(spans: Iterable[Region], repo_files: Sequence[str] = ()) -> list[str]:
    """Every case one of whose namespace anchors overlaps a span, or which plants into one of `repo_files`."""
    spans = list(spans)
    if not spans and not repo_files:
        sys.exit('sweep: an empty domain')
    picked: list[str] = []
    for case in mutants.CASES:
        hit = any(name in repo_files for name, _, _ in case.repo_edits)
        if case.file and not hit:
            text = source(case.file)
            for old, _ in case.edits:
                at = text.find(old)
                if at < 0:
                    continue
                first = text.count('\n', 0, at) + 1
                last = first + old.rstrip('\n').count('\n')
                if any(file == case.file and first <= end and last >= start for file, start, end in spans):
                    hit = True
                    break
        if hit:
            picked.append(case.id)
    return picked


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
                              env=env_for(era), capture_output=True, text=True, timeout=1800)
        killed = [line.split()[1].rstrip(':') for line in done.stdout.splitlines() if line.startswith('killed  ')]
        failed = [line[:300] for line in done.stdout.splitlines() if line.startswith('FAILED')]
        check(done.returncode == 0 and sorted(killed) == sorted(cases) and not failed,
              f'{era} era: {len(killed)}/{len(cases)} killed' + (f'; {failed}' if failed else ''))


def finish(label: str, cases: Sequence[str], equivalent: dict[str, str]) -> int:
    print(f'{label}: {len(cases)} cases swept in both eras: {", ".join(cases)}')
    print(f'{label}: equivalent, recorded, not run as cases:')
    for case, why in equivalent.items():
        print(f'  - {case}: {why}')
    if PROBLEMS:
        print(f'{label}: {len(PROBLEMS)} problem(s)')
        return 1
    print(f'{label}: ok')
    return 0
