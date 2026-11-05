"""Review cycle 1, F1: no call waits on the connection's shared write path past its own deadline.

Run from anywhere in the worktree:

    uv run python -I spec/ssh-half-open-link/remediation/F1-send-path.py both    # or legacy, modern

The finding's instance was `_signal` taking `clear_to_send_lock` with no bound at a command's
timeout, so an upload stalled on a silent link held the call until the liveness verdict. The class
is every send a call's own path makes on the shared transport once its own deadline is running or
after a loss. The property is checked two ways:

1. **Where the sends are made** (static, on `core/executor/ssh.py`'s syntax tree). The functions a
   `run` call passes through once its exec request is answered (`_exec`, `_collect`, `_stopped`,
   `_drain`) make no send of their own: no call to `_signal`, `_send_user_message`,
   `_send_message`, `send`, `sendall`, `shutdown`, `shutdown_write`, `recv` or `recv_stderr`
   (Paramiko's `recv` sends the window adjust on its caller's thread), and no channel `close()`;
   each goes through the call's sender (`_Sends`). `_take` may call `recv`/`recv_stderr` only in
   its branch for a channel that is not Paramiko's. `_signal` takes no lock but the write path
   (`clear_to_send_lock`), never `chan.lock`, so a request waiting on that path never blocks the
   call's reads or the transport thread. A site nobody has found yet that sends inline fails here.
2. **What the call does** (the rows, by id, in each era asked for): a timed command beside an
   upload stalled on the silent link returns `-1001` at its timeout; a timed call whose write path
   another sender holds from its exec request on returns at its timeout with all it read, and once
   the path is free its TERM reaches the command and the KILL comes `GRACE` later; with the path
   free, the TERM reaches the command at once and all it prints as it stops is read; a `signal`
   request is written holding the write path and not the channel's lock, and never follows a close
   marked while it waited; and the ssh grace row (`tpc`'s) still reads what a stopping command
   prints. Each must be reported passed, none skipped.
3. **The earlier cycles' cases on these paths still bite**: every `tests/mutants.py` case this
   remediation re-planted because its anchor moved into the sender (the end of stdin, the GRACE
   read, the TERM and KILL requests, the KILL's guard, `_signal`'s checks) is run in each era and
   must be reported killed.

Exit 0 when all three hold. Footprint: one pytest child per era, in its own process group, killed on exit;
the rows start loopback SSH servers and a silent hop, under 600 MB.
"""

from __future__ import annotations

import ast
import os
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOP = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                          check=True, cwd=Path(__file__).parent).stdout.strip())
SSH = TOP / 'packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py'
ERAS = ('legacy', 'modern')
EXEC = 'tests/test_ssh_exec.py'
ROWS = (
    f'{EXEC}::test_a_timed_command_beside_a_transfer_stalled_on_a_silent_link_ends_at_its_timeout',
    f'{EXEC}::test_a_timed_call_never_waits_on_a_write_path_another_call_holds[held]',
    f'{EXEC}::test_a_timed_call_never_waits_on_a_write_path_another_call_holds[free]',
    f'{EXEC}::test_a_signal_request_goes_while_the_channel_is_held_open',
    f'{EXEC}::test_a_signal_request_never_follows_a_close_made_as_it_waits',
    'tests/test_timeout_stop.py::test_a_stopping_command_gets_its_grace[ssh-bash]',
)
# The functions a call's path runs once its exec request is answered, and the sends none may make.
CALL_PATH = ('_exec', '_collect', '_stopped', '_drain')
SENDS = {'_signal', '_send_user_message', '_send_message', 'send', 'sendall', 'shutdown', 'shutdown_write',
         'recv', 'recv_stderr'}
