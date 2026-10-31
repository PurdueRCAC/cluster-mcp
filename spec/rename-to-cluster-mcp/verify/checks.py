# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Static checks for the rename-to-cluster-mcp cycle. Read files only; import nothing of the server.

    uv run --with pyyaml python spec/rename-to-cluster-mcp/verify/checks.py [--root DIR] CHECK...
    uv run --with pyyaml python spec/rename-to-cluster-mcp/verify/checks.py wheels DIST_DIR
    uv run --with pyyaml python spec/rename-to-cluster-mcp/verify/checks.py controls [CHECK...]

CHECK is any of: source (the workspace and namespace layout, scripts, one version), imports (no
`rcac_mcp` survives), env (the legacy variable names appear only where the window allows), uris
(the same for `rcac://`; uris-p3 lets the instructions keep naming them until the split), urls (R13), spdx (R14),
container (the Dockerfile and compose.yml), ci (ci.yml mirrors the profile and the recipe),
profile (the profile keys and the release recipe), readme (the one deprecation section), ledger
(the deferral seed and its ROADMAP entry), docs-p1 … docs-p5 (AGENTS.md says what each phase made
true). `wheels DIR` scans built artifacts. `controls` plants a violation for each check into a copy
of the tree and requires the check to reject it, and the unplanted copy to pass: a check that
cannot go red is not a check. Footprint: one process, a few MB; `controls` copies the text files
it plants into under $TMPDIR and removes the copy.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
import tarfile
from pathlib import Path

import yaml

HEADER = 'SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors'
LICENSE = 'SPDX-License-Identifier: MIT'
GOAL_HEADER_COUNT = 93
MEMBERS = {'cluster-mcp': 'core', 'cluster-mcp-slurm': 'slurm', 'cluster-mcp-rcac': 'rcac'}
ROOT_DIST = 'rcac-mcp'
CORE = 'packages/cluster-mcp/src/cluster_mcp/core'
URL = 'https://github.com/PurdueRCAC/cluster-mcp'
LEGACY_ENV = ('RCAC_SSH_HOST', 'RCAC_USER_MAP', 'RCAC_INSTRUCTIONS_BUDGET')
NEW_ENV = ('CLUSTER_MCP_SSH_HOST', 'CLUSTER_MCP_USER_MAP', 'CLUSTER_MCP_INSTRUCTIONS_BUDGET')
OLD_HIGH_BLAST = ['context.py', 'middleware.py', 'auth.py', 'token.py', 'executor/base.py',
                  'executor/delegate.py', 'executor/ssh.py', 'executor/launch.py', 'server.py',
                  '__init__.py']
VERIFY = ('uv lock --check && uv run pytest -q && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q'
          ' && bin/sandbox.sh uv run cluster-mcp --help')
BUILD = 'uv build --all-packages --no-sources -o dist/'
POST_VERIFY = [
    "bin/sandbox.sh uvx --from 'git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp' cluster-mcp --help",
    "bin/sandbox.sh uvx --from 'git+https://github.com/PurdueRCAC/cluster-mcp@{v}' rcac-mcp --help",
]
SEED = 'issues/rename-leftover-identity-strings.md'
WINDOW = 'deprecated in 0.2.0, removed no earlier than 0.4.0'
SKIP_DIRS = {'.git', '.venv', '.worktrees', 'dist', '__pycache__', '.pytest_cache', 'node_modules'}


# ---- file access -------------------------------------------------------------------------------

def tracked(root: Path) -> list[str]:
    """Tracked and untracked-but-not-ignored files, as git lists them; a walk when not a repo."""
    try:
        out = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others',
                              '--exclude-standard'], capture_output=True, check=True).stdout
        names = [n for n in out.decode().split('\0') if n]
    except (subprocess.CalledProcessError, FileNotFoundError):
        names = [str(p.relative_to(root)) for p in root.rglob('*')
                 if p.is_file() and not SKIP_DIRS & set(p.relative_to(root).parts)]
    return sorted(n for n in set(names) if (root / n).is_file())


def text(root: Path, name: str) -> str | None:
    try:
        return (root / name).read_text(encoding='utf-8')
    except (FileNotFoundError, UnicodeDecodeError, IsADirectoryError):
        return None


def section(md: str, heading: str) -> str:
    """The text under the first heading line equal to `heading`, up to the next heading of its level or higher."""
    level = len(heading) - len(heading.lstrip('#'))
    out, on = [], False
    for line in md.splitlines():
        m = re.match(r'^(#+) ', line)
        if on and m and len(m.group(1)) <= level:
            break
        if line.strip() == heading:
            on = True
            continue
        if on:
            out.append(line)
    return '\n'.join(out)


def profile_cell(agents: str, key: str) -> str | None:
    m = re.search(rf'^\| {re.escape(key)} \| (.*) \|$', agents, re.M)
    return m.group(1) if m else None


