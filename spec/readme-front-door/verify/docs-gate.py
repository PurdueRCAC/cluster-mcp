"""Frozen gates of readme-front-door: the README is a front door, the rest one level down.

Run from the cycle worktree root, after staging (every check reads the index, the GOAL's baseline
or the cycle's base, never the working copy):

    UV_PYTHON=3.14 uv run --with pyyaml python -I spec/readme-front-door/verify/docs-gate.py MODE ...

Modes, each one group of requirements:

  readme    R1, R2: README.md's level-2 sections, in order and no others; an opening of two or three
            sentences; Quick Start's one client configuration, one install line and one link to where
            docs/core/README.md says how to raise the client's limit; the capabilities table (a row
            each for the core and the two extras, each linking its docs page, the [rcac] row linking
            the documentation service); the run-modes table (ssh, local, delegate, each linking
            SECURITY.md); at most 120 lines; no figure outside § Upgrading from rcac-mcp, and that
            section the baseline's, byte for byte.
  pages     R3, R4's lists, R5's headings: each docs page has its Tools, What it needs on the cluster
            and How it behaves sections; every tool of EXPECTED_TOOLS on exactly one docs page, its
            member's, one list line each; each member's declared commands in its needs section; every
            line of docs/core/README.md stating a figure is in a list or a table; SECURITY.md's three
            hosting headings; every relative or repository link on every page resolves, anchors
            included; no HTML comment hides text on any page.
  facts     R4, R5, R6: the fact map (facts.yaml), as its header says; and every baseline SECURITY.md
            line outside its overview (lines 6-14) is still a line of SECURITY.md.
  packages  R7: each package README links its docs page and never the repository README.
  agents    R8: AGENTS.md § Documentation; §9 and every moved reference name the new home.
  paths     R9: the cycle changes only its pages, AGENTS.md, the two repointed tests, the comment in
            tests/test_registry.py and its spec; each repointed test differs from the base only in
            the path it reads.
  all       readme, pages, facts, packages, agents and paths, in that order.

Several modes may be named in one call; each prints its own `ok` or `red` line, and the call exits
non-zero when any is red.
  prepush   Before the push: a clean tree, no site-private text in the cycle's added lines (but the
            example hosts and addresses the baseline pages carry, Q4), and the deferral ledger.
  controls  Every decision above run on planted data: each plant refused for its reason, the sound
            data accepted.

Footprint: one Python process and one git child at a time; `pages` imports the installed package
to read each member's tools and commands. That import is the one read of the working copy (the
install is editable); `paths` refuses any change under `packages/*/src/`, and P2's `prepush` refuses
a working copy that differs from the index, so the two agree. Under 150 MB. Measured on a development host: each mode
under 5 s, `all` under 10 s.
"""

from __future__ import annotations

import ast
import posixpath
import re
import subprocess
import sys
from pathlib import Path

import yaml

SLUG = 'readme-front-door'
HERE = Path(__file__).resolve().parent
# The GOAL's baseline: the text every fact is quoted from.
FACT_BASE = '2719b7a'
# The cycle's start, found by the shape commit's subject on HEAD's history, so a rebase cannot leave
# the path check measuring from a commit that is no longer the cycle's base.
SHAPE_SUBJECT = f'[docs] Shape {SLUG} goal'

MEMBERS = ('core', 'slurm', 'rcac')
DOCS = {m: f'docs/{m}/README.md' for m in MEMBERS}
PACKAGES = {'core': 'packages/cluster-mcp/README.md', 'slurm': 'packages/cluster-mcp-slurm/README.md',
            'rcac': 'packages/cluster-mcp-rcac/README.md'}
PAGES = ('README.md', 'SECURITY.md', *DOCS.values(), *PACKAGES.values())

README_SECTIONS = ('Quick Start', 'Capabilities', 'Run modes', 'Upgrading from rcac-mcp', 'Development', 'License')
UPGRADING = 'Upgrading from rcac-mcp'
MAX_LINES = 120
DOCS_SECTIONS = ('Tools', 'What it needs on the cluster', 'How it behaves')
HOSTING = ('Basic HTTP Server', 'With JWT Authentication', 'Docker Compose with TLS')
REPO_URL = 'https://github.com/PurdueRCAC/cluster-mcp'

# A figure, as R2 and R4 name them: any digit; a number word before a unit of time or size; a
# multiple ("three times", "twice"); a signal name; the exit code `-N`.
UNITS = (r's|ms|sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|millisecond|milliseconds|byte|bytes|'
         r'kilobyte|kilobytes|KB|MB|KB/s|character|characters')
TENS = r'twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety'
NUMBER_WORDS = (rf'(?:(?:{TENS})(?:-(?:one|two|three|four|five|six|seven|eight|nine))?|one|two|three|four|five|six|seven|'
                r'eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|hundred|'
                r'thousand|half a|a few)')
FIGURES = ((re.compile(r'\d'), 'a digit'),
           (re.compile(rf'\b{NUMBER_WORDS}[ -](?:{UNITS})\b', re.I), 'a number word with a unit'),
           # "a second" as a span of time ("has a second to finish", "KILL a second later"), not an ordinal.
           (re.compile(r'\b(a|an)\s+(second|minute|hour)\b(?=\s*(?:[,.;:)]|$|to\b|later\b|after\b|before\b|of\b|'
                       r'and\b|or\b|until\b|in\b|for\b))', re.I), 'a number word with a unit'),
           (re.compile(r'\b(twice|thrice|(two|three|four|five|ten|\w+-fold) times)\b', re.I), 'a multiple'),
           (re.compile(r'\b(TERM|KILL|HUP|INT|QUIT|USR1|USR2)\b'), 'a signal name'),
           (re.compile(r'\bSIG[A-Z0-9]+\b', re.I), 'a signal name'),
           (re.compile(r'(?<![\w-])-N\b'), 'the exit code -N'))

ALLOWED_PATHS = {'README.md', 'SECURITY.md', 'AGENTS.md', *DOCS.values(), *PACKAGES.values(),
                 'tests/test_ssh_liveness.py', 'tests/test_ssh_exec.py', 'tests/test_registry.py'}
# Each repointed test and how many reads of the README it makes at the base.
REPOINTED = {'tests/test_ssh_liveness.py': 1, 'tests/test_ssh_exec.py': 2}
COMMENT_ONLY = ('tests/test_registry.py',)

# AGENTS.md text that names a README section this cycle moves: at the base, present; on the branch, gone.
AGENTS_GONE = (
    "commit as its capability's instructions text and the README (§ Invariants §9)",
    'which only the README points to',
    'AGENTS §2, the README and `Executor.write`',
    "footgun and the README to the monitor's figures",
    'this section, the README, the `run_command` description',
    'documented in `README.md` § *Docker Compose with TLS*',
    "the README's install note says the same",
    'same same-commit rule as the instructions texts and the README',
    'The same commit also updates the tool inventory in `README.md`',
)
# Where each now points: (a phrase that finds the block, what the block must now name).
AGENTS_NEW = (
    ('`EXPECTED_TOOLS` is hard-coded', 'docs/'),
    ('separate `rcac-docs-mcp` service', 'docs/rcac/README.md'),
    ('test_content_texts_state_the_sftp_route', 'docs/core/README.md'),
    ('The doc pin holds the', 'docs/core/README.md'),
    ('test_separation_texts_state_the_remote_rc_exception', 'docs/core/README.md'),
    ('Docker Compose with TLS', 'SECURITY.md'),
    ('install note', 'docs/core/README.md'),
    ('`compose.yml` pins the', 'docs/'),
)
# A block outside § Documentation may still name the README when it is about what the README keeps.
AGENTS_KEEP = ('upgrading', 'repo_files', 'readme line', "first line is the readme's", 'sdist takes only',
               'short `readme.md`', 'with `[slurm]`', '`[rcac]` row', 'deprecation_window', 'window')
