# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F6 (review 2, GOAL C12 as amended 2026-10-23): `delegate` mode serves only what every account can read.

`uv run python spec/agents-d-instructions/remediation/F6-delegate-every-account.py [all|docs]`, from
the tree root (`all` is the default; `docs` is only the documentation part, seconds). It supersedes
F3, whose library rows (a `0705` directory, a `0604` file) and open CLI row (under a per-user
temporary directory) encode the "others' bits only" reading that the amendment retired.

- Library, by mode bits, against an oracle of its own (the bits each class needs, written out): every
  file mode the owner can read (0o400-0o777), every directory mode the owner can list
  (0o500-0o777) and every mode of the directory above it the owner can search (0o100-0o777): a
  read for every account is unreadable exactly when one of the owner, group or other classes lacks
  read on the file, read and search on the directory, or search on the ancestor; a read for this
  process serves the files whatever the bits. Every row is planted under a directory every account
  can reach (`/tmp`), so an open row is served.
- Symlinks: the directory read through a link beside it, through a link that sits in a private
  directory, through a chain of links whose middle link sits in a private directory, and with a
  private directory above its target: all but the first unreadable.
- ACLs, set the platform's way and seen by an independent oracle (`ls -led` on macOS, the extended
  attributes on Linux): an entry on the file, the directory or the directory above it makes the
  read for every account unreadable; this process's read keeps the files.
- CLI: the real server in `delegate` mode over HTTP (JWT, two mapped users and one unmapped), both
  eras, on a group-class file, a group-class directory, a private ancestor, a private ancestor
  through a link and an ACL entry: the tool, the resource and the instructions carry the line and no
  file's text. In `local` mode over stdio the same directories serve the files. An open directory
  under `/tmp` serves the files in `delegate` mode.
- Docs: AGENTS.md §8 and README.md state the every-account rule (owner, group, other; ancestors;
  ACL), and no live text (AGENTS.md, README.md, `src/`, `tests/`) still states the "others" rule.
- The class's mutants: `site-others-unchecked`, `site-group-unchecked`, `site-ancestors-unchecked`,
  `site-acl-unchecked`, `site-acl-probe-blind`, `site-acl-posix-only`, `delegate-reads-for-itself`.

