#!/bin/sh
# The body of gate.sh; it expects to run inside bin/sandbox.sh (CLUSTER_MCP_SANDBOX set) with
# GATE_BASE exported by gate.sh.
set -eu
test -n "${CLUSTER_MCP_SANDBOX:-}" || { echo 'run.sh: run it through gate.sh (inside bin/sandbox.sh)' >&2; exit 2; }
test -n "${GATE_BASE:-}" || { echo 'run.sh: GATE_BASE is unset; run it through gate.sh' >&2; exit 2; }
cd "$CLUSTER_MCP_REPO"
V=spec/restore-test-coverage/verify
phase=${1:?usage: gate.sh P<n> [--phase-only]}
mode=${2:-}
n=${phase#P}
case $n in [1-8]) ;; *) echo "gate: unknown phase $phase" >&2; exit 2 ;; esac
base=$GATE_BASE

fail() { echo "gate[$phase]: $*" >&2; exit 1; }

# P8's own checks: the documentation, the downstream seeds and the deferral ledger.
p8_checks() {
    testing=$(awk '/^## Testing/ { f = 1; next } /^## / { f = 0 } f' AGENTS.md)
    for m in conftest.py harness.py mutants.py test_isolation.py test_hygiene.py test_mutations.py test_tools.py \
             test_no_executor.py test_identity.py test_executors.py test_exec_mode.py test_tokens.py \
             'PATH shim' 'issuer/audience swap'; do
        printf '%s\n' "$testing" | grep -q -F "$m" || fail "AGENTS.md § Testing does not name $m"
    done
    if printf '%s\n' "$testing" | grep -n -E 'no tests yet|The suite is three files'; then
        fail 'AGENTS.md § Testing still describes the pre-cycle suite'
    fi
    grep -q -F 'tests/harness.py' issues/stack-upgrade.md || fail 'issues/stack-upgrade.md lacks the internals-bound note'
    grep -q -F 'tests/test_executors.py' issues/safe-execution.md || fail 'issues/safe-execution.md lacks the argv-test note'
    grep -q -F 'tests/mutants.py' issues/ci-workflow.md || fail 'issues/ci-workflow.md lacks the mutation-runner note'
    for f in $(grep -o -E 'issues/[a-z0-9-]+\.md' spec/restore-test-coverage/TECH.md | sort -u); do
        test -f "$f" || fail "$f is named in TECH.md but does not exist"
        grep -q -F "$f" ROADMAP.md || fail "$f has no ROADMAP.md entry"
    done
}

# 1. Scope: src/ is byte-identical to the base (committed and in the working tree), only this
#    cycle's paths change, and no test carries a feature-scoped spec id (noqa codes aside).
git diff --quiet "$base" -- src || fail "src/ differs from $base"
test -z "$(git status --porcelain --untracked-files=all -- src)" || fail 'src/ has uncommitted or untracked changes'
changed=$( { git diff --name-only "$base" HEAD; git status --porcelain --untracked-files=all | cut -c4-; } | sort -u)
if printf '%s\n' "$changed" | grep -v -E '^(tests/|spec/restore-test-coverage/|AGENTS\.md$|issues/|ROADMAP\.md$|$)' >&2; then
    fail 'paths outside the cycle changed (listed above)'
fi
if grep -rnI -E '\b[RPF][0-9]+\b' tests --include='*.py' | grep -v -E '#[[:space:]]*noqa:' >&2; then
    fail 'feature-scoped spec ids in tests/'
fi

if [ "$n" = 8 ] && [ "$mode" = --phase-only ]; then
    p8_checks
    echo "gate[$phase]: phase-only checks passed" >&2
    exit 0
fi

# 2. Marker witness without the conftest, so no conftest can add markers to pass it.
s=0
uv run pytest -q -p no:cacheprovider --noconftest --collect-only -m 'not unit and not integration' > /dev/null 2>&1 || s=$?
test "$s" -eq 5 || fail "marker witness: expected exit 5, got $s"

# 3. The whole suite: green, and (from the JUnit report, not the terminal) every required id
#    passed and nothing was skipped, failed or errored.
s=0
uv run pytest -q -rA -p no:cacheprovider --junitxml="$HOME/suite.xml" > "$HOME/suite.txt" 2>&1 || s=$?
cat "$HOME/suite.txt" >&2
test "$s" -eq 0 || fail "suite exited $s"
uv run python "$V/ids_check.py" "$HOME/suite.xml" "$n" || fail 'required test ids'

