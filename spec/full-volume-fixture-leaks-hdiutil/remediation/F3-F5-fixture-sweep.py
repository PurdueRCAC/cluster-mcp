"""Review cycle 2, F3, F4 and F5: a step's wait cut short by any exception stops the step, and the
exception goes on as itself, with the cleanup R3 asks after a cut `create` or `attach` (a second
interrupt abandons it, naming what is left) and the volume and image named after a cut `detach`
(F3); the fill's own failure ends the body in rows of its own (F4); a cleanup that cannot list
devices names the image only when it is there (F5). Every decision the fixture makes is shown
pinned, in both protocol eras, additive carve-outs included.

This checker supersedes review cycle 1's `F2-fixture-sweep.py`, which stays as the record: its
`coverage` reads the fixture's functions as they were, so it is red once the fixture grows a
decision, and every one of its modes runs `coverage` first. This one takes F2's cases as they are
(one re-aimed, below), adds this round's, and derives and checks the case list over the fixture's
functions as they are now.

Usage, from the cycle worktree root:
    uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F3-F5-fixture-sweep.py MODE
Modes:
    coverage       static, no run: the case list is complete (below); every edit plants exactly once
    rows           every disk-image test id, by exact id, PASSED in both eras, none skipped, with
                   every kind cutting every wait short (`CLUSTER_MCP_TEST_EVERY_KIND=1`, asserted
                   collected); and the suite's own collection (no opt-in) holds one row per kind and
                   one per place
    new-legacy-a   this round's cases (`NEW_CASES`), the half whose name hashes even, handshake era
    new-legacy-b   the other half, handshake era
    new-modern-a   as new-legacy-a, in the 2026-07-28 era
    new-modern-b   as new-legacy-b, in the 2026-07-28 era
    prior-legacy-a F2's decision cases (re-aimed as below), handshake era
    prior-legacy-b F2's body-exit families, handshake era
    prior-modern-a, prior-modern-b  as the two above, in the 2026-07-28 era
    frozen-legacy  the 40 cases of verify/mutants.py (frozen), handshake era, judged by the message
                   alone (the frozen gate, verify/p3.sh sweep-a and sweep-b, runs them too, by its
                   own rule)
    frozen-modern  as frozen-legacy, in the 2026-07-28 era
Each sweep mode first runs its rows on an unchanged copy, which must pass.

The case list (`coverage` checks both, so a later decision or a later way to end a wait without a
case is red, not silently unswept):
1. Decisions. Every line of the fixture's functions (`FIXTURE`) that holds a decision node, read
   from the module's AST (F2's rule, with this round's calls added: the cut's stop, the cleanup
   after a cut, the note that names what is left), is changed by some case: frozen, F2's or this
   round's.
2. Ways a wait or a body ends. Every kind in the module's `BODY_EXITS` gets F2's body-exit families
   (the fill's own failure, `fill`, is this round's kind: F4) and this round's cut families
   (`CUT_FAMILIES`): a carve-out per kind of each place a cut is handled.

A case is killed only when every row it names fails with the row's `why` in the failure's message
(pytest's assertion text). F2 and the frozen runner match the `why` in the message and the
traceback together, and the traceback prints the failing test's source, which holds every
violation's wording: a row that failed any way matched. This checker reads the message alone, for
every case it runs, the frozen 40 and F2's included. The cut rows a case names
are the full matrix (every kind at every place), so every run sets `CLUSTER_MCP_TEST_EVERY_KIND=1`
(the suite never does); a case expected to survive runs every disk-image id that run collects. One
in `SURVIVORS` (F2's, and this round's) is expected to survive, seeded or equivalent, each with its
reason; one that is killed instead is reported, not red. Any other survivor, an unviable case, a
timeout at the 300 s cap, or a process left after the case's KILL, is red. F2's prior cases keep
F2's own rule for survivors: every id the suite collects (no opt-in).

Re-aimed from F2: `step-hang-uncaught` (the hang's `TimeoutExpired` no longer caught as a hang) now
reaches the cut path, which stops the step, so its row fails with no `HostFailure` rather than a
process left. `ps-pgid-not-read` (the group read as the pid column) keeps only the group's leader,
the sandbox script, which still runs under the survivor test's CONT, so the report does say what is
still running, and the test fails on the stand-in and its child left unnamed. Seven more name the
words their rows fail with in the message (`REAIMED`): F2 matched them in the printed test source,
so each was killed, but not by the words it named. Read under this checker's rule, each fails for
the decision it plants: a refusal not raised, an override lost, `ps` refused or timed out, the
step's failure missing from the report.

Footprint: one pytest at a time (the frozen runner's: about 6 processes, under 500 MB, a copy of
about 4 MB per case, removed after it). Measured on the build host: see the TECH.md amendment for
review cycle 2.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('f2_sweep', HERE / 'F2-fixture-sweep.py')
assert spec is not None and spec.loader is not None
f2 = importlib.util.module_from_spec(spec)
sys.modules['f2_sweep'] = f2
spec.loader.exec_module(f2)
frozen = f2.frozen

Case = frozen.Case
row = frozen.row
MODULE = frozen.MODULE
CAP = frozen.CAP
LEFT, OWN = frozen.LEFT, frozen.OWN
ERAS = f2.ERAS
OPT_IN = 'CLUSTER_MCP_TEST_EVERY_KIND'
CUT_TEST = 'test_a_disk_image_step_cut_short_is_stopped_and_its_exception_goes_on'
CUT_SURVIVOR = 'test_a_disk_image_step_cut_short_still_running_is_named'
STOP_CUT = 'test_a_disk_image_step_whose_stop_is_cut_short_names_its_group'
SELECT = 'disk_image or stopped_step or body_can_end'

FIXTURE = ('_bounds', '_processes', '_group', '_stop', '_cut_short', '_step', '_clean_up', '_clean_up_after',
           '_create_and_attach', '_in_use', 'attached_image')

# The fill's own failure joins the kinds F2 sweeps (in this process only; F2's file is unchanged).
f2.KIND_CLASS['fill'] = 'OSError'
KIND_CLASS = f2.KIND_CLASS
# Every place a wait is cut short in the rows (the module's `CUT_SITES`).
SITES = ['create', 'create-with-device', 'attach-with-device', 'detach', 'detach-after-the-body-failed',
         'then-cleanup-detach-fails', 'then-cleanup-info', 'then-cleanup-info-without-image', 'then-cleanup-detach']


def cut(site: str, kind: str = 'keyboard-interrupt') -> str:
    return f'{CUT_TEST}[{site}-{kind}]'


NOT_ITSELF = 'did not go on as itself'
CARRY = 'the report does not carry'
KEPT_FALSELY = 'names an image kept where none was'
NO_HOST = f2.NO_HOST
NOT_RAISED = f2.NOT_RAISED

# This round's decision lines, as the module holds them.
STEP_ARM = "    except BaseException as cut:\n        _cut_short(cut, verb, proc)\n        raise\n"
CUT_CALL = "        _cut_short(cut, verb, proc)\n"
CUT_STOP = "        running = _stop(proc)\n"
CUT_NOTE = "    cut.add_note(f'{verb}: cut short by {type(cut).__name__} and stopped' + running)\n"
STOP_CUT_NOTE = ("        again.add_note(f'{verb}: cut short by {type(cut).__name__}, then its stop by {type(again).__name__}: '\n"
                 "                       f'process group {proc.pid} may still be running')\n")
STOP_CUT_RAISE = "                       f'process group {proc.pid} may still be running')\n        raise\n"
NO_IMAGE = "    if failure is not None and not image.exists():\n        return [failure, f'there is no image at {image}']\n"
NO_IMAGE_RETURN = "        return [failure, f'there is no image at {image}']\n"
AFTER_CLEAN = "        left = _clean_up(hdiutil, bound, image)\n"
AFTER_NOTES = "    for line in left:\n        cut.add_note(line)\n"
ABANDON_RAISE = "                       else f'there is no image at {image}')\n        raise\n"
ABANDON_NOTE = "        again.add_note('the cleanup was abandoned')\n"
ABANDON_IMAGE = "stays attached' if image.exists()\n"
MADE_RETURN = "    return failure\n"
MADE_CALL = "        failure = _create_and_attach(hdiutil, bound, image, where)\n"
STOP_CUT_ARM = "    except BaseException as again:\n        again.add_note(f'{verb}"
ABANDON_ARM = "    except BaseException as again:\n        again.add_note('the cleanup"
MADE_ARM = "    except BaseException as cut:\n        _clean_up_after(cut, hdiutil, bound, image)\n        raise\n"
IN_USE = "        with _in_use(hdiutil, bound, image, where) as at:\n            yield at\n"
YIELD_AT = "            yield at\n"
USE_ARM = "    except BaseException as cut:\n        # Out of `_in_use`"
USE_NOTE = ("        if image.exists() and not isinstance(cut, HostFailure):\n"
            "            cut.add_note(f'the volume stays attached at {where}, and its image is kept at {image}')\n")
USE_RAISE = "            cut.add_note(f'the volume stays attached at {where}, and its image is kept at {image}')\n        raise\n"

# Kinds that are not `Exception`s, each with its cut row where the whole cleanup runs.
NOT_EXCEPTION = f2.NOT_EXCEPTION


def cut_families(kind: str) -> list[Case]:
    """Every carve-out, for one kind, of a place a cut is handled."""
    cls = KIND_CLASS[kind]
    whole, detach, after = cut('attach-with-device', kind), cut('detach', kind), cut('then-cleanup-detach-fails', kind)
    h = 'x'
    return [
        Case(f'cut-narrowed-past-{kind}', h, [(STEP_ARM, f"    except BaseException as cut:\n        if isinstance(cut, {cls}):\n"
                                                         f"            raise\n        _cut_short(cut, verb, proc)\n        raise\n")],
             [(whole, LEFT)], kind='additive'),
        Case(f'cut-unnoted-on-{kind}', h, [(CUT_NOTE, f"    if not isinstance(cut, {cls}):\n    " + CUT_NOTE)],
             [(whole, CARRY)], kind='additive'),
        Case(f'cut-replaced-on-{kind}', h, [(STEP_ARM, STEP_ARM.replace("        raise\n", f"        if isinstance(cut, {cls}):\n"
                                                                                       f"            raise HostFailure('cut short') from cut\n"
                                                                                       f"        raise\n"))],
             [(whole, NOT_ITSELF)], kind='additive'),
        Case(f'cut-cleanup-skipped-on-{kind}', h,
             [(MADE_ARM, MADE_ARM.replace("        _clean_up_after(", f"        if not isinstance(cut, {cls}):\n            _clean_up_after("))],
             [(whole, OWN)], kind='additive'),
        Case(f'cut-cleanup-unnoted-on-{kind}', h,
             [(AFTER_NOTES, f"    for line in left:\n        if not isinstance(cut, {cls}):\n            cut.add_note(line)\n")],
             [(after, CARRY)], kind='additive'),
        Case(f'detach-cut-unnamed-on-{kind}', h,
             [(USE_NOTE, USE_NOTE.replace("not isinstance(cut, HostFailure)", f"not isinstance(cut, (HostFailure, {cls}))"))],
             [(detach, CARRY)], kind='additive'),
        Case(f'detach-cut-replaced-on-{kind}', h,
             [(USE_RAISE, USE_RAISE.replace("        raise\n", f"        if isinstance(cut, {cls}):\n"
                                                              f"            raise HostFailure('cut short') from cut\n        raise\n"))],
             [(detach, NOT_ITSELF)], kind='additive'),
    ]


CUT_FAMILIES = [c.name.removesuffix('-assertion') for c in cut_families('assertion')]

DECISIONS = [
    # The step's own stop when its wait is cut short (F3, R1).
    Case('cut-arm-dropped', 'x', [(STEP_ARM, '')], [(cut('create'), LEFT), (cut('attach-with-device'), LEFT)], kind='additive'),
    Case('cut-unstopped', 'x', [(CUT_CALL, "        pass\n")], [(cut('create'), LEFT), (cut('detach'), LEFT)]),
    Case('cut-turned-into-failure', 'x', [(STEP_ARM, STEP_ARM.replace("        raise\n", "        return f'{verb}: cut short', b''\n"))],
         [(cut('create'), NOT_ITSELF), (cut('detach'), NOT_ITSELF)]),
    Case('cut-replaced', 'x', [(STEP_ARM, STEP_ARM.replace("        raise\n", "        raise HostFailure('cut short') from cut\n"))],
         [(cut('create'), NOT_ITSELF), (cut('detach'), NOT_ITSELF)]),
    Case('cut-narrowed-to-exception', 'x', [(STEP_ARM, STEP_ARM.replace('except BaseException', 'except Exception'))],
         [(cut('attach-with-device', kind), LEFT) for kind in NOT_EXCEPTION], kind='additive'),
    Case('cut-stop-unnamed', 'x', [(CUT_NOTE, CUT_NOTE.replace(" + running)", ")"))], [(CUT_SURVIVOR, 'does not say what is still running')]),
    Case('cut-unnoted', 'x', [(CUT_NOTE, '')], [(cut('create'), CARRY), (cut('detach'), CARRY)]),
    Case('cut-stop-skipped', 'x', [(CUT_STOP, "        running = ''\n")], [(cut('create'), LEFT)]),
    Case('stop-cut-unnoted', 'x', [(STOP_CUT_NOTE, '')], [(STOP_CUT, 'the report names the group')]),
    Case('stop-cut-swallowed', 'x', [(STOP_CUT_RAISE, STOP_CUT_RAISE.replace("        raise\n", "        running = ''\n"))],
         [(STOP_CUT, 'did not go on with the first as its context')]),
    Case('stop-cut-uncaught', 'x', [(STOP_CUT_ARM, STOP_CUT_ARM.replace('BaseException', 'ZeroDivisionError'))],
         [(STOP_CUT, 'the report names the group')]),
    Case('stop-cut-group-misnamed', 'x', [(STOP_CUT_NOTE, STOP_CUT_NOTE.replace('{proc.pid}', '{os.getpid()}'))],
         [(STOP_CUT, 'the report names the group')]),
    # A cleanup that cannot list devices names the image only when it is there (F5, R3/R4).
    Case('no-image-kept-anyway', 'x', [(NO_IMAGE, '')],
         [(row(r), KEPT_FALSELY) for r in ('info-fails-without-image', 'info-answers-garbled-without-image')]),
    Case('no-image-unnamed', 'x', [(NO_IMAGE_RETURN, "        return [failure]\n")],
         [(row(r), CARRY) for r in ('info-fails-without-image', 'info-answers-garbled-without-image')]),
    Case('no-image-check-inverted', 'x', [(NO_IMAGE, NO_IMAGE.replace('not image.exists()', 'image.exists()'))],
         [(row('info-fails-in-cleanup'), CARRY), (row('info-fails-without-image'), KEPT_FALSELY)]),
    # The cleanup after a cut `create` or `attach`, and its abandonment by a second interrupt (F3, R3).
    Case('cleanup-after-cut-skipped', 'x', [(AFTER_CLEAN, "        left = []\n")],
         [(cut('attach-with-device'), OWN), (cut('create-with-device'), OWN)]),
    Case('cleanup-after-cut-unnoted', 'x', [(AFTER_NOTES, '')], [(cut('then-cleanup-detach-fails'), CARRY)]),
    Case('abandon-swallowed', 'x', [(ABANDON_RAISE, ABANDON_RAISE.replace("        raise\n", "        left = []\n"))],
         [(cut(s), NOT_ITSELF) for s in ('then-cleanup-info', 'then-cleanup-detach')]),
    Case('abandon-uncaught', 'x', [(ABANDON_ARM, ABANDON_ARM.replace('BaseException', 'ZeroDivisionError'))],
         [(cut(s), CARRY) for s in ('then-cleanup-info', 'then-cleanup-detach')]),
    Case('abandon-unnoted', 'x', [(ABANDON_NOTE, '')], [(cut('then-cleanup-info'), CARRY)]),
    Case('abandon-image-always-kept', 'x', [(ABANDON_IMAGE, "stays attached' if True\n")],
         [(cut('then-cleanup-info-without-image'), KEPT_FALSELY)]),
    Case('abandon-image-never-kept', 'x', [(ABANDON_IMAGE, "stays attached' if False\n")],
         [(cut(s), CARRY) for s in ('then-cleanup-info', 'then-cleanup-detach')]),
    Case('made-not-run', 'x', [(MADE_CALL, "        failure = None\n")], [(row('every-step-succeeds'), 'the body ran with a device')]),
    Case('made-failure-dropped', 'x', [(MADE_RETURN, "    return None\n")],
         [(row(r), f"does not carry '{r.split('-')[0]}: exited with status 1") for r in ('create-fails', 'attach-fails')]),
    Case('made-cut-uncaught', 'x', [(MADE_ARM, MADE_ARM.replace('except BaseException', 'except Exception'))],
         [(cut('attach-with-device', kind), OWN) for kind in NOT_EXCEPTION], kind='additive'),
    Case('made-cut-cleanup-skipped', 'x', [(MADE_ARM, MADE_ARM.replace("        _clean_up_after(cut, hdiutil, bound, image)\n", ''))],
         [(cut('attach-with-device'), OWN), (cut('create-with-device'), OWN)]),
    Case('made-cut-replaced', 'x', [(MADE_ARM, MADE_ARM.replace("        raise\n", "        raise HostFailure('cut short') from cut\n"))],
         [(cut('attach-with-device'), NOT_ITSELF)]),
    # The detach after the body, cut short: not tried again, the volume and image named (F3, R4).
    Case('in-use-yields-elsewhere', 'x', [(YIELD_AT, "            yield where.parent\n")],
         [(row('every-step-succeeds'), 'the body ran with a device')]),
    Case('in-use-bypassed', 'x', [(IN_USE, "        if True:\n            yield where\n")], [(row('every-step-succeeds'), OWN)],
         kind='additive'),
    Case('in-use-cut-uncaught', 'x', [(USE_ARM, USE_ARM.replace('except BaseException', 'except Exception'))],
         [(cut('detach', kind), CARRY) for kind in NOT_EXCEPTION], kind='additive'),
    Case('detach-cut-unnamed', 'x', [(USE_NOTE, '')], [(cut(s), CARRY) for s in ('detach', 'detach-after-the-body-failed')]),
    Case('detach-cut-named-always', 'x', [(USE_NOTE, USE_NOTE.replace('image.exists() and ', ''))],
         [(row('body-fails'), KEPT_FALSELY)]),
    Case('detach-cut-named-on-failure', 'x', [(USE_NOTE, USE_NOTE.replace(' and not isinstance(cut, HostFailure)', ''))], []),
    Case('in-use-cut-replaced', 'x', [(USE_RAISE, USE_RAISE.replace("        raise\n", "        raise HostFailure('cut short') from cut\n"))],
         [(cut('detach'), NOT_ITSELF), (row('body-fails'), NOT_RAISED)]),
]

# This round's cases expected to survive, each with its class and reason.
NEW_SURVIVORS = {
    'detach-cut-named-on-failure': ('equivalent', "a failed detach's `HostFailure` already carries that line: the report "
                                                  "repeats a true line, and claims nothing it did not"),
}
SURVIVORS = {**f2.SURVIVORS, **NEW_SURVIVORS}

# F2's cases, as they are, except one re-aimed (module docstring).
REAIMED = {
    'step-hang-uncaught': [(row('create-hangs'), NO_HOST)],
    'ps-pgid-not-read': [(f2.SURVIVOR, 'is not named with its command')],
    # Matched by the failure's message alone (module docstring): the row fails, by these words.
    'bounds-unchecked': [(f2.FIGURES, 'DID NOT RAISE')],
    'bounds-unknown-blind': [(f2.FIGURES, 'DID NOT RAISE')],
    'bounds-overrides-lost': [(f2.FIGURES, '120 == 1')],
    'ps-bound-dropped': [(row('create-fails'), 'timed out after 0 seconds')],
    'ps-lines-skipped': [(row('create-fails'), 'ps listed no process')],
    'ps-commandless': [(row('create-fails'), 'ps listed no process')],
    'attach-failure-ignored': [(row('create-fails'), "does not carry 'create: exited with status 1"),
                               (row('attach-fails'), "does not carry 'attach: exited with status 1")],
}
PRIOR_DECISIONS = [Case(c.name, c.half, c.edits, REAIMED.get(c.name, c.rows), c.kind) for c in f2.DECISIONS]
PRIOR_FAMILIES = [c for kind in f2.KIND_CLASS if kind != 'fill' for c in f2.families(kind)]
NEW_CASES = DECISIONS + f2.families('fill') + [c for kind in KIND_CLASS for c in cut_families(kind)]
EVERY = frozen.CASES + PRIOR_DECISIONS + PRIOR_FAMILIES + NEW_CASES


def half(case: Case) -> str:
    """A case's half by a stable hash of its name: adding a case re-runs only its own half."""
    return 'a' if zlib.crc32(case.name.encode()) % 2 == 0 else 'b'


