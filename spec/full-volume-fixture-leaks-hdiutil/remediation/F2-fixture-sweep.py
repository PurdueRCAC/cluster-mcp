"""Review cycle 1, F2: however the test body leaves the disk-image fixture, the fixture detaches and
removes what it made, or reports both failures with the body's first; and every decision the
fixture makes is shown pinned, in both protocol eras, additive carve-outs included.

Usage, from the cycle worktree root:
    uv run python -I spec/full-volume-fixture-leaks-hdiutil/remediation/F2-fixture-sweep.py MODE
Modes:
    coverage      static, no run: the case list is complete (below); every edit plants exactly once
    rows          every disk-image test id, by exact id, PASSED in both eras, none skipped
    new-legacy-a  the decision cases this checker adds (`DECISIONS`), in the handshake era
    new-legacy-b  the body-exit families (`families`), in the handshake era
    new-modern-a  as new-legacy-a, in the 2026-07-28 era
    new-modern-b  as new-legacy-b, in the 2026-07-28 era
    frozen-modern the 40 cases of verify/mutants.py (frozen), in the 2026-07-28 era; the frozen gate
                  (verify/p3.sh sweep-a, sweep-b) runs them in the handshake era
Each sweep mode first runs its rows on an unchanged copy, which must pass.

How the case list is derived (the `coverage` mode checks both, so a later edit that adds a decision
or a way to end the body without a case is red, not silently unswept):
1. Decisions. Every line of the fixture's functions (`FIXTURE`) that holds a decision node, read
   from the module's AST: a branch (`if`, a conditional expression, a loop, a comprehension's
   condition), a handler (`except`, `contextlib.suppress`), an exit (`return`, `raise`, `assert`,
   `yield`), a comparison or boolean operator, or a call that starts, bounds, stops, waits for,
   detaches or removes something. Each such line must be one some case changes, or the line an
   additive case inserts before (the frozen 40 cases count; a case only covers lines its edits
   actually change).
2. Body exits. Every kind in the module's `BODY_EXITS` (the test `test_every_way_a_body_can_end_has_its_rows`
   pins that list against Python's and pytest's classes) gets every family in `FAMILIES`: a
   carve-out that narrows the catch past it, a skipped detach, a skipped removal, two early returns
   (before the detach, and after it in place of the re-raise), a dropped cause, and a dropped name of
   what is left; plus one case that narrows the catch to `Exception` (the review's M32).

A case is killed only when every row it names fails with the row's `why` (the frozen runner's rule,
reused from verify/mutants.py). A case listed in `SURVIVORS` is expected to survive, as seeded
(the review's coverage observations and this sweep's other survivors, filed as one seed,
issues/disk-image-fixture-deeper-pins.md) or equivalent, each with its reason; it runs every
disk-image id, and survives only when all of them pass. One that is killed instead is reported, not
red. Any other survivor, an unviable case (one that plants but runs no row), a timeout at the 300 s
cap, or a process left after the case's KILL, is red.

Footprint: one pytest at a time (the frozen runner's: about 6 processes, under 500 MB, a copy of
about 4 MB per case, removed after it). Measured on the build host: see the TECH.md amendment for
review cycle 1.
"""

from __future__ import annotations

import ast
import difflib
import importlib.util
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path.cwd()
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('frozen_mutants', HERE.parent / 'verify' / 'mutants.py')
assert spec is not None and spec.loader is not None
frozen = importlib.util.module_from_spec(spec)
sys.modules['frozen_mutants'] = frozen
spec.loader.exec_module(frozen)

Case = frozen.Case
row = frozen.row
MODULE = frozen.MODULE
LEFT, OWN, FOREIGN = frozen.LEFT, frozen.OWN, frozen.FOREIGN
FIGURES, SURVIVOR = frozen.FIGURES, frozen.SURVIVOR
EVERY_EXIT = 'test_every_way_a_body_can_end_has_its_rows'
CAP = frozen.CAP
ERAS = {'legacy': None, 'modern': 'modern'}

FIXTURE = ('_bounds', '_processes', '_group', '_stop', '_step', '_clean_up', 'attached_image')