# The cases re-planted on the sender, their decisions unchanged.
REPLANTED = (
    'ssh-stdin-not-closed', 'content-on-stdin-over-ssh', 'ssh-timeout-no-drain', 'ssh-returns-at-exit-status',
    'tpc-ssh-kill-dropped', 'tpc-ssh-kill-dropped-unit', 'tpc-ssh-kill-before-term', 'tpc-ssh-kill-before-term-output',
    'tpc-ssh-kill-before-grace', 'tpc-ssh-kill-before-grace-output',
    *(f'tpc-ssh-kill-{name}{unit}' for unit in ('', '-unit') for name in ('term', 'hup', 'int', 'quit', 'usr1', 'usr2',
                                                                         'stop')),
    'tpc-ssh-kill-unguarded', 'tpc-ssh-kill-guard-inverted', 'tpc-ssh-kill-guard-inverted-behaviour',
    'tpc-ssh-kill-guard-status', 'tpc-ssh-signal-unchecked', 'tpc-ssh-signal-active-checked',
    'tpc-ssh-signal-unlocked', 'tpc-ssh-signal-checked-then-sent', 'tpc-ssh-signal-no-key-exchange-wait',
    'tpc-ssh-signal-key-exchange-unchecked', 'tpc-ssh-signal-wait-locked', 'tpc-ssh-signal-user-message',
    'tpc-ssh-signal-exchange-unlocked',
)
DROPPED = ('VIRTUAL_ENV', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONSAFEPATH', 'CLUSTER_MCP_TEST_ERA')


def _called(node: ast.AST) -> list[tuple[str, str, int]]:
    """Each call under `node`: the name called, the receiver's text, the line."""
    found = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if isinstance(func, ast.Attribute):
            found.append((func.attr, ast.unparse(func.value), call.lineno))
        elif isinstance(func, ast.Name):
            found.append((func.id, '', call.lineno))
    return found


def static_problems() -> list[str]:
    tree = ast.parse(SSH.read_text())
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    problems = [f'{name}: not found in ssh.py' for name in (*CALL_PATH, '_take', '_signal') if name not in functions]
    if problems:
        return problems
    for name in CALL_PATH:
        for called, receiver, line in _called(functions[name]):
            if called in SENDS:
                problems.append(f'ssh.py:{line}: {name} calls {receiver + "." if receiver else ""}{called} on its own '
                                'thread')
            if called == 'close' and receiver == 'chan':
                problems.append(f'ssh.py:{line}: {name} closes the channel on its own thread')
    take = functions['_take']
    fallback = [stmt for stmt in take.body if isinstance(stmt, ast.If)
                and 'isinstance(chan, Channel)' in ast.unparse(stmt.test)]
    allowed = {id(node) for stmt in fallback for node in ast.walk(stmt)}
    for call in ast.walk(take):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in SENDS \
                and id(call) not in allowed:
            problems.append(f'ssh.py:{call.lineno}: _take calls {call.func.attr} outside its branch for a channel '
                            "that is not Paramiko's")
    if not fallback:
        problems.append("_take has no branch for a channel that is not Paramiko's, so the check above proves nothing")
    locks = [(receiver, line) for called, receiver, line in _called(functions['_signal'])
             if called == 'acquire' or receiver.endswith('lock')]
    if not any(receiver == 'transport.clear_to_send_lock' for receiver, _ in locks):
        problems.append('_signal does not take the write path (`clear_to_send_lock`)')
    text = ast.unparse(functions['_signal'])
    if 'chan.lock' in text:
        problems.append("_signal takes the channel's lock, which the call's reads and the transport thread take")
    return problems


def _env(era: str) -> dict[str, str]:
    env = dict(os.environ)
    for name in DROPPED:
        env.pop(name, None)
    env['CLUSTER_MCP_TEST_ERA'] = era
    return env


def row_problems(era: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix='f1-send-path-') as scratch:
        junit = Path(scratch) / 'junit.xml'
        argv = ['uv', 'run', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider', f'--junitxml={junit}', *ROWS]
        child = subprocess.Popen(argv, cwd=TOP, env=_env(era), start_new_session=True)
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
            tags = {child.tag for child in case}
            outcomes[case.get('name')] = 'failed' if tags & {'failure', 'error'} else (
                'skipped' if 'skipped' in tags else 'passed')
    problems = []
    for row in ROWS:
        name = row.split('::', 1)[1]
        got = outcomes.get(name, 'missing')
        if got != 'passed':
            problems.append(f'{era}: {row} {got}')
    if code != 0 and not problems:
        problems.append(f'{era}: pytest exited {code}')
    return problems


def case_problems(era: str) -> list[str]:
    run = subprocess.run([sys.executable, 'tests/mutants.py', *REPLANTED], cwd=TOP, env=_env(era),
                         capture_output=True, text=True, timeout=3000)
    killed = {line.split()[1].rstrip(':') for line in run.stdout.splitlines() if line.startswith('killed ')}
    problems = [f'{era}: {case} not killed' for case in REPLANTED if case not in killed]
    problems += [f'{era}: {line}' for line in run.stdout.splitlines() if line.startswith('FAILED')]
    if run.returncode != 0 and not problems:
        problems.append(f'{era}: tests/mutants.py exited {run.returncode}: {run.stderr[-400:]}')
    return problems


def main(eras: str) -> int:
    if eras not in (*ERAS, 'both'):
        print(f'usage: F1-send-path.py legacy|modern|both (got {eras!r})')
        return 2
    problems = static_problems()
    print('static: ' + ('the call path makes no send of its own' if not problems else f'{len(problems)} problems'))
    for era in ERAS if eras == 'both' else (eras,):
        found = row_problems(era)
        print(f'{era}: ' + (f'{len(ROWS)} rows passed' if not found else f'{len(found)} problems'))
        problems += found
        found = case_problems(era)
        print(f'{era}: ' + (f'{len(REPLANTED)} re-planted cases killed' if not found else f'{len(found)} problems'))
        problems += found
    for problem in problems:
        print(f'FAILED  {problem}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) == 2 else ''))
