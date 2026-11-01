# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The real CLI, in `local` mode, withholds what the host lacks, fails open within the bound, and probes
exactly when the GOAL says.

    bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run python -I spec/capability-probe/verify/drives.py [quick|all]'

Every drive starts `cluster-mcp` (this tree, `uv run`) in its own process group with this sandbox's
HOME, whose `.bash_profile` puts a stub directory first on PATH and appends one line to a login log
each time a login bash starts. In `local` mode the site read runs in this process, so the login log
counts the probe launches exactly. The calling shell's `CLUSTER_MCP_SKIP_PROBES` is removed from every
drive's environment. The expected tools and resources are pinned here from the GOAL (the core's seven,
the Slurm member's seven, the RCAC member's ten and the storage URIs); each text from its module.

Drives (R-IDs in brackets):
- every probed command stubbed: the full surface, every tool and resource whole and in the order a
  server built in process for every installed capability lists them, the base the three texts in
  order, no probe line, one launch [R3, R4]; its stderr is the reference: every later stdio drive's
  lines beyond it must be exactly the probe lines expected, nothing else (an extra line, or a warning
  from the resolver, fails);
- the Slurm member's commands absent, the RCAC member's, both, and one Slurm command alone absent:
  the surface without each withheld capability (tools, resources, its text), and exactly one stderr
  line per withheld capability naming its distribution and each missing command, nothing else; one
  launch [R1, R4];
- the login profile hangs (`sleep 61`): every capability served, one line each naming the
  distribution and why; the first answer comes no sooner than the bound less 1 s and no later than
  the bound plus 6 s; no `sleep 61` survives [R5, R6];
- stdin closed (`< /dev/null`), Slurm absent and then the profile hanging: exit 0, the same lines;
  over HTTP, Slurm absent: the HTTP listing without it, the same line [R1, R6];
- `--skip-probes`, and `CLUSTER_MCP_SKIP_PROBES` as `1`, `0`, `off` and a space (any non-empty value
  is set, § Configuration): every command absent yet the full surface, no launch, one line naming what
  skipped; as the empty string: probed (both withheld), one launch [R8];
- `--help`, `--version`, `--generate-token`, a planted capability that cannot load, an SSH host on a
  closed loopback port, and an instructions budget too small for the base, each with a profile that
  would hang a probe: no launch, no probe line, none waits on a probe; the load refusal and the
  connect failure exit 5, the budget 2 [R9].

`quick` runs the first two groups only. Footprint: this process, one server and its probe at a time
(plus a FastMCP client), under 600 MB; `all` about 1 min (one 10 s hang on stdio and one with stdin
closed), `quick` about 20 s. Every server is killed by process group, and no stub or sleep survives.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.rcac.instructions import RCAC_INSTRUCTIONS
from cluster_mcp.slurm.instructions import SLURM_INSTRUCTIONS

BOUND = 10.0
CORE = ({'run_command', 'list_directory', 'read_file', 'write_file', 'upload_file', 'download_file',
         'cluster_context'}, {'cluster://context', 'rcac://context'}, CORE_INSTRUCTIONS)
PARTS = {
    'cluster-mcp-slurm': ({'sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol_show_job',
                           'scontrol_show_node'}, set(), SLURM_INSTRUCTIONS,
                          ('sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol')),
    'cluster-mcp-rcac': ({'storage_paths', 'myquota', 'jobinfo', 'jobcmd', 'jobenv', 'jobscript', 'showpartitions',
                          'average_wait', 'slist', 'sfeatures'}, {'cluster://storage', 'rcac://storage'},
                         RCAC_INSTRUCTIONS, ('findscratch', 'myquota')),
}
ALL_COMMANDS = [c for p in PARTS.values() for c in p[3]]
HEADING_START = '\n\n## Site context ('
LISTED = re.compile(r'^- (\w+):', re.M)
# Any line a probe, the override or the resolver could log, whatever its case.
PROBE_LINE = re.compile(r'capabilit|probe|withh|skip|deprecat|legacy', re.I)
# A log line's timestamp prefix, which differs from run to run.
STAMP = re.compile(r'^\[[0-9/: ]+\]\s*')
# The stderr lines of a start that probes and withholds nothing (set by the first drive), against which
# every later stdio drive's extra lines are counted.
REFERENCE: set[str] = set()
HOME = Path(os.environ.get('HOME', '/nonexistent'))
LOG = HOME / 'login.log'
STUBS = HOME / 'stubs'