Footprint: one Python process, a few sandboxed `chmod`/`ls` children on macOS, one server at a time
(HTTP rows bind 127.0.0.1 on a free port), the mutation children; about 3 min, under 300 MB.
"""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from common import SANDBOX, check, finish, mutants, plant, site

import serve_gate as gate  # noqa: E402

FILES = {'a.md': 'Alpha rule.\n', 'b.md': 'Bravo rule.\n'}
LINE = 'No site rules are served: /etc/agents.d on this host could not be read ({}).'
DIR_LINE = LINE.format('not readable by every account')
FILE_LINE = LINE.format('b.md: not readable by every account')


def open_base() -> Path:
    base = Path(tempfile.mkdtemp(prefix='f6-', dir='/tmp'))
    base.chmod(0o755)
    return base


def reopen(base: Path) -> None:
    base.chmod(0o755)
    for parent, dirs, _ in os.walk(base):
        for name in dirs:
            Path(parent, name).chmod(0o755)


def tree(base: Path, label: str) -> tuple[Path, Path]:
    """`label/etc/agents.d` under `base`, every mode open; (etc, agents.d)."""
    parent = base / label / 'etc'
    root = plant(parent / 'agents.d', FILES)
    (base / label).chmod(0o755)
    parent.chmod(0o755)
    return parent, root


def expect(context: site.SiteContext, readable: bool, line: str, label: str) -> None:
    if readable:
        check([f.name for f in context.files] == ['a.md', 'b.md'], f'{label}: every account can read, yet {context}')
    else:
        check(context == site.SiteContext(reason=line, failed=True) and context.text == line,
              f'{label}: not every account can read, yet {context}')


def library(base: Path) -> None:
    rows = 0
    for mode in range(0o400, 0o1000):
        if mode & 0o400:
            _, root = tree(base, f'file-{mode:o}')
            (root / 'b.md').chmod(mode)
            expect(site.read_local('this host', str(root), for_others=True), mode & 0o444 == 0o444, FILE_LINE,
                   f'file {mode:o}')
            check(len(site.read_local('this host', str(root)).files) == 2, f'file {mode:o}: a read for itself lost files')
            rows += 1
    for mode in range(0o500, 0o1000):
        if mode & 0o500 == 0o500:
            _, root = tree(base, f'dir-{mode:o}')
            root.chmod(mode)
            expect(site.read_local('this host', str(root), for_others=True), mode & 0o555 == 0o555, DIR_LINE,
                   f'directory {mode:o}')
            check(len(site.read_local('this host', str(root)).files) == 2, f'directory {mode:o}: a read for itself lost files')
            rows += 1
    for mode in range(0o100, 0o1000):
        if mode & 0o100:
            parent, root = tree(base, f'up-{mode:o}')
            parent.chmod(mode)
            expect(site.read_local('this host', str(root), for_others=True), mode & 0o111 == 0o111, DIR_LINE,
                   f'ancestor {mode:o}')
            rows += 1
    check(rows == 256 + 128 + 256, f'library: {rows} rows, expected 640')


def links(base: Path) -> dict[str, tuple[Path, bool]]:
    """The symlink rows: the path each reads, and whether every account can read it."""
    parent, root = tree(base, 'links')
    hidden = base / 'links' / 'hidden'
    hidden.mkdir(mode=0o700)
    hidden.chmod(0o700)
    (base / 'links' / 'beside').symlink_to(root)
    (hidden / 'inside').symlink_to(root)
    (base / 'links' / 'chain').symlink_to(hidden / 'inside')
    private_parent, private_root = tree(base, 'private-target')
    private_parent.chmod(0o700)
    (base / 'links' / 'to-private').symlink_to(private_root)
    return {'beside': (base / 'links' / 'beside', True), 'inside-a-private-directory': (hidden / 'inside', False),
            'chain-through-a-private-directory': (base / 'links' / 'chain', False),
            'private-above-the-target': (base / 'links' / 'to-private', False)}


def symlinks(base: Path) -> None:
    for label, (path, readable) in links(base).items():
        expect(site.read_local('this host', str(path), for_others=True), readable, DIR_LINE, f'link {label}')
        check(len(site.read_local('this host', str(path)).files) == 2, f'link {label}: a read for itself lost files')


def give_acl(path: Path) -> None:
    if sys.platform == 'darwin':
        rule = 'user:nobody deny list,search' if path.is_dir() else 'user:nobody deny read'
        done = subprocess.run([str(SANDBOX), 'chmod', '+a', rule, str(path)], capture_output=True, text=True,
                              timeout=30, stdin=subprocess.DEVNULL)
        check(done.returncode == 0, f'chmod +a {path.name}: {done.stderr.strip()}')
        return
    own, rest = (7, 5) if path.is_dir() else (6, 4)
    entries = [(0x01, own, 0xFFFFFFFF), (0x02, 0, 65534), (0x04, rest, 0xFFFFFFFF), (0x10, rest, 0xFFFFFFFF),
               (0x20, rest, 0xFFFFFFFF)]
    os.setxattr(path, 'system.posix_acl_access', struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *e)
                                                                                     for e in entries))


def has_acl(path: Path) -> bool:
    """The oracle: `ls -led` lists an entry (macOS), or the ACL attribute is there (Linux)."""
    if sys.platform == 'darwin':
        done = subprocess.run([str(SANDBOX), 'ls', '-led', str(path)], capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL)
        return re.search(r'^\s*\d+: ', done.stdout, re.M) is not None
    return 'system.posix_acl_access' in os.listxattr(path)


def acls(base: Path) -> dict[str, Path]:
    """The ACL rows: the directory each reads, its entry already set."""
    rows = {}
    for label in ('file', 'directory', 'ancestor'):
        parent, root = tree(base, f'acl-{label}')
        target = {'file': root / 'b.md', 'directory': root, 'ancestor': parent}[label]
        give_acl(target)
        check(has_acl(target) and not has_acl(root / 'a.md'), f'acl {label}: the oracle does not see the entry alone')
        check(site._extended(str(target)), f'acl {label}: the probe does not see the entry')
        rows[label] = root
    return rows


def acl_reads(base: Path) -> None:
    for label, root in acls(base).items():
        expect(site.read_local('this host', str(root), for_others=True), False,
               FILE_LINE if label == 'file' else DIR_LINE, f'acl {label}')
        check(len(site.read_local('this host', str(root)).files) == 2, f'acl {label}: a read for itself lost files')


def cli(base: Path, tmp: Path) -> None:
    user_map = tmp / 'user-map'
    who = os.environ.get('USER', 'nobody')
    user_map.write_text(f'alice {who}\nbob {who}\n')
    rows: dict[str, tuple[Path, str | None]] = {}
    _, root = tree(base, 'cli-groupless-file')
    (root / 'b.md').chmod(0o604)
    rows['groupless-file'] = (root, FILE_LINE)
    _, root = tree(base, 'cli-groupless-dir')
    root.chmod(0o705)
    rows['groupless-dir'] = (root, DIR_LINE)
    parent, root = tree(base, 'cli-private-ancestor')
    parent.chmod(0o700)
    rows['private-ancestor'] = (root, DIR_LINE)
    (base / 'cli-link').symlink_to(root)
    rows['private-ancestor-through-link'] = (base / 'cli-link', DIR_LINE)
    rows['acl-file'] = (acls(base / 'cli')['file'], FILE_LINE)
    _, root = tree(base, 'cli-open')
    rows['open'] = (root, None)
    for label, (root, line) in rows.items():
        for era in gate.ERAS:
            port = gate.free_port()
            server = gate.Server(root, tmp / f'log-{label}-{era}', ['-e', 'delegate', '-a', 'jwt', '-t', 'http',
                                                                 '-p', str(port)],
                                 {'JWT_SECRET': gate.SECRET, 'RCAC_USER_MAP': str(user_map)})
            tokens = [gate.mint(gate.SECRET, sub=s) for s in ('alice', 'bob', 'mallory')]
            seen = gate.http_sessions(server, port, era, tokens, steps)
            check(len(seen) == 3, f'delegate {label} {era}: {len(seen)} sessions')
            for user, (tool, resource, instructions) in zip(('alice', 'bob', 'mallory'), seen):
                if line:
                    check(instructions.endswith(f'{site.HEADING}\n\n{line}') and resource == line
                          and (tool == line or user == 'mallory'),
                          f'delegate {label} {era} {user}: {tool[:60]!r} / {resource[:60]!r}')
                    check('rule.' not in tool + resource + instructions, f'delegate {label} {era} {user}: site text served')
                else:
                    check('Bravo rule.' in resource and 'Bravo rule.' in instructions,
                          f'delegate {label} {era} {user}: the open directory was not served')
            local = gate.stdio_session(gate.Server(root, tmp / f'log-local-{label}-{era}', ['-e', 'local', '-t', 'stdio']),
                                       era, steps)
            check(local[0] == local[1] and 'Alpha rule.' in local[1] and 'Bravo rule.' in local[1],
                  f'local {label} {era}: the file system answer was not served: {local[1][:80]!r}')
    check(gate.FAILURES == [], f'serve helpers: {gate.FAILURES}')


async def steps(client) -> tuple[str, str, str]:
    result = await client.call_tool('cluster_context', {}, raise_on_error=False)
    tool = ''.join(getattr(p, 'text', '') for p in result.content)
    contents = await client.read_resource('rcac://context')
    return tool, ''.join(getattr(c, 'text', '') for c in contents), client.instructions or ''


def section(text: str, start: str, end: str) -> str:
    match = re.search(rf'^{re.escape(start)}.*?(?=^{re.escape(end)})', text, re.S | re.M)
    return ' '.join(match.group(0).split()) if match else ''


# The retired rule's phrasing: a live text that still states it re-arms the trap.
RETIRED = [r'only what others can read', r"others' read", r'readable (and searchable )?by others',
           r'not readable by others', r'NOT_FOR_OTHERS', r'_others_may', r'world-readable administrative markdown']


def docs() -> None:
    s8 = section(Path('AGENTS.md').read_text(), '### 8.', '### 9.')
    check('serves only what every account can read' in s8, '§8 does not state the every-account rule')
    for needed in ('owner, group, other', 'every directory a lookup of the path passes', 'ACL', 'for_others=True',
                   '`local` and `ssh` read as the user'):
        check(needed in s8, f'§8 does not say {needed!r}')
    readme = ' '.join(Path('README.md').read_text().split())
    check('serves only what every account could read' in readme and 'the group' in readme and 'ACL' in readme
          and 'every directory above it' in readme, 'README.md does not state the every-account rule')
    for path in [Path('AGENTS.md'), Path('README.md'), *Path('src').rglob('*.py'), *Path('tests').glob('*.py')]:
        flat = ' '.join(path.read_text().split())
        for pattern in RETIRED:
            check(re.search(pattern, flat) is None, f'{path}: still states the retired rule ({pattern!r})')


def main(argv: list[str]) -> int:
    mode = argv[0] if argv else 'all'
    docs()
    if mode == 'all':
        base = open_base()
        try:
            check(site._open_to_everyone(str(base)), f'{base} is not open to every account; no row can be served')
            library(base)
            symlinks(base)
            acl_reads(base / 'acl')
            with tempfile.TemporaryDirectory(prefix='f6-') as name:
                cli(base, Path(name))
        finally:
            reopen(base)
            shutil.rmtree(base)
            check(not base.exists(), f'{base} was not removed')
        mutants('site-others-unchecked', 'site-group-unchecked', 'site-ancestors-unchecked', 'site-acl-unchecked',
                'site-acl-probe-blind', 'site-acl-posix-only', 'delegate-reads-for-itself')
    return finish(f'F6 delegate every account ({mode})')


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
