#!/bin/sh
# The phase gates of rcac-extra-brings-slurm, one mode per part.
#
# Usage, from the worktree root:  sh spec/rcac-extra-brings-slurm/verify/gate.sh MODE
#
#   files     the fixture's bytes are the pinned ones and the base's; the cycle changed only the paths
#             it may touch (text_checks.py files). Usable alone before any push.
#   p1        files; the lock; the packaging, surface, core-only and deprecation-window tests; the
#             install lines; the install-level check (install_surfaces.py); the extras mutants
#   p2        files; the rcac set read as the RCAC member registered alone; the ROADMAP entries and
#             the seed; the deferral ledger; the capability, surface and hygiene tests
#   full      the profile's whole verify, read from AGENTS.md § Factory (never restated here)
#
# Each mode runs only its own checks (code-plan Step 6.9). Every mode diffs against
# BASE=${GATE_BASE:-$(git merge-base HEAD origin/develop)}, never a commit found by its subject, so
# the gates survive the branch's squash at publish. Once the cycle has landed, HEAD is on
# origin/develop and the merge base is HEAD itself: re-run a gate then with GATE_BASE=916cecf.
# Every check reads the index, what the next commit holds, and every mode refuses unstaged changes:
# stage the phase's work before running a mode.
#
# Footprint: one pytest, uv or python process at a time, plus install_surfaces.py's one uvx server
# at a time under bin/sandbox.sh; peak about 5 processes, under 1.5 GB. Nothing runs in the
# background, so an early exit leaves no worker behind.

set -eu

SLUG=rcac-extra-brings-slurm
SPEC="spec/$SLUG"
FIXTURE=tests/fixtures/served_surface.json
# The fixture's bytes on the base, 916cecf: the cycle must not change them (GOAL R4).
FIXTURE_SHA256=2e0dc91fef3cfae3a04358178486e7dbef2faf0989c89e39ccce7399595d6561
UV_PYTHON=3.14
export UV_PYTHON
# The fixture's update mode is never on in a gate, and no uv env file can set a variable again.
unset UPDATE_SURFACE MCP_BASE_URL UV_ENV_FILE
UV_NO_ENV_FILE=1
export UV_NO_ENV_FILE

say() { printf '%s\n' "gate: $*" >&2; }
die() { printf '%s\n' "gate: FAIL: $*" >&2; exit 1; }

base() {
    b=${GATE_BASE:-$(git merge-base HEAD origin/develop)}
    [ -n "$b" ] || die 'no base: set GATE_BASE or fetch origin/develop'
    git rev-parse --verify --quiet "$b^{commit}" >/dev/null || die "base $b is not a commit"
    printf '%s\n' "$b"
}

# The fixture in the working tree, in the index and on the base is the pinned bytes.
fixture() {
    b=$(base)
    got=$(shasum -a 256 "$FIXTURE" | cut -d' ' -f1)
    [ "$got" = "$FIXTURE_SHA256" ] || die "$FIXTURE is $got, expected $FIXTURE_SHA256 ($1)"
    git diff --quiet -- "$FIXTURE" || die "$FIXTURE differs from the index ($1)"
    git diff --cached --quiet "$b" -- "$FIXTURE" || die "$FIXTURE in the index differs from the base ($1)"
    say "ok: $FIXTURE is $FIXTURE_SHA256 ($1)"
}

checks() { uv run python -I "$SPEC/verify/text_checks.py" "$1" "$(base)"; }

# The working tree is the index: pytest and uv read the working tree, every other check the index,
# so the two must be one tree for a green gate to mean the commit.
staged_is_worktree() {
    git diff --quiet || die "unstaged changes: stage the phase's work, or set them aside ($(git diff --name-only | tr '\n' ' '))"
}

files() {
    staged_is_worktree
    fixture 'files'
    checks files
}

p1() {
    files
    uv lock --check
    checks lock
    checks install-lines
    # The extras pin and its controls, by id; the compat root; the snapshot test; the real core-only
    # environment (the bare core installs no member); the README's upgrade section, which keeps the
    # compat root's [slurm,rcac] line.
    uv run pytest -q -p no:cacheprovider \
        tests/test_packaging.py::test_core_declares_the_capability_extras \
        tests/test_packaging.py::test_extra_check_names_the_extra_that_breaks_the_rule \
        tests/test_packaging.py::test_compat_root_installs_every_capability
    uv run pytest -q -p no:cacheprovider \
        tests/test_packaging.py tests/test_surface.py tests/test_core_only.py tests/test_deprecation_window.py
    fixture 'after pytest'
    uv run python -I "$SPEC/verify/install_surfaces.py" "$(base)"
    fixture 'after the install check'
    uv run python -I "$SPEC/verify/extra_mutants.py"
    fixture 'after the extras mutants'
}

p2() {
    files
    checks rcac-set
    checks roadmap
    checks ledger
    uv run pytest -q -p no:cacheprovider tests/test_capabilities.py tests/test_surface.py tests/test_hygiene.py
    fixture 'after pytest'
}

# The profile's verify row, from the base's AGENTS.md: the cycle edits AGENTS.md, and must not have
# changed the row it runs.
full() {
    staged_is_worktree
    b=$(base)
    cmd=$(git show "$b:AGENTS.md" | sed -n 's/^| verify | `\([^`]*\)`.*/\1/p')
    [ -n "$cmd" ] || die "no verify row in the base's AGENTS.md § Factory"
    now=$(git show ':AGENTS.md' | sed -n 's/^| verify | `\([^`]*\)`.*/\1/p')
    [ "$now" = "$cmd" ] || die 'the verify row in AGENTS.md differs from the base'
    fixture 'before the full verify'
    say "running the profile's verify"
    sh -c "$cmd"
    fixture 'after the full verify'
}

main() {
    [ $# -eq 1 ] || die 'usage: gate.sh files|p1|p2|full'
    [ -f "$SPEC/GOAL.md" ] || die 'run from the cycle worktree root'
    case $1 in
        files|p1|p2|full) "$1" ;;
        *) die "unknown mode: $1" ;;
    esac
    say "ok: $1"
}

main "$@"
