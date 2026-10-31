# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The site's rules: `/etc/agents.d/*.md`, read once at startup, and the instructions composed from them.

The files are every `*.md` regular file directly in the directory (a `maxdepth 1` glob; a symlink is
not a regular file, and dotfiles count, as `find -name` matches them) except the assembled
`AGENTS.md`, which repeats the others; only that exact name is skipped. Each becomes a block under a
`<!-- Source: {name} -->` header, in the byte order of the names (`LC_ALL=C sort`). A file's text is
its content with trailing whitespace removed; a file with nothing else in it carries no rule and is
not served.

The read happens once, before the server is built: over the shared executor in `ssh` mode (the
cluster's files), in this process in `local` and `delegate` modes (the host's files, read as the
server and never as a user). In `delegate` mode the server reads for accounts other than its own, so
it serves only what every account can read: each class (owner, group, other) must hold search on
every directory a lookup of the path passes, symlinks followed, read and search on the directory
itself and read on each file, and none of them may carry an extended ACL entry; anything else is
unreadable there, and no user receives text an ordinary account could not read. That read checks
what it reads: it walks the path from `/` by descriptor, following a symlinked directory only from
the descriptor of the directory holding it, and opens each file from the checked directory's
descriptor without following a link, so a swap after a check changes nothing read. `local` and `ssh`
keep the file system's own answer. The read is bounded: a read that has not finished within
`READ_TIMEOUT` seconds is abandoned, and the server starts with one line saying why no site rules
are served.

A file is its name's bytes: two names that decode alike (different invalid UTF-8 bytes, each read
as U+FFFD) are two files, ordered by those bytes whatever order the directory lists them in.

