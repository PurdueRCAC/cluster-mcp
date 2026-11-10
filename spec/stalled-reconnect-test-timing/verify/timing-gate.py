"""The cycle's gate: each timing row still catches what it guards, and no longer fails on a busy host.

Run from the worktree root, one mode at a time:

    UV_PYTHON=3.14 uv run -q python -I spec/stalled-reconnect-test-timing/verify/timing-gate.py <mode> [row]

Modes:

Every mode reads the tree under test from the index (`git write-tree`), as staged before a phase's
verify, never the working copy; "HEAD" below is that staged tree.

- `values [row…]`: R9 and the non-goals, read from the staged text. Every bound keeps its value
  (STALL_WINDOW, STALL_LATE, STALL_WORKER; ATTEMPT_POLL; BOUND, SLACK, BOUND / 2; 0.3 / 0 + 0.5), the
  four rows carry no skip, xfail or flaky mark and no skip, xfail or early return in their bodies,
  and each named row carries its design's reference point (PLAN § 2).
- `scope`: the cycle's diff from BASE touches only the files PLAN names (nothing under `packages/`,
  `.github/` or `bin/`, no profile row, no lock), and each era collects the same ids of the four rows
  as BASE does (R8, Non-goals).
- `rows <row>`: the row's tests pass in both eras.
- `faults <row>`: each planted product fault of the row's decision list (PLAN § 6) turns every target
  red with its fragment, through `tests/mutants.py`'s `Case` and `run_case` (the runner unchanged).
- `controls <row>`: under its stall (`srtt_stall.py`), the row passes on HEAD and fails on BASE with
  the fragment of the sighting, both trees read from their commits.
- `cases`: every existing `mutants.CASES` entry that names one of the four rows is still killed.
- `row <row>`: values for the row, scope, rows, faults, controls: P1-P4's phase gate.
- `sweep <part>`: the final sweep on HEAD, one part a run (`1`-`4`, `cases`), each appended to
  `verify/sweep.txt` with HEAD's `tests/` tree (`times`: each touched row's module on BASE and HEAD, R8's local evidence);
  `sweep-check` says the record covers every part on HEAD's `tests/` tree.
- `profile run|check`: the profile's `verify` once on the final tree, recorded in
  `verify/profile-verify.txt` (`run`, about 25 min, in the background), and the record's verdict.
- `ledger`: every deferral TECH.md's phases or the branch's commit bodies name has an `issues/` seed
  and a ROADMAP entry.

Footprint: one child at a time (a pytest, or a mutant child under bin/sandbox.sh), at most about
3 processes and 400 MB; two `git archive` copies of the tree (about 8 MB each) under a temp dir,
removed on exit.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

SLUG = 'stalled-reconnect-test-timing'
SPEC = Path('spec') / SLUG
HERE = Path(__file__).resolve().parent
# The GOAL's sign-off commit, the tree the cycle starts from: its rows are the "before".
BASE = 'abe12e3'
ERAS = ({}, {'CLUSTER_MCP_TEST_ERA': 'modern'})

SSH = 'tests/test_ssh_exec.py'
PROBES = 'tests/test_probes.py'
STARTUP = 'tests/test_probe_startup.py'
ROW_TESTS = {
    1: (SSH, 'test_a_stalled_reconnect_is_abandoned_against_a_real_handshake'),
    2: (SSH, 'test_a_reconnect_worker_that_cannot_start_frees_the_attempt'),
    3: (PROBES, 'test_every_ending_without_an_answer_serves_the_capability'),
    4: (STARTUP, 'test_every_ending_without_an_answer_serves_every_capability'),
}
RAISED = ('none', 'a-str', 'stdout-none', 'exception', 'exception-over-lines', 'os-error', 'unprintable', 'exit-0',
          'exit-3', 'exit-text', 'exit-none', 'base-exception', 'interrupt', 'thread-cannot-start')
MEMBER_SETS = ('core-only', 'slurm', 'rcac', 'both')
# How many tests each row runs in an era: row 4 is its 12 endings by 4 modes by 4 member sets.
COUNTS = {1: 1, 2: 1, 3: 56, 4: 192}


def row_ids(row: int) -> list[str]:
    """The node ids of the row: row 3 is its RAISED parameters only (GOAL, Problem 3)."""
    module, test = ROW_TESTS[row]
    if row == 3:
        return [f'{module}::{test}[{e}-{n}]' for e in RAISED for n in MEMBER_SETS]
    return [f'{module}::{test}']


# --- values -------------------------------------------------------------------------------------

# Module-level bindings that must keep their text (R9).
CONSTANTS = {
    SSH: {'STALL_WINDOW': 'ssh.RECONNECT_FACTOR * 1', 'STALL_LATE': '0.5', 'STALL_WORKER': '1.0'},
    PROBES: {'BOUND': '0.3', 'SLACK': '0.5', 'RAISED': repr(RAISED).replace('"', "'")},
}
# Code each row must hold on any tree, matched against the unparsed AST of the row and every function
# nested in it (never a comment or a string): the bound, compared as the base compares it (R9).
KEPT = {
    1: ("not_run_violations(result, 'timed out', took, STALL_WINDOW, host=LOOPBACK, slack=STALL_LATE)",
        'worker.join(STALL_WORKER)'),
    2: (),
    3: ('took <= BOUND + SLACK',),
    4: ("observed.seconds >= (0.3 if ending in ('hang', 'timeout-code') else 0) + 0.5",),
}
# Code each row holds once its phase has built it: the new reference point (PLAN § 2).
BUILT = {
    1: ("monkeypatch.setattr(threading.Thread, 'start', start)",),
    2: ('round(spent, 9) >= ssh.ATTEMPT_POLL', 'ensured >= ssh.ATTEMPT_POLL', "monkeypatch.setattr(ssh, '_await', wait)"),
    3: ("monkeypatch.setattr(probes, 'time', clock.time)", "monkeypatch.setattr(probes, 'threading', clock.threading)",
        "monkeypatch.setattr(time, 'sleep', clock.routed_sleep)", 'waited < BOUND / 2',
        'isinstance(pending._answered, clock.Event)'),
    4: ('collector_paused()',),
}
# Text each built row's failure messages carry (the fragments the faults and controls read, R7).
MESSAGES = {
    1: ('reconnect workers started during the call, not one', 'still running'),
    2: ("on the row's clock", 'from entering its reconnect to giving up', 'waited on an attempt'),
    3: ('decided only at the deadline', "did not take its deadline and its wait on the row's clock"),
    4: ('the start took', 'the collector pausing it'),
}
FORBIDDEN_MARKS = ('skip', 'skipif', 'xfail', 'flaky')
FORBIDDEN_CALLS = ('skip', 'xfail', 'importorskip', 'SkipTest', 'Exception')
# What no added line of the three modules may carry: a skip, a retry or a condition on the suite's load.
FORBIDDEN_ADDED = re.compile(r'\b(skip|skipif|xfail|flaky|rerun|reruns|SkipTest|pytestmark|autouse|getloadavg|'
                             r'session\.items|get_count|get_stats|cpu_count|except\s+AssertionError|'
                             r'except\s+Exception|except\s+BaseException|PYTEST_CURRENT_TEST)\b')


def staged() -> str:
    """The tree the index holds: what the phase staged before its verify."""
    return subprocess.run(['git', 'write-tree'], check=True, capture_output=True, text=True).stdout.strip()


def committed(rev: str, name: str) -> str:
    return subprocess.run(['git', 'show', f'{rev}:{name}'], check=True, capture_output=True, text=True).stdout


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise LookupError(name)


def _own_nodes(func: ast.FunctionDef):
    """The nodes of `func`'s body, not those of functions or classes defined inside it."""
    nested = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    stack = [node for node in func.body if not isinstance(node, nested)]
    while stack:
        node = stack.pop()
        yield node
        stack += [child for child in ast.iter_child_nodes(node) if not isinstance(child, nested)]


