# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""cluster-mcp: an MCP server for HPC clusters, enabling agentic development on them."""


# Type annotations
from __future__ import annotations
from typing import List, Final

# Standard libs
import sys
import os
from functools import partial
from importlib.metadata import version as get_version
from platform import python_version, python_implementation

# External libs
from cmdkit.app import Application, exit_status
from cmdkit.cli import Interface
from cmdkit.logging import Logger, level_by_name, logging_styles

# Internal libs
from cluster_mcp.core.server import base_instructions, create_mcp_server
from cluster_mcp.core import probes
from cluster_mcp.core.capabilities import CapabilityLoadError, installed
from cluster_mcp.core import site as site_context
from cluster_mcp.core.site import DEFAULT_BUDGET
from cluster_mcp.core.executor.ssh import connect_failure_message
from cluster_mcp.core.startup import StartupFailure, answer_until_eof
from cluster_mcp.core.token import generate_token
from cluster_mcp.core.deprecation import env_setting, legacy_warning

# Public interface
__all__ = ['main', 'legacy_main', 'MCPServerApp', '__version__']
__version__ = get_version('cluster-mcp')
__website__ = 'https://github.com/PurdueRCAC/cluster-mcp'
__description__ = 'An MCP server for HPC clusters: shell, files, jobs and storage for AI agents.'

# Global logger
log = Logger.default(name=__name__, level=level_by_name['INFO'], **logging_styles['default'])


def print_exception(exc: Exception, status: int) -> int:
    """Log `exc` and return `status`."""
    log.critical(str(exc))
    return status


def exit_reported(exc: Exception, status: int) -> int:
    """Return `status` for a failure whose message was already reported."""
    return status


# Default configuration values
DEFAULT_HOST: Final[str] = 'localhost'
DEFAULT_PORT: Final[int] = 8000
DEFAULT_TRANSPORT: Final[str] = 'stdio'
DEFAULT_AUTH: Final[str] = 'none'
DEFAULT_LIFETIME: Final[int] = 3600
DEFAULT_EXEC_MODE: Final[str] = 'ssh'


APP_NAME = 'cluster-mcp'
APP_VERSION = f'cluster-mcp v{__version__} ({python_implementation()} {python_version()})'
APP_USAGE = f"""\
Usage:
  {APP_NAME} [-h] [-v] [-t TRANSPORT] [-H HOST] [-p PORT] [-a AUTH] [-e EXEC_MODE] [--ssh-host HOST]
             [--instructions-budget CHARS] [--skip-probes] [--generate-token] [--lifetime SECONDS]

  {__description__}\
"""

