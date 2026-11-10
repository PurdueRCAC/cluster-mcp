"""Mutant sweep for full-volume-fixture-leaks-hdiutil: every decision the disk-image fixture makes,
and every carve-out it must not have, is shown pinned by a row.

Usage, from the cycle worktree root:  uv run python -I spec/full-volume-fixture-leaks-hdiutil/verify/mutants.py a|b

Each case plants one exact change (one or more edits, each of which must apply exactly once to the
pristine text, or the case is red) into a fresh `mktemp -d` copy of `tests/`, `bin/` and the
top-level files, then runs the case's named rows there in one era (the handshake era), with
`-p no:cacheprovider`, pytest's base directory inside the copy, and a 300 s cap: pytest starts in a
session of its own, and its process group is KILLed at the cap. A case is killed only when every
named row fails and its failure text carries the row's `why`. After each case, anything still
running whose command names the copy's token (the directory's unique name, which no other process
holds) is KILLed, and a second listing must find nothing. Before the cases, each mode runs its rows
on an unchanged copy, which must pass: a kill against a red baseline would be hollow.

Modes `a` and `b` split the cases by name (each case states its half), so adding a case re-runs only
its own half. `bound-constant` (a 120 s hang) is in the smaller half.

Footprint: one pytest at a time; peak about 6 processes (the driver, pytest, a sandbox script, a
stand-in, its child, ps); under 500 MB; a copy of about 4 MB per case, removed after it.
Time, measured on the build host (macOS 27, load average 4 to 10; the runs recorded in
mutant-sweep.md): mode a 4.3 min, mode b 1.6 min.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path.cwd()
MODULE = 'tests/test_ssh_exec.py'
ROWS = 'test_a_disk_image_step_that_fails_or_hangs_leaves_nothing_running'
SURVIVOR = 'test_a_stopped_step_still_running_is_named'
FIGURES = 'test_the_disk_image_figures'
CAP = 300

LEFT = 'still running after the fixture'
OWN = 'of its own devices left attached'
FOREIGN = 'it did not make was detached'


def row(name: str) -> str:
    return f'{ROWS}[{name}]'


@dataclass
class Case:
    name: str
    half: str
    edits: list[tuple[str, str]]
    rows: list[tuple[str, str]]
    kind: str = 'decision'
    path: str = MODULE
    extra: list[tuple[str, str, str]] = field(default_factory=list)


STOP_SIG = "STOP_SIGNAL = signal.SIGKILL\n"
KILLPG = "        os.killpg(proc.pid, STOP_SIGNAL)\n"
POLL = "    while (left := _group(proc.pid)) and time.monotonic() < deadline:\n        time.sleep(0.05)\n"
DEADLINE = "    deadline = time.monotonic() + STOP_WAIT\n"
NO_LEFT = "    if not left:\n        return ''\n"
COMMUNICATE = "        out, err = proc.communicate(timeout=bound)\n"
HANG_TEXT = "        return f'{verb}: ran past its bound of {bound} s and was stopped' + _stop(proc), b''\n"
FAIL_STOP = "        left = _stop(proc)\n"
FAIL_TEXT = "        return f'{verb}: exited with status {proc.returncode}: {err.decode(errors=\"replace\")[-400:].strip()}' + left, out\n"
STEP_DEF = "def _step(hdiutil: tuple[str, ...], verb: str, bound: float, *args: str) -> tuple[str | None, bytes]:\n"
STEP_DEF_STOP = "def _step(hdiutil: tuple[str, ...], verb: str, bound: float, *args: str, stop: bool = True) -> tuple[str | None, bytes]:\n"
CLEANUP_CALL = "        raise HostFailure('\\n'.join([failure, *_clean_up(hdiutil, bound, image)]))\n"
MATCH = "        if os.path.realpath(entry.get('image-path', '')) != os.path.realpath(image):\n            continue\n"
WHOLE = "        device = min(devices, key=len)\n"
CLEAN_START = "    failure, out = _step(hdiutil, 'info', bound['info'], '-plist')\n"
CLEAN_UNLINK = "    image.unlink(missing_ok=True)\n    return []\n"
INFO_KEEP = "        return [failure, f'the image is kept at {image}, and any device made from it stays attached']\n"
LISTING = "        except Exception as exc:\n            failure = f'info: answered with no listing ({type(exc).__name__}: {exc})'\n"
CLEAN_DETACH = "        failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', device)\n"
CLEAN_FAILED = "        if failure is not None:\n            mounts = "
LEFT_TEXT = "    left = f'the volume stays attached at {where}, and its image is kept at {image}'\n"
BODY_RAISE = "            raise HostFailure(f'{failure}\\n{left}') from body\n"
BODY_UNLINK = "        image.unlink()\n        raise\n"
FINAL = ("    failure, _ = _step(hdiutil, 'detach', bound['detach'], '-force', str(where))\n"
         "    if failure is not None:\n        raise HostFailure(f'{failure}\\n{left}')\n    image.unlink()\n")
BOUND_FIG = "HDIUTIL_BOUND = 120\n"
WAIT_FIG = "STOP_WAIT = 5\n"


def skip_stop(condition: str) -> list[tuple[str, str]]:
    """Edits that skip the stop in `_step` when `condition` (on `verb` and `stop`) holds."""
    return [(STEP_DEF, STEP_DEF_STOP),
            (HANG_TEXT, HANG_TEXT.replace("+ _stop(proc), b''", f"+ ('' if {condition} else _stop(proc)), b''")),
            (FAIL_STOP, f"        left = '' if {condition} else _stop(proc)\n")]


HANG_ROWS = ['create-hangs', 'create-hangs-with-device', 'attach-hangs', 'attach-hangs-with-device', 'detach-hangs',
             'cleanup-detach-hangs']

CASES = [
    # Decisions the fixture makes.
    Case('stop-term', 'a', [(STOP_SIG, "STOP_SIGNAL = signal.SIGTERM\n")],
         [(row('create-hangs'), LEFT), (row('detach-hangs'), LEFT), (FIGURES, 'SIGKILL')]),
    Case('stop-step-only', 'a', [(KILLPG, "        os.kill(proc.pid, STOP_SIGNAL)\n")],
         [(row(r), LEFT) for r in HANG_ROWS]),
    Case('wait-dropped', 'b', [(POLL, "    left = []\n")], [(SURVIVOR, 'does not say what is still running')]),
    Case('wait-x10', 'b', [(DEADLINE, "    deadline = time.monotonic() + STOP_WAIT * 10\n")], [(SURVIVOR, 'the run took')]),
    Case('survivors-unnamed', 'b', [(NO_LEFT, "    if True:\n        return ''\n")],
         [(SURVIVOR, 'does not say what is still running')]),
    Case('bound-constant', 'a', [(COMMUNICATE, "        out, err = proc.communicate(timeout=HDIUTIL_BOUND)\n")],
         [(row('create-hangs'), 'past its limit')]),
    Case('bound-misnamed', 'a', [(HANG_TEXT, HANG_TEXT.replace('{bound} s', '{HDIUTIL_BOUND} s'))],
         [(row('create-hangs'), 'ran past its bound of 1 s'), (row('detach-hangs'), 'ran past its bound of 1 s')]),
    Case('status-dropped', 'a', [(FAIL_TEXT, FAIL_TEXT.replace('exited with status {proc.returncode}', 'exited'))],
         [(row(r), 'exited with status 1') for r in ('create-fails', 'attach-fails', 'detach-fails', 'info-fails-in-cleanup')]),
    Case('stderr-dropped', 'a', [(FAIL_TEXT, FAIL_TEXT.replace('{err.decode(errors="replace")[-400:].strip()}', ''))],
         [(row(r), 'failed - stand-in failure') for r in ('create-fails', 'attach-fails', 'detach-fails')]),
    Case('cleanup-attach-only', 'a',
         [(CLEANUP_CALL, CLEANUP_CALL.replace('*_clean_up(hdiutil, bound, image)',
                                              '*(_clean_up(hdiutil, bound, image) if where.exists() else [])'))],
         [(row('create-hangs-with-device'), OWN), (row('create-fails-with-device'), OWN)]),
    Case('match-by-string', 'a',
         [(MATCH, MATCH.replace("os.path.realpath(entry.get('image-path', '')) != os.path.realpath(image)",
                                "entry.get('image-path', '') != str(image)"))],
         [(row(r), OWN) for r in ('create-hangs-with-device', 'create-fails-with-device', 'attach-hangs-with-device',
                                  'attach-fails-with-device')]
         + [(row('cleanup-detach-hangs'), 'the image is gone')]),
    Case('slice-not-disk', 'a', [(WHOLE, "        device = max(devices, key=len)\n")],
         [(row(r), OWN) for r in ('create-hangs-with-device', 'create-fails-with-device', 'attach-hangs-with-device',
                                  'attach-fails-with-device')]),
    Case('unlink-first', 'a', [(CLEAN_START, "    image.unlink(missing_ok=True)\n" + CLEAN_START)],
         [(row('cleanup-detach-hangs'), 'the image is gone')]),
    Case('unlink-strict', 'a', [(CLEAN_UNLINK, "    image.unlink()\n    return []\n")],
         [(row('create-hangs'), 'raised no HostFailure'), (row('create-fails'), 'raised no HostFailure')]),
    Case('info-ignored', 'b', [(INFO_KEEP, "        image.unlink(missing_ok=True)\n" + INFO_KEEP)],
         [(row('info-fails-in-cleanup'), 'the image is gone'), (row('info-answers-garbled'), 'the image is gone')]),
    Case('left-unnamed', 'b', [(LEFT_TEXT, "    left = ''\n")],
         [(row('detach-hangs'), 'the volume stays attached at'), (row('detach-fails'), 'the volume stays attached at')]),
    Case('chain-dropped', 'b', [(BODY_RAISE, BODY_RAISE.replace('from body', 'from None'))],
         [(row('body-and-detach-fail'), 'not caused by the body')]),
    Case('order-swapped', 'b',
         [(CLEANUP_CALL, CLEANUP_CALL.replace('[failure, *_clean_up(hdiutil, bound, image)]',
                                              '[*_clean_up(hdiutil, bound, image), failure]'))],
         [(row('cleanup-detach-hangs'), 'in order')]),
    Case('unlink-dropped', 'b', [(FINAL, FINAL.replace('    image.unlink()\n', ''))],
         [(row('every-step-succeeds'), 'the image was left')]),
    Case('detach-image', 'b', [(FINAL, FINAL.replace("'-force', str(where))", "'-force', str(image))"))],
         [(row('every-step-succeeds'), 'raised although every step succeeded')]),
    Case('figures-bound', 'b', [(BOUND_FIG, "HDIUTIL_BOUND = 60\n")], [(FIGURES, '120')]),
    Case('figures-wait', 'b', [(WAIT_FIG, "STOP_WAIT = 50\n")], [(FIGURES, '50 == 5')]),
    Case('raise-dropped', 'b', [(BODY_UNLINK, "        image.unlink()\n")],
         [(row('body-fails'), "the body's own failure was not raised unchanged")]),
    Case('unlink-dropped-on-body', 'b', [(BODY_UNLINK, "        raise\n")], [(row('body-fails'), 'the image was left')]),
    Case('match-basename', 'b',
         [(MATCH, MATCH.replace("os.path.realpath(entry.get('image-path', '')) != os.path.realpath(image)",
                                "Path(entry.get('image-path', '')).name != image.name"))],
         [(row(r), FOREIGN) for r in ('create-hangs', 'attach-fails', 'attach-hangs-with-device')]),
    Case('listing-unread', 'b', [(LISTING, LISTING.replace('except Exception', 'except ZeroDivisionError'))],
         [(row('info-answers-garbled'), 'raised no HostFailure')]),
    # Carve-outs the fixture must not have: each adds a step it does not take, or skips one it takes.
    Case('no-stop-detach', 'a', skip_stop("verb == 'detach'"),
         [(row('detach-hangs'), LEFT), (row('cleanup-detach-hangs'), LEFT)], kind='additive'),
    Case('no-stop-cleanup', 'a', skip_stop('not stop') + [(CLEAN_DETACH, CLEAN_DETACH.replace('device)', 'device, stop=False)'))],
         [(row('cleanup-detach-hangs'), LEFT)], kind='additive'),
    Case('no-stop-info', 'a', skip_stop("verb == 'info'"), [(row('info-fails-in-cleanup'), LEFT)], kind='additive'),
    Case('no-stop-on-fail', 'a', [(FAIL_STOP, "        left = ''\n")],
         [(row(r), LEFT) for r in ('create-fails', 'attach-fails', 'detach-fails', 'info-fails-in-cleanup')], kind='additive'),
    Case('no-stop-on-attach-fail', 'a', [(FAIL_STOP, "        left = '' if verb == 'attach' else _stop(proc)\n")],
         [(row('attach-fails'), LEFT), (row('attach-fails-with-device'), LEFT)], kind='additive'),
    Case('no-stop-on-detach-fail', 'a', [(FAIL_STOP, "        left = '' if verb == 'detach' else _stop(proc)\n")],
         [(row(r), LEFT) for r in ('detach-fails', 'body-and-detach-fail', 'cleanup-detach-fails')], kind='additive'),
    Case('no-cleanup-on-hang', 'a',
         [(CLEANUP_CALL, CLEANUP_CALL.replace('*_clean_up(hdiutil, bound, image)',
                                              "*([] if 'ran past its bound' in failure else _clean_up(hdiutil, bound, image))"))],
         [(row('create-hangs-with-device'), OWN), (row('attach-hangs-with-device'), OWN)], kind='additive'),
    Case('no-unlink-without-device', 'a',
         [(CLEAN_UNLINK, "    if any(os.path.realpath(e.get('image-path', '')) == os.path.realpath(image)"
                         " for e in listing.get('images', [])):\n        image.unlink(missing_ok=True)\n    return []\n")],
         [(row('attach-hangs'), 'the image was left'), (row('attach-fails'), 'the image was left')], kind='additive'),
    Case('retry-detach', 'b',
         [(BODY_RAISE, "            raise HostFailure('\\n'.join([failure, left, *_clean_up(hdiutil, bound, image)])) from body\n"),
          (FINAL, FINAL.replace("raise HostFailure(f'{failure}\\n{left}')",
                                "raise HostFailure('\\n'.join([failure, left, *_clean_up(hdiutil, bound, image)]))"))],
         [(row(r), f'{OWN}, not 1') for r in ('detach-hangs', 'detach-fails', 'body-and-detach-fail')], kind='additive'),
    Case('retry-cleanup-detach', 'b',
         [(CLEAN_FAILED, "        if failure is not None:\n"
                         "            failure = _step(hdiutil, 'detach', bound['detach'], '-force', device)[0] and failure\n"
                         + CLEAN_FAILED)],
         [(row('cleanup-detach-hangs'), f'{OWN}, not 1'), (row('cleanup-detach-fails'), f'{OWN}, not 1')], kind='additive'),
    Case('no-left-on-body', 'b', [(BODY_RAISE, "            raise HostFailure(failure) from body\n")],
         [(row('body-and-detach-fail'), 'the volume stays attached at')], kind='additive'),
    Case('match-any', 'b', [(MATCH, '')],
         [(row(r), FOREIGN) for r in ('create-hangs', 'attach-hangs', 'attach-fails-with-device')], kind='additive'),
    Case('term-then-kill', 'b',
         [(KILLPG, "        os.killpg(proc.pid, signal.SIGTERM)\n        time.sleep(1)\n" + KILLPG)],
         [(row('create-hangs'), 'sent TERM'), (row('detach-hangs'), 'sent TERM')], kind='additive'),
    Case('survivor-always', 'b', [(NO_LEFT, "    if False:\n        return ''\n")],
         [(row(r), 'names a survivor where none was left') for r in ('create-fails', 'create-hangs', 'detach-fails')],
         kind='additive'),
]


def processes() -> list[tuple[int, str]]:
    out = subprocess.run(['ps', '-A', '-ww', '-o', 'pid=', '-o', 'args='], capture_output=True, text=True, timeout=30).stdout
    found = []
    for line in out.splitlines():
        pid, _, command = line.strip().partition(' ')
        if pid.isdigit():
            found.append((int(pid), command))
    assert any(pid == os.getpid() for pid, _ in found), 'ps did not list this process'
    return found


def kill_token(token: str) -> int:
    """KILL every process whose command names `token`; return how many there were."""
    hit = [pid for pid, command in processes() if token in command]
    for pid in hit:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    return len(hit)


def make_copy() -> Path:
    copy = Path(tempfile.mkdtemp(prefix='fvfl-sweep.'))
    for name in os.listdir(ROOT):
        source = ROOT / name
        if source.is_file() and not name.startswith('.'):
            shutil.copy2(source, copy / name)
    for tree in ('tests', 'bin'):
        shutil.copytree(ROOT / tree, copy / tree, ignore=shutil.ignore_patterns('__pycache__'), symlinks=True)
    return copy


def run_rows(copy: Path, ids: list[str]) -> tuple[dict[str, tuple[str, str]], str]:
    """Run `ids` in `copy`, in the handshake era; return each id's outcome and text, and a note."""
    junit = copy / 'junit.xml'
    env = {k: v for k, v in os.environ.items() if k != 'CLUSTER_MCP_TEST_ERA'}
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
                results[name] = ('failed', (bad.get('message') or '') + '\n' + (bad.text or ''))
            elif skipped is not None:
                results[name] = ('skipped', skipped.get('message') or '')
            else:
                results[name] = ('passed', '')
    if not results:
        note = (note + '; ' if note else '') + 'no results: ' + out.decode(errors='replace')[-600:]
    return results, note


