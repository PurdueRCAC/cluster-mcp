"""Review cycle 3, N1: every statement of where a call's opens wait matches the code, on every caller path.

Run from anywhere in the worktree:

    UV_PYTHON=3.14 uv run python -I spec/ssh-half-open-link/remediation/F7-open-rule-statement.py both   # or legacy, modern

The finding's instance: the rule review cycle 2's remediation wrote (the `SSHExecutor` docstring and
the `executor/ssh.py` footgun, pinned as `OPEN_TEXT`) said every open after a reconnect or a loss is
held to the call's deadline. A `write`'s own later commands (its parent's `mkdir`, its place step)
go through `_run`, which takes the connection the write itself reconnected to as found live, so
their first open waits for its own verdict and may end past the write's deadline. The behaviour is
in contract (the transfer is in flight); the text was broader than the code. The class: every
statement of that rule, on every path into `_run` and `_sftp`. Checked four ways:

1. **The rule as built is stated, in both texts**: the `SSHExecutor` docstring and the footgun each
   carry every phrase of `STATED` (opens before the call's work starts; a `write`'s own commands,
   each named, on the connection they find live, their first open past the write's deadline; what
   a silence there gives), and the doc pin passes.
2. **The broader rule is gone from every live site**: no phrase of `RETIRED` in AGENTS.md,
   README.md, ROADMAP.md, `issues/`, the packages' or the suite's `.py` files.
3. **Every caller path is one the text names**: in `ssh.py` the calls of `self._run` are `run`'s and
   the write's own three commands (`MAKE_PARENT`, `VERIFY`, `PROBE`), and the calls of `self._sftp`
   are `write`'s, `put`'s and `get`'s, each public method taking its own deadline from its own start;
   no module but `ssh.py` reaches `_run` or `_sftp`, so every tool (`sbatch`'s `script_content` a
   `write` and then a `run`) goes through a public method, one call each.
4. **A write's own command after a late reconnect behaves as stated**, in each era asked for: with
   `CLUSTER_MCP_TEST_EVERY_KIND=1` (exported here, the rows asserted collected), the rows
   `test_a_write_cut_at_its_own_command_after_a_late_reconnect_is_a_lost_transfer[mkdir|place]` pass:
   the open waits for its own verdict, and the write raises `TransferLost`, the target unchanged, no
   sooner than B and within the bound after the silence. With the cap planted on every `_run` open
   (the first one included, `shol-cap-always`'s edit), both rows fail, so they pin the first open
   left to its own verdict.

Exit 0 when all four hold. Footprint: one pytest child at a time in its own process group (a row
starts a loopback SSH server, a silent hop and a sandboxed login bash), under 600 MB, about a minute
per era.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOP = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True, cwd=Path(__file__).parent).stdout.strip())
sys.path.insert(0, str(TOP / 'tests'))
os.chdir(TOP)

import mutants  # noqa: E402

ERAS = ('legacy', 'modern')
SSH = TOP / 'packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py'
STATED = (
    "A call's first open, on the connection it found live as it began, waits for its own verdict",
    "Every later open before the call's work starts (a command's exec request, a transfer's first file operation)",
    "Once its work has started, a call's end is bounded from the silence instead",
    "A `write`'s own later commands (its parent's `mkdir`, its place step, and the probe that asks why a "
    'transfer fell short) run inside its transfer',
    'each on the connection it finds live as it begins',
    "each one's first open waits for its own verdict, after a late reconnect too and past the write's deadline",
    "a later one is held to the write's deadline",
    'A silence at the `mkdir` or the place step raises `TransferLost` within the bound after it',
    'a probe that cannot run gives no reason',
)
RETIRED = (
    'Every later open, after a reconnect or a loss, runs on a worker',
    'keeps the call past the 3B bound',
    'every later one, after a reconnect or a loss, ends at the deadline',
)
PIN = 'tests/test_ssh_liveness.py::test_liveness_texts_state_the_monitor'
DRIVE = 'test_a_write_cut_at_its_own_command_after_a_late_reconnect_is_a_lost_transfer'
DRIVE_ROWS = tuple(f'test_ssh_exec.py::{DRIVE}[{command}]' for command in ('mkdir', 'place'))
# Where `_run` and `_sftp` are called from, and with which fixed program for a write's own command.
RUN_CALLERS = {('run', None), ('_write', 'MAKE_PARENT'), ('_write', 'VERIFY'), ('_reason', 'PROBE')}
SFTP_CALLERS = {'write', 'put', 'get'}
PUBLIC = ('run', 'write', 'put', 'get')


def _flat(text: str) -> str:
    return ' '.join(text.split())


def stated_problems() -> list[str]:
    tree = ast.parse(SSH.read_text())
    executor = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SSHExecutor')
    agents = (TOP / 'AGENTS.md').read_text()
    footgun = agents[agents.index('- **`executor/ssh.py`**'):agents.index('- **`__init__.py`**')]
    texts = {'the SSHExecutor docstring': _flat(ast.get_docstring(executor) or ''), 'the footgun': _flat(footgun)}
    problems = [f'{name} does not state: {phrase!r}' for name, text in texts.items() for phrase in STATED
                if phrase not in text]
    with tempfile.TemporaryDirectory(prefix='f7-pin-') as scratch:
        report = Path(scratch) / 'junit.xml'
        status = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={report}', PIN],
                                cwd=TOP, timeout=300).returncode
        passed = report.exists() and any(
            case.get('name') == PIN.split('::')[1] and not any(child.tag in ('failure', 'error', 'skipped')
                                                               for child in case)
            for case in ET.parse(report).getroot().iter('testcase'))
    if status != 0 or not passed:
        problems.append(f'the doc pin {PIN} did not pass (exit {status})')
    return problems


def retired_problems() -> list[str]:
    sites = [TOP / 'AGENTS.md', TOP / 'README.md', TOP / 'ROADMAP.md', *sorted((TOP / 'issues').glob('*.md')),
             *sorted((TOP / 'packages').rglob('*.py')), *sorted((TOP / 'tests').glob('*.py'))]
    problems = []
    for site in sites:
        text = _flat(site.read_text())
        problems += [f'{site.relative_to(TOP)} still states {phrase!r}' for phrase in RETIRED if phrase in text]
    return problems


def _calls(tree: ast.AST, name: str) -> list[tuple[str, ast.Call]]:
    """Every `self.<name>(…)` call in `tree`, with the function it is made in."""
    found = []
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(function):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == 'self'):
                    found.append((function.name, node))
    # A call inside a nested function is found under both; keep the innermost.
    innermost: dict[int, tuple[str, ast.Call]] = {}
    for function, node in found:
        innermost[id(node)] = (function, node)
    return list(innermost.values())


def _program(call: ast.Call) -> str | None:
    """The fixed program a write's own command runs: `launch.fixed_argv(<NAME> …)`'s first name."""
    first = call.args[0] if call.args else None
    if isinstance(first, ast.Call) and first.args:
        head = first.args[0]
        if isinstance(head, ast.BinOp):
            head = head.left
        if isinstance(head, ast.Name):
            return head.id
    return None


def caller_problems() -> list[str]:
    tree = ast.parse(SSH.read_text())
    executor = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SSHExecutor')
    runs = [(function, None if function == 'run' else _program(call)) for function, call in _calls(executor, '_run')
            if function != '_run']
    sftps = [function for function, _ in _calls(executor, '_sftp')]
    problems = []
    if sorted(runs, key=str) != sorted(RUN_CALLERS, key=str):
        problems.append(f'`_run` is called from {sorted(runs, key=str)}, not exactly {sorted(RUN_CALLERS, key=str)}')
    if sorted(sftps) != sorted(SFTP_CALLERS):
        problems.append(f'`_sftp` is called from {sorted(sftps)}, not exactly {sorted(SFTP_CALLERS)}')
    methods = {n.name: n for n in executor.body if isinstance(n, ast.FunctionDef)}
    for name in PUBLIC:
        source = ast.unparse(methods[name])
        if 'time.monotonic() + self._window' not in source:
            problems.append(f'`{name}` does not take its own deadline from its own start')
    for path in sorted((TOP / 'packages').rglob('*.py')):
        if path == SSH:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute) and node.attr == '_sftp' and not (
                    isinstance(node.value, ast.Name) and node.value.id == 'self'):
                problems.append(f'{path.relative_to(TOP)}:{node.lineno} reaches `{node.attr}` from outside ssh.py')
            if (isinstance(node, ast.Attribute) and node.attr == '_run' and isinstance(node.value, ast.Name)
                    and node.value.id != 'self'):
                problems.append(f'{path.relative_to(TOP)}:{node.lineno} reaches `_run` from outside an executor')
    if not problems:
        print(f'callers: `_run` from {sorted(runs, key=str)}; `_sftp` from {sorted(sftps)}; tools through '
              f'{", ".join(PUBLIC)} only')
    return problems


def _env(era: str) -> dict[str, str]:
    return {**os.environ, 'CLUSTER_MCP_TEST_ERA': era, 'CLUSTER_MCP_TEST_EVERY_KIND': '1'}


def drive_problems(era: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix='f7-drive-') as scratch:
        report = Path(scratch) / 'junit.xml'
        argv = ['uv', 'run', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', '--durations=0', f'--junitxml={report}',
                *(f'tests/{row}' for row in DRIVE_ROWS)]
        child = subprocess.Popen(argv, cwd=TOP, env=_env(era), start_new_session=True)
        try:
            code = child.wait(timeout=300)
        except subprocess.TimeoutExpired:
            code = -1
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        outcomes = {}
        if report.exists():
            for case in ET.parse(report).getroot().iter('testcase'):
                tags = {child.tag for child in case}
                outcomes[case.get('name')] = 'failed' if tags & {'failure', 'error'} else (
                    'skipped' if 'skipped' in tags else 'passed')
    problems = [f'{era}: {row}: {outcomes.get(row.split("::")[1], "not collected")}' for row in DRIVE_ROWS
                if outcomes.get(row.split('::')[1]) != 'passed']
    if code != 0 and not problems:
        problems.append(f'{era}: pytest exited {code}')
    always = next((case for case in mutants.CASES if case.id == 'shol-cap-always'), None)
    if always is None:
        return problems + ['no `shol-cap-always` case in tests/mutants.py to plant']
    os.environ.update({'CLUSTER_MCP_TEST_ERA': era, 'CLUSTER_MCP_TEST_EVERY_KIND': '1'})
    planted = dataclasses.replace(always, id='f7-cap-every-run-open', targets=DRIVE_ROWS, why='not a lost transfer')
    violations = mutants.run_case(planted)
    if violations:
        problems.append(f'{era}: with the cap on every `_run` open, the rows did not both fail as a write '
                        f'that is not a lost transfer: {"; ".join(violations)}')
    else:
        print(f'killed  the cap on every `_run` open by {", ".join(DRIVE_ROWS)}, {era}')
    return problems


def main(eras: str) -> int:
    if eras not in (*ERAS, 'both'):
        print(f'usage: F7-open-rule-statement.py legacy|modern|both (got {eras!r})')
        return 2
    problems = stated_problems() + retired_problems() + caller_problems()
    for era in ERAS if eras == 'both' else (eras,):
        problems += drive_problems(era)
    for problem in problems:
        print(f'FAILED  {problem}')
    print('ok' if not problems else f'{len(problems)} problems')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ''))
