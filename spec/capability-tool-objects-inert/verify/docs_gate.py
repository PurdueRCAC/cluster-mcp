# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""AGENTS.md § Invariants §7 says what the check lands, in the commit that lands it.

    uv run python -I spec/capability-tool-objects-inert/verify/docs_gate.py      from the worktree root

Reads the index (`git show :<file>`), the state the phase's commit takes, never the working copy. When
the index's `core/capabilities.py` holds the check (`def _tool_violation`), the index's AGENTS.md §7
(from its `### 7.` heading to the next `### `) must:

- in its refusal list, refuse a registered object that is not exactly a `FunctionTool` (the words
  "exactly a `FunctionTool`") and a field whose value its rule does not accept (the words "its rule");
- in its paragraph opening "**No read of a loaded record runs capability code.**": name the tool
  objects as decided too (`FunctionTool`), say the check holds at load (the words "at load"), and
  name `issues/capability-tool-objects-served-copy.md`;
- no longer list the tools among what FastMCP reads, running capability code, as it registers them
  (the words "its tools (each a `FunctionTool` holding its function)"), nor name them in the "What
  does run capability code" sentence before its "resource handlers".

A check that is not in the index yet passes with a note, so the gate also runs on the plan's tree.
Footprint: one process and two git reads, under 50 MB.
"""

from __future__ import annotations

import subprocess
import sys

LOADER = 'packages/cluster-mcp/src/cluster_mcp/core/capabilities.py'
SEED = 'issues/capability-tool-objects-served-copy.md'
PARAGRAPH = '**No read of a loaded record runs capability code.**'
OLD = 'its tools (each a `FunctionTool` holding its function)'
RUNS = 'What does run capability code'


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


def main() -> int:
    if 'def _tool_violation' not in staged(LOADER):
        print('docs_gate: the check is not in the index yet; nothing to hold §7 to', file=sys.stderr)
        return 0
    agents = staged('AGENTS.md')
    start = agents.find('\n### 7. ')
    end = agents.find('\n### ', start + 1)
    if start < 0 or end < 0:
        print('docs_gate: AGENTS.md has no § Invariants §7', file=sys.stderr)
        return 1
    section = ' '.join(agents[start:end].split())
    bad: list[str] = []
    if 'exactly a `FunctionTool`' not in section:
        bad.append('§7 does not refuse a registered object that is not exactly a `FunctionTool`')
    if 'its rule' not in section:
        bad.append('§7 does not refuse a field whose value its rule does not accept')
    at = section.find(PARAGRAPH)
    if at < 0:
        bad.append(f'§7 has no paragraph opening {PARAGRAPH}')
    else:
        rest = section[at + len(PARAGRAPH):]
        nxt = rest.find(' - **')
        paragraph = rest if nxt < 0 else rest[:nxt]
        for word, why in (('FunctionTool', 'name the tool objects as decided too'),
                          ('at load', 'say the check holds at load'),
                          (SEED, f'name {SEED}')):
            if word not in paragraph:
                bad.append(f'§7\'s "No read of a loaded record" paragraph does not {why}')
    if OLD in section:
        bad.append('§7 still lists the tools among what FastMCP reads, running capability code')
    runs = section.find(RUNS)
    if runs < 0:
        bad.append(f'§7 no longer says {RUNS!r}')
    else:
        listed = section[runs:section.find('resource handlers', runs)]
        for word in ('its tools', 'each a `FunctionTool`', 'FunctionTool` holding'):
            if word in listed:
                bad.append(f'§7\'s "{RUNS}" sentence still names the tools ({word!r}) before the resource handlers')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print('docs_gate: ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
