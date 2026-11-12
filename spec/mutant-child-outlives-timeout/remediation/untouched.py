"""The frozen `untouched` gate, run with one more AGENTS.md entry allowed to change (review cycle 1, F1).

Review cycle 1's F1 asks § Testing's `tests/test_mutations.py` entry to say what the module now holds
(an `integration` row besides the unit rows). The frozen gate allows AGENTS.md to change only inside
the mutation-runner bullet, so it refuses that entry. This wrapper runs `verify/gate.py`'s `untouched`
mode unchanged except that the AGENTS.md comparison also cuts that one entry from both sides; every
other check of the mode (the file list, the runner's statements, the test module's BASE rows) is the
gate's own. Its controls show the widened cut still refuses an AGENTS.md change anywhere else.

    UV_PYTHON=3.14 uv run python -I spec/mutant-child-outlives-timeout/remediation/untouched.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / 'verify' / 'gate.py'
ENTRY = '  - `tests/test_mutations.py` ('

spec = importlib.util.spec_from_file_location('gate', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)  # type: ignore[union-attr]
frozen_cut = gate.bullet_cut


def entry_cut(agents: str) -> str:
    """Cut the mutation-runner bullet (the gate's own cut), then the one `tests/test_mutations.py` entry."""
    text = frozen_cut(agents)
    if text.count(ENTRY) != 1:
        raise SystemExit(f'remediation/untouched.py: {text.count(ENTRY)} § Testing entries for tests/test_mutations.py, expected one')
    start = text.index(ENTRY)
    end = text.index('\n  - `', start + len(ENTRY))
    return text[:start] + text[end + 1:]


def controls() -> list[str]:
    base = gate.at(gate.BASE, 'AGENTS.md')
    entry = base.replace('the fast half of the mutation runner', 'the suite half of the mutation runner', 1)
    elsewhere = entry.replace('## Packaging', '## Packaging!', 1)
    found = []
    checks = [('entry edit accepted', entry, None), ('edit elsewhere refused', elsewhere, 'outside the mutation-runner bullet')]
    for label, head, why in checks:
        got = gate.untouched_violations([('M', 'AGENTS.md')], base, head, '', None)
        hit = any(why in v for v in got) if why else got == []
        print(f'{"ok " if hit else "BAD"} {label}: {got[:1]}')
        if not hit or head == base:
            found.append(f'control {label}: {got}')
    return found


def main() -> int:
    gate.bullet_cut = entry_cut
    found = controls()
    if found:
        for line in found:
            print(f'FAIL {line}')
        print('red  remediation untouched controls')
        return 1
    return gate.main(['untouched'])


if __name__ == '__main__':
    sys.exit(main())
