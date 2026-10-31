# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The Slurm member's part of the served instructions: every tool this member registers.

This module imports nothing. The member's capability (`capability.py`) carries the text to the
core, which places it in the base by the capability's order.
"""

SLURM_INSTRUCTIONS = """\
Slurm jobs:
- sbatch: Submit a batch job (script path or content)
- squeue: View the job queue
- scancel: Cancel jobs
- sacct: Job accounting history
- scontrol_show_job: Slurm's view of a job

Slurm cluster status:
- sinfo: Cluster and partition status
- scontrol_show_node: Node details for diagnostics"""