def _code(func: ast.FunctionDef) -> set[str]:
    """Every expression and statement of `func`, nested functions included, unparsed: code, never comments."""
    return {ast.unparse(node) for node in ast.walk(func) if isinstance(node, (ast.expr, ast.stmt))}


def merge_base() -> str:
    """Where the cycle's branch left the base branch: the diff the cycle owns, after any rebase."""
    out = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/develop'], capture_output=True, text=True)
    found = out.stdout.strip()
    if out.returncode != 0 or subprocess.run(['git', 'merge-base', '--is-ancestor', found, BASE]).returncode == 0:
        return BASE  # a base branch behind the GOAL's sign-off (a stale ref) never widens the diff
    return found


def added_lines(name: str) -> list[tuple[int, str]]:
    diff = subprocess.run(['git', 'diff', '-U0', '--cached', merge_base(), '--', name], check=True,
                          capture_output=True, text=True).stdout
    out, line_no = [], 0
    for line in diff.splitlines():
        hunk = re.match(r'@@ -\S+ \+(\d+)', line)
        if hunk:
            line_no = int(hunk.group(1))
        elif line.startswith('+') and not line.startswith('+++'):
            out.append((line_no, line[1:]))
            line_no += 1
    return out


def values(rows: list[int]) -> list[str]:
    problems = []
    tree = staged()
    texts = {name: committed(tree, name) for name in (SSH, PROBES, STARTUP)}
    trees = {name: ast.parse(text) for name, text in texts.items()}
    for name, wanted in CONSTANTS.items():
        bound = {t.id: ast.unparse(node.value) for node in trees[name].body if isinstance(node, ast.Assign)
                 for t in node.targets if isinstance(t, ast.Name)}
        for const, text in wanted.items():
            if bound.get(const) != text:
                problems.append(f'{name}: {const} = {bound.get(const)!r}, not {text!r} (R9)')
    for row, (name, test) in ROW_TESTS.items():
        try:
            func = _function(trees[name], test)
        except LookupError:
            problems.append(f'{name}: {test} is gone')
            continue
        source = ast.get_source_segment(texts[name], func) or ''
        code = _code(func)
        for deco in func.decorator_list:
            words = set(re.findall(r'\w+', ast.unparse(deco)))
            if words & set(FORBIDDEN_MARKS) or not words & {'parametrize', 'unit', 'integration', 'mark', 'pytest'}:
                problems.append(f'row {row}: carries {ast.unparse(deco)} (Non-goals)')
        for node in _own_nodes(func):
            if isinstance(node, ast.Return):
                problems.append(f'row {row}: returns early at line {node.lineno} (Non-goals)')
        for node in ast.walk(func):
            if isinstance(node, (ast.Call, ast.Raise)):
                called = ast.unparse(node.func if isinstance(node, ast.Call) else (node.exc or node))
                if set(re.findall(r'\w+', called)) & set(FORBIDDEN_CALLS) - {'Exception'} or 'skip.Exception' in called:
                    problems.append(f'row {row}: {called} at line {node.lineno} (Non-goals)')
        for text in KEPT[row]:
            if text not in code:
                problems.append(f'row {row}: no longer holds the code {text!r} (R9)')
        if row in rows:
            for text in BUILT[row]:
                if not any(text in c for c in code):
                    problems.append(f'row {row}: does not hold the code {text!r} (PLAN § 2)')
            for text in MESSAGES[row]:
                if text not in source:
                    problems.append(f'row {row}: no message carries {text!r} (R7)')
    for name in (SSH, PROBES, STARTUP):
        for line_no, line in added_lines(name):
            if FORBIDDEN_ADDED.search(line.split('#')[0]):
                problems.append(f'{name}:{line_no}: an added line carries {FORBIDDEN_ADDED.search(line).group(0)!r} '
                                f'(Non-goals: no skip, retry or load condition): {line.strip()[:100]}')
    return problems


