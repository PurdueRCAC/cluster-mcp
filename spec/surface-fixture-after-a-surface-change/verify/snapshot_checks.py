"""Text and inventory checks for surface-fixture-after-a-surface-change. Run from the worktree root.

Usage: uv run python -I spec/surface-fixture-after-a-surface-change/verify/snapshot_checks.py MODE

surface-cases  print the id of every `tests/mutants.py` case that plants into the served-surface
               fixture or targets a test in `tests/test_surface.py` (GOAL R7); fails unless they are
               exactly the eleven named here, the four named as planting among them
no-enable      the update mode's variable is named by no staged file but `tests/test_surface.py`, the
               documentation (`*.md`) and `spec/`; and not by the profile's `verify` row or the
               release recipe's `gate:` list in `AGENTS.md` (GOAL R1: no gate step or CI job enables it)
docs           `AGENTS.md` describes the snapshot test and nothing of the surface command (GOAL R8);
               the suite's own docstrings drop the command too
seeds          the `--out` seed and its ROADMAP entry are gone; the completeness seed, if kept, names
               none of the dropped items; every ROADMAP seed link resolves; Part I's counts follow
               (GOAL R11)
ledger         every deferral phrase in TECH.md's phase bodies (prose and list items, never headings)
               names an `issues/{slug}.md` that exists and that ROADMAP.md lists (code-plan Step 6.8)

Reads committed text where it can: every file is read from the index (`git show :path`), so a
check grades what the commit will hold, not the working copy. Footprint: one python process and a
few `git` children, a few MB.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
SPEC = 'spec/surface-fixture-after-a-surface-change'
FIXTURE = 'tests/fixtures/served_surface.json'
UPDATE = 'UPDATE_SURFACE'
ENVIRON = dict(os.environ)

NUMBER_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
    'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
    'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40,
}


def number(word: str) -> int:
    """A number written as digits or as English words up to forty-nine (`Thirty-one`)."""
    if word.isdigit():
        return int(word)
    parts = word.lower().split('-')
    return sum(NUMBER_WORDS[p] for p in parts)


def git(*args: str) -> str:
    done = subprocess.run(['git', *args], capture_output=True, text=True, env=dict(ENVIRON))
    if done.returncode != 0:
        raise SystemExit(f'snapshot_checks: git {" ".join(args)}: {done.stderr.strip()}')
    return done.stdout


def staged(path: str) -> str | None:
    """The file as the index holds it, or None when the index holds no such file."""
    done = subprocess.run(['git', 'show', f':{path}'], capture_output=True, env=dict(ENVIRON))
    # Read as text whatever the bytes: a binary file (the icon) cannot name the variable anyway.
    return done.stdout.decode('utf-8', 'replace') if done.returncode == 0 else None


def staged_paths(prefix: str) -> list[str]:
    return [p for p in git('ls-files', '--', prefix).splitlines() if p]


def section(text: str, start: str, stop: str) -> str:
    """The text from the first line starting with `start` to the next line matching `stop`."""
    at = text.find(start)
    if at < 0:
        return ''
    end = re.compile(stop, re.M).search(text, at + len(start))
    return text[at:end.start() if end else len(text)]


# The surface cases GOAL R7 keeps, and the four that plant into the fixture: a case dropped or
# renamed fails here, not silently out of the gate.
SURFACE_CASES = ('tool-description-summary-only', 'annotations-on-every-tool', 'empty-annotations-on-every-tool',
                 'annotations-on-one-tool', 'annotations-removed', 'annotation-hint-flipped',
                 'annotation-hint-dropped', 'annotation-hint-added', 'title-on-one-tool', 'title-on-every-tool',
                 'title-at-add-tool')
PLANTING = ('annotations-removed', 'annotation-hint-flipped', 'annotation-hint-dropped', 'annotation-hint-added')


def surface_cases() -> list[str]:
    sys.path.insert(0, str(ROOT / 'tests'))
    import mutants  # the runner's own case list
    ids, planting = [], []
    for case in mutants.CASES:
        plants = any(path == FIXTURE for path, _, _ in case.repo_edits)
        targets = any(t.startswith('test_surface.py::') for t in case.targets)
        if plants or targets:
            ids.append(case.id)
        if plants:
            planting.append(case.id)
    problems = []
    if sorted(ids) != sorted(SURFACE_CASES):
        problems.append(f'the surface cases are {sorted(ids)}, not {sorted(SURFACE_CASES)}')
    if sorted(planting) != sorted(PLANTING):
        problems.append(f'the fixture-planting cases are {sorted(planting)}, not {sorted(PLANTING)}')
    if not problems:
        print(' '.join(ids))
    return problems


def no_enable() -> list[str]:
    problems = []
    # Every staged file that could run or configure something: workflows and actions, `bin/`,
    # `pyproject.toml`, env and config files, every test module but the snapshot test's own.
    for name in staged_paths('.'):
        if name == 'tests/test_surface.py' or name.startswith('spec/') or name.endswith('.md'):
            continue
        if UPDATE in (staged(name) or ''):
            problems.append(f'{name} names {UPDATE}')
    agents = staged('AGENTS.md') or ''
    verify = [line for line in agents.splitlines() if line.startswith('| verify |')]
    if not verify:
        problems.append('AGENTS.md has no profile verify row')
    problems += [f'the profile verify row names {UPDATE}' for line in verify if UPDATE in line]
    gate = re.search(r'^(\s*)gate:\s*\n((?:\1\s+.*\n)+)', agents, re.M)
    if gate is None:
        problems.append('AGENTS.md has no release recipe gate: list')
    elif UPDATE in gate.group(2):
        problems.append(f'the release recipe gate: list names {UPDATE}')
    return problems


# Text the snapshot test retires: the command, its flags and base, the tolerance list, the
# carve-outs, the per-set check and the hand-edit rule.
STALE = ('record_surface', 'surface command', '--against', '--out FILE', 'TOLERATED', 'tolerated_differences',
         'carve-out', 'hand-edit', 'era_violations', 'set_violations', 'delta_lines', 'expected_surface',
         'command_main', 'CommandEffects', 'surface_differences', 'surface_violations',
         'test_surface_fixture_is_the_baseline_shape', 'test_every_capability_set_serves_the_fixtures_entries')
SHARED = ('surface_violations', 'era_violations')
# What a description of the snapshot test names, per place (GOAL R8).
NAMED = {
    '§9': (UPDATE, 'git diff', 'serverInfo.version', 'plain equality'),
    '§ Testing (tests/test_surface.py)': (UPDATE, 'git diff', 'serverInfo.version', 'SETS'),
    '§ Commands': (UPDATE,),
}


def docs() -> list[str]:
    agents = staged('AGENTS.md') or ''
    parts = {
        '§9': section(agents, '### 9. The agent-facing surface', r'^### '),
        '§ Testing (tests/test_surface.py)': section(agents, '  - `tests/test_surface.py`', r'^  - `tests/|^- '),
        '§ Commands': section(agents, '## Commands', r'^## '),
    }
    problems = []
    for where, text in parts.items():
        if not text:
            problems.append(f'{where}: not found')
            continue
        problems += [f'{where} does not name {word!r}' for word in NAMED[where] if word not in text]
    # Two of the retired names are also other modules' own functions, each in its own § Testing entry
    # (`tests/test_probe_startup.py`'s `surface_violations`, `tests/test_protocol.py`'s
    # `era_violations`): those two are read only where the snapshot test is described. Every other
    # word is read in the whole file; an identifier as a whole word (`set_violations` is not
    # `sandbox_unset_violations`), any other text as a substring.
    for word in STALE:
        where = '\n'.join(parts.values()) if word in SHARED else agents
        pattern = rf'(?<!\w){re.escape(word)}(?!\w)' if re.fullmatch(r'\w+', word) else re.escape(word)
        if re.search(pattern, where):
            problems.append(f'AGENTS.md names {word!r}')
    for name in ('tests/harness.py', 'tests/test_surface.py', 'tests/mutants.py'):
        text = staged(name) or ''
        problems += [f'{name} names {word!r}' for word in ('record_surface', 'surface command') if word in text]
    if staged('bin/record_surface.py') is not None or (ROOT / 'bin' / 'record_surface.py').exists():
        problems.append('bin/record_surface.py still exists')
    return problems


RELATIVE_OUT = 'issues/record-surface-relative-out.md'
COMPLETENESS = 'issues/surface-pin-completeness.md'
# The completeness seed's items that the snapshot test removes the ground of (PLAN § 2.6).
DROPPED = ('cmp-depth', 'ver-source-accept-several', 'set-loop-one-server', 'set-cut-only', 'no-run scan',
           'scan-tests', 'scan-ci-only', 'per-set')
SEED_LINK = re.compile(r'\*\*Seed:\*\* \[`(issues/[\w.-]+\.md)`\]')


def seeds() -> list[str]:
    problems = []
    roadmap = staged('ROADMAP.md') or ''
    if staged(RELATIVE_OUT) is not None or (ROOT / RELATIVE_OUT).exists():
        problems.append(f'{RELATIVE_OUT} still exists')
    if RELATIVE_OUT in roadmap:
        problems.append(f'ROADMAP.md still names {RELATIVE_OUT}')
    kept = staged(COMPLETENESS)
    if kept is None:
        if COMPLETENESS in roadmap:
            problems.append(f'ROADMAP.md names the retired {COMPLETENESS}')
    else:
        entry = section(roadmap, "## The surface pin's", r'^## ')
        for word in DROPPED:
            if word in kept:
                problems.append(f'{COMPLETENESS} still names {word!r}')
            if word in entry:
                problems.append(f'its ROADMAP.md entry still names {word!r}')
        if COMPLETENESS not in roadmap:
            problems.append(f'ROADMAP.md does not list the kept {COMPLETENESS}')
    for link in SEED_LINK.findall(roadmap):
        if staged(link) is None:
            problems.append(f'ROADMAP.md links {link}, which the index does not hold')
    part1 = section(roadmap, '# Part I ', r'^# Part II')
    entries = len(SEED_LINK.findall(part1))
    stated = re.search(r'^([A-Z][a-z]+(?:-[a-z]+)?|\d+) entries', part1, re.M)
    if stated is None or number(stated.group(1)) != entries:
        problems.append(f'Part I states {stated.group(1) if stated else "no"} entries; it holds {entries}')
    intro = re.search(r'\*\*Part I\*\*[^;]*;\s*(\d+|[A-Za-z-]+) entries', roadmap)
    if intro is None or number(intro.group(1)) != entries:
        problems.append(f'the introduction states {intro.group(1) if intro else "no"} Part I entries; it holds {entries}')
    gates = len(re.findall(r'^\*Horizon: Part I, gates', part1, re.M))
    group = re.search(r'\*\*Gates\*\* \(([a-z-]+|\d+)\)', part1)
    if group is None or number(group.group(1)) != gates:
        problems.append(f'Part I states {group.group(1) if group else "no"} gates; it holds {gates}')
    return problems


DEFERRAL = re.compile(r'do not fix here|known limitation|left as a follow-up|follow-up:|deferred to|deferred,',
                      re.I)
SEED = re.compile(r'issues/([\w.-]+\.md)')


def ledger() -> list[str]:
    tech = (staged(f'{SPEC}/TECH.md') or '').split('\n---\n', 1)[-1]
    roadmap = staged('ROADMAP.md') or ''
    problems = []
    for at, line in enumerate(tech.splitlines(), 1):
        if line.lstrip().startswith('#') or not DEFERRAL.search(line):
            continue
        found = SEED.findall(line)
        if not found:
            problems.append(f'TECH.md body line {at}: a deferral names no issues/ seed: {line.strip()}')
        for seed in found:
            if staged(f'issues/{seed}') is None:
                problems.append(f'TECH.md body line {at}: issues/{seed} is not in the index')
            elif f'issues/{seed}' not in roadmap:
                problems.append(f'TECH.md body line {at}: ROADMAP.md does not list issues/{seed}')
    return problems


def main(argv: list[str]) -> int:
    checks = {'surface-cases': surface_cases, 'no-enable': no_enable, 'docs': docs, 'seeds': seeds,
              'ledger': ledger}
    if len(argv) != 1 or argv[0] not in checks:
        print(f'usage: snapshot_checks.py {"|".join(checks)}', file=sys.stderr)
        return 2
    problems = checks[argv[0]]()
    for problem in problems:
        print(f'snapshot_checks: FAIL: {problem}', file=sys.stderr)
    if not problems:
        print(f'snapshot_checks: ok: {argv[0]}', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
