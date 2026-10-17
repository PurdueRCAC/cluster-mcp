"""R8's edit rule: outside the internals-bound list, existing tests are not edited.

Usage, from the repository root: python edits.py <base-commit>

Compares the working tree's `tests/*.py` with the same files at `<base-commit>` (the cycle's
merge-base with develop, so a rebase onto a newer develop is not counted as this cycle's edit):

- the modules this cycle rewrites (the harness, the mutation table, and the two older modules that
  read the FastMCP server API) may change freely;
- `tests/test_hygiene.py` may change only the stack-import check (`STACK`, `IMPORTERS` and the
  functions that read imports) and add statements; every other top-level statement, every `test_*`
  function with its decorators among them, must be byte-identical, and no import may be removed;
- every other module present at the base, `conftest.py` included, may only gain lines: no deleted or
  changed line, and the file must still exist.

New modules are unrestricted (added tests are allowed).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

# The modules this cycle rewrites. The other internals-bound modules (test_exec_mode.py,
# test_executors.py, test_tokens.py, test_mutations.py) need no edit on the new stack, so they are
# held to additions only like everything else; mutants.py is free because a moved anchor is
# re-planted in place, and controls.py/run.sh hold every changed case to a reason in a commit body.
INTERNALS_BOUND = frozenset({'harness.py', 'mutants.py', 'test_registry.py', 'test_instructions.py'})
HYGIENE = 'test_hygiene.py'
HYGIENE_MAY_CHANGE = frozenset({'STACK', 'IMPORTERS', '_literal', '_imported_name', 'stack_import_violations',
                                '__doc__'})


def top_level(source: str) -> tuple[dict[str, str], set[str]]:
    """Map each top-level statement's key to its source text; return (named statements, imports)."""
    tree = ast.parse(source)
    named: dict[str, str] = {}
    imports: set[str] = set()
    for index, node in enumerate(tree.body):
        text = ast.get_source_segment(source, node) or ''
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Decorators sit outside the node's own segment; include them.
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            text = '\n'.join(source.splitlines()[start - 1:node.end_lineno])
            named[node.name] = text
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.add(text)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            named[node.targets[0].id] = text
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            named[node.target.id] = text
        elif index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            named['__doc__'] = text
        else:
            named[f'<statement {text[:60]!r}>'] = text
    return named, imports


def hygiene_violations(base: str, head: str, filename: str = HYGIENE) -> list[str]:
    """Every top-level change to test_hygiene.py outside the stack-import check; empty means allowed."""
    base_named, base_imports = top_level(base)
    head_named, head_imports = top_level(head)
    violations = [f'{filename}: import removed or changed: {imp!r}' for imp in sorted(base_imports - head_imports)]
    for key, text in base_named.items():
        if key in HYGIENE_MAY_CHANGE:
            continue
        if key not in head_named:
            violations.append(f'{filename}: {key} removed')
        elif head_named[key] != text:
            violations.append(f'{filename}: {key} changed')
    return violations


def additions_only_violations(diff: str, filename: str) -> list[str]:
    """Every removed or changed line in a unified diff of `filename`; empty means it only gained lines."""
    return [f'{filename}: line removed or changed: {line[1:80]!r}' for line in diff.splitlines()
            if line.startswith('-') and not line.startswith(('--- a/', '--- /dev/null'))]


def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    base = sys.argv[1]
    names = [Path(p).name for p in git('ls-tree', '--name-only', f'{base}:tests').split() if p.endswith('.py')]
    violations: list[str] = []
    for name in sorted(names):
        path = Path('tests') / name
        if name in INTERNALS_BOUND:
            continue
        if not path.exists():
            violations.append(f'{name}: removed')
            continue
        if name == HYGIENE:
            violations += hygiene_violations(git('show', f'{base}:tests/{name}'), path.read_text())
        else:
            violations += additions_only_violations(git('diff', base, '--', str(path)), name)
    for v in violations:
        print(f'edits: {v}', file=sys.stderr)
    print(f'edits: {len(names)} base test files checked, {len(violations)} violations', file=sys.stderr)
    return 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())
