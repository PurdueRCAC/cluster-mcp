"""Documentation and ledger checks for surface-fixture-after-a-surface-change. Run from the worktree root.

Usage: uv run python -I spec/surface-fixture-after-a-surface-change/verify/docs_check.py docs|ledger

docs    AGENTS.md describes the method (GOAL R8): § Invariants §9 and the `tests/test_surface.py`
        entry of § Testing name the command and what the fixture records, and no longer carry the
        hand-edit rule, its delta history, the "open question" text or the retired names; § Commands
        lists the command. The suite's own docstrings (harness, test_surface) drop the same text.
ledger  every deferral phrase in TECH.md's phase bodies (prose and list items, never headings)
        names an `issues/{slug}.md` that exists and that ROADMAP.md lists (code-plan Step 6.8).

Footprint: one python process, a few MB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path.cwd()
SPEC = ROOT / 'spec' / 'surface-fixture-after-a-surface-change'
COMMAND = 'bin/record_surface.py'

# Text the method replaces: the hand-edit rule, its delta history, the open question, the retired names.
STALE = ('hand-edit', 'Deltas so far', 'long-term method', 'not in the fixture\'s shape', "fixture's shape test",
         '2.x-shaped', 'issues/surface-fixture-after-a-surface-change.md', 'test_surface_fixture_is_the_baseline_shape',
         'TOLERATED', 'tolerated_differences', '`safe-execution` changed')
# Text no part of AGENTS.md keeps: the server's name and the metadata are in the fixture now.
ANYWHERE = ("fixture's shape", 'test_surface_fixture_is_the_baseline_shape', 'TOLERATED', 'tolerated_differences')
# What a description of the method names: the command, what the fixture records, how a change lands.
NAMED = (COMMAND, 'capabilities', 'prompts', 'serverInfo', 'commit body')

DEFERRAL = re.compile(r'do not fix here|known limitation|left as a follow-up|follow-up:|deferred to|deferred,',
                      re.I)
SEED = re.compile(r'issues/([\w.-]+\.md)')


def section(text: str, start: str, stop: str) -> str:
    """The text from the line starting with `start` to the next line matching `stop`."""
    at = text.find(start)
    if at < 0:
        return ''
    end = re.compile(stop, re.M).search(text, at + len(start))
    return text[at:end.start() if end else len(text)]


def docs() -> list[str]:
    agents = (ROOT / 'AGENTS.md').read_text()
    parts = {
        '§9': section(agents, '### 9. The agent-facing surface', r'^### '),
        '§ Testing (tests/test_surface.py)': section(agents, '  - `tests/test_surface.py`', r'^  - `tests/|^- '),
    }
    problems = []
    for where, text in parts.items():
        if not text:
            problems.append(f'{where}: not found')
            continue
        problems += [f'{where} names {word!r}' for word in STALE if word in text]
        problems += [f'{where} does not name {word!r}' for word in NAMED if word not in text]
    problems += [f'AGENTS.md names {word!r}' for word in ANYWHERE if word in agents]
    commands = section(agents, '## Commands', r'^## ')
    if COMMAND not in commands:
        problems.append(f'§ Commands does not list {COMMAND}')
    for name in ('tests/harness.py', 'tests/test_surface.py'):
        text = (ROOT / name).read_text()
        problems += [f'{name} names {word!r}' for word in STALE if word in text]
    return problems


def ledger() -> list[str]:
    tech = (SPEC / 'TECH.md').read_text().split('\n---\n', 1)[-1]
    roadmap = (ROOT / 'ROADMAP.md').read_text()
    problems = []
    for number, line in enumerate(tech.splitlines(), 1):
        if line.lstrip().startswith('#') or not DEFERRAL.search(line):
            continue
        seeds = SEED.findall(line)
        if not seeds:
            problems.append(f'TECH.md body line {number}: a deferral names no issues/ seed: {line.strip()}')
        for seed in seeds:
            if not (ROOT / 'issues' / seed).exists():
                problems.append(f'TECH.md body line {number}: issues/{seed} does not exist')
            elif f'issues/{seed}' not in roadmap:
                problems.append(f'TECH.md body line {number}: ROADMAP.md does not list issues/{seed}')
    return problems


def main(argv: list[str]) -> int:
    checks = {'docs': docs, 'ledger': ledger}
    if len(argv) != 1 or argv[0] not in checks:
        print('usage: docs_check.py docs|ledger', file=sys.stderr)
        return 2
    problems = checks[argv[0]]()
    for problem in problems:
        print(f'docs_check: FAIL: {problem}', file=sys.stderr)
    if not problems:
        print(f'docs_check: ok: {argv[0]}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