# 4. Gate-level negative controls on the pure check functions and the planted-violation table.
uv run python "$V/controls.py" "$n" || fail 'gate-level controls'

# 5. Planted violations: every case the phases so far own is killed by each named target for its
#    stated reason, and the runner's own controls (a surviving mutant, a wrong import origin) are
#    reported. The report is the build record: paste it into the phase commit body.
cases=$(uv run python "$V/controls.py" --cases "$n")
s=0
uv run python tests/mutants.py --self-check $cases > "$HOME/mutants.txt" 2>&1 || s=$?
cat "$HOME/mutants.txt" >&2
test "$s" -eq 0 || fail 'a planted violation survived or was killed for the wrong reason'

# 6. Direct CLI drives (already inside the sandbox).
if [ "$n" -ge 6 ]; then
    s=0
    uv run rcac-mcp -t stdio -a jwt < /dev/null > "$HOME/ladder.out" 2> "$HOME/ladder.err" || s=$?
    test "$s" -eq 2 || fail "stdio with jwt exited $s, expected 2 (ssh, failing closed)"
    grep -q 'Execution mode: ssh' "$HOME/ladder.err" || fail 'stdio with jwt did not resolve to ssh'
    grep -q 'SSH host required' "$HOME/ladder.err" || fail 'stdio with jwt did not fail closed'
fi
if [ "$n" -ge 7 ]; then
    s=0
    JWT_SECRET=$(printf '%031d' 0) uv run rcac-mcp --generate-token > "$HOME/tok" 2> "$HOME/tok.err" || s=$?
    test "$s" -eq 2 || fail "a 31-character secret exited $s, expected 2"
    test ! -s "$HOME/tok" || fail 'a 31-character secret printed a token'
    grep -q JWT_SECRET "$HOME/tok.err" || fail 'the refusal does not name JWT_SECRET'
    JWT_SECRET=$(printf '%032d' 0) uv run rcac-mcp --generate-token --sub gate-user > "$HOME/tok" || fail 'a 32-character secret was refused'
    uv run python -c "import jwt, sys; c = jwt.decode(open(sys.argv[1]).read().strip(), '0' * 32, algorithms=['HS256'], audience='rcac-mcp', issuer='rcac-mcp'); assert c['sub'] == 'gate-user', c" "$HOME/tok" \
        || fail 'the minted token does not decode with the shared constants'
fi

if [ "$n" = 8 ]; then
    # 7. The profile's full verify (already inside the sandbox, so --help runs sandboxed).
    uv lock --check || fail 'uv lock --check'
    uv run rcac-mcp --help > /dev/null || fail 'rcac-mcp --help'
    p8_checks

    # 8. Committed state: a fresh clone of the branch, its own environment and import origin, the
    #    suite with every id, and every planted violation killed again.
    c="$HOME/clone"
    git clone -q "$CLUSTER_MCP_REPO" "$c"
    echo "gate[$phase]: checking the fresh clone at $c" >&2
    # A plain subshell, never one on the left of || or &&: there, sh ignores set -e inside it.
    (
        set -eu
        cd "$c"
        unset VIRTUAL_ENV
        UV_PROJECT=$PWD
        export UV_PROJECT
        git diff --quiet "$base" -- src
        uv sync --locked -q
        uv lock --check
        uv run python -c "import os, rcac_mcp; assert os.path.realpath(rcac_mcp.__file__).startswith(os.path.realpath(os.getcwd()) + os.sep), rcac_mcp.__file__"
        s=0
        uv run pytest -q -rA -p no:cacheprovider --junitxml="$HOME/clone.xml" > "$HOME/clone.txt" 2>&1 || s=$?
        cat "$HOME/clone.txt" >&2
        test "$s" -eq 0
        uv run python "$V/ids_check.py" "$HOME/clone.xml" 8
        s=0
        uv run python tests/mutants.py --self-check $cases > "$HOME/clone-mutants.txt" 2>&1 || s=$?
        cat "$HOME/clone-mutants.txt" >&2
        test "$s" -eq 0
    )
fi

echo "gate[$phase]: passed" >&2