def apply(text: str, edits: list[tuple[str, str]]) -> str:
    for old, new in edits:
        count = text.count(old)
        if count != 1:
            raise ValueError(f'an edit applies {count} times, not once: {old[:80]!r}')
        text = text.replace(old, new)
    return text


def run_case(case: Case) -> tuple[bool, str, float]:
    copy = make_copy()
    token = copy.name
    started = time.monotonic()
    try:
        target = copy / case.path
        try:
            target.write_text(apply(target.read_text(), case.edits))
        except ValueError as exc:
            return False, f'not planted: {exc}', time.monotonic() - started
        ids = [i for i, _ in case.rows]
        results, note = run_rows(copy, ids)
        verdicts = []
        for i, why in case.rows:
            outcome, text = results.get(i, ('missing', ''))
            if outcome != 'failed':
                verdicts.append(f'{i}: {outcome}')
            elif why not in text:
                verdicts.append(f'{i}: failed without {why!r}: {" ".join(text.split())[:300]}')
        left = kill_token(token)
        time.sleep(0.2)
        if kill_token(token):
            verdicts.append(f'processes naming {token} still ran after a KILL')
        detail = '; '.join(filter(None, [note, f'{left} left processes KILLed' if left else '']))
        return not verdicts, '; '.join(verdicts) or detail or 'killed', time.monotonic() - started
    finally:
        kill_token(token)
        shutil.rmtree(copy, ignore_errors=True)


