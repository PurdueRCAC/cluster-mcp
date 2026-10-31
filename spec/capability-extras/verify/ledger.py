# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Every deferral this cycle names has its record: an `issues/` seed and a ROADMAP.md entry.

    uv run --no-project python spec/capability-extras/verify/ledger.py      from the worktree root

Reads GOAL.md, PLAN.md, TECH.md and REVIEW.md (when present) of this cycle. Every
`issues/<slug>.md` they link must exist and be named in ROADMAP.md. Every paragraph or list item
that defers something (it says "defer", "deferred", "follow-up", "out of scope", "known limitation",
"not fixed here" or "left for", in any case) must also link an `issues/<slug>.md`, unless it says
the item is "not deferred". A phrase inside double quotes is quoted, not used, and is skipped. Footprint: one process, no network, under 50 MB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SPEC = Path('spec/capability-extras')
LINK = re.compile(r'issues/([a-z0-9-]+)\.md')
DEFERS = re.compile(r'\bdefer(red|s)?\b|follow-up|out of scope|known limitation|not fixed here|left for', re.I)


def blocks(text: str) -> list[str]:
    """Paragraphs and list items, each one string."""
    out, cur = [], []
    for line in text.splitlines():
        if not line.strip() or re.match(r'\s*([-*]|\d+\.|\|)\s', line):
            if cur:
                out.append(' '.join(cur))
            cur = [line] if line.strip() else []
        else:
            cur.append(line)
    if cur:
        out.append(' '.join(cur))
    return out


def main() -> int:
    roadmap = Path('ROADMAP.md').read_text()
    bad: list[str] = []
    for name in ('GOAL.md', 'PLAN.md', 'TECH.md', 'REVIEW.md'):
        f = SPEC / name
        if not f.exists():
            continue
        text = f.read_text()
        for slug in sorted(set(LINK.findall(text))):
            if not Path(f'issues/{slug}.md').exists():
                bad.append(f'{name}: links issues/{slug}.md, which does not exist')
            elif f'issues/{slug}.md' not in roadmap:
                bad.append(f'{name}: issues/{slug}.md has no ROADMAP.md entry')
        for b in blocks(text):
            if DEFERS.search(re.sub(r'"[^"]*"', '', b)) and not LINK.search(b) and 'not deferred' not in b.lower():
                bad.append(f'{name}: defers without a seed: {b.strip()[:120]}')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print('ledger: ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
