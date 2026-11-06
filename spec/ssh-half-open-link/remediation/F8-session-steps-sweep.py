"""`verify/silent-sweep.py`, unchanged, with review cycle 1's F1 rows, review cycle 2's F-A rows and
review cycle 3's N2 rows added to its table.

Run from the worktree root, with the frozen gate's own arguments:

    uv run python -I spec/ssh-half-open-link/remediation/F8-session-steps-sweep.py legacy [1|2]
    uv run python -I spec/ssh-half-open-link/remediation/F8-session-steps-sweep.py modern [1|2]

Why: review cycle 3's N2 found the cap on `_sftp`'s `sftp` subsystem and version steps pinned only
behind `CLUSTER_MCP_TEST_EVERY_KIND=1`. Its pin is a unit row in the default suite, and the plant it
kills is two `shol-session-` cases in `tests/mutants.py`. The frozen gate checks its table against
`tests/mutants.py` both ways, so with those cases planted it reads them as cases the sweep does not
name, and is red for that alone, as it was for the earlier cycles' cases.

What changes: `remediation/F5-late-reconnect-sweep.py` runs as it is (and it runs
`remediation/F1-send-path-sweep.py` as that is), and the gate it loads has the rows below appended
to its `SWEEP` first. Every earlier row, the both-ways check, the halves (split by sorted id), each
case reported killed and each equivalent shown are the gate's own.

Footprint: the frozen gate's, which it imports from its file and runs in this process.
"""

from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
F5_WRAPPER = os.path.join(HERE, 'F5-late-reconnect-sweep.py')

# Review cycle 3, N2: where an SFTP session opened after a reconnect makes its three steps.
ROWS = [
    ('the steps an SFTP session after a reconnect makes on its worker (`_sftp`)',
     'the channel only, the `sftp` subsystem and the version exchange on the call\'s thread',
     'shol-session-channel-only-on-the-worker'),
    ('the steps an SFTP session after a reconnect makes on its worker (`_sftp`)',
     'the channel and the subsystem, the version exchange on the call\'s thread',
     'shol-session-version-on-the-call'),
]


def _module(name: str, path: str) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f'cannot load {path}'
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    f5 = _module('f5_late_reconnect_sweep', F5_WRAPPER)
    rows = f5._rows

    def extended(gate: object) -> list[tuple[str, str, object]]:
        return rows(gate) + ROWS

    f5._rows = extended
    return f5.main(argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:3]) if len(sys.argv) in (2, 3) else main(['']))
