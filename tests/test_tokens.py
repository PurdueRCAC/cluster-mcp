# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""The shared secret has a 32-character floor, and the signer and the verifier agree on every claim.

`create_jwt_auth()` and `rcac-mcp --generate-token` each enforce the floor on their own (§ Invariants
§6), so each is pinned on its own: an unset, empty or 31-character `JWT_SECRET` is refused, and 32
characters is accepted. The CLI refuses with `exit_status.bad_argument`, nothing on stdout, and a
reason naming `JWT_SECRET`, because a removed `--generate-token` flag also exits 2.

A token minted by `generate_token`, or by the sandboxed CLI, is accepted by the `jwt` verifier built
from the same secret, and the command runs as the user its subject maps to. A token whose issuer,
audience, secret or algorithm differs, or that has expired, is rejected with a 401 and nothing runs.
Every token travels the harness's in-process HTTP route, so the real `JWTVerifier` decides; that
route is the `stack-upgrade` rewrite point, not this module.

Recorded limitation: `ISSUER == AUDIENCE == 'rcac-mcp'`, so a signer that swapped the two claims
mints the very same token and no test can tell the swap apart. It is not a defect while the two
constants are equal.

CLI drives run the installed console script through `bin/sandbox.sh`, which blanks `JWT_SECRET`;
`env` then sets the test secret inside the sandbox. The `unset` row omits `env`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import jwt
import pytest
from cmdkit.app import exit_status

from harness import JWTVerifier, Outcome, call_http, delegate_server, drive, mint, serving, user_map
from rcac_mcp.auth import create_jwt_auth
from rcac_mcp.token import ALGORITHM, AUDIENCE, ISSUER, generate_token
from test_identity import delegation_violations
from test_no_executor import report

TESTS = Path(__file__).resolve().parent
SANDBOX = TESTS.parent / 'bin' / 'sandbox.sh'

# The installed console script, which the editable install points at this tree.
CLI = Path(sys.executable).with_name('rcac-mcp')

SECRET = 's' * 32
OTHER_SECRET = 'z' * 32
USER_MAP = 'alice ualice\nbob ubob\n'
COMMAND = 'echo token-check'

SHORT_SECRETS = [
    pytest.param(None, id='unset'),
    pytest.param('', id='empty'),
    pytest.param('s' * 31, id='31-chars'),
]


def token_cli_violations(returncode: int, stdout: str, stderr: str, accept: bool, secret: str | None = None,
                         sub: str | None = None) -> list[str]:
    """Return every way a `--generate-token` run differs from the expected outcome; empty means it matched.

    To accept, the run exits 0 and prints exactly one line: a token that decodes with `secret` and
    the shared issuer, audience and algorithm, whose subject is `sub`. To refuse, it exits with
    `exit_status.bad_argument`, prints nothing to stdout, and names `JWT_SECRET` in stderr.
    """
    violations: list[str] = []
    if not accept:
        if returncode != exit_status.bad_argument:
            violations.append(f'exit status {returncode}, expected {exit_status.bad_argument}')
        if stdout:
            violations.append(f'stdout is not empty on a refusal (a token was printed?): {stdout[:80]!r}')
        if 'JWT_SECRET' not in stderr:
            violations.append(f'refusal reason does not name JWT_SECRET: {stderr[-200:]!r}')
        return violations
    if returncode != 0:
        violations.append(f'exit status {returncode}, expected 0: {stderr[-200:]!r}')
    lines = stdout.splitlines()
    if len(lines) != 1:
        violations.append(f'stdout holds {len(lines)} lines, expected exactly one token: {stdout[:160]!r}')
    if not lines:
        violations.append('no token was printed')
        return violations
    try:
        claims = jwt.decode(lines[0].strip(), secret, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    except jwt.PyJWTError as exc:
        violations.append(f'token does not decode with the secret and the shared claims: {exc}')
        return violations
    if claims.get('sub') != sub:
        violations.append(f'subject {claims.get("sub")!r}, expected {sub!r}')
    return violations


def generate(secret: str | None, sub: str = 'alice') -> subprocess.CompletedProcess[str]:
    """Run `rcac-mcp --generate-token --sub <sub>` in the sandbox with `JWT_SECRET` set to `secret`."""
    env = [] if secret is None else ['env', f'JWT_SECRET={secret}']
    return subprocess.run([str(SANDBOX), *env, str(CLI), '--generate-token', '--sub', sub],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)


def present(map_path: str, token: str) -> Outcome:
    """Build a delegate server inside the driven loop and call `run_command` over HTTP with `token`."""
    async def scenario() -> Outcome:
        server = delegate_server(map_path)
        async with serving(server) as app:
            return await call_http(app, token, 'run_command', {'command': COMMAND})

    return drive(scenario())


@pytest.mark.unit
@pytest.mark.parametrize('secret', SHORT_SECRETS)
def test_jwt_auth_refuses_short_secret(secret: str | None, monkeypatch: pytest.MonkeyPatch, guard) -> None:
    if secret is None:
        monkeypatch.delenv('JWT_SECRET', raising=False)
    else:
        monkeypatch.setenv('JWT_SECRET', secret)
    with pytest.raises(ValueError, match='JWT_SECRET'):
        create_jwt_auth()
    assert guard.refused == []


@pytest.mark.unit
def test_jwt_auth_accepts_32_char_secret(monkeypatch: pytest.MonkeyPatch, guard) -> None:
    monkeypatch.setenv('JWT_SECRET', SECRET)
    provider = create_jwt_auth()
    assert isinstance(provider, JWTVerifier), f'create_jwt_auth returned {provider!r}'
    assert guard.refused == []


@pytest.mark.integration
@pytest.mark.parametrize('secret', SHORT_SECRETS)
def test_generate_token_refuses_short_secret(secret: str | None) -> None:
    result = generate(secret)
    violations = token_cli_violations(result.returncode, result.stdout, result.stderr, False)
    assert violations == [], report(violations)


@pytest.mark.integration
def test_generate_token_accepts_32_char_secret() -> None:
    result = generate(SECRET, sub='alice')
    violations = token_cli_violations(result.returncode, result.stdout, result.stderr, True, SECRET, 'alice')
    assert violations == [], report(violations)


@pytest.mark.unit
def test_minted_token_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, launches: list[list[str]],
                                  guard) -> None:
    monkeypatch.setenv('JWT_SECRET', SECRET)
    outcome = present(user_map(tmp_path, USER_MAP), generate_token(SECRET, 60, 'alice'))
    violations = delegation_violations(outcome, launches, 'ualice', COMMAND)
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.integration
def test_cli_minted_token_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      request: pytest.FixtureRequest) -> None:
    """The CLI's token, presented to the verifier built from the same secret, runs as its subject.

    The sandboxed CLI drive runs first, with the real `subprocess.Popen`; only then is the
    `launches` recorder requested, so the in-process server call that follows is fenced and
    reaches no real `sudo`.
    """
    result = generate(SECRET, sub='alice')
    violations = token_cli_violations(result.returncode, result.stdout, result.stderr, True, SECRET, 'alice')
    launches = request.getfixturevalue('launches')
    monkeypatch.setenv('JWT_SECRET', SECRET)
    outcome = present(user_map(tmp_path, USER_MAP), result.stdout.strip())
    violations += delegation_violations(outcome, launches, 'ualice', COMMAND)
    assert violations == [], report(violations)