# The class each body exit raises, as the module names it.
KIND_CLASS = {
    'assertion': 'AssertionError',
    'pytest-fail': 'pytest.fail.Exception',
    'pytest-skip': 'pytest.skip.Exception',
    'pytest-xfail': 'pytest.xfail.Exception',
    'pytest-exit': 'pytest.exit.Exception',
    'keyboard-interrupt': 'KeyboardInterrupt',
    'system-exit': 'SystemExit',
    'generator-exit': 'GeneratorExit',
    'base-exception-group': 'BaseExceptionGroup',
    'bare-base-exception': '_BareExit',
}
# The kinds that are not `Exception`s.
NOT_EXCEPTION = ['pytest-fail', 'pytest-skip', 'pytest-xfail', 'keyboard-interrupt', 'system-exit', 'generator-exit',
                 'base-exception-group', 'bare-base-exception']


def body_rows(kind: str) -> tuple[str, str]:
    """The rows that end the body by `kind`: with a detach that succeeds, and with one that fails."""
    if kind == 'assertion':
        return row('body-fails'), row('body-and-detach-fail')
    return row(f'body-{kind}'), row(f'body-{kind}-and-detach-fail')


HANDLER = "    except BaseException as body:\n"
BODY_DETACH = "        failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', str(where))\n        if failure is not None:\n"
BODY_RAISE = frozen.BODY_RAISE
BODY_UNLINK = frozen.BODY_UNLINK
NOT_RAISED = "the body's own failure was not raised unchanged"
NO_HOST = 'raised no HostFailure'
IMAGE_LEFT = 'the image was left'


def families(kind: str) -> list[Case]:
    """Every carve-out of the body path for one way the body ends."""
    cls = KIND_CLASS[kind]
    ok, failing = body_rows(kind)
    half = 'x'
    return [
        Case(f'narrow-past-{kind}', half, [(HANDLER, f"    except {cls}:\n        raise\n" + HANDLER)],
             [(ok, OWN), (failing, NO_HOST)], kind='additive'),
        Case(f'no-detach-on-{kind}', half,
             [(HANDLER + BODY_DETACH,
               HANDLER + BODY_DETACH.replace("failure, _ = _step(", f"failure, _ = (None, b'') if isinstance(body, {cls}) else _step("))],
             [(ok, OWN), (failing, NO_HOST)], kind='additive'),
        Case(f'no-unlink-on-{kind}', half,
             [(BODY_UNLINK, f"        if not isinstance(body, {cls}):\n            image.unlink()\n        raise\n")],
             [(ok, IMAGE_LEFT)], kind='additive'),
        Case(f'return-before-detach-on-{kind}', half,
             [(HANDLER + BODY_DETACH, HANDLER + f"        if isinstance(body, {cls}):\n            return\n" + BODY_DETACH)],
             [(ok, NOT_RAISED), (failing, NO_HOST)], kind='additive'),
        Case(f'return-after-detach-on-{kind}', half,
             [(BODY_UNLINK, f"        image.unlink()\n        if isinstance(body, {cls}):\n            return\n        raise\n")],
             [(ok, NOT_RAISED)], kind='additive'),
        Case(f'cause-dropped-on-{kind}', half,
             [(BODY_RAISE, BODY_RAISE.replace('from body', f'from (None if isinstance(body, {cls}) else body)'))],
             [(failing, 'not caused by the body')], kind='additive'),
        Case(f'left-unnamed-on-{kind}', half,
             [(BODY_RAISE, BODY_RAISE.replace("HostFailure(f'{failure}\\n{left}')",
                                              f"HostFailure(failure if isinstance(body, {cls}) else f'{{failure}}\\n{{left}}')"))],
             [(failing, 'the volume stays attached at')], kind='additive'),
    ]


FAMILIES = [c.name.removesuffix('-assertion') for c in families('assertion')]

# Decision lines the frozen 40 do not change, each with its case.
PS_ARGV = "    proc = REAL_POPEN([str(SANDBOX), 'ps', '-A', '-ww', '-o', 'pid=', '-o', 'pgid=', '-o', 'stat=', '-o', 'args='],\n"
PS_WAIT = "    out, err = proc.communicate(timeout=30)\n"
PS_LOOP = "    for line in out.decode(errors='replace').splitlines():\n"
PS_PARSE = "        if len(fields) >= 3 and fields[0].isdigit() and fields[1].isdigit():\n"
PS_ARGS = "            listed.append((int(fields[0]), int(fields[1]), fields[2], fields[3] if len(fields) > 3 else ''))\n"
PS_SELF = ("    if not any(pid == os.getpid() and command for pid, _, _, command in listed):\n"
           "        raise HostFailure(")
