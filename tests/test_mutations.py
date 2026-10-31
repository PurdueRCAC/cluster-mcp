# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The fast half of the planted-violation runner (`mutants.py`), kept in the suite.

`test_mutation_anchor_applies[<case>]` goes red the moment a change moves the code a planted
violation edits: the contract that case pins has moved, and the case must be re-planted against the
new code before its targets can be trusted again. The `mutation_violations` controls prove the
runner cannot count a child as a kill unless every target failed for the case's stated reason.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mutants import CASES, MEMBERS, REPO_FILES, SURVIVOR_CONTROL, Case, apply, apply_repo, mutation_violations

TARGETS = ['test_isolation.py::test_a', 'test_isolation.py::test_b']
WHY = 'ran as'


def junit(*cases: tuple[str, str, str]) -> str:
    """A pytest-shaped JUnit report holding (name, child tag or '', message) testcases."""
    body = ''.join(
        f'<testcase classname="tests.test_isolation" name="{name}">'
        + (f'<{tag} message="{message}">{message}</{tag}>' if tag else '')
        + '</testcase>'
        for name, tag, message in cases)
    return f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>'


KILLED = junit(('test_a', 'failure', 'AssertionError: echo A ran as ubob, expected ualice'),
               ('test_b', 'failure', 'AssertionError: echo B ran as ualice, expected ubob'))


@pytest.mark.unit
@pytest.mark.parametrize('case', CASES, ids=[c.id for c in CASES])
def test_mutation_anchor_applies(case: Case, tmp_path: Path) -> None:
    src_root = apply(case, tmp_path)
    if case.file:
        mutated = src_root / 'cluster_mcp' / case.file
        compile(mutated.read_text(), str(mutated), 'exec')
    repo = apply_repo(case, tmp_path)
    if repo is not None:
        root = Path(__file__).resolve().parents[1]
        changed = [name for name in REPO_FILES if (repo / name).read_text() != (root / name).read_text()]
        assert changed == sorted({name for name, _, _ in case.repo_edits}), changed
    assert case.targets and case.why and (case.edits or case.repo_edits)


@pytest.mark.unit
def test_mutation_case_files_name_a_member(tmp_path: Path) -> None:
    # A case file is relative to the namespace, its member first, so it names the same file in the
    # copy and in any install; the copy holds every member and, like each member, no __init__.py.
    # A case planting only into repository files has no file, and plants only into `REPO_FILES`.
    repo_only = [c for c in CASES if not c.file and not c.edits and c.repo_edits]
    strays = [f'{c.id}: {c.file}' for c in (*CASES, SURVIVOR_CONTROL)
              if c.file.split('/')[0] not in MEMBERS and c not in repo_only]
    strays += [f'{c.id}: {name}' for c in CASES for name, _, _ in c.repo_edits if name not in REPO_FILES]
    assert strays == [], strays
    assert sorted(MEMBERS) == ['core', 'rcac', 'slurm']
    namespace = apply(SURVIVOR_CONTROL, tmp_path) / 'cluster_mcp'
    assert sorted(p.name for p in namespace.iterdir()) == ['core', 'rcac', 'slurm']
    assert not (namespace / '__init__.py').exists()
    partial = apply(SURVIVOR_CONTROL, tmp_path / 'partial', omit='rcac') / 'cluster_mcp'
    assert sorted(p.name for p in partial.iterdir()) == ['core', 'slurm']


@pytest.mark.unit
def test_mutation_check_accepts_a_clean_kill() -> None:
    assert mutation_violations(1, KILLED, TARGETS, WHY) == []


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'report', 'fragment'), [
    pytest.param(0, junit(('test_a', '', ''), ('test_b', '', '')), 'survived', id='all-passed'),
    pytest.param(1, junit(('test_a', 'failure', 'ran as ubob'), ('test_b', '', '')),
                 'test_b: passed', id='target-passed'),
    pytest.param(2, junit(('test_a', 'error', 'collection failure'), ('test_b', 'error', 'collection failure')),
                 'exited 2', id='collection-error'),
    pytest.param(4, None, 'exited 4', id='usage-error'),
    pytest.param(1, junit(('test_a', 'failure', 'ran as ubob')), 'test_b: missing', id='target-missing'),
    pytest.param(97, None, 'wrong import origin', id='wrong-origin'),
    pytest.param(1, junit(('test_a', 'failure', "NameError: name 'FastMCPx' is not defined"),
                          ('test_b', 'failure', 'ran as ualice')),
                 'test_a: killed for the wrong reason', id='wrong-reason'),
    pytest.param(1, junit(('test_a', 'error', 'ran as ubob'), ('test_b', 'failure', 'ran as ualice')),
                 'test_a: error, not a failure', id='error-not-failure'),
    pytest.param(1, junit(('test_a', 'error', 'failed on teardown'), ('test_b', 'failure', 'ran as ualice')),
                 'test_a: error, not a failure', id='teardown-error-only'),
])
def test_mutation_check_flags_survivors(returncode: int, report: str | None, fragment: str) -> None:
    violations = mutation_violations(returncode, report, TARGETS, WHY)
    assert any(fragment in v for v in violations), violations
