#!/bin/sh
# Review cycle 1, F1's class: the served sbatch description states every name the code can give a
# job script, the fallback for a job name that is missing, empty or sanitised to nothing included.
# Runs after the frozen P2 gate (verify/ is frozen at the plan commit), from the worktree root:
#
#   sh spec/sbatch-script-name-collision/remediation/F1-job-fallback.sh
#
# Offline and deterministic, like the frozen gate: UV_OFFLINE is set, the predicate imports the
# package from this tree and reads the fixture, and every pytest and mutant child runs inside
# bin/sandbox.sh. One child at a time; the temporary directory is removed on every path.
set -eu
export UV_OFFLINE=1
set -f
cd "$(git rev-parse --show-toplevel)"
fail() { echo "F1-job-fallback: $*" >&2; exit 1; }

# The predicate, evaluated: draw the stem the code gives each input that sanitises to nothing, and
# require the served description (the fixture, which test_surface holds to the server) to name
# that stem as the empty-name case, within this cycle's 2,000-character cap.
uv run -q python - <<'PY' || fail 'the served description does not state the fallback name the code gives'
import json, re, sys
from pathlib import Path
sys.path.insert(0, 'src')
import rcac_mcp.tools.slurm as slurm

served = json.loads(Path('tests/fixtures/served_surface.json').read_text())['tools']['sbatch']['description']
text = ' '.join(served.split())
found = []
stems = set()
for job_name in (None, '', '...', '-', '.-.'):
    name = str(slurm._job_script_path(job_name)).removeprefix('~/jobs/')
    stem = re.fullmatch(r'(.*)_\d{8}_\d{6}_[0-9a-f]{16}\.sh', name)
    if stem is None:
        found.append(f'{job_name!r}: {name!r} is not <name>_<YYYYmmdd_HHMMSS>_<token>.sh')
    else:
        stems.add(stem.group(1))
if len(stems) != 1:
    found.append(f'inputs that sanitise to nothing give more than one name: {sorted(stems)}')
stated = re.search(r"<name>: [^;)]*?'([^']+)' if empty", text)
if stated is None:
    found.append('the served sbatch description states no <name> for an empty job_name')
elif stems and stems != {stated.group(1)}:
    found.append(f'the description states {stated.group(1)!r}, the code gives {sorted(stems)}')
if len(served) > 2000:
    found.append(f'the served sbatch description is {len(served)} characters, over 2,000')
for line in found:
    print(f'F1-job-fallback: {line}', file=sys.stderr)
sys.exit(1 if found else 0)
PY

# The docstring test pins the fallback in both eras, and its mutant's anchor still applies.
tmp=$(mktemp -d)
for era in legacy modern; do
    bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && CLUSTER_MCP_TEST_ERA=$1 uv run pytest -q -p no:cacheprovider -rs \
        "tests/test_sbatch.py::test_the_docstring_states_the_script_path_the_tool_writes" \
        "tests/test_mutations.py::test_mutation_anchor_applies[script-fallback-renamed]"' sh "$era" >"$tmp/$era.log" 2>&1 ||
        { cat "$tmp/$era.log" >&2; rm -rf "$tmp"; fail "the docstring test is red in the $era era"; }
    grep -q '^2 passed' "$tmp/$era.log" || { cat "$tmp/$era.log" >&2; rm -rf "$tmp"; fail "expected 2 passed in the $era era"; }
done
rm -rf "$tmp"
test ! -e "$tmp" || fail "left $tmp behind"

# Not hollow: a fallback name other than the one the docstring states turns the test red.
uv run -q python tests/mutants.py script-fallback-renamed || fail 'a planted fallback mismatch survived'
echo 'F1-job-fallback: ok'
