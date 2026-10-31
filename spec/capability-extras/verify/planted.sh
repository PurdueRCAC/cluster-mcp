#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# A distribution the core has never heard of plugs in through the entry-point group, and one that
# fails to load stops the server at startup, naming itself.
#
#   sh spec/capability-extras/verify/planted.sh extra|broken        from the worktree root
#
# Each case plants a distribution (a `*.dist-info` with METADATA and entry_points.txt, beside its
# module) in its own directory under the sandbox HOME and puts that directory FIRST on PYTHONPATH,
# keeping whatever PYTHONPATH already held (the mutation runner's copy). Nothing in the tree is
# edited: that is the point of `extra`.
#
# extra: `planted-capability` declares `planted = planted_capability.capability:CAPABILITY`, a
#   Capability(name='planted', order=500, ...) whose tools module defines one @mcp_tool,
#   `planted_echo`, and which carries one resource, `cluster://planted` (executor True).
#   `cluster-mcp -e local` must serve the 24 tools and `planted_echo`, the four resources and
#   `cluster://planted`, and a base of the core, Slurm, planted and RCAC texts in that order (500
#   sorts between Slurm and RCAC whatever the discovery order) listing exactly the tools served
#   (served.py).
# broken: one distribution per failure, each `planted-<case>` but the last:
#   missing-module (the entry point names a module that does not exist), raising (the capability
#   module raises on import), wrong-type (the entry point names `os:sep`, a str), tools-missing (a
#   Capability whose `tools` module does not exist), tools-raising (its tools module registers a
#   tool, then raises), instructions-mismatch (its text lists `ghost`, its module defines
#   `planted_echo`), duplicate-tool (its tools module defines `sinfo`, which the Slurm member
#   serves, and its text lists `sinfo`), open-resource (a resource with `executor: False`),
#   duplicate-uri (a resource at `cluster://storage`), bad-resource (a resource whose handler is not
#   callable), and shadow (a `cluster_mcp_rcac-0.1.5.dist-info` ahead of the installed one, whose
#   `rcac` entry point names a missing module: the message must name `cluster-mcp-rcac`). For each:
#   `cluster-mcp` (stdio, no SSH host) with stdin closed exits 5 and its stderr carries
#   `cannot load capability <dist>: ` and neither `SSH host required` nor `Execution mode` (the
#   load precedes the mode ladder); fed an `initialize` request, it answers a JSON-RPC error
#   carrying that message on stdout and exits 5; `rcac-mcp` (the deprecated command) exits 5 with
#   the same message; and `cluster-mcp --help` still exits 0. The missing-module case is also
#   driven as `cluster-mcp -e local -t http -p 0`, which must exit 5 with the message within 60 s,
#   never binding.
# Runs inside bin/sandbox.sh. Footprint: one python or server process at a time, under 400 MB;
# about 45 s.
set -eu
mode=${1:?usage: planted.sh extra|broken}
case $mode in extra|broken) ;; *) echo "planted: unknown mode $mode" >&2; exit 2 ;; esac
if [ -z "${CLUSTER_MCP_SANDBOX:-}" ]; then
  exec bin/sandbox.sh sh "$PWD/spec/capability-extras/verify/planted.sh" "$@"
fi
cd "$CLUSTER_MCP_REPO"
V=spec/capability-extras/verify
fail() { echo "planted: $*" >&2; exit 1; }
unset VIRTUAL_ENV
uv sync --locked -q --offline || fail 'uv sync --locked failed'
CLI="$CLUSTER_MCP_REPO/.venv/bin/cluster-mcp"
LEGACY="$CLUSTER_MCP_REPO/.venv/bin/rcac-mcp"
PY="$CLUSTER_MCP_REPO/.venv/bin/python"
[ -x "$CLI" ] && [ -x "$LEGACY" ] || fail 'the development environment has no cluster-mcp or rcac-mcp command'
export FASTMCP_CHECK_FOR_UPDATES=off

# dist DIR NAME ENTRYPOINT: a distribution NAME (version 0.0.1) declaring one entry point in the group.
dist() {
  info="$1/$(printf '%s' "$2" | tr '-' '_')-0.0.1.dist-info"
  mkdir -p "$info"
  printf 'Metadata-Version: 2.1\nName: %s\nVersion: 0.0.1\n' "$2" > "$info/METADATA"
  printf '[cluster_mcp.capabilities]\n%s\n' "$3" > "$info/entry_points.txt"
}

