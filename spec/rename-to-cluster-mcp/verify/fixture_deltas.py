# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Apply this cycle's named served-surface deltas to tests/fixtures/served_surface.json, and check them.

Run from the worktree root: `uv run python spec/rename-to-cluster-mcp/verify/fixture_deltas.py
apply|check p1|p3|p4` (p1: nothing may differ yet; P1 and P2 check it). Footprint: one process, no network, under 200 MB.

The fixture keeps its FastMCP 2 snapshot shape (AGENTS.md § Invariants §9: `instructions`, `resources`,
`tools`); a deliberate change is a scripted edit of named deltas only, measured from the 0.1.4 tag's
fixture. This cycle's deltas, and nothing else (GOAL R8):

- p3 on, `resources`: a `cluster://context` and a `cluster://storage` key, each a copy of its
  `rcac://` entry, which stays unchanged (the aliases are listed, as served);
- p4 on, `instructions`: the composed base (core, Slurm snippet, RCAC-specific overlay) with the
  harness's site context (`harness.SITE`).

The server name is not in the fixture's shape; `test_server_identifies_as_cluster_mcp` pins it.
`tools` never changes. `check` fails, naming each path, when anything outside the phase's deltas
differs from 0.1.4's fixture, or a delta is not exactly what `apply` writes, or a due delta is
missing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, 'tests')

FIXTURE = Path('tests/fixtures/served_surface.json')
BASELINE_REF = '0.1.4'
ALIASED = ('rcac://context', 'rcac://storage')


def deltas(phase: str) -> tuple[str, ...]:
    if phase == 'p1':
        return ()
    out = tuple(f'resources.{u.replace("rcac://", "cluster://", 1)}' for u in ALIASED)
    return out + (('instructions',) if phase == 'p4' else ())


def expected(base: dict, phase: str) -> dict:
    fixture = json.loads(json.dumps(base))
    if phase == 'p1':
        return dict(sorted(fixture.items()))
    for uri in ALIASED:
        fixture['resources'][uri.replace('rcac://', 'cluster://', 1)] = dict(base['resources'][uri])
    if phase == 'p4':
        from harness import SITE
        from cluster_mcp.core.server import SERVER_INSTRUCTIONS
        from cluster_mcp.core.site import compose
        fixture['instructions'] = compose(SERVER_INSTRUCTIONS, SITE)
    return dict(sorted(fixture.items()))


def _paths(a: object, b: object, prefix: str = '') -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            out += _paths(a.get(key), b.get(key), f'{prefix}.{key}' if prefix else key)
        return out
    return [] if a == b else [prefix]


def main(argv: list[str]) -> int:
    mode, phase = argv
    if mode not in ('apply', 'check') or phase not in ('p1', 'p3', 'p4'):
        print('usage: fixture_deltas.py apply|check p1|p3|p4', file=sys.stderr)
        return 2
    base = json.loads(subprocess.run(['git', 'show', f'{BASELINE_REF}:{FIXTURE}'], check=True,
                                     capture_output=True, text=True).stdout)
    want = expected(base, phase)
    if mode == 'apply':
        FIXTURE.write_text(json.dumps(want, indent=1, sort_keys=True) + '\n')
        return 0
    have = json.loads(FIXTURE.read_text())
    named = deltas(phase)
    def covered(p: str) -> bool:
        return any(p == d or p.startswith(d + '.') for d in named)
    changed = _paths(base, have)
    stray = [p for p in changed if not covered(p)]
    wrong = _paths(want, have)
    missing = [d for d in named if not any(p == d or p.startswith(d + '.') for p in changed)]
    if phase == 'p4' and want['instructions'] == base['instructions']:
        print('fixture_deltas: the composed instructions equal 0.1.4\'s; nothing was split', file=sys.stderr)
        missing.append('instructions')
    for p in stray:
        print(f'fixture_deltas: {p} differs from {BASELINE_REF} and is not a named delta', file=sys.stderr)
    for p in wrong:
        print(f'fixture_deltas: {p} is not what the named delta writes', file=sys.stderr)
    for d in missing:
        print(f'fixture_deltas: the delta {d} was not applied', file=sys.stderr)
    ok = not (stray or wrong or missing)
    print(f"fixture_deltas: {'ok' if ok else 'FAILED'} ({phase})", file=sys.stderr)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
