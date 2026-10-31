# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Compare the 0.1.4 listings baseline.sh wrote with this tree's. Usage: compare.py p1|p3|p4 DIR REPLANTS."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


def functions(path: Path) -> Counter:
    return Counter(re.sub(r'\[.*$', '', line.strip()) for line in path.read_text().splitlines() if '::' in line)


# What the move itself changes in a case: its file (namespace-relative now) and the module path in
# its text. Anything else that differs must be named in replants.txt.
MODULES = (('rcac_mcp.tools.rcac', 'cluster_mcp.rcac.tools'), ('rcac_mcp.tools.slurm', 'cluster_mcp.slurm.tools'),
           ('rcac_mcp', 'cluster_mcp.core'))


def moved(text: str) -> str:
    for old, new in MODULES:
        text = text.replace(old, new)
    return text


def files_for(base_file: str) -> set[str]:
    if base_file == 'tools/slurm.py':
        return {'slurm/tools.py', 'rcac/tools.py'}
    if base_file == 'tools/rcac.py':
        return {'rcac/tools.py'}
    return {f'core/{base_file}'}


def read_replants(path: Path, phase: str) -> set[str]:
    order = ['p1', 'p2', 'p3', 'p4']
    allowed = set()
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        case, at, reason = (line.split('\t') + ['', ''])[:3]
        if at not in order or not reason.strip():
            raise SystemExit(f'replants.txt: {line!r} needs a case id, a phase and a reason, tab-separated')
        if order.index(at) <= order.index(phase if phase in order else 'p4'):
            allowed.add(case)
    return allowed


def compare_cases(base: list[dict], head: list[dict], replants: set[str]) -> list[str]:
    found = []
    if len(base) < 300:
        found.append(f'the baseline listed only {len(base)} mutation cases')
    by_id = {c['id']: c for c in head}
    for b in base:
        h = by_id.get(b['id'])
        if h is None:
            found.append(f'mutation case {b["id"]} is gone')
            continue
        if h['file'] not in files_for(b['file']):
            found.append(f'mutation case {b["id"]}: plants into {h["file"]}, expected one of {sorted(files_for(b["file"]))}')
        if b['id'] not in replants:
            if [list(map(moved, e)) for e in b['edits']] != [list(e) for e in h['edits']]:
                found.append(f'mutation case {b["id"]}: its plant changed beyond the module move (replants.txt names none)')
            if moved(b['why']) != h['why']:
                found.append(f'mutation case {b["id"]}: why changed from {b["why"]!r} to {h["why"]!r}')
        fns = {re.sub(r'\[.*$', '', t) for t in h['targets']}
        for t in b['targets']:
            if re.sub(r'\[.*$', '', t) not in fns:
                found.append(f'mutation case {b["id"]}: no longer targets {t}')
    return found


def compare(phase: str, d: Path, replants: set[str]) -> list[str]:
    found = []
    base, head = functions(d / 'base-ids.txt'), functions(d / 'head-ids.txt')
    if sum(base.values()) < 1000:
        found.append(f'the baseline collected only {sum(base.values())} ids: the 0.1.4 listing failed')
    for fn, n in sorted(base.items()):
        if head[fn] < n:
            found.append(f'test {fn}: {n} ids at 0.1.4, {head[fn]} here')
    found += compare_cases(json.loads((d / 'base-cases.json').read_text()),
                           json.loads((d / 'head-cases.json').read_text()), replants)
    bs = json.loads((d / 'base-surface.json').read_text())
    hs = json.loads((d / 'head-surface.json').read_text())
    if len(bs['tools']) < 20:
        found.append(f'the baseline served only {len(bs["tools"])} tools')
    if bs['tools'] != hs['tools']:
        bt, ht = {t['name']: t for t in bs['tools']}, {t['name']: t for t in hs['tools']}
        found += [f'tool {n} is gone' for n in bt.keys() - ht.keys()]
        found += [f'tool {n} is new' for n in ht.keys() - bt.keys()]
        found += [f'tool {n} differs in {k}' for n in bt.keys() & ht.keys() for k in bt[n] if bt[n][k] != ht[n].get(k)]
    if phase == 'p1':
        if bs['resources'] != hs['resources']:
            found.append(f'resources changed: {hs["resources"]}')
    else:
        want = []
        for r in bs['resources']:
            if not r['uri'].startswith('rcac://'):
                found.append(f'baseline resource {r["uri"]} is not rcac://')
            want += [r, {**r, 'uri': r['uri'].replace('rcac://', 'cluster://', 1)}]
        if sorted(want, key=lambda r: r['uri']) != hs['resources']:
            found.append(f'resources are {hs["resources"]}, expected each 0.1.4 entry and its cluster:// twin')
    if phase == 'p4' and hs['server_name'] != 'cluster-mcp':
        found.append(f'server name is {hs["server_name"]!r}')
    return found


if __name__ == '__main__':
    problems = compare(sys.argv[1], Path(sys.argv[2]), read_replants(Path(sys.argv[3]), sys.argv[1]))
    for p in problems:
        print(f'baseline: {p}', file=sys.stderr)
    print('baseline: ok' if not problems else f'baseline: {len(problems)} problems', file=sys.stderr)
    sys.exit(1 if problems else 0)
