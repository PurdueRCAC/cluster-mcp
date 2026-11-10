#!/bin/sh
# Review cycle 1, F1: the operating manual names every module in tests/, the disk-image stand-in
# included, as the other helpers are named, with its interface and the unit tests that hold its
# figures and its list of body exits.
#
# The predicate is evaluated over every tests/*.py, not over one name: each module's path appears in
# the manual as `tests/<name>.py`. Then the stand-in's entry says it is a helper that is not
# collected and names its interface (plan.json, devices.json, pids, bin/sandbox.sh) and the two
# unit tests.
#
# Usage, from the cycle worktree root:
#   sh spec/full-volume-fixture-leaks-hdiutil/remediation/F1-every-test-module-named.sh [MANUAL]
# MANUAL defaults to AGENTS.md (another path shows the check red on the reviewed text).
# Footprint: grep over one file; under a second.
set -u
manual=${1:-AGENTS.md}
[ -f "$manual" ] || { echo "F1: no manual at $manual" >&2; exit 1; }
n=0
bad=0
for module in tests/*.py; do
    [ -f "$module" ] || continue
    n=$((n + 1))
    grep -qF "\`$module\`" "$manual" || { echo "F1: $manual does not name \`$module\`" >&2; bad=1; }
done
[ "$n" -gt 40 ] || { echo "F1: only $n modules under tests/ (expected more than 40)" >&2; exit 1; }
entry=$(grep -n -F '`tests/hdiutil_standin.py`' "$manual" | head -1 | cut -d: -f1)
if [ -n "$entry" ]; then
    # The stand-in's entry: from the line naming it, the next 20 lines.
    text=$(sed -n "${entry},$((entry + 20))p" "$manual" | tr '\n' ' ' | tr -s ' ')
    for word in '(a helper, not collected)' '`plan.json`' '`devices.json`' '`pids`' '`bin/sandbox.sh`' \
        '`test_the_disk_image_figures` (`unit`)' '`test_every_way_a_body_can_end_has_its_rows` (`unit`)'; do
        case $text in
            *"$word"*) ;;
            *) echo "F1: the stand-in's entry does not say $word" >&2; bad=1 ;;
        esac
    done
fi
[ "$bad" -eq 0 ] || exit 1
echo "F1: $manual names all $n modules under tests/, and the stand-in's interface and unit tests"