def baseline(cases: list[Case]) -> bool:
    """The rows every case of this mode names must pass on an unchanged copy."""
    ids = sorted({i for case in cases for i, _ in case.rows})
    copy = make_copy()
    try:
        results, note = run_rows(copy, ids)
        bad = [f'{i}: {results.get(i, ("missing", ""))[0]}' for i in ids if results.get(i, ('missing', ''))[0] != 'passed']
        kill_token(copy.name)
        print(f'baseline: {len(ids) - len(bad)} of {len(ids)} rows passed unchanged' + (f' ({note})' if note else ''), flush=True)
        for line in bad:
            print(f'  {line}', flush=True)
        return not bad
    finally:
        kill_token(copy.name)
        shutil.rmtree(copy, ignore_errors=True)


def main(mode: str) -> int:
    if mode not in ('a', 'b'):
        print('usage: mutants.py a|b', file=sys.stderr)
        return 2
    names = [c.name for c in CASES]
    assert len(names) == len(set(names)), 'duplicate case names'
    cases = [c for c in CASES if c.half == mode]
    assert cases, 'no cases in this mode'
    started = time.monotonic()
    if not baseline(cases):
        print(f'mutants.py {mode}: the baseline is red; no case can be judged', flush=True)
        return 1
    survived = []
    for case in cases:
        killed, detail, took = run_case(case)
        print(f'{case.name} ({case.kind}): {"KILLED" if killed else "SURVIVED"} in {took:.1f} s; {detail}', flush=True)
        if not killed:
            survived.append(case.name)
    took = time.monotonic() - started
    print(f'mutants.py {mode}: {len(cases) - len(survived)} of {len(cases)} killed in {took / 60:.1f} min'
          + (f'; survived: {", ".join(survived)}' if survived else ''), flush=True)
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ''))
