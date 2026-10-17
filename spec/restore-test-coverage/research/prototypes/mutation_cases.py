# Planning prototype for restore-test-coverage (2026-10-16), kept as evidence for research/; not a test.
# Run from the worktree root: uv run python spec/restore-test-coverage/research/prototypes/mutation_cases.py
#
# The planted-violation table the build ports into tests/mutants.py (not collected; run by the phase
# gate). Each case names the package file it edits (a copy, never src/), the exact (old, new) edits,
# the test ids that must FAIL against the mutant, and the fragment each failure must carry (the kill
# reason), so a mutant that merely breaks an import is never counted as caught. Running this file
# checks that every anchor occurs exactly once in the current source and every mutant compiles.

from __future__ import annotations

import sys
from pathlib import Path

import rcac_mcp

PKG = Path(rcac_mcp.__file__).parent

GLOBAL_VAR = '''class _ProcessGlobal:
    value = None

    def get(self):
        return _ProcessGlobal.value

    def set(self, value):
        _ProcessGlobal.value = value


executor_var = _ProcessGlobal()'''

CASES = [
    # --- isolation (contract: per-request executor, ContextVar) ---
    ('isolation-module-global', 'context.py', [
        ("executor_var: ContextVar[Optional[Executor]] = ContextVar('executor', default=None)", GLOBAL_VAR)],
     ['test_isolation.py::test_concurrent_delegate_calls_stay_isolated',
      'test_isolation.py::test_concurrent_shared_servers_stay_isolated'],
     'ran as'),
    ('isolation-executor-cached', 'middleware.py', [
        ('        executor = DelegatingExecutor(identity, self._user_map)\n',
         "        executor = getattr(self, '_cached', None) or DelegatingExecutor(identity, self._user_map)\n"
         '        self._cached = executor\n')],
     ['test_isolation.py::test_concurrent_delegate_calls_stay_isolated'],
     'ran as'),
    # --- tool surface (contract: tools reach the cluster only through get_executor) ---
    ('tool-builds-local-executor', 'tools/slurm.py', [
        ("    executor = get_executor()\n\n    args = []\n    if partition:\n        args.append(f'-p {partition}')\n    if nodes:",
         "    executor = __import__('rcac_mcp.executor.shell', fromlist=['LocalShellExecutor']).LocalShellExecutor()\n\n"
         "    args = []\n    if partition:\n        args.append(f'-p {partition}')\n    if nodes:")],
     ['test_tools.py::test_tool_reaches_only_the_installed_executor[sinfo]'],
     'launched outside the executor'),
    ('tool-builds-ssh-executor', 'tools/rcac.py', [
        ("    executor = get_executor()\n    result = executor.run('myquota')",
         "    executor = __import__('rcac_mcp.executor.ssh', fromlist=['SSHExecutor']).SSHExecutor('cluster.invalid')\n"
         "    result = executor.run('myquota')")],
     ['test_tools.py::test_tool_reaches_only_the_installed_executor[myquota]'],
     'launched outside the executor'),
    # --- no executor set (contract: get_executor raises; no fallback) ---
    ('no-executor-module-global', 'context.py', [
        ("executor_var: ContextVar[Optional[Executor]] = ContextVar('executor', default=None)", GLOBAL_VAR)],
     ['test_no_executor.py::test_no_executor_after_earlier_request',
      'test_no_executor.py::test_no_executor_while_other_request_in_flight',
      'test_no_executor.py::test_delegate_without_token_after_authenticated_request',
      'test_no_executor.py::test_delegate_without_token_while_authenticated_request_in_flight'],
     'not an error'),
    ('no-executor-default-fallback', 'context.py', [
        ("        raise RuntimeError('No executor configured. Set executor via set_executor() first.')",
         '        from rcac_mcp.executor.shell import LocalShellExecutor\n        return LocalShellExecutor()')],
     ['test_no_executor.py::test_tool_without_executor_middleware_fails[run_command]',
      'test_no_executor.py::test_no_executor_after_earlier_request'],
     'not an error'),
    ('no-token-fallback-identity', 'middleware.py', [
        ('            # No auth - this shouldn\'t happen in delegate mode\n'
         '            # but let the request proceed (will fail at executor access)\n'
         '            return await call_next(context)',
         '            set_executor(DelegatingExecutor(next(iter(self._user_map)), self._user_map))\n'
         '            return await call_next(context)')],
     ['test_no_executor.py::test_delegate_without_token_fails'],
     'not an error'),
    # --- identity claims (contract: sub -> email -> preferred_username, first non-empty, no fallback) ---
    ('precedence-reordered', 'middleware.py', [
        ("for claim in ('sub', 'email', 'preferred_username'):",
         "for claim in ('email', 'sub', 'preferred_username'):")],
     ['test_identity.py::test_identity_claim_precedence[all-three]'],
     'ran as'),
    ('precedence-username-before-email', 'middleware.py', [
        ("for claim in ('sub', 'email', 'preferred_username'):",
         "for claim in ('sub', 'preferred_username', 'email'):")],
     ['test_identity.py::test_identity_claim_precedence[sub-absent]'],
     'ran as'),
    ('precedence-username-dropped', 'middleware.py', [
        ("for claim in ('sub', 'email', 'preferred_username'):",
         "for claim in ('sub', 'email'):")],
     ['test_identity.py::test_identity_claim_precedence[email-empty]',
      'test_identity.py::test_identity_claim_precedence[username-only]'],
     'error result'),
    ('precedence-empty-claim-accepted', 'middleware.py', [
        ('if claim in claims and claims[claim]:', 'if claim in claims:')],
     ['test_identity.py::test_identity_claim_precedence[sub-empty]'],
     'error result'),
    ('no-claim-fallback-identity', 'middleware.py', [
        ('                return str(claims[claim])\n        return None\n',
         '                return str(claims[claim])\n        return next(iter(self._user_map))\n')],
     ['test_identity.py::test_token_without_identity_fails[no-claims]',
      'test_identity.py::test_token_without_identity_fails[all-empty]'],
     'not an error'),
    # --- user map (contract: unmapped -> PermissionError / KeyError; malformed line -> ValueError naming it) ---
    ('unmapped-gets-default-user', 'middleware.py', [
        ('        if identity not in self._user_map:\n            raise PermissionError(',
         '        if identity not in self._user_map:\n            identity = next(iter(self._user_map))\n'
         '        if False:\n            raise PermissionError(')],
     ['test_identity.py::test_unmapped_identity_is_not_authorized',
      'test_identity.py::test_first_claim_unmapped_does_not_fall_through'],
     'not an error'),
    ('executor-unmapped-default', 'executor/delegate.py', [
        ("        if identity not in user_map:\n            raise KeyError(f'Identity {identity!r} not found in user map')\n",
         ''),
        ('        self._local_user = user_map[identity]', "        self._local_user = user_map.get(identity, 'nobody')")],
     ['test_identity.py::test_executor_rejects_unmapped_identity'],
     'DID NOT RAISE'),
    ('map-malformed-line-skipped', 'executor/delegate.py', [
        ('            if len(parts) != 2:\n                raise ValueError(',
         '            if len(parts) != 2:\n                continue\n                raise ValueError(')],
     ['test_identity.py::test_user_map_rejects_line_without_local_user'],
     'DID NOT RAISE'),
    ('map-line-number-dropped', 'executor/delegate.py', [
        ('''f'Invalid user map format at line {line_num}: expected "<id> <local-user>"\'''',
         '''f'Invalid user map format: expected "<id> <local-user>"\'''')],
     ['test_identity.py::test_user_map_rejects_line_without_local_user'],
     'line 3'),
    ('map-comments-loaded', 'executor/delegate.py', [
        ("if not line or line.startswith('#'):", 'if not line:')],
     ['test_identity.py::test_user_map_skips_comments_and_blanks'],
     'map differs'),
    # --- sudo argv (contract: sudo -n -H -u <user> <server $SHELL> -c <command>, cwd quoted only) ---
    ('sudo-n-dropped', 'executor/delegate.py', [
        ("sudo_cmd = ['sudo', '-n', '-H', '-u', self._local_user]", "sudo_cmd = ['sudo', '-H', '-u', self._local_user]")],
     ['test_executors.py::test_sudo_argv[no-cwd]'],
     'argv differs'),
    ('sudo-H-dropped', 'executor/delegate.py', [
        ("sudo_cmd = ['sudo', '-n', '-H', '-u', self._local_user]", "sudo_cmd = ['sudo', '-n', '-u', self._local_user]")],
     ['test_executors.py::test_sudo_argv[no-cwd]'],
     'argv differs'),
    ('cwd-unquoted', 'executor/delegate.py', [
        ("full_command = f'cd {shlex.quote(cwd)} && {command}'", "full_command = f'cd {cwd} && {command}'")],
     ['test_executors.py::test_sudo_argv[cwd-spaces]', 'test_executors.py::test_sudo_argv[cwd-metacharacters]'],
     'argv differs'),
    ('command-quoted', 'executor/delegate.py', [
        ('        else:\n            full_command = command\n', '        else:\n            full_command = shlex.quote(command)\n')],
     ['test_executors.py::test_sudo_argv[no-cwd]'],
     'argv differs'),
    ('shell-read-per-call', 'executor/delegate.py', [
        ("sudo_cmd.extend([self._shell, '-c', full_command])",
         "sudo_cmd.extend([os.environ.get('SHELL', '/bin/sh'), '-c', full_command])")],
     ['test_executors.py::test_shell_is_captured_at_construction'],
     'argv differs'),
    # --- executor protocol (contract: all three backends satisfy Executor) ---
    ('local-put-renamed', 'executor/shell.py', [
        ('    def put(self, local_path: str, remote_path: str) -> None:',
         '    def put_file(self, local_path: str, remote_path: str) -> None:')],
     ['test_executors.py::test_backend_satisfies_executor_protocol[local]'],
     'does not satisfy Executor'),
    ('delegate-hostname-renamed', 'executor/delegate.py', [
        ('    def hostname(self) -> str:', '    def host_name(self) -> str:')],
     ['test_executors.py::test_backend_satisfies_executor_protocol[delegate]'],
     'does not satisfy Executor'),
    ('ssh-close-renamed', 'executor/ssh.py', [
        ('    def close(self) -> None:\n        """Close the SSH connection."""',
         '    def disconnect(self) -> None:\n        """Close the SSH connection."""')],
     ['test_executors.py::test_backend_satisfies_executor_protocol[ssh]'],
     'does not satisfy Executor'),
    # --- execution-mode ladder (contract: five rungs in order; middleware by mode) ---
    ('ladder-rungs-1-2-swapped', '__init__.py', [
        ("        if self.exec_mode:\n            return self.exec_mode\n\n"
         "        # Auto-select based on transport, auth, and ssh-host\n"
         "        if self.transport == 'stdio':\n            return 'ssh'\n",
         "        if self.transport == 'stdio':\n            return 'ssh'\n"
         "        if self.exec_mode:\n            return self.exec_mode\n\n"
         "        # Auto-select based on transport, auth, and ssh-host\n"
         "        if False:\n            return 'ssh'\n")],
     ['test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-stdio]'],
     'mode:'),
    ('ladder-rungs-3-4-swapped', '__init__.py', [
        ("        elif self.ssh_host or os.environ.get('RCAC_SSH_HOST'):\n"
         "            # If SSH host is specified, use ssh mode regardless of transport\n"
         "            return 'ssh'\n"
         "        elif self.auth == 'none':\n            return 'local'\n",
         "        elif self.auth == 'none':\n            return 'local'\n"
         "        elif self.ssh_host or os.environ.get('RCAC_SSH_HOST'):\n"
         "            return 'ssh'\n")],
     ['test_exec_mode.py::test_exec_mode_ladder[host-flag-over-auth-none]',
      'test_exec_mode.py::test_exec_mode_ladder[env-host-over-auth-none]'],
     'mode:'),
    ('ladder-env-host-ignored', '__init__.py', [
        ("        elif self.ssh_host or os.environ.get('RCAC_SSH_HOST'):\n", '        elif self.ssh_host:\n')],
     ['test_exec_mode.py::test_exec_mode_ladder[env-host-over-auth-none]'],
     'mode:'),
    ('ladder-local-widened', '__init__.py', [
        ("        elif self.auth == 'none':\n            return 'local'\n        else:\n            return 'delegate'",
         "        else:\n            return 'local'")],
     ['test_exec_mode.py::test_exec_mode_ladder[jwt-without-host]',
      'test_exec_mode.py::test_exec_mode_ladder[oidc-without-host]'],
     'mode:'),
    ('delegate-gets-shared-middleware', '__init__.py', [
        ("        if exec_mode == 'delegate':\n", "        if exec_mode == 'delegate' and False:\n")],
     ['test_exec_mode.py::test_exec_mode_ladder[jwt-without-host]'],
     'middleware:'),
    # --- secrets and tokens (contract: 32-char floor twice; shared issuer/audience/algorithm) ---
    ('floor-auth-31', 'auth.py', [
        ('    if len(secret) < 32:\n', '    if len(secret) < 31:\n')],
     ['test_tokens.py::test_jwt_auth_refuses_short_secret[31-chars]'],
     'DID NOT RAISE'),
    ('floor-cli-31', '__init__.py', [
        ('            if len(secret) < 32:\n', '            if len(secret) < 31:\n')],
     ['test_tokens.py::test_generate_token_refuses_short_secret[31-chars]'],
     'status'),
    ('auth-unset-secret-defaulted', 'auth.py', [
        ("        raise ValueError('JWT_SECRET environment variable required for jwt auth mode')",
         "        secret = 'x' * 32")],
     ['test_tokens.py::test_jwt_auth_refuses_short_secret[unset]',
      'test_tokens.py::test_jwt_auth_refuses_short_secret[empty]'],
     'DID NOT RAISE'),
    ('verifier-audience-changed', 'auth.py', [
        ('        audience=AUDIENCE,\n', "        audience=AUDIENCE + '-other',\n")],
     ['test_tokens.py::test_minted_token_is_accepted', 'test_tokens.py::test_cli_minted_token_is_accepted'],
     'error result'),
    ('verifier-issuer-changed', 'auth.py', [
        ('        issuer=ISSUER,\n', "        issuer=ISSUER + '-other',\n")],
     ['test_tokens.py::test_minted_token_is_accepted'],
     'error result'),
    ('verifier-algorithm-changed', 'auth.py', [
        ('        algorithm=ALGORITHM,\n', "        algorithm='HS512',\n")],
     ['test_tokens.py::test_minted_token_is_accepted'],
     'error result'),
    ('signer-audience-changed', 'token.py', [
        ("        'aud': AUDIENCE,\n", "        'aud': AUDIENCE + '-other',\n")],
     ['test_tokens.py::test_minted_token_is_accepted', 'test_tokens.py::test_cli_minted_token_is_accepted'],
     'error result'),
    ('signer-token-expired', 'token.py', [
        ("        'exp': now + timedelta(seconds=lifetime),\n", "        'exp': now - timedelta(seconds=lifetime),\n")],
     ['test_tokens.py::test_minted_token_is_accepted'],
     'error result'),
    # --- found by the adversarial design review (2026-10-16) ---
    ('auth-middleware-sets-at-construction', 'middleware.py', [
        ('        self._user_map = load_user_map(user_map_path)\n',
         '        self._user_map = load_user_map(user_map_path)\n'
         '        set_executor(DelegatingExecutor(next(iter(self._user_map)), self._user_map))\n')],
     ['test_no_executor.py::test_delegate_without_token_fails',
      'test_no_executor.py::test_delegate_without_token_after_authenticated_request',
      'test_no_executor.py::test_delegate_without_token_while_authenticated_request_in_flight'],
     'not an error'),
    ('shared-middleware-sets-at-construction', 'middleware.py', [
        ('        super().__init__()\n        self._executor = executor\n',
         '        super().__init__()\n        self._executor = executor\n        set_executor(executor)\n')],
     ['test_no_executor.py::test_no_executor_after_earlier_request',
      'test_no_executor.py::test_no_executor_while_other_request_in_flight'],
     'not an error'),
    ('transfer-local-fallback', 'tools/transfer.py', [
        ('    executor = get_executor()\n    executor.get(remote_path, local_path)',
         '    try:\n        executor = get_executor()\n    except RuntimeError:\n'
         '        from rcac_mcp.executor.shell import LocalShellExecutor\n'
         '        executor = LocalShellExecutor()\n    executor.get(remote_path, local_path)')],
     ['test_no_executor.py::test_tool_without_executor_middleware_fails[download_file]'],
     'error lacks reason'),
    ('verifier-audience-unchecked', 'auth.py', [
        ('        audience=AUDIENCE,\n', '        audience=None,\n')],
     ['test_tokens.py::test_mismatched_token_is_rejected[audience]'],
     'expected 401'),
    ('verifier-issuer-unchecked', 'auth.py', [
        ('        issuer=ISSUER,\n', '        issuer=None,\n')],
     ['test_tokens.py::test_mismatched_token_is_rejected[issuer]'],
     'expected 401'),
]


def check() -> list[str]:
    problems = []
    ids = [case[0] for case in CASES]
    if len(ids) != len(set(ids)):
        problems.append('duplicate case ids')
    for case_id, rel, edits, targets, why in CASES:
        path = PKG / rel
        text = path.read_text()
        for old, new in edits:
            n = text.count(old)
            if n != 1:
                problems.append(f'{case_id}: anchor occurs {n} times in {rel}: {old[:60]!r}')
                continue
            text = text.replace(old, new)
        try:
            compile(text, str(path), 'exec')
        except SyntaxError as exc:
            problems.append(f'{case_id}: mutant does not compile: {exc}')
        if not targets:
            problems.append(f'{case_id}: no targets')
        if not why or why.lower() in ('error', 'failed', 'assert'):
            problems.append(f'{case_id}: the kill reason is not specific')
    return problems


if __name__ == '__main__':
    found = check()
    print('\n'.join(found) or f'{len(CASES)} cases: every anchor occurs once and every mutant compiles')
    sys.exit(1 if found else 0)
