# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Nothing the suite had before the cycle is lost: its test functions and its mutation cases.

    python kept.py BASE_IDS HEAD_IDS BASE_CASES HEAD_CASES RETIRED      run by baseline.sh

BASE_IDS and HEAD_IDS are `pytest --collect-only -q` listings; for every test function BASE_REF
collected (file::function, parameters dropped), HEAD must collect at least one id under the same
file and function. BASE_CASES and HEAD_CASES are the mutation case ids, one per line; every BASE
case id must still be a case. RETIRED (verify/retired.txt) names, one per line as `<id> — <reason>`,
each test function or case id this cycle retires on purpose, the reason opening with the phase
that retires it (`P3: …`); a retired name that BASE never had,
or one still present in HEAD, is itself an error, so the list cannot hide anything. Footprint: one
process, no network, under 50 MB.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def functions(path: str) -> set[str]:
    return {re.sub(r'\[.*$', '', line.strip()) for line in Path(path).read_text().splitlines() if '::' in line}


def lines(path: str) -> set[str]:
    return {line.strip() for line in Path(path).read_text().splitlines() if line.strip()}


def main() -> int:
    if len(sys.argv) != 6:
        raise SystemExit('usage: kept.py BASE_IDS HEAD_IDS BASE_CASES HEAD_CASES RETIRED')
    base_f, head_f = functions(sys.argv[1]), functions(sys.argv[2])
    base_c, head_c = lines(sys.argv[3]), lines(sys.argv[4])
    retired: dict[str, str] = {}
    for line in lines(sys.argv[5]) if Path(sys.argv[5]).exists() else set():
        if line.startswith('#'):
            continue
        name, sep, why = line.partition(' — ')
        if not sep or not re.match(r'P[0-9]+: \S', why.strip()):
            raise SystemExit(f'kept: retired.txt line without a phase and a reason: {line!r}')
        retired[name.strip()] = why.strip()
    if len(base_f) < 100 or len(base_c) < 20:
        raise SystemExit(f'kept: only {len(base_f)} base functions and {len(base_c)} base cases: the check would be blind')
    bad = []
    for name in sorted(base_f - head_f):
        if name not in retired:
            bad.append(f'test function lost: {name}')
    for name in sorted(base_c - head_c):
        if name not in retired:
            bad.append(f'mutation case lost: {name}')
    for name in sorted(retired):
        if name not in base_f and name not in base_c:
            bad.append(f'retired.txt names {name}, which the suite never had')
        elif name in head_f or name in head_c:
            bad.append(f'retired.txt names {name}, which is still there')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'kept: ok ({len(base_f)} functions, {len(base_c)} cases; {len(retired)} retired)', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