DOCUMENTATION_TERMS = ('README.md', 'docs/', 'SECURITY.md', 'short sentences', 'list or table', 'issues/',
                       'AGENTS.md', 'hurt', 'figure')

PRIVATE = [(r'\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', 'an IP address'),
           (r'\b[\w-]+(\.[\w-]+)*\.purdue\.edu\b', 'a site hostname'), (r'\.secur' r'ity/', 'a security-lane path'),
           (r'(?<![\w.+\\-])(?!git@)[\w.+-]+@[\w-]+(\.[\w-]+)+', 'an email address'),
           (r'/(Users|home)/(?!runner/)\w', 'a home path'), (r'/(private/tmp|var/folders)/', 'a host temporary path'),
           (r'~/K' r'B\b', "the operator's KB path"), (r'/scratch/\w', 'a cluster scratch path')]
SPEC_ID = r'(?<![A-Za-z0-9])([RPQF]\d{1,2}|F-[A-Z])(?![A-Za-z0-9])'
PHRASES = ('do not fix here', 'known limitation', 'left as a follow-up', 'follow-up', 'deferred', 'deferral',
           'not fixed')


# --- git --------------------------------------------------------------------------------------------

def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout


def staged(path: str) -> str:
    return git('show', f':{path}')


def at(rev: str, path: str) -> str:
    return git('show', f'{rev}:{path}')


def indexed() -> set[str]:
    return set(git('ls-files').splitlines())


def diff_base() -> str:
    log = git('log', '--format=%H%x00%s', 'HEAD')
    found = [h for h, _, subject in (line.partition('\0') for line in log.splitlines()) if subject == SHAPE_SUBJECT]
    if len(found) != 1:
        raise SystemExit(f'docs-gate.py: {len(found)} commits on HEAD carry the subject {SHAPE_SUBJECT!r}, expected one')
    return git('rev-parse', f'{found[0]}^').strip()


# --- Markdown, as read here ---------------------------------------------------------------------------

LINK = re.compile(r'\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^()\s]*(?:\([^()]*\)[^()\s]*)*)\)')
SPAN = re.compile(r'(`+)(.+?)\1')


def fenced(text: str) -> list[bool]:
    """For each line of `text`, whether it is a fence marker or inside a fenced block."""
    out, fence = [], None
    for line in text.splitlines():
        marker = re.match(r'\s*(```+|~~~+)', line)
        if fence is None and marker:
            fence = marker.group(1)[0] * 3
            out.append(True)
        elif fence is not None:
            out.append(True)
            if line.strip().startswith(fence):
                fence = None
        else:
            out.append(False)
    return out


def headings(text: str) -> list[tuple[int, int, str]]:
    """Every ATX heading outside a fence: (line index, level, title)."""
    out = []
    for i, (line, inside) in enumerate(zip(text.splitlines(), fenced(text))):
        m = re.match(r'(#{1,6})\s+(.*?)\s*#*\s*$', line)
        if m and not inside:
            out.append((i, len(m.group(1)), m.group(2)))
    return out


def sections(text: str, level: int = 2) -> list[tuple[str | None, str]]:
    """`text` cut at every heading of `level` or above: (title, text), the lead first with title None."""
    lines = text.splitlines()
    cuts = [(i, title) for i, lvl, title in headings(text) if lvl <= level]
    out, start, title = [], 0, None
    for i, next_title in cuts:
        out.append((title, '\n'.join(lines[start:i])))
        start, title = i, next_title
    out.append((title, '\n'.join(lines[start:])))
    return out


def section(text: str, title: str, level: int = 2) -> str | None:
    found = [body for t, body in sections(text, level) if t == title]
    return found[0] if len(found) == 1 else None


def plain_title(title: str) -> str:
    return LINK.sub(r'\1', title).replace('`', '').replace('*', '')


def slugs(text: str) -> dict[str, str]:
    """GitHub's anchor for every heading of `text`, mapped to the heading's section (to the next heading of its level or above)."""
    out: dict[str, str] = {}
    seen: dict[str, int] = {}
    lines = text.splitlines()
    found = headings(text)
    for n, (i, level, title) in enumerate(found):
        slug = re.sub(r'[^\w\- ]', '', plain_title(title).strip().lower()).replace(' ', '-')
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        end = next((j for j, lvl, _ in found[n + 1:] if lvl <= level), len(lines))
        out[slug if count == 0 else f'{slug}-{count}'] = '\n'.join(lines[i:end])
    return out


def links(text: str) -> list[tuple[str, str]]:
    """Every inline link outside a fence: (text, target)."""
    keep = '\n'.join(line for line, inside in zip(text.splitlines(), fenced(text)) if not inside)
    return [(m.group(1), m.group(2)) for m in LINK.finditer(keep)]


def norm(text: str) -> str:
    """The text a phrase is matched in: links read as text and target, no backticks or `*`, whitespace collapsed."""
    text = LINK.sub(r'\1 \2', text).replace('`', '').replace('*', '')
    return ' '.join(text.split())


def holds(text: str, phrase: str) -> bool:
    """Whether normalised `text` holds `phrase` whole: not inside a longer word or number; case kept when the phrase holds two capitals in a row."""
    phrase = norm(phrase)
    flags = 0 if re.search(r'[A-Z]{2}', phrase) else re.I
    return re.search(rf'(?<![\w.]){re.escape(phrase)}(?!\w)', text, flags) is not None


def no_targets(line: str) -> str:
    return LINK.sub(r'\1', line)


def figures_in(line: str) -> list[str]:
    line = no_targets(line)
    return [what for pattern, what in FIGURES if pattern.search(line)]


def sentences(text: str) -> int:
    body = SPAN.sub('x', LINK.sub(r'\1', text))
    return len([s for s in re.split(r'(?<=[.!?])\s+', ' '.join(body.split())) if s.strip()])


def table_rows(text: str) -> list[str]:
    """The body rows of the first table in `text` (the lines after its delimiter)."""
    rows = [line.strip() for line in text.splitlines() if line.strip().startswith('|')]
    if len(rows) < 2 or not re.fullmatch(r'[|:\- ]+', rows[1]):
        return []
    return rows[2:]


def hidden_comment(text: str) -> bool:
    keep = '\n'.join(line for line, inside in zip(text.splitlines(), fenced(text)) if not inside)
    return '<!--' in SPAN.sub('', keep)


def table_lines(text: str) -> set[int]:
    """The indexes of the lines of every table in `text`: a run of `|` lines whose second line is a delimiter."""
    lines, out, i = text.splitlines(), set(), 0
    while i < len(lines):
        j = i
        while j < len(lines) and lines[j].lstrip().startswith('|'):
            j += 1
        if j - i >= 2 and re.fullmatch(r'[|:\- ]+', lines[i + 1].strip()):
            out.update(range(i, j))
        i = max(j, i + 1)
    return out


