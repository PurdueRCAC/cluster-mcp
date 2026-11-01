#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# P1's gate: the probe contract (a capability declares the commands it needs, as data, refused at load
# when malformed) and the runner (one lookup of every declared name, one bound, every ending decided).
#
#   sh spec/capability-probe/verify/p1.sh [phase|mutants-handshake-1|mutants-handshake-2|mutants-modern-1|mutants-modern-2|full-legacy|full-modern|all]
#
# `phase` (about 1 min warm): declared.py; lookups.py under bin/sandbox.sh; docs_gate.py p1;
# alternatives.py coverage p1; then P1's named tests in both eras. `mutants-<era>-<k>` (about 5 min
# each: 93 alternatives, at about 6 s a case measured on the plan's prototype, halved into shards 1
# and 2 per era): every P1 alternative's case killed in that era. `full-legacy`/`full-modern`: the profile's verify, in halves.
# `all` runs every mode. Footprint: one process tree at a time, nothing in the background, under 1 GB.
set -eu
. "$(dirname "$0")/lib.sh"
MODE=${1:-all}
need_mode "$MODE" phase mutants-handshake-1 mutants-handshake-2 mutants-modern-1 mutants-modern-2 full-legacy full-modern all

if [ "$MODE" = phase ] || [ "$MODE" = all ]; then
  uv sync --locked -q
  $PY $V/declared.py
  bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/lookups.py'
  $PY $V/docs_gate.py p1
  $PY $V/alternatives.py coverage p1
  pytest_both 'tests/test_probes.py::test_nothing_declared_runs_nothing
tests/test_probes.py::test_every_declared_command_is_looked_up_once
tests/test_probes.py::test_a_capability_is_withheld_when_one_of_its_commands_is_absent
tests/test_probes.py::test_every_ending_without_an_answer_serves_the_capability
tests/test_probes.py::test_a_hung_probe_is_abandoned_at_the_bound
tests/test_probes.py::test_the_verdicts_are_decided_once
tests/test_probes.py::test_the_lookup_finds_only_what_exec_runs
tests/test_probes.py::test_the_lookup_over_ssh
tests/test_capabilities.py::test_a_malformed_command_declaration_is_refused_at_load
tests/test_capabilities.py::test_a_planted_capability_declares_commands_with_no_core_edit
tests/test_capabilities.py::test_the_members_declare_their_commands'
  echo 'p1.sh: phase ok' >&2
fi
case $MODE in mutants-handshake-1|all) $PY $V/alternatives.py cases p1 handshake 1/2 ;; esac
case $MODE in mutants-handshake-2|all) $PY $V/alternatives.py cases p1 handshake 2/2 ;; esac
case $MODE in mutants-modern-1|all) $PY $V/alternatives.py cases p1 modern 1/2 ;; esac
case $MODE in mutants-modern-2|all) $PY $V/alternatives.py cases p1 modern 2/2 ;; esac
case $MODE in full-legacy|all) full_legacy ;; esac
case $MODE in full-modern|all) full_modern ;; esac
