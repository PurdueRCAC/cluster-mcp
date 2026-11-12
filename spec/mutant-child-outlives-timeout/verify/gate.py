"""Frozen gates of mutant-child-outlives-timeout: a child run past its limit is stopped whole and reported.

Run from the cycle worktree root, after staging (the data checks read the index or BASE, never the
working copy; the two modes that run code first refuse a working copy that differs from the index):

    UV_PYTHON=3.14 uv run python -I spec/mutant-child-outlives-timeout/verify/gate.py MODE ...

Modes, each one requirement's proof:

  untouched     Non-goals and the sibling cycle's rebase: only the cycle's files change since BASE;
                AGENTS.md changes only inside the mutation-runner bullet; in tests/mutants.py every
                top-level statement but the docstring, the imports, run_child, run_case and the
                `__main__` block is byte-identical to BASE's and in BASE's order (so no case, control,
                `main` or `self_check` changes), and every new one sits between apply_repo and run_child.
  rows ERA      R1, R2, R3 and the early-exit stops: every row in ROWS, run in ERA from
                tests/test_mutations.py, is in the JUnit report and passed (no failure, error or skip);
                then no process whose command line carries TOKEN is left.
  within-limit  R4: the sample cases and --self-check, run with the index's runner, print exactly
                within-limit.expected (develop's runner at BASE, on this host) and exit 0; and each
                sample case's targets, run unmutated through run_case, report exactly what
                unmutated.expected records (every target passed, on develop).
  prepush       Before the push: a clean tree, no site-private text in the cycle's added lines, and
                the deferral ledger over TECH.md's phases, PLAN.md and the branch's commit bodies.
  controls      Every data check above run on planted data: each plant refused for its reason, the
                sound data accepted.

Footprint: one pytest (rows) or one mutation runner (within-limit) at a time, each with one child
pytest at a time below it and that child's own few processes; memory as one suite process. Measured
on a development host: within-limit about 200 s (develop's runner, 2026-11-09: the sample 99–104 s, the unmutated pass about the same); rows about 15 s per era
once the rows exist (measured by P1's build, PLAN.md § 6).
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SLUG = 'mutant-child-outlives-timeout'
# The cycle's shape commit, found by its subject on HEAD's history, so a rebase of the branch cannot
# leave the gate measuring from a commit that is no longer the cycle's start.
SHAPE_SUBJECT = f'[fix] Shape {SLUG} goal'


def shape_commit() -> str:
    log = subprocess.run(['git', 'log', '--format=%H%x00%s', 'HEAD'], check=True, capture_output=True, text=True).stdout
    found = [h for h, _, subject in (line.partition('\0') for line in log.splitlines()) if subject == SHAPE_SUBJECT]
    if len(found) != 1:
        raise SystemExit(f'gate.py: {len(found)} commits on HEAD carry the subject {SHAPE_SUBJECT!r}, expected one')
    return found[0]


BASE = shape_commit()
HERE = Path(__file__).resolve().parent
EXPECTED = HERE / 'within-limit.expected'
UNMUTATED = HERE / 'unmutated.expected'
RUNNER = 'tests/mutants.py'
TESTS = 'tests/test_mutations.py'
TOKEN = 'mutant-hang-'
SAVED_ENV = dict(os.environ)
# Variables that would change what a child selects or which environment it runs in.
DROPPED = ('VIRTUAL_ENV', 'CLUSTER_MCP_TEST_ERA', 'CLUSTER_MCP_ERA_LOG', 'PYTEST_ADDOPTS', 'PYTEST_PLUGINS',
           'UV_PROJECT_ENVIRONMENT', 'UV_PROJECT', 'PYTHONPATH')

ALLOWED = {RUNNER, TESTS, 'AGENTS.md', 'issues/sandbox-dirs-left-on-kill.md'}
# Top-level statements of tests/mutants.py the cycle may change, by name (docstring and imports by kind).
CHANGEABLE = {'run_child', 'run_case', '__main__'}
BULLET = '- **The mutation runner, `tests/mutants.py`, is not collected.**'

SAMPLE = ('isolation-module-global', 'auth-middleware-sets-first-call-only', 'read-hook-resolves-storage-only',
          'ssh-timeout-raises', 'delegate-tilde-server-home', 'timeout-sentinel-minus-one', 'sftp-tilde-root',
          'local-record-scan-from-end', 'ladder-rungs-1-2-swapped', 'boundary-leaks-traceback',
          'site-agents-md-included', 'startup-ssh-unbounded', 'launcher-arg-unquoted',
          'prologue-unalias-shared-line', 'legacy-command-silent', 'env-legacy-wins',
          'capability-order-from-discovery', 'readme-window-altered', 'probe-parse-newline-always',
          'tpc-watchdog-dropped', 'shol-hook-removed', 'signal-death-not-reraised')

T = 'test_mutations.py::'
ROWS = tuple(
    [f'{T}test_run_members_follow_parents_and_groups[{p}]' for p in
     ('child', 'grandchild', 'orphan-in-the-group', 'new-session-group', 'unrelated-orphan', 'runner-group')]
    + [f'{T}test_gone_waits_until_every_process_ends[{p}]' for p in
       ('gone-at-once', 'zombie-is-gone', 'gone-after-polls', 'new-member-in-a-group', 'still-running')]
    + [f'{T}test_stop_run_freezes_then_kills_the_whole_run']
    + [f'{T}test_stop_run_kills_what_it_found_when_it_is_cut_short[{p}]' for p in ('table-fails', 'wrapper-gone')]
    + [f'{T}test_the_stop_figures']
    + [f'{T}test_a_timeout_reason_names_the_limit[{p}]' for p in ('gone', 'left')]
    + [f'{T}test_run_child_returns_what_the_child_returned']
    + [f'{T}test_run_child_stops_the_run_on_every_early_exit[{p}]' for p in ('timeout', 'interrupt', 'signal')]
    + [f'{T}test_a_runner_signal_exits_through_the_stop[{p}]' for p in ('term', 'hup')]
    + [f'{T}test_the_script_installs_the_signal_stop']
    + [f'{T}test_a_child_past_its_limit_is_stopped_whole_and_reported'])

PRIVATE = [(r'\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'an IP address'),
           (r'\b[\w-]+\.purdue\.edu\b', 'a site hostname'), (r'\.secur' r'ity/', 'a security-lane path'),
           (r'(?<![\w.+\\-])(?!git@)[\w.+-]+@[\w-]+(\.[\w-]+)+', 'an email address'),
           (r'/(Users|home)/(?!runner/)\w', 'a home path'), (r'/(private/tmp|var/folders)/', 'a host temporary path'),
           (r'~/K' r'B\b', "the operator's KB path"), (r'/scratch/\w', 'a cluster scratch path')]
SPEC_ID = r'(?<![A-Za-z0-9])([RPQF]\d{1,2}|F-[A-Z])(?![A-Za-z0-9])'
PHRASES = ('do not fix here', 'known limitation', 'left as a follow-up', 'follow-up', 'deferred', 'deferral',
           'not fixed')


def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout


def staged(path: str) -> str:
    return git('show', f':{path}')


def at(rev: str, path: str) -> str:
    return git('show', f'{rev}:{path}')


def child_env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in SAVED_ENV.items() if k not in DROPPED}
    env.update(extra)
    return env


def working_copy_violations() -> list[str]:
    if git('diff', '--name-only').strip():
        return ['the working copy differs from the index: stage first, so the gate runs what is committed']
    return []


# --- untouched ------------------------------------------------------------------------------------

def top_level(source: str) -> list[tuple[str, str]]:
    """Each top-level statement of `source` as (key, exact source text); a key names a def, a class,
    an assigned name, or the statement's kind."""
    tree = ast.parse(source)
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            key = node.name
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
            key = f'{node.target.id}:{type(node).__name__}'
        elif isinstance(node, ast.If) and '__name__' in ast.unparse(node.test):
            key = '__main__'
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            key = 'import'
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and node is tree.body[0]:
            key = 'docstring'
        else:
            key = f'{type(node).__name__}:{ast.unparse(node)[:60]}'
        out.append((key, ast.get_source_segment(source, node) or ''))
    return out


