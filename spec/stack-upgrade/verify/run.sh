#!/bin/sh
# The body of gate.sh; it expects to run inside bin/sandbox.sh (CLUSTER_MCP_SANDBOX set) with
# GATE_BASE and BASELINE exported by gate.sh. Every report goes to stderr. The --audit mode prints
# uv's advisory report: that output belongs in the private build log only, never in a commit body,
# a PR body or a file under spec/.
set -eu
test -n "${CLUSTER_MCP_SANDBOX:-}" || { echo 'run.sh: run it through gate.sh (inside bin/sandbox.sh)' >&2; exit 2; }
test -n "${GATE_BASE:-}" && test -n "${BASELINE:-}" || { echo 'run.sh: GATE_BASE/BASELINE unset; run it through gate.sh' >&2; exit 2; }
cd "$CLUSTER_MCP_REPO"
V=spec/stack-upgrade/verify
phase=${1:?usage: gate.sh P<n> [--audit <planted-dir>|--phase-only]}
mode=${2:-}
n=${phase#P}
case $n in [1-7]) ;; *) echo "gate: unknown phase $phase" >&2; exit 2 ;; esac
unset CLUSTER_MCP_TEST_ERA CLUSTER_MCP_ERA_LOG
# The fewest in-process connects a suite pass and a mutation pass must log (era_log.py), set from the
# counts P1 measured (a suite pass logs 81 connects, a mutation pass 53 to 55, rounded down); raise
# them as phases add connects, never lower them.
SUITE_CONNECTS=80
MUTANT_CONNECTS=50

fail() { echo "gate[$phase]: $*" >&2; exit 1; }

# The baseline tree in its own locked environment (FastMCP 2.x): its collected ids, its mutation
# case ids, and (from P3) its served surface. A plain subshell, never one on the left of || or &&:
# there, sh ignores set -e inside it.
baseline() {
    b="$HOME/baseline"
    mkdir -p "$b"
    git archive "$BASELINE" | tar -x -C "$b"
    (
        set -eu
        cd "$b"
        unset VIRTUAL_ENV
        UV_PROJECT=$PWD
        export UV_PROJECT
        uv sync --locked -q
        uv run pytest --collect-only -q -p no:cacheprovider 2> /dev/null | grep '::' > "$HOME/baseline-ids.txt"
        uv run python -c "import sys; sys.path.insert(0, 'tests'); import mutants; print(*(c.id for c in mutants.CASES), sep='\n')" > "$HOME/baseline-cases.txt"
        if [ "$n" -ge 3 ]; then
            uv run python "$CLUSTER_MCP_REPO/$V/snapshot.py" "$HOME/baseline-surface.json"
        fi
    )
    count=$(wc -l < "$HOME/baseline-ids.txt" | tr -d ' ')
    test "$count" -eq 296 || fail "the baseline collected $count ids, expected the 296 collected at 3d010ec"
}