def list_lines(text: str) -> list[bool]:
    """For each line, whether it belongs to a list item (its marker line, an indented or lazy continuation) or a table."""
    out, in_item, blank = [], False, False
    tables = table_lines(text)
    for n, line in enumerate(text.splitlines()):
        if not line.strip():
            out.append(False)
            blank = True
            continue
        if n in tables:
            in_item = False
            out.append(True)
        elif re.match(r'\s{0,3}#{1,6}\s', line) or line.lstrip().startswith(('|', '>')):
            in_item = False
            out.append(False)
        else:
            if re.match(r'\s*([-*+]|\d+[.)])\s', line):
                in_item = True
            elif blank:
                in_item = in_item and line.startswith(('  ', '\t'))
            out.append(in_item)
        blank = False
    return out


# --- readme -----------------------------------------------------------------------------------------

def fences(text: str) -> list[tuple[str, str]]:
    """Every fenced block of `text`: (its info string, its body)."""
    out, current, lang, fence = [], [], '', ''
    for line in text.splitlines():
        m = re.match(r'\s*(```+|~~~+)\s*(\S*)', line)
        if not fence and m:
            fence, lang, current = m.group(1), m.group(2), []
        elif fence and line.strip().startswith(fence) and not line.strip().strip(fence[0]):
            out.append((lang, '\n'.join(current)))
            fence = ''
        elif fence:
            current.append(line)
    return out


def readme_violations(text: str, core: str | None, rcac: str | None, base: str | None = None) -> list[str]:
    found = []
    if base is not None and (section(text, UPGRADING) or '').rstrip() != (section(base, UPGRADING) or '').rstrip():
        found.append(f'README.md: § {UPGRADING} is not the baseline section, byte for byte')
    if len(text.splitlines()) > MAX_LINES:
        found.append(f'README.md: {len(text.splitlines())} lines, more than {MAX_LINES}')
    titles = tuple(title for _, level, title in headings(text) if level == 2)
    if titles != README_SECTIONS:
        found.append(f'README.md: level-2 sections {titles}, not {README_SECTIONS}')
    firsts = [title for _, level, title in headings(text) if level == 1]
    if len(firsts) != 1 or not text.startswith('# '):
        found.append('README.md: does not open with its one level-1 title')
    opening = [body for title, body in sections(text) if firsts and title == firsts[0]]
    lead = opening[0].split('\n', 1)[1] if opening and '\n' in opening[0] else ''
    count = sentences(lead)
    if not 2 <= count <= 3:
        found.append(f'README.md: the opening is {count} sentences, not two or three')
    for title, body in sections(text):
        if title == UPGRADING:
            continue
        for line in body.splitlines():
            for what in figures_in(line):
                found.append(f'README.md: {what} outside § {UPGRADING}: {line.strip()[:100]}')
    quick = section(text, 'Quick Start') or ''
    blocks = fences(quick)
    configs = [body for lang, body in blocks if 'mcpServers' in body]
    if len(configs) != 1:
        found.append(f'README.md: Quick Start holds {len(configs)} client configurations, not one')
    installs = [line for lang, body in blocks if 'mcpServers' not in body for line in body.splitlines()
                if re.match(r'\s*(uvx|uv tool install|uv pip install|pip install|pipx)\b', line)]
    if len(installs) != 1:
        found.append(f'README.md: Quick Start holds {len(installs)} install lines, not one')
    limit = [target for _, target in links(quick) if target.startswith(f'{DOCS["core"]}#')]
    if len(limit) != 1:
        found.append(f'README.md: Quick Start links {len(limit)} anchors of {DOCS["core"]}, not one (the client\'s limit)')
    elif core is not None:
        target = slugs(core).get(limit[0].split('#', 1)[1])
        if target is None or 'CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH' not in target:
            found.append(f'README.md: Quick Start\'s {limit[0]} is not where {DOCS["core"]} says how to raise the client\'s limit')
    rows = table_rows(section(text, 'Capabilities') or '')
    if len(rows) != 3:
        found.append(f'README.md: the capabilities table has {len(rows)} rows, not three')
    else:
        for member, row in zip(MEMBERS, rows):
            targets = [t.split('#', 1)[0] for _, t in links(row)]
            if DOCS[member] not in targets:
                found.append(f'README.md: the capabilities row for {member} does not link {DOCS[member]}')
        anchors = [t for _, t in links(rows[2]) if t.startswith(f'{DOCS["rcac"]}#')]
        service = [t for t in anchors if 'rcac-docs-mcp' in (slugs(rcac or '').get(t.split('#', 1)[1]) or '')]
        if not service:
            found.append(f'README.md: the [rcac] row does not link the documentation service on {DOCS["rcac"]}')
    rows = table_rows(section(text, 'Run modes') or '')
    modes = [re.findall(r'`([^`]+)`', row.strip('|').split('|')[0])[:1] for row in rows]
    if modes != [['ssh'], ['local'], ['delegate']]:
        found.append(f'README.md: the run-modes table rows are {modes}, not ssh, local, delegate')
    for row in rows:
        if not any(t.split('#', 1)[0] == 'SECURITY.md' for _, t in links(row)):
            found.append(f'README.md: a run-modes row does not link SECURITY.md: {row[:80]}')
    return found


def staged_or_none(path: str) -> str | None:
    try:
        return staged(path)
    except subprocess.CalledProcessError:
        return None


def mode_readme() -> list[str]:
    text = staged_or_none('README.md') or ''
    return readme_violations(text, staged_or_none(DOCS['core']), staged_or_none(DOCS['rcac']), at(FACT_BASE, 'README.md'))


# --- pages ------------------------------------------------------------------------------------------

def member_tools() -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """Each member's tools and declared commands, from the installed package (its source is unchanged, R9)."""
    from cluster_mcp.core.capabilities import installed
    from cluster_mcp.core.tools import CORE_TOOLS
    tools = {'core': tuple(t.name for t in CORE_TOOLS)}
    commands: dict[str, tuple[str, ...]] = {'core': ()}
    for loaded in installed():
        tools[loaded.capability.name] = tuple(t.name for t in loaded.tools)
        commands[loaded.capability.name] = tuple(loaded.capability.commands)
    return tools, commands


def expected_tools(source: str) -> set[str]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, 'id', '') == 'EXPECTED_TOOLS':
            return set(ast.literal_eval(node.value.args[0]))
    raise SystemExit('docs-gate.py: no EXPECTED_TOOLS in tests/test_registry.py')


def listed_tools(page: str) -> tuple[list[str], list[str]]:
    """The tool named by each list line of the page's Tools section, and every list line naming none."""
    body = section(page, 'Tools') or ''
    names, bad = [], []
    for line in body.splitlines():
        if not re.match(r'\s*[-*+]\s', line):
            continue
        m = re.match(r'\s*[-*+]\s+`([a-z_][a-z0-9_]*)(\([^`]*\))?`', line)
        (names.append(m.group(1)) if m else bad.append(line.strip()[:80]))
    return names, bad