def bound_names(node: ast.stmt) -> set[str]:
    """Every name a top-level statement binds: a def, a class, any assignment target, an import."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {(a.asname or a.name).split('.')[0] for a in node.names}
    targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, 'target', None)]
    return {n.id for t in targets if t is not None for n in ast.walk(t) if isinstance(n, ast.Name)}


def run_case_violations(base: str, head: str) -> list[str]:
    """run_case may change only by wrapping one statement of BASE's in a single added try."""
    def body(source: str) -> ast.FunctionDef | None:
        return next((n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'run_case'), None)
    old, new = body(base), body(head)
    if new is None:
        return [f'{RUNNER}: run_case is gone']
    if ast.unparse(new) == ast.unparse(old):
        return []
    tries = [n for n in ast.walk(new) if isinstance(n, ast.Try)]
    if len(tries) != 1:
        return [f'{RUNNER}: run_case holds {len(tries)} try statements, expected the one that catches the timeout']

    class Unwrap(ast.NodeTransformer):
        def visit_Try(self, node: ast.Try):
            return node.body
    if ast.unparse(Unwrap().visit(new)) != ast.unparse(old):
        return [f'{RUNNER}: run_case changed beyond the one try around the child run']
    return []


def runner_violations(base: str, head: str) -> list[str]:
    found = []
    free = CHANGEABLE | {'import', 'docstring'}
    old = [(k, s) for k, s in top_level(base) if k not in free]
    new_all = top_level(head)
    old_texts = {s for _, s in old}
    kept = [(k, s) for k, s in new_all if k not in free and s in old_texts]
    if kept != old:
        missing = [k for k, s in old if (k, s) not in kept]
        found.append(f'{RUNNER}: statements that must stay byte-identical changed or moved: {missing[:6]}')
    keys = [k for k, _ in new_all]
    for name in ('apply_repo', 'run_child', 'run_case', '__main__'):
        if name not in keys:
            found.append(f'{RUNNER}: {name} is gone')
    if found:
        return found
    if keys.count('__main__') != 1 or keys[-1] != '__main__':
        found.append(f'{RUNNER}: the __main__ block must be one, and last')
    first_code = next(i for i, k in enumerate(keys) if k not in ('docstring', 'import'))
    if any(k == 'import' for k in keys[first_code:]):
        found.append(f'{RUNNER}: an import after the first statement that is not one')
    base_nodes = ast.parse(base).body
    base_bound = {n for node in base_nodes for n in bound_names(node)}
    start, end = keys.index('apply_repo'), keys.index('run_child')
    for i, (node, (k, s)) in enumerate(zip(ast.parse(head).body, new_all)):
        if k in free or s in old_texts:
            continue
        if not start < i < end:
            found.append(f'{RUNNER}: new statement {k} is outside the run-child block (between apply_repo and run_child)')
        if rebound := sorted(bound_names(node) & base_bound):
            found.append(f'{RUNNER}: new statement {k} rebinds {rebound}, which BASE already binds')
    return found + run_case_violations(base, head)


