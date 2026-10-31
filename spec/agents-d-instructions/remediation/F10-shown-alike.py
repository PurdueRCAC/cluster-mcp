# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F10 (review 3, GOAL C13): no live text claims that no two names are shown alike.

`uv run python spec/agents-d-instructions/remediation/F10-shown-alike.py`, from the tree root (seconds).

- The property, evaluated: `shown` is injective on decoded text, and names that differ only in
  bytes that are not valid UTF-8 decode, and so show, alike (`b'a\\xff.md'`, `b'a\\xfe.md'` and
  `'a\\ufffd.md'` all show as one string).
- The claim: no live text (README.md, AGENTS.md, `src/`, `tests/`) says that no two names (rather
  than no two decoded names) are shown alike, and README.md says what is true: names are shown by
  their decoded text, so names differing only in invalid bytes can show alike, and are still two
  files.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from common import check, finish, site

CLAIM = re.compile(r'no two (?!decoded )(?:\w+ )?(?:names|texts) (?:are |is )?(?:shown|show) alike', re.I)


def main() -> int:
    alike = {site.shown(raw.decode('utf-8', 'replace')) for raw in (b'a\xff.md', b'a\xfe.md', 'a�.md'.encode())}
    check(len(alike) == 1, f'the names were meant to show alike: {alike}')
    for path in [Path('README.md'), Path('AGENTS.md'), *Path('src').rglob('*.py'), *Path('tests').glob('*.py')]:
        flat = ' '.join(path.read_text().split())
        for match in CLAIM.finditer(flat):
            if 'texts' not in match.group(0):
                check(False, f'{path}: still claims {match.group(0)!r}')
    readme = ' '.join(Path('README.md').read_text().split())
    check('Names are shown by their decoded text' in readme and 'can show alike' in readme
          and 'still two files' in readme, 'README.md does not say that decoded names can show alike')
    return finish('F10 shown alike')


if __name__ == '__main__':
    sys.exit(main())
