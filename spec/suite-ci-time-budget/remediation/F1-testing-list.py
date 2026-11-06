# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Class checker for review cycle 1, F-A: § Testing's per-module list is complete and current.

Run from the cycle worktree root, after staging (it reads the index, as the frozen gate does):

    UV_PYTHON=3.14 uv run -q python -I spec/suite-ci-time-budget/remediation/F1-testing-list.py

The class: the list under "Every module is built around pure check functions" in AGENTS.md
§ Testing names every collected test module (`tests/test_*.py`), each bullet names every marker the
module's tests carry, and every public `*_violations` the module defines (a leading underscore marks
a helper private to the module); and no name a bullet gives has gone stale: a backticked
`*_violations` is defined by the module or by a file the bullet names by path, and every other
backticked identifier with an underscore or a capital (`name` or `name()`) still occurs, as a word,
in some tracked `.py`, `.sh`, `.yml`, `.toml` or `.cfg` file outside `spec/`.

`--controls` runs the planted shapes each refusal must catch against the staged text, then exits.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys

MARKERS = ('unit', 'integration')


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], check=True, capture_output=True, text=True).stdout


def staged_modules() -> list[str]:
    out = subprocess.run(['git', 'ls-files', '--cached', 'tests/'], check=True, capture_output=True, text=True).stdout
    return sorted(n for n in out.splitlines() if re.fullmatch(r'tests/test_[^/]+\.py', n))


def module_list(agents: str) -> dict[str, list[str]]:
    """Each `  - `tests/...`` bullet of § Testing's per-module list, by path; a path listed twice
    keeps every bullet."""
    section = re.search(r'^## Testing\n(.*?)(?=^## )', agents, re.M | re.S)
    assert section, 'no § Testing'
    lead = re.search(r'^- The suite pins the coupled core.*?(?=^- )', section.group(1), re.M | re.S)
    assert lead, 'no per-module list in § Testing'
    bullets: dict[str, list[str]] = {}
    for bullet in re.split(r'^  - ', lead.group(0), flags=re.M)[1:]:
        head = re.match(r'`(tests/[^`]+)`', bullet)
        if head:
            bullets.setdefault(head.group(1), []).append(bullet)
    return bullets


