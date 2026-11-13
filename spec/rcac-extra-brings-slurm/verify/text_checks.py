"""The text checks of rcac-extra-brings-slurm, read from the index (what the next commit holds) against BASE.

Usage, from the worktree root:  python -I spec/rcac-extra-brings-slurm/verify/text_checks.py MODE BASE

  files          what the cycle changed since BASE: only the paths it may touch, and none of the paths
                 a non-goal or R2/R4 freezes (the fixture, the compat root, the members' metadata and
                 code, the Dockerfile, the mutation runner)
  lock           uv.lock differs from BASE by exactly the two lines that give the rcac extra the Slurm
                 member, both added
  install-lines  every RCAC install line names `cluster-mcp[rcac]` alone; `[slurm,rcac]` is left only
                 where it describes the compat root; no text says `[rcac]` goes with `[slurm]` or
                 that each extra installs one member
  rcac-set       the tests and docs that name the fixture's `rcac` set read it as the RCAC member
                 registered alone
  roadmap        the ROADMAP entries and the seed state the rule, its citation and its release, by
                 added lines only, with the entries' horizons and order untouched
  ledger         every deferral phrase in TECH.md's body (its prose and list items, never a heading
                 or the ledger item itself) names an issues/ seed that exists and ROADMAP.md indexes

Prose is read with its line breaks folded into single spaces, so a phrase wrapped across lines is
found. Footprint: one process, a few git calls; stdlib only. Exit 0 printing `ok: MODE`, or exit 1
naming every failure.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys

SLUG = 'rcac-extra-brings-slurm'
SPEC = f'spec/{SLUG}/'

# Paths the cycle may change, and paths it must leave as they are on BASE.
ALLOWED = {
    'packages/cluster-mcp/pyproject.toml', 'uv.lock', 'tests/test_packaging.py',
    'README.md', 'packages/cluster-mcp/README.md', 'packages/cluster-mcp-rcac/README.md',
    'docs/core/README.md', 'docs/rcac/README.md', 'docs/slurm/README.md', 'AGENTS.md',
    'tests/test_capabilities.py', 'tests/test_surface.py', 'ROADMAP.md', 'issues/site-extras.md',
}
FROZEN = ('tests/fixtures/served_surface.json', 'pyproject.toml', 'Dockerfile', 'compose.yml',
          'packages/cluster-mcp-slurm/pyproject.toml', 'packages/cluster-mcp-rcac/pyproject.toml',
          'packages/cluster-mcp/src/', 'packages/cluster-mcp-slurm/src/', 'packages/cluster-mcp-rcac/src/',
          'tests/mutants.py')

LOCK_ADDED = ['    { name = "cluster-mcp-slurm" },',
              '    { name = "cluster-mcp-slurm", marker = "extra == \'rcac\'", editable = "packages/cluster-mcp-slurm" },']

README_REQ = 'cluster-mcp[rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp'
RELEASE_REQ = 'cluster-mcp[rcac] @ git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp'
UVX_LINE = f"uvx --from '{README_REQ}' cluster-mcp --help"

# Each file's install lines, as they must read (whitespace folded).
REQUIRED = {
    'README.md': [f'"args": ["--from", "{README_REQ}",', UVX_LINE, '| RCAC | `cluster-mcp[rcac]` |'],
    'packages/cluster-mcp/README.md': [UVX_LINE],
    'packages/cluster-mcp-rcac/README.md': ['installed as the `cluster-mcp[rcac]` extra'],
    'docs/core/README.md': [UVX_LINE],
    'docs/rcac/README.md': ['`cluster-mcp[rcac]`'],
    'AGENTS.md': [f"bin/sandbox.sh uvx --from '{RELEASE_REQ}' cluster-mcp --help # the README line",
                  f'`{RELEASE_REQ}`', f'`{README_REQ}`', 'the core with the extra [rcac]'],
}

# An extras list naming both `slurm` and `rcac`, in either order, spaced or not, beside any others.
COMBINED = re.compile(r'\[\s*[\w,\s-]*\b(?:slurm\b[\w,\s-]*\brcac|rcac\b[\w,\s-]*\bslurm)\b[\w,\s-]*\]')

# The lines left naming both extras, per file, exactly (stripped): each describes the compat root,
# which keeps depending on `cluster-mcp[slurm,rcac]`, or pins that dependency. Any other line: none.
COMBINED_LINES = {
    'AGENTS.md': [
        "installs `cluster-mcp[slurm,rcac]` (§ Packaging).",
        "`cluster-mcp[slurm,rcac]` (installed: `cluster-mcp[rcac,slurm]`), and the development",
        "and its dependency closure; the root's `cluster-mcp[slurm,rcac]` is what brings both members into",
        "`cluster-mcp[slurm,rcac]`, ships no code (wheel `bypass-selection`), installs only the deprecated",
        "through cluster-mcp[slurm,rcac] (so that form stays exercised), and runs the deprecated rcac-mcp",
    ],
    'Dockerfile': [
        "# Install the root project, whose dependency cluster-mcp[slurm,rcac] builds the core and both of its",
    ],
    'README.md': [
        "distribution that carries every capability (`cluster-mcp[slurm,rcac]`) and runs the deprecated",
    ],
    'issues/shell-extra.md': [
        "`[shell]` along with `[slurm,rcac]`, so the deprecated name serves exactly what it serves today.",
    ],
    'pyproject.toml': [
        'description = "Deprecated name of cluster-mcp: installs cluster-mcp[slurm,rcac] and the rcac-mcp command"',
        'dependencies = ["cluster-mcp[slurm,rcac]"]',
    ],
    'tests/mutants.py': [
        "'distribution that carries every capability (`cluster-mcp[slurm,rcac]`) and runs the deprecated\\n'",
    ],
    'tests/test_packaging.py': [
        "`cluster-mcp[slurm,rcac]`, so the old install line, and `uv sync`, install every capability. Pinned",
        "assert root['project']['dependencies'] == ['cluster-mcp[slurm,rcac]']",
        "assert distribution(COMPAT).requires == ['cluster-mcp[rcac,slurm]']",
    ],
}

# What no text may say any more (whitespace folded): that `[rcac]` goes with `[slurm]`, that the RCAC
# member's independence from the Slurm member is the design, or that each extra installs one member.
FORBIDDEN = ('goes with `[slurm]`', 'go with `[slurm]`', 'which go with', 'Install it with `[slurm]`',
             'with `[slurm]` (`cluster-mcp', 'does not require the Slurm member',
             'install `[rcac]` with `[slurm]`', 'each one member', 'each install one member',
             'Each extra installs one member', 'The Slurm extra beside it', 'installs one member')
# The same claims in other words (whitespace folded, any case), in the texts a reader installs from
# (not the suite, whose messages name the breaks it refuses): the RCAC member or `[rcac]` not
# bringing Slurm, and a second requirement naming `[slurm]` beside an install.
PROSE = ('.md', '.toml', '.yml', '.yaml', 'Dockerfile')
FORBIDDEN_PATTERNS = (
    re.compile(r"\b(?:does not|doesn't|do not|don't|won't|will not|cannot|can't)\s+(?:bring|install|include|pull)"
               r"[^.]{0,80}\bslurm\b", re.IGNORECASE),
    re.compile(r"--with\s+'?\"?cluster-mcp\[slurm\]", re.IGNORECASE),
    re.compile(r"\b(?:add|also install|install)\s+`?cluster-mcp\[slurm\]`?\s+(?:as well|too|also|beside|with)",
               re.IGNORECASE),
    # `[rcac]` paired with a second `[slurm]` requirement, either way round, in any words that join them.
    re.compile(r"\[rcac\]`?(?:\s+extra)?\s+(?:together with|alongside|beside|with|and|plus)\s+`?(?:cluster-mcp)?\[slurm\]",
               re.IGNORECASE),
    re.compile(r"\[slurm\]`?(?:\s+extra)?\s+(?:together with|alongside|beside|with|plus)\s+`?(?:cluster-mcp)?\[rcac\]",
               re.IGNORECASE),
)

ALONE = 'the RCAC member registered alone'
RCAC_SET_FILES = ('tests/test_capabilities.py', 'tests/test_surface.py', 'AGENTS.md')

RULE = "a center's extra installs every extra its center's clusters need"
CITATION = 'maintainer decision, 2026-11-12'
RELEASE = '0.2.2'
# The release, `[rcac]` and its bringing `[slurm]`, in one sentence (whitespace folded).
BRINGS = re.compile(r'0\.2\.2[^.]*\[rcac\][^.]*\bbrings\b[^.]*\[slurm\]')
ENTRIES = ('## Site interfaces: abstract tools a center implements in its own extra',
           '## `[rcac]`: a site extra is shorthand plus a point of view')
# Nothing internal in an added line: no home or knowledge-base path, no tracker board, no address.
INTERNAL = re.compile(r'/Users/|~/|\bKB\b|asana|\bboard\b|@[\w-]+\.edu\b', re.IGNORECASE)

# The test modules whose comments and docstrings the cycle edits: their code must stay the base's.
CODE_FROZEN = ('tests/test_capabilities.py', 'tests/test_surface.py')

DEFERRAL = re.compile(r'defer|follow-up|follow up|known limitation|not fixed here|do not fix here|left as|'
                      r'out of scope|later cycle|postpone', re.IGNORECASE)


def git(*args: str) -> str:
    return subprocess.run(['git', *args], check=True, capture_output=True, text=True).stdout


def staged(name: str) -> str:
    return git('show', f':{name}')


def at_base(base: str, name: str) -> str:
    return git('show', f'{base}:{name}')


def folded(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


def tracked() -> list[str]:
    return [n for n in git('ls-files', '--cached').splitlines() if not n.startswith(SPEC.split('/')[0] + '/')]


def changed(base: str) -> list[str]:
    return git('diff', '--cached', '--name-only', base).splitlines()


def check_files(base: str) -> list[str]:
    problems = []
    for name in changed(base):
        if name.startswith(SPEC):
            continue
        if name.startswith(FROZEN) or name in FROZEN:
            problems.append(f'{name} changed, and the cycle must leave it as it is on {base[:9]}')
        elif name not in ALLOWED:
            problems.append(f'{name} changed, and it is not a path the cycle may touch')
    untracked = git('ls-files', '--others', '--exclude-standard').splitlines()
    problems += [f'{name} is untracked' for name in untracked]
    for name in CODE_FROZEN:
        if code_of(staged(name)) != code_of(at_base(base, name)):
            problems.append(f'{name} changes code, and the cycle may change only its comments and docstrings')
    return problems


def code_of(source: str) -> str:
    """The module's syntax tree with every docstring removed (comments are never in it)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def check_lock(base: str) -> list[str]:
    diff = git('diff', '--cached', '-U0', base, '--', 'uv.lock').splitlines()
    added = [line[1:] for line in diff if line.startswith('+') and not line.startswith('+++')]
    removed = [line[1:] for line in diff if line.startswith('-') and not line.startswith('---')]
    problems = [f'uv.lock removes {line!r}' for line in removed]
    if added != LOCK_ADDED:
        problems.append(f'uv.lock adds {added}, expected {LOCK_ADDED}')
    return problems