# P7's document checks: AGENTS.md says what is now true, and the deferral ledger is complete.
p7_checks() {
    grep -n -E 'FastMCP 2\.x|fastmcp\.tools\.tool\.FunctionTool|only parses because of PEP 563|get_tools\(\)' AGENTS.md >&2 \
        && fail 'AGENTS.md still describes the 2.x stack (lines above)'
    project=$(awk '/^## Project/ { f = 1; next } /^## / { f = 0 } f' AGENTS.md)
    for m in 'FastMCP 4' 'MCP SDK 2' '2026-07-28' 'stdio' 'sse' 'http'; do
        printf '%s\n' "$project" | grep -q -F "$m" || fail "AGENTS.md § Project does not name $m"
    done
    testing=$(awk '/^## Testing/ { f = 1; next } /^## / { f = 0 } f' AGENTS.md)
    for m in test_protocol.py test_surface.py test_transports.py test_auth_modes.py test_audit.py \
             CLUSTER_MCP_TEST_ERA httpx2 mcp_types importorskip served_surface.json; do
        printf '%s\n' "$testing" | grep -q -F "$m" || fail "AGENTS.md § Testing does not name $m"
    done
    grep -q -F 'uv run python bin/audit_lock.py' AGENTS.md || fail 'the release recipe gate does not run bin/audit_lock.py'
    grep -E '^\| verify \|' AGENTS.md | grep -q -i audit && fail "the profile's verify runs the audit"
    git show "$BASELINE:AGENTS.md" | awk '/^### High-blast-radius paths/ { f = 1; next } /^#### / { f = 0 } f && /^- /' > "$HOME/hbr-base"
    awk '/^### High-blast-radius paths/ { f = 1; next } /^#### / { f = 0 } f && /^- /' AGENTS.md > "$HOME/hbr-head"
    while IFS= read -r line; do
        grep -q -x -F -- "$line" "$HOME/hbr-head" || fail "the high-blast-radius list lost: $line"
    done < "$HOME/hbr-base"
    # While no workflow exists, no live file claims one runs (spec/, issues/ and ROADMAP.md are
    # point-in-time records; CLAUDE.md is AGENTS.md).
    if [ ! -d .github/workflows ]; then
        git ls-files | grep -v -E '^(spec/|issues/|ROADMAP\.md$|CLAUDE\.md$)' \
            | xargs grep -n -I -i -E 'CI workflow (runs|mirrors)|mirrors CI|(runs|run|step) in CI\b|\bCI (runs|mirrors|checks)' >&2 \
            && fail 'a file claims a CI workflow runs, and none exists (lines above)'
    fi
    # The OIDC client-registration store change is recorded with the other accepted 4.x changes.
    printf '%s\n' "$project" | grep -q -F FileTreeStore || fail 'AGENTS.md § Project does not record the OIDC store change'
    awk '/^### 6\./ { f = 1; next } /^### / { f = 0 } f' AGENTS.md | grep -q -F FileTreeStore \
        || fail 'AGENTS.md §6 does not record the OIDC store change'
    awk '/^### OIDC Configuration/ { f = 1; next } /^#+ / { f = 0 } f' SECURITY.md | grep -q -F FileTreeStore \
        || fail "SECURITY.md's OIDC subsection does not record the OIDC store change"
    # The stack-upgrade roadmap entry carries the dated correction of where the audit lives.
    awk '/^## Move the stack before building on it/ { f = 1; next } /^## / { f = 0 } f' ROADMAP.md \
        | grep -q -F '*Corrected 2026-10-17: the dependency audit' || fail "ROADMAP.md's stack-upgrade entry lacks its 2026-10-17 correction"
    test -f issues/resource-reads-without-executor.md || fail 'the resource-read deferral has no issues/ seed'
    for f in $(grep -o -E 'issues/[a-z0-9-]+\.md' spec/stack-upgrade/TECH.md | sort -u); do
        test -f "$f" || fail "$f is named in TECH.md but does not exist"
        grep -q -F "$f" ROADMAP.md || fail "$f has no ROADMAP.md entry"
    done
}

# 1. Scope: only this cycle's paths change, bin/sandbox.sh is untouched, and no comment in src/ or
#    tests/ carries a feature-scoped spec id.
changed=$( { git diff --name-only "$GATE_BASE" HEAD; git status --porcelain --untracked-files=all | cut -c4-; } | sort -u)
if printf '%s\n' "$changed" | grep -v -E '^(src/rcac_mcp/|tests/|spec/stack-upgrade/|pyproject\.toml$|uv\.lock$|AGENTS\.md$|README\.md$|SECURITY\.md$|issues/|ROADMAP\.md$|bin/audit_lock\.py$|\.github/workflows/ci\.yml$|$)' >&2; then
    fail 'paths outside the cycle changed (listed above)'
fi
git diff --quiet "$GATE_BASE" -- bin/sandbox.sh || fail 'bin/sandbox.sh changed'
if grep -rnI -E '#.*\b[RP][0-9]+\b' src tests --include='*.py' | grep -v -E '#[[:space:]]*noqa:' >&2; then
    fail 'feature-scoped spec ids in comments under src/ or tests/'
fi

if [ "$mode" = --phase-only ]; then
    test "$n" = 7 || fail '--phase-only is P7 only'
    p7_checks
    echo "gate[$phase]: phase-only checks passed" >&2
    exit 0
fi