PS_RETURN = "    return listed\n"
GROUP = "    return [(pid, command) for pid, group, state, command in _processes() if group == pgid and not state.startswith('Z')]\n"
SUPPRESS = "    with contextlib.suppress(ProcessLookupError, PermissionError):\n        # macOS answers EPERM"
LEADER_WAIT = "    with contextlib.suppress(subprocess.TimeoutExpired):\n        proc.wait(timeout=max(0.0, deadline - time.monotonic()))\n"
STREAMS = "    for stream in (proc.stdout, proc.stderr):\n        if stream is not None:\n            stream.close()\n"
NAMED = "    return f'; still running {STOP_WAIT} s after it was stopped: ' + ', '.join(f'pid {pid} ({command})' for pid, command in left)\n"
POPEN = "    proc = REAL_POPEN([*hdiutil, verb, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)\n"
FAILED_TEST = "    if proc.returncode != 0:\n        left = _stop(proc)\n"
SUCCESS = "    return None, out\n\n\ndef _clean_up("
LISTING_TYPE = "            if not isinstance(listing, dict):\n"
CLEAN_LOOP = "    for entry in listing.get('images', []):\n"
DEVICES = "        devices = [e['dev-entry'] for e in entities if 'dev-entry' in e]\n        if not devices:\n            continue\n"
MOUNTS = ("            mounts = [e['mount-point'] for e in entities if e.get('mount-point')]\n"
          "            at = f' at {mounts[0]}' if mounts else ', not mounted'\n")
KEPT_RETURN = "            return [failure, f'{device} stays attached{at}, and its image is kept at {image}']\n"
CREATE = "    if failure is None:\n        where.mkdir()\n"
ATTACH_FAILED = "    if failure is not None:\n        raise HostFailure('\\n'.join([failure, *_clean_up(hdiutil, bound, image)]))\n"
YIELD = "    try:\n        yield where\n"
BODY_FAILED = ("            raise HostFailure(f'{failure}\\n{left}') from body\n")
FINAL_DETACH = "    failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', str(where))\n    if failure is not None:\n        raise HostFailure(f'{failure}\\n{left}')\n"
BOUNDS_ASSERT = "    assert not unknown, f'no such hdiutil verb: {sorted(unknown)}'\n"
BOUNDS_MERGE = "    return {verb: HDIUTIL_BOUND for verb in HDIUTIL_VERBS} | dict(overrides or {})\n"
BOUNDS_UNKNOWN = "    unknown = set(overrides or {}) - set(HDIUTIL_VERBS)\n"
PS_RAISE = "        raise HostFailure(f'ps listed no process"
HANG_CATCH = "    except subprocess.TimeoutExpired:\n        return f'{verb}: ran past"
INFO_READ = "    if failure is None:\n        try:\n            listing = plistlib.loads(out)\n"
INFO_LOAD = "            listing = plistlib.loads(out)\n"
INFO_FAILED = "    if failure is not None:\n        return [failure, f'the image is kept at {image}, and any device made from it stays attached']\n"
DEVICES_READ = "        devices = [e['dev-entry'] for e in entities if 'dev-entry' in e]\n"
MOUNTS_READ = "            mounts = [e['mount-point'] for e in entities if e.get('mount-point')]\n"
CREATE_STEP = "    failure, _ = _step(hdiutil, 'create', bound['create'],"
ATTACH_STEP = "        failure, _ = _step(hdiutil, 'attach', bound['attach'],"

