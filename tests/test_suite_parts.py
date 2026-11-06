# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The suite's commands partition it: every test runs exactly once per protocol era.

Each era's suite runs as several pytest commands, each in a CI job of its own (AGENTS.md
§ Conventions, "CI mirrors the gate"). A layout of those commands can drop a test without any
command failing: a `-m` or `--deselect` that filters, a `-k` pair whose halves miss a row, a module
the last command neither names nor ignores. `suite_part_violations` refuses every shape that could,
so the only layouts the three lists can carry are those that partition the suite by construction:
commands naming modules (a module named once, or by exactly two commands that select from it by an
expression and its negation), then one last command that runs from the root and `--ignore`s exactly
the modules the others name. The second check holds the profile's `verify`, the release recipe's
`gate` and the workflow to the same suite commands in the same order.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODERN = 'CLUSTER_MCP_TEST_ERA=modern '
RUNNER = ['uv', 'run', 'pytest', '-q']
MODULE = r'tests/test_\w+\.py'


def suite_commands(commands: list[str]) -> list[str]:
    return [command for command in commands if 'pytest' in command]


def verify_commands(agents: str) -> list[str]:
    """The suite commands of the profile's `verify` cell, in order."""
    match = re.search(r'^\| verify \| `([^`]+)`', agents, re.M)
    return suite_commands([part.strip() for part in match.group(1).split('&&')]) if match else []


def gate_commands(agents: str) -> list[str]:
    """The suite commands of the release recipe's `gate` list, in order."""
    match = re.search(r'^### Release recipe\n[\s\S]*?^  gate:\n((?:    (?:- |#)[^\n]*\n)+)', agents, re.M)
    lines = match.group(1).splitlines() if match else []
    return suite_commands([line[len('    - '):] for line in lines if line.startswith('    - ')])


def workflow_commands(workflow: str) -> list[str]:
    """The suite commands of the workflow's run steps, in order."""
    return suite_commands(re.findall(r'^ +- run: (.*)$', workflow, re.M))


def split_command(command: str) -> tuple[list[str], list[str], list[str], list[str]]:
    """A suite command's named modules, `--ignore`d modules, `-k` expressions and any other word."""
    words = shlex.split(command)
    named, ignored, expressions, others = [], [], [], []
    rest = iter(words[len(RUNNER):])
    for word in rest:
        if word == '-k':
            expressions.append(next(rest, ''))
        elif word.startswith('--ignore='):
            ignored.append(word[len('--ignore='):])
        elif re.fullmatch(MODULE, word):
            named.append(word)
        else:
            others.append(word)
    return named, ignored, expressions, others


def negates(expression: str, other: str) -> bool:
    """True when `other` is exactly `expression`'s negation: `not (E)`, or `not E` for one word (for
    more than one word, `not x and y` is `(not x) and y`, which with `x and y` misses rows)."""
    if other == f'not ({expression})':
        return True
    return re.fullmatch(r'\w+', expression) is not None and other == f'not {expression}'


def suite_part_violations(commands: list[str], modules: set[str]) -> list[str]:
    """Every way the era's suite `commands` could drop or repeat a test of the `modules` that exist."""
    found = []
    handshake = [c for c in commands if not c.startswith(MODERN)]
    modern = [c[len(MODERN):] for c in commands if c.startswith(MODERN)]
    if not handshake:
        return ['no suite command']
    if handshake != modern or commands != handshake + [MODERN + c for c in modern]:
        found.append('the eras do not run the same commands, the handshake era first')
    parts = []
    for command in handshake:
        if shlex.split(command)[:len(RUNNER)] != RUNNER:
            found.append(f'{command!r} does not start with {" ".join(RUNNER)!r}')
        named, ignored, expressions, others = split_command(command)
        if others:
            found.append(f'{command!r} carries {others}, which could drop or repeat a test')
        for module in named + ignored:
            if module not in modules:
                found.append(f'{command!r} names {module}, which is not a test module')
        parts.append((command, named, ignored, expressions))
    *heads, (last, last_named, last_ignored, last_expressions) = parts
    if last_named or last_expressions:
        found.append(f'the last command {last!r} must run from the root with only --ignore: no module and no -k')
    if len(set(last_ignored)) != len(last_ignored):
        found.append(f'the last command ignores a module twice: {last_ignored}')
    named_by: dict[str, list[tuple[str, list[str]]]] = {}
    for command, named, ignored, expressions in heads:
        if ignored:
            found.append(f'{command!r} ignores {ignored}: only the last command may')
        if not named:
            found.append(f'{command!r} names no module: it would run the whole suite again')
        if len(set(named)) != len(named):
            found.append(f'{command!r} names a module twice')
        if len(expressions) > 1 or (expressions and len(named) != 1):
            found.append(f'{command!r}: a -k selects within exactly one named module, once')
        for module in set(named):
            named_by.setdefault(module, []).append((command, expressions))
    for module, users in sorted(named_by.items()):
        if len(users) == 1 and not users[0][1]:
            continue
        pair = [expressions[0] if expressions else '' for _, expressions in users]
        if len(users) != 2 or not (negates(pair[0], pair[1]) or negates(pair[1], pair[0])):
            found.append(f'{module} is named by {[c for c, _ in users]}: a module runs whole in one command, '
                         'or in two whose -k are an expression and its negation')
    if heads and sorted(set(last_ignored)) != sorted(named_by):
        found.append(f'the last command ignores {sorted(set(last_ignored))}, not exactly the named modules '
                     f'{sorted(named_by)}')
    return found