# 2. R1: the pin, the resolved majors, the lock and the environment.
uv run python - <<'EOF' || fail 'R1: pyproject.toml or uv.lock does not hold the new stack'
import sys, tomllib
deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']
pins = [d.replace(' ', '') for d in deps if d.replace(' ', '').startswith('fastmcp')]
lock = {p['name']: p['version'] for p in tomllib.load(open('uv.lock', 'rb'))['package'] if 'version' in p}
problems = []
if pins != ['fastmcp>=4,<5']:
    problems.append(f'pyproject pins {pins}, expected fastmcp>=4,<5')
if not lock.get('fastmcp', '').startswith('4.'):
    problems.append(f"uv.lock resolves fastmcp {lock.get('fastmcp')}")
if not lock.get('mcp', '').startswith('2.'):
    problems.append(f"uv.lock resolves mcp {lock.get('mcp')}")
if 'httpx' in lock:
    problems.append('uv.lock still pins httpx; the stack client is httpx2')
for p in problems:
    print(p, file=sys.stderr)
sys.exit(1 if problems else 0)
EOF
uv lock --check || fail 'uv lock --check'
uv sync --locked -q || fail 'uv sync --locked'

if [ "$mode" = --audit ]; then
    test "$n" -ge 6 || fail '--audit is P6 and later'
    # R10's networked proofs. Green on the shipped lock.
    uv run python bin/audit_lock.py || fail 'the audit is red on the shipped lock'
    # Red, naming package, version and advisory, on a planted lock: a directory outside the repo,
    # prepared by build, holding a pyproject.toml and a uv.lock that pins a version with a published
    # advisory. Which version and advisory is recorded in the private build log, never here.
    src=${3:?usage: gate.sh P<n> --audit <planted-dir with pyproject.toml and uv.lock>}
    test -f "$src/pyproject.toml" && test -f "$src/uv.lock" || fail "$src lacks pyproject.toml or uv.lock"
    p="$HOME/planted"
    mkdir -p "$p/bin"
    cp "$src/pyproject.toml" "$src/uv.lock" "$p/"
    test ! -f "$src/README.md" || cp "$src/README.md" "$p/"
    cp bin/audit_lock.py "$p/bin/audit_lock.py"
    s=0
    (cd "$p" && uv run --no-project python bin/audit_lock.py) > "$HOME/planted.out" 2> "$HOME/planted.err" || s=$?
    cat "$HOME/planted.out" "$HOME/planted.err" >&2
    test "$s" -eq 1 || fail "the planted lock exited $s, expected 1"
    grep -q -E '^[A-Za-z0-9_.-]+ [0-9][^ ]* has [0-9]+ known vulnerabilit' "$HOME/planted.out" || fail 'the planted report names no package and version'
    grep -q -E '^- [A-Z]+-[0-9A-Za-z-]+:' "$HOME/planted.out" || fail 'the planted report names no advisory'
    # Red when the advisory source cannot be reached.
    s=0
    UV_OFFLINE=1 HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
        uv run python bin/audit_lock.py > /dev/null 2> "$HOME/offline.err" || s=$?
    test "$s" -eq 2 || fail "the audit exited $s with the network cut, expected 2"
    grep -q 'advisory source unreachable' "$HOME/offline.err" || fail 'the offline refusal does not say the source is unreachable'
    # The planted proof again with UV_PROJECT naming the shipped tree: the audit must still read the
    # planted lock, because it names its own checkout with --project.
    s=0
    (cd "$p" && UV_PROJECT="$CLUSTER_MCP_REPO" uv run --no-project python bin/audit_lock.py) > /dev/null 2>&1 || s=$?
    test "$s" -eq 1 || fail "with UV_PROJECT elsewhere the planted lock exited $s, expected 1"
    echo "gate[$phase]: audit proofs passed (green on the shipped lock, red on the planted lock and offline)" >&2
    exit 0
fi

baseline

# 3. Marker witness without the conftest, so no conftest can add markers to pass it.
s=0
uv run pytest -q -p no:cacheprovider --noconftest --collect-only -m 'not unit and not integration' > /dev/null 2>&1 || s=$?
test "$s" -eq 5 || fail "marker witness: expected exit 5, got $s"

