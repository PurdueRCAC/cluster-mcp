#!/bin/sh
# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT
#
# The install probe: every install line, from one commit, installs exactly its capabilities, and
# the old install line serves exactly what it served before the cycle.
#
#   sh spec/capability-extras/verify/probe.sh        from the worktree root
#
# The tree as it stands (tracked and untracked, ignored files left out) is committed into a
# throwaway repository under the sandbox HOME, since the phase's own commit does not exist when its
# gate runs; a second commit after it carries a marker in the Slurm member, so a member built from
# any other commit is caught. Then, all under bin/sandbox.sh and offline from the warm uv cache:
#   1. `uv build --all-packages --no-sources` of the snapshot: the core wheel provides the extras
#      `rcac` and `slurm` and requires each member exactly under its own extra (markers evaluated,
#      names canonicalised); the root wheel requires exactly `cluster-mcp` with the extras
#      {slurm, rcac} and no marker; each member wheel declares its entry point in the group;
#   2. each install line into a fresh venv — `cluster-mcp @ <spec>`, `cluster-mcp[slurm] @ <spec>`,
#      `cluster-mcp[rcac] @ <spec>`, `cluster-mcp[slurm,rcac] @ <spec>` (`<spec>` the
#      `git+file://…@<sha>#subdirectory=packages/cluster-mcp` form) and `rcac-mcp @ git+file://…@<sha>`
#      (the repository root, the old line) — installs every cluster-mcp distribution it has from
#      commit <sha>, without the marker, and registry.py holds for its set;
#   3. the root install serves what the old install line served before the cycle, whole, compared
#      within one resolution mode (amended at the foreman's ruling, 2026-10-31: the first compare
#      set a lock-free install against the locked base.json, so a newer cached dependency turned
#      it red with no product change):
#      a. lock-free, as a user's install line resolves: BASE_REF's tree, committed into a second
#         throwaway repository and installed the same way from the same offline cache in this
#         run, serves exactly what this snapshot's root install serves;
#      b. lock-pinned: the snapshot's root installed with its uv.lock exported as constraints
#         (`uv export --frozen --no-hashes --no-emit-workspace --no-dev`) serves exactly base.json
#         (baseline.sh writes it from BASE_REF's locked sync);
#      and the root install's `rcac-mcp -e local` command, driven over stdio, serves the core,
#      Slurm and RCAC tools and resources with the base in that order (served.py);
#   4. `uvx --from 'cluster-mcp[slurm,rcac] @ <spec>' cluster-mcp --help` (the README line) and
#      `uvx --from 'git+file://…@<sha>' rcac-mcp --help` (the old line) exit 0.
# Footprint: one uv or python process tree at a time, under 1 GB; about 2 min warm.
set -eu
if [ -z "${CLUSTER_MCP_SANDBOX:-}" ]; then
  exec bin/sandbox.sh sh "$PWD/spec/capability-extras/verify/probe.sh" "$@"
fi
cd "$CLUSTER_MCP_REPO"
R=$CLUSTER_MCP_REPO
V=spec/capability-extras/verify
fail() { echo "probe: $*" >&2; exit 1; }
# The base commit, from its one definition in lib.sh.
BASE_REF=$(sed -n 's/^BASE_REF=//p' "$V/lib.sh")
[ -n "$BASE_REF" ] || fail 'lib.sh defines no BASE_REF'
sh $V/baseline.sh > /dev/null 2>&1 || fail 'baseline.sh failed: run it alone for the reason'
[ -s "$HOME/base.json" ] || fail 'baseline.sh wrote no base.json'
export FASTMCP_CHECK_FOR_UPDATES=off

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
printf '\nLATER_COMMIT_MARKER = True\n' >> "$snap/packages/cluster-mcp-slurm/src/cluster_mcp/slurm/__init__.py"
G commit -q -am later
[ "$sha" != "$(G rev-parse HEAD)" ] || fail 'the marker commit did not move HEAD'
unset UV_PROJECT VIRTUAL_ENV PYTHONPATH
cd "$HOME"

( cd "$snap" && git -C "$snap" checkout -q "$sha" && uv build -q --all-packages --no-sources --offline -o "$HOME/dist" ) \
  || fail 'uv build --all-packages --no-sources failed on the snapshot'