Every length here is in UTF-16 code units (`units`), the budget's own unit: what is reserved, cut
or checked. A name is shown with each control character (C0, DEL, C1, U+2028, U+2029) and the
backslash as an escape (`shown`), so no name can break a header, a reason or the note across lines,
and no two decoded names are shown alike.
"""

# Type annotations
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Final
from weakref import WeakKeyDictionary

# Standard libs
import base64
import binascii
import ctypes
import errno
import fnmatch
import functools
import os
import queue
import stat
import sys
import threading

# Internal libs
from cluster_mcp.core.executor.base import TIMEOUT_EXIT_CODE, Executor
from cluster_mcp.core.scripts import fixed, script_argv

# Public interface
__all__ = ['CONVENTION', 'AGENTS_D', 'EXCLUDED', 'READ_TIMEOUT', 'DEFAULT_BUDGET', 'DETAIL_LIMIT', 'NOT_FOR_EVERYONE',
           'HEADING', 'READ_SITE', 'SiteFile', 'SiteContext', 'BudgetError', 'units', 'shown', 'read_local', 'parse_remote',
           'read_remote', 'read_bounded', 'omission_note', 'compose', 'minimum_budget', 'register', 'site_of']

# The convention's path, as every text names it. `AGENTS_D` is where the read looks and `READ_TIMEOUT`
# how long it may take, both read at call time: a test points them elsewhere, and no text changes.
CONVENTION: Final = '/etc/agents.d'
AGENTS_D = CONVENTION
READ_TIMEOUT = 10.0
EXCLUDED: Final = 'AGENTS.md'
DEFAULT_BUDGET: Final = 4096
HEADING: Final = f'## Site context ({CONVENTION})'

# The longest detail a reason carries, in UTF-16 code units; a longer one (a long file name) is
# shortened, so every reason fits the room `minimum_budget` keeps for it.
DETAIL_LIMIT: Final = 80

# The detail of a directory or file that not every account can read, in `delegate` mode.
NOT_FOR_EVERYONE: Final = 'not readable by every account'

# The mode bits every class (owner, group, other) must hold in `delegate` mode: search on each
# directory a lookup passes, read and search on the site directory, read on a file.
SEARCH: Final = 0o111
LIST: Final = 0o555
READ: Final = 0o444

# On Linux an ACL shows as an extended attribute in the `system.` namespace whose name says so: a
# POSIX ACL (`system.posix_acl_access`, `system.posix_acl_default`), an NFSv4 ACL
# (`system.nfs4_acl`), a rich ACL (`system.richacl`), and any other of the family. A POSIX ACL that
# only restates the mode bits is not stored as one, so any such name present means extended entries.
ACL_NAMESPACE: Final = 'system.'

# macOS keeps an ACL where no extended attribute shows it (Python has no `os.listxattr` there);
# libSystem's acl(3) reads it.
ACL_TYPE_EXTENDED: Final = 0x100
ACL_FIRST_ENTRY: Final = 0

# The remote read: every regular `*.md` entry directly in "$1" (dotfiles and a bare `.md` too, as
# `find -name` matches them), each name and content as one base64 word, so no name or content can
# forge a line, then a count the parser checks, so an answer cut short reads as unreadable rather
# than as fewer files. Every command it runs that a function could replace is undone first:
# `launch.FIXED_RESET` covers `cd` and `printf`, and the first line here the rest (`base64`, `shopt`,
# `tr`, `test`). The others are POSIX special builtins (`unset`, `set`, `exit`, `continue`), which no
# function replaces in the POSIX-mode bash a fixed script runs in; `test` is spelled out, never `[`,
# a name `unset -f` cannot take there. The glob state a login profile can export (`BASHOPTS`,
# `SHELLOPTS`, `GLOBIGNORE`) is reset here too, so the match is the same whatever it set; an option
# this bash does not know is skipped.
READ_SITE = fixed(
    'unset -f base64 shopt tr test\n'
    'unset GLOBIGNORE\n'
    'set +f\n'
    'for o in dotglob nullglob failglob nocaseglob globstar extglob; do shopt -u "$o" 2>/dev/null; done\n'
    'd=$1\n'
    'if test ! -e "$d"; then printf "missing\\n"; exit 0; fi\n'
    'if test ! -d "$d"; then printf "notdir\\n"; exit 0; fi\n'
    'cd -- "$d" 2>/dev/null && test -r . || { printf "unreadable\\n"; exit 0; }\n'
    'n=0\n'
    'for f in ./*.md ./.*.md ./.md; do\n'
    '  test -f "$f" && test ! -h "$f" || continue\n'
    '  n=$((n+1))\n'
    '  name=$(printf %s "${f#./}" | base64 | tr -d "\\n")\n'
    '  if body=$(base64 < "$f"); then\n'
    '    printf "file %s %s\\n" "$name" "$(printf %s "$body" | tr -d "\\n")"\n'
    '  else\n'
    '    printf "unreadable-file %s\\n" "$name"\n'
    '  fi\n'
    'done\n'
    'printf "end %s\\n" "$n"\n')


@dataclass(frozen=True)
class SiteFile:
    """One file's name and its text (the content, trailing whitespace removed).

    `raw` is the name's bytes, which identify and order the file; `name` is those bytes decoded
    (U+FFFD for an invalid byte), which two files can share. It defaults to `name` encoded.
    """

    name: str
    text: str
    raw: bytes = b''

    def __post_init__(self) -> None:
        if not self.raw:
            object.__setattr__(self, 'raw', self.name.encode('utf-8', 'surrogatepass'))

    @property
    def block(self) -> str:
        """The file as the site context shows it: its header line, then its text."""
        return f'<!-- Source: {shown(self.name)} -->\n{self.text}'


@dataclass(frozen=True)
class SiteContext:
    """What the startup read found: the files, or one line saying why there are none.

    `failed` marks a read that could not finish (unreadable, timed out), whose line the tool and the
    resource return; a missing directory or one with no eligible file is not a failure, and they
    return `''`. Each line names where the read looked (`the cluster` or `this host`), never a host.
    """

    files: tuple[SiteFile, ...] = ()
    reason: str = ''
    failed: bool = False

    @property
    def text(self) -> str:
        """The full site text, as `cluster_context` and `cluster://context` return it."""
        if self.files:
            return '\n\n'.join(f.block for f in self.files)
        return self.reason if self.failed else ''

    @classmethod
    def found(cls, files: list[SiteFile], where: str) -> SiteContext:
        """The eligible files read, in byte order of their names; a blank file carries no rule."""
        files = sorted((f for f in files if f.text.strip()), key=lambda f: f.raw)
        if not files:
            return cls(reason=f'No site rules are served: {CONVENTION} on {where} holds no rules '
                              f'(no non-empty *.md file but {EXCLUDED}).')
        return cls(files=tuple(files))

    @classmethod
    def missing(cls, where: str) -> SiteContext:
        """The directory does not exist: not a failure."""
        return cls(reason=f'No site rules are served: {CONVENTION} does not exist on {where}.')

    @classmethod
    def unreadable(cls, where: str, detail: str) -> SiteContext:
        """The directory or one of its files could not be read; `detail` is shown and cut to `DETAIL_LIMIT` units."""
        return cls(reason=f'No site rules are served: {CONVENTION} on {where} could not be read ({_detail(detail)}).',
                   failed=True)

    @classmethod
    def timed_out(cls, where: str, timeout: float | None = None) -> SiteContext:
        """The read did not finish within `timeout` seconds (`READ_TIMEOUT` by default)."""
        timeout = READ_TIMEOUT if timeout is None else timeout
        return cls(reason=f'No site rules are served: reading {CONVENTION} on {where} did not finish '
                          f'within {timeout:g} s.', failed=True)


class BudgetError(ValueError):
    """The instructions budget cannot hold the base instructions and the site context's smallest form."""

    def __init__(self, budget: int, minimum: int) -> None:
        super().__init__(f'instructions budget {budget} is too small: the base instructions and the site '
                         f'context need {minimum} characters; set --instructions-budget or '
                         f'CLUSTER_MCP_INSTRUCTIONS_BUDGET to at least {minimum}')
        self.budget = budget
        self.minimum = minimum


