#!/bin/sh
# Review cycle 1, class 3: a write's texts say what it leaves. Run from the worktree root.
#
# The defect is a live text claiming a write's staging is removed on every path; the predicate is
# textual, so the check is that no live site (the package, AGENTS.md, README.md, SECURITY.md,
# INSTRUCTIONS.md) says so in any of the shapes it took, that each site that describes the staging
# states the case that leaves it, and that the cleanup is filed as a seed with its ROADMAP entry.
set -eu
claims='removed on every path|removed whatever happens|removes the staging on every path'
if git grep -n -i -E "$claims" -- src AGENTS.md README.md SECURITY.md INSTRUCTIONS.md; then
    echo "F3-write-texts: a live text still says the staging is always removed" >&2
    exit 1
fi
uv run python - <<'PY'
from pathlib import Path
from rcac_mcp.executor.base import Executor
from rcac_mcp.executor.ssh import SSHExecutor

said = 'lost after the content is staged'
texts = {
    'SSHExecutor.write': SSHExecutor.write.__doc__ or '',
    'Executor.write': Executor.write.__doc__ or '',
    'AGENTS.md §2': Path('AGENTS.md').read_text().split('### 2. Executor Protocol contract')[1].split('### 3.')[0],
}
missing = [name for name, text in texts.items() if said not in ' '.join(text.split())]
assert not missing, f'these texts do not say the staging can remain: {missing}'
assert 'issues/ssh-write-staging-leftover.md' in texts['AGENTS.md §2'], 'AGENTS.md §2 does not point at the seed'
PY
test -f issues/ssh-write-staging-leftover.md
grep -q '^status: unshaped$' issues/ssh-write-staging-leftover.md
grep -q '^lane: public$' issues/ssh-write-staging-leftover.md
grep -q 'issues/ssh-write-staging-leftover.md' ROADMAP.md
echo "F3-write-texts: green" >&2