def check_install_lines(base: str) -> list[str]:
    problems = []
    for name, lines in REQUIRED.items():
        text = folded(staged(name))
        problems += [f'{name} lacks {line!r}' for line in lines if folded(line) not in text]
    for name in tracked():
        try:
            text = staged(name)
        except (subprocess.CalledProcessError, UnicodeDecodeError):
            continue
        found = sorted(line.strip() for line in text.splitlines() if COMBINED.search(line))
        want = sorted(COMBINED_LINES.get(name, []))
        if found != want:
            extra = [line for line in found if line not in want]
            gone = [line for line in want if line not in found]
            problems.append(f'{name} names both extras on other lines than the compat root\'s: '
                            f'unexpected {extra}, missing {gone}')
        flat = folded(text)
        # Any case: a sentence may start with the phrase.
        problems += [f'{name} still says {phrase!r}' for phrase in FORBIDDEN if phrase.lower() in flat.lower()]
        if name.endswith(PROSE):
            # The compat root's own lines may name both extras; nothing else may pair them.
            allowed = [folded(line) for line in COMBINED_LINES.get(name, [])]
            problems += [f'{name} says {m[0]!r}' for pattern in FORBIDDEN_PATTERNS for m in pattern.finditer(flat)
                         if not any(m[0] in line for line in allowed)]
    return problems


