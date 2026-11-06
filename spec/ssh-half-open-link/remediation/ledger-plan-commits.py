"""`verify/ledger-check.py`, unchanged, reading two plan-stage commit bodies as naming their seed.

Run from the worktree root:

    uv run python -I spec/ssh-half-open-link/remediation/ledger-plan-commits.py

Why (the foreman's ruling at P3's build, 2026-11-05): the frozen ledger reads every commit body on
the branch, and two from the plan's sign-off name R4's floor in prose without the seed's path:
`7bf9666` (its subject) and `9d7411b` (a paragraph of its body). The deferral both mean is seeded,
`issues/ssh-liveness-message-gap.md` with its ROADMAP entry; their bodies only predate that path
being written in prose. Rewriting them would rewrite the branch's history, and the profile's
squash-local landing drops every branch body anyway.

What changes: the bodies of those two commits only are read with that seed's path on every line, so
each of their paragraphs names it, and the frozen gate then requires that seed and its ROADMAP entry
to exist, as for any seed named. Every other commit body, TECH's phase bodies, and every check of the
filed and noted seeds are the frozen gate's own.

Footprint: the frozen gate's (one `git log`, file reads), plus one `git log` here.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from types import SimpleNamespace

# The plan-stage commits whose bodies mean R4's floor, and the seed that records it.
PLAN_COMMITS = ('7bf9666', '9d7411b')
FLOOR_SEED = 'issues/ssh-liveness-message-gap.md'
GATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'verify', 'ledger-check.py')


def _load() -> object:
    spec = importlib.util.spec_from_file_location('ledger_check', GATE)
    assert spec is not None and spec.loader is not None, f'cannot load {GATE}'
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


def _bodies(base: str) -> str:
    """Every commit body on the branch, as `git log --format=%B` gives them, the two plan commits'
    each line carrying the floor's seed."""
    raw = subprocess.run(['git', 'log', f'{base}..HEAD', '--format=%H%x00%B%x01'], check=True,
                         capture_output=True, text=True).stdout
    bodies = []
    for record in raw.split('\x01'):
        if '\x00' not in record:
            continue
        commit, body = record.lstrip('\n').split('\x00', 1)
        if commit.startswith(PLAN_COMMITS):
            body = '\n'.join(f'{line} ({FLOOR_SEED})' if line.strip() else line for line in body.split('\n'))
        bodies.append(body)
    return '\n'.join(bodies)


def main() -> int:
    gate = _load()
    run = subprocess.run

    def reading(argv: list[str], *args: object, **kwargs: object) -> object:
        if argv == ['git', 'log', f'{gate.BASE}..HEAD', '--format=%B']:
            return SimpleNamespace(stdout=_bodies(gate.BASE), returncode=0)
        return run(argv, *args, **kwargs)

    gate.subprocess = SimpleNamespace(run=reading)
    return gate.main()


if __name__ == '__main__':
    sys.exit(main())
