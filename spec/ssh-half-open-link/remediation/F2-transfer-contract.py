"""Review cycle 1, F2: every statement of the Protocol's error contract says what may remain after a
lost transfer.

Run from anywhere in the worktree:

    uv run python -I spec/ssh-half-open-link/remediation/F2-transfer-contract.py

The finding's instance was `executor/base.py`'s `write`, `put` and `get`, whose Raises sections
still promised "nothing was written" or "nothing was transferred" for the exception types a lost
transfer now raises (`ssh.TransferLost`, a `ConnectionError` and so an `OSError`), after part of the
transfer may have landed. The defining property, evaluated on every live site rather than the lines
cited:

1. **Every docstring in the shipped packages** (`packages/*/src/**/*.py`, read by its syntax tree)
   that promises `nothing was written` or `nothing was transferred` also states the lost transfer
   in the same docstring (`partly made`). A new restatement of the promise without it fails here.
2. **The Protocol itself**: `Executor.write`, `Executor.put` and `Executor.get` in
   `executor/base.py` each name `ssh.TransferLost` and say the transfer may be partly made, in their
   Raises sections, and `write`'s body says a lost connection is the exception to "untouched".
3. **AGENTS.md §2**, which restates the Protocol, states `TransferLost` for `write`, and for `put`
   and `get`; and no paragraph of §2 or §3 promises `nothing was written` or `nothing was
   transferred` without `partly made` beside it.

The durable form of 1–2 for the Protocol is `tests/test_ssh_liveness.py`'s doc pin
(`test_liveness_texts_state_the_monitor`), which reads the same docstrings; this checker covers
every restatement besides.

Footprint: reads files; runs nothing.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

TOP = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True, cwd=Path(__file__).parent).stdout.strip())
PROMISES = ('nothing was written', 'nothing was transferred')
LOST = 'partly made'


def _flat(text: str) -> str:
    return ' '.join(text.split())


def _docstrings(path: Path) -> list[tuple[str, int, str]]:
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node)
            if doc:
                found.append((getattr(node, 'name', '<module>'), getattr(node, 'lineno', 1), _flat(doc)))
    return found


def _raises(doc: str) -> str:
    return doc[doc.index('Raises:'):] if 'Raises:' in doc else ''


def main() -> int:
    problems = []
    sources = sorted(TOP.glob('packages/*/src/**/*.py'))
    if not sources:
        problems.append('no package sources found')
    stated = 0
    for path in sources:
        for name, line, doc in _docstrings(path):
            if any(promise in doc for promise in PROMISES):
                stated += 1
                if LOST not in doc:
                    problems.append(f'{path.relative_to(TOP)}:{line} {name}: promises '
                                    f'{[p for p in PROMISES if p in doc]} and never states the lost transfer')
    if not stated:
        problems.append('no docstring states the promise at all, so check 1 proves nothing')
    base = {name: doc for name, _, doc in _docstrings(TOP / 'packages/cluster-mcp/src/cluster_mcp/core/executor/base.py')}
    for member in ('write', 'put', 'get'):
        raises = _raises(base.get(member, ''))
        if not ('TransferLost' in raises and LOST in raises):
            problems.append(f'executor/base.py {member}: its Raises section does not name TransferLost and a transfer '
                            'that may be partly made')
    if 'except a lost connection' not in base.get('write', '') and 'lost connection is the' not in base.get('write', ''):
        problems.append('executor/base.py write: its body says a failed transfer leaves the target untouched, with no '
                        'exception for a lost connection')
    agents = (TOP / 'AGENTS.md').read_text()
    section_2 = agents[agents.index('### 2. Executor Protocol'):agents.index('### 3.')]
    section_3 = agents[agents.index('### 3.'):agents.index('### 4.')]
    flat_2 = _flat(section_2)
    for part in ('raises `ssh.TransferLost`', "`put`'s remote target, or `get`'s local file, may be truncated"):
        if part not in flat_2:
            problems.append(f'AGENTS.md §2 does not state {part!r}')
    for title, section in (('§2', section_2), ('§3', section_3)):
        for paragraph in re.split(r'\n(?=- )|\n\n', section):
            flat = _flat(paragraph)
            if any(promise in flat for promise in PROMISES) and LOST not in flat:
                problems.append(f'AGENTS.md {title}: a paragraph promises nothing was written or transferred without '
                                f'the lost transfer: {flat[:120]!r}')
    print(f'{stated} docstrings state the promise; each, the Protocol and AGENTS.md §2/§3 checked')
    for problem in problems:
        print(f'FAILED  {problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
