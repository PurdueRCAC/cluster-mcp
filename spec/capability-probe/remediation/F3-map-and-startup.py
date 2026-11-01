# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 1, F3: every part of AGENTS.md that lists the core's modules or says what runs at startup
describes the probe, and each member's row names what it declares.

    uv run python -I spec/capability-probe/remediation/F3-map-and-startup.py      from the worktree root

The review found § Repository map with no row for `core/probes.py`, its `__init__.py` row and the two
members' `capability` rows silent on the probe, and § Architecture & data flow saying one read happens
before any request. The property is evaluated from the code, not from a list of the lines found:

- every module of the core package that defines anything (a module that only re-exports, such as
  `executor/__init__.py`, is not a responsibility of its own) has a row in the map's core table, by its
  path (a `{a,b}` group counts for each);
- the `__init__.py` row names every method `MCPServerApp.run()` calls on itself, `_probe()` and
  `_served()` among them, and the `--skip-probes` flag;
- each installed member's `capability` row names every command its record declares (read from the
  loaded record, so a command added later must be named too);
- § Architecture & data flow names each step `run()` takes before the server serves: the site read
  (`/etc/agents.d`, `READ_TIMEOUT`), the probe (`core/probes.py`, `PROBE_TIMEOUT`, the modes it runs and
  skips in) and `create_mcp_server`.

Footprint: one process, no network, seconds.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from cluster_mcp.core.capabilities import installed

ROOT = Path.cwd()
CORE = ROOT / 'packages/cluster-mcp/src/cluster_mcp/core'


def section(text: str, heading: str) -> str:
    start = text.index(f'\n## {heading}\n')
    end = text.find('\n## ', start + 1)
    return text[start:end if end != -1 else len(text)]


def rows(table_text: str) -> dict[str, str]:
    """Each table row by the backticked name in its first cell; a `{a,b}` group gives a row for each."""
    out: dict[str, str] = {}
    for line in table_text.splitlines():
        cells = line.split('|')
        if len(cells) < 3 or not cells[1].strip().startswith('`'):
            continue
        name = cells[1].strip().strip('`')
        group = re.fullmatch(r'(.*)\{([^}]*)\}(.*)', name)
        names = [group[1] + part + group[3] for part in group[2].split(',')] if group else [name]
        for each in names:
            out[each] = line
    return out


def defines(path: Path) -> bool:
    module = ast.parse(path.read_text())
    return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or
               (isinstance(node, (ast.Assign, ast.AnnAssign)) and '__all__' not in ast.unparse(node))
               for node in module.body)


def main() -> int:
    bad: list[str] = []
    text = (ROOT / 'AGENTS.md').read_text()
    repo_map = section(text, 'Repository map')
    table = rows(repo_map)
    modules = sorted(str(p.relative_to(CORE)) for p in CORE.rglob('*.py') if '__pycache__' not in p.parts)
    for module in modules:
        if defines(CORE / module) and module not in table:
            bad.append(f'§ Repository map: no row for core/{module}')
    init_row = table.get('__init__.py', '')
    run = next(n for n in ast.walk(ast.parse((CORE / '__init__.py').read_text()))
               if isinstance(n, ast.FunctionDef) and n.name == 'run')
    called = sorted({n.func.attr for n in ast.walk(run) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                     and n.func.value.id == 'self' and n.func.attr.startswith('_')})
    for method in called:
        if f'`{method}()`' not in init_row:
            bad.append(f'§ Repository map: the __init__.py row does not name {method}(), which run() calls')
    if '`--skip-probes`' not in init_row:
        bad.append('§ Repository map: the __init__.py row does not name --skip-probes')
    loaded = installed()
    if not loaded:
        bad.append('no member is installed: the member rows cannot be checked')
    for each in loaded:
        name = each.capability.name
        row = table.get(f'cluster_mcp.{name}.capability', '')
        if not row:
            bad.append(f'§ Repository map: no row for cluster_mcp.{name}.capability')
        for command in each.capability.commands:
            if f'`{command}`' not in row:
                bad.append(f'§ Repository map: the cluster_mcp.{name}.capability row does not name `{command}`')
    flow = section(text, 'Architecture & data flow')
    for word in ('/etc/agents.d', 'READ_TIMEOUT', 'core/probes.py', 'PROBE_TIMEOUT', '`ssh`', '`local`', '`delegate`',
                 '--skip-probes', 'create_mcp_server'):
        if word not in flow:
            bad.append(f'§ Architecture & data flow does not name {word}')
    print(*bad, sep='\n', file=sys.stderr)
    print(f'F3-map-and-startup: {len(modules)} core modules, run() calls {len(called)} of its own methods, '
          f'{len(loaded)} members' + ('' if bad else ': ok'), file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
