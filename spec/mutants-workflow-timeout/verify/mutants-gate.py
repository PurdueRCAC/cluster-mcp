"""Frozen gates of mutants-workflow-timeout: the dispatched mutation run, split into shards.

Run from the cycle worktree root, after staging (every tree mode reads the index or a commit, never
the working copy):

    UV_PYTHON=3.14 uv run -q python -I spec/mutants-workflow-timeout/verify/mutants-gate.py MODE ...

Modes, each one requirement's proof:

  rows PHASE        R1, R2, R3: every row PHASE names in tests/test_mutant_shards.py exists and passes,
                    each run by its own id (never a -k or marker selection), in both protocol eras.
                    Phase 1 names the runner's rows; phase 2 on adds the workflow's. The rows run
                    on the working copy, which `prepush` holds equal to the index.
  untouched PHASE   The case semantics and the sibling cycle's surface: in tests/mutants.py, every
                    top-level statement of the base except the module docstring, the imports and
                    `main` is unchanged, in order; `main` gains only the six sharding lines; the
                    imports gain only `Iterable`; the only new statements are the named sharding
                    block; tests/test_mutations.py is unchanged; and since the plan commit the cycle
                    changes only the files PHASE (1, 2, 3 or 4) may change.
  workflow          R1, R2, R5 and the Non-goals: .github/workflows/mutants.yml is dispatch-only,
                    read-only, holds a plan job and one matrix job, every job's timeout 20, its
                    shared steps verbatim as ci.yml's suite jobs carry them, the cases' step
                    capped below the job's, the ledger always run, and its header states the
                    dispatch state.
  docs [--final]    R4, R5: AGENTS.md § Testing drops the stale figure and dispatch sentence and
                    points to the `mutants budget` row, which holds the bound and the shard size
                    the code holds. --final: the row's baseline and § Testing's cost are filled and
                    equal what `runs` prints from the runs file.
  drive             R1, R2 on this host: the run's last shard, run as the workflow runs it, then its
                    ledger green; the same report with one case's line dropped, red naming it.
  prepush           Before a push: a clean tree, no site-private text in the cycle's added lines,
                    and the deferral ledger over TECH, PLAN and the commit bodies.
  runs --runs-file FILE [--final]
                    R1, R2, R3, R4 on the hosted runner (reads only, with gh): each listed run is a
                    dispatch of this workflow on the cycle branch at the measured commit (or one
                    that differs from it only in spec/, issues/ and ROADMAP.md); its plan names
                    every case this platform defines, each in one shard; every shard job reached
                    its ledger and reported each of its cases once; every job finished within
                    600 s, less HANG. Prints the worst of each job and the baseline sentence.
                    --final: exactly three runs, and every case not killed is named in an issues/
                    seed.
  controls          Every check above that decides from data, run on planted data: each plant must
                    be refused for its reason, and the sound data accepted.

Footprint: `rows` runs one pytest at a time (each a few seconds, one process); `drive` runs the
runner on one shard: one child pytest at a time under bin/sandbox.sh, about 90 s on a development
host; `runs` makes one gh call per run and per job log. Nothing runs in parallel.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SLUG = 'mutants-workflow-timeout'
BRANCH = f'ci/{SLUG}'
WORKFLOW = '.github/workflows/mutants.yml'
CI = '.github/workflows/ci.yml'
RUNNER = 'tests/mutants.py'
ROWS_FILE = 'tests/test_mutant_shards.py'
OLD_ROWS = 'tests/test_mutations.py'
BUDGET = 600
# The hang allowance under the plan's reading of R1 (PLAN § 3, row D1): a job holds one case stopped at
# the runner's 300 s limit, about 310 s, and still finishes within BUDGET.
HANG = 310
# The plan's shard size; `docs` holds the row to the runner's value and `runs` reads the measured commit's.
SHARD_SIZE = 15
# The one case only macOS defines (GOAL, Non-goals): the hosted runner's plan must lack it and nothing else.
DARWIN_ONLY = {'tpc-clobber'}
NEW_TOP = {'SHARD_SIZE', 'CONTROLS', 'shard_count', 'shard_ids', 'parse_shard', 'report_violations', 'sharded'}
ROWS = ('test_the_shards_hold_every_case_once', 'test_every_job_shards_the_cases_alike_whatever_their_order',
        'test_a_shard_outside_the_run_is_refused', 'test_the_run_holds_every_case_this_platform_defines',
        'test_the_ledger_accepts_a_shard_whose_every_case_was_killed', 'test_the_ledger_names_each_case_without_a_kill',
        'test_the_ledger_refuses_a_run_with_no_cases', 'test_the_ledger_reads_the_runner_s_own_lines',
        'test_the_mutants_workflow_runs_each_shard_to_a_ledger', 'test_cases_and_a_shard_together_are_refused',
        'test_the_ledger_fails_the_shard_and_names_each_case', 'test_a_run_with_no_cases_names_no_shard')
WORKFLOW_ROWS = ('test_the_mutants_workflow_runs_each_shard_to_a_ledger',)
PHASE_FILES = {
    1: {RUNNER, ROWS_FILE, 'AGENTS.md'},
    2: {RUNNER, ROWS_FILE, WORKFLOW, 'AGENTS.md'},
    3: {RUNNER, ROWS_FILE, WORKFLOW, 'AGENTS.md', 'ROADMAP.md'},
    4: {RUNNER, ROWS_FILE, WORKFLOW, 'AGENTS.md', 'ROADMAP.md'},
}
STALE = ('A child\n  takes about 2 s', 'about 2 s, all cases about 3 minutes', 'all cases about 3 minutes',
         'becomes dispatchable', 'it becomes\n  dispatchable', 'the release that first carries it')


def git(*args: str, check: bool = True) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, check=check).stdout


def base() -> str:
    return os.environ.get('MWT_BASE') or git('merge-base', 'HEAD', 'origin/develop').strip()


def plan_commit() -> str:
    """The commit that added PLAN.md: file lists grade from it, so the shaping commits' edits never count."""
    return os.environ.get('MWT_PLAN') or git('log', '-1', '--format=%H', '--diff-filter=A', '--',
                                             f'spec/{SLUG}/PLAN.md').strip()


def staged(name: str) -> str:
    return git('show', f':{name}', check=False)


def at(rev: str, name: str) -> str:
    return git('show', f'{rev}:{name}', check=False)