def recipe(agents: str) -> dict | None:
    body = section(agents, '### Release recipe')
    m = re.search(r'```yaml\n(.*?)```', body, re.S)
    try:
        return yaml.safe_load(m.group(1))['release'] if m else None
    except (yaml.YAMLError, KeyError, TypeError):
        return None


def pyproject(root: Path, name: str) -> dict | None:
    raw = text(root, name)
    try:
        return tomllib.loads(raw) if raw is not None else None
    except tomllib.TOMLDecodeError:
        return None


# ---- checks: each returns a list of violations -------------------------------------------------

def check_source(root: Path) -> list[str]:
    found = []
    files = tracked(root)
    inits = [f for f in files if re.fullmatch(r'packages/[^/]+/src/cluster_mcp/__init__\.py', f)]
    found += [f'{f}: a namespace __init__.py hides every other member' for f in inits]
    found += [f'{f}: code left under src/' for f in files if f.startswith('src/') and f.endswith('.py')]
    dirs = sorted({f.split('/')[1] for f in files if f.startswith('packages/') and f.count('/') > 1})
    if dirs != sorted(MEMBERS):
        found.append(f'packages/ holds {dirs}, expected {sorted(MEMBERS)}')
    versions = {}
    for dist, cap in MEMBERS.items():
        base = f'packages/{dist}'
        tree = sorted({f.split('/')[4] for f in files if f.startswith(f'{base}/src/cluster_mcp/')})
        if tree != [cap]:
            found.append(f'{base}/src/cluster_mcp holds {tree}, expected only {cap}/')
        doc = pyproject(root, f'{base}/pyproject.toml')
        if doc is None:
            found.append(f'{base}/pyproject.toml is missing or invalid')
            continue
        proj = doc.get('project', {})
        if proj.get('name') != dist:
            found.append(f'{base}: project.name is {proj.get("name")!r}, expected {dist!r}')
        versions[dist] = proj.get('version')
        wheel = doc.get('tool', {}).get('hatch', {}).get('build', {}).get('targets', {}).get('wheel', {})
        if wheel.get('only-include') != [f'src/cluster_mcp/{cap}'] or wheel.get('sources') != ['src'] or 'packages' in wheel:
            found.append(f'{base}: the wheel must take only-include = ["src/cluster_mcp/{cap}"], sources = ["src"], no packages')
        deps = [re.split(r'[ <>=!~;\[]', d, maxsplit=1)[0] for d in proj.get('dependencies', [])]
        want = [d for d in MEMBERS if d != dist] if cap == 'core' else ['cluster-mcp']
        for d in want:
            if d not in deps:
                found.append(f'{base}: does not depend on {d}')
            if doc.get('tool', {}).get('uv', {}).get('sources', {}).get(d) != {'workspace': True}:
                found.append(f'{base}: {d} is not a workspace source')
        scripts = proj.get('scripts', {})
        if cap == 'core' and scripts != {'cluster-mcp': 'cluster_mcp.core:main'}:
            found.append(f'{base}: scripts are {scripts}, expected only cluster-mcp = cluster_mcp.core:main')
        if cap != 'core' and scripts:
            found.append(f'{base}: a capability member installs no script, found {scripts}')
    root_doc = pyproject(root, 'pyproject.toml') or {}
    rp = root_doc.get('project', {})
    if rp.get('name') != ROOT_DIST:
        found.append(f'pyproject.toml: the root distribution is {rp.get("name")!r}, expected {ROOT_DIST!r}')
    if rp.get('scripts') != {'rcac-mcp': 'cluster_mcp.core:legacy_main'}:
        found.append(f'pyproject.toml: scripts are {rp.get("scripts")}, expected only rcac-mcp = cluster_mcp.core:legacy_main')
    if [re.split(r'[ <>=!~;\[]', d, maxsplit=1)[0] for d in rp.get('dependencies', [])] != ['cluster-mcp']:
        found.append('pyproject.toml: the root distribution must depend on cluster-mcp alone')
    if root_doc.get('tool', {}).get('uv', {}).get('workspace', {}).get('members') != ['packages/*']:
        found.append('pyproject.toml: tool.uv.workspace.members is not ["packages/*"]')
    versions[ROOT_DIST] = rp.get('version')
    if len(set(versions.values())) != 1 or None in versions.values():
        found.append(f'the four distributions do not carry one version: {versions}')
    init = text(root, f'{CORE}/__init__.py') or ''
    if "get_version('cluster-mcp')" not in init:
        found.append(f"{CORE}/__init__.py: __version__ does not read get_version('cluster-mcp')")
    if re.search(r'^__version__\s*=\s*[\'"]', init, re.M):
        found.append(f'{CORE}/__init__.py: a hardcoded __version__')
    if 'def legacy_main' not in init:
        found.append(f'{CORE}/__init__.py: no legacy_main')
    if text(root, f'{CORE}/__main__.py') is None:
        found.append(f'{CORE}/__main__.py is missing: python -m cluster_mcp.core cannot run')
    return found


