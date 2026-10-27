#!/bin/sh
# The develop merge before final review: the frozen gate, with the retired context row and mutant
# swapped for their successors. Run from the worktree root:
#   sh spec/ssh-reconnect-loop/remediation/M1-merge-develop.sh P2|tests|mutants
#
# agents-d-instructions (09ce3af, on develop) deleted `resources.load_cluster_context` and its
# cache: the site context is read once at startup and `cluster_context` / `rcac://context` serve
# that text and run nothing. P2's guard (a -1002 is never cached as the context, R3) is moot by
# construction, so its row and mutant were retired with the code they targeted:
#   test_a_reconnect_failure_is_never_cached_as_cluster_context -> test_a_reconnect_failure_never_changes_the_cluster_context
#   context-caches-not-started                                  -> context-served-from-a-failed-read
# `verify/` is frozen at the plan commit (code-build Step 1.3), so gate.sh still names the retired
# ids. This runs a copy of it with exactly those two names rewritten, and fails if either is no
# longer in the frozen gate (the copy would then run something other than the gate).
set -eu
mode=${1:?usage: M1-merge-develop.sh P2|tests|mutants}
gate=spec/ssh-reconnect-loop/verify/gate.sh
OLD_ROW=test_a_reconnect_failure_is_never_cached_as_cluster_context
NEW_ROW=test_a_reconnect_failure_never_changes_the_cluster_context
OLD_CASE=context-caches-not-started
NEW_CASE=context-served-from-a-failed-read

grep -q "::$OLD_ROW\"\$" "$gate" || { echo "M1: $OLD_ROW is not in $gate" >&2; exit 1; }
grep -q "^$OLD_CASE\"\$" "$gate" || { echo "M1: $OLD_CASE is not in $gate" >&2; exit 1; }

copy=$(mktemp "${TMPDIR:-/tmp}/gate.XXXXXX")
trap 'rm -f "$copy"' EXIT
sed -e "s/::$OLD_ROW\"\$/::$NEW_ROW\"/" -e "s/^$OLD_CASE\"\$/$NEW_CASE\"/" "$gate" > "$copy"

# Exactly the two lines changed, and the retired names are gone from the copy.
changed=$(diff "$gate" "$copy" | grep -c '^>' || true)
[ "$changed" -eq 2 ] || { echo "M1: the copy differs from $gate in $changed lines, not 2" >&2; exit 1; }
if grep -q "$OLD_ROW\|$OLD_CASE" "$copy"; then echo "M1: a retired name survived the rewrite" >&2; exit 1; fi

sh "$copy" "$mode"
echo "M1-merge-develop $mode: green" >&2
