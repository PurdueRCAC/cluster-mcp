# SPDX-FileCopyrightText: 2026 Purdue University
# SPDX-License-Identifier: MIT

"""F2 (review 1): in `delegate` mode every read outside `OPEN_RESOURCES` resolves identity.

`uv run python spec/resource-reads-without-executor/remediation/F2-read-hook-refuses-by-default.py`,
from the tree root.

The property: the delegate read hook refuses by default. Every read outside `OPEN_RESOURCES` resolves
the request's identity before FastMCP looks the URI up, an unknown URI included, and only the open
set skips it. Both sides are pinned, in both eras: an unknown URI read by a request a `storage_paths`
call is refused for (no identity claim, all claims empty, unmapped, first claim unmapped) gets exactly
that call's reason (`test_unknown_uri_read_is_refused`), while a mapped caller and a tokenless one
still get `-32602 Resource not found` (`test_unknown_uri_is_not_found_in_delegate_mode`), as every
caller does in shared mode (`test_unknown_uri_is_not_found`). The `_install` decisions a read shares
with a tool call are pinned for reads too: alternating reads each set their own executor
(`test_sequential_storage_reads_each_get_their_executor`, now in both eras) and a read's identity
state is set and request-scoped (`test_delegate_read_state_is_request_scoped`).

The sweep: every case planted in `AuthExecutorMiddleware.on_read_resource` or `._install`, found by
where its anchor sits, plus the `OPEN_RESOURCES` cases in `resources.py`, each in both eras; the
reviewer's `read-hook-resolves-storage-only` among them. About 4 min, under 1 GB, one process tree
at a time.
"""

from __future__ import annotations

import sys

from sweep import cases_in, finish, run_sweep, run_tests

P = 'tests/test_protocol.py::'
S = 'tests/test_storage_resource.py::'
C = 'tests/test_context.py::'
TESTS = [f'{S}test_unknown_uri_read_is_refused', f'{S}test_unknown_uri_is_not_found_in_delegate_mode',
         f'{S}test_unknown_uri_is_not_found', f'{S}test_sequential_storage_reads_each_get_their_executor',
         f'{S}test_storage_read_runs_as_the_mapped_user', f'{C}test_any_client_reads_the_context_in_delegate_mode',
         f'{P}test_delegate_read_state_is_request_scoped', f'{P}test_read_state_scope_check_catches_drift']
COUNT = 8 + 4 + 2 + 2 + 2 + 8 + 2 + 1

REQUIRED = ['read-hook-resolves-storage-only', 'read-hook-ignores-open-set', 'read-hook-open-set-inverted',
            'read-hook-installs-after-handler', 'read-hook-drops-result', 'auth-read-sets-no-executor',
            'read-no-token-reuses-last-executor', 'no-token-refused-in-middleware', 'no-token-fallback-identity',
            'no-claim-not-refused', 'unmapped-gets-default-user', 'isolation-executor-cached',
            'auth-middleware-sets-first-call-only', 'delegate-state-session-scoped', 'delegate-state-not-set',
            'storage-read-left-open', 'context-read-closed']

# The OPEN_RESOURCES decisions live in resources.py, outside the middleware's spans.
EXTRAS = ['storage-read-left-open', 'context-read-closed']

EQUIVALENT = {
    'no-token-check-falsy': '`if not access_token` for `if access_token is None`: an AccessToken is always truthy',
    'read-hook-stringifies-uri': '`str(context.message.uri)`: FastMCP builds the read params with uri=str(uri), so it '
                                 'is a str already',
    'executor-set-after-state': 'set_executor after the two set_state calls: nothing between them reads the executor, '
                                'and set_state does not touch it',
}


def main() -> int:
    run_tests(TESTS, COUNT)
    cases = list(dict.fromkeys(cases_in('AuthExecutorMiddleware.on_read_resource', 'AuthExecutorMiddleware._install')
                               + EXTRAS))
    run_sweep(cases, REQUIRED, EQUIVALENT)
    return finish('F2 read hook refuses by default', cases, EQUIVALENT)


if __name__ == '__main__':
    sys.exit(main())