def _eligible(name: str) -> bool:
    return fnmatch.fnmatchcase(name, '*.md') and name != EXCLUDED


def _decode(data: bytes) -> str:
    """A file's content as text: invalid UTF-8 becomes U+FFFD, trailing whitespace goes."""
    return data.decode('utf-8', 'replace').rstrip()


def _name(name: str) -> str:
    """A directory entry's name as text, by the remote read's rule: U+FFFD, never a lone surrogate."""
    return os.fsencode(name).decode('utf-8', 'replace')


def _breaks(char: str) -> bool:
    code = ord(char)
    return code < 0x20 or 0x7f <= code <= 0x9f or code in (0x2028, 0x2029)


def _escaped(char: str) -> bool:
    return _breaks(char) or char == '\\'


def _escape(char: str) -> str:
    code = ord(char)
    return f'\\x{code:02x}' if code <= 0xff else f'\\u{code:04x}'


def shown(text: str) -> str:
    """`text` as the site context shows a name: each control character (C0, DEL, C1, U+2028, U+2029)
    and the backslash becomes a `\\xNN` or `\\uNNNN` escape, so no name can break a served line, and
    no two texts are shown alike: every backslash shown starts an escape."""
    return ''.join(_escape(c) if _escaped(c) else c for c in text)


def _cut(text: str, limit: int) -> str:
    """`text`, or its longest start that fits `limit` UTF-16 code units with `…` after it."""
    if units(text) <= limit:
        return text
    kept, room = [], limit - units('…')
    for char in text:
        room -= units(char)
        if room < 0:
            break
        kept.append(char)
    return ''.join(kept) + '…'


def _detail(text: str) -> str:
    return _cut(shown(text), DETAIL_LIMIT)


def _why(exc: OSError) -> str:
    return (exc.strerror or type(exc).__name__).lower()


@functools.cache
def _libsystem() -> ctypes.CDLL | None:
    """macOS's libSystem, with acl(3)'s calls typed; None when it or one of them is missing."""
    try:
        lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        lib.acl_get_file.restype, lib.acl_get_file.argtypes = ctypes.c_void_p, [ctypes.c_char_p, ctypes.c_int]
        lib.acl_get_fd_np.restype, lib.acl_get_fd_np.argtypes = ctypes.c_void_p, [ctypes.c_int, ctypes.c_int]
        lib.acl_get_entry.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
        lib.acl_free.argtypes = [ctypes.c_void_p]
    except (OSError, AttributeError):
        return None
    return lib


