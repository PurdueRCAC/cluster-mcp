#!/bin/sh
# The phase gates of surface-fixture-after-a-surface-change, one mode per phase.
#
# Usage, from the worktree root:  sh spec/surface-fixture-after-a-surface-change/verify/gate.sh MODE
#
#   files   nothing under packages/ differs from the plan commit (the cycle changes no served
#           surface); usable alone before any push
#   ids     each required drift-control row ran and passed (P2 and P3 rows), so a matrix cannot
#           shrink, skip or xfail and stay green
#   p1      the re-baseline: recorder, comparison, command, fixture, R6 check, mutants re-planted
#   p2      the drift, recorder, carve-out, era, delta and no-run controls
#   p3      the per-set check and its additive controls
#   p4      the documented method, the comparison/recorder sweep and the deferral ledger
#   full    the profile's whole verify, read from AGENTS.md (the last phase, after p4)
#
# Each mode runs only its own phase's checks (code-plan Step 6.9): the last phase's TECH verify
# adds the profile's full verify after `p4`.
#
# Footprint: one pytest (or one python) process at a time, plus the mutation runner's and the
# sweep's single child at a time; peak about 4 processes and under 1 GB. Nothing runs in the
# background, so an early exit leaves no worker behind.

set -eu

SLUG=surface-fixture-after-a-surface-change
SPEC="spec/$SLUG"
UV_PYTHON=3.14
export UV_PYTHON

say() { printf '%s\n' "gate: $*" >&2; }
die() { printf '%s\n' "gate: FAIL: $*" >&2; exit 1; }

# The commit that added this cycle's TECH.md: the plan commit, the base every file check grades from.
plan_commit() {
    base=$(git log --diff-filter=A --format=%H -- "$SPEC/TECH.md" | tail -n 1)
    [ -n "$base" ] || die "no commit adds $SPEC/TECH.md: run from the cycle worktree after the plan commit"
    printf '%s\n' "$base"
}

# What the served surface is built from: the members' source and the locked stack.
SOURCES='packages/ uv.lock pyproject.toml'

files() {
    base=$(plan_commit)
    # shellcheck disable=SC2086
    changed=$(git diff --name-only "$base" -- $SOURCES)
    # shellcheck disable=SC2086
    untracked=$(git ls-files --others --exclude-standard -- $SOURCES)
    [ -z "$changed$untracked" ] || die "the cycle changes what the served surface is built from (Non-goal): $changed $untracked"
    say 'ok: nothing under packages/, uv.lock or pyproject.toml changed since the plan commit'
}

FIXTURE=tests/fixtures/served_surface.json

# The fixture in the working tree is the staged one, before and after every step that could write it:
# neither the suite nor a drive may update it (R1).
fixture_untouched() {
    git diff --quiet -- "$FIXTURE" || die "$FIXTURE differs from the staged copy ($1)"
}

# `grep` finds nothing (status 1) where the text must be gone; a missing file (status 2) is a failure.
absent() {
    pattern=$1; shift
    set +e
    grep -nw -- "$pattern" "$@"
    status=$?
    set -e
    [ "$status" -eq 1 ] || die "'$pattern' is still in $* (or a file is missing: grep exited $status)"
}

# Both eras, the same arguments; each era named, never inherited from the calling shell.
both_eras() {
    CLUSTER_MCP_TEST_ERA=legacy uv run pytest -q "$@"
    CLUSTER_MCP_TEST_ERA=modern uv run pytest -q "$@"
    fixture_untouched "after pytest $*"
}

ids() {
    uv run python -I "$SPEC/verify/surface_checks.py" ids all
}

p1() {
    files
    uv lock --check
    fixture_untouched 'at the start'
    absent 'test_surface_fixture_is_the_baseline_shape' tests/test_surface.py
    absent 'TOLERATED' tests/test_surface.py tests/harness.py
    both_eras tests/test_surface.py::test_served_surface_matches_baseline \
        tests/test_surface.py::test_surface_fixture_is_the_commands_form
    both_eras tests/test_surface.py tests/test_mutations.py tests/test_capabilities.py tests/test_literal_args.py \
        tests/test_storage_resource.py tests/test_protocol.py tests/test_probe_startup.py
    # The baseline test connected in each era it ran in (a test that returned early would log nothing).
    uv run python -I "$SPEC/verify/surface_checks.py" era-proof
    uv run python -I "$SPEC/verify/command_drive.py" all
    fixture_untouched 'after the command drive'
    uv run python -I "$SPEC/verify/rebaseline_check.py" tests/fixtures/served_surface.json
    # Every mutation case that plants into the fixture or targets the surface comparison applies and is killed.
    cases=$(uv run python -I "$SPEC/verify/surface_checks.py" surface-cases)
    [ -n "$cases" ] || die 'no surface mutation case found'
    # shellcheck disable=SC2086
    uv run python tests/mutants.py --self-check $cases
    fixture_untouched 'after the mutation cases'
}