def check_wheels(dist: Path) -> list[str]:
    found = []
    wheels = sorted(dist.glob('*.whl'))
    sdists = sorted(dist.glob('*.tar.gz'))
    want = {d.replace('-', '_') for d in [*MEMBERS, ROOT_DIST]}
    got_w = {w.name.split('-')[0] for w in wheels}
    got_s = {s.name.rsplit('-', 1)[0] for s in sdists}
    if got_w != want or len(wheels) != len(want):
        found.append(f'wheels {sorted(got_w)} (n={len(wheels)}), expected one each of {sorted(want)}')
    if got_s != want or len(sdists) != len(want):
        found.append(f'sdists {sorted(got_s)} (n={len(sdists)}), expected one each of {sorted(want)}')
    for w in wheels:
        with zipfile.ZipFile(w) as z:
            names = z.namelist()
            entry = next((n for n in names if n.endswith('.dist-info/entry_points.txt')), None)
            entries = z.read(entry).decode() if entry else ''
        if 'cluster_mcp/__init__.py' in names:
            found.append(f'{w.name}: ships cluster_mcp/__init__.py')
        code = [n for n in names if '.dist-info/' not in n]
        dist_name = w.name.split('-')[0]
        cap = {d.replace('-', '_'): c for d, c in MEMBERS.items()}.get(dist_name)
        if cap is None:  # the root compat distribution: no code, one script
            if code:
                found.append(f'{w.name}: the compat wheel ships code {code[:3]}')
            if 'rcac-mcp = cluster_mcp.core:legacy_main' not in entries:
                found.append(f'{w.name}: no rcac-mcp entry point')
            continue
        stray = [n for n in code if not n.startswith(f'cluster_mcp/{cap}/')]
        if stray:
            found.append(f'{w.name}: ships outside cluster_mcp/{cap}/: {stray[:3]}')
        if cap == 'core':
            for need in ('cluster_mcp/core/__main__.py', 'cluster_mcp/core/static/purdue-favicon.ico',
                         'cluster_mcp/core/deprecation.py'):
                if need not in names:
                    found.append(f'{w.name}: missing {need}')
            if 'cluster-mcp = cluster_mcp.core:main' not in entries or 'rcac-mcp' in entries:
                found.append(f'{w.name}: entry points are not exactly cluster-mcp')
    for s in sdists:
        with tarfile.open(s) as t:
            names = t.getnames()
        top = s.name[:-len('.tar.gz')]
        bad = [n for n in names if re.match(rf'{re.escape(top)}/(bin|spec|issues|tests|\.security|packages)(/|$)', n)]
        if bad:
            found.append(f'{s.name}: ships repository furniture {bad[:3]}')
    return found


def _scan(root: Path, pattern: str, exclude: tuple[str, ...] = ('spec/', 'issues/', 'ROADMAP.md')) -> list[tuple[str, int, str]]:
    rx = re.compile(pattern)
    hits = []
    for f in tracked(root):
        if f.startswith(exclude) or f.startswith('spec/rename-to-cluster-mcp/') or (root / f).is_symlink():
            continue
        body = text(root, f)
        if body is None:
            continue
        for i, line in enumerate(body.splitlines(), 1):
            if rx.search(line):
                hits.append((f, i, line))
    return hits


def check_imports(root: Path) -> list[str]:
    allowed = {'tests/test_registry.py'}
    return [f'{f}:{i}: rcac_mcp survives: {l.strip()[:90]}' for f, i, l in _scan(root, r'\brcac_mcp\b')
            if f not in allowed and f != 'AGENTS.md']


def _readme_window(root: Path) -> tuple[str, str]:
    readme = text(root, 'README.md') or ''
    head = next((l for l in readme.splitlines() if re.match(r'^## .*rcac-mcp', l)), None)
    return (head or '', section(readme, head) if head else '')