def list_violations(verify: list[str], gate: list[str], workflow: list[str]) -> list[str]:
    found = []
    if not verify:
        found.append("the profile's verify runs no suite command")
    if gate != verify:
        found.append(f"the release gate's suite commands {gate} are not the profile verify's {verify}")
    if workflow != verify:
        found.append(f"the workflow's suite commands {workflow} are not the profile verify's {verify}")
    return found


def module_names() -> set[str]:
    return {f'tests/{p.name}' for p in (ROOT / 'tests').glob('test_*.py')}


@pytest.mark.unit
def test_the_suite_commands_partition_the_suite() -> None:
    commands = verify_commands((ROOT / 'AGENTS.md').read_text())
    assert commands, "no suite command found in the profile's verify"
    modules = module_names()
    assert 'tests/test_suite_parts.py' in modules, modules
    assert suite_part_violations(commands, modules) == []


@pytest.mark.unit
def test_the_three_lists_run_the_same_suite_commands() -> None:
    agents = (ROOT / 'AGENTS.md').read_text()
    workflow = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text()
    verify, gate, steps = verify_commands(agents), gate_commands(agents), workflow_commands(workflow)
    assert verify and gate and steps, (verify, gate, steps)
    assert list_violations(verify, gate, steps) == []


# A sound layout, and plants of each shape the check refuses.
SOUND = ['uv run pytest -q tests/test_a.py -k slow',
         "uv run pytest -q tests/test_a.py -k 'not slow'",
         'uv run pytest -q tests/test_b.py tests/test_c.py',
         'uv run pytest -q --ignore=tests/test_a.py --ignore=tests/test_b.py --ignore=tests/test_c.py']
MODULES = {'tests/test_a.py', 'tests/test_b.py', 'tests/test_c.py', 'tests/test_d.py'}


def both_eras(handshake: list[str]) -> list[str]:
    return handshake + [MODERN + command for command in handshake]


def planted(index: int, command: str) -> list[str]:
    return both_eras(SOUND[:index] + [command] + SOUND[index + 1:])


@pytest.mark.unit
@pytest.mark.parametrize('commands', [
    pytest.param(both_eras(SOUND), id='sound'),
    pytest.param(planted(1, "uv run pytest -q tests/test_a.py -k 'not (slow)'"), id='negation-in-parentheses'),
    pytest.param(both_eras(["uv run pytest -q tests/test_a.py -k 'x and y'",
                            "uv run pytest -q tests/test_a.py -k 'not (x and y)'"] + SOUND[2:]), id='compound-pair'),
    pytest.param(both_eras(["uv run pytest -q tests/test_a.py -k 'not slow'", 'uv run pytest -q tests/test_a.py -k slow']
                           + SOUND[2:]), id='negation-first'),
    pytest.param(both_eras(['uv run pytest -q tests/test_a.py tests/test_b.py tests/test_c.py', SOUND[3]]),
                 id='no-k-pair'),
])
def test_the_part_check_accepts_a_partition(commands: list[str]) -> None:
    assert suite_part_violations(commands, MODULES) == []


