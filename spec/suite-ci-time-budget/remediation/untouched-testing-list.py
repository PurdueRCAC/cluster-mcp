# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The frozen `untouched` and `controls` modes, run unedited but for one region a review opened.

Review cycle 1, F-A, routed the fix of § Testing's per-module list ("Every module is built around
pure check functions", its `  - ` sub-bullets) into AGENTS.md. The frozen gate's `untouched` mode
allows AGENTS.md changes only in four regions (the profile, the recipe, the CI bullet, the era
bullet), so the ruled fix turns it red by construction, and with it the `controls` mode's
"untouched sound" case, which feeds the staged AGENTS.md to the same check. This wrapper loads
`verify/suite-gate.py` from its file, unedited, adds exactly that list as a fifth region, and runs
the mode named (`untouched` when none is). Everything else the modes check (the files changed, the
new module's imports and import-time body, the profile rows, the ci row's landing rule, the recipe
beyond its gate, AGENTS.md outside the five regions, and every other control) is decided by the
frozen code.

The region is bounded and must match once in both the base's text and the staged text: it starts at
the list's first sub-bullet and ends before the next top-level bullet of § Testing. The wrapper
refuses to run if either text lacks it, so a reshaped section can never widen what the mode skips.

Run from the cycle worktree root, after staging:

    UV_PYTHON=3.14 uv run -q --with pyyaml python -I spec/suite-ci-time-budget/remediation/untouched-testing-list.py [untouched|controls]
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / 'verify' / 'suite-gate.py'
# From the first `  - ` sub-bullet after the list's lead sentence to the next top-level bullet.
LIST = r'(?<=breaks a gate loudly\. Each check\n  has standing negative controls, planted shapes it must reject\.\n)  - `tests/.*?(?=^- )'


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'untouched'
    if mode not in ('untouched', 'controls') or len(sys.argv) > 2:
        raise SystemExit('untouched-testing-list: the mode is untouched or controls')
    spec = importlib.util.spec_from_file_location('suite_gate', GATE)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    if not Path('AGENTS.md').is_file() or not Path(f'spec/{gate.SLUG}').is_dir():
        raise SystemExit('untouched-testing-list: run from the cycle worktree root')
    for label, text in (('base', gate.at(gate.BASE, 'AGENTS.md')), ('staged', gate.staged('AGENTS.md'))):
        found = re.findall(LIST, text, re.M | re.S)
        if len(found) != 1 or not found[0].rstrip().endswith('.') or '\n- ' in found[0]:
            raise SystemExit(f'untouched-testing-list: the {label} AGENTS.md does not hold the per-module list once')
        print(f'untouched-testing-list: {label} list region, {found[0].count(chr(10))} lines')
    gate.AGENTS_REGIONS.append(LIST)
    found = gate.mode_untouched() if mode == 'untouched' else gate.mode_controls()
    print('\n'.join(found) if found else f'suite-gate {mode} (with the per-module list region): ok')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