def norm(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


# --- rows ------------------------------------------------------------------------------------------

def mode_rows(phase: int) -> list[str]:
    found = []
    text = staged(ROWS_FILE)
    rows = ROWS if phase >= 2 else tuple(r for r in ROWS if r not in WORKFLOW_ROWS)
    for row in rows:
        if not re.search(rf'^def {row}\(', text, re.M):
            found.append(f'{ROWS_FILE}: no row {row}')
    if found:
        return found
    for era in ('legacy', 'modern'):
        env = {**os.environ, 'CLUSTER_MCP_TEST_ERA': era} if era == 'modern' else dict(os.environ)
        env.pop('CLUSTER_MCP_TEST_ERA', None) if era == 'legacy' else None
        ids = [f'{ROWS_FILE}::{row}' for row in rows]
        run = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', *ids], env=env,
                             capture_output=True, text=True)
        tail = run.stdout.strip().splitlines()[-1:] or ['']
        print(f'rows {era}: {tail[0]}')
        if run.returncode != 0 or ' passed' not in tail[0] or re.search(r'\b(failed|error|skipped|deselected)\b', tail[0]):
            found.append(f'rows {era}: {run.stdout[-1500:]}')
    return found


# --- untouched -------------------------------------------------------------------------------------

def top_level(source: str) -> list[tuple[str, str]]:
    """Each top-level statement's name and text, the comments and blank lines before it included."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    out, end = [], 0
    for i, node in enumerate(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif i == 0 and isinstance(node, ast.Expr) and isinstance(getattr(node, 'value', None), ast.Constant):
            name = '<docstring>'
        else:
            name = f'<{type(node).__name__}>'
        out.append((name, ''.join(lines[end:node.end_lineno])))
        end = node.end_lineno
    return out


MAIN_ADDED = (r"    parser\.add_argument\('--matrix', .*\)",
              r"    parser\.add_argument\('--shard', .*\)",
              r"    parser\.add_argument\('--ledger', .*\)",
              r"    status = sharded\(parser, args, list\(known\)\)",
              r"    if status is not None:",
              r"        return status")


def main_violations(old_main: str, new_main: str) -> list[str]:
    """`main` may only gain the sharding lines: nothing removed or changed, each added line one of MAIN_ADDED, once."""
    import difflib
    found = []
    diff = [line for line in difflib.unified_diff(old_main.splitlines(), new_main.splitlines(), lineterm='', n=0)
            if line[:1] in '+-' and not line.startswith(('+++', '---'))]
    removed = [line[1:] for line in diff if line.startswith('-')]
    added = [line[1:] for line in diff if line.startswith('+') and line[1:].strip()]
    found += [f'{RUNNER}: main lost or changed a line: {line.strip()[:100]}' for line in removed]
    for line in added:
        if not any(re.fullmatch(pattern, line) for pattern in MAIN_ADDED):
            found.append(f'{RUNNER}: main gained a line outside the sharding call: {line.strip()[:100]}')
    if sorted(added) != sorted(set(added)) or len(added) != len(MAIN_ADDED):
        found.append(f'{RUNNER}: main gained {len(added)} lines, not the {len(MAIN_ADDED)} sharding lines')
    return found


def untouched_violations(old: str, new: str, old_rows: str, new_rows: str, changed: set[str], phase: int) -> list[str]:
    found = []
    allowed = {'<docstring>', 'main', '<Import>', '<ImportFrom>'}
    old_top = top_level(old)
    old_names = {n for n, _ in old_top}
    found += main_violations(dict(old_top).get('main', ''), dict(top_level(new)).get('main', ''))
    before = [(n, s) for n, s in old_top if n not in allowed]
    after = top_level(new)
    extra = [n for n, _ in after if n not in old_names and n not in NEW_TOP]
    found += [f'{RUNNER}: a new top-level statement outside the sharding block: {n}' for n in extra]
    kept = [(n, s) for n, s in after if n not in allowed and n not in NEW_TOP]
    if kept != before:
        for (n1, s1), (n2, s2) in zip(before, kept):
            if (n1, s1) != (n2, s2):
                found.append(f'{RUNNER}: {n1} changed (the case semantics and the sibling cycle\'s surface stay as the base has them)')
                break
        else:
            found.append(f'{RUNNER}: the base\'s top-level statements are not all kept, in order')
    # Imports may only gain `Iterable` from typing.
    old_imports = [s for n, s in old_top if n in ('<Import>', '<ImportFrom>')]
    new_imports = [s for n, s in after if n in ('<Import>', '<ImportFrom>')]
    if [s.replace('from typing import Iterable, Sequence', 'from typing import Sequence') for s in new_imports] != old_imports:
        found.append(f'{RUNNER}: the imports changed beyond `Iterable`')
    if new_rows != old_rows:
        found.append(f'{OLD_ROWS}: changed (the sharding rows live in {ROWS_FILE})')
    stray = sorted(f for f in changed if not f.startswith(f'spec/{SLUG}/') and not f.startswith('issues/')
                   and f not in PHASE_FILES[phase])
    found += [f'a file phase {phase} does not change: {f}' for f in stray]
    return found


def mode_untouched(phase: int) -> list[str]:
    b = base()
    changed = set(git('diff', '--cached', '--name-only', plan_commit()).split())
    return untouched_violations(at(b, RUNNER), staged(RUNNER), at(b, OLD_ROWS), staged(OLD_ROWS), changed, phase)


# --- workflow --------------------------------------------------------------------------------------

def steps_of(text: str, job: str) -> list[str]:
    """The step blocks of one job, each as its text (comments dropped)."""
    jobs = text.split('\njobs:\n', 1)[1]
    blocks = re.split(r'^  (?=[\w-]+:\n)', jobs, flags=re.M)
    block = next((b for b in blocks if b.startswith(f'{job}:\n')), '')
    body = block.split('\n    steps:\n', 1)[1] if '\n    steps:\n' in block else ''
    body = '\n'.join(line for line in body.splitlines() if not line.strip().startswith('#'))
    return ['      - ' + s.rstrip() for s in re.split(r'^      - ', body, flags=re.M) if s.strip()]


def workflow_violations(text: str, ci_text: str) -> list[str]:
    found = []
    head = text.split('\nname:', 1)[0]
    if not re.search(r'^on:\n  workflow_dispatch:\n\n', text, re.M) or re.search(r'^  (push|pull_request|schedule|workflow_run)\b', text, re.M):
        found.append('the workflow runs on something other than a dispatch')
    if not re.search(r'^permissions:\n  contents: read\n\n', text, re.M) or text.count('permissions:') != 1:
        found.append('the token is not read-only')
    if '\ndefaults:\n  run:\n    shell: bash\n' not in text or text.count('shell:') != 1:
        found.append('a step does not run under the default bash (-e, pipefail)')
    for word, what in (('secrets.', 'reads a secret'), ('upload-artifact', 'uploads'), ('actions/cache', 'caches'),
                       ('continue-on-error', 'lets a step fail unseen'), ('|| true', 'lets a step fail unseen'),
                       ('max-parallel', 'caps the shards'), ('exclude:', 'drops a shard'), ('include:', 'adds a shard'),
                       ('github.token', 'hands a step the token'), ('GH_TOKEN', 'hands a step the token')):
        if word in text:
            found.append(f'the workflow {what}')
    jobs = re.findall(r'^  ([\w-]+):\n', text.split('\njobs:\n', 1)[1], re.M)
    if jobs != ['plan', 'mutants']:
        found.append(f'the jobs are {jobs}, not plan and mutants')
    timeouts = re.findall(r'^    timeout-minutes: (\d+)$', text, re.M)
    if timeouts != ['20'] * len(jobs):
        found.append(f'a job timeout is not 20: {timeouts}')
    if text.count('runs-on: ubuntu-24.04') != len(jobs) or text.count('runs-on:') != len(jobs):
        found.append('a job runs elsewhere than ubuntu-24.04')
    uses = set(re.findall(r'uses: (\S+)', text))
    unpinned = sorted(uses - set(re.findall(r'uses: (\S+)', ci_text)))
    if not uses or unpinned:
        found.append(f'an action ci.yml does not pin: {unpinned}')
    ci_steps = steps_of(ci_text, 'suite-legacy-1')
    shared = ci_steps[:-1]  # checkout, setup-uv, the shells, setup: everything but the suite command
    mine = steps_of(text, 'mutants')
    if mine[:len(shared)] != shared:
        found.append('the shard job\'s first steps are not ci.yml\'s suite-job steps verbatim')
    plan_steps = steps_of(text, 'plan')
    if plan_steps[:2] != shared[:2] or plan_steps[2:3] != [s for s in shared if 'uv sync --locked' in s]:
        found.append('the plan job\'s first steps are not ci.yml\'s checkout, setup-uv and setup verbatim')
    if plan_steps[3:] != ['      - id: shards\n        run: |\n          shards=$(uv run python tests/mutants.py --matrix)\n'
                          '          echo "shards=${shards}" >> "$GITHUB_OUTPUT"']:
        found.append('the plan job does not name the shards from the runner')
    if '      fail-fast: false\n' not in text:
        found.append('one shard failing cancels the others (fail-fast)')
    if '        shard: ${{ fromJSON(needs.plan.outputs.shards) }}\n' not in text or '    needs: plan\n' not in text:
        found.append('the shards are not the plan\'s')
    if '      SHARD: ${{ matrix.shard }}/${{ strategy.job-total }}\n' not in text:
        found.append('a shard is not told the run\'s shard count')
    rest = mine[len(shared):]
    run = rest[0] if rest else ''
    ledger = rest[1] if len(rest) > 1 else ''
    if run.splitlines()[:2] != ['      - name: run', '        timeout-minutes: 15']:
        found.append('the cases\' step is not capped at 15 minutes (PLAN § 3 row D2)')
    if run.splitlines()[2:] != ['        run: uv run python -u tests/mutants.py --self-check --shard "$SHARD" | tee mutants-report.txt']:
        found.append('the cases\' step is not the runner on its shard, with its controls, unbuffered, into the report')
    if ledger.splitlines() != ['      - name: ledger', '        if: always()',
                               '        run: uv run python tests/mutants.py --ledger mutants-report.txt --shard "$SHARD"']:
        found.append('the ledger does not always run on the shard\'s report')
    if len(rest) != 2:
        found.append(f'the shard job has {len(rest)} steps after setup, not the cases and the ledger')
    if 'becomes dispatchable' in norm(head) or 'main carries this one' not in norm(head):
        found.append('the header does not state the dispatch state')
    return found


def mode_workflow() -> list[str]:
    return workflow_violations(staged(WORKFLOW), staged(CI))


# --- docs ------------------------------------------------------------------------------------------

def testing_bullet(agents: str) -> str:
    m = re.search(r'^- \*\*The mutation runner, `tests/mutants.py`, is not collected\.\*\*.*?(?=^- \*\*)', agents, re.M | re.S)
    return m.group(0) if m else ''


def budget_row(agents: str) -> str:
    m = re.search(r'^\| mutants budget \| (.*) \|$', agents, re.M)
    return m.group(1) if m else ''


def docs_violations(agents: str, runner: str, final: bool, baseline: str | None) -> list[str]:
    found = []
    bullet, row = testing_bullet(agents), budget_row(agents)
    if not bullet:
        return ['AGENTS.md § Testing: no mutation-runner bullet']
    for phrase in STALE:
        if norm(phrase) in norm(bullet):
            found.append(f'§ Testing still says {phrase!r}')
    if '`mutants budget`' not in bullet:
        found.append('§ Testing does not point to the `mutants budget` row')
    for flag in ('--shard', '--ledger', '--matrix'):
        if flag not in bullet:
            found.append(f'§ Testing does not show {flag}')
    if 'main' not in bullet or 'dispatched against any branch' not in norm(bullet):
        found.append('§ Testing does not state the dispatch state')
    if not row:
        return found + ['§ Factory: no `mutants budget` row']
    for part in ('10 minutes of wall time', '`timeout-minutes` at 20', 'ubuntu-24.04', 'gh run view --json jobs'):
        if part not in row:
            found.append(f'the `mutants budget` row lacks {part!r}')
    size = re.search(r'^SHARD_SIZE = (\d+)$', runner, re.M)
    if not size or f'at most {size.group(1)} cases' not in row:
        found.append('the `mutants budget` row does not hold the shard size the runner holds')
    if not final:
        if 'Baseline' not in row:
            found.append('the `mutants budget` row has no Baseline')
        return found
    if baseline is None or baseline not in row:
        found.append(f'the row\'s baseline is not the measured one: {baseline!r}')
    if 'pending' in row:
        found.append('the row\'s baseline is still pending')
    cost = re.search(r'(\d[\d,]*) cases in (\d+) shards, slowest job (\d+:\d\d)', baseline or '')
    if not cost or f'{cost.group(1)} cases in {cost.group(2)} shards' not in norm(bullet) \
            or f'slowest job {cost.group(3)}' not in norm(bullet):
        found.append('§ Testing does not state the measured cost the row holds (cases, shards, slowest job)')
    return found


def mode_docs(final: bool) -> list[str]:
    baseline = None
    if final:
        report, found = read_runs(Path(f'spec/{SLUG}/runs.txt'), final=True)
        if found:
            return found
        baseline = report['baseline']
    return docs_violations(staged('AGENTS.md'), staged(RUNNER), final, baseline)


# --- drive -----------------------------------------------------------------------------------------

def mode_drive() -> list[str]:
    found = []
    with tempfile.TemporaryDirectory(prefix='mwt-drive-') as scratch:
        tree = Path(scratch) / 'tree'
        # The index, not the working copy: what the commit would hold.
        subprocess.run(['git', 'checkout-index', '-a', f'--prefix={tree}/'], check=True)
        env = {**os.environ, 'UV_PROJECT_ENVIRONMENT': str(Path(scratch) / 'venv')}
        subprocess.run(['uv', 'sync', '--locked', '-q'], cwd=tree, env=env, check=True)
        matrix = subprocess.run(['uv', 'run', 'python', 'tests/mutants.py', '--matrix'], cwd=tree, env=env,
                                capture_output=True, text=True)
        numbers = json.loads(matrix.stdout)
        count = numbers[-1]
        shard = f'{count}/{count}'
        report = Path(scratch) / 'report.txt'
        run = subprocess.run(f'set -o pipefail; uv run python -u tests/mutants.py --self-check --shard "{shard}" | tee "{report}"',
                             shell=True, cwd=tree, env=env, capture_output=True, text=True,
                             executable='/bin/bash')
        ledger = subprocess.run(['uv', 'run', 'python', 'tests/mutants.py', '--ledger', str(report), '--shard', shard],
                                cwd=tree, env=env, capture_output=True, text=True)
        print(f'drive: shard {shard}: runner {run.returncode}, ledger {ledger.returncode}: {ledger.stdout.strip()[-200:]}')
        if run.returncode != 0 or ledger.returncode != 0 or not ledger.stdout.startswith('ledger  '):
            found.append(f'the last shard is not green: {run.stdout[-800:]} {ledger.stdout[-800:]}')
        lines = report.read_text().splitlines()
        dropped = next(line for line in lines if line.startswith('killed  '))
        report.write_text('\n'.join(line for line in lines if line != dropped) + '\n')
        planted = subprocess.run(['uv', 'run', 'python', 'tests/mutants.py', '--ledger', str(report), '--shard', shard],
                                 cwd=tree, env=env, capture_output=True, text=True)
        case_id = dropped.split('  ', 1)[1].split(': ', 1)[0]
        if planted.returncode != 1 or f'FAILED  {case_id}: no verdict' not in planted.stdout:
            found.append(f'the ledger did not name a dropped case: {planted.stdout[-400:]}')
    return found


# --- prepush ---------------------------------------------------------------------------------------

PRIVATE = [(r'\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'an IP address'),
           (r'\b[\w-]+\.purdue\.edu\b', 'a site hostname'), (r'\.secur' r'ity/', 'a security-lane path'),
           (r'\b(GHSA-\w{4}-|CVE-\d{4}-\d|PYSEC-\d{4}-)', 'an advisory id'),
           (r'(?<![\w.+\\-])(?!git@)[\w.+-]+@[\w-]+(\.[\w-]+)+', 'an email address'),
           (r'/(Users|home)/(?!runner/)\w', 'a home path'),
           (r'/(private/tmp|var/folders)/', 'a host temporary path'), (r'~/K' r'B\b', "the operator's KB path"),
           (r'/scratch/\w', 'a cluster scratch path')]
SPEC_ID = r'(?<![A-Za-z0-9])([RPQF]\d{1,2}|F-[A-Z])(?![A-Za-z0-9])'
PHRASES = ('do not fix here', 'known limitation', 'left as a follow-up', 'follow-up', 'deferred', 'deferral',
           'not fixed', 'seeded')


def added_lines(rev: str) -> list[tuple[str, str]]:
    current, lines = '', []
    for line in git('diff', '--cached', '-U0', '--no-color', rev).splitlines():
        if line.startswith('+++ b/'):
            current = line[6:]
        elif line.startswith('+') and not line.startswith('+++'):
            lines.append((current, line[1:]))
    return lines


def private_violations(lines: list[tuple[str, str]]) -> list[str]:
    found = []
    for name, line in lines:
        if name.startswith(f'spec/{SLUG}/verify/'):
            continue  # The gate names the patterns it scans for.
        for pattern, what in PRIVATE:
            if re.search(pattern, line):
                found.append(f'{name}: {what}: {line.strip()[:120]}')
        if name.startswith(('packages/', 'tests/', '.github/')) and re.search(SPEC_ID, line):
            found.append(f'{name}: a feature-scoped id: {line.strip()[:120]}')
    return found


def blocks(text: str) -> list[str]:
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


def ledger_violations(text: str, source: str, roadmap: str, exists) -> list[str]:
    found = []
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
    b = base()
    found += private_violations(added_lines(b))
    exists = lambda p: bool(git('ls-files', '--', p).strip())
    roadmap = staged('ROADMAP.md')
    tech = staged(f'spec/{SLUG}/TECH.md')
    phases = tech[tech.find('## Phase P1'):tech.find('## How `code-build` drives this')]
    found += ledger_violations(phases, 'TECH.md', roadmap, exists)
    plan = staged(f'spec/{SLUG}/PLAN.md')
    found += ledger_violations(plan[plan.find('## 5.'):plan.find('## 6.')], 'PLAN.md § 5', roadmap, exists)
    found += ledger_violations(git('log', f'{b}..HEAD', '--format=%B'), 'commit bodies', roadmap, exists)
    return found


# --- runs ------------------------------------------------------------------------------------------

def log_text(line: str) -> tuple[str, str]:
    """A `gh run view --log` line: its step name and its text, without the timestamp."""
    parts = line.split('\t', 2)
    if len(parts) < 3:
        return '', ''
    text = re.sub(r'^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?', '', parts[2])
    return parts[1], text


def seconds(job: dict) -> float:
    from datetime import datetime
    start = datetime.fromisoformat(job['startedAt'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(job['completedAt'].replace('Z', '+00:00'))
    return (end - start).total_seconds()


CONTROL_TEXTS = ('surviving mutant reported', 'wrong origin reported', 'member missing from the copy reported')
QUEUE = 60


def same_code(measured: str, other: str) -> bool:
    """`other` is the measured commit, or one this clone holds that differs from it only in the cycle's records."""
    for sha in (measured, other):
        if not sha or subprocess.run(['git', 'cat-file', '-e', f'{sha}^{{commit}}'], capture_output=True).returncode:
            return False
    if other == measured:
        return True
    names = subprocess.run(['git', 'diff', '--name-only', measured, other], capture_output=True, text=True, check=True).stdout
    return all(n.startswith(('spec/', 'issues/')) or n == 'ROADMAP.md' for n in names.split())


