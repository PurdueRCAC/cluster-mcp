"""R5 gate: the existing timeout tests, and everything they assert through, are unchanged and pass.

Run from the worktree root:  uv run python -I spec/timeout-process-cleanup/verify/r5-timeout-tests-kept.py

1. The tests: every top-level test function in the three files R5 names whose name holds `timeout`.
2. What they assert through: every module-level name (function, class, assignment) the tests refer
   to, followed transitively through the bodies of what it finds, in the same file, and, for a name
   imported `from test_x import name`, in `tests/test_x.py`. Each is compared at `BASE` and in the
   working tree by its AST (line numbers ignored). A change, or a missing name, is red.
   `tests/conftest.py` is not compared: its `sudo` stand-in changes on purpose (R6 asks it to relay
   as sudo does), and the rows are run below against the new one.
   **One change is allowed, by the GOAL's Q6:** `test_a_timeout_drains_what_follows_the_term` may
   assert the `signal` requests sent at a timeout as `['TERM', 'KILL']` instead of `['TERM']`. The
   gate checks that test against `BASE`'s text with exactly that substitution made (or with none),
   so any other change to it, its result assertions included, is red.
3. The rows: the node ids the tests collect at `BASE` (in a scratch copy of `BASE`'s tree) and in the
   working tree must be the same set, so no parametrization was dropped; then every row must pass in
   the working tree (a skip is red: a row that did not run proves nothing).

Footprint: one `uv sync` of the scratch copy (cache-backed) and one pytest child at a time (each row
starts at most a sandbox, a login bash and a `sleep`; an ssh row adds one in-process server), under
400 MB. Measured on the prototype: about 40 s, the sync included.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

BASE = 'c8843b2'
FILES = ('tests/test_executors.py', 'tests/test_launch.py', 'tests/test_ssh_exec.py')
# The one assertion change GOAL Q6 rules for R5: (file, function) -> (text at BASE, ruled text).
RULED = {('tests/test_ssh_exec.py', 'test_a_timeout_drains_what_follows_the_term'):
         ("assert [name for name, _ in sent] == ['TERM'] and sent[0][1] < 0.5, sent",
          "assert [name for name, _ in sent] == ['TERM', 'KILL'] and sent[0][1] < 0.5, sent")}


def ruled(name: str, ident: str, node: ast.AST, source: str) -> str | None:
    """The AST dump `ident` may have in the working tree by Q6's ruling, or None when none applies."""
    if (name, ident) not in RULED:
        return None
    old, new = RULED[name, ident]
    first = min([node.lineno, *(d.lineno for d in getattr(node, 'decorator_list', []))])
    text = '\n'.join(source.splitlines()[first - 1:node.end_lineno])  # decorators included
    if text.count(old) != 1:
        raise SystemExit(f'{name}::{ident}: the ruled assertion is not in its {BASE} text; the gate is wrong')
    return ast.dump(ast.parse(text.replace(old, new)).body[0])


def definitions(source: str) -> tuple[dict[str, ast.AST], dict[str, str]]:
    """Each module-level definition's node by name, and each `from test_x import name`'s module."""
    nodes: dict[str, ast.AST] = {}
    imported: dict[str, str] = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nodes[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        nodes[name.id] = node
        elif isinstance(node, ast.ImportFrom) and (node.module or '').startswith('test_'):
            for alias in node.names:
                imported[alias.asname or alias.name] = f'tests/{node.module}.py'
    return nodes, imported


def referenced(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def source_at(name: str, rev: str | None) -> str:
    if rev is None:
        with open(name, encoding='utf-8') as handle:
            return handle.read()
    return subprocess.run(['git', 'show', f'{rev}:{name}'], check=True, capture_output=True, text=True).stdout


def collect(cwd: str, env: dict[str, str], tests: list[str]) -> set[str]:
    out = subprocess.run(['uv', 'run', '--no-sync', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider', *tests],
                         cwd=cwd, env=env, capture_output=True, text=True).stdout
    return {line.strip() for line in out.splitlines() if '::' in line}


def main() -> int:
    problems: list[str] = []
    tests: list[str] = []
    files = {rev: {} for rev in (BASE, None)}

    def defs(name: str, rev: str | None) -> tuple[dict[str, ast.AST], dict[str, str]]:
        if name not in files[rev]:
            files[rev][name] = definitions(source_at(name, rev))
        return files[rev][name]

    seen: set[tuple[str, str]] = set()
    queue: list[tuple[str, str]] = []
    for name in FILES:
        before, _ = defs(name, BASE)
        found = [f for f, node in before.items()
                 if f.startswith('test_') and 'timeout' in f and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if not found:
            problems.append(f'{name}: no timeout test found at {BASE}; the selection is wrong')
        tests += [f'{name}::{f}' for f in sorted(found)]
        queue += [(name, f) for f in found]
    while queue:
        name, ident = queue.pop()
        if (name, ident) in seen:
            continue
        seen.add((name, ident))
        before, imported = defs(name, BASE)
        if ident in imported:
            queue.append((imported[ident], ident))
            continue
        if ident not in before:
            continue  # a builtin, a parameter, or a name from a package: not the tests' own
        after, _ = defs(name, None)
        if ident not in after:
            problems.append(f'{name}::{ident} was removed')
        elif ast.dump(after[ident]) not in (ast.dump(before[ident]),
                                            ruled(name, ident, before[ident], source_at(name, BASE))):
            problems.append(f'{name}::{ident} changed since {BASE}'
                            + (' beyond the one assertion Q6 rules' if (name, ident) in RULED else ''))
        queue += [(name, ref) for ref in referenced(before[ident])]
    if problems:
        print('\n'.join(problems))
        return 1
    env = dict(os.environ)
    for key in ('VIRTUAL_ENV', 'UV_PROJECT', 'UV_PROJECT_ENVIRONMENT'):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='tpc-r5-') as scratch:
        archive = subprocess.run(['git', 'archive', BASE], check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', scratch], input=archive, check=True)
        subprocess.run(['uv', 'sync', '--locked', '--quiet'], cwd=scratch, env=env, check=True)
        then = collect(scratch, env, tests)
    now = collect(os.getcwd(), env, tests)
    if not then or then != now:
        problems.append(f'collected rows differ from {BASE}: missing {sorted(then - now)}, new {sorted(now - then)}')
    with tempfile.TemporaryDirectory() as scratch:
        report = os.path.join(scratch, 'junit.xml')
        code = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                               f'--junitxml={report}', *tests]).returncode
        outcomes = []
        for case in ET.parse(report).getroot().iter('testcase'):
            tags = {child.tag for child in case}
            outcomes.append('passed' if not tags & {'failure', 'error', 'skipped'} else '/'.join(sorted(tags)))
    if len(outcomes) != len(now) or any(outcome != 'passed' for outcome in outcomes):
        problems.append(f'{outcomes.count("passed")} of {len(now)} collected rows passed')
    print('\n'.join(problems) or f'R5: {len(tests)} timeout tests and {len(seen)} names unchanged since {BASE}, '
                                 f'{len(now)} rows, every one passed')
    return 1 if problems or code else 0


if __name__ == '__main__':
    sys.exit(main())
