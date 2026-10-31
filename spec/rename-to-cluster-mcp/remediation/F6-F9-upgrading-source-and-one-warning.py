# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F6 to F9 (review 3): README § Upgrading from rcac-mcp read from its source, and one command warning.

`uv run python spec/rename-to-cluster-mcp/remediation/F6-F9-upgrading-source-and-one-warning.py`,
from the tree root.

The property, completing F3's and F4's: every `|` line of the section is the table's header, its
delimiter, or a two-cell row of code spans (F6); with markup removed (tags, entities, escapes, `*`),
each `RCAC_*` variable and `rcac://` URI is named once in the section (F6); the section holds no
`<!--` or `-->` (F7), and no comment elsewhere hides its heading; versions are read with `_` emphasis
removed as well, each one `0.2.0` or `0.4.0`, and outside the window only one `0.2.0` (F8). On the
serving path and in the four legacy drives, exactly one stderr line names `rcac-mcp`, and it is the
whole deprecation warning (F9). Accepted residuals, recorded below and not run: a contradiction
naming no version, one outside the section, and a bullet or sentence pairing `rcac-mcp` with another
name (the section names the old project by it, so it is not counted).

The pins are counted by name, never by a file's pass total: each named test below (`NAMED`) must be
reported passed, in both eras, and nothing the run collects may fail or skip. Tests added later to
the same files change nothing here.