def tools_violations(pages: dict[str, str], expected: set[str], tools: dict[str, tuple[str, ...]],
                     commands: dict[str, tuple[str, ...]]) -> list[str]:
    found = []
    if expected != {t for names in tools.values() for t in names}:
        found.append(f'EXPECTED_TOOLS {sorted(expected)} is not the set the members register')
    seen: dict[str, list[str]] = {}
    for member, page in pages.items():
        for title in DOCS_SECTIONS:
            if section(page, title) is None:
                found.append(f'{DOCS[member]}: no single § {title}')
        names, bad = listed_tools(page)
        found += [f'{DOCS[member]}: a Tools list line names no tool: {line}' for line in bad]
        for name in names:
            seen.setdefault(name, []).append(member)
        needs = section(page, 'What it needs on the cluster') or ''
        for command in commands.get(member, ()):
            if f'`{command}`' not in needs:
                found.append(f'{DOCS[member]}: § What it needs on the cluster does not name `{command}`')
        if member == 'core' and '/bin/bash' not in needs:
            found.append(f'{DOCS["core"]}: § What it needs on the cluster does not name the login bash')
    for member, names in tools.items():
        for name in names:
            where = seen.get(name, [])
            if where != [member]:
                found.append(f'tool {name}: listed on {[DOCS[m] for m in where]}, expected once, on {DOCS[member]}')
    for name in sorted(set(seen) - expected):
        found.append(f'tool {name}: listed on {[DOCS[m] for m in seen[name]]} but not registered')
    return found


def figure_violations(path: str, text: str) -> list[str]:
    found = []
    for line, listed in zip(text.splitlines(), list_lines(text)):
        if listed:
            continue
        for what in figures_in(line):
            found.append(f'{path}: {what} outside a list or table: {line.strip()[:100]}')
    return found


def link_violations(path: str, text: str, files: set[str], read) -> list[str]:
    found = []
    base = posixpath.dirname(path)
    for _, target in links(text):
        if target.startswith(('mailto:', 'http://')) or (target.startswith('https://') and not target.startswith(REPO_URL)):
            continue
        if target.startswith(REPO_URL):
            m = re.match(rf'{re.escape(REPO_URL)}/(?:blob|tree)/[^/]+/([^#?]+)(?:#(.*))?$', target)
            if not m:
                continue
            ref, anchor = m.group(1), m.group(2)
        else:
            ref, _, anchor = target.partition('#')
            ref = posixpath.normpath(posixpath.join(base, ref)) if ref else path
        if ref not in files and not any(f.startswith(ref.rstrip('/') + '/') for f in files):
            found.append(f'{path}: link {target} resolves to {ref}, which is not in the tree')
            continue
        if anchor and ref.endswith('.md') and anchor not in slugs(read(ref)):
            found.append(f'{path}: link {target}: {ref} has no heading #{anchor}')
    return found


def mode_pages() -> list[str]:
    found = []
    files = indexed()
    pages = {m: staged_or_none(p) for m, p in DOCS.items()}
    for member, page in pages.items():
        if page is None:
            found.append(f'{DOCS[member]}: not in the index')
    pages = {m: p for m, p in pages.items() if p is not None}
    tools, commands = member_tools()
    found += tools_violations(pages, expected_tools(staged('tests/test_registry.py')), tools, commands)
    if 'core' in pages:
        found += figure_violations(DOCS['core'], pages['core'])
    security = staged('SECURITY.md')
    titles = [plain_title(title) for _, _, title in headings(security)]
    for title in HOSTING:
        if titles.count(title) != 1:
            found.append(f'SECURITY.md: {titles.count(title)} headings {title!r}, expected one')
    for path in PAGES:
        text = staged_or_none(path)
        if text is None:
            continue
        found += link_violations(path, text, files, staged)
        if hidden_comment(text):
            found.append(f'{path}: an HTML comment outside code hides text from a reader')
    return found


# --- facts ------------------------------------------------------------------------------------------

def load_facts(text: str) -> list[dict]:
    return yaml.safe_load(text)['facts']


def src_lines(src: str) -> tuple[str, int, int]:
    path, _, span = src.partition(':')
    first, _, last = span.partition('-')
    return path, int(first), int(last or first)


def mapped_line(line: str, inside: bool) -> bool:
    """Whether a baseline line states something the map must place (not blank, a heading, a fence marker or a table delimiter)."""
    stripped = line.strip()
    if not stripped or re.fullmatch(r'(```+|~~~+)\w*', stripped) or re.fullmatch(r'[|:\- ]+', stripped):
        return False
    return inside or not re.match(r'#{1,6}\s', stripped)


def facts_violations(facts: list[dict], baseline: dict[str, str], dest_text, docs_links: set[str]) -> list[str]:
    found = []
    covered: dict[str, set[int]] = {path: set() for path in baseline}
    for fact in facts:
        path, first, last = src_lines(fact['src'])
        if path not in baseline:
            found.append(f'fact {fact["id"]}: src {path} is not a baseline page')
            continue
        lines = baseline[path].splitlines()
        covered[path].update(range(first, last + 1))
        source = norm('\n'.join(lines[first - 1:last]))
        for phrase in fact['phrases']:
            if not holds(source, phrase):
                found.append(f'fact {fact["id"]}: {phrase!r} is not in the baseline {fact["src"]}')
        dest = fact['dest']
        text = dest_text(dest)
        if text is None:
            found.append(f'fact {fact["id"]}: its home {dest} is not in the index')
            continue
        homes = [norm(body) for _, body in sections(text)]
        whole = norm(text)
        missing = [p for p in fact['phrases'] if not holds(whole, p)]
        if missing:
            found.append(f'fact {fact["id"]}: {dest} does not state {missing}')
        elif not any(all(holds(home, p) for p in fact['phrases']) for home in homes):
            found.append(f'fact {fact["id"]}: {dest} states its phrases, but not inside one level-2 section')
        marks = fenced(baseline[path])
        dest_lines = {line.strip() for line in text.splitlines()}
        for n in range(first, last + 1):
            line = lines[n - 1]
            if marks[n - 1] and line.strip() and not re.fullmatch(r'(```+|~~~+)\w*', line.strip()) \
                    and line.strip() not in dest_lines:
                found.append(f'fact {fact["id"]}: {dest} does not carry the baseline code line {path}:{n} verbatim: '
                             f'{line.strip()[:80]}')
        if dest.startswith('issues/') and dest not in docs_links:
            found.append(f'fact {fact["id"]}: {dest} is linked from no docs page')
    for path, text in baseline.items():
        for n, (line, inside) in enumerate(zip(text.splitlines(), fenced(text)), start=1):
            if mapped_line(line, inside) and n not in covered[path]:
                found.append(f'{path}:{n} at the baseline is in no fact: {line.strip()[:80]}')
    return found


def docs_issue_links(pages: dict[str, str]) -> set[str]:
    out = set()
    for path, text in pages.items():
        for _, target in links(text):
            ref = posixpath.normpath(posixpath.join(posixpath.dirname(path), target.partition('#')[0]))
            if ref.startswith('issues/'):
                out.add(ref)
    return out


# SECURITY.md's overview (baseline lines 6-14), the one part R5 lets the move rewrite.
SECURITY_OVERVIEW = range(6, 15)


