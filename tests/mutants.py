# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Planted violations: each contract test must go red against a copy of the package that breaks it.

Usage, from the repository root:

    uv run python tests/mutants.py [--self-check] CASE_ID...

Each `Case` copies the imported `cluster_mcp` namespace, every member's portion of it (never a
member's `src/` itself, and with no `cluster_mcp/__init__.py`), applies exact source edits that
break one contract, and runs the named target tests against the copy in a child pytest
under `bin/sandbox.sh`. A case may also plant into a repository file a test reads (one of
`REPO_FILES`: the README, the served-surface fixture); its child then runs in a copy of the
repository's tests, `bin/` and top-level files holding that plant, still under this
repository's `bin/sandbox.sh`. A case is caught only when every target fails (a JUnit `<failure>`, not an
`<error>` or a skip) and the failure carries the case's `why`: the fragment of the violation
message that names the broken contract. A mutant that merely breaks an import fails for the wrong
reason and counts as surviving.

This module is not collected: a child takes seconds, so the phase gates run it and its report is
recorded with the change. `test_mutations.py` keeps the fast parts in the suite: every anchor still
applies, and `mutation_violations` rejects each way a child can fail to prove a kill.

`--self-check` also runs the runner's own controls: a docstring-only edit must be reported as
surviving, and a child that does not import the mutated copy, or imports one member from outside
it, must be reported as a wrong origin.
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

import cluster_mcp.core
import cluster_mcp.rcac
import cluster_mcp.slurm

TESTS = Path(__file__).resolve().parent
SANDBOX = TESTS.parent / 'bin' / 'sandbox.sh'

# Exit status of the child when the mutated copy is not what it imports.
WRONG_ORIGIN = 97

# Every member's portion of the `cluster_mcp` namespace, by subpackage name. A case's `file` names
# its member first (`core/middleware.py`, `slurm/tools.py`, `rcac/tools.py`).
MEMBERS = {'core': cluster_mcp.core, 'slurm': cluster_mcp.slurm, 'rcac': cluster_mcp.rcac}

# The repository files outside the namespace a case may plant into (`repo_edits`), and what a
# repository copy for such a case holds besides `tests/` and `bin/`.
REPO_FILES = ('README.md', 'tests/fixtures/served_surface.json')
REPO_TOP = ('README.md', 'AGENTS.md', 'pyproject.toml')

# The child steps back into the repository, or a case's copy of it (the sandbox starts elsewhere), so
# pytest reads pyproject.toml, refuses to run unless every member of the `cluster_mcp` namespace
# resolves under the mutated copy (a portion missing from the copy would load, silently, from the
# editable install), then runs the targets with a JUnit report.
CHILD = """\
py=$1
root=$2
junit=$3
cd "$4" || exit 96
shift 4
"$py" -c 'import os, sys, importlib; root = os.path.realpath(sys.argv[1]) + os.sep; sys.exit(0 if all(os.path.realpath(importlib.import_module(f"cluster_mcp.{m}").__file__).startswith(root) for m in ("core", "slurm", "rcac")) else 97)' "$root" || exit 97
exec "$py" -m pytest -q -rA -p no:cacheprovider --junitxml="$junit" "$@"
"""


@dataclass(frozen=True)
class Case:
    """One planted violation.

    `file` is relative to the `cluster_mcp` namespace directory, its member first (`core/auth.py`); `edits` are exact `(old, new)` replacements, each
    `old` occurring once; `targets` are `tests/`-relative test ids that must fail; `why` is the
    fragment each target's failure must carry. `repo_edits` are `(path, old, new)` replacements in
    repository files, each path one of `REPO_FILES`, each `old` occurring once; a case that plants
    only there has an empty `file` and no `edits`.
    """

    id: str
    file: str
    edits: tuple[tuple[str, str], ...]
    targets: tuple[str, ...]
    why: str
    repo_edits: tuple[tuple[str, str, str], ...] = ()


PROCESS_GLOBAL = '''class _ProcessGlobal:
    value = None

    def get(self):
        return _ProcessGlobal.value

    def set(self, value):
        _ProcessGlobal.value = value


executor_var = _ProcessGlobal()'''

CONTEXT_VAR = "executor_var: ContextVar[Optional[Executor]] = ContextVar('executor', default=None)"

CLAIM_ORDER = "for claim in ('sub', 'email', 'preferred_username'):"

SUDO_PREFIX = "SUDO: Final = ('sudo', '-n', '-H', '-u')"

DELEGATE_PROGRAM = "        prog, marks = launch.program(command, cwd, start='home')\n"

TIMEOUT_ROWS = ('test_executors.py::test_timeout_returns_the_captured_output[local]',
                'test_executors.py::test_timeout_returns_the_captured_output[delegate]',
                'test_ssh_exec.py::test_timeout_returns_the_captured_output[bash]')

EXPLICIT_MODE = '        if self.exec_mode:\n'

BOUNDARY_ROWS = tuple(f'test_protocol.py::test_middleware_refusal_is_a_tool_error_result[{row}]'
                      for row in ('permission-memory', 'permission-http', 'runtime-memory', 'mcp-error-memory'))

STORAGE = 'test_storage_resource.py'

# The renamed environment variables, as the resolver's tests parametrize them.
ENV_NAMES = ('CLUSTER_MCP_SSH_HOST', 'CLUSTER_MCP_USER_MAP', 'CLUSTER_MCP_INSTRUCTIONS_BUDGET')

ERAS = ('legacy', 'modern')

# The schemes every resource read runs under: each test that reads a resource runs once per URI the
# resource is served under, its row id ending in the scheme.
SCHEMES = ('cluster', 'rcac')


def per_scheme(*ids: str, schemes: Sequence[str] = SCHEMES) -> tuple[str, ...]:
    """Each test id in `ids` (`file::test[params]`, or `file::test` for none), once per scheme in `schemes`."""
    return tuple(f'{i[:-1]}-{s}]' if i.endswith(']') else f'{i}[{s}]' for i in ids for s in schemes)


CONCURRENT_READS = per_scheme(*(f'{STORAGE}::test_concurrent_storage_reads_stay_isolated[{era}]' for era in ERAS))

TOKENLESS_READS = per_scheme(*(f'{STORAGE}::test_storage_read_without_token_{name}[{era}]'
                               for name in ('after_an_authenticated_read_fails',
                                            'while_an_authenticated_read_is_in_flight')
                               for era in ERAS))


def refused_reads(*rows: str, eras: Sequence[str] = ERAS, schemes: Sequence[str] = SCHEMES) -> tuple[str, ...]:
    """The storage read refusal rows `rows`, in `eras`, under `schemes`."""
    return per_scheme(*(f'{STORAGE}::test_storage_read_refused[{row}-{era}]' for row in rows for era in eras),
                      schemes=schemes)


# Every refusal the delegate middleware itself raises (not the tokenless row, which fails in the handler).
MIDDLEWARE_REFUSALS = ('no-claims', 'all-empty', 'unmapped', 'first-claim-unmapped')

UNKNOWN_REFUSED = tuple(f'{STORAGE}::test_unknown_uri_read_is_refused[{row}-{era}]'
                        for row in MIDDLEWARE_REFUSALS for era in ERAS)

# The generated neighbourhood of every served URI, read by an unmapped caller in the selected era (the
# sweeps run each case in both): the row a URI normaliser in the read hook's membership test fails,
# whatever shape it lets through.
def near_refused(uri: str) -> tuple[str, ...]:
    """The row reading the neighbourhood of the served `uri` as an unmapped caller."""
    return (f"{STORAGE}::test_near_open_read_is_refused[unmapped-{uri.replace('://', '-')}]",)


NEAR_REFUSED = near_refused('rcac://context')

NOT_FOUND = (*(f'{STORAGE}::test_unknown_uri_is_not_found[{era}]' for era in ERAS),
             *(f'{STORAGE}::test_unknown_uri_is_not_found_in_delegate_mode[{who}-{era}]'
               for who in ('mapped', 'no-token') for era in ERAS))

# The alias rows: each resource's alias read after its target, in every mode and both eras.
ALIAS_READS = tuple(f'{STORAGE}::test_alias_read_returns_target_content[{resource}-{mode}-{era}]'
                    for resource in ('context', 'storage') for mode in ('bare', 'shared', 'delegate') for era in ERAS)

MAPPED_READS = per_scheme(*(f'{STORAGE}::test_storage_read_runs_as_the_mapped_user[{era}]' for era in ERAS))

SEQUENTIAL_READS = per_scheme(*(f'{STORAGE}::test_sequential_storage_reads_each_get_their_executor[{era}]'
                                for era in ERAS))

DELEGATE_NOT_FOUND = tuple(f'{STORAGE}::test_unknown_uri_is_not_found_in_delegate_mode[{who}-{era}]'
                           for who in ('mapped', 'no-token') for era in ERAS)

# The delegate read hook's membership test, which every URI-shape case replaces.
OPEN_TEST = '        if context.message.uri not in OPEN_RESOURCES:\n'

URLLIB = "__import__('urllib.parse', fromlist=['urlsplit', 'unquote'])"

# The alias derivation (`legacy_aliases`, which the core and the RCAC capability both call), the
# core's alias line and the open set's, which the alias cases plant against.
DERIVATION = "    return [{**entry, 'uri': entry['uri'].replace('cluster://', 'rcac://', 1)} for entry in entries]\n"
ALIAS_LINE = 'RESOURCE_REGISTRY += legacy_aliases(list(RESOURCE_REGISTRY))\n'
OPEN_SET = ("OPEN_RESOURCES: Final[frozenset[str]] = frozenset(\n"
            "    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])\n")


def resolves_if(condition: str) -> tuple[tuple[str, str], ...]:
    """Replace the read hook's membership test: resolve identity only where `condition` holds of `u`, the URI read."""
    return ((OPEN_TEST, f'        if (lambda u: {condition})(context.message.uri):\n'),)


def let_through(uri: str) -> str:
    """The failure fragment naming `uri`, a URI not exactly open, as a refused caller's read let through."""
    return f'reading {uri!r} ('


def open_to_refused(schemes: Sequence[str] = SCHEMES) -> tuple[str, ...]:
    """The context reads in `delegate` mode by a caller a tool call refuses, under `schemes`."""
    return per_scheme(*(f'test_context.py::test_any_client_reads_the_context_in_delegate_mode[{who}-{era}]'
                        for who in ('no-claim', 'unmapped') for era in ERAS), schemes=schemes)


OPEN_TO_REFUSED = open_to_refused()


def read_boundary_rows(*rows: str) -> tuple[str, ...]:
    """The read boundary rows `rows` of `test_protocol.py`, in both eras."""
    return per_scheme(*(f'test_protocol.py::test_middleware_refusal_is_a_read_error[{row}-{era}]'
                        for row in rows for era in ERAS))


# The read boundary rows whose exception is not already an MCPError, so a read hook that lets it
# through unconverted changes what the client sees.
CONVERTED_READS = read_boundary_rows('permission-memory', 'permission-http', 'runtime-memory', 'runtime-http',
                                     'other-memory')

READ_HOOK = ('        return await _bounded(context, call_next, ResourceError, (FastMCPError, NotFoundError, DisabledError))\n')


def read_hook_raising(text: str) -> str:
    """The read boundary written out inline, raising `ResourceError(<text>)` for a converted exception."""
    return ('        try:\n'
            '            return await call_next(context)\n'
            '        except (FastMCPError, NotFoundError, DisabledError):\n'
            '            raise\n'
            '        except Exception as exc:\n'
            f'            raise ResourceError({text}) from exc\n')


OIDC_ROWS = tuple(f'test_auth_modes.py::test_oidc_requires_all_four[{variable}-{how}]'
                  for variable in ('OIDC_CONFIG_URL', 'OIDC_CLIENT_ID', 'OIDC_CLIENT_SECRET', 'MCP_BASE_URL')
                  for how in ('unset', 'empty'))

# Every test that reads the deprecation window from a warning, each comparing it with the window
# written out: the command's (each argv, and on stdio), each variable's, honoured or ignored.
COMMAND_WARNED = tuple(f'test_cli.py::test_legacy_command_warns_then_runs_cluster_mcp[{argv}]'
                       for argv in ('none', 'help', 'version', 'bogus'))
VARIABLE_WARNED = {shape: tuple(f'test_env.py::test_warning_names_replacement_and_window[{name}-{shape}]'
                                for name in ENV_NAMES) for shape in ('honoured', 'ignored')}

README_TEST = 'test_deprecation_window.py::test_readme_states_each_deprecation_and_the_window'

# README's upgrade section, whole, and its table's rows.
UPGRADING_SECTION = (
    '## Upgrading from rcac-mcp\n\nIn 0.2.0 the server was renamed from `rcac-mcp` to `cluster-mcp`. Each old name is\n'
    'deprecated in 0.2.0, removed no earlier than 0.4.0, and keeps working until it is removed:\n\n'
    '| Deprecated | Replacement |\n|---|---|\n'
    '| the `rcac-mcp` command | `cluster-mcp` |\n'
    '| `RCAC_SSH_HOST`, `RCAC_USER_MAP`, `RCAC_INSTRUCTIONS_BUDGET` | `CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP`, '
    '`CLUSTER_MCP_INSTRUCTIONS_BUDGET` |\n'
    '| the `rcac://context` and `rcac://storage` resources | `cluster://context` and `cluster://storage` |\n\n'
    'The command and each old variable print a warning on stderr naming the replacement and the window.\n'
    'When an old and a new variable are both set, the new one wins, and the warning says the old one is\n'
    'ignored. An `rcac://` URI returns the same content as its `cluster://` replacement. The install\n'
    'line earlier releases documented keeps working through the window too: it installs a compatibility\n'
    'distribution that carries every capability (`cluster-mcp[slurm,rcac]`) and runs the deprecated\n'
    '`rcac-mcp` command. Update your MCP client\n'
    'configuration to the Quick Start form above.\n\n')
COMMAND_ROW = '| the `rcac-mcp` command | `cluster-mcp` |\n'
VARIABLES_ROW = ('| `RCAC_SSH_HOST`, `RCAC_USER_MAP`, `RCAC_INSTRUCTIONS_BUDGET` | `CLUSTER_MCP_SSH_HOST`, '
                 '`CLUSTER_MCP_USER_MAP`, `CLUSTER_MCP_INSTRUCTIONS_BUDGET` |\n')
RESOURCES_ROW = '| the `rcac://context` and `rcac://storage` resources | `cluster://context` and `cluster://storage` |\n'


# A row giving `RCAC_SSH_HOST` a replacement the server never reads; the window sentence's words.
CONTRADICTING_ROW = '| `RCAC_SSH_HOST` | `CLUSTER_SSH_HOST` |\n'
WINDOWED = 'removed no earlier than 0.4.0, and keeps'

# The same contradicting pairing in each other form a reader sees as a table row, and the upgrade
# section's last line, after which a plant adds a paragraph or a sentence.
UNREAD_ROWS = {
    'plain': '| RCAC_SSH_HOST | CLUSTER_SSH_HOST |\n',
    'bold': '| **RCAC_SSH_HOST** | **CLUSTER_SSH_HOST** |\n',
    'escaped': '| RCAC\\_SSH\\_HOST | CLUSTER\\_SSH\\_HOST |\n',
    'html-code': '| <code>RCAC_SSH_HOST</code> | <code>CLUSTER_SSH_HOST</code> |\n',
    'three-cells': '| `RCAC_SSH_HOST` | `CLUSTER_SSH_HOST` | |\n',
    'no-leading-pipe': '`RCAC_SSH_HOST` | `CLUSTER_SSH_HOST`\n',
}
UPGRADING_END = 'configuration to the Quick Start form above.\n'


def upgrading_paragraph(text: str) -> tuple[tuple[str, str, str], ...]:
    """A README plant adding the paragraph `text` at the upgrade section's end."""
    return readme(UPGRADING_END, f'{UPGRADING_END}\n{text}\n')


def upgrading_sentence(text: str) -> tuple[tuple[str, str, str], ...]:
    """A README plant adding the sentence `text` to the upgrade section's last paragraph."""
    return readme(UPGRADING_END, f'{UPGRADING_END[:-1]} {text}\n')


# The capability load's one exit for a failure: the registry cut back, then a refusal or an interrupt
# raised as it is, anything else refused naming the capability.
ROLLBACK = ('    except BaseException as exc:\n'
            '        del TOOL_REGISTRY[start:]\n'
            '        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n'
            '            raise\n'
            '        raise CapabilityLoadError(distribution, _cause(exc)) from exc\n')

# The member sets the capability loader's rows run beside, as `test_capabilities.MEMBER_SETS` names them.
MEMBER_SETS = ('core-only', 'slurm', 'rcac', 'both')
CAPABILITIES = 'test_capabilities.py'
REFUSED_AT_LOAD = f'{CAPABILITIES}::test_what_a_server_would_refuse_is_refused_at_load'
MALFORMED = f'{CAPABILITIES}::test_a_malformed_capability_is_refused_as_such'
LISTING = f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused'
TOOL_TAKEN = f'{CAPABILITIES}::test_a_tool_name_already_taken_is_refused'
URI_TAKEN = f'{CAPABILITIES}::test_a_resource_uri_already_taken_is_refused'


def every_set(test: str, *cases: str) -> tuple[str, ...]:
    """`test`'s row for each case in `cases` (none: the test takes only the set) beside every member set."""
    return tuple(f'{test}[{case}-{names}]' if case else f'{test}[{names}]'
                 for case in (cases or ('',)) for names in MEMBER_SETS)


# The three files the capability sweep mutates every decision of, and the startup tests it kills with.
LOADER, CLI, TOOLS = 'core/capabilities.py', 'core/__init__.py', 'core/tools/__init__.py'
STARTUP = 'test_startup.py'


def alternative(case_id: str, file: str, edits: tuple[tuple[str, str], ...], test: str, kind: str, why: str) -> Case:
    """A case killed by `test`'s row for `kind` (or its only row) beside every member set."""
    return Case(case_id, file, edits, every_set(test, kind), why)


def partition_alternative(case_id: str, file: str, edits: tuple[tuple[str, str], ...], test: str, kind: str,
                          why: str) -> Case:
    """A case killed by `test`'s row beside each member set but the core alone."""
    return Case(case_id, file, edits, tuple(row for row in every_set(test, kind) if not row.endswith('[core-only]')), why)


def readme(old: str, new: str) -> tuple[tuple[str, str, str], ...]:
    """One README plant."""
    return (('README.md', old, new),)


# Tool annotations: the decorator's registration line, a `ToolAnnotations` built where it is planted,
# and the served-surface fixture's `run_command` entry, where a plant records annotations as if 0.1.4
# had served them.
REGISTER = '    tool = Tool.from_function(func, description=inspect.getdoc(func))\n'
ANNOTATIONS = "__import__('mcp.types', fromlist=['ToolAnnotations']).ToolAnnotations"
SURFACE = 'tests/fixtures/served_surface.json'
RUN_COMMAND_ENTRY = '  "run_command": {\n   "description":'
SURFACE_TEST = ('test_surface.py::test_served_surface_matches_baseline',)


def titled(title: str) -> tuple[tuple[str, str], ...]:
    """The decorator registering each tool with top-level title `title` (an expression over `func`)."""
    return ((REGISTER, f'    tool = Tool.from_function(func, description=inspect.getdoc(func), title={title})\n'),)


def annotate(condition: str, hints: str) -> tuple[tuple[str, str], ...]:
    """The decorator registering each tool for which `condition` holds with annotations `hints`."""
    return ((REGISTER, f'    tool = Tool.from_function(func, description=inspect.getdoc(func), '
                       f'annotations={ANNOTATIONS}({hints}) if {condition} else None)\n'),)


def recorded(hints: str) -> tuple[tuple[str, str, str], ...]:
    """The fixture recording `run_command` as served with annotations `hints` (JSON)."""
    return ((SURFACE, RUN_COMMAND_ENTRY, f'  "run_command": {{\n   "annotations": {hints},\n   "description":'),)


