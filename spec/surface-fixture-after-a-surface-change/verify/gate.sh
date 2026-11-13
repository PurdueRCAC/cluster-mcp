#!/bin/sh
# The phase gates of surface-fixture-after-a-surface-change (the snapshot-test re-shape), one mode per phase.
#
# Usage, from the worktree root:  sh spec/surface-fixture-after-a-surface-change/verify/gate.sh MODE
#
#   files   nothing that builds the served surface (packages/, uv.lock, pyproject.toml) differs from
#           the plan commit: the cycle changes no served surface. Usable alone before any push.
#   p1      the snapshot test, its controls, the command gone, the mutation cases re-planted, the
#           re-baselined fixture and its R6 record, the docs
#   p2      the seeds and ROADMAP, the deferral ledger, the aimed mutant sweep (written by P2)
#   full    the profile's whole verify, read from AGENTS.md (the last phase, after p2)
#
# Each mode runs only its own phase's checks (code-plan Step 6.9); the last phase's TECH verify
# adds `full` after `p2`.
#
# Footprint: one pytest or python process at a time, plus the mutation runner's and the sweep's one
# child at a time; peak about 4 processes, under 1 GB. Nothing runs in the background, so an early
# exit leaves no worker behind.

set -eu

SLUG=surface-fixture-after-a-surface-change
SPEC="spec/$SLUG"
FIXTURE=tests/fixtures/served_surface.json
UV_PYTHON=3.14
export UV_PYTHON
# The update mode is never on in a gate (GOAL R1), whatever the calling shell exports, and no uv env
# file can set it again after the unset. `MCP_BASE_URL` is read when `server.py` is imported, before
# the conftest blanks it, and the served icon follows it: the fixture holds the unset value.
unset UPDATE_SURFACE MCP_BASE_URL
UV_NO_ENV_FILE=1
export UV_NO_ENV_FILE
unset UV_ENV_FILE

say() { printf '%s\n' "gate: $*" >&2; }
die() { printf '%s\n' "gate: FAIL: $*" >&2; exit 1; }

# The plan commit, the base every file check grades from: the newest commit whose subject is exactly
# code-plan's (the recorder design's plan commit carries the same subject and is older). The subject
# is compared whole, so a body quoting it does not match.
PLAN_SUBJECT="[test] Plan $SLUG: design + phased roadmap"
plan_commit() {
    base=$(git log --format='%H %s' | awk -v want="$PLAN_SUBJECT" 'substr($0, 42) == want { print $1; exit }')
    [ -n "$base" ] || die "no plan commit ('$PLAN_SUBJECT'): run after it"
    printf '%s\n' "$base"
}

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

# The working tree's fixture is the staged one, before and after every step that could write it:
# nothing in the suite writes it while the update mode is off (R1).
fixture_untouched() {
    git diff --quiet -- "$FIXTURE" || die "$FIXTURE differs from the staged copy ($1)"
}

# The text is gone from the staged copy of each file (the index, what the commit holds): `git grep`
# finds nothing (status 1); a file the index lacks, or any other status, is a failure.
absent() {
    pattern=$1; shift
    for staged in "$@"; do
        git cat-file -e ":$staged" 2>/dev/null || die "$staged is not in the index"
    done
    set +e
    git grep -n --cached -F -e "$pattern" -- "$@"
    status=$?
    set -e
    [ "$status" -eq 1 ] || die "'$pattern' is still in $* (git grep exited $status)"
}

# Both eras, the same arguments; each era named, never inherited from the calling shell.
both_eras() {
    CLUSTER_MCP_TEST_ERA=legacy uv run pytest -q -p no:cacheprovider "$@"
    CLUSTER_MCP_TEST_ERA=modern uv run pytest -q -p no:cacheprovider "$@"
    fixture_untouched "after pytest $*"
}

TS=tests/test_surface.py

