#!/bin/sh
# Runs the frozen row gate, verify/rows.sh, unchanged, with its two leftover checks scoped to this
# run: an attached image counts only when its path lies under this run's pytest base directory, and a
# stand-in process only when its command names that directory. Every other check of rows.sh (each id
# PASSED by exact id in both eras, pytest's exit, the annotations, the partition and hygiene in `all`)
# runs as it is.
#
# Why: rows.sh's leftover check reads any image under a pytest temp root (`pytest-of-`) as the rows'.
# Other suites on the same host that still run the fixture as it was can leak such an image while this
# gate runs, and the check then goes red on host state no row made. Seen red that way first: P1's gate,
# attempt 1 (2026-11-10), every id passed in both eras.
#
# How: pytest runs with `--basetemp` set (through PYTEST_ADDOPTS) to a directory this script makes,
# whose name carries `pytest-of-` (so rows.sh's own pattern still matches the rows' images) and a
# unique token. Two shims go first on PATH: `hdiutil info` (exactly that argv) drops each line naming
# `pytest-of-` without the token, and `ps -A -ww -o stat= -o args=` (exactly rows.sh's argv) drops
# each stand-in line without the token; every other call of either tool runs the real one, unchanged.
# After a green run, the script asserts the leftover step went through both shims (the `hdiutil` one
# only where `hdiutil` exists) and that, when it read `ps`, the rows had run under the base directory
# (a later pytest in the same mode, the hygiene run of `all`, reuses that directory), so the scoping
# is never vacuous.
#
# Usage, from the cycle worktree root:
#   sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh p1|p2|all
#   sh spec/full-volume-fixture-leaks-hdiutil/remediation/scoped-leftovers.sh --around CMD...
# The second form runs CMD (a gate that runs rows.sh itself, such as `verify/p3.sh pre`) under the
# same scoping and the same checks.
# SCOPED_GATE_WORK may name an existing empty directory to use instead of a fresh one (the planted
# red and green runs that showed this wrapper's checks use it to plant under, or beside, the base).
#
# Footprint: rows.sh's (one pytest at a time, under 400 MB), plus two tiny shell shims. Leaves its
# directory (the shims and pytest's base directory, as pytest's own temp root does) under $TMPDIR.
set -u
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
rows="$here/../verify/rows.sh"
real_ps=$(command -v ps) || { echo 'scoped-leftovers.sh: no ps' >&2; exit 1; }
real_hdiutil=$(command -v hdiutil || true)
work=${SCOPED_GATE_WORK:-$(mktemp -d "${TMPDIR:-/tmp}/fvfl-gate.XXXXXX")}
work=$(CDPATH= cd -- "$work" && pwd) || exit 1
token=$(basename "$work")
basetemp="$work/pytest-of-gate"
mkdir -p "$work/shims" || exit 1
: > "$work/used"

cat > "$work/shims/ps" <<EOF
#!/bin/sh
if [ "\$*" = '-A -ww -o stat= -o args=' ]; then
    echo ps >> '$work/used'
    ls -d '$basetemp'/test_a_disk_image_step_tha* >/dev/null 2>&1 && echo rows-under-base >> '$work/used'
    '$real_ps' "\$@" | awk -v t='$token' 'index(\$0, "tests/hdiutil_standin.py") == 0 || index(\$0, t) > 0'
else
    exec '$real_ps' "\$@"
fi
EOF
chmod +x "$work/shims/ps"
if [ -n "$real_hdiutil" ]; then
    cat > "$work/shims/hdiutil" <<EOF
#!/bin/sh
if [ "\$#" -eq 1 ] && [ "\$1" = info ]; then
    echo hdiutil >> '$work/used'
    '$real_hdiutil' info | awk -v t='$token' 'index(\$0, "pytest-of-") == 0 || index(\$0, t) > 0'
else
    exec '$real_hdiutil' "\$@"
fi
EOF
    chmod +x "$work/shims/hdiutil"
fi

if [ "${1:-}" = --around ]; then
    shift
    what=$*
    PATH="$work/shims:$PATH" PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }--basetemp=$basetemp" "$@"
else
    what=$1
    PATH="$work/shims:$PATH" PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }--basetemp=$basetemp" sh "$rows" "$@"
fi
status=$?
[ "$status" -eq 0 ] || exit "$status"

grep -qx ps "$work/used" || { echo 'scoped-leftovers.sh: the leftover check did not read ps through the shim' >&2; exit 1; }
grep -qx rows-under-base "$work/used" \
    || { echo "scoped-leftovers.sh: the rows did not run under $basetemp" >&2; exit 1; }
if [ -n "$real_hdiutil" ]; then
    grep -qx hdiutil "$work/used" \
        || { echo 'scoped-leftovers.sh: the leftover check did not read hdiutil info through the shim' >&2; exit 1; }
fi
echo "scoped-leftovers.sh: leftovers scoped to $token; $what ok"