def tests_violations(base: str, head: str) -> list[str]:
    """tests/test_mutations.py: every non-import top-level statement of BASE's stays, byte-identical, in order."""
    old = [(k, s) for k, s in top_level(base) if k not in ('import', 'docstring')]
    texts = {s for _, s in top_level(head)}
    gone = [k for k, s in old if s not in texts]
    order = [s for _, s in top_level(head) if s in {t for _, t in old}]
    if gone:
        return [f'{TESTS}: BASE statements changed or removed: {gone[:6]}']
    if order != [s for _, s in old]:
        return [f'{TESTS}: BASE statements reordered']
    return []


def bullet_cut(agents: str) -> str:
    start = agents.index(BULLET)
    nxt = agents.find('\n- **', start + len(BULLET))
    return agents[:start] + agents[nxt if nxt != -1 else len(agents):]


def untouched_violations(name_status: list[tuple[str, str]], base_agents: str, head_agents: str | None,
                         base_runner: str, head_runner: str | None, base_tests: str = '',
                         head_tests: str | None = None) -> list[str]:
    found = []
    for status, name in name_status:
        if name.startswith(f'spec/{SLUG}/'):
            continue
        if name not in ALLOWED or status != 'M':
            found.append(f'{name}: {status}, outside the cycle\'s files')
    if head_agents is not None and bullet_cut(head_agents) != bullet_cut(base_agents):
        found.append('AGENTS.md: changed outside the mutation-runner bullet')
    if head_runner is not None:
        found += runner_violations(base_runner, head_runner)
    if head_tests is not None:
        found += tests_violations(base_tests, head_tests)
    return found