APP_HELP = f"""\
{APP_USAGE}

  cluster-mcp exposes an HPC cluster through the Model Context Protocol (MCP),
  enabling AI agents to run commands, move files, and manage jobs and storage
  on it.

  Transports:
    stdio     Standard I/O (default) - for local MCP clients
    sse       Server-Sent Events over HTTP - for web-based clients
    http      Streamable HTTP - for production deployments

  Authentication:
    none      No authentication (default) - for local development
    jwt       JWT with symmetric key (HS256) - requires JWT_SECRET env var
    oidc      OIDC proxy - requires OIDC_* env vars

  Execution Modes:
    ssh       Execute commands via SSH (default for stdio, or when --ssh-host is set)
    local     Execute commands locally under bash (default for http with auth=none)
    delegate  Execute commands as authenticated user via sudo (http with auth)

Options:
  -t, --transport   TRANSPORT   Transport protocol: stdio, sse, http (default: {DEFAULT_TRANSPORT}).
  -H, --host        HOST        Bind address for HTTP/SSE (default: {DEFAULT_HOST}).
  -p, --port        PORT        Port number for HTTP/SSE (default: {DEFAULT_PORT}).
  -a, --auth        AUTH        Authentication mode: none, jwt, oidc (default: {DEFAULT_AUTH}).
  -e, --exec-mode   MODE        Execution mode: ssh, local, delegate (default: auto).
      --ssh-host    HOST        SSH host to connect to (required for ssh mode).
      --instructions-budget CHARS
                                Most characters the served instructions may take (default: {DEFAULT_BUDGET}).
      --skip-probes             Serve every installed capability without probing the cluster for
                                the commands it needs (ssh and local modes probe by default).
      --generate-token          Generate a JWT token and exit (requires JWT_SECRET).
      --sub         SUBJECT     Subject identifier for token (username or user ID).
      --lifetime    SECONDS     Token lifetime in seconds (default: {DEFAULT_LIFETIME}).
  -v, --version                 Show version and exit.
  -h, --help                    Show this message and exit.

Environment Variables:
  JWT_SECRET                Shared secret for JWT signing (min 32 chars, required for jwt auth).
  OIDC_CONFIG_URL           OIDC provider discovery URL (required for oidc auth).
  OIDC_CLIENT_ID            OAuth client ID (required for oidc auth).
  OIDC_CLIENT_SECRET        OAuth client secret (required for oidc auth).
  MCP_BASE_URL              Public URL of this server (required for oidc auth).
  CLUSTER_MCP_SSH_HOST      Default SSH host (can be overridden with --ssh-host).
  CLUSTER_MCP_USER_MAP      Path to user mapping file for delegate mode.
  CLUSTER_MCP_INSTRUCTIONS_BUDGET
                            Default for --instructions-budget.
  CLUSTER_MCP_SKIP_PROBES   Any non-empty value, 0 included, does as --skip-probes; empty is unset.

Examples:
  {APP_NAME} --ssh-host login.cluster.edu         # SSH to cluster (stdio)
  {APP_NAME} -t http --ssh-host cluster.edu       # HTTP server with SSH execution
  {APP_NAME} -t http -e local                     # Local execution over HTTP
  {APP_NAME} -t http -a jwt -e delegate           # Delegate to auth user\
"""