DECISIONS = [
    Case('bounds-unchecked', 'x', [(BOUNDS_ASSERT, '')], [(FIGURES, 'no such hdiutil verb')]),
    Case('bounds-overrides-lost', 'x', [(BOUNDS_MERGE, "    return dict(overrides or {}) | {verb: HDIUTIL_BOUND for verb in HDIUTIL_VERBS}\n")],
         [(FIGURES, "_bounds({'create': SHORT_BOUND})")]),
    Case('bounds-unknown-blind', 'x', [(BOUNDS_UNKNOWN, "    unknown = set()\n")], [(FIGURES, 'no such hdiutil verb')]),
    Case('ps-pgid-not-read', 'x', [(PS_ARGV, PS_ARGV.replace("'-o', 'pgid=', ", "'-o', 'pid=', "))],
         [(SURVIVOR, 'does not say what is still running')]),
    Case('ps-bound-dropped', 'x', [(PS_WAIT, "    out, err = proc.communicate(timeout=0)\n")],
         [(row('create-fails'), 'raised no HostFailure')]),
    Case('ps-lines-skipped', 'x', [(PS_LOOP, "    for line in out.decode(errors='replace').splitlines()[:1]:\n")],
         [(row('create-fails'), 'raised no HostFailure')]),
    Case('ps-group-column', 'x', [(PS_PARSE, PS_PARSE.replace("fields[1].isdigit()", "fields[1].isdigit() and fields[0] == fields[1]"))],
         [(SURVIVOR, 'is not named with its command')]),
    Case('ps-commandless', 'x', [(PS_ARGS, PS_ARGS.replace("fields[3] if len(fields) > 3 else ''", "''"))],
         [(row('create-fails'), 'raised no HostFailure')]),
    Case('ps-empty', 'x', [(PS_RETURN, "    return []\n")], [(SURVIVOR, 'does not say what is still running')]),
    Case('ps-self-unchecked', 'x', [(PS_SELF, "    if False:\n        raise HostFailure(")], []),
    Case('group-any', 'x', [(GROUP, GROUP.replace('group == pgid and ', ''))],
         [(row(r), 'names a survivor where none was left') for r in ('create-fails', 'create-hangs')]),
    Case('group-zombies-counted', 'x', [(GROUP, GROUP.replace(" and not state.startswith('Z')", ''))], []),
    Case('stop-eperm-raised', 'x', [(SUPPRESS, SUPPRESS.replace('ProcessLookupError, PermissionError', 'ProcessLookupError'))], []),
    Case('stop-esrch-raised', 'x', [(SUPPRESS, SUPPRESS.replace('ProcessLookupError, PermissionError', 'PermissionError'))],
         [(row('create-fails-alone'), 'raised no HostFailure')]),
    Case('stop-leader-unwaited', 'x', [(LEADER_WAIT, '')], []),
    Case('stop-poll-once', 'x', [(frozen.POLL, "    left = _group(proc.pid)\n")], []),
    Case('stop-streams-open', 'x', [(STREAMS, '')], []),
    Case('stop-unnamed-command', 'x', [(NAMED, NAMED.replace(' ({command})', ''))], [(SURVIVOR, 'is not named with its command')]),
    Case('step-own-group-dropped', 'x', [(POPEN, POPEN.replace('start_new_session=True', 'start_new_session=False'))],
         [(row('create-hangs'), LEFT), (row('create-fails'), LEFT)]),
    Case('step-failure-ignored', 'x', [(FAILED_TEST, "    if False:\n        left = _stop(proc)\n")],
         [(row(r), NO_HOST) for r in ('create-fails', 'attach-fails')]),
    Case('step-success-as-failure', 'x', [(SUCCESS, "    return 'succeeded', out\n\n\ndef _clean_up(")],
         [(row('every-step-succeeds'), 'raised although every step succeeded')]),
    Case('stderr-head', 'x', [(frozen.FAIL_TEXT, frozen.FAIL_TEXT.replace('[-400:]', '[:400]'))], []),
    Case('listing-type-unchecked', 'x', [(LISTING_TYPE, "            if False:\n")], []),
    Case('cleanup-first-entry-only', 'x', [(KEPT_RETURN, KEPT_RETURN + "        break\n")], []),
    Case('cleanup-loop-skipped', 'x', [(CLEAN_LOOP, "    for entry in []:\n")],
         [(row('attach-fails-with-device'), OWN)]),
    Case('cleanup-deviceless-detached', 'x', [(DEVICES, DEVICES.replace("        if not devices:\n            continue\n", ''))], []),
    Case('cleanup-mount-unnamed', 'x', [(MOUNTS, MOUNTS.replace("f' at {mounts[0]}' if mounts else ", ''))],
         [(row('cleanup-detach-fails'), 'stays attached at')]),
    Case('cleanup-kept-unnamed', 'x', [(KEPT_RETURN, "            return [failure]\n")],
         [(row('cleanup-detach-fails'), 'stays attached at')]),
    Case('attach-skipped', 'x', [(CREATE, "    if False:\n        where.mkdir()\n")],
         [(row('every-step-succeeds'), 'the body ran with a device')]),
    Case('attach-failure-ignored', 'x', [(ATTACH_FAILED, "    if False:\n        raise HostFailure('\\n'.join([failure, *_clean_up(hdiutil, bound, image)]))\n")],
         [(row(r), NO_HOST) for r in ('create-fails', 'attach-fails')]),
    Case('yield-elsewhere', 'x', [(YIELD, "    try:\n        yield where.parent\n")],
         [(row('every-step-succeeds'), 'the body ran with a device')]),
    Case('final-detach-skipped', 'x', [(FINAL_DETACH, "    failure = None\n")], [(row('every-step-succeeds'), OWN)],
         kind='additive'),
    Case('final-return-early', 'x', [(FINAL_DETACH, "    return\n" + FINAL_DETACH)], [(row('every-step-succeeds'), OWN)],
         kind='additive'),
    Case('final-failure-ignored', 'x', [(FINAL_DETACH, FINAL_DETACH.replace('    if failure is not None:\n', '    if False:\n'))],
         [(row('detach-fails'), NO_HOST)]),
    Case('cleanup-detach-skipped', 'x', [(frozen.CLEAN_DETACH, "        failure = None\n")],
         [(row('attach-fails-with-device'), OWN)], kind='additive'),
    Case('cleanup-unlink-skipped', 'x', [(frozen.CLEAN_UNLINK, "    return []\n")],
         [(row(r), IMAGE_LEFT) for r in ('create-fails-with-device', 'attach-fails')], kind='additive'),
    Case('cleanup-return-early', 'x', [(frozen.CLEAN_START, "    return []\n" + frozen.CLEAN_START)],
         [(row('attach-fails-with-device'), OWN)], kind='additive'),
    Case('stop-return-early', 'x', [(frozen.KILLPG, "        return ''\n" + frozen.KILLPG)],
         [(row('create-hangs'), LEFT)], kind='additive'),
    Case('step-return-early', 'x', [(POPEN, "    return None, b''\n" + POPEN)],
         [(row('every-step-succeeds'), 'the body ran with a device')], kind='additive'),
    Case('ps-self-returns', 'x', [(PS_RAISE, "        return listed\n" + PS_RAISE)], []),
    Case('stop-none-left-named', 'x', [(frozen.NO_LEFT, "    if not left:\n        return '; still running: nothing'\n")],
         [(row('create-fails'), 'names a survivor where none was left')]),
    Case('step-hang-uncaught', 'x', [(HANG_CATCH, HANG_CATCH.replace('subprocess.TimeoutExpired', 'ZeroDivisionError'))],
         [(row('create-hangs'), LEFT)]),
    Case('info-failure-read', 'x', [(INFO_READ, INFO_READ.replace('if failure is None', 'if True'))],
         [(row('info-fails-in-cleanup'), 'info: exited with status 1')]),
    Case('info-answer-dropped', 'x', [(INFO_LOAD, "            listing = {}\n")], [(row('attach-fails-with-device'), OWN)]),
    Case('info-failure-ignored', 'x', [(INFO_FAILED, "    if False:\n" + INFO_FAILED.split('\n', 1)[1])],
         [(row('info-fails-in-cleanup'), NO_HOST)]),
    Case('cleanup-slices-only', 'x', [(DEVICES_READ, DEVICES_READ.replace('for e in entities', 'for e in entities[1:]'))],
         [(row('attach-fails-with-device'), OWN)]),
    Case('cleanup-mounts-unread', 'x', [(MOUNTS_READ, "            mounts = []\n")], [(row('cleanup-detach-fails'), 'stays attached at')]),
    Case('cleanup-says-kept', 'x', [(frozen.CLEAN_UNLINK, "    image.unlink(missing_ok=True)\n    return [f'the image is kept at {image}']\n")],
         [(row('create-fails-with-device'), 'names an image kept where none was')]),
    Case('create-not-run', 'x', [(CREATE_STEP, CREATE_STEP.replace("_step(hdiutil, 'create',", "_step(hdiutil, 'info',"))],
         [(row('every-step-succeeds'), 'raised although every step succeeded')]),
    Case('mount-point-unmade', 'x', [(CREATE, "    if failure is None:\n        pass\n")], []),
    Case('attach-not-run', 'x', [(ATTACH_STEP, ATTACH_STEP.replace("_step(hdiutil, 'attach',", "_step(hdiutil, 'info',"))],
         [(row('every-step-succeeds'), 'the body ran with a device')]),
    Case('body-detach-failure-ignored', 'x', [(HANDLER + BODY_DETACH, HANDLER + BODY_DETACH.replace('        if failure is not None:\n', '        if False:\n'))],
         [(row('body-and-detach-fail'), NO_HOST)]),
    Case('narrow-to-exception', 'x', [(HANDLER, "    except Exception as body:\n")],
         [(r, OWN) for kind in NOT_EXCEPTION for r in body_rows(kind)[:1]]
         + [(r, NO_HOST) for kind in NOT_EXCEPTION for r in body_rows(kind)[1:]], kind='additive'),
]