def mode_untouched() -> list[str]:
    pairs = [tuple(line.split('\t', 1)) for line in git('diff', '--cached', '--name-status', BASE).splitlines()]
    names = {n for _, n in pairs}
    return untouched_violations(pairs, at(BASE, 'AGENTS.md'), staged('AGENTS.md') if 'AGENTS.md' in names else None,
                                at(BASE, RUNNER), staged(RUNNER) if RUNNER in names else None,
                                at(BASE, TESTS), staged(TESTS) if TESTS in names else None)


# --- rows -----------------------------------------------------------------------------------------

def node_id(case: ET.Element) -> str:
    module = case.get('classname', '').split('.')
    return '/'.join(module[1:-1] + [module[-1] + '.py']) + '::' + case.get('name', '')


def rows_violations(junit_xml: str | None, rows: tuple[str, ...], leftovers: str) -> list[str]:
    found = []
    if junit_xml is None:
        return ['no JUnit report']
    seen: dict[str, list[str]] = {}
    for case in ET.fromstring(junit_xml).iter('testcase'):
        seen.setdefault(node_id(case), []).extend(c.tag for c in case)
    for row in rows:
        if row not in seen:
            found.append(f'{row}: not in the report')
        elif bad := sorted(set(seen[row]) & {'failure', 'error', 'skipped'}):
            found.append(f'{row}: {" and ".join(bad)}')
    if leftovers.strip():
        found.append(f'processes left carrying {TOKEN!r}: {leftovers.split()}')
    return found


def mode_rows(era: str) -> list[str]:
    found = working_copy_violations()
    with tempfile.TemporaryDirectory(prefix='mcot-gate-') as scratch:
        junit = Path(scratch) / 'junit.xml'
        subprocess.run(['uv', 'run', 'pytest', '-q', '-rA', '-p', 'no:cacheprovider', f'--junitxml={junit}',
                        'tests/test_mutations.py'], env=child_env(CLUSTER_MCP_TEST_ERA=era))
        report = junit.read_text() if junit.exists() else None
    left = subprocess.run(['pgrep', '-f', TOKEN], capture_output=True, text=True).stdout
    return found + rows_violations(report, ROWS, left)


# --- within-limit ---------------------------------------------------------------------------------

def within_violations(returncode: int, out: str, expected: str) -> list[str]:
    found = []
    if returncode != 0:
        found.append(f'the runner exited {returncode}, not 0')
    got, want = out.splitlines(), expected.splitlines()
    for i in range(max(len(got), len(want))):
        g = got[i] if i < len(got) else '<missing>'
        w = want[i] if i < len(want) else '<none expected>'
        if g != w:
            found.append(f'line {i + 1} differs from develop\'s: {g[:120]!r}, expected {w[:120]!r}')
    return found


# Each sample case's targets, run against a copy carrying only the survivor control's docstring edit:
# every target must pass as it does on develop, so a start that made a target fail by itself (a false
# kill, which would hide a real survivor) shows here even where the planted case still reads killed.
UNMUTATED_DRIVER = '''
import sys
sys.path.insert(0, 'tests')
import mutants
known = {c.id: c for c in mutants.CASES}
control = mutants.SURVIVOR_CONTROL
for cid in sys.argv[1:]:
    case = known[cid]
    plain = mutants.Case(f'unmutated-{cid}', control.file, control.edits, case.targets, case.why)
    print(f'{cid}: {mutants.run_case(plain)}', flush=True)
'''


