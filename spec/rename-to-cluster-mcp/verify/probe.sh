#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# The install probe: the git `#subdirectory=` install of packages/cluster-mcp from one commit builds
# the Slurm and RCAC members from that same commit, and the installed commands run.
#
#   sh spec/rename-to-cluster-mcp/verify/probe.sh        from the worktree root
#
# The tree as it stands (tracked and untracked, ignored files left out) is committed into a
# throwaway repository under the sandbox HOME, since the phase's own commit does not exist yet when
# its gate runs. Then, all under bin/sandbox.sh:
#   1. `uvx --from 'git+file://<snapshot>@<sha>#subdirectory=packages/cluster-mcp' cluster-mcp --help`
#      exits 0 and prints the cluster-mcp usage (the post_verify shape, against a local clone);
#   2. the same spec installed into a throwaway venv: each of cluster-mcp, cluster-mcp-slurm and
#      cluster-mcp-rcac records a VCS install of commit <sha> from its own packages/ subdirectory, the
#      venv imports cluster_mcp.slurm and cluster_mcp.rcac from site-packages, and
#      `python -m cluster_mcp.core` with --help, --version and --bogus matches the installed
#      cluster-mcp command in exit status, stdout and stderr;
#   3. the old install line, `uvx --from 'git+file://<snapshot>@<sha>' rcac-mcp --help`, exits 0,
#      prints the same usage on stdout, and warns on stderr naming cluster-mcp, 0.2.0 and 0.4.0.
# A second commit in the snapshot, made after <sha>, carries a different marker in the Slurm member,
# so a sibling built from any other commit, or from the working tree, is caught by its commit id.
# Needs the network on a cold uv cache (PyPI for hatchling and the dependency tree). Footprint: one
# uv process tree at a time, under 1 GB; about 1 min warm.
set -eu
if [ -z "${CLUSTER_MCP_SANDBOX:-}" ]; then
  exec bin/sandbox.sh sh "$PWD/spec/rename-to-cluster-mcp/verify/probe.sh" "$@"
fi
fail() { echo "probe: $*" >&2; exit 1; }
cd "$CLUSTER_MCP_REPO"
snap="$HOME/snapshot"
mkdir -p "$snap"
git ls-files -z --cached --others --exclude-standard \
  | xargs -0 sh -c 'for f; do if [ -e "$f" ] || [ -L "$f" ]; then printf "%s\0" "$f"; fi; done' sh \
  | tar --null -T - -cf - | tar -xf - -C "$snap"
G() { git -C "$snap" -c user.name=probe -c user.email=probe@invalid -c commit.gpgsign=false "$@"; }
G init -q
G add -A
G commit -q -m snapshot
sha=$(G rev-parse HEAD)
# A later commit the install must not see.
printf '\nLATER_COMMIT_MARKER = True\n' >> "$snap/packages/cluster-mcp-slurm/src/cluster_mcp/slurm/__init__.py"
G commit -q -am later
later=$(G rev-parse HEAD)
[ "$sha" != "$later" ] || fail 'the marker commit did not move HEAD'
unset UV_PROJECT VIRTUAL_ENV
cd "$HOME"

spec="git+file://$snap@$sha#subdirectory=packages/cluster-mcp"
uvx -q --from "$spec" cluster-mcp --help > "$HOME/help.out" 2> "$HOME/help.err" || { cat "$HOME/help.err" >&2; fail 'uvx cluster-mcp --help failed'; }
grep -q 'cluster-mcp' "$HOME/help.out" || fail 'cluster-mcp --help does not name cluster-mcp'

uv venv -q "$HOME/venv"
uv pip install -q --python "$HOME/venv/bin/python" "cluster-mcp @ $spec" || fail 'uv pip install of the subdirectory spec failed'
"$HOME/venv/bin/python" -I - "$sha" "$snap" <<'EOF' || fail 'the installed members fail the origin and namespace checks (above)'
import importlib, importlib.metadata as md, json, sys
sha, snap = sys.argv[1], sys.argv[2]
bad = []
for dist, sub in (('cluster-mcp', 'cluster-mcp'), ('cluster-mcp-slurm', 'cluster-mcp-slurm'), ('cluster-mcp-rcac', 'cluster-mcp-rcac')):
    raw = md.distribution(dist).read_text('direct_url.json')
    info = json.loads(raw or '{}')
    vcs = info.get('vcs_info', {})
    if vcs.get('commit_id') != sha or info.get('subdirectory') != f'packages/{sub}' or not info.get('url', '').startswith('file://'):
        bad.append(f'{dist}: {raw}')
for mod in ('cluster_mcp.core', 'cluster_mcp.slurm', 'cluster_mcp.rcac'):
    m = importlib.import_module(mod)
    if 'site-packages' not in (m.__file__ or '') or snap in (m.__file__ or ''):
        bad.append(f'{mod} imported from {m.__file__}')
import cluster_mcp
if getattr(cluster_mcp, '__file__', None) is not None:
    bad.append(f'cluster_mcp is a regular package: {cluster_mcp.__file__}')
import cluster_mcp.slurm as s
if hasattr(s, 'LATER_COMMIT_MARKER'):
    bad.append('cluster_mcp.slurm carries the later commit')
print(*bad, sep='\n', file=sys.stderr)
sys.exit(1 if bad else 0)
EOF
for arg in --help --version --bogus; do
  "$HOME/venv/bin/cluster-mcp" "$arg" < /dev/null > "$HOME/c.out" 2> "$HOME/c.err" && crc=0 || crc=$?
  "$HOME/venv/bin/python" -m cluster_mcp.core "$arg" < /dev/null > "$HOME/m.out" 2> "$HOME/m.err" && mrc=0 || mrc=$?
  [ "$crc" = "$mrc" ] || fail "python -m cluster_mcp.core $arg exits $mrc, cluster-mcp $crc"
  cmp -s "$HOME/c.out" "$HOME/m.out" || fail "python -m cluster_mcp.core $arg: stdout differs from cluster-mcp's"
  cmp -s "$HOME/c.err" "$HOME/m.err" || fail "python -m cluster_mcp.core $arg: stderr differs from cluster-mcp's"
done
[ "$crc" -ne 0 ] || fail 'cluster-mcp --bogus exited 0'
"$HOME/venv/bin/cluster-mcp" --help > "$HOME/venv-help.out"
cmp -s "$HOME/help.out" "$HOME/venv-help.out" || fail 'the venv install and the uvx install print different usage'

uvx -q --from "git+file://$snap@$sha" rcac-mcp --help > "$HOME/legacy.out" 2> "$HOME/legacy.err" || { cat "$HOME/legacy.err" >&2; fail 'the old install line (rcac-mcp from the root) failed'; }
cmp -s "$HOME/help.out" "$HOME/legacy.out" || fail 'rcac-mcp --help stdout differs from cluster-mcp --help'
grep -q -- 'cluster-mcp' "$HOME/legacy.err" || fail 'the rcac-mcp warning does not name cluster-mcp'
grep -q -F -- 'deprecated in 0.2.0, removed no earlier than 0.4.0' "$HOME/legacy.err" || fail 'the rcac-mcp warning does not state the window'
echo "probe: ok (commit $sha; members from the same commit; old install line runs rcac-mcp)" >&2