# Cases expected to survive, each with its class and reason.
SURVIVORS = {
    'ps-self-unchecked': ('seeded', "the review's M25: defensive; `ps` answers in the parsed shape on both platforms"),
    'group-zombies-counted': ("seeded", "the review's M17: a zombie in the group is reaped at once, so none is seen"),
    'stop-eperm-raised': ('seeded', "the review's M24: defensive; the EPERM race on a group of zombies is never reached"),
    'stop-poll-once': ('seeded', "the review's M03: every process a row starts dies at the KILL, so one look finds none"),
    'stderr-head': ('seeded', "the review's M19: the stand-in's standard error is shorter than the 400-character tail"),
    'cleanup-first-entry-only': ('seeded', "the review's M30: no row makes two devices from one image"),
    'ps-self-returns': ('seeded', "with M25: the refusal of a listing without this process is never reached"),
    'stop-streams-open': ('seeded', "a stopped step's pipes stay open until its `Popen` is collected; no row counts open descriptors"),
    'listing-type-unchecked': ('seeded', "an `info` answer that is a plist but not a dictionary (a top-level array) is in no row; "
                                         "a deeper layer of `info-answers-garbled`"),
    'stop-leader-unwaited': ('seeded', "the poll that follows sees the step's own process gone once it is a zombie, so "
                                         "only its reaping waits until the `Popen` is collected; no row looks for zombies"),
    'cleanup-deviceless-detached': ('seeded', "an image entry with no `dev-entry` is in no row (every stand-in entry "
                                                "carries one); defensive"),
    'mount-point-unmade': ('equivalent', "`hdiutil attach -mountpoint` makes a missing directory itself and `detach` removes it "
                                         "(probed with the real tool on the build host, 2026-11-10); the stand-in needs none"),
}