# 4. The whole suite in each protocol era: green, and (from the JUnit report) every id collected at
#    3d010ec and every id phases 1..n require passed, and nothing was skipped, failed or errored.
# The default pass sets no selector: the profile's verify runs it that way, and it must be the
# handshake era (test_protocol.py pins the default).
# Each pass logs every in-process connect (era_log.py), so a selector the harness ignored, or a
# client pinned to a version that sends no server/discover, fails here even when every test passed.
for era in default modern; do
    s=0
    log="$HOME/era-$era.log"
    if [ "$era" = default ]; then
        CLUSTER_MCP_ERA_LOG=$log uv run pytest -q -rA -p no:cacheprovider --junitxml="$HOME/suite-$era.xml" > "$HOME/suite-$era.txt" 2>&1 || s=$?
        expect=legacy
    else
        CLUSTER_MCP_ERA_LOG=$log CLUSTER_MCP_TEST_ERA=$era uv run pytest -q -rA -p no:cacheprovider --junitxml="$HOME/suite-$era.xml" > "$HOME/suite-$era.txt" 2>&1 || s=$?
        expect=$era
    fi
    tail -n 5 "$HOME/suite-$era.txt" >&2
    test "$s" -eq 0 || { cat "$HOME/suite-$era.txt" >&2; fail "suite ($era era) exited $s"; }
    uv run python "$V/ids_check.py" "$HOME/suite-$era.xml" "$HOME/baseline-ids.txt" "$n" || fail "required test ids ($era era)"
    uv run python "$V/era_log.py" "$log" "$expect" "$SUITE_CONNECTS" || fail "the $era pass did not run in the $expect era"
done
# An unknown selector must stop the run, naming the variable, rather than fall back to an era.
s=0
CLUSTER_MCP_TEST_ERA=bogus uv run pytest -q -p no:cacheprovider tests/test_protocol.py > "$HOME/bogus.txt" 2>&1 || s=$?
test "$s" -ne 0 && grep -q CLUSTER_MCP_TEST_ERA "$HOME/bogus.txt" || fail 'an unknown CLUSTER_MCP_TEST_ERA did not stop the run'

# 5. R8's edit rule, and the gate's own controls and case table.
uv run python "$V/edits.py" "$GATE_BASE" || fail 'R8: an existing test outside the internals-bound list was edited'
uv run python "$V/controls.py" "$n" "$HOME/baseline-cases.txt" || fail 'gate-level controls'

# 6. Planted violations: every case in tests/mutants.py, the 53 from 3d010ec included, killed by each
#    named target for its stated reason, with the runner's own controls; in the handshake era every
#    phase, and in the modern era too at P1 and P7. The report is the build record: paste it into
#    the phase commit body.
cases=$(uv run python -c "import sys; sys.path.insert(0, 'tests'); import mutants; print(*(c.id for c in mutants.CASES))")
s=0
CLUSTER_MCP_ERA_LOG="$HOME/era-mutants.log" uv run python tests/mutants.py --self-check $cases > "$HOME/mutants.txt" 2>&1 || s=$?
cat "$HOME/mutants.txt" >&2
test "$s" -eq 0 || fail 'a planted violation survived or was killed for the wrong reason'
uv run python "$V/era_log.py" "$HOME/era-mutants.log" legacy "$MUTANT_CONNECTS" || fail 'the mutation pass did not run in the legacy era'
if [ "$n" = 1 ] || [ "$n" = 7 ]; then
    s=0
    CLUSTER_MCP_ERA_LOG="$HOME/era-mutants-modern.log" CLUSTER_MCP_TEST_ERA=modern uv run python tests/mutants.py $cases > "$HOME/mutants-modern.txt" 2>&1 || s=$?
    cat "$HOME/mutants-modern.txt" >&2
    test "$s" -eq 0 || fail 'a planted violation survived in the modern era'
    uv run python "$V/era_log.py" "$HOME/era-mutants-modern.log" modern "$MUTANT_CONNECTS" || fail 'the modern mutation pass did not run in the modern era'
fi

