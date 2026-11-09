#!/bin/sh
# Phase gates for annotation-check.
#
# Usage: sh spec/annotation-check/verify/gate.sh MODE
#   static  the cycle's footprint: only its own files changed, § Factory untouched
#   P1      static, the new module in both eras with its named tests, the rails it must keep, the
#           served-surface baseline, and seen_red.sh (a slice planted in each kind of position, in
#           the core and in two other members' modules)
#   P2      static, the AGENTS.md entry and the deferral ledger, then `full`
#   phase   P2 without `full` (the part build's fail-once mutation targets)
#   full    the profile's verify, read from AGENTS.md § Factory at run time (never restated here)
#
# Footprint: one command at a time. P1 peaks at 5 processes (this shell, uv, pytest,
# bin/sandbox.sh, the check's child interpreter), about 300 MB, 113 s in the plan's dry run (35 plants).
# `full` is the profile's verify: about 26 min on the planner's host; run it in the background.
set -eu
# Where this script lives, worked out before the cd, so a relative invocation from anywhere works.
here=$(cd "$(dirname "$0")" && pwd)
cd "$(git rev-parse --show-toplevel)"
export UV_PYTHON="${UV_PYTHON:-3.14}"
mode=${1:?usage: gate.sh static|P1|P2|phase|full}

fail() { echo "gate: FAIL $*" >&2; exit 1; }
ok() { echo "gate: ok $*"; }

scratch=$(mktemp -d "${TMPDIR:-/tmp}/ac-gate.XXXXXX")
trap 'rm -rf "$scratch"' EXIT HUP INT TERM

# The base the cycle grades against: where the branch left develop.
base=$(git merge-base HEAD origin/develop)

static() {
  # Every path changed since the base, committed, staged, unstaged or untracked, is one this
  # cycle may change: the new test module, AGENTS.md, its own spec, and a deferral seed with its
  # ROADMAP entry. Nothing under packages/ (no src change, no dependency), no lock or pyproject, no
  # workflow, no fixture, no bin/, and neither file the sibling gate cycles hold.
  # --no-renames: a file moved out of packages/ is listed at both ends, never only where it landed.
  changed=$( { git diff --no-renames --name-only "$base"; git ls-files --others --exclude-standard; } | sort -u)
  bad=$(printf '%s\n' "$changed" | grep -v -E '^(tests/test_annotations\.py|AGENTS\.md|ROADMAP\.md|issues/[^/]+\.md|spec/annotation-check/.*)$' || true)
  [ -z "$bad" ] || fail "static: paths outside the cycle's footprint changed: $(printf '%s ' $bad)"
  # No new gate command: § Factory (the profile, the release recipe and its gate) is unchanged.
  git show "$base:AGENTS.md" | sed -n '/^## Factory$/,/^## Invariants$/p' > "$scratch/factory-base"
  sed -n '/^## Factory$/,/^## Invariants$/p' AGENTS.md > "$scratch/factory-now"
  [ -s "$scratch/factory-now" ] || fail 'static: AGENTS.md has no § Factory'
  cmp -s "$scratch/factory-base" "$scratch/factory-now" || fail 'static: AGENTS.md § Factory changed (the profile, recipe or gate)'
  ok "static (base $(git rev-parse --short "$base"))"
}

# The test ids this cycle's gates depend on: a missing one is a pytest usage error, not a pass.
IDS="tests/test_annotations.py::test_every_kept_annotation_in_the_workspace_is_a_type
tests/test_annotations.py::test_the_members_are_the_locked_workspace
tests/test_annotations.py::test_a_planted_slice_is_refused_naming_where
tests/test_annotations.py::test_an_unresolvable_annotation_is_refused
tests/test_annotations.py::test_a_scope_dependent_annotation_is_refused
tests/test_annotations.py::test_a_member_without_src_is_refused
tests/test_annotations.py::test_a_type_checking_only_declaration_is_not_read
tests/test_annotations.py::test_a_qualifier_out_of_its_place_is_named
tests/test_annotations.py::test_a_failed_import_names_the_statement_that_raised
tests/test_annotations.py::test_valid_shapes_pass
tests/test_annotations.py::test_a_main_module_is_never_imported
tests/test_annotations.py::test_a_member_added_later_is_checked
tests/test_annotations.py::test_an_excluded_member_is_not_checked
tests/test_annotations.py::test_a_module_imported_from_elsewhere_is_refused
tests/test_annotations.py::test_non_types_are_named"

