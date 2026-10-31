# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The release gate's dependency audit: `bin/audit_lock.py` decides red or green, and fails closed.

`audit_violations` turns one `uv audit` run into an exit status and its reasons. It is green only
when uv reports no finding **and** audited exactly as many packages as `uv.lock` pins from a
registry; a finding, an unreachable advisory source, an audit that could not run, a short, long or
missing summary are each red for their own stated reason. Every verdict is compared whole (the
documented exit status as a literal, and every reason word for word), so a change to any decision
in the script changes a verdict here. The planted outputs below name made-up packages and
advisories: nothing here is a claim about a real one.

The wrapper decides offline itself: it reads `UV_OFFLINE` by uv's own boolean rules, passes it to uv
as `--offline`, and reports any offline audit as an unreachable advisory source, whatever uv printed
and whatever it exited. So these tests pin the wrapper's exit status and its own messages, never
uv's wording, which differs between supported uv releases. uv's boolean vocabulary is spelled out
below, every case form of every word, with values outside it that uv refuses; a unit row pins the
wrapper's reading of each, and an integration row asks the running uv itself, by whether it makes a
request, that it reads each value the same way.

The audit always names this checkout with `--project`, runs the uv that launched it (`UV`, which
`uv run` sets), and runs uv with every `UV_*` variable but a short allowlist removed, so
`UV_PROJECT` (which `bin/sandbox.sh` exports) or a group selector cannot point it at another tree or
a subset. The argv and the allowlist are pinned exactly.

The two audit rows run the real script under `bin/sandbox.sh` with every proxy at a canary:
a loopback listener the test owns that counts the connections made to it and answers none. Offline,
the canary must count zero, so no advisory request was attempted; online, it must count at least
one, which shows the canary sees the requests this uv makes through this wrapper. Each row requires
its own mode's message, so an offline run reported as merely unreachable fails. A unit row shows
the wrapper gives uv the same environment in both modes, so the online count vouches for the
offline zero. The networked proofs (green on the shipped lock, red on a planted one) belong to the
release gate, never to this suite.

