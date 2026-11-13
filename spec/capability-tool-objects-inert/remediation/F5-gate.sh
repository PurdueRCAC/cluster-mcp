#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Review cycle 2, N1: every class a tool's return type holds, at any depth, carries its own
# `__module__`, exactly a `str`, in its own namespace (a class defined in C excepted: `type` reads its
# module from its C name); a class that does not is refused, naming the distribution and the field,
# with none of the capability's code run, and the registry cut back.
#
#   sh spec/capability-tool-objects-inert/remediation/F5-gate.sh [pins|cases|sweep-handshake|sweep-modern]
#
# `pins` (about 1 min): the refusal rows of each accepted metaclass beside each member set, the CLI
# drive of each (exit status, the distribution named, stdout empty), the accepted shapes and the served
# surface, by name, in both eras (verify/lib.sh's pytest_both: a missing id, an empty parameter set or a
# skip fails). `cases` (about 1 min): the two kept cases of tests/mutants.py for the decision, with the
# runner's controls, in both eras. `sweep-<era>` (about 2 min an era): F1-tool-rule-sweep.py's mutants
# of the decision (the class branch of `_return_type_violation`, as the generator numbers them; an id
# the generator no longer makes fails the run), one at a time, each killed. Footprint: one pytest or
# one mutant child at a time, under 1 GB; nothing in the background.
set -eu
. "$(dirname "$0")/../verify/lib.sh"
R=spec/capability-tool-objects-inert/remediation
REFUSED=tests/test_capabilities.py::test_a_capability_that_cannot_load_is_refused_naming_it
METAS='type abc model enum typed-dict'
SETS='core-only slurm rcac both'
SWEEP='_return_type_violation:If@9:always _return_type_violation:If@9:never _return_type_violation:If@9:negated
_return_type_violation:Compare@8:negated _return_type_violation:Continue@2:dropped
_return_type_violation:If@13:always _return_type_violation:If@13:never _return_type_violation:If@13:negated
_return_type_violation:Compare@17:negated _return_type_violation:Return@7:answers-none
_return_type_violation:If@14:always _return_type_violation:If@14:never _return_type_violation:If@14:negated
_return_type_violation:Return@8:answers-none'
MODE=${1:-}
case $MODE in
  pins)
    uv sync --locked -q
    ids=''
    for meta in $METAS; do
      for names in $SETS; do ids="$ids
$REFUSED[tool-exact-return_type-no-own-module-$meta-$names]"; done
      ids="$ids
tests/test_startup.py::test_a_return_type_with_no_module_of_its_own_stops_startup_running_none_of_its_code[$meta]"
    done
    pytest_both "$ids
tests/test_capabilities.py::test_an_inert_tool_of_every_accepted_shape_loads
tests/test_capabilities.py::test_a_served_capability_runs_none_of_its_code_but_its_handler
tests/test_surface.py::test_served_surface_matches_baseline
tests/test_startup.py::test_the_cli_drives_name_kinds_that_exist
tests/test_mutations.py::test_mutation_anchor_applies"
    echo 'F5-gate.sh: pins ok' >&2 ;;
  cases)
    for era in legacy modern; do
      env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=$era uv run python tests/mutants.py --self-check \
        capability-tool-return-type-own-module-unrequired capability-tool-return-type-c-class-refused
    done
    echo 'F5-gate.sh: cases ok' >&2 ;;
  sweep-handshake|sweep-modern)
    # shellcheck disable=SC2086
    $PY $R/F1-tool-rule-sweep.py ids "${MODE#sweep-}" $SWEEP
    echo "F5-gate.sh: $MODE ok" >&2 ;;
  *) echo "F5-gate.sh: unknown mode '$MODE' (pins|cases|sweep-handshake|sweep-modern)" >&2; exit 2 ;;
esac
