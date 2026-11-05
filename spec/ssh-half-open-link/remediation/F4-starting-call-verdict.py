"""Review cycle 1, F4: R4's third case, both ways, on a live link where another call starts.

Run from the worktree root:

    uv run python -I spec/ssh-half-open-link/remediation/F4-starting-call-verdict.py both   # or legacy, modern

R4: while another call starts on the connection, a quiet command and a slow transfer have that
call's verdict, B after its start. The rows (2 s connect bound) make the link silent under a quiet
command, or under a 4 MiB upload at its first write, start a call beside it, and let the held
connection answer again 1 s into the call (within its verdict: both finish on one connection) or
2.8 s in (past it, inside the 3 s a background probe waits: the work is cut, and the call completes
on a new connection).

1. **The rows pass**, by id, in each era asked for, none skipped.
2. **The rows have teeth both ways** (in each era): the poke's verdict planted at once
   (`shol-poke-verdict-zero`'s edit) fails the two `answered` rows, and at a background probe's
   2B less the margin (`shol-poke-verdict-background`'s edit) fails the two `unanswered` rows, each
   for its own stated reason. The edits are taken from `tests/mutants.py` by case id and planted with
   these rows as targets through its runner (`run_case`), so the cases themselves are unchanged.
   The rows pass on the reviewed commit (`b09a991`), whose code already meets R4's third case, so
   they cannot be shown red there: these mutants are their red.

Exit 0 when both hold. Footprint: one pytest child at a time, in its own process group; each row
starts a loopback SSH server and a silent hop; under 600 MB.
"""

from __future__ import annotations

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
from mutants import Case  # noqa: E402

ERAS = ('legacy', 'modern')
EXEC = 'test_ssh_exec.py'
COMMAND = 'test_a_quiet_command_beside_a_starting_call_has_that_calls_verdict'
TRANSFER = 'test_a_slow_transfer_beside_a_starting_call_has_that_calls_verdict'
ROWS = tuple(f'{EXEC}::{row}[{answer}]' for row in (COMMAND, TRANSFER) for answer in ('answered', 'unanswered'))
MISSED = 'an answer within the verdict was missed'
# Each planted verdict, the rows it must fail, and the text each failure carries.
PLANTS = (
    ('shol-poke-verdict-zero', f'{EXEC}::{COMMAND}[answered]', MISSED),
    ('shol-poke-verdict-zero', f'{EXEC}::{TRANSFER}[answered]', MISSED),
    ('shol-poke-verdict-background', f'{EXEC}::{COMMAND}[unanswered]', 'not -1003'),
    ('shol-poke-verdict-background', f'{EXEC}::{TRANSFER}[unanswered]', 'not a lost transfer'),
)
DROPPED = ('VIRTUAL_ENV', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONSAFEPATH', 'CLUSTER_MCP_TEST_ERA')


def row_problems(era: str) -> list[str]:
    env = dict(os.environ)
    for name in DROPPED:
        env.pop(name, None)
    env['CLUSTER_MCP_TEST_ERA'] = era
    with tempfile.TemporaryDirectory(prefix='f4-verdict-') as scratch:
        junit = Path(scratch) / 'junit.xml'
        argv = ['uv', 'run', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', f'--junitxml={junit}',
                *(f'tests/{row}' for row in ROWS)]
        child = subprocess.Popen(argv, cwd=TOP, env=env, start_new_session=True)
        try:
            code = child.wait(timeout=600)
        except subprocess.TimeoutExpired:
            code = -1
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if not junit.exists():
            return [f'{era}: pytest exited {code} with no JUnit report']
        outcomes = {}
        for case in ET.parse(junit).getroot().iter('testcase'):
            tags = {c.tag for c in case}
            outcomes[case.get('name')] = 'failed' if tags & {'failure', 'error'} else (
                'skipped' if 'skipped' in tags else 'passed')
    problems = [f'{era}: {row} {outcomes.get(row.split("::")[1], "missing")}' for row in ROWS
                if outcomes.get(row.split('::')[1]) != 'passed']
    if code != 0 and not problems:
        problems.append(f'{era}: pytest exited {code}')
    return problems


def plant_problems(era: str) -> list[str]:
    os.environ['CLUSTER_MCP_TEST_ERA'] = era
    known = {case.id: case for case in mutants.CASES}
    problems = []
    for case_id, row, why in PLANTS:
        if case_id not in known:
            problems.append(f'{era}: {case_id}: no such case in tests/mutants.py')
            continue
        planted = Case(f'f4-{case_id}', known[case_id].file, known[case_id].edits, (row,), why)
        violations = mutants.run_case(planted)
        if violations:
            problems.append(f'{era}: {case_id} against {row}: {"; ".join(violations)}')
        else:
            print(f'killed  {case_id} by {row} ({why!r}), {era}')
    return problems


def main(eras: str) -> int:
    if eras not in (*ERAS, 'both'):
        print(f'usage: F4-starting-call-verdict.py legacy|modern|both (got {eras!r})')
        return 2
    problems: list[str] = []
    for era in ERAS if eras == 'both' else (eras,):
        found = row_problems(era)
        print(f'{era}: ' + (f'{len(ROWS)} rows passed' if not found else f'{len(found)} problems'))
        problems += found + plant_problems(era)
    for problem in problems:
        print(f'FAILED  {problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ''))