`main()` is pinned on what it says: with `subprocess.run` a fake uv that answers only the expected
launch (argv, working directory, environment), each planted run must give exactly the wrapper's exit
status, uv's own output passed through on its own stream, and the wrapper's `audit_lock:` lines on
stderr. So a fault in anything `main()` derives on its way to the verdict (the launch, the offline
decision, the lock it reads, the output it classifies, uv's exit status, the lines it prints) changes
what the wrapper says, under any uv. `main()` decides offline once and `command` takes that decision,
so the argv's `--offline` and the verdict cannot be read from the environment separately; a clean run
under every value of uv's vocabulary and every refused value pins that one decision, and that the
argv and the verdict agree on it, against the vocabulary spelled out here.

The script is stdlib-only and is loaded from its file; nothing here imports the stack.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
import socket
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

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

# A made-up package and advisory in uv's report shape, and a second package with several.
FINDING = ('demo-package 1.0.0 has 1 known vulnerability:\n\n'
           '- DEMO-2026-0001: a planted advisory\n\n  Fixed in: 1.0.1\n')
SECOND_FINDING = ('other-package 2.0.0 has 12 known vulnerabilities:\n\n'
                  '- DEMO-2026-0002: a planted advisory\n\n  Fixed in: 2.0.1\n')
BOTH_NAMED = 'known advisories against locked packages: demo-package 1.0.0, other-package 2.0.0'

# A made-up offline refusal: no uv release prints it, so a verdict that reads uv's text cannot pass.
INVENTED_REFUSAL = 'error: the advisory database is out of reach in this mode\n'

# Every proxy variable uv reads, upper and lower case.
PROXY_VARIABLES = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')

# The documented exit statuses, as literals: a finding, an unreachable source or failed run, and an
# unverified success.
FINDINGS, UNREACHABLE, UNVERIFIED = 1, 2, 3

UNREACHABLE_MESSAGE = 'audit_lock: advisory source unreachable'

# The wrapper's message for each kind of unreachable run, up to uv's exit status.
OFFLINE_MESSAGE = f'{UNREACHABLE_MESSAGE}: the audit ran offline (uv audit exited '
ONLINE_UNREACHABLE_MESSAGE = f'{UNREACHABLE_MESSAGE} (uv audit exited '

NO_SUMMARY = 'uv audit exited 0 without its no-findings summary; the verdict is unverified'

# A lock pinning one registry package beside the project itself and an entry with no source.
ONE_PACKAGE_LOCK = '''version = 1

[[package]]
name = "demo-package"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "rcac-mcp"
version = "0.0.0"
source = { editable = "." }

[[package]]
name = "unsourced"
version = "0.0.0"
'''
EMPTY_LOCK = 'version = 1\n'

# uv's boolean vocabulary for `UV_OFFLINE`, as uv 0.12.17 and 0.13.1 read it: each word in any case
# form. Values outside it are refused by uv (exit 2, no request); the wrapper reads them as offline.
UV_TRUE = ('1', 't', 'true', 'y', 'yes', 'on')
UV_FALSE = ('0', 'f', 'false', 'n', 'no', 'off')
UV_REFUSED = ('', ' 0', '0 ', '\t0', 'off\n', ' false ', ' 1', 'nO ', 'garbage', '2', '00', 'tru',
              'falſe', 'ＴＲＵＥ')


def case_forms(word: str) -> list[str]:
    """Every upper/lower-case spelling of `word`."""
    return sorted({''.join(chars) for chars in itertools.product(*((c.lower(), c.upper()) for c in word))})


UV_ONLINE_VALUES = [form for word in UV_FALSE for form in case_forms(word)]
UV_OFFLINE_VALUES = [form for word in UV_TRUE for form in case_forms(word)] + list(UV_REFUSED)


def offline_reason(returncode: int) -> str:
    return f'advisory source unreachable: the audit ran offline (uv audit exited {returncode})'


@pytest.mark.unit
def test_audit_check_accepts_a_clean_audit() -> None:
    assert PINNED > 0, 'uv.lock pins no registry package; the count cross-check would be vacuous'
    assert audit.audit_violations(0, CLEAN, LOCK) == (0, [])
    assert audit.audit_violations(0, f'warning: planted\n{CLEAN}warning: planted\n', LOCK) == (0, [])
    one = 'Found no known vulnerabilities and no adverse project statuses in 1 package\n'
    assert audit.audit_violations(0, one, ONE_PACKAGE_LOCK) == (0, [])


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'output', 'lock', 'status', 'reasons'), [
    pytest.param(1, FINDING, LOCK, FINDINGS, ['known advisories against locked packages: demo-package 1.0.0'],
                 id='finding'),
    pytest.param(1, f'warning: planted\n{FINDING}{SECOND_FINDING}', LOCK, FINDINGS, [BOTH_NAMED], id='two-findings'),
    pytest.param(1, 'a report in a shape the wrapper does not parse\n', LOCK, FINDINGS,
                 ['known advisories against locked packages: see the report above'], id='finding-unparsed'),
    pytest.param(1, '  - DEMO-2026-0003: other-package 2.0.0 has 1 known vulnerability upstream\n', LOCK, FINDINGS,
                 ['known advisories against locked packages: see the report above'], id='finding-mid-line'),
    pytest.param(0, FINDING + CLEAN, LOCK, FINDINGS, ['known advisories against locked packages: demo-package 1.0.0'],
                 id='finding-with-exit-zero'),
    *(pytest.param(2, f'error: planted\n  Caused by: {marker}: planted\n', LOCK, UNREACHABLE,
                   ['advisory source unreachable (uv audit exited 2)'], id=f'unreachable-{marker}')
      for marker in ('requires network access', 'Request failed', 'error sending request', 'deadline has elapsed',
                     'dns error', 'tcp connect error')),
    pytest.param(101, 'error: planted\n  Caused by: tcp connect error: planted\n', LOCK, UNREACHABLE,
                 ['advisory source unreachable (uv audit exited 101)'], id='unreachable-exit-101'),
    pytest.param(2, "error: unrecognized subcommand 'audit'\n", LOCK, UNREACHABLE,
                 ['the audit could not run (uv audit exited 2)'], id='cannot-run'),
    pytest.param(-9, '', LOCK, UNREACHABLE, ['the audit could not run (uv audit exited -9)'], id='killed'),
    pytest.param(0, CLEAN.replace(f' {PINNED} ', f' {PINNED - 1} '), LOCK, UNVERIFIED,
                 [f'uv audit covered {PINNED - 1} packages, but uv.lock pins {PINNED}'], id='short-count'),
    pytest.param(0, CLEAN.replace(f' {PINNED} ', f' {PINNED + 1} '), LOCK, UNVERIFIED,
                 [f'uv audit covered {PINNED + 1} packages, but uv.lock pins {PINNED}'], id='long-count'),
    pytest.param(0, 'Found no known vulnerabilities and no adverse project statuses in 0 packages\n', EMPTY_LOCK,
                 UNVERIFIED, ['uv audit covered 0 packages, but uv.lock pins 0'], id='empty-lock'),
    pytest.param(0, CLEAN, ONE_PACKAGE_LOCK, UNVERIFIED, [f'uv audit covered {PINNED} packages, but uv.lock pins 1'],
                 id='other-lock'),
    pytest.param(0, '', LOCK, UNVERIFIED, [NO_SUMMARY], id='no-summary'),
    pytest.param(0, f'note: {CLEAN}', LOCK, UNVERIFIED, [NO_SUMMARY], id='summary-mid-line'),
    pytest.param(0, CLEAN.replace('packages\n', 'packages, then more\n'), LOCK, UNVERIFIED, [NO_SUMMARY],
                 id='summary-trailing-text'),
])
def test_audit_check_catches(returncode: int, output: str, lock: str, status: int, reasons: list[str]) -> None:
    assert audit.audit_violations(returncode, output, lock) == (status, reasons)


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'output'), [
    pytest.param(2, INVENTED_REFUSAL, id='invented-wording'),
    pytest.param(2, '', id='no-output'),
    pytest.param(0, CLEAN, id='clean-summary'),
])
def test_offline_audit_is_unreachable_whatever_uv_says(returncode: int, output: str) -> None:
    got = audit.audit_violations(returncode, output, LOCK, offline=True)
    assert got == (UNREACHABLE, [offline_reason(returncode)]), got


