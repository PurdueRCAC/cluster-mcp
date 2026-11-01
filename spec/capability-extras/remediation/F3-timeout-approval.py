# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 1, F3: no live text says the timeout measurement still waits for approval.

    uv run --no-project python -I spec/capability-extras/remediation/F3-timeout-approval.py      from the worktree root

The measurement was approved on 2026-10-29. The predicate, over every tracked Markdown file outside
`spec/` (the records): a sentence that ties the measurement, or the entry "A timed-out command may
keep running after its call returns", to approval it does not yet have is a violation, unless a dated
correction saying it was approved follows it in the same file (an append-only correction of a seed).
The entry's prose and its Horizon line must say approved, with the date, as the Part I intro does.
Seen red on HEAD before the fix: the entry's two sentences and its Horizon line. Footprint: one
process, no network, under 50 MB.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ENTRY = '## A timed-out command may keep running after its call returns'
# A claim that approval is still to come.
PENDING = re.compile(r"(needs|waits for|wait for|awaits|until it has it|once its measurement is approved)"
                     r"[^.]{0,80}?approv|approval first", re.I)
CORRECTED = re.compile(r'^- 2026-10-29: the measurement was approved\.$', re.M)


def flat(s: str) -> str:
    return re.sub(r'\s+', ' ', s)


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find('\n## ', start + len(heading))
    return text[start:nxt if nxt >= 0 else len(text)]


def main() -> int:
    bad: list[str] = []
    files = subprocess.run(['git', 'ls-files', '*.md', ':!spec'], capture_output=True, text=True,
                           check=True).stdout.split()
    checked = 0
    for name in files:
        text = Path(name).read_text()
        if not re.search(r'measur', text, re.I):
            continue
        for m in PENDING.finditer(flat(text)):
            window = flat(text)[max(0, m.start() - 200):m.end() + 40]
            if not re.search(r'measur|timed-out|timeout', window, re.I):
                continue
            checked += 1
            if CORRECTED.search(text) and name.startswith('issues/'):
                continue
            bad.append(f'{name}: still waits for approval: …{flat(text)[max(0, m.start() - 60):m.end() + 20]}…')
    roadmap = Path('ROADMAP.md').read_text()
    entry = flat(section(roadmap, ENTRY))
    if 'Its measurement was approved on 2026-10-29.' not in entry:
        bad.append('the entry does not say its measurement was approved on 2026-10-29')
    if not re.search(r'\*Horizon: [^*·]*approved on 2026-10-29', entry):
        bad.append('the entry\'s Horizon line does not say the measurement was approved on 2026-10-29')
    if 'measurement now approved' not in flat(roadmap.split(ENTRY)[0]):
        bad.append('the Part I intro no longer says the measurement is approved')
    if checked == 0:
        bad.append('no pending-approval claim was evaluated: the seed\'s own sentence should be (corrected)')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F3: ok ({len(files)} files, {checked} approval claim(s) evaluated, each corrected)', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
