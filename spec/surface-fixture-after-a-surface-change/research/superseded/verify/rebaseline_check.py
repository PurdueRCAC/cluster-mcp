"""The re-baseline differs from the 2.x fixture only by the five TOLERATED kinds (GOAL R6). Run from the worktree root.

Usage: uv run python -I spec/surface-fixture-after-a-surface-change/verify/rebaseline_check.py NEW_FIXTURE [BASE]

BASE defaults to `0bfacae` (origin/develop when the cycle was shaped). The check:

1. reads the fixture and `tests/test_surface.py` as they were at BASE, and imports that old module
   (from a fresh temporary directory, beside today's `tests/` for `harness` and `test_registry`);
2. projects NEW_FIXTURE onto the fields the old recorder recorded: each tool's `description`,
   `inputSchema` and `outputSchema`, its `annotations` and `title` when present; each resource's
   `name`, `description` and `mimeType`; the instructions;
3. requires the old `surface_violations(old fixture, projection)` to be empty, and prints the old
   `tolerated_differences`, per kind, so the commit records which of the five kinds occur where;
4. requires each argument `description` to be its tool's `Args:` line, whitespace aside, closing
   `argument-description`'s "any string" for the moment the descriptions enter the pin;
5. prints every field the old fixture did not record, which enters as served (R6's second sentence).

Exit 0 when 3 and 4 hold. The printed report is what the re-baseline commit body records.
Footprint: one python process, under 300 MB.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
TESTS = ROOT / 'tests'
OLD_TOOL_KEYS = ('description', 'inputSchema', 'outputSchema')
OLD_OPTIONAL_TOOL_KEYS = ('annotations', 'title')
OLD_RESOURCE_KEYS = ('name', 'description', 'mimeType')
ENVIRON = dict(os.environ)


def show(rev: str, path: str) -> str:
    done = subprocess.run(['git', 'show', f'{rev}:{path}'], capture_output=True, text=True, env=dict(ENVIRON))
    if done.returncode != 0:
        raise SystemExit(f'rebaseline_check: cannot read {rev}:{path}: {done.stderr.strip()}')
    return done.stdout


def old_comparison(rev: str, scratch: Path) -> Any:
    """`tests/test_surface.py` as it was at `rev`, imported under a name of its own."""
    source = scratch / 'baseline_surface_at_base.py'
    source.write_text(show(rev, 'tests/test_surface.py'))
    sys.path[:0] = [str(scratch), str(TESTS)]
    spec = importlib.util.spec_from_file_location('baseline_surface_at_base', source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def projection(new: dict[str, Any]) -> dict[str, Any]:
    tools = {}
    for name, entry in new.get('tools', {}).items():
        tools[name] = {k: entry.get(k) for k in OLD_TOOL_KEYS}
        tools[name].update({k: entry[k] for k in OLD_OPTIONAL_TOOL_KEYS if k in entry})
    resources = {uri: {k: entry.get(k) for k in OLD_RESOURCE_KEYS} for uri, entry in new.get('resources', {}).items()}
    return {'instructions': new.get('instructions'), 'tools': tools, 'resources': resources}


def unrecorded(projected: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Every field of `new` the projection drops, grouped by field: top-level keys, then per-entry keys."""
    lines = [f'- {key}' for key in sorted(set(new) - set(projected))]
    for listing in ('tools', 'resources'):
        by_key: dict[str, list[str]] = {}
        for name, entry in new.get(listing, {}).items():
            for key in sorted(set(entry) - set(projected[listing].get(name, {}))):
                by_key.setdefault(key, []).append(name)
        for key, names in sorted(by_key.items()):
            lines.append(f'- {listing}.<each>.{key}, on {len(names)} of {len(new[listing])}: {", ".join(sorted(names))}')
    return lines


def args_lines(description: str) -> dict[str, str]:
    """Each `Args:` entry of a docstring, by argument name, its wrapped lines joined."""
    block = re.search(r'^Args:\n((?:(?:    |\t).*\n?|\n)+)', description, re.M)
    entries: dict[str, str] = {}
    current = None
    for line in (block.group(1).splitlines() if block else []):
        head = re.match(r'^    (\w+)(?: \([^)]*\))?: ?(.*)$', line)
        if head:
            current = head.group(1)
            entries[current] = head.group(2)
        elif current and line.strip():
            entries[current] += ' ' + line.strip()
    return {name: ' '.join(text.split()) for name, text in entries.items()}


def argument_problems(new: dict[str, Any]) -> list[str]:
    problems = []
    for name, entry in sorted(new.get('tools', {}).items()):
        documented = args_lines(entry.get('description') or '')
        for arg, schema in sorted((entry.get('inputSchema') or {}).get('properties', {}).items()):
            if 'description' not in schema:
                continue
            served = ' '.join(str(schema['description']).split())
            if documented.get(arg) != served:
                problems.append(f'{name}.{arg}: served {served!r}, its Args: line is {documented.get(arg)!r}')
    return problems


def main(argv: list[str]) -> int:
    if len(argv) not in (1, 2):
        print(__doc__.splitlines()[2], file=sys.stderr)
        return 2
    new = json.loads(Path(argv[0]).read_text())
    rev = argv[1] if len(argv) == 2 else '0bfacae'
    old = json.loads(show(rev, 'tests/fixtures/served_surface.json'))
    with tempfile.TemporaryDirectory(prefix='surface-rebaseline-') as scratch:
        module = old_comparison(rev, Path(scratch))
        projected = projection(new)
        violations = module.surface_violations(old, projected)
        tolerated = module.tolerated_differences(old, projected)
        kinds = sorted(module.TOLERATED)
    arguments = argument_problems(new)

    print(f'Re-baseline check against the fixture at {rev} (the fields it recorded):')
    if violations:
        print('- differences beyond the tolerated kinds:')
        print('\n'.join(f'  - {v}' for v in violations))
    else:
        print(f'- no difference beyond the {len(kinds)} tolerated kinds ({", ".join(kinds)})')
    by_kind: dict[str, list[str]] = {}
    for tool, entries in tolerated.items():
        for entry in entries:
            by_kind.setdefault(entry.split(':')[0], []).append(tool)
    for kind in kinds:
        tools = sorted(set(by_kind.get(kind, [])))
        print(f'  - {kind}: {len(tools)} tools' + (f' ({", ".join(tools)})' if tools else ''))
    if arguments:
        print('- argument descriptions that are not their Args: line:')
        print('\n'.join(f'  - {p}' for p in arguments))
    else:
        count = sum('description' in s for e in new.get('tools', {}).values()
                    for s in (e.get('inputSchema') or {}).get('properties', {}).values())
        print(f'- each of the {count} argument descriptions is its Args: line')
    extra = unrecorded(projected, new)
    print('Fields the old fixture did not record, entering as served:')
    print('\n'.join(extra) if extra else '- none')
    return 1 if violations or arguments else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