def decision_lines(text: str) -> dict[int, str]:
    """F2's rule over `FIXTURE`, with this round's calls added."""
    calls = {'_step', '_stop', '_group', '_processes', '_clean_up', 'killpg', 'wait', 'communicate', 'sleep', 'unlink',
             'mkdir', 'REAL_POPEN', 'realpath', 'min', 'loads', 'monotonic', 'close', 'suppress', 'exists',
             '_cut_short', '_clean_up_after', '_create_and_attach', '_in_use', 'add_note'}
    found: dict[int, str] = {}
    for node in ast.parse(text).body:
        if not (isinstance(node, ast.FunctionDef) and node.name in FIXTURE):
            continue
        for sub in ast.walk(node):
            hit = isinstance(sub, (ast.If, ast.IfExp, ast.While, ast.For, ast.ExceptHandler, ast.Return, ast.Raise,
                                   ast.Assert, ast.Yield, ast.Compare, ast.BoolOp, ast.Continue, ast.Break, ast.With))
            if isinstance(sub, ast.comprehension):
                for c in sub.ifs:
                    found[c.lineno] = node.name
            if isinstance(sub, ast.Call):
                func = sub.func
                name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ''
                hit = hit or name in calls
            if hit:
                found[sub.lineno] = node.name
    return found


