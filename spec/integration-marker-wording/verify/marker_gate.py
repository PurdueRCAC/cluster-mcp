"""Checks behind gate.sh for integration-marker-wording. Run from the worktree root with the
project's interpreter, isolated:

    uv run --no-sync python -I spec/integration-marker-wording/verify/marker_gate.py wording
    uv run --no-sync python -I spec/integration-marker-wording/verify/marker_gate.py scope P1|P2|P3
    uv run --no-sync python -I spec/integration-marker-wording/verify/marker_gate.py ids JUNIT [JUNIT ...]
    uv run --no-sync python -I spec/integration-marker-wording/verify/marker_gate.py ledger

Every check reads committed state: the index (`git show :<path>`), so a phase stages before its
gate. Exits 1 naming each failed check. One process, no children but git; under 100 MB.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SLUG = 'integration-marker-wording'
V = Path('spec') / SLUG / 'verify'
SEED = 'issues/marker-rule-gaps.md'
PLAN_SUBJECT = rf'^\[test\] Plan {SLUG}: design'
ALLOWED = {
    'P1': {'pyproject.toml', 'AGENTS.md'},
    'P2': {'pyproject.toml', 'AGENTS.md', 'tests/test_hygiene.py'},
    'P3': {'pyproject.toml', 'AGENTS.md', 'tests/test_hygiene.py', 'ROADMAP.md'},
}
# A seed the P3 ledger files is the only other path P3 may add.
P3_SEEDS = 'issues/'
NEVER = ('tests/conftest.py', 'bin/sandbox.sh', 'packages/', '.github/', 'uv.lock')
LIVE = 'test_the_markers_are_stated_as_pyproject_describes_them'
ROWS = 'test_marker_statement_check_catches_planted_drift'
ACCEPTS = 'test_marker_statement_check_accepts_a_rewrapped_statement'
ACCEPT_IDS = {'as-planted', 'rewrapped', 'unwrapped', 'paragraph-after-a-blank'}
KEPT = ('test_the_id_rule_is_stated_as_the_check_enforces_it', 'test_no_spec_ids_in_the_package_or_the_suite',
        'test_cli_drives_are_sandboxed', 'test_only_need_shell_skips')
DEFERRAL = re.compile(r'do not fix here|known limitation|follow-up|deferr|\bseeds?\b|\bfiled\b', re.I)
# Every seed this cycle relies on: each committed, and each with its ROADMAP.md entry.
SEEDS = (SEED, 'issues/integration-marker-check.md')
# The only gate file a phase may change after the plan commit: the sweep's record.
GATE_RECORD = f'spec/{SLUG}/verify/mutant-sweep.md'


def git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, text=True, check=True).stdout


def staged(name: str) -> str:
    return git('show', f':{name}')


def flat(text: str) -> str:
    return ' '.join(text.split())


def draft_check() -> dict:
    """The planned check (verify/draft/check_block.py), as the design states it."""
    ns = {'re': re, 'tomllib': tomllib, 'pytest': pytest, 'Path': Path}
    exec(compile((V / 'draft' / 'check_block.py').read_text(), 'check_block.py', 'exec'), ns)
    return ns


def wording() -> list[str]:
    bad = []
    pyproject, agents = staged('pyproject.toml'), staged('AGENTS.md')
    ns = draft_check()
    bad += [f'word for word: {v}' for v in ns['marker_statement_violations'](pyproject, agents)]
    if re.search(r'drives? no CLI|does not drive (?:the|a) CLI', flat(agents)):
        bad.append('AGENTS.md keeps a note that an integration test drives no CLI by exception')
    commands = agents[agents.index('\n## Commands\n'):agents.index('\n## Repository map')]
    comments = flat(' '.join(line.split('#', 1)[1] for line in commands.splitlines() if '#' in line))
    for words in ('each means what its pyproject.toml description says (§ Testing)',
                  'the rule the suite enforces is per launch: every process an integration test launches '
                  'goes through bin/sandbox.sh (§ Testing)'):
        if words not in comments:
            bad.append(f'the development commands do not say: {words!r}')
    testing = flat(ns['agents_section'](agents, '## Testing'))
    for words in ('what was bound before the test or sits below them is not refused: a `Popen` class bound '
                  'earlier (`conftest.REAL_POPEN`, a `from subprocess import Popen`) still launches; a `_socket` '
                  'connect, a UDP `sendto` and an early-bound `getaddrinfo` still reach the network; '
                  '`socket.gethostbyname` and its kin still look a name up; and a fixture of wider scope has '
                  f'launched before the guard is active (`{SEED}`)',
                  "which does not read a call through `conftest.REAL_POPEN`: `tests/test_ssh_exec.py`'s `_host` "
                  f'runs `hdiutil` through it, outside the sandbox, `{SEED}`;'):
        if words not in testing:
            bad.append(f'§ Testing does not say: {words!r}')
    return bad


def scope(phase: str) -> list[str]:
    plan = git('log', '-1', '--format=%H', '-E', f'--grep={PLAN_SUBJECT}').strip()
    if not plan:
        return ['no plan commit found']
    changed = [n for n in git('diff', '--cached', '--name-only', '--no-renames', plan).split('\n') if n]
    bad = [f'{phase} may not change {n}' for n in changed
           if not n.startswith(f'spec/{SLUG}/') and n not in ALLOWED[phase]
           and not (phase == 'P3' and n.startswith(P3_SEEDS))]
    bad += [f'never changed by this cycle: {n}' for n in changed if n.startswith(NEVER)]
    bad += [f'a gate file changed after the plan: {n}' for n in changed
            if n.startswith(f'spec/{SLUG}/verify/') and n != GATE_RECORD]
    if 'tests/test_hygiene.py' in changed:
        before, now = (top_level(git('show', f'{plan}:tests/test_hygiene.py')),
                       top_level(staged('tests/test_hygiene.py')))
        bad += [f'tests/test_hygiene.py binds {name} {count} times at top level'
                for name, count in now.items() if count > before.get(name, 0) and count > 1]
        bad += [f'tests/test_hygiene.py no longer binds {name}' for name in before if name not in now]
    for line in git('diff', '--cached', '--numstat', '--no-renames', plan).splitlines():
        added, removed, name = line.split('\t')
        if name == 'pyproject.toml' and (added, removed) != ('2', '2'):
            bad.append(f'pyproject.toml changes more than the two marker lines (+{added} -{removed})')
        if name == 'tests/test_hygiene.py' and removed != '0':
            bad.append(f'tests/test_hygiene.py removes {removed} lines; the cycle only adds')
    return bad


def top_level(source: str) -> dict[str, int]:
    """How many times each name is bound at the module's top level (def, class, assignment, import)."""
    counts: dict[str, int] = {}
    for node in ast.parse(source).body:
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [n.id for target in targets for n in ast.walk(target) if isinstance(n, ast.Name)]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [(a.asname or a.name).split('.')[0] for a in node.names]
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    return counts