# --- scope --------------------------------------------------------------------------------------

ALLOWED = (re.compile(r'tests/(test_ssh_exec|test_probes|test_probe_startup|mutants)\.py'),
           re.compile(rf'spec/{SLUG}/.+'), re.compile(r'issues/[a-z0-9-]+\.md'), re.compile(r'ROADMAP\.md'))


def collected(root: Path, env: dict[str, str]) -> list[str]:
    ids = [f'{ROW_TESTS[r][0]}::{ROW_TESTS[r][1]}' for r in ROW_TESTS]
    out = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider', *ids],
                         cwd=root, env={**os.environ, **env}, capture_output=True, text=True)
    return sorted(line for line in out.stdout.splitlines() if '::' in line)


def scope(base_tree: Path) -> list[str]:
    problems = []
    changed = subprocess.run(['git', 'diff', '--name-only', '--cached', merge_base()], check=True,
                             capture_output=True, text=True).stdout.split()
    for name in changed:
        if not any(p.fullmatch(name) for p in ALLOWED):
            problems.append(f'{name}: the cycle may not change it (PLAN § 2, Non-goals)')
    if 'tests/mutants.py' in changed:
        diff = subprocess.run(['git', 'diff', '-U0', '--cached', merge_base(), '--', 'tests/mutants.py'], check=True,
                              capture_output=True, text=True).stdout
        for line in diff.splitlines():
            if line[:1] in '+-' and not line.startswith(('+++', '---')) and 'test_' not in line and line[1:].strip():
                problems.append(f'tests/mutants.py: a change beyond a Case target: {line[:120]!r}')
    problems += amended()
    for env in ERAS:
        era = env.get('CLUSTER_MCP_TEST_ERA', 'handshake')
        here, there = collected(Path.cwd(), env), collected(base_tree, env)
        if here != there or not here:
            problems.append(f'{era}: the four rows collect {len(here)} ids, the base {len(there)} (R8)')
    return problems


PLAN_SUBJECT = f'[test] Plan {SLUG}: design + phased roadmap'
AMENDMENTS = SPEC / 'verify' / 'amendments.txt'


def amended() -> list[str]:
    """Each gate script changed since the plan commit is named, with a reason, in `verify/amendments.txt`."""
    plan = subprocess.run(['git', 'log', '-1', '--format=%H', '--fixed-strings', f'--grep={PLAN_SUBJECT}'],
                          capture_output=True, text=True).stdout.strip()
    if not plan:
        return []
    changed = subprocess.run(['git', 'diff', '--name-only', '--cached', plan, '--', f'{SPEC}/verify/'], check=True,
                             capture_output=True, text=True).stdout.split()
    named = AMENDMENTS.read_text(encoding='utf-8') if AMENDMENTS.exists() else ''
    return [f'{name}: changed since the plan commit and not named in {AMENDMENTS} (the gate is pinned at sign-off)'
            for name in changed if name.endswith('.py') and Path(name).name not in named]