@pytest.mark.unit
@pytest.mark.parametrize(('returncode', 'output'), [
    pytest.param(1, FINDING + SECOND_FINDING, id='exit-1'),
    pytest.param(0, FINDING + SECOND_FINDING + CLEAN, id='exit-0'),
])
def test_offline_audit_with_findings_still_exits_unreachable(returncode: int, output: str) -> None:
    got = audit.audit_violations(returncode, output, LOCK, offline=True)
    assert got == (UNREACHABLE, [offline_reason(returncode), BOTH_NAMED]), got


@pytest.mark.unit
@pytest.mark.parametrize(('value', 'offline'), [
    pytest.param(None, False, id='unset'),
    *(pytest.param(v, False, id=f'online-{ascii(v)}') for v in UV_ONLINE_VALUES),
    *(pytest.param(v, True, id=f'offline-{ascii(v)}') for v in UV_OFFLINE_VALUES),
])
def test_offline_setting_reaches_uv_as_a_flag(value: str | None, offline: bool) -> None:
    environ = {'PATH': '/bin', 'UV': '/opt/uv/bin/uv'}
    if value is not None:
        environ['UV_OFFLINE'] = value
    assert audit.offline_requested(environ) is offline, value
    argv = audit.command(environ['UV'], audit.offline_requested(environ))
    assert ('--offline' in argv) is offline, argv
    assert 'UV_OFFLINE' not in audit.child_env(environ), audit.child_env(environ)


UV_PATH = '/opt/uv/bin/uv'
UNREACHABLE_STDERR = 'error: Request failed after 3 retries\n  Caused by: tcp connect error: Connection refused\n'
NO_ADVISORIES = 'no known advisories against any locked package'
ADVISORY_REASON = 'known advisories against locked packages: demo-package 1.0.0'

# The exit status the fake uv gives when main() launched it with anything but the expected argv,
# working directory or environment; no row plants it.
WRONG_LAUNCH = 97


