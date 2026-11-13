"""The F1 wrapper, run unchanged, with the two `docs final` controls re-run on the pre-fill AGENTS.md (F2).

The frozen `controls` mode's `docs final sound` and `docs final pending` controls build their data by
replacing `pending` in the staged `mutants budget` row. P5 fills that row with the measured baseline
by design, so once it is staged neither plant lands. `docs final sound` then checks the real row
against a made-up sentence, and `docs final pending` finds no `pending`. Both report BAD although
`docs --final` is sound.

This wrapper:
  1. runs `remediation/F1-controls-anchor.py` unchanged. In F1's own findings it accepts exactly the
     BADs of those two controls, and only while the staged row holds no `pending`. Any other BAD or
     FAILED line of F1's own is red, and so is a frozen BAD outside F1's stale control and these two;
  2. re-runs those two controls exactly as the frozen mode builds them, on AGENTS.md as of
     `PREFILL`, the last commit before the row was filled. It asserts first that the row and the
     bullet occur once and that the plant lands exactly once. Red if either control still fails
     there.

Run from the cycle worktree root, after staging (it reads the index and one commit, as the gate does):

    UV_PYTHON=3.14 uv run -q python -I spec/mutants-workflow-timeout/remediation/F2-docs-controls-prefill.py

Footprint: F1 (the gate's `controls` mode, then two in-process checks), then two in-process calls of
the gate's own `docs_violations`. A few seconds.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'verify' / 'mutants-gate.py'
F1 = HERE / 'F1-controls-anchor.py'
# The P5 Run A commit: the last commit whose `mutants budget` row still reads `Baseline: pending`.
PREFILL = '36bd540'
STALE = ('docs final sound', 'docs final pending')
F1_STALE = 'untouched run_child'
# The frozen mode's own data for these two controls (verify/mutants-gate.py, mode_controls).
SENTENCE = ('1,164 cases in 78 shards, the run 8:30 from dispatch, slowest job 3:41 (14.7 s a case with its setup, '
            'over its 15 cases); worst')
COST = ' 1,164 cases in 78 shards, the run 8:30 from dispatch, slowest job 3:41 '

spec = importlib.util.spec_from_file_location('mutants_gate', GATE)
gate = importlib.util.module_from_spec(spec)
sys.modules['mutants_gate'] = gate
spec.loader.exec_module(gate)  # type: ignore[union-attr]


def accepted_lines() -> set[str]:
    return {f'FAILED  frozen control {label}: BAD' for label in STALE}


def f1_findings(row_pending: bool) -> list[str]:
    """Run F1 unchanged; return every result it reports beyond the two stale docs controls."""
    ran = subprocess.run([sys.executable, '-I', str(F1)], capture_output=True, text=True)
    sys.stdout.write(ran.stdout)
    sys.stderr.write(ran.stderr)
    lines = ran.stdout.splitlines()
    ends = [i for i, line in enumerate(lines) if re.match(r'^controls: ', line)]
    if not ends:
        return ["F1 printed no frozen summary line ('controls: ...')"]
    frozen, own = lines[:ends[-1] + 1], lines[ends[-1] + 1:]
    found = []
    frozen_bad = {m.group(1) for line in frozen if (m := re.match(r'^BAD (.+?): ', line))}
    found += [f'frozen control {label}: BAD' for label in sorted(frozen_bad - {F1_STALE, *STALE})]
    allowed = accepted_lines()
    for line in own:
        if line.startswith('BAD '):
            found.append(f'F1: {line}')
        elif line.startswith('FAILED  '):
            stale = line in allowed or any(line.startswith(f'FAILED  frozen: control {label}: ') for label in STALE)
            if not stale:
                found.append(f'F1: {line[8:]}')
            elif row_pending:
                found.append(f'F1: {line[8:]} (the staged row still holds `pending`, so its plant should land)')
    summary = [line for line in own if line.startswith('controls (re-anchored): ')]
    if len(summary) != 1:
        found.append('F1 printed no summary line')
    if ran.returncode not in (0, 1):
        found.append(f'F1 exited {ran.returncode}')
    if ran.returncode == 0 and any(line.startswith('FAILED  ') for line in own):
        found.append('F1 exited 0 naming a failure')
    return found


def prefill_controls(runner: str) -> list[str]:
    """The two stale controls, built as the frozen mode builds them, on AGENTS.md as of PREFILL."""
    agents = gate.at(PREFILL, 'AGENTS.md')
    if not agents:
        return [f'AGENTS.md at {PREFILL} could not be read']
    row, bullet = gate.budget_row(agents), gate.testing_bullet(agents)
    found = []
    if not row or agents.count(row) != 1:
        found.append(f'the `mutants budget` row at {PREFILL} is missing or not unique')
    if not bullet or agents.count(bullet) != 1:
        found.append(f'the § Testing bullet at {PREFILL} is missing or not unique')
    if row.count('pending') != 1:
        found.append(f'the row at {PREFILL} holds `pending` {row.count("pending")} times, wanted once')
    if found:
        return found
    filled = agents.replace(row, row.replace('pending', SENTENCE))
    if filled == agents or filled.count(SENTENCE) != agents.count(SENTENCE) + 1 or filled.count(bullet) != 1:
        return ['the docs final plant did not land exactly once']
    sound = gate.docs_violations(filled.replace(bullet, bullet + COST), runner, True, SENTENCE)
    print(f'{"ok " if not sound else "BAD"} docs final sound, on the pre-fill AGENTS.md: {sound[:2] or "sound data accepted"}')
    if sound:
        found.append(f'control docs final sound (pre-fill): {sound}, wanted none')
    pending = gate.docs_violations(agents, runner, True, SENTENCE)
    hit = any('pending' in v for v in pending)
    print(f'{"ok " if hit else "BAD"} docs final pending, on the pre-fill AGENTS.md: {pending[:2]}')
    if not hit:
        found.append(f'control docs final pending (pre-fill): {pending}, wanted pending')
    return found


def main() -> int:
    row_pending = 'pending' in gate.budget_row(gate.staged('AGENTS.md'))
    found = f1_findings(row_pending) + prefill_controls(gate.staged(gate.RUNNER))
    for line in found:
        print(f'FAILED  {line}')
    print(f'controls (re-anchored, pre-fill docs): {"ok" if not found else f"{len(found)} failed"}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
