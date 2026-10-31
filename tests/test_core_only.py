# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A real install of the core alone starts, and serves the core and nothing else.

The capabilities are the core's extras, so `cluster-mcp` without an extra is the core alone. The
development environment carries every member (the root's extras), so the core alone is a real
environment of its own: built once per session with `uv sync --package cluster-mcp --no-dev`, frozen
and offline from the cache the development sync filled, into a scratch directory, never `.venv`. It
is editable, so it runs this tree's source, never a cached wheel.

In it, only the core's distribution is installed and the capability group is empty; after the startup
load the tool registry holds exactly the core's seven tools; and its `cluster-mcp`, driven over stdio
in the selected protocol era, serves exactly those tools, only the core's context resources (no
storage resource), and a base that is the core's text and lists exactly the tools it serves.

Every launch goes through `bin/sandbox.sh`. `VIRTUAL_ENV` is dropped, so uv targets the scratch
environment and nothing else; `PYTHONPATH` is passed through, so a mutated copy of the core is the
core that runs.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from harness import ERA, SANDBOX, stdio_tools
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.site import HEADING
from test_instructions import LISTED, instruction_violations

# The core's tools and resources, pinned here rather than read from the tree.
CORE_TOOLS = {'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file',
              'cluster_context'}
CORE_RESOURCES = {'cluster://context', 'rcac://context'}
STORAGE_URIS = {'cluster://storage', 'rcac://storage'}

# Run in the core-only environment's own interpreter, isolated: what is installed, what the group
# lists, and what the startup load registers.
PROBE = '''\
import importlib.metadata as md, json
from cluster_mcp.core.capabilities import GROUP, installed
from cluster_mcp.core.tools import TOOL_REGISTRY
before = [tool.name for tool in TOOL_REGISTRY]
loaded = [entry.distribution for entry in installed()]
print(json.dumps({
    'distributions': sorted(d.metadata['Name'] for d in md.distributions()
                            if d.metadata['Name'].replace('_', '-').lower().startswith(('cluster-mcp', 'rcac-mcp'))),
    'entry_points': sorted(ep.name for ep in md.entry_points(group=GROUP)),
    'loaded': loaded,
    'before': before,
    'registry': [tool.name for tool in TOOL_REGISTRY],
}))
'''


def child_env() -> dict[str, str]:
    """This process's environment, minus `VIRTUAL_ENV`, with FastMCP's update check off."""
    env = {k: v for k, v in os.environ.items() if k not in ('VIRTUAL_ENV', 'UV_PROJECT_ENVIRONMENT')}
    env['FASTMCP_CHECK_FOR_UPDATES'] = 'off'
    return env


@pytest.fixture(scope='session')
def core_only(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real editable environment holding the core alone; its directory."""
    venv = tmp_path_factory.mktemp('core-only') / 'venv'
    env = {**child_env(), 'UV_PROJECT_ENVIRONMENT': str(venv)}
    result = subprocess.run([str(SANDBOX), 'uv', 'sync', '-q', '--package', 'cluster-mcp', '--no-dev', '--frozen',
                             '--offline'], capture_output=True, text=True, timeout=300, env=env)
    assert result.returncode == 0, f'cannot build the core-only environment:\n{result.stderr}'
    assert (venv / 'bin' / 'cluster-mcp').is_file(), f'no cluster-mcp in {venv}'
    return venv


@pytest.mark.integration
def test_core_only_registry_holds_exactly_the_core_tools(core_only: Path) -> None:
    result = subprocess.run([str(SANDBOX), str(core_only / 'bin' / 'python'), '-I', '-c', PROBE],
                            capture_output=True, text=True, timeout=120, env=child_env())
    assert result.returncode == 0, result.stderr
    found = json.loads(result.stdout)
    assert found['distributions'] == ['cluster-mcp'], f'the core-only install holds {found["distributions"]}'
    assert found['entry_points'] == [] and found['loaded'] == [], found
    assert sorted(found['registry']) == sorted(CORE_TOOLS), f'TOOL_REGISTRY after the startup load: {found["registry"]}'
    assert len(found['registry']) == len(set(found['registry'])), found['registry']
    assert found['before'] == found['registry'], 'importing the core registered other tools than the startup load'


@pytest.mark.integration
def test_core_only_install_serves_the_core(core_only: Path) -> None:
    listed = stdio_tools([str(SANDBOX), str(core_only / 'bin' / 'cluster-mcp'), '-e', 'local'], ERA, env=child_env())
    assert listed.tools, 'the core-only server listed no tool'
    assert sorted(listed.tools) == sorted(CORE_TOOLS), f'serves {sorted(set(listed.tools) ^ CORE_TOOLS)} beyond or ' \
                                                       f'short of the core'
    assert len(listed.tools) == len(set(listed.tools)), listed.tools
    assert listed.tools[-1] == 'cluster_context', listed.tools
    assert listed.resources, 'the core-only server listed no resource'
    assert set(listed.resources) == CORE_RESOURCES, f'serves resources {sorted(listed.resources)}'
    assert not STORAGE_URIS & set(listed.resources), 'a storage resource is served without the RCAC capability'


@pytest.mark.integration
def test_core_only_instructions_name_exactly_its_tools(core_only: Path) -> None:
    listed = stdio_tools([str(SANDBOX), str(core_only / 'bin' / 'cluster-mcp'), '-e', 'local'], ERA, env=child_env())
    base, heading, _ = (listed.instructions or '').partition(f'\n\n{HEADING}\n\n')
    assert heading, 'the served instructions carry no site section'
    assert base == CORE_INSTRUCTIONS, 'the core-only base is not the core text alone'
    names = LISTED.findall(base)
    assert names, 'the base lists no tool'
    assert len(names) == len(set(names)), f'the base lists a tool twice: {names}'
    assert sorted(names) == sorted(listed.tools), f'the base lists {sorted(set(names) - set(listed.tools))} not ' \
                                                  f'served and omits {sorted(set(listed.tools) - set(names))}'
    assert instruction_violations(base, listed.tools) == []