def coverage() -> int:
    text = (ROOT / MODULE).read_text()
    problems = []
    names = [c.name for c in EVERY]
    problems += [f'duplicate case {n}' for n in sorted({n for n in names if names.count(n) > 1})]
    defined = {node.name for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}
    problems += [f'no function {f} in the module' for f in FIXTURE if f not in defined]
    for case in EVERY:
        try:
            frozen.apply(text, case.edits)
        except ValueError as exc:
            problems.append(f'{case.name}: {exc}')
    if problems:
        print('\n'.join(problems))
        return 1
    covered: set[int] = set()
    for case in EVERY:
        covered |= f2.changed_lines(text, case)
    sites = decision_lines(text)
    source = text.splitlines()
    missing = {n: f for n, f in sites.items() if n not in covered}
    for n, f in sorted(missing.items()):
        problems.append(f'no case changes {f} line {n}: {source[n - 1].strip()}')
    kinds = f2.body_exit_kinds(text)
    if sorted(kinds) != sorted(KIND_CLASS):
        problems.append(f'BODY_EXITS {sorted(kinds)} is not the swept kinds {sorted(KIND_CLASS)}')
    for kind in kinds:
        problems += [f'no case {family}-{kind}' for family in f2.FAMILIES if f'{family}-{kind}' not in names]
        problems += [f'no case {family}-{kind}' for family in CUT_FAMILIES if f'{family}-{kind}' not in names]
    sites_here = cut_sites(text)
    if sites_here != SITES:
        problems.append(f'CUT_SITES {sites_here} is not the swept places {SITES}')
    for name, (cls, _) in SURVIVORS.items():
        if name not in names or cls not in ('seeded', 'equivalent'):
            problems.append(f'survivor entry {name}: no such case, or class {cls!r}')
    for case in NEW_CASES:
        if not case.rows and case.name not in SURVIVORS:
            problems.append(f'{case.name}: names no row and is not an expected survivor')
    print(f'coverage: {len(sites)} decision lines in {len(FIXTURE)} functions, {len(sites) - len(missing)} changed by a case; '
          f'{len(kinds)} kinds x ({len(f2.FAMILIES)} body + {len(CUT_FAMILIES)} cut) families, {len(SITES)} places; '
          f'{len(frozen.CASES)} frozen + {len(PRIOR_DECISIONS) + len(PRIOR_FAMILIES)} prior + {len(NEW_CASES)} new cases; '
          f'{len(SURVIVORS)} expected survivors ({len(NEW_SURVIVORS)} new)')
    if problems:
        print('\n'.join(problems))
        return 1
    print('F3-F5-fixture-sweep.py coverage: ok')
    return 0


