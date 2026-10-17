# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""Planted violations: each contract test must go red against a copy of the package that breaks it.

Usage, from the repository root:

    uv run python tests/mutants.py [--self-check] CASE_ID...

Each `Case` copies the imported `rcac_mcp` package (never `src/` itself), applies exact source
edits that break one contract, and runs the named target tests against the copy in a child pytest
under `bin/sandbox.sh`. A case is caught only when every target fails (a JUnit `<failure>`, not an
`<error>` or a skip) and the failure carries the case's `why`: the fragment of the violation
message that names the broken contract. A mutant that merely breaks an import fails for the wrong
reason and counts as surviving.

This module is not collected: a child takes seconds, so the phase gates run it and its report is
recorded with the change. `test_mutations.py` keeps the fast parts in the suite: every anchor still
applies, and `mutation_violations` rejects each way a child can fail to prove a kill.

`--self-check` also runs the runner's own controls: a docstring-only edit must be reported as
surviving, and a child that does not import the mutated copy must be reported as a wrong origin.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import rcac_mcp

TESTS = Path(__file__).resolve().parent
SANDBOX = TESTS.parent / 'bin' / 'sandbox.sh'

# Exit status of the child when the mutated copy is not what it imports.
WRONG_ORIGIN = 97

# The child steps back into the repository (the sandbox starts elsewhere) so pytest reads
# pyproject.toml, refuses to run unless `rcac_mcp` resolves under the mutated copy, then runs the
# targets with a JUnit report.
CHILD = """\
cd "$CLUSTER_MCP_REPO" || exit 96
py=$1
root=$2
junit=$3
shift 3
"$py" -c 'import os, sys, rcac_mcp; sys.exit(0 if os.path.realpath(rcac_mcp.__file__).startswith(os.path.realpath(sys.argv[1]) + os.sep) else 97)' "$root" || exit 97
exec "$py" -m pytest -q -rA -p no:cacheprovider --junitxml="$junit" "$@"
"""


@dataclass(frozen=True)
class Case:
    """One planted violation.

    `file` is relative to the package directory; `edits` are exact `(old, new)` replacements, each
    `old` occurring once; `targets` are `tests/`-relative test ids that must fail; `why` is the
    fragment each target's failure must carry.
    """

    id: str
    file: str
    edits: tuple[tuple[str, str], ...]
    targets: tuple[str, ...]
    why: str


PROCESS_GLOBAL = '''class _ProcessGlobal:
    value = None

    def get(self):
        return _ProcessGlobal.value

    def set(self, value):
        _ProcessGlobal.value = value


executor_var = _ProcessGlobal()'''

CONTEXT_VAR = "executor_var: ContextVar[Optional[Executor]] = ContextVar('executor', default=None)"

CLAIM_ORDER = "for claim in ('sub', 'email', 'preferred_username'):"

SUDO_PREFIX = "sudo_cmd = ['sudo', '-n', '-H', '-u', self._local_user]"

EXPLICIT_MODE = '        if self.exec_mode:\n'

