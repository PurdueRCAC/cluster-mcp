#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# Real installs of the core alone, the core with one extra, and the core with both: each serves
# exactly its capabilities, and its instructions name exactly the tools it serves.
#
#   sh spec/capability-extras/verify/coreonly.sh        from the worktree root
#
# For each set (none; slurm; rcac; slurm and rcac), `uv sync --package cluster-mcp --no-dev --frozen
# --offline [--extra …]` builds a separate environment under the sandbox HOME
# (UV_PROJECT_ENVIRONMENT; the development .venv is never touched), editable, so it runs this tree's
# source and never a cached wheel. In it:
#   1. registry.py: only the distributions of the set are installed; no other member package can
#      be imported; the entry-point group lists exactly the set; after the startup load,
#      TOOL_REGISTRY holds exactly the core's seven tools and the set's own (for the core alone,
#      exactly the seven R4 names);
#   2. served.py: that environment's `cluster-mcp -e local`, driven over stdio, serves exactly the
#      core's tools and resources and the set's, with a base of the core text and each set text in
#      composition order (Slurm before RCAC) that lists exactly the tools served.
# PYTHONPATH is dropped, so each environment holds only what it installed. Offline from the uv
# cache the development sync filled. Runs inside bin/sandbox.sh. Footprint:
# one uv, python or server process at a time, under 500 MB; about 20 s warm.
set -eu
if [ -z "${CLUSTER_MCP_SANDBOX:-}" ]; then
  exec bin/sandbox.sh sh "$PWD/spec/capability-extras/verify/coreonly.sh" "$@"
fi
cd "$CLUSTER_MCP_REPO"
V=spec/capability-extras/verify
fail() { echo "coreonly: $*" >&2; exit 1; }
unset VIRTUAL_ENV PYTHONPATH
export FASTMCP_CHECK_FOR_UPDATES=off
uv sync --locked -q --offline || fail 'uv sync --locked failed'

one() { # one LABEL EXTRA… : build the environment for the set and check it
  label=$1; shift
  env_dir="$HOME/env-$label"
  extras=''
  for e in "$@"; do extras="$extras --extra $e"; done
  # shellcheck disable=SC2086
  UV_PROJECT_ENVIRONMENT="$env_dir" uv sync -q --package cluster-mcp --no-dev --frozen --offline $extras \
    || fail "$label: cannot build the environment"
  "$env_dir/bin/python" -I "$CLUSTER_MCP_REPO/$V/registry.py" "$@" || fail "$label: the installed set is wrong (above)"
  parts='core'
  for p in slurm rcac; do
    for e in "$@"; do [ "$e" = "$p" ] && parts="$parts $p"; done
  done
  # shellcheck disable=SC2086
  uv run --offline python $V/expect.py "$HOME/$label.json" $parts
  uv run --offline python $V/served.py "$HOME/$label.json" -- "$env_dir/bin/cluster-mcp" -e local \
    || fail "$label: the served surface is wrong (above)"
  echo "coreonly: $label ok" >&2
}

one core
one slurm slurm
one rcac rcac
one both slurm rcac
echo 'coreonly: ok' >&2