def profile(present: list[str], hang: bool = False) -> None:
    """Stub `present`, and nothing else, first on PATH for every login bash; log each login."""
    if STUBS.exists():
        shutil.rmtree(STUBS)
    STUBS.mkdir()
    for name in present:
        f = STUBS / name
        f.write_text('#!/bin/sh\nexit 0\n')
        f.chmod(0o755)
    text = f'printf "login\\n" >> "{LOG}"\nPATH="{STUBS}:$PATH"\nexport PATH\n'
    if hang:
        text += 'sleep 61\n'
    (HOME / '.bash_profile').write_text(text)
    LOG.write_text('')


def launches() -> int:
    return len(LOG.read_text().splitlines())


def env(**extra: str) -> dict[str, str]:
    out = {k: v for k, v in os.environ.items() if k != 'CLUSTER_MCP_SKIP_PROBES'}
    out['FASTMCP_CHECK_FOR_UPDATES'] = 'off'
    out.update(extra)
    return out


CLI = ['uv', 'run', '--offline', 'cluster-mcp']


def expected(withheld: set[str]) -> tuple[set[str], set[str], str]:
    tools, resources, texts = set(CORE[0]), set(CORE[1]), [CORE[2]]
    for dist in ('cluster-mcp-slurm', 'cluster-mcp-rcac'):  # Composition order: Slurm 100, RCAC 900.
        if dist not in withheld:
            tools |= PARTS[dist][0]
            resources |= PARTS[dist][1]
            texts.append(PARTS[dist][2])
    return tools, resources, '\n\n'.join(texts)


DUMPS: dict[str, list] = {}


async def list_stdio(argv: list[str], environ: dict[str, str]):
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport
    transport = StdioTransport(argv[0], argv[1:], env=environ, keep_alive=False)
    async with Client(transport) as client:
        tools, resources = await client.list_tools(), await client.list_resources()
        DUMPS['tools'] = [t.model_dump(mode='json', by_alias=True) for t in tools]
        DUMPS['resources'] = [r.model_dump(mode='json', by_alias=True) for r in resources]
        return [t.name for t in tools], [str(r.uri) for r in resources], client.instructions or ''


async def list_in_process():
    """Every tool and resource a server built in this process for every installed capability lists, whole."""
    from fastmcp import Client
    from cluster_mcp.core.server import create_mcp_server
    from cluster_mcp.core.site import SiteContext
    async with Client(create_mcp_server('none', site=SiteContext.missing('the gate'))) as client:
        return ([t.model_dump(mode='json', by_alias=True) for t in await client.list_tools()],
                [r.model_dump(mode='json', by_alias=True) for r in await client.list_resources()])


def stdio_drive(argv_extra: list[str], environ: dict[str, str]):
    """Start the server over stdio through a wrapper that records its stderr; list it; the time to the
    first answer."""
    err = HOME / 'server.err'
    wrapper = ['sh', '-c', f'exec "$@" 2>"{err}"', 'sh', *CLI, '-e', 'local', *argv_extra]
    began = time.monotonic()
    tools, resources, instructions = asyncio.run(asyncio.wait_for(list_stdio(wrapper, environ), 90))
    took = time.monotonic() - began
    return tools, resources, instructions, err.read_text(), took