# --- running rows -------------------------------------------------------------------------------

def junit_outcomes(path: Path) -> dict[str, tuple[str, str]]:
    """Each test's outcome in a JUnit report: ('passed' | 'failed' | 'error' | 'skipped', its message)."""
    out = {}
    for case in ET.parse(path).getroot().iter('testcase'):
        module = case.get('classname', '').split('.')
        node = '/'.join(module[:-1] + [module[-1] + '.py']) + '::' + case.get('name', '')
        kind, message = 'passed', ''
        for child in case:
            if child.tag in ('failure', 'error', 'skipped'):
                kind, message = child.tag.replace('failure', 'failed'), (child.get('message', '') + (child.text or ''))
        out[node] = (kind, message)
    return out


def run_rows(root: Path, ids: list[str], env: dict[str, str], extra: list[str] = ()) -> dict[str, tuple[str, str]]:
    with tempfile.TemporaryDirectory(prefix='srtt-junit-') as scratch:
        junit = Path(scratch) / 'junit.xml'
        subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *extra,
                        f'--junitxml={junit}', *ids], cwd=root, env={**os.environ, **env}, capture_output=True,
                       text=True, timeout=540)
        return junit_outcomes(junit) if junit.exists() else {}


def rows(row: int) -> list[str]:
    problems = []
    ids = row_ids(row)
    for env in ERAS:
        era = env.get('CLUSTER_MCP_TEST_ERA', 'handshake')
        got = run_rows(Path.cwd(), ids, env)
        bad = {k: v for k, v in got.items() if v[0] != 'passed'}
        if len(got) != COUNTS[row] or bad:
            problems.append(f'row {row}, {era}: {len(got)} of {COUNTS[row]} ran, {len(bad)} not passed: '
                            + '; '.join(f'{k.split("::")[1]} {v[0]}: {v[1][:200]}' for k, v in list(bad.items())[:3]))
        else:
            print(f'row {row}, {era}: {len(got)} passed')
    return problems


# --- faults -------------------------------------------------------------------------------------

SSH_FILE = 'core/executor/ssh.py'
PROBES_FILE = 'core/probes.py'
INIT_FILE = 'core/__init__.py'
START = ("                        threading.Thread(target=self._settle, args=(pending,), name='cluster-mcp-reconnect',\n"
         "                                         daemon=True).start()\n")
UNSTARTED = ('                        pending.done.set()\n'
             '                        if not isinstance(exc, Exception):\n'
             '                            raise\n'
             '                        return connect_failure_message(self._host, exc)\n')
GIVE_UP = '                        return connect_failure_message(self._host, exc)\n'
WAIT = '            answer = (self._answer if self._answered.wait(self._deadline - time.monotonic())\n'
POST = '        pending._post(answer)\n'
START_POST = '        pending._post(_why(exc))\n'
R3 = [f'test_probes.py::{ROW_TESTS[3][1]}[{p}]' for p in ('exception-core-only', 'interrupt-both', 'interrupt-rcac',
                                                           'exit-0-slurm', 'none-both', 'thread-cannot-start-rcac')]
R4_HANG = [f'test_probe_startup.py::{ROW_TESTS[4][1]}[{p}]' for p in ('hang-ssh-sse-core-only', 'hang-local-stdio-both')]
R4_ANY = [f'test_probe_startup.py::{ROW_TESTS[4][1]}[{p}]' for p in ('exit-1-local-stdio-core-only', 'raises-ssh-sse-both')]
R1 = [f'test_ssh_exec.py::{ROW_TESTS[1][1]}']
R2 = [f'test_ssh_exec.py::{ROW_TESTS[2][1]}']

