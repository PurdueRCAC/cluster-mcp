#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Fail when any package `uv.lock` pins carries a known advisory, or when that cannot be determined.

Usage, from the repository root:

    uv run python bin/audit_lock.py

Runs `uv audit` over the tree this checkout's `uv.lock` resolves (frozen: the lock is read, never
re-resolved), always naming this checkout with `--project`, with `--no-config` so no user or system
`uv.toml` can add ignores or redirect the advisory service, and with every `UV_*` variable but a
short allowlist removed from uv's environment, so neither `UV_PROJECT` (which `bin/sandbox.sh`
exports) nor a group selector such as `UV_NO_DEV` can point the audit at another tree or a subset.
`UV_OFFLINE` passes through: an offline audit fails closed.
The release recipe's `gate` (AGENTS.md § Factory) and the CI workflow both run this file, so the
two cannot drift. It takes no options: there is no waiver for an advisory.

Exit status: 0 only when uv reports no known vulnerability and no adverse status **and** audited
exactly as many packages as the lock pins from a registry; 1 when a locked package carries an
advisory (uv's report, naming each package, version and advisory, is printed); 2 when the advisory
source cannot be reached or the audit cannot run at all; 3 when uv reported success but its summary
is missing or covers a different number of packages than the lock pins. The verdict is decided by
`audit_violations`, which the test suite feeds planted outputs.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMAND = ['uv', 'audit', '--frozen', '--no-config', '--preview-features', 'audit-command', '--project', str(ROOT)]

# The only uv variables the audit inherits: none of them selects a project, a group or a service.
UV_ALLOWED = frozenset({'UV_CACHE_DIR', 'UV_OFFLINE', 'UV_NATIVE_TLS', 'UV_SYSTEM_CERTS'})

# uv's one-line verdict on success, and the line that opens each package's findings.
SUMMARY = re.compile(r'^Found no known vulnerabilities and no adverse project statuses in (\d+) packages?$',
                     re.MULTILINE)
FINDING = re.compile(r'^(\S+) (\S+) has \d+ known vulnerabilit', re.MULTILINE)

# What uv prints when it cannot reach the advisory service, or is told not to.
UNREACHABLE = ('requires network access', 'Request failed', 'error sending request', 'deadline has elapsed',
               'dns error', 'tcp connect error')

EXIT_FINDINGS, EXIT_UNREACHABLE, EXIT_UNVERIFIED = 1, 2, 3


def registry_packages(lock_text: str) -> int:
    """The number of packages the lock pins from an index: every entry but the project's own."""
    lock = tomllib.loads(lock_text)
    return sum(1 for p in lock.get('package', []) if 'registry' in p.get('source', {}))


def child_env(environ: dict[str, str]) -> dict[str, str]:
    """The environment uv audit runs with: `environ` minus every `UV_*` variable not in UV_ALLOWED."""
    return {k: v for k, v in environ.items() if not k.startswith('UV_') or k in UV_ALLOWED}


def audit_violations(returncode: int, output: str, lock_text: str) -> tuple[int, list[str]]:
    """Return (exit status, reasons) for one `uv audit` run; (0, []) means the lock audits clean."""
    findings = [f'{m.group(1)} {m.group(2)}' for m in FINDING.finditer(output)]
    if findings or returncode == 1:
        named = ', '.join(findings) or 'see the report above'
        return EXIT_FINDINGS, [f'known advisories against locked packages: {named}']
    if returncode != 0:
        if any(marker in output for marker in UNREACHABLE):
            return EXIT_UNREACHABLE, [f'advisory source unreachable (uv audit exited {returncode})']
        return EXIT_UNREACHABLE, [f'the audit could not run (uv audit exited {returncode})']
    summary = SUMMARY.search(output)
    if summary is None:
        return EXIT_UNVERIFIED, ['uv audit exited 0 without its no-findings summary; the verdict is unverified']
    audited, pinned = int(summary.group(1)), registry_packages(lock_text)
    if pinned == 0 or audited != pinned:
        return EXIT_UNVERIFIED, [f'uv audit covered {audited} packages, but uv.lock pins {pinned}']
    return 0, []


def main() -> int:
    run = subprocess.run(COMMAND, cwd=ROOT, env=child_env(dict(os.environ)), capture_output=True, text=True)
    output = run.stdout + run.stderr
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    status, reasons = audit_violations(run.returncode, output, (ROOT / 'uv.lock').read_text())
    for reason in reasons:
        print(f'audit_lock: {reason}', file=sys.stderr)
    if status == 0:
        print('audit_lock: no known advisories against any locked package', file=sys.stderr)
    return status


if __name__ == '__main__':
    sys.exit(main())
