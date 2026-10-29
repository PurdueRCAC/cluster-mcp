# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""L1 (review 3): the delegate read hook refuses every URI near an open one, not only the named shapes.

`uv run python spec/resource-reads-without-executor/remediation/L1-read-hook-refuses-near-open-uris.py`,
from the tree root.

The property is F2's and G1's, over a domain no finite table reaches: in `delegate` mode, for every URI
not exactly in `OPEN_RESOURCES`, a refused caller gets exactly its tool call's reason, as -32603, and
nothing runs. G1 pinned it over `NOT_OPEN`, 21 named shapes; ten URI normalisers planted in the
membership test (CR/LF stripped, a trailing `?`/`#` stripped, a port dropped, userinfo dropped, a
trailing dot stripped, tab and newline removed anywhere, a leading slash stripped, quotes and angle
brackets stripped, a trailing NUL stripped, a `/.` segment dropped), their disjunction, and an open set
that also holds each open URI with `?` appended each change only shapes outside the table, and each
passed the suite in both eras.

The pin is now generated (`tests/test_storage_resource.py`, `NEAR_OPEN`): for every served URI, the
open ones and those that run commands, every one-character insertion, deletion and substitution over
printable ASCII and NUL, tab, newline, vertical tab, form feed, carriage return and DEL, at every
position, plus wrappers (`<>`, quotes, brackets, surrounding whitespace, NUL), suffixes (`?`, `#`, `?#`,
`:`, `:80`, `.`, `/.`, `/./`, `/`, `//`, CRLF) and userinfo (`@`, `u@`, `u:p@`), leaving out exactly the
open URIs: 5,712 shapes today. `test_near_open_read_is_refused[no-claims|unmapped]` reads every shape
verbatim (`harness.read_verbatim`) on one session in the selected era, 128 in flight at a time, and
requires the exact refusal and no launch for each; `test_near_open_shapes_cover_every_served_uri` pins
what the generated set must hold. The other side keeps G1's table pins: a mapped and a tokenless caller
and every shared-mode caller get -32602 for every `NOT_OPEN` shape, and `rcac://context` answers every
client. The pinning tests run under `CLUSTER_MCP_TEST_ERA` unset and `modern`, so the generated rows run
once in each era.

The sweep is G1's, evaluated afresh: every case whose edit replaces the read hook's membership test,
plus every case editing the derivation of `OPEN_RESOURCES`, found by evaluating each case's edits
(`sweep.cases_editing`), each under both eras. Each URI-shape case's failure fragment names a shape it
lets through, so a kill by an anchor check or an unrelated failure does not count. The twelve cases
this finding adds, as `tests/mutants.py` names them (the reviewer's names in brackets):
`read-hook-strips-crlf` [strip-crlf], `read-hook-strips-trailing-query-or-fragment-mark`
[rstrip-qmark-hash], `read-hook-drops-port` [drop-port], `read-hook-drops-userinfo` [drop-userinfo],
`read-hook-strips-trailing-dot` [rstrip-dot], `read-hook-removes-tab-and-newline`
[whatwg-tabnl-removed], `read-hook-strips-leading-slash` [lstrip-slash],
`read-hook-strips-quotes-and-brackets` [strip-quotes-brackets], `read-hook-strips-trailing-nul`
[rstrip-nul], `read-hook-drops-dot-segment` [dot-segment], `read-hook-any-normaliser`
[composite-survivors], `open-set-holds-query-variants` [r-open-plus-query]. Seen red first: planted
against G1's table rows, every one of the twelve survives in both eras; with `NEAR_OPEN` cut back to the
`NOT_OPEN` shapes, every one survives this checker's sweep. This checker supersedes none: G1's stays as
the record of the table, and still passes. About 6 min, under 1 GB, one process tree at a time.
"""

from __future__ import annotations

import sys

from sweep import cases_editing, finish, run_sweep, run_tests

S = 'tests/test_storage_resource.py::'
C = 'tests/test_context.py::'
TESTS = [f'{S}test_near_open_shapes_cover_every_served_uri', f'{S}test_near_open_read_is_refused',
         f'{S}test_not_open_shapes_are_neither_open_nor_served', f'{S}test_unknown_uri_read_is_refused',
         f'{S}test_unknown_uri_is_not_found_in_delegate_mode', f'{S}test_unknown_uri_is_not_found',
         f'{C}test_any_client_reads_the_context_in_delegate_mode']
COUNT = 1 + 2 + 1 + 8 + 4 + 2 + 8

# The read hook's membership test, and the line OPEN_RESOURCES is derived by.
MEMBERSHIP = '        if context.message.uri not in OPEN_RESOURCES:\n'
DERIVATION = "    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])"

ADDED = ['read-hook-strips-crlf', 'read-hook-strips-trailing-query-or-fragment-mark', 'read-hook-drops-port',
         'read-hook-drops-userinfo', 'read-hook-strips-trailing-dot', 'read-hook-removes-tab-and-newline',
         'read-hook-strips-leading-slash', 'read-hook-strips-quotes-and-brackets', 'read-hook-strips-trailing-nul',
         'read-hook-drops-dot-segment', 'read-hook-any-normaliser', 'open-set-holds-query-variants']

# G1's required cases: the table's shapes, the other side, and the open set itself.
CARRIED = ['read-hook-open-by-prefix', 'read-hook-rcac-scheme-only', 'read-hook-open-by-suffix',
           'read-hook-open-by-substring', 'read-hook-open-within-open-uri', 'read-hook-open-if-prefix-of-open',
           'read-hook-open-by-host', 'read-hook-case-folded', 'read-hook-casefolded', 'read-hook-scheme-case-folded',
           'read-hook-strips-trailing-slash', 'read-hook-strips-space', 'read-hook-strips-leading-space',
           'read-hook-drops-query-and-fragment', 'read-hook-authority-only', 'read-hook-ignores-scheme',
           'read-hook-defaults-scheme', 'read-hook-adds-authority-slashes', 'read-hook-unquotes',
           'read-hook-nfkc-normalised', 'open-set-holds-slash-variants', 'read-hook-refuses-unserved',
           'read-hook-resolves-storage-only', 'read-hook-ignores-open-set', 'read-hook-open-set-inverted',
           'context-read-closed']

# Carried from G1 unchanged: neither is a normaliser, and no shape tells either from the shipped test.
EQUIVALENT = {
    'read-hook-open-by-equality': "`context.message.uri != 'rcac://context'`: the same exact-string test while "
                                  'OPEN_RESOURCES holds one URI; what the set holds is pinned by context-read-closed, '
                                  'storage-read-left-open, open-set-holds-slash-variants and open-set-holds-query-variants',
    'read-hook-open-in-list': '`context.message.uri not in list(OPEN_RESOURCES)`: membership in a list is the same '
                              "exact-string equality as in the frozenset (likewise `not any(u == o ...)`)",
}


def main() -> int:
    run_tests(TESTS, COUNT)
    cases = list(dict.fromkeys(cases_editing(MEMBERSHIP) + cases_editing(DERIVATION, 'resources.py')))
    run_sweep(cases, ADDED + CARRIED, EQUIVALENT)
    return finish('L1 read hook refuses every URI near an open one', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
