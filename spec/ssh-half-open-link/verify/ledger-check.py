"""Every deferral this cycle writes names an `issues/` seed that exists and has a ROADMAP entry.

Run from the worktree root:

    uv run python -I spec/ssh-half-open-link/verify/ledger-check.py

It reads the prose and list items of TECH.md's phase bodies and of the branch's commit bodies
(BASE..HEAD), never a Markdown heading (`REVIEW.md`'s "Out of scope (recorded, not blocking)" is a
heading, not a deferral). Each paragraph or list item that carries a deferral phrase must name an
`issues/<slug>.md` that exists and that ROADMAP.md links. Then every seed in FILED and NOTED must exist, be
linked from ROADMAP.md, and, for those this cycle only notes, carry a dated note on one line
naming `spec/ssh-half-open-link/`. A quoted phrase (the ledger's own wording) is not a deferral.

Footprint: one `git log`, file reads; no child but git, a few MB.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

BASE = '13c0e83'
SLUG = 'ssh-half-open-link'
TECH = f'spec/{SLUG}/TECH.md'
PHRASES = ('do not fix here', 'known limitation', 'left as a follow-up', 'follow-up', 'limit',
           'deferred', 'deferral', 'floor', 'not fixed')
SEED = re.compile(r'issues/([a-z0-9-]+)\.md')
# The seed this plan filed, and the existing seeds the cycle adds a dated note to.
FILED = ['ssh-liveness-message-gap']
NOTED = ['ssh-gateway-hops-unpinned', 'ssh-write-staging-leftover', 'ssh-open-session-reset-raises']


def _blocks(text: str) -> list[str]:
    """Paragraphs and list items, joined across their wrapped lines; headings and rules dropped."""
    blocks, current = [], []
    for line in text.splitlines():
        stripped = line.strip()
        starts_item = bool(re.match(r'([-*]|\d+\.)\s', stripped))
        if not stripped or stripped.startswith('#') or stripped == '---' or starts_item:
            if current:
                blocks.append(' '.join(current))
            current = [] if not starts_item else [stripped]
            continue
        current.append(stripped)
    if current:
        blocks.append(' '.join(current))
    return blocks


def main() -> int:
    with open(TECH, encoding='utf-8') as handle:
        tech = handle.read()
    phases = tech[tech.index('## Phase P1'):tech.index('## How `code-build` drives this')]
    bodies = subprocess.run(['git', 'log', f'{BASE}..HEAD', '--format=%B'], check=True, capture_output=True,
                            text=True).stdout
    with open('ROADMAP.md', encoding='utf-8') as handle:
        roadmap = handle.read()
    problems = []
    for source, text in (('TECH.md', phases), ('commit bodies', bodies)):
        for block in _blocks(text):
            # A quoted phrase is the ledger's own wording, not a deferral.
            lowered = re.sub(r'"[^"]*"', '', block).lower()
            if not any(phrase in lowered for phrase in PHRASES):
                continue
            seeds = SEED.findall(block)
            if not seeds:
                problems.append(f'{source}: a deferral names no issues/ seed: {block[:160]}')
            for seed in seeds:
                if not os.path.exists(f'issues/{seed}.md'):
                    problems.append(f'{source}: issues/{seed}.md does not exist ({block[:100]})')
                elif f'issues/{seed}.md' not in roadmap:
                    problems.append(f'{source}: issues/{seed}.md has no ROADMAP.md entry')
    for seed in FILED + NOTED:
        name = f'issues/{seed}.md'
        if not os.path.exists(name):
            problems.append(f'{name} does not exist')
            continue
        if name not in roadmap:
            problems.append(f'{name} has no ROADMAP.md entry')
        if seed in NOTED:
            with open(name, encoding='utf-8') as handle:
                if not re.search(rf'20\d\d-\d\d-\d\d\b.*spec/{SLUG}/', handle.read()):
                    problems.append(f'{name} carries no dated note naming spec/{SLUG}/')
    print('\n'.join(problems) or 'every deferral names a seed with a ROADMAP entry')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
