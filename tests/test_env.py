# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Each environment variable the server reads has a `CLUSTER_MCP_*` name and honours its legacy name.

`env_setting(name)` returns the value and the variable it came from: the replacement when it is
non-empty, else the legacy `RCAC_*` value when that is non-empty, else None. A legacy value is
honoured with one deprecation warning on stderr naming the replacement and the window; a legacy
value set beside its replacement is ignored, with one warning saying so. Each warning states the
window exactly as `harness.DEPRECATION_WINDOW` writes it out, compared with that literal, never with
the module's own constant. Each legacy name warns at most once per process, and never on stdout,
which carries the stdio transport. An empty value counts as unset, and nothing is stripped: a
whitespace-only host is truthy, and the execution-mode ladder must keep selecting `ssh` for it.

The pairs below are written out, not read from `LEGACY_ENV`, so a dropped or renamed pair fails
here. A variable that came after the rename has no legacy name (None in `LEGACY_ENV`): it is read
alone, an empty value counting as unset, with no warning. The warnings are read from `caplog` (the records the deprecation logger emits) and stdout from
`capsys`; a fixture resets the warn-once set before every test.
"""

from __future__ import annotations

import logging
import re

import pytest

from harness import DEPRECATION_WINDOW
from cluster_mcp.core import deprecation
from cluster_mcp.core.deprecation import LEGACY_ENV, env_setting

# Each replacement, its legacy name, and a value the server would accept for it.
PAIRS = (
    ('CLUSTER_MCP_SSH_HOST', 'RCAC_SSH_HOST', 'env-host.invalid'),
    ('CLUSTER_MCP_USER_MAP', 'RCAC_USER_MAP', '/nonexistent/user-map'),
    ('CLUSTER_MCP_INSTRUCTIONS_BUDGET', 'RCAC_INSTRUCTIONS_BUDGET', '7000'),
)
EACH = [pytest.param(new, old, value, id=new) for new, old, value in PAIRS]

LOGGER = 'cluster_mcp.core.deprecation'


@pytest.fixture(autouse=True)
def fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    """No variable of either name set, and no legacy name warned about yet in this process."""
    monkeypatch.setattr(deprecation, '_warned', set())
    for new, old, _ in PAIRS:
        monkeypatch.delenv(new, raising=False)
        monkeypatch.delenv(old, raising=False)


def warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The deprecation warnings logged so far."""
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING]


def one_warning(caplog: pytest.LogCaptureFixture, old: str) -> str:
    """The one deprecation warning naming `old`; fails unless there is exactly one."""
    found = [w for w in warnings(caplog) if old in w]
    assert len(found) == 1, f'{old}: {len(found)} deprecation warnings on stderr, expected one: {warnings(caplog)!r}'
    return found[0]


# The variables that came after the rename, so have no legacy name.
NO_LEGACY = ('CLUSTER_MCP_SKIP_PROBES',)


@pytest.mark.unit
def test_every_variable_has_its_legacy_name() -> None:
    assert {new: old for new, old in LEGACY_ENV.items() if old is not None} == {new: old for new, old, _ in PAIRS}
    assert sorted(new for new, old in LEGACY_ENV.items() if old is None) == sorted(NO_LEGACY)