def cut_sites(text: str) -> list[str]:
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'CUT_SITES' for t in node.targets):
            assert isinstance(node.value, ast.Dict)
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    raise AssertionError('no CUT_SITES in the module')


def run_rows(copy: Path, ids: list[str], era: str | None, every: bool) -> tuple[dict[str, tuple[str, str]], str]:
    """Run `ids` in `copy` in one era, with or without the opt-in: each id's outcome and text, and a note."""
    junit = copy / 'junit.xml'
    env = {k: v for k, v in os.environ.items() if k not in ('CLUSTER_MCP_TEST_ERA', OPT_IN)}
    if era:
        env['CLUSTER_MCP_TEST_ERA'] = era
    if every:
        env[OPT_IN] = '1'
    argv = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', f'--basetemp={copy / "bt"}',
            f'--junitxml={junit}', *[f'{MODULE}::{i}' for i in ids]]
    proc = subprocess.Popen(argv, cwd=copy, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    note = ''
    try:
        out, _ = proc.communicate(timeout=CAP)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        out, _ = proc.communicate()
        note = f'capped at {CAP} s'
    results: dict[str, tuple[str, str]] = {}
    if junit.exists():
        for case in ET.parse(junit).getroot().iter('testcase'):
            name = case.get('name', '')
            bad = case.find('failure') if case.find('failure') is not None else case.find('error')
            skipped = case.find('skipped')
            if bad is not None:
                # The failure's message only: its text also prints the test's source, which holds every
                # violation's wording, so a `why` matched there is matched whatever failed.
                results[name] = ('failed', bad.get('message') or '')
            elif skipped is not None:
                results[name] = ('skipped', skipped.get('message') or '')
            else:
                results[name] = ('passed', '')
    if not results:
        note = (note + '; ' if note else '') + 'no results: ' + out.decode(errors='replace')[-600:]
    return results, note


def all_ids(every: bool) -> list[str]:
    """Every disk-image test id the module collects, with or without the opt-in."""
    env = {k: v for k, v in os.environ.items() if k != OPT_IN}
    if every:
        env[OPT_IN] = '1'
    collected = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--collect-only', '-p', 'no:cacheprovider', MODULE,
                                '-k', SELECT], capture_output=True, text=True, timeout=120, env=env).stdout
    return sorted(line.split('::', 1)[1] for line in collected.splitlines() if line.startswith(f'{MODULE}::'))


