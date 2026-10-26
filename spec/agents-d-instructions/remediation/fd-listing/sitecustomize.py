# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Run a frozen gate's shim with a directory listed by its descriptor (review 3, GOAL C13).

`CLUSTER_MCP_FD_LISTING=1 PYTHONPATH=spec/agents-d-instructions/remediation/fd-listing <command>`:
in the frozen shim's process (and no other), `os.fspath` given a descriptor returns the path that
descriptor names, as `F_GETPATH` (macOS) or `/proc/self/fd` (Linux) report it. The frozen
`verify/serve_shim.py` logs every listing of the planted directory by passing the listed argument to
`os.fspath`, which refuses a descriptor; since review 3 the read for every account (`delegate` mode)
lists the directory it checked by its descriptor, so without this the shim's own logger raises
(`TypeError`) and the server serves that error's line. With it, the shim sees and logs that listing
as a listing of the planted directory, as it was meant to. No assertion of any gate changes, and
`verify/` stays as frozen.

With `CLUSTER_MCP_OPEN_TMP` set too, `remediation/open-tmp`'s customization applies as well (one
`sitecustomize` loads per Python).
"""

import os
import runpy
import sys

if os.environ.get('CLUSTER_MCP_OPEN_TMP'):
    runpy.run_path(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'open-tmp',
                                'sitecustomize.py'))

if os.environ.get('CLUSTER_MCP_FD_LISTING') and sys.argv[0].endswith('serve_shim.py'):
    _fspath = os.fspath

    def _named(fd: int) -> str:
        if sys.platform == 'darwin':
            import fcntl
            return fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b'\0', 1)[0].decode()
        return os.readlink(f'/proc/self/fd/{fd}')

    def fspath(path):
        if isinstance(path, int) and not isinstance(path, bool):
            return _named(path)
        return _fspath(path)

    os.fspath = fspath