def _darwin_acl(target: str | int) -> bool:
    """Whether the path or descriptor `target` carries an ACL entry, by libSystem's acl(3).

    Anything that cannot be asked (no libSystem, no such call, an error other than "no ACL") counts
    as an entry, so the read for every account fails closed.
    """
    lib = _libsystem()
    if lib is None:
        return True
    ctypes.set_errno(0)
    if isinstance(target, int):
        acl = lib.acl_get_fd_np(target, ACL_TYPE_EXTENDED)
    else:
        acl = lib.acl_get_file(os.fsencode(target), ACL_TYPE_EXTENDED)
    if not acl:
        return ctypes.get_errno() != errno.ENOENT
    try:
        entry = ctypes.c_void_p()
        return lib.acl_get_entry(acl, ACL_FIRST_ENTRY, ctypes.byref(entry)) == 0
    finally:
        lib.acl_free(acl)


def _acl_attribute(name: str) -> bool:
    return name.startswith(ACL_NAMESPACE) and 'acl' in name[len(ACL_NAMESPACE):]


def _attributes(target: str | int) -> list[str]:
    """The extended attribute names of the path or descriptor `target`.

    A descriptor opened for search only (`O_PATH`) cannot list them itself on every kernel; its
    `/proc/self/fd` entry names that same object and cannot be replaced, so it is listed there.
    """
    try:
        return os.listxattr(target)
    except OSError as exc:
        if exc.errno != errno.EBADF or not isinstance(target, int):
            raise
        return os.listxattr(f'/proc/self/fd/{target}')


def _listed_acl(target: str | int) -> bool:
    """Whether the path or descriptor `target` lists an ACL attribute (Linux).

    A file system without extended attributes holds no ACL. Any other failure to list them is
    raised, so the read for every account is unreadable: it fails closed.
    """
    try:
        return any(_acl_attribute(name) for name in _attributes(target))
    except OSError as exc:
        if exc.errno in (errno.ENOTSUP, errno.EOPNOTSUPP):
            return False
        raise


def _extended(target: str | int) -> bool:
    """Whether the path or descriptor `target` carries an extended ACL entry.

    Linux lists an ACL among the extended attributes (`_listed_acl`); macOS answers through acl(3).
    Where neither can be asked, every path counts as carrying one.
    """
    if sys.platform == 'darwin':
        return _darwin_acl(target)
    if not hasattr(os, 'listxattr'):
        return True
    return _listed_acl(target)


def _everyone_may(target: str | int, need: int) -> bool:
    """Whether every class (owner, group, other) holds the bits `need` on `target`, with no ACL entry."""
    return os.stat(target).st_mode & need == need and not _extended(target)


# How the read for every account opens what it checks. A directory on the way is opened for search
# only where the system can (Linux's `O_PATH`, macOS's `O_SEARCH`), so one every account may search
# but not list is passed as a lookup passes it; the directory reached is opened again from that
# descriptor to be listed. A file is opened without following a link or waiting for a FIFO's writer.
_SEARCH_ONLY: Final = getattr(os, 'O_PATH', 0) or getattr(os, 'O_SEARCH', 0) or os.O_RDONLY
_STEP: Final = _SEARCH_ONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_LISTING: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
_FILE: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC

# The most symlinks one lookup follows, as the kernel allows.
MAX_LINKS: Final = 40


def _link(name: str, directory: int, error: OSError) -> str:
    """The target of the symlink `name` in the directory descriptor `directory`.

    `error` is why `name` did not open as a directory without following it; when `name` is no
    symlink, that error is raised again.
    """
    if error.errno not in (errno.ELOOP, errno.ENOTDIR):
        raise error
    try:
        return os.readlink(name, dir_fd=directory)
    except OSError:
        raise error from None