CASES: tuple[Case, ...] = (
    # Per-request isolation: the executor lives in a ContextVar and is built per call.
    Case('isolation-module-global', 'core/context.py',
         ((CONTEXT_VAR, PROCESS_GLOBAL),),
         ('test_isolation.py::test_concurrent_delegate_calls_stay_isolated',
          'test_isolation.py::test_concurrent_shared_servers_stay_isolated', *CONCURRENT_READS),
         'ran as'),
    Case('isolation-executor-cached', 'core/middleware.py',
         (('        executor = DelegatingExecutor(identity, self._user_map)\n',
           "        executor = getattr(self, '_cached', None) or DelegatingExecutor(identity, self._user_map)\n"
           '        self._cached = executor\n'),),
         ('test_isolation.py::test_concurrent_delegate_calls_stay_isolated', *CONCURRENT_READS),
         'ran as'),
    # Each executor middleware sets the executor on every call; set once, the later calls of the
    # same server find none.
    Case('shared-middleware-sets-first-call-only', 'core/middleware.py',
         (('        set_executor(self._executor)\n',
           "        if not getattr(self, '_set_once', False):\n"
           '            set_executor(self._executor)\n'
           '            self._set_once = True\n'),),
         ('test_isolation.py::test_sequential_shared_calls_each_get_the_executor',),
         'ran 0 times'),
    # A resource read gets its request's executor as a tool call does: the shared middleware sets it
    # for each read too, and the handler reaches it through the undecorated storage helper.
    Case('shared-read-sets-no-executor', 'core/middleware.py',
         (('    async def on_read_resource(self, context: MiddlewareContext, call_next):\n'
           '        """Set the shared executor for this resource read, then run the rest of the chain."""\n'
           '        self._install()\n',
           '    async def on_read_resource(self, context: MiddlewareContext, call_next):\n'
           '        """Set the shared executor for this resource read, then run the rest of the chain."""\n'),),
         per_scheme(*(f'test_storage_resource.py::test_storage_read_{name}[{era}]'
                      for name in ('runs_on_the_shared_executor', 'runs_the_local_executor')
                      for era in ('legacy', 'modern'))),
         'No executor configured'),
    Case('resource-calls-decorated-tool', 'rcac/resources.py',
         (('    from cluster_mcp.rcac.tools import resolve_storage_paths\n\n    paths = resolve_storage_paths()\n',
           '    from cluster_mcp.rcac.tools import storage_paths\n\n    paths = storage_paths()\n'),),
         per_scheme('test_storage_resource.py::test_storage_read_runs_on_the_shared_executor[legacy]',
                    'test_storage_resource.py::test_storage_read_runs_on_the_shared_executor[modern]'),
         'not callable'),
    Case('auth-middleware-sets-first-call-only', 'core/middleware.py',
         (('        executor = DelegatingExecutor(identity, self._user_map)\n        set_executor(executor)\n',
           '        executor = DelegatingExecutor(identity, self._user_map)\n'
           "        if not getattr(self, '_set_once', False):\n"
           '            set_executor(executor)\n'
           '            self._set_once = True\n'),),
         ('test_isolation.py::test_sequential_delegate_calls_each_get_their_executor', *SEQUENTIAL_READS),
         'ran 0 times'),
    # A delegate-mode read is resolved and refused by the path a tool call takes, except a read of a
    # resource that runs nothing, which answers any client; a tokenless read finds no executor, never
    # one an earlier read installed.
    Case('auth-read-sets-no-executor', 'core/middleware.py',
         (('        if context.message.uri not in OPEN_RESOURCES:\n            await self._install(context)\n', ''),),
         (*MAPPED_READS, *refused_reads('unmapped')),
         'No executor configured'),
    # The read hook refuses by default: every URI outside OPEN_RESOURCES is resolved, an unknown one
    # included, and only the open set skips it; the hook resolves before the handler runs and
    # returns what the handler returned.
    Case('read-hook-resolves-storage-only', 'core/middleware.py',
         (('        if context.message.uri not in OPEN_RESOURCES:\n', "        if context.message.uri == 'cluster://storage':\n"),),
         UNKNOWN_REFUSED,
         'refused read: error'),
    Case('read-hook-ignores-open-set', 'core/middleware.py',
         (('        if context.message.uri not in OPEN_RESOURCES:\n', '        if True:\n'),),
         OPEN_TO_REFUSED,
         '(error=True)'),
    # The open set holds both context URIs, so a test of equality with one of them refuses the other.
    Case('read-hook-open-by-equality', 'core/middleware.py',
         ((OPEN_TEST, "        if context.message.uri != 'cluster://context':\n"),),
         open_to_refused(('rcac',)),
         '(error=True)'),
    Case('read-hook-open-set-inverted', 'core/middleware.py',
         (('        if context.message.uri not in OPEN_RESOURCES:\n', '        if context.message.uri in OPEN_RESOURCES:\n'),),
         MAPPED_READS,
         'No executor configured'),
    Case('read-hook-installs-after-handler', 'core/middleware.py',
         (('        if context.message.uri not in OPEN_RESOURCES:\n            await self._install(context)\n'
           '        return await call_next(context)\n',
           '        result = await call_next(context)\n'
           '        if context.message.uri not in OPEN_RESOURCES:\n            await self._install(context)\n'
           '        return result\n'),),
         MAPPED_READS,
         'No executor configured'),
    Case('read-hook-drops-result', 'core/middleware.py',
         (('            await self._install(context)\n        return await call_next(context)\n',
           '            await self._install(context)\n        await call_next(context)\n'),),
         MAPPED_READS,
         'the read failed'),
    # The read hook's membership test is the exact string the client sent: a URI that only looks like
    # an open one (a prefix, suffix or substring of it, a case, slash, space, query, encoding or scheme
    # variant) is resolved like any read that may run commands, so a refused caller is refused.
    Case('read-hook-open-by-prefix', 'core/middleware.py',
         ((OPEN_TEST, '        if not context.message.uri.startswith(tuple(OPEN_RESOURCES)):\n'),),
         UNKNOWN_REFUSED,
         let_through('rcac://contextual')),
    Case('read-hook-rcac-scheme-only', 'core/middleware.py',
         ((OPEN_TEST, "        if context.message.uri.startswith('rcac://') and context.message.uri not in OPEN_RESOURCES:\n"),),
         UNKNOWN_REFUSED,
         let_through('file:///nope')),
    Case('read-hook-cluster-scheme-only', 'core/middleware.py',
         ((OPEN_TEST, "        if context.message.uri.startswith('cluster://') and context.message.uri not in OPEN_RESOURCES:\n"),),
         UNKNOWN_REFUSED,
         let_through('rcac://nope')),
    Case('read-hook-open-by-suffix', 'core/middleware.py',
         resolves_if('not u.endswith(tuple(OPEN_RESOURCES))'),
         UNKNOWN_REFUSED,
         let_through('xrcac://context')),
    Case('read-hook-open-by-substring', 'core/middleware.py',
         resolves_if('not any(o in u for o in OPEN_RESOURCES)'),
         UNKNOWN_REFUSED,
         let_through(' rcac://context')),
    Case('read-hook-open-within-open-uri', 'core/middleware.py',
         resolves_if('not any(u in o for o in OPEN_RESOURCES)'),
         UNKNOWN_REFUSED,
         let_through('rcac://contex')),
    Case('read-hook-open-if-prefix-of-open', 'core/middleware.py',
         resolves_if('not any(o.startswith(u) for o in OPEN_RESOURCES)'),
         UNKNOWN_REFUSED,
         let_through('rcac://contex')),
    Case('read-hook-open-by-host', 'core/middleware.py',
         resolves_if(f'{URLLIB}.urlsplit(u).netloc not in {{{URLLIB}.urlsplit(o).netloc for o in OPEN_RESOURCES}}'),
         UNKNOWN_REFUSED,
         let_through('rcac://context/x')),
    Case('read-hook-case-folded', 'core/middleware.py',
         resolves_if('u.lower() not in OPEN_RESOURCES'),
         UNKNOWN_REFUSED,
         let_through('rcac://CONTEXT')),
    Case('read-hook-casefolded', 'core/middleware.py',
         resolves_if('u.casefold() not in OPEN_RESOURCES'),
         UNKNOWN_REFUSED,
         let_through('RCAC://context')),
    Case('read-hook-scheme-case-folded', 'core/middleware.py',
         resolves_if("u.partition(':')[0].lower() + ''.join(u.partition(':')[1:]) not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         let_through('RCAC://context')),
    Case('read-hook-strips-trailing-slash', 'core/middleware.py',
         resolves_if("u.rstrip('/') not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         let_through('rcac://context/')),
    Case('read-hook-strips-space', 'core/middleware.py',
         resolves_if('u.strip() not in OPEN_RESOURCES'),
         UNKNOWN_REFUSED,
         let_through('rcac://context ')),
    Case('read-hook-strips-leading-space', 'core/middleware.py',
         resolves_if('u.lstrip() not in OPEN_RESOURCES'),
         UNKNOWN_REFUSED,
         let_through(' rcac://context')),
    Case('read-hook-drops-query-and-fragment', 'core/middleware.py',
         resolves_if("u.split('#')[0].split('?')[0] not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         let_through('rcac://context?x=1')),
    Case('read-hook-authority-only', 'core/middleware.py',
         resolves_if(f"'{{0}}://{{1}}'.format(*{URLLIB}.urlsplit(u)) not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         let_through('rcac://context#f')),
    Case('read-hook-ignores-scheme', 'core/middleware.py',
         resolves_if("u.partition('://')[2] not in {o.partition('://')[2] for o in OPEN_RESOURCES}"),
         UNKNOWN_REFUSED,
         let_through('xrcac://context')),
    Case('read-hook-defaults-scheme', 'core/middleware.py',
         resolves_if("(u if '://' in u else 'rcac://' + u) not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         let_through('context')),
    Case('read-hook-adds-authority-slashes', 'core/middleware.py',
         resolves_if("(u if '://' in u else u.replace(':', '://', 1)) not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         let_through('rcac:context')),
    Case('read-hook-unquotes', 'core/middleware.py',
         resolves_if(f'{URLLIB}.unquote(u) not in OPEN_RESOURCES'),
         UNKNOWN_REFUSED,
         let_through('rcac://%63ontext')),
    Case('read-hook-nfkc-normalised', 'core/middleware.py',
         resolves_if("__import__('unicodedata').normalize('NFKC', u) not in OPEN_RESOURCES"),
         UNKNOWN_REFUSED,
         '(the open URI, a letter full-width)'),
    Case('open-set-holds-slash-variants', 'core/resources.py',
         (("    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])",
           "    uri for entry in RESOURCE_REGISTRY if not entry['executor'] for uri in (entry['uri'], entry['uri'] + '/'))"),),
         UNKNOWN_REFUSED,
         let_through('rcac://context/')),
    # URI normalisers that change only shapes one edit, a wrapper or a suffix away from a served URI:
    # each maps such a shape onto the open URI, so a refused caller's read of it is let through, and
    # only the generated neighbourhood (`NEAR_OPEN`) reaches it.
    Case('read-hook-strips-crlf', 'core/middleware.py',
         resolves_if("u.strip('\\r\\n') not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('rcac://context\n')),
    Case('read-hook-strips-trailing-query-or-fragment-mark', 'core/middleware.py',
         resolves_if("u.rstrip('?#') not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('rcac://context?')),
    Case('read-hook-drops-port', 'core/middleware.py',
         resolves_if("__import__('re').sub(r':[0-9]*$', '', u) not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('rcac://context:80')),
    Case('read-hook-drops-userinfo', 'core/middleware.py',
         resolves_if("__import__('re').sub(r'(?<=://)[^/@]*@', '', u, count=1) not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('rcac://u@context')),
    Case('read-hook-strips-trailing-dot', 'core/middleware.py',
         resolves_if("u.rstrip('.') not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('rcac://context.')),
    Case('read-hook-removes-tab-and-newline', 'core/middleware.py',
         resolves_if('u.translate({9: None, 10: None, 13: None}) not in OPEN_RESOURCES'),
         NEAR_REFUSED,
         let_through('rcac://con\ttext')),
    Case('read-hook-strips-leading-slash', 'core/middleware.py',
         resolves_if("u.lstrip('/') not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('/rcac://context')),
    Case('read-hook-strips-quotes-and-brackets', 'core/middleware.py',
         resolves_if("u.strip('<>' + chr(34) + chr(39)) not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('<rcac://context>')),
    Case('read-hook-strips-trailing-nul', 'core/middleware.py',
         resolves_if('u.rstrip(chr(0)) not in OPEN_RESOURCES'),
         NEAR_REFUSED,
         let_through('rcac://context\x00')),
    Case('read-hook-drops-dot-segment', 'core/middleware.py',
         resolves_if("__import__('re').sub(r'/\\.(?=/|$)', '', u) not in OPEN_RESOURCES"),
         NEAR_REFUSED,
         let_through('rcac://context/.')),
    Case('read-hook-any-normaliser', 'core/middleware.py',
         resolves_if("all(f(u) not in OPEN_RESOURCES for f in (lambda v: v, lambda v: v.strip('\\r\\n'), "
                     "lambda v: v.rstrip('?#'), lambda v: __import__('re').sub(r':[0-9]*$', '', v), "
                     "lambda v: __import__('re').sub(r'(?<=://)[^/@]*@', '', v, count=1), lambda v: v.rstrip('.'), "
                     "lambda v: v.translate({9: None, 10: None, 13: None}), lambda v: v.lstrip('/'), "
                     "lambda v: v.strip('<>' + chr(34) + chr(39)), lambda v: v.rstrip(chr(0)), "
                     "lambda v: __import__('re').sub(r'/\\.(?=/|$)', '', v)))"),
         NEAR_REFUSED,
         let_through('rcac://context#')),
    Case('open-set-holds-query-variants', 'core/resources.py',
         (("    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])",
           "    uri for entry in RESOURCE_REGISTRY if not entry['executor'] for uri in (entry['uri'], entry['uri'] + '?'))"),),
         NEAR_REFUSED,
         let_through('rcac://context?')),
    # The other side: a caller the hook does not refuse still gets the protocol's not-found for every
    # such shape, so the hook refuses by identity, never by what the URI looks like.
    Case('read-hook-refuses-unserved', 'core/middleware.py',
         ((OPEN_TEST,
           "        if context.message.uri not in {e['uri'] for e in __import__('cluster_mcp.core.resources', "
           "fromlist=['RESOURCE_REGISTRY']).RESOURCE_REGISTRY}:\n"
           "            raise PermissionError('Unknown resource.')\n" + OPEN_TEST),),
         DELEGATE_NOT_FOUND,
         let_through('RCAC://storage')),
    # A tokenless request is let through with nothing set, never refused in the middleware: a read of
    # a URI the server does not serve is still not found.
    Case('no-token-refused-in-middleware', 'core/middleware.py',
         (("            # No auth - this shouldn't happen in delegate mode\n"
           '            # but let the request proceed (will fail at executor access)\n'
           '            return\n',
           "            raise RuntimeError('No executor configured. Set executor via set_executor() first.')\n"),),
         tuple(f'{STORAGE}::test_unknown_uri_is_not_found_in_delegate_mode[no-token-{era}]' for era in ERAS),
         'expected -32602'),
    # The storage resource is the RCAC capability's, so the core's open set alone decides that it is
    # resolved: a capability resource marked open is refused at load, never served open.
    Case('storage-read-left-open', 'core/resources.py',
         ((OPEN_SET, OPEN_SET.replace("if not entry['executor'])",
                                      "if not entry['executor']) | {'cluster://storage', 'rcac://storage'}")),),
         refused_reads('unmapped', 'first-claim-unmapped'),
         'not authorized'),
    Case('context-read-closed', 'core/resources.py',
         (("    entry['uri'] for entry in RESOURCE_REGISTRY if not entry['executor'])",
           "    entry['uri'] for entry in RESOURCE_REGISTRY if False)"),),
         OPEN_TO_REFUSED,
         '(error=True)'),
    # Each deprecated rcac:// alias is derived from its cluster:// target before the open set is: it
    # keeps the target's executor flag and handler, it exists, and the open set holds it when it
    # holds its target. The storage alias is the RCAC capability's, so only the core's open set can
    # open it.
    Case('alias-flag-hand-set-open', 'core/resources.py',
         ((OPEN_SET, OPEN_SET.replace("if not entry['executor'])", "if not entry['executor']) | {'rcac://storage'}")),),
         refused_reads('unmapped', 'first-claim-unmapped', schemes=('rcac',)),
         'not authorized'),
    Case('alias-flag-hand-set-closed', 'core/resources.py',
         ((DERIVATION, DERIVATION.replace("1)}", "1), 'executor': True}")),),
         open_to_refused(('rcac',)),
         '(error=True)'),
    Case('open-set-before-aliases', 'core/resources.py',
         ((ALIAS_LINE, ''), (OPEN_SET, OPEN_SET + ALIAS_LINE)),
         open_to_refused(('rcac',)),
         '(error=True)'),
    Case('open-set-target-scheme-only', 'core/resources.py',
         ((OPEN_SET, OPEN_SET.replace("if not entry['executor'])", "if not entry['executor'] and entry['uri'].startswith('cluster://'))")),),
         open_to_refused(('rcac',)),
         '(error=True)'),
    Case('alias-handler-differs', 'core/resources.py',
         ((DERIVATION, DERIVATION.replace("1)}", "1), 'handler': lambda: 'not the target'}")),),
         ALIAS_READS,
         'reading the alias'),
    Case('alias-missing', 'core/resources.py',
         ((DERIVATION, '    return []\n'),),
         ALIAS_READS,
         'code=-32602'),
    Case('read-no-token-reuses-last-executor', 'core/middleware.py',
         (('        if context.message.uri not in OPEN_RESOURCES:\n            await self._install(context)\n',
           '        if context.message.uri not in OPEN_RESOURCES:\n'
           "            if get_access_token() is None and getattr(self, '_last', None) is not None:\n"
           '                set_executor(self._last)\n'
           '            else:\n'
           '                await self._install(context)\n'
           "                self._last = __import__('cluster_mcp.core.context', fromlist=['executor_var']).executor_var.get()\n"),),
         TOKENLESS_READS,
         'not an error'),
    # The tool surface: tools reach the cluster only through get_executor(), never an executor of
    # their own.
    Case('tool-builds-local-executor', 'slurm/tools.py',
         (("    executor = get_executor()\n\n    argv = ['sinfo']\n",
           "    executor = __import__('cluster_mcp.core.executor.shell', fromlist=['LocalShellExecutor']).LocalShellExecutor()\n\n"
           "    argv = ['sinfo']\n"),),
         ('test_tools.py::test_tool_reaches_only_the_installed_executor[sinfo]',),
         'launched outside the executor'),
    Case('tool-builds-ssh-executor', 'rcac/tools.py',
         (("    executor = get_executor()\n    result = executor.run(['myquota'])",
           "    executor = __import__('cluster_mcp.core.executor.ssh', fromlist=['SSHExecutor']).SSHExecutor('cluster.invalid')\n"
           "    result = executor.run(['myquota'])"),),
         ('test_tools.py::test_tool_reaches_only_the_installed_executor[myquota]',),
         'launched outside the executor'),
    # No executor set: get_executor() raises, with no fallback, and nothing set at construction or
    # by another request reaches this one.
    Case('no-executor-module-global', 'core/context.py',
         ((CONTEXT_VAR, PROCESS_GLOBAL),),
         ('test_no_executor.py::test_no_executor_after_earlier_request',
          'test_no_executor.py::test_no_executor_while_other_request_in_flight',
          'test_no_executor.py::test_delegate_without_token_after_authenticated_request',
          'test_no_executor.py::test_delegate_without_token_while_authenticated_request_in_flight',
          *TOKENLESS_READS),
         'not an error'),
    Case('no-executor-default-fallback', 'core/context.py',
         (("        raise RuntimeError('No executor configured. Set executor via set_executor() first.')",
           '        from cluster_mcp.core.executor.shell import LocalShellExecutor\n        return LocalShellExecutor()'),),
         ('test_no_executor.py::test_tool_without_executor_middleware_fails[run_command]',
          'test_no_executor.py::test_no_executor_after_earlier_request'),
         'not an error'),
    Case('no-token-fallback-identity', 'core/middleware.py',
         (("            # No auth - this shouldn't happen in delegate mode\n"
           '            # but let the request proceed (will fail at executor access)\n'
           '            return\n',
           '            set_executor(DelegatingExecutor(next(iter(self._user_map)), self._user_map))\n'
           '            return\n'),),
         ('test_no_executor.py::test_delegate_without_token_fails', *refused_reads('no-token')),
         'not an error'),
    Case('auth-middleware-sets-at-construction', 'core/middleware.py',
         (('        self._user_map = load_user_map(user_map_path)\n',
           '        self._user_map = load_user_map(user_map_path)\n'
           '        set_executor(DelegatingExecutor(next(iter(self._user_map)), self._user_map))\n'),),
         ('test_no_executor.py::test_delegate_without_token_fails',
          'test_no_executor.py::test_delegate_without_token_after_authenticated_request',
          'test_no_executor.py::test_delegate_without_token_while_authenticated_request_in_flight',
          *refused_reads('no-token'), *TOKENLESS_READS),
         'not an error'),
    Case('shared-middleware-sets-at-construction', 'core/middleware.py',
         (('        super().__init__()\n        self._executor = executor\n',
           '        super().__init__()\n        self._executor = executor\n        set_executor(executor)\n'),),
         ('test_no_executor.py::test_no_executor_after_earlier_request',
          'test_no_executor.py::test_no_executor_while_other_request_in_flight'),
         'not an error'),
    # A tool that falls back to a local executor fails on the missing file with a local error, not
    # the refusal; only the stated reason tells the two apart.
    Case('transfer-local-fallback', 'core/tools/transfer.py',
         (("    executor = get_executor()\n    return executor.get(_path('remote_path', remote_path), "
           "_path('local_path', local_path))",
           "    try:\n        executor = get_executor()\n    except RuntimeError:\n"
           "        from cluster_mcp.core.executor.shell import LocalShellExecutor\n"
           "        executor = LocalShellExecutor()\n    return executor.get(_path('remote_path', remote_path), "
           "_path('local_path', local_path))"),),
         ('test_no_executor.py::test_tool_without_executor_middleware_fails[download_file]',),
         'error lacks reason'),
    # Identity claims: sub, then email, then preferred_username, the first non-empty one wins, and
    # a token with none of them is refused rather than given an identity.
    Case('precedence-reordered', 'core/middleware.py',
         ((CLAIM_ORDER, "for claim in ('email', 'sub', 'preferred_username'):"),),
         ('test_identity.py::test_identity_claim_precedence[all-three]',),
         'ran as'),
    Case('precedence-username-before-email', 'core/middleware.py',
         ((CLAIM_ORDER, "for claim in ('sub', 'preferred_username', 'email'):"),),
         ('test_identity.py::test_identity_claim_precedence[sub-absent]',),
         'ran as'),
    Case('precedence-username-dropped', 'core/middleware.py',
         ((CLAIM_ORDER, "for claim in ('sub', 'email'):"),),
         ('test_identity.py::test_identity_claim_precedence[email-empty]',
          'test_identity.py::test_identity_claim_precedence[username-only]'),
         'error result'),
    Case('precedence-empty-claim-accepted', 'core/middleware.py',
         (('if claim in claims and claims[claim]:', 'if claim in claims:'),),
         ('test_identity.py::test_identity_claim_precedence[sub-empty]',),
         'error result'),
    Case('no-claim-fallback-identity', 'core/middleware.py',
         (('                return str(claims[claim])\n        return None\n',
           '                return str(claims[claim])\n        return next(iter(self._user_map))\n'),),
         ('test_identity.py::test_token_without_identity_fails[no-claims]',
          'test_identity.py::test_token_without_identity_fails[all-empty]',
          *refused_reads('no-claims', 'all-empty')),
         'not an error'),
    # The middleware's own check: a token naming no identity is refused for what it lacks, not looked
    # up in the map as None.
    Case('no-claim-not-refused', 'core/middleware.py',
         (('        if identity is None:\n', '        if False:\n'),),
         (*refused_reads('no-claims', 'all-empty'),
          *(f'{STORAGE}::test_unknown_uri_read_is_refused[{row}-{era}]' for row in ('no-claims', 'all-empty')
            for era in ERAS)),
         'error lacks reason'),
    # The user map: an unmapped identity is refused by the middleware and by the executor, never
    # given a default user; a malformed line fails naming its line; comments load as nothing.
    Case('unmapped-gets-default-user', 'core/middleware.py',
         (('        if identity not in self._user_map:\n            raise PermissionError(',
           '        if identity not in self._user_map:\n            identity = next(iter(self._user_map))\n'
           '        if False:\n            raise PermissionError('),),
         ('test_identity.py::test_unmapped_identity_is_not_authorized',
          'test_identity.py::test_first_claim_unmapped_does_not_fall_through',
          *refused_reads('unmapped', 'first-claim-unmapped')),
         'not an error'),
    Case('executor-unmapped-default', 'core/executor/delegate.py',
         (("        if identity not in user_map:\n            raise KeyError(f'Identity {identity!r} not found in user map')\n",
           ''),
          ('        self._local_user = user_map[identity]', "        self._local_user = user_map.get(identity, 'nobody')")),
         ('test_identity.py::test_executor_rejects_unmapped_identity',),
         'DID NOT RAISE'),
    Case('map-malformed-line-skipped', 'core/executor/delegate.py',
         (('            if len(parts) != 2:\n                raise ValueError(',
           '            if len(parts) != 2:\n                continue\n                raise ValueError('),),
         ('test_identity.py::test_user_map_rejects_line_without_local_user',),
         'DID NOT RAISE'),
    Case('map-line-number-dropped', 'core/executor/delegate.py',
         (('''f'Invalid user map format at line {line_num}: expected "<id> <local-user>"\'''',
           '''f'Invalid user map format: expected "<id> <local-user>"\''''),),
         ('test_identity.py::test_user_map_rejects_line_without_local_user',),
         'does not name line 5'),
    # Numbering by entries, not file lines, names the wrong line once comments or blanks precede it.
    Case('map-line-counts-entries', 'core/executor/delegate.py',
         (('Invalid user map format at line {line_num}:', 'Invalid user map format at line {len(user_map) + 1}:'),),
         ('test_identity.py::test_user_map_rejects_line_without_local_user',),
         'does not name line 5'),
    Case('map-comments-loaded', 'core/executor/delegate.py',
         (("if not line or line.startswith('#'):", 'if not line:'),),
         ('test_identity.py::test_user_map_skips_comments_and_blanks',),
         'map differs'),
    # The delegated launch: exactly sudo -n -H -u <user>, then the launcher's stage and one program
    # that runs the script as one word, with the cwd quoted as one word.
    Case('sudo-n-dropped', 'core/executor/delegate.py',
         ((SUDO_PREFIX, "SUDO: Final = ('sudo', '-H', '-u')"),),
         ('test_executors.py::test_sudo_argv[no-cwd]',),
         'argv differs'),
    Case('sudo-H-dropped', 'core/executor/delegate.py',
         ((SUDO_PREFIX, "SUDO: Final = ('sudo', '-n', '-u')"),),
         ('test_executors.py::test_sudo_argv[no-cwd]',),
         'argv differs'),
    Case('cwd-unquoted', 'core/executor/launch.py',
         (("lines.append(CD_LINE.format(word=word(UserPath(cwd))))", "lines.append(CD_LINE.format(word=cwd))"),),
         ('test_executors.py::test_sudo_argv[cwd-spaces]', 'test_executors.py::test_sudo_argv[cwd-metacharacters]'),
         'argv differs'),
    Case('command-quoted', 'core/executor/launch.py',
         (("lines.append(SCRIPT.format(script=shlex.quote(_checked(command, 'command'))))",
           "lines.append(SCRIPT.format(script=shlex.quote(shlex.quote(_checked(command, 'command')))))"),),
         ('test_executors.py::test_sudo_argv[no-cwd]',),
         'argv differs'),
    # The interpreter is the constant /bin/bash in every backend, never the server's $SHELL.
    Case('interpreter-from-shell-env', 'core/executor/launch.py',
         (("    return [*POSIX_STAGE, '-c', STAGE, 'cluster-mcp', prog]",
           "    return [os.environ.get('SHELL', BASH), NORC, '--posix', '-c', STAGE, 'cluster-mcp', prog]"),),
         ('test_executors.py::test_interpreter_is_pinned[local]', 'test_executors.py::test_interpreter_is_pinned[delegate]'),
         'argv differs'),
    # Delegate mode: the program starts in the mapped user's $HOME, `~` resolves there inside the
    # program, and transfers run as the mapped user through the same launch.
    Case('delegate-tilde-server-home', 'core/executor/delegate.py',
         ((DELEGATE_PROGRAM,
           "        prog, marks = launch.program(command, __import__('os').path.expanduser(cwd) if cwd else cwd,"
           " start='home')\n"),),
         ('test_executors.py::test_delegate_cwd_resolves_in_the_mapped_home[tilde]',
          'test_executors.py::test_delegate_cwd_resolves_in_the_mapped_home[tilde-sub-dir]',
          'test_literal_args.py::test_literal_argument[delegate-run_command-cwd]'),
         'not the mapped home'),
    Case('delegate-server-cwd', 'core/executor/delegate.py',
         ((DELEGATE_PROGRAM, '        prog, marks = launch.program(command, cwd)\n'),),
         ('test_executors.py::test_delegate_starts_in_the_mapped_home',),
         'not the mapped home'),
    Case('transfer-as-server', 'core/executor/delegate.py',
         (('        return self._copy(local_path, remote_path)\n',
           "        return __import__('shutil').copy2(launch.expand_local(local_path), launch.expand_local(remote_path))\n"),),
         ('test_executors.py::test_delegate_transfers_land_in_the_mapped_home[put]',),
         'not the mapped home'),
    # One timeout contract: every backend returns the captured output and a marker no completed or
    # signal-killed command can produce, and the ssh backend never raises.
    Case('timeout-sentinel-minus-one', 'core/executor/base.py',
         (('TIMEOUT_EXIT_CODE: Final = -1001\n', 'TIMEOUT_EXIT_CODE: Final = -1\n'),),
         TIMEOUT_ROWS,
         'indistinguishable'),
    Case('ssh-timeout-raises', 'core/executor/ssh.py',
         (("            return bytes(out), bytes(err), TIMEOUT_EXIT_CODE, b''\n",
           "            raise TimeoutError(f'timed out after {timeout} s')\n"),),
         ('test_ssh_exec.py::test_timeout_returns_the_captured_output[bash]',),
         'raised'),
    # The ssh wire: the program travels behind the bootstrap, stdin carries nothing and its end goes
    # at once, the output loop waits rather than spins, and the login shell's startup output is cut
    # away.
    Case('ssh-bootstrap-dropped', 'core/executor/ssh.py',
         (('        wire = launch.ssh_command(prog)\n', '        wire = prog\n'),),
         ('test_ssh_exec.py::test_bash_runs_whatever_the_login_shell[zsh]',),
         'pinned interpreter'),
    Case('ssh-stdin-not-closed', 'core/executor/ssh.py',
         (('                chan.shutdown_write()\n', '                pass\n'),),
         ('test_ssh_exec.py::test_stdin_is_empty_and_ends_at_once[bash]',),
         'EOF'),
    Case('ssh-drain-spins', 'core/executor/ssh.py',
         (('        time.sleep(wait)\n', '        pass\n'),),
         ('test_ssh_exec.py::test_drain_waits_instead_of_spinning',),
         'busy-waited'),
    Case('backend-separation-skipped', 'core/executor/ssh.py',
         (('        out, err, code = launch.separate(out, err, code, marks, note)\n', ''),),
         ('test_ssh_exec.py::test_startup_output_is_separated[bash]',),
         'differs from the quiet home'),
    # No startup file moves where an ssh command starts, reads a write's content, or holds the call;
    # a timeout reads what the command prints as it stops; the one separation exception is stated.
    Case('ssh-start-not-home', 'core/executor/ssh.py',
         (("        prog, marks = launch.program(command, cwd, start='home')\n",
           '        prog, marks = launch.program(command, cwd)\n'),),
         ('test_ssh_exec.py::test_a_startup_cd_does_not_move_the_start[bash-profile]',
          'test_ssh_exec.py::test_a_startup_cd_does_not_move_the_start[zshenv]'),
         'a startup cd moved'),
    Case('content-on-stdin-over-ssh', 'core/executor/ssh.py',
         (("                chan.shutdown_write()\n",
           "                chan.sendall(SSHExecutor.content)\n                SSHExecutor.content = b''\n"
           "                chan.shutdown_write()\n"),
          ("        if not path:\n            # As a shell's `>` with an empty name.\n",
           "        SSHExecutor.content = data\n"
           "        return self.run(launch.write_argv(path, append, parent, executable))\n"
           "        if not path:\n            # As a shell's `>` with an empty name.\n"),
          ("    _host: str\n", "    content = b''\n    _host: str\n")),
         ('test_ssh_exec.py::test_a_remote_rc_never_reads_a_writes_content[zshenv]',
          'test_ssh_exec.py::test_a_remote_rc_never_reads_a_writes_content[bashrc]'),
         "content rode a command's stdin"),
    Case('ssh-timeout-no-drain', 'core/executor/ssh.py',
         (('            _stopped(chan, out, err)\n', ''),),
         ('test_ssh_exec.py::test_a_timeout_drains_what_follows_the_term',),
         'lost what followed the TERM'),
    # Over ssh the exit status comes ahead of output still queued on a slow link: the read goes on to
    # both end records however slowly they come, and a timeout before them names the status.
    Case('ssh-returns-at-exit-status', 'core/executor/ssh.py',
         (('        _drain(chan, out, err)\n        if end is not None:\n',
           '        _drain(chan, out, err)\n'
           "        if chan.exit_status_ready():\n"
           "            return bytes(out), bytes(err), chan.recv_exit_status(), b''\n"
           '        if end is not None:\n'),),
         ('test_ssh_exec.py::test_a_slow_link_returns_the_whole_file[256KiBps]',
          'test_ssh_exec.py::test_a_stalling_link_returns_the_whole_file[stall-1.6s-after-exit]',
          'test_ssh_exec.py::test_a_stalling_link_returns_the_whole_file[packets-6000Bps]',
          'test_ssh_exec.py::test_a_slow_link_returns_both_streams_whole',
          'test_ssh_exec.py::test_a_late_sentinel_still_counts_as_started[bashrc]',
          'test_ssh_exec.py::test_a_job_that_ran_is_never_reported_as_not_started'),
         'cut before its end records'),
    Case('ssh-one-record-is-the-end', 'core/executor/ssh.py',
         (('            if scanned == [-1, -1]:\n', '            if -1 in scanned:\n'),),
         ('test_ssh_exec.py::test_one_record_is_not_the_end',),
         'TIMEOUT_EXIT_CODE'),
    Case('ssh-late-stop-silent', 'core/executor/ssh.py',
         (("                note = launch.LATE_NOTE.format(code=chan.recv_exit_status()).encode()\n",
           "                note = b''\n"),),
         ('test_ssh_exec.py::test_a_command_whose_records_have_not_come_by_the_deadline_is_a_timeout',
          'test_ssh_exec.py::test_a_timeout_before_the_records_names_the_status'),
         'LATE_NOTE'),
    Case('separation-exception-unstated', 'core/tools/shell.py',
         (("    are available whatever the user's login shell). Nothing the initialisation prints is returned,\n"
           "    with one exception: over ssh, a background job started by the remote login shell's own rc file\n"
           "    (zsh's .zshenv, say) can write into the result while the command runs. The result holds all of\n",
           "    are available whatever the user's login shell); nothing the initialisation prints is returned.\n"
           "    The result holds all of\n"),),
         ('test_ssh_exec.py::test_separation_texts_state_the_remote_rc_exception',),
         'does not state the exception'),
    Case('content-route-unstated', 'core/executor/base.py',
         (("        in place; over `ssh` they never ride a command's stdin, but go by SFTP to a private\n"
           "        temporary file (mode 0600, in a fresh directory of mode 0700) beside the target, every\n",
           "        in place; over `ssh` they never ride a command's stdin, but go to a private\n"
           "        temporary file (mode 0600, in a fresh directory of mode 0700) beside the target, every\n"),),
         ('test_ssh_exec.py::test_content_texts_state_the_sftp_route',),
         'does not state its route'),
    # SFTP: `~//x` stays in the login home, and a local name is taken literally.
    Case('sftp-tilde-root', 'core/executor/ssh.py',
         (("        return path[2:].lstrip('/') or '.'\n", "        return path[2:] or '.'\n"),),
         ('test_ssh_exec.py::test_transfers_land_where_named[put-tilde-double-slash]',
          'test_ssh_exec.py::test_transfers_land_where_named[get-tilde-double-slash]'),
         'did not land at'),
    Case('sftp-path-formatted', 'core/executor/ssh.py',
         (('            sftp.get(remote, local)\n', '            self._conn.get(remote_path, local_path)\n'),),
         ('test_ssh_exec.py::test_transfers_land_where_named[get-brace-local-name]',),
         'did not land at'),
    # A write over ssh: the content staged by SFTP privately beside the target, moved into place whole
    # with the target's mode, a link followed, and the staging removed on every path.
    Case('staging-not-cleaned', 'core/executor/ssh.py',
         (('    for remove, target in (*((sftp.remove, path) for path in staged), (sftp.rmdir, directory)):\n',
           '    for remove, target in ():\n'),),
         ('test_ssh_exec.py::test_an_ssh_write_replaces_the_file_whole_and_keeps_its_mode',
          'test_ssh_exec.py::test_a_failed_ssh_write_leaves_nothing_behind'),
         'left its staging behind'),
    Case('move-not-atomic', 'core/executor/ssh.py',
         (("""PLACE: Final = 'chmod -- "$3" "$1" && mv -f -- "$1" "$2"'""", """PLACE: Final = 'cat -- "$1" >"$2"'"""),),
         ('test_ssh_exec.py::test_an_ssh_write_replaces_the_file_whole_and_keeps_its_mode',),
         'not replaced whole'),
    Case('mode-not-kept', 'core/executor/ssh.py',
         (("""PLACE: Final = 'chmod -- "$3" "$1" && mv -f -- "$1" "$2"'""", """PLACE: Final = 'mv -f -- "$1" "$2"'"""),),
         ('test_ssh_exec.py::test_an_ssh_write_replaces_the_file_whole_and_keeps_its_mode',),
         'lost its mode'),
    Case('staging-not-private', 'core/executor/ssh.py',
         (('    sftp.mkdir(directory, 0o700)\n', '    sftp.mkdir(directory, 0o755)\n'),),
         ('test_ssh_exec.py::test_an_ssh_write_stages_its_content_privately',),
         'not staged privately'),
    Case('staged-file-not-private', 'core/executor/ssh.py',
         (('            sftp.chmod(staged, 0o600)\n', ''),),
         ('test_ssh_exec.py::test_an_ssh_write_stages_its_content_privately',),
         'not staged privately'),
    Case('staging-not-beside-target', 'core/executor/ssh.py',
         (("            near = '.' if through else posixpath.dirname(target) or '.'\n", "            near = '.'\n"),),
         ('test_ssh_exec.py::test_an_ssh_write_stages_its_content_privately',),
         'not staged privately beside the target'),
    Case('link-replaced', 'core/executor/ssh.py',
         (('    if link:\n        try:\n            resolved = sftp.normalize(path)\n',
           '    if False:\n        try:\n            resolved = sftp.normalize(path)\n'),),
         ('test_ssh_exec.py::test_an_ssh_write_follows_a_link',),
         'replaced the link'),
    Case('ssh-append-overwrites', 'core/executor/ssh.py',
         (('                if append:\n                    script = PLACE_APPEND\n',
           '                if False:\n                    script = PLACE_APPEND\n'),),
         ('test_writes.py::test_writes_are_byte_exact[ssh-append]',),
         'differs from the bytes sent'),
    # A transfer that fails is never a write: every write's reply and the close are checked, then the
    # staged file's size and checksum, before the move; the remote filesystem names the cause.
    Case('sftp-writes-pipelined', 'core/executor/ssh.py',
         (('            handle.set_pipelined(False)\n', '            handle.set_pipelined(True)\n'),),
         ('test_ssh_exec.py::test_a_write_that_runs_out_of_room_keeps_the_file[edquot]',),
         'does not name its cause'),
    Case('sftp-close-unchecked', 'core/executor/ssh.py',
         (('        _close(sftp, handle)\n', '        handle.close()\n'),),
         ('test_ssh_exec.py::test_a_staged_file_that_is_not_what_was_sent_is_never_placed[close-fails]',),
         'was not refused for its staged file'),
    Case('staged-size-unchecked', 'core/executor/ssh.py',
         (('    if size != len(data):\n', '    if False:\n'),),
         ('test_ssh_exec.py::test_a_staged_file_that_is_not_what_was_sent_is_never_placed[short]',),
         'was not refused for its staged file'),
    Case('staged-checksum-unchecked', 'core/executor/ssh.py',
         (('                return self._run(launch.fixed_argv(VERIFY + script,', '                return self._run(launch.fixed_argv(script,'),),
         ('test_ssh_exec.py::test_a_staged_file_that_is_not_what_was_sent_is_never_placed[changed]',),
         'was not refused for its staged file'),
    Case('transfer-cause-unnamed', 'core/executor/ssh.py',
         (("                                f'{self._reason(staged, deadline) or exc}; the file is unchanged') from None\n",
           "                                f'{exc}; the file is unchanged') from None\n"),),
         ('test_ssh_exec.py::test_a_write_that_runs_out_of_room_keeps_the_file[8k-free]',),
         'does not name its cause'),
    # Over ssh a write refuses what `cat >` refuses and leaves what it leaves.
    Case('unwritable-target-replaced', 'core/executor/ssh.py',
         (('                    script = WRITABLE + PLACE\n', '                    script = PLACE\n'),),
         ('test_writes.py::test_a_write_refuses_what_cat_refuses[ssh]',
          'test_writes.py::test_a_write_refuses_what_cat_refuses[ssh-openssh]'),
         'read-only target was not refused'),
    Case('dangling-link-replaced', 'core/executor/ssh.py',
         (('        except FileNotFoundError:\n            resolved = None\n',
           '        except FileNotFoundError:\n            return path, None, False\n'),),
         ('test_writes.py::test_a_write_refuses_what_cat_refuses[ssh-openssh]',),
         'did not stay a link'),
    Case('link-loop-named-missing', 'core/executor/ssh.py',
         (('                if _loops(sftp, remote):\n', '                if False:\n'),),
         ('test_writes.py::test_a_write_refuses_what_cat_refuses[ssh]',
          'test_writes.py::test_a_write_refuses_what_cat_refuses[ssh-openssh]'),
         'loop of links'),
    Case('set-id-bits-kept', 'core/executor/ssh.py',
         (("    return path, f'{stat.S_IMODE(mode) & ~SET_ID:o}', not stat.S_ISREG(mode)\n",
           "    return path, f'{stat.S_IMODE(mode):o}', not stat.S_ISREG(mode)\n"),),
         ('test_writes.py::test_a_write_refuses_what_cat_refuses[ssh]',),
         'kept or lost the wrong bits'),
    # A lost connection is never a command that did not start, nor a failed submission.
    Case('lost-link-read-as-ended', 'core/executor/ssh.py',
         (('            if _lost(chan) and not (', '            if False and not ('),),
         ('test_ssh_exec.py::test_a_lost_connection_is_never_did_not_start[after-the-command]',),
         'connection was lost after it ran'),
    Case('lost-link-at-exec-raised', 'core/executor/ssh.py',
         (('                if transport.is_active():\n                    raise\n',
           '                raise\n'),),
         ('test_ssh_exec.py::test_a_lost_connection_is_never_did_not_start[before-the-reply]',),
         'instead of returning'),
    Case('lost-link-at-exec-unsettled', 'core/executor/ssh.py',
         (('                transport.join(SETTLE)\n', ''),),
         ('test_ssh_exec.py::test_a_lost_link_at_exec_is_lost_while_the_transport_unwinds',),
         'instead of returning'),
    Case('lost-link-not-started', 'core/executor/launch.py',
         (('        if code in (TIMEOUT_EXIT_CODE, CONNECTION_LOST_EXIT_CODE):\n            return b\'\', note, code\n',
           '        if code == TIMEOUT_EXIT_CODE:\n            return b\'\', note, code\n'),),
         ('test_ssh_exec.py::test_a_lost_connection_is_never_did_not_start[after-the-command]',
          'test_ssh_exec.py::test_a_lost_connection_is_never_did_not_start[before-the-reply]'),
         'reported as not started'),
    Case('lost-submission-failed', 'slurm/tools.py',
         (('    if result.exit_code == CONNECTION_LOST_EXIT_CODE:\n', '    if False:\n'),),
         ('test_ssh_exec.py::test_a_lost_connection_is_never_did_not_start[after-the-command]',),
         'never that it failed'),
    # A call that cannot reconnect gives up within its bound and runs nothing: it stops waiting on an
    # attempt at its deadline, starts none after its last chance, reads as not started (never as a
    # lost connection), gives up at once on a refused authentication, publishes a success no call
    # waits for, joins the one attempt in flight rather than start its own, and frees that attempt's
    # slot when its worker cannot start.
    Case('ssh-reconnect-unbounded-poll', 'core/executor/ssh.py',
         (('            while not _await(pending.done, max(0.0, min(ATTEMPT_POLL, deadline - time.monotonic()))):\n'
           '                if time.monotonic() >= deadline and self._leave(pending):\n'
           '                    return connect_failure_message(self._host, cause)\n',
           '            while not _await(pending.done, ATTEMPT_POLL):\n'
           '                pass\n'),),
         ('test_ssh_exec.py::test_a_reconnect_attempt_that_hangs_is_abandoned_at_the_bound',),
         'still reconnecting'),
    Case('ssh-reconnect-unbounded-retry', 'core/executor/ssh.py',
         (('            if now >= deadline - FINAL_ATTEMPT_LEAD:\n'
           '                return connect_failure_message(self._host, cause)\n'
           '            time.sleep(min(delay, deadline - FINAL_ATTEMPT_LEAD - now))\n',
           '            time.sleep(delay)\n'),),
         ('test_ssh_exec.py::test_a_reconnect_that_cannot_succeed_fails_within_the_bound[refused]',),
         'still reconnecting'),
    Case('ssh-reconnect-reads-as-lost', 'core/executor/ssh.py',
         (("', NOT_STARTED_EXIT_CODE,\n                             self._host)\n",
           "', CONNECTION_LOST_EXIT_CODE,\n                             self._host)\n"),),
         ('test_ssh_exec.py::test_a_reconnect_that_cannot_succeed_fails_within_the_bound[refused]',),
         'read as a lost connection'),
    Case('ssh-reconnect-retries-refused-auth', 'core/executor/ssh.py',
         (("            if _auth_ending(cause) == 'refused':\n", '            if False:\n'),),
         ('test_ssh_exec.py::test_a_reconnect_refused_authentication_fails_at_once',),
         'was retried'),
    Case('ssh-reconnect-late-success-leaks', 'core/executor/ssh.py',
         (('                pending.transport, dropped = self._publish(conn)\n',
           '                pending.transport, dropped = self._publish(conn) if pending.waiters else (None, None)\n'),),
         ('test_ssh_exec.py::test_a_reconnect_attempt_that_hangs_is_abandoned_at_the_bound',),
         'leaked'),
    Case('ssh-reconnect-attempt-per-call', 'core/executor/ssh.py',
         (('                pending = self._inflight\n', '                pending = None\n'),),
         ('test_ssh_exec.py::test_concurrent_calls_during_a_stall_start_one_attempt[hang]',
          'test_ssh_exec.py::test_concurrent_calls_during_a_stall_start_one_attempt[canonicalisation]'),
         'not one'),
    Case('ssh-reconnect-unstarted-worker-holds-slot', 'core/executor/ssh.py',
         (('                        self._inflight = None\n                        pending.error = exc\n',
           '                        pending.error = exc\n'),),
         ('test_ssh_exec.py::test_a_reconnect_worker_that_cannot_start_frees_the_attempt',),
         'stayed taken'),
    # An authentication is a refusal only when the server answered: one cut short, by a closed link or
    # its own timeout, is retried, and a call never takes on the failure of an attempt aborted at
    # another call's deadline. An abort never closes a published connection, and an aborted attempt
    # is never published; a call at its deadline takes an outcome that has just come; a connection
    # published meanwhile stays published; a shorter connect timeout never lowers the bound; and each
    # of a write's own commands shares the write's deadline.
    Case('ssh-reconnect-auth-class-not-cause', 'core/executor/ssh.py',
         (("            if _auth_ending(cause) == 'refused':\n",
           '            if isinstance(cause, AuthenticationException):\n'),),
         ('test_ssh_exec.py::test_an_authentication_cut_short_is_retried[closed]',
          'test_ssh_exec.py::test_an_authentication_cut_short_is_retried[timed-out]'),
         'taken for a refusal'),
    Case('ssh-reconnect-joiner-inherits-abort', 'core/executor/ssh.py',
         (('            if pending.aborted:\n                continue\n',
           '            if False:\n                continue\n'),),
         ('test_ssh_exec.py::test_a_call_never_inherits_an_aborted_attempt',),
         'as its own'),
    Case('ssh-reconnect-abort-unchecked', 'core/executor/ssh.py',
         (('            if pending.done.is_set() or pending.waiters:\n', '            if pending.waiters:\n'),),
         ('test_ssh_exec.py::test_an_abort_and_a_publish_never_cross[published-first]',),
         'closed a published connection'),
    Case('ssh-reconnect-publishes-aborted', 'core/executor/ssh.py',
         (('            if pending.aborted:\n                pending.error = ConnectionAbortedError(',
           '            if False:\n                pending.error = ConnectionAbortedError('),),
         ('test_ssh_exec.py::test_an_abort_and_a_publish_never_cross[opened-first]',),
         'published a connection the abort closed'),
    Case('ssh-reconnect-leave-ignores-outcome', 'core/executor/ssh.py',
         (('            if pending.done.is_set():\n                return False\n', ''),),
         ('test_ssh_exec.py::test_a_call_at_its_deadline_takes_an_outcome_that_has_come',),
         'reported a failure'),
    Case('ssh-reconnect-publish-replaces-live', 'core/executor/ssh.py',
         (('        if current is not None:\n            return current, conn\n', ''),),
         ('test_ssh_exec.py::test_a_reconnect_keeps_a_connection_published_meanwhile',),
         'closed or replaced'),
    Case('ssh-reconnect-bound-unfloored', 'core/executor/ssh.py',
         (("    return max(CONNECT_TIMEOUT, getattr(conn, 'connect_timeout', None) or 0, explicit or 0)\n",
           "    return max(0, getattr(conn, 'connect_timeout', None) or 0, explicit or 0)\n"),),
         tuple(f'test_ssh_exec.py::test_a_reconnect_bound_never_falls_below_the_default[{given}]'
               for given in ('ssh-config', 'connect-kwargs', 'connect-timeout')),
         'lowered'),
    # Every refusal Paramiko raises gives up at once, and an `AuthFailure` is one only when every
    # source was refused; the declared Paramiko floor is the classifier's. No attempt starts or is
    # joined after a call's last start; an abort spares an attempt another call has joined since;
    # and a failed attempt releases its connection.
    Case('ssh-auth-strategy-read-as-refusal', 'core/executor/ssh.py',
         (("        return 'refused' if cause is exc else _auth_ending(cause)\n", "        return 'refused'\n"),),
         ('test_ssh_exec.py::test_a_reconnect_that_cannot_succeed_fails_within_the_bound[auth-failure-closed]',
          'test_ssh_exec.py::test_a_reconnect_that_cannot_succeed_fails_within_the_bound[auth-failure-agent]'),
         'never retried'),
    Case('ssh-auth-subclass-not-refusal', 'core/executor/ssh.py',
         (("    if isinstance(exc, REFUSALS):\n        return 'refused'\n",
           "    if isinstance(exc, REFUSALS):\n        return None\n"),),
         tuple(f'test_ssh_exec.py::test_every_refusal_ends_the_reconnect_at_once[{refusal}]'
               for refusal in ('bad-type', 'partial', 'password-required', 'auth-failure')),
         'was retried'),
    Case('ssh-paramiko-floor-disagrees', 'core/executor/ssh.py',
         (('PARAMIKO_FLOOR: Final = (3, 2)\n', 'PARAMIKO_FLOOR: Final = (3, 1)\n'),),
         ('test_ssh_exec.py::test_the_declared_paramiko_floor_matches_the_classifier',),
         'disagree'),
    Case('ssh-reconnect-starts-past-last-start', 'core/executor/ssh.py',
         (('                if not scheduled and time.monotonic() >= deadline - FINAL_ATTEMPT_LEAD:\n',
           '                if False:\n'),),
         ('test_ssh_exec.py::test_a_call_past_its_last_start_starts_no_attempt[none-in-flight]',
          'test_ssh_exec.py::test_a_call_past_its_last_start_starts_no_attempt[one-in-flight]',
          'test_ssh_exec.py::test_a_write_command_past_its_last_start_starts_no_attempt'),
         'past its last start'),
    Case('ssh-reconnect-abort-spares-no-joiner', 'core/executor/ssh.py',
         (('            if pending.done.is_set() or pending.waiters:\n', '            if pending.done.is_set():\n'),),
         ('test_ssh_exec.py::test_an_abort_spares_an_attempt_another_call_joined_since',),
         'joined since'),
    Case('ssh-reconnect-failed-attempt-unreleased', 'core/executor/ssh.py',
         (('            if conn is not None:\n                _release(conn)\n            raise\n', '            raise\n'),),
         ('test_ssh_exec.py::test_a_failed_attempt_releases_its_connection',),
         'left its connection open'),
    Case('ssh-write-parent-own-deadline', 'core/executor/ssh.py',
         (("UserPath(parent)),\n                                 deadline=deadline)",
           "UserPath(parent)),\n                                 deadline=time.monotonic() + self._window)"),),
         ('test_ssh_exec.py::test_a_write_spends_one_reconnect_window[parent]',),
         'took a deadline of its own'),
    Case('ssh-write-place-own-deadline', 'core/executor/ssh.py',
         (("UserPath(expected)),\n                                 deadline=deadline)",
           "UserPath(expected)),\n                                 deadline=time.monotonic() + self._window)"),),
         ('test_ssh_exec.py::test_a_write_spends_one_reconnect_window[place]',),
         'took a deadline of its own'),
    Case('ssh-write-probe-own-deadline', 'core/executor/ssh.py',
         (("timeout=60,\n                              deadline=deadline)",
           "timeout=60,\n                              deadline=time.monotonic() + self._window)"),),
         ('test_ssh_exec.py::test_a_write_spends_one_reconnect_window[probe]',),
         'took a deadline of its own'),
    # A host that returns is used: a failed reconnect is never remembered, so the next call tries
    # again. A reconnect that gives up reads as nothing run at every tool: sbatch says nothing was
    # submitted, sacct stops at its failed whoami, and the cluster context is never cached from it.
    Case('ssh-reconnect-gives-up-for-good', 'core/executor/ssh.py',
         (('        transport = self._ensure_connected(deadline)\n'
           '        if isinstance(transport, str):\n'
           '            return self._not_run(transport)\n'
           '        out, err, code, note',
           "        transport = getattr(self, '_gave_up', None) or self._ensure_connected(deadline)\n"
           '        if isinstance(transport, str):\n'
           '            self._gave_up = transport\n'
           '            return self._not_run(transport)\n'
           '        out, err, code, note'),),
         ('test_ssh_exec.py::test_a_failed_reconnect_leaves_the_server_serving',),
         'after the host returned'),
    Case('sbatch-not-started-reads-as-failed', 'slurm/tools.py',
         (('        if written.exit_code == NOT_STARTED_EXIT_CODE:\n', '        if False:\n'),
          ('    if result.exit_code == NOT_STARTED_EXIT_CODE:\n', '    if False:\n')),
         ('test_ssh_exec.py::test_a_reconnect_failure_reaches_each_tool_as_not_run[sbatch-script-path]',
          'test_ssh_exec.py::test_a_reconnect_failure_reaches_each_tool_as_not_run[sbatch-script-content]'),
         'must say the job was not submitted'),
    Case('sacct-whoami-unchecked', 'slurm/tools.py',
         (('        if user_result.exit_code != 0:\n', '        if False:\n'),),
         ('test_ssh_exec.py::test_sacct_spends_one_reconnect_window',),
         'more than one reconnect window'),
    # The cluster context is the startup read, so a reconnect that gives up never reaches it: served
    # from a read through the executor instead, the failed read's line replaces the site text.
    Case('context-served-from-a-failed-read', 'core/tools/context.py',
         (("    return site_of(get_server()).text\n",
           "    from cluster_mcp.core.context import get_executor\n"
           "    from cluster_mcp.core.site import read_remote\n"
           "    return read_remote(get_executor()).text\n"),),
         per_scheme('test_ssh_exec.py::test_a_reconnect_failure_never_changes_the_cluster_context'),
         'not the startup read'),
    # An end record split across reads is found, at its full stop, while something holds the streams.
    Case('ssh-record-scan-from-end', 'core/executor/ssh.py',
         (('                    scanned[i] = -1 if found else max(0, len(buf) - len(end) - 5)\n',
           '                    scanned[i] = -1 if found else len(buf)\n'),),
         ('test_ssh_exec.py::test_an_end_record_split_across_reads_is_found',),
         'split across reads'),
    Case('local-record-scan-from-end', 'core/executor/launch.py',
         (('                self.scanned[stream] = max(0, len(buf) - len(self.end) - 5)\n',
           '                self.scanned[stream] = len(buf)\n'),),
         ('test_launch.py::test_a_local_end_record_split_across_reads_is_found',),
         'split across reads'),
    Case('record-without-full-stop', 'core/executor/launch.py',
         (("RECORD_TAIL: Final = re.compile(rb'([xs])([0-9]{1,3})\\.')\n",
           "RECORD_TAIL: Final = re.compile(rb'([xs])([0-9]{1,3})')\n"),),
         ('test_ssh_exec.py::test_an_end_record_split_across_reads_is_found',
          'test_launch.py::test_a_local_end_record_split_across_reads_is_found'),
         'split across reads'),
    # The Executor protocol: every backend carries all nine members; a renamed one drops out.
    Case('local-put-renamed', 'core/executor/shell.py',
         (('    def put(self, local_path: str, remote_path: str) -> str:',
           '    def put_file(self, local_path: str, remote_path: str) -> str:'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[local]',),
         'does not satisfy Executor'),
    Case('delegate-hostname-renamed', 'core/executor/delegate.py',
         (('    def hostname(self) -> str:', '    def host_name(self) -> str:'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[delegate]',),
         'does not satisfy Executor'),
    Case('ssh-close-renamed', 'core/executor/ssh.py',
         (('    def close(self) -> None:\n        """Close the SSH connection."""',
           '    def disconnect(self) -> None:\n        """Close the SSH connection."""'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[ssh]',),
         'does not satisfy Executor'),
    Case('ssh-write-renamed', 'core/executor/ssh.py',
         (('    def write(self, path: str, data: bytes, append: bool = False, parent: str | None = None,\n',
           '    def write_file(self, path: str, data: bytes, append: bool = False, parent: str | None = None,\n'),),
         ('test_executors.py::test_backend_satisfies_executor_protocol[ssh]',),
         'does not satisfy Executor'),
    # The execution-mode ladder: explicit -e, then stdio, then an SSH host from the flag or the
    # environment, then auth none, then delegate; delegate alone gets the auth middleware.
    Case('ladder-rungs-1-2-swapped', 'core/__init__.py',
         (("        if self.exec_mode:\n            return self.exec_mode\n\n"
           "        # Auto-select based on transport, auth, and ssh-host\n"
           "        if self.transport == 'stdio':\n            return 'ssh'\n",
           "        if self.transport == 'stdio':\n            return 'ssh'\n"
           "        if self.exec_mode:\n            return self.exec_mode\n\n"
           "        # Auto-select based on transport, auth, and ssh-host\n"
           "        if False:\n            return 'ssh'\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-stdio]',),
         'mode:'),
    Case('ladder-rungs-3-4-swapped', 'core/__init__.py',
         (("        elif self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]:\n"
           '            # If SSH host is specified, use ssh mode regardless of transport\n'
           "            return 'ssh'\n"
           "        elif self.auth == 'none':\n            return 'local'\n",
           "        elif self.auth == 'none':\n            return 'local'\n"
           "        elif self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]:\n"
           "            return 'ssh'\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[host-flag-over-auth-none]',
          'test_exec_mode.py::test_exec_mode_ladder[env-host-over-auth-none]'),
         'mode:'),
    # Each value of an explicit -e wins on its own; ignoring one lets the later rungs decide.
    Case('ladder-explicit-local-ignored', 'core/__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.exec_mode != 'local':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-stdio]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-host]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-auth]'),
         'mode:'),
    Case('ladder-explicit-ssh-ignored', 'core/__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.exec_mode != 'ssh':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-ssh-over-auth-none]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-ssh-over-auth]'),
         'mode:'),
    Case('ladder-explicit-delegate-ignored', 'core/__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.exec_mode != 'delegate':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-stdio]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-host]'),
         'mode:'),
    # An explicit -e that yields to one later-rung input: auth none (delegate falls to an
    # unauthenticated local shell), CLUSTER_MCP_SSH_HOST, or auth oidc.
    Case('ladder-explicit-delegate-yields-to-auth-none', 'core/__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and not (self.exec_mode == 'delegate' and self.auth == 'none'):\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-auth-none]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[delegate]'),
         'mode: resolved local, expected delegate'),
    Case('ladder-explicit-yields-to-env-host', 'core/__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and not env_setting('CLUSTER_MCP_SSH_HOST')[0]:\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-env-host]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-delegate-over-env-host]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[local]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[delegate]'),
         'mode: resolved ssh'),
    Case('ladder-explicit-yields-to-oidc', 'core/__init__.py',
         ((EXPLICIT_MODE, "        if self.exec_mode and self.auth != 'oidc':\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[explicit-local-over-oidc]',
          'test_exec_mode.py::test_exec_mode_ladder[explicit-ssh-over-oidc]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[local]',
          'test_exec_mode.py::test_explicit_mode_decides_alone[ssh]'),
         'mode: resolved delegate'),
    # Rung 1 decides, but to the wrong mode: every explicit row, including those whose later rungs
    # agree with the explicit value, reads the mode it resolved.
    Case('ladder-explicit-misrouted', 'core/__init__.py',
         (("        if self.exec_mode:\n            return self.exec_mode\n",
           "        if self.exec_mode:\n"
           "            return {'local': 'delegate', 'delegate': 'ssh', 'ssh': 'local'}[self.exec_mode]\n"),),
         tuple(f'test_exec_mode.py::test_exec_mode_ladder[explicit-{mode}-over-{later}]'
               for mode in ('local', 'ssh', 'delegate')
               for later in ('stdio', 'host', 'env-host', 'auth-none', 'auth', 'oidc'))
         + tuple(f'test_exec_mode.py::test_explicit_mode_decides_alone[{mode}]' for mode in ('local', 'ssh', 'delegate')),
         'mode: resolved'),
    Case('ladder-env-host-ignored', 'core/__init__.py',
         (("        elif self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]:\n", '        elif self.ssh_host:\n'),),
         ('test_exec_mode.py::test_exec_mode_ladder[env-host-over-auth-none]',),
         'mode:'),
    Case('ladder-local-widened', 'core/__init__.py',
         (("        elif self.auth == 'none':\n            return 'local'\n        else:\n            return 'delegate'",
           "        else:\n            return 'local'"),),
         ('test_exec_mode.py::test_exec_mode_ladder[jwt-without-host]',
          'test_exec_mode.py::test_exec_mode_ladder[oidc-without-host]'),
         'mode:'),
    Case('delegate-gets-shared-middleware', 'core/__init__.py',
         (("        if exec_mode == 'delegate':\n            # Delegate mode uses per-request executors via middleware\n",
           "        if exec_mode == 'delegate' and False:\n            # Delegate mode uses per-request executors via middleware\n"),),
         ('test_exec_mode.py::test_exec_mode_ladder[jwt-without-host]',),
         'middleware:'),
    # The secret floor: create_jwt_auth() and --generate-token each refuse an unset, empty or
    # 31-character JWT_SECRET on their own, so each floor is lowered separately.
    Case('floor-auth-31', 'core/auth.py',
         (('    if len(secret) < 32:\n', '    if len(secret) < 31:\n'),),
         ('test_tokens.py::test_jwt_auth_refuses_short_secret[31-chars]',),
         'DID NOT RAISE'),
    Case('floor-cli-31', 'core/__init__.py',
         (('            if len(secret) < 32:\n', '            if len(secret) < 31:\n'),),
         ('test_tokens.py::test_generate_token_refuses_short_secret[31-chars]',),
         'status'),
    Case('auth-unset-secret-defaulted', 'core/auth.py',
         (("        raise ValueError('JWT_SECRET environment variable required for jwt auth mode')",
           "        secret = 'x' * 32"),),
         ('test_tokens.py::test_jwt_auth_refuses_short_secret[unset]',
          'test_tokens.py::test_jwt_auth_refuses_short_secret[empty]'),
         'DID NOT RAISE'),
    # Signer and verifier agree on issuer, audience, algorithm and lifetime: drifting either side
    # rejects the tokens the other mints.
    Case('verifier-audience-changed', 'core/auth.py',
         (('        audience=AUDIENCE,\n', "        audience=AUDIENCE + '-other',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted', 'test_tokens.py::test_cli_minted_token_is_accepted'),
         'error result'),
    Case('verifier-issuer-changed', 'core/auth.py',
         (('        issuer=ISSUER,\n', "        issuer=ISSUER + '-other',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted',),
         'error result'),
    Case('verifier-algorithm-changed', 'core/auth.py',
         (('        algorithm=ALGORITHM,\n', "        algorithm='HS512',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted',),
         'error result'),
    Case('signer-audience-changed', 'core/token.py',
         (("        'aud': AUDIENCE,\n", "        'aud': AUDIENCE + '-other',\n"),),
         ('test_tokens.py::test_minted_token_is_accepted', 'test_tokens.py::test_cli_minted_token_is_accepted'),
         'error result'),
    Case('signer-token-expired', 'core/token.py',
         (("        'exp': now + timedelta(seconds=lifetime),\n", "        'exp': now - timedelta(seconds=lifetime),\n"),),
         ('test_tokens.py::test_minted_token_is_accepted',),
         'error result'),
    # The rejection half: a verifier that stops checking a claim accepts a token minted for
    # another audience or issuer.
    Case('verifier-audience-unchecked', 'core/auth.py',
         (('        audience=AUDIENCE,\n', '        audience=None,\n'),),
         ('test_tokens.py::test_mismatched_token_is_rejected[audience]',),
         'expected 401'),
    Case('verifier-issuer-unchecked', 'core/auth.py',
         (('        issuer=ISSUER,\n', '        issuer=None,\n'),),
         ('test_tokens.py::test_mismatched_token_is_rejected[issuer]',),
         'expected 401'),
    # The error boundary: an exception an executor middleware raises around a tool call reaches the
    # client as a tool error result whose text is exactly str(exc); cancellation passes through.
    Case('tool-error-boundary-dropped', 'core/server.py',
         (('    server.add_middleware(ToolErrorMiddleware())\n', ''),),
         BOUNDARY_ROWS,
         'protocol error instead of a tool error result'),
    Case('boundary-leaks-traceback', 'core/middleware.py',
         (('raise error(str(exc)) from exc', "raise error(str(exc) + __import__('traceback').format_exc()) from exc"),),
         (*BOUNDARY_ROWS, *read_boundary_rows('permission-memory', 'mcp-error-memory'),
          *refused_reads(*MIDDLEWARE_REFUSALS)),
         'error text differs'),
    Case('boundary-type-name', 'core/middleware.py',
         (('raise error(str(exc)) from exc', "raise error(f'{type(exc).__name__}: {exc}') from exc"),),
         (*BOUNDARY_ROWS, *read_boundary_rows('permission-memory', 'mcp-error-memory'),
          *refused_reads(*MIDDLEWARE_REFUSALS)),
         'error text differs'),
    Case('boundary-catches-base-exception', 'core/middleware.py',
         (('    except Exception as exc:\n        raise error(', '    except BaseException as exc:\n        raise error('),),
         ('test_protocol.py::test_boundary_lets_cancellation_through[on_call_tool]',
          'test_protocol.py::test_boundary_lets_cancellation_through[on_read_resource]'),
         'swallowed cancellation'),
    Case('boundary-catches-named-only', 'core/middleware.py',
         (('    except Exception as exc:\n        raise error(', '    except (PermissionError, RuntimeError) as exc:\n        raise error('),),
         read_boundary_rows('other-memory'),
         'refused read: error'),
    # Re-raised unconverted around a tool call, the refusal is a protocol error that aborts a test's
    # tool call before its read is checked, so the read rows here are the ones that read alone.
    Case('boundary-reraises-original', 'core/middleware.py',
         (('raise error(str(exc)) from exc', 'raise'),),
         CONVERTED_READS,
         'refused read: error'),
    Case('boundary-passes-nothing', 'core/middleware.py',
         (('    except passes:\n        raise\n', ''),),
         NOT_FOUND,
         'expected -32602'),
    Case('boundary-drops-result', 'core/middleware.py',
         (('    try:\n        return await call_next(context)\n', '    try:\n        await call_next(context)\n'),),
         per_scheme(*(f'{STORAGE}::test_storage_read_runs_the_local_executor[{era}]' for era in ERAS)),
         'the read failed'),
    Case('boundary-reraises-mcp-error', 'core/middleware.py',
         (('    except passes:\n        raise\n',
           "    except (*passes, __import__('mcp').MCPError):\n        raise\n"),),
         ('test_protocol.py::test_middleware_refusal_is_a_tool_error_result[mcp-error-memory]',),
         'protocol error instead of a tool error result'),
    # The read boundary: a refusal raised around a read reaches the client as an internal error whose
    # text is exactly str(exc), in both eras (unbounded, the modern era masks the text and the
    # handshake era sends code 0), while the not-found error FastMCP raises for a URI it does not
    # serve passes through as the protocol's own.
    Case('read-boundary-dropped', 'core/middleware.py',
         ((READ_HOOK, '        return await call_next(context)\n'),),
         (*CONVERTED_READS, *refused_reads(*MIDDLEWARE_REFUSALS)),
         'refused read: error'),
    Case('read-boundary-leaks-traceback', 'core/middleware.py',
         ((READ_HOOK, read_hook_raising("str(exc) + __import__('traceback').format_exc()")),),
         (*read_boundary_rows('permission-memory', 'mcp-error-memory', 'other-memory'),
          *refused_reads(*MIDDLEWARE_REFUSALS)),
         'error text differs'),
    Case('read-boundary-type-name', 'core/middleware.py',
         ((READ_HOOK, read_hook_raising("f'{type(exc).__name__}: {exc}'")),),
         (*read_boundary_rows('permission-memory', 'mcp-error-memory', 'other-memory'),
          *refused_reads(*MIDDLEWARE_REFUSALS)),
         'error text differs'),
    Case('read-boundary-wraps-not-found', 'core/middleware.py',
         (('ResourceError, (FastMCPError, NotFoundError, DisabledError))', 'ResourceError, (FastMCPError,))'),),
         NOT_FOUND,
         'expected -32602'),
    # The identity the delegate middleware stores in the context state is request-scoped: it never
    # reaches the session store, where a later request on the same session would read it. Only the
    # handshake era has a session to leak into: under revision 2026-07-28 FastMCP keys each request's
    # state afresh, so the modern row holds whatever the scope and cannot catch this plant.
    Case('delegate-state-session-scoped', 'core/middleware.py',
         (("set_state('rcac_user', identity, serializable=False)", "set_state('rcac_user', identity)"),
          ("set_state('rcac_local_user', executor.local_user, serializable=False)",
           "set_state('rcac_local_user', executor.local_user)")),
         ('test_protocol.py::test_delegate_state_is_request_scoped[legacy]',
          *per_scheme('test_protocol.py::test_delegate_read_state_is_request_scoped[legacy]')),
         'state outlived its request'),
    Case('delegate-state-not-set', 'core/middleware.py',
         (("        await context.fastmcp_context.set_state('rcac_user', identity, serializable=False)\n"
           "        await context.fastmcp_context.set_state('rcac_local_user', executor.local_user, serializable=False)\n",
           ''),),
         (*(f'test_protocol.py::test_delegate_state_is_request_scoped[{era}]' for era in ERAS),
          *per_scheme(*(f'test_protocol.py::test_delegate_read_state_is_request_scoped[{era}]' for era in ERAS))),
         'no state was set'),
    # The server's instructions reach a client in both protocol eras: in the InitializeResult of a
    # handshake and in the DiscoverResult of revision 2026-07-28.
    Case('instructions-dropped', 'core/server.py',
         (('        instructions=compose(base_instructions(loaded), site, budget),\n', '        instructions=None,\n'),),
         ('test_protocol.py::test_client_era_is_served[legacy-memory]',
          'test_protocol.py::test_client_era_is_served[modern-memory]'),
         'instructions differ'),
    # The site read skips the assembled AGENTS.md, which repeats the topic files.
    Case('site-agents-md-included', 'core/site.py',
         (("    return fnmatch.fnmatchcase(name, '*.md') and name != EXCLUDED\n",
           "    return fnmatch.fnmatchcase(name, '*.md')\n"),),
         ('test_site.py::test_local_read_takes_the_eligible_files_in_byte_order',),
         'files:'),
    # The files are ordered by the bytes of their names, whatever the locale.
    Case('site-byte-order', 'core/site.py',
         (("key=lambda f: f.raw)", "key=lambda f: f.name.lower())"),),
         ('test_site.py::test_local_read_takes_the_eligible_files_in_byte_order',),
         'files:'),
    # The composed instructions never exceed the budget.
    Case('site-budget-overflow', 'core/site.py',
         (("        if units(_render(base, trial, rest)) <= budget:\n",
           "        if units(_render(base, trial, rest)) <= budget + 40:\n"),),
         ('test_site.py::test_compose_keeps_its_contract_at_every_budget[sizes0]',),
         'over the budget'),
    # A read that has not finished is abandoned at its bound, not at twice it.
    Case('site-read-unbounded', 'core/site.py',
         (("        return box.get(timeout=timeout)\n", "        return box.get(timeout=timeout * 2)\n"),),
         ('test_site.py::test_bounded_read_times_out_and_contains_errors',),
         'past its 0.3 s bound'),
    # In ssh mode the startup read is bounded too, not only the local one.
    Case('startup-ssh-unbounded', 'core/__init__.py',
         (("            return site_context.read_bounded(lambda: site_context.read_remote(executor), 'the cluster')\n",
           "            return site_context.read_remote(executor)\n"),),
         ('test_site_startup.py::test_a_hung_read_does_not_hold_startup[ssh]',),
         'a hung read held startup'),
    # What a server serves is the text read at startup, whatever the directory holds later.
    Case('context-rereads', 'core/site.py',
         (("    return _SITES[server]\n", "    return read_local() if _SITES[server].files else _SITES[server]\n"),),
         per_scheme('test_context.py::test_a_changed_directory_changes_nothing_served'),
         'what is served changed after startup'),
    # The tool answers from the startup text and runs nothing through the request's executor.
    Case('context-through-executor', 'core/tools/context.py',
         (("    return site_of(get_server()).text\n",
           "    from cluster_mcp.core.context import get_executor\n"
           "    get_executor().run(['cat', '--', '/etc/agents.d/a.md'])\n"
           "    return site_of(get_server()).text\n"),),
         per_scheme('test_context.py::test_tool_and_resource_serve_the_startup_text[shared-files-legacy]',
                    'test_context.py::test_tool_and_resource_serve_the_startup_text[shared-files-modern]'),
         'an executor ran'),
    # Each server serves the site it was built with: the holder is keyed by the server, never one
    # module value that the last server built overwrites.
    Case('site-holder-global', 'core/site.py',
         (("    _SITES[server] = site\n", "    global _ONE\n    _ONE = site\n"),
          ("    return _SITES[server]\n", "    return _ONE\n")),
         per_scheme('test_context.py::test_each_server_keeps_its_own_site[legacy]',
                    'test_context.py::test_each_server_keeps_its_own_site[modern]'),
         "another server's site"),
    # A reason's detail is cut in UTF-16 code units, the budget's unit, not in code points.
    Case('site-detail-code-points', 'core/site.py',
         (("    if units(text) <= limit:\n        return text\n", "    if len(text) <= limit:\n        return text\n"),
          ("        room -= units(char)\n", "        room -= 1\n")),
         ('test_site.py::test_astral_names_and_reasons_keep_the_budget[unreadable-local]',
          'test_site.py::test_astral_names_and_reasons_keep_the_budget[unreadable-remote]'),
         "needs more than a good read's minimum"),
    # With no files, the minimum holds the site's own reason, so that path never serves past the budget.
    Case('site-reason-unchecked', 'core/site.py',
         (("        return max(floor, units(_head(base) + site.reason))\n", "        return floor\n"),),
         ('test_site.py::test_every_reason_fits_the_room_kept_for_it',),
         'over the budget'),
    # A name's control characters are shown escaped, so no name breaks a served line.
    Case('site-name-unescaped', 'core/site.py',
         (("    return ''.join(_escape(c) if _escaped(c) else c for c in text)\n", "    return text\n"),),
         ('test_site.py::test_a_name_cannot_break_a_served_line[files-local]',
          'test_site.py::test_a_name_cannot_break_a_served_line[unreadable-remote]'),
         'is not one line'),
    # A read for others keeps only the files every account can read.
    Case('site-others-unchecked', 'core/site.py',
         (("                    if not _everyone_may(fd, READ):\n", "                    if False:\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[private-file-for-others]',),
         'files:'),
    # Every account means every class: the owner's and the group's bits count, not only others'.
    Case('site-group-unchecked', 'core/site.py',
         (("SEARCH: Final = 0o111\nLIST: Final = 0o555\nREAD: Final = 0o444\n",
           "SEARCH: Final = 0o001\nLIST: Final = 0o005\nREAD: Final = 0o004\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[groupless-file-for-others]',
          'test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[groupless-dir-for-others]',
          'test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[groupless-ancestor-for-others]'),
         'files:'),
    # Every directory a lookup of the path passes must be searchable by every account, a symlink's
    # way included, not only the directory reached.
    Case('site-ancestors-unchecked', 'core/site.py',
         (("            everyone = everyone and _everyone_may(directory, SEARCH)\n", "            pass\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[private-ancestor-for-others]',
          'test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read'
          '[private-ancestor-through-link-for-others]',
          'test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[link-in-private-dir-for-others]'),
         'files:'),
    # A path carrying an ACL entry is not every account's to read, whatever its mode bits.
    Case('site-acl-unchecked', 'core/site.py',
         (("    return os.stat(target).st_mode & need == need and not _extended(target)\n",
           "    return os.stat(target).st_mode & need == need\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[acl-file-for-others]',
          'test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[acl-ancestor-for-others]',
          'test_site.py::test_an_acl_entry_makes_a_path_unreadable_for_others[file]',
          'test_site.py::test_an_acl_entry_makes_a_path_unreadable_for_others[ancestor]'),
         'files:'),
    # The probe sees a real ACL entry, the way this platform stores one.
    Case('site-acl-probe-blind', 'core/site.py',
         (("        return _darwin_acl(target)\n", "        return False\n"),
          ("        return any(_acl_attribute(name) for name in _attributes(target))\n", "        return False\n")),
         ('test_site.py::test_an_acl_entry_makes_a_path_unreadable_for_others[file]',
          'test_site.py::test_an_acl_entry_makes_a_path_unreadable_for_others[directory]'),
         'the probe missed it'),
    # The route is checked from `/`: the root is a directory every lookup searches.
    Case('site-root-unsearched', 'core/site.py',
         (("    searched: set[int] = set()\n", "    searched: set[int] = {root}\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[acl-root-for-others]',),
         'files:'),
    # A relative symlink's target is looked up from the directory holding the link, not from `/`.
    Case('site-link-from-root', 'core/site.py',
         (("                route = walk([root] if target.startswith('/') else route, target)\n",
           "                route = walk([root], target)\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read'
          '[open-through-relative-link-for-others]',),
         'files:'),
    # A `..` step is a lookup in the directory it leaves, which every account must be able to search.
    Case('site-dotdot-unsearched', 'core/site.py',
         (("            search(route[-1])\n            if part == '..':\n                route = route[:-1] or route\n"
           "                continue\n",
           "            if part == '..':\n                route = route[:-1] or route\n                continue\n"
           "            search(route[-1])\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read'
          '[dotdot-out-of-private-dir-for-others]',),
         'files:'),
    # An abandoned read never holds the process open at exit.
    Case('site-read-thread-kept', 'core/site.py',
         (("name='cluster-mcp-site-read', daemon=True", "name='cluster-mcp-site-read', daemon=False"),),
         ('test_site.py::test_an_abandoned_read_does_not_hold_the_process',),
         'would hold the process open'),
    # An acl(3) failure other than "no ACL" counts as an entry: the probe fails closed on macOS.
    Case('site-acl-error-open', 'core/site.py',
         (("        return ctypes.get_errno() != errno.ENOENT\n", "        return False\n"),),
         ('test_site.py::test_an_acl_the_system_cannot_answer_counts_as_one[eacces]',
          'test_site.py::test_an_acl_the_system_cannot_answer_counts_as_one[eio]'),
         'must count as an ACL entry'),
    # What the read for every account checks is what it reads: no file is read again by its path, so a
    # swap of the file or of the route after the check changes nothing served.
    Case('site-file-reread-by-path', 'core/site.py',
         (("                    data = stream.read()\n",
           "                    data = open(os.path.join(directory, entry.name), 'rb').read()\n"),),
         ('test_site.py::test_a_swap_after_a_check_changes_nothing_read_for_others[route]',
          'test_site.py::test_a_swap_after_a_check_changes_nothing_read_for_others[file]'),
         'served text no ordinary account could read'),
    Case('site-listed-by-path', 'core/site.py',
         (("            listing = os.open('.', _LISTING, dir_fd=reached)\n",
           "            listing = os.open(directory, _LISTING)\n"),),
         ('test_site.py::test_a_swap_after_a_check_changes_nothing_read_for_others[route]',),
         'served text no ordinary account could read'),
    # A directory on the route is opened for search only, so one every account may search but the
    # server may not list is passed, as a lookup passes it.
    Case('site-route-opened-for-read', 'core/site.py',
         (("_STEP: Final = _SEARCH_ONLY | os.O_DIRECTORY", "_STEP: Final = os.O_RDONLY | os.O_DIRECTORY"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read[search-only-ancestor-for-others]',),
         'files:'),
    # A symlink is never followed where a file is expected, nor on the route without its check.
    Case('site-file-follows-links', 'core/site.py',
         (("_FILE: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC\n",
           "_FILE: Final = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC\n"),),
         ('test_site.py::test_a_swap_after_a_check_changes_nothing_read_for_others[listed-then-linked]',),
         'served text no ordinary account could read'),
    Case('site-route-follows-links', 'core/site.py',
         (("_STEP: Final = _SEARCH_ONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC\n",
           "_STEP: Final = _SEARCH_ONLY | os.O_DIRECTORY | os.O_CLOEXEC\n"),),
         ('test_site.py::test_a_read_for_others_keeps_only_what_every_account_can_read'
          '[private-ancestor-through-link-for-others]',),
         'files:'),
    # In delegate mode the startup read is a read for others.
    Case('delegate-reads-for-itself', 'core/__init__.py',
         (("        for_others = exec_mode == 'delegate'\n", "        for_others = False\n"),),
         ('test_site_startup.py::test_startup_reads_once_where_the_mode_says[delegate]',),
         'the read for others was False'),
    # On Linux every ACL the system lists counts, not only a POSIX one.
    Case('site-acl-posix-only', 'core/site.py',
         (("    return name.startswith(ACL_NAMESPACE) and 'acl' in name[len(ACL_NAMESPACE):]\n",
           "    return name in ('system.posix_acl_access', 'system.posix_acl_default')\n"),),
         ('test_site.py::test_a_listed_acl_makes_a_path_unreadable_for_others[nfs4_acl-file]',
          'test_site.py::test_a_listed_acl_makes_a_path_unreadable_for_others[richacl-ancestor]'),
         'files:'),
    # The remote read undoes the functions a login profile exports over the commands it runs.
    Case('site-reset-dropped', 'core/site.py',
         (("    'unset -f base64 shopt tr test\\n'\n", ""),),
         ('test_site.py::test_a_profile_cannot_change_the_remote_read[local]',
          'test_site.py::test_a_profile_cannot_change_the_remote_read[ssh]'),
         'a profile function changed what the remote read found'),
    # A file is its name's bytes: two names that decode alike stay two files, in the order of their
    # bytes, and each is served or named; a shown name reads back as itself.
    Case('site-names-by-text', 'core/site.py',
         (("key=lambda f: f.raw)", "key=lambda f: f.name.encode('utf-8'))"),),
         ('test_site.py::test_two_names_that_decode_alike_are_two_files[remote]',),
         'not as two files in byte order'),
    Case('site-omitted-by-name', 'core/site.py',
         (("    omitted = [f.name for i, f in enumerate(files) if i not in taken]\n",
           "    omitted = [f.name for f in files if f.name not in {g.name for g in included}]\n"),),
         ('test_site.py::test_two_names_that_decode_alike_are_two_files[remote]',),
         'served and 0 named'),
    Case('site-backslash-unescaped', 'core/site.py',
         (("    return _breaks(char) or char == '\\\\'\n", "    return _breaks(char)\n"),),
         ('test_site.py::test_a_shown_name_reads_back_as_itself',),
         'does not read back as itself'),
    # The remote read resets the glob state a login profile can leave its bash.
    Case('site-glob-state-inherited', 'core/site.py',
         (("    'unset GLOBIGNORE\\n'\n    'set +f\\n'\n", ""),
          ("    'for o in dotglob nullglob failglob nocaseglob globstar extglob; do shopt -u \"$o\" 2>/dev/null; done\\n'\n",
           "")),
         ('test_site.py::test_remote_read_ignores_the_login_shells_glob_state[globignore-files-layout]',
          'test_site.py::test_remote_read_ignores_the_login_shells_glob_state[dotglob-layout]',
          'test_site.py::test_remote_read_ignores_the_login_shells_glob_state[failglob-lower-agents]'),
         'the glob state changed what the remote read found'),
    # Every tool's served description is its full docstring, as FastMCP 2.x served it; FastMCP 4
    # alone serves only the summary paragraph.
    Case('tool-description-summary-only', 'core/tools/__init__.py',
         (('    tool = Tool.from_function(func, description=inspect.getdoc(func))\n',
           '    tool = Tool.from_function(func)\n'),),
         ('test_surface.py::test_served_surface_matches_baseline',),
         'description differs'),
    # The ssh executor maps the remote exit status into its CommandResult.
    Case('ssh-exit-status-dropped', 'core/executor/ssh.py',
         (("            return bytes(out), bytes(err), chan.recv_exit_status(), b''\n",
           "            return bytes(out), bytes(err), 0, b''\n"),),
         ('test_ssh_exec.py::test_a_profile_that_exits_is_not_started',),
         "the channel's status"),
    # `-t sse` serves: the CLI dispatches it to FastMCP's SSE transport and the server listens. The
    # target runs the installed console script, which imports this copy through PYTHONPATH.
    Case('sse-transport-unserved', 'core/__init__.py',
         (("                mcp.run(transport='sse', host=self.host, port=self.port)\n",
           '                pass\n'),),
         ('test_transports.py::test_transport_lists_expected_tools[sse-legacy]',),
         'did not start'),
    # OIDC is all-or-nothing: a configuration missing any of the four variables is refused, naming
    # all four, before a provider is built. The proxy keeps the FastMCP 2.x posture.
    Case('oidc-check-dropped', 'core/auth.py',
         (('    if not all([config_url, client_id, client_secret, base_url]):\n', '    if False:\n'),),
         OIDC_ROWS,
         'raised no ValueError'),
    Case('oidc-secret-not-required', 'core/auth.py',
         (('    if not all([config_url, client_id, client_secret, base_url]):\n',
           '    if not all([config_url, client_id, base_url]):\n'),),
         tuple(row for row in OIDC_ROWS if '[OIDC_CLIENT_SECRET-' in row),
         'raised no ValueError'),
    Case('oidc-message-incomplete', 'core/auth.py',
         (("            'OIDC_CLIENT_SECRET, MCP_BASE_URL'\n", "            'OIDC_CLIENT_SECRET'\n"),),
         tuple(row for row in OIDC_ROWS if '[MCP_BASE_URL-' in row),
         'does not name MCP_BASE_URL'),
    Case('oidc-cimd-enabled', 'core/auth.py',
         (('        enable_cimd=False,\n', ''),),
         ('test_auth_modes.py::test_oidc_proxy_keeps_the_2x_posture',),
         'enable_cimd=True'),
    # `none` installs no provider.
    Case('none-mode-installs-provider', 'core/auth.py',
         (("    'none': lambda: None,\n",
           "    'none': lambda: JWTVerifier(public_key='x' * 32, issuer=ISSUER, audience=AUDIENCE, algorithm=ALGORITHM),\n"),),
         ('test_auth_modes.py::test_none_mode_installs_no_provider',),
         'none mode installed a provider'),
    # The registry's annotation resolves to a provider-factory map; the stray `:` made it a slice.
    Case('auth-modes-annotation-slice', 'core/auth.py',
         (('AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider | None]]] = {',
           'AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider | None]]:] = {'),),
         ('test_auth_modes.py::test_auth_modes_annotation_is_a_provider_factory_map',),
         'slice'),
    # The launcher: every argument one literal word; a UserPath's leading ~ through the guarded
    # $HOME and nothing else expanded; a relative path or cwd anchored with ./.
    Case('launcher-arg-unquoted', 'core/executor/launch.py',
         (('    return shlex.quote(str(arg))\n', '    return str(arg)\n'),),
         ('test_launch.py::test_program_quotes_each_argument_as_one_word[hostile]',
          'test_launch.py::test_values_arrive_literally[local]',
          'test_literal_args.py::test_literal_argument[local-squeue-user]'),
         'reaches the command as'),
    Case('launcher-tilde-user-expanded', 'core/executor/launch.py',
         (("        if arg == '~':\n            return HOME_WORD\n", "        if arg == '~':\n            return '~'\n"),
          ("return f'{HOME_WORD}/{shlex.quote(rest)}' if rest else HOME_WORD",
           "return f'~/{shlex.quote(rest)}' if rest else '~'")),
         ('test_launch.py::test_program_quotes_each_argument_as_one_word[user-paths]',
          'test_launch.py::test_an_empty_home_fails_a_tilde_path[local]'),
         'does not resolve through $HOME'),
    Case('launcher-tilde-name-expanded', 'core/executor/launch.py',
         (("        if arg and not arg.startswith('/'):\n",
           "        if arg.startswith('~'):\n"
           "            user, _, rest = arg[1:].partition('/')\n"
           "            return '~' + user + ('/' + shlex.quote(rest) if rest else '')\n"
           "        if arg and not arg.startswith('/'):\n"),),
         ('test_launch.py::test_program_quotes_each_argument_as_one_word[user-paths]',),
         'leaves ~name for bash to expand'),
    Case('launcher-cwd-cdpath', 'core/executor/launch.py',
         (("lines.append(CD_LINE.format(word=word(UserPath(cwd))))", "lines.append(CD_LINE.format(word=shlex.quote(cwd)))"),),
         ('test_launch.py::test_program_renders_the_cwd[sub]',
          'test_launch.py::test_cwd_resolves_in_the_running_users_home[local]'),
         'reaches cd as'),
    Case('launcher-relative-dash', 'core/executor/launch.py',
         (("            return shlex.quote('./' + arg)\n", '            return shlex.quote(arg)\n'),),
         ('test_launch.py::test_program_quotes_each_argument_as_one_word[user-paths]',
          'test_launch.py::test_user_paths_resolve_only_a_leading_tilde[local]'),
         'reaches the command as'),
    # The SSH wire: the program travels as one base64 word behind a fixed bootstrap that keeps its
    # trailing newlines and runs nothing when decoding fails.
    Case('bootstrap-raw-program', 'core/executor/launch.py',
         (("    wire = BOOTSTRAP + base64.b64encode(prog.encode('utf-8')).decode('ascii')\n",
           '    wire = BOOTSTRAP + shlex.quote(prog)\n'),),
         ('test_launch.py::test_bootstrap_is_inert_text[hostile]',),
         'not base64'),
    Case('bootstrap-newlines-stripped', 'core/executor/launch.py',
         (('base64 -d && printf .)', 'base64 -d)'), (r'-c -- \"${{p%.}}\"', r'-c -- \"$p\"')),
         ('test_launch.py::test_bootstrap_delivers_the_program_exactly[ssh-bash]',),
         'not the program sent'),
    Case('bootstrap-decode-unchecked', 'core/executor/launch.py',
         (('base64 -d && printf .)', 'base64 -d; printf .)'),),
         ('test_launch.py::test_bootstrap_fails_without_base64[ssh-bash]',),
         'without base64'),
    # The login initialisation runs with the caller's streams parked and none of its output, traps
    # or exits reaching a result.
    Case('stdin-not-parked', 'core/executor/launch.py',
         (("PARK: Final = 'exec 57<&0 58>&1 59>&2 47<&0 48>&1 49>&2 </dev/null >/dev/null 2>&1'",
           "PARK: Final = 'exec 57<&0 58>&1 59>&2 47<&0 48>&1 49>&2 >/dev/null 2>&1'"),),
         ('test_launch.py::test_profile_cannot_read_stdin_or_shadow_cd[local]',
          'test_executors.py::test_a_profile_cannot_read_a_writes_content[local]',
          'test_executors.py::test_a_profile_cannot_read_a_writes_content[delegate]'),
         'the profile read'),
    Case('startup-not-parked', 'core/executor/launch.py',
         (("PARK: Final = 'exec 57<&0 58>&1 59>&2 47<&0 48>&1 49>&2 </dev/null >/dev/null 2>&1'",
           "PARK: Final = 'exec 57<&0 58>&1 59>&2 47<&0 48>&1 49>&2 </dev/null'"),),
         ('test_launch.py::test_startup_output_is_separated[local-slow]',),
         'differs from the quiet home'),
    # A startup file that took a parked descriptor leaves the command not run, and the result says so.
    Case('parked-descriptor-unchecked', 'core/executor/launch.py',
         (("PARKED_SAME: Final = '[[ /dev/fd/57 -ef /dev/fd/47 && /dev/fd/58 -ef /dev/fd/48 && /dev/fd/59 -ef /dev/fd/49 ]]'",
           "PARKED_SAME: Final = 'true'"),),
         ('test_launch.py::test_a_taken_parked_descriptor_runs_nothing[57]',
          'test_launch.py::test_a_taken_parked_descriptor_runs_nothing[58]'),
         'taken: the result is'),
    Case('parked-descriptor-unnoted', 'core/executor/launch.py',
         (('        if TAKEN_MARK in err:\n', '        if False:\n'),),
         ('test_launch.py::test_a_taken_parked_descriptor_runs_nothing[58]',
          'test_launch.py::test_a_taken_parked_descriptor_runs_nothing[49]'),
         'taken: the result is'),
    Case('startup-traps-kept', 'core/executor/launch.py',
         (("'set +euxvTkP +o errtrace +o posix; trap - EXIT ERR DEBUG RETURN; '",
           "'set +euxvTkP +o errtrace +o posix; '"),),
         ('test_launch.py::test_startup_output_is_separated[local-argv]',),
         'differs from the quiet home'),
    Case('prologue-unalias-shared-line', 'core/executor/launch.py',
         ((r"PROLOGUE: Final = ('\\unalias -a\n'" + "\n                   'unset -f builtin",
           "PROLOGUE: Final = ('unalias -a; '\n                   'unset -f builtin"),),
         ('test_launch.py::test_profile_cannot_hijack_the_prologue[local-alias]',),
         'differs from the quiet home'),
    Case('prologue-read-function-kept', 'core/executor/launch.py',
         (("export declare compgen read kill ulimit exit; '", "export declare compgen kill ulimit exit; '"),),
         ('test_launch.py::test_profile_cannot_hijack_the_prologue[local-read-function]',),
         'differs from the quiet home'),
    Case('stage-reads-bash-env', 'core/executor/launch.py',
         (("    return [*POSIX_STAGE, '-c', STAGE, 'cluster-mcp', prog]",
           "    return [BASH, NORC, '-c', STAGE, 'cluster-mcp', prog]"),),
         ('test_launch.py::test_startup_output_is_separated[local-stdin]',),
         'differs from the quiet home'),
    Case('script-in-login-shell', 'core/executor/launch.py',
         (("lines.append(SCRIPT.format(script=shlex.quote(_checked(command, 'command'))))",
           "lines.append(_checked(command, 'command'))"),),
         ('test_launch.py::test_a_signal_death_is_reported_and_reraised[local-script-kill]',
          'test_launch.py::test_a_signal_death_is_reported_and_reraised[ssh-bash-script-kill]'),
         'not exit code'),
    Case('startup-output-kept', 'core/executor/launch.py',
         (('    kept_out, kept_err = _after(out, marks.start), _after(err, marks.start)\n',
           '    kept_out, kept_err = out, err\n'),),
         ('test_launch.py::test_separate_keeps_only_the_commands_output[chatty-prefix]',),
         'kept output from before the sentinel'),
    Case('not-started-exit-zero', 'core/executor/launch.py',
         (("        return b'', NOT_STARTED_NOTE.format(code=code).encode() + note, NOT_STARTED_EXIT_CODE\n",
           "        return b'', NOT_STARTED_NOTE.format(code=code).encode() + note, code\n"),),
         ('test_launch.py::test_separate_keeps_only_the_commands_output[not-started]',
          'test_launch.py::test_a_profile_that_exits_is_not_started[local]'),
         'did not start, but'),
    # Timeouts: the whole group is stopped, the captured output kept, and a launch that already
    # exited keeps its own status.
    Case('timeout-group-not-killed', 'core/executor/launch.py',
         (('            os.killpg(proc.pid, sig)\n', '            os.kill(proc.pid, sig)\n'),),
         ('test_launch.py::test_timeout_kills_the_process_group',),
         'still running'),
    Case('timeout-partial-output-dropped', 'core/executor/launch.py',
         (("        return pipes.out, pipes.err, TIMEOUT_EXIT_CODE, b''\n", "        return b'', b'', TIMEOUT_EXIT_CODE, b''\n"),),
         ('test_launch.py::test_timeout_keeps_partial_output',),
         'lost the output'),
    Case('timeout-completed-misreported', 'core/executor/launch.py',
         (("                return pipes.out, pipes.err, proc.returncode, b''\n",
           "                return pipes.out, pipes.err, TIMEOUT_EXIT_CODE, b''\n"),),
         ('test_launch.py::test_a_raw_launch_is_complete_at_its_exit',),
         'not its own 3'),
    # A launch that has exited is complete at its exit, whatever it left running.
    Case('exit-not-noticed', 'core/executor/launch.py',
         (('            if proc.poll() is not None:\n', '            if False:\n'),),
         ('test_launch.py::test_a_raw_launch_is_complete_at_its_exit',),
         'held an exited launch'),
    # Where a local command starts: the server's working directory, written into the program text,
    # never carried by a positional parameter (bash 4 and later let a startup file rewrite those).
    Case('local-start-dropped', 'core/executor/shell.py',
         (('        prog, marks = launch.program(command, cwd, start=os.getcwd())\n',
           '        prog, marks = launch.program(command, cwd)\n'),),
         ('test_executors.py::test_a_profile_cd_does_not_move_the_start[local]',),
         'a profile cd moved'),
    Case('local-start-positional', 'core/executor/launch.py',
         (("""-c -- "$1"'\n""", """-c -- "$1" cluster-mcp "$PWD"'\n"""),
          ("        lines.append(CD_LINE.format(word=shlex.quote(start)))\n",
           """        lines.append(CD_LINE.format(word='"${1:?the start directory is not set}"'))\n""")),
         ('test_launch.py::test_program_reads_no_positional_parameter[argv-directory]',
          'test_launch.py::test_program_reads_no_positional_parameter[script-directory]'),
         'positional parameter'),
    # A result is complete exactly when both end records have arrived: the command runs as a child,
    # the program prints a record carrying a per-call nonce and the status on both streams after it,
    # re-raises a signal death, and the result's status is the record's.
    Case('command-exec-in-place', 'core/executor/launch.py',
         (("                      SUBSHELL[0], *lines, SUBSHELL[1], STATUS, record_line(end_nonce), RERAISE])\n",
           "                      *lines, STATUS, record_line(end_nonce), RERAISE])\n"),),
         ('test_launch.py::test_the_call_ends_at_its_records[local]',
          'test_launch.py::test_the_call_ends_at_its_records[ssh-zsh]'),
         "not the command's own output"),
    Case('end-record-one-stream', 'core/executor/launch.py',
         (("""            f'printf %s%s%s. {_halves(end)} "$cluster_mcp_r" >&59')\n""",
           """            f'true')\n"""),),
         ('test_launch.py::test_the_call_ends_at_its_records[local]',
          'test_launch.py::test_the_call_ends_at_its_records[ssh-bash]'),
         "not the command's own output"),
    Case('end-record-without-nonce', 'core/executor/launch.py',
         (('    start_nonce, end_nonce = secrets.token_hex(16), secrets.token_hex(16)\n',
           "    start_nonce, end_nonce = secrets.token_hex(16), '0' * 32\n"),),
         ('test_launch.py::test_a_command_printing_record_lookalikes_keeps_them[local]',
          'test_launch.py::test_a_command_printing_record_lookalikes_keeps_them[ssh-zsh]'),
         'cut the result'),
    Case('signal-death-not-reraised', 'core/executor/launch.py',
         (("""RERAISE: Final = ('[[ -z $cluster_mcp_k ]] || { ulimit -c 0; trap - "$cluster_mcp_k"; kill -s "$cluster_mcp_k" "$$"; }\\n'\n""",
           """RERAISE: Final = ('\\n'\n"""),),
         ('test_launch.py::test_a_signal_death_is_reported_and_reraised[local-hup]',
          'test_launch.py::test_a_signal_death_is_reported_and_reraised[ssh-bash-term]'),
         'the signal was not re-raised'),
    Case('signal-death-unreported', 'core/executor/launch.py',
         (("cluster_mcp_r=s$((cluster_mcp_s - 128)) ;; '", "cluster_mcp_r=x$cluster_mcp_s ;; '"),),
         ('test_launch.py::test_a_signal_death_is_reported_and_reraised[local-term]',
          'test_launch.py::test_a_signal_death_is_reported_and_reraised[ssh-zsh-hup]'),
         'not exit code'),
    Case('record-status-ignored', 'core/executor/launch.py',
         (('        if reported:\n            code = reported[0]\n', ''),),
         ('test_ssh_exec.py::test_a_signal_death_is_reported[/bin/bash]',),
         'not reported as one'),
    Case('separate-note-dropped', 'core/executor/launch.py',
         (("    return streams[0], streams[1] + notes + note, code\n", "    return streams[0], streams[1] + notes, code\n"),),
         ('test_ssh_exec.py::test_a_timeout_before_the_records_names_the_status',),
         'does not name the status'),
    # Every step of the timeout sequence: SIGTERM first, what follows it kept, then SIGKILL.
    Case('timeout-sigkill-dropped', 'core/executor/launch.py',
         (('    for sig in (signal.SIGTERM, signal.SIGKILL):\n', '    for sig in (signal.SIGTERM,):\n'),),
         ('test_launch.py::test_a_timeout_escalates_to_sigkill',),
         'no SIGKILL followed'),
    Case('timeout-sigterm-dropped', 'core/executor/launch.py',
         (('    for sig in (signal.SIGTERM, signal.SIGKILL):\n', '    for sig in (signal.SIGKILL,):\n'),),
         ('test_launch.py::test_a_timeout_sends_term_first_and_keeps_what_follows',
          'test_launch.py::test_a_timeout_signals_the_whole_group_term_first'),
         'SIGTERM'),
    # Nothing after the startup files depends on shell state they can change: the function export
    # neither splits nor globs, the prologue resets `set -k` and `set -P`, and a fixed script undoes
    # the functions and options a profile exported to it.
    Case('function-export-split', 'core/executor/launch.py',
         (("""SCRIPT: Final = ('while IFS= read -r cluster_mcp_fn; do export -f -- "$cluster_mcp_fn"; '\n"""
           """                 'done < <(compgen -A function); unset cluster_mcp_fn; '\n""",
           """SCRIPT: Final = ('fns=$(compgen -A function); [ -z "$fns" ] || export -f $fns; '\n"""),),
         ('test_launch.py::test_profile_state_does_not_reach_the_launcher[local-glob-options]',
          'test_launch.py::test_profile_state_does_not_reach_the_launcher[ssh-zsh-glob-options]'),
         'reached the launcher'),
    Case('prologue-keyword-kept', 'core/executor/launch.py',
         (("'set +euxvTkP +o errtrace", "'set +euxvTP +o errtrace"),),
         ('test_launch.py::test_profile_state_does_not_reach_the_launcher[local-keyword]',
          'test_launch.py::test_profile_state_does_not_reach_the_launcher[ssh-bash-keyword]'),
         'reached the launcher'),
    Case('prologue-physical-kept', 'core/executor/launch.py',
         (("'set +euxvTkP +o errtrace", "'set +euxvTk +o errtrace"),),
         ('test_launch.py::test_profile_state_does_not_reach_the_launcher[local-physical]',
          'test_launch.py::test_profile_state_does_not_reach_the_launcher[ssh-zsh-physical]'),
         'reached the launcher'),
    Case('fixed-reset-dropped', 'core/executor/launch.py',
         (("    return [*POSIX_STAGE, '-c', FIXED_RESET + script, name, *values]\n",
           "    return [*POSIX_STAGE, '-c', script, name, *values]\n"),),
         ('test_writes.py::test_a_profile_cannot_change_a_fixed_script[local]',
          'test_writes.py::test_a_profile_cannot_change_a_fixed_script[ssh]'),
         'changed what a fixed script does'),
    # No bash the launcher starts but the login bash reads a startup file, whatever sshd sets.
    Case('stage-reads-bashrc', 'core/executor/launch.py',
         (("    return [*POSIX_STAGE, '-c', STAGE, 'cluster-mcp', prog]",
           "    return [BASH, '--posix', '-c', STAGE, 'cluster-mcp', prog]"),),
         ('test_launch.py::test_no_stage_reads_a_startup_file_under_sshd[local-argv]',),
         'a stage read a startup file'),
    Case('bootstrap-reads-bashrc', 'core/executor/launch.py',
         (('''BOOTSTRAP: Final = (f"exec {' '.join(POSIX_STAGE)} -c ''', '''BOOTSTRAP: Final = (f"exec {BASH} --posix -c '''),),
         ('test_launch.py::test_no_stage_reads_a_startup_file_under_sshd[ssh-zsh-argv]',
          'test_launch.py::test_no_stage_reads_a_startup_file_under_sshd[ssh-sh-argv]'),
         'a stage read a startup file'),
    Case('script-reads-bashrc', 'core/executor/launch.py',
         (("f'BASH_ENV= ENV= exec {BASH} {NORC} -c -- {{script}}')", "f'BASH_ENV= ENV= exec {BASH} -c -- {{script}}')"),),
         ('test_launch.py::test_no_stage_reads_a_startup_file_under_sshd[local-script]',),
         'a stage read a startup file'),
    Case('fixed-script-reads-bashrc', 'core/executor/launch.py',
         (("    return [*POSIX_STAGE, '-c', FIXED_RESET + script, name, *values]\n",
           "    return [BASH, '--posix', '-c', FIXED_RESET + script, name, *values]\n"),),
         ('test_launch.py::test_no_stage_reads_a_startup_file_under_sshd[local-fixed-script]',),
         'a stage read a startup file'),
    # Feature-scoped spec ids stay out of the package.
    Case('spec-id-in-source', 'core/executor/base.py',
         (('# The exit code of a command stopped at its timeout.', '# The exit code of a command stopped at its timeout (R' + '8).'),),
         ('test_hygiene.py::test_no_spec_ids_in_the_package_or_the_suite',),
         'a spec id names'),
    # Every size limit is checked against the bytes that cross it.
    Case('local-size-unchecked', 'core/executor/launch.py',
         (("    _fits(prog, 'its program')\n", ''),),
         ('test_launch.py::test_local_launch_limit_is_the_per_argument_limit',),
         'over the per-argument limit'),
    Case('ssh-size-ignores-bootstrap', 'core/executor/launch.py',
         (("    return _fits(wire, 'its SSH exec string')\n", "    _fits(prog, 'its SSH exec string')\n    return wire\n"),),
         ('test_launch.py::test_ssh_wire_limit_counts_the_bootstrap',
          'test_ssh_exec.py::test_an_oversize_program_is_refused_before_connecting'),
         'over the per-argument limit'),
    # A failed SSH connect at startup is answered: every request until EOF (a 2026-07-28 client
    # retries with `initialize` after its `server/discover` is refused), naming the host, on stdout
    # nothing but the answers, then a nonzero exit; and the connect itself is bounded.
    Case('startup-answers-first-only', 'core/startup.py',
         (('            stdout.write(refusal(request_id, message))\n            stdout.flush()\n',
           '            stdout.write(refusal(request_id, message))\n            stdout.flush()\n            return\n'),),
         ('test_startup.py::test_responder_answers_every_request',
          'test_startup.py::test_raw_wire_answers_every_request',
          'test_startup.py::test_startup_failure_is_answered[modern]'),
         'not answered'),
    Case('startup-host-unnamed', 'core/executor/ssh.py',
         (('    cause = _cause_class(exc)\n', "    cause = _cause_class(exc)\n    host = 'the SSH host'\n"),),
         ('test_startup.py::test_raw_wire_answers_every_request',
          'test_startup.py::test_connect_failure_names_host_and_cause[unknown-host]',
          'test_startup.py::test_connect_failure_names_host_and_cause[other]'),
         'does not name the host'),
    Case('startup-exit-zero', 'core/__init__.py',
         (('        StartupFailure: partial(exit_reported, status=exit_status.runtime_error),\n',
           '        StartupFailure: partial(exit_reported, status=exit_status.success),\n'),),
         ('test_startup.py::test_raw_wire_answers_every_request',
          'test_startup.py::test_connect_failure_names_host_and_cause[refused]'),
         'exit status 0'),
    Case('startup-stdout-noise', 'core/startup.py',
         (('    if stdin.isatty():\n        return\n',
           "    if stdin.isatty():\n        return\n    stdout.write(message + '\\n')\n"),),
         ('test_startup.py::test_responder_answers_every_request',
          'test_startup.py::test_raw_wire_answers_every_request'),
         'is not an error response'),
    Case('startup-no-connect-timeout', 'core/executor/ssh.py',
         (('        return Connection(self._host, **_bounded(self._connect_kwargs))\n',
           '        return Connection(self._host, **self._connect_kwargs)\n'),),
         ('test_startup.py::test_connect_is_bounded[default]',
          'test_startup.py::test_silent_banner_is_answered_within_the_bound'),
         'the connect has no bound'),
    # The filesystem tools hand the executor argvs (a shell only for a registered fixed script, with
    # values as its positional parameters), and write_file writes exactly the bytes sent, through the
    # executor's write, after validating them.
    Case('tool-command-string', 'core/tools/filesystem.py',
         (("        result = executor.run(['cat', '--', UserPath(path)])\n",
           "        result = executor.run(f'cat {path}')\n"),),
         ('test_tools.py::test_tool_reaches_only_the_installed_executor[read_file]',
          'test_literal_args.py::test_literal_argument[local-read_file-path]'),
         'passed a command string'),
    Case('fixed-script-interpolated', 'core/tools/filesystem.py',
         (("    result = executor.run(script_argv(LIST, 'list_directory', UserPath(path), *options))\n",
           "    result = executor.run(script_argv(LIST.replace('\"$1\"', __import__('shlex').quote(path)),"
           " 'list_directory', *options))\n"),),
         ('test_tools.py::test_tool_reaches_only_the_installed_executor[list_directory]',),
         'unregistered script'),
    Case('read-file-no-dashdash', 'core/tools/filesystem.py',
         (("        result = executor.run(['cat', '--', UserPath(path)])\n",
           "        result = executor.run(['cat', UserPath(path)])\n"),),
         ('test_tools.py::test_filesystem_argvs[read-cat]',),
         'argv differs'),
    Case('write-final-newline', 'core/tools/filesystem.py',
         (('        result = executor.write(path, data, append=append, parent=parent or None)\n',
           "        result = executor.write(path, data + b'\\n', append=append, parent=parent or None)\n"),),
         ('test_writes.py::test_writes_are_byte_exact[local-overwrite]',
          'test_writes.py::test_writes_are_byte_exact[delegate-overwrite]',
          'test_writes.py::test_writes_are_byte_exact[ssh-overwrite]'),
         'differs from the bytes sent'),
    Case('content-in-argv', 'core/tools/filesystem.py',
         (('        result = executor.write(path, data, append=append, parent=parent or None)\n',
           "        result = executor.run(['/bin/sh', '-c', 'printf %s \"$1\" >\"$2\"', 'w', content, path])\n"),),
         ('test_writes.py::test_content_never_travels_in_argv[overwrite]',),
         'content in argv'),
    Case('append-overwrites', 'core/tools/filesystem.py',
         (('        result = executor.write(path, data, append=append, parent=parent or None)\n',
           '        result = executor.write(path, data, append=False, parent=parent or None)\n'),),
         ('test_writes.py::test_writes_are_byte_exact[local-append]',
          'test_writes.py::test_writes_are_byte_exact[delegate-append]',
          'test_writes.py::test_writes_are_byte_exact[ssh-append]'),
         'differs from the bytes sent'),
    Case('create-dirs-dirname-subst', 'core/executor/launch.py',
         (("""WRITE_MKDIR: Final = 'mkdir -p -- "$2" && '""", """WRITE_MKDIR: Final = 'mkdir -p -- "$(dirname -- "$1")" && '"""),),
         ('test_writes.py::test_create_dirs_makes_the_exact_parent[local]',
          'test_writes.py::test_create_dirs_makes_the_exact_parent[delegate]'),
         'not written'),
    Case('base64-unvalidated', 'core/tools/filesystem.py',
         (('validate=True', 'validate=False'),),
         ('test_writes.py::test_invalid_write_leaves_the_target_untouched[local]',
          'test_writes.py::test_refused_writes_never_reach_the_executor[vertical-tab]'),
         'was accepted'),
    Case('write-before-validate', 'core/tools/filesystem.py',
         (('    data = _content_bytes(content, encoding)\n    executor = get_executor()\n',
           "    executor = get_executor()\n    executor.write(path, b'')\n"
           '    data = _content_bytes(content, encoding)\n'),),
         ('test_writes.py::test_invalid_write_leaves_the_target_untouched[local]',
          'test_writes.py::test_invalid_write_leaves_the_target_untouched[delegate]'),
         'target changed'),
    # The Slurm tools hand the executor argvs: each option value its own element after its option, a
    # positional after `--`, the job script's arguments after its path, the extra options as a list
    # of single arguments, and script_content written exactly, through the executor's write.
    Case('sbatch-args-joined', 'slurm/tools.py',
         (("    argv += [*options, '--', path, *(args or [])]\n",
           "    argv += [*options, '--', path, *([' '.join(args)] if args else [])]\n"),),
         ('test_sbatch.py::test_args_follow_the_script_and_extra_args_precede_dashdash',
          'test_sbatch.py::test_sbatch_receives_each_value_as_one_argument[local]'),
         'does not end with the extra options'),
    Case('extra-args-accepts-str', 'slurm/tools.py',
         (('    error: Optional[str] = None,\n    extra_args: Optional[List[str]] = None,\n',
           '    error: Optional[str] = None,\n    extra_args: Optional[List[str] | str] = None,\n'),
          ('    me: bool = True,\n    extra_args: Optional[List[str]] = None,\n) -> str:\n    """\n    View the Slurm job queue.',
           '    me: bool = True,\n    extra_args: Optional[List[str] | str] = None,\n) -> str:\n    """\n    View the Slurm job queue.'),
          ('    if not extra_args:\n        return []\n',
           '    if not extra_args:\n        return []\n    if isinstance(extra_args, str):\n        extra_args = extra_args.split()\n')),
         ('test_sbatch.py::test_a_string_list_parameter_is_refused_by_the_schema[extra_args-legacy]',
          'test_sbatch.py::test_a_string_list_parameter_is_refused_by_the_schema[extra_args-modern]',
          'test_extra_args.py::test_a_string_extra_args_is_refused_by_the_schema[squeue-legacy]',
          'test_extra_args.py::test_a_string_extra_args_is_refused_by_the_schema[squeue-modern]'),
         'as a string was accepted'),
    Case('extra-args-swallow-dashdash', 'slurm/tools.py',
         (('        path = UserPath(script_path)\n', '        path = script_path\n'),),
         ('test_sbatch.py::test_sbatch_receives_each_value_as_one_argument[local]',
          'test_sbatch.py::test_sbatch_receives_each_value_as_one_argument[delegate]'),
         'readable as an option'),
    Case('option-value-joined', 'slurm/tools.py',
         (('            argv += [option, value]\n', "            argv.append(f'{option}{value}')\n"),),
         ('test_tools.py::test_slurm_and_site_argvs[squeue]',
          'test_tools.py::test_slurm_and_site_argvs[sinfo]',
          'test_tools.py::test_slurm_and_site_argvs[sbatch]',
          'test_literal_args.py::test_literal_argument[delegate-sinfo-format]',
          'test_literal_args.py::test_literal_argument[ssh-sbatch-mem]'),
         'argv differs'),
    Case('script-content-newline', 'slurm/tools.py',
         (('            written = executor.write(path, data, parent=DEFAULT_JOBS_DIR, executable=True)\n',
           "            written = executor.write(path, data + b'\\n', parent=DEFAULT_JOBS_DIR, executable=True)\n"),),
         ('test_writes.py::test_job_scripts_are_byte_exact[local]',
          'test_writes.py::test_job_scripts_are_byte_exact[delegate]',
          'test_writes.py::test_job_scripts_are_byte_exact[ssh]'),
         'differs from the bytes sent'),
    # A job script's name carries a token drawn per call from the entropy source, so no two calls
    # share one: not in one second, and not across server processes alike in clock, pid and host.
    Case('script-name-per-second', 'slurm/tools.py',
         (("    return UserPath(f'{DEFAULT_JOBS_DIR}/{name}_{timestamp}_{token}.sh')\n",
           "    return UserPath(f'{DEFAULT_JOBS_DIR}/{name}_{timestamp}.sh')\n"),),
         ('test_sbatch.py::test_same_second_scripts_get_their_own_paths[same-name]',
          'test_writes.py::test_same_second_scripts_keep_their_own_bytes[local]',
          'test_sbatch.py::test_overlapping_submissions_each_submit_their_own_script[local-one-server]'),
         'share a script path'),
    Case('script-name-process-counter', 'slurm/tools.py',
         (('import secrets\n', 'import itertools\nimport secrets\n_SCRIPT_COUNTER = itertools.count()\n'),
          ('    token = secrets.token_hex(8)\n', "    token = f'{next(_SCRIPT_COUNTER):016x}'\n")),
         ('test_sbatch.py::test_separate_server_processes_name_scripts_apart',),
         'share a script path'),
    # The sbatch docstring states the token's width, so a narrower token is a served falsehood.
    Case('script-token-short', 'slurm/tools.py',
         (('    token = secrets.token_hex(8)\n', '    token = secrets.token_hex(4)\n'),),
         ('test_sbatch.py::test_the_docstring_states_the_script_path_the_tool_writes',),
         'does not match the docstring'),
    # The sbatch docstring states the name an empty job name falls back to, so another is a served
    # falsehood.
    Case('script-fallback-renamed', 'slurm/tools.py',
         (("    name = UNSAFE_NAME.sub('_', job_name or '').lstrip('.-') or 'job'\n",
           "    name = UNSAFE_NAME.sub('_', job_name or '').lstrip('.-') or 'script'\n"),),
         ('test_sbatch.py::test_the_docstring_states_the_script_path_the_tool_writes',),
         'does not match the docstring'),
    Case('empty-optional-passed-literally', 'slurm/tools.py',
         (('        if value:\n            argv += [option, value]\n',
           '        if value is not None:\n            argv += [option, value]\n'),),
         tuple(f'test_tools.py::test_empty_optional_scalars_mean_not_given[{row}]'
               for row in ('squeue-user', 'squeue', 'scancel', 'sacct', 'sinfo', 'sbatch'))
         + ('test_literal_args.py::test_literal_argument[local-squeue-state]',),
         'argv differs'),
    Case('scontrol-node-positional', 'slurm/tools.py',
         (("        argv += ['--', node]\n", '        argv += [node]\n'),),
         ('test_tools.py::test_slurm_and_site_argvs[scontrol-node]',
          'test_literal_args.py::test_literal_argument[local-scontrol_show_node-node]'),
         'argv differs'),
    # The site's `average_wait` passes options it does not know to `sacct`, whose partition option is
    # `--partition` (`-p` there is `--parsable`, which takes no value).
    Case('average-wait-short-partition', 'rcac/tools.py',
         (("        argv += ['--partition', partition]\n", "        argv += ['-p', partition]\n"),),
         ('test_tools.py::test_slurm_and_site_argvs[average-wait]',),
         'argv differs'),
    # An empty optional positional was not given: `scontrol show node` shows every node, and an
    # empty script path leaves sbatch nothing to submit.
    Case('empty-positional-passed-literally', 'slurm/tools.py',
         (('    if not script_path and script_content is None:\n',
           '    if script_path is None and script_content is None:\n'),
          ('    if script_path and script_content is not None:\n',
           '    if script_path is not None and script_content is not None:\n'),
          ('    if node:\n', '    if node is not None:\n')),
         ('test_tools.py::test_empty_optional_scalars_mean_not_given[scontrol-node]',
          'test_tools.py::test_empty_optional_scalars_mean_not_given[sbatch-script-path]',
          'test_literal_args.py::test_literal_argument[local-scontrol_show_node-node]',
          'test_literal_args.py::test_literal_argument[local-sbatch-script_path]'),
         'argv differs'),
    # An empty directory to list, or an empty cwd, was not given. (Bash runs `cd ''` as staying
    # put, so no matrix row can see either: the exact calls pin them.)
    Case('empty-list-path-passed-literally', 'core/tools/filesystem.py',
         (("    path = path or '.'\n", ''),),
         ('test_tools.py::test_empty_optional_scalars_mean_not_given[list-directory]',),
         'argv differs'),
    Case('empty-cwd-passed-literally', 'core/tools/shell.py',
         (('cwd=cwd or None', 'cwd=cwd'),),
         ('test_tools.py::test_empty_optional_scalars_mean_not_given[run-command-cwd]',),
         'argv differs'),
    # An empty transfer path names no file: refused, naming the parameter, before anything runs. The
    # row's calls run concurrently, so under this mutant the empty path's upload races another into
    # the same file and the call's own failure varies; its reaching the executor does not.
    Case('transfer-empty-path-passed', 'core/tools/transfer.py',
         (("    if not path:\n        raise ValueError(f'{name} is empty: an empty path names no file')\n", ''),),
         ('test_literal_args.py::test_literal_argument[ssh-upload_file-remote_path]',),
         'reaches the executor as an empty path'),
    # Every string argument with a lone surrogate is refused naming its parameter, in every mode.
    Case('surrogate-unnamed', 'core/tools/__init__.py',
         (('    func = _literal_text(func)\n', ''),),
         ('test_literal_args.py::test_literal_argument[local-squeue-user]',
          'test_literal_args.py::test_literal_argument[ssh-upload_file-local_path]'),
         'does not name'),
    # The deprecated rcac-mcp command warns once on stderr, then is cluster-mcp: same exit status,
    # same stdout, and nothing of its own on stdout, which carries the stdio transport.
    Case('legacy-command-silent', 'core/__init__.py',
         (("    legacy_warning('the rcac-mcp command', 'cluster-mcp')\n", ''),),
         tuple(f'test_cli.py::test_legacy_command_warns_then_runs_cluster_mcp[{argv}]'
               for argv in ('none', 'help', 'version', 'bogus')),
         'not the deprecation warning'),
    Case('legacy-command-exit-swallowed', 'core/__init__.py',
         (('    return main(argv)\n', '    main(argv)\n    return 0\n'),),
         ('test_cli.py::test_legacy_command_warns_then_runs_cluster_mcp[none]',
          'test_cli.py::test_legacy_command_warns_then_runs_cluster_mcp[bogus]'),
         'under rcac-mcp, 2 under cluster-mcp'),
    Case('legacy-warning-to-stdout', 'core/deprecation.py',
         (("    log.warning(f'{old} is {WINDOW}: use {new} instead')\n",
           "    print(f'{old} is {WINDOW}: use {new} instead')\n"),),
         ('test_cli.py::test_legacy_command_keeps_stdout_clean_on_stdio',),
         'not JSON-RPC'),
    # Each renamed variable: the replacement is read and wins over its legacy name; a legacy name
    # alone is honoured, with one warning on stderr naming the replacement and the window; nothing
    # is stripped. Every read site asks the resolver, so a site reading the replacement directly
    # drops the legacy name.
    Case('env-legacy-wins', 'core/deprecation.py',
         (('    value = os.environ.get(name)\n', '    value = os.environ.get(legacy) or os.environ.get(name)\n'),),
         tuple(f'test_env.py::test_replacement_wins_over_legacy[{name}]' for name in ENV_NAMES),
         'both set: resolved'),
    Case('env-legacy-ignored', 'core/deprecation.py',
         (('    value = os.environ.get(legacy)\n', '    value = None\n'),),
         tuple(f'test_env.py::test_legacy_is_honoured_with_a_warning[{name}]' for name in ENV_NAMES),
         'alone: resolved'),
    Case('env-replacement-ignored', 'core/deprecation.py',
         (('    value = os.environ.get(name)\n', '    value = None\n'),),
         tuple(f'test_env.py::test_replacement_is_read[{name}]' for name in ENV_NAMES),
         'alone: resolved'),
    Case('env-no-warning', 'core/deprecation.py',
         (('        legacy_warning(legacy, name)\n', '        pass\n'),),
         tuple(f'test_env.py::test_legacy_is_honoured_with_a_warning[{name}]' for name in ENV_NAMES)
         + tuple(f'test_env.py::test_warning_names_replacement_and_window[{name}-honoured]' for name in ENV_NAMES),
         'deprecation warnings on stderr, expected one'),
    Case('env-warning-to-stdout', 'core/deprecation.py',
         (('        legacy_warning(legacy, name)\n', "        print(f'{legacy} is {WINDOW}: use {name} instead')\n"),),
         tuple(f'test_env.py::test_warning_names_replacement_and_window[{name}-honoured]' for name in ENV_NAMES),
         'went to stdout'),
    Case('env-host-stripped', 'core/deprecation.py',
         (('    value = os.environ.get(name)\n', "    value = (os.environ.get(name) or '').strip()\n"),),
         ('test_env.py::test_whitespace_host_is_not_stripped[CLUSTER_MCP_SSH_HOST-space-replacement]',
          'test_exec_mode.py::test_env_host_selects_ssh[whitespace]'),
         'resolved'),
    Case('user-map-legacy-ignored', 'core/middleware.py',
         (("env_setting('CLUSTER_MCP_USER_MAP')[0]", "__import__('os').environ.get('CLUSTER_MCP_USER_MAP')"),),
         ('test_identity.py::test_user_map_is_read_from_either_name[legacy]',),
         'User map path required'),
    Case('budget-legacy-ignored', 'core/__init__.py',
         (("            value, variable = env_setting('CLUSTER_MCP_INSTRUCTIONS_BUDGET')\n",
           "            value, variable = os.environ.get('CLUSTER_MCP_INSTRUCTIONS_BUDGET'), 'CLUSTER_MCP_INSTRUCTIONS_BUDGET'\n"),),
         ('test_site_startup.py::test_budget_resolution[env-legacy]',),
         'expected [7100]'),
    # The served base is the generic core, the Slurm snippet and the RCAC-specific overlay, in that
    # order; the core names no site and no tool of the RCAC member; the server is named cluster-mcp in
    # both protocol eras.
    Case('overlay-dropped', 'core/server.py',
         (("    return '\\n\\n'.join((CORE_INSTRUCTIONS, *texts))\n",
           "    return '\\n\\n'.join((CORE_INSTRUCTIONS, *texts[:-1]))\n"),),
         ('test_instructions.py::test_base_is_core_slurm_then_overlay',),
         'not core, Slurm then overlay'),
    Case('core-names-rcac-tool', 'core/instructions.py',
         (('- download_file: Copy a file from the cluster\n',
           '- download_file: Copy a file from the cluster\n- myquota: Storage spaces, usage and quotas\n'),),
         ('test_instructions.py::test_core_instructions_are_generic',),
         "the core names the RCAC tool 'myquota'"),
    Case('server-name-rcac', 'core/server.py',
         (("name='cluster-mcp',", "name='RCAC',"),),
         ('test_protocol.py::test_server_identifies_as_cluster_mcp[legacy]',
          'test_protocol.py::test_server_identifies_as_cluster_mcp[modern]'),
         "serverInfo name is 'RCAC'"),
    # Capabilities register through the entry-point group: their texts compose by (order,
    # distribution) whatever order they are found or given in; a server serves the core's tools and
    # the given capabilities' only; no core module imports a member by name; and a capability whose
    # tool name is taken, whose tools module fails to import, or whose text does not list exactly its
    # tools is refused.
    Case('capability-order-from-discovery', 'core/capabilities.py',
         (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
           '    return tuple(capabilities)\n'),),
         ('test_capabilities.py::test_composition_order_ignores_discovery_order',
          *every_set(f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution')),
         'composition follows the given order'),
    Case('capability-tools-unfiltered', 'core/server.py',
         (('    serve(server, _tools_of(loaded), _resources_of(loaded))\n',
           "    serve(server, __import__('cluster_mcp.core.tools', fromlist=['TOOL_REGISTRY']).TOOL_REGISTRY, "
           "_resources_of(loaded))\n"),),
         ('test_capabilities.py::test_served_tools_are_the_core_and_the_given_capabilities[core-only]',
          'test_capabilities.py::test_served_tools_are_the_core_and_the_given_capabilities[slurm]'),
         'serves tools beyond or short of'),
    Case('core-imports-member-by-name', 'core/tools/__init__.py',
         (('from cluster_mcp.core.tools import context  # noqa: E402, F401\n',
           'from cluster_mcp.core.tools import context  # noqa: E402, F401\nimport cluster_mcp.slurm  # noqa: E402, F401\n'),),
         ('test_capabilities.py::test_core_imports_no_member',),
         'imports cluster_mcp.slurm'),
    Case('capability-duplicate-tool-allowed', 'core/capabilities.py',
         (("                if tool.name in core:\n"
           "                    raise CapabilityLoadError(distribution, f'tool {tool.name!r} is already registered by the core')\n"
           "                if tool.name in owners:\n"
           "                    raise CapabilityLoadError(distribution, f'tool {tool.name!r} is already registered by '\n"
           "                                                            f'{owners[tool.name]}')\n", ''),),
         ('test_capabilities.py::test_a_duplicate_tool_is_refused[member-tool]',
          'test_capabilities.py::test_a_duplicate_tool_is_refused[core-tool]',
          *every_set(TOOL_TAKEN, 'core', 'earlier')),
         'a duplicate tool loaded'),
    Case('capability-tools-import-swallowed', 'core/capabilities.py',
         (('            import_module(capability.tools)\n',
           '            try:\n'
           '                import_module(capability.tools)\n'
           '            except Exception:\n'
           '                continue\n'),),
         ('test_capabilities.py::test_a_tools_module_failure_names_the_distribution[tools-missing]',
          'test_capabilities.py::test_a_tools_module_failure_names_the_distribution[tools-raising]',
          *every_set(f'{CAPABILITIES}::test_a_failing_tools_module_is_refused_with_its_cause',
                     'tools-missing', 'tools-raising')),
         'a failing tools module loaded'),
    Case('capability-instructions-unchecked', 'core/capabilities.py',
         (('            if why:\n                raise CapabilityLoadError(distribution, why)\n', ''),),
         ('test_capabilities.py::test_instructions_must_list_exactly_the_tools[lists-another]',
          'test_capabilities.py::test_instructions_must_list_exactly_the_tools[omits-its-tool]',
          *every_set(LISTING, 'lists-another', 'omits-its-tool', 'lists-twice')),
         'instructions that do not list exactly its tools loaded'),
    # The storage resource and its alias are served exactly with the RCAC capability, and a capability
    # resource that claims to run nothing is refused at load rather than served gated.
    Case('storage-resource-unconditional', 'core/server.py',
         (('               *(entry for loaded in _listed(capabilities) for entry in loaded.capability.resources)]\n',
           '               *(entry for loaded in _listed(installed()) for entry in loaded.capability.resources)]\n'),),
         ('test_capabilities.py::test_storage_is_served_only_with_the_rcac_capability',),
         'served beyond or short of the core'),
    Case('capability-resource-open-allowed', 'core/capabilities.py',
         (("    if entry.get('executor') is not True:\n"
           "        raise _Invalid(f'its resource {entry[\"uri\"]!r} has executor {entry.get(\"executor\")!r}, not True: '\n"
           "                       f'a capability resource is never open')\n", ''),),
         ('test_capabilities.py::test_a_capability_resource_must_need_an_executor[false]',
          'test_capabilities.py::test_a_capability_resource_must_need_an_executor[missing]',
          'test_capabilities.py::test_a_capability_resource_must_need_an_executor[truthy]',
          *every_set(MALFORMED, 'resource-open', 'resource-open-truthy')),
         'an open resource loaded'),
    # An installed capability that cannot load stops the server at startup, before the mode ladder
    # runs, with the message naming its distribution: never a start with the capability missing.
    Case('capability-load-failure-swallowed', 'core/capabilities.py',
         (('                capability = _checked(ep.load())\n'
           '            except _Invalid as exc:\n'
           '                raise CapabilityLoadError(distribution, str(exc)) from exc\n',
           '                capability = _checked(ep.load())\n'
           '            except _Invalid as exc:\n'
           '                raise CapabilityLoadError(distribution, str(exc)) from exc\n'
           '            except Exception:\n'
           '                continue\n'),),
         ('test_startup.py::test_a_broken_capability_stops_startup[raw-wire]',
          'test_startup.py::test_a_broken_capability_stops_startup[modern]',
          'test_startup.py::test_a_broken_capability_stops_startup[rcac-mcp]',
          'test_startup.py::test_capabilities_load_before_the_mode_ladder',
          *every_set(f'{CAPABILITIES}::test_a_failing_capability_module_is_refused_with_its_cause',
                     'raising', 'raising-empty')),
         'does not name the distribution'),
    Case('capability-load-after-ladder', 'core/__init__.py',
         (('        self._load_capabilities()\n\n'
           '        # Determine execution mode\n'
           '        exec_mode = self._resolve_exec_mode()\n'
           "        log.info(f'Execution mode: {exec_mode}')\n",
           '\n        # Determine execution mode\n'
           '        exec_mode = self._resolve_exec_mode()\n'
           "        log.info(f'Execution mode: {exec_mode}')\n"
           '        self._load_capabilities()\n'),),
         ('test_startup.py::test_a_broken_capability_stops_startup[raw-wire]',
          'test_startup.py::test_a_broken_capability_stops_startup[rcac-mcp]',
          'test_startup.py::test_capabilities_load_before_the_mode_ladder',
          *every_set('test_startup.py::test_capabilities_load_before_the_mode_ladder_beside_every_set')),
         'the mode ladder ran before the capability load'),
    # Every decision the capability loader makes, mutated one at a time, each caught beside every
    # member set (core only, each member, both): what it refuses, the message it refuses with, how it
    # attributes a tool to its capability, the order it loads in, and how it assembles each
    # capability on its scratch server, as every server is assembled. A mutant that changes no
    # behaviour is not a case: it is recorded, with why, in the commit that added these.
    Case('capability-message-not-one-line', 'core/capabilities.py',
         (("        super().__init__(' '.join(f'cannot load capability {distribution}: {cause}'.split()))\n",
           "        super().__init__(f'cannot load capability {distribution}: {cause}')\n"),),
         every_set(REFUSED_AT_LOAD, 'resource-not-a-url'), 'the refusal is not one line'),
    Case('capability-named-by-entry-point-value', 'core/capabilities.py',
         (('    return name, None\n', '    return ep.value, None\n'),),
         every_set(REFUSED_AT_LOAD, 'resource-not-a-url'), 'a contribution the server would refuse loaded'),
    Case('capability-named-by-missing-distribution', 'core/capabilities.py',
         (('    if ep.dist is None:\n        return ep.value, None\n', ''),),
         every_set(f'{CAPABILITIES}::test_a_hand_built_entry_point_is_named_by_its_value'),
         'is not named by its value'),
    Case('capability-cause-always-with-text', 'core/capabilities.py',
         (("    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__\n",
           "    return f'{type(exc).__name__}: {text}'\n"),),
         every_set(f'{CAPABILITIES}::test_a_failing_capability_module_is_refused_with_its_cause', 'raising-empty'),
         'does not name the distribution with its cause'),
    Case('capability-cause-type-only', 'core/capabilities.py',
         (("    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__\n",
           '    return type(exc).__name__\n'),),
         every_set(f'{CAPABILITIES}::test_a_failing_capability_module_is_refused_with_its_cause', 'raising'),
         'does not name the distribution with its cause'),
    Case('capability-attribution-exact-module', 'core/capabilities.py',
         (("    return module == package or module.startswith(package + '.')\n", '    return module == package\n'),),
         every_set(f'{CAPABILITIES}::test_a_tool_below_the_tools_module_is_attributed_to_it'),
         'a tool below the tools module was refused'),
    Case('capability-attribution-by-prefix', 'core/capabilities.py',
         (("    return module == package or module.startswith(package + '.')\n",
           '    return module == package or module.startswith(package)\n'),),
         every_set(f'{CAPABILITIES}::test_a_tool_outside_the_tools_module_is_refused'),
         'a tool outside the tools module loaded'),
    Case('capability-type-unchecked', 'core/capabilities.py',
         (("    if type(value) is not Capability:\n"
           "        raise _Invalid(f'the entry point names a {type(value).__name__}, not a Capability')\n", ''),),
         every_set(MALFORMED, 'not-a-capability'), 'a malformed capability was not refused as such'),
    Case('capability-field-types-unchecked', 'core/capabilities.py',
         (("        if not isinstance(getattr(value, field), kind):\n"
           "            raise _Invalid(f'its {field} is a {type(getattr(value, field)).__name__}, not a {kind.__name__}')\n",
           '        pass\n'),),
         every_set(MALFORMED, 'name-not-a-str', 'tools-not-a-str', 'instructions-not-a-str', 'resources-not-a-tuple'),
         'a malformed capability was not refused as such'),
    Case('capability-order-unchecked', 'core/capabilities.py',
         (("    if not isinstance(value.order, int) or isinstance(value.order, bool):\n"
           "        raise _Invalid(f'its order is a {type(value.order).__name__}, not an int')\n", ''),),
         every_set(MALFORMED, 'order-not-an-int', 'order-a-bool'), 'a malformed capability was not refused as such'),
    Case('capability-order-bool-allowed', 'core/capabilities.py',
         (('    if not isinstance(value.order, int) or isinstance(value.order, bool):\n',
           '    if not isinstance(value.order, int):\n'),),
         every_set(MALFORMED, 'order-a-bool'), 'a malformed capability was not refused as such'),
    Case('capability-name-empty-allowed', 'core/capabilities.py',
         (("    if not value.name:\n        raise _Invalid('its name is empty')\n", ''),),
         every_set(MALFORMED, 'name-empty'), 'a malformed capability was not refused as such'),
    Case('capability-instructions-blank-allowed', 'core/capabilities.py',
         (('    if not value.instructions.strip():\n', '    if not value.instructions:\n'),),
         every_set(MALFORMED, 'instructions-blank'), 'a malformed capability was not refused as such'),
    Case('capability-resources-unchecked', 'core/capabilities.py',
         (('    for entry in value.resources:\n        _check_resource(entry)\n', ''),),
         every_set(MALFORMED, 'resource-not-a-dict', 'resource-name-not-a-str'),
         'a malformed capability was not refused as such'),
    Case('capability-resource-not-a-dict-allowed', 'core/capabilities.py',
         (("    if not isinstance(entry, dict):\n"
           "        raise _Invalid(f'one of its resources is a {type(entry).__name__}, not a dict')\n", ''),),
         every_set(MALFORMED, 'resource-not-a-dict'), 'a malformed capability was not refused as such'),
    Case('capability-resource-fields-unchecked', 'core/capabilities.py',
         (("        if not isinstance(entry.get(key), str):\n"
           "            raise _Invalid(f'its resource {entry.get(\"uri\")!r} has a {type(entry.get(key)).__name__} {key}, not a str')\n",
           '        pass\n'),),
         every_set(MALFORMED, 'resource-uri-not-a-str', 'resource-name-not-a-str', 'resource-description-not-a-str'),
         'a malformed capability was not refused as such'),
    Case('capability-resource-handler-unchecked', 'core/capabilities.py',
         (("    if not callable(entry.get('handler')):\n"
           "        raise _Invalid(f'the handler of its resource {entry[\"uri\"]!r} is not callable')\n", ''),),
         every_set(MALFORMED, 'resource-handler-not-callable'), 'a malformed capability was not refused as such'),
    Case('capability-resource-open-if-truthy', 'core/capabilities.py',
         (("    if entry.get('executor') is not True:\n", "    if not entry.get('executor'):\n"),),
         every_set(MALFORMED, 'resource-open-truthy'), 'an open resource loaded'),
    Case('capability-listing-subset-allowed', 'core/capabilities.py',
         (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
           '    if set(listed) <= set(names) and len(set(listed)) == len(listed):\n'),),
         every_set(LISTING, 'omits-its-tool'), 'instructions that do not list exactly its tools loaded'),
    Case('capability-listing-extra-unnamed', 'core/capabilities.py',
         (("    parts = ([f'list {extra}, which it does not register'] if extra else []) \\\n",
           '    parts = [] \\\n'),),
         every_set(LISTING, 'lists-another'), 'instructions that do not list exactly its tools loaded'),
    Case('capability-listing-missing-unnamed', 'core/capabilities.py',
         (("        + ([f'omit {missing}, which it registers'] if missing else []) \\\n", '        + [] \\\n'),),
         every_set(LISTING, 'omits-its-tool'), 'instructions that do not list exactly its tools loaded'),
    Case('capability-listing-twice-unnamed', 'core/capabilities.py',
         (("        + ([f'list {twice} more than once'] if twice else [])\n", '        + []\n'),),
         every_set(LISTING, 'lists-twice'), 'instructions that do not list exactly its tools loaded'),
    Case('capability-listing-twice-overcounted', 'core/capabilities.py',
         (('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
           '    twice = sorted({n for n in listed if listed.count(n) >= 1})\n'),),
         every_set(LISTING, 'lists-another'), 'instructions that do not list exactly its tools loaded'),
    Case('capability-serve-drops-tools', 'core/capabilities.py',
         (('    for tool in tools:\n        server.add_tool(tool)\n', '    for tool in ():\n        server.add_tool(tool)\n'),),
         tuple(f'{CAPABILITIES}::test_served_tools_are_the_core_and_the_given_capabilities[{names}]'
               for names in MEMBER_SETS), 'serves tools beyond or short of'),
    Case('capability-serve-drops-resources', 'core/capabilities.py',
         (('    for entry in resources:\n        server.resource(', '    for entry in ():\n        server.resource('),),
         every_set(f'{CAPABILITIES}::test_what_loads_is_served_whole'), 'is not served whole'),
    Case('capability-scratch-lets-duplicates-replace', 'core/capabilities.py',
         (("    server = FastMCP(name='cluster-mcp', on_duplicate='error')\n", "    server = FastMCP(name='cluster-mcp')\n"),),
         every_set(REFUSED_AT_LOAD, 'resource-uri-collides', 'resource-uri-collides-with-the-core'),
         'a contribution the server would refuse loaded'),
    Case('capability-scratch-without-core-resources', 'core/capabilities.py',
         (('    serve(server, CORE_TOOLS, RESOURCE_REGISTRY)\n', '    serve(server, CORE_TOOLS, ())\n'),),
         every_set(REFUSED_AT_LOAD, 'resource-uri-collides-with-the-core'),
         'a contribution the server would refuse loaded'),
    Case('capability-scratch-per-capability', 'core/capabilities.py',
         (('    scratch = _scratch()\n    try:\n        for distribution, nameless, ep in ordered:\n',
           '    try:\n        for distribution, nameless, ep in ordered:\n            scratch = _scratch()\n'),),
         every_set(f'{CAPABILITIES}::test_a_uri_colliding_with_an_earlier_capability_is_refused'),
         'as FastMCP keys it, loaded'),
    Case('capability-given-entry-points-ignored', 'core/capabilities.py',
         (('    found = _discovered() if eps is None else tuple(eps)\n', '    found = _discovered()\n'),),
         every_set(f'{CAPABILITIES}::test_a_hand_built_entry_point_is_named_by_its_value'),
         'is not named by its value'),
    Case('capability-load-order-unsorted', 'core/capabilities.py',
         (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n', '    ordered = entries\n'),),
         every_set(f'{CAPABILITIES}::test_capabilities_load_by_distribution_then_entry_point_name'),
         'does not follow (distribution, entry-point name)'),
    Case('capability-load-order-by-entry-point-name', 'core/capabilities.py',
         (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
           '    ordered = sorted(entries, key=lambda each: each.ep.name)\n'),),
         every_set(f'{CAPABILITIES}::test_capabilities_load_by_distribution_then_entry_point_name'),
         'does not follow (distribution, entry-point name)'),
    Case('capability-load-order-by-distribution-only', 'core/capabilities.py',
         (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
           '    ordered = sorted(entries, key=lambda each: each.distribution)\n'),),
         every_set(f'{CAPABILITIES}::test_capabilities_load_by_distribution_then_entry_point_name'),
         'does not follow (distribution, entry-point name)'),
    Case('capability-core-tool-names-forgotten', 'core/capabilities.py',
         (('    core = {tool.name for tool in CORE_TOOLS}\n', '    core = set()\n'),),
         every_set(TOOL_TAKEN, 'core'), 'a duplicate tool loaded'),
    Case('capability-core-uris-forgotten', 'core/capabilities.py',
         (("    core_uris = {entry['uri'] for entry in RESOURCE_REGISTRY}\n", '    core_uris = set()\n'),),
         every_set(URI_TAKEN, 'core', 'core-alias'), 'a duplicate resource URI loaded'),
    Case('capability-invalid-reported-as-exception', 'core/capabilities.py',
         (('            except _Invalid as exc:\n                raise CapabilityLoadError(distribution, str(exc)) from exc\n',
           '            except _Invalid as exc:\n                raise CapabilityLoadError(distribution, _cause(exc)) from exc\n'),),
         every_set(MALFORMED, 'not-a-capability', 'order-not-an-int'), 'a malformed capability was not refused as such'),
    Case('capability-non-tool-unseen', 'core/capabilities.py',
         (('            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if not isinstance(entry, FunctionTool)]\n',
           '            odd = []\n'),),
         every_set(REFUSED_AT_LOAD, 'tool-not-a-tool'), 'a contribution the server would refuse loaded'),
    Case('capability-non-tool-allowed', 'core/capabilities.py',
         (('            if odd:\n', '            if False:\n'),),
         every_set(REFUSED_AT_LOAD, 'tool-not-a-tool'), 'a contribution the server would refuse loaded'),
    Case('capability-stray-unseen', 'core/capabilities.py',
         (('                     if not _below(tool.fn.__module__, capability.tools)]\n', '                     if False]\n'),),
         every_set(f'{CAPABILITIES}::test_a_tool_outside_the_tools_module_is_refused'),
         'a tool outside the tools module loaded'),
    Case('capability-stray-allowed', 'core/capabilities.py',
         (('            if stray:\n', '            if False:\n'),),
         every_set(f'{CAPABILITIES}::test_a_tool_outside_the_tools_module_is_refused'),
         'a tool outside the tools module loaded'),
    Case('capability-name-taken-allowed', 'core/capabilities.py',
         (('            if capability.name in names:\n', '            if False:\n'),),
         every_set(f'{CAPABILITIES}::test_a_capability_name_already_taken_is_refused'),
         'a duplicate capability name loaded'),
    Case('capability-tools-only-from-the-import', 'core/capabilities.py',
         (('            tools = tuple(tool for tool in TOOL_REGISTRY if _below(tool.fn.__module__, capability.tools))\n',
           '            tools = tuple(tool for tool in TOOL_REGISTRY[before:] if _below(tool.fn.__module__, capability.tools))\n'),),
         every_set(f'{CAPABILITIES}::test_a_capability_whose_tools_are_already_imported_keeps_them'),
         'a capability whose tools module was already imported lost its tools'),
    Case('capability-same-capability-duplicate-allowed', 'core/capabilities.py',
         (('                if any(other.name == tool.name for other in tools[:i]):\n', '                if False:\n'),),
         every_set(f'{CAPABILITIES}::test_a_tool_registered_twice_by_one_capability_is_refused'),
         'a tool registered twice was not refused as such'),
    Case('capability-core-tool-allowed', 'core/capabilities.py',
         (('                if tool.name in core:\n', '                if False:\n'),),
         every_set(TOOL_TAKEN, 'core'), 'a duplicate tool loaded'),
    Case('capability-earlier-tool-allowed', 'core/capabilities.py',
         (('                if tool.name in owners:\n', '                if False:\n'),),
         every_set(TOOL_TAKEN, 'earlier'), 'a duplicate tool loaded'),
    Case('capability-uri-twice-allowed', 'core/capabilities.py',
         (('                if uri in uris[:i]:\n', '                if False:\n'),),
         every_set(URI_TAKEN, 'twice'), 'a duplicate resource URI loaded'),
    Case('capability-core-uri-allowed', 'core/capabilities.py',
         (('                if uri in core_uris:\n', '                if False:\n'),),
         every_set(URI_TAKEN, 'core', 'core-alias'), 'a duplicate resource URI loaded'),
    Case('capability-earlier-uri-allowed', 'core/capabilities.py',
         (('                if uri in uri_owners:\n', '                if False:\n'),),
         every_set(URI_TAKEN, 'earlier'), 'a duplicate resource URI loaded'),
    Case('capability-resources-not-assembled', 'core/capabilities.py',
         (('            for entry in capability.resources:\n                try:\n                    serve(scratch, (), (entry,))\n',
           '            for entry in ():\n                try:\n                    serve(scratch, (), (entry,))\n'),),
         every_set(REFUSED_AT_LOAD, 'resource-not-a-url', 'resource-handler-is-a-method'),
         'a contribution the server would refuse loaded'),
    Case('capability-resource-refusal-unattributed', 'core/capabilities.py',
         (('                    serve(scratch, (), (entry,))\n                except KeyboardInterrupt:\n'
           '                    raise\n                except BaseException as exc:\n',
           '                    serve(scratch, (), (entry,))\n                except KeyboardInterrupt:\n'
           '                    raise\n                except CapabilityLoadError as exc:\n'),),
         every_set(REFUSED_AT_LOAD, 'resource-not-a-url'), 'a contribution the server would refuse loaded'),
    Case('capability-names-not-recorded', 'core/capabilities.py',
         (('            names[capability.name] = distribution\n', ''),),
         every_set(f'{CAPABILITIES}::test_a_capability_name_already_taken_is_refused'),
         'a duplicate capability name loaded'),
    Case('capability-tool-owners-not-recorded', 'core/capabilities.py',
         (('            owners.update((tool.name, distribution) for tool in tools)\n', ''),),
         every_set(TOOL_TAKEN, 'earlier'), 'a duplicate tool loaded'),
    Case('capability-uri-owners-not-recorded', 'core/capabilities.py',
         (('            uri_owners.update((uri, distribution) for uri in uris)\n', ''),),
         every_set(URI_TAKEN, 'earlier'), 'a duplicate resource URI loaded'),
    Case('capability-refusal-keeps-registry', 'core/capabilities.py',
         ((ROLLBACK, ROLLBACK.replace('        del TOOL_REGISTRY[start:]\n', '').replace(
             '            raise\n', '            raise\n        del TOOL_REGISTRY[start:]\n')),),
         every_set(REFUSED_AT_LOAD, 'resource-not-a-url'), 'a refused load left'),
    Case('capability-other-exception-escapes', 'core/capabilities.py',
         (('        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n',
           '        if True:\n'),),
         every_set(REFUSED_AT_LOAD, 'tool-without-a-module'), 'not a CapabilityLoadError'),
    Case('capability-other-exception-keeps-registry', 'core/capabilities.py',
         ((ROLLBACK, ROLLBACK.replace('        del TOOL_REGISTRY[start:]\n', '').replace(
             '            raise\n', '            del TOOL_REGISTRY[start:]\n            raise\n')),),
         every_set(REFUSED_AT_LOAD, 'tool-without-a-module'), 'a refused load left'),
    Case('capability-composition-tie-unbroken', 'core/capabilities.py',
         (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
           '    return tuple(sorted(capabilities, key=lambda c: c.capability.order))\n'),),
         ('test_capabilities.py::test_composition_order_ignores_discovery_order',
          *every_set(f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution')),
         'composition follows the given order'),
    # Every alternative each decision of the capability load could take, not one per decision: each
    # condition always, never and negated, each boolean operator without each operand and with the
    # other, each comparison negated, each `except` widened, narrowed or re-raising, each type of a
    # pass-through tuple dropped, each other sort key over the fields it could use, the cache of a
    # failed load, where a capability's registrations begin to be checked, where `run()` loads the
    # capabilities, and where the core's tools split into the listing's opening and closing ones.
    # Each is killed beside every member set; the partition's index beside each set with a member, since
    # with the core alone the listing is every core tool in registration order wherever it splits (its
    # halves exchanged moves the site context tool first, which the core alone shows too).
    alternative('capability-identity-dist-always', LOADER,
                (('    if ep.dist is None:\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-declared',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-dist-negated', LOADER,
                (('    if ep.dist is None:\n',
                  '    if not ep.dist is None:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-declared',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-isinstance-strip-always', LOADER,
                (('    if not isinstance(name, str) or not name.strip():\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-identity-isinstance-strip-never', LOADER,
                (('    if not isinstance(name, str) or not name.strip():\n',
                  '    if False:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-blank-name',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-isinstance-strip-negated', LOADER,
                (('    if not isinstance(name, str) or not name.strip():\n',
                  '    if not (not isinstance(name, str) or not name.strip()):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-capability-always', LOADER,
                (('    if type(value) is not Capability:\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-capability-negated', LOADER,
                (('    if type(value) is not Capability:\n',
                  '    if not type(value) is not Capability:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-order-int-bool-always', LOADER,
                (('    if not isinstance(value.order, int) or isinstance(value.order, bool):\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-order-int-bool-negated', LOADER,
                (('    if not isinstance(value.order, int) or isinstance(value.order, bool):\n',
                  '    if not (not isinstance(value.order, int) or isinstance(value.order, bool)):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-name-empty-always', LOADER,
                (('    if not value.name:\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-name-empty-negated', LOADER,
                (('    if not value.name:\n',
                  '    if value.name:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-instructions-strip-always', LOADER,
                (('    if not value.instructions.strip():\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-instructions-strip-never', LOADER,
                (('    if not value.instructions.strip():\n',
                  '    if False:\n'),),
                f'{CAPABILITIES}::test_a_malformed_capability_is_refused_as_such', 'instructions-blank',
                'a malformed capability was not refused as such'),
    alternative('capability-check-instructions-strip-negated', LOADER,
                (('    if not value.instructions.strip():\n',
                  '    if value.instructions.strip():\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-resource-check-isinstance-dict-always', LOADER,
                (('    if not isinstance(entry, dict):\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-resource-check-isinstance-dict-negated', LOADER,
                (('    if not isinstance(entry, dict):\n',
                  '    if isinstance(entry, dict):\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-resource-check-callable-get-handler-always', LOADER,
                (("    if not callable(entry.get('handler')):\n",
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-resource-check-callable-get-handler-negated', LOADER,
                (("    if not callable(entry.get('handler')):\n",
                  "    if callable(entry.get('handler')):\n"),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-resource-check-get-executor-true-always', LOADER,
                (("    if entry.get('executor') is not True:\n",
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-resource-check-get-executor-true-negated', LOADER,
                (("    if entry.get('executor') is not True:\n",
                  "    if not entry.get('executor') is not True:\n"),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-listing-sorted-listed-names-len-set-always', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-sorted-listed-names-len-set-never', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if False:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-listing-sorted-listed-names-len-set-negated', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if not (sorted(listed) == sorted(names) and len(set(listed)) == len(listed)):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-installed-installed-always', LOADER,
                (('    if _installed is None:\n',
                  '    if True:\n'),),
                f'{CAPABILITIES}::test_a_failed_load_is_not_cached', '',
                'a load that succeeded was not cached'),
    alternative('capability-installed-installed-never', LOADER,
                (('    if _installed is None:\n',
                  '    if False:\n'),),
                f'{CAPABILITIES}::test_a_failed_load_is_not_cached', '',
                'a failed load was cached'),
    alternative('capability-installed-installed-negated', LOADER,
                (('    if _installed is None:\n',
                  '    if not _installed is None:\n'),),
                f'{CAPABILITIES}::test_a_failed_load_is_not_cached', '',
                'a failed load was cached'),
    alternative('capability-identity-exception-re-raises', LOADER,
                (('    except Exception as exc:\n'
                  "        return ep.value, f'its distribution metadata cannot be read: {_cause(exc)}'\n",
                  '    except Exception as exc:\n'
                  '        raise\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-unreadable',
                'the load raised UnicodeDecodeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-identity-isinstance-strip-without-operand-1', LOADER,
                (('    if not isinstance(name, str) or not name.strip():\n',
                  '    if not name.strip():\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-no-name',
                'the load raised AttributeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-identity-isinstance-strip-without-operand-2', LOADER,
                (('    if not isinstance(name, str) or not name.strip():\n',
                  '    if not isinstance(name, str):\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-blank-name',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-isinstance-strip-the-other-operator', LOADER,
                (('    if not isinstance(name, str) or not name.strip():\n',
                  '    if not isinstance(name, str) and (not name.strip()):\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-blank-name',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-named-exception-re-raises', LOADER,
                (('    except Exception:\n'
                  '        name = None\n',
                  '    except Exception:\n'
                  '        raise\n'),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'the load raised UnicodeDecodeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-named-isinstance-strip-getattr-dist-path-always', LOADER,
                (("    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))\n",
                  "    return name if True else str(getattr(dist, '_path', dist))\n"),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'unreadable entry points were not refused naming their distribution'),
    alternative('capability-named-isinstance-strip-getattr-dist-path-never', LOADER,
                (("    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))\n",
                  "    return name if False else str(getattr(dist, '_path', dist))\n"),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'named',
                'unreadable entry points were not refused naming their distribution'),
    alternative('capability-named-isinstance-strip-getattr-dist-path-negated', LOADER,
                (("    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))\n",
                  "    return name if not (isinstance(name, str) and name.strip()) else str(getattr(dist, '_path', dist))\n"),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'unreadable entry points were not refused naming their distribution'),
    alternative('capability-discovery-exception-re-raises', LOADER,
                (('    except Exception as exc:\n'
                  '        unreadable = exc\n',
                  '    except Exception as exc:\n'
                  '        raise\n'),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'the load raised TypeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-cause-keyboardinterrupt-exception', LOADER,
                (('        text = str(exc)\n'
                  '    except KeyboardInterrupt:\n',
                  '        text = str(exc)\n'
                  '    except Exception:\n'),),
                f'{CAPABILITIES}::test_a_keyboard_interrupt_while_loading_still_interrupts', 'in-its-text-declared',
                'a keyboard interrupt did not interrupt the load'),
    alternative('capability-cause-keyboardinterrupt-baseexception', LOADER,
                (('        text = str(exc)\n'
                  '    except KeyboardInterrupt:\n',
                  '        text = str(exc)\n'
                  '    except BaseException:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'raises-unprintable-at-declared',
                'the load raised SystemExit, not a CapabilityLoadError naming a capability'),
    alternative('capability-cause-baseexception-exception', LOADER,
                (('    except BaseException:\n',
                  '    except Exception:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'raises-unprintable-at-declared',
                'the load raised SystemExit, not a CapabilityLoadError naming a capability'),
    alternative('capability-cause-baseexception-re-raises', LOADER,
                (('    except BaseException:\n'
                  "        text = ''\n",
                  '    except BaseException:\n'
                  '        raise\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'raises-unprintable-at-declared',
                'the load raised SystemExit, not a CapabilityLoadError naming a capability'),
    alternative('capability-cause-type-text-negated', LOADER,
                (("    return f'{type(exc).__name__}: {text}' if text else type(exc).__name__\n",
                  "    return f'{type(exc).__name__}: {text}' if not text else type(exc).__name__\n"),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-declared',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-attribution-module-package-startswith-without-operand-1', LOADER,
                (("    return module == package or module.startswith(package + '.')\n",
                  "    return module.startswith(package + '.')\n"),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-attribution-module-package-startswith-the-other-operator', LOADER,
                (("    return module == package or module.startswith(package + '.')\n",
                  "    return module == package and module.startswith(package + '.')\n"),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-getattr-field-kind-always', LOADER,
                (('        if not isinstance(getattr(value, field), kind):\n',
                  '        if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-getattr-field-kind-negated', LOADER,
                (('        if not isinstance(getattr(value, field), kind):\n',
                  '        if isinstance(getattr(value, field), kind):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-check-isinstance-order-int-bool-without-operand-1', LOADER,
                (('    if not isinstance(value.order, int) or isinstance(value.order, bool):\n',
                  '    if isinstance(value.order, bool):\n'),),
                f'{CAPABILITIES}::test_a_malformed_capability_is_refused_as_such', 'order-not-an-int',
                'a malformed capability was not refused as such'),
    alternative('capability-check-isinstance-order-int-bool-the-other-operator', LOADER,
                (('    if not isinstance(value.order, int) or isinstance(value.order, bool):\n',
                  '    if not isinstance(value.order, int) and isinstance(value.order, bool):\n'),),
                f'{CAPABILITIES}::test_a_malformed_capability_is_refused_as_such', 'order-a-bool',
                'a malformed capability was not refused as such'),
    alternative('capability-resource-check-isinstance-get-always', LOADER,
                (('        if not isinstance(entry.get(key), str):\n',
                  '        if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-resource-check-isinstance-get-negated', LOADER,
                (('        if not isinstance(entry.get(key), str):\n',
                  '        if isinstance(entry.get(key), str):\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-listing-sorted-listed-names-len-set-without-operand-1', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if len(set(listed)) == len(listed):\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-sorted-listed-names-len-set-the-other-operator', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if sorted(listed) == sorted(names) or len(set(listed)) == len(listed):\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-load-found-discovered-eps-never', LOADER,
                (('    found = _discovered() if eps is None else tuple(eps)\n',
                  '    found = _discovered() if False else tuple(eps)\n'),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'the load raised TypeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-load-found-discovered-eps-negated', LOADER,
                (('    found = _discovered() if eps is None else tuple(eps)\n',
                  '    found = _discovered() if not eps is None else tuple(eps)\n'),),
                f'{CAPABILITIES}::test_a_hand_built_entry_point_is_named_by_its_value', '',
                'is not named by its value'),
    alternative('capability-load-order-key-value', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: each.ep.value)\n'),),
                f'{CAPABILITIES}::test_entry_points_load_by_distribution_then_name_not_value', '',
                'the load does not follow (distribution, entry-point name)'),
    alternative('capability-load-order-key-distribution-value', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.value))\n'),),
                f'{CAPABILITIES}::test_entry_points_load_by_distribution_then_name_not_value', '',
                'the load does not follow (distribution, entry-point name)'),
    alternative('capability-load-order-key-name-distribution', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: (each.ep.name, each.distribution))\n'),),
                f'{CAPABILITIES}::test_entry_points_load_by_distribution_then_name_not_value', '',
                'the load does not follow (distribution, entry-point name)'),
    alternative('capability-load-order-key-name-value', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: (each.ep.name, each.ep.value))\n'),),
                f'{CAPABILITIES}::test_entry_points_load_by_distribution_then_name_not_value', '',
                'the load does not follow (distribution, entry-point name)'),
    alternative('capability-load-order-key-value-distribution', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: (each.ep.value, each.distribution))\n'),),
                f'{CAPABILITIES}::test_entry_points_load_by_distribution_then_name_not_value', '',
                'the load does not follow (distribution, entry-point name)'),
    alternative('capability-load-order-key-value-name', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: (each.ep.value, each.ep.name))\n'),),
                f'{CAPABILITIES}::test_entry_points_load_by_distribution_then_name_not_value', '',
                'the load does not follow (distribution, entry-point name)'),
    alternative('capability-load-order-key-reversed', LOADER,
                (('    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name))\n',
                  '    ordered = sorted(entries, key=lambda each: (each.distribution, each.ep.name), reverse=True)\n'),),
                f'{CAPABILITIES}::test_a_tool_name_already_taken_is_refused', 'earlier',
                'a duplicate tool loaded'),
    alternative('capability-load-baseexception-exception', LOADER,
                (('            loaded.append(Loaded(capability, distribution, tools))\n'
                  '    except BaseException as exc:\n',
                  '            loaded.append(Loaded(capability, distribution, tools))\n'
                  '    except Exception as exc:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-declared',
                'the load raised SystemExit, not a CapabilityLoadError naming a capability'),
    alternative('capability-load-failure-passes-re-raises', LOADER,
                (('    except BaseException as exc:\n'
                  '        del TOOL_REGISTRY[start:]\n'
                  '        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n'
                  '            raise\n'
                  '        raise CapabilityLoadError(distribution, _cause(exc)) from exc\n',
                  '    except BaseException as exc:\n'
                  '        raise\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-declared',
                'the load raised SystemExit, not a CapabilityLoadError naming a capability'),
    alternative('capability-named-isinstance-strip-getattr-dist-path-without-operand-1', LOADER,
                (("    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))\n",
                  "    return name if name.strip() else str(getattr(dist, '_path', dist))\n"),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'the load raised AttributeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-named-isinstance-strip-getattr-dist-path-without-operand-2', LOADER,
                (("    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))\n",
                  "    return name if isinstance(name, str) else str(getattr(dist, '_path', dist))\n"),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'blank-name',
                'unreadable entry points were not refused naming their distribution'),
    alternative('capability-named-isinstance-strip-getattr-dist-path-the-other-operator', LOADER,
                (("    return name if isinstance(name, str) and name.strip() else str(getattr(dist, '_path', dist))\n",
                  "    return name if isinstance(name, str) or name.strip() else str(getattr(dist, '_path', dist))\n"),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'the load raised AttributeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-discovery-exception-re-raises-2', LOADER,
                (('        except Exception as exc:\n'
                  "            raise CapabilityLoadError(_named(dist), f'its entry points cannot be read: {_cause(exc)}') from exc\n",
                  '        except Exception as exc:\n'
                  '            raise\n'),),
                f'{CAPABILITIES}::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution', 'metadata-unreadable',
                'the load raised TypeError, not a CapabilityLoadError naming a capability'),
    alternative('capability-attribution-module-package-startswith-noteq', LOADER,
                (("    return module == package or module.startswith(package + '.')\n",
                  "    return module != package or module.startswith(package + '.')\n"),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-listing-sorted-listed-names-len-set-noteq', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if sorted(listed) != sorted(names) and len(set(listed)) == len(listed):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-listing-sorted-listed-names-len-set-noteq-2', LOADER,
                (('    if sorted(listed) == sorted(names) and len(set(listed)) == len(listed):\n',
                  '    if sorted(listed) == sorted(names) and len(set(listed)) != len(listed):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-listing-list-twice-more-than-once-always', LOADER,
                (("        + ([f'list {twice} more than once'] if twice else [])\n",
                  "        + ([f'list {twice} more than once'] if True else [])\n"),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-list-twice-more-than-once-negated', LOADER,
                (("        + ([f'list {twice} more than once'] if twice else [])\n",
                  "        + ([f'list {twice} more than once'] if not twice else [])\n"),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-load-nameless-always', LOADER,
                (('            if nameless:\n',
                  '            if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-nameless-never', LOADER,
                (('            if nameless:\n',
                  '            if False:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-blank-name',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-nameless-negated', LOADER,
                (('            if nameless:\n',
                  '            if not nameless:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-odd-always', LOADER,
                (('            if odd:\n',
                  '            if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-odd-negated', LOADER,
                (('            if odd:\n',
                  '            if not odd:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-stray-always', LOADER,
                (('            if stray:\n',
                  '            if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-stray-negated', LOADER,
                (('            if stray:\n',
                  '            if not stray:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-capability-names-always', LOADER,
                (('            if capability.name in names:\n',
                  '            if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-capability-names-negated', LOADER,
                (('            if capability.name in names:\n',
                  '            if not capability.name in names:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-why-always', LOADER,
                (('            if why:\n',
                  '            if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-why-negated', LOADER,
                (('            if why:\n',
                  '            if not why:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-failure-passes-never', LOADER,
                (('        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n',
                  '        if False:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-failure-passes-negated', LOADER,
                (('        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n',
                  '        if not isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-declared',
                'the load raised SystemExit, not a CapabilityLoadError naming a capability'),
    alternative('capability-composition-key-distribution', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: c.distribution))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-name', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: c.capability.name))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-tools', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: c.capability.tools))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-order-name', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.capability.name)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-order-tools', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.capability.tools)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-distribution-order', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.distribution, c.capability.order)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-distribution-name', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.distribution, c.capability.name)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-distribution-tools', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.distribution, c.capability.tools)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-name-order', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.name, c.capability.order)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-name-distribution', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.name, c.distribution)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-name-tools', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.name, c.capability.tools)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-tools-order', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.tools, c.capability.order)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-tools-distribution', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.tools, c.distribution)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-tools-name', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.tools, c.capability.name)))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-composition-key-reversed', LOADER,
                (('    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution)))\n',
                  '    return tuple(sorted(capabilities, key=lambda c: (c.capability.order, c.distribution), reverse=True))\n'),),
                f'{CAPABILITIES}::test_composition_breaks_ties_by_distribution', '',
                'composed out of (order, distribution)'),
    alternative('capability-listing-twice-sorted-listed-count-always', LOADER,
                (('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
                  '    twice = sorted({n for n in listed if True})\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-twice-sorted-listed-count-never', LOADER,
                (('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
                  '    twice = sorted({n for n in listed if False})\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-twice',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-twice-sorted-listed-count-negated', LOADER,
                (('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
                  '    twice = sorted({n for n in listed if not listed.count(n) > 1})\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-parts-list-extra-which-it-does-register-always', LOADER,
                (("    parts = ([f'list {extra}, which it does not register'] if extra else []) \\\n",
                  "    parts = ([f'list {extra}, which it does not register'] if True else []) \\\n"),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-twice',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-parts-list-extra-which-it-does-register-negated', LOADER,
                (("    parts = ([f'list {extra}, which it does not register'] if extra else []) \\\n",
                  "    parts = ([f'list {extra}, which it does not register'] if not extra else []) \\\n"),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-omit-missing-which-it-registers-always', LOADER,
                (("        + ([f'omit {missing}, which it registers'] if missing else []) \\\n",
                  "        + ([f'omit {missing}, which it registers'] if True else []) \\\n"),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-twice',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-omit-missing-which-it-registers-negated', LOADER,
                (("        + ([f'omit {missing}, which it registers'] if missing else []) \\\n",
                  "        + ([f'omit {missing}, which it registers'] if not missing else []) \\\n"),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-load-invalid-exception', LOADER,
                (('            except _Invalid as exc:\n',
                  '            except Exception as exc:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'raises-at-entry-point',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-invalid-baseexception', LOADER,
                (('            except _Invalid as exc:\n',
                  '            except BaseException as exc:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-entry-point',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-invalid-re-raises', LOADER,
                (('            except _Invalid as exc:\n'
                  '                raise CapabilityLoadError(distribution, str(exc)) from exc\n',
                  '            except _Invalid as exc:\n'
                  '                raise\n'),),
                f'{CAPABILITIES}::test_a_malformed_capability_is_refused_as_such', 'instructions-blank',
                'a malformed capability was not refused as such'),
    alternative('capability-load-any-other-tools-i-always', LOADER,
                (('                if any(other.name == tool.name for other in tools[:i]):\n',
                  '                if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-any-other-tools-i-negated', LOADER,
                (('                if any(other.name == tool.name for other in tools[:i]):\n',
                  '                if not any((other.name == tool.name for other in tools[:i])):\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-core-always', LOADER,
                (('                if tool.name in core:\n',
                  '                if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-core-negated', LOADER,
                (('                if tool.name in core:\n',
                  '                if not tool.name in core:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-owners-always', LOADER,
                (('                if tool.name in owners:\n',
                  '                if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-owners-negated', LOADER,
                (('                if tool.name in owners:\n',
                  '                if not tool.name in owners:\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-uri-uris-i-always', LOADER,
                (('                if uri in uris[:i]:\n',
                  '                if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-uri-uris-i-negated', LOADER,
                (('                if uri in uris[:i]:\n',
                  '                if not uri in uris[:i]:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-uri-core-uris-always', LOADER,
                (('                if uri in core_uris:\n',
                  '                if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-uri-core-uris-negated', LOADER,
                (('                if uri in core_uris:\n',
                  '                if not uri in core_uris:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-uri-owners-always', LOADER,
                (('                if uri in uri_owners:\n',
                  '                if True:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-uri-owners-negated', LOADER,
                (('                if uri in uri_owners:\n',
                  '                if not uri in uri_owners:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-failure-passes-without-capabilityloaderror', LOADER,
                (('        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n',
                  '        if isinstance(exc, KeyboardInterrupt):\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-failure-passes-without-keyboardinterrupt', LOADER,
                (('        if isinstance(exc, (CapabilityLoadError, KeyboardInterrupt)):\n',
                  '        if isinstance(exc, CapabilityLoadError):\n'),),
                f'{CAPABILITIES}::test_a_keyboard_interrupt_while_loading_still_interrupts', 'in-its-text-served',
                'a keyboard interrupt did not interrupt the load'),
    alternative('capability-listing-twice-sorted-listed-count-lt', LOADER,
                (('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
                  '    twice = sorted({n for n in listed if listed.count(n) < 1})\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-twice',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-listing-twice-sorted-listed-count-eq', LOADER,
                (('    twice = sorted({n for n in listed if listed.count(n) > 1})\n',
                  '    twice = sorted({n for n in listed if listed.count(n) == 1})\n'),),
                f'{CAPABILITIES}::test_instructions_that_do_not_list_exactly_its_tools_are_refused', 'lists-another',
                'instructions that do not list exactly its tools loaded'),
    alternative('capability-load-odd-type-registry-before-isinstance-func-always', LOADER,
                (('            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if not isinstance(entry, FunctionTool)]\n',
                  '            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if True]\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-odd-type-registry-before-isinstance-func-never', LOADER,
                (('            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if not isinstance(entry, FunctionTool)]\n',
                  '            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if False]\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'not-a-tool-from-the-entry-point',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-odd-type-registry-before-isinstance-func-negated', LOADER,
                (('            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if not isinstance(entry, FunctionTool)]\n',
                  '            odd = [type(entry).__name__ for entry in TOOL_REGISTRY[before:] if isinstance(entry, FunctionTool)]\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-below-fn-module-capability-tools-always', LOADER,
                (('                     if not _below(tool.fn.__module__, capability.tools)]\n',
                  '                     if True]\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-below-fn-module-capability-tools-negated', LOADER,
                (('                     if not _below(tool.fn.__module__, capability.tools)]\n',
                  '                     if _below(tool.fn.__module__, capability.tools)]\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-tool-assembly-interrupt-clause-exception', LOADER,
                (('                    serve(scratch, (tool,), ())\n'
                  '                except KeyboardInterrupt:\n',
                  '                    serve(scratch, (tool,), ())\n'
                  '                except Exception:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'raises-at-served-tool',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-tool-assembly-interrupt-clause-baseexception', LOADER,
                (('                    serve(scratch, (tool,), ())\n'
                  '                except KeyboardInterrupt:\n',
                  '                    serve(scratch, (tool,), ())\n'
                  '                except BaseException:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served-tool',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-tool-assembly-clause-exception', LOADER,
                (('                    serve(scratch, (tool,), ())\n'
                  '                except KeyboardInterrupt:\n'
                  '                    raise\n'
                  '                except BaseException as exc:\n',
                  '                    serve(scratch, (tool,), ())\n'
                  '                except KeyboardInterrupt:\n'
                  '                    raise\n'
                  '                except Exception as exc:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served-tool',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-tool-assembly-clause-re-raises', LOADER,
                (('                except BaseException as exc:\n'
                  "                    raise CapabilityLoadError(distribution, f'its tool {tool.name!r} cannot be served: '\n"
                  "                                                            f'{_cause(exc)}') from exc\n",
                  '                except BaseException as exc:\n'
                  '                    raise\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served-tool',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-resource-assembly-interrupt-clause-exception', LOADER,
                (('                    serve(scratch, (), (entry,))\n'
                  '                except KeyboardInterrupt:\n',
                  '                    serve(scratch, (), (entry,))\n'
                  '                except Exception:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'raises-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-resource-assembly-interrupt-clause-baseexception', LOADER,
                (('                    serve(scratch, (), (entry,))\n'
                  '                except KeyboardInterrupt:\n',
                  '                    serve(scratch, (), (entry,))\n'
                  '                except BaseException:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-resource-assembly-clause-exception', LOADER,
                (('                    serve(scratch, (), (entry,))\n'
                  '                except KeyboardInterrupt:\n'
                  '                    raise\n'
                  '                except BaseException as exc:\n',
                  '                    serve(scratch, (), (entry,))\n'
                  '                except KeyboardInterrupt:\n'
                  '                    raise\n'
                  '                except Exception as exc:\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-resource-assembly-clause-re-raises', LOADER,
                (('                except BaseException as exc:\n'
                  '                    raise CapabilityLoadError(distribution, f\'its resource {entry["uri"]!r} cannot be served: \'\n'
                  "                                                            f'{_cause(exc)}') from exc\n",
                  '                except BaseException as exc:\n'
                  '                    raise\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-tools-registry-below-fn-module-capabilit-always', LOADER,
                (('            tools = tuple(tool for tool in TOOL_REGISTRY if _below(tool.fn.__module__, capability.tools))\n',
                  '            tools = tuple(tool for tool in TOOL_REGISTRY if True)\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-tools-registry-below-fn-module-capabilit-never', LOADER,
                (('            tools = tuple(tool for tool in TOOL_REGISTRY if _below(tool.fn.__module__, capability.tools))\n',
                  '            tools = tuple(tool for tool in TOOL_REGISTRY if False)\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-tools-registry-below-fn-module-capabilit-negated', LOADER,
                (('            tools = tuple(tool for tool in TOOL_REGISTRY if _below(tool.fn.__module__, capability.tools))\n',
                  '            tools = tuple(tool for tool in TOOL_REGISTRY if not _below(tool.fn.__module__, capability.tools))\n'),),
                f'{CAPABILITIES}::test_a_capability_whose_entry_point_imports_its_tools_loads', '',
                'a well-formed capability was refused'),
    alternative('capability-load-any-other-tools-i-noteq', LOADER,
                (('                if any(other.name == tool.name for other in tools[:i]):\n',
                  '                if any(other.name != tool.name for other in tools[:i]):\n'),),
                f'{CAPABILITIES}::test_a_tool_registered_twice_by_one_capability_is_refused', '',
                'a tool registered twice was not refused as such'),
    alternative('capability-installed-caches-a-failed-load-as-no-capability', LOADER,
                (('    if _installed is None:\n'
                  '        _installed = load()\n'
                  '    return _installed\n',
                  '    if _installed is None:\n'
                  '        try:\n'
                  '            _installed = load()\n'
                  '        except CapabilityLoadError:\n'
                  '            _installed = ()\n'
                  '            raise\n'
                  '    return _installed\n'),),
                f'{CAPABILITIES}::test_a_failed_load_is_not_cached', '',
                'a failed load was cached'),
    alternative('capability-installed-caches-a-failed-load-as-its-error-raised-again', LOADER,
                (('    if _installed is None:\n'
                  '        _installed = load()\n'
                  '    return _installed\n',
                  '    if _installed is None:\n'
                  '        try:\n'
                  '            _installed = load()\n'
                  '        except CapabilityLoadError as exc:\n'
                  '            _installed = exc\n'
                  '    if isinstance(_installed, CapabilityLoadError):\n'
                  '        raise _installed\n'
                  '    return _installed\n'),),
                f'{CAPABILITIES}::test_a_failed_load_is_not_cached', '',
                'a failed load was cached'),
    alternative('capability-registrations-checked-from-after-the-entry-point-loads', LOADER,
                (('            before = len(TOOL_REGISTRY)\n'
                  '            try:\n'
                  '                capability = _checked(ep.load())\n'
                  '            except _Invalid as exc:\n'
                  '                raise CapabilityLoadError(distribution, str(exc)) from exc\n'
                  '            import_module(capability.tools)\n',
                  '            try:\n'
                  '                capability = _checked(ep.load())\n'
                  '            except _Invalid as exc:\n'
                  '                raise CapabilityLoadError(distribution, str(exc)) from exc\n'
                  '            before = len(TOOL_REGISTRY)\n'
                  '            import_module(capability.tools)\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'not-a-tool-from-the-entry-point',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-registrations-checked-from-after-the-tools-module-is-imported', LOADER,
                (('            before = len(TOOL_REGISTRY)\n'
                  '            try:\n'
                  '                capability = _checked(ep.load())\n'
                  '            except _Invalid as exc:\n'
                  '                raise CapabilityLoadError(distribution, str(exc)) from exc\n'
                  '            import_module(capability.tools)\n',
                  '            try:\n'
                  '                capability = _checked(ep.load())\n'
                  '            except _Invalid as exc:\n'
                  '                raise CapabilityLoadError(distribution, str(exc)) from exc\n'
                  '            import_module(capability.tools)\n'
                  '            before = len(TOOL_REGISTRY)\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'not-a-tool-from-the-entry-point',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-load-placed-before-statement-1-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('        """Run the MCP server or generate token."""\n',
                  '        self._load_capabilities()\n'
                  '        """Run the MCP server or generate token."""\n'),),
                f'{STARTUP}::test_a_token_is_generated_before_any_capability_loads', '',
                'the capability load ran before the token was generated'),
    alternative('capability-load-placed-before-statement-2-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('        if self.generate_token_flag:\n',
                  '        self._load_capabilities()\n'
                  '        if self.generate_token_flag:\n'),),
                f'{STARTUP}::test_a_token_is_generated_before_any_capability_loads', '',
                'the capability load ran before the token was generated'),
    alternative('capability-load-placed-before-statement-4-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ("        log.info(f'Execution mode: {exec_mode}')\n",
                  '        self._load_capabilities()\n'
                  "        log.info(f'Execution mode: {exec_mode}')\n"),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-before-statement-6-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('        middlewares = []\n',
                  '        self._load_capabilities()\n'
                  '        middlewares = []\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-before-statement-7-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ("        if exec_mode == 'delegate':\n            # Delegate mode uses per-request executors via middleware\n",
                  '        self._load_capabilities()\n'
                  "        if exec_mode == 'delegate':\n            # Delegate mode uses per-request executors via middleware\n"),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-before-statement-8-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ("                log.info(f'SSH connection established to {executor.hostname}')\n"
                  '\n'
                  '        try:\n',
                  "                log.info(f'SSH connection established to {executor.hostname}')\n"
                  '\n'
                  '        self._load_capabilities()\n'
                  '        try:\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-at-the-end-of-its-body', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('                executor.close()\n',
                  '                executor.close()\n'
                  '        self._load_capabilities()\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-before-statement-1-of-its-try', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('            budget = self._resolve_budget()\n',
                  '            self._load_capabilities()\n'
                  '            budget = self._resolve_budget()\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-before-statement-2-of-its-try', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('            site = self._read_site(exec_mode, executor)\n',
                  '            self._load_capabilities()\n'
                  '            site = self._read_site(exec_mode, executor)\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-before-statement-3-of-its-try', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ('            mcp = create_mcp_server(self.auth, middlewares=middlewares, site=site, budget=budget,\n',
                  '            self._load_capabilities()\n'
                  '            mcp = create_mcp_server(self.auth, middlewares=middlewares, site=site, budget=budget,\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    *(alternative(f'capability-load-placed-before-the-{step}-of-its-try', CLI,
                  (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                    '        self._load_capabilities()\n'
                    '\n',
                    ''),
                   (line, '            self._load_capabilities()\n' + line)),
                  f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                  'the mode ladder ran before the capability load')
      for step, line in (('override', '            skipped = self._resolve_skip_probes()\n'),
                         ('budget-check', '            site_context.compose(base_instructions(installed()), site, budget)\n'),
                         ('probe', '            served = self._served(self._probe(exec_mode, executor, skipped))\n'))),
    alternative('capability-load-placed-before-statement-4-of-its-try', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ("            if self.transport == 'stdio':\n",
                  '            self._load_capabilities()\n'
                  "            if self.transport == 'stdio':\n"),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-at-the-end-of-its-try', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),
                 ("                mcp.run(transport='sse', host=self.host, port=self.port)\n"
                  "            elif self.transport == 'http':\n"
                  "                mcp.run(transport='streamable-http', host=self.host, port=self.port)\n",
                  "                mcp.run(transport='sse', host=self.host, port=self.port)\n"
                  "            elif self.transport == 'http':\n"
                  "                mcp.run(transport='streamable-http', host=self.host, port=self.port)\n"
                  '            self._load_capabilities()\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-placed-no-load', CLI,
                (('        # Load every installed capability before the mode ladder: one that cannot load stops startup\n'
                  '        self._load_capabilities()\n'
                  '\n',
                  ''),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'the mode ladder ran before the capability load'),
    alternative('capability-load-refusal-except-baseexception', CLI,
                (('        except CapabilityLoadError as exc:\n'
                  '            message = str(exc)\n'
                  '            self._report_startup_failure(message)\n'
                  '            raise StartupFailure(message) from exc\n',
                  '        except BaseException as exc:\n'
                  '            message = str(exc)\n'
                  '            self._report_startup_failure(message)\n'
                  '            raise StartupFailure(message) from exc\n'),),
                f'{STARTUP}::test_a_keyboard_interrupt_while_loading_interrupts_the_start_beside_every_set', '',
                'a keyboard interrupt did not interrupt the start'),
    alternative('capability-load-refusal-except-re-raises', CLI,
                (('        except CapabilityLoadError as exc:\n'
                  '            message = str(exc)\n'
                  '            self._report_startup_failure(message)\n'
                  '            raise StartupFailure(message) from exc\n',
                  '        except CapabilityLoadError as exc:\n'
                  '            raise\n'),),
                f'{STARTUP}::test_capabilities_load_before_the_mode_ladder_beside_every_set', '',
                'request 1 not answered'),
    partition_alternative('capability-partition-before-shell', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  ''),
                 ('from cluster_mcp.core.tools import shell  # noqa: E402, F401\n',
                  '_OPENING = len(TOOL_REGISTRY)\n'
                  'from cluster_mcp.core.tools import shell  # noqa: E402, F401\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-before-filesystem', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  ''),
                 ('from cluster_mcp.core.tools import filesystem  # noqa: E402, F401\n',
                  '_OPENING = len(TOOL_REGISTRY)\n'
                  'from cluster_mcp.core.tools import filesystem  # noqa: E402, F401\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-before-transfer', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  ''),
                 ('from cluster_mcp.core.tools import transfer  # noqa: E402, F401\n',
                  '_OPENING = len(TOOL_REGISTRY)\n'
                  'from cluster_mcp.core.tools import transfer  # noqa: E402, F401\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-before-core-tools', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  ''),
                 ('CORE_TOOLS: Final[tuple[Tool, ...]] = tuple(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY)\n'
                  'CORE_TOOLS: Final[tuple[Tool, ...]] = tuple(TOOL_REGISTRY)\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-0', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) - 6\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-1', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) - 5\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-2', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) - 4\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-3', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) - 3\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-4', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) - 2\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-5', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) - 1\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    partition_alternative('capability-partition-at-7', TOOLS,
                (('_OPENING = len(TOOL_REGISTRY)\n',
                  '_OPENING = len(TOOL_REGISTRY) + 1\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    alternative('capability-partition-halves-exchanged', TOOLS,
                (('CLOSING_TOOLS: Final[tuple[Tool, ...]] = CORE_TOOLS[_OPENING:]\n',
                  'CLOSING_TOOLS: Final[tuple[Tool, ...]] = CORE_TOOLS[:_OPENING]\n'),),
                f'{CAPABILITIES}::test_the_listing_opens_and_closes_with_the_core_tools_by_name', '',
                'the core tools do not open and close the listing'),
    alternative('capability-tool-assembly-dropped', LOADER,
                (('            for tool in tools:\n'
                  '                try:\n'
                  '                    serve(scratch, (tool,), ())\n'
                  '                except KeyboardInterrupt:\n'
                  '                    raise\n'
                  '                except BaseException as exc:\n'
                  "                    raise CapabilityLoadError(distribution, f'its tool {tool.name!r} cannot be served: '\n"
                  "                                                            f'{_cause(exc)}') from exc\n",
                  ''),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'exits-0-at-served-tool',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-name-key-error-exception', LOADER,
                (('    except KeyError:\n        name = None\n',
                  '    except Exception:\n        name = None\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-unreadable',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-name-key-error-baseexception', LOADER,
                (('    except KeyError:\n        name = None\n',
                  '    except BaseException:\n        name = None\n'),),
                f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it', 'nameless-unreadable',
                'a capability that cannot load was not refused naming it'),
    alternative('capability-identity-name-key-error-re-raises', LOADER,
                (('    except KeyError:\n        name = None\n',
                  '    except KeyError:\n        raise\n'),),
                f'{CAPABILITIES}::test_a_name_missing_as_a_key_error_is_no_name', '',
                'not a CapabilityLoadError'),
    Case('capability-installed-reloads-when-empty', LOADER,
         (('    if _installed is None:\n', '    if not _installed:\n'),),
         (f'{CAPABILITIES}::test_a_failed_load_is_not_cached[core-only]',), 'a load that succeeded was not cached'),
    # The deprecation window is one string, deprecated in 0.2.0, removed no earlier than 0.4.0, wherever
    # a user reads it: the constant, every warning (each emitter, and each call site that emits one),
    # and README's upgrade section, which states it once and pairs each deprecated name with its
    # replacement. Each test compares with the window written out, never with the constant.
    Case('deprecation-window-altered', 'core/deprecation.py',
         (("WINDOW: Final[str] = 'deprecated in 0.2.0, removed no earlier than 0.4.0'",
           "WINDOW: Final[str] = 'deprecated in 0.2.0, removed no earlier than 0.3.0'"),),
         ('test_deprecation_window.py::test_window_is_the_published_one', *COMMAND_WARNED,
          'test_cli.py::test_legacy_command_keeps_stdout_clean_on_stdio', *VARIABLE_WARNED['honoured'],
          *VARIABLE_WARNED['ignored']),
         'not the published window'),
    Case('legacy-warning-omits-window', 'core/deprecation.py',
         (("    log.warning(f'{old} is {WINDOW}: use {new} instead')\n",
           "    log.warning(f'{old} is deprecated: use {new} instead')\n"),),
         (*COMMAND_WARNED, *VARIABLE_WARNED['honoured']),
         'not the published window'),
    Case('ignored-warning-omits-window', 'core/deprecation.py',
         (("    log.warning(f'{old} is {WINDOW}, and ignored: {new} is set')\n",
           "    log.warning(f'{old} is deprecated, and ignored: {new} is set')\n"),),
         VARIABLE_WARNED['ignored'],
         'not the published window'),
    Case('legacy-command-own-window', 'core/__init__.py',
         (("    legacy_warning('the rcac-mcp command', 'cluster-mcp')\n",
           "    __import__('cluster_mcp.core.deprecation', fromlist=['log']).log.warning("
           "'the rcac-mcp command is deprecated in 0.2.0, removed no earlier than 0.3.0: use cluster-mcp instead')\n"),),
         COMMAND_WARNED,
         'not the published window'),
    Case('env-legacy-own-warning', 'core/deprecation.py',
         (('        legacy_warning(legacy, name)\n', "        log.warning(f'{legacy} is deprecated: use {name} instead')\n"),),
         VARIABLE_WARNED['honoured'],
         'not the published window'),
    Case('env-ignored-own-warning', 'core/deprecation.py',
         (('            ignored_warning(legacy, name)\n',
           "            log.warning(f'{legacy} is deprecated, and ignored: {name} is set')\n"),),
         VARIABLE_WARNED['ignored'],
         'not the published window'),
    Case('readme-window-altered', '', (), (README_TEST,), 'does not state the published window',
         readme('removed no earlier than 0.4.0, and keeps', 'removed no earlier than 0.3.0, and keeps')),
    Case('readme-upgrading-deleted', '', (), (README_TEST,), "has no '## Upgrading from rcac-mcp' section",
         readme(UPGRADING_SECTION, '')),
    Case('readme-command-row-dropped', '', (), (README_TEST,), "does not list 'rcac-mcp' as deprecated",
         readme(COMMAND_ROW, '')),
    Case('readme-variables-row-dropped', '', (), (README_TEST,), "does not list 'RCAC_SSH_HOST' as deprecated",
         readme(VARIABLES_ROW, '')),
    Case('readme-resources-row-dropped', '', (), (README_TEST,), "does not list 'rcac://context' as deprecated",
         readme(RESOURCES_ROW, '')),
    Case('readme-replacement-dropped', '', (), (README_TEST,), 'pairs deprecated names and replacements unevenly',
         readme('`CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP`, ', '`CLUSTER_MCP_SSH_HOST`, ')),
    Case('readme-replacements-swapped', '', (), (README_TEST,),
         "gives 'rcac://context' the replacement 'cluster://storage'",
         readme('`cluster://context` and `cluster://storage` |', '`cluster://storage` and `cluster://context` |')),
    # Every tool's annotations, each hint's presence and value, are 0.1.4's: none. A tool served with
    # annotations, or a hint added, dropped or changed against what the fixture records, fails the
    # served-surface comparison. 0.1.4 served no annotations, so a hint can only be dropped or changed
    # against a fixture planted to record some.
    Case('annotations-on-every-tool', 'core/tools/__init__.py', annotate('True', 'readOnlyHint=True'),
         SURFACE_TEST, "tool entry gained 'annotations'"),
    Case('empty-annotations-on-every-tool', 'core/tools/__init__.py', annotate('True', ''),
         SURFACE_TEST, "tool entry gained 'annotations'"),
    Case('annotations-on-one-tool', 'core/tools/__init__.py', annotate("func.__name__ == 'sacct'", 'readOnlyHint=True'),
         SURFACE_TEST, "sacct: tool entry gained 'annotations'"),
    Case('annotations-removed', '', (), SURFACE_TEST, "run_command: tool entry lost 'annotations'",
         recorded('{"readOnlyHint": true}')),
    Case('annotation-hint-flipped', 'core/tools/__init__.py',
         annotate("func.__name__ == 'run_command'", 'readOnlyHint=True, destructiveHint=False'),
         SURFACE_TEST, 'run_command: annotation readOnlyHint differs: False -> True',
         recorded('{"destructiveHint": false, "readOnlyHint": false}')),
    Case('annotation-hint-dropped', 'core/tools/__init__.py',
         annotate("func.__name__ == 'run_command'", 'readOnlyHint=True'),
         SURFACE_TEST, "run_command: annotations lost hint 'destructiveHint'",
         recorded('{"destructiveHint": false, "readOnlyHint": true}')),
    Case('annotation-hint-added', 'core/tools/__init__.py',
         annotate("func.__name__ == 'run_command'", 'readOnlyHint=True, idempotentHint=True'),
         SURFACE_TEST, "run_command: annotations gained hint 'idempotentHint'",
         recorded('{"readOnlyHint": true}')),
    # README's upgrade section pairs each deprecated name with exactly one replacement, whatever the
    # order of its rows; names no version but the window's two ends; and states the window as the
    # whole published phrase.
    Case('readme-contradicting-row-before', '', (), (README_TEST,), "pairs 'RCAC_SSH_HOST' 2 times",
         readme(VARIABLES_ROW, CONTRADICTING_ROW + VARIABLES_ROW)),
    Case('readme-contradicting-row-after', '', (), (README_TEST,), "pairs 'RCAC_SSH_HOST' 2 times",
         readme(VARIABLES_ROW, VARIABLES_ROW + CONTRADICTING_ROW)),
    Case('readme-row-repeated', '', (), (README_TEST,), "pairs 'rcac-mcp' 2 times",
         readme(COMMAND_ROW, COMMAND_ROW + COMMAND_ROW)),
    Case('readme-removed-in-other-words', '', (), (README_TEST,), "names the version '0.3.0'",
         readme('configuration to the Quick Start form above.\n',
                'configuration to the Quick Start form above. The old names will be removed in 0.3.0.\n')),
    Case('readme-kept-until-other-version', '', (), (README_TEST,), "names the version '0.3.0'",
         readme('and keeps working until it is removed:', 'and keeps working until 0.3.0:')),
    Case('readme-window-suffixed', '', (), (README_TEST,), "names the version '0.4.0-alpha'",
         readme(WINDOWED, 'removed no earlier than 0.4.0-alpha, and keeps')),
    Case('readme-window-extra-component', '', (), (README_TEST,), "names the version '0.4.0.1'",
         readme(WINDOWED, 'removed no earlier than 0.4.0.1, and keeps')),
    Case('readme-window-parenthetical', '', (), (README_TEST,), "names the version '0.3.0'",
         readme(WINDOWED, 'removed no earlier than 0.4.0 (0.3.0 for the command), and keeps')),
    Case('readme-upgrading-commented', '', (), (README_TEST,), "has no '## Upgrading from rcac-mcp' section",
         readme(UPGRADING_SECTION, f'<!--\n{UPGRADING_SECTION}-->\n\n')),
    # The command's warning is a whole stderr line: nothing but the level and the logger's name before
    # the message, so a contradicting prefix fails.
    Case('legacy-command-prefixed-warning', 'core/__init__.py',
         (("    legacy_warning('the rcac-mcp command', 'cluster-mcp')\n",
           "    legacy_warning('removed in 0.3.0; the rcac-mcp command', 'cluster-mcp')\n"),),
         (*COMMAND_WARNED, 'test_cli.py::test_legacy_command_keeps_stdout_clean_on_stdio'),
         'the deprecation warning'),
    # Every tool's top-level title is 0.1.4's: the one FastMCP 4 derives from its name. A title set on
    # one tool, on every tool, or where the server adds each tool fails the served-surface comparison.
    Case('title-on-one-tool', 'core/tools/__init__.py',
         titled("'Run a command' if func.__name__ == 'run_command' else None"),
         SURFACE_TEST, "run_command: tool entry gained the title 'Run a command'"),
    Case('title-on-every-tool', 'core/tools/__init__.py', titled('func.__name__'),
         SURFACE_TEST, "run_command: tool entry gained the title 'run_command'"),
    Case('title-at-add-tool', 'core/capabilities.py',
         (('        server.add_tool(tool)\n', "        server.add_tool(tool.model_copy(update={'title': tool.name}))\n"),),
         SURFACE_TEST, "run_command: tool entry gained the title 'run_command'"),
    # README's upgrade section, read from its source: every `|` line is the header, the delimiter or a
    # two-cell row of code spans; each variable and URI is named once, markup removed; versions are read
    # with markup removed, and outside the window only the rename's 0.2.0 appears, once; and the
    # section holds no HTML comment marker, wherever a reader would see one.
    *(Case(f'readme-{form}-row-{"before" if before else "after"}', '', (), (README_TEST,),
           'a table line the pairing does not read',
           readme(VARIABLES_ROW, row + VARIABLES_ROW if before else VARIABLES_ROW + row))
      for form, row in UNREAD_ROWS.items() for before in (True, False)),
    Case('readme-bullet-mapping', '', (), (README_TEST,), "names 'RCAC_SSH_HOST' 2 times",
         upgrading_paragraph('- `RCAC_SSH_HOST` is now `CLUSTER_SSH_HOST`.')),
    Case('readme-prose-mapping', '', (), (README_TEST,), "names 'RCAC_SSH_HOST' 2 times",
         upgrading_sentence('Set `CLUSTER_SSH_HOST` in place of `RCAC_SSH_HOST`.')),
    Case('readme-comment-in-code-spans', '', (), (README_TEST,), 'holds the HTML comment marker',
         upgrading_sentence('An HTML comment opens with `<!--`. The old names will be removed in 0.3.0. '
                            'A comment closes with `-->`.')),
    Case('readme-comment-fenced', '', (), (README_TEST,), 'holds the HTML comment marker',
         upgrading_paragraph('```\n<!-- removed in 0.3.0 -->\n```')),
    Case('readme-comment-across-paragraphs', '', (), (README_TEST,), 'holds the HTML comment marker',
         upgrading_paragraph('Notes open with <!-- and\n\nthe old names will be removed in 0.3.0; notes close with -->.')),
    Case('readme-version-escaped-dots', '', (), (README_TEST,), "names the version '0.3.0'",
         upgrading_sentence('The old names will be removed in 0\\.3\\.0.')),
    Case('readme-version-entity-dots', '', (), (README_TEST,), "names the version '0.3.0'",
         upgrading_sentence('The old names will be removed in 0&#46;3&#46;0.')),
    Case('readme-version-bold-component', '', (), (README_TEST,), "names the version '0.3.0'",
         upgrading_sentence('The old names will be removed in 0.**3**.0.')),
    Case('readme-removed-in-the-rename', '', (), (README_TEST,), "names ['0.2.0', '0.2.0'] outside the window",
         upgrading_sentence('The `rcac-mcp` command is removed in 0.2.0.')),
    # A comment in the section fails even where a reader would not see it, so a contradiction inside one
    # is caught: the check reads the section's source, not a rendering of it.
    Case('readme-contradiction-in-a-comment', '', (), (README_TEST,), 'holds the HTML comment marker',
         upgrading_sentence('<!-- The old names will be removed in 0.3.0. -->')),
    # The command's warning is the one stderr line naming rcac-mcp: a second warning, printed only when
    # the command serves (`-e`), fails the stdio session.
    Case('legacy-command-second-warning-when-serving', 'core/__init__.py',
         (("    legacy_warning('the rcac-mcp command', 'cluster-mcp')\n",
           "    legacy_warning('the rcac-mcp command', 'cluster-mcp')\n"
           "    if '-e' in (sys.argv if argv is None else argv):\n"
           "        __import__('cluster_mcp.core.deprecation', fromlist=['log']).log.warning("
           "'the rcac-mcp command is removed in 0.3.0: use cluster-mcp instead')\n"),),
         ('test_cli.py::test_legacy_command_keeps_stdout_clean_on_stdio',),
         '2 stderr lines name rcac-mcp'),
)

# The cluster:// twin of each case whose failure names an rcac:// shape it lets through, or whose
# plant defaults to the rcac scheme: the same plant (defaulting to cluster:// instead), killed by
# naming that shape's twin, so each scheme's neighbourhood is held by a kill of its own.
CLUSTER_TWINS = {
    'read-hook-open-by-prefix': 'cluster://contextual',
    'read-hook-open-by-suffix': 'xcluster://context',
    'read-hook-open-by-substring': ' cluster://context',
    'read-hook-open-within-open-uri': 'cluster://contex',
    'read-hook-open-if-prefix-of-open': 'cluster://contex',
    'read-hook-open-by-host': 'cluster://context/x',
    'read-hook-case-folded': 'cluster://CONTEXT',
    'read-hook-casefolded': 'CLUSTER://context',
    'read-hook-scheme-case-folded': 'CLUSTER://context',
    'read-hook-strips-trailing-slash': 'cluster://context/',
    'read-hook-strips-space': 'cluster://context ',
    'read-hook-strips-leading-space': ' cluster://context',
    'read-hook-drops-query-and-fragment': 'cluster://context?x=1',
    'read-hook-authority-only': 'cluster://context#f',
    'read-hook-ignores-scheme': 'xcluster://context',
    'read-hook-defaults-scheme': 'context',
    'read-hook-adds-authority-slashes': 'cluster:context',
    'read-hook-unquotes': 'cluster://%63ontext',
    'read-hook-nfkc-normalised': 'cluster://\uff43ontext',
    'open-set-holds-slash-variants': 'cluster://context/',
    'read-hook-strips-crlf': 'cluster://context\n',
    'read-hook-strips-trailing-query-or-fragment-mark': 'cluster://context?',
    'read-hook-drops-port': 'cluster://context:80',
    'read-hook-drops-userinfo': 'cluster://u@context',
    'read-hook-strips-trailing-dot': 'cluster://context.',
    'read-hook-removes-tab-and-newline': 'cluster://con\ttext',
    'read-hook-strips-leading-slash': '/cluster://context',
    'read-hook-strips-quotes-and-brackets': '<cluster://context>',
    'read-hook-strips-trailing-nul': 'cluster://context\x00',
    'read-hook-drops-dot-segment': 'cluster://context/.',
    'read-hook-any-normaliser': 'cluster://context#',
    'open-set-holds-query-variants': 'cluster://context?',
    'read-hook-refuses-unserved': 'CLUSTER://storage',
}


def cluster_twin(case: Case, shape: str) -> Case:
    """`case` planted for the cluster scheme, its failure naming `shape`; the near rows read cluster://context."""
    targets = near_refused('cluster://context') if case.targets == NEAR_REFUSED else case.targets
    edits = tuple((old, new.replace("'rcac://'", "'cluster://'")) for old, new in case.edits)
    return Case(f'{case.id}-cluster', case.file, edits, targets, let_through(shape))



# The capability probe: every decision of `core/probes.py`, and each check the load makes of a declared
# command, mutated to every alternative it could take (each condition always, never and negated, each
# boolean operator without each operand and with the other, each comparison negated, each `in` tuple
# without each element, each `except` widened, narrowed or re-raising), and the decisions no node kind
# names: the bound's figure, the worker thread's `daemon`, the timeout the lookup is given, and the
# lookup's words. Each is killed beside every member set by the probe's rows, or the load's.
PROBES_FILE = 'core/probes.py'
PROBE_ROWS = 'test_probes.py'

# Each target test, with the fragment its failure carries.
WITHHELD = (f'{PROBE_ROWS}::test_a_capability_is_withheld_when_one_of_its_commands_is_absent',
            'the verdict does not follow the answer')
ENDING = (f'{PROBE_ROWS}::test_every_ending_without_an_answer_serves_the_capability',
          'an ending without an answer did not serve')
HUNG = (f'{PROBE_ROWS}::test_a_hung_probe_is_abandoned_at_the_bound', 'a hung probe was not abandoned at the bound')
ONCE = (f'{PROBE_ROWS}::test_the_verdicts_are_decided_once', 'the verdicts changed on a later call')
NOTHING = (f'{PROBE_ROWS}::test_nothing_declared_runs_nothing', 'nothing was declared, yet the probe ran')
LOOKED_UP = (f'{PROBE_ROWS}::test_every_declared_command_is_looked_up_once',
             'the lookup was not one call of every declared command')
INTERRUPT = (f'{PROBE_ROWS}::test_an_interrupt_while_the_probe_starts_still_interrupts',
             'an interrupt while the probe started did not interrupt')
BASH = (f'{PROBE_ROWS}::test_the_lookup_finds_only_what_exec_runs', 'the lookup did not find exactly what exec runs')
WELL_FORMED = (f'{CAPABILITIES}::test_a_planted_capability_declares_commands_with_no_core_edit',
               'a well-formed command declaration was refused')
MALFORMED_COMMANDS = (f'{CAPABILITIES}::test_a_malformed_command_declaration_is_refused_at_load',
                      'a malformed command declaration was not refused as such')


def probe_alternative(case_id: str, file: str, edits: tuple[tuple[str, str], ...], target: tuple[str, str],
                      kind: str = '') -> Case:
    """A case killed by the target test's row for `kind` (or its only row) beside every member set."""
    test, why = target
    return Case(case_id, file, edits, every_set(test, kind), why)


CASES += (
    probe_alternative('probe-parse-newline-always', PROBES_FILE,
                      (("    if not stdout.endswith('\\n'):\n",
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-parse-newline-never', PROBES_FILE,
                      (("    if not stdout.endswith('\\n'):\n",
                        '    if False:\n'),),
                      ENDING, 'end-ended-by-cr'),
    probe_alternative('probe-parse-newline-negated', PROBES_FILE,
                      (("    if not stdout.endswith('\\n'):\n",
                        "    if stdout.endswith('\\n'):\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-shape-always', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-parse-shape-never', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        '    if False:\n'),),
                      ENDING, 'wrong-end'),
    probe_alternative('probe-parse-shape-negated', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        "    if not (len(lines) != count + 1 or lines[-1] != f'end {count}'):\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-shape-without-count', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        "    if lines[-1] != f'end {count}':\n"),),
                      ENDING, 'one-short'),
    probe_alternative('probe-parse-shape-without-end', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        '    if len(lines) != count + 1:\n'),),
                      ENDING, 'wrong-end'),
    probe_alternative('probe-parse-shape-and', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        "    if len(lines) != count + 1 and lines[-1] != f'end {count}':\n"),),
                      ENDING, 'wrong-end'),
    probe_alternative('probe-parse-shape-end-equal', PROBES_FILE,
                      (("    if len(lines) != count + 1 or lines[-1] != f'end {count}':\n",
                        "    if len(lines) != count + 1 or lines[-1] == f'end {count}':\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-lines-always', PROBES_FILE,
                      (("    if any(line not in ('0', '1') for line in lines[:-1]):\n",
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-parse-lines-never', PROBES_FILE,
                      (("    if any(line not in ('0', '1') for line in lines[:-1]):\n",
                        '    if False:\n'),),
                      ENDING, 'a-2'),
    probe_alternative('probe-parse-lines-negated', PROBES_FILE,
                      (("    if any(line not in ('0', '1') for line in lines[:-1]):\n",
                        "    if not any(line not in ('0', '1') for line in lines[:-1]):\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-lines-in', PROBES_FILE,
                      (("    if any(line not in ('0', '1') for line in lines[:-1]):\n",
                        "    if any(line in ('0', '1') for line in lines[:-1]):\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-lines-without-0', PROBES_FILE,
                      (("    if any(line not in ('0', '1') for line in lines[:-1]):\n",
                        "    if any(line not in ('1',) for line in lines[:-1]):\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-lines-without-1', PROBES_FILE,
                      (("    if any(line not in ('0', '1') for line in lines[:-1]):\n",
                        "    if any(line not in ('0',) for line in lines[:-1]):\n"),),
                      WITHHELD),
    probe_alternative('probe-parse-found-inverted', PROBES_FILE,
                      (("    return [line == '1' for line in lines[:-1]]\n",
                        "    return [line != '1' for line in lines[:-1]]\n"),),
                      WITHHELD),
    probe_alternative('probe-ask-timeout-always', PROBES_FILE,
                      (('    if result.exit_code == TIMEOUT_EXIT_CODE:\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-timeout-never', PROBES_FILE,
                      (('    if result.exit_code == TIMEOUT_EXIT_CODE:\n',
                        '    if False:\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-ask-timeout-negated', PROBES_FILE,
                      (('    if result.exit_code == TIMEOUT_EXIT_CODE:\n',
                        '    if not result.exit_code == TIMEOUT_EXIT_CODE:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-lost-always', PROBES_FILE,
                      (('    if result.exit_code == CONNECTION_LOST_EXIT_CODE:\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-lost-never', PROBES_FILE,
                      (('    if result.exit_code == CONNECTION_LOST_EXIT_CODE:\n',
                        '    if False:\n'),),
                      ENDING, 'connection-lost-code'),
    probe_alternative('probe-ask-lost-negated', PROBES_FILE,
                      (('    if result.exit_code == CONNECTION_LOST_EXIT_CODE:\n',
                        '    if not result.exit_code == CONNECTION_LOST_EXIT_CODE:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-not-started-always', PROBES_FILE,
                      (('    if result.exit_code == NOT_STARTED_EXIT_CODE:\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-not-started-never', PROBES_FILE,
                      (('    if result.exit_code == NOT_STARTED_EXIT_CODE:\n',
                        '    if False:\n'),),
                      ENDING, 'not-started-code'),
    probe_alternative('probe-ask-not-started-negated', PROBES_FILE,
                      (('    if result.exit_code == NOT_STARTED_EXIT_CODE:\n',
                        '    if not result.exit_code == NOT_STARTED_EXIT_CODE:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-exit-always', PROBES_FILE,
                      (('    if result.exit_code != 0:\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-exit-never', PROBES_FILE,
                      (('    if result.exit_code != 0:\n',
                        '    if False:\n'),),
                      ENDING, 'exit-1'),
    probe_alternative('probe-ask-exit-negated', PROBES_FILE,
                      (('    if result.exit_code != 0:\n',
                        '    if not result.exit_code != 0:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-unparsed-always', PROBES_FILE,
                      (('    if found is None:\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-ask-unparsed-never', PROBES_FILE,
                      (('    if found is None:\n',
                        '    if False:\n'),),
                      ENDING, 'empty'),
    probe_alternative('probe-ask-unparsed-negated', PROBES_FILE,
                      (('    if found is None:\n',
                        '    if not found is None:\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-no-answer-always', PROBES_FILE,
                      (('    if isinstance(answer, str):\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-no-answer-never', PROBES_FILE,
                      (('    if isinstance(answer, str):\n',
                        '    if False:\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-verdict-no-answer-negated', PROBES_FILE,
                      (('    if isinstance(answer, str):\n',
                        '    if not isinstance(answer, str):\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-reason-always', PROBES_FILE,
                      (('        return Verdict(loaded, True, answer if commands else None)\n',
                        '        return Verdict(loaded, True, answer)\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-verdict-reason-never', PROBES_FILE,
                      (('        return Verdict(loaded, True, answer if commands else None)\n',
                        '        return Verdict(loaded, True, None)\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-verdict-reason-negated', PROBES_FILE,
                      (('        return Verdict(loaded, True, answer if commands else None)\n',
                        '        return Verdict(loaded, True, answer if not commands else None)\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-verdict-missing-always', PROBES_FILE,
                      (('    missing = [name for name in commands if not answer[name]]\n',
                        '    missing = [name for name in commands if True]\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-missing-never', PROBES_FILE,
                      (('    missing = [name for name in commands if not answer[name]]\n',
                        '    missing = [name for name in commands if False]\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-missing-negated', PROBES_FILE,
                      (('    missing = [name for name in commands if not answer[name]]\n',
                        '    missing = [name for name in commands if answer[name]]\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-missing-reason-always', PROBES_FILE,
                      (('    return Verdict(loaded, not missing, f\'missing {", ".join(missing)}\' if missing else None)\n',
                        '    return Verdict(loaded, not missing, f\'missing {", ".join(missing)}\')\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-missing-reason-never', PROBES_FILE,
                      (('    return Verdict(loaded, not missing, f\'missing {", ".join(missing)}\' if missing else None)\n',
                        '    return Verdict(loaded, not missing, None)\n'),),
                      WITHHELD),
    probe_alternative('probe-verdict-missing-reason-negated', PROBES_FILE,
                      (('    return Verdict(loaded, not missing, f\'missing {", ".join(missing)}\' if missing else None)\n',
                        '    return Verdict(loaded, not missing, f\'missing {", ".join(missing)}\' if not missing else None)\n'),),
                      WITHHELD),
    probe_alternative('probe-verdicts-memo-always', PROBES_FILE,
                      (('        if self._verdicts is None:\n',
                        '        if True:\n'),),
                      ONCE),
    probe_alternative('probe-verdicts-memo-never', PROBES_FILE,
                      (('        if self._verdicts is None:\n',
                        '        if False:\n'),),
                      WITHHELD),
    probe_alternative('probe-verdicts-memo-negated', PROBES_FILE,
                      (('        if self._verdicts is None:\n',
                        '        if not self._verdicts is None:\n'),),
                      WITHHELD),
    probe_alternative('probe-verdicts-wait-always', PROBES_FILE,
                      (("            answer = (self._answer if self._answered.wait(self._deadline - time.monotonic())\n                      else f'did not answer within {self._bound:g} s')\n",
                        '            answer = self._answer\n'),),
                      HUNG),
    probe_alternative('probe-verdicts-wait-never', PROBES_FILE,
                      (("            answer = (self._answer if self._answered.wait(self._deadline - time.monotonic())\n                      else f'did not answer within {self._bound:g} s')\n",
                        "            answer = f'did not answer within {self._bound:g} s'\n"),),
                      WITHHELD),
    probe_alternative('probe-verdicts-wait-negated', PROBES_FILE,
                      (("            answer = (self._answer if self._answered.wait(self._deadline - time.monotonic())\n                      else f'did not answer within {self._bound:g} s')\n",
                        "            answer = (self._answer if not self._answered.wait(self._deadline - time.monotonic())\n                      else f'did not answer within {self._bound:g} s')\n"),),
                      WITHHELD),
    probe_alternative('probe-start-bound-always', PROBES_FILE,
                      (('    bound = PROBE_TIMEOUT if timeout is None else timeout\n',
                        '    bound = PROBE_TIMEOUT\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-start-bound-never', PROBES_FILE,
                      (('    bound = PROBE_TIMEOUT if timeout is None else timeout\n',
                        '    bound = timeout\n'),),
                      HUNG),
    probe_alternative('probe-start-bound-negated', PROBES_FILE,
                      (('    bound = PROBE_TIMEOUT if timeout is None else timeout\n',
                        '    bound = PROBE_TIMEOUT if not timeout is None else timeout\n'),),
                      ENDING, 'timeout-code'),
    probe_alternative('probe-start-nothing-always', PROBES_FILE,
                      (('    if not names:\n',
                        '    if True:\n'),),
                      WITHHELD),
    probe_alternative('probe-start-nothing-never', PROBES_FILE,
                      (('    if not names:\n',
                        '    if False:\n'),),
                      NOTHING),
    probe_alternative('probe-start-nothing-negated', PROBES_FILE,
                      (('    if not names:\n',
                        '    if names:\n'),),
                      WITHHELD),
    probe_alternative('probe-worker-catches-exception', PROBES_FILE,
                      (('        except BaseException as exc:\n            answer = _why(exc)\n',
                        '        except Exception as exc:\n            answer = _why(exc)\n'),),
                      ENDING, 'exit-0'),
    probe_alternative('probe-worker-re-raises', PROBES_FILE,
                      (('        except BaseException as exc:\n            answer = _why(exc)\n',
                        '        except BaseException as exc:\n            raise\n'),),
                      ENDING, 'exception'),
    probe_alternative('probe-thread-start-catches-baseexception', PROBES_FILE,
                      (('    except Exception as exc:\n        pending._post(_why(exc))\n',
                        '    except BaseException as exc:\n        pending._post(_why(exc))\n'),),
                      INTERRUPT),
    probe_alternative('probe-thread-start-re-raises', PROBES_FILE,
                      (('    except Exception as exc:\n        pending._post(_why(exc))\n',
                        '    except Exception as exc:\n        raise\n'),),
                      ENDING, 'thread-cannot-start'),
    probe_alternative('capability-commands-type-always', LOADER,
                      (('    if type(value.commands) is not tuple:\n',
                        '    if True:\n'),),
                      WELL_FORMED),
    probe_alternative('capability-commands-type-never', LOADER,
                      (('    if type(value.commands) is not tuple:\n',
                        '    if False:\n'),),
                      MALFORMED_COMMANDS, 'bare-string'),
    probe_alternative('capability-commands-type-negated', LOADER,
                      (('    if type(value.commands) is not tuple:\n',
                        '    if not type(value.commands) is not tuple:\n'),),
                      WELL_FORMED),
    probe_alternative('capability-command-type-always', LOADER,
                      (('        if type(command) is not str:\n',
                        '        if True:\n'),),
                      WELL_FORMED),
    probe_alternative('capability-command-type-never', LOADER,
                      (('        if type(command) is not str:\n',
                        '        if False:\n'),),
                      MALFORMED_COMMANDS, 'str-subclass'),
    probe_alternative('capability-command-type-negated', LOADER,
                      (('        if type(command) is not str:\n',
                        '        if not type(command) is not str:\n'),),
                      WELL_FORMED),
    probe_alternative('capability-command-name-always', LOADER,
                      (('        if not COMMAND.fullmatch(command):\n',
                        '        if True:\n'),),
                      WELL_FORMED),
    probe_alternative('capability-command-name-never', LOADER,
                      (('        if not COMMAND.fullmatch(command):\n',
                        '        if False:\n'),),
                      MALFORMED_COMMANDS, 'empty'),
    probe_alternative('capability-command-name-negated', LOADER,
                      (('        if not COMMAND.fullmatch(command):\n',
                        '        if COMMAND.fullmatch(command):\n'),),
                      WELL_FORMED),
    probe_alternative('capability-command-twice-always', LOADER,
                      (('        if command in value.commands[:i]:\n',
                        '        if True:\n'),),
                      WELL_FORMED),
    probe_alternative('capability-command-twice-never', LOADER,
                      (('        if command in value.commands[:i]:\n',
                        '        if False:\n'),),
                      MALFORMED_COMMANDS, 'twice'),
    probe_alternative('capability-command-twice-negated', LOADER,
                      (('        if command in value.commands[:i]:\n',
                        '        if not command in value.commands[:i]:\n'),),
                      WELL_FORMED),
    probe_alternative('probe-bound-5-s', PROBES_FILE,
                      (('PROBE_TIMEOUT: Final = 10.0\n',
                        'PROBE_TIMEOUT: Final = 5.0\n'),),
                      HUNG),
    probe_alternative('probe-bound-9-s', PROBES_FILE,
                      (('PROBE_TIMEOUT: Final = 10.0\n',
                        'PROBE_TIMEOUT: Final = 9.0\n'),),
                      HUNG),
    probe_alternative('probe-bound-11-s', PROBES_FILE,
                      (('PROBE_TIMEOUT: Final = 10.0\n',
                        'PROBE_TIMEOUT: Final = 11.0\n'),),
                      HUNG),
    probe_alternative('probe-bound-20-s', PROBES_FILE,
                      (('PROBE_TIMEOUT: Final = 10.0\n',
                        'PROBE_TIMEOUT: Final = 20.0\n'),),
                      HUNG),
    probe_alternative('probe-worker-not-a-daemon', PROBES_FILE,
                      (('daemon=True',
                        'daemon=False'),),
                      HUNG),
    probe_alternative('probe-lookup-without-timeout', PROBES_FILE,
                      (('timeout=timeout)',
                        'timeout=None)'),),
                      LOOKED_UP),
    probe_alternative('probe-lookup-twice-the-bound', PROBES_FILE,
                      (('timeout=timeout)',
                        'timeout=2 * timeout)'),),
                      LOOKED_UP),
    probe_alternative('probe-lookup-command-v', PROBES_FILE,
                      (('if type -P -- "$n" >/dev/null 2>&1',
                        'if command -v -- "$n" >/dev/null 2>&1'),),
                      BASH),
    probe_alternative('probe-lookup-type-t', PROBES_FILE,
                      (('if type -P -- "$n" >/dev/null 2>&1',
                        'if type -t -- "$n" >/dev/null 2>&1'),),
                      BASH),
    probe_alternative('probe-lookup-type-function-kept', PROBES_FILE,
                      (("    'unset -f type\\n'\n",
                        ''),),
                      BASH),
    probe_alternative('probe-lookup-answers-swapped', PROBES_FILE,
                      (('printf "1\\\\n"; else printf "0\\\\n"',
                        'printf "0\\\\n"; else printf "1\\\\n"'),),
                      BASH),
    probe_alternative('probe-lookup-without-count', PROBES_FILE,
                      (('    \'printf "end %s\\\\n" "$#"\\n\'\n',
                        ''),),
                      BASH),

)


# A capability record is exactly a `Capability`: the load's check of what the entry point names, put
# back to `isinstance`, lets a subclass load, whichever field its code reads.
SUBCLASS_KINDS = ('subclass-reads-nothing', 'subclass-reads-name', 'subclass-reads-order', 'subclass-reads-tools',
                  'subclass-reads-instructions', 'subclass-reads-resources', 'subclass-reads-commands')
UNLOADABLE_ROWS = f'{CAPABILITIES}::test_a_capability_that_cannot_load_is_refused_naming_it'

CASES += (
    Case('capability-check-exact-capability-isinstance', LOADER,
         (('    if type(value) is not Capability:\n',
           '    if not isinstance(value, Capability):\n'),),
         every_set(UNLOADABLE_ROWS, *SUBCLASS_KINDS), 'a capability that cannot load was not refused naming it'),
)


# Startup's probe step: every decision of `_resolve_skip_probes`, `_probe` and `_served`, mutated to every
# alternative it could take, the decisions no node kind names (the skip branches' order and what they
# serve, what the server is built from, what the budget is checked against), each probe statement of
# `run()` at every other boundary of its `try` and of its body and not at all, and the branch of
# `env_setting` for a variable with no legacy name. Each is killed beside every member set by a row of
# `test_probe_startup.py` (or, for the one the resolver alone can observe, of `test_env.py`).
PROBE_STARTUP = 'test_probe_startup.py'
DEPRECATION = 'core/deprecation.py'

ONCE = (f'{PROBE_STARTUP}::test_local_and_ssh_probe_once_after_the_executor', 'local',
        'the probe did not run once after the executor')
KEPT = (f'{PROBE_STARTUP}::test_the_server_is_built_from_what_the_probe_keeps', 'local-each-member',
        'the server was not built from what the probe kept')
NO_ANSWER = (f'{PROBE_STARTUP}::test_every_ending_without_an_answer_serves_every_capability', 'exit-1-local-stdio',
             'an ending without an answer did not serve every capability')
DELEGATE_UNSET = (f'{PROBE_STARTUP}::test_delegate_runs_no_probe_and_says_so', 'unset',
                  'delegate mode probed or did not say it skipped')
DELEGATE_OVERRIDDEN = (f'{PROBE_STARTUP}::test_delegate_runs_no_probe_and_says_so', 'variable',
                       'delegate mode probed or did not say it skipped')
FLAG = (f'{PROBE_STARTUP}::test_the_override_skips_every_probe', 'local-flag', 'the override did not skip every probe')
VARIABLE = (f'{PROBE_STARTUP}::test_the_override_skips_every_probe', 'local-variable-1',
            'the override did not skip every probe')
LEGACY_BUDGET = (f'{PROBE_STARTUP}::test_no_probe_runs_before_a_refusal', 'legacy-budget-short-of-every',
                 'a probe ran before the legacy-budget-short-of-every refusal')
BUDGET_ANSWER = (f'{PROBE_STARTUP}::test_the_budget_never_depends_on_the_answer', 'short-of-every-absent',
                 'the budget depends on the answer')


def startup_alternative(case_id: str, file: str, edits: tuple[tuple[str, str], ...], target: tuple[str, str, str]) -> Case:
    """A case killed by the target test's rows for its case beside every member set."""
    test, kind, why = target
    return Case(case_id, file, edits, every_set(test, kind), why)


SKIP_FLAG = "        if self.skip_probes:\n"
SKIP_VALUE = "        return variable if value else None\n"
DELEGATE_BRANCH = ("        if exec_mode == 'delegate':\n"
                   "            log.info('Capability probes skipped in delegate mode: every installed capability is served')\n"
                   "            return probes.unprobed(loaded)\n")
OVERRIDE_BRANCH = ("        if skipped:\n"
                   "            log.info(f'Capability probes skipped ({skipped}): every installed capability is served')\n"
                   "            return probes.unprobed(loaded)\n")
WITHHELD_TEST = "            if not verdict.served:\n"
REASON_TEST = "            if verdict.reason:\n"
NO_LEGACY = "    if legacy is None:\n"
NO_LEGACY_VALUE = "        return (value or None), name\n"

# The statements of `run()`'s `try`, in order, and where it ends; the statements of its body, and where
# it ends. The three the probe step adds are each placed before every other one, at each end, and nowhere.
RUN_TRY = ('            budget = self._resolve_budget()\n',
           '            skipped = self._resolve_skip_probes()\n',
           '            site = self._read_site(exec_mode, executor)\n',
           '            site_context.compose(base_instructions(installed()), site, budget)\n',
           '            served = self._served(self._probe(exec_mode, executor, skipped))\n',
           '            mcp = create_mcp_server(self.auth, middlewares=middlewares, site=site, budget=budget,\n',
           "            if self.transport == 'stdio':\n")
RUN_TRY_END = "                mcp.run(transport='streamable-http', host=self.host, port=self.port)\n"
RUN_BODY = ('        """Run the MCP server or generate token."""\n',
            '        if self.generate_token_flag:\n',
            '        self._load_capabilities()\n',
            '        exec_mode = self._resolve_exec_mode()\n',
            "        log.info(f'Execution mode: {exec_mode}')\n",
            '        executor = None\n',
            '        middlewares = []\n',
            "        if exec_mode == 'delegate':\n            # Delegate mode uses per-request executors via middleware\n",
            '        try:\n            budget = self._resolve_budget()\n')
RUN_BODY_END = '                executor.close()\n'
PROBE_STATEMENTS = {'override': RUN_TRY[1], 'check': RUN_TRY[3], 'probe': RUN_TRY[4]}


def placed(name: str, where: str | None, at: int | None) -> Case:
    """The probe statement `name` moved before statement `at + 1` of `run()`'s `where` (`try` or `body`;
    `at` past the last: at its end), or, with `where` None, dropped."""
    line = PROBE_STATEMENTS[name]
    edits: list[tuple[str, str]] = [(line, '')]
    if where == 'try':
        rest = [s for s in RUN_TRY if s != line]
        edits.append((rest[at], line + rest[at]) if at < len(rest) else (RUN_TRY_END, RUN_TRY_END + line))
    elif where == 'body':
        moved = line[4:]
        edits.append((RUN_BODY[at], moved + RUN_BODY[at]) if at < len(RUN_BODY)
                     else (RUN_BODY_END, RUN_BODY_END + moved))
    what = 'dropped' if where is None else f'placed-before-statement-{at + 1}-of-its-{where}'
    return startup_alternative(f'probe-step-{name}-{what}', CLI, tuple(edits), ONCE)


CASES += (
    startup_alternative('probe-override-flag-always', CLI, ((SKIP_FLAG, '        if True:\n'),), ONCE),
    startup_alternative('probe-override-flag-never', CLI, ((SKIP_FLAG, '        if False:\n'),), FLAG),
    startup_alternative('probe-override-flag-negated', CLI, ((SKIP_FLAG, '        if not self.skip_probes:\n'),), ONCE),
    startup_alternative('probe-override-value-always', CLI, ((SKIP_VALUE, '        return variable\n'),), ONCE),
    startup_alternative('probe-override-value-never', CLI, ((SKIP_VALUE, '        return None\n'),), VARIABLE),
    startup_alternative('probe-override-value-negated', CLI,
                        ((SKIP_VALUE, '        return variable if not value else None\n'),), ONCE),
    startup_alternative('probe-delegate-always', CLI,
                        (("        if exec_mode == 'delegate':\n            log.info('Capability probes skipped in",
                          "        if True:\n            log.info('Capability probes skipped in"),), ONCE),
    startup_alternative('probe-delegate-never', CLI,
                        (("        if exec_mode == 'delegate':\n            log.info('Capability probes skipped in",
                          "        if False:\n            log.info('Capability probes skipped in"),), DELEGATE_UNSET),
    startup_alternative('probe-delegate-negated', CLI,
                        (("        if exec_mode == 'delegate':\n            log.info('Capability probes skipped in",
                          "        if not exec_mode == 'delegate':\n            log.info('Capability probes skipped in"),),
                        ONCE),
    startup_alternative('probe-skipped-always', CLI, (('        if skipped:\n', '        if True:\n'),), ONCE),
    startup_alternative('probe-skipped-never', CLI, (('        if skipped:\n', '        if False:\n'),), FLAG),
    startup_alternative('probe-skipped-negated', CLI, (('        if skipped:\n', '        if not skipped:\n'),), ONCE),
    startup_alternative('probe-skip-branches-exchanged', CLI,
                        ((DELEGATE_BRANCH + OVERRIDE_BRANCH, OVERRIDE_BRANCH + DELEGATE_BRANCH),), DELEGATE_OVERRIDDEN),
    startup_alternative('probe-delegate-still-probes', CLI,
                        ((DELEGATE_BRANCH, DELEGATE_BRANCH.replace('probes.unprobed(loaded)', 'probes.start(executor, loaded)')),),
                        DELEGATE_UNSET),
    startup_alternative('probe-override-still-probes', CLI,
                        ((OVERRIDE_BRANCH, OVERRIDE_BRANCH.replace('probes.unprobed(loaded)', 'probes.start(executor, loaded)')),),
                        FLAG),
    startup_alternative('probe-served-withheld-always', CLI, ((WITHHELD_TEST, '            if True:\n'),), ONCE),
    startup_alternative('probe-served-withheld-never', CLI, ((WITHHELD_TEST, '            if False:\n'),), KEPT),
    startup_alternative('probe-served-withheld-negated', CLI, ((WITHHELD_TEST, '            if verdict.served:\n'),), ONCE),
    startup_alternative('probe-served-reason-always', CLI, ((REASON_TEST, '            if True:\n'),), ONCE),
    startup_alternative('probe-served-reason-never', CLI, ((REASON_TEST, '            if False:\n'),), NO_ANSWER),
    startup_alternative('probe-served-reason-negated', CLI, ((REASON_TEST, '            if not verdict.reason:\n'),), ONCE),
    startup_alternative('probe-server-built-from-every-installed', CLI,
                        (('                                    capabilities=served)',
                          '                                    capabilities=None)'),), KEPT),
    startup_alternative('probe-budget-checked-against-the-core-alone', CLI,
                        (('site_context.compose(base_instructions(installed()), site, budget)',
                          'site_context.compose(base_instructions(()), site, budget)'),), BUDGET_ANSWER),
    *(placed(name, 'try', at) for name in PROBE_STATEMENTS for at in range(len(RUN_TRY))
      if at != RUN_TRY.index(PROBE_STATEMENTS[name])),
    *(placed(name, 'body', at) for name in PROBE_STATEMENTS for at in range(len(RUN_BODY) + 1)),
    *(placed(name, None, None) for name in PROBE_STATEMENTS),
    startup_alternative('env-no-legacy-always', DEPRECATION, ((NO_LEGACY, '    if True:\n'),), LEGACY_BUDGET),
    startup_alternative('env-no-legacy-never', DEPRECATION, ((NO_LEGACY, '    if False:\n'),), ONCE),
    startup_alternative('env-no-legacy-negated', DEPRECATION, ((NO_LEGACY, '    if not legacy is None:\n'),), ONCE),
    startup_alternative('env-no-legacy-value-ignored', DEPRECATION,
                        ((NO_LEGACY_VALUE, '        return None, name\n'),), VARIABLE),
    startup_alternative('env-no-legacy-value-and', DEPRECATION,
                        ((NO_LEGACY_VALUE, '        return (value and None), name\n'),), VARIABLE),
    # An empty value handed back as itself, not None: the resolver alone can tell (every start reads it
    # as unset either way), so its row is the resolver's, with no member set to run beside.
    Case('env-no-legacy-value-empty-kept', DEPRECATION, ((NO_LEGACY_VALUE, '        return value, name\n'),),
         ('test_env.py::test_a_variable_without_a_legacy_name[empty-CLUSTER_MCP_SKIP_PROBES]',),
         "resolved ('', 'CLUSTER_MCP_SKIP_PROBES')"),
)

CASES += tuple(cluster_twin(case, CLUSTER_TWINS[case.id]) for case in CASES if case.id in CLUSTER_TWINS)
if len(CASES) != len({case.id for case in CASES}):
    raise RuntimeError('two mutation cases share an id')

# The runner's own controls (--self-check). A docstring edit changes no behaviour, so its target
# passes and the runner must call it a survivor; this proves the child really runs the targets.
SURVIVOR_CONTROL = Case(
    'control-docstring-only', 'core/context.py',
    (('"""Context management for request-scoped state."""',
      '"""Context management for request-scoped state (unchanged behaviour)."""'),),
    ('test_isolation.py::test_concurrent_delegate_calls_stay_isolated',),
    'ran as')


def apply(case: Case, dest: Path, omit: str | None = None) -> Path:
    """Copy every imported member under `dest/src/cluster_mcp`, apply the case's edits, return `dest/src`.

    A case that plants only into repository files (`file` empty) gets the copy unchanged.

    No `cluster_mcp/__init__.py` is written: the copy is a namespace portion like each member's own.
    `omit` leaves one member out of the copy (the runner's origin control).
    """
    src_root = dest / 'src'
    namespace = src_root / 'cluster_mcp'
    for name, member in MEMBERS.items():
        if name != omit:
            shutil.copytree(Path(member.__file__).parent, namespace / name, ignore=shutil.ignore_patterns('__pycache__'))
    if not case.file:
        return src_root
    path = namespace / case.file
    text = path.read_text()
    for old, new in case.edits:
        count = text.count(old)
        if count != 1:
            raise ValueError(f'{case.id}: the anchor occurs {count} times in {case.file}, expected once; '
                             f'the code this case plants against has moved: {old[:80]!r}')
        text = text.replace(old, new)
    path.write_text(text)
    return src_root


def apply_repo(case: Case, dest: Path) -> Path | None:
    """For a case with `repo_edits`, copy the repository's tests, `bin/` and top-level files to `dest/repo`, plant them, return the copy.

    A case without `repo_edits` gets None: its child runs in the repository itself.
    """
    if not case.repo_edits:
        return None
    root, repo = TESTS.parent, dest / 'repo'
    for name in ('tests', 'bin'):
        shutil.copytree(root / name, repo / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in REPO_TOP:
        shutil.copy2(root / name, repo / name)
    for name, old, new in case.repo_edits:
        if name not in REPO_FILES:
            raise ValueError(f'{case.id}: plants into {name}, which is not one of {REPO_FILES}')
        path = repo / name
        text = path.read_text()
        count = text.count(old)
        if count != 1:
            raise ValueError(f'{case.id}: the anchor occurs {count} times in {name}, expected once; '
                             f'the text this case plants against has moved: {old[:80]!r}')
        path.write_text(text.replace(old, new))
    return repo


def run_child(src_root: Path, targets: Sequence[str], junit: Path,
              repo: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run `targets` against the package under `src_root` in a sandboxed child pytest, in `repo` (default: this one)."""
    env = {**os.environ, 'PYTHONPATH': str(src_root), 'PYTHONDONTWRITEBYTECODE': '1'}
    return subprocess.run(
        [str(SANDBOX), 'sh', '-c', CHILD, 'sh', sys.executable, str(src_root), str(junit), str(repo or TESTS.parent),
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


def run_case(case: Case, src_override: Path | None = None, omit: str | None = None) -> list[str]:
    """Plant `case` in a scratch copy, run its targets, and return `mutation_violations`."""
    with tempfile.TemporaryDirectory(prefix=f'mutant-{case.id}-') as scratch:
        dest = Path(scratch)
        src_root = apply(case, dest, omit)
        repo = apply_repo(case, dest)
        junit = dest / 'junit.xml'
        child = run_child(src_override or src_root, case.targets, junit, repo)
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
    # A copy missing one member: that member loads from the editable install, not the copy.
    partial = run_case(SURVIVOR_CONTROL, omit='rcac')
    ok = any('wrong import origin' in v for v in partial)
    lines.append(f'{"control" if ok else "FAILED"}  member missing from the copy reported: {partial[:1]}')
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
