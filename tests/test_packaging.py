# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The uv workspace: one `cluster_mcp` namespace across its members, one version, two commands.

The repository is a uv workspace. `packages/cluster-mcp` holds the core (`cluster_mcp.core`),
`packages/cluster-mcp-slurm` and `packages/cluster-mcp-rcac` the Slurm and RCAC members
(`cluster_mcp.slurm`, `cluster_mcp.rcac`), and the root `pyproject.toml` is the code-less compat
distribution `rcac-mcp`. `cluster_mcp` is a pure namespace: a `cluster_mcp/__init__.py` in any
member would hide every other member's portion, in the editable install and in an installed wheel
alike. The four distributions carry one version (uv does not check it), the core's being the source,
and `__version__` reads it from the installed metadata. The core installs `cluster-mcp`; the root
installs the deprecated `rcac-mcp`; no member installs both.
"""

from __future__ import annotations

import re
import tomllib
from importlib.metadata import distribution, entry_points, version
from pathlib import Path

import pytest

import cluster_mcp
import cluster_mcp.core

ROOT = Path(__file__).resolve().parents[1]

# Each workspace member's directory under packages/, and the namespace subpackage it owns.
MEMBERS = {'cluster-mcp': 'core', 'cluster-mcp-slurm': 'slurm', 'cluster-mcp-rcac': 'rcac'}
COMPAT = 'rcac-mcp'


def pyprojects(root: Path) -> dict[str, dict]:
    """Every distribution's parsed `pyproject.toml` under `root`, by project name."""
    files = [root / 'pyproject.toml', *sorted((root / 'packages').glob('*/pyproject.toml'))]
    docs = [tomllib.loads(f.read_text()) for f in files if f.is_file()]
    return {d['project']['name']: d for d in docs}


def namespace_violations(root: Path) -> list[str]:
    """Every `cluster_mcp/__init__.py` in a member's source, and every portion holding a stranger."""
    found = [f'{p.relative_to(root)}: a namespace __init__.py hides every other member'
             for p in sorted((root / 'packages').glob('*/src/cluster_mcp/__init__.py'))]
    for member, cap in MEMBERS.items():
        portion = root / 'packages' / member / 'src' / 'cluster_mcp'
        held = sorted(p.name for p in portion.iterdir() if p.name != '__pycache__') if portion.is_dir() else []
        if held != [cap] and not (held == ['__init__.py', cap]):
            found.append(f'packages/{member}/src/cluster_mcp holds {held}, expected only {cap}/')
    return found


def version_violations(docs: dict[str, dict]) -> list[str]:
    """Every way the workspace's distributions fail to carry one version, the core's."""
    expected = {*MEMBERS, COMPAT}
    found = [f'no pyproject.toml names {name}' for name in sorted(expected - docs.keys())]
    versions = {name: docs[name]['project'].get('version') for name in sorted(expected & docs.keys())}
    core = versions.get('cluster-mcp')
    found += [f'{name} is version {v!r}, the core is {core!r}' for name, v in versions.items() if v != core or v is None]
    return found


@pytest.mark.unit
def test_no_member_ships_a_namespace_init() -> None:
    assert namespace_violations(ROOT) == []
    assert getattr(cluster_mcp, '__file__', None) is None, f'cluster_mcp is a regular package: {cluster_mcp.__file__}'
    for member, cap in MEMBERS.items():
        wheel = pyprojects(ROOT)[member]['tool']['hatch']['build']['targets']['wheel']
        assert wheel.get('only-include') == [f'src/cluster_mcp/{cap}'] and wheel.get('sources') == ['src'], member
        assert 'packages' not in wheel, f'{member}: `packages` would ship a stray cluster_mcp/__init__.py'


