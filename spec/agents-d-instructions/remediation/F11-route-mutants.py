# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""F11 (review 3, GOAL C13): the five route-check mutants that survived review 3 are pinned.

`uv run python spec/agents-d-instructions/remediation/F11-route-mutants.py`, from the tree root.

Review 3's survivors, each now a case in `tests/mutants.py` against the descriptor read, killed under
`--self-check` by its test:

- the ancestor check skipping `/`: `site-root-unsearched`, by the `acl-root` row of
  `test_a_read_for_others_keeps_only_what_every_account_can_read`;
- relative symlink targets resolved from `/`: `site-link-from-root`, by its
  `open-through-relative-link` row;
- `..` steps not recorded as searched: `site-dotdot-unsearched`, by its `dotdot-out-of-private-dir`
  row;
- the read thread made non-daemon: `site-read-thread-kept`, by
  `test_an_abandoned_read_does_not_hold_the_process`;
- macOS acl(3) errors failing open: `site-acl-error-open`, by
  `test_an_acl_the_system_cannot_answer_counts_as_one` (libSystem stubbed, so every platform).

Each test also passes on the tree as built, and none skips. About 1 min, under 300 MB.
"""

from __future__ import annotations

import subprocess
import sys

from common import check, finish, mutants

T = 'tests/test_site.py::'
ROWS = ['acl-root', 'open-through-relative-link', 'dotdot-out-of-private-dir']
TESTS = [*(f'{T}test_a_read_for_others_keeps_only_what_every_account_can_read[{row}-{who}]'
           for row in ROWS for who in ('for-this-process', 'for-others')),
         f'{T}test_an_abandoned_read_does_not_hold_the_process',
         f'{T}test_an_acl_the_system_cannot_answer_counts_as_one']


def main() -> int:
    done = subprocess.run(['uv', 'run', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', *TESTS], capture_output=True,
                          text=True, timeout=300)
    check(done.returncode == 0 and '11 passed' in done.stdout and 'skipped' not in done.stdout,
          f'the pinning tests: {done.stdout[-300:]}')
    mutants('site-root-unsearched', 'site-link-from-root', 'site-dotdot-unsearched', 'site-read-thread-kept',
            'site-acl-error-open')
    return finish('F11 route mutants')


if __name__ == '__main__':
    sys.exit(main())
