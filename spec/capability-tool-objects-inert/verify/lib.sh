# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Shared by this cycle's phase gates (p1.sh, p2.sh); sourced, never run. Run from the worktree
# root. Every helper runs one process tree at a time and starts nothing in the background, so an early
# exit leaves no worker behind; nothing here starts a server. Scratch state lives under pytest's or
# the mutation runner's own temporary directories: nothing here deletes a file itself.

V=spec/capability-tool-objects-inert/verify
# Develop when the cycle opened (the GOAL commit's parent): the served surface R5 holds unchanged.
BASE_REF=238f86b
# Gate Python runs isolated (-I): no script directory on sys.path, no PYTHONPATH, no user site. A gate
# that must see a planted distribution builds its own path from arguments instead.
PY='uv run python -I'

fail() { echo "gate: $*" >&2; exit 1; }

# Mode check: `need_mode MODE allowed…`.
need_mode() {
  m=$1; shift
  for a in "$@"; do [ "$m" = "$a" ] && return 0; done
  echo "gate: unknown mode $m (one of: $*)" >&2; exit 2
}

# Run the named pytest ids (one per line in $1) in the handshake era, then in the modern era. A
# named id that does not exist fails the run (pytest exits 4), so a gate never passes on a test
# that was not written; an empty parameter set fails at collection, and a run that skips anything
# fails here, so a gate never passes on a test that did not run. The calling shell's probe override
# is dropped: the suite sets its own.
pytest_both() {
  set -f
  for era in legacy modern; do
    # shellcheck disable=SC2086
    ran_pytest "$era" $1
  done
  set +f
}

# `ran_pytest ERA ARGS…`: one pytest run in ERA, refused when it skips or deselects nothing it was asked
# to run and still reports a skip. Output is kept in a file under $TMPDIR, read, then left for the OS.
ran_pytest() {
  era=$1; shift
  out=$(mktemp "${TMPDIR:-/tmp}/tool-objects-gate.XXXXXX")
  set +e
  env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA="$era" uv run pytest -q -p no:cacheprovider \
    -o empty_parameter_set_mark=fail_at_collect "$@" > "$out" 2>&1
  status=$?
  set -e
  tail -3 "$out" >&2
  [ "$status" -eq 0 ] || fail "pytest ($era era) exited $status: $(tail -1 "$out")"
  if grep -Eq '[0-9]+ skipped' "$out"; then fail "pytest ($era era) skipped a test it was asked to run"; fi
}

# Every mutation case whose file is one of the namespace-relative paths given, plus the named ids,
# deduped. A named id the runner does not know is passed through, and the runner fails on it.
cases_for() {
  files=$1; shift
  uv run python - "$files" "$@" <<'EOF'
import sys
sys.path.insert(0, 'tests')
import mutants
files = sys.argv[1].split()
ids = [c.id for c in mutants.CASES if '*' in files or c.file in files]
if not ids and sys.argv[2:] == []:
    sys.exit(f'gate: no mutation case plants into {files}')
print(*dict.fromkeys(ids + sys.argv[2:]))
EOF
}

# Run mutation cases (ids as arguments) and the runner's self-check controls; the runner exits
# nonzero when any case survives, dies for the wrong reason, or names an unknown id.
run_mutants() {
  # shellcheck disable=SC2068
  env -u CLUSTER_MCP_SKIP_PROBES uv run python tests/mutants.py --self-check $@
}

# The profile's full verify as its own commands: `uv lock --check`, then each era's four suite
# commands (AGENTS.md § Factory `verify`, § Conventions "CI mirrors the gate"), then the sandboxed
# --help. `full_part ERA K` runs command K (1-4) of era ERA (legacy|modern), each under the 10-minute
# command cap on its own (CI's slowest part is 7:34).
full_part() {
  case $1 in legacy) era=legacy ;; modern) era=modern ;; *) fail "full_part: era $1" ;; esac
  ign='--ignore=tests/test_ssh_exec.py --ignore=tests/test_timeout_stop.py --ignore=tests/test_startup.py --ignore=tests/test_launch.py'
  case $2 in
    1) env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=$era uv run pytest -q tests/test_ssh_exec.py -k silent ;;
    2) env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=$era uv run pytest -q tests/test_ssh_exec.py -k 'not silent' ;;
    3) env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=$era uv run pytest -q tests/test_timeout_stop.py tests/test_startup.py tests/test_launch.py ;;
    # shellcheck disable=SC2086
    4) env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=$era uv run pytest -q $ign ;;
    *) fail "full_part: part $2" ;;
  esac
}
full_ends() { uv lock --check && bin/sandbox.sh uv run cluster-mcp --help > /dev/null; }