def judge(case: Case, era: str | None, every: bool, everything: list[str]) -> tuple[str, str, float]:
    """Plant one case in a fresh copy and run it: (killed | survived | unviable | timeout | red, detail, seconds)."""
    copy = frozen.make_copy()
    token = copy.name
    started = time.monotonic()
    try:
        target = copy / case.path
        try:
            target.write_text(frozen.apply(target.read_text(), case.edits))
        except ValueError as exc:
            return 'unviable', f'not planted: {exc}', time.monotonic() - started
        expected = case.name in SURVIVORS
        ids = everything if expected else [i for i, _ in case.rows]
        results, note = run_rows(copy, ids, era, every)
        outcomes = {i: results.get(i, ('missing', ''))[0] for i in ids}
        left = frozen.kill_token(token)
        time.sleep(0.2)
        if frozen.kill_token(token):
            return 'red', f'processes naming {token} still ran after a KILL', time.monotonic() - started
        took = time.monotonic() - started
        if note.startswith('capped'):
            return 'timeout', note, took
        if all(o == 'missing' for o in outcomes.values()):
            return 'unviable', note or 'no row ran', took
        extra = f'; {left} left processes KILLed' if left else ''
        if expected:
            failed = [f'{i}: {o}' for i, o in outcomes.items() if o != 'passed']
            return ('killed', 'failed: ' + '; '.join(failed)[:600] + extra, took) if failed else \
                ('survived', f'all {len(ids)} disk-image ids passed{extra}', took)
        verdicts = []
        for i, why in case.rows:
            outcome, text = results.get(i, ('missing', ''))
            if outcome != 'failed':
                verdicts.append(f'{i}: {outcome}')
            elif why not in text:
                verdicts.append(f'{i}: failed without {why!r}: {" ".join(text.split())[:300]}')
        return ('survived', '; '.join(verdicts), took) if verdicts else ('killed', 'killed' + extra, took)
    finally:
        frozen.kill_token(token)
        frozen.shutil.rmtree(copy, ignore_errors=True)


