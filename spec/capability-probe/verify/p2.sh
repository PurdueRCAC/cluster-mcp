#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P2's gate: startup withholds what the cluster lacks and fails open within the bound in `ssh` and
# `local` modes, skips the probe in `delegate` mode and under the override, probes after every refusal
# would have stopped it, and the documents say so.
#
#   sh spec/capability-probe/verify/p2.sh [phase|pre-push|mutants-handshake-1|mutants-handshake-2|mutants-modern-1|mutants-modern-2|full-legacy|full-modern|all]
#
# `pre-push` (about 7 s): docs_gate.py p2 and drives.py quick, the checks a reader of the branch
# would see first. `phase` (about 4 min warm): startup_order.py; drives.py all under bin/sandbox.sh
# (two real 10 s hangs); docs_gate.py p2; alternatives.py coverage p2; then P2's named tests in both
# eras, with every test file whose starts the suite's default override keeps green (about 80 s an
# era on the prototype). `mutants-<era>-<k>` (about 4 min each: 79 alternatives, at about 6 s a case
# measured on the plan's prototype, halved into shards 1 and 2 per era): every P2 alternative's case
# killed in that era. `full-legacy`/`full-modern`: the
# profile's verify, in halves. `all` runs every mode but pre-push. Footprint: one process tree at a
# time (a drive's server is reaped by process group), nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase pre-push mutants-handshake-1 mutants-handshake-2 mutants-modern-1 mutants-modern-2 full-legacy full-modern all

if [ "$MODE" = pre-push ]; then
  $PY $V/docs_gate.py p2
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/drives.py quick'
fi
if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  $PY $V/startup_order.py
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/drives.py all'
  $PY $V/docs_gate.py p2
  $PY $V/alternatives.py coverage p2
  pytest_both 'tests/test_probe_startup.py::test_local_and_ssh_probe_once_after_the_executor
tests/test_probe_startup.py::test_the_server_is_built_from_what_the_probe_keeps
tests/test_probe_startup.py::test_the_served_instructions_name_exactly_the_served_tools
tests/test_probe_startup.py::test_the_probe_follows_the_site_read_and_is_bounded
tests/test_probe_startup.py::test_delegate_runs_no_probe_and_says_so
tests/test_probe_startup.py::test_the_override_skips_every_probe
tests/test_probe_startup.py::test_any_non_empty_override_value_skips
tests/test_probe_startup.py::test_no_probe_runs_before_a_refusal
tests/test_probe_startup.py::test_the_budget_never_depends_on_the_answer
tests/test_probe_startup.py::test_a_withheld_capability_is_not_served_over_stdio
tests/test_probe_startup.py::test_a_probe_without_an_answer_serves_every_capability_over_stdio
tests/test_probe_startup.py::test_withheld_with_stdin_closed_and_over_http
tests/test_env.py::test_a_variable_without_a_legacy_name
tests/test_hygiene.py::test_the_suite_skips_probes_by_default
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_exec_mode.py
tests/test_site_startup.py
tests/test_transports.py
tests/test_cli.py
tests/test_env.py
tests/test_hygiene.py
tests/test_startup.py
tests/test_tokens.py'
  echo 'p2.sh: phase ok' >&2
fi
case $MODE in mutants-handshake-1|all) $PY $V/alternatives.py cases p2 handshake 1/2 ;; esac
case $MODE in mutants-handshake-2|all) $PY $V/alternatives.py cases p2 handshake 2/2 ;; esac
case $MODE in mutants-modern-1|all) $PY $V/alternatives.py cases p2 modern 1/2 ;; esac
case $MODE in mutants-modern-2|all) $PY $V/alternatives.py cases p2 modern 2/2 ;; esac
case $MODE in full-legacy|all) full_legacy ;; esac
case $MODE in full-modern|all) full_modern ;; esac
