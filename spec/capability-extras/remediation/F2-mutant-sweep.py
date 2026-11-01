# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 1, F2: every decision in the capability loader is mutated, and every mutant is caught.

    uv run python -I spec/capability-extras/remediation/F2-mutant-sweep.py [coverage|cases|equivalents|all]
                                                                       from the worktree root

`coverage` (seconds): every decision in `core/capabilities.py`, found by parsing it (each `if`, each
conditional expression, boolean operator and comparison, each comprehension condition, each `except`
clause, each sort key), lies on a line some mutant edits: a mutation case of `tests/mutants.py`
planting into that file, or one of the equivalent mutants recorded below. A decision nobody mutated
fails here, whoever adds it.

`cases` (about 8 min): every mutation case planting into `core/capabilities.py`, run by
`tests/mutants.py` (with its self-check controls) in the handshake era, then in revision
2026-07-28's. Their targets are the rows beside every member set (core only, each member, both);
each case must be killed, every target failing with its `why`.

`equivalents` (about 5 min): each equivalent mutant below is planted the same way and the whole
capability selection (`EQUIVALENT_TARGETS`) runs against it in each era; it must pass, which is what
recording it as equivalent claims. One that fails is no longer equivalent, and needs a case.

`all` (the default) runs the three. Footprint: one mutant child at a time, under 1 GB.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'tests'))
import mutants  # noqa: E402

FILE = 'core/capabilities.py'
SOURCE = ROOT / 'packages/cluster-mcp/src/cluster_mcp' / FILE
ERAS = {'handshake': None, 'modern': 'modern'}

# Mutants that change no behaviour, each with why. `edit` is (old, new), as a case's.
TOOL_ASSEMBLY = ('            for tool in tools:\n'
                 '                try:\n'
                 '                    serve(scratch, (tool,), ())\n'
                 '                except Exception as exc:\n'
                 "                    raise CapabilityLoadError(distribution, f'its tool {tool.name!r} cannot be served: '\n"
                 "                                                            f'{_cause(exc)}') from exc\n")
EQUIVALENT = {
    'capability-installed-uncached': (
        ('    if _installed is None:\n', '    if True:\n'),
        'A second load imports each tools module from the import cache, so it registers nothing and '
        'attributes to each capability the tools the first load did: the same capabilities, the same '
        'tools, the same registry. Only the cost of the second load differs.'),
    'capability-tool-assembly-dropped': (
        (TOOL_ASSEMBLY, ''),
        "Every tool that reaches the assembly has a name no core tool, no earlier capability's tool and "
        "no other tool of its own holds (the three name refusals before it), and FastMCP 4.1.4's "
        '`add_tool` refuses only a key already held or a versioned tool beside an unversioned one of the '
        'same name. The assembly is kept as the one path a refusal of a later FastMCP would take.'),
    'capability-scratch-without-core-tools': (
        ('    serve(server, CORE_TOOLS, RESOURCE_REGISTRY)\n', '    serve(server, (), RESOURCE_REGISTRY)\n'),
        "A capability tool named as a core tool is refused by the core-name check before the assembly, "
        'so the scratch server never meets a tool that would collide with a core one.'),
    'capability-listing-duplicates-unchecked': (
        ('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
         '    if sorted(listed) == sorted(names):\n'),
        'The tool names are distinct by then (the duplicate-tool refusals run first), so a text whose '
        'sorted names equal them lists none twice.'),
}

# What an equivalent mutant must pass: every test of the loader, the composed surface and the
# startup refusal.
EQUIVALENT_TARGETS = (
    'test_capabilities.py', 'test_instructions.py', 'test_registry.py', 'test_surface.py',
    'test_storage_resource.py',
    'test_startup.py::test_a_broken_capability_stops_startup',
    'test_startup.py::test_capabilities_load_before_the_mode_ladder',
    'test_startup.py::test_http_load_failure_exits_before_binding',
    'test_startup.py::test_a_contribution_the_server_would_refuse_stops_startup',
)


def decisions(text: str) -> dict[int, str]:
    """Every decision in `text`, by line: what kind of node makes it."""
    found: dict[int, str] = {}
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.If):
            found.setdefault(node.lineno, 'if')
        elif isinstance(node, ast.IfExp):
            found.setdefault(node.lineno, 'conditional expression')
        elif isinstance(node, ast.BoolOp):
            found.setdefault(node.lineno, 'boolean operator')
        elif isinstance(node, ast.Compare):
            found.setdefault(node.lineno, 'comparison')
        elif isinstance(node, ast.ExceptHandler):
            found.setdefault(node.lineno, 'except clause')
        elif isinstance(node, ast.comprehension):
            for condition in node.ifs:
                found.setdefault(condition.lineno, 'comprehension condition')
        elif isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'sorted':
            for keyword in node.keywords:
                if keyword.arg == 'key':
                    found.setdefault(keyword.value.lineno, 'sort key')
    return found