# 7. Direct drives (already inside the sandbox).
uv run rcac-mcp --help > "$HOME/help.txt" || fail 'rcac-mcp --help'
for t in stdio sse http; do grep -q -E "^ +$t " "$HOME/help.txt" || fail "--help does not list the $t transport"; done
s=0
uv run rcac-mcp -t stdio -a none < /dev/null > /dev/null 2> "$HOME/ssh.err" || s=$?
test "$s" -eq 2 && grep -q 'SSH host required' "$HOME/ssh.err" || fail "a bare stdio server did not fail closed on ssh (exit $s)"
if [ "$n" -ge 3 ]; then
    uv run python -c "import json, sys; a, b = (json.load(open(p)) for p in sys.argv[1:]); sys.exit(0 if a == b else 1)" \
        "$HOME/baseline-surface.json" tests/fixtures/served_surface.json \
        || fail 'R3: tests/fixtures/served_surface.json is not the surface 3d010ec serves'
fi
if [ "$n" -ge 5 ]; then
    s=0
    JWT_SECRET=$(printf '%031d' 0) uv run rcac-mcp --generate-token > "$HOME/tok" 2> "$HOME/tok.err" || s=$?
    test "$s" -eq 2 && test ! -s "$HOME/tok" && grep -q JWT_SECRET "$HOME/tok.err" || fail 'a 31-character secret was not refused'
    JWT_SECRET=$(printf '%032d' 0) uv run rcac-mcp --generate-token --sub gate-user > "$HOME/tok" || fail 'a 32-character secret was refused'
    uv run python -c "import jwt, sys; c = jwt.decode(open(sys.argv[1]).read().strip(), '0' * 32, algorithms=['HS256'], audience='rcac-mcp', issuer='rcac-mcp'); assert c['sub'] == 'gate-user', c" "$HOME/tok" \
        || fail 'the minted token does not decode with the shared constants'
    s=0
    OIDC_CONFIG_URL=https://idp.invalid/.well-known/openid-configuration OIDC_CLIENT_ID=x MCP_BASE_URL=https://mcp.invalid \
        uv run rcac-mcp -e local -t http -a oidc < /dev/null > /dev/null 2> "$HOME/oidc.err" || s=$?
    test "$s" -eq 2 || fail "oidc without OIDC_CLIENT_SECRET exited $s, expected 2"
    for v in OIDC_CONFIG_URL OIDC_CLIENT_ID OIDC_CLIENT_SECRET MCP_BASE_URL; do
        grep -q "$v" "$HOME/oidc.err" || fail "the oidc refusal does not name $v"
    done
fi
if [ "$n" -ge 6 ]; then
    test -f bin/audit_lock.py || fail 'bin/audit_lock.py is missing'
    grep -q -F -- '- uv run python bin/audit_lock.py' AGENTS.md || fail "the release recipe's gate does not run the audit"
    grep -E '^\| verify \|' AGENTS.md | grep -q -i audit && fail "the profile's verify runs the audit"
    if [ -f .github/workflows/ci.yml ]; then
        grep -q -E '^ *- run: uv run python bin/audit_lock.py$' .github/workflows/ci.yml || fail 'ci.yml does not run the audit step'
    fi
    # Offline by construction: uv is told it is offline and every proxy is a dead loopback port, so a
    # request it attempted anyway would fail differently; uv's own offline refusal must be the cause.
    s=0
    UV_OFFLINE=1 HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
        uv run python bin/audit_lock.py > /dev/null 2> "$HOME/offline.err" || s=$?
    test "$s" -eq 2 && grep -q 'advisory source unreachable' "$HOME/offline.err" \
        && grep -q 'requires network access and cannot be performed in offline mode' "$HOME/offline.err" \
        || fail "the audit does not fail closed offline (exit $s)"
fi

if [ "$n" = 7 ]; then
    p7_checks
    # 8. R9's record: a base case whose targets or reason changed is named in some branch commit body.
    uv run python - "$HOME/baseline/tests" <<'EOF' > "$HOME/retargeted.txt" || fail 'could not compare the case table with 3d010ec'
import importlib.util, sys
# Each copy is registered under its own name while it executes: its dataclass, under postponed
# annotations, resolves them through sys.modules, and fails on an unregistered module.
def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    sys.path.insert(0, str(path.rsplit('/', 1)[0])); spec.loader.exec_module(m); sys.path.pop(0); return m
base = {c.id: c for c in load(sys.argv[1] + '/mutants.py', 'baseline_mutants').CASES}
head = {c.id: c for c in load('tests/mutants.py', 'head_mutants').CASES}
missing = sorted(set(base) - set(head))
if missing:
    sys.exit(f'base cases missing from tests/mutants.py: {missing}')