NEW_CASES = DECISIONS + [c for kind in KIND_CLASS for c in families(kind)]


def decision_lines(text: str) -> dict[int, str]:
    """Each line of the fixture's functions that holds a decision node: line number to function."""
    calls = {'_step', '_stop', '_group', '_processes', '_clean_up', 'killpg', 'wait', 'communicate', 'sleep', 'unlink',
             'mkdir', 'REAL_POPEN', 'realpath', 'min', 'loads', 'monotonic', 'close', 'suppress'}
    found: dict[int, str] = {}
    for node in ast.parse(text).body:
        if not (isinstance(node, ast.FunctionDef) and node.name in FIXTURE):
            continue
        for sub in ast.walk(node):
            hit = isinstance(sub, (ast.If, ast.IfExp, ast.While, ast.For, ast.ExceptHandler, ast.Return, ast.Raise,
                                   ast.Assert, ast.Yield, ast.Compare, ast.BoolOp, ast.Continue, ast.Break))
            if isinstance(sub, ast.comprehension):
                for cond in sub.ifs:
                    found[cond.lineno] = node.name
            if isinstance(sub, ast.Call):
                func = sub.func
                name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ''
                hit = hit or name in calls
            if hit:
                found[sub.lineno] = node.name
    return found


def changed_lines(text: str, case: Case) -> set[int]:
    """The pristine lines a case's edits change, or insert before."""
    lines: set[int] = set()
    for old, new in case.edits:
        start = text.index(old)
        first = text.count('\n', 0, start) + 1
        olds, news = old.splitlines(), new.splitlines()
        for tag, i1, i2, _, _ in difflib.SequenceMatcher(a=olds, b=news, autojunk=False).get_opcodes():
            if tag in ('replace', 'delete'):
                lines.update(range(first + i1, first + i2))
            elif tag == 'insert':
                lines.add(first + min(i1, len(olds) - 1))
    return lines


