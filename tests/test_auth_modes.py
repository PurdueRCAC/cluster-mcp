# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The auth registry: OIDC is all-or-nothing, `none` installs nothing, and `AUTH_MODES` says what it holds.

`create_auth_oidc()` refuses a configuration missing any of `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`,
`OIDC_CLIENT_SECRET` or `MCP_BASE_URL` (unset or empty) with a `ValueError` naming all four, before
any provider is built and before any request leaves the process (§ Invariants §6). Each row
replaces `cluster_mcp.core.auth.OIDCProxy` with a recorder, so "nothing built" is observed rather than
assumed, and the unit guard records any network reach (the real proxy fetches its discovery
document when it is built). With all four set the recorder is reached, so the refusal rows cannot
pass vacuously; the keywords it receives are bound against the real `OIDCProxy` signature, so a
keyword the real class lacks fails here instead of at a deployment's first start. The proxy keeps
the FastMCP 2.x posture: client-metadata (CIMD) fetches and `resource` forwarding are passed off.

`none` installs no provider: its factory returns None, a server built in that mode holds none, and a
tokenless HTTP call to it is answered.

`typing.get_type_hints(cluster_mcp.core.auth)['AUTH_MODES']` resolves to `Final` of a mapping from `str` to a
zero-argument factory returning an `AuthProvider` (or None). The annotation once carried a stray
`:` that made the `Final` argument a `slice`; evaluation succeeded all the same, so the check reads
the resolved shape, not merely that it resolves.

