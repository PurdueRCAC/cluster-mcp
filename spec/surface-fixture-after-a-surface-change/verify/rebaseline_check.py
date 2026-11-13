"""The re-baseline serves what the 2.x fixture records, but for the five former TOLERATED kinds (GOAL R6).

Usage, from the worktree root:
    uv run python -I spec/surface-fixture-after-a-surface-change/verify/rebaseline_check.py [FIXTURE [BASE]]

FIXTURE defaults to the staged `tests/fixtures/served_surface.json` (`git show :path`, so the check
reads what the commit will hold, never the working copy); BASE defaults to `0bfacae`
(origin/develop when the cycle was shaped). The fixture is the snapshot test's serialization:
`{listing: {identity: {era: {set: entry}}}}` for the four listings and `{key: {era: {set: value}}}`
for every other top-level key (PLAN § 2.1). The check:

1. reads the fixture and `tests/test_surface.py` as they were at BASE and imports that old module
   (from a fresh temporary directory, beside today's `tests/` for `harness` and `test_registry`);
2. for each protocol era, takes the full capability set's surface out of FIXTURE (set `both`; the
   prototype showed it equal to a server built from every installed capability) and projects it
   onto the fields the old recorder recorded: each tool's `description`, `inputSchema` and
   `outputSchema`, its `annotations` and `title` when present; each resource's `name`,
   `description` and `mimeType`; the instructions;
3. requires the old `surface_violations(old fixture, projection)` to be empty in each era, and
   prints the old `tolerated_differences` per kind, so the commit records which of the five kinds
   occur where; then, because that comparison reads some leaves with Python `==` (`False == 0`) and
   some keys with defaults (`.get('required', [])`), a type-strict pass of its own: every leaf the
   old fixture records (output schemas with `$defs` inlined on both sides) is in the projection with
   the same JSON text, and every leaf the projection adds is one of the five kinds' places (a tool's
   `title`, `inputSchema.additionalProperties`, an argument's `description`, a `description` on an
   output node that was a `$ref`);
4. requires each argument `description` to be its tool's `Args:` line, whitespace aside, which
   closes `argument-description`'s "any string" now that the descriptions are in the pin;
5. prints every field the old fixture did not record, which enters as served (R6's second
   sentence): the top-level keys, the per-entry keys, and the eras and sets beyond the full set.

Exit 0 when 3 and 4 hold in both eras. The printed report is what the re-baseline commit body and
the landing commit body record. Footprint: one python process and one `git` child, under 300 MB.
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
FIXTURE = 'tests/fixtures/served_surface.json'
LISTINGS = ('tools', 'resources', 'resourceTemplates', 'prompts')
ERAS = ('legacy', 'modern')
FULL_SET = 'both'
OLD_TOOL_KEYS = ('description', 'inputSchema', 'outputSchema')
OLD_OPTIONAL_TOOL_KEYS = ('annotations', 'title')
OLD_RESOURCE_KEYS = ('name', 'description', 'mimeType')
ENVIRON = dict(os.environ)


def show(rev: str, path: str) -> str:
    """`git show rev:path`; `rev` empty reads the index (the staged copy)."""
    done = subprocess.run(['git', 'show', f'{rev}:{path}'], capture_output=True, text=True, env=dict(ENVIRON))
    if done.returncode != 0:
        raise SystemExit(f'rebaseline_check: cannot read {rev or "the index"}:{path}: {done.stderr.strip()}')
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


def leaves(node: Any, path: tuple[Any, ...] = ()) -> dict[tuple[Any, ...], str]:
    """Every leaf of `node` by its key and index path, as JSON text; an empty dict or list is a leaf."""
    if isinstance(node, dict) and node:
        return {k: v for key, value in node.items() for k, v in leaves(value, path + (key,)).items()}
    if isinstance(node, list) and node:
        return {k: v for i, value in enumerate(node) for k, v in leaves(value, path + (i,)).items()}
    return {path: json.dumps(node, sort_keys=True)}


def strict_problems(module: Any, old: dict[str, Any], projected: dict[str, Any]) -> list[str]:
    """The type-strict pass: what the old fixture records is in the projection, JSON for JSON, and
    the projection adds a leaf only at one of the five kinds' places."""
    problems = []
    if json.dumps(old.get('instructions')) != json.dumps(projected.get('instructions')):
        problems.append('instructions differ')
    for listing in ('tools', 'resources'):
        for name in sorted(set(old.get(listing, {})) | set(projected.get(listing, {}))):
            base, head = old.get(listing, {}).get(name), projected.get(listing, {}).get(name)
            if base is None or head is None:
                problems.append(f'{listing}.{name}: {"added" if base is None else "removed"}')
                continue
            base, head, targets = dict(base), dict(head), set()
            if listing == 'tools' and isinstance(base.get('outputSchema'), dict):
                base['outputSchema'], targets = module.inline_defs(base['outputSchema'])
                head['outputSchema'], _ = module.inline_defs(head.get('outputSchema'))
            was, now = leaves(base), leaves(head)
            for path, text in sorted(was.items(), key=str):
                if now.get(path) != text:
                    problems.append(f'{listing}.{name}: {path} was {text}, now {now.get(path, "absent")}')
            for path in sorted(set(now) - set(was), key=str):
                allowed = listing == 'tools' and (
                    path == ('title',) or path == ('inputSchema', 'additionalProperties')
                    or (len(path) == 4 and path[:2] == ('inputSchema', 'properties') and path[3] == 'description')
                    or (path[0] == 'outputSchema' and path[-1] == 'description' and path[1:-1] in targets))
                if not allowed:
                    problems.append(f'{listing}.{name}: {path} gained {now[path]}, not one of the five kinds')
    return problems