def check_env(root: Path) -> list[str]:
    found = []
    allowed_code = {f'{CORE}/deprecation.py', 'bin/sandbox.sh'}
    head, sect = _readme_window(root)
    for f, i, line in _scan(root, r'\bRCAC_(SSH_HOST|USER_MAP|INSTRUCTIONS_BUDGET)\b'):
        if f.startswith('tests/') or f in allowed_code or f == 'AGENTS.md':
            continue
        if f == 'README.md' and sect and line in sect.splitlines():
            continue
        found.append(f'{f}:{i}: a legacy variable outside the window: {line.strip()[:90]}')
    dep = text(root, f'{CORE}/deprecation.py') or ''
    for old, new in zip(LEGACY_ENV, NEW_ENV):
        if not re.search(rf"['\"]{new}['\"]\s*:\s*['\"]{old}['\"]", dep):
            found.append(f'{CORE}/deprecation.py: no {new} -> {old} entry')
    sandbox = text(root, 'bin/sandbox.sh') or ''
    unset = ' '.join(re.findall(r'^unset ((?:[^\n]*\\\n)*[^\n]*)', sandbox, re.M)).replace('\\', ' ').split()
    for name in ('CLUSTER_MCP_SSH_HOST', 'RCAC_SSH_HOST', 'CLUSTER_MCP_USER_MAP', 'RCAC_USER_MAP'):
        if name not in unset:
            found.append(f'bin/sandbox.sh: does not unset {name}')
    conftest = text(root, 'tests/conftest.py') or ''
    blanked = re.search(r'^BLANKED_ENV[^=]*=\s*([\(\[{].*?[\)\]}])\s*$', conftest, re.M | re.S)
    for name in (*NEW_ENV[:2], *LEGACY_ENV[:2]):
        if not blanked or f"'{name}'" not in blanked.group(1):
            found.append(f'tests/conftest.py: BLANKED_ENV does not blank {name}')
    if 'UV_NO_ENV_FILE' not in sandbox or not re.search(r'^unset[^\n]*\bUV_ENV_FILE\b', sandbox, re.M):
        found.append('bin/sandbox.sh: does not unset UV_ENV_FILE and set UV_NO_ENV_FILE')
    for f in tracked(root):
        if f.startswith(('packages/', 'bin/')) and f.endswith(('.py', '.sh')) and f not in allowed_code:
            body = text(root, f) or ''
            if re.search(r'environ(\.get)?\s*[\[(]\s*[\'"]CLUSTER_MCP_(SSH_HOST|USER_MAP|INSTRUCTIONS_BUDGET)', body) \
                    or re.search(r'getenv\(\s*[\'"]CLUSTER_MCP_(SSH_HOST|USER_MAP|INSTRUCTIONS_BUDGET)', body):
                found.append(f'{f}: reads a replacement variable directly, not through env_setting')
    return found


def check_uris(root: Path, instructions_moved: bool = True) -> list[str]:
    found = []
    head, sect = _readme_window(root)
    for f, i, line in _scan(root, r'rcac://'):
        if f.startswith('tests/') or f == 'AGENTS.md' or f == f'{CORE}/resources.py':
            continue
        if not instructions_moved and f == f'{CORE}/server.py':
            continue  # The instructions name the URIs until the split rewrites them.
        if f == 'README.md' and sect and line in sect.splitlines():
            continue
        found.append(f'{f}:{i}: an rcac:// URI outside the aliases: {line.strip()[:90]}')
    res = text(root, f'{CORE}/resources.py') or ''
    lits = re.findall(r"""['"](\w+://[\w/]*)['"]""", res)
    if sorted(set(lits)) != ['cluster://', 'cluster://context', 'cluster://storage', 'rcac://'] and \
       sorted(set(lits)) != ['cluster://context', 'cluster://storage', 'rcac://']:
        found.append(f'{CORE}/resources.py: URI literals are {sorted(set(lits))}; the aliases must be derived, not hand-written')
    return found


def check_urls(root: Path) -> list[str]:
    found = [f'{f}:{i}: the old repository URL: {l.strip()[:90]}'
             for f, i, l in _scan(root, r'(?i)github\.com[/:]purduercac/rcac-mcp', exclude=('spec/', 'issues/'))]
    for f, i, line in _scan(root, r'(?i)github\.com[/:]purduercac/', exclude=('spec/', 'issues/')):
        for m in re.finditer(r'(?i)github\.com[/:]purduercac/[\w.-]+', line):
            if m.group(0)[len('github.com/'):] != 'PurdueRCAC/cluster-mcp':
                found.append(f'{f}:{i}: names {m.group(0)}, not github.com/PurdueRCAC/cluster-mcp')
    init = text(root, f'{CORE}/__init__.py') or ''
    if f"__website__ = '{URL}'" not in init:
        found.append(f'{CORE}/__init__.py: __website__ is not {URL}')
    return found


SPDX_LINE = re.compile(r'^\s*(?:#|//|<!--|\*|;|--)?\s*(SPDX-(FileCopyrightText|License-Identifier):.*?)\s*(?:-->)?\s*$')


