# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""P5's frozen deferral ledger, run unchanged but for Markdown headings (foreman's ruling, 2026-10-31).

    uv run --no-project python -I spec/capability-extras/remediation/P5-ledger-headings.py      from the worktree root

`verify/ledger.py` reads each heading line as a block of its own, so the heading the review template
writes, `### Out of scope (recorded, not blocking)`, reads as a deferral without a seed. This loads
the frozen `ledger.py` by path, unedited, wraps its `blocks()` to drop heading lines (`#` to `######`
then a space) before splitting, and runs its `main()`. Every paragraph and list item is still read,
so a deferral item under that heading without a seed still fails. Footprint: one process, no
network, under 50 MB.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / 'verify' / 'ledger.py'
HEADING = re.compile(r'^#{1,6}\s')


def main() -> int:
    spec = importlib.util.spec_from_file_location('frozen_ledger', LEDGER)
    ledger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ledger)
    frozen = ledger.blocks

    def blocks(text: str) -> list[str]:
        return frozen('\n'.join(line for line in text.splitlines() if not HEADING.match(line)))

    ledger.blocks = blocks
    return ledger.main()


if __name__ == '__main__':
    sys.exit(main())