def mode_within() -> list[str]:
    found = working_copy_violations()
    run = subprocess.run(['uv', 'run', 'python', RUNNER, '--self-check', *SAMPLE], env=child_env(),
                         capture_output=True, text=True)
    found += within_violations(run.returncode, run.stdout, EXPECTED.read_text())
    plain = subprocess.run(['uv', 'run', 'python', '-I', '-c', UNMUTATED_DRIVER, *SAMPLE], env=child_env(),
                           capture_output=True, text=True)
    found += [f'unmutated: {v}' for v in within_violations(plain.returncode, plain.stdout, UNMUTATED.read_text())]
    return found


# --- prepush --------------------------------------------------------------------------------------

def added_lines() -> list[tuple[str, str]]:
    current, lines = '', []
    for line in git('diff', '--cached', '-U0', '--no-color', BASE).splitlines():
        if line.startswith('+++ b/'):
            current = line[6:]
        elif line.startswith('+') and not line.startswith('+++'):
            lines.append((current, line[1:]))
    return lines


def private_violations(lines: list[tuple[str, str]]) -> list[str]:
    found = []
    for name, line in lines:
        for pattern, what in PRIVATE:
            if re.search(pattern, line):
                found.append(f'{name}: {what}: {line.strip()[:120]}')
        if name.startswith(('packages/', 'tests/')) and re.search(SPEC_ID, line):
            found.append(f'{name}: a feature-scoped id: {line.strip()[:120]}')
    return found


def blocks(text: str) -> list[str]:
    """Prose paragraphs and list items; Markdown headings and rules are never a block."""
    out, current = [], []
    for line in text.splitlines():
        stripped = line.strip()
        item = bool(re.match(r'([-*]|\d+\.)\s', stripped))
        if not stripped or stripped.startswith('#') or stripped == '---' or item:
            if current:
                out.append(' '.join(current))
            current = [stripped] if item else []
            continue
        current.append(stripped)
    if current:
        out.append(' '.join(current))
    return out


def ledger_violations(sources: list[tuple[str, str]], roadmap: str, exists) -> list[str]:
    found = []
    for source, text in sources:
        for block in blocks(text):
            if not any(p in re.sub(r'"[^"]*"', '', block).lower() for p in PHRASES):
                continue
            seeds = re.findall(r'issues/([a-z0-9-]+)\.md', block)
            if not seeds:
                found.append(f'{source}: a deferral names no issues/ seed: {block[:160]}')
            for seed in seeds:
                if not exists(f'issues/{seed}.md'):
                    found.append(f'{source}: issues/{seed}.md does not exist')
                elif f'issues/{seed}.md' not in roadmap:
                    found.append(f'{source}: issues/{seed}.md has no ROADMAP.md entry')
    return found


def mode_prepush() -> list[str]:
    found = []
    if git('diff', '--name-only').strip() or git('ls-files', '--others', '--exclude-standard').strip():
        found.append('the working tree holds changes the index does not')
    found += private_violations(added_lines())
    tech = staged(f'spec/{SLUG}/TECH.md')
    phases = tech[tech.index('## Phase P1'):tech.index('## How `code-build` drives this')]
    sources = [('TECH.md', phases), ('PLAN.md', staged(f'spec/{SLUG}/PLAN.md')),
               ('commit bodies', git('log', f'{BASE}..HEAD', '--format=%B'))]
    exists = lambda p: bool(git('ls-files', '--', p).strip())
    return found + ledger_violations(sources, staged('ROADMAP.md'), exists)


# --- controls -------------------------------------------------------------------------------------

