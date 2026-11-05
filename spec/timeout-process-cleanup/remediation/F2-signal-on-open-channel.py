"""Review cycle 1, F2: no `signal` request goes on a channel the client has closed or begun to close.

    uv run python -I spec/timeout-process-cleanup/remediation/F2-signal-on-open-channel.py      from the worktree root

The property, evaluated on every request the suite's `ssh` rows make rather than read from the code:
a pytest plugin wraps Paramiko's `Transport._send_message` for the run, and for each `signal`
channel request a client transport writes, records the name and the channel's state at that moment
(closed or not, its lock held or not; a channel already unlinked from the transport counts as
closed). It also counts every message the loopback server receives for a channel it has freed
(`ssh_server._Forgotten`), each of which drops the connection, as sshd does. The rows are
`tests/test_ssh_exec.py` whole and `tests/test_timeout_stop.py`'s `ssh` rows with every login shell
(`CLUSTER_MCP_TEST_EVERY_KIND=1`, which this checker sets and asserts it collected). Green when:

- every row passed;
- no request was written on a closed channel, and each was written holding the channel's lock;
- no server dropped a connection for a message on a freed channel;
- it is not vacuous: at least one TERM and one KILL request were written (the KILL on a channel open
  after the grace), and in every login shell the `tree` stop row, whose command dies at the TERM so
  that its channel ends during the grace, asked for TERM alone.

Footprint: one pytest child at a time (each row a sandbox, a login shell, a few `sleep`s and one
in-process server), under 500 MB, about 3 minutes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SHELLS = ('bash', 'zsh', 'sh', 'tcsh')

PLUGIN = '''
import json, os
import paramiko
from paramiko.common import cMSG_CHANNEL_REQUEST
import ssh_server

RECORD = {"requests": [], "freed": 0}
_send = paramiko.Transport._send_message
_seen = ssh_server._Forgotten.__contains__


def _watched(self, data):
    try:
        m = paramiko.Message(data.asbytes())
        if not self.server_mode and m.get_byte() == cMSG_CHANNEL_REQUEST:
            remote = m.get_int()
            if m.get_text() == "signal":
                m.get_boolean()
                name = m.get_text()
                chan = next((c for c in self._channels.values() if c.remote_chanid == remote), None)
                RECORD["requests"].append({"name": name, "test": os.environ.get("PYTEST_CURRENT_TEST", ""),
                                           "closed": chan is None or chan.closed,
                                           "locked": chan is not None and chan.lock.locked()})
    except Exception as exc:
        RECORD["requests"].append({"name": "?", "error": repr(exc)})
    return _send(self, data)


def _freed(self, key):
    RECORD["freed"] += 1
    return _seen(self, key)


def pytest_configure(config):
    paramiko.Transport._send_message = _watched
    ssh_server._Forgotten.__contains__ = _freed


def pytest_sessionfinish(session, exitstatus):
    with open(os.environ["F2_RECORD"], "w") as handle:
        json.dump(RECORD, handle)
'''


def main() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix='tpc-f2-') as scratch:
        Path(scratch, 'f2_plugin.py').write_text(PLUGIN)
        record, report = Path(scratch, 'record.json'), Path(scratch, 'junit.xml')
        env = dict(os.environ, CLUSTER_MCP_TEST_EVERY_KIND='1', F2_RECORD=str(record),
                   PYTHONPATH=os.pathsep.join([scratch, str(Path('tests').resolve())]))
        code = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-p', 'f2_plugin',
                               f'--junitxml={report}', 'tests/test_ssh_exec.py', 'tests/test_timeout_stop.py',
                               '-k', 'test_ssh_exec or ssh or usable'], env=env).returncode
        cases = list(ET.parse(report).getroot().iter('testcase'))
        failed = [c.get('name') for c in cases if any(t.tag in ('failure', 'error') for t in c)]
        names = {c.get('name') for c in cases if not any(t.tag in ('failure', 'error', 'skipped') for t in c)}
        found = json.loads(record.read_text())
    if code or failed:
        problems.append(f'pytest exit {code}; failed: {failed}')
    for shell in SHELLS:
        if f'test_a_timed_out_command_is_stopped[ssh-{shell}-tree]' not in names:
            problems.append(f'ssh-{shell}: its stop rows did not run and pass (every login shell must)')
    requests = found['requests']
    errors = [r for r in requests if 'error' in r]
    on_closed = [r for r in requests if r.get('closed')]
    unlocked = [r for r in requests if not r.get('closed') and not r.get('locked')]
    problems += [f'a request could not be read: {r}' for r in errors]
    problems += [f'{r["name"]} asked for on a closed channel in {r["test"]}' for r in on_closed]
    problems += [f'{r["name"]} written without the channel\'s lock in {r["test"]}' for r in unlocked]
    if found['freed']:
        problems.append(f'the server dropped a connection {found["freed"]} time(s) for a message on a freed channel')
    kills = [r for r in requests if r.get('name') == 'KILL']
    if not kills or not any(r.get('name') == 'TERM' for r in requests):
        problems.append(f'vacuous: TERM and KILL requests seen {[r.get("name") for r in requests]}')
    for shell in SHELLS:
        row = f'test_a_timed_out_command_is_stopped[ssh-{shell}-tree]'
        asked = [r['name'] for r in requests if row in r.get('test', '')]
        if asked != ['TERM']:
            problems.append(f'{row}: the requests were {asked}, not TERM alone (its command dies at the TERM, so '
                            'its channel ends during the grace and no KILL follows)')
    print('\n'.join(problems) or f'F2: {len(requests)} signal requests over {len(names)} rows, every one on an '
                                  f'open channel, written holding its lock ({len(kills)} KILL); no connection '
                                  'dropped for a freed channel')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