# (id, member file, edits, targets, the fragment each target's failure carries): PLAN § 6's decision list.
FAULTS = {
    1: [
        ('gives-up-late', SSH_FILE, (('                if time.monotonic() >= deadline and self._leave(pending):\n',
                                      '                if time.monotonic() >= deadline + 0.7 and self._leave(pending):\n'),),
         R1, 'past its 3 s bound and 0.5 s of slack'),
        ('starts-no-attempt', SSH_FILE, (('                if not scheduled and time.monotonic() >= deadline - FINAL_ATTEMPT_LEAD:\n',
                                          '                if not scheduled:\n'),),
         R1, 'no attempt reached the silent host'),
        ('two-workers', SSH_FILE, ((START, START + START),), R1, '2 reconnect workers started during the call, not one'),
        ('abort-closes-nothing', SSH_FILE, (('        for transport in transports:\n', '        for transport in ():\n'),),
         R1, 'still running 1.0 s after the call gave up'),
        ('window-one-factor-more', SSH_FILE, (('        self._window = RECONNECT_FACTOR * _bound(conn)\n',
                                               '        self._window = (RECONNECT_FACTOR + 1) * _bound(conn)\n'),),
         R1, 'window, not 3 s'),
    ],
    2: [
        ('waits-out-the-deadline', SSH_FILE, ((UNSTARTED, '                        cause = exc\n'),),
         R2, "on the row's clock"),
        ('waits-one-poll', SSH_FILE, ((GIVE_UP, '                        _await(threading.Event(), ATTEMPT_POLL)\n' + GIVE_UP),),
         R2, "on the row's clock"),
        ('waits-half-a-poll', SSH_FILE, ((GIVE_UP, '                        _await(threading.Event(), ATTEMPT_POLL / 2)\n' + GIVE_UP),),
         R2, 'waited on an attempt'),
        ('retries-after-backoff', SSH_FILE, ((GIVE_UP, '                        pass\n'),), R2, "on the row's clock"),
        ('waits-off-the-clock', SSH_FILE, ((GIVE_UP, '                        threading.Event().wait(ATTEMPT_POLL)\n'
                                                     + GIVE_UP),),
         R2, 'from entering its reconnect to giving up'),
    ],
    3: [
        ('decides-at-the-deadline', PROBES_FILE,
         ((WAIT, WAIT.replace('(self._answer if self._answered.wait(',
                              '(self._answer if (time.sleep(max(0.0, self._deadline - time.monotonic())) or '
                              'self._answered.wait(').replace('time.monotonic())\n', 'time.monotonic()))\n', 1)),),
         R3, 'decided only at the deadline'),
        ('posts-at-the-deadline', PROBES_FILE,
         ((POST, '        time.sleep(max(0.0, pending._deadline - time.monotonic()))\n' + POST),
          (START_POST, '        time.sleep(max(0.0, pending._deadline - time.monotonic()))\n' + START_POST)),
         R3, 'decided only at the deadline'),
        ('reads-the-answer-when-the-wait-runs-out', PROBES_FILE,
         (('        self._answered.set()\n', '        pass\n'),
          (WAIT, WAIT.replace('self._answered.wait(self._deadline - time.monotonic())',
                              '(self._answered.wait(self._deadline - time.monotonic()) or self._answer)'))),
         R3, 'decided only at the deadline'),
        ('worker-sleeps-off-the-clock', PROBES_FILE,
         ((POST, "        __import__('time').sleep(0.25)\n" + POST),),
         R3[:5], 'decided only at the deadline'),
        ('deadline-off-the-rows-clock', PROBES_FILE,
         (('        self._deadline = time.monotonic() + bound\n',
           "        self._deadline = __import__('time').monotonic() + bound\n"),),
         R3, "did not take its deadline and its wait on the row's clock"),
        ('wait-off-the-rows-clock', PROBES_FILE,
         (('        self._answered = threading.Event()\n', "        self._answered = __import__('threading').Event()\n"),),
         R3, "did not take its deadline and its wait on the row's clock"),
    ],
    4: [
        ('waits-past-the-bound', PROBES_FILE,
         ((WAIT, WAIT.replace('self._deadline - time.monotonic()', 'self._deadline - time.monotonic() + 2 * self._bound')),),
         R4_HANG, 'the start took'),
        ('joins-the-hung-worker', INIT_FILE,
         (('        for verdict in pending.verdicts():\n',
           "        [t.join(1.0) for t in __import__('threading').enumerate() if t.name == 'cluster-mcp-probe']\n"
           '        for verdict in pending.verdicts():\n'),),
         R4_HANG, 'the start took'),
        ('waits-after-the-answer', INIT_FILE,
         (('        for verdict in pending.verdicts():\n',
           "        __import__('time').sleep(0.6)\n        for verdict in pending.verdicts():\n"),),
         R4_ANY, 'the start took'),
        # A collection inside the start that takes 0.6 s: the row still fails, and says the collector took it.
        ('collects-slowly-in-the-start', INIT_FILE,
         (('        for verdict in pending.verdicts():\n',
           '        def _slow(phase, info):\n'
           "            if phase == 'start':\n"
           "                __import__('time').sleep(0.6)\n"
           "        __import__('gc').callbacks.append(_slow)\n"
           "        __import__('gc').collect()\n"
           "        __import__('gc').callbacks.remove(_slow)\n"
           '        for verdict in pending.verdicts():\n'),),
         R4_ANY, 'the collector pausing it 0.6'),
    ],
}


def mutants_module():
    sys.path.insert(0, str(Path.cwd() / 'tests'))
    import mutants  # noqa: E402  (the tree's own runner, unchanged)
    return mutants


def faults(row: int) -> list[str]:
    mutants = mutants_module()
    problems = []
    for case_id, file, edits, targets, why in FAULTS[row]:
        began = time.monotonic()
        case = mutants.Case(f'srtt-{row}-{case_id}', file, edits, tuple(targets), why)
        violations = mutants.run_case(case)
        took = time.monotonic() - began
        if violations:
            problems += [f'fault {row}/{case_id}: {v}' for v in violations]
            print(f'fault {row}/{case_id}: SURVIVED or wrong reason ({took:.0f} s)')
        else:
            print(f'fault {row}/{case_id}: killed, {len(targets)} targets with {why!r} ({took:.0f} s)')
    return problems