@pytest.mark.unit
@pytest.mark.parametrize('mismatch', [
    pytest.param({'iss': 'another-issuer'}, id='issuer'),
    pytest.param({'aud': 'another-audience'}, id='audience'),
    pytest.param({'secret': OTHER_SECRET}, id='secret'),
    pytest.param({'alg': 'HS512'}, id='algorithm'),
    pytest.param({'exp_in': -60}, id='expired'),
])
def test_mismatched_token_is_rejected(mismatch: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      launches: list[list[str]], guard) -> None:
    monkeypatch.setenv('JWT_SECRET', SECRET)
    fields = dict(mismatch)
    token = mint(fields.pop('secret', SECRET), sub='alice', **fields)
    outcome = present(user_map(tmp_path, USER_MAP), token)
    violations = []
    if outcome.status != 401:
        violations.append(f'status {outcome.status}, expected 401: {outcome!r}')
    if launches:
        violations.append(f'process launched for a rejected token: {launches!r}')
    assert violations == [], report(violations)
    assert guard.refused == []


# Module-level tokens outlive any suite run: they are decoded only when the drift rows run.
TOKEN = generate_token(SECRET, 3600, 'alice')
REFUSED = 'CRITICAL [rcac_mcp] JWT_SECRET must be at least 32 characters'


@pytest.mark.unit
@pytest.mark.parametrize(('run', 'accept', 'fragment'), [
    pytest.param((0, TOKEN + '\n', ''), False, 'exit status 0', id='accepted-short-secret'),
    pytest.param((2, TOKEN + '\n', REFUSED), False, 'stdout', id='token-on-refusal'),
    pytest.param((1, '', REFUSED), False, 'exit status 1', id='wrong-status'),
    pytest.param((2, '', 'CRITICAL [rcac_mcp] unrecognized arguments: --generate-token'), False, 'reason',
                 id='refused-for-another-reason'),
    pytest.param((0, '', ''), True, 'no token', id='no-token'),
    pytest.param((0, TOKEN + '\n' + TOKEN + '\n', ''), True, 'stdout holds 2 lines', id='two-lines'),
    pytest.param((0, generate_token(OTHER_SECRET, 3600, 'alice') + '\n', ''), True, 'token does not decode',
                 id='other-secret'),
    pytest.param((0, generate_token(SECRET, 3600, 'bob') + '\n', ''), True, 'subject', id='wrong-subject'),
])
def test_token_check_catches_drift(run: tuple[int, str, str], accept: bool, fragment: str) -> None:
    assert token_cli_violations(0, TOKEN + '\n', '', True, SECRET, 'alice') == []
    assert token_cli_violations(2, '', REFUSED, False) == []
    violations = token_cli_violations(*run, accept, SECRET if accept else None, 'alice' if accept else None)
    assert any(fragment in v for v in violations), violations
