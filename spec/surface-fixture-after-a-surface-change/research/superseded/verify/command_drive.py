"""Drive the surface command, `bin/record_surface.py`, the way a maintainer runs it. Run from the worktree root.

Usage: uv run python -I spec/surface-fixture-after-a-surface-change/verify/command_drive.py all

`all` checks, in order:
  determinism   two sandboxed runs write byte-identical files (R1), equal to the staged fixture: the
                committed fixture is the command's own output, not a hand-edit (R5, R6); the first
                run's delta, against the fixture at 0bfacae, goes to stderr for the re-baseline body
  sandbox       outside bin/sandbox.sh the command refuses and writes nothing (R1)
  pytest        under pytest (PYTEST_CURRENT_TEST set) the command refuses and writes nothing (R1)
  eras          with the modern record planted to differ from the legacy one beyond the capabilities,
                the command refuses, names each differing field path and writes nothing (R4)
  version       with a served version no candidate distribution is installed at, it refuses, naming
                `serverInfo.version` and both candidates (M1)
  version-core  with the served version planted as the core's installed version, the written fixture
                attributes it to `cluster-mcp` (the second candidate is really consulted)
  delta         with both eras planted with a changed description, an added argument and a removed
                resource, it writes a fixture that passes against the planted records and prints
                exactly those three paths, one line each (R5)
  against       with `--against` naming an empty surface, it lists the delta against that file, not
                the fixture at HEAD: one `added` line per top-level key (review cycle 1, F3)
  head          without `--against`, the delta is the one listed against the fixture at HEAD
                (review cycle 1, F3)

The planted drives import the command in a child under bin/sandbox.sh and replace the suite's
`command_record(era)`, which the command hands `command_main` as its record effect (review cycle 2,
N1); nothing is planted into the package or the committed fixture. The first run's delta against
0bfacae goes to stderr, for the re-baseline commit's body. The gate checks, around this drive, that
the working tree's fixture still equals the staged one: a drive or command that wrote the real
fixture fails there.

Footprint: one child at a time (the sandbox, uv and one python), under 1 GB.
"""

from __future__ import annotations

import copy
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENVIRON = dict(os.environ)
ROOT = Path.cwd()
SANDBOX = ROOT / 'bin' / 'sandbox.sh'
# Where the command and the suite's modules are read from: the worktree, or a mutated copy of its
# `bin/` and `tests/` when the cycle's sweep sets SURFACE_CODE_ROOT (the sandbox, the environment and
# the staged fixture stay the worktree's).
CODE = Path(ENVIRON.get('SURFACE_CODE_ROOT') or ROOT)
COMMAND = CODE / 'bin' / 'record_surface.py'
FIXTURE = 'tests/fixtures/served_surface.json'
# The documented form: the locked stack, synced exactly (an extra distribution in the environment
# would be served and recorded).
UV_RUN = ('uv', 'run', '--locked', '--exact', 'python')
# The fixture as the cycle found it (origin/develop when it was shaped): the base of the re-baseline's delta.
BASE = '0bfacae'


def fail(message: str) -> None:
    print(f'command_drive: FAIL: {message}', file=sys.stderr)
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f'command_drive: ok: {message}', file=sys.stderr)


def run(argv: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, env=dict(ENVIRON if env is None else env))


def staged_fixture() -> bytes:
    shown = subprocess.run(['git', 'show', f':{FIXTURE}'], capture_output=True, env=dict(ENVIRON))
    if shown.returncode != 0:
        fail(f'cannot read the staged {FIXTURE}: {shown.stderr.decode()}')
    return shown.stdout


def sandboxed(*argv: str) -> subprocess.CompletedProcess[str]:
    return run([str(SANDBOX), *UV_RUN, *argv])


