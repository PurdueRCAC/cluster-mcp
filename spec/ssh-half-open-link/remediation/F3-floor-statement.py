"""Review cycle 1, F3: every statement of the liveness floor says what the code does.

Run from anywhere in the worktree:

    uv run python -I spec/ssh-half-open-link/remediation/F3-floor-statement.py

The code (`ssh._verdict`) judges a background probe dead at `out + 2B - VERDICT_MARGIN` (29 s at
the default 15 s bound) and, only while a call starts, one bound after that call's poke. The
finding's instance was the floor seed's title and its ROADMAP entry, which said a link is called
dead once a probe has been out for one connect bound. The defining property, over every live site
(`AGENTS.md`, `README.md`, `ROADMAP.md`, `issues/*.md`, and every docstring and comment in
`packages/*/src`):

1. **No site says the verdict is one connect bound in general**: none of `ONE_BOUND`'s phrasings
   appears (flattened, case folded), however it is worded among them.
2. **The floor seed and its ROADMAP entry state both verdicts**: the seed's title and the entry's
   heading are the same words; the entry names the background verdict (`29 s`, two bounds less
   `VERDICT_MARGIN`) and the starting call's (`15 s`, one bound after its start).
3. **The figures are the code's**: `2 * CONNECT_TIMEOUT - VERDICT_MARGIN` is 29 and `CONNECT_TIMEOUT`
   is 15, read from `ssh.py` itself.

`GOAL.md` is locked and already states 29 s; `spec/**` records are not live sites.

Footprint: reads files; runs nothing.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TOP = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True, cwd=Path(__file__).parent).stdout.strip())
SEED = 'issues/ssh-liveness-message-gap.md'
# The misstatement, in the ways it was or could be put: a link called dead once a probe has been out,
# or nothing has arrived, for one connect bound, said of every probe.
ONE_BOUND = (
    r'delivers nothing for one connect bound',
    r'(?:probe|it) has been out for one (?:connect )?bound',
    r'nothing (?:at all )?(?:has )?(?:arrived|been heard|arrives) for one (?:connect )?bound[^.]*(?:reads|is called|is taken for|is judged) (?:as )?dead',
    r'dead (?:once|when|after) a probe has been (?:out|unanswered) for one (?:connect )?bound',
)


def _flat(text: str) -> str:
    return ' '.join(text.split()).lower()


def _sites() -> list[Path]:
    sites = [TOP / name for name in ('AGENTS.md', 'README.md', 'ROADMAP.md', 'INSTRUCTIONS.md')]
    sites += sorted((TOP / 'issues').glob('*.md'))
    sites += sorted(TOP.glob('packages/*/src/**/*.py'))
    return [site for site in sites if site.exists()]


def _entry(roadmap: str) -> tuple[str, str]:
    """The ROADMAP heading and body whose seed line names the floor seed."""
    for block in re.split(r'\n(?=## )', roadmap):
        if f'({SEED})' in block:
            heading, _, body = block.partition('\n')
            return heading.removeprefix('## ').strip(), body
    return '', ''


def main() -> int:
    problems = []
    sites = _sites()
    if len(sites) < 10:
        problems.append(f'only {len(sites)} live sites found, so check 1 proves little')
    for site in sites:
        text = _flat(site.read_text())
        for pattern in ONE_BOUND:
            for found in re.finditer(pattern, text):
                problems.append(f'{site.relative_to(TOP)}: says {found.group(0)!r}')
    seed = (TOP / SEED).read_text()
    title = next((line.removeprefix('# ').strip() for line in seed.splitlines() if line.startswith('# ')), '')
    heading, body = _entry((TOP / 'ROADMAP.md').read_text())
    if not heading:
        problems.append(f'ROADMAP.md has no entry whose seed is {SEED}')
    elif heading != title:
        problems.append(f'the seed is titled {title!r} and its ROADMAP entry {heading!r}')
    flat = _flat(body)
    for part in ('29 s', 'two connect bounds less `verdict_margin`', '15 s', 'one bound after'):
        if part not in flat:
            problems.append(f'the ROADMAP entry for {SEED} does not state {part!r}')
    source = (TOP / 'packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py').read_text()
    bound = int(re.search(r'^CONNECT_TIMEOUT: Final = (\d+)$', source, re.M).group(1))
    margin = float(re.search(r'^VERDICT_MARGIN: Final = ([\d.]+)$', source, re.M).group(1))
    if (bound, 2 * bound - margin) != (15, 29.0):
        problems.append(f'the code gives {bound} s and {2 * bound - margin} s, not the 15 s and 29 s the texts state')
    if 'due = out + 2 * bound - VERDICT_MARGIN' not in source or 'max(out, poked) + bound' not in source:
        problems.append("`_verdict` no longer reads as the texts state it; re-read before trusting this check")
    print(f'{len(sites)} live sites read; the floor seed and its entry checked')
    for problem in problems:
        print(f'FAILED  {problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
