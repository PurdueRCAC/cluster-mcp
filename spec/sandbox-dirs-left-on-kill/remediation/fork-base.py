"""Run the frozen gate, verify/cleanup.py, unchanged, with its `files` mode measured from the branch's fork point.

The gate pins BASE = 0bfacae, the develop commit the cycle was planned on. The branch was since rebased onto
origin/develop (the foreman, 2026-11-09, before P1), so `git diff --cached --name-only 0bfacae` also lists
develop's own changes since then, and the `files` mode's allowed-paths check names them as strays. This
wrapper restores the precondition the gate was written under, that BASE is the commit the branch forks from:

1. R5 as the gate states it: bin/sandbox.sh is byte-identical to 0bfacae, in the tree and in the index;
2. bin/sandbox.sh is also unchanged from 0bfacae to the fork point, so step 3's R5 check is the same check;
3. the gate's own modes, as given on the command line, with BASE set to the fork point
   (`git merge-base HEAD origin/develop`), and the `files` mode's allowed paths widened by ALSO_ALLOWED:
   the seeds P3's ledger files on the foreman's rulings (2026-11-12), and the seeds review cycles 1 and 2
   filed for their coverage observations (2026-11-12), which the frozen ALLOWED predates.

Run from the cycle worktree, staged, as
`uv run python -I spec/sandbox-dirs-left-on-kill/remediation/fork-base.py MODE…`.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

PLANNED = '0bfacae'
GATE = Path(__file__).resolve().parent.parent / 'verify' / 'cleanup.py'
ALSO_ALLOWED = ('issues/mutant-case-cleanup-interrupted.md', 'issues/sandbox-dirs-outside-repo-runs.md',
                'issues/sandbox-sweep-listing-failure-unpinned.md',
                'issues/sandbox-reopen-link-in-closed-dir-unpinned.md')


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', *args], capture_output=True, text=True)


def main(argv: list[str]) -> int:
    spec = importlib.util.spec_from_file_location('cleanup_gate', GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    fork = git('merge-base', 'HEAD', 'origin/develop').stdout.strip()
    if not fork:
        gate.fail('files', 'no fork point: git merge-base HEAD origin/develop printed nothing')
        return 1
    tree = git('diff', '--quiet', PLANNED, '--', 'bin/sandbox.sh').returncode == 0
    index = git('diff', '--cached', '--quiet', PLANNED, '--', 'bin/sandbox.sh').returncode == 0
    gate.check('files', tree and index, f'R5: bin/sandbox.sh is byte-identical to {PLANNED}, in the tree and the index',
               f'R5: bin/sandbox.sh differs from {PLANNED} (tree same: {tree}, index same: {index})')
    between = git('diff', '--quiet', PLANNED, fork, '--', 'bin/sandbox.sh').returncode == 0
    gate.check('files', between, f'bin/sandbox.sh is unchanged from {PLANNED} to the fork point {fork[:7]}',
               f'bin/sandbox.sh changed between {PLANNED} and the fork point {fork[:7]}')
    gate.BASE = fork
    gate.ALLOWED = (*gate.ALLOWED, *ALSO_ALLOWED)
    status = gate.main(argv)
    return 1 if gate.FAILS else status


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
