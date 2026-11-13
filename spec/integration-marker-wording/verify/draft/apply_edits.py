# Draft: the edits the plan dry-ran on its prototype (a detached worktree), applied as
#   python3 apply_edits.py <tree> check_block.py P1|P2
# P1 = pyproject.toml and AGENTS.md wording; P2 adds the check and its § Testing entry. Build
# makes the real edits; this records the exact text the gates passed on.
import sys
from pathlib import Path
root = Path(sys.argv[1]); block = Path(sys.argv[2]).read_text(); phase = sys.argv[3]
block = ''.join(line for line in block.splitlines(True) if not line.startswith('# Draft') and not (
    block.startswith('# Draft') and block.splitlines(True).index(line) < 4))
UNIT = 'starts no process, opens no network connection (a name lookup included) and sees no real HOME; the unit guard holds it to that'
INTEG = ('needs what a unit test is refused (a process, a network connection or name lookup, or the real HOME), '
         'itself or through a fixture or helper; every process it launches goes through bin/sandbox.sh')
def sub(p, old, new):
    t = p.read_text(); assert t.count(old) == 1, (p, old); p.write_text(t.replace(old, new))
sub(root / 'pyproject.toml', '    "unit: fast and isolated; no subprocess, no network, no real cluster",\n    "integration: drives the installed CLI; run it under bin/sandbox.sh",\n',
    f'    "unit: {UNIT}",\n    "integration: {INTEG}",\n')
STATED = ('  Each marker means what its description in `pyproject.toml` says, word for word:\n'
          '  - `unit`: starts no process, opens no network connection (a name lookup included) and sees no\n'
          '    real HOME; the unit guard holds it to that\n'
          '  - `integration`: needs what a unit test is refused (a process, a network connection or name\n'
          '    lookup, or the real HOME), itself or through a fixture or helper; every process it launches\n'
          '    goes through bin/sandbox.sh\n')
A = root / 'AGENTS.md'
sub(A, '  neither. So `-m unit` and `-m integration` each select a real subset.\n',
    '  neither. So `-m unit` and `-m integration` each select a real subset, and a test that is not `unit`\n'
    '  is `integration`: the unit guard (below) is inactive for it.\n' + STATED + '\n'
    '  `test_the_markers_are_stated_as_pyproject_describes_them` holds this statement and § Conventions\'\n'
    '  to those descriptions (`tests/test_hygiene.py`, below).\n')
sub(A, 'So `test_docs_modules_absent` is `integration` although it drives no CLI, and\n',
    'So `test_docs_modules_absent` is `integration`, and\n')
sub(A, '  nothing, or not the tests you meant, and pass green. Name the test ids the gate depends on.\n',
    '  nothing, or not the tests you meant, and pass green. Name the test ids the gate depends on.\n' + STATED)
sub(A, '                                         #   run on an unmarked test (§ Testing)\n',
    '                                         #   run on an unmarked test; each means what its\n'
    '                                         #   pyproject.toml description says (§ Testing)\n')
sub(A, "# --strict-markers and every registered marker). HOME/auth/SSH isolation is unaffected.\n",
    "# --strict-markers and every registered marker). HOME/auth/SSH isolation is unaffected. Wrapping\n"
    "# the whole run is a choice for a manual run; the rule the suite enforces is per launch: every\n"
    "# process an integration test launches goes through bin/sandbox.sh (§ Testing).\n")
sub(A, '    body, because a refusal inside a tool comes back as a tool error. **File I/O is not guarded:** a\n',
    '    body, because a refusal inside a tool comes back as a tool error. It replaces those names, so\n'
    '    what was bound before the test or sits below them is not refused: a `Popen` class bound earlier\n'
    '    (`conftest.REAL_POPEN`, a `from subprocess import Popen`) still launches; a `_socket` connect, a\n'
    '    UDP `sendto` and an early-bound `getaddrinfo` still reach the network; `socket.gethostbyname`\n'
    '    and its kin still look a name up; and a fixture of wider scope has launched before the guard is\n'
    '    active (`issues/marker-rule-gaps.md`). **File I/O is not guarded:** a\n')
sub(A, '    through `bin/sandbox.sh` and no argv names `sudo` or `ssh` (`test_cli_drives_are_sandboxed`,\n',
    '    through `bin/sandbox.sh` and no argv names `sudo` or `ssh` (`test_cli_drives_are_sandboxed`,\n'
    '    which does not read a call through `conftest.REAL_POPEN`: `tests/test_ssh_exec.py`\'s `_host`\n'
    '    runs `hdiutil` through it, outside the sandbox, `issues/marker-rule-gaps.md`;\n')
if phase == 'P1':
    print('applied P1'); raise SystemExit
sub(A, '    `sandbox_unset_violations`, the suite\'s own rails.', '    `sandbox_unset_violations`, `marker_statement_violations`, the suite\'s own rails.')
sub(A, "    holds this statement and § Conventions' to the check, word for word. A row",
    "    holds this statement and § Conventions' to the check, word for word.\n"
    "    `test_the_markers_are_stated_as_pyproject_describes_them` holds § Testing's and § Conventions'\n"
    "    statement of the markers to the `markers` descriptions in `pyproject.toml` word for word\n"
    "    (`marker_statement_violations`): line wrapping is the only freedom, and case, punctuation,\n"
    "    markup, spacing, order, a missing or third marker and a clause added anywhere all count;\n"
    "    `test_marker_statement_check_catches_planted_drift` plants each. A row")
H = root / 'tests' / 'test_hygiene.py'
sub(H, 'import subprocess\nfrom contextvars', 'import subprocess\nimport tomllib\nfrom contextvars')
t = H.read_text(); anchor = "\n\n# Every name of the SSH-host and user-map variables bin/sandbox.sh must unset"
assert t.count(anchor) == 1; H.write_text(t.replace(anchor, block.rstrip('\n') + anchor))
print('applied')
