---
status: accepted-behaviour
kind: fix
appetite: small
lane: public
---

# A job name of 220–236 characters no longer fits the script's file name

## Problem

`sbatch` writes a script given as content to `~/jobs/<name>_<YYYYmmdd_HHMMSS>_<token>.sh`, where
`<token>` is 16 hex digits drawn per call (`sbatch-script-name-collision`). The token adds 17
characters, so a sanitised `job_name` of 220–236 characters, whose file name fit within the file
system's 255-byte limit before, now exceeds it: the call fails with "Failed to write job script
(exit 1): … File name too long" before anything is submitted. A name of 237 or more already failed.

## Why it is accepted

Ruled at the `sbatch-script-name-collision` PLAN/TECH gate (foreman, 2026-10-23), and reproduced by
both of that cycle's reviews: the failure is loud and nothing is submitted; truncating the name would
change the sanitisation (a non-goal) and break the rule that the file name begins with the sanitised
job name (R4); and a Slurm job name of that length is not a use worth the trade. What would change
the answer: a real workflow that needs such names, in which case the token or the name would be
shortened by a rule stated in the tool's description.

## Notes

- Related: `spec/sbatch-script-name-collision/` (PLAN §5, REVIEW cycles 1–2).
- Found by: the `sbatch-script-name-collision` plan; re-raised by both reviews, 2026-10-23 and 2026-10-26.