def surface_violations(label, tools, resources, instructions, withheld: set[str]) -> list[str]:
    bad = []
    want_tools, want_resources, want_base = expected(withheld)
    if sorted(tools) != sorted(want_tools) or len(tools) != len(set(tools)):
        bad.append(f'{label}: tools {sorted(tools)}, expected {sorted(want_tools)}')
    if sorted(resources) != sorted(want_resources):
        bad.append(f'{label}: resources {sorted(resources)}, expected {sorted(want_resources)}')
    base = instructions.split(HEADING_START, 1)[0]
    if HEADING_START not in instructions or base != want_base:
        bad.append(f'{label}: the base is not the texts of what is served, in order')
    listed = LISTED.findall(base)
    if sorted(listed) != sorted(tools):
        bad.append(f'{label}: the base lists {sorted(listed)}, served {sorted(tools)}')
    return bad


def normalized(stderr: str) -> list[str]:
    return [STAMP.sub('', line).strip() for line in stderr.splitlines() if line.strip()]


def probe_lines(stderr: str, stdio: bool = True) -> list[str]:
    """The lines beyond a plain stdio start's: against REFERENCE once it is set (stdio only), else by keyword."""
    lines = normalized(stderr)
    if REFERENCE and stdio:
        return [line for line in lines if line not in REFERENCE]
    return [line for line in lines if PROBE_LINE.search(line) and 'Starting MCP server' not in line]


def withheld_violations(label: str, stderr: str, absent: set[str], stdio: bool = True) -> list[str]:
    """Exactly one line per withheld capability, naming it and each missing command; nothing else."""
    bad = []
    lines = probe_lines(stderr, stdio)
    withheld = {d for d, p in PARTS.items() if set(p[3]) & absent}
    for dist in PARTS:
        mine = [line for line in lines if dist in line]
        if dist in withheld:
            missing = [c for c in PARTS[dist][3] if c in absent]
            if len(mine) != 1 or not all(re.search(rf'\b{c}\b', mine[0]) for c in missing):
                bad.append(f'{label}: expected one line for {dist} naming {missing}: {mine}')
            elif any(re.search(rf'\b{c}\b', mine[0]) for c in PARTS[dist][3] if c not in absent):
                bad.append(f'{label}: the line for {dist} names a command that is present: {mine[0]}')
        elif mine:
            bad.append(f'{label}: a line for {dist}, which is served: {mine}')
    if len(lines) != len(withheld):
        bad.append(f'{label}: {len(lines)} probe lines, expected {len(withheld)}: {lines}')
    return bad


def withholding() -> list[str]:
    bad: list[str] = []
    cases = {
        'every command present': set(),
        'slurm absent': set(PARTS['cluster-mcp-slurm'][3]),
        'rcac absent': set(PARTS['cluster-mcp-rcac'][3]),
        'both absent': set(ALL_COMMANDS),
        'scontrol alone absent': {'scontrol'},
    }
    for label, absent in cases.items():
        profile([c for c in ALL_COMMANDS if c not in absent])
        tools, resources, instructions, stderr, _ = stdio_drive([], env())
        withheld = {d for d, p in PARTS.items() if set(p[3]) & absent}
        if not absent:
            # The plain start: no probe line by keyword, and every tool and resource whole and in order
            # as a server built in process for every installed capability lists them (R3).
            keyed = [line for line in normalized(stderr) if PROBE_LINE.search(line) and 'Starting MCP' not in line]
            if keyed:
                bad.append(f'{label}: probe lines with nothing absent: {keyed}')
            want_tools, want_resources = asyncio.run(list_in_process())
            if DUMPS['tools'] != want_tools or DUMPS['resources'] != want_resources:
                bad.append(f'{label}: the tools or resources differ, whole or in order, from an unprobed server\'s')
            REFERENCE.update(normalized(stderr))
        bad += surface_violations(label, tools, resources, instructions, withheld)
        bad += withheld_violations(label, stderr, absent)
        if launches() != 1:
            bad.append(f'{label}: {launches()} probe launches, expected 1')
    return bad


def leftover(marker: str) -> list[str]:
    found = subprocess.run(['pgrep', '-f', marker], capture_output=True, text=True).stdout.split()
    return [pid for pid in found if pid != str(os.getpid())]