def determinism(scratch: Path) -> None:
    first, second, base = scratch / 'first.json', scratch / 'second.json', scratch / 'base.json'
    shown = subprocess.run(['git', 'show', f'{BASE}:{FIXTURE}'], capture_output=True, env=dict(ENVIRON))
    if shown.returncode != 0:
        fail(f'cannot read {BASE}:{FIXTURE}')
    base.write_bytes(shown.stdout)
    one = sandboxed(str(COMMAND), '--out', str(first), '--against', str(base))
    two = sandboxed(str(COMMAND), '--out', str(second))
    for name, done in (('first', one), ('second', two)):
        if done.returncode != 0:
            fail(f'the {name} run exited {done.returncode}:\n{done.stdout}{done.stderr}')
    if first.read_bytes() != second.read_bytes():
        fail('two runs with no change between them wrote different bytes')
    if first.read_bytes() != staged_fixture():
        fail(f'a fresh run differs from the staged {FIXTURE}: the fixture is not the command\'s output')
    print(f'--- delta of a fresh run against the fixture at {BASE} (for the re-baseline commit body) ---',
          file=sys.stderr)
    print(one.stdout, end='', file=sys.stderr)
    ok('two runs are byte-identical and equal the staged fixture')


def refusal(scratch: Path, name: str, env: dict[str, str], argv: list[str], fragment: str) -> None:
    out = scratch / f'{name}.json'
    done = run([*argv, '--out', str(out)], env)
    if done.returncode == 0 or out.exists():
        fail(f'{name}: the command ran (exit {done.returncode}, wrote {out.exists()})')
    if fragment not in done.stderr:
        fail(f'{name}: the refusal does not name {fragment!r}:\n{done.stderr}')
    ok(f'{name}: refused, naming {fragment!r}, and wrote nothing')


def planted(scratch: Path, plant: str) -> subprocess.CompletedProcess[str]:
    return sandboxed('-I', str(Path(__file__).resolve()), 'child', plant, str(scratch / f'{plant}.json'), str(CODE))