# capability DIR MODULE TOOLS_PY RESOURCES_EXPR [TEXT [TOOLS_MODULE]]: a package MODULE with
# tools.py and capability.py; TEXT defaults to the planted_echo listing, TOOLS_MODULE to MODULE.tools.
capability() {
  mkdir -p "$1/$2"
  : > "$1/$2/__init__.py"
  printf '%s\n' "$3" > "$1/$2/tools.py"
  cat > "$1/$2/capability.py" <<EOF
from cluster_mcp.core.capabilities import Capability


def _read() -> str:
    """The text a planted resource serves."""
    return 'planted'


CAPABILITY = Capability(name='$2', order=500, tools='${6:-$2.tools}',
                        instructions='${5:-Planted tools:\n- planted_echo: Echo a text back}',
                        resources=$4)
EOF
}

ECHO_TOOL='from cluster_mcp.core.tools import mcp_tool


@mcp_tool
def planted_echo(text: str) -> str:
    """Echo a text back.

    Args:
        text: The text.

    Returns:
        The same text.
    """
    return text'

with_path() { # with_path DIR CMD…: run CMD with DIR first on PYTHONPATH, the old value kept after it
  d=$1; shift
  PYTHONPATH="$d${PYTHONPATH:+:$PYTHONPATH}" "$@"
}

if [ "$mode" = extra ]; then
  d="$HOME/planted/extra"
  capability "$d" planted_capability "$ECHO_TOOL" \
    "({'uri': 'cluster://planted', 'name': 'planted', 'description': 'Planted', 'handler': _read, 'executor': True},)"
  dist "$d" planted-capability 'planted = planted_capability.capability:CAPABILITY'
  uv run --offline python $V/expect.py "$HOME/extra.json" core slurm planted rcac
  with_path "$d" "$PY" $V/served.py "$HOME/extra.json" -- "$CLI" -e local \
    || fail 'a planted capability is not served as a capability like the members'
  echo 'planted: extra ok' >&2
  exit 0
fi

INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"gate","version":"0"}}}'

check() { # check CASE DIR DIST: the four drives above, with DIR first on PYTHONPATH
  c=$1; d=$2; want="cannot load capability $3: "
  with_path "$d" "$CLI" < /dev/null > "$HOME/$c.out" 2> "$HOME/$c.err" && rc=0 || rc=$?
  [ "$rc" = 5 ] || { cat "$HOME/$c.err" >&2; fail "$c: cluster-mcp exited $rc, expected 5"; }
  grep -q -F -- "$want" "$HOME/$c.err" || { cat "$HOME/$c.err" >&2; fail "$c: stderr does not carry '$want'"; }
  ! grep -q -e 'SSH host required' -e 'Execution mode' "$HOME/$c.err" || fail "$c: the mode ladder ran before the load"
  printf '%s\n' "$INIT" | with_path "$d" "$CLI" > "$HOME/$c.wire" 2> "$HOME/$c.wire.err" && rc=0 || rc=$?
  [ "$rc" = 5 ] || fail "$c: cluster-mcp fed a request exited $rc, expected 5"
  grep -q '"error"' "$HOME/$c.wire" && grep -q -F -- "$want" "$HOME/$c.wire" \
    || { cat "$HOME/$c.wire" >&2; fail "$c: the stdio answer is not an error carrying '$want'"; }
  with_path "$d" "$LEGACY" < /dev/null > /dev/null 2> "$HOME/$c.legacy" && rc=0 || rc=$?
  [ "$rc" = 5 ] && grep -q -F -- "$want" "$HOME/$c.legacy" || fail "$c: rcac-mcp exited $rc or did not name the distribution"
  with_path "$d" "$CLI" --help > /dev/null 2>&1 || fail "$c: cluster-mcp --help failed with a broken capability installed"
  echo "planted: $c ok" >&2
}