def ids(junits: list[str]) -> list[str]:
    bad = []
    drift = set((V / 'drift-ids.txt').read_text().split())
    for junit in junits:
        seen = {}
        for case in ET.parse(junit).iter('testcase'):
            seen[case.get('name')] = next((c.tag for c in case if c.tag in ('failure', 'error', 'skipped')), 'passed')
        rows = {k[len(ROWS) + 1:-1] for k in seen if k.startswith(ROWS + '[')}
        accepts = {k[len(ACCEPTS) + 1:-1] for k in seen if k.startswith(ACCEPTS + '[')}
        if rows != drift:
            bad.append(f'{junit}: drift rows differ from drift-ids.txt: missing {sorted(drift - rows)}, '
                       f'extra {sorted(rows - drift)}')
        if accepts != ACCEPT_IDS:
            bad.append(f'{junit}: accept rows are {sorted(accepts)}, not {sorted(ACCEPT_IDS)}')
        named = [LIVE, *KEPT, *(f'{ROWS}[{r}]' for r in drift), *(f'{ACCEPTS}[{a}]' for a in ACCEPT_IDS)]
        bad += [f'{junit}: {n} {seen.get(n, "missing")}' for n in named if seen.get(n) != 'passed']
    return bad


def ledger() -> list[str]:
    bad = []
    roadmap = staged('ROADMAP.md')
    for doc in ('PLAN.md', 'TECH.md'):
        text = staged(f'spec/{SLUG}/{doc}')
        body = text.split('\n---\n', 2)[-1] if doc == 'TECH.md' else text
        for block in re.split(r'\n\s*\n|\n(?=\s*[-*] |\s*\d+\. |\|)', body):
            if block.lstrip().startswith('#') or not DEFERRAL.search(block):
                continue
            seeds = re.findall(r'issues/[a-z0-9-]+\.md', block)
            if not seeds:
                bad.append(f'{doc}: a deferral names no issues/ seed: {flat(block)[:100]!r}')
            for seed in seeds:
                try:
                    staged(seed)
                except subprocess.CalledProcessError:
                    bad.append(f'{doc}: {seed} is not committed')
                    continue
                if f'**Seed:** [`{seed}`]({seed})' not in roadmap:
                    bad.append(f'ROADMAP.md has no entry for {seed}')
    for seed in SEEDS:
        try:
            text = staged(seed)
        except subprocess.CalledProcessError:
            bad.append(f'{seed} is not committed')
            continue
        if not text.startswith('---\nstatus: unshaped\n'):
            bad.append(f'{seed} is not an unshaped seed')
        if f'**Seed:** [`{seed}`]({seed})' not in roadmap:
            bad.append(f'ROADMAP.md has no entry for {seed}')
    return bad


def main(argv: list[str]) -> int:
    mode, rest = argv[0], argv[1:]
    bad = {'wording': wording, 'ledger': ledger}.get(mode, lambda: None)()
    if mode == 'scope':
        bad = scope(rest[0])
    elif mode == 'ids':
        bad = ids(rest)
    if bad is None:
        print(f'unknown mode {mode}', file=sys.stderr)
        return 2
    for line in bad:
        print(f'{mode}: {line}', file=sys.stderr)
    print(f'{mode}: {"ok" if not bad else f"{len(bad)} failed"}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