"$R/.venv/bin/python" -I - "$HOME/dist" <<'EOF' || fail 'the built metadata is wrong (above)'
import re, sys, zipfile
from packaging.requirements import Requirement
from email.parser import Parser
from pathlib import Path
bad = []
def wheel(prefix):
    found = sorted(Path(sys.argv[1]).glob(f'{prefix}-*.whl'))
    if len(found) != 1:
        sys.exit(f'probe: {len(found)} wheels for {prefix}')
    return zipfile.ZipFile(found[0])
def meta(z):
    return Parser().parsestr(next(z.read(n).decode() for n in z.namelist() if n.endswith('.dist-info/METADATA')))
core = meta(wheel('cluster_mcp'))
if sorted(core.get_all('Provides-Extra') or []) != ['rcac', 'slurm']:
    bad.append(f"core Provides-Extra: {core.get_all('Provides-Extra')}")
def canon(name):
    return re.sub(r'[-_.]+', '-', name).lower()
internal = {}
for raw in core.get_all('Requires-Dist') or []:
    req = Requirement(raw)
    if canon(req.name).startswith('cluster-mcp'):
        internal[canon(req.name)] = req
        for extra in ('', 'slurm', 'rcac', 'other'):
            on = req.marker is None or req.marker.evaluate({'extra': extra})
            if on != (extra != '' and canon(req.name) == f'cluster-mcp-{extra}'):
                bad.append(f'core requires {raw!r} with extra {extra!r}: {"on" if on else "off"}')
if set(internal) != {'cluster-mcp-slurm', 'cluster-mcp-rcac'}:
    bad.append(f'core requires internal {sorted(internal)}')
root = meta(wheel('rcac_mcp'))
reqs = [Requirement(r) for r in root.get_all('Requires-Dist') or []]
if [(canon(r.name), set(r.extras), r.marker) for r in reqs] != [('cluster-mcp', {'slurm', 'rcac'}, None)]:
    bad.append(f"root Requires-Dist: {root.get_all('Requires-Dist')}")
for short in ('slurm', 'rcac'):
    z = wheel(f'cluster_mcp_{short}')
    eps = [z.read(n).decode() for n in z.namelist() if n.endswith('.dist-info/entry_points.txt')]
    want = f'{short} = cluster_mcp.{short}.capability:CAPABILITY'
    if not eps or '[cluster_mcp.capabilities]' not in eps[0] or want not in eps[0]:
        bad.append(f'cluster-mcp-{short} wheel entry points: {eps}')
print(*bad, sep='\n', file=sys.stderr)
sys.exit(1 if bad else 0)
EOF

spec="git+file://$snap@$sha#subdirectory=packages/cluster-mcp"
install() { # install LABEL REQUIREMENT SET…: a fresh venv from REQUIREMENT, checked for SET
  # With CONSTRAINTS naming a file, the install is pinned by it (uv pip install -c).
  label=$1; req=$2; shift 2
  uv venv -q "$HOME/venv-$label" || fail "$label: uv venv failed"
  if [ -n "${CONSTRAINTS:-}" ]; then
    uv pip install -q --offline --python "$HOME/venv-$label/bin/python" -c "$CONSTRAINTS" "$req" \
      || fail "$label: uv pip install -c $CONSTRAINTS $req failed"
  else
    uv pip install -q --offline --python "$HOME/venv-$label/bin/python" "$req" || fail "$label: uv pip install $req failed"
  fi
  "$HOME/venv-$label/bin/python" -I - "$sha" "$snap" <<'EOF' || fail "$label: an installed distribution is not from the snapshot commit (above)"
import importlib.metadata as md, json, sys
sha, snap = sys.argv[1], sys.argv[2]
bad = []
for d in md.distributions():
    name = d.metadata['Name']
    if not (name.replace('_', '-').lower().startswith('cluster-mcp') or name.replace('_', '-').lower() == 'rcac-mcp'):
        continue
    info = json.loads(d.read_text('direct_url.json') or '{}')
    if info.get('vcs_info', {}).get('commit_id') != sha:
        bad.append(f'{name}: {info}')
try:
    import cluster_mcp.slurm as s
    if hasattr(s, 'LATER_COMMIT_MARKER'):
        bad.append('cluster_mcp.slurm carries the later commit')
except ImportError:
    pass
print(*bad, sep='\n', file=sys.stderr)
sys.exit(1 if bad else 0)
EOF
  "$HOME/venv-$label/bin/python" -I "$R/$V/registry.py" "$@" || fail "$label: the installed set is wrong (above)"
  echo "probe: $label ok" >&2
}
install core "cluster-mcp @ $spec"
install slurm "cluster-mcp[slurm] @ $spec" slurm
install rcac "cluster-mcp[rcac] @ $spec" rcac
install both "cluster-mcp[slurm,rcac] @ $spec" slurm rcac
install root "rcac-mcp @ git+file://$snap@$sha" slurm rcac

