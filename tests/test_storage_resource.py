# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Reading `rcac://storage` runs on the executor of the request that read it, as `storage_paths` does.

The resource's handler and the `storage_paths` tool both call the undecorated
`resolve_storage_paths()`: a decorated tool is not callable (§ Invariants §7). It runs
`findscratch`, then `myquota`, through `get_executor()`, so a read needs its request's executor,
which the executor middleware sets for a resource read exactly as for a tool call, in that
request's own context (§1). A read on a server whose `SharedExecutorMiddleware` installs an
executor returns the summary in its text format, built from that executor's answers and naming the
same home, scratch and depot paths the tool returns there, in both protocol eras; through a
`LocalShellExecutor` it launches as the server's own account, never through `sudo`. A read on a
server with no executor middleware fails naming `No executor configured`, and nothing runs.

In `delegate` mode a read is resolved by the same path as a tool call (§5): a token whose identity
is in the user map reads as the local user it maps to, through `sudo -n -H -u`, and two reads under
different identities held in flight together each run only as their own user and get back only
their own paths, as do alternating reads on one server. A read whose request a `storage_paths` call
would be refused for (no token, a token naming no identity, an identity the map does not hold, the
first claim unmapped) fails with exactly the reason that call gets, as an internal error (-32603)
with no type name and no traceback, and nothing runs; a tokenless read finds no executor right
after, and while, another identity's read did set one.

