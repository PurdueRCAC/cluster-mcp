"""The extras pin fails naming the extra, in the declarations and in the installed metadata.

Usage, from the worktree root:  python -I spec/rcac-extra-brings-slurm/verify/extra_mutants.py

Each case archives the index (what the next commit holds) into a fresh lab (`tempfile.mkdtemp`,
removed on exit), plants one break into the lab's `packages/cluster-mcp/pyproject.toml` and syncs the
lab's own environment from it (`uv sync`, which relocks the lab copy only). It then runs
`tests/test_packaging.py::test_core_declares_the_capability_extras` in the lab twice: once as
planted, where the declarations break (red, naming the extra, at the declarations' assertion), and
once with the declarations restored but the environment left as synced, where only the installed
metadata breaks (red, naming the extra, at the metadata's assertion). A control lab, unplanted,
syncs and passes. Each plant is confirmed landed before it runs.

  rcac-without-slurm  the rcac extra no longer installs the Slurm member
  slurm-with-rcac     the slurm extra starts installing the RCAC member

Footprint: one uv or pytest process at a time; peak about 3 processes, under 1 GB. Nothing runs in
the background. Exit 0 printing `ok`, or exit 1 naming every case that did not go as expected.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

CORE_PYPROJECT = Path('packages/cluster-mcp/pyproject.toml')
TEST = 'tests/test_packaging.py::test_core_declares_the_capability_extras'
DECLARED = 'the declared extras break the rule'
INSTALLED = 'the installed extras break the rule'

# Each case: the extra it plants, the members it plants for it, and the message the test must name.
CASES = {
    'rcac-without-slurm': ('rcac', ['cluster-mcp-rcac'], 'the rcac extra does not install cluster-mcp-slurm'),
    'slurm-with-rcac': ('slurm', ['cluster-mcp-slurm', 'cluster-mcp-rcac'],
                        'the slurm extra installs cluster-mcp-rcac, which it must not'),
}
RULE = {'slurm': {'cluster-mcp-slurm'}, 'rcac': {'cluster-mcp-rcac', 'cluster-mcp-slurm'}}


def extras(text: str) -> dict[str, set[str]]:
    """The core's declared extras, each as the set of its requirements."""
    table = tomllib.loads(text)['project'].get('optional-dependencies') or {}
    return {extra: set(reqs) for extra, reqs in table.items()}


def plant(text: str, extra: str, members: list[str]) -> str:
    """`text` with `extra`'s array (one line or several) replaced by `members`."""
    array = re.compile(rf'^{extra}\s*=\s*\[[^\]]*\]', re.MULTILINE)
    if len(array.findall(text)) != 1:
        raise ValueError(f'no single {extra} array to plant into')
    return array.sub(f'{extra} = {members!r}'.replace("'", '"'), text)


def failed_at(out: str, message: str, layer: str) -> bool:
    """Whether pytest's report shows the failure raised at `layer`'s assertion, naming `message`.

    Only the `E` lines are read: the traceback also prints the test's source, which holds every
    assertion's text, so a match anywhere else would credit the wrong assertion.
    """
    raised = [line[1:].strip() for line in out.splitlines() if line.startswith('E ')]
    return f'AssertionError: {layer}' in raised and any(message in line for line in raised)

ENV = {k: v for k, v in os.environ.items() if k not in ('VIRTUAL_ENV', 'UV_PROJECT', 'UV_PROJECT_ENVIRONMENT')}
ENV |= {'UV_PYTHON': '3.14', 'UV_NO_ENV_FILE': '1'}
ENV.pop('UV_ENV_FILE', None)


def lab_from_index(parent: Path, name: str) -> Path:
    tree = subprocess.run(['git', 'write-tree'], check=True, capture_output=True, text=True).stdout.strip()
    data = subprocess.run(['git', 'archive', '--format=tar', tree], check=True, capture_output=True).stdout
    lab = parent / name
    lab.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(lab, filter='data')
    return lab


def sync(lab: Path) -> None:
    subprocess.run(['uv', 'sync', '--quiet', '--project', str(lab)], check=True, cwd=lab, env=ENV, timeout=600)


def run_test(lab: Path) -> tuple[int, str]:
    done = subprocess.run(['uv', 'run', '--no-sync', '--project', str(lab), 'pytest', '-q', '-p', 'no:cacheprovider',
                           TEST], cwd=lab, env=ENV, capture_output=True, text=True, timeout=600)
    return done.returncode, done.stdout + done.stderr


def main() -> int:
    if not Path('spec/rcac-extra-brings-slurm/GOAL.md').is_file():
        sys.exit('extra_mutants: run from the cycle worktree root')
    problems: list[str] = []
    parent = Path(tempfile.mkdtemp(prefix='rebs-mutants-'))
    try:
        control = lab_from_index(parent, 'control')
        text = (control / CORE_PYPROJECT).read_text()
        if extras(text) != RULE:
            return print(f'extra_mutants: FAIL: the index declares {extras(text)}, not {RULE}', file=sys.stderr) or 1
        sync(control)
        status, out = run_test(control)
        if status != 0:
            problems.append(f'control: the unplanted lab fails:\n{out[-2000:]}')
        for case, (extra, members, message) in CASES.items():
            lab = lab_from_index(parent, case)
            pyproject = lab / CORE_PYPROJECT
            original = pyproject.read_text()
            pyproject.write_text(plant(original, extra, members))
            if extras(pyproject.read_text()) != RULE | {extra: set(members)}:
                problems.append(f'{case}: the plant did not land')
                continue
            sync(lab)
            for layer, restore, want in (('declarations', False, DECLARED), ('metadata', True, INSTALLED)):
                if restore:
                    pyproject.write_text(original)
                    if pyproject.read_text() != original:
                        problems.append(f'{case}: the declarations were not restored')
                        continue
                status, out = run_test(lab)
                if status == 0:
                    problems.append(f'{case} ({layer}): survived')
                elif not failed_at(out, message, want):
                    problems.append(f'{case} ({layer}): red, but not naming {message!r} at {want!r}:\n{out[-2000:]}')
                else:
                    print(f'killed: {case} ({layer}): {message}')
    finally:
        shutil.rmtree(parent)
    for problem in problems:
        print(f'extra_mutants: FAIL: {problem}', file=sys.stderr)
    if problems:
        return 1
    print(f'ok: {len(CASES)} cases x 2 layers killed naming the extra; the control passes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
