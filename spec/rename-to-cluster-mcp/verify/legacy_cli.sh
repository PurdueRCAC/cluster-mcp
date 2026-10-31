#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# The rcac-mcp command behaves exactly as cluster-mcp, plus one warning on stderr; both identify as
# cluster-mcp.
#
#   sh spec/rename-to-cluster-mcp/verify/legacy_cli.sh p1|p2     from the worktree root
#
# For each argv in (none), --help, --version, --bogus, both commands of this tree's venv run under
# bin/sandbox.sh with stdin at EOF and no SSH host. They must exit alike and print byte-identical
# stdout; rcac-mcp's stderr must be exactly one line naming cluster-mcp, 0.2.0 and 0.4.0 followed by
# cluster-mcp's stderr, byte for byte, the window stated exactly as WINDOW below. `--version` must
# start with "cluster-mcp", and neither --help
# nor --version may say "RCAC MCP Server" or "Purdue"; in p2 (the variables renamed) neither may say
# RCAC or Purdue in any case. Then a stdio session: `rcac-mcp -e local` fed one initialize request
# then EOF writes only JSON-RPC lines on stdout (the warning never reaches the transport); in p2
# RCAC_INSTRUCTIONS_BUDGET=8192 is set inside, and its warning (one line naming both variables and
# the same window) joins stderr, still never stdout. Footprint: one short process tree at a time; about 15 s.
set -eu
mode=${1:?usage: legacy_cli.sh p1|p2}
case $mode in p1|p2) ;; *) echo "legacy_cli: unknown mode $mode" >&2; exit 2 ;; esac
fail() { echo "legacy_cli: $*" >&2; exit 1; }
out=$(mktemp -d "${TMPDIR:-/tmp}/legacy-cli.XXXXXX")
trap 'rm -rf "$out"' EXIT HUP INT TERM
venv=${UV_PROJECT_ENVIRONMENT:-$PWD/.venv}
WINDOW='deprecated in 0.2.0, removed no earlier than 0.4.0'

drive() { # drive NAME CMD ARGS…: stdout, stderr and exit status into $out/NAME.*
  name=$1; cmd=$2; shift 2
  bin/sandbox.sh "$venv/bin/$cmd" "$@" < /dev/null > "$out/$name.out" 2> "$out/$name.err" && rc=0 || rc=$?
  echo "$rc" > "$out/$name.rc"
}

for args in '' '--help' '--version' '--bogus'; do
  label=${args:-'(no arguments)'}
  # shellcheck disable=SC2086
  drive new cluster-mcp $args
  # shellcheck disable=SC2086
  drive old rcac-mcp $args
  cmp -s "$out/new.rc" "$out/old.rc" || fail "$label: exit $(cat "$out/old.rc") under rcac-mcp, $(cat "$out/new.rc") under cluster-mcp"
  cmp -s "$out/new.out" "$out/old.out" || fail "$label: stdout differs"
  head -n 1 "$out/old.err" > "$out/warning"
  tail -n +2 "$out/old.err" > "$out/old.rest"
  cmp -s "$out/new.err" "$out/old.rest" || { diff "$out/new.err" "$out/old.rest" >&2 || true; fail "$label: rcac-mcp stderr is not one warning line plus cluster-mcp's"; }
  grep -q -- 'cluster-mcp' "$out/warning" || fail "$label: the warning line does not name cluster-mcp: $(cat "$out/warning")"
  grep -q -F -- "$WINDOW" "$out/warning" || fail "$label: the warning line does not state the window: $(cat "$out/warning")"
  if [ "$args" = --help ] || [ "$args" = --version ]; then
    ! grep -q -e 'RCAC MCP Server' -e 'Purdue' "$out/new.out" || fail "$label: still identifies as RCAC or Purdue"
    if [ "$mode" = p2 ]; then
      ! grep -q -i -e 'rcac' -e 'purdue' "$out/new.out" || fail "$label: names RCAC or Purdue: $(grep -i -e rcac -e purdue "$out/new.out" | head -n 2)"
    fi
  fi
  if [ "$args" = --version ]; then
    case $(head -n 1 "$out/new.out") in cluster-mcp*) ;; *) fail "--version starts $(head -n 1 "$out/new.out")" ;; esac
  fi
  echo "ok   $label" >&2
done

init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"gate","version":"0"}}}'
if [ "$mode" = p2 ]; then set -- env RCAC_INSTRUCTIONS_BUDGET=8192; else set --; fi
printf '%s\n' "$init" | bin/sandbox.sh "$@" "$venv/bin/rcac-mcp" -e local > "$out/stdio.out" 2> "$out/stdio.err" || true
[ -s "$out/stdio.out" ] || { cat "$out/stdio.err" >&2; fail 'stdio: no answer on stdout'; }
uv run --no-project python - "$out/stdio.out" <<'EOF' || fail 'stdio: stdout carries a line that is not JSON-RPC'
import json, sys
for line in open(sys.argv[1]):
    msg = json.loads(line)
    assert msg.get('jsonrpc') == '2.0', line
EOF
grep -q 'cluster-mcp' "$out/stdio.err" || fail 'stdio: no command warning on stderr'
if [ "$mode" = p2 ]; then
  grep 'RCAC_INSTRUCTIONS_BUDGET' "$out/stdio.err" | grep 'CLUSTER_MCP_INSTRUCTIONS_BUDGET' | grep -q -F -- "$WINDOW" \
    || fail 'stdio: no warning naming RCAC_INSTRUCTIONS_BUDGET, CLUSTER_MCP_INSTRUCTIONS_BUDGET and the window on one line'
fi
echo "ok   stdio session" >&2
echo 'legacy_cli: ok' >&2
