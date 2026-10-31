# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F2 (review 1): every tool's annotations, each hint's presence and value, are 0.1.4's.

`uv run python spec/rename-to-cluster-mcp/remediation/F2-tool-annotations-pinned.py`, from the tree
root.

The property: the served surface of every tool, its annotations included, equals 0.1.4's, which
served none. `harness.served_surface` records a tool's annotations when the server sends any, each
hint it sent with its value and no other, so a tool served without them keeps the fixture's shape
and the fixture needs no change. `test_surface.py`'s `surface_violations` fails on any difference:
annotations on one side only (a key missing on one side), a hint on one side only, or a hint's
value. The pins: `test_served_surface_matches_baseline`, the fixture's shape test (no tool entry has
an `annotations` key), and the comparison's drift controls, the annotation rows included
(`test_surface_check_catches_annotation_drift`), in both eras.

The sweep: every case whose anchor sits on a `Tool.from_function` call anywhere in the namespace
(where a tool's annotations are set), plus every case planted into the served-surface fixture, found
by evaluating where each anchor sits; each in both eras. 0.1.4 served no annotations, so a hint can
be dropped or changed only against a fixture planted to record some: those cases plant the product
and the fixture together. The reviewer's plant (`readOnlyHint` and `destructiveHint` on every tool
through the decorator) is `annotations-on-every-tool`'s shape. About 1 min, under 1 GB, one process
tree at a time.
"""

from __future__ import annotations

import sys

from sweep import calls_to, cases_in, finish, regions, run_sweep, run_tests

S = 'tests/test_surface.py'
TESTS = [S]
COUNT = 1 + 1 + 13 + 9 + 4

REQUIRED = ['annotations-on-every-tool', 'empty-annotations-on-every-tool', 'annotations-on-one-tool',
            'annotations-removed', 'annotation-hint-flipped', 'annotation-hint-dropped', 'annotation-hint-added']

EQUIVALENT = {
    'annotations-none-passed': '`annotations=None` passed to Tool.from_function: its default, so nothing is served',
    'hint-order-changed': "a tool's hints given in another order: JSON objects are unordered, and the comparison "
                          'reads them as mappings',
}


def main() -> int:
    run_tests(TESTS, COUNT)
    cases = cases_in(regions(calls_to('from_function')), ('tests/fixtures/served_surface.json',))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('F2 tool annotations pinned', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