p1() {
  static
  uv lock --check
  # The named tests exist and pass, in each era; the whole module too.
  uv run pytest -q -p no:cacheprovider $IDS
  CLUSTER_MCP_TEST_ERA=modern uv run pytest -q -p no:cacheprovider $IDS
  start=$(date +%s)
  uv run pytest -q -p no:cacheprovider tests/test_annotations.py
  end=$(date +%s)
  ok "module, legacy era, $((end - start)) s wall (the figure the CI-budget row quotes)"
  CLUSTER_MCP_TEST_ERA=modern uv run pytest -q -p no:cacheprovider tests/test_annotations.py
  # The rails the new module must keep (spec ids, sandboxed launches, skips, stack imports), the
  # suite partition, and the one exact-shape pin this check does not replace.
  uv run pytest -q -p no:cacheprovider tests/test_hygiene.py tests/test_suite_parts.py tests/test_auth_modes.py
  # The served surface is unchanged.
  uv run pytest -q -p no:cacheprovider tests/test_surface.py::test_served_surface_matches_baseline
  # Seen red: a slice planted in each kind of position, in the core and in other members.
  sh "$here/seen_red.sh"
  ok P1
}

ledger() {
  # Every deferral the plan or a phase body names has its seed and ROADMAP entry. Headings are
  # skipped: a template heading is not a deferral. A missing plan file is a failure, not a pass.
  for doc in spec/annotation-check/TECH.md spec/annotation-check/PLAN.md; do
    [ -f "$doc" ] || fail "ledger: $doc is missing"
  done
  grep -v -h -E '^#' spec/annotation-check/TECH.md spec/annotation-check/PLAN.md \
    | grep -i -E 'do not fix here|known limitation|limitation|follow-up|left as|deferred to|not covered|leniency' \
    > "$scratch/deferrals" || true
  while IFS= read -r line; do
    seed=$(printf '%s\n' "$line" | grep -o -E 'issues/[a-z0-9-]+\.md' | head -1 || true)
    [ -n "$seed" ] || fail "ledger: a deferral names no issues/ seed: $line"
    [ -f "$seed" ] || fail "ledger: $seed does not exist"
    grep -q -F "$seed" ROADMAP.md || fail "ledger: ROADMAP.md has no entry for $seed"
  done < "$scratch/deferrals"
  ok "ledger ($(wc -l < "$scratch/deferrals" | tr -d ' ') deferrals)"
}

docs() {
  # AGENTS.md § Testing has an entry for the new module, and that entry names its check functions.
  sed -n '/^## Testing$/,/^## Packaging$/p' AGENTS.md \
    | awk '/^  - `tests\/test_annotations\.py`/ {on=1; print; next} on && /^  - / {on=0} on {print}' \
    > "$scratch/entry"
  [ -s "$scratch/entry" ] || fail 'docs: AGENTS.md § Testing has no tests/test_annotations.py entry'
  for word in workspace_violations type_expression_violations annotation_positions; do
    grep -q -F "$word" "$scratch/entry" || fail "docs: the tests/test_annotations.py entry does not name $word"
  done
  ok docs
}

full() {
  # The profile's verify, verbatim from AGENTS.md § Factory → Profile.
  cmd=$(sed -n 's/^| verify | `\(.*\)`: the full gate\..*$/\1/p' AGENTS.md)
  [ -n "$cmd" ] || fail 'full: no verify row found in AGENTS.md § Factory'
  echo "gate: running the profile's verify"
  sh -c "$cmd"
  ok full
}

# The whole dispatch is one function, called on the last line with `exit` beside it: sh reads a
# script as it runs, so an edit made to this file during a 26-minute `full` would otherwise run
# whatever bytes then follow the read offset.
main() {
  case "$mode" in
    static) static ;;
    P1) p1 ;;
    phase) static; docs; ledger; ok phase ;;
    P2) static; docs; ledger; full; ok P2 ;;
    full) full ;;
    *) fail "unknown mode $mode" ;;
  esac
}

main "$@"; exit $?