def _reach(path: str, held: list[int]) -> tuple[int, bool]:
    """A descriptor of the directory `path` names, walked from `/`, and whether every account may reach it.

    Each component is opened relative to the descriptor of the directory it sits in, never through
    a link: a symlink is read there and its target walked from that same descriptor (or from `/`),
    so the checks act on the directories held, and no name is resolved again once the directory
    holding it was checked. Every directory a lookup searches, a `..` step's and a link's included,
    must give every class search with no ACL entry (`_everyone_may`). Every descriptor opened is
    added to `held`, for the caller to close.
    """
    def hold(fd: int) -> int:
        held.append(fd)
        return fd

    root = hold(os.open('/', _SEARCH_ONLY | os.O_DIRECTORY | os.O_CLOEXEC))
    searched: set[int] = set()
    everyone = True
    links = 0

    def search(directory: int) -> None:
        nonlocal everyone
        if directory not in searched:
            searched.add(directory)
            everyone = everyone and _everyone_may(directory, SEARCH)

    def walk(route: list[int], rest: str) -> list[int]:
        nonlocal links
        for part in rest.split('/'):
            if part in ('', '.'):
                continue
            search(route[-1])
            if part == '..':
                route = route[:-1] or route
                continue
            try:
                route = [*route, hold(os.open(part, _STEP, dir_fd=route[-1]))]
            except OSError as exc:
                target = _link(part, route[-1], exc)
                links += 1
                if links > MAX_LINKS:
                    raise OSError(errno.ELOOP, os.strerror(errno.ELOOP), path) from None
                route = walk([root] if target.startswith('/') else route, target)
        return route

    start = path if path.startswith('/') else os.path.join(os.getcwd(), path)
    return walk([root], start)[-1], everyone


def _open_to_everyone(directory: str) -> bool:
    """Whether every account can reach and list `directory`: search on each directory its lookup
    passes, read and search on the directory, and no ACL entry on any of them."""
    held: list[int] = []
    try:
        reached, everyone = _reach(directory, held)
        return everyone and _everyone_may(reached, LIST)
    finally:
        for fd in held:
            os.close(fd)


def _read_for_everyone(where: str, directory: str) -> SiteContext:
    """`read_local(for_others=True)`: what is checked is what is read.

    The directory is reached by descriptor (`_reach`) and listed from that descriptor; each file is
    opened relative to it without following a link, and its descriptor is checked as a regular file
    every account may read before it is read. A swap of a file or of a directory on the route after
    its check changes nothing read; an entry that is no regular file when opened is not read.
    """
    held: list[int] = []
    try:
        try:
            reached, everyone = _reach(directory, held)
            listing = os.open('.', _LISTING, dir_fd=reached)
            held.append(listing)
            entries = list(os.scandir(listing))
            if not (everyone and _everyone_may(listing, LIST)):
                return SiteContext.unreadable(where, NOT_FOR_EVERYONE)
        except FileNotFoundError:
            return SiteContext.missing(where)
        except OSError as exc:
            return SiteContext.unreadable(where, _why(exc))
        files = []
        for entry in entries:
            name = _name(entry.name)
            try:
                if not (_eligible(name) and entry.is_file(follow_symlinks=False)):
                    continue
                try:
                    fd = os.open(entry.name, _FILE, dir_fd=listing)
                except OSError as exc:
                    if exc.errno == errno.ELOOP:
                        continue
                    raise
                with open(fd, 'rb') as stream:
                    if not stat.S_ISREG(os.fstat(fd).st_mode):
                        continue
                    if not _everyone_may(fd, READ):
                        return SiteContext.unreadable(where, f'{name}: {NOT_FOR_EVERYONE}')
                    data = stream.read()
            except OSError as exc:
                return SiteContext.unreadable(where, f'{name}: {_why(exc)}')
            files.append(SiteFile(name, _decode(data), os.fsencode(entry.name)))
        return SiteContext.found(files, where)
    finally:
        for fd in held:
            os.close(fd)