def sweep(cases: list[Case], era: str | None, every: bool, label: str) -> int:
    started = time.monotonic()
    everything = all_ids(every)
    if len(everything) < 40:
        print(f'F3-F5-fixture-sweep.py {label}: only {len(everything)} disk-image ids collected')
        return 1
    ids = sorted({i for c in cases for i, _ in c.rows} | (set(everything) if any(c.name in SURVIVORS for c in cases) else set()))
    missing = sorted(set(ids) - set(everything))
    if missing:
        print(f'F3-F5-fixture-sweep.py {label}: cases name ids the module does not collect: {missing}')
        return 1
    copy = frozen.make_copy()
    try:
        results, note = run_rows(copy, ids, era, every)
        bad = [i for i in ids if results.get(i, ('missing', ''))[0] != 'passed']
        print(f'baseline ({label}): {len(ids) - len(bad)} of {len(ids)} rows passed unchanged' + (f' ({note})' if note else ''),
              flush=True)
    finally:
        frozen.kill_token(copy.name)
        frozen.shutil.rmtree(copy, ignore_errors=True)
    if bad:
        print('  ' + '\n  '.join(bad))
        print(f'F3-F5-fixture-sweep.py {label}: the baseline is red; no case can be judged')
        return 1
    counts: dict[str, list[str]] = {k: [] for k in ('killed', 'against', 'seeded', 'equivalent', 'survived', 'unviable',
                                                     'timeout', 'red')}
    for case in cases:
        status, detail, took = judge(case, era, every, everything)
        if case.name in SURVIVORS and status in ('killed', 'survived'):
            cls, why = SURVIVORS[case.name]
            key = cls if status == 'survived' else 'against'
            verdict = f'SURVIVED, {cls}: {why}' if status == 'survived' else 'KILLED (expected to survive)'
        else:
            key = status
            verdict = status.upper()
        counts[key].append(case.name)
        print(f'{case.name} ({case.kind}): {verdict} in {took:.1f} s; {detail}', flush=True)
    took = time.monotonic() - started
    print(f'F3-F5-fixture-sweep.py {label}: {len(cases)} generated, {len(counts["killed"]) + len(counts["against"])} killed, '
          f'{len(counts["survived"])} survived, {len(counts["seeded"])} seeded and {len(counts["equivalent"])} equivalent '
          f'(expected survivors), {len(counts["unviable"])} unviable, {len(counts["timeout"])} timed out, 0 unrun, '
          f'in {took / 60:.1f} min'
          + ''.join(f'; {k}: {", ".join(v)}' for k, v in counts.items() if v and k in ('against', 'survived', 'unviable',
                                                                                         'timeout', 'red')), flush=True)
    return 1 if counts['survived'] or counts['unviable'] or counts['timeout'] or counts['red'] else 0


