"""Review cycle 1, F5: a clarification id (`Q#`) is a feature-scoped spec id, kept out of the code like `R#` and `P#`.

    uv run python -I spec/timeout-process-cleanup/remediation/F5-clarification-ids.py      from the worktree root

The property is the suite's own check, `tests/test_hygiene.py`'s `spec_id_violations`, evaluated
where a `Q#` can hide: it must flag the comment review cycle 1 found (`tests/mutants.py` at the
reviewed commit, which named a clarification) and a planted `Q3` in a comment, a docstring and a
message, flag nothing in today's package and suite, and flag none of the look-alikes that are not
ids (`Q100`, `QUIT`, `SIGQUIT`, `IQ3`, `Q3PO`). Then the suite's hygiene rows run. Footprint: one
process and one pytest child, seconds.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path('tests').resolve()))

from test_hygiene import namespace_portions, spec_id_violations  # noqa: E402

REVIEWED = '386efa3'
PLANTED = ('# As the GOAL rules (Q3), the stop waits.', '"""Settled by Q3."""', "raise ValueError('see Q3')")
LOOK_ALIKES = ('x = "Q100 QUIT SIGQUIT IQ3 Q3PO"', 'signal.SIGQUIT', "kill -s QUIT 0")


def main() -> int:
    problems = []
    reviewed = subprocess.run(['git', 'show', f'{REVIEWED}:tests/mutants.py'], check=True, capture_output=True,
                              text=True).stdout
    if not any('Q6' in v for v in spec_id_violations('reviewed', reviewed)):
        problems.append(f'the comment naming a clarification in {REVIEWED}\'s tests/mutants.py is not flagged')
    problems += [f'not flagged: {text!r}' for text in PLANTED if not spec_id_violations('planted', text)]
    problems += [f'flagged, though no id: {text!r}' for text in LOOK_ALIKES if spec_id_violations('look-alike', text)]
    files = [f for portion in namespace_portions() for f in sorted(portion.rglob('*.py'))]
    files += sorted(Path('tests').resolve().glob('*.py'))
    problems += [v for f in files for v in spec_id_violations(str(f), f.read_text())]
    code = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'tests/test_hygiene.py',
                           '-k', 'spec_id']).returncode
    if code:
        problems.append(f'the hygiene rows failed (exit {code})')
    print('\n'.join(problems) or f'F5: Q# flagged where planted and at {REVIEWED}, nowhere in {len(files)} files '
                                 'today, never on a look-alike')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
