# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""No core module names a capability member: not in an import, not in a string.

    uv run --no-project python spec/capability-extras/verify/imports.py p1|p2      from the worktree root

p1 tolerates violations in `core/resources.py` alone (the storage handler moves to the RCAC member
in p2); p2 tolerates none.

The members are read from the tree, not pinned: every `packages/*/src/cluster_mcp/<name>/` but the
core's is a member package `cluster_mcp.<name>`, and its `pyproject.toml` names its distribution.
Every `.py` file under the core's `src/cluster_mcp/core/` is parsed; a violation is
- an `import` or `from … import` of a member package or anything below it, at any depth in the file
  (a function-local import counts, as `resources.py` had one);
- a `from cluster_mcp import <member>`;
- a relative import that resolves, against the file's own package, to a member (`from ..slurm
  import tools` from `core/`: PEP 420 portions resolve relatively across distributions);
- any string constant naming a member package (`cluster_mcp.<member>`, dotted or as a path
  `cluster_mcp/<member>`), a member relative to the namespace (`.slurm.tools`), a bare member name
  (`'rcac'`), a prefix for building one (`'cluster_mcp.'`), or a member distribution: how
  `importlib.import_module`, `__import__`, an entry-point lookup or a special case would reach one;
- a walk of the namespace (`cluster_mcp.__path__`, `pkgutil.iter_modules`, `walk_packages`).
Comments and docstrings are prose, not code, and are not scanned; every other string constant is.
The scan is checked against controls first (each must be caught), so a scan that sees nothing fails.
Footprint: one process, no network, under 100 MB.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path('.')
CORE = ROOT / 'packages' / 'cluster-mcp' / 'src' / 'cluster_mcp' / 'core'


def members() -> tuple[set[str], set[str]]:
    packages, dists = set(), set()
    for pkg in sorted((ROOT / 'packages').glob('*/src/cluster_mcp/*/')):
        if pkg.name == 'core' or pkg.name == '__pycache__':
            continue
        packages.add(pkg.name)
        meta = tomllib.loads((pkg.parents[2] / 'pyproject.toml').read_text())
        dists.add(meta['project']['name'])
    return packages, dists


def package_of(where: str) -> list[str]:
    """The package a file's relative imports resolve against, as parts (`['cluster_mcp', 'core', …]`)."""
    parts = Path(where).with_suffix('').parts
    if 'cluster_mcp' not in parts:
        return ['cluster_mcp', 'core']
    parts = list(parts[parts.index('cluster_mcp'):])
    return parts if parts[-1] == '__init__' and parts.pop() else parts[:-1]


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f'{dotted(node.value)}.{node.attr}'
    return ''


def violations(source: str, where: str, packages: set[str], dists: set[str]) -> list[str]:
    bad = []
    names = '|'.join(sorted(map(re.escape, packages)))
    named = re.compile(rf'cluster_mcp[./]({names})\b')
    relative = re.compile(rf'^\.+({names})\b')
    dist_named = re.compile('|'.join(rf'(?<![\w-]){re.escape(d)}(?![\w-])' for d in sorted(dists)))
    tree = ast.parse(source, where)
    prose = {id(n.body[0].value) for n in ast.walk(tree)
             if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
             and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    package = package_of(where)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if named.match(alias.name):
                    bad.append(f'{where}:{node.lineno}: imports {alias.name}')
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ''
            if node.level:
                base = package[:len(package) - (node.level - 1)] if node.level - 1 <= len(package) else []
                mod = '.'.join(base + ([mod] if mod else []))
            if named.match(mod):
                bad.append(f'{where}:{node.lineno}: imports from {mod}')
            elif mod == 'cluster_mcp' and any(a.name in packages for a in node.names):
                bad.append(f'{where}:{node.lineno}: from cluster_mcp imports a member')
        elif isinstance(node, ast.Attribute) and node.attr == '__path__' and dotted(node.value) == 'cluster_mcp':
            bad.append(f'{where}:{node.lineno}: walks the cluster_mcp namespace')
        elif isinstance(node, ast.Call) and dotted(node.func).split('.')[-1] in ('iter_modules', 'walk_packages'):
            bad.append(f'{where}:{node.lineno}: walks packages ({dotted(node.func)})')
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose:
            v = node.value
            if named.search(v):
                bad.append(f'{where}:{node.lineno}: a string names {named.search(v).group(0)}')
            elif relative.match(v):
                bad.append(f'{where}:{node.lineno}: a string names {v!r}, a member relative to the namespace')
            elif v in packages:
                bad.append(f'{where}:{node.lineno}: a string is the member name {v!r}')
            elif v.endswith('cluster_mcp.') or v.endswith('cluster_mcp/'):
                bad.append(f'{where}:{node.lineno}: a string {v!r} builds a name under the namespace')
            elif dists and dist_named.search(v):
                bad.append(f'{where}:{node.lineno}: a string names {dist_named.search(v).group(0)}')
    return bad


CONTROLS = (
    'from cluster_mcp.{m} import tools',
    'import cluster_mcp.{m}.tools as t',
    'def f():\n    from cluster_mcp.{m}.tools import x\n',
    'from cluster_mcp import {m}',
    'from ..{m} import tools',
    'from .. import {m}',
    'def f():\n    from ..{m}.tools import resolve_storage_paths\n',
    'import importlib\nimportlib.import_module("cluster_mcp.{m}.tools")',
    'import importlib\nimportlib.import_module(".{m}.tools", "cluster_mcp")',
    'x = __import__("cluster_mcp.{m}")',
    'x = "cluster_mcp." + "{m}"',
    'import cluster_mcp, pkgutil\nx = list(pkgutil.iter_modules(cluster_mcp.__path__))',
    'if c.name == "{m}":\n    pass',
    'NAME = "{d}"',
    '"""Prose."""\nX = 1\nY = "cluster_mcp.{m}"',
)


def main() -> int:
    phase = sys.argv[1] if len(sys.argv) == 2 else ''
    if phase not in ('p1', 'p2'):
        sys.exit('usage: imports.py p1|p2')
    packages, dists = members()
    if not packages or not dists:
        sys.exit('imports: found no member package: the scan would be blind')
    for m, d in zip(sorted(packages), sorted(dists)):
        for c in CONTROLS:
            if not violations(c.format(m=m, d=d), str(CORE / 'control.py'), packages, dists):
                sys.exit(f'imports: the control {c.format(m=m, d=d)!r} was not caught: the scan is blind')
    files = sorted(CORE.rglob('*.py'))
    if len(files) < 10:
        sys.exit(f'imports: only {len(files)} core files found under {CORE}')
    bad = [v for f in files for v in violations(f.read_text(), str(f), packages, dists)
           if not (phase == 'p1' and f == CORE / 'resources.py')]
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'imports: ok ({len(files)} core files; members {sorted(packages)})', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