@pytest.mark.unit
@pytest.mark.parametrize(('uv', 'offline', 'returncode', 'stdout', 'stderr', 'status', 'lines'), [
    pytest.param(UV_PATH, None, 0, CLEAN, '', 0, [NO_ADVISORIES], id='online-clean'),
    pytest.param(None, None, 0, CLEAN.replace(f' {PINNED} ', f' {PINNED - 1} '), '', UNVERIFIED,
                 [f'uv audit covered {PINNED - 1} packages, but uv.lock pins {PINNED}'], id='online-short-count'),
    pytest.param(UV_PATH, None, 1, FINDING, 'uv: planted stderr\n', FINDINGS, [ADVISORY_REASON],
                 id='online-finding-on-stdout'),
    pytest.param(UV_PATH, None, 1, FINDING, SECOND_FINDING, FINDINGS, [BOTH_NAMED], id='online-findings-stdout-first'),
    pytest.param(UV_PATH, None, 2, 'uv: planted stdout\n', UNREACHABLE_STDERR, UNREACHABLE,
                 ['advisory source unreachable (uv audit exited 2)'], id='online-unreachable-on-stderr'),
    pytest.param(UV_PATH, None, 5, '', "error: unrecognized subcommand 'audit'\n", UNREACHABLE,
                 ['the audit could not run (uv audit exited 5)'], id='online-cannot-run'),
    pytest.param(UV_PATH, '1', 2, '', INVENTED_REFUSAL, UNREACHABLE, [offline_reason(2)],
                 id='offline-invented-wording'),
    pytest.param(None, '1', 0, CLEAN, '', UNREACHABLE, [offline_reason(0)], id='offline-clean-summary'),
    pytest.param(UV_PATH, 'yes', 1, FINDING, '', UNREACHABLE, [offline_reason(1), ADVISORY_REASON],
                 id='offline-with-findings'),
    *(pytest.param(UV_PATH, v, 0, CLEAN, '', 0, [NO_ADVISORIES], id=f'vocabulary-online-{ascii(v)}')
      for v in UV_ONLINE_VALUES),
    *(pytest.param(UV_PATH, v, 0, CLEAN, '', UNREACHABLE, [offline_reason(0)], id=f'vocabulary-offline-{ascii(v)}')
      for v in UV_OFFLINE_VALUES),
])
def test_main_runs_the_command_and_env_it_derives(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                  tmp_path: Path, uv: str | None, offline: str | None,
                                                  returncode: int, stdout: str, stderr: str, status: int,
                                                  lines: list[str]) -> None:
    """main() reports, as its own exit status and `audit_lock:` lines, exactly what it derives.

    `subprocess.run` is a fake uv that answers the row's planted run only when launched with the
    expected argv, working directory and environment, its output captured as text, and otherwise
    exits WRONG_LAUNCH. The whole of stdout and stderr is compared, so the offline decision, the lock
    read, the output classified, uv's exit status, and where each line goes are all read off what the
    wrapper says, under any uv. The expected `--offline` comes from the vocabulary above, never from
    the wrapper, and the argv uv was given must carry `--offline` exactly when the verdict says the
    audit ran offline: one decision, consumed by both.
    """
    for name, value in (('UV', uv), ('UV_OFFLINE', offline)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:3128')
    monkeypatch.setenv('UV_PROJECT', '/elsewhere')
    monkeypatch.chdir(tmp_path)
    wants_offline = offline is not None and offline not in UV_ONLINE_VALUES
    expected_argv = [uv or 'uv', *audit.ARGS, *(['--offline'] if wants_offline else [])]
    expected_env = audit.child_env(dict(os.environ))
    assert expected_env.get('HTTPS_PROXY') == 'http://127.0.0.1:3128', expected_env
    assert 'UV_PROJECT' not in expected_env and 'UV_OFFLINE' not in expected_env, expected_env
    calls: list[list[str]] = []

    def fake_uv(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        launch = (list(args), kwargs)
        if launch != (expected_argv, {'cwd': audit.ROOT, 'env': expected_env, 'capture_output': True, 'text': True}):
            return subprocess.CompletedProcess(args, WRONG_LAUNCH, '', f'unexpected launch: {launch}\n')
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    monkeypatch.setattr(audit.subprocess, 'run', fake_uv)
    got = audit.main()
    out, err = capsys.readouterr()
    assert len(calls) == 1, calls
    ran_offline = any(line.startswith(OFFLINE_MESSAGE) for line in err.splitlines())
    assert ('--offline' in calls[0]) is ran_offline, (calls[0], err)
    assert (got, out, err) == (status, stdout, stderr + ''.join(f'audit_lock: {line}\n' for line in lines))


@pytest.mark.unit
def test_audit_names_this_checkout_whatever_uv_project_says() -> None:
    args = ['audit', '--frozen', '--no-config', '--preview-features', 'audit-command', '--project', str(REPO_ROOT)]
    assert audit.command(None, False) == ['uv', *args]
    assert audit.command('', False) == ['uv', *args]
    assert audit.command('/opt/uv/bin/uv', False) == ['/opt/uv/bin/uv', *args]
    assert audit.command('/opt/uv/bin/uv', True) == ['/opt/uv/bin/uv', *args, '--offline']
    assert audit.command(None, True) == ['uv', *args, '--offline']
    env = audit.child_env({'UV_PROJECT': '/elsewhere', 'PATH': '/bin'})
    assert 'UV_PROJECT' not in env, env
    assert env == {'PATH': '/bin'}, env


@pytest.mark.unit
def test_audit_env_drops_uv_selectors() -> None:
    kept = {'PATH': '/bin', 'HOME': '/home/someone', 'UV': '/opt/uv/bin/uv', 'UV_CACHE_DIR': '/cache',
            'UV_HTTP_RETRIES': '0', 'UV_NATIVE_TLS': '1', 'UV_SYSTEM_CERTS': '1'}
    dropped = {'UV_PROJECT': '/elsewhere', 'UV_NO_DEV': '1', 'UV_ONLY_GROUP': 'dev', 'UV_NO_GROUP': 'dev',
               'UV_GROUP': 'extra', 'UV_FROZEN': '0', 'UV_CONFIG_FILE': '/etc/uv.toml', 'UV_INDEX_URL': 'http://x',
               'UV_OFFLINE': '1'}
    env = audit.child_env({**kept, **dropped})
    assert env == kept, env
    assert audit.UV_ALLOWED == {k for k in kept if k.startswith('UV_')}, audit.UV_ALLOWED


class Canary:
    """A loopback listener that counts every connection made to it and closes each unanswered.

    `accept` waits on a short timeout in a loop that checks a stop event, so `close()` never relies
    on closing the socket to wake a blocked `accept` (it does not on Linux). Once the loop has
    stopped, `close()` accepts whatever is still queued, so a connection made just before it is
    counted too.
    """

    def __init__(self) -> None:
        self.server = socket.create_server(('127.0.0.1', 0))
        self.server.settimeout(0.05)
        self.url = f'http://127.0.0.1:{self.server.getsockname()[1]}'
        self.connections = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _accept(self) -> bool:
        try:
            connection, _ = self.server.accept()
        except (TimeoutError, BlockingIOError):
            return False
        self.connections += 1
        connection.close()
        return True

    def _serve(self) -> None:
        while not self._stop.is_set():
            self._accept()

    def close(self) -> int:
        """Stop listening and return the number of connections made."""
        self._stop.set()
        self._thread.join()
        self.server.setblocking(False)
        while self._accept():
            pass
        self.server.close()
        return self.connections


def canary_run(argv: list[str], env: dict[str, str], tmp_path: Path) -> tuple[int, str, int]:
    """Run `argv` under bin/sandbox.sh with every proxy at a fresh canary and no retries.

    Returns (exit status, stderr, the connections the canary counted). The advisory service is
    reached only through the canary, which answers nothing, so no run here can reach it.
    """
    canary = Canary()
    try:
        env = {**env, **{name: canary.url for name in PROXY_VARIABLES}, 'UV_HTTP_RETRIES': '0', 'TMPDIR': str(tmp_path)}
        result = subprocess.run([str(SANDBOX), *argv], capture_output=True, text=True, timeout=120, cwd=tmp_path,
                                env=env)
    finally:
        connections = canary.close()
    return result.returncode, result.stderr, connections


def proxied_environ() -> dict[str, str]:
    """This process's environment without anything that would bypass a proxy or set offline."""
    return {k: v for k, v in os.environ.items() if k not in ('NO_PROXY', 'no_proxy', 'UV_OFFLINE')}


def run_audit(tmp_path: Path, offline: bool) -> tuple[int, str, int]:
    """Run the real script under bin/sandbox.sh with every proxy at a canary."""
    env = proxied_environ()
    if offline:
        env['UV_OFFLINE'] = '1'
    return canary_run([sys.executable, str(SCRIPT)], env, tmp_path)


def refusal_violations(returncode: int, stderr: str, message: str) -> list[str]:
    violations: list[str] = []
    if returncode != UNREACHABLE:
        violations.append(f'exit status {returncode}, expected {UNREACHABLE}')
    if message not in stderr:
        violations.append(f'the wrapper does not say {message!r}')
    return violations


def offline_violations(returncode: int, stderr: str, connections: int) -> list[str]:
    """Return every way an offline audit run differs from a closed refusal; empty means it failed closed.

    A closed refusal exits with the unreachable status, the wrapper says the advisory source is
    unreachable because the audit ran offline, and the canary counted no connection, so no request
    was attempted.
    """
    violations = refusal_violations(returncode, stderr, OFFLINE_MESSAGE)
    if connections != 0:
        violations.append(f'the canary counted {connections} connections, so the offline setting did not reach uv')
    return violations


def unreachable_violations(returncode: int, stderr: str, connections: int) -> list[str]:
    """Return every way an online audit with no reachable advisory source differs from a closed refusal.

    A closed refusal exits with the unreachable status and the wrapper says the advisory source is
    unreachable, not that the audit ran offline; the canary counted at least one connection, so it
    does see this uv's requests.
    """
    violations = refusal_violations(returncode, stderr, ONLINE_UNREACHABLE_MESSAGE)
    if connections < 1:
        violations.append('the canary counted no connection, so it cannot vouch for an offline zero')
    return violations


@pytest.mark.integration
def test_audit_fails_closed_offline(tmp_path: Path) -> None:
    refused = f'{OFFLINE_MESSAGE}2)\n'
    assert offline_violations(2, refused, 0) == []
    for returncode, stderr, connections in ((0, refused, 0), (2, refused.replace('unreachable', 'x'), 0),
                                            (2, f'{ONLINE_UNREACHABLE_MESSAGE}2)\n', 0), (2, refused, 1)):
        assert offline_violations(returncode, stderr, connections), (returncode, stderr, connections)

    returncode, stderr, connections = run_audit(tmp_path, offline=True)
    assert offline_violations(returncode, stderr, connections) == [], (connections, stderr)


@pytest.mark.integration
def test_audit_fails_closed_unreachable(tmp_path: Path) -> None:
    refused = f'{ONLINE_UNREACHABLE_MESSAGE}2)\n'
    assert unreachable_violations(2, refused, 1) == []
    for returncode, stderr, connections in ((0, refused, 1), (2, refused.replace('unreachable', 'x'), 1),
                                            (2, f'{OFFLINE_MESSAGE}2)\n', 1), (2, refused, 0)):
        assert unreachable_violations(returncode, stderr, connections), (returncode, stderr, connections)

    returncode, stderr, connections = run_audit(tmp_path, offline=False)
    assert unreachable_violations(returncode, stderr, connections) == [], (connections, stderr)


@pytest.mark.integration
def test_wrapper_reads_uv_offline_as_uv_does(tmp_path: Path) -> None:
    """The running uv makes a request for a `UV_OFFLINE` value exactly when the wrapper reads it as online.

    Each value is handed to uv itself, on the wrapper's own argv and environment with no `--offline`,
    and the canary shows whether uv went online. uv reads a false word as online, a true word as
    offline, and refuses any other value before a request; the wrapper must agree on every one.
    """
    env = audit.child_env(proxied_environ())
    argv = audit.command(env.get('UV'), False)
    assert '--offline' not in argv, argv
    values = UV_ONLINE_VALUES + UV_OFFLINE_VALUES

    def requests_made(value: str) -> int:
        return canary_run(argv, {**env, 'UV_OFFLINE': value}, tmp_path)[2]

    with ThreadPoolExecutor(max_workers=8) as pool:
        requests = dict(zip(values, pool.map(requests_made, values)))
    assert {v for v, n in requests.items() if n > 0} == set(UV_ONLINE_VALUES), requests
    disagreements = {v: n for v, n in requests.items() if (n > 0) is audit.offline_requested({'UV_OFFLINE': v})}
    assert disagreements == {}, disagreements