The delegate read hook refuses by default: it resolves the identity of every read of a URI not
exactly in `OPEN_RESOURCES`, before FastMCP looks the URI up, so a refused caller reading a URI the
server does not serve gets the refusal its tool call gets, while a mapped caller and a tokenless one
still get the protocol's `Resource not found` (-32602) for it, as every caller does in shared mode.
Membership is the exact string the client sent, so this holds for every shape in `NOT_OPEN`: a path
below an open URI, a prefix of one or a URI it prefixes, a trailing slash, a case, percent-encoded or
full-width variant, surrounding space, a query or fragment, a missing scheme or authority, a variant
of the URI that runs commands, another scheme. Each is sent on the wire as written. The table names
shapes; `NEAR_OPEN` covers the neighbourhood of every served URI structurally: every one-character
insertion, deletion and substitution over printable ASCII and the control characters, at every
position, every wrapper, suffix and userinfo a URI normaliser undoes, so a membership test that
normalises the URI in any of those ways lets some refused caller's read through and is caught.
"""

from __future__ import annotations

import asyncio
import json
import string
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from conftest import LOCAL_OWNER, launch_user
from harness import (Outcome, RecordingExecutor, Rendezvous, bare_server, call, delegate_server, drive,
                     http_client, in_memory, launched_script, mint, read_resource, read_verbatim, serving,
                     shared_server, user_map)
from rcac_mcp.executor.shell import LocalShellExecutor
from rcac_mcp.resources import OPEN_RESOURCES, RESOURCE_REGISTRY
from test_identity import NO_IDENTITY, NOT_AUTHORIZED
from test_no_executor import NO_EXECUTOR, refusal_violations, report
from test_protocol import read_boundary_violations
from test_tools import quota_and_scratch

URI = 'rcac://storage'
ERAS = ['legacy', 'modern']

# The commands a storage read runs, in order: the scratch path, then the quota table.
STORAGE_ARGVS = [['findscratch'], ['myquota']]

SECRET = 'storage-resource-test-secret-0123456789abcdef'
USER_MAP = 'alice ualice\nal@example.org uemail\nbob ubob\n'

# The prefix FastMCP puts before the reason when a tool's body fails, and when a resource handler does.
TOOL_PREFIX = "Error calling tool 'storage_paths': "
READ_PREFIX = f'Error reading resource {URI!r}: '

# The open URI and the URI that runs commands the shapes below are built from.
OPEN_URI = 'rcac://context'

# Every shape of URI the server does not serve, each sent on the wire exactly as written
# (`harness.read_verbatim`), with what it is. None is exactly a URI in OPEN_RESOURCES, so in
# `delegate` mode each is resolved like a read that runs commands. FastMCP's own client would send
# some of them normalised (`RCAC://context` as the open `rcac://context`), hence verbatim.
NOT_OPEN = {
    'rcac://nope': 'an rcac URI the server does not serve',
    'rcac://context/x': 'a path below the open URI',
    'rcac://context/': 'the open URI with a trailing slash',
    'rcac://contextual': 'a URI the open URI is a prefix of',
    'rcac://contex': 'a prefix of the open URI',
    'xrcac://context': 'a URI ending in the open URI',
    'rcac://CONTEXT': 'the open URI, its host upper-cased',
    'RCAC://context': 'the open URI, its scheme upper-cased',
    'rcac://%63ontext': 'the open URI, a letter percent-encoded',
    'rcac://\uff43ontext': 'the open URI, a letter full-width',
    ' rcac://context': 'the open URI after a space',
    'rcac://context ': 'the open URI before a space',
    'rcac://context?x=1': 'the open URI with a query',
    'rcac://context#f': 'the open URI with a fragment',
    'rcac:context': 'the open URI without its authority slashes',
    'context': 'the open URI without its scheme',
    'rcac://storage/': 'the URI that runs commands, with a trailing slash',
    'RCAC://storage': 'the URI that runs commands, its scheme upper-cased',
    'rcac://STORAGE': 'the URI that runs commands, its host upper-cased',
    'file:///nope': 'a file URI',
    'https://example.org/x': 'an https URL',
}

# The characters a one-character edit draws on: printable ASCII, then the control characters a URI
# parser drops or a normaliser trims (NUL, tab, newline, vertical tab, form feed, carriage return, DEL).
EDIT_CHARACTERS = ''.join(map(chr, range(0x20, 0x7f))) + '\x00\t\n\x0b\x0c\r\x7f'

# What a URI normaliser unwraps, removes from the end, or removes from the authority.
WRAPPERS = (('<', '>'), ('"', '"'), ("'", "'"), ('`', '`'), ('(', ')'), ('[', ']'), ('{', '}'),
            (' ', ' '), ('\t', '\t'), ('\n', '\n'), ('\r\n', '\r\n'), ('\x00', '\x00'))
SUFFIXES = ('?', '#', '?#', ':', ':80', '.', '/.', '/./', '/', '//', '\r\n')
USERINFO = ('@', 'u@', 'u:p@')


def near(uri: str) -> dict[str, str]:
    """Every shape one edit, a wrapper, a suffix or userinfo away from `uri`, each with how it was made."""
    shapes: dict[str, str] = {}
    for at in range(len(uri) + 1):
        for char in EDIT_CHARACTERS:
            shapes.setdefault(uri[:at] + char + uri[at:], f'{uri!r} with {char!r} inserted at {at}')
    for at, old in enumerate(uri):
        shapes.setdefault(uri[:at] + uri[at + 1:], f'{uri!r} with {old!r} at {at} deleted')
        for char in EDIT_CHARACTERS:
            if char != old:
                shapes.setdefault(uri[:at] + char + uri[at + 1:], f'{uri!r} with {old!r} at {at} replaced by {char!r}')
    for before, after in WRAPPERS:
        shapes.setdefault(before + uri + after, f'{uri!r} wrapped in {before!r} and {after!r}')
    for suffix in SUFFIXES:
        shapes.setdefault(uri + suffix, f'{uri!r} followed by {suffix!r}')
    scheme, separator, rest = uri.partition('://')
    for info in USERINFO if separator else ():
        shapes.setdefault(f'{scheme}://{info}{rest}', f'{uri!r} with userinfo {info!r}')
    return shapes


def neighbourhood(uris: Sequence[str], open_uris: frozenset[str]) -> dict[str, str]:
    """The shapes near any of `uris`, each with how it was first made, leaving out exactly `open_uris`."""
    shapes: dict[str, str] = {}
    for uri in uris:
        for shape, how in near(uri).items():
            if shape not in open_uris:
                shapes.setdefault(shape, how)
    return shapes


# The neighbourhood of every served URI, the open ones and those that run commands: about 2,900
# shapes each. It leaves out the URIs the registry marks as running nothing, not whatever
# OPEN_RESOURCES holds, so an open set grown past the registry's open entries is read here too. None
# is exactly open, so in `delegate` mode a refused caller is refused for each.
NEAR_OPEN = neighbourhood([entry['uri'] for entry in RESOURCE_REGISTRY],
                          frozenset(entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor']))

# Shapes a common URI normaliser maps onto the open URI; the neighbourhood must hold each of them.
NORMALISED = ('rcac://context?', 'rcac://context#', 'rcac://context:', 'rcac://context:80', 'rcac://u@context',
              'rcac://context.', 'rcac://context\n', 'rcac://con\ttext', 'rcac://context\x00', '/rcac://context',
              '<rcac://context>', '"rcac://context"', 'rcac://context/.', 'rcac://context\r\n', ' rcac://context')

# Reads held in flight together when a test reads the whole neighbourhood on one session.
READ_BATCH = 128

# The paths `test_tools.quota_and_scratch` answers with.
SHARED_PATHS = ('/home/alice', '/scratch/test/installed-executor-scratch', '/depot/lab')


def summary(home: str, scratch: str, depot: str) -> str:
    """The resource's text for one home, one scratch and one depot, with the quota tables' usage."""
    return ('User Storage Paths:\n'
            '\n'
            f'Home: {home}\n'
            '  Usage: 14.6GB / 25.0GB (58.6%)\n'
            '\n'
            f'Scratch: {scratch}\n'
            '  Usage: 1.2TB / 200TB (0.6%)\n'
            '\n'
            'Depot Spaces (1 available):\n'
            f'  - {depot}\n'
            '    Usage: 3.0TB / 10TB (30.0%)')


def owner_paths(owner: str) -> tuple[str, str, str]:
    """The home, scratch and depot `conftest.storage_answer` names for `owner`."""
    return f'/home/{owner}', f'/scratch/test/{owner}', f'/depot/lab-{owner}'


def read_violations(outcome: Outcome, expected: str, ran: Sequence[tuple[str, Any]], owner: str) -> list[str]:
    """Return every way a storage read went wrong; empty means it returned `expected`, running as `owner`.

    `ran` holds the (who, command) pairs seen where the read's commands left the process; the read
    must have run `findscratch`, then `myquota`, each once and each as `owner`, and nothing else.
    """
    violations: list[str] = []
    if outcome.is_error:
        violations.append(f'the read failed: {outcome.text!r}')
    elif outcome.text != expected:
        violations.append(f'the read returned {outcome.text!r}, expected {expected!r}')
    wanted = [(owner, argv) for argv in STORAGE_ARGVS]
    if list(ran) != wanted:
        violations.append(f'the read ran {list(ran)!r}, expected {wanted!r}')
    return violations


def tool_path_violations(text: str, tool: Outcome) -> list[str]:
    """Return every path the read's text and the `storage_paths` tool's result do not share."""
    if tool.is_error:
        return [f'the tool failed: {tool.text!r}']
    result = json.loads(tool.text)
    paths = [result['home']['path'], result['scratch']['path'], *(d['path'] for d in result['depots'])]
    if not result['depots']:
        return [f'the tool returned no depot: {tool.text!r}']
    lines = text.splitlines()
    shown = [line.split(': ', 1)[1] for line in lines if line.startswith(('Home: ', 'Scratch: '))]
    shown += [line.removeprefix('  - ') for line in lines if line.startswith('  - ')]
    return [] if shown == paths else [f'the read names {shown!r}, the tool {paths!r}']


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_storage_read_runs_on_the_shared_executor(era: str, launches: list[list[str]], guard) -> None:
    executor = RecordingExecutor('shared', responder=quota_and_scratch)

    async def scenario() -> tuple[Outcome, list[tuple[Any, ...]], Outcome]:
        async with in_memory(shared_server(executor), era=era) as client:
            read = await read_resource(client, URI)
            ran = list(executor.calls)
            return read, ran, await call(client, 'storage_paths', {})

    read, calls, tool = drive(scenario())
    ran = [('shared', c[1]) for c in calls]
    violations = read_violations(read, summary(*SHARED_PATHS), ran, 'shared')
    if not violations:
        violations += tool_path_violations(read.text, tool)
    violations += [f'process launched: {argv!r}' for argv in launches]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_storage_read_runs_the_local_executor(era: str, storage_launches: list[list[str]], guard) -> None:
    async def scenario() -> Outcome:
        async with in_memory(shared_server(LocalShellExecutor()), era=era) as client:
            return await read_resource(client, URI)

    read = drive(scenario())
    ran = [(launch_user(argv) or LOCAL_OWNER, launched_script(argv)[0]) for argv in storage_launches]
    violations = read_violations(read, summary(*owner_paths(LOCAL_OWNER)), ran, LOCAL_OWNER)
    violations += [f'launched through sudo: {argv!r}' for argv in storage_launches if argv[:1] == ['sudo']]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_storage_read_without_executor_middleware_fails(era: str, launches: list[list[str]], guard) -> None:
    async def scenario() -> Outcome:
        async with in_memory(bare_server(), era=era) as client:
            return await read_resource(client, URI)

    violations = refusal_violations(drive(scenario()), [], launches, NO_EXECUTOR)
    assert violations == [], report(violations)
    assert guard.refused == []


def ran_by(launches: Sequence[Sequence[str]]) -> list[tuple[str, Any]]:
    """The (user, command) of each recorded launch: the user after `-u`, or `LOCAL_OWNER` for none."""
    return [(launch_user(list(argv)) or LOCAL_OWNER, launched_script(argv)[0]) for argv in launches]


def storage_isolation_violations(reads: Mapping[str, Outcome], ran: Sequence[tuple[str, Any]]) -> list[str]:
    """Return every way concurrent reads crossed; empty means each ran, and answered, only as its own user.

    `reads` maps each local user to the read its own client got, and `ran` holds the (user, command)
    pairs seen where the reads' commands left the process: each user must have run `findscratch` and
    `myquota` once each, and each read must name its own user's paths and no other user's.
    """
    violations: list[str] = []
    for user, outcome in reads.items():
        for argv in STORAGE_ARGVS:
            count = sum(1 for who, command in ran if who == user and command == argv)
            if count != 1:
                violations.append(f'{argv[0]} ran as {user} {count} times, expected once')
        if outcome.is_error:
            violations.append(f"{user}'s read failed: {outcome.text!r}")
        elif outcome.text != summary(*owner_paths(user)):
            violations.append(f"{user}'s read returned {outcome.text!r}, expected its own summary")
        for other in reads:
            if other != user and any(path in outcome.text for path in owner_paths(other)):
                violations.append(f"{user}'s read ran as {other}: it names {other}'s paths: {outcome.text!r}")
    for who, command in ran:
        if who not in reads or command not in STORAGE_ARGVS:
            violations.append(f'unexpected run of {command!r} as {who}')
    return violations


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_storage_read_runs_as_the_mapped_user(era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                              storage_launches: list[list[str]], guard) -> None:
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> Outcome:
        async with serving(delegate_server(map_path)) as app:
            async with http_client(app, mint(SECRET, sub='alice'), era=era) as client:
                return await read_resource(client, URI)

    read = drive(scenario())
    violations = read_violations(read, summary(*owner_paths('ualice')), ran_by(storage_launches), 'ualice')
    violations += [f'not launched through sudo -n -H -u: {argv!r}' for argv in storage_launches
                   if argv[:4] != ['sudo', '-n', '-H', '-u']]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_concurrent_storage_reads_stay_isolated(era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                storage_launches: list[list[str]], guard) -> None:
    # Both reads are held at one rendezvous inside the executor middleware, so each has set its
    # executor before either handler runs; a module global or a cached executor crosses them.
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> tuple[Outcome, Outcome]:
        async with serving(delegate_server(map_path, Rendezvous(2))) as app:
            async with (http_client(app, mint(SECRET, sub='alice'), era=era) as alice,
                        http_client(app, mint(SECRET, sub='bob'), era=era) as bob):
                return await asyncio.gather(read_resource(alice, URI), read_resource(bob, URI))

    for_alice, for_bob = drive(scenario())
    violations = storage_isolation_violations({'ualice': for_alice, 'ubob': for_bob}, ran_by(storage_launches))
    violations += [f'not launched through sudo -n -H -u: {argv!r}' for argv in storage_launches
                   if argv[:4] != ['sudo', '-n', '-H', '-u']]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_sequential_storage_reads_each_get_their_executor(era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                          storage_launches: list[list[str]], guard) -> None:
    # Alternating identities on one server, one read at a time: every read builds and sets the
    # executor for its own token, so none runs with no executor or with the previous reader's.
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)
    sequence = ['alice', 'bob', 'alice']

    async def scenario() -> tuple[list[Outcome], list[int]]:
        reads: list[Outcome] = []
        marks: list[int] = []
        async with serving(delegate_server(map_path)) as app:
            async with (http_client(app, mint(SECRET, sub='alice'), era=era) as alice,
                        http_client(app, mint(SECRET, sub='bob'), era=era) as bob):
                clients = {'alice': alice, 'bob': bob}
                for who in sequence:
                    reads.append(await read_resource(clients[who], URI))
                    marks.append(len(storage_launches))
        return reads, marks

    reads, marks = drive(scenario())
    ran = ran_by(storage_launches)
    violations: list[str] = []
    for at, (who, read, start, end) in enumerate(zip(sequence, reads, [0, *marks], marks)):
        user = f'u{who}'
        if end - start != len(STORAGE_ARGVS):
            violations.append(f'read {at + 1} as {user} ran {end - start} times, expected {len(STORAGE_ARGVS)}')
        violations += [f'read {at + 1}: {v}' for v in
                       read_violations(read, summary(*owner_paths(user)), ran[start:end], user)]
    if len(ran) != 2 * len(sequence):
        violations.append(f'{len(ran)} launches, expected {2 * len(sequence)}: {ran!r}')
    assert violations == [], report(violations)
    assert guard.refused == []


def _read(user: str) -> Outcome:
    return Outcome(False, summary(*owner_paths(user)))


GOOD_RAN = [('ualice', ['findscratch']), ('ualice', ['myquota']), ('ubob', ['findscratch']), ('ubob', ['myquota'])]


@pytest.mark.unit
@pytest.mark.parametrize(('reads', 'ran', 'fragment'), [
    pytest.param({'ualice': _read('ubob'), 'ubob': _read('ubob')}, [('ubob', a) for _, a in GOOD_RAN],
                 'findscratch ran as ualice 0 times', id='crossed-user'),
    pytest.param({'ualice': _read('ualice'), 'ubob': _read('ubob')}, GOOD_RAN[:3],
                 'myquota ran as ubob 0 times', id='missing-launch'),
    pytest.param({'ualice': Outcome(False, _read('ualice').text + '\n  - /depot/lab-ubob'), 'ubob': _read('ubob')},
                 GOOD_RAN, "ualice's read ran as ubob", id='foreign-path'),
    pytest.param({'ualice': _read('ualice'), 'ubob': _read('ubob')}, GOOD_RAN + [('ualice', ['myquota'])],
                 'myquota ran as ualice 2 times', id='duplicate-launch'),
    pytest.param({'ualice': _read('ualice'), 'ubob': _read('ubob')}, GOOD_RAN + [('ughost', ['findscratch'])],
                 "unexpected run of ['findscratch'] as ughost", id='unexpected-launch'),
])
def test_storage_check_catches_crossing(reads: dict[str, Outcome], ran: list[tuple[str, Any]], fragment: str) -> None:
    assert storage_isolation_violations({'ualice': _read('ualice'), 'ubob': _read('ubob')}, GOOD_RAN) == []
    violations = storage_isolation_violations(reads, ran)
    assert any(fragment in v for v in violations), violations


# The exact reasons a request is refused with: what the client reads, with no type name and no traceback.
NO_EXECUTOR_REASON = 'No executor configured. Set executor via set_executor() first.'
NO_IDENTITY_REASON = ('Could not extract user identity from token claims. '
                      'Token must contain sub, email, or preferred_username claim.')
GHOST_REASON = "User 'ghost' is not authorized. Contact administrator to request access."

# Each refused request: the claims its token carries (None: no token at all, over the in-memory
# client), the fragment of the reason it is refused with, and that reason in full.
REFUSED = {
    'no-token': (None, NO_EXECUTOR, NO_EXECUTOR_REASON),
    'no-claims': ({}, NO_IDENTITY, NO_IDENTITY_REASON),
    'all-empty': ({'sub': '', 'email': '', 'preferred_username': ''}, NO_IDENTITY, NO_IDENTITY_REASON),
    'unmapped': ({'sub': 'ghost'}, NOT_AUTHORIZED, GHOST_REASON),
    'first-claim-unmapped': ({'sub': 'ghost', 'email': 'al@example.org'}, NOT_AUTHORIZED, GHOST_REASON),
}


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
@pytest.mark.parametrize('row', list(REFUSED))
def test_storage_read_refused(row: str, era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                              storage_launches: list[list[str]], guard) -> None:
    # The same request is built twice: one calls `storage_paths`, the other reads the resource. Each
    # must be refused with exactly the row's reason, whatever prefix FastMCP puts before it.
    claims, fragment, reason = REFUSED[row]
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> tuple[Outcome, Outcome]:
        server = delegate_server(map_path)
        if claims is None:
            async with in_memory(server, era=era) as caller, in_memory(server, era=era) as reader:
                return await call(caller, 'storage_paths', {}), await read_resource(reader, URI)
        token = mint(SECRET, **claims)
        async with serving(server) as app:
            async with http_client(app, token, era=era) as caller, http_client(app, token, era=era) as reader:
                return await call(caller, 'storage_paths', {}), await read_resource(reader, URI)

    tool, read = drive(scenario())
    violations = refusal_violations(read, [], storage_launches, fragment)
    # A tokenless request is let through and fails in the handler, which FastMCP prefixes; every
    # other row is refused by the middleware, with its reason alone.
    violations += read_boundary_violations(read, READ_PREFIX + reason if claims is None else reason)
    violations += tool_refusal_violations(tool, TOOL_PREFIX + reason if claims is None else reason)
    assert violations == [], report(violations)
    assert guard.refused == []


def tool_refusal_violations(tool: Outcome, expected: str) -> list[str]:
    """Return how the `storage_paths` call was not refused with exactly `expected`; empty means it was."""
    if tool.is_error and tool.text == expected:
        return []
    return [f'the tool call was not refused with {expected!r}: {tool.text!r} (error={tool.is_error})']


@pytest.mark.unit
def test_not_open_shapes_are_neither_open_nor_served() -> None:
    # The shapes are variants of a served open URI and a served URI that runs commands; none of them
    # may itself be served or open, or the tests below would test nothing about it.
    served = {entry['uri'] for entry in RESOURCE_REGISTRY}
    violations = [f'{uri!r} is served or open' for uri in NOT_OPEN if uri in served | OPEN_RESOURCES]
    if OPEN_URI not in OPEN_RESOURCES or URI not in served - OPEN_RESOURCES:
        violations.append(f'{OPEN_URI!r} must be open and {URI!r} served and not open: {sorted(OPEN_RESOURCES)!r}')
    assert violations == [], report(violations)


def shape_violations(uri: str, violations: Sequence[str], shapes: Mapping[str, str] = NOT_OPEN) -> list[str]:
    """`violations` of reading `uri`, each naming the URI and its shape as `shapes` describes it."""
    return [f'reading {uri!r} ({shapes[uri]}): {v}' for v in violations]


async def read_each(client: Any, uris: Sequence[str]) -> dict[str, Outcome]:
    """Read every URI in `uris` verbatim on `client`, `READ_BATCH` reads in flight at a time."""
    reads: dict[str, Outcome] = {}
    for start in range(0, len(uris), READ_BATCH):
        batch = uris[start:start + READ_BATCH]
        reads.update(zip(batch, await asyncio.gather(*(read_verbatim(client, uri) for uri in batch))))
    return reads


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
@pytest.mark.parametrize('row', [row for row, (claims, _, _) in REFUSED.items() if claims is not None])
def test_unknown_uri_read_is_refused(row: str, era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                     storage_launches: list[list[str]], guard) -> None:
    # The delegate read hook resolves the identity of every read of a URI not exactly in OPEN_RESOURCES
    # before FastMCP looks the URI up, so a refused caller reading any shape of URI the server does not
    # serve is refused with its tool call's reason, not told the URI is not found.
    claims, fragment, reason = REFUSED[row]
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> tuple[Outcome, dict[str, Outcome]]:
        token = mint(SECRET, **claims)
        async with serving(delegate_server(map_path)) as app:
            async with http_client(app, token, era=era) as caller, http_client(app, token, era=era) as reader:
                tool = await call(caller, 'storage_paths', {})
                return tool, {uri: await read_verbatim(reader, uri) for uri in NOT_OPEN}

    tool, reads = drive(scenario())
    violations = tool_refusal_violations(tool, reason)
    for uri, read in reads.items():
        violations += shape_violations(uri, refusal_violations(read, [], [], fragment)
                                       + read_boundary_violations(read, reason))
    violations += [f'process launched: {argv!r}' for argv in storage_launches]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_near_open_shapes_cover_every_served_uri() -> None:
    # The neighbourhood is generated, so pin what it must hold: no open URI, every served URI's
    # deletions and its control-character and printable insertions at both ends, and the shapes common
    # normalisers map onto the open URI.
    violations = [f'{uri!r} is open' for uri in NEAR_OPEN if uri in OPEN_RESOURCES]
    served = [entry['uri'] for entry in RESOURCE_REGISTRY]
    for uri in served:
        wanted = [uri[:at] + uri[at + 1:] for at in range(len(uri))]
        wanted += [f'{char}{uri}' for char in '\x00\t\n\r\x7f' + string.punctuation + string.whitespace]
        wanted += [f'{uri}{char}' for char in '\x00\t\n\r\x7f' + string.punctuation + string.whitespace]
        violations += [f'the neighbourhood of {uri!r} lacks {shape!r}' for shape in wanted if shape not in NEAR_OPEN]
    violations += [f'the neighbourhood lacks {shape!r}' for shape in NORMALISED if shape not in NEAR_OPEN]
    if len(NEAR_OPEN) < 2500 * len(served):
        violations.append(f'the neighbourhood holds {len(NEAR_OPEN)} shapes, expected at least {2500 * len(served)}')
    if OPEN_URI not in OPEN_RESOURCES or OPEN_URI not in served:
        violations.append(f'{OPEN_URI!r} must be served and open: {sorted(OPEN_RESOURCES)!r}')
    assert violations == [], report(violations)


@pytest.mark.unit
@pytest.mark.parametrize('row', ['no-claims', 'unmapped'])
def test_near_open_read_is_refused(row: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   storage_launches: list[list[str]], guard) -> None:
    # Every shape near a served URI and not exactly open, read on one session: a membership test that
    # normalises the URI (drops a port, a query mark, userinfo, a dot segment, surrounding quotes or
    # control characters) maps some shape onto the open URI and lets this refused caller through.
    # About 5,700 reads, so the client speaks the selected era, not each era on every run: the
    # profile's gate runs the suite once per era.
    claims, fragment, reason = REFUSED[row]
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> dict[str, Outcome]:
        async with serving(delegate_server(map_path)) as app:
            async with http_client(app, mint(SECRET, **claims)) as reader:
                return await read_each(reader, list(NEAR_OPEN))

    reads = drive(scenario(), timeout=120)
    violations: list[str] = []
    if len(reads) != len(NEAR_OPEN) or not reads:
        violations.append(f'{len(reads)} reads, expected {len(NEAR_OPEN)}')
    for uri, read in reads.items():
        violations += shape_violations(uri, refusal_violations(read, [], [], fragment)
                                       + read_boundary_violations(read, reason), NEAR_OPEN)
    violations += [f'process launched: {argv!r}' for argv in storage_launches]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_storage_read_without_token_after_an_authenticated_read_fails(
        era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, storage_launches: list[list[str]],
        guard) -> None:
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> tuple[Outcome, Outcome]:
        server = delegate_server(map_path)
        async with serving(server) as app:
            async with http_client(app, mint(SECRET, sub='alice'), era=era) as alice:
                first = await read_resource(alice, URI)
            async with in_memory(server, era=era) as client:
                return first, await read_resource(client, URI)

    first, anon = drive(scenario())
    ran = ran_by(storage_launches)
    violations = refusal_violations(anon, [], storage_launches[2:], NO_EXECUTOR)
    violations += [f'the authenticated read: {v}' for v in
                   read_violations(first, summary(*owner_paths('ualice')), ran[:2], 'ualice')]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_storage_read_without_token_while_an_authenticated_read_is_in_flight(
        era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, storage_launches: list[list[str]],
        guard) -> None:
    # The authenticated read is held at the rendezvous, its executor set, before the tokenless read
    # is sent; both then run together.
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> tuple[Outcome, Outcome]:
        rendezvous = Rendezvous(2)
        server = delegate_server(map_path, rendezvous)

        async def tokenless(client: Any) -> Outcome:
            async with asyncio.timeout(5):
                while rendezvous.waiting < 1:
                    await asyncio.sleep(0.01)
            return await read_resource(client, URI)

        async with serving(server) as app:
            async with http_client(app, mint(SECRET, sub='alice'), era=era) as alice, in_memory(server, era=era) as client:
                return await asyncio.gather(read_resource(alice, URI), tokenless(client))

    first, anon = drive(scenario())
    ran = ran_by(storage_launches)
    violations = refusal_violations(anon, [], storage_launches[2:], NO_EXECUTOR)
    violations += [f'the authenticated read: {v}' for v in
                   read_violations(first, summary(*owner_paths('ualice')), ran[:2], 'ualice')]
    assert violations == [], report(violations)
    assert guard.refused == []


def not_found_violations(reads: Mapping[str, Outcome]) -> list[str]:
    """Return every shape whose read was not the protocol's `Resource not found`; empty means none."""
    violations: list[str] = []
    for uri, read in reads.items():
        if not read.is_error or read.code != -32602 or 'Resource not found' not in read.text:
            violations += shape_violations(uri, [f'drew {read.code} {read.text!r} (error={read.is_error}), '
                                                 'expected -32602 Resource not found'])
    return violations


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
def test_unknown_uri_is_not_found(era: str, launches: list[list[str]], guard) -> None:
    executor = RecordingExecutor('shared')

    async def scenario() -> dict[str, Outcome]:
        async with in_memory(shared_server(executor), era=era) as client:
            return {uri: await read_verbatim(client, uri) for uri in NOT_OPEN}

    violations = not_found_violations(drive(scenario()))
    violations += [f'executor ran: {c!r}' for c in executor.calls]
    violations += [f'process launched: {argv!r}' for argv in launches]
    assert violations == [], report(violations)
    assert guard.refused == []


@pytest.mark.unit
@pytest.mark.parametrize('era', ERAS)
@pytest.mark.parametrize('who', ['mapped', 'no-token'])
def test_unknown_uri_is_not_found_in_delegate_mode(who: str, era: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                   launches: list[list[str]], guard) -> None:
    # A mapped caller's read resolves its identity and then finds no such URI, whatever its shape; a
    # tokenless read is let through with nothing set. Neither is refused: each gets the not-found every
    # caller gets in shared mode.
    monkeypatch.setenv('JWT_SECRET', SECRET)
    map_path = user_map(tmp_path, USER_MAP)

    async def scenario() -> dict[str, Outcome]:
        server = delegate_server(map_path)
        if who == 'no-token':
            async with in_memory(server, era=era) as client:
                return {uri: await read_verbatim(client, uri) for uri in NOT_OPEN}
        async with serving(server) as app:
            async with http_client(app, mint(SECRET, sub='alice'), era=era) as client:
                return {uri: await read_verbatim(client, uri) for uri in NOT_OPEN}

    violations = not_found_violations(drive(scenario()))
    violations += [f'process launched: {argv!r}' for argv in launches]
    assert violations == [], report(violations)
    assert guard.refused == []