This checker supersedes `F3-F4-upgrading-section-as-read.py`, which stays as the record: it pins
53 passes over whole files, and these pins add drift controls to those files. It runs F3-F4's pins
(read from it) and sweeps its domain, which holds F6's to F9's: every case whose anchor sits in the
window's assignment, in `legacy_warning` or `ignored_warning` or on a call of either anywhere in the
namespace (the command's warning is one), plus every case planted into `README.md`, each in both
eras. F3-F4's required cases carry over; of its equivalents, `readme-contradiction-in-a-comment` is
now a case, killed (a comment in the section fails, F7). About 5 min, under 1 GB, one process tree
at a time.
"""

from __future__ import annotations

import runpy
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from sweep import ERAS, ROOT, assigns, calls_to, cases_in, check, env_for, finish, regions, run_sweep

F3F4 = runpy.run_path(str(Path(__file__).with_name('F3-F4-upgrading-section-as-read.py')))

D = 'tests/test_deprecation_window.py::'
E = 'tests/test_env.py::'
C = 'tests/test_cli.py::'
TESTS = F3F4['TESTS']

# Every drift control of the section check; each runs on the README and on the README ending in an
# unclosed comment.
DRIFT = ['window-altered', 'window-altered-across-lines', 'second-window', 'section-deleted', 'section-renamed',
         'section-twice', 'command-row-dropped', 'variables-row-dropped', 'resources-row-dropped',
         'replacement-dropped', 'replacement-changed', 'contradicting-row-before', 'contradicting-row-after',
         'row-repeated', 'row-added',
         *(f'{form}-row-{where}' for form in ('plain', 'bold', 'escaped', 'html-code', 'three-cells', 'no-leading-pipe')
           for where in ('before', 'after')),
         'bullet-mapping', 'prose-mapping', 'bold-mapping', 'second-window-removed-in', 'second-window-until',
         'second-window-two-components', 'version-escaped-dots', 'version-entity-dots', 'version-bold-component',
         'version-underscore-component', 'version-tagged-component', 'removed-in-the-rename',
         'removed-at-the-window-end', 'window-suffixed', 'window-suffixed-unbounded', 'window-extra-component',
         'window-parenthetical', 'window-run-on-before', 'section-commented', 'section-commented-unclosed',
         'row-commented', 'hidden-comment', 'comment-code-spans', 'comment-fenced', 'comment-across-paragraphs']
READ_SAME = ['rows-reordered', 'window-ends-a-sentence', 'window-rewrapped', 'window-emphasised',
             'comment-before-the-section', 'unclosed-comment-at-the-end']
LEGACY_DRIFT = ['silent', 'exit-swallowed', 'stdout', 'no-window', 'other-window', 'twice', 'prefixed',
                'before-the-level', 'suffixed', 'second-warning', 'second-line-naming-the-command']
VARIABLES = ('CLUSTER_MCP_SSH_HOST', 'CLUSTER_MCP_USER_MAP', 'CLUSTER_MCP_INSTRUCTIONS_BUDGET')

NAMED = [f'{D}test_window_is_the_published_one', f'{D}test_readme_states_each_deprecation_and_the_window',
         *(f'{D}test_upgrading_check_catches_drift[{row}-{tail}]' for row in DRIFT
           for tail in ('readme', 'readme-unclosed-comment-at-the-end')),
         *(f'{D}test_upgrading_check_reads_as_a_reader_does[{row}]' for row in READ_SAME),
         *(f'{E}test_warning_names_replacement_and_window[{name}-{shape}]' for name in VARIABLES
           for shape in ('honoured', 'ignored')),
         *(f'{C}test_legacy_command_warns_then_runs_cluster_mcp[{argv}]' for argv in ('none', 'help', 'version', 'bogus')),
         *(f'{C}test_legacy_check_catches_drift[{row}]' for row in LEGACY_DRIFT),
         f'{C}test_legacy_command_keeps_stdout_clean_on_stdio', f'{C}test_stdio_check_catches_a_stray_line']

# A test that must no longer exist: the comment control flipped from reading the same to drift (F7).
RETIRED = [f'{D}test_upgrading_check_reads_as_a_reader_does[hidden-comment]']

NEW_CASES = [*(f'readme-{form}-row-{where}' for form in ('plain', 'bold', 'escaped', 'html-code', 'three-cells',
                                                          'no-leading-pipe') for where in ('before', 'after')),
             'readme-bullet-mapping', 'readme-prose-mapping', 'readme-comment-in-code-spans', 'readme-comment-fenced',
             'readme-comment-across-paragraphs', 'readme-version-escaped-dots', 'readme-version-entity-dots',
             'readme-version-bold-component', 'readme-removed-in-the-rename', 'readme-contradiction-in-a-comment',
             'legacy-command-second-warning-when-serving']
REQUIRED = [*F3F4['REQUIRED'], *NEW_CASES]

EQUIVALENT = {case: why for case, why in F3F4['EQUIVALENT'].items() if case != 'readme-contradiction-in-a-comment'}

RESIDUAL = {
    'readme-contradiction-without-a-version': '"removed in the next minor release": no version literal to read; '
                                              'accepted at the review bound (2026-10-30)',
    'readme-contradiction-outside-the-section': 'a second window outside the section in other words than the '
                                                "window's: the version checks read the section only; accepted at "
                                                'the review bound (2026-10-30)',
    'readme-command-mapped-in-prose': 'a bullet or sentence pairing `rcac-mcp` with another name: the section names '
                                      'the old project by it four times, so it is not counted',
}


def node_id(case: ET.Element) -> str:
    # pytest writes classname "tests.test_x" and name "test_y[param]" for tests/test_x.py::test_y[param].
    module = case.get('classname', '').split('.')
    return '/'.join(module[:-1] + [module[-1] + '.py']) + '::' + case.get('name', '')


def run_named() -> None:
    check(len(NAMED) == len(set(NAMED)), f'the named pins are distinct: {len(NAMED)}')
    for era in ERAS:
        with tempfile.TemporaryDirectory(prefix='f6-f9-') as scratch:
            junit = Path(scratch) / 'junit.xml'
            done = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={junit}', *TESTS],
                                  cwd=ROOT, env=env_for(era), capture_output=True, text=True, timeout=600)
            results = {}
            if junit.exists():
                for case in ET.parse(junit).getroot().iter('testcase'):
                    tags = {child.tag for child in case} & {'failure', 'error', 'skipped'}
                    results[node_id(case)] = ' and '.join(sorted(tags)) or 'passed'
        bad = sorted(f'{test}: {result}' for test, result in results.items() if result != 'passed')
        check(done.returncode == 0 and not bad,
              f'{era} era: every collected test passed, none skipped ({len(results)} collected)' + (f'; {bad[:5]}' if bad else ''))
        passed = [test for test in NAMED if results.get(test) == 'passed']
        missing = [test for test in NAMED if test not in results]
        check(len(passed) == len(NAMED), f'{era} era: {len(passed)}/{len(NAMED)} named pins passed'
              + (f'; not collected: {missing[:5]}' if missing else ''))
        stale = [test for test in RETIRED if test in results]
        check(not stale, f'{era} era: the retired read-the-same comment control is gone ({stale})')


def main() -> int:
    run_named()
    spans = regions(assigns('WINDOW')) + regions(calls_to('legacy_warning', 'ignored_warning'))
    cases = cases_in(spans, ('README.md',))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    print('F6-F9: accepted residuals, recorded, not run as cases:')
    for case, why in RESIDUAL.items():
        print(f'  - {case}: {why}')
    return finish('F6-F9 upgrading section from source, one command warning', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