def body_exit_kinds(text: str) -> list[str]:
    for node in ast.parse(text).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == 'BODY_EXITS':
            assert isinstance(node.value, ast.Dict)
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    raise AssertionError('no BODY_EXITS in the module')


def coverage() -> int:
    text = (ROOT / MODULE).read_text()
    problems = []
    every = frozen.CASES + NEW_CASES
    names = [c.name for c in every]
    problems += [f'duplicate case {n}' for n in sorted({n for n in names if names.count(n) > 1})]
    for case in every:
        try:
            frozen.apply(text, case.edits)
        except ValueError as exc:
            problems.append(f'{case.name}: {exc}')
    if problems:
        print('\n'.join(problems))
        return 1
    covered: set[int] = set()
    for case in every:
        covered |= changed_lines(text, case)
    sites = decision_lines(text)
    source = text.splitlines()
    missing = {n: f for n, f in sites.items() if n not in covered}
    for n, f in sorted(missing.items()):
        problems.append(f'no case changes {f} line {n}: {source[n - 1].strip()}')
    kinds = body_exit_kinds(text)
    if sorted(kinds) != sorted(KIND_CLASS):
        problems.append(f'BODY_EXITS {sorted(kinds)} is not the swept kinds {sorted(KIND_CLASS)}')
    for kind in kinds:
        for family in FAMILIES:
            if f'{family}-{kind}' not in names:
                problems.append(f'no case {family}-{kind}')
    for name, (cls, _) in SURVIVORS.items():
        if name not in names or cls not in ('seeded', 'equivalent'):
            problems.append(f'survivor entry {name}: no such case, or class {cls!r}')
    for case in NEW_CASES:
        if not case.rows and case.name not in SURVIVORS:
            problems.append(f'{case.name}: names no row and is not an expected survivor')
    print(f'coverage: {len(sites)} decision lines in {len(FIXTURE)} functions, {len(sites) - len(missing)} changed by a case; '
          f'{len(kinds)} body exits x {len(FAMILIES)} families; {len(frozen.CASES)} frozen + {len(NEW_CASES)} new cases; '
          f'{len(SURVIVORS)} expected survivors')
    if problems:
        print('\n'.join(problems))
        return 1
    print('F2-fixture-sweep.py coverage: ok')
    return 0


def run_rows(copy: Path, ids: list[str], era: str | None) -> tuple[dict[str, tuple[str, str]], str]:
    """Run `ids` in `copy` in one era; each id's outcome and text, and a note (the frozen runner's, with the era)."""
    junit = copy / 'junit.xml'
    env = {k: v for k, v in os.environ.items() if k != 'CLUSTER_MCP_TEST_ERA'}
    if era:
        env['CLUSTER_MCP_TEST_ERA'] = era
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
            if bad is not None:
                results[name] = ('failed', (bad.get('message') or '') + '\n' + (bad.text or ''))
            elif case.find('skipped') is not None:
                results[name] = ('skipped', case.find('skipped').get('message') or '')  # type: ignore[union-attr]
            else:
                results[name] = ('passed', '')
    if not results:
        note = (note + '; ' if note else '') + 'no results: ' + out.decode(errors='replace')[-600:]
    return results, note


def all_ids() -> list[str]:
    """Every disk-image test id the module collects: the rows, the survivor and the two unit tests."""
    collected = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--collect-only', '-p', 'no:cacheprovider', MODULE,
                                '-k', 'disk_image or stopped_step or body_can_end'],
                               capture_output=True, text=True, timeout=120).stdout
    return sorted(line.split('::', 1)[1] for line in collected.splitlines() if line.startswith(f'{MODULE}::'))


def judge(case: Case, era: str | None, everything: list[str]) -> tuple[str, str, float]:
    """Plant one case in a fresh copy and run it: (killed | survived | unviable | timeout | red, detail, seconds).

    A case expected to survive runs every disk-image id and survives only when all pass; any other
    case is killed only when every row it names fails with that row's `why`.
    """
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
        results, note = run_rows(copy, ids, era)
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
            return ('killed', 'failed: ' + '; '.join(failed) + extra, took) if failed else \
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


