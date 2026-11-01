# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Write the EXPECT.json served.py checks against, for the named parts in composition order.

    python expect.py OUT.json PART…        PART is core, slurm, rcac or planted

The tool and resource sets are pinned here from GOAL.md (R4's core tools, the Slurm member's seven,
the RCAC member's ten with the storage URIs); each part's text is read from its instructions module
in the full development environment (the planted part's text and its one resource,
`cluster://planted`, from planted.sh), so the order
of the PART arguments is the order the base must take. Footprint: one process, under 100 MB.
"""

from __future__ import annotations

import json
import sys

from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.rcac.instructions import RCAC_INSTRUCTIONS
from cluster_mcp.slurm.instructions import SLURM_INSTRUCTIONS

PLANTED_TEXT = 'Planted tools:\n- planted_echo: Echo a text back'

PARTS = {
    'core': ({'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file',
              'cluster_context'}, {'cluster://context', 'rcac://context'}, CORE_INSTRUCTIONS),
    'slurm': ({'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job', 'scontrol_show_node'},
              set(), SLURM_INSTRUCTIONS),
    'rcac': ({'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
              'average_wait', 'slist', 'sfeatures'}, {'cluster://storage', 'rcac://storage'}, RCAC_INSTRUCTIONS),
    'planted': ({'planted_echo'}, {'cluster://planted'}, PLANTED_TEXT),
}


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[2] != 'core' or any(p not in PARTS for p in sys.argv[2:]):
        raise SystemExit('usage: expect.py OUT.json core [slurm|rcac|planted]…')
    parts = [PARTS[p] for p in sys.argv[2:]]
    out = {'tools': sorted(set().union(*(p[0] for p in parts))),
           'resources': sorted(set().union(*(p[1] for p in parts))),
           'texts': [p[2] for p in parts]}
    with open(sys.argv[1], 'w') as f:
        json.dump(out, f)
    return 0


if __name__ == '__main__':
    sys.exit(main())