def security_violations(base: str, head: str) -> list[str]:
    """Every baseline SECURITY.md line outside its overview that the branch's SECURITY.md does not carry, stripped, as a line."""
    kept = {line.strip() for line in head.splitlines()}
    return [f'SECURITY.md: no longer carries baseline line {n}: {line.strip()[:80]}'
            for n, line in enumerate(base.splitlines(), start=1)
            if n not in SECURITY_OVERVIEW and line.strip() and line.strip() not in kept]


def mode_facts() -> list[str]:
    facts = load_facts(staged(f'spec/{SLUG}/verify/facts.yaml'))
    baseline = {p: at(FACT_BASE, p) for p in ('README.md', 'SECURITY.md')}
    pages = {p: t for p in DOCS.values() if (t := staged_or_none(p)) is not None}
    found = facts_violations(facts, baseline, staged_or_none, docs_issue_links(pages))
    return found + security_violations(baseline['SECURITY.md'], staged('SECURITY.md'))


# --- packages ---------------------------------------------------------------------------------------

def urls(text: str) -> list[str]:
    found = [m.group(2) for m in LINK.finditer(text)]
    found += re.findall(r'(?<![\w+(])https?://[^\s)<>\]\'"`]+', LINK.sub(r'\1', text))
    return found


ROOT_DOC = re.compile(rf'{re.escape(REPO_URL)}(/?(\?[^#]*)?(#.*)?|/(blob|tree)/[^/]+/?(README\.md)?(\?[^#]*)?(#.*)?)$'
                      r'|https://github\.com/PurdueRCAC/rcac-mcp(/.*)?$', re.I)


def package_violations(member: str, path: str, text: str) -> list[str]:
    found = []
    targets = urls(text)
    want = re.compile(rf'{re.escape(REPO_URL)}/(blob|tree)/[^/]+/docs/{member}/README\.md(#[\w-]+)?$')
    if not any(want.match(t) for t in targets):
        found.append(f'{path}: does not link {DOCS[member]} by its repository URL')
    for t in targets:
        if ROOT_DOC.match(t) or posixpath.normpath(posixpath.join(posixpath.dirname(path), t)) == 'README.md':
            found.append(f'{path}: links the repository README: {t}')
    if re.search(r"repository'?s README", text, re.I):
        found.append(f"{path}: still calls the repository's README its documentation")
    return found


def mode_packages() -> list[str]:
    found = []
    for member, path in PACKAGES.items():
        found += package_violations(member, path, staged(path))
    return found


# --- agents -----------------------------------------------------------------------------------------

def blocks(text: str) -> list[str]:
    """Prose paragraphs and list items; Markdown headings and rules are never a block."""
    out, current = [], []
    for line in text.splitlines():
        stripped = line.strip()
        item = bool(re.match(r'([-*]|\d+\.)\s', stripped))
        if not stripped or stripped.startswith('#') or stripped == '---' or item:
            if current:
                out.append(' '.join(current))
            current = [stripped] if item else []
            continue
        current.append(stripped)
    if current:
        out.append(' '.join(current))
    return out


def flat(text: str) -> str:
    return ' '.join(text.split())


def agents_violations(base: str, head: str) -> list[str]:
    found = []
    titles = [title for _, level, title in headings(head) if level == 2]
    if titles.count('Documentation') != 1:
        found.append(f'AGENTS.md: {titles.count("Documentation")} § Documentation sections, expected one')
    documentation = section(head, 'Documentation') or ''
    for term in DOCUMENTATION_TERMS:
        if term.casefold() not in documentation.casefold():
            found.append(f'AGENTS.md: § Documentation does not say {term!r}')
    nine = head[head.find('### 9. '):head.find('### Conventions')] if '### 9. ' in head else ''
    bullet = [b for b in blocks(nine) if 'The same commit also updates' in b]
    if len(bullet) != 1 or '`README.md`' in bullet[0] or 'docs/' not in bullet[0]:
        found.append("AGENTS.md: §9's same-commit bullet does not name the tool's docs page in place of README.md")
    for gone in AGENTS_GONE:
        if flat(gone) not in flat(base):
            found.append(f'AGENTS.md: {gone!r} is not in the base: the gate is stale')
        if flat(gone) in flat(head):
            found.append(f'AGENTS.md: still says {gone!r}')
    head_blocks = blocks(head)
    for finder, home in AGENTS_NEW:
        hits = [b for b in head_blocks if finder in b]
        if not hits or not any(home in b for b in hits):
            found.append(f'AGENTS.md: the text around {finder!r} does not name {home}')
    repo_map = section(head, 'Repository map') or ''
    if 'docs/' not in repo_map:
        found.append('AGENTS.md: § Repository map does not name docs/')
    outside = head.replace(documentation, '') if documentation else head
    for block in blocks(outside):
        bare = re.sub(r'(docs/\w+/|packages/[\w-]+/)README\.md', '', block)
        if re.search(r'(?<![\w/.-])README\b', bare) and not any(k in bare.casefold() for k in AGENTS_KEEP):
            found.append(f'AGENTS.md: names the README outside what it keeps: {block[:120]}')
    return found


def mode_agents() -> list[str]:
    return agents_violations(at(FACT_BASE, 'AGENTS.md'), staged('AGENTS.md'))


# --- paths ------------------------------------------------------------------------------------------

class PathBack(ast.NodeTransformer):
    """Maps a read of docs/core/README.md back to the base's read of README.md, counting each."""

    def __init__(self) -> None:
        self.moved = 0
        self.plain = 0

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        if isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == 'docs/core/README.md':
            self.moved += 1
            return ast.BinOp(left=self.visit(node.left), op=ast.Div(), right=ast.Constant('README.md'))
        self.generic_visit(node)
        if isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == 'README.md':
            left = node.left
            if (isinstance(left, ast.BinOp) and isinstance(left.op, ast.Div)
                    and isinstance(left.right, ast.Constant) and left.right.value == 'core'
                    and isinstance(left.left, ast.BinOp) and isinstance(left.left.op, ast.Div)
                    and isinstance(left.left.right, ast.Constant) and left.left.right.value == 'docs'):
                self.moved += 1
                return ast.BinOp(left=left.left.left, op=ast.Div(), right=ast.Constant('README.md'))
            self.plain += 1
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """A label naming the file (`'docs/core/README.md'` as a dict key) maps back to the base's label."""
        return ast.Constant('README.md') if node.value == 'docs/core/README.md' else node


def repoint_violations(path: str, base: str, head: str, reads: int) -> list[str]:
    back = PathBack()
    mapped = back.visit(ast.parse(head))
    found = []
    if back.plain:
        found.append(f'{path}: still reads README.md {back.plain} time(s)')
    if back.moved != reads:
        found.append(f'{path}: reads {DOCS["core"]} {back.moved} time(s), expected {reads} (one per README read at the base)')
    if ast.dump(mapped) != ast.dump(ast.parse(base)):
        found.append(f'{path}: differs from the base in more than the path it reads')
    return found