def sweep(cases: list[Case], era: str | None, label: str) -> int:
    started = time.monotonic()
    everything = all_ids()
    if len(everything) < 39:
        print(f'F2-fixture-sweep.py {label}: only {len(everything)} disk-image ids collected')
        return 1
    ids = sorted({i for c in cases for i, _ in c.rows} | (set(everything) if any(c.name in SURVIVORS for c in cases) else set()))
    copy = frozen.make_copy()
    try:
        results, note = run_rows(copy, ids, era)
        bad = [i for i in ids if results.get(i, ('missing', ''))[0] != 'passed']
        print(f'baseline ({label}): {len(ids) - len(bad)} of {len(ids)} rows passed unchanged' + (f' ({note})' if note else ''),
              flush=True)
    finally:
        frozen.kill_token(copy.name)
        frozen.shutil.rmtree(copy, ignore_errors=True)
    if bad:
        print('  ' + '\n  '.join(bad))
        print(f'F2-fixture-sweep.py {label}: the baseline is red; no case can be judged')
        return 1
    counts: dict[str, list[str]] = {k: [] for k in ('killed', 'against', 'seeded', 'equivalent', 'survived', 'unviable',
                                                     'timeout', 'red')}
    for case in cases:
        status, detail, took = judge(case, era, everything)
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
    print(f'F2-fixture-sweep.py {label}: {len(cases)} generated, {len(counts["killed"]) + len(counts["against"])} killed, '
          f'{len(counts["survived"])} survived, {len(counts["seeded"])} seeded and {len(counts["equivalent"])} equivalent '
          f'(expected survivors), {len(counts["unviable"])} unviable, {len(counts["timeout"])} timed out, 0 unrun, '
          f'in {took / 60:.1f} min'
          + ''.join(f'; {k}: {", ".join(v)}' for k, v in counts.items() if v and k in ('against', 'survived', 'unviable',
                                                                                         'timeout', 'red')), flush=True)
    return 1 if counts['survived'] or counts['unviable'] or counts['timeout'] or counts['red'] else 0


def rows() -> int:
    """Every disk-image test id, by exact id, PASSED in both eras; none skipped."""
    text = (ROOT / MODULE).read_text()
    kinds = body_exit_kinds(text)
    ids = all_ids()
    need = {r for kind in kinds for r in body_rows(kind)} | {FIGURES, SURVIVOR, EVERY_EXIT, row('create-fails-alone')}
    missing = sorted(need - set(ids))
    if missing or len(ids) < 18 + 2 * (len(kinds) - 1) + 3:
        print(f'F2-fixture-sweep.py rows: collected {len(ids)} ids; missing {missing}')
        return 1
    for label, era in ERAS.items():
        copy = frozen.make_copy()
        try:
            results, note = run_rows(copy, ids, era)
        finally:
            frozen.kill_token(copy.name)
            frozen.shutil.rmtree(copy, ignore_errors=True)
        bad = [f'{i}: {results.get(i, ("missing", ""))[0]}' for i in ids if results.get(i, ('missing', ''))[0] != 'passed']
        if bad:
            print(f'F2-fixture-sweep.py rows: era {label}: ' + '; '.join(bad) + (f' ({note})' if note else ''))
            return 1
        print(f'F2-fixture-sweep.py rows: era {label}: {len(ids)} ids passed, none skipped')
    print('F2-fixture-sweep.py rows: ok')
    return 0


MODES = {
    'new-legacy-a': (DECISIONS, 'legacy'),
    'new-legacy-b': ([c for c in NEW_CASES if c not in DECISIONS], 'legacy'),
    'new-modern-a': (DECISIONS, 'modern'),
    'new-modern-b': ([c for c in NEW_CASES if c not in DECISIONS], 'modern'),
    'frozen-modern': (frozen.CASES, 'modern'),
}


def main(mode: str) -> int:
    if mode == 'coverage':
        return coverage()
    if mode not in MODES and mode != 'rows':
        print(f'usage: F2-fixture-sweep.py coverage|rows|{"|".join(MODES)}', file=sys.stderr)
        return 2
    if coverage() != 0:
        return 1
    if mode == 'rows':
        return rows()
    cases, era = MODES[mode]
    return sweep(cases, ERAS[era], mode)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