def check_spdx(root: Path) -> list[str]:
    found, holders = [], 0
    for f in tracked(root):
        body = None if (root / f).is_symlink() else text(root, f)
        if body is None:
            continue
        cr = lic = 0
        for i, line in enumerate(body.splitlines(), 1):
            m = SPDX_LINE.match(line)
            if not m:
                continue
            if m.group(2) == 'FileCopyrightText':
                cr += 1
                if m.group(1) != HEADER:
                    found.append(f'{f}:{i}: {m.group(1)!r} is not {HEADER!r}')
            else:
                lic += 1
                if m.group(1) != LICENSE:
                    found.append(f'{f}:{i}: {m.group(1)!r} is not {LICENSE!r}')
        if cr != lic:
            found.append(f'{f}: {cr} copyright lines, {lic} license lines')
        holders += cr > 0
        if cr == 0 and f.endswith(('.py', '.sh')) and not f.startswith('spec/') and (body.strip() != ''):
            found.append(f'{f}: no SPDX header')
    if holders < GOAL_HEADER_COUNT:
        found.append(f'only {holders} files carry a header; the GOAL counted {GOAL_HEADER_COUNT}')
    return found


def check_ci(root: Path) -> list[str]:
    agents = text(root, 'AGENTS.md') or ''
    setup, verify, rel = profile_cell(agents, 'setup'), profile_cell(agents, 'verify'), recipe(agents)
    if not (setup and verify and rel):
        return ['AGENTS.md: cannot read the profile setup/verify or the recipe gate']
    setup = re.match(r'`([^`]*)`', setup).group(1)
    verify = re.match(r'`([^`]*)`', verify).group(1)
    parts = [s.strip() for s in verify.split('&&')]
    want = [setup, *parts, *[g for g in rel['gate'] if g not in parts]]
    try:
        doc = yaml.safe_load(text(root, '.github/workflows/ci.yml') or '')
        runs = [s['run'] for s in doc['jobs']['gate']['steps'] if 'run' in s]
    except (yaml.YAMLError, KeyError, TypeError):
        return ['.github/workflows/ci.yml: cannot read the gate job']
    if runs and runs[0].startswith('sudo apt-get'):
        runs = runs[1:]
    return [] if runs == want else [f'ci.yml gate runs {runs}, expected {want}']


def check_profile(root: Path, final: bool) -> list[str]:
    found = []
    agents = text(root, 'AGENTS.md') or ''
    verify = profile_cell(agents, 'verify') or ''
    if not verify.startswith(f'`{VERIFY}`'):
        found.append(f'profile verify is not `{VERIFY}`')
    core = profile_cell(agents, 'coupled core') or ''
    for f in ('context.py', 'middleware.py', 'auth.py', 'token.py', 'executor/*', 'server.py'):
        if f'{CORE}/{f}' not in core and not (f'{CORE}/' in core and f in core):
            found.append(f'profile coupled core does not name {CORE}/{f}')
    if 'src/rcac_mcp' in core:
        found.append('profile coupled core still names src/rcac_mcp')
    blast = section(agents, '### High-blast-radius paths (human gate)')
    entries = re.findall(r'^- `([^`]+)`', blast, re.M)
    for f in OLD_HIGH_BLAST:
        if f'src/rcac_mcp/{f}' not in entries:
            found.append(f'high-blast list lost src/rcac_mcp/{f}')
        if f'{CORE}/{f}' not in entries:
            found.append(f'high-blast list lacks {CORE}/{f}')
    if 'bin/sandbox.sh' not in entries:
        found.append('high-blast list lost bin/sandbox.sh')
    rel = recipe(agents) or {}
    if rel.get('version', {}).get('source') != 'packages/cluster-mcp/pyproject.toml project.version':
        found.append('recipe version.source is not packages/cluster-mcp/pyproject.toml project.version')
    files = rel.get('bump', {}).get('files', [])
    for f in ['pyproject.toml', *[f'packages/{d}/pyproject.toml' for d in MEMBERS], 'uv.lock']:
        if f not in files:
            found.append(f'recipe bump.files lacks {f}')
    if BUILD not in rel.get('gate', []) or 'uv build -o dist/' in rel.get('gate', []):
        found.append(f'recipe gate does not build with `{BUILD}`')
    if rel.get('tag', {}).get('message') != 'cluster-mcp {v}':
        found.append('recipe tag.message is not "cluster-mcp {v}"')
    if rel.get('post_verify') != POST_VERIFY:
        found.append(f'recipe post_verify is not {POST_VERIFY}')
    if final and 'repo-rename-first' not in rel.get('caveats', {}):
        found.append('recipe caveats lack repo-rename-first')
    return found


