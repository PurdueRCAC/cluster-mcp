# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 1, F5: every timing decision of `core/probes.py` is mutated to every alternative it could
take, and each mutant is caught beside every member set, in both protocol eras.

    uv run python -I spec/capability-probe/remediation/F5-probe-timing.py [coverage|cases|equivalents|all]
                                                                       from the worktree root

The frozen `alternatives.py` sweeps the probe's conditions, operators, comparisons and `except`
clauses, and a few named figures; it never reaches a value a call is given, so `wait(self._bound)` in
place of `wait(self._deadline - time.monotonic())` survived (the review's F5). The decisions it misses
are the probe's timing:

- where the deadline is taken: when the probe starts (`Pending.__init__`, from `start()`), at the wait,
  or just after the worker starts (an equivalent);
- what the deadline is: the clock plus the bound, the bound alone, the clock alone, the clock less the
  bound, the wall clock, the module's bound in place of the one given, the operands exchanged (an
  equivalent);
- what the wait is given: the time left to the deadline, the bound, nothing (`None`, no argument),
  zero, the deadline itself, the clock, the time past the deadline, the deadline plus the clock, the
  time left on the wall clock, or the time left floored at zero (an equivalent);
- what happens past the deadline: the reason a late decision names (the bound kept, the module's), and
  the bound kept itself;
- the bound each part is handed: the `Pending` `start()` builds, the lookup `_ask` runs and the executor
  call it makes (the module's bound, the given timeout, zero), the reason a timed-out lookup names, the
  default of `start()`'s timeout, and the bound `unprobed()` holds (zero is an equivalent, `None` not).

Modes:

- `coverage` (seconds): each alternative above turned, by a case of `tests/mutants.py` or an equivalent
  recorded here, into the same syntax tree, each case targeting a row beside every member set; every
  alternative the frozen `alternatives.py` gives `core/probes.py` still has its case; and every line of
  `core/probes.py` that handles time (`time.`, a deadline, a bound, a timeout, a wait) carries an
  alternative from one list or the other, so a timing decision added later and swept by neither is a
  gap.
- `cases` (about 5 s a case an era): each case run by `tests/mutants.py --self-check`, in the handshake
  era, then in revision 2026-07-28's, each killed.
- `equivalents` (about 20 s each an era): each equivalent planted, `EQUIVALENT_TARGETS` passing in each
  era.

`all` (the default) runs the three. Footprint: one process, then one mutant child at a time under
bin/sandbox.sh, under 1 GB; no network.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import tokenize
from pathlib import Path

ROOT = Path.cwd()
VERIFY = ROOT / 'spec/capability-probe/verify'
_spec = importlib.util.spec_from_file_location('capability_probe_alternatives', VERIFY / 'alternatives.py')
alternatives = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = alternatives
_spec.loader.exec_module(alternatives)
mutants = alternatives.mutants

PROBES = 'core/probes.py'
SETS = tuple(mutants.MEMBER_SETS)

DEADLINE = '        self._deadline = time.monotonic() + bound\n'
BOUND_KEPT = '        self._bound = bound\n'
WAIT = '            answer = (self._answer if self._answered.wait(self._deadline - time.monotonic())\n'
LEFT = 'self._deadline - time.monotonic()'
LATE_REASON = "                      else f'did not answer within {self._bound:g} s')\n"
MEMO = '        if self._verdicts is None:\n'
STARTED = '    pending = Pending(tuple(capabilities), bound)\n'
WORKER = "        threading.Thread(target=work, name='cluster-mcp-probe', daemon=True).start()\n"
ASKED = '            answer = _ask(executor, names, bound)\n'
RAN = 'timeout=timeout)'
ASK_REASON = "        return f'did not answer within {timeout:g} s'\n"
SIGNATURE = 'def start(executor: Executor, capabilities: Iterable[Loaded], timeout: float | None = None) -> Pending:\n'
UNPROBED = '    pending = Pending(tuple(capabilities), PROBE_TIMEOUT)\n'


def waited(given: str) -> tuple[tuple[str, str], ...]:
    return ((WAIT, WAIT.replace(LEFT, given)),)


# Every timing alternative: (what, edits). Each must be a case's tree or an equivalent's.
TIMING: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ('the deadline is taken at the wait',
     ((DEADLINE, ''), (MEMO, MEMO + '            self._deadline = time.monotonic() + self._bound\n'))),
    ('the deadline is taken just after the worker starts',
     ((WORKER, WORKER + '        pending._deadline = time.monotonic() + bound\n'),)),
    ('the deadline is the clock less the bound', ((DEADLINE, DEADLINE.replace(' + bound', ' - bound')),)),
    ('the deadline is the bound alone', ((DEADLINE, '        self._deadline = bound\n'),)),
    ('the deadline is the clock alone', ((DEADLINE, '        self._deadline = time.monotonic()\n'),)),
    ('the deadline is on the wall clock', ((DEADLINE, DEADLINE.replace('time.monotonic()', 'time.time()')),)),
    ("the deadline is the module's bound", ((DEADLINE, DEADLINE.replace(' + bound', ' + PROBE_TIMEOUT')),)),
    ('the deadline is the bound plus the clock',
     ((DEADLINE, '        self._deadline = bound + time.monotonic()\n'),)),
    ('the wait is given the bound', waited('self._bound')),
    ('the wait is given None', waited('None')),
    ('the wait is given no timeout', ((WAIT, WAIT.replace(f'wait({LEFT})', 'wait()')),)),
    ('the wait is given zero', waited('0')),
    ('the wait is given the deadline', waited('self._deadline')),
    ('the wait is given the clock', waited('time.monotonic()')),
    ('the wait is given the time past the deadline', waited('time.monotonic() - self._deadline')),
    ('the wait is given the deadline plus the clock', waited('self._deadline + time.monotonic()')),
    ('the wait is given the time left on the wall clock', waited('self._deadline - time.time()')),
    ('the wait is given the time left, floored at zero', waited(f'max(0.0, {LEFT})')),
    ("a late decision names the module's bound",
     ((LATE_REASON, LATE_REASON.replace('{self._bound:g}', '{PROBE_TIMEOUT:g}')),)),
    ("the bound kept is the module's", ((BOUND_KEPT, '        self._bound = PROBE_TIMEOUT\n'),)),
    ("start() builds its Pending with the module's bound", ((STARTED, STARTED.replace(', bound)', ', PROBE_TIMEOUT)')),)),
    ('start() builds its Pending with the given timeout', ((STARTED, STARTED.replace(', bound)', ', timeout)')),)),
    ('start() builds its Pending with zero', ((STARTED, STARTED.replace(', bound)', ', 0)')),)),
    ("the lookup is asked with the module's bound", ((ASKED, ASKED.replace(', bound)', ', PROBE_TIMEOUT)')),)),
    ('the lookup is asked with the given timeout', ((ASKED, ASKED.replace(', bound)', ', timeout)')),)),
    ('the lookup is asked with zero', ((ASKED, ASKED.replace(', bound)', ', 0)')),)),
    ("the executor is given the module's bound", ((RAN, 'timeout=PROBE_TIMEOUT)'),)),
    ('the executor is given zero', ((RAN, 'timeout=0)'),)),
    ("a timed-out lookup names the module's bound",
     ((ASK_REASON, ASK_REASON.replace('{timeout:g}', '{PROBE_TIMEOUT:g}')),)),
    ("start()'s timeout defaults to the module's bound",
     ((SIGNATURE, SIGNATURE.replace('timeout: float | None = None', 'timeout: float | None = PROBE_TIMEOUT')),)),
    ('unprobed() holds no bound', ((UNPROBED, UNPROBED.replace('PROBE_TIMEOUT)', 'None)')),)),
    ('unprobed() holds a zero bound', ((UNPROBED, UNPROBED.replace('PROBE_TIMEOUT)', '0)')),)),
)

# The alternatives that change no behaviour: what -> why. Each is planted by `equivalents`.
EQUIVALENT = {
    'the deadline is taken just after the worker starts':
        'starting a thread takes microseconds against a bound of seconds: neither a row nor a client can tell '
        'the two deadlines apart, and both come before any wait',
    'the deadline is the bound plus the clock': 'addition of two floats commutes; the deadline is the same number',
    'the wait is given the time left, floored at zero':
        '`threading.Event.wait` gives a negative timeout the meaning of zero, so a floor at zero waits the same',
    'unprobed() holds a zero bound':
        '`unprobed()` posts its answer before returning, so `verdicts()` finds the event set and never waits, and '
        'a reason naming the bound is never formed: nothing reads the bound',
}
EQUIVALENT_TARGETS = ('test_probes.py',
                      'test_probe_startup.py::test_the_probe_follows_the_site_read_and_is_bounded',
                      'test_probe_startup.py::test_delegate_runs_no_probe_and_says_so',
                      'test_probe_startup.py::test_the_override_skips_every_probe')

# What marks a line of probes.py as handling time.
TIMING_WORDS = ('time.', '_deadline', '_bound', 'bound', 'timeout', 'PROBE_TIMEOUT', '.wait(')


def code_lines(text: str) -> dict[int, str]:
    """Each line of `text` holding code, its comments and docstrings dropped, by number."""
    module = ast.parse(text)
    docs = set()
    for node in ast.walk(module):
        body = getattr(node, 'body', None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and \
                isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
            docs.update(range(body[0].lineno, body[0].end_lineno + 1))
    lines: dict[int, list[str]] = {}
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
                        tokenize.ENDMARKER, tokenize.STRING):
            continue
        if tok.start[0] in docs:
            continue
        for line in range(tok.start[0], tok.end[0] + 1):
            lines.setdefault(line, []).append(tok.string)
    return {n: ' '.join(parts) for n, parts in lines.items()}


def timing_lines(text: str) -> dict[int, str]:
    """The code lines of `text` that handle time, but imports and signatures with no default."""
    module = ast.parse(text)
    skipped = set()
    for node in ast.walk(module):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            skipped.update(range(node.lineno, node.end_lineno + 1))
        if isinstance(node, ast.FunctionDef) and not (node.args.defaults or node.args.kw_defaults):
            skipped.add(node.lineno)
    return {n: line for n, line in code_lines(text).items()
            if n not in skipped and any(word in line.replace(' ', '') or word in line for word in TIMING_WORDS)}


def coverage() -> tuple[list[str], list[str]]:
    text = alternatives.source(PROBES)
    own = alternatives.tree(text)
    gaps: list[str] = []
    by_tree: dict[str, list[str]] = {}
    for case in mutants.CASES:
        if case.file == PROBES:
            mutated = alternatives.applied(text, case.edits)
            if mutated is not None:
                by_tree.setdefault(alternatives.tree(mutated), []).append(case.id)
    known = {case.id: case for case in mutants.CASES}
    swept: list[str] = []
    anchored: set[int] = set()

    def needs(alt_tree: str, what: str) -> None:
        names = by_tree.get(alt_tree, [])
        if not names:
            gaps.append(f'{PROBES}: {what}: no mutant')
        for name in names:
            missing = [s for s in SETS if s not in {alternatives.row_set(t) for t in known[name].targets}]
            if missing:
                gaps.append(f'{name}: no target row beside {missing}')
        swept.extend(names)

    for what, edits in TIMING:
        mutated = alternatives.applied(text, edits)
        if mutated is None:
            gaps.append(f'{PROBES}: the anchor of "{what}" is not in the file once')
            continue
        tree = alternatives.tree(mutated)
        if tree == own:
            gaps.append(f'{PROBES}: "{what}" changes nothing in the syntax tree')
            continue
        for old, _ in edits:
            start = text.index(old)
            anchored.update(range(text[:start].count('\n') + 1, text[:start + len(old)].count('\n') + 2))
        if what in EQUIVALENT:
            if by_tree.get(tree):
                gaps.append(f'{PROBES}: "{what}" is recorded as equivalent and has a case {by_tree[tree]}')
            continue
        needs(tree, what)
    frozen, frozen_gaps = alternatives.alternatives('p1')
    gaps += [g for g in frozen_gaps if g.startswith(PROBES)]
    for alt in frozen:
        if alt.file == PROBES:
            anchored.add(alt.line)
            needs(alt.tree, f'line {alt.line}: {alt.what} (the frozen sweep)')
    for line, code in sorted(timing_lines(text).items()):
        if line not in anchored:
            gaps.append(f'{PROBES}:{line}: a timing decision no alternative reaches: {code}')
    mine = sum(1 for what, _ in TIMING if what not in EQUIVALENT)
    print(f'coverage: {len(TIMING)} timing alternatives ({mine} with cases, {len(EQUIVALENT)} equivalent), '
          f'{sum(1 for a in frozen if a.file == PROBES)} frozen alternatives of {PROBES}, '
          f'{len(timing_lines(text))} timing lines', file=sys.stderr)
    timing_ids = [i for i in dict.fromkeys(swept) if i.startswith('probe-timing-')]
    return timing_ids, gaps


def cases(ids: list[str]) -> list[str]:
    bad: list[str] = []
    for label, era in alternatives.ERAS.items():
        result = subprocess.run([sys.executable, 'tests/mutants.py', '--self-check', *ids],
                                env=alternatives.era_env(era), capture_output=True, text=True)
        killed = [line for line in result.stdout.splitlines() if line.startswith('killed ')]
        print(f'cases, {label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}', file=sys.stderr)
        if result.returncode != 0 or len(killed) != len(ids):
            bad.append(f'{label} era: {len(killed)} of {len(ids)} killed, exit {result.returncode}: '
                       f'{(result.stdout + result.stderr)[-800:]}')
    return bad


def equivalents() -> list[str]:
    bad: list[str] = []
    edits = dict(TIMING)
    for what in EQUIVALENT:
        case = mutants.Case('equivalent', PROBES, edits[what], EQUIVALENT_TARGETS, '')
        for label, era in alternatives.ERAS.items():
            with tempfile.TemporaryDirectory(prefix='f5-equivalent-') as scratch:
                src_root = mutants.apply(case, Path(scratch))
                # The era's environment is taken before the process's is cleared: `era_env` reads it.
                saved, wanted = os.environ.copy(), alternatives.era_env(era)
                os.environ.clear()
                os.environ.update(wanted)
                try:
                    child = mutants.run_child(src_root, EQUIVALENT_TARGETS, Path(scratch) / 'junit.xml')
                finally:
                    os.environ.clear()
                    os.environ.update(saved)
            summary = (child.stdout.strip().splitlines() or [''])[-1]
            print(f'equivalent, {label} era: {what}: exit {child.returncode}, {summary}', file=sys.stderr)
            if child.returncode != 0:
                bad.append(f'{what}, {label} era: recorded as equivalent, but its targets fail: '
                           f'{(child.stdout + child.stderr)[-600:]}')
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('coverage', 'cases', 'equivalents', 'all'):
        raise SystemExit('usage: F5-probe-timing.py [coverage|cases|equivalents|all]')
    ids, bad = coverage()
    if mode in ('cases', 'all'):
        bad += cases(ids) if ids else ['no case to run']
    if mode in ('equivalents', 'all'):
        bad += equivalents()
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F5-probe-timing: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