def span(text: str, old: str) -> range:
    if text.count(old) != 1:
        raise SystemExit(f'F2: a mutant anchor occurs {text.count(old)} times in {FILE}: {old[:60]!r}')
    first = text[:text.index(old)].count('\n') + 1
    return range(first, first + old.rstrip('\n').count('\n') + 1)


def cases() -> list[mutants.Case]:
    return [case for case in mutants.CASES if case.file == FILE]


def coverage() -> list[str]:
    text = SOURCE.read_text()
    covered: dict[int, list[str]] = {}
    for case in cases():
        for old, _ in case.edits:
            for line in span(text, old):
                covered.setdefault(line, []).append(case.id)
    for name, ((old, _), _) in EQUIVALENT.items():
        for line in span(text, old):
            covered.setdefault(line, []).append(f'{name} (equivalent)')
    found = decisions(text)
    lines = text.splitlines()
    bad = [f'{FILE}:{n}: a {kind} no mutant edits: {lines[n - 1].strip()}' for n, kind in sorted(found.items())
           if n not in covered]
    print(f'F2 coverage: {len(found)} decisions on {len(found)} lines, {len(cases())} cases, '
          f'{len(EQUIVALENT)} equivalent mutants', file=sys.stderr)
    for n, kind in sorted(found.items()):
        print(f'  {n:4} {kind:24} {", ".join(covered.get(n, ["-"]))}', file=sys.stderr)
    return bad


def era_env(era: str | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != 'CLUSTER_MCP_TEST_ERA'}
    if era:
        env['CLUSTER_MCP_TEST_ERA'] = era
    return env


def run_cases() -> list[str]:
    bad: list[str] = []
    ids = [case.id for case in cases()]
    for label, era in ERAS.items():
        result = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids], env=era_env(era),
                                capture_output=True, text=True)
        killed = [line for line in result.stdout.splitlines() if line.startswith('killed ')]
        failed = [line for line in result.stdout.splitlines() if line.startswith('FAILED')]
        print(f'F2 cases, {label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}', file=sys.stderr)
        bad += [f'{label} era: {line}' for line in failed]
        if result.returncode != 0 and not failed:
            bad.append(f'{label} era: the runner exited {result.returncode}: {result.stderr[-400:]}')
        if len(killed) != len(ids):
            bad.append(f'{label} era: {len(killed)} of {len(ids)} cases reported killed')
    return bad


def run_equivalents() -> list[str]:
    bad: list[str] = []
    for name, (edit, _) in EQUIVALENT.items():
        case = mutants.Case(name, FILE, (edit,), EQUIVALENT_TARGETS, '')
        for label, era in ERAS.items():
            with tempfile.TemporaryDirectory(prefix=f'equivalent-{name}-') as scratch:
                dest = Path(scratch)
                src_root = mutants.apply(case, dest)
                saved, wanted = os.environ.copy(), era_env(era)
                os.environ.clear()
                os.environ.update(wanted)
                try:
                    child = mutants.run_child(src_root, EQUIVALENT_TARGETS, dest / 'junit.xml')
                finally:
                    os.environ.clear()
                    os.environ.update(saved)
            tail = child.stdout.strip().splitlines()[-1:] or ['']
            print(f'F2 equivalent {name}, {label} era: exit {child.returncode}, {tail[0]}', file=sys.stderr)
            if child.returncode == mutants.WRONG_ORIGIN:
                bad.append(f'{name}, {label} era: the child did not import the mutated copy')
            elif child.returncode != 0:
                failing = [line for line in child.stdout.splitlines() if line.startswith('FAILED')]
                bad.append(f'{name}, {label} era: recorded as equivalent, but the selection fails: '
                           f'{failing[:5] or (child.stdout + child.stderr)[-400:]}')
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('coverage', 'cases', 'equivalents', 'all'):
        raise SystemExit('usage: F2-mutant-sweep.py [coverage|cases|equivalents|all]')
    bad = coverage()
    if mode in ('cases', 'all'):
        bad += run_cases()
    if mode in ('equivalents', 'all'):
        bad += run_equivalents()
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F2: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
