"""Review cycle 1, F2a-c, and F1's new decisions: each pin fails, naming its contract, when its decision is mutated.

The review found three decisions of the cleanup no suite row pinned (a hand-planted mutant of each survived
tests/test_sandbox_dirs.py): the sweep of the run's pytest temporary directory (F2a), the keep of a run
directory holding a sandbox in use (F2b), and the keep of a case scratch in use (F2c). F1's fix adds more
decisions (`reopen`, `remove`, and what the sweep and `case_scratch` keep and name). Each plant below breaks
one decision in a copy of tests/ and is run through the mutation runner's own `run_case` against the rows
that pin it: it counts as killed only when every target fails (not errors, not skips) and its failure
carries the plant's `why`, a fragment of the row's assertion message that names the contract. The frozen
gate's `mutants` mode cannot grade these: its `units` mode prints only the first line of a failing run.

Run from the cycle worktree, staged, as
`uv run python -I spec/sandbox-dirs-left-on-kill/remediation/F2-pins.py`; it prints a line per plant and
the counts the mutation-testing method asks for, and exits 1 unless every plant is killed and the control
survives. About 2 minutes, one child at a time.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip())
SD, MU = 'tests/sandbox_dirs.py', 'tests/mutants.py'
T = 'test_sandbox_dirs.py::'

SWEEP_CLOSED = (f'{T}test_the_sweep_removes_what_a_stopped_test_left_closed[0o555]',
                f'{T}test_the_sweep_removes_what_a_stopped_test_left_closed[0]')
SCRATCH_CLOSED = (f'{T}test_a_case_scratch_a_stopped_test_left_closed_is_removed[0o555]',
                  f'{T}test_a_case_scratch_a_stopped_test_left_closed_is_removed[0]')
SWEEP_STUCK = (f'{T}test_what_the_sweep_cannot_remove_is_kept_and_named[sandbox]',
               f'{T}test_what_the_sweep_cannot_remove_is_kept_and_named[run]')
SWEEP_UNLISTED = (f'{T}test_the_sweep_keeps_what_it_finds_when_its_processes_cannot_be_listed',)
SWEEP_HIDDEN = (f'{T}test_a_sandbox_in_use_under_a_directory_left_closed_is_seen',)
SCRATCH_HIDDEN = (f'{T}test_a_case_scratch_with_a_sandbox_in_use_under_a_directory_left_closed_is_kept',)
SCRATCH_STUCK = (f'{T}test_what_a_case_scratch_cannot_remove_is_kept_and_named',)

# (id, the decision, [(file, old, new)], targets, why)
PLANTS = (
    ('f2a-basetemp-not-swept', "the sweep takes the run's pytest temporary directory",
     [(SD, 'kept = sweep([run, basetemp], tell)', 'kept = sweep([run], tell)')],
     (f'{T}test_the_sweep_takes_the_runs_pytest_temporary_directory',), "in the run's pytest temporary directory"),
    ('f2b-run-dir-removed-though-kept', 'the run directory is kept while a sandbox in it is in use',
     [(SD, 'if not any(run in path.parents for path in kept):', 'if True or not any(run in path.parents for path in kept):')],
     (f'{T}test_a_run_directory_holding_a_sandbox_in_use_is_kept',),
     "the run's directory was removed while a sandbox directory in it was in use"),
    ('f2c-case-scratch-busy-ignored', 'the case scratch is kept while a sandbox in it is in use',
     [(MU, 'if left and sandbox_dirs.in_use(left, sandbox_dirs.processes()):',
       'if left and sandbox_dirs.in_use(left, sandbox_dirs.processes()) and False:')],
     (f'{T}test_a_case_scratch_holding_a_sandbox_in_use_is_kept',),
     "the case's scratch was removed while a sandbox directory in it was in use"),
    ('f1-remove-no-retry-sweep', 'remove opens what a stopped test left closed',
     [(SD, '    error = _rmtree(path)\n    if error is None:\n        return None\n', '    return _rmtree(path)\n')],
     SWEEP_CLOSED, 'the sweep kept something it could remove'),
    ('f1-remove-no-retry-scratch', 'remove opens what a stopped test left closed',
     [(SD, '    error = _rmtree(path)\n    if error is None:\n        return None\n', '    return _rmtree(path)\n')],
     SCRATCH_CLOSED, 'the case scratch was kept although nothing in it was in use'),
    ('f1-remove-raises-sweep', 'remove never raises',
     [(SD, '    return errors[0] if errors else None\n', '    if errors:\n        raise errors[0]\n    return None\n')],
     SWEEP_STUCK, 'the sweep raised instead of keeping and naming'),
    ('f1-remove-raises-scratch', 'remove never raises',
     [(SD, '    return errors[0] if errors else None\n', '    if errors:\n        raise errors[0]\n    return None\n')],
     SCRATCH_STUCK, 'the case scratch raised instead of keeping and naming'),
    ('f1-holder-not-opened', 'remove opens the closed directory holding a sandbox directory',
     [(SD, '        if stat.S_ISDIR(mode) and mode & 0o300 != 0o300:', '        if False:')],
     SWEEP_CLOSED, 'the sweep kept something it could remove'),
    ('f1-holder-not-restored', 'remove gives the holding directory its mode back',
     [(SD, '        if restore is not None:\n            try:\n                os.chmod(holder, restore)',
       '        if False:\n            try:\n                os.chmod(holder, restore)')],
     SWEEP_CLOSED, 'did not get its mode back'),
    ('f1-reopen-dropped-sweep', "the run's directory is opened before it is scanned",
     [(SD, '            reopen(run)\n', '')],
     SWEEP_HIDDEN, 'hidden under a directory a test left closed'),
    ('f1-reopen-dropped-scratch', 'the case scratch is opened before it is scanned',
     [(MU, '            sandbox_dirs.reopen(Path(scratch))\n', '')],
     SCRATCH_HIDDEN, 'hidden under a directory a test left closed'),
    ('f1-reopen-enters-sandboxes', 'reopen never touches a sandbox directory',
     [(SD, '            if SANDBOX_NAME.fullmatch(name):\n                dirs.remove(name)\n                continue\n', '')],
     SWEEP_HIDDEN + SCRATCH_HIDDEN, 'a sandbox directory in use was'),
    ('f1-reopen-follows-links', 'reopen never follows a link',
     [(SD, '    for parent, dirs, _ in os.walk(root):\n        for name in list(dirs):\n            path = os.path.join(parent, name)',
       '    for parent, dirs, _ in os.walk(root, followlinks=True):\n        for name in list(dirs):\n            path = os.path.join(parent, name)')],
     (SWEEP_CLOSED[1], SCRATCH_CLOSED[1]), 'reached through a link'),
    ('f1-reopen-stat-follows', 'reopen never opens through a link',
     [(SD, '                mode = os.lstat(path).st_mode\n                if stat.S_ISDIR(mode) and mode & 0o500',
       '                mode = os.stat(path).st_mode\n                if stat.S_ISDIR(mode) and mode & 0o500')],
     (SWEEP_CLOSED[1], SCRATCH_CLOSED[1]), 'reached through a link'),
    ('f1-sweep-unlisted-removes', 'the sweep keeps what it found when the processes cannot be listed',
     [(SD, '        return sorted(found)\n', '        busy = set()\n')],
     SWEEP_UNLISTED, 'although its processes could not be listed'),
    ('f1-sweep-unlisted-raises', 'the sweep never raises when the processes cannot be listed',
     [(SD, '    except Exception as exc:\n        for path in found:', '    except Exception as exc:\n        raise\n        for path in found:')],
     SWEEP_UNLISTED, 'the sweep raised instead of keeping and naming'),
    ('f1-sweep-unlisted-silent', 'the sweep names what it keeps unlisted',
     [(SD, "            tell(f'kept {path}: its processes could not be listed", "            (f'kept {path}: its processes could not be listed")],
     SWEEP_UNLISTED, 'what the sweep kept was not named on stderr'),
    ('f1-sweep-unremovable-silent', 'the sweep names a sandbox directory it cannot remove',
     [(SD, "                kept.add(path)\n                tell(f'kept {path}: it could not all be removed", "                kept.add(path)\n                (f'kept {path}: it could not all be removed")],
     SWEEP_STUCK[:1], 'was not named on stderr'),
    ('f1-sweep-unremovable-dropped', 'the sweep returns a sandbox directory it cannot remove as kept',
     [(SD, "                kept.add(path)\n                tell(", "                tell(")],
     SWEEP_STUCK[:1], 'was not named on stderr'),
    ('f1-run-dir-unremovable-silent', "own_tmp names a run directory it cannot remove",
     [(SD, "            if error is not None:\n                tell(f'kept {run}", "            if False:\n                tell(f'kept {run}")],
     SWEEP_STUCK[1:], 'was not named on stderr'),
    ('f1-scratch-unremovable-silent', 'case_scratch names a scratch it cannot remove',
     [(MU, "            if error is not None:\n                reason = f'it could not all be removed",
       "            if False:\n                reason = f'it could not all be removed")],
     SCRATCH_STUCK, 'was not named on stderr'),
    ('f1-scratch-plain-rmtree', 'case_scratch removes through remove, never a bare rmtree',
     [(MU, '            error = sandbox_dirs.remove(Path(scratch))\n', '            shutil.rmtree(scratch)\n            error = None\n')],
     SCRATCH_CLOSED, 'the case scratch raised instead of keeping and naming'),
)


def staged_runner(top: Path):
    repo = top / 'repo'
    repo.mkdir()
    subprocess.run(['git', '-C', str(ROOT), 'checkout-index', '-a', f'--prefix={repo}/'], check=True)
    sys.path.insert(0, str(repo / 'tests'))
    mutants = importlib.import_module('mutants')
    mutants.REPO_FILES = mutants.REPO_FILES + (SD, MU)
    return mutants


def main() -> int:
    top = Path(tempfile.mkdtemp(prefix='sdlk-f2-'))
    tmp = top / 't'
    tmp.mkdir()
    os.environ['TMPDIR'] = str(tmp)
    tempfile.tempdir = None
    counts = {'generated': 0, 'killed': 0, 'survived': 0, 'unviable': 0, 'wrong reason': 0}
    try:
        mutants = staged_runner(top)
        every = tuple(dict.fromkeys(t for plant in PLANTS for t in plant[3]))
        control = mutants.Case('f2-control', '', (), every, 'control', ((SD, '"""Where a suite run', '"""Where  a suite run'),))
        violations = mutants.run_case(control)
        # Every target passed: the runner's own survival line, then one per target.
        held = (violations[:1] == ['the mutant survived: every target passed'] and len(violations) == 1 + len(every)
                and all(v.endswith('passed, so the mutant survived it') for v in violations[1:]))
        print(f'{"control" if held else "FAILED "}  unmutated: all {len(every)} pinning rows pass: {violations[:1]}', flush=True)
        for ident, decision, edits, targets, why in PLANTS:
            counts['generated'] += 1
            try:
                violations = mutants.run_case(mutants.Case(ident, '', (), targets, why, tuple(edits)))
            except ValueError as exc:
                counts['unviable'] += 1
                print(f'UNVIABLE {ident} ({decision}): {exc}', flush=True)
                continue
            if not violations:
                counts['killed'] += 1
                print(f'killed   {ident} ({decision}): {len(targets)} row(s) failed with {why!r}', flush=True)
            elif any('survived' in v for v in violations):
                counts['survived'] += 1
                print(f'SURVIVED {ident} ({decision}): {violations[:3]}', flush=True)
            else:
                counts['wrong reason'] += 1
                print(f'WRONG    {ident} ({decision}): {violations[:3]}', flush=True)
        left = sorted(str(p.relative_to(tmp)) for p in tmp.iterdir())
        print(f'counts: {counts}; timed out 0, equivalent 0, unrun 0; left under the TMPDIR: {left}', flush=True)
        good = held and counts['killed'] == counts['generated'] and not left
    finally:
        shutil.rmtree(top, ignore_errors=True)
    return 0 if good else 1


if __name__ == '__main__':
    sys.exit(main())
