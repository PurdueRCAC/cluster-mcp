#!/bin/sh
# Runs a gate (here the frozen verify/p3.sh pre) unchanged, with its scope check admitting the one
# seed review cycle 1 routed: issues/disk-image-fixture-deeper-pins.md and its ROADMAP.md entry.
#
# Why: p3.sh's `scope` grades every path changed since the plan commit against the cycle's own files
# (the fixture's module, the stand-in, AGENTS.md, spec/<slug>/). Review cycle 1 routed the review's
# coverage observations to an issues/ seed with its ROADMAP.md entry, which lie outside that list, so
# the frozen check goes red on a change the review asked for. Seen red first: p3.sh pre with the seed
# staged, every other step green (review cycle 1's remediation, 2026-11-10).
#
# How: before the gate, this script checks the two paths itself: the seed exists with
# `status: unshaped`, ROADMAP.md links it as a seed, and every line ROADMAP.md loses since the plan
# commit is one of the Part I counts the entry moves (the entry count, the gates count, the gates
# list). Then a `git` shim goes first on PATH: exactly p3.sh's two forms, `git diff --name-only REV
# HEAD` and `git diff --cached --name-only REV`, drop those two paths from their answer; every other
# call runs the real git, unchanged. After a green gate the script asserts the shim answered both
# forms and dropped the seed, so the admission is never vacuous.
#
# Usage, from the cycle worktree root:
#   sh spec/full-volume-fixture-leaks-hdiutil/remediation/seed-in-scope.sh CMD...
# Footprint: the gate's own, plus one shell shim. Leaves its directory under $TMPDIR.
set -u
SLUG=full-volume-fixture-leaks-hdiutil
seed=issues/disk-image-fixture-deeper-pins.md
real_git=$(command -v git) || { echo 'seed-in-scope.sh: no git' >&2; exit 1; }
plan=$("$real_git" log --format=%H -1 --grep="Plan $SLUG")
[ -n "$plan" ] || { echo 'seed-in-scope.sh: no plan commit found' >&2; exit 1; }

[ -f "$seed" ] || { echo "seed-in-scope.sh: no $seed" >&2; exit 1; }
grep -qx 'status: unshaped' "$seed" || { echo "seed-in-scope.sh: $seed is not status: unshaped" >&2; exit 1; }
grep -qF "**Seed:** [\`$seed\`]($seed)" ROADMAP.md || { echo "seed-in-scope.sh: ROADMAP.md does not link $seed as a seed" >&2; exit 1; }
lost=$("$real_git" diff "$plan" -- ROADMAP.md | grep '^-' | grep -v '^---')
printf '%s\n' "$lost" | grep -v -e '^$' -e '28 entries' -e 'Twenty-eight entries' -e 'Gates first\*\* (twelve entries)' \
    -e "the test harnesses' leftovers" | grep -q . \
    && { echo 'seed-in-scope.sh: ROADMAP.md loses lines beyond the counts the entry moves:' >&2; printf '%s\n' "$lost" >&2; exit 1; }

work=$(mktemp -d "${TMPDIR:-/tmp}/fvfl-seed.XXXXXX") || exit 1
mkdir -p "$work/shims" && : > "$work/used" || exit 1
cat > "$work/shims/git" <<EOF
#!/bin/sh
if [ "\$#" -eq 4 ] && [ "\$1" = diff ] && [ "\$2" = --name-only ] && [ "\$4" = HEAD ]; then
    form=committed
elif [ "\$#" -eq 4 ] && [ "\$1" = diff ] && [ "\$2" = --cached ] && [ "\$3" = --name-only ]; then
    form=cached
else
    exec '$real_git' "\$@"
fi
out=\$('$real_git' "\$@") || exit \$?
echo "\$form" >> '$work/used'
printf '%s\n' "\$out" | grep -qx '$seed' && echo dropped >> '$work/used'
printf '%s\n' "\$out" | grep -v -x -e '$seed' -e 'ROADMAP.md' -e ''
exit 0
EOF
chmod +x "$work/shims/git"

PATH="$work/shims:$PATH" "$@"
status=$?
[ "$status" -eq 0 ] || exit "$status"
grep -qx committed "$work/used" && grep -qx cached "$work/used" \
    || { echo 'seed-in-scope.sh: the scope check did not read both diffs through the shim' >&2; exit 1; }
grep -qx dropped "$work/used" || { echo "seed-in-scope.sh: the scope check never saw $seed" >&2; exit 1; }
echo "seed-in-scope.sh: $seed and its ROADMAP.md entry admitted; $* ok"
