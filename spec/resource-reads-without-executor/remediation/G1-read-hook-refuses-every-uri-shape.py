# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""G1 (review 2): the delegate read hook refuses by default over the whole URI domain, not one URI.

`uv run python spec/resource-reads-without-executor/remediation/G1-read-hook-refuses-every-uri-shape.py`,
from the tree root.

The property, F2's over its whole domain: in `delegate` mode, for every URI not exactly in
`OPEN_RESOURCES`, a refused caller (no identity claim, all claims empty, unmapped, first claim
unmapped) gets exactly its tool call's reason, as -32603; exactly the open URIs skip identity. The
membership test is the exact string the client sent, which is also the string FastMCP looks up: the
server normalises nothing (probed in both eras, 2026-10-28), while FastMCP's own client lowercases the
scheme and strips surrounding space before sending, so the pins send each URI verbatim
(`harness.read_verbatim`). Pinned in `tests/test_storage_resource.py` over `NOT_OPEN`, 21 shapes: a
path below the open URI, a URI it prefixes, a prefix of it, a URI ending in it, a trailing slash, host
and scheme case variants, a percent-encoded and a full-width letter, a leading and a trailing space, a
query, a fragment, no authority slashes, no scheme, three variants of `rcac://storage`, a `file:` URI,
an `https:` URL, and `rcac://nope`. Both sides, both eras: every refused row gets the refusal for every
shape (`test_unknown_uri_read_is_refused`); a mapped and a tokenless caller
(`test_unknown_uri_is_not_found_in_delegate_mode`) and every shared-mode caller
(`test_unknown_uri_is_not_found`) get -32602 `Resource not found` for every shape; `rcac://context`
answers every client (`test_any_client_reads_the_context_in_delegate_mode`); and the table holds no
served or open URI (`test_not_open_shapes_are_neither_open_nor_served`).

The sweep: every case whose edit replaces the read hook's membership test, plus every case editing
the derivation of `OPEN_RESOURCES`, found by evaluating each case's edits, each in both eras. Among
them the reviewer's two survivors, planted as the reviewer wrote them: `read-hook-open-by-prefix`
(`not uri.startswith(tuple(OPEN_RESOURCES))`) and `read-hook-rcac-scheme-only`
(`uri.startswith('rcac://') and uri not in OPEN_RESOURCES`). Each URI-shape case's failure fragment
names the shape that kills it, so a kill by an anchor check or an unrelated failure does not count.
About 3 min, under 1 GB, one process tree at a time.
"""

from __future__ import annotations

import sys

from sweep import cases_editing, finish, run_sweep, run_tests

S = 'tests/test_storage_resource.py::'
C = 'tests/test_context.py::'
TESTS = [f'{S}test_not_open_shapes_are_neither_open_nor_served', f'{S}test_unknown_uri_read_is_refused',
         f'{S}test_unknown_uri_is_not_found_in_delegate_mode', f'{S}test_unknown_uri_is_not_found',
         f'{C}test_any_client_reads_the_context_in_delegate_mode']
COUNT = 1 + 8 + 4 + 2 + 8

# The read hook's membership test, and the line OPEN_RESOURCES is derived by.
MEMBERSHIP = '        if context.message.uri not in OPEN_RESOURCES:\n'
DERIVATION = "    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])"

REQUIRED = ['read-hook-open-by-prefix', 'read-hook-rcac-scheme-only', 'read-hook-open-by-suffix',
            'read-hook-open-by-substring', 'read-hook-open-within-open-uri', 'read-hook-open-if-prefix-of-open',
            'read-hook-open-by-host', 'read-hook-case-folded', 'read-hook-casefolded', 'read-hook-scheme-case-folded',
            'read-hook-strips-trailing-slash', 'read-hook-strips-space', 'read-hook-strips-leading-space',
            'read-hook-drops-query-and-fragment', 'read-hook-authority-only', 'read-hook-ignores-scheme',
            'read-hook-defaults-scheme', 'read-hook-adds-authority-slashes', 'read-hook-unquotes',
            'read-hook-nfkc-normalised', 'open-set-holds-slash-variants', 'read-hook-refuses-unserved',
            'read-hook-resolves-storage-only', 'read-hook-ignores-open-set', 'read-hook-open-set-inverted',
            'context-read-closed']

EQUIVALENT = {
    'read-hook-open-by-equality': "`context.message.uri != 'rcac://context'`: the same exact-string test while "
                                  'OPEN_RESOURCES holds one URI; what the set holds is pinned by context-read-closed, '
                                  'storage-read-left-open and open-set-holds-slash-variants',
    'read-hook-open-in-list': '`context.message.uri not in list(OPEN_RESOURCES)`: membership in a list is the same '
                              "exact-string equality as in the frozenset (likewise `not any(u == o ...)`)",
}


def main() -> int:
    run_tests(TESTS, COUNT)
    cases = list(dict.fromkeys(cases_editing(MEMBERSHIP) + cases_editing(DERIVATION, 'resources.py')))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('G1 read hook refuses every URI shape', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
