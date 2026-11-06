"""Frozen gates of suite-ci-time-budget: each era's suite split into several CI jobs.

Run from the cycle worktree root, after staging (every mode reads the index or a commit, never the
working copy):

    UV_PYTHON=3.14 uv run --with pyyaml python -I spec/suite-ci-time-budget/verify/suite-gate.py MODE ...

Modes, each one requirement's proof:

  mirror            R6: the profile's verify, the release recipe's gate and ci.yml run the same suite
                    commands, verbatim and in order; every suite job is the base's suite job with its
                    one pytest step replaced; the gate job needs every suite job; the documents
                    describe the jobs; every commit that changes one list changes the workflow too.
                    Also R7's row (budget and measure) is present.
  untouched         R3: no existing test module, conftest, helper, package, lock or pytest setting
                    changes, and AGENTS.md changes only where the profile, the recipe, the CI bullet and
                    the era bullet are (the suite reads other sections of it).
  partition ERA     R2: the base's suite command and the branch's suite jobs, collected in ERA: the jobs
                    are pairwise disjoint, together hold every base id, and add only ids of new modules.
  fixtures ERA      R4: each session-scoped or autouse fixture and the collection hook of
                    tests/conftest.py fails a planted violation under each branch suite command of ERA,
                    for the same reason it fails under the base's single command.
  fixtures-control ERA
                    Each fixture or hook turned off in turn: its plant must stop failing under the
                    era's first and last commands, and every other plant still fail.
  shard ERA N       One branch suite command (the N-th of ERA in ci.yml), run as CI runs it: green.
  ci --runs-file FILE | --sha SHA --runs ID:ATTEMPT... [--replaced ID:ATTEMPT] [--base-run ID] [--check-baseline]
                    R1, R5, R2 on CI, R7: reads the counted CI runs with `gh` (reads only), every
                    attempt of the measured commit accounted for, each attempt's own logs.
  head              Before landing: every push run of HEAD green with each suite job within the
                    budget, and origin/develop still the base.
  prepush           Before the push: a clean tree, no site-private text in the cycle's added lines,
                    and the deferral ledger.
  controls          Every check above that decides from data, run on planted data: each plant must be
                    refused for its reason, and the sound data accepted.

Footprint: one child pytest at a time (and its own children: loopback servers, sandboxed CLI
drives), each in a process group of its own, killed whole on every exit and checked gone with
`pgrep -g`; memory as one suite process. The tree modes export the index or the base commit
to a fresh directory under $TMPDIR and sync a venv there (about 20 s, from uv's cache), removed after.
Measured times: see PLAN.md § 6.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml

BASE = '5f6e98418232b4e35246d47d3703d7e24a6d06e3'
SLUG = 'suite-ci-time-budget'
CI = '.github/workflows/ci.yml'
SEED = 'issues/stalled-reconnect-test-timing.md'
MODERN = 'CLUSTER_MCP_TEST_ERA=modern '
BUDGET = 600
TIMEOUT_MINUTES = 20
MIN_RUNS = 3
BASE_RUN = 42210568801
REPO = 'PurdueRCAC/cluster-mcp'
HOOKS = {'path_shim', 'skip_probes', 'guard', 'main_context_holds_no_executor', 'pytest_collection_modifyitems'}
SAVED_ENV = dict(os.environ)
# Variables that would change what a child pytest selects or which environment it runs in.
DROPPED = ('VIRTUAL_ENV', 'CLUSTER_MCP_TEST_ERA', 'CLUSTER_MCP_TEST_EVERY_KIND', 'CLUSTER_MCP_ERA_LOG',
           'PYTEST_ADDOPTS', 'PYTEST_PLUGINS', 'CLUSTER_MCP_SKIP_PROBES', 'UV_PROJECT_ENVIRONMENT', 'UV_PROJECT', 'PYTHONPATH')
MARK = 'SUITE_GATE_CHILD'
NUMBER = {2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
          11: 'eleven', 12: 'twelve', 13: 'thirteen'}
STALE = [r'a run of three jobs', r'The two suite commands', r'`suite-legacy` and `suite-modern`',
         r'each era in a job of its own', r'neither job nears', r'all three jobs', r'needs both']
BANNED = [r'\$\{\{', r'\bsecrets\b', r'GITHUB_TOKEN', r'pull_request_target', r'workflow_run', r'continue-on-error',
          r'\|\|\s*true', r'id-token', r'upload-artifact', r'actions/cache', r'\bcurl\b', r'\bwget\b',
          r'\bgit\s+(push|tag)\b', r'\bgh\s+\w']


# --- Reading the lists -------------------------------------------------------------------------------

def git(*args: str, check: bool = True) -> str:
    return subprocess.run(['git', *args], check=check, capture_output=True, text=True).stdout


def staged(path: str) -> str:
    return git('show', f':{path}')


def at(rev: str, path: str) -> str:
    return git('show', f'{rev}:{path}')


def verify_cell(agents: str) -> list[str]:
    match = re.search(r'^\| verify \| `([^`]+)`', agents, re.M)
    return [part.strip() for part in match.group(1).split('&&')] if match else []


def recipe(agents: str) -> dict:
    match = re.search(r'^### Release recipe\n.*?^```yaml\n(.*?)^```', agents, re.M | re.S)
    return yaml.safe_load(match.group(1))['release'] if match else {}


def profile_row(agents: str, key: str) -> str:
    match = re.search(rf'^\| {re.escape(key)} \| (.*) \|$', agents, re.M)
    return match.group(1) if match else ''


def ci_bullet(agents: str) -> str:
    match = re.search(r'^- \*\*CI mirrors the gate\.\*\*.*?(?=^- \*\*)', agents, re.M | re.S)
    return match.group(0) if match else ''


def era_of(command: str) -> str:
    return 'modern' if command.startswith(MODERN) else 'legacy'


def suite_jobs(workflow: dict) -> list[tuple[str, dict, str]]:
    """(job id, job, its pytest command) for every job with a pytest step, in workflow order."""
    found = []
    for job_id, job in workflow.get('jobs', {}).items():
        runs = [step['run'] for step in job.get('steps', []) if 'pytest' in str(step.get('run', ''))]
        if runs:
            found.append((job_id, job, runs[-1]))
    return found


def is_suite(command: str) -> bool:
    return 'pytest' in command


# --- mirror (R6, R7's row) -------------------------------------------------------------------------

def mirror_violations(agents: str, ci_text: str, base_agents: str, base_ci_text: str) -> list[str]:
    found: list[str] = []
    ci, base_ci = yaml.safe_load(ci_text), yaml.safe_load(base_ci_text)
    for key in set(ci) | set(base_ci):
        if key != 'jobs' and ci.get(key) != base_ci.get(key):
            found.append(f'workflow: top-level {key!r} differs from the base')
    jobs = suite_jobs(ci)
    base_jobs = suite_jobs(base_ci)
    template = base_jobs[0][1]
    ids = [job_id for job_id, _, _ in jobs]
    for job_id, job, command in jobs:
        if set(job) != {'name', 'runs-on', 'timeout-minutes', 'steps'}:
            found.append(f'workflow: {job_id} has keys {sorted(job)}, not exactly the suite job keys')
        if job.get('runs-on') != 'ubuntu-24.04':
            found.append(f'workflow: {job_id} runs on {job.get("runs-on")!r}')
        if job.get('timeout-minutes') != TIMEOUT_MINUTES:
            found.append(f'workflow: {job_id} has timeout-minutes {job.get("timeout-minutes")!r}, not {TIMEOUT_MINUTES}')
        steps = job.get('steps', [])
        if steps[:-1] != template['steps'][:-1] or steps[-1:] != [{'run': command}]:
            found.append(f"workflow: {job_id}'s steps are not the base suite job's, its pytest step replaced")
    legacy_jobs = [c for _, _, c in jobs if era_of(c) == 'legacy']
    for index, (job_id, job, command) in enumerate(jobs):
        era, number = era_of(command), (index % max(len(legacy_jobs), 1)) + 1
        label = 'handshake' if era == 'legacy' else 'modern'
        want_name = f'suite ({label} era, {number} of {len(legacy_jobs)})'
        if job.get('name') != want_name or job_id != f'suite-{era}-{number}':
            found.append(f'workflow: {job_id} named {job.get("name")!r}, not suite-{era}-{number} {want_name!r}')
    others = [job_id for job_id in ci.get('jobs', {}) if job_id not in ids]
    if others != ['gate']:
        found.append(f'workflow: the jobs besides the suite jobs are {others}, not exactly gate')
    else:
        gate, base_gate = dict(ci['jobs']['gate']), dict(base_ci['jobs']['gate'])
        needs = gate.pop('needs', None)
        base_gate.pop('needs', None)
        if gate != base_gate:
            found.append('workflow: the gate job changed beyond its needs')
        if needs != ids:
            found.append(f'workflow: gate needs {needs}, not every suite job in order {ids}')
    for pattern in BANNED:
        code = '\n'.join(line for line in ci_text.splitlines() if not line.lstrip().startswith('#'))
        if re.search(pattern, code):
            found.append(f'workflow: banned text {pattern!r}')
    commands = [command for _, _, command in jobs]
    verify, base_verify = verify_cell(agents), verify_cell(base_agents)
    gate_list, base_gate_list = recipe(agents).get('gate', []), recipe(base_agents).get('gate', [])
    if [c for c in verify if is_suite(c)] != commands:
        found.append("the profile verify's suite commands are not the workflow's, verbatim and in order")
    if [c for c in gate_list if is_suite(c)] != commands:
        found.append("the release gate's suite commands are not the workflow's, verbatim and in order")
    if [c for c in verify if not is_suite(c)] != [c for c in base_verify if not is_suite(c)]:
        found.append("the profile verify's other commands changed")
    if [c for c in gate_list if not is_suite(c)] != [c for c in base_gate_list if not is_suite(c)]:
        found.append("the release gate's other commands changed")
    legacy = [c for c in commands if era_of(c) == 'legacy']
    modern = [c[len(MODERN):] for c in commands if era_of(c) == 'modern']
    if not legacy or legacy != modern or commands != legacy + [MODERN + c for c in modern]:
        found.append('the workflow does not run the same commands in each era, the handshake era first')
    per_era, total = len(legacy), len(jobs) + 1
    era_bullet = re.search(r'^- \*\*The protocol era\.\*\*.*?(?=^- )', agents, re.M | re.S)
    texts = {'the ci row': profile_row(agents, 'ci'), 'the CI bullet': ci_bullet(agents),
             'the verify row': profile_row(agents, 'verify').split('`:', 1)[-1],
             'the era bullet': era_bullet.group(0) if era_bullet else '',
             'the workflow header': '\n'.join(line for line in ci_text.splitlines() if line.startswith('#'))}
    for where, text in texts.items():
        flat = ' '.join(text.split())
        for phrase in STALE:
            if re.search(phrase, flat):
                found.append(f'{where} still says {phrase!r}')
        if not re.search(rf'\b({per_era}|{NUMBER.get(per_era, per_era)})\b', flat, re.I):
            found.append(f'{where} does not state the {per_era} suite commands per era')
    bullet = ' '.join(texts['the CI bullet'].split())
    header = ' '.join(texts['the workflow header'].split())
    for word in sorted({w for c in legacy for w in shlex.split(c)[4:] if re.fullmatch(r'tests/test_\w+\.py', w)}
                       | {w for c in legacy for i, w in enumerate(shlex.split(c)) if shlex.split(c)[i - 1] == '-k'}):
        for where, text in (('the CI bullet', bullet), ('the workflow header', header)):
            if word not in text and word.split('/')[-1] not in text:
                found.append(f'{where} does not name {word!r}, which a suite command selects by')
    ci_row = ' '.join(texts['the ci row'].split())
    if not re.search(rf'\b({total}|{NUMBER.get(total, total)}) jobs\b', ci_row):
        found.append(f'the ci row does not state the run\'s {total} jobs')
    for job_id in ids:
        if job_id not in ci_row and not range_names(ci_row, job_id):
            found.append(f'the ci row does not name {job_id}')
    budget = ' '.join(profile_row(agents, 'ci budget').split())
    for needed in ('10 minutes', 'gh run view --json jobs', 'ubuntu-24.04', 'timeout-minutes', 'Baseline'):
        if needed not in budget:
            found.append(f'the ci budget row does not state {needed!r}')
    return found


def range_names(text: str, job_id: str) -> bool:
    """True when `text` names `job_id` inside a range such as `suite-legacy-1` to `suite-legacy-4`."""
    match = re.fullmatch(r'(.*-)(\d+)', job_id)
    if not match:
        return False
    for low, high in re.findall(rf'`{re.escape(match.group(1))}(\d+)` to `{re.escape(match.group(1))}(\d+)`', text):
        if int(low) <= int(match.group(2)) <= int(high):
            return True
    return False


def same_commit_violations() -> list[str]:
    """Every commit since the base (and the staged change) that changes the verify or gate list
    changes the workflow, and every one that changes the workflow changes AGENTS.md."""
    found = []
    revs = git('rev-list', '--reverse', f'{BASE}..HEAD').split()
    steps = [(rev, f'{rev}^', rev) for rev in revs] + [('the staged change', 'HEAD', None)]
    for label, before, after in steps:
        if after is None:
            names = git('diff', '--cached', '--name-only').split()
            new_agents = staged('AGENTS.md')
        else:
            names = git('diff', '--name-only', f'{after}^', after).split()
            new_agents = at(after, 'AGENTS.md')
        old_agents = at(before, 'AGENTS.md')
        lists_changed = (verify_cell(old_agents) != verify_cell(new_agents)
                         or recipe(old_agents).get('gate') != recipe(new_agents).get('gate'))
        if lists_changed and CI not in names:
            found.append(f'{label[:12]}: changes the verify or gate list but not {CI}')
        if CI in names and 'AGENTS.md' not in names:
            found.append(f'{label[:12]}: changes {CI} but not AGENTS.md')
    return found


def mode_mirror() -> list[str]:
    return (mirror_violations(staged('AGENTS.md'), staged(CI), at(BASE, 'AGENTS.md'), at(BASE, CI))
            + same_commit_violations())


# --- untouched (R3) --------------------------------------------------------------------------------

AGENTS_REGIONS = [r'^### Profile\n.*?(?=^### Release recipe)', r'^```yaml\n.*?^```',
                  r'^- \*\*CI mirrors the gate\.\*\*.*?(?=^- \*\*)', r'^- \*\*The protocol era\.\*\*.*?(?=^- )']


def outside_regions(agents: str) -> str:
    for pattern in AGENTS_REGIONS:
        agents = re.sub(pattern, '', agents, count=1, flags=re.M | re.S)
    return agents


# The one test module this design adds, and what it may import.
NEW_MODULE = 'tests/test_suite_parts.py'
NEW_MODULE_IMPORTS = {'__future__', 're', 'shlex', 'pathlib', 'pytest'}
# Files pytest reads as configuration or collects, wherever they sit.
PYTEST_FILES = re.compile(r'(^|/)(conftest\.py|test_[^/]*\.py|[^/]*_test\.py|__init__\.py|pytest\.ini|tox\.ini|setup\.cfg|pyproject\.toml)$')


def module_violations(source: str) -> list[str]:
    """The added module may import only the standard helpers and pytest, and at import time may only
    bind names: nothing it runs on import can reach another module's helpers or constants."""
    found = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            names = [alias.name.split('.')[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or '').split('.')[0]]
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            continue
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not all(isinstance(t, ast.Name) for t in targets):
                found.append(f'{NEW_MODULE}: line {node.lineno} assigns to something other than a name')
            calls = [ast.unparse(c.func) for c in ast.walk(node) if isinstance(c, ast.Call)]
            if any(name in ('setattr', 'delattr', 'exec', 'eval', '__import__', 'globals', 'vars') or 'import' in name
                   for name in calls):
                found.append(f'{NEW_MODULE}: line {node.lineno} calls {calls}')
            continue
        else:
            found.append(f'{NEW_MODULE}: line {node.lineno} runs a {type(node).__name__} at import')
            continue
        bad = [n for n in names if n not in NEW_MODULE_IMPORTS]
        if bad:
            found.append(f'{NEW_MODULE}: imports {bad}')
    return found