p1() {
    files
    uv lock --check
    fixture_untouched 'at the start'
    # The command and everything that served only it are gone (R10); so are the tolerance list, the
    # carve-outs, the per-set check and the generated controls (R3, R7).
    [ ! -e bin/record_surface.py ] || die 'bin/record_surface.py still exists'
    for name in record_surface TOLERATED tolerated_differences command_main CommandEffects \
            surface_violations set_violations era_violations expected_surface delta_lines \
            test_surface_fixture_is_the_baseline_shape test_every_key_the_fixture_holds_is_compared \
            test_set_check_compares_every_key_the_fixture_holds test_former_tolerated_kinds_are_differences \
            test_inlined_output_definitions_are_a_difference test_controls_reach_past_the_fixtures_extent; do
        absent "$name" tests/test_surface.py tests/harness.py
    done
    # The snapshot test and its controls, by id, then the module whole and every consumer of the
    # harness's surface verbs, with the hygiene scans the module answers to.
    both_eras "$TS::test_served_surface_matches_baseline" \
        "$TS::test_a_field_changed_at_depth_fails_naming_its_entry_and_field" \
        "$TS::test_update_mode_regenerates_a_conflicted_fixture" \
        "$TS::test_version_source_names_exactly_one_distribution" \
        "$TS::test_no_workflow_or_script_turns_the_update_mode_on" \
        "$TS::test_recorder_sees_what_the_server_starts_serving" \
        "$TS::test_recorder_follows_every_page" \
        "$TS::test_recorder_refuses_a_name_served_twice" \
        "$TS::test_record_keeps_keys_no_model_declares"
    both_eras "$TS" tests/test_capabilities.py tests/test_literal_args.py tests/test_storage_resource.py \
        tests/test_protocol.py tests/test_probe_startup.py tests/test_mutations.py tests/test_hygiene.py
    # The re-baseline's record (R6), read from the staged fixture.
    uv run python -I "$SPEC/verify/rebaseline_check.py"
    # Every mutation case that plants into the fixture or targets the surface test applies and is
    # killed, in each era (R7).
    cases=$(uv run python -I "$SPEC/verify/snapshot_checks.py" surface-cases)
    [ -n "$cases" ] || die 'no surface mutation case found'
    # shellcheck disable=SC2086
    CLUSTER_MCP_TEST_ERA=legacy uv run python tests/mutants.py $cases
    # shellcheck disable=SC2086
    CLUSTER_MCP_TEST_ERA=modern uv run python tests/mutants.py $cases
    fixture_untouched 'after the mutation cases'
    uv run python -I "$SPEC/verify/snapshot_checks.py" no-enable
    uv run python -I "$SPEC/verify/snapshot_checks.py" docs
    say 'ok: p1'
}

p2() {
    files
    fixture_untouched 'at the start'
    uv run python -I "$SPEC/verify/snapshot_checks.py" seeds
    uv run python -I "$SPEC/verify/snapshot_checks.py" ledger
    # The aimed sweep of the comparison and the normalization (PLAN § 4), both eras; P2 writes it.
    [ -f "$SPEC/verify/sweep.py" ] || die "$SPEC/verify/sweep.py is P2's to write"
    uv run python -I "$SPEC/verify/sweep.py"
    fixture_untouched 'after the sweep'
    # Each sweep child carries the token as its own argv word.
    if pgrep -f 'snapshot-sweep-child' >/dev/null; then die 'a sweep child outlived the sweep'; fi
    say 'ok: p2'
}

# The profile's whole `verify`, read from AGENTS.md § Factory so it is never restated here.
full() {
    cmd=$(sed -n 's/^| verify | `\([^`]*\)`.*/\1/p' AGENTS.md)
    [ -n "$cmd" ] || die "no verify row in AGENTS.md § Factory"
    say "running the profile's verify (about 26 minutes)"
    sh -c "$cmd"
    fixture_untouched 'after the full verify'
}

main() {
    [ $# -eq 1 ] || die "usage: gate.sh files|p1|p2|full"
    [ -f "$SPEC/GOAL.md" ] || die "run from the cycle worktree root"
    case $1 in
        files|p1|p2|full) "$1" ;;
        *) die "unknown mode: $1" ;;
    esac
    say "ok: $1"
}

main "$@"; exit $?