def defined(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names |= {t.id for t in targets if isinstance(t, ast.Name)}
    return names


def markers_of(source: str) -> set[str]:
    return {m for m in MARKERS if re.search(rf'pytest\.mark\.{m}\b', source)}


def occurs(word: str) -> bool:
    """`word` occurs as a word in a tracked code or configuration file (the index, as staged)."""
    return subprocess.run(['git', 'grep', '--cached', '-q', '-w', '-e', word, '--', '*.py', '*.sh', '*.yml',
                           '*.toml', '*.cfg', ':(exclude)spec/'], capture_output=True).returncode == 0


def bullet_violations(name: str, bullet: str, source: str, other_sources: dict[str, str], occurs=occurs) -> list[str]:
    found = []
    head = bullet.split(':', 1)[0]
    for marker in sorted(markers_of(source)):
        if f'`{marker}`' not in head:
            found.append(f'{name}: the bullet does not name the marker `{marker}`')
    names = defined(source)
    for check in sorted(n for n in names if n.endswith('_violations') and not n.startswith('_')):
        if f'`{check}`' not in bullet:
            found.append(f'{name}: the bullet does not name `{check}`')
    elsewhere = set().union(*(defined(s) for p, s in other_sources.items() if f'`{p}`' in bullet)) if other_sources else set()
    for check in sorted(set(re.findall(r'`(\w+_violations)`', bullet))):
        if check not in names and check not in elsewhere:
            found.append(f'{name}: the bullet names `{check}`, which neither it nor a file the bullet names defines')
    words = {w for w in re.findall(r'`([A-Za-z_]\w*)(?:\(\))?`', bullet)
             if not w.endswith('_violations') and ('_' in w or w != w.lower())}
    for word in sorted(words):
        if not occurs(word):
            found.append(f'{name}: the bullet names `{word}`, which no tracked code holds')
    return found


def list_violations(agents: str, modules: dict[str, str], other_sources: dict[str, str]) -> list[str]:
    bullets = module_list(agents)
    found = []
    for name in sorted(modules):
        if name not in bullets:
            found.append(f'{name}: no bullet in § Testing')
            continue
        if len(bullets[name]) > 1:
            found.append(f'{name}: {len(bullets[name])} bullets in § Testing')
        found += bullet_violations(name, bullets[name][0], modules[name], other_sources)
    for name in sorted(set(bullets) - set(modules)):
        if re.fullmatch(r'tests/test_[^/]+\.py', name):
            found.append(f'{name}: a bullet for a module that does not exist')
    return found


def sources() -> tuple[str, dict[str, str], dict[str, str]]:
    agents = staged('AGENTS.md')
    modules = {name: staged(name) for name in staged_modules()}
    paths = set(re.findall(r'`((?:bin|tests|packages)/[\w/.-]+\.py)`', agents))
    others = {}
    for p in sorted(paths):
        try:
            others[p] = staged(p)
        except subprocess.CalledProcessError:
            pass
    return agents, modules, others


def controls(agents: str, modules: dict[str, str], others: dict[str, str]) -> int:
    failures = []

    def expect(label: str, violations: list[str], fragment: str) -> None:
        if not any(fragment in v for v in violations):
            failures.append(f'control {label}: expected a line with {fragment!r}, got {violations}')

    target = 'tests/test_suite_parts.py'
    line = next(l for l in agents.splitlines() if l.startswith(f'  - `{target}`'))
    expect('bullet dropped', list_violations(agents.replace(line, '  - `tests/elsewhere.py`: x'), modules, others),
           f'{target}: no bullet')
    expect('marker dropped', list_violations(agents.replace(line, line.replace('`unit`', 'unit', 1)), modules, others),
           'marker `unit`')
    expect('check dropped', list_violations(agents.replace('`suite_part_violations`', 'the part check', 1), modules, others),
           '`suite_part_violations`')
    expect('stale check', list_violations(agents.replace('`list_violations`', '`lists_violations`', 1), modules, others),
           '`lists_violations`, which neither')
    expect('stale name', list_violations(agents.replace('`workflow_commands`', '`workflow_command_list`', 1), modules,
                                         others), '`workflow_command_list`, which no tracked code holds')
    expect('private check named', list_violations(agents, {**modules, target: modules[target]
                                                           + '\ndef also_violations(): pass\n'}, others),
           '`also_violations`')
    expect('module added', list_violations(agents, {**modules, 'tests/test_zz.py': 'def zz_violations(): pass\n'}, others),
           'tests/test_zz.py: no bullet')
    expect('module gone', list_violations(agents, {k: v for k, v in modules.items() if k != target}, others),
           f'{target}: a bullet for a module that does not exist')
    if list_violations(agents, modules, others):
        failures.append('control sound: the staged text itself is refused')
    for f in failures:
        print(f'F1-testing-list: {f}', file=sys.stderr)
    print(f'F1-testing-list controls: {"FAILED" if failures else "ok"} (8 plants)', file=sys.stderr)
    return 1 if failures else 0


def main() -> int:
    agents, modules, others = sources()
    if not modules:
        print('F1-testing-list: no test module in the index', file=sys.stderr)
        return 1
    if '--controls' in sys.argv[1:]:
        return controls(agents, modules, others)
    violations = list_violations(agents, modules, others)
    for v in violations:
        print(f'F1-testing-list: {v}', file=sys.stderr)
    print(f'F1-testing-list: {"FAILED, " + str(len(violations)) if violations else "ok"} '
          f'({len(modules)} modules, {len(module_list(agents))} bullets)', file=sys.stderr)
    return 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())