@pytest.mark.unit
@pytest.mark.parametrize(('commands', 'fragment'), [
    pytest.param(planted(2, SOUND[2] + ' -x'), 'could drop or repeat', id='another-option'),
    pytest.param(planted(2, SOUND[2] + ' -m unit'), 'could drop or repeat', id='marker'),
    pytest.param(planted(2, SOUND[2] + ' --deselect tests/test_b.py::test_x'), 'could drop or repeat', id='deselect'),
    pytest.param(planted(2, 'uv run pytest tests/test_b.py tests/test_c.py'), 'does not start with', id='runner'),
    pytest.param(planted(2, SOUND[2] + ' tests/test_b.py'), 'names a module twice', id='module-twice-in-a-command'),
    pytest.param(planted(2, SOUND[2] + ' tests/test_a.py'), 'is named by', id='module-in-two-commands'),
    pytest.param(planted(1, "uv run pytest -q tests/test_a.py -k 'not fast'"), 'is named by', id='k-not-a-negation'),
    pytest.param(both_eras(["uv run pytest -q tests/test_a.py -k 'x and y'",
                            "uv run pytest -q tests/test_a.py -k 'not x and y'"] + SOUND[2:]), 'is named by',
                 id='compound-without-parentheses'),
    pytest.param(planted(1, 'uv run pytest -q tests/test_a.py'), 'is named by', id='k-on-one-half'),
    pytest.param(both_eras([SOUND[0]] + SOUND[2:]), 'is named by', id='k-without-its-negation'),
    pytest.param(planted(0, 'uv run pytest -q tests/test_a.py tests/test_b.py -k slow'), 'exactly one named module',
                 id='k-over-two-modules'),
    pytest.param(planted(0, 'uv run pytest -q tests/test_a.py -k slow -k fast'), 'exactly one named module',
                 id='two-k'),
    pytest.param(planted(3, SOUND[3] + ' -k slow'), 'the last command', id='k-on-the-last-command'),
    pytest.param(planted(3, SOUND[3] + ' tests/test_d.py'), 'the last command', id='module-on-the-last-command'),
    pytest.param(planted(3, SOUND[3].replace(' --ignore=tests/test_c.py', '')), 'not exactly the named modules',
                 id='complement-misses-a-module'),
    pytest.param(planted(3, SOUND[3] + ' --ignore=tests/test_d.py'), 'not exactly the named modules',
                 id='complement-ignores-an-unnamed-module'),
    pytest.param(planted(3, SOUND[3] + ' --ignore=tests/test_c.py'), 'ignores a module twice',
                 id='complement-ignores-twice'),
    pytest.param(planted(2, SOUND[2] + ' --ignore=tests/test_d.py'), 'only the last command may',
                 id='ignore-on-a-head'),
    pytest.param(planted(2, 'uv run pytest -q'), 'names no module', id='whole-suite-twice'),
    pytest.param(planted(2, 'uv run pytest -q tests/test_b.py tests/test_e.py'), 'not a test module',
                 id='unknown-module'),
    pytest.param(SOUND + [MODERN + c for c in SOUND[:3]], 'eras do not run the same', id='era-missing-a-command'),
    pytest.param(SOUND + [MODERN + c for c in SOUND[1::-1] + SOUND[2:]], 'eras do not run the same',
                 id='era-reordered'),
    pytest.param([MODERN + c for c in SOUND] + SOUND, 'eras do not run the same', id='modern-first'),
    pytest.param([MODERN + c for c in SOUND], 'no suite command', id='no-handshake-era'),
])
def test_the_part_check_refuses_a_layout_that_could_drop_a_test(commands: list[str], fragment: str) -> None:
    violations = suite_part_violations(commands, MODULES)
    assert any(fragment in v for v in violations), violations


@pytest.mark.unit
@pytest.mark.parametrize(('verify', 'gate', 'workflow', 'fragment'), [
    pytest.param(SOUND, SOUND, SOUND, None, id='sound'),
    pytest.param(SOUND, SOUND[1::-1] + SOUND[2:], SOUND, "release gate's", id='gate-reordered'),
    pytest.param(SOUND, SOUND, SOUND[:3], "workflow's", id='workflow-missing-a-command'),
    pytest.param(SOUND, SOUND, SOUND[:2] + [SOUND[2] + ' -x', SOUND[3]], "workflow's", id='workflow-differs'),
    pytest.param([], [], [], 'runs no suite command', id='empty'),
])
def test_the_list_check_holds_the_three_lists_together(verify: list[str], gate: list[str], workflow: list[str],
                                                       fragment: str | None) -> None:
    violations = list_violations(verify, gate, workflow)
    assert any(fragment in v for v in violations) if fragment else violations == [], violations


@pytest.mark.unit
def test_the_list_readers_read_each_list() -> None:
    agents = ('| verify | `uv lock --check && uv run pytest -q tests/test_a.py && x --help`: prose |\n'
              '### Release recipe\n\n```yaml\nrelease:\n  gate:\n    - uv lock --check\n'
              '    # a comment\n    - uv run pytest -q tests/test_a.py\n    - uv build\n  tag:\n    - uv run pytest -q\n```\n')
    workflow = 'jobs:\n  a:\n    steps:\n      - run: uv sync --locked\n      - run: uv run pytest -q tests/test_a.py\n'
    assert verify_commands(agents) == ['uv run pytest -q tests/test_a.py']
    assert gate_commands(agents) == ['uv run pytest -q tests/test_a.py']
    assert workflow_commands(workflow) == ['uv run pytest -q tests/test_a.py']
