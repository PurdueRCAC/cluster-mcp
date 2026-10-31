# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F1 (review 1): the deprecation window is one string, the published one, wherever a user reads it.

`uv run python spec/rename-to-cluster-mcp/remediation/F1-deprecation-window-pinned.py`, from the
tree root.

The property: the window is "deprecated in 0.2.0, removed no earlier than 0.4.0", and every place a
user reads it says exactly that: the `WINDOW` constant, every warning that names it (the `rcac-mcp`
command, each legacy variable honoured, each legacy twin ignored), and README § Upgrading from
rcac-mcp, which exists once and pairs each of the three deprecations with its replacement. Every pin
compares with the window written out (`harness.DEPRECATION_WINDOW`), never with the constant:
`test_deprecation_window.py` (the constant, the README section, and the section check's drift
controls), `test_env.py::test_warning_names_replacement_and_window` (each variable, each shape, the
window captured from the message and compared), and `test_cli.py`'s legacy-command drives and their
drift controls (`legacy_violations`, `stdio_violations`).

The sweep: every case whose anchor sits in the window's assignment, in `legacy_warning` or
`ignored_warning`, or on a call of either anywhere in the namespace, plus every case planted into
`README.md`, found by evaluating where each anchor sits; each in both eras. The reviewer's plants
(the window altered, the README section deleted) are among them. About 3 min, under 1 GB, one
process tree at a time.
"""

from __future__ import annotations

import sys

from sweep import assigns, calls_to, cases_in, finish, regions, run_sweep, run_tests

D = 'tests/test_deprecation_window.py'
E = 'tests/test_env.py::'
C = 'tests/test_cli.py::'
TESTS = [D, f'{E}test_warning_names_replacement_and_window', f'{C}test_legacy_command_warns_then_runs_cluster_mcp',
         f'{C}test_legacy_check_catches_drift', f'{C}test_legacy_command_keeps_stdout_clean_on_stdio',
         f'{C}test_stdio_check_catches_a_stray_line']
COUNT = (1 + 1 + 11) + 6 + 4 + 6 + 1 + 1

REQUIRED = ['deprecation-window-altered', 'legacy-warning-omits-window', 'ignored-warning-omits-window',
            'legacy-command-own-window', 'env-legacy-own-warning', 'env-ignored-own-warning',
            'readme-window-altered', 'readme-upgrading-deleted', 'readme-command-row-dropped',
            'readme-variables-row-dropped', 'readme-resources-row-dropped', 'readme-replacement-dropped',
            'readme-replacements-swapped']

EQUIVALENT = {
    'readme-window-rewrapped': 'the README window broken across lines at any space: Markdown renders a line break '
                               'inside a paragraph as a space, so a reader sees the same window; the check '
                               'compares whitespace-normalised text',
    'readme-rows-reordered': "the upgrade table's rows in another order: each deprecation still names its "
                             'replacement, and nothing reads the order',
    'window-constant-concatenated': "WINDOW written as 'deprecated in 0.2.0, ' + 'removed no earlier than 0.4.0': "
                                    'the same string',
}


def main() -> int:
    run_tests(TESTS, COUNT)
    spans = regions(assigns('WINDOW')) + regions(calls_to('legacy_warning', 'ignored_warning'))
    cases = cases_in(spans, ('README.md',))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('F1 deprecation window pinned', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
