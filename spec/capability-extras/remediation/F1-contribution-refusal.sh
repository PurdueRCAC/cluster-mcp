#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Review cycle 1, F1's class checker: whatever a capability declares fails at the load or not at all.
#
#   sh spec/capability-extras/remediation/F1-contribution-refusal.sh        from the worktree root
#
# 1. F1-contribution-refusal.py: the property evaluated over a generated domain of contributions,
#    beside each member set (about 5 s).
# 2. The durable pins, by id, in the handshake era and then revision 2026-07-28's: each kind refused
#    at load beside every member set, each resource kind's control, a URI keyed as an earlier
#    capability's, a capability that loads served whole, and each kind driven through the CLI over
#    the raw wire, with stdin closed and over HTTP before binding (about 1 min per era).
# Footprint: one process tree at a time, under 1 GB; the drives run under bin/sandbox.sh.
set -eu
. spec/capability-extras/verify/lib.sh
uv sync --locked -q
uv run python -I spec/capability-extras/remediation/F1-contribution-refusal.py
pytest_both "tests/test_capabilities.py::test_what_a_server_would_refuse_is_refused_at_load
tests/test_capabilities.py::test_each_refused_resource_is_one_fastmcp_refuses
tests/test_capabilities.py::test_a_colliding_uri_would_be_replaced_silently
tests/test_capabilities.py::test_a_uri_colliding_with_an_earlier_capability_is_refused
tests/test_capabilities.py::test_what_loads_is_served_whole
tests/test_startup.py::test_a_contribution_the_server_would_refuse_stops_startup"
echo 'F1: ok' >&2