def unanswered_violations(label: str, stderr: str) -> list[str]:
    lines = probe_lines(stderr)
    bad = []
    for dist in PARTS:
        mine = [line for line in lines if dist in line]
        if len(mine) != 1 or str(int(BOUND)) not in mine[0]:
            bad.append(f'{label}: expected one line for {dist} saying it was not answered within the bound: {mine}')
    if len(lines) != len(PARTS):
        bad.append(f'{label}: {len(lines)} probe lines, expected {len(PARTS)}: {lines}')
    return bad


def hanging() -> list[str]:
    bad: list[str] = []
    profile([], hang=True)
    tools, resources, instructions, stderr, took = stdio_drive([], env())
    bad += surface_violations('hang', tools, resources, instructions, set())
    bad += unanswered_violations('hang', stderr)
    if not BOUND - 1 <= took <= BOUND + 6:
        bad.append(f'hang: the first answer came after {took:.1f} s, outside [{BOUND - 1}, {BOUND + 6}]')
    time.sleep(1)
    if leftover('sleep 61'):
        bad.append(f'hang: a probe outlived its bound: {leftover("sleep 61")}')
    return bad


def closed_stdin(label: str, absent: set[str], hang: bool) -> list[str]:
    profile([c for c in ALL_COMMANDS if c not in absent], hang=hang)
    began = time.monotonic()
    done = subprocess.run([*CLI, '-e', 'local'], stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          env=env(), timeout=90, start_new_session=True)
    took = time.monotonic() - began
    bad = [] if done.returncode == 0 else [f'{label}: exit {done.returncode}: {done.stderr[-300:]}']
    bad += unanswered_violations(label, done.stderr) if hang else withheld_violations(label, done.stderr, absent)
    if hang and took > BOUND + 8:
        bad.append(f'{label}: took {took:.1f} s with stdin closed')
    return bad


def free_port() -> int:
    """A loopback port the system says is free, outside the ports this host keeps for other servers."""
    while True:
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        if not 54001 <= port <= 54004:
            return port


async def list_http(url: str):
    from fastmcp import Client
    async with Client(url) as client:
        return [t.name for t in await client.list_tools()], [str(r.uri) for r in await client.list_resources()], \
            client.instructions or ''