def read_local(where: str = 'this host', directory: str | None = None, *, for_others: bool = False) -> SiteContext:
    """Read the site files on this host, as this process (`directory` defaults to `AGENTS_D`).

    `for_others` is the read of a server that serves accounts other than its own (`delegate` mode):
    every account must be able to reach and list the directory (`_open_to_everyone`) and read each
    file, by its owner, group and other bits with no ACL entry, or the read is unreadable, whatever
    this process itself may read. That read acts on descriptors throughout (`_read_for_everyone`).
    """
    directory = AGENTS_D if directory is None else directory
    if for_others:
        return _read_for_everyone(where, directory)
    try:
        entries = list(os.scandir(directory))
    except FileNotFoundError:
        return SiteContext.missing(where)
    except OSError as exc:
        return SiteContext.unreadable(where, _why(exc))
    files = []
    for entry in entries:
        name = _name(entry.name)
        try:
            # Not followed through a symlink: a link, a directory or a FIFO is not a regular file,
            # and opening a FIFO would wait for a writer.
            if not (_eligible(name) and entry.is_file(follow_symlinks=False)):
                continue
            with open(entry.path, 'rb') as stream:
                data = stream.read()
        except OSError as exc:
            return SiteContext.unreadable(where, f'{name}: {_why(exc)}')
        files.append(SiteFile(name, _decode(data), os.fsencode(entry.name)))
    return SiteContext.found(files, where)


def _word(text: str) -> bytes:
    return base64.b64decode(text.encode('ascii'), validate=True)


def parse_remote(stdout: str, where: str) -> SiteContext:
    """The site context from `READ_SITE`'s answer; anything malformed or short is unreadable.

    Eligibility and order are applied again here, so the answer decides only what was read.
    """
    lines = stdout.splitlines()
    if lines == ['missing']:
        return SiteContext.missing(where)
    if lines == ['unreadable']:
        return SiteContext.unreadable(where, 'permission denied')
    if lines == ['notdir']:
        return SiteContext.unreadable(where, 'not a directory')
    if not lines or not lines[-1].startswith('end '):
        return SiteContext.unreadable(where, 'the answer was incomplete')
    files = []
    try:
        count = int(lines[-1][4:])
        for line in lines[:-1]:
            kind, _, rest = line.partition(' ')
            if kind == 'file':
                encoded_name, _, encoded_body = rest.partition(' ')
                raw = _word(encoded_name)
                name = raw.decode('utf-8', 'replace')
                if _eligible(name):
                    files.append(SiteFile(name, _decode(_word(encoded_body)), raw))
            elif kind == 'unreadable-file':
                name = _word(rest).decode('utf-8', 'replace')
                if _eligible(name):
                    return SiteContext.unreadable(where, f'{name}: permission denied')
            else:
                raise ValueError(line)
    except (ValueError, binascii.Error):
        return SiteContext.unreadable(where, 'the answer was malformed')
    if count != len(lines) - 1:
        return SiteContext.unreadable(where, 'the answer was incomplete')
    return SiteContext.found(files, where)


def read_remote(executor: Executor, where: str = 'the cluster', directory: str | None = None,
                timeout: float | None = None) -> SiteContext:
    """Read the site files through `executor` (the cluster's, in `ssh` mode), waiting `timeout` seconds.

    A timeout is a timed-out read; any other nonzero exit (the command never started, or the
    connection was lost) is an unreadable one.
    """
    directory = AGENTS_D if directory is None else directory
    timeout = READ_TIMEOUT if timeout is None else timeout
    result = executor.run(script_argv(READ_SITE, 'cluster_context', directory), timeout=timeout)
    if result.exit_code == TIMEOUT_EXIT_CODE:
        return SiteContext.timed_out(where, timeout)
    if result.exit_code != 0:
        return SiteContext.unreadable(where, f'the read exited {result.exit_code}')
    return parse_remote(result.stdout, where)