def check_rcac_set(base: str) -> list[str]:
    return [f'{name} does not read the rcac set as {ALONE!r}' for name in RCAC_SET_FILES
            if ALONE not in folded(staged(name))]


def sections(text: str) -> dict[str, str]:
    """Each level-2 section of a Markdown text, by its heading line."""
    found: dict[str, str] = {}
    heading = None
    for line in text.splitlines(keepends=True):
        if line.startswith('## '):
            heading = line.rstrip('\n')
            found[heading] = ''
        elif heading is not None:
            found[heading] += line
    return found


def only_added(base: str, name: str) -> list[str]:
    """Every line of `name` the index adds over BASE, or a problem for each line it removes."""
    diff = git('diff', '--cached', '-U0', base, '--', name).splitlines()
    removed = [line for line in diff if line.startswith('-') and not line.startswith('---')]
    if removed:
        raise ValueError(f'{name} removes or rewrites {len(removed)} lines: {removed[:3]}')
    return [line[1:] for line in diff if line.startswith('+') and not line.startswith('+++')]


def check_roadmap(base: str) -> list[str]:
    problems = []
    new, old = staged('ROADMAP.md'), at_base(base, 'ROADMAP.md')
    new_sections, old_sections = sections(new), sections(old)
    if list(new_sections) != list(old_sections):
        problems.append('ROADMAP.md sections were added, removed or reordered')
    for heading in ENTRIES:
        body = new_sections.get(heading)
        if body is None:
            problems.append(f'ROADMAP.md lacks {heading!r}')
            continue
        flat = folded(body)
        problems += [f'{heading!r} lacks {want!r}' for want in (RULE, CITATION) if want not in flat]
        if not BRINGS.search(flat):
            problems.append(f'{heading!r} does not say, in one sentence, that from 0.2.2 [rcac] brings [slurm]')
        new_h = [ln for ln in body.splitlines() if ln.startswith('*Horizon:')]
        old_h = [ln for ln in old_sections.get(heading, '').splitlines() if ln.startswith('*Horizon:')]
        if new_h != old_h:
            problems.append(f'{heading!r} changed its horizon line')
    flat = folded(staged('issues/site-extras.md'))
    problems += [f'issues/site-extras.md lacks {want!r}' for want in (RULE, CITATION) if want not in flat]
    if not BRINGS.search(flat):
        problems.append('issues/site-extras.md does not say, in one sentence, that from 0.2.2 [rcac] brings [slurm]')
    for name in ('ROADMAP.md', 'issues/site-extras.md'):
        try:
            added = only_added(base, name)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if not added:
            problems.append(f'{name} adds nothing')
        problems += [f'{name} adds an internal reference: {line!r}' for line in added if INTERNAL.search(line)]
        # Every added line sits inside one of the two entries (ROADMAP) or anywhere in the seed.
        if name == 'ROADMAP.md':
            inside = folded(''.join(new_sections.get(h, '') for h in ENTRIES))
            problems += [f'ROADMAP.md adds a line outside the two entries: {line!r}' for line in added
                         if line.strip() and folded(line).strip() not in inside]
    return problems


