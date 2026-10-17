# Planning prototype for restore-test-coverage (2026-10-16), kept as evidence for research/; not a test.
# Run from the worktree root: uv run python spec/restore-test-coverage/research/prototypes/mutation_child.py [args]
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
import rcac_mcp
REPO = Path(sys.argv[1]); pkg = Path(rcac_mcp.__file__).parent
mut = Path(tempfile.mkdtemp()) / 'src'
shutil.copytree(pkg, mut / 'rcac_mcp', ignore=shutil.ignore_patterns('__pycache__'))
f = mut / 'rcac_mcp/tools/__init__.py'; t = f.read_text(); old = 'from rcac_mcp.tools import slurm  # noqa: E402, F401'
assert t.count(old) == 1; f.write_text(t.replace(old, ''))
env = {**os.environ, 'PYTHONPATH': str(mut), 'PYTHONDONTWRITEBYTECODE': '1'}
r = subprocess.run([str(REPO/'bin/sandbox.sh'), 'sh', '-c', '"$1" -c "import rcac_mcp, sys; assert rcac_mcp.__file__.startswith(sys.argv[1]), rcac_mcp.__file__" "$2" && shift 2 && exec "$@"', 'sh', sys.executable, str(mut),
    sys.executable, '-m', 'pytest', '--rootdir', str(REPO), '-c', str(REPO/'pyproject.toml'), '-p', 'no:cacheprovider', '-q', '-rA',
    str(REPO/'tests/test_registry.py') + '::test_registry_matches_expected_tools', str(REPO/'tests/test_registry.py') + '::test_docs_modules_absent'],
    capture_output=True, text=True, env=env)
print(r.returncode); print('\n'.join(l for l in r.stdout.splitlines() if l.startswith(('FAILED', 'PASSED', 'ERROR'))))
print(r.stderr[-300:])