def rows() -> int:
    """Every disk-image id, the full matrix collected, PASSED in both eras; none skipped."""
    text = (ROOT / MODULE).read_text()
    kinds = f2.body_exit_kinds(text)
    every, suite = all_ids(True), all_ids(False)
    cut_every = [i for i in every if i.startswith(f'{CUT_TEST}[')]
    cut_suite = [i for i in suite if i.startswith(f'{CUT_TEST}[')]
    need = {cut(s, k) for s in SITES for k in kinds} | {r for k in kinds for r in f2.body_rows(k)} \
        | {CUT_SURVIVOR, STOP_CUT, f2.FIGURES, f2.SURVIVOR, f2.EVERY_EXIT, row('info-fails-without-image'),
           row('info-answers-garbled-without-image')}
    problems = [f'not collected: {sorted(need - set(every))}'] if need - set(every) else []
    if len(cut_every) != len(SITES) * len(kinds):
        problems.append(f'with the opt-in, {len(cut_every)} cut rows, not every kind at every place ({len(SITES) * len(kinds)})')
    if sorted(cut_suite) != sorted({cut('attach-with-device', k) for k in kinds} | {cut(s) for s in SITES}):
        problems.append(f'without the opt-in, the cut rows are {cut_suite}, not each kind once and each place once')
    if problems:
        print('F3-F5-fixture-sweep.py rows: ' + '; '.join(problems))
        return 1
    print(f'F3-F5-fixture-sweep.py rows: {len(every)} ids with the opt-in ({len(cut_every)} cut rows), '
          f'{len(suite)} in the suite ({len(cut_suite)} cut rows)')
    for label, era in ERAS.items():
        copy = frozen.make_copy()
        try:
            results, note = run_rows(copy, every, era, True)
        finally:
            frozen.kill_token(copy.name)
            frozen.shutil.rmtree(copy, ignore_errors=True)
        bad = [f'{i}: {results.get(i, ("missing", ""))[0]}' for i in every if results.get(i, ('missing', ''))[0] != 'passed']
        if bad:
            print(f'F3-F5-fixture-sweep.py rows: era {label}: ' + '; '.join(bad) + (f' ({note})' if note else ''))
            return 1
        print(f'F3-F5-fixture-sweep.py rows: era {label}: {len(every)} ids passed, none skipped')
    print('F3-F5-fixture-sweep.py rows: ok')
    return 0


