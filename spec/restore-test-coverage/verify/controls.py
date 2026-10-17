"""Gate-level negative controls for restore-test-coverage.

Usage (from the repository root):
  uv run python spec/restore-test-coverage/verify/controls.py <n>           run the controls for phases 1..n
  uv run python spec/restore-test-coverage/verify/controls.py --cases <n>   print the planted cases phases 1..n own

Runs the controls for phases 1..n. Each control imports a pure check function from the suite and
feeds it a planted shape it must reject, plus one clean shape it must accept, so a check that
returns [] for everything fails the gate even when every test id shows PASSED. The case table of
planted source violations is also checked here: every case a phase owns exists, and every target a
case names is a test id that some phase gate requires.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, 'tests')

PHASE_CASES = {
    1: {'isolation-module-global', 'isolation-executor-cached', 'shared-middleware-sets-first-call-only',
        'auth-middleware-sets-first-call-only'},
    2: {'tool-builds-local-executor', 'tool-builds-ssh-executor'},
    3: {'no-executor-module-global', 'no-executor-default-fallback', 'no-token-fallback-identity',
        'auth-middleware-sets-at-construction', 'shared-middleware-sets-at-construction',
        'transfer-local-fallback'},
    4: {'precedence-reordered', 'precedence-username-before-email', 'precedence-username-dropped',
        'precedence-empty-claim-accepted', 'no-claim-fallback-identity',
        'unmapped-gets-default-user', 'executor-unmapped-default', 'map-malformed-line-skipped',
        'map-line-number-dropped', 'map-line-counts-entries', 'map-comments-loaded'},
    5: {'sudo-n-dropped', 'sudo-H-dropped', 'cwd-unquoted', 'command-quoted', 'shell-read-per-call',
        'local-put-renamed', 'delegate-hostname-renamed', 'ssh-close-renamed'},
    6: {'ladder-rungs-1-2-swapped', 'ladder-rungs-3-4-swapped', 'ladder-env-host-ignored',
        'ladder-local-widened', 'delegate-gets-shared-middleware', 'ladder-explicit-local-ignored',
        'ladder-explicit-ssh-ignored', 'ladder-explicit-delegate-ignored',
        'ladder-explicit-delegate-yields-to-auth-none', 'ladder-explicit-yields-to-env-host',
        'ladder-explicit-yields-to-oidc', 'ladder-explicit-misrouted'},
    7: {'floor-auth-31', 'floor-cli-31', 'auth-unset-secret-defaulted', 'verifier-audience-changed',
        'verifier-issuer-changed', 'verifier-algorithm-changed', 'signer-audience-changed',
        'signer-token-expired', 'verifier-audience-unchecked', 'verifier-issuer-unchecked'},
}


def required_ids() -> set[str]:
    ids: set[str] = set()
    for path in sorted(HERE.glob('ids/P*.txt')):
        for line in path.read_text().splitlines():
            if line and not line.startswith('#'):
                ids.add(line)
    return ids


def phase1() -> None:
    from test_isolation import isolation_violations as iso
    exp = {'echo A': 'ualice', 'echo B': 'ubob'}
    ran = [('ualice', 'echo A'), ('ubob', 'echo B')]
    res = {'echo A': 'ualice|echo A', 'echo B': 'ubob|echo B'}
    assert iso(exp, ran, res) == [], iso(exp, ran, res)
    assert iso(exp, [('ubob', 'echo A'), ('ubob', 'echo B')], {'echo A': 'ubob|echo A', 'echo B': 'ubob|echo B'})
    assert iso(exp, ran, {'echo A': 'ualice|echo A', 'echo B': 'ualice|echo A'})
    assert iso(exp, ran, {'echo A': 'ualice|echo A ubob|echo B', 'echo B': 'ubob|echo B'})
    assert iso(exp, ran[:1], res)
    assert iso(exp, ran + [('ubob', 'echo B')], res)
    assert iso(exp, ran + [('ualice', 'echo C')], res)

    from test_hygiene import sandbox_violations as sb
    assert sb('import subprocess\nsubprocess.run([str(SANDBOX), "sh"])\n', 'f.py') == []
    assert sb('import subprocess\nsubprocess.run((SANDBOX, "sh"))\n', 'f.py') == []
    assert sb('import subprocess\nsubprocess.run(["rcac-mcp", "--help"])\n', 'f.py')
    assert sb('import subprocess\nsubprocess.run(argv)\n', 'f.py')
    assert sb('import subprocess\nsubprocess.Popen(["sh", "-c", "x"])\n', 'f.py')
    assert sb('import subprocess\nsubprocess.check_output([CLI])\n', 'f.py')
    assert sb('from subprocess import run\nrun([str(SANDBOX)])\n', 'f.py')
    assert sb('import os\nos.system("rcac-mcp --help")\n', 'f.py')
    assert sb('import subprocess as sp\nsp.run(["rcac-mcp"])\n', 'f.py')
    assert sb('import os\nos.execvp("rcac-mcp", ["rcac-mcp"])\n', 'f.py')
    assert sb('import asyncio\nasyncio.create_subprocess_exec("rcac-mcp")\n', 'f.py')
    assert sb('import subprocess\nsubprocess.run([str(SANDBOX), "sudo", "-n", "true"])\n', 'f.py')
    assert sb('import subprocess\nsubprocess.run([str(SANDBOX), "/usr/bin/ssh", "host"])\n', 'f.py')
    assert sb('import pytest, subprocess\n@pytest.mark.integration\ndef test_x():\n    subprocess.run(["true"])\n', 'f.py')
    assert sb('import pytest, subprocess\n@pytest.mark.unit\ndef test_x():\n    subprocess.run(["true"])\n', 'f.py') == []

    from mutants import CASES, mutation_violations as mv
    t = ['test_isolation.py::test_a', 'test_isolation.py::test_b']

    def jx(*cases: tuple[str, str, str]) -> str:
        body = ''.join(
            f'<testcase classname="tests.test_isolation" name="{name}">'
            + (f'<{tag} message="{msg}">{msg}</{tag}>' if tag else '') + '</testcase>'
            for name, tag, msg in cases)
        return f'<testsuites><testsuite name="pytest">{body}</testsuite></testsuites>'

    why = 'ran as'
    kill = jx(('test_a', 'failure', 'AssertionError: echo A ran as ubob, expected ualice'),
              ('test_b', 'failure', 'AssertionError: echo B ran as ualice, expected ubob'))
    assert mv(1, kill, t, why) == [], mv(1, kill, t, why)
    assert mv(0, jx(('test_a', '', ''), ('test_b', '', '')), t, why)
    assert mv(1, jx(('test_a', 'failure', 'ran as ubob'), ('test_b', '', '')), t, why)
    assert mv(1, jx(('test_a', 'failure', 'ran as ubob')), t, why)
    assert mv(1, jx(('test_a', 'failure', "NameError: name 'FastMCPx' is not defined"),
                    ('test_b', 'failure', 'ran as ualice')), t, why)
    assert mv(1, jx(('test_a', 'error', 'ran as ubob'), ('test_b', 'failure', 'ran as ualice')), t, why)
    assert mv(1, jx(('test_a', 'skipped', 'ran as'), ('test_b', 'failure', 'ran as ualice')), t, why)
    assert mv(1, None, t, why)
    for status in (2, 3, 4, 5, 97):
        assert mv(status, kill, t, why), status
    check_cases(CASES, 1)


def check_cases(cases, n: int) -> None:
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids)), 'duplicate case ids'
    want = set().union(*(PHASE_CASES[i] for i in range(1, n + 1)))
    missing = want - set(ids)
    assert not missing, f'planted-violation cases missing: {sorted(missing)}'
    required = required_ids()
    for c in cases:
        assert c.targets, f'{c.id}: no targets'
        assert c.edits, f'{c.id}: no edits'
        assert c.why and c.why.lower() not in ('error', 'failed', 'assert'), f'{c.id}: kill reason not specific'
        for target in c.targets:
            assert target in required, f'{c.id}: target {target} is not a required test id'
        if c.id in want:
            assert f'test_mutations.py::test_mutation_anchor_applies[{c.id}]' in required, c.id


def phase2() -> None:
    from harness import Outcome
    from test_registry import EXPECTED_TOOLS
    from test_tools import TOOL_CASES, tool_violations as tv
    good = Outcome(False, 'SENTINEL-sinfo')
    calls = [('run', 'sinfo')]
    assert tv(good, calls, [], 'SENTINEL-sinfo') == []
    assert tv(Outcome(False, ''), calls, [], None) == []
    assert tv(good, [], [], 'SENTINEL-sinfo')
    assert tv(good, calls, [('Popen', ['sh', '-c', 'sinfo'])], 'SENTINEL-sinfo')
    assert tv(Outcome(False, 'something else'), calls, [], 'SENTINEL-sinfo')
    assert tv(Outcome(True, 'SENTINEL-sinfo'), calls, [], 'SENTINEL-sinfo')
    assert set(TOOL_CASES) == set(EXPECTED_TOOLS), sorted(set(TOOL_CASES) ^ set(EXPECTED_TOOLS))


def phase3() -> None:
    from harness import Outcome
    from test_no_executor import refusal_violations as rv
    reason = 'No executor configured'
    assert rv(Outcome(True, "Error calling tool 'run_command': No executor configured."), [], [], reason) == []
    assert rv(Outcome(False, 'ualice|echo ANON'), [], [], reason)
    assert rv(Outcome(True, "[Errno 2] No such file or directory: '/remote/results.csv'"), [], [], reason)
    assert rv(Outcome(True, reason), [('run', 'echo ANON')], [], reason)
    assert rv(Outcome(True, reason), [], [['sudo', '-n', '-H', '-u', 'ualice', '/bin/sh', '-c', 'echo ANON']], reason)


def phase4() -> None:
    from harness import Outcome
    from test_identity import delegation_violations as dv

    def argv(user: str, command: str) -> list[str]:
        return ['sudo', '-n', '-H', '-u', user, '/bin/sh', '-c', command]

    assert dv(Outcome(False, 'ualice|echo X'), [argv('ualice', 'echo X')], 'ualice', 'echo X') == []
    assert dv(Outcome(False, 'uemail|echo X'), [argv('uemail', 'echo X')], 'ualice', 'echo X')
    assert dv(Outcome(True, 'User is not authorized'), [], 'ualice', 'echo X')
    assert dv(Outcome(False, 'ualice|echo X'), [argv('ualice', 'echo X')] * 2, 'ualice', 'echo X')
    assert dv(Outcome(False, 'ubob|echo Y'), [argv('ualice', 'echo X')], 'ualice', 'echo X')


def phase5() -> None:
    from test_executors import sudo_argv_violations as av
    cmd = 'echo $HOME; ls *'
    good = ['sudo', '-n', '-H', '-u', 'ubob', '/opt/test-shell-a', '-c', cmd]
    assert av(good, 'ubob', '/opt/test-shell-a', cmd) == []
    assert av(['sudo', '-H', '-u', 'ubob', '/opt/test-shell-a', '-c', cmd], 'ubob', '/opt/test-shell-a', cmd)
    assert av(['sudo', '-n', '-u', 'ubob', '/opt/test-shell-a', '-c', cmd], 'ubob', '/opt/test-shell-a', cmd)
    assert av(good[:-1] + ["'echo $HOME; ls *'"], 'ubob', '/opt/test-shell-a', cmd)
    assert av(good[:5] + ['/opt/test-shell-b'] + good[6:], 'ubob', '/opt/test-shell-a', cmd)
    assert av(good[:4] + ['ualice'] + good[5:], 'ubob', '/opt/test-shell-a', cmd)
    quoted = "cd '/data/my dir' && echo hi"
    assert av(good[:-1] + ['cd /data/my dir && echo hi'], 'ubob', '/opt/test-shell-a', quoted)


def phase6() -> None:
    from test_exec_mode import LADDER_CASES, ladder_violations as lv
    seen = {'status': 0, 'mode': 'delegate', 'middleware': ['AuthExecutorMiddleware'], 'ssh_hosts': [], 'started': True}
    want = {'status': 0, 'mode': 'delegate', 'middleware': ['AuthExecutorMiddleware'], 'ssh_host': None, 'started': True}
    assert lv(seen, want) == [], lv(seen, want)
    assert lv({**seen, 'mode': 'local', 'middleware': ['SharedExecutorMiddleware']}, want)
    assert lv({**seen, 'middleware': ['SharedExecutorMiddleware']}, want)
    assert lv({**seen, 'middleware': ['AuthExecutorMiddleware', 'SharedExecutorMiddleware']}, want)
    assert lv({**seen, 'ssh_hosts': ['h']}, want)
    closed = {'status': 2, 'mode': 'ssh', 'middleware': None, 'ssh_host': None, 'started': False}
    assert lv({'status': 2, 'mode': 'ssh', 'middleware': None, 'ssh_hosts': [], 'started': False}, closed) == []
    assert lv({'status': 0, 'mode': 'ssh', 'middleware': ['SharedExecutorMiddleware'], 'ssh_hosts': ['h'],
               'started': True}, closed)
    ids = {p.id for p in LADDER_CASES}
    explicit = {f'explicit-{mode}-over-{later}' for mode in ('local', 'ssh', 'delegate')
                for later in ('stdio', 'host', 'env-host', 'auth-none', 'auth', 'oidc')}
    assert explicit <= ids, sorted(explicit - ids)
    assert ids == explicit | {'stdio-over-auth', 'stdio-default', 'host-flag-over-auth-none',
                              'env-host-over-auth-none', 'host-over-jwt', 'auth-none-http', 'auth-none-sse',
                              'jwt-without-host', 'oidc-without-host'}, sorted(ids)


def phase7() -> None:
    from rcac_mcp.token import generate_token
    from test_tokens import token_cli_violations as tk
    s = 'k' * 32
    tok = generate_token(s, 60, 'alice')
    refused = 'CRITICAL [rcac_mcp] JWT_SECRET must be at least 32 characters'
    assert tk(0, tok + '\n', '', True, s, 'alice') == []
    assert tk(2, '', refused, False) == []
    assert tk(0, tok + '\n', '', False)
    assert tk(2, tok + '\n', refused, False)
    assert tk(1, '', refused, False)
    assert tk(2, '', 'CRITICAL [rcac_mcp] unrecognized arguments: --generate-token', False)
    assert tk(0, '', '', True, s, 'alice')
    assert tk(0, tok + '\n' + tok + '\n', '', True, s, 'alice')
    assert tk(0, generate_token('z' * 32, 60, 'alice') + '\n', '', True, s, 'alice')
    assert tk(0, generate_token(s, 60, 'bob') + '\n', '', True, s, 'alice')


def main() -> int:
    if sys.argv[1] == '--cases':
        n = int(sys.argv[2])
        print('\n'.join(sorted(set().union(*(PHASE_CASES[i] for i in range(1, min(n, 7) + 1))))))
        return 0
    n = int(sys.argv[1])
    for i, control in enumerate((phase1, phase2, phase3, phase4, phase5, phase6, phase7), start=1):
        if i <= n:
            control()
            print(f'controls: phase {i} ok', file=sys.stderr)
    if n >= 2:
        from mutants import CASES
        check_cases(CASES, min(n, 7))
    return 0


if __name__ == '__main__':
    sys.exit(main())