@pytest.mark.unit
@pytest.mark.parametrize('name', NO_LEGACY)
@pytest.mark.parametrize(('value', 'expected'), [
    pytest.param('1', '1', id='set'),
    pytest.param('0', '0', id='zero'),
    pytest.param(' ', ' ', id='space'),
    pytest.param('', None, id='empty'),
    pytest.param(None, None, id='unset'),
])
def test_a_variable_without_a_legacy_name(name: str, value: str | None, expected: str | None,
                                          monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    # Read alone, as given, an empty value counting as unset, with no legacy branch and no warning.
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        got = env_setting(name)
    assert got == (expected, name), f'{name}={value!r}: resolved {got!r}, expected {(expected, name)!r}'
    assert [r.getMessage() for r in caplog.records if r.name == LOGGER] == []
    assert capsys.readouterr().out == ''


@pytest.mark.unit
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
def test_replacement_is_read(new: str, old: str, value: str, monkeypatch: pytest.MonkeyPatch,
                             caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(new, value)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        got = env_setting(new)
    assert got == (value, new), f'{new} alone: resolved {got!r}, expected {(value, new)!r}'
    assert warnings(caplog) == [], f'the replacement drew a warning: {warnings(caplog)!r}'


@pytest.mark.unit
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
def test_legacy_is_honoured_with_a_warning(new: str, old: str, value: str, monkeypatch: pytest.MonkeyPatch,
                                           caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(old, value)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        got = env_setting(new)
    assert got == (value, old), f'{old} alone: resolved {got!r}, expected {(value, old)!r}'
    one_warning(caplog, old)


@pytest.mark.unit
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
def test_replacement_wins_over_legacy(new: str, old: str, value: str, monkeypatch: pytest.MonkeyPatch,
                                      caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setenv(new, value)
    monkeypatch.setenv(old, f'{value}-legacy')
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        got = env_setting(new)
    assert got == (value, new), f'{new} and {old} both set: resolved {got!r}, expected {(value, new)!r}'
    assert 'ignored' in one_warning(caplog, old)


@pytest.mark.unit
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
@pytest.mark.parametrize(('new_value', 'old_value', 'expected'), [
    pytest.param('', None, 'none', id='replacement-empty'),
    pytest.param(None, '', 'none', id='legacy-empty'),
    pytest.param('', '', 'none', id='both-empty'),
    pytest.param('', 'set', 'legacy', id='empty-replacement-yields'),
])
def test_empty_counts_as_unset(new: str, old: str, value: str, new_value: str | None, old_value: str | None,
                               expected: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    if new_value is not None:
        monkeypatch.setenv(new, new_value)
    if old_value is not None:
        monkeypatch.setenv(old, value if old_value == 'set' else old_value)
    want = (None, new) if expected == 'none' else (value, old)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        got = env_setting(new)
    assert got == want, f'{new}={new_value!r} {old}={old_value!r}: resolved {got!r}, expected {want!r}'
    assert len(warnings(caplog)) == (expected == 'legacy'), warnings(caplog)


@pytest.mark.unit
@pytest.mark.parametrize('which', ['replacement', 'legacy'])
@pytest.mark.parametrize('raw', [pytest.param(' ', id='space'), pytest.param(' \t ', id='blanks')])
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
def test_whitespace_host_is_not_stripped(new: str, old: str, value: str, raw: str, which: str,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    variable = new if which == 'replacement' else old
    monkeypatch.setenv(variable, raw)
    got = env_setting(new)
    assert got == (raw, variable), f'{variable}={raw!r} resolved {got!r}, expected {(raw, variable)!r}, unstripped'


@pytest.mark.unit
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
def test_warning_fires_once_per_name(new: str, old: str, value: str, monkeypatch: pytest.MonkeyPatch,
                                     caplog: pytest.LogCaptureFixture) -> None:
    for other_new, other_old, other_value in PAIRS:
        monkeypatch.setenv(other_old, other_value)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for _ in range(3):
            assert env_setting(new) == (value, old)
        one_warning(caplog, old)
        # Now set beside its replacement, it is ignored, and still not warned about a second time.
        monkeypatch.setenv(new, value)
        assert env_setting(new) == (value, new)
        one_warning(caplog, old)
        # Every other legacy name still warns, once, on its own first read.
        for other_new, other_old, _ in PAIRS:
            env_setting(other_new)
            env_setting(other_new)
    for _, other_old, _ in PAIRS:
        one_warning(caplog, other_old)
    assert len(warnings(caplog)) == len(PAIRS), warnings(caplog)


@pytest.mark.unit
@pytest.mark.parametrize('shape', ['honoured', 'ignored'])
@pytest.mark.parametrize(('new', 'old', 'value'), EACH)
def test_warning_names_replacement_and_window(new: str, old: str, value: str, shape: str,
                                              monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv(old, value)
    if shape == 'ignored':
        monkeypatch.setenv(new, value)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        env_setting(new)
    out = capsys.readouterr().out
    assert out == '', f'the deprecation warning went to stdout, which carries the stdio transport: {out!r}'
    warning = one_warning(caplog, old)
    old_re, new_re = re.escape(old), re.escape(new)
    pattern = {'honoured': rf'{old_re} is (.*): use {new_re} instead',
               'ignored': rf'{old_re} is (.*), and ignored: {new_re} is set'}[shape]
    match = re.fullmatch(pattern, warning)
    assert match, f'the warning is not the {shape} deprecation warning naming {old} and {new}: {warning!r}'
    assert match[1] == DEPRECATION_WINDOW, \
        f'the warning states the window {match[1]!r}, not the published window {DEPRECATION_WINDOW!r}'