def paths_violations(changed: list[str], read_base, read_head) -> list[str]:
    found = []
    for path in changed:
        if path in ALLOWED_PATHS or path.startswith(f'spec/{SLUG}/'):
            continue
        why = ('a package source (R9)' if re.match(r'packages/[^/]+/src/', path) else
               'the served-surface fixture (R9)' if path == 'tests/fixtures/served_surface.json' else
               'a non-goal' if path in ('INSTRUCTIONS.md', 'compose.yml', 'ROADMAP.md') or path.startswith('issues/') else
               'outside the cycle')
        found.append(f'{path}: changed, {why}')
    for path, reads in REPOINTED.items():
        found += repoint_violations(path, read_base(path), read_head(path), reads)
    for path in COMMENT_ONLY:
        if ast.dump(ast.parse(read_base(path))) != ast.dump(ast.parse(read_head(path))):
            found.append(f'{path}: changes more than a comment')
    return found


def mode_paths() -> list[str]:
    base = diff_base()
    changed = git('diff', '--cached', '--name-only', '--no-renames', base).splitlines()
    return paths_violations(changed, lambda p: at(base, p), staged)


# --- prepush ----------------------------------------------------------------------------------------

def added_lines(base: str) -> list[tuple[str, str]]:
    current, lines = '', []
    for line in git('diff', '--cached', '-U0', '--no-color', base).splitlines():
        if line.startswith('+++ b/'):
            current = line[6:]
        elif line.startswith('+') and not line.startswith('+++'):
            lines.append((current, line[1:]))
    return lines


def private_violations(lines: list[tuple[str, str]], carried: str) -> list[str]:
    """Site-private text in `lines`, but a match the baseline pages `carried` hold as the same match (Q4)."""
    found = []
    allowed = {m.group(0) for pattern, _ in PRIVATE for m in re.finditer(pattern, carried)}
    for name, line in lines:
        for pattern, what in PRIVATE:
            for m in re.finditer(pattern, line):
                if m.group(0) not in allowed:
                    found.append(f'{name}: {what}: {line.strip()[:120]}')
        if name.startswith(('packages/', 'tests/')) and re.search(SPEC_ID, line):
            found.append(f'{name}: a feature-scoped id: {line.strip()[:120]}')
    return found


def ledger_violations(sources: list[tuple[str, str]], roadmap: str, exists) -> list[str]:
    found = []
    for source, text in sources:
        for block in blocks(text):
            if not any(p in re.sub(r'"[^"]*"', '', block).lower() for p in PHRASES):
                continue
            seeds = re.findall(r'issues/([a-z0-9-]+)\.md', block)
            if not seeds:
                found.append(f'{source}: a deferral names no issues/ seed: {block[:160]}')
            for seed in seeds:
                if not exists(f'issues/{seed}.md'):
                    found.append(f'{source}: issues/{seed}.md does not exist')
                elif f'issues/{seed}.md' not in roadmap:
                    found.append(f'{source}: issues/{seed}.md has no ROADMAP.md entry')
    return found


def mode_prepush() -> list[str]:
    found = []
    base = diff_base()
    if git('diff', '--name-only').strip() or git('ls-files', '--others', '--exclude-standard').strip():
        found.append('the working tree holds changes the index does not')
    carried = at(FACT_BASE, 'README.md') + at(FACT_BASE, 'SECURITY.md')
    found += private_violations([(n, l) for n, l in added_lines(base) if not n.startswith(f'spec/{SLUG}/verify/')],
                                carried)
    tech = staged(f'spec/{SLUG}/TECH.md')
    phases = tech[tech.index('## Phase P1'):tech.index('## How `code-build` drives this')]
    sources = [('TECH.md', phases), ('PLAN.md', staged(f'spec/{SLUG}/PLAN.md')),
               ('commit bodies', git('log', f'{base}..HEAD', '--format=%B'))]
    exists = lambda p: bool(git('ls-files', '--', p).strip())
    return found + ledger_violations(sources, staged('ROADMAP.md'), exists)


# --- controls ---------------------------------------------------------------------------------------

SOUND_CORE = """# cluster-mcp core

The core serves shell and file tools on any cluster.

## Tools

- `run_command(command)` — Run a command

## What it needs on the cluster

- a login bash, `/bin/bash -l`

## How it behaves

Commands run in a login bash.

- A timeout returns exit code `-1001`.

### Raising the client's limit

Set `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` in the shell.
"""

SOUND_RCAC = """# RCAC tools

## Tools

- `myquota()` — Show quota

## What it needs on the cluster

- `myquota`

## How it behaves

It runs RCAC's commands.

## RCAC documentation

The `rcac-docs-mcp` service searches it.
"""

SOUND_README = """# cluster-mcp

An MCP server for HPC clusters. It runs commands for AI agents.

## Quick Start

```json
{"mcpServers": {"cluster": {"command": "uvx"}}}
```

```bash
uvx --from 'cluster-mcp' cluster-mcp --help
```

Claude Code cuts long instructions: [raise its limit](docs/core/README.md#raising-the-clients-limit).

## Capabilities

| Capability | Docs |
|---|---|
| core | [core](docs/core/README.md) |
| `[slurm]` | [slurm](docs/slurm/README.md) |
| `[rcac]`, with `[slurm]` | [rcac](docs/rcac/README.md); search the docs with [the service](docs/rcac/README.md#rcac-documentation) |

## Run modes

| Mode | Docs |
|---|---|
| `ssh` | [SSH](SECURITY.md#mode-1) |
| `local` | [local](SECURITY.md#mode-2) |
| `delegate` | [delegate](SECURITY.md#mode-3) |

## Upgrading from rcac-mcp

Deprecated in 0.2.0, removed no earlier than 0.4.0.

## Development

Run `uv sync`.

## License

MIT
"""