def check_readme(root: Path) -> list[str]:
    found = []
    head, sect = _readme_window(root)
    if not sect:
        return ['README.md: no "## … rcac-mcp …" deprecation section']
    for need in ('`rcac-mcp`', '`cluster-mcp`', *LEGACY_ENV, *NEW_ENV, 'rcac://context', 'rcac://storage',
                 'cluster://context', 'cluster://storage', '0.2.0', '0.4.0'):
        if need not in sect:
            found.append(f'README.md deprecation section does not name {need}')
    rest = (text(root, 'README.md') or '').replace(sect, '')
    for old in (*LEGACY_ENV, 'rcac://'):
        if old in rest:
            found.append(f'README.md names {old} outside the deprecation section')
    for line in rest.splitlines():
        if re.search(r'\buvx?\b[^\n]*\brcac-mcp\b', line):
            found.append(f'README.md runs rcac-mcp outside the deprecation section: {line.strip()[:90]}')
    if 'git+https://github.com/PurdueRCAC/cluster-mcp' not in rest or 'subdirectory=packages/cluster-mcp' not in rest:
        found.append('README.md has no install line from PurdueRCAC/cluster-mcp with #subdirectory=packages/cluster-mcp')
    dep = text(root, f'{CORE}/deprecation.py') or ''
    m = re.search(r"^WINDOW[^=]*=\s*['\"]([^'\"]+)['\"]", dep, re.M)
    if not m or m.group(1) != WINDOW:
        found.append(f'{CORE}/deprecation.py: WINDOW is not {WINDOW!r}')
    if WINDOW not in sect:
        found.append(f'README.md deprecation section does not state the window as the warnings do: {WINDOW!r}')
    return found


def check_ledger(root: Path) -> list[str]:
    found = []
    seed = text(root, SEED)
    if seed is None or not re.search(r'^status: unshaped$', seed, re.M):
        found.append(f'{SEED} is missing or not status: unshaped')
    for need in ('ISSUER', 'AUDIENCE', 'serverInfo', 'favicon'):
        if seed is not None and need not in seed:
            found.append(f'{SEED} does not record {need}')
    roadmap = text(root, 'ROADMAP.md') or ''
    if f'**Seed:** [`{SEED}`]({SEED})' not in roadmap:
        found.append(f'ROADMAP.md has no entry whose **Seed:** is `{SEED}`')
    adopted = text(root, 'issues/rename-to-cluster-mcp.md') or ''
    if not re.search(r'^status: adopted:rename-to-cluster-mcp$', adopted, re.M):
        found.append('issues/rename-to-cluster-mcp.md is not status: adopted:rename-to-cluster-mcp')
    tech = text(root, 'spec/rename-to-cluster-mcp/TECH.md') or ''
    phases = '\n'.join(section(tech, h) for h in re.findall(r'^## Phase P\d.*$', tech, re.M))
    for line in phases.splitlines():
        if re.search(r'(?i)\b(defer|follow-up|known limitation|not fixed here|do not fix)', line) \
                and not re.search(r'issues/[\w-]+\.md', line) and 'deferral' not in line.lower():
            found.append(f'TECH.md: a deferral with no issues/ destination: {line.strip()[:90]}')
        for p in re.findall(r'issues/[\w-]+\.md', line):
            if text(root, p) is None:
                found.append(f'TECH.md names {p}, which does not exist')
    return found


def check_container(root: Path) -> list[str]:
    found = []
    docker = text(root, 'Dockerfile') or ''
    if not re.search(r'^ENTRYPOINT \["cluster-mcp"\]\s*$', docker, re.M):
        found.append('Dockerfile: ENTRYPOINT is not ["cluster-mcp"]')
    copies = re.findall(r'^COPY\s+(?!--)(.+?)\s+\S+\s*$', docker, re.M)
    sources = [s for c in copies for s in c.split()]
    files = tracked(root)
    for s in sources:
        stem = s.rstrip('/')
        if stem not in files and not any(f.startswith(stem + '/') for f in files):
            found.append(f'Dockerfile: COPY {s}, which is not in the tree')
    for need in ('pyproject.toml', 'uv.lock', 'packages/'):
        if need not in sources:
            found.append(f'Dockerfile: does not COPY {need}')
    if re.search(r'rcac-mcp|rcac_mcp|src/', docker):
        found.append('Dockerfile: still names rcac-mcp, rcac_mcp or src/')
    try:
        compose = yaml.safe_load(text(root, 'compose.yml') or '')
        name = compose['services']['mcp'].get('container_name')
    except (yaml.YAMLError, KeyError, TypeError, AttributeError):
        name = None
    if name != 'cluster-mcp':
        found.append(f'compose.yml: container_name is {name!r}, not cluster-mcp')
    return found


def _agents_outside_blast(agents: str) -> str:
    blast = section(agents, '### High-blast-radius paths (human gate)')
    return agents.replace(blast, '')