def profile_rows(agents: str) -> dict[str, str]:
    match = re.search(r'^### Profile\n(.*?)(?=^### )', agents, re.M | re.S)
    return dict(re.findall(r'^\| ([^|]+?) \| (.*) \|$', match.group(1), re.M)) if match else {}


def untouched_violations(name_status: list[tuple[str, str]], agents: str, base_agents: str,
                         new_module: str | None) -> list[str]:
    found = []
    for status, name in name_status:
        if name == NEW_MODULE and status == 'A':
            continue
        if PYTEST_FILES.search(name):
            found.append(f'{status} {name}: a file pytest reads or collects')
            continue
        if name.startswith(f'spec/{SLUG}/') or name in (CI, 'AGENTS.md', 'ROADMAP.md'):
            continue
        if name.startswith('issues/') and name.endswith('.md'):
            continue
        found.append(f'{status} {name}: outside what this design may change')
    if new_module is not None:
        found += module_violations(new_module)
    rows, base_rows = profile_rows(agents), profile_rows(base_agents)
    for key in sorted(set(rows) | set(base_rows)):
        if key in ('verify', 'ci', 'ci budget'):
            continue
        if rows.get(key) != base_rows.get(key):
            found.append(f'the profile row {key!r} changed')
    landing_rule = lambda text: text[text.find('Before a `squash-local` landing'):] if text else ''
    if landing_rule(rows.get('ci', '')) != landing_rule(base_rows.get('ci', '')) or 'Before a' not in rows.get('ci', ''):
        found.append("the ci row's landing rule changed")
    new_recipe, base_recipe = dict(recipe(agents)), dict(recipe(base_agents))
    new_recipe.pop('gate', None)
    base_recipe.pop('gate', None)
    if new_recipe != base_recipe:
        found.append('the release recipe changed beyond its gate list')
    if outside_regions(agents) != outside_regions(base_agents):
        found.append('AGENTS.md changes outside the profile, the recipe, the CI bullet and the era bullet')
    return found