# --- controls -----------------------------------------------------------------------------------

# Under its stall, what the base's row fails with: the sighting's own words.
SIGHTING = {1: 'reconnect workers ran, not one', 2: 'not giving up at once', 3: 'decided only at the deadline',
            4: 'the start took'}


def tree_of(rev: str, into: Path) -> Path:
    """The committed tree of `rev`, unpacked under `into` (read from the commit, never the working copy)."""
    root = into / rev
    root.mkdir(parents=True)
    archive = into / f'{rev}.tar'
    subprocess.run(['git', 'archive', '-o', str(archive), staged() if rev == 'HEAD' else rev], check=True)
    with tarfile.open(archive) as tar:
        tar.extractall(root, filter='data')
    return root


def controls(row: int, scratch: Path) -> list[str]:
    problems = []
    env = {'SRTT_STALL': str(row), 'PYTHONPATH': str(HERE)}
    ids = row_ids(row)
    for (rev, want), era in ((pair, era) for pair in (('HEAD', 'passed'), (BASE, 'failed')) for era in ERAS):
        root = scratch / rev if (scratch / rev).exists() else tree_of(rev, scratch)
        got = run_rows(root, ids, {**env, **era}, ['-p', 'srtt_stall'])
        rev_era = f'{rev}, {era.get("CLUSTER_MCP_TEST_ERA", "handshake")}'
        kinds = [v[0] for v in got.values()]
        if want == 'passed':
            ok = len(got) == COUNTS[row] and all(k == 'passed' for k in kinds)
            detail = '; '.join(f'{k.split("::")[1]} {v[0]}: {v[1][:160]}' for k, v in got.items() if v[0] != 'passed')
        else:
            hit = [k for k, v in got.items() if v[0] == 'failed' and SIGHTING[row] in v[1]]
            ok = bool(hit)
            detail = f'{len(hit)} of {COUNTS[row]} failed with {SIGHTING[row]!r}'
        print(f'control {row} on {rev_era}: {kinds.count("passed")} passed, {kinds.count("failed")} failed of {len(got)}'
              + (f' ({detail})' if want == 'failed' else ''))
        if not ok:
            problems.append(f'control {row} on {rev_era}: expected {want}: {detail or kinds}')
    return problems


# --- existing cases -----------------------------------------------------------------------------

# Every `mutants.CASES` entry whose targets name one of the four rows, at BASE (R6).
NAMED_CASES = (
    'ssh-reconnect-unstarted-worker-holds-slot', 'probe-parse-newline-never', 'probe-parse-shape-never',
    'probe-parse-shape-without-count', 'probe-parse-shape-without-end', 'probe-parse-shape-and',
    'probe-parse-lines-never', 'probe-ask-timeout-never', 'probe-ask-lost-never', 'probe-ask-not-started-never',
    'probe-ask-exit-never', 'probe-ask-unparsed-never', 'probe-verdict-no-answer-never',
    'probe-verdict-reason-always', 'probe-verdict-reason-never', 'probe-verdict-reason-negated',
    'probe-start-bound-always', 'probe-start-bound-negated', 'probe-worker-catches-exception',
    'probe-worker-re-raises', 'probe-thread-start-re-raises', 'probe-timing-ask-reason-names-the-module-bound',
    'probe-served-reason-never', 'probe-level-unanswered-devel', 'probe-level-unanswered-trace',
    'probe-level-unanswered-debug', 'probe-level-unanswered-info', 'probe-level-unanswered-notice',
    'probe-level-unanswered-error', 'probe-level-unanswered-exception', 'probe-level-unanswered-critical',
    'probe-level-unanswered-fatal',
)


def cases() -> list[str]:
    mutants = mutants_module()
    names = {f'{ROW_TESTS[r][0].removeprefix("tests/")}::{ROW_TESTS[r][1]}' for r in ROW_TESTS}
    now = {c.id for c in mutants.CASES if any(t.split('[')[0] in names for t in c.targets)}
    # The cases whose fragment quotes `not_run_violations`' message, which D4 rewords.
    now |= {c.id for c in mutants.CASES if c.why.startswith('past its') and c.file == SSH_FILE}
    ids = sorted(set(NAMED_CASES) | now)
    missing = sorted(set(NAMED_CASES) - {c.id for c in mutants.CASES})
    out = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids], capture_output=True, text=True,
                         timeout=580)
    print(out.stdout.strip().splitlines()[-1] if out.stdout.strip() else '(no output)')
    problems = [f'case {c} is gone from mutants.CASES' for c in missing]
    if out.returncode != 0:
        problems.append(f'mutants.py --self-check exited {out.returncode}: '
                        + ' | '.join(l for l in out.stdout.splitlines() if 'FAILED' in l)[:1200])
    else:
        print(f'cases: {len(ids)} named cases killed, controls held')
    return problems


