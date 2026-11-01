# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A capability declares its probe as data on its entry point; what it declares loads or is refused at load.

    uv run python -I spec/capability-probe/verify/declared.py        from the worktree root

Plants third-party capability distributions (a dist-info and a package under a scratch directory, put
first on sys.path by this process, never by PYTHONPATH) and loads each through
`cluster_mcp.core.capabilities.load` with its own entry point:

- a capability that declares commands loads with no core edit and keeps them as declared, in order;
  one that declares none loads with `commands == ()`, as one built positionally with the five fields
  of the previous contract does;
- each malformed declaration is refused with `CapabilityLoadError` naming the planted distribution,
  and leaves `TOOL_REGISTRY` as it was: a bare string, a list, a non-string element, an empty name,
  a name with `/`, a space, a tab, a newline, NUL, a leading `-` or `.`, a non-ASCII letter, a shell
  metacharacter (`;`, `$`, `` ` ``, `*`, `'`), 256 characters, a name declared twice, a subclass of
  `tuple` and an element that is a subclass of `str` (their code would run at probe time), each for
  that reason (`REASON`), never for another (an unexpected keyword is no such refusal); a name of
  255 characters and one with `.`, `+`, `-` and `_` inside load;
- the Slurm member declares exactly `sbatch squeue scancel sacct sinfo scontrol`, and the RCAC member
  exactly `findscratch myquota` (PLAN §2.4), each through its installed entry point.

Footprint: one process, no network, no subprocess, under 300 MB; a few seconds.
"""

from __future__ import annotations

import re
import sys
import tempfile
import textwrap
from importlib.metadata import Distribution, entry_points
from pathlib import Path

from cluster_mcp.core.capabilities import GROUP, CapabilityLoadError, load
from cluster_mcp.core.tools import TOOL_REGISTRY

# A refusal for the declaration itself, as the load words it; any other cause (an unexpected keyword,
# an import error) is a refusal for the wrong reason.
REASON = re.compile(r'(its commands is a |one of its commands is a |its command .* is (not a command name|declared twice))')

SLURM = ('sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol')
RCAC = ('findscratch', 'myquota')

GOOD = {
    'plain': "('planted_cmd_a', 'planted_cmd_b')",
    'none': None,
    'positional': 'POSITIONAL',
    'longest': repr(('x' * 255,)),
    'inner-marks': "('a.b+c-d_e',)",
}
BAD = {
    'bare-string': "'sinfo'",
    'list': "['sinfo']",
    'not-a-str': '(1,)',
    'bytes': "(b'sinfo',)",
    'empty': "('',)",
    'slash': "('/usr/bin/sinfo',)",
    'relative-slash': "('bin/sinfo',)",
    'space': "('s info',)",
    'tab': "('s\\tinfo',)",
    'newline': "('sinfo\\n',)",
    'nul': "('sin\\x00fo',)",
    'leading-dash': "('-sinfo',)",
    'leading-dot': "('.sinfo',)",
    'non-ascii': "('sïnfo',)",
    'semicolon': "('a;b',)",
    'dollar': "('$x',)",
    'backtick': "('`x`',)",
    'star': "('s*',)",
    'quote': "(\"a'b\",)",
    'too-long': repr(('x' * 256,)),
    'twice': "('sinfo', 'sinfo')",
    'tuple-subclass': "type('T', (tuple,), {})(('sinfo',))",
    'str-subclass': "(type('S', (str,), {})('sinfo'),)",
}


def plant(root: Path, label: str, commands: str | None) -> tuple[str, object]:
    """A planted distribution `planted-<label>` whose capability declares `commands`; its entry point."""
    mod = 'planted_' + label.replace('-', '_')
    dist = f'planted-{label}'
    pkg = root / mod
    pkg.mkdir()
    (pkg / '__init__.py').write_text('')
    (pkg / 'tools.py').write_text(textwrap.dedent(f'''\
        from cluster_mcp.core.tools import mcp_tool

        @mcp_tool
        def {mod}_echo(text: str) -> str:
            """Echo a text back."""
            return text
        '''))
    text = f'Planted tools:\\n- {mod}_echo: Echo a text back'
    if commands == 'POSITIONAL':
        made = f"Capability('{mod}', 500, '{mod}.tools', '{text}', ())"
    elif commands is None:
        made = f"Capability(name='{mod}', order=500, tools='{mod}.tools', instructions='{text}')"
    else:
        made = (f"Capability(name='{mod}', order=500, tools='{mod}.tools', instructions='{text}', "
                f"commands={commands})")
    (pkg / 'capability.py').write_text(
        f'from cluster_mcp.core.capabilities import Capability\nCAPABILITY = {made}\n')
    info = root / f'{mod}-1.0.dist-info'
    info.mkdir()
    (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: {dist}\nVersion: 1.0\n')
    (info / 'entry_points.txt').write_text(f'[{GROUP}]\n{mod} = {mod}.capability:CAPABILITY\n')
    (eps,) = [ep for ep in Distribution.at(info).entry_points if ep.group == GROUP]
    return dist, eps


def main() -> int:
    bad: list[str] = []
    with tempfile.TemporaryDirectory(prefix='declared-') as scratch:
        root = Path(scratch)
        sys.path.insert(0, scratch)
        for label, commands in GOOD.items():
            dist, ep = plant(root, label, commands)
            try:
                (loaded,) = load([ep])
            except CapabilityLoadError as exc:
                bad.append(f'{label}: refused, expected to load: {exc}')
                continue
            want = () if commands in (None, 'POSITIONAL') else eval(commands)
            if getattr(loaded.capability, 'commands', None) != want:
                bad.append(f'{label}: loaded commands {getattr(loaded.capability, "commands", None)!r}, declared {want!r}')
            if loaded.distribution != dist:
                bad.append(f'{label}: loaded as {loaded.distribution}, expected {dist}')
        for label, commands in BAD.items():
            dist, ep = plant(root, label, commands)
            before = list(TOOL_REGISTRY)
            try:
                load([ep])
            except CapabilityLoadError as exc:
                if not str(exc).startswith(f'cannot load capability {dist}: '):
                    bad.append(f'{label}: refused without naming {dist}: {exc}')
                elif not REASON.match(str(exc).split(': ', 1)[1]):
                    bad.append(f'{label}: refused, but not for its declaration: {exc}')
                if '\n' in str(exc):
                    bad.append(f'{label}: the refusal is more than one line: {exc!r}')
            except BaseException as exc:
                bad.append(f'{label}: {type(exc).__name__} escaped the load: {exc}')
            else:
                bad.append(f'{label}: loaded, expected a refusal at load')
            if list(TOOL_REGISTRY) != before:
                bad.append(f'{label}: the refusal left the tool registry changed')
    members = {ep.dist.name: ep.load() for ep in entry_points(group=GROUP)}
    for dist, want in (('cluster-mcp-slurm', SLURM), ('cluster-mcp-rcac', RCAC)):
        got = getattr(members.get(dist), 'commands', None)
        if got != want:
            bad.append(f'{dist} declares {got!r}, expected {want!r}')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f'declared: ok ({len(GOOD)} loaded, {len(BAD)} refused, both members)', file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