def mode_controls() -> list[str]:
    found: list[str] = []

    def expect(label: str, violations: list[str], why: str | None) -> None:
        if why is None and violations:
            found.append(f'control {label}: sound data refused: {violations}')
        elif why is not None and not any(why in v for v in violations):
            found.append(f'control {label}: plant not refused for {why!r}: {violations}')

    expect('readme sound', readme_violations(SOUND_README, SOUND_CORE, SOUND_RCAC), None)
    expect('readme long', readme_violations(SOUND_README + '\n' * 80, SOUND_CORE, SOUND_RCAC), 'more than 120')
    expect('readme order', readme_violations(SOUND_README.replace('## Run modes', '## Modes'), SOUND_CORE, SOUND_RCAC),
           'level-2 sections')
    expect('readme digit', readme_violations(SOUND_README.replace('Run `uv sync`.', 'Run it in 15 s.'), SOUND_CORE, SOUND_RCAC),
           'a digit outside')
    expect('readme number word', readme_violations(SOUND_README.replace('Run `uv sync`.', 'Wait fifteen seconds.'),
                                                   SOUND_CORE, SOUND_RCAC), 'a number word')
    expect('readme signal', readme_violations(SOUND_README.replace('Run `uv sync`.', 'It sends TERM.'), SOUND_CORE, SOUND_RCAC),
           'a signal name')
    expect('readme opening', readme_violations(SOUND_README.replace('It runs commands for AI agents.', ''),
                                               SOUND_CORE, SOUND_RCAC), 'the opening is 1')
    expect('readme two installs', readme_violations(SOUND_README.replace('```bash\n', '```bash\npip install x\n'),
                                                    SOUND_CORE, SOUND_RCAC), 'install lines')
    expect('readme limit anchor', readme_violations(SOUND_README.replace('#raising-the-clients-limit', '#tools'),
                                                    SOUND_CORE, SOUND_RCAC), "raise the client's limit")
    expect('readme rcac service', readme_violations(SOUND_README.replace('#rcac-documentation', '#tools'),
                                                    SOUND_CORE, SOUND_RCAC), 'documentation service')
    expect('readme mode row', readme_violations(SOUND_README.replace('[local](SECURITY.md#mode-2)', 'local'),
                                                SOUND_CORE, SOUND_RCAC), 'does not link SECURITY.md')

    tools = {'core': ('run_command',), 'rcac': ('myquota',)}
    commands = {'core': (), 'rcac': ('myquota',)}
    sound = {'core': SOUND_CORE, 'rcac': SOUND_RCAC}
    expect('tools sound', tools_violations(sound, {'run_command', 'myquota'}, tools, commands), None)
    expect('tools twice', tools_violations({**sound, 'core': SOUND_CORE.replace('- `run_command(command)` — Run a command',
                                            '- `run_command(command)` — Run\n- `myquota()` — Quota')},
                                           {'run_command', 'myquota'}, tools, commands), 'expected once')
    expect('tools missing', tools_violations({**sound, 'rcac': SOUND_RCAC.replace('- `myquota()` — Show quota\n', '')},
                                             {'run_command', 'myquota'}, tools, commands), 'tool myquota')
    expect('tools bare line', tools_violations({**sound, 'rcac': SOUND_RCAC.replace('- `myquota()`', '- myquota')},
                                               {'run_command', 'myquota'}, tools, commands), 'names no tool')
    expect('tools command', tools_violations({**sound, 'rcac': SOUND_RCAC.replace('- `myquota`\n', '- quota\n')},
                                             {'run_command', 'myquota'}, tools, commands), 'does not name `myquota`')
    expect('figures sound', figure_violations('core', SOUND_CORE + '\n| code | means |\n|---|---|\n| `-1003` | lost |\n'), None)
    expect('figures prose', figure_violations('core', SOUND_CORE + '\nA lost link gives `-1003`.\n'), 'outside a list')
    expect('figures lazy', figure_violations('core', '- A timeout gives\n`-1001` at once.\n'), None)
    expect('figures after list', figure_violations('core', '- an item\n\nThen 2 s pass.\n'), 'outside a list')
    expect('figures link target', figure_violations('core', 'See [the seed](../../issues/x-2.md).\n'), None)
    expect('hidden comment', ['hidden'] if hidden_comment('Text <!-- hidden --> text') else [], 'hidden')
    expect('comment in code', ['hidden'] if hidden_comment('Header `<!-- Source: x.md -->`') else [], None)

    files = {'README.md', 'docs/core/README.md', 'issues/x.md'}
    read = lambda p: SOUND_CORE
    expect('link sound', link_violations('docs/core/README.md', '[x](../../issues/x.md) [y](#tools)', files, read), None)
    expect('link missing', link_violations('docs/core/README.md', '[x](issues/x.md)', files, read), 'not in the tree')
    expect('link anchor', link_violations('README.md', '[x](docs/core/README.md#nowhere)', files, read), 'no heading')

    base = 'Line one states a fact.\nLine two states another.\n'
    facts = [{'id': 'a', 'src': 'B.md:1-2', 'dest': 'D.md', 'phrases': ['states a fact', 'states another']}]
    expect('facts sound', facts_violations(facts, {'B.md': base}, lambda p: '## X\nstates a fact; states another\n', set()),
           None)
    expect('facts missing', facts_violations(facts, {'B.md': base}, lambda p: '## X\nstates a fact\n', set()),
           'does not state')
    expect('facts split', facts_violations(facts, {'B.md': base},
                                           lambda p: '## X\nstates a fact\n## Y\nstates another\n', set()),
           'not inside one level-2 section')
    expect('facts invented', facts_violations([{**facts[0], 'phrases': ['states a lie']}], {'B.md': base},
                                              lambda p: 'states a lie', set()), 'not in the baseline')
    expect('facts uncovered', facts_violations([{**facts[0], 'src': 'B.md:1'}], {'B.md': base},
                                               lambda p: 'states a fact; states another', set()), 'B.md:2')
    expect('facts unlinked seed', facts_violations([{**facts[0], 'dest': 'issues/x.md'}], {'B.md': base},
                                                   lambda p: 'states a fact; states another', set()), 'linked from no')

    good = f'See {REPO_URL}/blob/main/docs/rcac/README.md for the tools.\n'
    expect('package sound', package_violations('rcac', 'p/README.md', good + "uvx --from 'git+" + REPO_URL + "#subdirectory=x'"),
           None)
    expect('package root', package_violations('rcac', 'p/README.md', good + f'Or [the README]({REPO_URL}).'),
           'links the repository README')
    expect('package root file', package_violations('rcac', 'p/README.md', good + f'{REPO_URL}/blob/main/README.md'),
           'links the repository README')
    expect('package other page', package_violations('rcac', 'p/README.md', f'{REPO_URL}/blob/main/docs/core/README.md'),
           'does not link docs/rcac')

    agents_base = ('## Repository map\n\nThe map.\n\n## Testing\n\n- Pins the README to the figures; '
                   'which only the README points to.\n\n### 9. Surface\n\n- The same commit also updates the tool '
                   'inventory in `README.md`.\n\n### Conventions\n')
    gone = ('which only the README points to',)
    saved = globals()['AGENTS_GONE'], globals()['AGENTS_NEW']
    globals()['AGENTS_GONE'], globals()['AGENTS_NEW'] = gone, (('Pins the', 'docs/core/README.md'),)
    try:
        agents_head = ('## Repository map\n\nThe map and docs/.\n\n## Documentation\n\nREADME.md, docs/, SECURITY.md, '
                       'short sentences, list or table, issues/, AGENTS.md, hurt, figure.\n\n## Testing\n\n- Pins the '
                       'docs/core/README.md to the figures; which only docs/rcac/README.md points to.\n\n### 9. '
                       'Surface\n\n- The same commit also updates the tool\'s docs page, `docs/<member>/README.md`.\n\n'
                       '### Conventions\n')
        expect('agents sound', agents_violations(agents_base, agents_head), None)
        expect('agents stale', agents_violations(agents_base, agents_head.replace('which only docs/rcac/README.md',
                                                                                  'which only the README')),
               'still says')
        expect('agents nine', agents_violations(agents_base, agents_head.replace("tool's docs page, `docs/<member>/README.md`",
                                                                                 'tool inventory in `README.md`')),
               "§9's same-commit bullet")
        expect('agents stray', agents_violations(agents_base, agents_head + '\n- The README lists the timeouts.\n'),
               'outside what it keeps')
    finally:
        globals()['AGENTS_GONE'], globals()['AGENTS_NEW'] = saved

    test_base = "from pathlib import Path\nroot = Path('.')\nX = ('a', 'b')\ntexts = {'README.md': (root / 'README.md').read_text()}\nassert X, 'the README does not state'\n"
    test_head = test_base.replace("(root / 'README.md')", "(root / 'docs' / 'core' / 'README.md')")
    expect('repoint sound', repoint_violations('t.py', test_base, test_head, 1), None)
    expect('repoint label', repoint_violations('t.py', test_base, test_head.replace("{'README.md'", "{'docs/core/README.md'"), 1),
           None)
    expect('repoint string', repoint_violations('t.py', test_base, test_head.replace("('a', 'b')", "('a',)"), 1),
           'more than the path')
    expect('repoint message', repoint_violations('t.py', test_base, test_head.replace('the README does', 'the page does'), 1),
           'more than the path')
    expect('repoint unmoved', repoint_violations('t.py', test_base, test_base, 1), 'still reads README.md')
    expect('paths src', [v for v in paths_violations(['packages/cluster-mcp/src/x.py'], lambda p: test_base,
                                                     lambda p: test_head if p in REPOINTED else test_base)
                         if 'x.py' in v], 'a package source')
    expect('paths fixture', [v for v in paths_violations(['tests/fixtures/served_surface.json'], lambda p: test_base,
                                                         lambda p: test_head if p in REPOINTED else test_base)
                             if 'served_surface' in v], 'fixture')

    expect('private carried', private_violations([('docs/core/README.md', 'ssh to cluster.rcac.purdue.edu')],
                                                 'cluster.rcac.purdue.edu'), None)
    expect('private new host', private_violations([('docs/core/README.md', 'ssh to login.rcac.purdue.edu')],
                                                  'cluster.rcac.purdue.edu'), 'a site hostname')
    # Review fold (PLAN § 4): each finding's plant.
    expect('readme upgrading edited', readme_violations(SOUND_README.replace('removed no earlier', 'removed not before'),
                                                        SOUND_CORE, SOUND_RCAC, SOUND_README), 'byte for byte')
    expect('readme upgrading kept', readme_violations(SOUND_README, SOUND_CORE, SOUND_RCAC, SOUND_README), None)
    expect('readme install span', readme_violations(SOUND_README.replace('Claude Code cuts', 'The JSON runs `uvx`. Claude Code cuts'),
                                                    SOUND_CORE, SOUND_RCAC), None)
    expect('readme ordinal', readme_violations(SOUND_README.replace('Run `uv sync`.', 'Name a second extra.'),
                                               SOUND_CORE, SOUND_RCAC), None)
    for label, plant in (('teen', 'Wait thirteen seconds.'), ('s unit', 'Wait fifteen s.'), ('ms', 'Wait ten ms.'),
                         ('tens', 'Wait eighty seconds.'), ('sigterm', 'It sends sigterm.'), ('a second', 'It waits a second.')):
        expect(f'readme {label}', readme_violations(SOUND_README.replace('Run `uv sync`.', plant), SOUND_CORE, SOUND_RCAC),
               'outside §')
    whole = [{'id': 'b', 'src': 'B.md:1', 'dest': 'D.md', 'phrases': ['45 s']}]
    expect('facts inside a number', facts_violations(whole, {'B.md': 'gives up at 45 s.\n'},
                                                     lambda p: '## X\nat most 44.45 s\n', set()), 'does not state')
    expect('facts inside a word', facts_violations([{**whole[0], 'phrases': ['MIT']}], {'B.md': 'MIT\n'},
                                                   lambda p: '## X\nthe limit\n', set()), 'does not state')
    expect('facts case', facts_violations([{**whole[0], 'phrases': ['TERM']}], {'B.md': 'one TERM signal\n'},
                                          lambda p: '## X\nit determines the term\n', set()), 'does not state')
    expect('facts any case', facts_violations([{**whole[0], 'phrases': ['never cut']}], {'B.md': 'is never cut\n'},
                                              lambda p: '## X\nNever cut.\n', set()), None)
    code = '```bash\nmkdir -p certs\ndocker compose up\n```\n'
    expect('facts code line', facts_violations([{**whole[0], 'src': 'B.md:1-4', 'phrases': ['docker compose up']}],
                                               {'B.md': code}, lambda p: '## X\n```\ndocker compose up\n```\n', set()),
           'verbatim')
    expect('security line kept', security_violations('# T\n' * 14 + 'Kept line.\n', '# T\nNew.\nKept line.\n'), None)
    expect('security line dropped', security_violations('# T\n' * 14 + 'Kept line.\n', '# T\nNew.\n'), 'line 15')
    expect('package root case', package_violations('rcac', 'p/README.md', good + 'https://github.com/purduercac/cluster-mcp'),
           'links the repository README')
    expect('package root query', package_violations('rcac', 'p/README.md', good + f'{REPO_URL}/blob/main/README.md?plain=1'),
           'links the repository README')
    expect('private new address', private_violations([('docs/core/README.md', 'mail help@purdue.edu')],
                                                     'mail rcac-help@purdue.edu'), 'an email address')
    expect('figures heading', figure_violations('core', '- item\n### Bound 15 s\n'), 'outside a list')
    expect('figures lone bar', figure_violations('core', '| 29 s of quiet\n'), 'outside a list')
    expect('tools nested', tools_violations({**sound, 'rcac': SOUND_RCAC.replace('- `myquota()` — Show quota',
                                             '- `myquota()` — Show quota\n  - `run_command()` — again')},
                                            {'run_command', 'myquota'}, tools, commands), 'expected once')
    expect('repoint one string', repoint_violations('t.py', test_base, test_base.replace("(root / 'README.md')",
                                                    "(root / 'docs/core/README.md')"), 1), None)
    agents_rcac = agents_base.replace('which only the README points to', "which only the README's `[rcac]` row points to")
    globals()['AGENTS_GONE'], globals()['AGENTS_NEW'] = (), ()
    try:
        expect('agents rcac row', [v for v in agents_violations(agents_base, agents_rcac.replace(
            '## Testing', '## Documentation\n\nREADME.md, docs/, SECURITY.md, short sentences, list or table, issues/, '
            'AGENTS.md, hurt, figure.\n\n## Testing').replace('The map.', 'The map and docs/.').replace(
            'Pins the README', 'Pins the docs/core/README.md').replace("tool inventory in `README.md`",
            "tool's docs page, `docs/<member>/README.md`")) if 'outside what it keeps' in v], None)
    finally:
        globals()['AGENTS_GONE'], globals()['AGENTS_NEW'] = saved
    road = 'issues/rename-in-docs.md'
    ex = lambda p: p == 'issues/rename-in-docs.md'
    expect('ledger sound', ledger_violations([('TECH.md', 'Left as it is: `issues/rename-in-docs.md`, deferred.')], road, ex),
           None)
    expect('ledger no seed', ledger_violations([('TECH.md', 'A known limitation, recorded nowhere.')], road, ex),
           'names no issues/ seed')
    return found


# --- main -------------------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    modes = {'readme': mode_readme, 'pages': mode_pages, 'facts': mode_facts, 'packages': mode_packages,
             'agents': mode_agents, 'paths': mode_paths, 'prepush': mode_prepush, 'controls': mode_controls}
    every = ['readme', 'pages', 'facts', 'packages', 'agents', 'paths']
    run = [m for a in argv for m in (every if a == 'all' else [a])]
    if not run or not all(m in modes for m in run):
        print(f'usage: docs-gate.py {{all|{"|".join(modes)}}}...', file=sys.stderr)
        return 2
    red = False
    for name in run:
        found = modes[name]()
        for line in found:
            print(f'FAIL {name}: {line}')
        print(f'{"ok" if not found else "red"}  {name}')
        red = red or bool(found)
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
