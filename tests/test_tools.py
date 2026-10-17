# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Every served tool does its work on the executor the middleware installed, and on nothing else.

Tools never construct an executor; they call `get_executor()` (§ Invariants §1, §7). Each tool in
`EXPECTED_TOOLS` is called through the in-memory MCP client on a server whose
`SharedExecutorMiddleware` installs a `RecordingExecutor`. The call must reach that executor, carry
the tool's own argument there, and hand the executor's answer back to the client, while the unit
guard refuses every process and connection made anywhere else. A tool that built its own
`LocalShellExecutor` or `SSHExecutor` would trip the guard, which this module reports as a launch
outside the executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import pytest

from harness import Outcome, RecordingExecutor, call, drive, in_memory, shared_server
from test_registry import EXPECTED_TOOLS

# What the installed executor answers when a case gives no responder of its own; a result carrying
# it can only have come from that executor.
ANSWER = 'answered-by-the-installed-executor'

# Stands for the test's tmp_path in a case's arguments and expectations.
TMP = '{tmp}'

LS_LINES = ('total 8\n'
            'drwxr-xr-x 2 alice lab 4096 2026-10-16 12:00 installed-executor-entry\n'
            '-rw-r--r-- 1 alice lab   12 2026-10-16 12:00 notes.txt\n')

QUOTA_TABLE = ('Type        Location        Size    Limit   Use     Files   Limit   Use\n'
               '==============================================================================\n'
               'home        alice           14.6GB  25.0GB  58.6%   -       -       -\n'
               'scratch     alice           1.2TB   200TB   0.6%    10k     2000k   0.5%\n'
               'depot       lab             3.0TB   10TB    30.0%   -       -       -\n')


def answer(command: str) -> str:
    return ANSWER


def ls_listing(command: str) -> str:
    return LS_LINES if command.startswith('ls ') else ANSWER


def quota_and_scratch(command: str) -> str:
    if command == 'findscratch':
        return '/scratch/test/installed-executor-scratch'
    return QUOTA_TABLE if command == 'myquota' else ANSWER


def submitted(command: str) -> str:
    return 'Submitted batch job 987654321' if command.startswith('sbatch') else ANSWER


@dataclass(frozen=True)
class ToolCase:
    """How one tool is called, what the installed executor answers, and what must come back.

    `reaches` is a fragment some recorded executor call must carry (the tool's own argument, or the
    command it wraps); `expect` must appear in the result text, or is None for a tool that returns
    nothing. `TMP` in either stands for the test's tmp_path.
    """

    args: dict[str, Any]
    reaches: str
    expect: str | None = ANSWER
    responder: Callable[[str], str] = field(default=answer)

    def arguments(self, tmp_path: Path) -> dict[str, Any]:
        """The call's arguments with `TMP` resolved to `tmp_path`."""
        return {k: v.replace(TMP, str(tmp_path)) if isinstance(v, str) else v for k, v in self.args.items()}

    def expected(self, tmp_path: Path) -> str | None:
        return None if self.expect is None else self.expect.replace(TMP, str(tmp_path))


TOOL_CASES: dict[str, ToolCase] = {
    'average_wait': ToolCase({'partition': 'wait-partition'}, 'wait-partition'),
    'download_file': ToolCase({'remote_path': '/remote/results.csv', 'local_path': f'{TMP}/results.csv'},
                              '/remote/results.csv', expect=f'{TMP}/results.csv'),
    'jobcmd': ToolCase({'job_id': 4242001}, '4242001'),
    'jobenv': ToolCase({'job_id': 4242002}, '4242002'),
    'jobinfo': ToolCase({'job_id': 4242003}, '4242003'),
    'jobscript': ToolCase({'job_id': 4242004}, '4242004'),
    'list_directory': ToolCase({'path': '/data/listed-dir'}, '/data/listed-dir',
                               expect='/data/listed-dir/installed-executor-entry', responder=ls_listing),
    'myquota': ToolCase({}, 'myquota'),
    'read_file': ToolCase({'path': '/data/read-me.txt'}, '/data/read-me.txt'),
    'run_command': ToolCase({'command': 'echo tool-check'}, 'echo tool-check'),
    'sacct': ToolCase({'user': 'sacct-user', 'job_ids': [4242005]}, '4242005'),
    'sbatch': ToolCase({'script_path': '/data/job.sh', 'partition': 'batch-partition'}, 'batch-partition',
                       expect='987654321', responder=submitted),
    'scancel': ToolCase({'job_ids': [4242006]}, '4242006'),
    'scontrol_show_job': ToolCase({'job_id': 4242007}, '4242007'),
    'scontrol_show_node': ToolCase({'node': 'node-a000'}, 'node-a000'),
    'sfeatures': ToolCase({}, 'sfeatures'),
    'showpartitions': ToolCase({}, 'showpartitions'),
    'sinfo': ToolCase({'partition': 'info-partition'}, 'info-partition'),
    'slist': ToolCase({}, 'slist'),
    'squeue': ToolCase({'partition': 'queue-partition'}, 'queue-partition'),
    'storage_paths': ToolCase({}, 'findscratch', expect='/scratch/test/installed-executor-scratch',
                              responder=quota_and_scratch),
    'upload_file': ToolCase({'local_path': '/data/upload-in.csv', 'remote_path': '/remote/upload-out.csv'},
                            '/remote/upload-out.csv'),
    'write_file': ToolCase({'path': '/data/written.txt', 'content': 'written-by-the-tool'}, 'written-by-the-tool',
                           expect=None),
}


