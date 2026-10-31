# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F5 (review 2): every tool's top-level title is 0.1.4's.

`uv run python spec/rename-to-cluster-mcp/remediation/F5-tool-title-pinned.py`, from the tree root.

The property, completing F2's: the served surface of every tool, its title included, equals
0.1.4's. FastMCP 4, which 0.1.4 ran on, serves every tool that sets no title one derived from its
name ("Run Command"), so a title is served for every tool: `harness.served_surface` records it
whenever one is served, and `test_surface.py`'s comparison accepts, where the snapshot has none,
only the derived title (`TOLERATED['derived-title']`, the derivation written out). A title gained
other than that one, a title the snapshot has lost or changed, or a tool served with no title at all
fails. The fixture does not change. The pins: `test_served_surface_matches_baseline`, the fixture's
shape test, the comparison's drift controls (annotations and titles) and tolerated differences, in
both eras.

This checker supersedes `F2-tool-annotations-pinned.py`, which stays as the record: its pin count
(28) no longer holds once these pins add title rows to the file it counts. It runs F2's pins at
their new count and sweeps F2's domain widened by the server's registration: every case whose
anchor sits on a `Tool.from_function` or `add_tool` call anywhere in the namespace (where a tool's
annotations or title are set), plus every case planted into the served-surface fixture, each in
both eras. F2's required cases and recorded equivalents carry over, read from F2's checker. About
1 min, under 1 GB, one process tree at a time.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

from sweep import calls_to, cases_in, finish, regions, run_sweep, run_tests

F2 = runpy.run_path(str(Path(__file__).with_name('F2-tool-annotations-pinned.py')))

TESTS = F2['TESTS']
# The baseline, the shape, 13 surface drift controls, 9 annotation and 7 title drift controls,
# 6 tolerated differences.
COUNT = 1 + 1 + 13 + 9 + 7 + 6

REQUIRED = [*F2['REQUIRED'], 'title-on-one-tool', 'title-on-every-tool', 'title-at-add-tool']

EQUIVALENT = {
    **F2['EQUIVALENT'],
    'title-set-to-the-derived-one': "`title='Run Command'` on run_command: FastMCP 4 serves that title for it already, "
                                    'so the bytes served are unchanged',
    'title-none-passed': '`title=None` passed to Tool.from_function: its default, so the derived title is served',
}


def main() -> int:
    run_tests(TESTS, COUNT)
    cases = cases_in(regions(calls_to('from_function', 'add_tool')), ('tests/fixtures/served_surface.json',))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('F5 tool title pinned', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
