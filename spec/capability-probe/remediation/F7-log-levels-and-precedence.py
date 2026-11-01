# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Review cycle 2, F4: the probe step's documented log levels and the override's precedence hold under
every alternative of the decisions that make them, beside every member set, in both protocol eras.

    uv run python -I spec/capability-probe/remediation/F7-log-levels-and-precedence.py [coverage|docs|cases|equivalents|all]
                                                                                      from the worktree root

The frozen `alternatives.py` sweeps the conditions of `_resolve_skip_probes`, `_probe` and `_served`,
the skip branches' order and what they serve; it never reaches the level a line is logged at, or the
order in which the resolver reads the flag and the variable, so `log.info` and `log.warning` exchanged
in `_served` and the variable read before the flag both survived (the review's F4). The decisions it
misses:

- the level of each line `_served` and `_probe` log: every other method of the core's logger that logs
  a record (`LOG_METHODS`, which must name a method for every level `cmdkit` defines), found from the
  source, so a line added later is swept too; and `_served`'s two levels exchanged;
- the precedence of the override: the variable read before the flag, the flag's line naming the
  variable, the variable's line naming the flag;
- the test that the variable is set: stripped, compared with `''`, compared with None (an equivalent);
- `_probe`'s skip test compared with None (an equivalent), and the delegate branch after the override's
  (the frozen sweep's case, swept here again).

Modes:

- `coverage` (seconds): each alternative above, and every alternative the frozen sweep gives these
  three methods, turned by a case of `tests/mutants.py` or an equivalent recorded here into the same
  syntax tree; each case targeting a row beside every member set; every log call of the three methods
  reached.
- `docs` (instant): AGENTS § Invariants §4 quotes each line those log calls format, each after the
  level its call logs at ("one INFO line, `…`"), and says the flag wins when both are set.
- `cases` (about 5 s a case an era): each case of this sweep run by `tests/mutants.py --self-check`, in
  the handshake era, then in revision 2026-07-28's, each killed.
- `equivalents` (about 25 s each an era): each equivalent planted, `EQUIVALENT_TARGETS` passing in each
  era.

`all` (the default) runs the four. Footprint: one process, then one mutant child at a time under
bin/sandbox.sh, under 1 GB; no network.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
VERIFY = ROOT / 'spec/capability-probe/verify'
_spec = importlib.util.spec_from_file_location('capability_probe_alternatives', VERIFY / 'alternatives.py')
alternatives = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = alternatives
_spec.loader.exec_module(alternatives)
mutants = alternatives.mutants

CLI = 'core/__init__.py'
SETS = tuple(mutants.MEMBER_SETS)
METHODS = ('_resolve_skip_probes', '_probe', '_served')

# Every method of the core's logger that logs a record. `warn` is `warning`'s deprecated alias, `fatal`
# `critical`'s, and `exception` logs at ERROR with the exception being handled.
LOG_METHODS = ('devel', 'trace', 'debug', 'info', 'notice', 'warning', 'warn', 'error', 'exception', 'critical',
               'fatal')
LEVEL_OF = {'warn': 'WARNING', 'fatal': 'CRITICAL', 'exception': 'ERROR'}

SKIP_FLAG = "        if self.skip_probes:\n            return '--skip-probes'\n"
VARIABLE = "        value, variable = env_setting('CLUSTER_MCP_SKIP_PROBES')\n"
SKIP_VALUE = '        return variable if value else None\n'
SKIPPED = '        if skipped:\n'
DELEGATE_BRANCH = ("        if exec_mode == 'delegate':\n"
                   "            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
                   "            return probes.unprobed(loaded)\n")
OVERRIDE_BRANCH = ("        if skipped:\n"
                   "            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')\n"
                   "            return probes.unprobed(loaded)\n")

# The decisions the level sweep cannot derive from a single call: (what, edits).
FIXED: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ('the variable is read before the flag',
     ((SKIP_FLAG + VARIABLE + SKIP_VALUE,
       VARIABLE + "        if value:\n            return variable\n" + SKIP_FLAG + '        return None\n'),)),
    ("the flag's line names the variable",
     (("            return '--skip-probes'\n", "            return 'CLUSTER_MCP_SKIP_PROBES'\n"),)),
    ("the variable's line names the flag", ((SKIP_VALUE, "        return '--skip-probes' if value else None\n"),)),
    ('the variable is set when it is not blank', ((SKIP_VALUE, "        return variable if (value or '').strip() else None\n"),)),
    ("the variable is set when it is not ''", ((SKIP_VALUE, "        return variable if value != '' else None\n"),)),
    ('the variable is set when it is not None', ((SKIP_VALUE, '        return variable if value is not None else None\n'),)),
    ('a skip is any name that is not None', ((SKIPPED, '        if skipped is not None:\n'),)),
    ("the delegate branch comes after the override's", ((DELEGATE_BRANCH + OVERRIDE_BRANCH, OVERRIDE_BRANCH + DELEGATE_BRANCH),)),
)

# The alternatives that change no behaviour: what -> why. Each is planted by `equivalents`.
EQUIVALENT = {
    'the unanswered line is logged by warn':
        "`Logger.warn` is `warning`'s deprecated alias: the record, its level and its caller are the same; the "
        'only difference, a DeprecationWarning, is ignored by default outside `__main__` and reaches no client '
        '(a server run under `-W error` would see it; nothing here does)',
    'the variable is set when it is not None':
        '`env_setting` hands back `value or None` for a variable with no legacy name, so the resolver sees a '
        'non-empty string or None, never an empty one: `is not None` and truthiness agree on every value it can '
        'get',
    'a skip is any name that is not None':
        "`_resolve_skip_probes` returns '--skip-probes', the variable's name or None, never an empty string, so "
        '`is not None` and truthiness agree on every value `_probe` is given',
}
EQUIVALENT_TARGETS = ('test_probe_startup.py', 'test_env.py::test_a_variable_without_a_legacy_name')


def log_calls(text: str) -> list[tuple[str, str, str, int]]:
    """Each `log.<method>(…)` call in the three methods: (method, its line's source, its message, line)."""
    module = ast.parse(text)
    lines = text.splitlines(keepends=True)
    found = []
    for name in METHODS:
        scope = alternatives.method(module, 'MCPServerApp', name)
        if scope is None:
            raise SystemExit(f'{CLI}: MCPServerApp.{name} is missing')
        for node in ast.walk(scope):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    isinstance(node.func.value, ast.Name) and node.func.value.id == 'log':
                if node.lineno != node.end_lineno:
                    raise SystemExit(f'{CLI}:{node.lineno}: a log call over several lines; this sweep reads one line')
                found.append((node.func.attr, lines[node.lineno - 1], ast.unparse(node.args[0]), node.lineno))
    return found


def relevelled(line: str, own: str, level: str) -> str:
    return line.replace(f'log.{own}(', f'log.{level}(', 1)


def labelled(message: str) -> str:
    """A short label for a line: what its message says."""
    if 'withheld' in message:
        return 'the withheld line'
    if 'without a probe answer' in message:
        return 'the unanswered line'
    if 'delegate mode' in message:
        return 'the delegate line'
    return 'the override line'


def sweep(text: str) -> tuple[list[tuple[str, tuple[tuple[str, str], ...]]], list[str]]:
    gaps: list[str] = []
    import cmdkit.logging
    levels = [n.lower() for n, v in cmdkit.logging.level_by_name.items() if v > 0]
    missing = [n for n in levels if n not in LOG_METHODS]
    if missing:
        gaps.append(f'LOG_METHODS names no method for the levels {missing}')
    import cluster_mcp.core
    absent = [m for m in LOG_METHODS if not callable(getattr(cluster_mcp.core.log, m, None))]
    if absent:
        gaps.append(f'the core logger has no method {absent}')
    calls = log_calls(text)
    if len(calls) != 4:
        gaps.append(f'expected 4 log calls in {METHODS}, found {len(calls)}')
    swept: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for own, line, message, _ in calls:
        label = labelled(message)
        swept += [(f'{label} is logged by {level}', ((line, relevelled(line, own, level)),))
                  for level in LOG_METHODS if level != own]
    served = [(own, line) for own, line, message, _ in calls if 'withheld' in message or 'without a probe' in message]
    if len(served) == 2 and {own for own, _ in served} == {'info', 'warning'}:
        (a_own, a_line), (b_own, b_line) = served
        swept.append(("_served's two levels exchanged",
                      ((a_line, relevelled(a_line, a_own, b_own)), (b_line, relevelled(b_line, b_own, a_own)))))
    else:
        gaps.append(f"_served logs {[own for own, _ in served]}, not one INFO and one WARNING line")
    return swept + list(FIXED), gaps


def coverage() -> tuple[list[str], list[str]]:
    text = alternatives.source(CLI)
    own_tree = alternatives.tree(text)
    alts, gaps = sweep(text)
    by_tree: dict[str, list[str]] = {}
    for case in mutants.CASES:
        if case.file == CLI:
            mutated = alternatives.applied(text, case.edits)
            if mutated is not None:
                by_tree.setdefault(alternatives.tree(mutated), []).append(case.id)
    known = {case.id: case for case in mutants.CASES}
    swept: list[str] = []

    def needs(alt_tree: str, what: str) -> None:
        names = by_tree.get(alt_tree, [])
        if not names:
            gaps.append(f'{CLI}: {what}: no mutant')
        for name in names:
            rows = {alternatives.row_set(t) for t in known[name].targets}
            missing = [s for s in SETS if s not in rows]
            if missing:
                gaps.append(f'{name}: no target row beside {missing}')
        swept.extend(names)

    for what, edits in alts:
        mutated = alternatives.applied(text, edits)
        if mutated is None:
            gaps.append(f'{CLI}: the anchor of "{what}" is not in the file once')
            continue
        alt_tree = alternatives.tree(mutated)
        if alt_tree == own_tree:
            gaps.append(f'{CLI}: "{what}" changes nothing in the syntax tree')
            continue
        if what in EQUIVALENT:
            if by_tree.get(alt_tree):
                gaps.append(f'{CLI}: "{what}" is recorded as equivalent and has a case {by_tree[alt_tree]}')
            continue
        needs(alt_tree, what)
    stale = [w for w in EQUIVALENT if w not in {what for what, _ in alts}]
    if stale:
        gaps.append(f'equivalents recorded for no alternative: {stale}')
    frozen, frozen_gaps = alternatives.alternatives('p2')
    gaps += [g for g in frozen_gaps if g.startswith(CLI)]
    module = ast.parse(text)
    spans = []
    for name in METHODS:
        scope = alternatives.method(module, 'MCPServerApp', name)
        spans.append((scope.lineno, scope.end_lineno))
    frozen_here = [a for a in frozen if a.file == CLI and any(lo <= a.line <= hi for lo, hi in spans)]
    for alt in frozen_here:
        needs(alt.tree, f'line {alt.line}: {alt.what} (the frozen sweep)')
    mine = sum(1 for what, _ in alts if what not in EQUIVALENT)
    print(f'coverage: {len(alts)} alternatives ({mine} with cases, {len(EQUIVALENT)} equivalent) over '
          f'{len(log_calls(text))} log calls and the resolver; {len(frozen_here)} frozen alternatives of '
          f'{", ".join(METHODS)} still cased', file=sys.stderr)
    ids = []
    for what, edits in alts:
        mutated = alternatives.applied(text, edits)
        if mutated is not None and what not in EQUIVALENT:
            ids += by_tree.get(alternatives.tree(mutated), [])
    return list(dict.fromkeys(ids)), gaps


def section_4() -> str:
    agents = (ROOT / 'AGENTS.md').read_text()
    start = agents.index('### 4. Execution-mode resolution')
    end = agents.index('\n### 5.', start)
    return ' '.join(agents[start:end].split())


LEVEL_WORD = re.compile(r'\b(DEVEL|TRACE|DEBUG|INFO|NOTICE|WARNING|ERROR|CRITICAL)\b')


def docs() -> list[str]:
    s4 = section_4()
    bad: list[str] = []
    for own, _, message, line in log_calls(alternatives.source(CLI)):
        level = LEVEL_OF.get(own, own.upper())
        chunks = [c.strip() for c in re.split(r'\{[^}]*\}', ast.literal_eval(message) if message.startswith("'")
                                              else message[2:-1]) if c.strip()]
        quote = max(chunks, key=len)
        at = s4.find(quote)
        if at < 0:
            bad.append(f'§4 does not quote the line {CLI}:{line} logs ({quote!r})')
            continue
        opening = s4.rfind('`', 0, at)
        before = LEVEL_WORD.findall(s4[max(0, opening - 40):opening])
        if not before or before[-1] != level:
            bad.append(f'§4 quotes {quote!r} after {before[-1] if before else "no level"}, but {CLI}:{line} logs it at '
                       f'{level}')
    if not re.search(r'both set, the flag wins', s4):
        bad.append('§4 does not say the flag wins when both are set')
    print(f'docs: {len(log_calls(alternatives.source(CLI)))} lines checked against §4', file=sys.stderr)
    return bad


def cases(ids: list[str]) -> list[str]:
    import subprocess
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
    alts, _ = sweep(alternatives.source(CLI))
    edits = dict(alts)
    for what in EQUIVALENT:
        case = mutants.Case('equivalent', CLI, edits[what], EQUIVALENT_TARGETS, '')
        for label, era in alternatives.ERAS.items():
            with tempfile.TemporaryDirectory(prefix='f7-equivalent-') as scratch:
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
            if child.returncode != 0 or ' passed' not in summary:
                bad.append(f'{what}, {label} era: recorded as equivalent, but its targets fail: '
                           f'{(child.stdout + child.stderr)[-600:]}')
    return bad


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('coverage', 'docs', 'cases', 'equivalents', 'all'):
        raise SystemExit('usage: F7-log-levels-and-precedence.py [coverage|docs|cases|equivalents|all]')
    ids, bad = coverage()
    if mode in ('docs', 'all'):
        bad += docs()
    if mode in ('cases', 'all'):
        bad += cases(ids) if ids else ['no case to run']
    if mode in ('equivalents', 'all'):
        bad += equivalents()
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'F7-log-levels-and-precedence: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