def over_http() -> list[str]:
    absent = set(PARTS['cluster-mcp-slurm'][3])
    profile([c for c in ALL_COMMANDS if c not in absent])
    port = free_port()
    err = HOME / 'http.err'
    with open(err, 'w') as sink:
        server = subprocess.Popen([*CLI, '-t', 'http', '-e', 'local', '-p', str(port)], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=sink, env=env(), start_new_session=True)
    bad: list[str] = []
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                socket.create_connection(('127.0.0.1', port), timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    return [f'http: the server exited {server.returncode}: {err.read_text()[-300:]}']
                time.sleep(0.2)
        tools, resources, instructions = asyncio.run(asyncio.wait_for(list_http(f'http://127.0.0.1:{port}/mcp'), 60))
        bad += surface_violations('http', tools, resources, instructions, {'cluster-mcp-slurm'})
        bad += withheld_violations('http', err.read_text(), absent, stdio=False)
    finally:
        os.killpg(server.pid, signal.SIGKILL)
        server.wait()
    return bad


def override() -> list[str]:
    bad: list[str] = []
    for label, extra, environ in (('--skip-probes', ['--skip-probes'], env()),
                                  ('variable 1', [], env(CLUSTER_MCP_SKIP_PROBES='1')),
                                  ('variable 0', [], env(CLUSTER_MCP_SKIP_PROBES='0')),
                                  ('variable off', [], env(CLUSTER_MCP_SKIP_PROBES='off')),
                                  ('variable " "', [], env(CLUSTER_MCP_SKIP_PROBES=' '))):
        profile([])
        tools, resources, instructions, stderr, _ = stdio_drive(extra, environ)
        bad += surface_violations(label, tools, resources, instructions, set())
        lines = probe_lines(stderr)
        if len(lines) != 1 or not re.search(r'skip', lines[0], re.I):
            bad.append(f'{label}: expected one line saying probes were skipped: {lines}')
        if launches():
            bad.append(f'{label}: {launches()} probe launches, expected none')
    profile([])
    tools, resources, instructions, stderr, _ = stdio_drive([], env(CLUSTER_MCP_SKIP_PROBES=''))
    bad += surface_violations('variable empty', tools, resources, instructions, set(PARTS))
    if launches() != 1:
        bad.append(f'variable empty: {launches()} probe launches, expected 1')
    return bad


def refusals() -> list[str]:
    bad: list[str] = []
    plant = Path(tempfile.mkdtemp(prefix='broken-', dir=HOME))
    (plant / 'broken_plant.py').write_text('raise RuntimeError("planted")\n')
    info = plant / 'broken_plant-1.0.dist-info'
    info.mkdir()
    (info / 'METADATA').write_text('Metadata-Version: 2.1\nName: broken-plant\nVersion: 1.0\n')
    (info / 'entry_points.txt').write_text('[cluster_mcp.capabilities]\nbroken = broken_plant:CAPABILITY\n')
    closed = free_port()
    secret = 'x' * 40
    runs = {
        '--help': ([*CLI, '--help'], env(), 0),
        '--version': ([*CLI, '--version'], env(), 0),
        '--generate-token': ([*CLI, '--generate-token', '--sub', 'gate'], env(JWT_SECRET=secret), 0),
        'load refusal': ([*CLI, '-e', 'local'], env(PYTHONPATH=str(plant)), 5),
        'connect failure': ([*CLI, '--ssh-host', f'127.0.0.1:{closed}'], env(), 5),
        'budget refusal': ([*CLI, '-e', 'local', '--instructions-budget', '100'], env(), 2),
    }
    for label, (argv, environ, status) in runs.items():
        # A hanging profile: a refusal that probed first would wait out the bound and log for it.
        profile([], hang=True)
        began = time.monotonic()
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, env=environ,
                              timeout=60, start_new_session=True)
        if done.returncode != status:
            bad.append(f'{label}: exit {done.returncode}, expected {status}: {done.stderr[-300:]}')
        if time.monotonic() - began > BOUND - 2:
            bad.append(f'{label}: took {time.monotonic() - began:.1f} s, as if it waited on a probe')
        if launches():
            bad.append(f'{label}: {launches()} probe launches, expected none')
        lines = [line for line in normalized(done.stderr) if PROBE_LINE.search(line)
                 and 'cannot load capability' not in line and 'Starting MCP' not in line]
        if lines:
            bad.append(f'{label}: a probe line: {lines}')
    return bad


def main() -> int:
    if not os.environ.get('CLUSTER_MCP_SANDBOX'):
        raise SystemExit('drives: run inside bin/sandbox.sh (it writes the HOME .bash_profile)')
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if mode not in ('quick', 'all'):
        raise SystemExit('usage: drives.py [quick|all]')
    groups = [withholding]
    if mode == 'all':
        groups += [hanging,
                   lambda: closed_stdin('stdin closed, slurm absent', set(PARTS['cluster-mcp-slurm'][3]), False),
                   lambda: closed_stdin('stdin closed, hang', set(), True),
                   over_http, override, refusals]
    bad: list[str] = []
    for group in groups:
        began = time.monotonic()
        try:
            found = group()
        except Exception as exc:
            # A drive that cannot complete (the server exited, the client was refused) is a failure
            # of its group, reported with the rest.
            found = [f'{getattr(group, "__name__", "group")}: a drive failed: {type(exc).__name__}: {exc}']
        print(f'drives: {getattr(group, "__name__", "group")}: {len(found)} problems, {time.monotonic() - began:.1f} s',
              file=sys.stderr)
        bad += found
    if leftover(str(STUBS)):
        bad.append(f'a process from the stubs survived: {leftover(str(STUBS))}')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'drives: {mode} ok', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
