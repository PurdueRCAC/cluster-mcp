# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Shared by this cycle's phase gates (p1.sh, p2.sh, p3.sh); sourced, never run. Run from the worktree
# root. Every helper runs one process tree at a time and starts nothing in the background, so an early
# exit leaves no worker behind (the drives that start a server reap their own process groups:
# drives.py). Scratch state lives under the sandbox HOME, which bin/sandbox.sh removes on every exit
# path: nothing here deletes a file itself.

V=spec/capability-probe/verify
# Today's served surface and suite: develop when the cycle opened (the shape commit's parent).
BASE_REF=c520432
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
# that was not written. The calling shell's probe override is dropped: the suite sets its own.
pytest_both() {
  set -f
  _ifs=$IFS
  IFS='
'
  # shellcheck disable=SC2086
  env -u CLUSTER_MCP_TEST_ERA -u CLUSTER_MCP_SKIP_PROBES uv run pytest -q -p no:cacheprovider $1
  # shellcheck disable=SC2086
  env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=modern uv run pytest -q -p no:cacheprovider $1
  IFS=$_ifs
  set +f
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

# The profile's full verify, in two halves so a caller with a 10 min command cap can split it.
full_legacy() { uv lock --check && env -u CLUSTER_MCP_TEST_ERA -u CLUSTER_MCP_SKIP_PROBES uv run pytest -q; }
full_modern() { env -u CLUSTER_MCP_SKIP_PROBES CLUSTER_MCP_TEST_ERA=modern uv run pytest -q && bin/sandbox.sh uv run cluster-mcp --help > /dev/null; }