def check_docs(root: Path, phase: int) -> list[str]:
    found = []
    agents = text(root, 'AGENTS.md') or ''
    rest = _agents_outside_blast(agents)
    def need(where: str, body: str, *marks: str) -> None:
        for m in marks:
            if m not in body:
                found.append(f'AGENTS.md {where} does not say {m!r}')
    if phase >= 1:
        need('§ Project', section(agents, '## Project'), 'cluster_mcp.core:main', 'python -m cluster_mcp.core', 'rcac-mcp')
        need('§ Repository map', section(agents, '## Repository map'), 'packages/cluster-mcp', 'packages/cluster-mcp-slurm',
             'packages/cluster-mcp-rcac', 'cluster_mcp.slurm', 'cluster_mcp.rcac')
        need('§ Packaging', section(agents, '## Packaging'), 'workspace', '__init__.py', '--all-packages')
        need('§ Conventions', section(agents, '### Conventions (same-commit rules)'), "importlib.metadata.version('cluster-mcp')")
        for i, line in enumerate(rest.splitlines(), 1):
            if 'src/rcac_mcp' in line:
                found.append(f'AGENTS.md: src/rcac_mcp outside the high-blast list: {line.strip()[:90]}')
            elif re.search(r'\brcac_mcp\b', line) and not re.search(r'(?i)absen|leftover|unimportable|stale', line):
                found.append(f'AGENTS.md: rcac_mcp outside the absence rows: {line.strip()[:90]}')
            if re.search(r'uv run rcac-mcp|sandbox\.sh[^\n`]*rcac-mcp --help', line) and 'legacy' not in line.lower() \
                    and 'deprecat' not in line.lower():
                found.append(f'AGENTS.md: a drive of rcac-mcp that is not the legacy alias: {line.strip()[:90]}')
    if phase >= 2:
        need('§ Configuration', section(agents, '## Configuration'), *NEW_ENV, *LEGACY_ENV, 'warning')
        need('§4', section(agents, '### 4. Execution-mode resolution (`__init__.py`) — read before touching `__init__.py` or `middleware.py` [human gate]'),
             'CLUSTER_MCP_SSH_HOST')
        need('§ Throwaway environment', section(agents, '### Throwaway environment'), 'CLUSTER_MCP_SSH_HOST', 'RCAC_SSH_HOST')
        blast = section(agents, '### High-blast-radius paths (human gate)')
        need('high-blast list', blast, f'{CORE}/deprecation.py')
    if phase >= 3:
        s8 = section(agents, '### 8. Resources and the `/etc/agents.d/*.md` convention (`resources.py`, `site.py`)')
        need('§8', s8, 'cluster://context', 'cluster://storage', 'alias', 'OPEN_RESOURCES')
    if phase >= 4:
        s9 = section(agents, '### 9. The agent-facing surface is part of the API (`server.py`) [human gate]')
        need('§9', s9, 'CORE_INSTRUCTIONS', 'RCAC_INSTRUCTIONS', 'SLURM_INSTRUCTIONS', 'rename-to-cluster-mcp')
    if phase >= 5:
        direction = section(agents, '### Direction — this is becoming `cluster-mcp`') or section(agents, '### Direction')
        if 'Rename and generalize' in direction:
            found.append('AGENTS.md § Direction still lists the rename as future work')
        if 'mid-generalization' in section(agents, '## Invariants') and 'from `rcac-mcp` to `cluster-mcp` (see' in agents:
            found.append('AGENTS.md § Invariants preface still says the rename is in progress')
    return found


CHECKS = {
    'source': check_source, 'imports': check_imports, 'env': check_env, 'uris': check_uris,
    'uris-p3': lambda r: check_uris(r, False), 'urls': check_urls, 'spdx': check_spdx, 'ci': check_ci, 'readme': check_readme,
    'ledger': check_ledger, 'container': check_container, 'profile': lambda r: check_profile(r, False),
    'profile-final': lambda r: check_profile(r, True),
    **{f'docs-p{n}': (lambda r, n=n: check_docs(r, n)) for n in range(1, 6)},
}


# ---- controls: one plant per check, each must be rejected -------------------------------------

def _plant(path: str, old: str | None, new: str):
    def edit(root: Path) -> bool:
        p = root / path
        if old is None:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(new)
            return True
        body = p.read_text() if p.exists() else ''
        if old not in body:
            return False
        p.write_text(body.replace(old, new, 1))
        return True
    return edit


