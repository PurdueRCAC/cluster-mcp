#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Review cycle 2, F1-F3's class checker (F4): every failure from discovering, ordering or loading a
# capability is refused naming its distribution, and a registration is checked whenever it happens.
#
#   sh spec/capability-extras/remediation/F4-load-refusal.sh        from the worktree root
#
# 1. F4-load-refusal.py: the property evaluated over a generated domain beside each member set
#    (about 10 s).
# 2. The durable pins, by id, in the handshake era and then revision 2026-07-28's: each kind refused
#    at load beside every member set, a keyboard interrupt raised as it is, a capability whose entry
#    point imports its tools loading, unreadable entry points refused while discovering, and each kind
#    driven through the CLI over the raw wire, with stdin closed and over HTTP before binding, an
#    interrupt through the CLI, and the load's place in run() beside every member set (about 3 min
#    per era).
# Footprint: one process tree at a time, under 1 GB; the drives run under bin/sandbox.sh, each in its
# own process group.
set -eu
. spec/capability-extras/verify/lib.sh
uv sync --locked -q
uv run python -I spec/capability-extras/remediation/F4-load-refusal.py

# The CLI drives below run over every kind (`UNLOADABLE`), not the suite's one kind per family: the suite
# never sets CLUSTER_MCP_TEST_EVERY_KIND. Collected with it set, they must number every kind's three.
export CLUSTER_MCP_TEST_EVERY_KIND=1
drives=$(uv run pytest -q -p no:cacheprovider --collect-only tests/test_startup.py::test_a_capability_that_cannot_load_stops_startup | grep -c '::' || true)
want=$(uv run python -c 'import sys; sys.path.insert(0, "tests"); from test_capabilities import UNLOADABLE; print(3 * len(UNLOADABLE))')
[ "$drives" = "$want" ] || { echo "F4: $drives CLI drives collected, not every kind's $want" >&2; exit 1; }
pytest_both "tests/test_capabilities.py::test_a_capability_that_cannot_load_is_refused_naming_it
tests/test_capabilities.py::test_a_keyboard_interrupt_while_loading_still_interrupts
tests/test_capabilities.py::test_a_capability_whose_entry_point_imports_its_tools_loads
tests/test_capabilities.py::test_entry_points_that_cannot_be_read_are_refused_naming_their_distribution
tests/test_capabilities.py::test_a_discovery_that_fails_with_every_distribution_readable_is_refused_naming_the_group
tests/test_capabilities.py::test_a_tool_outside_the_tools_module_is_refused
tests/test_capabilities.py::test_what_a_server_would_refuse_is_refused_at_load
tests/test_startup.py::test_a_capability_that_cannot_load_stops_startup
tests/test_startup.py::test_a_keyboard_interrupt_while_loading_still_interrupts_the_start
tests/test_startup.py::test_a_keyboard_interrupt_while_loading_interrupts_the_start_beside_every_set
tests/test_startup.py::test_a_token_is_generated_before_any_capability_loads
tests/test_startup.py::test_capabilities_load_before_the_mode_ladder_beside_every_set"
echo 'F4: ok' >&2
