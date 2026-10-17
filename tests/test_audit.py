# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""The release gate's dependency audit: `bin/audit_lock.py` decides red or green, and fails closed.

`audit_violations` turns one `uv audit` run into an exit status and its reasons. It is green only
when uv reports no finding **and** audited exactly as many packages as `uv.lock` pins from a
registry; a finding, an unreachable advisory source, an audit that could not run, a short or
missing summary are each red for their own stated reason. The planted outputs below name a made-up
package and advisory: nothing here is a claim about a real one.

The audit always names this checkout with `--project` and runs uv with every `UV_*` variable but a
short allowlist removed, so `UV_PROJECT` (which `bin/sandbox.sh` exports) or a group selector cannot
point it at another tree or a subset.

The one integration row runs the real script under `bin/sandbox.sh` offline **by construction**:
uv is told it is offline and every proxy is a dead loopback port, and uv's own offline refusal must
be in the output, so no advisory lookup was attempted. The networked proofs (green on the shipped
lock, red on a planted one) belong to the release gate, never to this suite.

The script is stdlib-only and is loaded from its file; nothing here imports the stack.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX = REPO_ROOT / 'bin' / 'sandbox.sh'
SCRIPT = REPO_ROOT / 'bin' / 'audit_lock.py'


def load_audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location('audit_lock', SCRIPT)
    assert spec is not None and spec.loader is not None, f'cannot load {SCRIPT}'
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load_audit()

LOCK = (REPO_ROOT / 'uv.lock').read_text()
PINNED = audit.registry_packages(LOCK)
CLEAN = f'Found no known vulnerabilities and no adverse project statuses in {PINNED} packages\n'

# A made-up package and advisory in uv's report shape.
FINDING = ('demo-package 1.0.0 has 1 known vulnerability:\n\n'
           '- DEMO-2026-0001: a planted advisory\n\n  Fixed in: 1.0.1\n')

OFFLINE_REFUSAL = 'requires network access and cannot be performed in offline mode'

# Every proxy variable uv reads, upper and lower case, at a loopback port nothing listens on.
DEAD_PROXY = 'http://127.0.0.1:9'
PROXY_VARIABLES = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')


@pytest.mark.unit
def test_audit_check_accepts_a_clean_audit() -> None:
    assert PINNED > 0, 'uv.lock pins no registry package; the count cross-check would be vacuous'
    assert audit.audit_violations(0, CLEAN, LOCK) == (0, [])


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'output', 'status', 'reason'), [
    pytest.param(1, FINDING, audit.EXIT_FINDINGS, 'demo-package 1.0.0', id='finding'),
    pytest.param(2, f'error: Auditing {OFFLINE_REFUSAL}\n', audit.EXIT_UNREACHABLE,
                 'advisory source unreachable', id='offline'),
    pytest.param(2, 'error: Request failed after 3 retries\n  Caused by: tcp connect error: Connection refused\n',
                 audit.EXIT_UNREACHABLE, 'advisory source unreachable', id='unreachable'),
    pytest.param(2, "error: unrecognized subcommand 'audit'\n", audit.EXIT_UNREACHABLE,
                 'the audit could not run', id='cannot-run'),
    pytest.param(0, CLEAN.replace(f' {PINNED} ', f' {PINNED - 1} '), audit.EXIT_UNVERIFIED,
                 f'covered {PINNED - 1} packages', id='short-count'),
    pytest.param(0, '', audit.EXIT_UNVERIFIED, 'without its no-findings summary', id='no-summary'),
    pytest.param(0, FINDING + CLEAN, audit.EXIT_FINDINGS, 'demo-package 1.0.0', id='finding-with-exit-zero'),
])
def test_audit_check_catches(returncode: int, output: str, status: int, reason: str) -> None:
    got_status, reasons = audit.audit_violations(returncode, output, LOCK)
    assert got_status == status, (got_status, reasons)
    assert any(reason in r for r in reasons), reasons


@pytest.mark.unit
def test_audit_names_this_checkout_whatever_uv_project_says() -> None:
    command = audit.COMMAND
    assert command[:2] == ['uv', 'audit'], command
    for flag in ('--frozen', '--no-config'):
        assert flag in command, f'the audit runs without {flag}'
    assert command.count('--project') == 1, command
    assert Path(command[command.index('--project') + 1]) == REPO_ROOT, command
    env = audit.child_env({'UV_PROJECT': '/elsewhere', 'PATH': '/bin'})
    assert 'UV_PROJECT' not in env, env
    assert env == {'PATH': '/bin'}, env


@pytest.mark.unit
def test_audit_env_drops_uv_selectors() -> None:
    kept = {'PATH': '/bin', 'HOME': '/home/someone', 'UV_CACHE_DIR': '/cache', 'UV_OFFLINE': '1',
            'UV_NATIVE_TLS': '1', 'UV_SYSTEM_CERTS': '1'}
    dropped = {'UV_PROJECT': '/elsewhere', 'UV_NO_DEV': '1', 'UV_ONLY_GROUP': 'dev', 'UV_NO_GROUP': 'dev',
               'UV_GROUP': 'extra', 'UV_FROZEN': '0', 'UV_CONFIG_FILE': '/etc/uv.toml', 'UV_INDEX_URL': 'http://x'}
    env = audit.child_env({**kept, **dropped})
    assert env == kept, env


def offline_violations(returncode: int, stderr: str) -> list[str]:
    """Return every way an offline audit run differs from a closed refusal; empty means it failed closed.

    A closed refusal exits with the unreachable status, says the advisory source is unreachable, and
    carries uv's own offline refusal, which proves uv attempted no request.
    """
    violations: list[str] = []
    if returncode != audit.EXIT_UNREACHABLE:
        violations.append(f'exit status {returncode}, expected {audit.EXIT_UNREACHABLE}')
    if 'advisory source unreachable' not in stderr:
        violations.append('the refusal does not say the advisory source is unreachable')
    if OFFLINE_REFUSAL not in stderr:
        violations.append("uv's own offline refusal is missing, so a request may have been attempted")
    return violations


@pytest.mark.integration
def test_audit_fails_closed_offline(tmp_path: Path) -> None:
    refused = f'error: Auditing {OFFLINE_REFUSAL}\naudit_lock: advisory source unreachable (uv audit exited 2)\n'
    assert offline_violations(2, refused) == []
    for returncode, stderr in ((0, refused), (2, refused.replace('advisory source unreachable', 'x')),
                               (2, 'error: Request failed\naudit_lock: advisory source unreachable\n')):
        assert offline_violations(returncode, stderr), (returncode, stderr)

    env = dict(os.environ, UV_OFFLINE='1', TMPDIR=str(tmp_path))
    env.update({name: DEAD_PROXY for name in PROXY_VARIABLES})
    env.pop('NO_PROXY', None)
    env.pop('no_proxy', None)
    result = subprocess.run([str(SANDBOX), sys.executable, str(SCRIPT)],
                            capture_output=True, text=True, timeout=120, cwd=tmp_path, env=env)
    assert offline_violations(result.returncode, result.stderr) == [], result.stderr