def mode_untouched() -> list[str]:
    lines = git('diff', '--cached', '--name-status', '--no-renames', BASE).splitlines()
    pairs = [tuple(line.split('\t', 1)) for line in lines if line]
    new_module = staged(NEW_MODULE) if any(name == NEW_MODULE for _, name in pairs) else None
    return untouched_violations(pairs, staged('AGENTS.md'), at(BASE, 'AGENTS.md'), new_module)


# --- trees and children ----------------------------------------------------------------------------

def child_env() -> dict[str, str]:
    env = {key: value for key, value in SAVED_ENV.items() if key not in DROPPED}
    env['UV_PYTHON'] = '3.14'
    env[MARK] = '1'
    return env


def run(command: str, cwd: Path, timeout: float) -> tuple[int, str, float]:
    """Run `command` in bash, in a process group of its own, and kill the whole group after."""
    start = time.monotonic()
    child = subprocess.Popen(['bash', '-c', command], cwd=cwd, env=child_env(), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = child.communicate(timeout=timeout)
        code = child.returncode
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        out, _ = child.communicate()
        code = -1
        out += f'\n[suite-gate] timed out after {timeout:.0f} s'
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    for _ in range(20):
        left = subprocess.run(['pgrep', '-g', str(child.pid)], capture_output=True, text=True).stdout.split()
        if not left:
            break
        time.sleep(0.1)
    if left:
        raise SystemExit(f'suite-gate: processes outlived their group {child.pid}: {left}')
    return code, out, time.monotonic() - start


@contextmanager
def tree(rev: str | None) -> Iterator[Path]:
    """A synced copy of the index (rev None) or of a commit, removed after."""
    root = Path(tempfile.mkdtemp(prefix='suite-gate-'))
    try:
        if rev is None:
            subprocess.run(['git', 'checkout-index', '-a', f'--prefix={root}/'], check=True)
        else:
            archive = subprocess.run(['git', 'archive', rev], check=True, capture_output=True).stdout
            subprocess.run(['tar', '-x', '-C', str(root)], input=archive, check=True)
        code, out, _ = run('uv sync --locked -q', root, 600)
        if code != 0:
            raise SystemExit(f'suite-gate: uv sync failed in {root}:\n{out[-2000:]}')
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def commands_of(root: Path, era: str) -> list[str]:
    return [c for _, _, c in suite_jobs(yaml.safe_load((root / CI).read_text())) if era_of(c) == era]


def collected(root: Path, command: str) -> tuple[list[str], str]:
    code, out, _ = run(f'{command} --collect-only -p no:cacheprovider', root, 600)
    ids = [line for line in out.splitlines() if re.match(r'tests/[^ ]+\.py::', line)]
    summary = re.search(r'^(\d+)(?:/(\d+))? tests? collected', out, re.M)
    if code != 0 or not summary or int(summary.group(1)) != len(ids):
        raise SystemExit(f'suite-gate: could not collect {command!r} (exit {code}):\n{out[-3000:]}')
    return ids, summary.group(0)


# --- partition (R2) --------------------------------------------------------------------------------

def partition_violations(base_ids: list[str], jobs: dict[str, list[str]], new_modules: set[str]) -> list[str]:
    found = []
    seen: dict[str, str] = {}
    for label, ids in jobs.items():
        if len(set(ids)) != len(ids):
            found.append(f'{label}: collects an id twice')
        for node in ids:
            if node in seen:
                found.append(f'{node} runs in both {seen[node]} and {label}')
            seen.setdefault(node, label)
    missing = sorted(set(base_ids) - set(seen))
    if missing:
        found.append(f'{len(missing)} base ids run in no job, among them {missing[:5]}')
    extra = sorted(node for node in set(seen) - set(base_ids) if node.split('::')[0] not in new_modules)
    if extra:
        found.append(f'{len(extra)} ids are new in modules the base has, among them {extra[:5]}')
    return found


def mode_partition(era: str) -> list[str]:
    with tree(BASE) as base:
        base_commands = commands_of(base, era)
        if len(base_commands) != 1:
            return [f'the base has {len(base_commands)} {era} suite commands, not one']
        base_ids, base_summary = collected(base, base_commands[0])
        base_modules = {f'tests/{p.name}' for p in (base / 'tests').glob('test_*.py')}
    print(f'base {era}: {base_summary}  ({base_commands[0]})')
    jobs = {}
    with tree(None) as branch:
        for index, command in enumerate(commands_of(branch, era), 1):
            jobs[f'{era} {index}'], summary = collected(branch, command)
            print(f'{era} {index}: {summary}  ({command})')
        modules = {f'tests/{p.name}' for p in (branch / 'tests').glob('test_*.py')}
    return partition_violations(base_ids, jobs, modules - base_modules)


# --- fixtures (R4) ---------------------------------------------------------------------------------

REASONS = {'guard': 'unit guard: the test tried to launch a process',
           'context': 'an executor leaked into the main context',
           'shim': 'refused by the test PATH shim',
           'probes': 'planted: the probe override is set'}
UNMARKED = 'every test must carry @pytest.mark.unit or @pytest.mark.integration; unmarked:'


def plants(tag: str) -> str:
    return f'''

@pytest.mark.unit
def test_planted_{tag}_guard():
    import subprocess
    try:
        subprocess.run(['true'])
    except OSError:
        pass


@pytest.mark.unit
def test_planted_{tag}_context():
    import cluster_mcp.core.context
    cluster_mcp.core.context.executor_var.set(object())


@pytest.mark.integration
def test_planted_{tag}_shim():
    import subprocess
    ran = subprocess.run(['ssh', '-V'], capture_output=True, text=True)
    assert 'refused by the test PATH shim' not in ran.stderr, 'planted: ' + ran.stderr


@pytest.mark.unit
def test_planted_{tag}_probes():
    import os
    assert os.environ.get('CLUSTER_MCP_SKIP_PROBES') != '1', 'planted: the probe override is set'


@pytest.mark.unit
def test_planted_{tag}_zend():
    pytest.exit('planted: the plants have run')

'''


def unmarked(tag: str) -> str:
    # A marked fifth plant ends the session if the hook lets the unmarked one through.
    return (f'\n\ndef test_planted_{tag}_unmarked():\n    pass\n\n\n@pytest.mark.unit\n'
            f'def test_planted_{tag}_zend():\n    pytest.exit("planted: the plants have run")\n\n')


def hook_names(conftest: str) -> set[str]:
    names = set()
    for node in ast.parse(conftest).body:
        if isinstance(node, ast.Assign) and 'fixture' in ast.unparse(node.value):
            names.update(ast.unparse(t) for t in node.targets)
            continue
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if re.match(r'pytest_(collection|collect|itemcollected|deselected|ignore_collect|pycollect|generate_tests)', node.name):
            names.add(node.name)
        for decorator in node.decorator_list:
            text = ast.unparse(decorator)
            if 'fixture' in text and (re.search(r'autouse=(?!False|0\b|None)', text) or re.search(r"scope=['\"](session|package)", text)):
                names.add(node.name)
    return names


def plant_into(root: Path, command: str, text: str, tag: str) -> tuple[Path, str | None]:
    """Write `text` where `command` collects it first: before the first test of its first module, or
    as a module of its own that sorts first."""
    files = [w for w in shlex.split(command) if re.fullmatch(r'tests/test_\w+\.py', w)]
    if not files:
        target = root / 'tests' / f'test_aaa_planted_{tag}.py'
        target.write_text('import pytest\n' + text)
        return target, None
    target = root / files[0]
    source = target.read_text()
    first = min((n.decorator_list[0].lineno if n.decorator_list else n.lineno)
                for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name.startswith('test'))
    lines = source.splitlines(keepends=True)
    target.write_text(''.join(lines[:first - 1]) + text + ''.join(lines[first - 1:]))
    return target, source


def plant_verdicts(root: Path, command: str) -> dict[str, str]:
    """For each plant, the reason it failed for under `command` (or why it did not fail as planted)."""
    verdicts: dict[str, str] = {}
    for tag in ('silent', 'plain'):
        target, backup = plant_into(root, command, plants(tag), tag)
        try:
            ids, _ = collected(root, command)
            names = [f'test_planted_{tag}_{p}' for p in REASONS]
            if [i.split('::', 1)[1] for i in ids[:5]] != names + [f'test_planted_{tag}_zend']:
                continue
            junit = root / 'planted.xml'
            # The fifth plant ends the session, so no row of the suite runs after the plants.
            code, out, _ = run(f'{command} -p no:cacheprovider --junitxml={junit}', root, 600)
            if 'planted: the plants have run' not in out:
                verdicts['end'] = f'the session did not end after the plants (exit {code})'
            failing: dict[str, str] = {}
            cases = ET.parse(junit).getroot().iter('testcase') if junit.exists() else []
            for case in cases:
                for bad in list(case.iter('failure')) + list(case.iter('error')):
                    failing[case.get('name')] = failing.get(case.get('name'), '') + (bad.get('message') or '') + (bad.text or '')
            for plant, name in zip(REASONS, names):
                text = failing.pop(name, None)
                verdicts[plant] = ('fails: ' + REASONS[plant] if text and REASONS[plant] in text
                                   else f'did not fail as planted (exit {code}): {(text or "passed")[:200]}')
            if failing:
                verdicts['others'] = f'other tests failed: {sorted(failing)[:3]}'
        finally:
            restore(target, backup)
        target, backup = plant_into(root, command, unmarked(tag), tag)
        try:
            code, out, _ = run(f'{command} -p no:cacheprovider', root, 600)
            named = UNMARKED in out and f'test_planted_{tag}_unmarked' in out
            verdicts['collection hook'] = ('fails: ' + UNMARKED if code == 4 and named
                                           else f'did not fail as planted (exit {code}): {out[-300:]}')
        finally:
            restore(target, backup)
        return verdicts
    return {'plants': f'no plant name is collected first by {command!r}'}


def restore(target: Path, backup: str | None) -> None:
    if backup is None:
        target.unlink()
    else:
        target.write_text(backup)


def fixture_violations(base: dict[str, str], branch: dict[str, dict[str, str]]) -> list[str]:
    found = []
    expected = {**{p: 'fails: ' + r for p, r in REASONS.items()}, 'collection hook': 'fails: ' + UNMARKED}
    if base != expected:
        found.append(f'the plants do not fail as expected under the base: {base}')
    for label, verdicts in branch.items():
        if verdicts != base:
            found.append(f'{label}: {verdicts}, not the base verdicts')
    return found


def mode_fixtures(era: str) -> list[str]:
    found = []
    with tree(BASE) as base:
        if hook_names((base / 'tests/conftest.py').read_text()) != HOOKS:
            found.append(f'the base conftest holds {sorted(hook_names((base / "tests/conftest.py").read_text()))}')
        base_verdicts = plant_verdicts(base, commands_of(base, era)[0])
    print(f'base {era}: {base_verdicts}')
    branch_verdicts = {}
    with tree(None) as branch:
        conftest = (branch / 'tests/conftest.py').read_text()
        if hook_names(conftest) != HOOKS:
            found.append(f'the branch conftest holds {sorted(hook_names(conftest))}, not {sorted(HOOKS)}')
        if sorted(p.relative_to(branch) for p in branch.rglob('conftest.py') if '.venv' not in p.parts) != [Path('tests/conftest.py')]:
            found.append('the branch has a conftest.py besides tests/conftest.py')
        for index, command in enumerate(commands_of(branch, era), 1):
            branch_verdicts[f'{era} {index}'] = plant_verdicts(branch, command)
            print(f'{era} {index}: {branch_verdicts[f"{era} {index}"]}')
    return found + fixture_violations(base_verdicts, branch_verdicts)


# Each fixture or hook, turned off in the conftest, and the plant that must then stop failing.
DISABLED = {
    'guard': ('@pytest.fixture(autouse=True)\ndef guard(', '@pytest.fixture\ndef guard('),
    'context': ('@pytest.fixture(autouse=True)\ndef main_context_holds_no_executor(',
                '@pytest.fixture\ndef main_context_holds_no_executor('),
    'shim': ("@pytest.fixture(scope='session', autouse=True)\ndef path_shim(", "@pytest.fixture(scope='session')\ndef path_shim("),
    'probes': ("@pytest.fixture(scope='session', autouse=True)\ndef skip_probes(",
               "@pytest.fixture(scope='session')\ndef skip_probes("),
    'collection hook': ('def pytest_collection_modifyitems(', 'def disabled_collection_modifyitems('),
}


def mode_fixtures_control(era: str) -> list[str]:
    """With each fixture or hook turned off in turn, under the era's first and last commands (one
    planting into a named module, one into a module of its own), its plant must stop failing while
    every other plant still fails: the fixtures mode can go red for each, along both plant paths."""
    found = []
    with tree(None) as branch:
        conftest = branch / 'tests/conftest.py'
        original = conftest.read_text()
        commands = commands_of(branch, era)
        try:
            for plant, (old, new) in DISABLED.items():
                if original.count(old) != 1:
                    found.append(f'control {plant}: the conftest no longer reads {old!r}')
                    continue
                conftest.write_text(original.replace(old, new))
                for command in (commands[0], commands[-1]):
                    verdicts = plant_verdicts(branch, command)
                    ok = (verdicts.get(plant, '').startswith('did not fail')
                          and all(v.startswith('fails: ') for k, v in verdicts.items() if k != plant))
                    print(f'{"ok " if ok else "BAD"} {plant} off under {command}: {verdicts.get(plant)}')
                    if not ok:
                        found.append(f'control {plant} off under {command}: {verdicts}')
        finally:
            conftest.write_text(original)
    return found


# --- shard -----------------------------------------------------------------------------------------

def mode_shard(era: str, number: int) -> list[str]:
    with tree(None) as branch:
        commands = commands_of(branch, era)
        command = commands[number - 1]
        junit = branch / 'shard.xml'
        code, out, secs = run(f'{command} -p no:cacheprovider --junitxml={junit}', branch, 1500)
        summary = out.strip().splitlines()[-1] if out.strip() else ''
        print(f'{era} {number} of {len(commands)}: {summary} ({secs:.0f} s wall, {command})')
        cases = list(ET.parse(junit).getroot().iter('testcase')) if junit.exists() else []
        bad = [c.get('name') for c in cases if c.find('failure') is not None or c.find('error') is not None]
        bad = bad if cases else ['no report']
        # A part starts cold: its first rows pay the imports and the first server start.
        print('first rows: ' + ', '.join(f'{c.get("name")} {float(c.get("time", 0)):.2f} s' for c in cases[:3]))
    if code != 0 or bad:
        return [f'{era} {number}: exit {code}, failing {bad[:5]}:\n{out[-3000:]}']
    return []


# --- ci (R1, R5, R2 on CI, R7) -----------------------------------------------------------------------

def gh(*args: str) -> str:
    return subprocess.run(['gh', '-R', REPO, *args], check=True, capture_output=True, text=True).stdout


def gh_json(*args: str) -> dict | list:
    return json.loads(gh(*args))


def when(stamp: str):
    from datetime import datetime
    return datetime.fromisoformat(stamp.replace('Z', '+00:00'))


def seconds(job: dict) -> float:
    return (when(job['completedAt']) - when(job['startedAt'])).total_seconds()


def counts(log: str) -> dict[str, int]:
    """The counts of pytest's last summary line in a job log: {'passed': 4996, 'deselected': 12, ...}."""
    found = re.findall(r'((?:\d+ \w+, )*\d+ \w+) in [\d.]+s(?: \(\d+:\d\d:\d\d\))?\s*$', log, re.M)
    if not found:
        return {}
    return {word.rstrip('s') if word in ('warnings', 'errors') else word: int(n)
            for n, word in re.findall(r'(\d+) (\w+)', found[-1])}


def failed_rows(log: str) -> list[str]:
    """The node ids pytest's short summary names as FAILED or ERROR in a job log."""
    return re.findall(r'\b(?:FAILED|ERROR) (tests/\S+?\.py::\S+)', log)


def attempt_key(spec: str) -> tuple[int, int]:
    run_id, attempt = spec.split(':')
    return int(run_id), int(attempt)


def ci_violations(runs: list[dict], expected_names: dict[str, str], sha: str, base_passed: dict[str, int],
                  added: dict[str, int], replaced: list[dict], listed: set[tuple[int, int]]) -> tuple[list[str], dict[str, float]]:
    """`runs`: one dict per counted attempt (key, startedAt, headSha, event, status, conclusion, and
    jobs, each with name, conclusion, startedAt, seconds and, for suite jobs, counts). `replaced`: the
    same for a replaced attempt, with each job's failed rows. `listed`: every attempt of every push run
    of the measured commit that GitHub lists. Returns the violations and each suite job's worst wall
    time."""
    found = []
    keys = [r['key'] for r in runs]
    if len(set(keys)) != len(keys):
        found.append(f'an attempt is counted twice: {keys}')
    if len(set(keys)) < MIN_RUNS:
        found.append(f'{len(set(keys))} distinct counted runs, not at least {MIN_RUNS}')
    if len(replaced) > 1:
        found.append(f'{len(replaced)} runs replaced, not at most one')
    if set(keys) & {r['key'] for r in replaced}:
        found.append('an attempt is both counted and replaced')
    unaccounted = sorted(listed - set(keys) - {r['key'] for r in replaced})
    if unaccounted:
        found.append(f'attempts of the measured commit neither counted nor replaced: {unaccounted}')
    stray = sorted(set(keys) - listed)
    if stray:
        found.append(f'counted attempts GitHub does not list for the measured commit: {stray}')
    for r in replaced:
        red = [j for j in r['jobs'] if j['conclusion'] not in ('success', 'skipped')]
        rows = [row for j in red for row in j.get('failed', [])]
        if len(red) != 1 or not red[0]['name'].startswith('suite') or len(rows) != 1:
            found.append(f'replaced {r["key"]}: red jobs {[j["name"] for j in red]}, failed rows {rows}: '
                         f'R5 replaces a run only for one row of one suite job')
    worst: dict[str, float] = {}
    for r in runs:
        label = f'{r["key"][0]}:{r["key"][1]}'
        if not r['headSha'].startswith(sha):
            found.append(f'{label}: runs {r["headSha"][:12]}, not {sha}')
        if r['event'] != 'push' or r['status'] != 'completed' or r['conclusion'] != 'success':
            found.append(f'{label}: {r["event"]} {r["status"]} {r["conclusion"]}, not a green push run')
        names = [j['name'] for j in r['jobs']]
        if sorted(names) != sorted(list(expected_names.values()) + ['gate']):
            found.append(f'{label}: jobs {sorted(names)}, not the workflow\'s')
        passed = {'legacy': 0, 'modern': 0}
        for job in r['jobs']:
            if job['conclusion'] != 'success':
                found.append(f'{label}: {job["name"]} is {job["conclusion"]}')
            if when(job['startedAt']) < when(r['startedAt']):
                found.append(f'{label}: {job["name"]} started before the attempt: not a full re-run')
            job_id = next((k for k, v in expected_names.items() if v == job['name']), None)
            if job_id is None:
                continue
            worst[job_id] = max(worst.get(job_id, 0), job['seconds'])
            if job['seconds'] > BUDGET:
                found.append(f'{label}: {job_id} took {job["seconds"]:.0f} s, over {BUDGET} s')
            c = job['counts']
            if not c.get('passed') or set(c) - {'passed', 'deselected', 'warning'}:
                found.append(f'{label}: {job_id} ended {c}, not passed (and deselected) only')
            passed['modern' if 'modern' in job_id else 'legacy'] += c.get('passed', 0)
        for era in passed:
            if passed[era] != base_passed[era] + added[era]:
                found.append(f'{label}: the {era} jobs passed {passed[era]}, not the base\'s {base_passed[era]} '
                             f'and the {added[era]} new')
    return found, worst


def baseline_text(worst: dict[str, float], sha: str, keys: list[tuple[int, int]]) -> str:
    parts = ', '.join(f'`{job_id}` {int(s) // 60}:{int(s) % 60:02d}' for job_id, s in worst.items())
    runs = ', '.join(f'{run_id}#{attempt}' for run_id, attempt in keys)
    return (f'Baseline (worst of each job over the {len(keys)} runs counted at landing, commit `{sha[:7]}`, '
            f'runs {runs}): {parts}')


def read_runs_file(args: argparse.Namespace) -> None:
    """Fill --sha, --runs and --replaced from a file of `sha <commit>`, `run <id>:<attempt>` and
    `replaced <id>:<attempt>` lines (the foreman's run ids, committed beside the gate)."""
    for line in Path(args.runs_file).read_text().splitlines():
        words = line.split('#', 1)[0].split()
        if not words:
            continue
        key, value = words
        if key == 'sha':
            args.sha = value
        elif key == 'run':
            args.runs.append(value)
        elif key == 'replaced':
            args.replaced.append(value)
        else:
            raise SystemExit(f'suite-gate: {args.runs_file}: an unknown line {line!r}')


def read_attempt(key: tuple[int, int], suite_logs: bool) -> dict:
    run_id, attempt = map(str, key)
    data = gh_json('run', 'view', run_id, '--attempt', attempt,
                   '--json', 'jobs,headSha,event,status,conclusion,startedAt')
    jobs = []
    for job in data['jobs']:
        entry = {'name': job['name'], 'conclusion': job['conclusion'], 'startedAt': job['startedAt'],
                 'seconds': seconds(job), 'counts': {}, 'failed': []}
        if suite_logs and job['name'].startswith('suite'):
            log = gh('run', 'view', run_id, '--attempt', attempt, '--job', str(job['databaseId']), '--log')
            entry['counts'], entry['failed'] = counts(log), failed_rows(log)
        jobs.append(entry)
    return {'key': key, **{k: data[k] for k in ('headSha', 'event', 'status', 'conclusion', 'startedAt')},
            'jobs': jobs}


def listed_attempts(sha: str) -> set[tuple[int, int]]:
    runs = gh_json('run', 'list', '--workflow', 'ci.yml', '--commit', sha, '-e', 'push', '--limit', '50',
                   '--json', 'databaseId,attempt')
    return {(r['databaseId'], n) for r in runs for n in range(1, r['attempt'] + 1)}


def mode_ci(args: argparse.Namespace) -> list[str]:
    if args.runs_file:
        read_runs_file(args)
    if not args.sha or not args.runs:
        return ['ci: no measured commit or runs given (--runs-file, or --sha and --runs)']
    sha = git('rev-parse', args.sha).strip()
    workflow = yaml.safe_load(at(sha, CI))
    expected_names = {job_id: job['name'] for job_id, job, _ in suite_jobs(workflow)}
    base = read_attempt((args.base_run, int(gh_json('run', 'view', str(args.base_run), '--json', 'attempt')['attempt'])), True)
    if not base['headSha'].startswith(BASE) or base['conclusion'] != 'success':
        return [f'the base run {args.base_run} ran {base["headSha"][:12]} ({base["conclusion"]}), not a green {BASE[:12]}']
    base_passed = {'legacy': 0, 'modern': 0}
    for job in base['jobs']:
        if job['name'].startswith('suite'):
            base_passed['modern' if 'modern' in job['name'] else 'legacy'] += job['counts'].get('passed', 0)
    with tree(sha) as branch:
        base_modules = set(git('ls-tree', '--name-only', BASE, 'tests/').split())
        new = sorted(f'tests/{p.name}' for p in (branch / 'tests').glob('test_*.py') if f'tests/{p.name}' not in base_modules)
        added = {}
        for era, prefix in (('legacy', ''), ('modern', MODERN)):
            added[era] = len(collected(branch, f'{prefix}uv run pytest -q {" ".join(new)}')[0]) if new else 0
    keys = [attempt_key(spec) for spec in args.runs]
    runs = [read_attempt(key, True) for key in dict.fromkeys(keys)]
    runs = [next(r for r in runs if r['key'] == key) for key in keys]
    replaced = [read_attempt(attempt_key(spec), True) for spec in args.replaced]
    found, worst = ci_violations(runs, expected_names, sha, base_passed, added, replaced, listed_attempts(sha))
    seed_added = '\n'.join(line[1:] for line in git('diff', '--cached', '-U0', sha, '--', SEED).splitlines()
                           if line.startswith('+') and not line.startswith('+++'))
    for r in replaced:
        red = [j for j in r['jobs'] if j['conclusion'] not in ('success', 'skipped')]
        era = 'modern' if red and 'modern' in red[0]['name'] else 'handshake'
        rows = [row for j in red for row in j['failed']]
        needed = [str(r['key'][0]), era] + [row.split('::', 1)[1].split('[')[0] for row in rows[:1]]
        if not re.search(r'20\d\d-\d\d-\d\d', seed_added) or any(n not in seed_added for n in needed):
            found.append(f'the replaced run {r["key"]} has no dated sighting in {SEED} naming {needed}')
    for job_id, s in worst.items():
        print(f'{job_id}: worst {s:.0f} s ({s / 60:.1f} min) of {BUDGET} s')
    worst = {job_id: worst[job_id] for job_id in expected_names if job_id in worst}
    text = baseline_text(worst, sha, sorted(set(keys)))
    print(text)
    if args.check_baseline:
        found += baseline_violations(sha, text, bool(args.replaced))
    return found


def baseline_violations(sha: str, text: str, replaced: bool) -> list[str]:
    """The staged tree is the measured commit plus the baseline in the ci budget row, the runs file,
    TECH state and (with a replaced run) the seed's sighting: nothing a suite job runs differs."""
    found = []
    row = ' '.join(profile_row(staged('AGENTS.md'), 'ci budget').split())
    if text not in row:
        found.append(f'the ci budget row does not carry: {text}')
    allowed = {'AGENTS.md', f'spec/{SLUG}/ci-runs.txt', f'spec/{SLUG}/TECH.md'} | ({SEED} if replaced else set())
    changed = git('diff', '--cached', '--name-only', sha).split()
    if set(changed) - allowed:
        found.append(f'the tree after the measured commit changes {sorted(set(changed) - allowed)}')
    import difflib
    old, new = at(sha, 'AGENTS.md').splitlines(), staged('AGENTS.md').splitlines()
    edits = [line for line in difflib.unified_diff(old, new, lineterm='', n=0)
             if line[:1] in '+-' and not line.startswith(('+++', '---'))]
    if sorted(line[0] for line in edits) != ['+', '-'] or not all(line[1:].startswith('| ci budget |') for line in edits):
        found.append(f'AGENTS.md changes beyond the ci budget row after the measured commit: {edits[:4]}')
    return found


def mode_head(args: argparse.Namespace) -> list[str]:
    """Before landing: every push run of HEAD is green with every suite job within the budget, and the
    base is still origin/develop (else the landed tree is neither the measured one nor HEAD)."""
    found = []
    sha = git('rev-parse', 'HEAD').strip()
    if git('rev-parse', 'origin/develop').strip() != BASE:
        found.append('origin/develop has moved past the base: the landed tree would differ from the measured one')
    listed = listed_attempts(sha)
    if not listed:
        found.append(f'no push run of {sha[:12]} is listed')
    for key in sorted(listed):
        r = read_attempt(key, False)
        if r['status'] != 'completed' or r['conclusion'] != 'success':
            found.append(f'{key}: {r["status"]} {r["conclusion"]}')
        for job in r['jobs']:
            if job['name'].startswith('suite') and job['seconds'] > BUDGET:
                found.append(f'{key}: {job["name"]} took {job["seconds"]:.0f} s, over {BUDGET} s')
            if job['conclusion'] != 'success':
                found.append(f'{key}: {job["name"]} is {job["conclusion"]}')
        print(f'{key}: ' + ', '.join(f'{j["name"]} {j["seconds"]:.0f} s' for j in r['jobs']))
    return found


# --- prepush ---------------------------------------------------------------------------------------

PRIVATE = [(r'\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'an IP address'),
           (r'\b[\w-]+\.purdue\.edu\b', 'a site hostname'), (r'\.secur' r'ity/', 'a security-lane path'),
           (r'\b(GHSA-\w{4}-|CVE-\d{4}-\d|PYSEC-\d{4}-)', 'an advisory id'),
           (r'(?<![\w.+\\-])(?!git@)[\w.+-]+@[\w-]+(\.[\w-]+)+', 'an email address'), (r'/(Users|home)/(?!runner/)\w', 'a home path'),
           (r'/(private/tmp|var/folders)/', 'a host temporary path'), (r'~/K' r'B\b', "the operator's KB path"),
           (r'/scratch/\w', 'a cluster scratch path')]
SPEC_ID = r'(?<![A-Za-z0-9])([RPQF]\d{1,2}|F-[A-Z])(?![A-Za-z0-9])'
PHRASES = ('do not fix here', 'known limitation', 'left as a follow-up', 'follow-up', 'deferred', 'deferral',
           'not fixed')


def added_lines() -> list[tuple[str, str]]:
    out = git('diff', '--cached', '-U0', '--no-color', BASE)
    current, lines = '', []
    for line in out.splitlines():
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


def ledger_violations(tech: str, bodies: str, roadmap: str, exists) -> list[str]:
    found = []
    phases = tech[tech.index('## Phase P1'):tech.index('## How `code-build` drives this')]
    for source, text in (('TECH.md', phases), ('commit bodies', bodies)):
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
    bodies = git('log', f'{BASE}..HEAD', '--format=%B')
    exists = lambda p: bool(git('ls-files', '--', p).strip())
    found += ledger_violations(staged(f'spec/{SLUG}/TECH.md'), bodies, staged('ROADMAP.md'), exists)
    plan = staged(f'spec/{SLUG}/PLAN.md')
    found += [v.replace('TECH.md', 'PLAN.md') for v in
              ledger_violations('## Phase P1\n' + plan + '\n## How `code-build` drives this\n', '', staged('ROADMAP.md'), exists)]
    return found


# --- controls --------------------------------------------------------------------------------------

def mode_controls() -> list[str]:
    found: list[str] = []

    def expect(label: str, violations: list[str], why: str | None) -> None:
        hit = any(why in v for v in violations) if why else violations == []
        print(f'{"ok " if hit else "BAD"} {label}: {violations[:2] if why else "sound data accepted"}')
        if not hit:
            found.append(f'control {label}: {violations}, wanted {why or "none"}')

    agents, ci_text = staged('AGENTS.md'), staged(CI)
    base_agents, base_ci = at(BASE, 'AGENTS.md'), at(BASE, CI)
    expect('mirror sound', mirror_violations(agents, ci_text, base_agents, base_ci), None)
    commands = [c for _, _, c in suite_jobs(yaml.safe_load(ci_text))]
    first = commands[0]
    expect('mirror ci-differs', mirror_violations(agents, ci_text.replace(f'- run: {first}\n', f'- run: {first} -x\n', 1),
                                                  base_agents, base_ci), 'not the workflow')
    expect('mirror timeout', mirror_violations(agents, ci_text.replace('timeout-minutes: 20', 'timeout-minutes: 25', 1),
                                               base_agents, base_ci), 'timeout-minutes')
    expect('mirror env', mirror_violations(agents, ci_text.replace('    timeout-minutes: 20\n',
                                                                   '    timeout-minutes: 20\n    env:\n      CI_PART: x\n', 1),
                                           base_agents, base_ci), 'not exactly the suite job keys')
    last = suite_jobs(yaml.safe_load(ci_text))[-1][0]
    expect('mirror needs', mirror_violations(agents, re.sub(rf', {last}\]', ']', ci_text), base_agents, base_ci),
           'gate needs')
    expect('mirror stale', mirror_violations(agents.replace('a run of nine jobs', 'a run of three jobs'), ci_text,
                                             base_agents, base_ci), 'still says')
    expect('mirror budget', mirror_violations(re.sub(r'^\| ci budget \|.*\n', '', agents, flags=re.M), ci_text,
                                              base_agents, base_ci), 'ci budget row')
    gate_cmd = [c for c in recipe(agents)['gate'] if is_suite(c)][-1]
    expect('mirror gate', mirror_violations(agents.replace(f'    - {gate_cmd}\n', ''), ci_text, base_agents, base_ci),
           "release gate's suite")
    expect('mirror era', mirror_violations(agents, ci_text.replace(f'- run: {MODERN}', '- run: ', 1), base_agents, base_ci),
           'same commands in each era')
    module = staged(NEW_MODULE) if git('ls-files', '--', NEW_MODULE).strip() else 'import re\n'
    u = lambda pairs, a=agents, m=module: untouched_violations(pairs, a, base_agents, m)
    expect('untouched sound', u([('M', CI), ('M', 'AGENTS.md'), ('A', NEW_MODULE), ('A', f'spec/{SLUG}/PLAN.md')]), None)
    expect('untouched test', u([('M', 'tests/test_ssh_exec.py')]), 'pytest reads or collects')
    expect('untouched conftest', u([('M', 'tests/conftest.py')]), 'pytest reads or collects')
    expect('untouched spec conftest', u([('A', f'spec/{SLUG}/conftest.py')]), 'pytest reads or collects')
    expect('untouched spec test', u([('A', f'spec/{SLUG}/verify/test_x.py')]), 'pytest reads or collects')
    expect('untouched other module', u([('A', 'tests/test_zz.py')]), 'pytest reads or collects')
    expect('untouched module patches', u([('A', NEW_MODULE)], m='import ssh_server\nssh_server.WAIT = 0.1\n'), 'imports')
    expect('untouched module attr', u([('A', NEW_MODULE)], m='import re\nre.X = 1\n'), 'other than a name')
    expect('untouched module call', u([('A', NEW_MODULE)], m='import pytest\npytest.skip("x")\n'), 'at import')
    expect('untouched package', u([('M', 'packages/cluster-mcp/x.py')]), 'outside')
    expect('untouched pyproject', u([('M', 'pyproject.toml')]), 'pytest reads or collects')
    expect('untouched agents', u([], a=agents.replace('### 3. ', '### 3.  ', 1)), 'outside the profile')
    expect('untouched setup row', u([], a=agents.replace('| setup | `uv sync --locked`', '| setup | `uv sync`', 1)),
           "row 'setup' changed")
    expect('untouched landing rule', u([], a=agents.replace('at least one run must be listed', 'a run may be listed', 1)),
           'landing rule')
    expect('untouched recipe', u([], a=agents.replace('  clean_paths: [dist/]', '  clean_paths: []', 1)),
           'beyond its gate list')
    base_ids = ['tests/test_a.py::t1', 'tests/test_a.py::t2', 'tests/test_b.py::t3']
    sound = {'1': ['tests/test_a.py::t1'], '2': ['tests/test_a.py::t2'], '3': ['tests/test_b.py::t3', 'tests/test_n.py::t4']}
    expect('partition sound', partition_violations(base_ids, sound, {'tests/test_n.py'}), None)
    expect('partition dropped', partition_violations(base_ids, {**sound, '2': []}, {'tests/test_n.py'}), 'run in no job')
    expect('partition twice', partition_violations(base_ids, {**sound, '2': ['tests/test_a.py::t2', 'tests/test_a.py::t1']},
                                                   {'tests/test_n.py'}), 'runs in both')
    expect('partition old-module', partition_violations(base_ids, {**sound, '1': ['tests/test_a.py::t1', 'tests/test_a.py::t9']},
                                                        {'tests/test_n.py'}), 'modules the base has')
    good = {'guard': 'fails: ' + REASONS['guard'], 'context': 'fails: ' + REASONS['context'],
            'shim': 'fails: ' + REASONS['shim'], 'probes': 'fails: ' + REASONS['probes'],
            'collection hook': 'fails: ' + UNMARKED}
    expect('fixtures sound', fixture_violations(good, {'legacy 1': dict(good)}), None)
    expect('fixtures differs', fixture_violations(good, {'legacy 1': {**good, 'guard': 'did not fail as planted'}}),
           'not the base verdicts')
    expect('hooks', [] if hook_names(staged('tests/conftest.py')) == HOOKS else ['hooks differ'], None)
    names = {'suite-legacy-1': 'suite (handshake era, 1 of 2)', 'suite-modern-1': 'suite (modern era, 1 of 2)'}
    t0, early = '2026-11-06T12:00:00Z', '2026-11-06T11:00:00Z'
    job = lambda name, s=300.0, c='success', n=10, at=t0, failed=(): {
        'name': name, 'conclusion': c, 'seconds': s, 'startedAt': at, 'failed': list(failed),
        'counts': {'passed': n} if name.startswith('suite') else {}}
    run = lambda key=(1, 1), jobs=None: {'key': key, 'startedAt': t0, 'headSha': 'abc1234ff', 'event': 'push',
                                        'status': 'completed', 'conclusion': 'success',
                                        'jobs': jobs or [job(names['suite-legacy-1']), job(names['suite-modern-1']), job('gate')]}
    three = [run((1, 1)), run((1, 2)), run((1, 3))]
    listed = {(1, 1), (1, 2), (1, 3)}
    args = (names, 'abc1234', {'legacy': 9, 'modern': 9}, {'legacy': 1, 'modern': 1})
    ok = lambda runs, replaced=(), seen=listed: ci_violations(runs, *args, list(replaced), set(seen))[0]
    expect('ci sound', ok(three), None)
    expect('ci slow', ok(three[:2] + [run((1, 3), [job(names['suite-legacy-1'], 601), job(names['suite-modern-1']),
                                                   job('gate')])]), 'over 600 s')
    expect('ci red', ok(three[:2] + [run((1, 3), [job(names['suite-legacy-1']), job(names['suite-modern-1']),
                                                  job('gate', c='failure')])]), 'gate is failure')
    expect('ci two', ok(three[:2], seen={(1, 1), (1, 2)}), 'not at least 3')
    expect('ci repeated', ok([three[0]] * 3, seen={(1, 1)}), 'counted twice')
    expect('ci missing', ok(three[:2] + [run((1, 3), [job(names['suite-legacy-1']), job('gate')])]), "not the workflow's")
    expect('ci count', ok(three[:2] + [run((1, 3), [job(names['suite-legacy-1'], n=9), job(names['suite-modern-1']),
                                                    job('gate')])]), 'passed 9')
    expect('ci partial', ok(three[:2] + [run((1, 3), [job(names['suite-legacy-1'], at=early), job(names['suite-modern-1']),
                                                      job('gate')])]), 'not a full re-run')
    expect('ci cherry-picked', ok(three, seen=listed | {(1, 4)}), 'neither counted nor replaced')
    red_one = run((1, 4), [job(names['suite-legacy-1'], c='failure', failed=['tests/test_x.py::test_a']),
                           job(names['suite-modern-1']), job('gate', c='skipped')])
    expect('ci replaced sound', ok(three, [red_one], listed | {(1, 4)}), None)
    red_two = run((1, 4), [job(names['suite-legacy-1'], c='failure', failed=['tests/test_x.py::test_a', 'tests/test_x.py::test_b']),
                           job(names['suite-modern-1']), job('gate', c='skipped')])
    expect('ci replaced two rows', ok(three, [red_two], listed | {(1, 4)}), 'one row of one suite job')
    expect('ci replaced twice', ok(three, [red_one, run((1, 5), red_one['jobs'])], listed | {(1, 4), (1, 5)}),
           'not at most one')
    expect('counts', [] if counts('x 2026Z 4996 passed, 12 deselected, 1 warning in 758.95s (0:12:38)\n')
           == {'passed': 4996, 'deselected': 12, 'warning': 1} else ['counts misread'], None)
    expect('private', private_violations([('tests/test_x.py', 'host ' + '.'.join(['10', '1', '2', '3']) + ' via a.' + 'purdue' + '.edu')]), 'an IP address')
    expect('spec id', private_violations([('tests/test_x.py', '# per R2')]), 'feature-scoped id')
    expect('private sound', private_violations([('tests/test_x.py', '@pytest.mark.unit'), ('x', 'git@github.com:o/r'),
                                                ('x', "'\\n@pytest.mark.unit\\n'"),
                                                ('x', '/home/runner/work/x'), ('x', '127.0.0.1')]), None)
    expect('private mail', private_violations([('x', 'mail someone' + '@' + 'example.org')]), 'an email address')
    expect('ledger', ledger_violations('## Phase P1\nThis is left as a follow-up.\n## How `code-build` drives this\n',
                                       '', '', lambda p: False), 'names no issues/ seed')
    return found


# --- main ------------------------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['mirror', 'untouched', 'partition', 'fixtures', 'shard', 'ci', 'head', 'prepush',
                                         'controls', 'fixtures-control'])
    parser.add_argument('rest', nargs='*')
    parser.add_argument('--sha')
    parser.add_argument('--runs', nargs='*', default=[])
    parser.add_argument('--replaced', nargs='*', default=[])
    parser.add_argument('--base-run', type=int, default=BASE_RUN)
    parser.add_argument('--check-baseline', action='store_true')
    parser.add_argument('--runs-file')
    args = parser.parse_args()
    if not Path('AGENTS.md').is_file() or not Path(f'spec/{SLUG}').is_dir():
        raise SystemExit('suite-gate: run from the cycle worktree root')
    start = time.monotonic()
    if args.mode == 'mirror':
        found = mode_mirror()
    elif args.mode == 'untouched':
        found = mode_untouched()
    elif args.mode in ('partition', 'fixtures', 'shard'):
        era = args.rest[0] if args.rest else ''
        if era not in ('legacy', 'modern'):
            raise SystemExit('suite-gate: name the era, legacy or modern')
        found = (mode_partition(era) if args.mode == 'partition' else mode_fixtures(era) if args.mode == 'fixtures'
                 else mode_shard(era, int(args.rest[1])))
    elif args.mode == 'fixtures-control':
        found = mode_fixtures_control(args.rest[0] if args.rest else 'legacy')
    elif args.mode == 'ci':
        found = mode_ci(args)
    elif args.mode == 'head':
        found = mode_head(args)
    elif args.mode == 'prepush':
        found = mode_prepush()
    else:
        found = mode_controls()
    print('\n'.join(found) if found else f'suite-gate {args.mode} {" ".join(args.rest)}: ok')
    print(f'[suite-gate] {args.mode} {" ".join(args.rest)}: {time.monotonic() - start:.0f} s')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