def run_violations(run: dict, plan_log: list[str], shard_logs: dict[str, list[str]], expected: set[str],
                   sha_ok, size: int = SHARD_SIZE) -> tuple[list[str], dict[str, float], list[str], dict[str, int]]:
    """One run's violations, each job's seconds and each shard's case count by name, and the cases not killed."""
    found: list[str] = []
    rid = run.get('databaseId')
    if run.get('event') != 'workflow_dispatch' or run.get('workflowName') != 'Mutants' or run.get('headBranch') != BRANCH:
        found.append(f'run {rid}: not a dispatch of Mutants on {BRANCH}')
    if run.get('attempt') != 1:
        found.append(f'run {rid}: attempt {run.get("attempt")}, not a dispatch\'s first')
    if not sha_ok(run.get('headSha', '')):
        found.append(f'run {rid}: commit {run.get("headSha")} is unknown here or differs from the measured one '
                     f'outside spec/, issues/ and ROADMAP.md')
    if run.get('status') != 'completed':
        found.append(f'run {rid}: {run.get("status")}')
    plan: dict[int, list[str]] = {}
    count = 0
    for line in plan_log:
        m = re.match(r'shard (\d+) of (\d+): (.*)$', log_text(line)[1])
        if m:
            plan[int(m.group(1))] = m.group(3).split()
            count = int(m.group(2))
    named = [i for ids in plan.values() for i in ids]
    if sorted(plan) != list(range(1, count + 1)) or not count:
        found.append(f'run {rid}: the plan does not name shards 1 to {count}')
    if len(named) != len(set(named)) or set(named) != expected:
        found.append(f'run {rid}: the plan\'s shards do not hold each case once: missing {sorted(expected - set(named))[:5]}, '
                     f'extra {sorted(set(named) - expected)[:5]}, twice {len(named) - len(set(named))}')
    if count != -(-len(expected) // size):
        found.append(f'run {rid}: {count} shards for {len(expected)} cases at {size} a shard')
    times: dict[str, float] = {}
    sizes: dict[str, int] = {}
    jobs = run.get('jobs', [])
    names = sorted(j['name'] for j in jobs)
    wanted = sorted(['plan'] + [f'mutants ({n} of {count})' for n in range(1, count + 1)])
    if names != wanted:
        found.append(f'run {rid}: jobs {len(names)}, not the plan and {count} shards')
    not_killed: list[str] = []
    reported: list[str] = []
    for job in jobs:
        name = job['name']
        if job.get('status') != 'completed' or job.get('conclusion') not in ('success', 'failure'):
            found.append(f'run {rid}: {name} {job.get("status")}/{job.get("conclusion")}')
            continue
        times[name] = seconds(job)
        steps = job.get('steps', [])
        # A job's measured start is when a runner took it; a wait in the queue before that would inflate it.
        if steps and steps[0].get('startedAt') and seconds({'startedAt': job['startedAt'],
                                                             'completedAt': steps[0]['startedAt']}) > QUEUE:
            found.append(f'run {rid}: {name} started {QUEUE} s or more before its first step: the measure holds a wait')
        if times[name] > BUDGET - HANG:
            found.append(f'run {rid}: {name} took {times[name]:.0f} s, over {BUDGET} s less one hung case ({HANG} s)')
        if name == 'plan':
            continue
        by_name = {s['name']: s for s in steps}
        if by_name.get('ledger', {}).get('conclusion') not in ('success', 'failure'):
            found.append(f'run {rid}: {name} never reached its ledger')
        number = int(re.match(r'mutants \((\d+) of', name).group(1))
        sizes[name] = len(plan.get(number, []))
        lines = [log_text(line) for line in shard_logs.get(name, [])]
        ran = [text for step, text in lines if step == 'run']
        verdicts = [re.match(r'(killed|FAILED)  ([^\s:]+): ', text) for text in ran]
        ids = [m.group(2) for m in verdicts if m]
        if sorted(ids) != sorted(plan.get(number, [])):
            found.append(f'run {rid}: {name} reported {len(ids)} verdicts, not one for each of its {sizes[name]} cases')
        # A failed control means the shard's kills prove nothing: the run is no evidence.
        controls = sorted(text.split('  ', 1)[1].split(': ', 1)[0] for text in ran if text.startswith('control  '))
        if controls != sorted(CONTROL_TEXTS) or any(text.startswith(f'FAILED  {c}') for text in ran for c in CONTROL_TEXTS):
            found.append(f'run {rid}: {name}: the runner\'s controls did not all pass ({controls})')
        reported += ids
        not_killed += [m.group(2) for m in verdicts if m and m.group(1) == 'FAILED']
        ledger = [text for step, text in lines if step == 'ledger' and re.match(r'(ledger|FAILED)  ', text)]
        if any(t.startswith('FAILED  control ') for t in ledger):
            found.append(f'run {rid}: {name}: its ledger found a control failed')
        if job['conclusion'] == 'success' and not any(t.startswith(f'ledger  shard {number} of {count}: ') for t in ledger):
            found.append(f'run {rid}: {name} passed without its ledger line')
        if job['conclusion'] == 'failure' and not any(t.startswith('FAILED  ') for t in ledger):
            found.append(f'run {rid}: {name} failed and its ledger names no case')
    if sorted(reported) != sorted(named):
        found.append(f'run {rid}: the shards\' reports do not hold each planned case once')
    return found, times, not_killed, sizes


def fmt(s: float) -> str:
    return f'{int(s) // 60}:{int(s) % 60:02d}'


def expected_cases(sha: str) -> set[str]:
    with tempfile.TemporaryDirectory(prefix='mwt-cases-') as scratch:
        subprocess.run(f'git archive {sha} | tar -x -C "{scratch}"', shell=True, check=True)
        out = subprocess.run(['uv', 'run', 'python', '-c', "import sys; sys.path.insert(0, 'tests'); import mutants; "
                              "print(*(c.id for c in mutants.CASES))"], cwd=scratch, capture_output=True, text=True,
                             check=True).stdout.split()
    return set(out) - (DARWIN_ONLY if sys.platform == 'darwin' else set())


def baseline_sentence(n_cases: int, ids: list[str], sha: str, worst: dict[str, float], sizes: dict[str, int]) -> str:
    shards = sorted((n for n in worst if n != 'plan'), key=lambda n: int(re.match(r'mutants \((\d+)', n).group(1)))
    slowest = max(shards, key=lambda n: worst[n]) if shards else ''
    per_case = worst[slowest] / sizes[slowest] if slowest and sizes.get(slowest) else 0.0
    return (f'{n_cases:,} cases in {len(shards)} shards, slowest job {fmt(worst.get(slowest, 0))} '
            f'({per_case:.1f} s a case with its setup, over its {sizes.get(slowest, 0)} cases); worst of each job over the '
            f'{len(ids)} runs counted at landing, commit `{sha[:7]}`, runs {", ".join(ids)}: plan {fmt(worst.get("plan", 0))}, '
            f'shards ' + ' '.join(fmt(worst[n]) for n in shards))


def read_runs(path: Path, final: bool, fetch=None) -> tuple[dict, list[str]]:
    lines = [line.split('#', 1)[0].strip() for line in path.read_text().splitlines()] if path.exists() else []
    sha = next((line.split()[1] for line in lines if line.startswith('sha ')), '')
    ids = [line.split()[1] for line in lines if line.startswith('run ')]
    if not sha or not ids:
        return {}, [f'{path}: no sha or no run']
    if final and len(ids) != 3:
        return {}, [f'{path}: {len(ids)} runs, not the three counted']
    if not same_code(sha, sha):
        return {}, [f'{path}: the measured commit {sha} is not in this clone']
    size = re.search(r'^SHARD_SIZE = (\d+)$', at(sha, RUNNER), re.M)
    if not size:
        return {}, [f'{RUNNER} at {sha[:7]} holds no SHARD_SIZE']
    fetch = fetch or gh_fetch
    expected = expected_cases(sha)
    found: list[str] = []
    worst: dict[str, float] = {}
    sizes: dict[str, int] = {}
    not_killed: set[str] = set()
    for rid in ids:
        run, plan_log, shard_logs = fetch(rid)
        v, times, nk, sz = run_violations(run, plan_log, shard_logs, expected, lambda other: same_code(sha, other),
                                          int(size.group(1)))
        found += v
        not_killed |= set(nk)
        sizes.update(sz)
        for name, s in times.items():
            worst[name] = max(worst.get(name, 0), s)
    baseline = baseline_sentence(len(expected), ids, sha, worst, sizes)
    print(f'baseline: {baseline}')
    shard_times = [s for n, s in worst.items() if n != 'plan']
    if shard_times:
        print(f'worst shard {fmt(max(shard_times))}; headroom under {BUDGET} s: {BUDGET - max(shard_times):.0f} s, '
              f'{BUDGET - HANG - max(shard_times):.0f} s after one hung case')
    for case_id in sorted(not_killed):
        print(f'not killed: {case_id}')
    if final:
        # What lands is what was measured: after the measured commit only the records and the row's documents change.
        drift = [n for n in git('diff', '--cached', '--name-only', sha).split()
                 if not (n.startswith(('spec/', 'issues/')) or n in ('ROADMAP.md', 'AGENTS.md'))]
        found += [f'{n}: changed since the measured commit {sha[:7]}' for n in drift]
        seeds = git('grep', '-l', '-e', SLUG, '--cached', '--', 'issues/', check=False)
        texts = '\n'.join(staged(name) for name in seeds.split())
        found += [f'{case_id}: not killed on the hosted runner and named in no issues/ seed' for case_id in sorted(not_killed)
                  if not re.search(rf'(?<![\w-]){re.escape(case_id)}(?![\w-])', texts)]
    return {'baseline': baseline, 'worst': worst, 'not_killed': not_killed}, found


def gh_fetch(rid: str) -> tuple[dict, list[str], dict[str, list[str]]]:
    run = json.loads(subprocess.run(['gh', 'run', 'view', rid, '--json',
                                     'databaseId,event,workflowName,headBranch,headSha,status,conclusion,attempt,jobs'],
                                    capture_output=True, text=True, check=True).stdout)
    logs: dict[str, list[str]] = {}
    for job in run['jobs']:
        out = subprocess.run(['gh', 'run', 'view', rid, '--log', '--job', str(job['databaseId'])],
                             capture_output=True, text=True).stdout
        logs[job['name']] = out.splitlines()
    return run, logs.pop('plan', []), logs


def mode_runs(path: Path, final: bool) -> list[str]:
    return read_runs(path, final)[1]


# --- controls --------------------------------------------------------------------------------------

def mode_controls() -> list[str]:
    found: list[str] = []

    def expect(label: str, violations: list[str], why: str | None) -> None:
        hit = any(why in v for v in violations) if why else violations == []
        print(f'{"ok " if hit else "BAD"} {label}: {violations[:2] if why else "sound data accepted"}')
        if not hit:
            found.append(f'control {label}: {violations}, wanted {why or "none"}')

    wf, ci_text = staged(WORKFLOW), staged(CI)
    expect('workflow sound', workflow_violations(wf, ci_text), None)
    for label, old, new, why in [
        ('push', 'on:\n  workflow_dispatch:\n', 'on:\n  workflow_dispatch:\n  push:\n', 'other than a dispatch'),
        ('write token', '  contents: read\n', '  contents: write\n', 'not read-only'),
        ('fail-fast', 'fail-fast: false', 'fail-fast: true', 'fail-fast'),
        ('job timeout', '    timeout-minutes: 20\n    strategy:', '    timeout-minutes: 30\n    strategy:', 'not 20'),
        ('step timeout', '        timeout-minutes: 15\n', '        timeout-minutes: 19\n', 'not capped'),
        ('no shells', '      - run: sudo apt-get', '      - run: sudo true || sudo apt-get', 'verbatim'),
        ('matrix fixed', '${{ fromJSON(needs.plan.outputs.shards) }}', '[1, 2]', 'not the plan'),
        ('ledger skipped', '        if: always()\n', '', 'always run'),
        ('no controls', '--self-check --shard', '--shard', 'with its controls'),
        ('buffered', 'python -u tests', 'python tests', 'unbuffered'),
        ('upload', '      - name: ledger\n', '      - uses: actions/upload-artifact@0\n      - name: ledger\n', 'uploads'),
        ('stale header', 'main carries this one', 'it becomes dispatchable later', 'dispatch state'),
        ('ledger or true', '--shard "$SHARD"\n', '--shard "$SHARD" || true\n', 'fail unseen'),
        ('runner or true', '| tee mutants-report.txt', '| tee mutants-report.txt || true', 'fail unseen'),
        ('no pipefail', 'defaults:\n  run:\n    shell: bash\n\n', '', 'default bash'),
        ('step shell', '        timeout-minutes: 15\n', '        timeout-minutes: 15\n        shell: bash {0}\n', 'default bash'),
        ('shard excluded', '      fail-fast: false\n', '      fail-fast: false\n      matrix-exclude: x\n        exclude: [{shard: 1}]\n',
         'drops a shard'),
        ('cap zero', '        timeout-minutes: 15\n', '        timeout-minutes: 0\n', 'capped at 15'),
        ('token', '    env:\n', '    env:\n      GH_TOKEN: ${{ github.token }}\n', 'the token'),
    ]:
        expect(f'workflow {label}', workflow_violations(wf.replace(old, new, 1) if old in wf else wf + '\nPLANT-MISSED', ci_text), why)

    agents, runner = staged('AGENTS.md'), staged(RUNNER)
    expect('docs sound', docs_violations(agents, runner, False, None), None)
    bullet = testing_bullet(agents)
    expect('docs stale figure', docs_violations(agents.replace(bullet, bullet + 'A child takes about 2 s, all cases about 3 minutes.\n'),
                                                runner, False, None), 'still says')
    expect('docs size differs', docs_violations(agents, runner.replace(f'SHARD_SIZE = {SHARD_SIZE}', 'SHARD_SIZE = 36'), False, None),
           'shard size')
    expect('docs no pointer', docs_violations(agents.replace(bullet, bullet.replace('`mutants budget`', '`budget`')), runner, False, None),
           'point to')
    row = budget_row(agents)
    sentence = '1,164 cases in 78 shards, slowest job 3:41 (14.7 s a case with its setup, over its 15 cases); worst'
    filled = agents.replace(row, row.replace('pending', sentence))
    expect('docs final sound', docs_violations(filled.replace(bullet, bullet + ' 1,164 cases in 78 shards, slowest job 3:41 '),
                                               runner, True, sentence), None)
    expect('docs final no time', docs_violations(filled.replace(bullet, bullet + ' 1,164 cases in 78 shards '),
                                                 runner, True, sentence), 'slowest job')
    expect('docs final pending', docs_violations(agents, runner, True, sentence), 'pending')

    b = base()
    old, new = at(b, RUNNER), staged(RUNNER)
    rows_old, rows_new = at(b, OLD_ROWS), staged(OLD_ROWS)
    expect('untouched sound', untouched_violations(old, new, rows_old, rows_new, {RUNNER, ROWS_FILE}, 1), None)
    expect('untouched run_child', untouched_violations(old, new.replace('timeout=300)', 'timeout=600)'), rows_old, rows_new,
                                                       {RUNNER}, 1), 'run_child changed')
    expect('untouched case', untouched_violations(old, new.replace("'still waiting'", "'still'", 1), rows_old, rows_new,
                                                  {RUNNER}, 1), 'changed')
    expect('untouched stray', untouched_violations(old, new.replace('\n\ndef main(', '\n\nEXTRA = 1\n\n\ndef main('), rows_old,
                                                   rows_new, {RUNNER}, 1), 'outside the sharding block')
    expect('untouched old rows changed', untouched_violations(old, new, rows_old, rows_new.replace('@pytest.mark.unit\n', '', 1),
                                                              {RUNNER}, 1), 'the sharding rows live')
    expect('untouched main swallows a crash', untouched_violations(
        old, new.replace('        violations = run_case(case)\n',
                         '        try:\n            violations = run_case(case)\n        except Exception:\n'
                         '            violations = []\n'), rows_old, rows_new, {RUNNER}, 1), 'main lost or changed')
    expect('untouched main extra line', untouched_violations(
        old, new.replace('    status = sharded(parser, args, list(known))\n',
                         '    status = sharded(parser, args, list(known))\n    args.self_check = True\n'),
        rows_old, rows_new, {RUNNER}, 1), 'outside the sharding call')
    expect('untouched file', untouched_violations(old, new, rows_old, rows_new, {'tests/conftest.py'}, 1), 'does not change')
    expect('untouched workflow early', untouched_violations(old, new, rows_old, rows_new, {WORKFLOW}, 1), 'does not change')

    expect('private home', private_violations([('AGENTS.md', 'see /Users/someone/x')]), 'a home path')
    expect('private spec id', private_violations([('tests/test_mutations.py', '# R1 holds')]), 'feature-scoped')
    expect('ledger unseeded', ledger_violations('- left as a follow-up, nowhere', 'TECH.md', '', lambda p: False), 'names no')

    # The runs check, on a run built as the workflow would produce it.
    ids = sorted(f'case-{n:03d}' for n in range(40))
    count = -(-len(ids) // SHARD_SIZE)
    shards = {n: ids[n - 1::count] for n in range(1, count + 1)}
    stamp = '2026-11-10T01:00:00.0000000Z '

    def job(name: str, secs: int, conclusion: str = 'success', ledger: str = 'success', wait: int = 1) -> dict:
        return {'name': name, 'status': 'completed', 'conclusion': conclusion, 'startedAt': '2026-11-10T01:00:00Z',
                'completedAt': f'2026-11-10T01:{secs // 60:02d}:{secs % 60:02d}Z',
                'steps': [{'name': 'Set up job', 'conclusion': 'success',
                           'startedAt': f'2026-11-10T01:{wait // 60:02d}:{wait % 60:02d}Z'},
                          {'name': 'run', 'conclusion': conclusion}, {'name': 'ledger', 'conclusion': ledger}]}

    def sound() -> tuple[dict, list[str], dict[str, list[str]]]:
        run = {'databaseId': 1, 'event': 'workflow_dispatch', 'workflowName': 'Mutants', 'headBranch': BRANCH,
               'headSha': 'a' * 40, 'status': 'completed', 'conclusion': 'success', 'attempt': 1,
               'jobs': [job('plan', 30)] + [job(f'mutants ({n} of {count})', 200) for n in shards]}
        plan_log = [f'plan\tshards\t{stamp}shard {n} of {count}: {" ".join(s)}' for n, s in shards.items()]
        logs = {f'mutants ({n} of {count})': [f'x\trun\t{stamp}killed  {i}: t failed with \'w\'' for i in s]
                + [f'x\trun\t{stamp}control  {c}: [...]' for c in CONTROL_TEXTS]
                + [f'x\tledger\t{stamp}ledger  shard {n} of {count}: {len(s)} cases killed, 3 controls passed']
                for n, s in shards.items()}
        return run, plan_log, logs

    ok = lambda sha: sha == 'a' * 40
    expect('runs sound', run_violations(*sound(), set(ids), ok)[0], None)
    run, plan_log, logs = sound()
    expect('runs push', run_violations({**run, 'event': 'push'}, plan_log, logs, set(ids), ok)[0], 'not a dispatch')
    expect('runs other sha', run_violations({**run, 'headSha': 'b' * 40}, plan_log, logs, set(ids), ok)[0], 'differs')
    expect('runs plan lost a case', run_violations(run, [plan_log[0].replace(f' {ids[0]}', '')] + plan_log[1:], logs,
                                                   set(ids), ok)[0], 'each case once')
    expect('runs plan overlap', run_violations(run, plan_log[:1] + [plan_log[1] + f' {ids[0]}'] + plan_log[2:], logs,
                                               set(ids), ok)[0], 'each case once')
    expect('runs platform case lost', run_violations(run, plan_log, logs, set(ids) | {'tpc-only'}, ok)[0], 'missing')
    slow = {**run, 'jobs': [job('plan', 30)] + [job(f'mutants ({n} of {count})', 300 if n == 1 else 200) for n in shards]}
    expect('runs slow job', run_violations(slow, plan_log, logs, set(ids), ok)[0], 'less one hung case')
    gone = {**run, 'jobs': run['jobs'][:-1]}
    expect('runs shard missing', run_violations(gone, plan_log, logs, set(ids), ok)[0], 'not the plan and')
    cancelled = {**run, 'jobs': run['jobs'][:-1] + [{**run['jobs'][-1], 'conclusion': 'cancelled'}]}
    expect('runs shard cancelled', run_violations(cancelled, plan_log, logs, set(ids), ok)[0], 'cancelled')
    short = {k: (v[1:] if k.startswith('mutants (1 ') else v) for k, v in logs.items()}
    expect('runs verdict lost', run_violations(run, plan_log, short, set(ids), ok)[0], 'not one for each')
    noledger = {k: [line for line in v if '\tledger\t' not in line] for k, v in logs.items()}
    expect('runs no ledger line', run_violations(run, plan_log, noledger, set(ids), ok)[0], 'without its ledger line')
    failed_logs = dict(logs)
    first = f'mutants (1 of {count})'
    failed_logs[first] = [line.replace(f'killed  {shards[1][0]}', f'FAILED  {shards[1][0]}') for line in logs[first]]
    failed_logs[first] = [line for line in failed_logs[first] if '\tledger\t' not in line] + \
        [f'x\tledger\t{stamp}FAILED  {shards[1][0]}: not killed (its FAILED line says why)']
    failed_run = {**run, 'jobs': [job('plan', 30), job(first, 200, 'failure', 'failure')] + run['jobs'][2:]}
    v, _, nk, _ = run_violations(failed_run, plan_log, failed_logs, set(ids), ok)
    expect('runs a survivor is reported, not refused', v, None)
    if nk != [shards[1][0]]:
        found.append(f'control runs survivor: not-killed list {nk}')
    print(f'{"ok " if nk == [shards[1][0]] else "BAD"} runs survivor listed: {nk}')
    bad_control = {k: [line.replace(f'control  {CONTROL_TEXTS[1]}', f'FAILED  {CONTROL_TEXTS[1]}') for line in v]
                   for k, v in logs.items()}
    expect('runs control failed', run_violations(run, plan_log, bad_control, set(ids), ok)[0], 'controls did not all pass')
    queued = {**run, 'jobs': [job('plan', 30)] + [job(f'mutants ({n} of {count})', 200, wait=120 if n == 2 else 1)
                                                  for n in shards]}
    expect('runs queue inside the measure', run_violations(queued, plan_log, logs, set(ids), ok)[0], 'holds a wait')
    expect('runs size from the measured commit', run_violations(run, plan_log, logs, set(ids), ok, size=50)[0],
           'at 50 a shard')
    head = git('rev-parse', 'HEAD').strip()
    expect('same code: the commit itself', [] if same_code(head, head) else ['refused'], None)
    expect('same code: an unknown commit', ['unknown'] if not same_code(head, 'f' * 40) else [], 'unknown')
    expect('log line parse', [] if log_text(f'job\tledger\t﻿{stamp}ledger  x') == ('ledger', 'ledger  x') else ['bad'], None)
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['rows', 'untouched', 'workflow', 'docs', 'drive', 'prepush', 'runs', 'controls'])
    parser.add_argument('phase', nargs='?', type=int)
    parser.add_argument('--final', action='store_true')
    parser.add_argument('--runs-file', type=Path, default=Path(f'spec/{SLUG}/runs.txt'))
    args = parser.parse_args()
    if args.mode in ('untouched', 'rows') and args.phase not in PHASE_FILES:
        parser.error(f'{args.mode} takes the phase: 1, 2, 3 or 4')
    if args.mode == 'untouched':
        found = mode_untouched(args.phase)
    elif args.mode == 'rows':
        found = mode_rows(args.phase)
    elif args.mode == 'docs':
        found = mode_docs(args.final)
    elif args.mode == 'runs':
        found = mode_runs(args.runs_file, args.final)
    else:
        found = {'workflow': mode_workflow, 'drive': mode_drive, 'prepush': mode_prepush,
                 'controls': mode_controls}[args.mode]()
    for line in found:
        print(f'FAILED  {line}')
    print(f'{args.mode}: {"ok" if not found else f"{len(found)} failed"}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
