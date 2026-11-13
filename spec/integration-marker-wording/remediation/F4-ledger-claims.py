"""Review cycle 1, finding 4: the claims the ledger lines this cycle adds or edits make about the code
and the history hold.

Run from the worktree root, after staging, through remediation/checks.sh (or alone):

    uv run --no-sync python -I spec/integration-marker-wording/remediation/F4-ledger-claims.py

The ledger files are `ROADMAP.md` and `issues/*.md`; the lines read are those the index adds against
the merge base with `origin/develop`. On them:

- every commit a line cites (seven or more hex digits in backticks) is one HEAD reaches;
- every repository path a line cites in backticks (`tests/…`, `spec/…`, `issues/…`, `bin/…`, an
  optional `:line` after it) exists in the index (a file only on another cycle's branch does not
  count);
- every `<path>`'s `<name>` pair names a top-level function, class or assignment in that file;
- every fixture a line calls session- or module-scoped (`… -scoped fixture (`<name>`, …`) is a
  fixture of that scope in `tests/`, and it launches through `SANDBOX`.

Exits 1 naming each failed claim. One process, git children only; under 100 MB.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', *args], capture_output=True, text=True, check=check)


def staged(name: str) -> str:
    return git('show', f':{name}').stdout


def added_lines() -> list[tuple[str, str]]:
    base = git('merge-base', 'HEAD', 'origin/develop').stdout.strip()
    diff = git('diff', '--cached', '-U0', '--no-renames', base, '--', 'ROADMAP.md', 'issues/').stdout
    lines, name = [], ''
    for line in diff.splitlines():
        if line.startswith('+++ b/'):
            name = line[6:]
        elif line.startswith('+') and not line.startswith('+++'):
            lines.append((name, line[1:]))
    return lines


def top_level(source: str) -> set[str]:
    names = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}
    return names


def wider_fixtures() -> dict[str, tuple[str, bool]]:
    """Every session- or module-scoped fixture in tests/: its scope and whether it launches through SANDBOX."""
    found = {}
    for path in git('ls-files', 'tests/*.py').stdout.split():
        tree = ast.parse(staged(path))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for deco in node.decorator_list:
                scope = next((kw.value.value for kw in getattr(deco, 'keywords', [])
                              if kw.arg == 'scope' and isinstance(kw.value, ast.Constant)), None)
                if scope in ('session', 'module'):
                    launches = any(isinstance(n, ast.Name) and n.id == 'SANDBOX' for n in ast.walk(node))
                    found[node.name] = (scope, launches)
    return found


def main() -> int:
    bad = []
    lines = added_lines()
    if not lines:
        bad.append('no ledger line added: the diff base or the index is not what the cycle expects')
    fixtures = wider_fixtures()
    for name, line in lines:
        for sha in re.findall(r'`([0-9a-f]{7,40})`', line):
            known = git('rev-parse', '--verify', '--quiet', f'{sha}^{{commit}}', check=False)
            if known.returncode != 0 or git('merge-base', '--is-ancestor', sha, 'HEAD', check=False).returncode != 0:
                bad.append(f'{name}: cites {sha}, which HEAD does not reach')
        for path in re.findall(r'`((?:tests|spec|issues|bin)/[\w./-]+?)(?::[\d-]+)?`', line):
            present = (git('ls-files', '--', path).stdout.strip() if path.endswith('/')
                       else git('cat-file', '-e', f':{path}', check=False).returncode == 0)
            if not present:
                bad.append(f'{name}: cites {path}, which is not in the index')
        for path, ident in re.findall(r"`((?:tests|bin)/[\w./-]+\.py)`'s `(\w+)`", line):
            if ident not in top_level(staged(path)):
                bad.append(f'{name}: says {path} has {ident}, which it does not define at top level')
        for scope, ident in re.findall(r'(session|module)-scoped fixture \(`(\w+)`', line):
            got = fixtures.get(ident)
            if got is None or got[0] != scope or not got[1]:
                bad.append(f'{name}: calls {ident} a {scope}-scoped fixture that launches; tests/ has {got}')
    for line in bad:
        print(f'ledger claims: {line}', file=sys.stderr)
    print(f'ledger claims: {len(lines)} added lines read, {"ok" if not bad else f"{len(bad)} failed"}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
