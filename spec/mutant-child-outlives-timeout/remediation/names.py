"""Every name the cycle adds is described, and no new runner name collides (review cycle 2, F5).

Lists the top-level names the cycle adds since the shape commit (`BASE`, from `verify/gate.py`), read
from the index, and checks:

  - each name added to `tests/mutants.py` that is public is named, in backticks, in AGENTS.md
    § Testing; each private one there or in the runner's module docstring;
  - each name added to `tests/test_mutations.py` (test functions aside: their names are their
    description) is named in § Testing or in that module's docstring;
  - no public name added to the runner is also bound at the top level of another `tests/` module,
    where a reader looking it up would land on the wrong one (`timeout_violations` once did);
  - neither list is empty, so the check cannot pass on nothing.

Its controls plant each refusal. Run from the cycle worktree root, after staging:

    UV_PYTHON=3.14 uv run python -I spec/mutant-child-outlives-timeout/remediation/names.py
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / 'verify' / 'gate.py'
spec = importlib.util.spec_from_file_location('gate', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)  # type: ignore[union-attr]

RUNNER, TESTS = gate.RUNNER, gate.TESTS
MIRRORS = {RUNNER, TESTS}


def defined(source: str) -> set[str]:
    """The top-level names `source` binds, imports aside."""
    return {name for node in ast.parse(source).body if not isinstance(node, (ast.Import, ast.ImportFrom))
            for name in gate.bound_names(node)}


def docstring(source: str) -> str:
    return ast.get_docstring(ast.parse(source)) or ''


def testing_section(agents: str) -> str:
    start = agents.index('\n## Testing\n')
    end = agents.index('\n## ', start + 1)
    return agents[start:end]


def named(name: str, *texts: str) -> bool:
    return any(f'`{name}`' in text for text in texts)


def names_violations(base_runner: str, head_runner: str, base_tests: str, head_tests: str, testing: str,
                     others: dict[str, set[str]]) -> tuple[list[str], list[str], list[str]]:
    """Return (violations, names added to the runner, names added to its test module)."""
    found = []
    runner_added = sorted(defined(head_runner) - defined(base_runner))
    tests_added = sorted(n for n in defined(head_tests) - defined(base_tests) if not n.startswith('test_'))
    if not runner_added:
        found.append(f'{RUNNER}: no name added, so nothing was checked')
    if not tests_added:
        found.append(f'{TESTS}: no name added, so nothing was checked')
    runner_doc, tests_doc = docstring(head_runner), docstring(head_tests)
    for name in runner_added:
        if name.startswith('_'):
            if not named(name, testing, runner_doc):
                found.append(f'{RUNNER}: {name} is named neither in AGENTS.md § Testing nor in the module docstring')
        elif not named(name, testing):
            found.append(f'{RUNNER}: public {name} is not named in AGENTS.md § Testing')
        else:
            clash = sorted(module for module, names in others.items() if name in names)
            if clash:
                found.append(f'{RUNNER}: public {name} is also bound at the top level of {", ".join(clash)}')
    for name in tests_added:
        if not named(name, testing, tests_doc):
            found.append(f'{TESTS}: {name} is named neither in AGENTS.md § Testing nor in the module docstring')
    return found, runner_added, tests_added


def other_modules() -> dict[str, set[str]]:
    paths = [p for p in gate.git('ls-files', '--', 'tests/*.py').split() if p not in MIRRORS]
    return {p: defined(gate.staged(p)) for p in paths}


def controls(base_runner: str, head_runner: str, base_tests: str, head_tests: str, testing: str,
             others: dict[str, set[str]]) -> list[str]:
    bad = []

    def expect(label: str, got: list[str], why: str | None) -> None:
        hit = any(why in v for v in got) if why else got == []
        print(f'{"ok " if hit else "BAD"} {label}: {got[:1] if why else "sound data accepted"}')
        if not hit:
            bad.append(f'control {label}: {got}, wanted {why or "none"}')

    check = lambda runner=head_runner, tests=head_tests, manual=testing, mods=others: names_violations(
        base_runner, runner, base_tests, tests, manual, mods)[0]
    expect('sound', check(), None)
    expect('undocumented public', check(runner=head_runner + '\n\ndef undocumented_helper():\n    pass\n'),
           'public undocumented_helper is not named')
    expect('undocumented private', check(runner=head_runner + '\n\ndef _undocumented():\n    pass\n'),
           '_undocumented is named neither')
    expect('undocumented test helper', check(tests=head_tests + '\n\nUNDESCRIBED = 1\n'), 'UNDESCRIBED is named neither')
    expect('test function exempt', check(tests=head_tests + '\n\ndef test_extra():\n    pass\n'), None)
    clash = check(runner=head_runner + '\n\ndef shared_name():\n    pass\n', manual=testing + ' `shared_name` ',
                  mods={**others, 'tests/test_other.py': {'shared_name'}})
    expect('collision', clash, 'also bound at the top level of tests/test_other.py')
    expect('nothing added', check(runner=base_runner), 'no name added')
    return bad


def main() -> int:
    found = gate.working_copy_violations()
    base_runner, base_tests = gate.at(gate.BASE, RUNNER), gate.at(gate.BASE, TESTS)
    head_runner, head_tests = gate.staged(RUNNER), gate.staged(TESTS)
    testing, others = testing_section(gate.staged('AGENTS.md')), other_modules()
    found += controls(base_runner, head_runner, base_tests, head_tests, testing, others)
    violations, runner_added, tests_added = names_violations(base_runner, head_runner, base_tests, head_tests,
                                                             testing, others)
    print(f'names added to {RUNNER} ({len(runner_added)}): {" ".join(runner_added)}')
    print(f'names added to {TESTS} ({len(tests_added)}): {" ".join(tests_added)}')
    found += violations
    for line in found:
        print(f'FAIL {line}')
    print(f'{"ok" if not found else "red"}  names')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