def mode_controls() -> list[str]:
    found: list[str] = []

    def expect(label: str, violations: list[str], why: str | None) -> None:
        hit = any(why in v for v in violations) if why else violations == []
        print(f'{"ok " if hit else "BAD"} {label}: {violations[:2] if why else "sound data accepted"}')
        if not hit:
            found.append(f'control {label}: {violations}, wanted {why or "none"}')

    base_runner, base_agents = at(BASE, RUNNER), at(BASE, 'AGENTS.md')
    helper = '\n\ndef stop_run(proc):\n    return []\n'
    sound = base_runner.replace('\n\ndef run_child(', helper + '\n\ndef run_child(', 1)
    sound = sound.replace("timeout=300)", "timeout=LIMIT)", 1).replace('import argparse\n', 'import argparse\nimport signal\n', 1)
    sound_agents = base_agents.replace('A `FAILED` line means a case survived',
                                       'A `FAILED` line means a case timed out, survived', 1)
    u = lambda pairs, a=sound_agents, r=sound: untouched_violations(pairs, base_agents, a, base_runner, r)
    expect('untouched sound', u([('M', RUNNER), ('M', 'AGENTS.md'), ('A', f'spec/{SLUG}/PLAN.md')]), None)
    expect('untouched other file', u([('M', 'tests/test_hygiene.py')]), 'outside the cycle')
    expect('untouched new module', u([('A', 'tests/test_stop.py')]), 'outside the cycle')
    expect('untouched agents elsewhere', u([('M', 'AGENTS.md')], a=sound_agents.replace('## Packaging', '## Packaging!', 1)),
           'outside the mutation-runner bullet')
    expect('untouched main', u([('M', RUNNER)], r=sound.replace("    failed = False\n", "    failed = True\n", 1)),
           'byte-identical')
    expect('untouched self-check', u([('M', RUNNER)], r=sound.replace("prefix='mutant-origin-'", "prefix='mutant-o-'", 1)),
           'byte-identical')
    expect('untouched case', u([('M', RUNNER)], r=sound.replace("'ran as')", "'ran')", 1)), 'byte-identical')
    expect('untouched far helper', u([('M', RUNNER)], r=sound.replace(helper, '\n', 1).replace(
        '\n\ndef main(', helper + '\n\ndef main(', 1)), 'outside the run-child block')
    expect('untouched rebinds', u([('M', RUNNER)], r=sound.replace(helper, helper + '\n\nCASES = CASES[:9]\n', 1)),
           'rebinds')
    expect('untouched rebinds tuple', u([('M', RUNNER)], r=sound.replace(helper, helper + '\n\nMEMBERS, x = {}, 1\n', 1)),
           'rebinds')
    expect('untouched main-like if', u([('M', RUNNER)], r=sound.replace(helper, helper + "\n\nif __name__ != '':\n    pass\n", 1)),
           'one, and last')
    expect('untouched late import', u([('M', RUNNER)], r=sound.replace(helper, helper + '\n\nimport json\n', 1)),
           'an import after')
    tried = sound.replace('        child = run_child(src_override or src_root, case.targets, junit, repo)\n',
                          '        try:\n            child = run_child(src_override or src_root, case.targets, junit, repo)\n'
                          '        except ValueError as exc:\n            return [str(exc)]\n', 1)
    expect('untouched run_case try', u([('M', RUNNER)], r=tried), None)
    expect('untouched run_case filter', u([('M', RUNNER)], r=tried.replace(
        '    with tempfile.TemporaryDirectory(', "    if case.id.startswith('x'):\n        return []\n    with tempfile.TemporaryDirectory(", 1)),
           'beyond the one try')
    expect('untouched run_case two tries', u([('M', RUNNER)], r=tried.replace(
        '        report = junit.read_text() if junit.exists() else None\n',
        '        try:\n            report = junit.read_text() if junit.exists() else None\n        except OSError:\n            raise\n', 1)),
           'try statements')
    base_tests = at(BASE, TESTS)
    added = base_tests + '\n\n@pytest.mark.unit\ndef test_new() -> None:\n    assert True\n'
    t = lambda head: untouched_violations([('M', TESTS)], base_agents, None, base_runner, None, base_tests, head)
    expect('untouched tests sound', t(added.replace('from mutants import CASES,', 'from mutants import LIMIT, CASES,', 1)), None)
    expect('untouched tests weakened', t(added.replace("assert mutation_violations(1, KILLED, TARGETS, WHY) == []",
                                                       "assert True", 1)), 'changed or removed')

    good = ('<testsuites><testsuite>' + ''.join(
        f'<testcase classname="tests.{r.split("::")[0][:-3]}" name="{r.split("::")[1]}"/>' for r in ROWS)
        + '</testsuite></testsuites>')
    expect('rows sound', rows_violations(good, ROWS, ''), None)
    expect('rows missing', rows_violations(good.replace(f'name="{ROWS[-1].split("::")[1]}"', 'name="other"'), ROWS, ''),
           'not in the report')
    skipped = good.replace(f'name="{ROWS[0].split("::")[1]}"/>', f'name="{ROWS[0].split("::")[1]}"><skipped/></testcase>')
    expect('rows skipped', rows_violations(skipped, ROWS, ''), 'skipped')
    failed = good.replace(f'name="{ROWS[3].split("::")[1]}"/>', f'name="{ROWS[3].split("::")[1]}"><failure/></testcase>')
    expect('rows failed', rows_violations(failed, ROWS, ''), 'failure')
    expect('rows no report', rows_violations(None, ROWS, ''), 'no JUnit report')
    expect('rows leftover', rows_violations(good, ROWS, '4242\n'), 'processes left')

    want = EXPECTED.read_text()
    expect('within sound', within_violations(0, want, want), None)
    expect('within exit', within_violations(1, want, want), 'exited 1')
    expect('within changed', within_violations(0, want.replace('killed  ssh-timeout-raises', 'FAILED  ssh-timeout-raises', 1),
                                               want), 'line 4 differs')
    expect('within short', within_violations(0, '\n'.join(want.splitlines()[:-1]) + '\n', want), '<missing>')
    expect('within extra', within_violations(0, want + 'killed  extra\n', want), '<none expected>')

    expect('private home', private_violations([('tests/mutants.py', '# see /Us' 'ers/someone/x')]), 'a home path')
    expect('private spec id', private_violations([('tests/test_mutations.py', '# pins R2')]), 'feature-scoped id')
    expect('private sound', private_violations([('tests/mutants.py', 'LIMIT = 300')]), None)
    road = '**Seed:** [`issues/sandbox-dirs-left-on-kill.md`](issues/sandbox-dirs-left-on-kill.md)'
    real = {'issues/sandbox-dirs-left-on-kill.md', 'issues/other.md'}
    ex = lambda p: p in real
    expect('ledger sound', ledger_violations([('TECH.md', 'Deferred to `issues/sandbox-dirs-left-on-kill.md`.')], road, ex), None)
    expect('ledger no seed', ledger_violations([('TECH.md', 'A known limitation, recorded nowhere.')], road, ex),
           'names no issues/ seed')
    expect('ledger no entry', ledger_violations([('TECH.md', 'Left as a follow-up in `issues/other.md`.')], road, ex),
           'no ROADMAP.md entry')
    expect('ledger heading', ledger_violations([('PLAN.md', '## Out of scope (deferred)\n')], road, ex), None)
    return found


def main(argv: list[str]) -> int:
    modes = {'untouched': mode_untouched, 'within-limit': mode_within, 'prepush': mode_prepush,
             'controls': mode_controls}
    if argv[:1] == ['rows'] and len(argv) == 2 and argv[1] in ('legacy', 'modern'):
        found = mode_rows(argv[1])
    elif len(argv) == 1 and argv[0] in modes:
        found = modes[argv[0]]()
    else:
        print(f'usage: gate.py {{{"|".join(modes)}}} | rows legacy|modern', file=sys.stderr)
        return 2
    for line in found:
        print(f'FAIL {line}')
    print(f'{"ok" if not found else "red"}  {" ".join(argv)}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