def read_bounded(read: Callable[[], SiteContext], where: str, timeout: float | None = None) -> SiteContext:
    """`read()`, or a timed-out context when it has not returned within `timeout` seconds.

    The read runs on a daemon thread, which is abandoned at the deadline: nothing waits for it, and
    it cannot hold the process open at exit. An exception it raises makes the context unreadable.
    An executor's own timeout is no such bound: over ssh, opening a session can wait past it.
    """
    timeout = READ_TIMEOUT if timeout is None else timeout
    box: queue.Queue[SiteContext] = queue.Queue(maxsize=1)

    def work() -> None:
        try:
            box.put(read())
        except Exception as exc:
            box.put(SiteContext.unreadable(where, type(exc).__name__))

    threading.Thread(target=work, name='cluster-mcp-site-read', daemon=True).start()
    try:
        return box.get(timeout=timeout)
    except queue.Empty:
        return SiteContext.timed_out(where, timeout)


def units(text: str) -> int:
    """`text`'s length in UTF-16 code units, the unit JavaScript clients count (never fewer than code points)."""
    return len(text.encode('utf-16-le', 'surrogatepass')) // 2


def omission_note(names: list[str]) -> str:
    """The line naming every file left out of the instructions, and the tool that returns them."""
    return (f'Left out here for length: {", ".join(shown(n) for n in names)}. '
            f'Call the `cluster_context` tool for the full site context.')


def _head(base: str) -> str:
    return f'{base}\n\n{HEADING}\n\n'


def _render(base: str, included: list[SiteFile], omitted: list[str]) -> str:
    parts = [f.block for f in included]
    if omitted:
        parts.append(omission_note(omitted))
    return _head(base) + '\n\n'.join(parts)


def _reserve(where: str) -> int:
    """The longest one-line reason a read can end in, in units: the room a failed read needs."""
    detail = 'x' * DETAIL_LIMIT
    return max(units(r.reason) for r in (SiteContext.missing(where), SiteContext.found([], where),
                                          SiteContext.unreadable(where, detail), SiteContext.timed_out(where)))


def minimum_budget(base: str, site: SiteContext) -> int:
    """The smallest budget `compose` accepts for `site`.

    Never less than the base and the longest reason a read can end in, so a budget that serves a good
    read also serves a failed one: the server starts whatever the read finds. Without files, also
    the base with this site's own reason, so no path serves more than the budget; with files, also
    the smaller of the whole text and the base with the note naming every file.
    """
    floor = units(_head(base)) + max(_reserve('the cluster'), _reserve('this host'))
    if not site.files:
        return max(floor, units(_head(base) + site.reason))
    names = [f.name for f in site.files]
    return max(floor, min(units(_render(base, list(site.files), [])), units(_render(base, [], names))))


def compose(base: str, site: SiteContext, budget: int = DEFAULT_BUDGET) -> str:
    """The served instructions: `base`, then the site context, within `budget` UTF-16 code units.

    The base is never cut, and files go in whole, in order. When they do not all fit, a file goes in
    if it fits beside the note naming every file not yet in, so the final note, which names fewer,
    fits too; a later file that fits still goes in after one left out. A budget under
    `minimum_budget` raises a `BudgetError` naming the minimum.
    """
    minimum = minimum_budget(base, site)
    if budget < minimum:
        raise BudgetError(budget, minimum)
    if not site.files:
        return _head(base) + site.reason
    whole = _render(base, list(site.files), [])
    if units(whole) <= budget:
        return whole
    # Files are taken by position, never compared: two files can share a decoded name and a text.
    files = site.files
    included: list[SiteFile] = []
    taken: set[int] = set()
    for i, f in enumerate(files):
        trial = [*included, f]
        rest = [g.name for j, g in enumerate(files) if j not in taken and j != i]
        if units(_render(base, trial, rest)) <= budget:
            included.append(f)
            taken.add(i)
    omitted = [f.name for i, f in enumerate(files) if i not in taken]
    return _render(base, included, omitted)


# The site context of each server built, keyed by the server object itself: set once at construction,
# read by that server's tool and resource, never per user and never by hostname.
_SITES: WeakKeyDictionary[object, SiteContext] = WeakKeyDictionary()


def register(server: object, site: SiteContext) -> None:
    """Hold `site` as `server`'s site context, for as long as the server lives."""
    _SITES[server] = site


def site_of(server: object) -> SiteContext:
    """The site context `server` was built with."""
    return _SITES[server]
