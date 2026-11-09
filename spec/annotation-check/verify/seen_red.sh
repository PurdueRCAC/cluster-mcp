#!/bin/sh
# Seen red: the annotation check fails on a slice planted in each kind of position it covers, in a
# module of the core and in a module of another member, naming the planted position, and passes on
# the unplanted tree.
#
# Reads committed state: the scratch tree is `git archive` of HEAD (SEEN_RED_REV overrides it, for
# the plan's dry run only), synced offline into its own environment, so a plant never touches the
# worktree and the check reads the scratch copy's files, not the worktree's.
#
# Footprint: one pytest at a time; peak 5 processes (this shell, uv, pytest, bin/sandbox.sh, the
# check's child interpreter), about 300 MB. Wall time: PLAN § 4 quotes the dry run's (one baseline run,
# then one run per case).
#
# Usage: spec/annotation-check/verify/seen_red.sh            run every case
#        spec/annotation-check/verify/seen_red.sh <case>...  run the named cases (and the baseline)
set -eu

# The whole run is one function, called on the last line with `exit` beside it: sh reads a script
# as it runs, so an edit made to this file mid-run would otherwise run whatever bytes then follow.
main() {

repo=$(git rev-parse --show-toplevel)
rev=${SEEN_RED_REV:-HEAD}
scratch=$(mktemp -d "${TMPDIR:-/tmp}/seen-red.XXXXXX")
trap 'rm -rf "$scratch"' EXIT HUP INT TERM
export UV_PYTHON="${UV_PYTHON:-3.14}"

git -C "$repo" archive "$rev" | tar -x -C "$scratch"
test -f "$scratch/tests/test_annotations.py" || { echo "seen_red: $rev has no tests/test_annotations.py" >&2; exit 1; }
(cd "$scratch" && uv sync --locked --offline -q) || (cd "$scratch" && uv sync --locked -q)

TEST=tests/test_annotations.py::test_every_kept_annotation_in_the_workspace_is_a_type
CORE=packages/cluster-mcp/src/cluster_mcp/core/auth.py
SLURM=packages/cluster-mcp-slurm/src/cluster_mcp/slurm/tools.py
RCAC=packages/cluster-mcp-rcac/src/cluster_mcp/rcac/resources.py

# Each case, its fields split on '~': id, file, plant mode (append or replace), the text, and what the red output must hold.
# auth.py and slurm/tools.py postpone their annotations; rcac/resources.py evaluates them eagerly.
cases() {
  cat <<'EOF'
core-variable~CORE~append~_PLANTED: dict[str, int:] = {}~cluster_mcp.core.auth:~: _PLANTED: 
core-conditional-variable~CORE~append~if True:\n    _PLANTED: dict[str, int:] = {}~cluster_mcp.core.auth:~: _PLANTED: 
core-attribute~CORE~append~class _Planted:\n    held: dict[str, int:]~cluster_mcp.core.auth:~: _Planted.held: 
core-nested-attribute~CORE~append~class _Planted:\n    class Inner:\n        held: dict[str, int:]~cluster_mcp.core.auth:~: _Planted.Inner.held: 
core-functional-attribute~CORE~append~from typing import TypedDict as _TD\n_Planted = _TD('_Planted', {'held': dict[str, int:]})~cluster_mcp.core.auth:~: _Planted.held: 
core-parameter~CORE~append~def _planted(given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _planted(given): 
core-positional-only~CORE~append~def _planted(given: dict[str, int:], /) -> None: ...~cluster_mcp.core.auth:~: _planted(given): 
core-keyword-only~CORE~append~def _planted(*, given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _planted(given): 
core-varargs~CORE~append~def _planted(*given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _planted(given): 
core-kwargs~CORE~append~def _planted(**given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _planted(given): 
core-return~CORE~append~def _planted() -> dict[str, int:]: ...~cluster_mcp.core.auth:~: _planted() ->: 
core-async-return~CORE~append~async def _planted() -> dict[str, int:]: ...~cluster_mcp.core.auth:~: _planted() ->: 
core-method-parameter~CORE~append~class _Planted:\n    def run(self, given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _Planted.run(given): 
core-method-return~CORE~append~class _Planted:\n    def run(self) -> dict[str, int:]: ...~cluster_mcp.core.auth:~: _Planted.run() ->: 
core-static-method~CORE~append~class _Planted:\n    @staticmethod\n    def run(given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _Planted.run(given): 
core-nested-parameter~CORE~append~def _planted() -> None:\n    def inner(given: dict[str, int:]) -> None: ...~cluster_mcp.core.auth:~: _planted.inner(given): 
core-auth-modes~CORE~replace~AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider | None]]] =>>>AUTH_MODES: Final[Dict[str, Callable[[], AuthProvider | None]]:] =~cluster_mcp.core.auth:~: AUTH_MODES: 
member-variable~RCAC~append~_PLANTED: dict[str, int:] = {}~cluster_mcp.rcac.resources:~: _PLANTED: 
member-conditional-variable~RCAC~append~if True:\n    _PLANTED: dict[str, int:] = {}~cluster_mcp.rcac.resources:~: _PLANTED: 
member-attribute~RCAC~append~class _Planted:\n    held: dict[str, int:]~cluster_mcp.rcac.resources:~: _Planted.held: 
member-nested-attribute~RCAC~append~class _Planted:\n    class Inner:\n        held: dict[str, int:]~cluster_mcp.rcac.resources:~: _Planted.Inner.held: 
member-functional-attribute~RCAC~append~from typing import TypedDict as _TD\n_Planted = _TD('_Planted', {'held': dict[str, int:]})~cluster_mcp.rcac.resources:~: _Planted.held: 
member-parameter~RCAC~append~def _planted(given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _planted(given): 
member-positional-only~RCAC~append~def _planted(given: dict[str, int:], /) -> None: ...~cluster_mcp.rcac.resources:~: _planted(given): 
member-keyword-only~RCAC~append~def _planted(*, given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _planted(given): 
member-varargs~RCAC~append~def _planted(*given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _planted(given): 
member-kwargs~RCAC~append~def _planted(**given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _planted(given): 
member-return~RCAC~append~def _planted() -> dict[str, int:]: ...~cluster_mcp.rcac.resources:~: _planted() ->: 
member-async-return~RCAC~append~async def _planted() -> dict[str, int:]: ...~cluster_mcp.rcac.resources:~: _planted() ->: 
member-method-parameter~RCAC~append~class _Planted:\n    def run(self, given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _Planted.run(given): 
member-method-return~RCAC~append~class _Planted:\n    def run(self) -> dict[str, int:]: ...~cluster_mcp.rcac.resources:~: _Planted.run() ->: 
member-static-method~RCAC~append~class _Planted:\n    @staticmethod\n    def run(given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _Planted.run(given): 
member-nested-parameter~RCAC~append~def _planted() -> None:\n    def inner(given: dict[str, int:]) -> None: ...~cluster_mcp.rcac.resources:~: _planted.inner(given): 
tool-parameter~SLURM~replace~def scontrol_show_job(job_id: int) -> str:>>>def scontrol_show_job(job_id: dict[str, int:]) -> str:~cluster_mcp.slurm.tools:~: scontrol_show_job(job_id): 
tool-return~SLURM~replace~def scontrol_show_job(job_id: int) -> str:>>>def scontrol_show_job(job_id: int) -> dict[str, int:]:~cluster_mcp.slurm.tools:~: scontrol_show_job() ->: 
EOF
}

run_test() { (cd "$scratch" && uv run --offline -q pytest -q -p no:cacheprovider "$TEST" 2>&1); }

if ! out=$(run_test); then
  printf '%s\n' "$out" | tail -20 >&2
  echo "seen_red: FAIL baseline: the check is red on the unplanted tree" >&2
  exit 1
fi
echo "seen_red: ok baseline (green on the unplanted tree)"

cases > "$scratch/cases"
ran=''
while IFS='~' read -r id file mode text module where; do
  if [ "$#" -gt 0 ]; then
    wanted=0
    for name in "$@"; do [ "$name" = "$id" ] && wanted=1; done
    [ "$wanted" = 1 ] || continue
  fi
  ran="$ran $id"
  case "$file" in CORE) rel=$CORE ;; SLURM) rel=$SLURM ;; RCAC) rel=$RCAC ;; esac
  target="$scratch/$rel"
  cp "$target" "$target.orig"
  "$scratch/.venv/bin/python" -I - "$target" "$mode" "$text" <<'PY'
import sys
path, mode, text = sys.argv[1], sys.argv[2], sys.argv[3].replace('\\n', '\n')
source = open(path).read()
if mode == 'append':
    planted = source.rstrip('\n') + '\n\n\n' + text + '\n'
else:
    old, new = text.split('>>>')
    if source.count(old) != 1:
        sys.exit(f'seen_red: the text to replace occurs {source.count(old)} times in {path}')
    planted = source.replace(old, new)
open(path, 'w').write(planted)
PY
  if cmp -s "$target" "$target.orig"; then
    echo "seen_red: FAIL $id: the plant did not change $rel" >&2; exit 1
  fi
  if out=$(run_test); then
    echo "seen_red: FAIL $id: the check stayed green with a slice planted in $rel" >&2; exit 1
  fi
  # The red must be the check's own, naming the planted position and the slice it resolved to.
  if ! printf '%s\n' "$out" | grep -F -- "$module" | grep -F -- "$where" | grep -q 'slice'; then
    printf '%s\n' "$out" | grep '^E ' | head -10 >&2
    echo "seen_red: FAIL $id: red, but not naming $module$where with its slice" >&2; exit 1
  fi
  mv "$target.orig" "$target"
  echo "seen_red: ok $id"
done < "$scratch/cases"
for name in "$@"; do
  case " $ran " in *" $name "*) ;; *) echo "seen_red: FAIL no case is named $name" >&2; exit 1 ;; esac
done
[ -n "$ran" ] || { echo "seen_red: FAIL no case ran" >&2; exit 1; }
echo "seen_red: ok every case ($(printf '%s' "$ran" | wc -w | tr -d ' ') planted)"
}

main "$@"; exit $?
