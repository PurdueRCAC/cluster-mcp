#!/bin/sh
# Review cycle 2, class 3: every text about stalls says what the code does. Run from the worktree
# root.
#
# The defect is a live text listing an SSH-agent query among the steps with nothing to close, or
# saying its late success is published: the agent query comes once the transport exists, the abort
# closes it, and the worker's late outcome is discarded. The check reads every live text with its
# whitespace collapsed, sentence by sentence (a dated correction quoting the old claim excepted),
# then that the `_abort` docstring and the footgun state the agent case, and that the seed and its
# ROADMAP entry carry their dated corrections.
set -eu
uv run python - <<'PY'
import re
import subprocess
from pathlib import Path

from rcac_mcp.executor.ssh import SSHExecutor

files = subprocess.run(['git', 'ls-files', 'src', 'AGENTS.md', 'README.md', 'SECURITY.md', 'INSTRUCTIONS.md',
                        'ROADMAP.md', 'issues'], capture_output=True, text=True, check=True).stdout.split()
assert files, 'no live text was read'
wrong = []
for name in files:
    if not name.endswith(('.py', '.md')):
        continue
    text = ' '.join(re.sub(r'^\s*#\s?', '', Path(name).read_text(), flags=re.M).split())
    for sentence in re.split(r'(?<=[.;])\s', text):
        if 'As first filed' in sentence or 'agent' not in sentence.lower():
            continue
        if re.search(r'SSH[- ]agent', sentence, re.I) and \
                re.search(r'nothing to close|cannot close|late success is published', sentence):
            wrong.append(f'{name}: {sentence[:160]}')
assert not wrong, 'a live text still says an SSH-agent stall has nothing to close:\n' + '\n'.join(wrong)
abort = ' '.join((SSHExecutor._abort.__doc__ or '').split())
assert 'SSH-agent query' in abort and 'is discarded' in abort, abort
agents = ' '.join(Path('AGENTS.md').read_text().split())
assert 'has its transport closed but runs on until the agent answers, and its late outcome is discarded' in agents
for name in ('issues/ssh-reconnect-stuck-step.md', 'ROADMAP.md'):
    assert '- 2026-10-26: corrected.' in Path(name).read_text(), f'{name} carries no dated correction'
PY
echo "F7-stall-texts: green" >&2
