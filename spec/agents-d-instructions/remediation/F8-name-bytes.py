# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F8 (review 2): a file is identified and ordered by its raw name bytes, never by its decoded or shown form.

`uv run python spec/agents-d-instructions/remediation/F8-name-bytes.py`, from the tree root.

- Library, by an oracle of its own (the sorted bytes; a count of headers and named files): sets of
  two and three names that differ only in invalid UTF-8 bytes, so each set decodes to one name,
  each file holding the same text, parsed from `READ_SITE`'s answer in every listing order: as many
  files as names, in the byte order of the names, the same context whatever the order; and at every
  budget from the minimum to the whole text, each file is served or named, within the budget. On
  Linux the same names are planted and read by `read_local`; on macOS the file system's refusal of
  such a name is asserted instead.
- `shown` is injective: every string of up to three characters over an alphabet of a backslash, the
  escape letters and digits, and control characters is shown differently from every other, and
  reads back as itself through an independent decoder.
- CLI: the real server (`-e local`, stdio, both eras) on a directory holding a name with a line
  break and the name spelled with its escape (`a\\x0a.md`): two headers, shown differently.
- The class's mutants: `site-names-by-text`, `site-omitted-by-name`, `site-backslash-unescaped`,
  `site-byte-order`.

Footprint: one Python process, one server at a time, the mutation children; about 1 min, under
300 MB.
"""

from __future__ import annotations

import base64
import itertools
import os
import re
import sys
import tempfile
from pathlib import Path

from common import breaks, check, finish, mutants, plant, site

import serve_gate as gate  # noqa: E402

SETS = [[b'a\xff.md', b'a\xfe.md'], [b'\x80.md', b'\xc0.md', b'\xff.md'], [b'r\xed\xa0\x80.md', b'r\xed\xbf\xbf.md']]
TEXT = ' '.join(['Same rule.'] * 30)


def answer(order: list[bytes]) -> str:
    body = base64.b64encode(f'{TEXT}\n'.encode()).decode()
    return '\n'.join([*(f'file {base64.b64encode(raw).decode()} {body}' for raw in order), f'end {len(order)}']) + '\n'


def held(context: site.SiteContext, names: list[bytes], label: str) -> None:
    check([f.raw for f in context.files] == sorted(names), f'{label}: read as {[f.raw for f in context.files]}')
    shown = {f.name for f in context.files}
    check(len(shown) == 1, f'{label}: the names were meant to decode alike, got {shown}')
    whole = site.units(site.compose('Base.', context, 100_000))
    for budget in range(site.minimum_budget('Base.', context), whole + 1):
        text = site.compose('Base.', context, budget)
        section = text.split(f'{site.HEADING}\n\n', 1)[1]
        served = len(re.findall(r'^<!-- Source: ', section, re.M))
        notes = [line for line in section.splitlines() if line.startswith('Left out here for length: ')]
        named = sum(len(line[len('Left out here for length: '):].split('. Call')[0].split(', ')) for line in notes)
        check(site.units(text) <= budget, f'{label} at {budget}: over the budget')
        check(served + named == len(names), f'{label} at {budget}: {served} served and {named} named of {len(names)}')


def library(tmp: Path) -> None:
    for n, names in enumerate(SETS):
        contexts = [site.parse_remote(answer(list(order)), 'this host') for order in itertools.permutations(names)]
        check(all(c == contexts[0] for c in contexts), f'set {n}: the listing order changed the read')
        held(contexts[0], names, f'set {n} remote')
        root = tmp / f'set-{n}'
        root.mkdir()
        try:
            for raw in names:
                Path(os.fsdecode(bytes(root) + b'/' + raw)).write_text(f'{TEXT}\n')
        except OSError:
            check(not sys.platform.startswith('linux'), f'set {n}: Linux refused a name that is not UTF-8')
            check(list(root.iterdir()) == [], f'set {n}: a refused name left a file')
            continue
        local = site.read_local('this host', str(root))
        held(local, names, f'set {n} local')
        check(local == contexts[0], f'set {n}: the local read differs from the remote parse')


def decode(text: str) -> str:
    return re.sub(r'\\x([0-9a-f]{2})|\\u([0-9a-f]{4})', lambda m: chr(int(m.group(1) or m.group(2), 16)), text)


def injective() -> None:
    alphabet = ['\\', 'x', 'u', '0', 'a', '5', 'c', '\n', '\x85', ' ', '\x7f']
    strings = [''.join(p) for k in range(4) for p in itertools.product(alphabet, repeat=k)]
    shown = {s: site.shown(s) for s in strings}
    check(len(set(shown.values())) == len(strings), f'shown: {len(strings) - len(set(shown.values()))} collisions')
    check(all(decode(v) == k for k, v in shown.items()), 'shown: a name does not read back as itself')
    check(not any(breaks(c) for v in shown.values() for c in v), 'shown: a control character survived')


def cli(tmp: Path) -> None:
    root = plant(tmp / 'cli', {'a\n.md': 'Line break.\n', 'a\\x0a.md': 'Spelled escape.\n'})

    async def steps(client) -> tuple[str, str]:
        result = await client.call_tool('cluster_context', {})
        return client.instructions or '', ''.join(getattr(p, 'text', '') for p in result.content)

    for era in gate.ERAS:
        instructions, tool = gate.stdio_session(gate.Server(root, tmp / f'log-{era}', ['-e', 'local', '-t', 'stdio']),
                                                era, steps)
        for text, label in ((instructions, 'instructions'), (tool, 'tool')):
            headers = re.findall(r'^<!-- Source: (.*) -->$', text, re.M)
            check(sorted(headers) == ['a\\x0a.md', 'a\\x5cx0a.md'], f'cli {era} {label}: headers {headers}')
    check(gate.FAILURES == [], f'serve helpers: {gate.FAILURES}')


def main() -> int:
    injective()
    with tempfile.TemporaryDirectory(prefix='f8-') as name:
        library(Path(name))
        cli(Path(name))
    mutants('site-names-by-text', 'site-omitted-by-name', 'site-backslash-unescaped', 'site-byte-order')
    return finish('F8 name bytes')


if __name__ == '__main__':
    sys.exit(main())
