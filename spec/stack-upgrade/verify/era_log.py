"""Prove a suite or mutation pass really ran in the era it selected.

Usage: python era_log.py <log> <legacy|modern> <minimum>

The harness appends one line per in-process client connect to `$CLUSTER_MCP_ERA_LOG`:
`era=<selected> version=<negotiated protocol version> first=<first method the server saw on that
connection>` (the server side is read from the harness's method log, not from the client). A pass
is accepted only when it wrote at least `minimum` lines and every line agrees with the era: modern →
`version=2026-07-28 first=server/discover`; legacy → a handshake version and `first=initialize`. A
harness that ignored the selector, or a client pinned to a version (which sends no
`server/discover`), fails here even when every test passed.
"""

from __future__ import annotations

import sys
from pathlib import Path

MODERN = '2026-07-28'


def era_log_violations(lines: list[str], era: str, minimum: int) -> list[str]:
    """Every way `lines` fails to prove a pass in `era`; empty means proven."""
    violations: list[str] = []
    rows = [line.split() for line in lines if line.strip()]
    if len(rows) < minimum:
        violations.append(f'{len(rows)} connects logged, expected at least {minimum}')
    for number, fields in enumerate(rows, 1):
        row = dict(field.split('=', 1) for field in fields if '=' in field)
        selected, version, first = row.get('era'), row.get('version'), row.get('first')
        if selected != era:
            violations.append(f'line {number}: era={selected}, expected {era}')
        if era == 'modern' and (version != MODERN or first != 'server/discover'):
            violations.append(f'line {number}: version={version} first={first}, expected {MODERN} via server/discover')
        if era == 'legacy' and (version in (None, MODERN) or first != 'initialize'):
            violations.append(f'line {number}: version={version} first={first}, expected a handshake via initialize')
    return violations


def main() -> int:
    log, era, minimum = sys.argv[1], sys.argv[2], int(sys.argv[3])
    path = Path(log)
    lines = path.read_text().splitlines() if path.exists() else []
    violations = era_log_violations(lines, era, minimum)
    for v in violations[:20]:
        print(f'era_log: {v}', file=sys.stderr)
    print(f'era_log: {len(lines)} connects, era {era}, {len(violations)} violations', file=sys.stderr)
    return 1 if violations else 0


if __name__ == '__main__':
    sys.exit(main())