"$HOME/venv-root/bin/python" -I "$R/$V/surface.py" "$HOME/root.json" || fail 'cannot describe the root install surface'

# 3a. Lock-free: BASE_REF's old install line, resolved as this run resolved the snapshot's.
oldsnap="$HOME/base-snapshot"
mkdir -p "$oldsnap"
git -C "$R" archive "$BASE_REF" | tar -xf - -C "$oldsnap"
O() { git -C "$oldsnap" -c user.name=probe -c user.email=probe@invalid -c commit.gpgsign=false "$@"; }
O init -q
O add -A
O commit -q -m base
oldsha=$(O rev-parse HEAD)
uv venv -q "$HOME/venv-baseroot" || fail 'baseroot: uv venv failed'
uv pip install -q --offline --python "$HOME/venv-baseroot/bin/python" "rcac-mcp @ git+file://$oldsnap@$oldsha" \
  || fail "baseroot: uv pip install of BASE_REF's root failed"
"$HOME/venv-baseroot/bin/python" -I "$R/$V/surface.py" "$HOME/baseroot.json" || fail "cannot describe BASE_REF's root install surface"
uv run --no-project --offline python -I "$R/$V/compare.py" "$HOME/baseroot.json" "$HOME/root.json" \
  || fail 'lock-free: the old install line serves another surface than it did at BASE_REF'
echo 'probe: lock-free compare ok' >&2

# 3b. Lock-pinned: the snapshot's root under its own lock, against BASE_REF's locked sync.
( cd "$snap" && uv export -q --frozen --offline --no-hashes --no-emit-workspace --no-dev -o "$HOME/constraints.txt" ) \
  || fail 'cannot export the snapshot lock as constraints'
grep -q '^fastmcp==' "$HOME/constraints.txt" || fail 'the exported constraints pin no fastmcp'
CONSTRAINTS="$HOME/constraints.txt" install lockroot "rcac-mcp @ git+file://$snap@$sha" slurm rcac
"$HOME/venv-lockroot/bin/python" -I "$R/$V/surface.py" "$HOME/lockroot.json" || fail 'cannot describe the lock-pinned root install surface'
uv run --no-project --offline python -I "$R/$V/compare.py" "$HOME/base.json" "$HOME/lockroot.json" \
  || fail 'lock-pinned: the old install line serves another surface than before the cycle'
echo 'probe: lock-pinned compare ok' >&2

"$R/.venv/bin/python" -I "$R/$V/expect.py" "$HOME/root-expect.json" core slurm rcac
"$R/.venv/bin/python" -I "$R/$V/served.py" "$HOME/root-expect.json" -- "$HOME/venv-root/bin/rcac-mcp" -e local \
  || fail 'the rcac-mcp command of the old install line serves another surface over stdio'

uvx -q --offline --from "cluster-mcp[slurm,rcac] @ $spec" cluster-mcp --help > /dev/null 2> "$HOME/uvx.err" \
  || { cat "$HOME/uvx.err" >&2; fail 'the README install line (uvx with the extras) failed'; }
uvx -q --offline --from "git+file://$snap@$sha" rcac-mcp --help > /dev/null 2> "$HOME/legacy.err" \
  || { cat "$HOME/legacy.err" >&2; fail 'the old install line (rcac-mcp from the root) failed'; }
echo "probe: ok (commit $sha)" >&2