ITEM = re.compile(r'\s*(?:[-*] |\d+\. |\|)')


def blocks(text: str) -> list[str]:
    """Each paragraph, list item and table row of a Markdown text, its lines folded into one; no heading."""
    found: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith('#') or ITEM.match(line):
            if current:
                found.append(folded(' '.join(current)).strip())
            current = [] if (not line.strip() or line.startswith('#')) else [line]
        else:
            current.append(line)
    if current:
        found.append(folded(' '.join(current)).strip())
    return found


def check_ledger(base: str) -> list[str]:
    tech = staged(f'{SPEC}TECH.md')
    body = tech.split('\n---\n', 1)[1] if tech.startswith('---\n') else tech
    roadmap = staged('ROADMAP.md')
    problems = []
    for line in blocks(body) + blocks(staged(f'{SPEC}PLAN.md')):
        # The ledger's own item names the phrases it looks for, so it is not read.
        if 'ledger' in line or not DEFERRAL.search(line):
            continue
        seeds = re.findall(r'issues/[\w.-]+\.md', line)
        if not seeds:
            problems.append(f'a deferral names no issues/ seed: {line!r}')
        for seed in seeds:
            if seed not in git('ls-files', '--cached', seed):
                problems.append(f'{seed} is named in TECH.md and does not exist')
            elif f'**Seed:** [`{seed}`]' not in roadmap:
                problems.append(f'{seed} has no ROADMAP.md entry')
    return problems


MODES = {'files': check_files, 'lock': check_lock, 'install-lines': check_install_lines,
         'rcac-set': check_rcac_set, 'roadmap': check_roadmap, 'ledger': check_ledger}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in MODES:
        sys.exit(f'usage: text_checks.py {"|".join(MODES)} BASE')
    mode, base = argv
    problems = MODES[mode](base)
    for problem in problems:
        print(f'text_checks {mode}: FAIL: {problem}', file=sys.stderr)
    if problems:
        return 1
    print(f'ok: {mode}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