No module here imports the stack: the real `OIDCProxy` and `AuthProvider` are read from
`cluster_mcp.core.auth`, which is what the code under test uses.
"""

from __future__ import annotations

import collections.abc
import inspect
import typing
from typing import Any, Callable, Dict, Final, Mapping, Sequence

import pytest

import cluster_mcp.core.auth
from harness import Outcome, RecordingExecutor, call_http, drive, installed_auth, serving, shared_server
from cluster_mcp.core.auth import AUTH_MODES, AuthProvider, create_auth_oidc

OIDC_VARIABLES = ('OIDC_CONFIG_URL', 'OIDC_CLIENT_ID', 'OIDC_CLIENT_SECRET', 'MCP_BASE_URL')

# Placeholder values under reserved, unresolvable names: nothing here is a real endpoint or secret.
OIDC_VALUES = {
    'OIDC_CONFIG_URL': 'https://idp.invalid/.well-known/openid-configuration',
    'OIDC_CLIENT_ID': 'test-client',
    'OIDC_CLIENT_SECRET': 'test-client-secret',
    'MCP_BASE_URL': 'https://mcp.invalid',
}

# What `create_auth_oidc()` hands the proxy for each variable.
OIDC_KEYWORDS = {'OIDC_CONFIG_URL': 'config_url', 'OIDC_CLIENT_ID': 'client_id',
                 'OIDC_CLIENT_SECRET': 'client_secret', 'MCP_BASE_URL': 'base_url'}

# The two behaviours FastMCP 4's proxy adds, on by default, that the 2.x posture keeps off.
POSTURE = ('enable_cimd', 'forward_resource')

# Read at import, before any test replaces it.
PROXY_SIGNATURE = inspect.signature(cluster_mcp.core.auth.OIDCProxy)


def oidc_violations(raised: BaseException | None, message: str, built: Sequence[Any],
                    refused: Sequence[Any]) -> list[str]:
    """Return every way a half-configured OIDC build differs from the refusal; empty means it refused.

    `raised` is what `create_auth_oidc()` raised (None when it returned), `message` its text, `built`
    every construction the proxy recorder saw, and `refused` every process or network reach the
    unit guard refused. The refusal is a `ValueError` naming all four variables, with nothing built
    and nothing reached.
    """
    violations: list[str] = []
    if raised is None:
        violations.append('raised no ValueError: a half configuration was accepted')
    elif not isinstance(raised, ValueError):
        violations.append(f'raised {type(raised).__name__}, expected ValueError: {message!r}')
    for variable in OIDC_VARIABLES:
        if raised is not None and variable not in message:
            violations.append(f'the error does not name {variable}: {message!r}')
    if built:
        violations.append(f'a provider was built before the check refused: {list(built)!r}')
    if refused:
        violations.append(f'reached for the network or a process before refusing: {list(refused)!r}')
    return violations


def proxy_violations(signature: inspect.Signature, args: Sequence[Any], kwargs: Mapping[str, Any],
                     expected: Mapping[str, Any]) -> list[str]:
    """Return every way a recorded proxy construction differs from a valid one; empty means it matched.

    The arguments must bind to `signature` (the real `OIDCProxy`'s), so an unknown keyword or a
    positional argument fails; each `expected` keyword must arrive with its value.
    """
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as exc:
        return [f'the arguments are not a keyword set OIDCProxy accepts: {exc}']
    violations = []
    for name, value in expected.items():
        if bound.arguments.get(name) != value:
            violations.append(f'{name}={bound.arguments.get(name)!r}, expected {value!r}')
    return violations


def posture_violations(signature: inspect.Signature, args: Sequence[Any], kwargs: Mapping[str, Any]) -> list[str]:
    """Return each 2.x-posture keyword that is not False once the real signature's defaults apply."""
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError as exc:
        return [f'the arguments are not a keyword set OIDCProxy accepts: {exc}']
    bound.apply_defaults()
    return [f'{name}={bound.arguments.get(name)!r}, expected False (the FastMCP 2.x posture)'
            for name in POSTURE if bound.arguments.get(name) is not False]


class ProxyRecorder:
    """Stands in for `OIDCProxy`: records each construction's arguments and builds nothing."""

    def __init__(self) -> None:
        self.built: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> ProxyRecorder:
        self.built.append((args, kwargs))
        return self


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> ProxyRecorder:
    rec = ProxyRecorder()
    monkeypatch.setattr(cluster_mcp.core.auth, 'OIDCProxy', rec)
    return rec


def configure(monkeypatch: pytest.MonkeyPatch, missing: str | None = None, how: str = 'unset') -> None:
    """Set the four OIDC variables, leaving `missing` unset or empty."""
    for variable, value in OIDC_VALUES.items():
        if variable == missing and how == 'unset':
            monkeypatch.delenv(variable, raising=False)
        else:
            monkeypatch.setenv(variable, '' if variable == missing else value)


def attempt() -> tuple[BaseException | None, str]:
    try:
        create_auth_oidc()
    except Exception as exc:
        return exc, str(exc)
    return None, ''


@pytest.mark.unit
@pytest.mark.parametrize(('missing', 'how'), [
    pytest.param(variable, how, id=f'{variable}-{how}')
    for variable in OIDC_VARIABLES for how in ('unset', 'empty')
])
def test_oidc_requires_all_four(missing: str, how: str, monkeypatch: pytest.MonkeyPatch,
                                recorder: ProxyRecorder, guard) -> None:
    configure(monkeypatch, missing, how)
    raised, message = attempt()
    violations = oidc_violations(raised, message, recorder.built, guard.refused)
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_oidc_with_all_four_builds_the_proxy(monkeypatch: pytest.MonkeyPatch, recorder: ProxyRecorder,
                                             guard) -> None:
    configure(monkeypatch)
    provider = create_auth_oidc()
    assert provider is recorder, provider
    assert len(recorder.built) == 1, recorder.built
    args, kwargs = recorder.built[0]
    expected = {OIDC_KEYWORDS[variable]: value for variable, value in OIDC_VALUES.items()}
    violations = proxy_violations(PROXY_SIGNATURE, args, kwargs, expected)
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_oidc_proxy_keeps_the_2x_posture(monkeypatch: pytest.MonkeyPatch, recorder: ProxyRecorder,
                                         guard) -> None:
    configure(monkeypatch)
    create_auth_oidc()
    assert len(recorder.built) == 1, recorder.built
    violations = posture_violations(PROXY_SIGNATURE, *recorder.built[0])
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


FOUR = {OIDC_KEYWORDS[variable]: value for variable, value in OIDC_VALUES.items()}
ALL_NAMED = ('OIDC auth requires: OIDC_CONFIG_URL, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET, MCP_BASE_URL')
HELD = {'enable_cimd': False, 'forward_resource': False}


@pytest.mark.unit
@pytest.mark.parametrize(('check', 'clean', 'planted', 'fragment'), [
    pytest.param(oidc_violations, (ValueError(ALL_NAMED), ALL_NAMED, [], []),
                 (ValueError(ALL_NAMED), ALL_NAMED, [((), FOUR)], []),
                 'a provider was built', id='provider-built'),
    pytest.param(oidc_violations, (ValueError(ALL_NAMED), ALL_NAMED, [], []),
                 (None, '', [((), FOUR)], []), 'raised no ValueError', id='accepted'),
    pytest.param(oidc_violations, (ValueError(ALL_NAMED), ALL_NAMED, [], []),
                 (ValueError(ALL_NAMED.removesuffix(', MCP_BASE_URL')), ALL_NAMED.removesuffix(', MCP_BASE_URL'),
                  [], []),
                 'does not name MCP_BASE_URL', id='name-missing'),
    pytest.param(oidc_violations, (ValueError(ALL_NAMED), ALL_NAMED, [], []),
                 (ValueError(ALL_NAMED), ALL_NAMED, [], [('socket.getaddrinfo', ('idp.invalid', 443))]),
                 'reached for the network', id='network'),
    pytest.param(lambda *a: proxy_violations(PROXY_SIGNATURE, *a, FOUR), ((), {**FOUR, **HELD}),
                 ((), {**FOUR, **HELD, 'issuer': 'https://idp.invalid'}),
                 'not a keyword set OIDCProxy accepts', id='unknown-keyword'),
    pytest.param(lambda *a: posture_violations(PROXY_SIGNATURE, *a), ((), {**FOUR, **HELD}),
                 ((), {**FOUR, 'forward_resource': False}), 'enable_cimd=True', id='cimd-enabled'),
    pytest.param(lambda *a: posture_violations(PROXY_SIGNATURE, *a), ((), {**FOUR, **HELD}),
                 ((), {**FOUR, 'enable_cimd': False, 'forward_resource': True}),
                 'forward_resource=True', id='resource-forwarded'),
])
def test_oidc_check_catches_drift(check: Callable[..., list[str]], clean: tuple[Any, ...],
                                  planted: tuple[Any, ...], fragment: str) -> None:
    assert check(*clean) == []
    violations = check(*planted)
    assert any(fragment in v for v in violations), violations


@pytest.mark.unit
def test_none_mode_installs_no_provider(guard) -> None:
    provider = AUTH_MODES['none']()
    assert provider is None, f'none mode installed a provider: {provider!r}'
    executor = RecordingExecutor('open')

    async def scenario() -> tuple[Any, Outcome]:
        server = shared_server(executor)
        installed = installed_auth(server)
        async with serving(server) as app:
            return installed, await call_http(app, None, 'run_command', {'command': 'echo open'})

    installed, outcome = drive(scenario())
    assert installed is None, f'none mode installed a provider: {installed!r}'
    assert outcome.status is None and not outcome.is_error, f'a tokenless call was refused: {outcome}'
    assert 'open|echo open' in outcome.text, outcome
    assert [c[1] for c in executor.calls] == ['echo open'], executor.calls
    assert guard.refused == []


def annotation_violations(hint: Any) -> list[str]:
    """Return every way a resolved `AUTH_MODES` hint differs from a provider-factory map; empty means it matched.

    The hint is `Final[M]`, where `M` is a mapping type from `str` to `Callable[[], R]` (exactly no
    parameters: `Callable[..., R]` accepts any) and `R` is `AuthProvider` or `AuthProvider | None`.
    """
    if typing.get_origin(hint) is not Final:
        return [f'the annotation is not Final: {hint!r}']
    args = typing.get_args(hint)
    if len(args) != 1:
        return [f'Final takes one argument, got {args!r}']
    mapping = args[0]
    if isinstance(mapping, slice):
        return [f'the Final argument is a slice, not a mapping type: {mapping!r}']
    origin = typing.get_origin(mapping)
    if not (isinstance(origin, type) and issubclass(origin, collections.abc.Mapping)):
        return [f'the Final argument is not a mapping type: {mapping!r}']
    violations: list[str] = []
    key, value = (typing.get_args(mapping) + (None, None))[:2]
    if key is not str:
        violations.append(f'the keys are {key!r}, not str')
    if typing.get_origin(value) is not collections.abc.Callable:
        violations.append(f'the values are not a Callable: {value!r}')
        return violations
    params, returns = typing.get_args(value)
    if params != []:
        violations.append(f'the factory takes {params!r}, expected no arguments ([])')
    allowed = ({AuthProvider}, {AuthProvider, type(None)})
    returned = set(typing.get_args(returns)) if typing.get_origin(returns) is typing.Union else {returns}
    if returned not in allowed:
        violations.append(f'the factory returns {returns!r}, expected AuthProvider or AuthProvider | None')
    return violations


@pytest.mark.unit
def test_auth_modes_annotation_is_a_provider_factory_map() -> None:
    hint = typing.get_type_hints(cluster_mcp.core.auth)['AUTH_MODES']
    violations = annotation_violations(hint)
    assert violations == [], '\n'.join(violations)
    assert set(AUTH_MODES) == {'none', 'jwt', 'oidc'}, AUTH_MODES


FACTORY = Callable[[], AuthProvider | None]


@pytest.mark.unit
@pytest.mark.parametrize(('hint', 'fragment'), [
    pytest.param(Final[slice(Dict[str, Callable[[], AuthProvider]], None, None)], 'slice', id='slice'),
    pytest.param(Dict[str, FACTORY], 'not Final', id='not-final'),
    pytest.param(Final[Dict[int, FACTORY]], 'the keys are', id='wrong-key'),
    pytest.param(Final[Dict[str, Callable[[str], AuthProvider]]], 'expected no arguments', id='takes-an-argument'),
    pytest.param(Final[Dict[str, Callable[..., AuthProvider]]], 'expected no arguments', id='any-arguments'),
    pytest.param(Final[list[FACTORY]], 'not a mapping type', id='not-a-mapping'),
])
def test_annotation_check_catches_drift(hint: Any, fragment: str) -> None:
    assert annotation_violations(Final[Dict[str, FACTORY]]) == []
    assert annotation_violations(Final[Dict[str, Callable[[], AuthProvider]]]) == []
    violations = annotation_violations(hint)
    assert any(fragment in v for v in violations), violations
