# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""F1 (review 1): a refused read's client-visible error is exactly the refusal's text, in both eras.

`uv run python spec/resource-reads-without-executor/remediation/F1-read-boundary-text.py`, from the
tree root.

The property: a read refused around its handler reaches the client as an internal error (-32603)
whose text is exactly `str(exc)`, with no type name and no traceback, in both protocol eras, as
strictly as the tool boundary's text is pinned. The pins: `test_protocol.py`'s
`test_middleware_refusal_is_a_read_error` (a `PermissionError` in memory and over HTTP, a
`RuntimeError` in memory and over HTTP, an `MCPError`, any other `Exception`) with its drift control
`test_read_boundary_check_catches_drift`, the read row of `test_boundary_lets_cancellation_through`,
and `test_storage_resource.py`'s `test_storage_read_refused`, now exact against each row's full
reason rather than a containment check.

The sweep: every case planted in `_bounded` or `ToolErrorMiddleware.on_read_resource`, found by
where its anchor sits, each in both eras; the reviewer's `read-boundary-leaks-traceback` and
`read-boundary-type-name` among them. About 3 min, under 1 GB, one process tree at a time.
"""

from __future__ import annotations

import sys

from sweep import cases_in, finish, run_sweep, run_tests

P = 'tests/test_protocol.py::'
S = 'tests/test_storage_resource.py::'
TESTS = [f'{P}test_middleware_refusal_is_a_read_error', f'{P}test_read_boundary_check_catches_drift',
         f'{P}test_boundary_lets_cancellation_through', f'{S}test_storage_read_refused']
COUNT = 12 + 6 + 2 + 10

REQUIRED = ['read-boundary-leaks-traceback', 'read-boundary-type-name', 'read-boundary-dropped',
            'read-boundary-wraps-not-found', 'boundary-leaks-traceback', 'boundary-type-name',
            'boundary-catches-base-exception', 'boundary-catches-named-only', 'boundary-reraises-original',
            'boundary-passes-nothing', 'boundary-drops-result']

EQUIVALENT = {
    'read-boundary-raises-tool-error': "the read hook raising ToolError, not ResourceError: FastMCP's read handler "
                                       'turns every FastMCPError but NotFoundError, DisabledError and ValidationError '
                                       'into MCPError(-32603, str(exc)) (to_mcp_error), so both reach the wire identically',
    'read-boundary-wraps-disabled': 'DisabledError dropped from the read passes: FastMCP 4.1.4 raises DisabledError '
                                    'nowhere (only except clauses name it), so none reaches the boundary',
    'read-boundary-rewraps-fastmcp-error': 'FastMCPError dropped from the read passes: the only FastMCPError raised '
                                           "inside a read here is a handler's ResourceError, and ResourceError(str(exc)) "
                                           'reaches the wire as the same -32603 error with the same text',
    'boundary-drops-cause': '`from exc` dropped: the chained cause never reaches the wire',
    'read-boundary-passes-mcp-error': 'an MCPError let through the read hook reaches the client as itself; wrapped, '
                                      'it is -32603 with str(exc), the same error for the internal-error MCPError, the '
                                      'only kind anything raises around a read (nothing in the server raises one there)',
}


def main() -> int:
    run_tests(TESTS, COUNT)
    cases = cases_in('_bounded', 'ToolErrorMiddleware.on_read_resource')
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('F1 read boundary text', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