def surface_of(fixture: dict[str, Any], era: str, set_id: str) -> dict[str, Any]:
    """The one surface the serialization recorded for `era` and `set_id`, in `served_surface`'s shape."""
    surface: dict[str, Any] = {}
    for key, value in fixture.items():
        if key in LISTINGS:
            surface[key] = {ident: by_era[era][set_id] for ident, by_era in value.items()
                            if set_id in by_era.get(era, {})}
        else:
            surface[key] = value[era][set_id]
    return surface


def projection(new: dict[str, Any]) -> dict[str, Any]:
    tools = {}
    for name, entry in new.get('tools', {}).items():
        tools[name] = {k: entry.get(k) for k in OLD_TOOL_KEYS}
        tools[name].update({k: entry[k] for k in OLD_OPTIONAL_TOOL_KEYS if k in entry})
    resources = {uri: {k: entry.get(k) for k in OLD_RESOURCE_KEYS} for uri, entry in new.get('resources', {}).items()}
    return {'instructions': new.get('instructions'), 'tools': tools, 'resources': resources}


def unrecorded(projected: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Every field of `new` the projection drops: top-level keys, then per-entry keys."""
    lines = [f'- {key}' for key in sorted(set(new) - set(projected))]
    for listing in ('tools', 'resources'):
        by_key: dict[str, list[str]] = {}
        for name, entry in new.get(listing, {}).items():
            for key in sorted(set(entry) - set(projected[listing].get(name, {}))):
                by_key.setdefault(key, []).append(name)
        for key, names in sorted(by_key.items()):
            lines.append(f'- {listing}.<each>.{key}, on {len(names)} of {len(new[listing])}: {", ".join(sorted(names))}')
    return lines


def recorded_sets(fixture: dict[str, Any]) -> dict[str, list[str]]:
    """The set ids recorded per era, read from the instructions (recorded for every era and set)."""
    return {era: sorted(fixture.get('instructions', {}).get(era, {})) for era in ERAS}


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
    if len(argv) > 2:
        print(__doc__.splitlines()[3], file=sys.stderr)
        return 2
    text = Path(argv[0]).read_text() if argv else show('', FIXTURE)
    fixture = json.loads(text)
    rev = argv[1] if len(argv) == 2 else '0bfacae'
    old = json.loads(show(rev, FIXTURE))
    failed = False
    with tempfile.TemporaryDirectory(prefix='surface-rebaseline-') as scratch:
        module = old_comparison(rev, Path(scratch))
        kinds = sorted(module.TOLERATED)
        print(f'Re-baseline check against the fixture at {rev} (the fields it recorded), set {FULL_SET!r}:')
        for era in ERAS:
            new = surface_of(fixture, era, FULL_SET)
            projected = projection(new)
            violations = module.surface_violations(old, projected) + strict_problems(module, old, projected)
            tolerated = module.tolerated_differences(old, projected)
            arguments = argument_problems(new)
            failed = failed or bool(violations) or bool(arguments)
            print(f'{era}:')
            if violations:
                print('- differences beyond the tolerated kinds (the old comparison, then the strict pass):')
                print('\n'.join(f'  - {v}' for v in violations))
            else:
                print(f'- no difference beyond the {len(kinds)} tolerated kinds ({", ".join(kinds)}), '
                      'by the old comparison and by the type-strict pass')
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
            print('Fields the old fixture did not record, entering as served:')
            extra = unrecorded(projected, new)
            print('\n'.join(extra) if extra else '- none')
    sets = recorded_sets(fixture)
    print('Eras and sets the old fixture did not record, entering as served:')
    for era in ERAS:
        others = [s for s in sets[era] if s != FULL_SET]
        print(f'- {era}: ' + (', '.join(others) if others else 'none'))
    if any(FULL_SET not in sets[era] for era in ERAS):
        print(f'rebaseline_check: FAIL: set {FULL_SET!r} is not recorded in every era', file=sys.stderr)
        failed = True
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
