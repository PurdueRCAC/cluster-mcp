# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The refusal rows the cycle's check needs exist, beside every member set, and the CLI drives a kind
of each family.

    uv run python -I spec/capability-tool-objects-inert/verify/rows.py      from the worktree root

Collects (never runs) `test_a_capability_that_cannot_load_is_refused_naming_it` and
`test_a_capability_that_cannot_load_stops_startup`, and requires, each from the installed FastMCP's
`FunctionTool.model_fields` and the load's `TOOL_RULES` as they stand when the gate runs (so a field
FastMCP adds, or a rule the build adds, asks for its rows):

- `tool-subclass-reads-<field>` for every model field, plus `tool-subclass-reads-nothing` and
  `tool-subclass-named-by-its-metaclass` (a subclass of `FunctionTool`, refused for its type);
- `tool-exact-<field>` for every model field (a value of a type of its own there; for `fn`, a callable
  that is not a function);
- `tool-default-<field>` for every field of `F_FIELDS` (the default rule; an exact value that is not
  its default), each mapped to `_default_violation` in `TOOL_RULES`;
- the depth and state rows `DEPTH` names;

each beside every member set (`<kind>-<set>`, `mutants.MEMBER_SETS`); and, among the CLI's kinds,
at least one `tool-subclass-` kind and one `tool-exact-` kind, each over every drive. Footprint: two
pytest collections in turn, under 300 MB, seconds.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'tests'))
import mutants  # noqa: E402
from fastmcp.tools.function_tool import FunctionTool  # noqa: E402

from cluster_mcp.core import capabilities  # noqa: E402

REFUSED = 'tests/test_capabilities.py::test_a_capability_that_cannot_load_is_refused_naming_it'
STOPS = 'tests/test_startup.py::test_a_capability_that_cannot_load_stops_startup'
DRIVES = ('raw-wire', 'stdin-closed', 'http')
# The fields PLAN.md § 2 gives the default rule (F), named here so a rule wrapped another way still asks for
# its rows; each must map to `_default_violation` itself.
F_FIELDS = ('version', 'title', 'icons', 'tags', 'meta', 'task_config', 'annotations', 'execution', 'auth',
            'timeout', 'run_in_thread')

# The rows at depth and in the instance state, by kind.
DEPTH = (
    'tool-exact-parameters-key', 'tool-exact-parameters-value', 'tool-exact-parameters-element',
    'tool-exact-parameters-twice', 'tool-exact-output_schema-value',
    'tool-exact-task_config-state', 'tool-exact-task_config-mode', 'tool-exact-task_config-poll_interval',
    'tool-exact-return_type-module', 'tool-exact-return_type-attribute-name', 'tool-exact-return_type-argument',
    'tool-state-dict', 'tool-state-key', 'tool-state-extra-key', 'tool-state-missing-field',
    'tool-state-fields-set', 'tool-state-fields-set-element', 'tool-state-extra', 'tool-state-private',
    'tool-state-missing-slot',
    'tool-exact-fn-module', 'tool-changed-by-a-resource-handler', 'tool-changed-by-a-later-capability',
)


def collected(node: str) -> set[str]:
    out = subprocess.run([sys.executable, '-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider', node],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f'rows: cannot collect {node}: {out.stdout[-400:]}{out.stderr[-400:]}')
    return {line.split('[', 1)[1].rstrip(']') for line in out.stdout.splitlines() if line.startswith(node + '[')}


def main() -> int:
    fields = list(FunctionTool.model_fields)
    rules = getattr(capabilities, 'TOOL_RULES', None)
    default_rule = getattr(capabilities, '_default_violation', None)
    bad: list[str] = []
    if not isinstance(rules, dict) or default_rule is None:
        return print('rows: the load has no TOOL_RULES table or no _default_violation', file=sys.stderr) or 1
    kinds = ([f'tool-subclass-reads-{f}' for f in fields] + ['tool-subclass-reads-nothing', 'tool-subclass-named-by-its-metaclass']
             + [f'tool-exact-{f}' for f in fields]
             + [f'tool-default-{f}' for f in F_FIELDS if f in fields]
             + list(DEPTH))
    for f in F_FIELDS:
        if f in fields and rules.get(f) is not default_rule:
            bad.append(f'TOOL_RULES[{f!r}] is not _default_violation')
    have = collected(REFUSED)
    for kind in kinds:
        for names in mutants.MEMBER_SETS:
            if f'{kind}-{names}' not in have:
                bad.append(f'{REFUSED}[{kind}-{names}]: no such row')
    drives = collected(STOPS)
    cli = {row[:-len(d) - 1] for row in drives for d in DRIVES if row.endswith(f'-{d}')}
    for family in ('tool-subclass-', 'tool-exact-'):
        hit = sorted(k for k in cli if k.startswith(family))
        if not hit:
            bad.append(f'{STOPS}: no {family}* kind is driven through the CLI')
        for k in hit:
            for d in DRIVES:
                if f'{k}-{d}' not in drives:
                    bad.append(f'{STOPS}[{k}-{d}]: no such row')
    print(*bad, sep='\n', file=sys.stderr)
    print(f'rows: {len(kinds)} kinds beside {len(mutants.MEMBER_SETS)} sets; {len(bad)} missing', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