class MCPServerApp(Application):
    """The cluster-mcp server application."""

    interface = Interface(APP_NAME, APP_USAGE, APP_HELP)
    interface.add_argument('-v', '--version', action='version', version=APP_VERSION)
    ALLOW_NOARGS = True  # Run application even when no arguments are given

    transport: str = DEFAULT_TRANSPORT
    interface.add_argument('-t', '--transport', default=transport,
                           choices=['stdio', 'sse', 'http'])

    host: str = DEFAULT_HOST
    interface.add_argument('-H', '--host', default=host)

    port: int = DEFAULT_PORT
    interface.add_argument('-p', '--port', type=int, default=port)

    auth: str = DEFAULT_AUTH
    interface.add_argument('-a', '--auth', default=auth,
                           choices=['none', 'jwt', 'oidc'])

    exec_mode: str | None = None
    interface.add_argument('-e', '--exec-mode', default=exec_mode,
                           choices=['ssh', 'local', 'delegate'])

    ssh_host: str | None = None
    interface.add_argument('--ssh-host', default=ssh_host)

    instructions_budget: int | None = None
    interface.add_argument('--instructions-budget', type=int, default=instructions_budget)

    skip_probes: bool = False
    interface.add_argument('--skip-probes', action='store_true', dest='skip_probes')

    generate_token_flag: bool = False
    interface.add_argument('--generate-token', action='store_true', dest='generate_token_flag')

    subject: str | None = None
    interface.add_argument('--sub', dest='subject', default=subject)

    lifetime: int = DEFAULT_LIFETIME
    interface.add_argument('--lifetime', type=int, default=lifetime)

    log_critical = log.critical
    log_exception = log.exception
    exceptions = {
        StartupFailure: partial(exit_reported, status=exit_status.runtime_error),
        ValueError: partial(print_exception, status=exit_status.bad_argument),
        RuntimeError: partial(print_exception, status=exit_status.runtime_error),
        Exception: partial(print_exception, status=exit_status.uncaught_exception),
    }

    def run(self) -> None:
        """Run the MCP server or generate token."""
        if self.generate_token_flag:
            secret = os.environ.get('JWT_SECRET')
            if not secret:
                raise ValueError('JWT_SECRET environment variable required for token generation')
            if len(secret) < 32:
                raise ValueError('JWT_SECRET must be at least 32 characters')
            print(generate_token(secret, self.lifetime, self.subject))
            return

        # Load every installed capability before the mode ladder: one that cannot load stops startup
        self._load_capabilities()

        # Determine execution mode
        exec_mode = self._resolve_exec_mode()
        log.info(f'Execution mode: {exec_mode}')

        # Create executor and middleware based on mode
        executor = None
        middlewares = []

        if exec_mode == 'delegate':
            # Delegate mode uses per-request executors via middleware
            from cluster_mcp.core.middleware import AuthExecutorMiddleware
            middlewares.append(AuthExecutorMiddleware(self.auth))
            log.info('Delegate mode: executor will be created per-request based on auth')
        else:
            # SSH and local modes use a shared executor via middleware
            from cluster_mcp.core.middleware import SharedExecutorMiddleware
            executor = self._create_executor(exec_mode)
            middlewares.append(SharedExecutorMiddleware(executor))

            if exec_mode == 'ssh':
                log.info(f'SSH connection established to {executor.hostname}')

        try:
            budget = self._resolve_budget()
            skipped = self._resolve_skip_probes()
            site = self._read_site(exec_mode, executor)
            # The budget must hold every installed capability's text, so whether it fits never
            # depends on what the cluster answers, and a budget that cannot fit refuses before any probe.
            site_context.compose(base_instructions(installed()), site, budget)
            served = self._served(self._probe(exec_mode, executor, skipped))
            mcp = create_mcp_server(self.auth, middlewares=middlewares, site=site, budget=budget,
                                    capabilities=served)
            if self.transport == 'stdio':
                mcp.run(transport='stdio')
            elif self.transport == 'sse':
                mcp.run(transport='sse', host=self.host, port=self.port)
            elif self.transport == 'http':
                mcp.run(transport='streamable-http', host=self.host, port=self.port)
        finally:
            # Clean up executor (if any)
            if executor:
                executor.close()

    def _load_capabilities(self) -> None:
        """Load every installed capability, or report the one that cannot load and refuse to start.

        The refusal takes the path a failed SSH connect takes: nothing is built, registered or served,
        and the message, `cannot load capability <distribution>: <cause>`, is reported as
        `_report_startup_failure` reports it, then the server exits `exit_status.runtime_error`.
        """
        try:
            installed()
        except CapabilityLoadError as exc:
            message = str(exc)
            self._report_startup_failure(message)
            raise StartupFailure(message) from exc

    def _resolve_exec_mode(self) -> str:
        """Determine execution mode from args or defaults."""
        if self.exec_mode:
            return self.exec_mode

        # Auto-select based on transport, auth, and ssh-host
        if self.transport == 'stdio':
            return 'ssh'
        elif self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]:
            # If SSH host is specified, use ssh mode regardless of transport
            return 'ssh'
        elif self.auth == 'none':
            return 'local'
        else:
            return 'delegate'

    def _resolve_budget(self) -> int:
        """The instructions budget: the flag, else CLUSTER_MCP_INSTRUCTIONS_BUDGET, else the default.

        A value from the environment is stripped, and an error names the variable it was read from.
        """
        budget = self.instructions_budget
        if budget is None:
            value, variable = env_setting('CLUSTER_MCP_INSTRUCTIONS_BUDGET')
            value = (value or '').strip()
            if not value:
                return DEFAULT_BUDGET
            try:
                budget = int(value)
            except ValueError:
                raise ValueError(f'{variable} must be a whole number of characters, not {value!r}') from None
        if budget <= 0:
            raise ValueError(f'the instructions budget must be over 0, not {budget}')
        return budget

    def _resolve_skip_probes(self) -> str | None:
        """What skips every probe: `--skip-probes`, else CLUSTER_MCP_SKIP_PROBES when it holds any
        non-empty value (never parsed, so `0` skips too); None when neither does."""
        if self.skip_probes:
            return '--skip-probes'
        value, variable = env_setting('CLUSTER_MCP_SKIP_PROBES')
        return variable if value else None

    def _probe(self, exec_mode: str, executor, skipped: str | None) -> probes.Pending:
        """Start probing every installed capability through the shared executor, once.

        In `delegate` mode, or when `skipped` names what skips it, nothing is probed: one line says so
        (the delegate line alone when both apply) and every installed capability is served.
        """
        loaded = installed()
        if exec_mode == 'delegate':
            log.info('Capability probes skipped in delegate mode: every installed capability is served')
            return probes.unprobed(loaded)
        if skipped:
            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')
            return probes.unprobed(loaded)
        return probes.start(executor, loaded)

    def _served(self, pending: probes.Pending) -> tuple:
        """The installed capabilities to serve, in load order, once the probe has answered or its
        deadline has passed: one line for each capability withheld, and one for each served without
        an answer."""
        served = []
        for verdict in pending.verdicts():
            name = verdict.loaded.distribution
            if not verdict.served:
                log.info(f'Capability {name} withheld: the cluster is {verdict.reason}')
                continue
            if verdict.reason:
                log.warning(f'Capability {name} served without a probe answer: the probe {verdict.reason}')
            served.append(verdict.loaded)
        return tuple(served)

    def _read_site(self, exec_mode: str, executor):
        """Read /etc/agents.d once: the cluster's over the executor in ssh mode, else this host's.

        In delegate mode the server reads for other accounts, so it keeps only what every account can read.
        """
        if exec_mode == 'ssh':
            return site_context.read_bounded(lambda: site_context.read_remote(executor), 'the cluster')
        for_others = exec_mode == 'delegate'
        return site_context.read_bounded(lambda: site_context.read_local(for_others=for_others), 'this host')

    def _create_executor(self, exec_mode: str):
        """Create executor based on mode."""
        from cluster_mcp.core.executor.ssh import SSHExecutor
        from cluster_mcp.core.executor.shell import LocalShellExecutor
        from cluster_mcp.core.executor.delegate import DelegatingExecutor, load_user_map

        if exec_mode == 'ssh':
            ssh_host = self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]
            if not ssh_host:
                raise ValueError(
                    'SSH host required: use --ssh-host or set CLUSTER_MCP_SSH_HOST'
                )
            try:
                return SSHExecutor(ssh_host)
            except Exception as exc:
                message = connect_failure_message(ssh_host, exc)
                self._report_startup_failure(message)
                raise StartupFailure(message) from exc

        elif exec_mode == 'local':
            return LocalShellExecutor()

        else:
            raise ValueError(f'Unknown exec mode: {exec_mode}')

    def _report_startup_failure(self, message: str) -> None:
        """Report why the server cannot start: on stderr at once, then, on stdio, to every request.

        A stdio client that discards stderr still sees the message, as the error answering each
        request it sends, until it closes the stream.
        """
        log.critical(message)
        if self.transport == 'stdio':
            answer_until_eof(sys.stdin, sys.stdout, message)


def main(argv: List[str] | None = None) -> int:
    """Entry point for the cluster-mcp server."""
    return MCPServerApp.main(argv or sys.argv[1:])


def legacy_main(argv: List[str] | None = None) -> int:
    """Entry point for the deprecated rcac-mcp command: one warning on stderr, then cluster-mcp."""
    legacy_warning('the rcac-mcp command', 'cluster-mcp')
    return main(argv)