# --- sweep record -------------------------------------------------------------------------------

RECORD = SPEC / 'verify' / 'sweep.txt'
PARTS = ('1', '2', '3', '4', 'cases', 'times')
TIMED = (SSH + '::' + ROW_TESTS[1][1], SSH + '::' + ROW_TESTS[2][1], PROBES, STARTUP)


def times(scratch: Path) -> list[str]:
    """R8's local evidence: each touched row's module (rows 1-2 by id) timed three times on BASE and on HEAD, handshake era."""
    lines = []
    for rev in (BASE, 'HEAD'):
        root = scratch / rev if (scratch / rev).exists() else tree_of(rev, scratch)
        for target in TIMED:
            # Three runs each, the least and the most: one run on a shared host is mostly its load.
            took, bad = [], 0
            for _ in range(3):
                began = time.monotonic()
                got = run_rows(root, [target], {})
                took.append(time.monotonic() - began)
                bad += sum(1 for v in got.values() if v[0] != 'passed')
            lines.append(f'times · {rev} · {target} · {len(got)} tests · {bad} not passed · '
                         f'{min(took):.1f}-{max(took):.1f} s · load {os.getloadavg()[0]:.1f}')
    print('\n'.join(lines))
    with RECORD.open('a', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    return [l for l in lines if ' 0 not passed ' not in l and 'HEAD' in l]


def gate_hash() -> str:
    """The staged blobs of the gate's own scripts, so a record names the gate that graded it."""
    tree = staged()
    blobs = [subprocess.run(['git', 'rev-parse', f'{tree}:{SPEC}/verify/{n}'], capture_output=True,
                            text=True).stdout.strip()[:10] for n in ('timing-gate.py', 'srtt_stall.py')]
    return '+'.join(blobs)


def tests_tree() -> str:
    return subprocess.run(['git', 'rev-parse', f'{staged()}:tests'], check=True, capture_output=True,
                          text=True).stdout.strip()


def sweep(part: str, scratch: Path) -> list[str]:
    began = time.monotonic()
    if part == 'cases':
        problems = cases()
    elif part == 'times':
        problems = times(scratch)
    else:
        row = int(part)
        problems = values([row]) + faults(row) + controls(row, scratch)
    took = time.monotonic() - began
    verdict = 'red' if problems else 'green'
    with RECORD.open('a', encoding='utf-8') as handle:
        handle.write(f'{time.strftime("%Y-%m-%d %H:%M")} · part {part} · tests tree {tests_tree()} · '
                     f'gate {gate_hash()} · {verdict} · {took:.0f} s\n')
    return problems


def sweep_check() -> list[str]:
    tree = tests_tree()
    lines = RECORD.read_text(encoding='utf-8').splitlines() if RECORD.exists() else []
    problems = []
    key = f'· tests tree {tree} · gate {gate_hash()} ·'
    for part in PARTS:
        if not any(f'· part {part} {key} green' in line for line in lines):
            problems.append(f'sweep.txt: no green part {part} on the tests tree {tree} with this gate')
    # A red on the same tree and gate is not washed out by a later green: it goes to the foreman.
    problems += [f'sweep.txt: a red part on this tree and gate: {line}' for line in lines if key in line and
                 line.split(' · ')[-2] == 'red']
    return problems


# --- the profile's verify, once, on the final tree ---------------------------------------------

PROFILE_RECORD = SPEC / 'verify' / 'profile-verify.txt'


def trees() -> str:
    tree = staged()
    return ' · '.join(f'{d} tree ' + subprocess.run(['git', 'rev-parse', f'{tree}:{d}'], check=True, capture_output=True,
                                                     text=True).stdout.strip() for d in ('tests', 'packages'))


def profile(action: str) -> list[str]:
    """`run`: the profile's `verify`, read from AGENTS.md's profile row, recorded (about 25 min: background it).
    `check`: the record says it exited 0 on HEAD's `tests/` and `packages/` trees."""
    if action == 'check':
        text = PROFILE_RECORD.read_text(encoding='utf-8') if PROFILE_RECORD.exists() else ''
        problems = [] if f'{trees()} · exit 0' in text else [f'{PROFILE_RECORD}: no exit 0 on {trees()}']
        problems += [f'{PROFILE_RECORD}: row {r} did not pass {2 * COUNTS[r]} times (once per era)' for r in ROW_TESTS
                     if f'row {r} · passed {2 * COUNTS[r]} of {2 * COUNTS[r]}' not in text]
        return problems
    row = next(l for l in Path('AGENTS.md').read_text(encoding='utf-8').splitlines() if l.startswith('| verify |'))
    command = row.split('`')[1]
    began = time.monotonic()
    out = subprocess.run(['sh', '-c', command], env={**os.environ, 'UV_PYTHON': '3.14', 'PYTEST_ADDOPTS': '-rA'},
                         capture_output=True, text=True)
    summaries = [l for l in out.stdout.splitlines() if re.search(r'^=+ .*\d+ (passed|failed)', l)]
    # R8: each row's tests passed once in each era (twice in all), never skipped or re-run.
    counts = []
    for row, (name, test) in ROW_TESTS.items():
        passed = sum(1 for l in out.stdout.splitlines() if l.startswith(f'PASSED {name}::{test}')
                     and (row != 3 or any(f'[{e}-' in l for e in RAISED)))
        counts.append(f'row {row} · passed {passed} of {2 * COUNTS[row]}')
    PROFILE_RECORD.write_text(f'{time.strftime("%Y-%m-%d %H:%M")} · {trees()} · exit {out.returncode} · '
                              f'{time.monotonic() - began:.0f} s\n' + '\n'.join(counts + summaries) + '\n',
                              encoding='utf-8')
    print(PROFILE_RECORD.read_text(encoding='utf-8'))
    return [] if out.returncode == 0 else [f'the profile verify exited {out.returncode}']


# --- ledger -------------------------------------------------------------------------------------

PHRASES = ('do not fix here', 'known limitation', 'left as a follow-up', 'follow-up', 'deferred',
           'not fixed')
SEED = re.compile(r'issues/([a-z0-9-]+)\.md')


def _blocks(text: str) -> list[str]:
    """Paragraphs and list items, joined across their wrapped lines; headings and rules dropped."""
    blocks, current = [], []
    for line in text.splitlines():
        stripped = line.strip()
        starts_item = bool(re.match(r'([-*]|\d+\.)\s', stripped))
        if not stripped or stripped.startswith('#') or stripped == '---' or starts_item:
            if current:
                blocks.append(' '.join(current))
            current = [] if not starts_item else [stripped]
            continue
        current.append(stripped)
    if current:
        blocks.append(' '.join(current))
    return blocks


def ledger() -> list[str]:
    tech = (SPEC / 'TECH.md').read_text(encoding='utf-8')
    phases = tech[tech.index('## Phase P1'):tech.index('## How `code-build` drives this')]
    bodies = subprocess.run(['git', 'log', f'{BASE}..HEAD', '--format=%B'], check=True, capture_output=True,
                            text=True).stdout
    roadmap = Path('ROADMAP.md').read_text(encoding='utf-8')
    problems = []
    for source, text in (('TECH.md', phases), ('commit bodies', bodies)):
        for block in _blocks(text):
            lowered = re.sub(r'"[^"]*"', '', block).lower()
            if not any(phrase in lowered for phrase in PHRASES):
                continue
            seeds = SEED.findall(block)
            if not seeds:
                problems.append(f'{source}: a deferral names no issues/ seed: {block[:160]}')
            for seed in seeds:
                if not Path(f'issues/{seed}.md').exists():
                    problems.append(f'{source}: issues/{seed}.md does not exist ({block[:100]})')
                elif f'issues/{seed}.md' not in roadmap:
                    problems.append(f'{source}: issues/{seed}.md has no ROADMAP.md entry')
    return problems


# --- main ---------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    if not argv:
        print(__doc__)
        return 2
    mode, rest = argv[0], argv[1:]
    # The modes that run tests run the working copy: it must be what is staged (M1).
    dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=all', '--', 'tests', 'packages',
                            f'{SPEC}/verify/timing-gate.py', f'{SPEC}/verify/srtt_stall.py'],
                           check=True, capture_output=True, text=True).stdout.splitlines()
    unstaged = [l for l in dirty if l[1:2] != ' ']
    if unstaged and mode not in ('values', 'ledger', 'sweep-check'):
        print('the working copy differs from what is staged; stage it first:\n' + '\n'.join(unstaged))
        return 1
    with tempfile.TemporaryDirectory(prefix='srtt-gate-') as scratch_dir:
        scratch = Path(scratch_dir)
        if mode == 'values':
            problems = values([int(r) for r in rest])
        elif mode == 'scope':
            problems = scope(tree_of(BASE, scratch))
        elif mode == 'rows':
            problems = rows(int(rest[0]))
        elif mode == 'faults':
            problems = faults(int(rest[0]))
        elif mode == 'controls':
            problems = controls(int(rest[0]), scratch)
        elif mode == 'cases':
            problems = cases()
        elif mode == 'row':
            row = int(rest[0])
            problems = values([row])
            for step in (lambda: scope(tree_of(BASE, scratch)), lambda: rows(row), lambda: faults(row),
                         lambda: controls(row, scratch)):
                if problems:
                    break
                problems = step()
        elif mode == 'sweep':
            problems = sweep(rest[0], scratch)
        elif mode == 'sweep-check':
            problems = sweep_check()
        elif mode == 'ledger':
            problems = ledger()
        elif mode == 'profile':
            problems = profile(rest[0])
        else:
            print(f'unknown mode {mode!r}')
            return 2
    print('\n'.join(problems) if problems else f'{mode} {" ".join(rest)}: ok')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
