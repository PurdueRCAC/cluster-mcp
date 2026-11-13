"""The frozen `controls` gate, run unchanged, with its one `run_child` control re-anchored (rebase, F1).

After the rebase onto develop at 2719b7a, the sibling cycle's `run_child` no longer holds the text
`timeout=300)`: it waits with `proc.communicate(timeout=LIMIT)`. The frozen `controls` mode's
"untouched run_child" control plants `timeout=300)` -> `timeout=600)`, which now changes nothing, so
that control sees no violation and reports BAD although the `untouched` check is sound.

This wrapper:
  1. runs `verify/mutants-gate.py controls` unchanged, and accepts its result only if every BAD
     line is that one control, and only because its plant missed (its anchor occurs nowhere in the
     staged runner); any other BAD or FAILED line is red;
  2. re-runs that control with plants that land, each anchor required exactly once in the staged
     runner and the planted text read back changed:
       - `communicate(timeout=LIMIT)` -> `communicate(timeout=600)`, wanted "run_child changed";
       - `LIMIT = 300` -> `LIMIT = 600`, wanted "LIMIT changed".

Run from the cycle worktree root, after staging (it reads the index, as the gate does):

    UV_PYTHON=3.14 uv run -q python -I spec/mutants-workflow-timeout/remediation/F1-controls-anchor.py

Footprint: the gate's `controls` mode (one process, in-process checks and git reads), then two
in-process calls of the gate's own `untouched_violations`. A few seconds.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / 'verify' / 'mutants-gate.py'
STALE_LABEL = 'untouched run_child'
STALE_ANCHOR = 'timeout=300)'
PLANTS = (
    ('untouched run_child, re-anchored', 'communicate(timeout=LIMIT)', 'communicate(timeout=600)', 'run_child changed'),
    ('untouched LIMIT', 'LIMIT = 300\n', 'LIMIT = 600\n', 'LIMIT changed'),
)

spec = importlib.util.spec_from_file_location('mutants_gate', GATE)
gate = importlib.util.module_from_spec(spec)
sys.modules['mutants_gate'] = gate
spec.loader.exec_module(gate)  # type: ignore[union-attr]


def frozen_controls(runner: str) -> list[str]:
    """Run the frozen mode unchanged; return every result it reports other than the one stale control."""
    ran = subprocess.run([sys.executable, '-I', str(GATE), 'controls'], capture_output=True, text=True)
    sys.stdout.write(ran.stdout)
    sys.stderr.write(ran.stderr)
    bad = [m.group(1) for m in re.finditer(r'^BAD (.+?): ', ran.stdout, re.M)]
    failed = [line for line in ran.stdout.splitlines() if line.startswith('FAILED  ')]
    oks = [line for line in ran.stdout.splitlines() if line.startswith('ok ')]
    found = []
    if not oks:
        found.append('the frozen controls mode reported no control at all')
    found += [f'frozen control {label}: BAD' for label in bad if label != STALE_LABEL]
    found += [f'frozen: {line[8:]}' for line in failed if not line.startswith(f'FAILED  control {STALE_LABEL}: ')]
    if STALE_LABEL in bad and runner.count(STALE_ANCHOR) != 0:
        found.append(f'frozen control {STALE_LABEL}: BAD although its anchor {STALE_ANCHOR!r} is in the runner')
    if ran.returncode not in (0, 1):
        found.append(f'the frozen controls mode exited {ran.returncode}')
    if ran.returncode == 1 and not failed:
        found.append('the frozen controls mode exited 1 naming no failure')
    return found


def replanted(old: str, new: str, rows_old: str, rows_new: str) -> list[str]:
    """The stale control's plants, re-anchored on text the staged runner holds once."""
    found = []
    sound = gate.untouched_violations(old, new, rows_old, rows_new, {gate.RUNNER}, 1)
    print(f'{"ok " if not sound else "BAD"} untouched sound (re-run): {sound[:2] or "sound data accepted"}')
    if sound:
        found.append(f'control untouched sound: {sound}')
    for label, anchor, plant, why in PLANTS:
        count = new.count(anchor)
        if count != 1:
            found.append(f'control {label}: its anchor {anchor!r} occurs {count} times in the staged runner, wanted once')
            continue
        mutated = new.replace(anchor, plant)
        if mutated == new or mutated.count(plant) != new.count(plant) + 1:
            found.append(f'control {label}: the plant did not land')
            continue
        violations = gate.untouched_violations(old, mutated, rows_old, rows_new, {gate.RUNNER}, 1)
        hit = any(why in v for v in violations)
        print(f'{"ok " if hit else "BAD"} {label}: {violations[:2]}')
        if not hit:
            found.append(f'control {label}: {violations}, wanted {why}')
    return found


def main() -> int:
    b = gate.base()
    old, new = gate.at(b, gate.RUNNER), gate.staged(gate.RUNNER)
    rows_old, rows_new = gate.at(b, gate.OLD_ROWS), gate.staged(gate.OLD_ROWS)
    found = frozen_controls(new) + replanted(old, new, rows_old, rows_new)
    for line in found:
        print(f'FAILED  {line}')
    print(f'controls (re-anchored): {"ok" if not found else f"{len(found)} failed"}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