def all_checks() -> None:
    if not COMMAND.exists():
        fail(f'{COMMAND} does not exist yet (build writes it)')
    # Every run below writes to --out only: the fixture at its default path is never written, not even
    # with the bytes it already holds (review cycle 1, F3).
    fixture = CODE / FIXTURE
    before = fixture.stat().st_mtime_ns
    with tempfile.TemporaryDirectory(prefix='surface-drive-') as name:
        scratch = Path(name)
        determinism(scratch)
        bare = {k: v for k, v in ENVIRON.items() if k != 'CLUSTER_MCP_SANDBOX'}
        refusal(scratch, 'sandbox', bare, [*UV_RUN, str(COMMAND)], 'bin/sandbox.sh')
        refusal(scratch, 'pytest', {**ENVIRON, 'PYTEST_CURRENT_TEST': 'tests/test_x.py::test_x (call)'},
                [str(SANDBOX), *UV_RUN, str(COMMAND)], 'PYTEST_CURRENT_TEST')

        eras = planted(scratch, 'eras')
        if eras.returncode == 0 or (scratch / 'eras.json').exists():
            fail(f'eras: the command wrote a fixture from eras that differ:\n{eras.stdout}{eras.stderr}')
        for path in ('run_command', 'description', 'serverInfo', 'websiteUrl'):
            if path not in eras.stderr:
                fail(f'eras: the refusal does not name {path!r}:\n{eras.stderr}')
        if 'the two protocol eras are served different surfaces' not in eras.stderr:
            fail(f'eras: the refusal does not say the eras differ (review cycle 1, F3):\n{eras.stderr}')
        if 'capabilities' in eras.stderr:
            fail(f'eras: the refusal names the capabilities, which are recorded per era:\n{eras.stderr}')
        ok('eras: refused, naming each differing field, and wrote nothing')

        version = planted(scratch, 'version')
        named = all(word in version.stderr for word in ('serverInfo.version', 'cluster-mcp', 'fastmcp-slim'))
        if version.returncode == 0 or (scratch / 'version.json').exists() or not named:
            fail(f'version: not refused naming serverInfo.version and both candidates:\n{version.stdout}{version.stderr}')
        ok('version: a served version no candidate is installed at is refused, naming the candidates')

        core = planted(scratch, 'version-core')
        written = scratch / 'version-core.json'
        source = json.loads(written.read_text())['serverInfo']['version'] if written.exists() else None
        if core.returncode != 0 or source != {'distribution': 'cluster-mcp'}:
            fail(f'version-core: the core\'s version was not attributed to cluster-mcp ({source!r}):\n{core.stderr}')
        ok('version-core: a served version equal to the core\'s is recorded as the core\'s')

        delta = planted(scratch, 'delta')
        if delta.returncode != 0 or not (scratch / 'delta.json').exists():
            fail(f'delta: exited {delta.returncode}:\n{delta.stdout}{delta.stderr}')
        lines = [line for line in delta.stdout.splitlines() if line.strip()]
        want = (('run_command', 'description', 'changed'), ('run_command', 'planted_argument', 'added'),
                ('rcac://storage', 'removed'))
        if len(lines) != len(want) or not all(any(all(w in line for w in words) for line in lines) for words in want):
            fail(f'delta: expected exactly one line per planted path, got:\n{delta.stdout}')
        if 'failed' in delta.stderr.lower():
            fail(f'delta: the written fixture does not pass against the planted records:\n{delta.stderr}')
        ok('delta: wrote a passing fixture and printed exactly the planted paths')

        empty = scratch / 'empty.json'
        empty.write_text('{}\n')
        against = sandboxed(str(COMMAND), '--out', str(scratch / 'against.json'), '--against', str(empty))
        written = json.loads((scratch / 'against.json').read_text()) if (scratch / 'against.json').exists() else {}
        want = [f'- {key}: added' for key in sorted(written)]
        if against.returncode != 0 or not want or against.stdout.splitlines() != want:
            fail(f'against: the delta is not listed against --against (want {want}):\n{against.stdout}{against.stderr}')
        ok('against: the delta is listed against the --against file')

        shown = subprocess.run(['git', 'show', f'HEAD:{FIXTURE}'], capture_output=True, env=dict(ENVIRON))
        head = scratch / 'head.json'
        head.write_bytes(shown.stdout)
        implicit = sandboxed(str(COMMAND), '--out', str(scratch / 'implicit.json'))
        explicit = sandboxed(str(COMMAND), '--out', str(scratch / 'explicit.json'), '--against', str(head))
        if shown.returncode != 0 or implicit.returncode != 0 or implicit.stdout != explicit.stdout:
            fail(f'head: without --against the delta is not listed against HEAD:\n{implicit.stdout}---\n{explicit.stdout}')
        ok('head: without --against the delta is listed against the fixture at HEAD')

    if fixture.stat().st_mtime_ns != before:
        fail(f'the command wrote the fixture at its default path ({fixture}), not only --out')
    ok('no run wrote the fixture at its default path')


def child(plant: str, out: str, code: str) -> int:
    """In the sandbox: import the command from `code`, replace its record seam with a planted one, run it."""
    repo = Path(os.environ['CLUSTER_MCP_REPO'])
    sys.path[:0] = [str(Path(code) / 'bin'), str(Path(code) / 'tests')]
    import record_surface  # noqa: E402 - the command, imported from the repository's bin/
    import test_surface  # noqa: E402 - the suite's module the command takes its choices and record from

    real = test_surface.command_record

    def record(era: str) -> dict:
        surface = copy.deepcopy(real(era))
        if plant == 'eras' and era == 'modern':
            surface['tools']['run_command']['description'] += '\nPlanted.'
            surface['serverInfo']['websiteUrl'] = 'https://planted.invalid'
        elif plant == 'version':
            surface['serverInfo']['version'] = '0.0.0+planted'
        elif plant == 'version-core':
            surface['serverInfo']['version'] = importlib.metadata.version('cluster-mcp')
        elif plant == 'delta':
            surface['tools']['run_command']['description'] += '\nPlanted.'
            surface['tools']['run_command']['inputSchema']['properties']['planted_argument'] = {'type': 'string'}
            del surface['resources']['rcac://storage']
        return surface

    test_surface.command_record = record
    return record_surface.main(['--out', out, '--against', str(repo / FIXTURE)])


def main(argv: list[str]) -> int:
    if argv == ['all']:
        all_checks()
        return 0
    if len(argv) == 4 and argv[0] == 'child':
        return child(argv[1], argv[2], argv[3])
    print('usage: command_drive.py all', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