d="$HOME/planted/missing-module"; dist "$d" planted-missing-module 'gone = planted_nowhere_at_all.capability:CAPABILITY'
check missing-module "$d" planted-missing-module
# Over HTTP the failure must come before the bind; a server that binds is killed at the timeout.
with_path "$d" "$PY" - "$CLI" "cannot load capability planted-missing-module: " <<'EOF' || fail 'missing-module over http (above)'
import subprocess, sys
try:
    r = subprocess.run([sys.argv[1], '-e', 'local', '-t', 'http', '-H', '127.0.0.1', '-p', '0'],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
except subprocess.TimeoutExpired:
    sys.exit('planted: over http the server was still running after 60 s')
if r.returncode != 5 or sys.argv[2] not in r.stderr:
    sys.exit(f'planted: over http exited {r.returncode}; stderr: {r.stderr[-400:]}')
EOF

d="$HOME/planted/raising"; mkdir -p "$d/planted_raising"; : > "$d/planted_raising/__init__.py"
printf 'raise RuntimeError("planted failure at import")\n' > "$d/planted_raising/capability.py"
dist "$d" planted-raising 'raising = planted_raising.capability:CAPABILITY'
check raising "$d" planted-raising

d="$HOME/planted/wrong-type"; dist "$d" planted-wrong-type 'wrong = os:sep'
check wrong-type "$d" planted-wrong-type

d="$HOME/planted/tools-missing"
capability "$d" planted_tools_missing "$ECHO_TOOL" '()' '' 'planted_tools_missing.nowhere'
dist "$d" planted-tools-missing 'tm = planted_tools_missing.capability:CAPABILITY'
check tools-missing "$d" planted-tools-missing

d="$HOME/planted/tools-raising"
capability "$d" planted_tools_raising "$ECHO_TOOL
raise RuntimeError('planted failure after registering a tool')" '()'
dist "$d" planted-tools-raising 'tr = planted_tools_raising.capability:CAPABILITY'
check tools-raising "$d" planted-tools-raising

d="$HOME/planted/instructions-mismatch"
capability "$d" planted_mismatch "$ECHO_TOOL" '()' 'Planted tools:\n- ghost: A tool nobody defines'
dist "$d" planted-instructions-mismatch 'mm = planted_mismatch.capability:CAPABILITY'
check instructions-mismatch "$d" planted-instructions-mismatch

d="$HOME/planted/duplicate-tool"
capability "$d" planted_duplicate "$(printf '%s' "$ECHO_TOOL" | sed 's/planted_echo/sinfo/')" '()' \
  'Planted tools:\n- sinfo: Echo a text back'
dist "$d" planted-duplicate-tool 'dup = planted_duplicate.capability:CAPABILITY'
check duplicate-tool "$d" planted-duplicate-tool

d="$HOME/planted/open-resource"
capability "$d" planted_open "$ECHO_TOOL" "({'uri': 'cluster://planted', 'name': 'planted', 'description': 'Planted', 'handler': _read, 'executor': False},)"
dist "$d" planted-open-resource 'open = planted_open.capability:CAPABILITY'
check open-resource "$d" planted-open-resource

d="$HOME/planted/duplicate-uri"
capability "$d" planted_uri "$ECHO_TOOL" "({'uri': 'cluster://storage', 'name': 'planted', 'description': 'Planted', 'handler': _read, 'executor': True},)"
dist "$d" planted-duplicate-uri 'uri = planted_uri.capability:CAPABILITY'
check duplicate-uri "$d" planted-duplicate-uri

d="$HOME/planted/bad-resource"
capability "$d" planted_bad "$ECHO_TOOL" "({'uri': 'cluster://planted', 'name': 'planted', 'description': 'Planted', 'handler': 'not callable', 'executor': True},)"
dist "$d" planted-bad-resource 'bad = planted_bad.capability:CAPABILITY'
check bad-resource "$d" planted-bad-resource

d="$HOME/planted/shadow"; info="$d/cluster_mcp_rcac-0.1.5.dist-info"; mkdir -p "$info"
printf 'Metadata-Version: 2.1\nName: cluster-mcp-rcac\nVersion: 0.1.5\n' > "$info/METADATA"
printf '[cluster_mcp.capabilities]\nrcac = cluster_mcp.rcac.planted_nowhere:CAPABILITY\n' > "$info/entry_points.txt"
check shadow "$d" cluster-mcp-rcac

echo 'planted: broken ok (11 cases, and one over http)' >&2