def tool_violations(outcome: Outcome, calls: Sequence[tuple[Any, ...]], refused: Sequence[Any],
                    expect: str | None, reaches: str | None = None) -> list[str]:
    """Return every way a tool call bypassed or ignored its installed executor; empty means it did not.

    `calls` is what the installed executor recorded, `refused` what the unit guard refused (a
    process or connection made anywhere else), `expect` a fragment the client's result must carry
    (None for a tool that returns nothing), and `reaches` a fragment some recorded call must carry.
    """
    violations: list[str] = []
    if outcome.is_error:
        violations.append(f'error result: {outcome.text!r}')
    if not calls:
        violations.append('the tool never reached the executor: it recorded no call')
    elif reaches is not None and not any(reaches in str(part) for c in calls for part in c[1:]):
        violations.append(f'the tool never reached the executor with {reaches!r}: {list(calls)!r}')
    for attempt in refused:
        violations.append(f'launched outside the executor: {attempt!r}')
    if expect is not None and expect not in outcome.text:
        violations.append(f'result lacks {expect!r}: {outcome.text!r}')
    return violations


@pytest.mark.unit
@pytest.mark.parametrize('tool', sorted(EXPECTED_TOOLS))
def test_tool_reaches_only_the_installed_executor(tool: str, tmp_path: Path, guard) -> None:
    case = TOOL_CASES[tool]
    executor = RecordingExecutor('installed', responder=case.responder)

    async def scenario() -> Outcome:
        server = shared_server(executor)
        async with in_memory(server) as client:
            return await call(client, tool, case.arguments(tmp_path))

    outcome = drive(scenario())
    violations = tool_violations(outcome, executor.calls, guard.refused, case.expected(tmp_path), case.reaches)
    # A joined string, not the list: pytest abbreviates a long list's repr, which can cut a
    # violation out of the failure text.
    assert violations == [], '\n'.join(violations)
    assert guard.refused == []


@pytest.mark.unit
def test_tool_cases_cover_expected_tools() -> None:
    assert set(TOOL_CASES) == set(EXPECTED_TOOLS), sorted(set(TOOL_CASES) ^ set(EXPECTED_TOOLS))


GOOD = Outcome(False, f'{ANSWER} for sinfo')
CALLS = [('run', 'sinfo -p gpu', None, None)]


@pytest.mark.unit
@pytest.mark.parametrize(('outcome', 'calls', 'refused', 'fragment'), [
    pytest.param(GOOD, [], [], 'never reached the executor', id='no-executor-call'),
    pytest.param(GOOD, CALLS, [('subprocess.Popen', (['/bin/sh', '-c', 'sinfo -p gpu'],))],
                 'launched outside the executor', id='outside-launch'),
    pytest.param(Outcome(False, 'something else'), CALLS, [], 'result lacks', id='result-dropped'),
    pytest.param(Outcome(True, f'{ANSWER} for sinfo'), CALLS, [], 'error result', id='error-result'),
])
def test_tool_check_catches_bypass(outcome: Outcome, calls: list[tuple[Any, ...]], refused: list[Any],
                                   fragment: str) -> None:
    assert tool_violations(GOOD, CALLS, [], ANSWER, 'gpu') == []
    assert tool_violations(Outcome(False, ''), CALLS, [], None) == []
    violations = tool_violations(outcome, calls, refused, ANSWER, 'gpu')
    assert any(fragment in v for v in violations), violations


@pytest.mark.unit
def test_tool_check_requires_the_tool_argument_at_the_executor() -> None:
    violations = tool_violations(GOOD, [('run', 'sinfo', None, None)], [], ANSWER, 'gpu')
    assert any('never reached the executor' in v for v in violations), violations