CASES: tuple[Case, ...] = (
    # Per-request isolation: the executor lives in a ContextVar and is built per call.
    Case('isolation-module-global', 'context.py',
         ((CONTEXT_VAR, PROCESS_GLOBAL),),
         ('test_isolation.py::test_concurrent_delegate_calls_stay_isolated',
          'test_isolation.py::test_concurrent_shared_servers_stay_isolated'),
         'ran as'),
    Case('isolation-executor-cached', 'middleware.py',
         (('        executor = DelegatingExecutor(identity, self._user_map)\n',
           "        executor = getattr(self, '_cached', None) or DelegatingExecutor(identity, self._user_map)\n"
           '        self._cached = executor\n'),),
         ('test_isolation.py::test_concurrent_delegate_calls_stay_isolated',),
         'ran as'),
    # Each executor middleware sets the executor on every call; set once, the later calls of the
    # same server find none.
    Case('shared-middleware-sets-first-call-only', 'middleware.py',
         (('        set_executor(self._executor)\n        return await call_next(context)\n',
           "        if not getattr(self, '_set_once', False):\n"
           '            set_executor(self._executor)\n'
           '            self._set_once = True\n'
           '        return await call_next(context)\n'),),
         ('test_isolation.py::test_sequential_shared_calls_each_get_the_executor',),
         'ran 0 times'),
    Case('auth-middleware-sets-first-call-only', 'middleware.py',
         (('        executor = DelegatingExecutor(identity, self._user_map)\n        set_executor(executor)\n',
           '        executor = DelegatingExecutor(identity, self._user_map)\n'
           "        if not getattr(self, '_set_once', False):\n"
           '            set_executor(executor)\n'
           '            self._set_once = True\n'),),
         ('test_isolation.py::test_sequential_delegate_calls_each_get_their_executor',),
         'ran 0 times'),
    # The tool surface: tools reach the cluster only through get_executor(), never an executor of
    # their own.
    Case('tool-builds-local-executor', 'tools/slurm.py',
         (("    executor = get_executor()\n\n    args = []\n    if partition:\n        args.append(f'-p {partition}')\n"
           '    if nodes:',
           "    executor = __import__('rcac_mcp.executor.shell', fromlist=['LocalShellExecutor']).LocalShellExecutor()\n\n"
           "    args = []\n    if partition:\n        args.append(f'-p {partition}')\n    if nodes:"),),
         ('test_tools.py::test_tool_reaches_only_the_installed_executor[sinfo]',),
         'launched outside the executor'),
    Case('tool-builds-ssh-executor', 'tools/rcac.py',
         (("    executor = get_executor()\n    result = executor.run('myquota')",
           "    executor = __import__('rcac_mcp.executor.ssh', fromlist=['SSHExecutor']).SSHExecutor('cluster.invalid')\n"
           "    result = executor.run('myquota')"),),
         ('test_tools.py::test_tool_reaches_only_the_installed_executor[myquota]',),
         'launched outside the executor'),
    # No executor set: get_executor() raises, with no fallback, and nothing set at construction or
    # by another request reaches this one.
    Case('no-executor-module-global', 'context.py',
         ((CONTEXT_VAR, PROCESS_GLOBAL),),
         ('test_no_executor.py::test_no_executor_after_earlier_request',
          'test_no_executor.py::test_no_executor_while_other_request_in_flight',
          'test_no_executor.py::test_delegate_without_token_after_authenticated_request',
          'test_no_executor.py::test_delegate_without_token_while_authenticated_request_in_flight'),
         'not an error'),
    Case('no-executor-default-fallback', 'context.py',
         (("        raise RuntimeError('No executor configured. Set executor via set_executor() first.')",
           '        from rcac_mcp.executor.shell import LocalShellExecutor\n        return LocalShellExecutor()'),),
         ('test_no_executor.py::test_tool_without_executor_middleware_fails[run_command]',
          'test_no_executor.py::test_no_executor_after_earlier_request'),
         'not an error'),
    Case('no-token-fallback-identity', 'middleware.py',
         (("            # No auth - this shouldn't happen in delegate mode\n"
           '            # but let the request proceed (will fail at executor access)\n'
           '            return await call_next(context)',
           '            set_executor(DelegatingExecutor(next(iter(self._user_map)), self._user_map))\n'
           '            return await call_next(context)'),),
         ('test_no_executor.py::test_delegate_without_token_fails',),
         'not an error'),
    Case('auth-middleware-sets-at-construction', 'middleware.py',
         (('        self._user_map = load_user_map(user_map_path)\n',
           '        self._user_map = load_user_map(user_map_path)\n'
           '        set_executor(DelegatingExecutor(next(iter(self._user_map)), self._user_map))\n'),),
         ('test_no_executor.py::test_delegate_without_token_fails',
          'test_no_executor.py::test_delegate_without_token_after_authenticated_request',
          'test_no_executor.py::test_delegate_without_token_while_authenticated_request_in_flight'),
         'not an error'),
    Case('shared-middleware-sets-at-construction', 'middleware.py',
         (('        super().__init__()\n        self._executor = executor\n',
           '        super().__init__()\n        self._executor = executor\n        set_executor(executor)\n'),),
         ('test_no_executor.py::test_no_executor_after_earlier_request',
          'test_no_executor.py::test_no_executor_while_other_request_in_flight'),
         'not an error'),
    # A tool that falls back to a local executor fails on the missing file with a local error, not
    # the refusal; only the stated reason tells the two apart.
    Case('transfer-local-fallback', 'tools/transfer.py',
         (('    executor = get_executor()\n    executor.get(remote_path, local_path)',
           '    try:\n        executor = get_executor()\n    except RuntimeError:\n'
           '        from rcac_mcp.executor.shell import LocalShellExecutor\n'
           '        executor = LocalShellExecutor()\n    executor.get(remote_path, local_path)'),),
         ('test_no_executor.py::test_tool_without_executor_middleware_fails[download_file]',),
         'error lacks reason'),
    # Identity claims: sub, then email, then preferred_username, the first non-empty one wins, and
    # a token with none of them is refused rather than given an identity.
    Case('precedence-reordered', 'middleware.py',
         ((CLAIM_ORDER, "for claim in ('email', 'sub', 'preferred_username'):"),),
         ('test_identity.py::test_identity_claim_precedence[all-three]',),
         'ran as'),
    Case('precedence-username-before-email', 'middleware.py',
         ((CLAIM_ORDER, "for claim in ('sub', 'preferred_username', 'email'):"),),
         ('test_identity.py::test_identity_claim_precedence[sub-absent]',),
         'ran as'),
    Case('precedence-username-dropped', 'middleware.py',
         ((CLAIM_ORDER, "for claim in ('sub', 'email'):"),),
         ('test_identity.py::test_identity_claim_precedence[email-empty]',
          'test_identity.py::test_identity_claim_precedence[username-only]'),
         'error result'),
    Case('precedence-empty-claim-accepted', 'middleware.py',
         (('if claim in claims and claims[claim]:', 'if claim in claims:'),),
         ('test_identity.py::test_identity_claim_precedence[sub-empty]',),
         'error result'),
    Case('no-claim-fallback-identity', 'middleware.py',
         (('                return str(claims[claim])\n        return None\n',
           '                return str(claims[claim])\n        return next(iter(self._user_map))\n'),),
         ('test_identity.py::test_token_without_identity_fails[no-claims]',
          'test_identity.py::test_token_without_identity_fails[all-empty]'),
         'not an error'),
    # The user map: an unmapped identity is refused by the middleware and by the executor, never
    # given a default user; a malformed line fails naming its line; comments load as nothing.
    Case('unmapped-gets-default-user', 'middleware.py',
         (('        if identity not in self._user_map:\n            raise PermissionError(',
           '        if identity not in self._user_map:\n            identity = next(iter(self._user_map))\n'
           '        if False:\n            raise PermissionError('),),
         ('test_identity.py::test_unmapped_identity_is_not_authorized',
          'test_identity.py::test_first_claim_unmapped_does_not_fall_through'),
         'not an error'),
    Case('executor-unmapped-default', 'executor/delegate.py',
         (("        if identity not in user_map:\n            raise KeyError(f'Identity {identity!r} not found in user map')\n",
           ''),
          ('        self._local_user = user_map[identity]', "        self._local_user = user_map.get(identity, 'nobody')")),
         ('test_identity.py::test_executor_rejects_unmapped_identity',),
         'DID NOT RAISE'),
    Case('map-malformed-line-skipped', 'executor/delegate.py',
         (('            if len(parts) != 2:\n                raise ValueError(',
           '            if len(parts) != 2:\n                continue\n                raise ValueError('),),
         ('test_identity.py::test_user_map_rejects_line_without_local_user',),
         'DID NOT RAISE'),
    Case('map-line-number-dropped', 'executor/delegate.py',
         (('''f'Invalid user map format at line {line_num}: expected "<id> <local-user>"\'''',
           '''f'Invalid user map format: expected "<id> <local-user>"\''''),),
         ('test_identity.py::test_user_map_rejects_line_without_local_user',),
         'does not name line 5'),
    # Numbering by entries, not file lines, names the wrong line once comments or blanks precede it.
    Case('map-line-counts-entries', 'executor/delegate.py',
         (('Invalid user map format at line {line_num}:', 'Invalid user map format at line {len(user_map) + 1}:'),),
         ('test_identity.py::test_user_map_rejects_line_without_local_user',),
         'does not name line 5'),
    Case('map-comments-loaded', 'executor/delegate.py',
         (("if not line or line.startswith('#'):", 'if not line:'),),
         ('test_identity.py::test_user_map_skips_comments_and_blanks',),
         'map differs'),
    # The delegated launch: exactly sudo -n -H -u <user> <shell captured at construction> -c
    # <command line>, with the cwd quoted and the command not.
    Case('sudo-n-dropped', 'executor/delegate.py',
         ((SUDO_PREFIX, "sudo_cmd = ['sudo', '-H', '-u', self._local_user]"),),
         ('test_executors.py::test_sudo_argv[no-cwd]',),
         'argv differs'),
    Case('sudo-H-dropped', 'executor/delegate.py',
         ((SUDO_PREFIX, "sudo_cmd = ['sudo', '-n', '-u', self._local_user]"),),
         ('test_executors.py::test_sudo_argv[no-cwd]',),
         'argv differs'),
    Case('cwd-unquoted', 'executor/delegate.py',
         (("full_command = f'cd {shlex.quote(cwd)} && {command}'", "full_command = f'cd {cwd} && {command}'"),),
         ('test_executors.py::test_sudo_argv[cwd-spaces]', 'test_executors.py::test_sudo_argv[cwd-metacharacters]'),
         'argv differs'),
    Case('command-quoted', 'executor/delegate.py',
         (('        else:\n            full_command = command\n',
           '        else:\n            full_command = shlex.quote(command)\n'),),
         ('test_executors.py::test_sudo_argv[no-cwd]',),
         'argv differs'),
    Case('shell-read-per-call', 'executor/delegate.py',
         (("sudo_cmd.extend([self._shell, '-c', full_command])",
           "sudo_cmd.extend([os.environ.get('SHELL', '/bin/sh'), '-c', full_command])"),),
         ('test_executors.py::test_shell_is_captured_at_construction',),
         'argv differs'),
    # The Executor protocol: every backend carries all eight members; a renamed one drops out.
    Case('local-put-renamed', 'executor/shell.py',
         (('    def put(self, local_path: str, remote_path: str) -> None:',
           '    def put_file(self, local_path: str, remote_path: str) -> None:'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[local]',),
         'does not satisfy Executor'),
    Case('delegate-hostname-renamed', 'executor/delegate.py',
         (('    def hostname(self) -> str:', '    def host_name(self) -> str:'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[delegate]',),
         'does not satisfy Executor'),
    Case('ssh-close-renamed', 'executor/ssh.py',
         (('    def close(self) -> None:\n        """Close the SSH connection."""',
           '    def disconnect(self) -> None:\n        """Close the SSH connection."""'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[ssh]',),
         'does not satisfy Executor'),
    # The execution-mode ladder: explicit -e, then stdio, then an SSH host from the flag or the
    # environment, then auth none, then delegate; delegate alone gets the auth middleware.
    Case('ladder-rungs-1-2-swapped', '__init__.py',
         (("        if self.exec_mode:\n            return self.exec_mode\n\n"
           "        # Auto-select based on transport, auth, and ssh-host\n"
           "        if self.transport == 'stdio':\n            return 'ssh'\n",
           "        if self.transport == 'stdio':\n            return 'ssh'\n"
           "        if self.exec_mode:\n            return self.exec_mode\n\n"
           "        # Auto-select based on transport, auth, and ssh-host\n"
           "        if False:\n            return 'ssh'\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-stdio]',),
         'mode:'),
    Case('ladder-rungs-3-4-swapped', '__init__.py',
         (("        elif self.ssh_host or os.environ.get('RCAC_SSH_HOST'):\n"
           '            # If SSH host is specified, use ssh mode regardless of transport\n'
           "            return 'ssh'\n"
           "        elif self.auth == 'none':\n            return 'local'\n",
           "        elif self.auth == 'none':\n            return 'local'\n"
           "        elif self.ssh_host or os.environ.get('RCAC_SSH_HOST'):\n"
           "            return 'ssh'\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[host-flag-over-auth-none]',
          'test_exec_mode.py::test_exec_mode_ladder[env-host-over-auth-none]'),
         'mode:'),
    # Each value of an explicit -e wins on its own; ignoring one lets the later rungs decide.
    Case('ladder-explicit-local-ignored', '__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.exec_mode != 'local':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-stdio]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-host]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-auth]'),
         'mode:'),
    Case('ladder-explicit-ssh-ignored', '__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.exec_mode != 'ssh':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-ssh-over-auth-none]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-ssh-over-auth]'),
         'mode:'),
    Case('ladder-explicit-delegate-ignored', '__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.exec_mode != 'delegate':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-stdio]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-host]'),
         'mode:'),
    # An explicit -e that yields to one later-rung input: auth none (delegate falls to an
    # unauthenticated local shell), RCAC_SSH_HOST, or auth oidc.
    Case('ladder-explicit-delegate-yields-to-auth-none', '__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and not (self.exec_mode == 'delegate' and self.auth == 'none'):\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-auth-none]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[delegate]'),
         'mode: resolved local, expected delegate'),
    Case('ladder-explicit-yields-to-env-host', '__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and not os.environ.get('RCAC_SSH_HOST'):\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-env-host]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-env-host]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[local]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[delegate]'),
         'mode: resolved ssh'),
    Case('ladder-explicit-yields-to-oidc', '__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.auth != 'oidc':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-oidc]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-ssh-over-oidc]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[local]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[ssh]'),
         'mode: resolved delegate'),
    # Rung 1 decides, but to the wrong mode: every explicit row, including those whose later rungs
    # agree with the explicit value, reads the mode it resolved.
    Case('ladder-explicit-misrouted', '__init__.py',
         (("        if self.exec_mode:\n            return self.exec_mode\n",
           "        if self.exec_mode:\n"
           "            return {'local': 'delegate', 'delegate': 'ssh', 'ssh': 'local'}[self.exec_mode]\n"),),
         tuple(f'test_exec_mode.py::test_exec_mode_ladder[explicit-{mode}-over-{later}]'
               for mode in ('local', 'ssh', 'delegate')
               for later in ('stdio', 'host', 'env-host', 'auth-none', 'auth', 'oidc'))
         + tuple(f'test_exec_mode.py::test_explicit_mode_decides_alone[{mode}]' for mode in ('local', 'ssh', 'delegate')),
         'mode: resolved'),
    Case('ladder-env-host-ignored', '__init__.py',
         (("        elif self.ssh_host or os.environ.get('RCAC_SSH_HOST'):\n", '        elif self.ssh_host:\n'),),
         ('test_exec_mode.py::test_exec_mode_ladder[env-host-over-auth-none]',),
         'mode:'),
    Case('ladder-local-widened', '__init__.py',
         (("        elif self.auth == 'none':\n            return 'local'\n        else:\n            return 'delegate'",
           "        else:\n            return 'local'"),),
         ('test_exec_mode.py::test_exec_mode_ladder[jwt-without-host]',
          'test_exec_mode.py::test_exec_mode_ladder[oidc-without-host]'),
         'mode:'),
    Case('delegate-gets-shared-middleware', '__init__.py',
         (("        if exec_mode == 'delegate':\n", "        if exec_mode == 'delegate' and False:\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[jwt-without-host]',),
         'middleware:'),
    # The secret floor: create_jwt_auth() and --generate-token each refuse an unset, empty or
    # 31-character JWT_SECRET on their own, so each floor is lowered separately.
    Case('floor-auth-31', 'auth.py',
         (('    if len(secret) < 32:\n', '    if len(secret) < 31:\n'),),
         ('test_tokens.py::test_jwt_auth_refuses_short_secret[31-chars]',),
         'DID NOT RAISE'),
    Case('floor-cli-31', '__init__.py',
         (('            if len(secret) < 32:\n', '            if len(secret) < 31:\n'),),
         ('test_tokens.py::test_generate_token_refuses_short_secret[31-chars]',),
         'status'),
    Case('auth-unset-secret-defaulted', 'auth.py',
         (("        raise ValueError('JWT_SECRET environment variable required for jwt auth mode')",
           "        secret = 'x' * 32"),),
         ('test_tokens.py::test_jwt_auth_refuses_short_secret[unset]',
          'test_tokens.py::test_jwt_auth_refuses_short_secret[empty]'),
         'DID NOT RAISE'),
    # Signer and verifier agree on issuer, audience, algorithm and lifetime: drifting either side
    # rejects the tokens the other mints.
    Case('verifier-audience-changed', 'auth.py',
         (('        audience=AUDIENCE,\n', "        audience=AUDIENCE + '-other',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted', 'test_tokens.py::test_cli_minted_token_is_accepted'),
         'error result'),
    Case('verifier-issuer-changed', 'auth.py',
         (('        issuer=ISSUER,\n', "        issuer=ISSUER + '-other',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted',),
         'error result'),
    Case('verifier-algorithm-changed', 'auth.py',
         (('        algorithm=ALGORITHM,\n', "        algorithm='HS512',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted',),
         'error result'),
    Case('signer-audience-changed', 'token.py',
         (("        'aud': AUDIENCE,\n", "        'aud': AUDIENCE + '-other',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted', 'test_tokens.py::test_cli_minted_token_is_accepted'),
         'error result'),
    Case('signer-token-expired', 'token.py',
         (("        'exp': now + timedelta(seconds=lifetime),\n", "        'exp': now - timedelta(seconds=lifetime),\n"),),
         ('test_tokens.py::test_minted_token_is_accepted',),
         'error result'),
    # The rejection half: a verifier that stops checking a claim accepts a token minted for
    # another audience or issuer.
    Case('verifier-audience-unchecked', 'auth.py',
         (('        audience=AUDIENCE,\n', '        audience=None,\n'),),
         ('test_tokens.py::test_mismatched_token_is_rejected[audience]',),
         'expected 401'),
    Case('verifier-issuer-unchecked', 'auth.py',
         (('        issuer=ISSUER,\n', '        issuer=None,\n'),),
         ('test_tokens.py::test_mismatched_token_is_rejected[issuer]',),
         'expected 401'),
)

# The runner's own controls (--self-check). A docstring edit changes no behaviour, so its target
# passes and the runner must call it a survivor; this proves the child really runs the targets.
SURVIVOR_CONTROL = Case(
    'control-docstring-only', 'context.py',
    (('"""Context management for request-scoped state."""',
      '"""Context management for request-scoped state (unchanged behaviour)."""'),),
    ('test_isolation.py::test_concurrent_delegate_calls_stay_isolated',),
    'ran as')


def apply(case: Case, dest: Path) -> Path:
    """Copy the imported package under `dest/src`, apply the case's edits, and return `dest/src`."""
    src_root = dest / 'src'
    package = src_root / 'rcac_mcp'
    shutil.copytree(Path(rcac_mcp.__file__).parent, package, ignore=shutil.ignore_patterns('__pycache__'))
    path = package / case.file
    text = path.read_text()
    for old, new in case.edits:
        count = text.count(old)
        if count != 1:
            raise ValueError(f'{case.id}: the anchor occurs {count} times in {case.file}, expected once; '
                             f'the code this case plants against has moved: {old[:80]!r}')
        text = text.replace(old, new)
    path.write_text(text)
    return src_root


def run_child(src_root: Path, targets: Sequence[str], junit: Path) -> subprocess.CompletedProcess[str]:
    """Run `targets` against the package under `src_root` in a sandboxed child pytest."""
    env = {**os.environ, 'PYTHONPATH': str(src_root), 'PYTHONDONTWRITEBYTECODE': '1'}
    return subprocess.run(
        [str(SANDBOX), 'sh', '-c', CHILD, 'sh', sys.executable, str(src_root), str(junit),
         *[f'tests/{target}' for target in targets]],
        env=env, capture_output=True, text=True, timeout=300)


def _node_id(case: ET.Element) -> str:
    # pytest writes classname "tests.test_x" and name "test_y[param]" for tests/test_x.py::test_y[param].
    module = case.get('classname', '').split('.')
    return '/'.join(module[1:-1] + [module[-1] + '.py']) + '::' + case.get('name', '')


def mutation_violations(returncode: int, junit_xml: str | None, targets: Sequence[str], why: str) -> list[str]:
    """Return every reason a child run does not prove the mutant was caught; empty means caught.

    The child must exit 1, and each target must hold a `<failure>` whose message or text carries
    `why`. Exit 0 means the mutant survived, 97 that the child imported something other than the
    mutated copy, anything else a harness failure.
    """
    violations: list[str] = []
    if returncode == 0:
        violations.append('the mutant survived: every target passed')
    elif returncode == WRONG_ORIGIN:
        violations.append('wrong import origin: the child did not import the mutated copy')
    elif returncode != 1:
        violations.append(f'harness failure: the child exited {returncode}')
    if junit_xml is None:
        violations.append('no JUnit report')
        return violations
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError as exc:
        violations.append(f'unreadable JUnit report: {exc}')
        return violations
    children: dict[str, list[ET.Element]] = {}
    for testcase in root.iter('testcase'):
        children.setdefault(_node_id(testcase), []).extend(testcase)
    for target in targets:
        if target not in children:
            violations.append(f'{target}: missing from the report')
            continue
        failures = [c for c in children[target] if c.tag == 'failure']
        if not failures:
            others = sorted({c.tag for c in children[target] if c.tag in ('error', 'skipped')})
            if others:
                violations.append(f'{target}: {" and ".join(others)}, not a failure')
            else:
                violations.append(f'{target}: passed, so the mutant survived it')
        elif not any(why in (f.get('message', '') + (f.text or '')) for f in failures):
            violations.append(f'{target}: killed for the wrong reason (no {why!r} in the failure)')
    return violations


def run_case(case: Case, src_override: Path | None = None) -> list[str]:
    """Plant `case` in a scratch copy, run its targets, and return `mutation_violations`."""
    with tempfile.TemporaryDirectory(prefix=f'mutant-{case.id}-') as scratch:
        dest = Path(scratch)
        src_root = apply(case, dest)
        junit = dest / 'junit.xml'
        child = run_child(src_override or src_root, case.targets, junit)
        report = junit.read_text() if junit.exists() else None
        violations = mutation_violations(child.returncode, report, case.targets, case.why)
        if violations and child.returncode not in (0, 1):
            violations.append(f'child stderr: {child.stderr.strip()[-400:]!r}')
        return violations


def self_check() -> list[str]:
    """Run the runner's controls; return a report line per control, failures prefixed `FAILED`."""
    lines = []
    survived = run_case(SURVIVOR_CONTROL)
    ok = any('survived' in v for v in survived)
    lines.append(f'{"control" if ok else "FAILED"}  surviving mutant reported: {survived}')
    with tempfile.TemporaryDirectory(prefix='mutant-origin-') as elsewhere:
        origin = run_case(SURVIVOR_CONTROL, src_override=Path(elsewhere))
    ok = any('wrong import origin' in v for v in origin)
    lines.append(f'{"control" if ok else "FAILED"}  wrong origin reported: {origin[:1]}')
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run planted violations against a copy of the package.')
    parser.add_argument('--self-check', action='store_true', help="also run the runner's own controls")
    parser.add_argument('cases', nargs='*', metavar='CASE_ID')
    args = parser.parse_args(argv)
    known = {case.id: case for case in CASES}
    failed = False
    for case_id in args.cases:
        case = known.get(case_id)
        if case is None:
            print(f'FAILED  {case_id}: no such case')
            failed = True
            continue
        violations = run_case(case)
        if violations:
            failed = True
            print(f'FAILED  {case.id}: {"; ".join(violations)}')
        else:
            print(f'killed  {case.id}: {", ".join(case.targets)} failed with {case.why!r}')
    if args.self_check:
        for line in self_check():
            failed = failed or line.startswith('FAILED')
            print(line)
    if not args.cases and not args.self_check:
        parser.error('name at least one case, or pass --self-check')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
