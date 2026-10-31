#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# bin/sandbox.sh still fails closed with either SSH-host variable exported in the calling shell.
#
#   sh spec/rename-to-cluster-mcp/verify/failclosed.sh        from the worktree root, outside the sandbox
#
# Rows: each of CLUSTER_MCP_SSH_HOST, RCAC_SSH_HOST, and both, exported here with an unresolvable host
# (`.invalid`, RFC 2606), times each of the cluster-mcp and rcac-mcp commands, each run two ways (this
# tree's venv binary, and `uv run --frozen` as the profile's verify and CI drive it), plus a uv env
# file named by UV_ENV_FILE that carries both host variables; every command bare (stdio, so the ssh
# rung) under the sandbox with stdin at EOF. Each must exit 2
# (exit_status.bad_argument), print nothing on stdout, and say "SSH host required" naming
# CLUSTER_MCP_SSH_HOST on stderr, with no "cannot connect" and no trace of the leaked host. Then the
# control rows, which show the assertions discriminate: the same host set *inside* the sandbox, by
# each name, for each command, must reach the connect step instead (nonzero, not 2, "cannot connect
# to leak-…invalid"), and the legacy name set inside must also draw the deprecation warning naming
# CLUSTER_MCP_SSH_HOST. Last, with all four host and user-map names and the env file exported, the
# sandboxed command's environment carries none of them and has UV_NO_ENV_FILE set. Footprint: one
# short process tree at a time; about 40 s.
set -eu
fail() { echo "failclosed: $*" >&2; exit 1; }
[ -z "${CLUSTER_MCP_SANDBOX:-}" ] || fail 'run it outside the sandbox: the variables must leak from the calling shell'
out=$(mktemp -d "${TMPDIR:-/tmp}/failclosed.XXXXXX")
trap 'rm -rf "$out"' EXIT HUP INT TERM
venv=${UV_PROJECT_ENVIRONMENT:-$PWD/.venv}
for cmd in cluster-mcp rcac-mcp; do
  [ -x "$venv/bin/$cmd" ] || fail "no $venv/bin/$cmd: run the profile's setup (uv sync --locked) first"
done

# A uv env file the calling shell points at, carrying the host: `uv run` would load it after the
# sandbox has unset the variables, unless the sandbox turns env files off.
printf 'CLUSTER_MCP_SSH_HOST=leak-ENVFILE.invalid\nRCAC_SSH_HOST=leak-ENVFILE.invalid\n' > "$out/leak.env"

row() { # row LABEL HOW CMD [VAR…]: export each VAR=leak-<var>.invalid here, run CMD bare in the sandbox
  label=$1; how=$2; cmd=$3; shift 3
  (
    for var in "$@"; do eval "$var=leak-$var.invalid; export $var"; done
    case $how in
      venv) bin/sandbox.sh "$venv/bin/$cmd" ;;
      uv) bin/sandbox.sh uv run --frozen "$cmd" ;;
      envfile) UV_ENV_FILE="$out/leak.env"; export UV_ENV_FILE; bin/sandbox.sh uv run --frozen "$cmd" ;;
    esac < /dev/null > "$out/stdout" 2> "$out/stderr"
  ) && rc=0 || rc=$?
  [ "$rc" -eq 2 ] || { cat "$out/stderr" >&2; fail "$label: exit $rc, expected 2"; }
  [ ! -s "$out/stdout" ] || fail "$label: wrote to stdout"
  grep -q 'SSH host required' "$out/stderr" || fail "$label: no 'SSH host required'"
  grep -q 'CLUSTER_MCP_SSH_HOST' "$out/stderr" || fail "$label: the message does not name CLUSTER_MCP_SSH_HOST"
  ! grep -q -e 'cannot connect' -e 'leak-' "$out/stderr" || fail "$label: the leaked host reached the server"
  echo "ok   $label" >&2
}

control() { # control LABEL CMD VAR: the host set inside the sandbox reaches the connect step
  label=$1; cmd=$2; var=$3
  bin/sandbox.sh env "$var=leak-$var.invalid" "$venv/bin/$cmd" < /dev/null > "$out/stdout" 2> "$out/stderr" && rc=0 || rc=$?
  [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ] || { cat "$out/stderr" >&2; fail "control $label: exit $rc, expected a failed connect"; }
  grep -q "cannot connect to leak-$var.invalid" "$out/stderr" || fail "control $label: no connect attempt to the inside host"
  if [ "$var" = RCAC_SSH_HOST ]; then
    grep -q 'CLUSTER_MCP_SSH_HOST' "$out/stderr" || fail "control $label: the legacy host drew no warning naming CLUSTER_MCP_SSH_HOST"
  fi
  echo "ok   control $label" >&2
}

for cmd in cluster-mcp rcac-mcp; do
  for how in venv uv; do
    row "$cmd ($how) with CLUSTER_MCP_SSH_HOST exported" $how "$cmd" CLUSTER_MCP_SSH_HOST
    row "$cmd ($how) with RCAC_SSH_HOST exported" $how "$cmd" RCAC_SSH_HOST
    row "$cmd ($how) with both exported" $how "$cmd" CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST
  done
  row "$cmd (uv) with UV_ENV_FILE carrying both" envfile "$cmd"
  control "$cmd CLUSTER_MCP_SSH_HOST inside" "$cmd" CLUSTER_MCP_SSH_HOST
  control "$cmd RCAC_SSH_HOST inside" "$cmd" RCAC_SSH_HOST
done
# Nothing of either name, nor the env file, reaches anything the sandbox runs.
(
  for var in CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST CLUSTER_MCP_USER_MAP RCAC_USER_MAP; do
    eval "$var=leak-$var.invalid; export $var"
  done
  UV_ENV_FILE="$out/leak.env"; export UV_ENV_FILE
  bin/sandbox.sh env > "$out/env"
)
! grep -E '^(CLUSTER_MCP_SSH_HOST|RCAC_SSH_HOST|CLUSTER_MCP_USER_MAP|RCAC_USER_MAP|UV_ENV_FILE)=' "$out/env" \
  || fail 'a host, user-map or env-file variable reached the sandboxed command'
grep -q '^UV_NO_ENV_FILE=' "$out/env" || fail 'the sandbox does not turn uv env files off'
echo 'ok   the sandboxed environment carries none of them' >&2
echo 'failclosed: ok' >&2