@pytest.mark.unit
def test_namespace_check_catches_a_stray_init(tmp_path: Path) -> None:
    for member, cap in MEMBERS.items():
        (tmp_path / 'packages' / member / 'src' / 'cluster_mcp' / cap).mkdir(parents=True)
    assert namespace_violations(tmp_path) == []
    (tmp_path / 'packages' / 'cluster-mcp-rcac' / 'src' / 'cluster_mcp' / '__init__.py').write_text('')
    violations = namespace_violations(tmp_path)
    assert any('cluster-mcp-rcac/src/cluster_mcp/__init__.py: a namespace __init__.py' in v for v in violations), violations


@pytest.mark.unit
def test_each_member_holds_only_its_own_subpackage(tmp_path: Path) -> None:
    assert sorted(p.name for p in (ROOT / 'packages').iterdir() if p.is_dir()) == sorted(MEMBERS)
    for member, cap in MEMBERS.items():
        (tmp_path / 'packages' / member / 'src' / 'cluster_mcp' / cap).mkdir(parents=True)
    (tmp_path / 'packages' / 'cluster-mcp-slurm' / 'src' / 'cluster_mcp' / 'rcac').mkdir()
    violations = namespace_violations(tmp_path)
    assert any("cluster-mcp-slurm/src/cluster_mcp holds ['rcac', 'slurm']" in v for v in violations), violations
    imported = {cap: Path(__import__(f'cluster_mcp.{cap}', fromlist=['_']).__file__).resolve() for cap in MEMBERS.values()}
    for member, cap in MEMBERS.items():
        home = (ROOT / 'packages' / member / 'src' / 'cluster_mcp' / cap).resolve()
        assert imported[cap].parent == home, f'cluster_mcp.{cap} imports from {imported[cap]}, not {home}'


@pytest.mark.unit
def test_every_distribution_carries_one_version() -> None:
    docs = pyprojects(ROOT)
    assert sorted(docs) == sorted({*MEMBERS, COMPAT})
    assert version_violations(docs) == []


@pytest.mark.unit
def test_version_check_catches_drift() -> None:
    docs = pyprojects(ROOT)
    drifted = {**docs, 'cluster-mcp-slurm': {'project': {**docs['cluster-mcp-slurm']['project'], 'version': '9.9.9'}}}
    assert any(v.startswith("cluster-mcp-slurm is version '9.9.9'") for v in version_violations(drifted))
    missing = {name: doc for name, doc in docs.items() if name != COMPAT}
    assert any(v == f'no pyproject.toml names {COMPAT}' for v in version_violations(missing))


@pytest.mark.unit
def test_version_comes_from_the_installed_metadata() -> None:
    assert cluster_mcp.core.__version__ == version('cluster-mcp') == pyprojects(ROOT)['cluster-mcp']['project']['version']
    source = Path(cluster_mcp.core.__file__).read_text()
    assert "__version__ = get_version('cluster-mcp')" in source
    assert not re.search(r'^__version__\s*=\s*[\'"]', source, re.MULTILINE), 'a hardcoded __version__'


@pytest.mark.unit
def test_console_scripts_are_cluster_mcp_and_the_legacy_alias() -> None:
    docs = pyprojects(ROOT)
    assert docs['cluster-mcp']['project'].get('scripts') == {'cluster-mcp': 'cluster_mcp.core:main'}
    assert docs[COMPAT]['project'].get('scripts') == {'rcac-mcp': 'cluster_mcp.core:legacy_main'}
    for member in ('cluster-mcp-slurm', 'cluster-mcp-rcac'):
        assert 'scripts' not in docs[member]['project'], member
    installed = {(ep.dist.name, ep.name): ep.value for ep in entry_points(group='console_scripts')
                 if ep.dist is not None and ep.dist.name in {*MEMBERS, COMPAT}}
    assert installed == {('cluster-mcp', 'cluster-mcp'): 'cluster_mcp.core:main',
                         (COMPAT, 'rcac-mcp'): 'cluster_mcp.core:legacy_main'}
    assert distribution(COMPAT).requires == ['cluster-mcp']