for cid, c in base.items():
    h = head.get(cid)
    if h is not None and (h.file, h.edits, h.targets, h.why) != (c.file, c.edits, c.targets, c.why):
        print(cid)
EOF
    while IFS= read -r cid; do
        git log "$GATE_BASE"..HEAD --format=%B | grep -q -F "$cid" || fail "case $cid was changed with no reason in a commit body"
    done < "$HOME/retargeted.txt"
    # Every package whose major version moved in uv.lock is named, with its reason, in a commit body.
    git show "$BASELINE:uv.lock" > "$HOME/baseline.lock"
    uv run python - "$HOME/baseline.lock" uv.lock <<'PYEOF' > "$HOME/majors.txt" || fail 'could not compare the locks'
import sys, tomllib
def majors(path):
    out = {}
    for p in tomllib.load(open(path, 'rb'))['package']:
        if 'version' in p and 'registry' in p.get('source', {}):
            out.setdefault(p['name'], set()).add(p['version'].split('.')[0])
    return out
base, head = majors(sys.argv[1]), majors(sys.argv[2])
for name in sorted(set(base) & set(head)):
    if base[name] != head[name]:
        print(name)
PYEOF
    while IFS= read -r pkg; do
        git log "$GATE_BASE"..HEAD --format=%B | grep -q -w -F "$pkg" || fail "uv.lock moved $pkg to a new major with no reason in a commit body"
    done < "$HOME/majors.txt"

    # 9. Committed state: a fresh clone of the branch, its own environment and import origin, the
    #    suite in both eras with every id and its era log, and every planted violation killed
    #    again in both eras, each mutation pass era-logged.
    c="$HOME/clone"
    git clone -q "$CLUSTER_MCP_REPO" "$c"
    echo "gate[$phase]: checking the fresh clone at $c" >&2
    (
        set -eu
        cd "$c"
        unset VIRTUAL_ENV
        UV_PROJECT=$PWD
        export UV_PROJECT
        uv sync --locked -q
        uv lock --check
        uv run python -c "import os, rcac_mcp; assert os.path.realpath(rcac_mcp.__file__).startswith(os.path.realpath(os.getcwd()) + os.sep), rcac_mcp.__file__"
        for era in legacy modern; do
            s=0
            CLUSTER_MCP_ERA_LOG="$HOME/clone-era-$era.log" CLUSTER_MCP_TEST_ERA=$era uv run pytest -q -rA -p no:cacheprovider --junitxml="$HOME/clone-$era.xml" > "$HOME/clone-$era.txt" 2>&1 || s=$?
            tail -n 5 "$HOME/clone-$era.txt" >&2
            test "$s" -eq 0 || { cat "$HOME/clone-$era.txt" >&2; fail "clone: suite ($era era) exited $s"; }
            uv run python "$V/ids_check.py" "$HOME/clone-$era.xml" "$HOME/baseline-ids.txt" 7 || fail "clone: required test ids ($era era)"
            uv run python "$V/era_log.py" "$HOME/clone-era-$era.log" "$era" "$SUITE_CONNECTS" || fail "clone: the $era pass did not run in the $era era"
            s=0
            if [ "$era" = legacy ]; then
                CLUSTER_MCP_ERA_LOG="$HOME/clone-era-mutants-$era.log" CLUSTER_MCP_TEST_ERA=$era uv run python tests/mutants.py --self-check $cases > "$HOME/clone-mutants-$era.txt" 2>&1 || s=$?
            else
                CLUSTER_MCP_ERA_LOG="$HOME/clone-era-mutants-$era.log" CLUSTER_MCP_TEST_ERA=$era uv run python tests/mutants.py $cases > "$HOME/clone-mutants-$era.txt" 2>&1 || s=$?
            fi
            cat "$HOME/clone-mutants-$era.txt" >&2
            test "$s" -eq 0 || fail "clone: a planted violation survived ($era era)"
            uv run python "$V/era_log.py" "$HOME/clone-era-mutants-$era.log" "$era" "$MUTANT_CONNECTS" || fail "clone: the $era mutation pass did not run in the $era era"
        done
    )
fi

echo "gate[$phase]: passed" >&2
