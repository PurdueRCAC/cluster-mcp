"""Mutant sweep of mutants-workflow-timeout: each decision of the sharded run is pinned by a row that kills it.

Run from the cycle worktree root, after staging (it reads the index, never the working copy):

    UV_PYTHON=3.14 uv run -q python -I spec/mutants-workflow-timeout/verify/shard-mutants.py MODE

Modes:

  runner    For each mutant of the runner's split, ledger and CLI (PLAN § 6.2, 24 entries): export the
            index into a fresh temporary directory, plant the mutant into the export's
            tests/mutants.py (its anchor must occur there exactly once, and the planted file is read
            back to confirm the mutant landed), and run the killing row by its id. The row must fail
            (exit 1, one failed, no error: a mutant that breaks collection is not a kill). Then the
            runner's rows, unplanted, in a fresh export, must all pass.

Footprint: one pytest at a time, never in parallel, each a single process of this environment's
interpreter (no install, no child pytest of the runner, nothing under bin/sandbox.sh: the rows fake
`run_case`) taking a few seconds; one export of the index (~550 files) per mutant, under the system
temporary directory and removed after it. About two minutes in all on a development host.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RUNNER = 'tests/mutants.py'
ROWS_FILE = 'tests/test_mutant_shards.py'

SHARDS_HOLD = 'test_the_shards_hold_every_case_once'
ORDER = 'test_every_job_shards_the_cases_alike_whatever_their_order'
OUTSIDE = 'test_a_shard_outside_the_run_is_refused'
PLATFORM = 'test_the_run_holds_every_case_this_platform_defines'
ACCEPTS = 'test_the_ledger_accepts_a_shard_whose_every_case_was_killed'
NAMES = 'test_the_ledger_names_each_case_without_a_kill'
NO_CASES = 'test_the_ledger_refuses_a_run_with_no_cases'
OWN_LINES = 'test_the_ledger_reads_the_runner_s_own_lines'
MIXED = 'test_cases_and_a_shard_together_are_refused'
FAILS = 'test_the_ledger_fails_the_shard_and_names_each_case'
EMPTY = 'test_a_run_with_no_cases_names_no_shard'
RUNNER_ROWS = (SHARDS_HOLD, ORDER, OUTSIDE, PLATFORM, ACCEPTS, NAMES, NO_CASES, OWN_LINES, MIXED, FAILS, EMPTY)

# (label, anchor, replacement, killing row). Each anchor is the decision itself, so a mutant cannot land elsewhere.
RUNNER_MUTANTS = (
    ('a case skipped, a shard shifted', 'return sorted(ids)[number - 1::count]', 'return sorted(ids)[number::count]',
     SHARDS_HOLD),
    ('order-dependent split', 'return sorted(ids)[number - 1::count]', 'return list(ids)[number - 1::count]', ORDER),
    ('a split that differs between processes', 'return sorted(ids)[number - 1::count]',
     'return sorted(ids, key=hash)[number - 1::count]', ORDER),
    ('too few shards', 'return -(-len(ids) // size)', 'return len(ids) // size', SHARDS_HOLD),
    ('an empty shard', 'return -(-len(ids) // size)', 'return -(-len(ids) // size) + 1', SHARDS_HOLD),
    ('the last shard refused', 'if not 1 <= number <= count:', 'if not 1 <= number < count:', SHARDS_HOLD),
    ('shard 0 accepted', 'if not 1 <= number <= count:', 'if not 0 <= number <= count:', OUTSIDE),
    ('a job splitting by another count', '    if int(count) != shard_count(ids):\n', '    if False:\n', OUTSIDE),
    ('a case skipped unseen',
     "        if not words:\n            found.append(f'{case_id}: no verdict reported')\n        elif len(words) > 1:\n",
     '        if len(words) > 1:\n', NAMES),
    ('a case run twice unseen', "        elif len(words) > 1:\n            found.append(f'{case_id}: reported {len(words)} times')\n",
     '', NAMES),
    ('a survivor accepted',
     "        elif words != ['killed']:\n            found.append(f'{case_id}: not killed (its FAILED line in the report says why)')\n",
     '', NAMES),
    ('a shard overlap unseen',
     "    found += [f'{case_id}: not a case of this shard' for case_id in verdicts if case_id not in expected]\n", '', NAMES),
    ('a failed control accepted', "        if words != ['control']:\n", '        if not words:\n', NAMES),
    ('a missing control accepted', '    for text in CONTROLS:\n        words = controls.get(text, [])\n',
     '    for text in ():\n        words = controls.get(text, [])\n', NAMES),
    ('no cases accepted', "    if not expected:\n        return ['no mutation cases found']\n", '', NO_CASES),
    ("the runner's lines misread", "line.partition('  ')", "line.partition(' ')", ACCEPTS),
    ('a platform-only (last-defined) case lost', '    status = sharded(parser, args, list(known))\n',
     '    status = sharded(parser, args, list(known)[:-1])\n', PLATFORM),
    ("the plan's log disagrees with its shards", '{" ".join(shard_ids(ids, number, count))}',
     '{" ".join(ids[number - 1::count])}', PLATFORM),
    ('a shard that runs nothing', '    args.cases = shard\n', '', PLATFORM),
    ('named cases silently replaced', "    if args.cases:\n        parser.error('name cases or a shard, not both')\n", '',
     MIXED),
    ('a red ledger that passes its job', '        return 1 if found else 0\n', '        return 0\n', FAILS),
    ("a stopped step's cases unnamed", 'report.read_text().splitlines() if report.exists() else []',
     'report.read_text().splitlines()', FAILS),
    ('no case found, run green',
     "        if not ids:\n            print('no mutation cases found in tests/mutants.py', file=sys.stderr)\n"
     '            return 1\n', '', EMPTY),
    ('the last shard never scheduled', 'numbers = list(range(1, count + 1))', 'numbers = list(range(1, count))', PLATFORM),
)

MODES = {'runner': (RUNNER, RUNNER_MUTANTS, RUNNER_ROWS)}


def export(dest: Path) -> None:
    """The index, not the working copy: what the commit would hold."""
    subprocess.run(['git', 'checkout-index', '-a', f'--prefix={dest}/'], check=True)


def pytest(tree: Path, rows: tuple[str, ...]) -> tuple[int, str]:
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    env.pop('CLUSTER_MCP_TEST_ERA', None)
    run = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                          *(f'{ROWS_FILE}::{row}' for row in rows)],
                         cwd=tree, env=env, capture_output=True, text=True, timeout=300)
    tail = (run.stdout.strip().splitlines() or [''])[-1]
    return run.returncode, tail


def plant(tree: Path, name: str, anchor: str, replacement: str) -> str | None:
    """Plant one mutant in the export; a reason it could not be planted, or None."""
    path = tree / name
    original = path.read_text()
    count = original.count(anchor)
    if count != 1:
        return f'its anchor occurs {count} times in {name}, not once: {anchor[:80]!r}'
    planted = original.replace(anchor, replacement)
    path.write_text(planted)
    if path.read_text() != planted or planted == original:
        return 'the mutant did not land'
    return None


def sweep(mode: str) -> list[str]:
    name, mutants, rows = MODES[mode]
    found: list[str] = []
    for label, anchor, replacement, row in mutants:
        with tempfile.TemporaryDirectory(prefix='mwt-mutant-') as scratch:
            tree = Path(scratch) / 'tree'
            export(tree)
            refused = plant(tree, name, anchor, replacement)
            if refused:
                print(f'BAD  {label}: {refused}')
                found.append(f'{label}: {refused}')
                continue
            code, tail = pytest(tree, (row,))
        killed = code == 1 and tail.startswith('1 failed') and 'error' not in tail
        print(f'{"ok " if killed else "BAD"}  {label}: {row}: {tail}')
        if not killed:
            found.append(f'{label}: {row} was not red ({code}: {tail})')
    with tempfile.TemporaryDirectory(prefix='mwt-unplanted-') as scratch:
        tree = Path(scratch) / 'tree'
        export(tree)
        code, tail = pytest(tree, rows)
    green = code == 0 and tail.startswith(f'{len(rows)} passed') and not any(
        word in tail for word in ('failed', 'error', 'skipped', 'deselected'))
    print(f'{"ok " if green else "BAD"}  unplanted rows: {tail}')
    if not green:
        found.append(f'the unplanted rows are not all green ({code}: {tail})')
    print(f'{mode}: {len(mutants) - sum(1 for f in found if not f.startswith("the unplanted"))} of {len(mutants)} '
          f'mutants killed')
    return found


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(f'usage: shard-mutants.py {"|".join(MODES)}', file=sys.stderr)
        return 2
    found = sweep(sys.argv[1])
    for line in found:
        print(f'FAILED  {line}')
    print(f'{sys.argv[1]}: {"ok" if not found else f"{len(found)} failed"}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
