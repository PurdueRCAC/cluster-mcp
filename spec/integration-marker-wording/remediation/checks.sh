#!/bin/sh
# The class checkers for integration-marker-wording, run after the frozen gate (verify/gate.sh) by
# each reopened phase's verify. From the worktree root, after staging:
#
#   sh spec/integration-marker-wording/remediation/checks.sh F1 F4 F5 F6 F7 F8
#
# Review cycle 1:
# F1: the guard and check wording against an executed probe of tests/conftest.py (F1-guard-wording.py).
# F2: the module-wide mutant sweep of the marker-statement check (F2-marker-check-sweep.py). Superseded
#     by F8, which carries its table: it keyed on lines review cycle 2's F2 rewrote, so it no longer
#     applies and stays as the record.
# F4: the ledger lines' claims about the code and the history (F4-ledger-claims.py).
# Review cycle 2:
# F5 (finding 1): every sentence in AGENTS.md about the markers' tests in general, in pyproject.toml's
#     terms (F5-marker-meaning-sweep.py).
# F6 (finding 2): the statement ends where CommonMark ends the last item (F6-statement-end-commonmark.py).
# F7 (finding 3): the static check's and the guard's gaps, stated as classes and named in the seed,
#     against an executed probe (F7-gap-statements.py).
# F8 (finding 4): the mutant sweep after the whole-domain control (F8-marker-check-sweep.py), about
#     80 s.
# Refuses a tree with unstaged or untracked changes, as the frozen gate does. One child at a time;
# under 200 MB; offline; nothing outlives it.

R=spec/integration-marker-wording/remediation

fail() { echo "checks[$1]: $2" >&2; exit 1; }

main() {
    set -u
    export UV_PYTHON=3.14
    cd "$(git rev-parse --show-toplevel)" || exit 1
    [ "$#" -gt 0 ] || fail usage 'name F1, F2, F4, F5, F6, F7 or F8'
    git diff --quiet && [ -z "$(git ls-files --others --exclude-standard)" ] ||
        fail tree 'unstaged or untracked changes: stage first, so the checks grade what commits'
    for one in "$@"; do
        case $one in
            F1) env XDG_STATE_HOME=/nonexistent/marker-f1/XDG_STATE_HOME \
                    XDG_RUNTIME_DIR=/nonexistent/marker-f1/XDG_RUNTIME_DIR \
                    XDG_CONFIG_DIRS=/nonexistent/marker-f1/XDG_CONFIG_DIRS \
                    XDG_DATA_DIRS=/nonexistent/marker-f1/XDG_DATA_DIRS MARKER_F1_PROBE=1 \
                    PYTHONPATH=tests:spec/integration-marker-wording/verify \
                    uv run --no-sync pytest -q -p no:cacheprovider -p conftest -c pyproject.toml --rootdir=. \
                    "$R/F1-guard-wording.py" || fail F1 'a statement about the guard or a check is not what the code does' ;;
            F2) uv run --no-sync python -I "$R/F2-marker-check-sweep.py" || fail F2 'a mutant of the check survived' ;;
            F4) uv run --no-sync python -I "$R/F4-ledger-claims.py" || fail F4 'a ledger claim does not hold' ;;
            F5) uv run --no-sync python -I "$R/F5-marker-meaning-sweep.py" ||
                    fail F5 'AGENTS.md says what a marker means in other terms than pyproject.toml' ;;
            F6) uv run --no-sync python -I "$R/F6-statement-end-commonmark.py" ||
                    fail F6 'the check passes a line CommonMark renders into the statement' ;;
            F7) env GNUPGHOME=/nonexistent/marker-f7/GNUPGHOME PYTHONPATH=tests \
                    uv run --no-sync pytest -q -p no:cacheprovider -p conftest -c pyproject.toml --rootdir=. \
                    "$R/F7-gap-statements.py" || fail F7 'a gap statement is not true of a probed route' ;;
            F8) uv run --no-sync python -I "$R/F8-marker-check-sweep.py" || fail F8 'a mutant of the check is not accounted for' ;;
            *) fail "$one" 'unknown checker' ;;
        esac
    done
    echo "checks[$*]: ok"
}

main "$@"; exit $?
