# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""F9 (review 3, GOAL C13): the read for every account reads what it checked, so no swap races past C12.

`uv run python spec/agents-d-instructions/remediation/F9-read-what-is-checked.py`, from the tree root.

- Race, in this process, against a writer of the directory and of a symlink on its route (a separate
  process swapping as fast as it can, the shape of review 3's probe): a file swapped between a
  regular file and a symlink to a file under a private directory, and the symlink read swapped
  between an open directory and one under a private directory. Not one read for every account may
  serve the private text; the race is real (the swapper swapped, the open text was served, and a
  lookup by name during the race reached the private text).
- CLI: the real server in `delegate` mode over HTTP (JWT, two mapped users and one unmapped), both
  eras: once before the race, serving the open text; then started again and again while the file
  swap runs, where every instructions, resource and tool answer carries the open text or the line
  saying the directory holds no rules, and none the private text. The frozen shim runs under
  `remediation/fd-listing`, which this checker sets for its servers.
- `local` keeps its own answer: on a directory holding a symlinked `*.md` file, a FIFO and a
  directory named `*.md`, `read_local` for this process equals `READ_SITE`'s answer, and a
  symlinked file is never read for every account either.
- The deterministic seams: `test_a_swap_after_a_check_changes_nothing_read_for_others` and the
  route rows of `test_a_read_for_others_keeps_only_what_every_account_can_read`.
- The class's mutants: `site-file-reread-by-path`, `site-listed-by-path`, `site-file-follows-links`,
  `site-route-follows-links`, `site-route-opened-for-read`.

Footprint: one Python process, one swapper process, one server at a time (HTTP on 127.0.0.1, a free
port), the mutation children; about 2 min, under 300 MB. Everything planted is under `/tmp` and
removed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from common import both, check, finish, mutants, plant, site

import serve_gate as gate  # noqa: E402

PRIVATE = 'PRIVATE-RULE-TEXT'
PUBLIC = 'Public rule.'
RACE_SECONDS = 5.0
STARTS_PER_ERA = 4

# Swaps `argv[1]` between a symlink to `argv[2]` and a regular file holding the public text (or,
# with `argv[4] == 'link'`, between symlinks to `argv[2]` and `argv[3]`) until `argv[5]` exists;
# prints how many swaps it made.
SWAPPER = """
import os, sys
at, one, two, kind, stop = sys.argv[1:6]
tmp = at + '.swap'
swaps = 0
while not os.path.exists(stop):
    for target in (one, two):
        try:
            if kind == 'link' or target == one:
                os.symlink(target, tmp)
            else:
                with open(tmp, 'w') as f:
                    f.write(two)
                os.chmod(tmp, 0o644)
            os.replace(tmp, at)
            swaps += 1
        except FileExistsError:
            os.unlink(tmp)
print(swaps)
"""


def tree(base: Path) -> dict[str, Path]:
    """`open/agents.d` with the public file, `private/agents.d` with the private one, `private`
    at mode 700, and `site`, a symlink to the open directory."""
    public = plant(base / 'open' / 'agents.d', {'a.md': f'{PUBLIC}\n'})
    hidden = base / 'private'
    elsewhere = plant(hidden / 'agents.d', {'a.md': f'{PRIVATE}\n'})
    (hidden / 'secret.md').write_text(f'{PRIVATE}\n')
    for path, mode in ((base, 0o755), (base / 'open', 0o755), (hidden / 'secret.md', 0o644), (hidden, 0o700)):
        path.chmod(mode)
    (base / 'site').symlink_to(public)
    return {'public': public, 'elsewhere': elsewhere, 'secret': hidden / 'secret.md', 'site': base / 'site'}


class Swapper:
    def __init__(self, at: Path, one: Path | str, two: Path | str, kind: str) -> None:
        self.stop = at.parent / f'.stop-{at.name}'
        self.proc = subprocess.Popen([sys.executable, '-c', SWAPPER, str(at), str(one), str(two), kind, str(self.stop)],
                                     stdout=subprocess.PIPE, text=True)
        time.sleep(0.5)

    def finish(self) -> int:
        self.stop.touch()
        out, _ = self.proc.communicate(timeout=30)
        self.stop.unlink()
        return int(out.strip() or 0)


def race(base: Path) -> None:
    paths = tree(base)
    shapes = {'file': (paths['public'] / 'a.md', paths['secret'], PUBLIC + '\n', 'file'),
              'route': (paths['site'], paths['public'], paths['elsewhere'], 'link')}
    for shape, (at, one, two, kind) in shapes.items():
        swapper = Swapper(at, one, two, kind)
        counts = {'private': 0, 'public': 0, 'other': 0}
        reached = 0
        try:
            start = time.monotonic()
            while time.monotonic() - start < RACE_SECONDS:
                text = site.read_local('this host', str(paths['site']), for_others=True).text
                counts['private' if PRIVATE in text else 'public' if PUBLIC in text else 'other'] += 1
                try:
                    reached += PRIVATE in (paths['site'] / 'a.md').read_text()
                except OSError:
                    pass
        finally:
            swaps = swapper.finish()
        print(f'F9 race {shape}: {counts}, {swaps} swaps, private reached by name {reached} times', file=sys.stderr)
        check(counts['private'] == 0, f'race {shape}: {counts["private"]} reads served the private text')
        check(swaps > 100 and counts['public'] > 0 and reached > 0, f'race {shape}: the race did not run '
              f'({swaps} swaps, {counts["public"]} public reads, private reached {reached} times)')
        if shape == 'file':
            (paths['public'] / 'a.md').unlink(missing_ok=True)
            (paths['public'] / 'a.md').write_text(f'{PUBLIC}\n')
            (paths['public'] / 'a.md').chmod(0o644)


async def steps(client) -> str:
    result = await client.call_tool('cluster_context', {}, raise_on_error=False)
    contents = await client.read_resource('rcac://context')
    return (''.join(getattr(p, 'text', '') for p in result.content) + ''.join(getattr(c, 'text', '') for c in contents)
            + (client.instructions or ''))


def sessions(site_dir: Path, user_map: Path, log: Path, era: str) -> list[str]:
    port = gate.free_port()
    server = gate.Server(site_dir, log, ['-e', 'delegate', '-a', 'jwt', '-t', 'http', '-p', str(port)],
                         {'JWT_SECRET': gate.SECRET, 'RCAC_USER_MAP': str(user_map)})
    seen = gate.http_sessions(server, port, era, [gate.mint(gate.SECRET, sub=s) for s in ('alice', 'bob', 'mallory')],
                              steps)
    check(len(seen) == 3, f'cli {era} {log.name}: {len(seen)} sessions')
    return seen


def cli(base: Path, tmp: Path) -> None:
    os.environ['CLUSTER_MCP_FD_LISTING'] = '1'
    os.environ['PYTHONPATH'] = str(Path(__file__).resolve().parent / 'fd-listing')
    paths = tree(base)
    user_map = tmp / 'user-map'
    who = os.environ.get('USER', 'nobody')
    user_map.write_text(f'alice {who}\nbob {who}\n')
    for era in gate.ERAS:
        check(all(PUBLIC in text for text in sessions(paths['site'], user_map, tmp / f'log-calm-{era}', era)),
              f'cli {era}: the open text was not served before the race')
    swapper = Swapper(paths['public'] / 'a.md', paths['secret'], PUBLIC + '\n', 'file')
    served = {'private': 0, 'public': 0, 'none': 0, 'other': 0}
    try:
        for era in gate.ERAS:
            for n in range(STARTS_PER_ERA):
                for text in sessions(paths['site'], user_map, tmp / f'log-{era}-{n}', era):
                    served['private' if PRIVATE in text else 'public' if PUBLIC in text
                           else 'none' if text.endswith('holds no rules (no non-empty *.md file but AGENTS.md).')
                           else 'other'] += 1
    finally:
        swaps = swapper.finish()
    print(f'F9 cli: {served} sessions over {2 * STARTS_PER_ERA} starts, {swaps} swaps', file=sys.stderr)
    check(served['private'] == 0, f'cli: {served["private"]} sessions carried the private text')
    check(served['other'] == 0, f'cli: {served["other"]} sessions served neither the open text nor its absence')
    check(swaps > 0, 'cli: the swapper never swapped')
    check(gate.FAILURES == [], f'serve helpers: {gate.FAILURES}')


def local(base: Path) -> None:
    root = plant(base / 'local', {'a.md': 'Alpha rule.\n', 'b.md': 'Bravo rule.\n'})
    (base / 'outside.md').write_text('Outside rule.\n')
    (base / 'outside.md').chmod(0o644)
    (root / 'linked.md').symlink_to(base / 'outside.md')
    (root / 'dir.md').mkdir()
    os.mkfifo(root / 'fifo.md')
    reads = both(root)
    check([f.name for f in reads['local'].files] == ['a.md', 'b.md'], f'local: read {reads["local"]}')
    others = site.read_local('this host', str(root), for_others=True)
    check([f.name for f in others.files] == ['a.md', 'b.md'] and 'Outside' not in others.text,
          f'for every account: read {others}')


def reopen(base: Path) -> None:
    for parent, dirs, _ in os.walk(base):
        for name in dirs:
            Path(parent, name).chmod(0o755)


def main() -> int:
    base = Path(tempfile.mkdtemp(prefix='f9-', dir='/tmp'))
    base.chmod(0o755)
    try:
        check(site._open_to_everyone(str(base)), f'{base} is not open to every account; no row can be served')
        race(base / 'race')
        local(base)
        with tempfile.TemporaryDirectory(prefix='f9-') as name:
            cli(base / 'cli', Path(name))
    finally:
        reopen(base)
        shutil.rmtree(base)
        check(not base.exists(), f'{base} was not removed')
    seams = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider',
                            'tests/test_site.py::test_a_swap_after_a_check_changes_nothing_read_for_others',
                            'tests/test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read'],
                           capture_output=True, text=True, timeout=300)
    check(seams.returncode == 0 and ' passed' in seams.stdout and 'skipped' not in seams.stdout,
          f'the seam tests: {seams.stdout[-300:]}')
    mutants('site-file-reread-by-path', 'site-listed-by-path', 'site-file-follows-links', 'site-route-follows-links',
            'site-route-opened-for-read')
    return finish('F9 read what is checked')


if __name__ == '__main__':
    sys.exit(main())