MODES = {
    'new-legacy-a': ([c for c in NEW_CASES if half(c) == 'a'], 'legacy', True),
    'new-legacy-b': ([c for c in NEW_CASES if half(c) == 'b'], 'legacy', True),
    'new-modern-a': ([c for c in NEW_CASES if half(c) == 'a'], 'modern', True),
    'new-modern-b': ([c for c in NEW_CASES if half(c) == 'b'], 'modern', True),
    'prior-legacy-a': (PRIOR_DECISIONS, 'legacy', False),
    'prior-legacy-b': (PRIOR_FAMILIES, 'legacy', False),
    'prior-modern-a': (PRIOR_DECISIONS, 'modern', False),
    'prior-modern-b': (PRIOR_FAMILIES, 'modern', False),
    'frozen-legacy': (frozen.CASES, 'legacy', False),
    'frozen-modern': (frozen.CASES, 'modern', False),
}


def main(mode: str) -> int:
    if mode == 'coverage':
        return coverage()
    if mode not in MODES and mode != 'rows':
        print(f'usage: F3-F5-fixture-sweep.py coverage|rows|{"|".join(MODES)}', file=sys.stderr)
        return 2
    if coverage() != 0:
        return 1
    if mode == 'rows':
        return rows()
    cases, era, every = MODES[mode]
    return sweep(cases, ERAS[era], every, mode)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