PLANTS = [
    ('source', _plant('packages/cluster-mcp-rcac/src/cluster_mcp/__init__.py', None, ''), 'namespace __init__'),
    ('source', _plant('packages/cluster-mcp-slurm/pyproject.toml', 'version = "', 'version = "9'), 'one version'),
    ('source', _plant('pyproject.toml', 'cluster_mcp.core:legacy_main', 'cluster_mcp.core:main'), 'legacy_main'),
    ('imports', _plant(f'{CORE}/site.py', '\n', '\nimport rcac_mcp\n'), 'rcac_mcp survives'),
    ('env', _plant(f'{CORE}/site.py', '\n', "\nX = os.environ.get('RCAC_SSH_HOST')\n"), 'outside the window'),
    ('env', _plant(f'{CORE}/site.py', '\n', "\nX = os.environ.get('CLUSTER_MCP_SSH_HOST')\n"), 'directly'),
    ('env', _plant('bin/sandbox.sh', 'unset CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST', 'unset CLUSTER_MCP_SSH_HOST'), 'does not unset RCAC_SSH_HOST'),
    ('env', _plant('bin/sandbox.sh', 'UV_NO_ENV_FILE', 'UV_NO_ENV'), 'UV_ENV_FILE'),
    ('env', _plant('tests/conftest.py', "'CLUSTER_MCP_SSH_HOST'", "'CLUSTER_MCP_SSH_HOSTX'"), 'BLANKED_ENV'),
    ('container', _plant('Dockerfile', 'ENTRYPOINT ["cluster-mcp"]', 'ENTRYPOINT ["rcac-mcp"]'), 'ENTRYPOINT'),
    ('container', _plant('Dockerfile', 'COPY packages/', 'COPY src/'), 'not in the tree'),
    ('container', _plant('compose.yml', 'container_name: cluster-mcp', 'container_name: rcac-mcp'), 'container_name'),
    ('urls', _plant('README.md', '\n', '\nhttps://github.com/PurdueRCAC/rcac-mcp\n'), 'old repository URL'),
    ('readme', _plant('README.md', '\n', '\nuvx --from git+https://github.com/PurdueRCAC/cluster-mcp rcac-mcp\n'), 'runs rcac-mcp outside'),
    ('uris', _plant(f'{CORE}/server.py', '\n', "\nU = 'rcac://context'\n"), 'outside the aliases'),
    ('uris', _plant(f'{CORE}/resources.py', '\n', "\nU = 'rcac://storage'\n"), 'derived'),
    ('urls', _plant('SECURITY.md', '\n', '\nhttps://github.com/purduercac/rcac-mcp\n'), 'old repository URL'),
    ('urls', _plant('SECURITY.md', '\n', '\nhttps://github.com/purduercac/cluster-mcp\n'), 'not github.com/PurdueRCAC'),
    ('spdx', _plant(f'{CORE}/site.py', HEADER, 'SPDX-FileCopyrightText: 2025 Purdue University'), 'is not'),
    ('spdx', _plant(f'{CORE}/site.py', LICENSE, 'SPDX-License-Identifier: Apache-2.0'), 'is not'),
    ('spdx', _plant(f'{CORE}/new_module.py', None, '"""No header."""\n'), 'no SPDX header'),
    ('ci', _plant('.github/workflows/ci.yml', '      - run: uv lock --check\n', ''), 'ci.yml gate runs'),
    ('readme', _plant('README.md', 'removed no earlier than 0.4.0', 'removed in 0.4.0'), 'as the warnings do'),
    ('ledger', _plant('ROADMAP.md', f'**Seed:** [`{SEED}`]({SEED})', '**Seed:** [`issues/x.md`](issues/x.md)'), 'ROADMAP.md has no entry'),
]


def controls(root: Path, only: list[str]) -> list[str]:
    problems = []
    with tempfile.TemporaryDirectory(prefix='rename-controls-') as tmp:
        for name, plant, fragment in PLANTS:
            if only and name not in only:
                continue
            copy = Path(tmp) / f'{name}-{len(problems)}-{abs(hash(fragment)) % 10**6}'
            shutil.copytree(root, copy, ignore=shutil.ignore_patterns(*SKIP_DIRS), symlinks=True)
            subprocess.run(['git', '-C', str(copy), 'init', '-q'], check=True)
            subprocess.run(['git', '-C', str(copy), 'add', '-A'], check=True)
            if CHECKS[name](copy):
                problems.append(f'control {name}: the unplanted copy already fails, so the plant proves nothing')
                continue
            if not plant(copy):
                problems.append(f'control {name} ({fragment}): the plant anchor is missing')
                continue
            subprocess.run(['git', '-C', str(copy), 'add', '-A'], check=True)
            found = CHECKS[name](copy)
            if not any(fragment in v for v in found):
                problems.append(f'control {name}: the plant ({fragment}) passed: {found[:2]}')
            else:
                print(f'ok   control {name}: {fragment}')
            shutil.rmtree(copy)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='.')
    ap.add_argument('checks', nargs='+')
    args = ap.parse_args()
    root = Path(args.root).resolve()
    problems = []
    if args.checks[0] == 'wheels':
        problems = check_wheels(Path(args.checks[1]))
        print(f"{'ok  ' if not problems else 'FAIL'} wheels", file=sys.stderr)
    elif args.checks[0] == 'controls':
        problems = controls(root, args.checks[1:])
    else:
        for name in args.checks:
            if name not in CHECKS:
                print(f'checks: unknown check {name}', file=sys.stderr)
                return 2
            found = CHECKS[name](root)
            print(f"{'ok  ' if not found else 'FAIL'} {name}", file=sys.stderr)
            problems += found
    for p in problems:
        print(f'checks: {p}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