p2() {
    files
    fixture_untouched 'at the start'
    uv run python -I "$SPEC/verify/surface_checks.py" ids full
    both_eras tests/test_surface.py::test_surface_check_catches_drift \
        tests/test_surface.py::test_recorder_sees_what_the_server_starts_serving \
        tests/test_surface.py::test_version_carve_out_accepts_only_the_served_version \
        tests/test_surface.py::test_era_carve_out_accepts_only_the_capabilities \
        tests/test_surface.py::test_era_check_refuses_every_other_difference \
        tests/test_surface.py::test_delta_lists_every_changed_path \
        tests/test_surface.py::test_nothing_runs_the_surface_command \
        tests/test_surface.py::test_command_scan_catches_planted_runs
    # Review cycle 2: every key the fixture holds and the five former tolerated kinds (N2), and the
    # command's choices made in `command_main`, its file holding none (N1).
    both_eras tests/test_surface.py::test_every_key_the_fixture_holds_is_compared \
        tests/test_surface.py::test_former_tolerated_kinds_are_differences \
        tests/test_surface.py::test_inlined_output_definitions_are_a_difference \
        tests/test_surface.py::test_command_lists_the_delta_against_the_against_file \
        tests/test_surface.py::test_command_lists_the_delta_against_head_without_against \
        tests/test_surface.py::test_command_lists_every_key_added_when_head_has_no_fixture \
        tests/test_surface.py::test_command_writes_the_fixture_by_default \
        tests/test_surface.py::test_command_refuses_writing_nothing \
        tests/test_surface.py::test_command_refuses_a_bad_argument_before_anything \
        tests/test_surface.py::test_the_surface_command_makes_no_choice \
        tests/test_surface.py::test_command_choice_scan_catches_planted_choices
    both_eras tests/test_surface.py
}

p3() {
    files
    fixture_untouched 'at the start'
    uv run python -I "$SPEC/verify/surface_checks.py" ids sets
    both_eras tests/test_surface.py::test_every_capability_set_serves_the_fixtures_entries \
        tests/test_surface.py::test_set_check_catches_drift \
        tests/test_surface.py::test_set_check_compares_every_key_the_fixture_holds
    both_eras tests/test_surface.py tests/test_capabilities.py
}

p4() {
    files
    fixture_untouched 'at the start'
    ids
    uv run python -I "$SPEC/verify/command_drive.py" all
    fixture_untouched 'after the command drive'
    uv run python -I "$SPEC/verify/rebaseline_check.py" tests/fixtures/served_surface.json
    uv run python -I "$SPEC/verify/docs_check.py" docs
    uv run python -I "$SPEC/verify/docs_check.py" ledger
    uv run python -I "$SPEC/verify/sweep.py"
    fixture_untouched 'after the sweep'
    # Each sweep child carries the token as its own argv word (`sh -c … surface-sweep-child`).
    if pgrep -f 'surface-sweep-child' >/dev/null; then die 'a sweep child outlived the sweep'; fi
    say 'ok: p4'
}

# The profile's whole `verify`, read from AGENTS.md § Factory so it is never restated here.
full() {
    cmd=$(sed -n 's/^| verify | `\([^`]*\)`.*/\1/p' AGENTS.md)
    [ -n "$cmd" ] || die "no verify row in AGENTS.md § Factory"
    say "running the profile's verify (about 26 minutes)"
    sh -c "$cmd"
}

main() {
    [ $# -eq 1 ] || die "usage: gate.sh files|ids|p1|p2|p3|p4|full"
    [ -f "$SPEC/GOAL.md" ] || die "run from the cycle worktree root"
    case $1 in
        files|ids|p1|p2|p3|p4|full) "$1" ;;
        *) die "unknown mode: $1" ;;
    esac
    say "ok: $1"
}

main "$@"; exit $?
