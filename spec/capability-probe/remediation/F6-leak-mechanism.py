# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 2, F2: every record of the `local` leak states the mechanism the code shows, and the
seed's sketch covers a normal exit.

    uv run python -I spec/capability-probe/remediation/F6-leak-mechanism.py      from the worktree root

The seed's 2026-11-01 note said the `local` executor's timeout "sends SIGTERM only"; `run_process`
sends SIGTERM, reads for `GRACE`, then sends SIGKILL, and the leak on a normal exit is the probe's
daemon worker, abandoned at the deadline, cut off by the interpreter's exit before its SIGKILL (the
review's F2). The facts are read from the code, not restated here:

- the signals `run_process`'s timeout sends, in order (the tuple its loop walks), and that it reads
  for `GRACE` after each;
- that the probe's worker thread is a daemon (`core/probes.py`).

A record of the leak is the seed, every paragraph or list item of a live file outside `spec/` that
links it (tracked: `ROADMAP.md`, `AGENTS.md`, other seeds), and the ROADMAP entry's whole section. Each must:

- never say the timeout sends one signal "only", nor name SIGTERM as the timeout's last signal;
- where it states the timeout's signals, name them in the code's order.

The seed must also state the normal-exit mechanism (the daemon worker, the interpreter's exit,
`GRACE`, SIGKILL), and its R1 sketch must name a normal exit and both the probe and a tool call. The
ROADMAP entry must name a normal exit. Footprint: one process, under 100 MB, no network.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
CORE = ROOT / 'packages/cluster-mcp/src/cluster_mcp/core'
SEED = 'issues/local-command-outlives-server.md'
ONLY = re.compile(r'\b(SIG)?(TERM|KILL)\s+only\b|\bonly\s+(SIG)?(TERM|KILL)\b', re.I)
SIGNAL = re.compile(r'\bSIG(TERM|KILL)\b')


def timeout_signals() -> list[str]:
    """The signals `run_process` sends at its deadline, in the order its loop walks them."""
    module = ast.parse((CORE / 'executor/launch.py').read_text())
    run = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'run_process')
    loops = [n for n in ast.walk(run) if isinstance(n, ast.For) and isinstance(n.iter, ast.Tuple)
             and all(isinstance(e, ast.Attribute) and e.attr.startswith('SIG') for e in n.iter.elts)]
    if len(loops) != 1:
        raise SystemExit(f'run_process: expected one loop over signals, found {len(loops)}')
    loop = loops[0]
    if 'GRACE' not in ast.unparse(loop):
        raise SystemExit('run_process: the signal loop no longer reads for GRACE after each signal')
    return [e.attr for e in loop.iter.elts]


def worker_is_daemon() -> bool:
    text = (CORE / 'probes.py').read_text()
    return bool(re.search(r'threading\.Thread\([^)]*daemon=True', text))


def blocks(text: str) -> list[str]:
    """Paragraphs and list items, each one string with its whitespace collapsed."""
    out, cur = [], []
    for line in text.splitlines():
        if not line.strip() or re.match(r'\s*([-*]|\d+\.)\s', line) or line.startswith('#'):
            if cur:
                out.append(' '.join(' '.join(cur).split()))
            cur = [line] if line.strip() and not line.startswith('#') else []
        else:
            cur.append(line)
    if cur:
        out.append(' '.join(' '.join(cur).split()))
    return out


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find('\n## ', start + 1)
    return text[start:end if end > 0 else len(text)]


def live_files() -> list[Path]:
    """Every tracked Markdown file outside `spec/`."""
    listed = subprocess.run(['git', 'ls-files', '-z', '--', '*.md'], cwd=ROOT, capture_output=True, check=True).stdout
    names = [n for n in listed.decode().split('\0') if n and not n.startswith('spec/')]
    return [ROOT / n for n in sorted(names)]


def main() -> int:
    signals = timeout_signals()
    bad: list[str] = []
    if signals != ['SIGTERM', 'SIGKILL']:
        bad.append(f'run_process sends {signals} at its deadline; this check knows SIGTERM then SIGKILL')
    if not worker_is_daemon():
        bad.append('core/probes.py: the probe worker is no longer a daemon thread; the seed describes one')
    records: list[tuple[str, str]] = []
    for f in live_files():
        rel = str(f.relative_to(ROOT))
        text = f.read_text()
        if rel == SEED:
            records += [(rel, b) for b in blocks(text)]
            continue
        records += [(rel, b) for b in blocks(text) if 'local-command-outlives-server' in b]
    roadmap = (ROOT / 'ROADMAP.md').read_text()
    entry = section(roadmap, '## A local command in flight')
    records += [('ROADMAP.md (entry)', b) for b in blocks(entry)]
    for where, b in records:
        if ONLY.search(b):
            bad.append(f'{where}: says a signal "only": {b[:160]}')
        named = [f'SIG{m}' for m in SIGNAL.findall(b)]
        if set(signals) <= set(named) and named.index(signals[-1]) < named.index(signals[0]):
            bad.append(f'{where}: names {signals[-1]} before {signals[0]}: {b[:160]}')
    seed = ' '.join((ROOT / SEED).read_text().split())
    for need, what in ((r'daemon', 'the daemon worker'), (r'interpreter exits|interpreter\'s exit', 'the interpreter\'s exit'),
                       (r'`GRACE`', 'GRACE'), (r'SIGTERM[^.]*SIGKILL', 'SIGTERM, then SIGKILL'),
                       (r'normal', 'a normal exit')):
        if not re.search(need, seed):
            bad.append(f'{SEED}: does not state {what}')
    r1 = re.search(r'\*\*R1\*\*(.*?)(?=\n## |\Z)', (ROOT / SEED).read_text(), re.S)
    r1_text = ' '.join(r1.group(1).split()) if r1 else ''
    for need, what in ((r'normally', 'a normal exit'), (r'probe', 'the startup probe'), (r'tool call', 'a tool call'),
                       (r'SIGTERM or SIGINT', 'the signals')):
        if not re.search(need, r1_text):
            bad.append(f'{SEED}: R1 does not name {what}')
    if not re.search(r'normally', ' '.join(entry.split())):
        bad.append('ROADMAP.md: the entry does not name a normal exit')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F6-leak-mechanism: ok ({len(records)} blocks of {len({w for w, _ in records})} records; '
              f'the timeout sends {" then ".join(signals)}, the worker is a daemon)', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
