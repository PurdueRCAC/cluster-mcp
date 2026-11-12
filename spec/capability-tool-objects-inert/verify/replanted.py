# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The mutation cases this cycle re-plants: every case of `tests/mutants.py` whose edits or targets
differ from develop's at the cycle start (`BASE_REF`), or that is new; and every case that plants
into `core/capabilities.py` with an edit inside `load()`, or that targets a `served-tool` row. The
cases of this cycle's own alternatives are left to `alternatives.py`, which runs them.

    uv run python -I spec/capability-tool-objects-inert/verify/replanted.py      from the worktree root

Prints the ids, space-separated, for `tests/mutants.py --self-check`; fails when there are none.
Footprint: one process, under 100 MB, seconds.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'tests'))
sys.path.insert(0, str(ROOT / 'spec/capability-tool-objects-inert/verify'))
import mutants  # noqa: E402
import alternatives  # noqa: E402

LOADER = 'core/capabilities.py'
BASE_REF = '238f86b'


def base_cases() -> dict[str, tuple]:
    """Each case of `tests/mutants.py` as develop held it at the cycle start: id -> (file, edits, targets)."""
    text = subprocess.run(['git', 'show', f'{BASE_REF}:tests/mutants.py'], capture_output=True, text=True,
                          check=True).stdout
    module = types.ModuleType('base_mutants')
    module.__file__ = str(ROOT / 'tests' / 'mutants.py')
    sys.modules['base_mutants'] = module
    exec(compile(text, 'base_mutants.py', 'exec'), module.__dict__)
    return {c.id: (c.file, c.edits, c.targets) for c in module.CASES}


def main() -> int:
    text = (alternatives.NAMESPACE / LOADER).read_text()
    load = alternatives.function(ast.parse(text), 'load')
    body = ast.get_source_segment(text, load) if load else ''
    own = set(alternatives.coverage('p1')[0])
    base = base_cases()
    ids = [c.id for c in mutants.CASES if c.id not in own
           and (base.get(c.id) != (c.file, c.edits, c.targets)
                or (c.file == LOADER and any(old in body for old, _ in c.edits))
                or any('served-tool' in t for t in c.targets))]
    if not ids:
        print('replanted: no case', file=sys.stderr)
        return 1
    print(f'replanted: {len(ids)} cases', file=sys.stderr)
    print(*ids)
    return 0


if __name__ == '__main__':
    sys.exit(main())
