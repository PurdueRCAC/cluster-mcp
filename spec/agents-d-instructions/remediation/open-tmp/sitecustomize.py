# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Run a frozen gate with every temporary directory open to every account (review 2, GOAL C12).

`CLUSTER_MCP_OPEN_TMP=1 PYTHONPATH=spec/agents-d-instructions/remediation/open-tmp sh <gate>`: each
Python the gate starts makes its temporary directories under `/tmp` (mode 1777 on Linux and macOS),
at mode 755. The frozen `verify/serve_gate.py` serves a planted directory in `delegate` mode and
expects its files; under C12 as amended on 2026-10-23 that holds only where every account can
reach the directory, and `tempfile`'s own directory (mode 700, under a per-user `TMPDIR` on macOS)
is reachable by its owner alone. Nothing else about the gate changes: `verify/` stays as frozen.
"""

import os
import tempfile

if os.environ.get('CLUSTER_MCP_OPEN_TMP'):
    tempfile.tempdir = '/tmp'
    _made = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        path = _made(*args, **kwargs)
        os.chmod(path, 0o755)
        return path

    tempfile.mkdtemp = mkdtemp
