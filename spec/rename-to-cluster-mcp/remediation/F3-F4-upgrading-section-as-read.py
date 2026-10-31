# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F3 and F4 (review 2): README § Upgrading from rcac-mcp, as a reader sees it, and the command's warning, whole.

`uv run python spec/rename-to-cluster-mcp/remediation/F3-F4-upgrading-section-as-read.py`, from the
tree root.

The property, completing F1's: the section a reader sees (HTML comments removed, an unclosed one
hiding the rest) maps each deprecated name to exactly one replacement, whatever the order of its
rows, and names no other; every version it names (`\\d+(?:\\.\\d+)+\\S*`, trailing punctuation
dropped, a superset of the routing's three-part literal) is `0.2.0` or `0.4.0`; and it states the
window as the whole published phrase, bounded at tokens. The `rcac-mcp` command's warning is a
whole stderr line, the padded level and the logger's name and then the message, matched from the
line's start. The pins: `test_deprecation_window.py` (`upgrading_violations`, its drift controls
and the controls a reader reads the same), `test_cli.py`'s legacy drives and their drift controls
(`legacy_violations`, `stdio_violations`), and `test_env.py`'s warnings, in both eras.

This checker supersedes `F1-deprecation-window-pinned.py`, which stays as the record: its pin count
(31) no longer holds once these pins add drift controls to the files it counts. It runs F1's pins
at their new count and sweeps F1's domain, which holds F3's and F4's: every case whose anchor sits
in the window's assignment, in `legacy_warning` or `ignored_warning` or on a call of either
anywhere in the namespace (the command's warning is one), plus every case planted into `README.md`,
each in both eras. F1's required cases and recorded equivalents carry over, read from F1's checker.
About 4 min, under 1 GB, one process tree at a time.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

from sweep import assigns, calls_to, cases_in, finish, regions, run_sweep, run_tests

F1 = runpy.run_path(str(Path(__file__).with_name('F1-deprecation-window-pinned.py')))

D = 'tests/test_deprecation_window.py'
E = 'tests/test_env.py::'
C = 'tests/test_cli.py::'
TESTS = F1['TESTS']
# test_deprecation_window.py: the constant, the README, 26 drift controls, 4 read-the-same controls;
# the six variable warnings; the four legacy drives; nine legacy drift controls; stdio and its control.
COUNT = (1 + 1 + 26 + 4) + 6 + 4 + 9 + 1 + 1

REQUIRED = [*F1['REQUIRED'],
            'readme-contradicting-row-before', 'readme-contradicting-row-after', 'readme-row-repeated',
            'readme-removed-in-other-words', 'readme-kept-until-other-version', 'readme-window-suffixed',
            'readme-window-extra-component', 'readme-window-parenthetical', 'readme-upgrading-commented',
            'legacy-command-prefixed-warning']

EQUIVALENT = {
    **F1['EQUIVALENT'],
    'readme-contradiction-in-a-comment': 'a contradicting window inside an HTML comment: Markdown does not render it, '
                                         'so a reader sees the section unchanged',
    'readme-window-ends-a-sentence': "the window's last version followed by a full stop and a new sentence: the "
                                     'punctuation ends the sentence, not the version',
    'command-warning-level-unpadded': "the level in the command's warning padded to another width: the line still "
                                      'holds only the level and the logger before the message',
}


def main() -> int:
    run_tests(TESTS, COUNT)
    spans = regions(assigns('WINDOW')) + regions(calls_to('legacy_warning', 'ignored_warning'))
    cases = cases_in(spans, ('README.md',))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('F3-F4 upgrading section as read', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
