"""The aimed sweep of the snapshot test's comparison and normalization (PLAN § 6, GOAL R7).

Usage, from the worktree root:  uv run python -I spec/surface-fixture-after-a-surface-change/verify/sweep.py [MUTANT_ID...]

Each mutant attacks one decision of `tests/test_surface.py`: the comparison (whether it runs, its
verdict, its report), the one normalization, or the serializer. Per mutant and per protocol era,
the sweep copies the index's `tests/`, `bin/`, `.github/` and top-level files (`git checkout-index`,
so it grades what the commit holds) into a fresh directory, plants the one edit there (its anchor
must occur exactly once), and runs the mutant's named tests in a child pytest under this worktree's
`bin/sandbox.sh`, with this worktree's environment, the child carrying the word
`snapshot-sweep-child` in its argv. The JUnit report is judged per test by
`mutants.mutation_violations`: each target must fail, carrying its own `why`, not error or skip.

A mutant is killed only when every target fails for its reason in **both** eras. After every
child, the copy's fixture must still be the staged fixture. A mutant marked equivalent is run and
reported with the reason no control can reach it; its survival is not a failure. The update mode is
not swept (GOAL Non-goals): the update control holds it.

Writes `spec/surface-fixture-after-a-surface-change/verify/sweep-report.txt` (verdicts only, no
timings, so a re-run on the same tree writes the same bytes) when run without arguments, and exits 1
when any mutant that is not equivalent survives.

Footprint: one child process tree at a time (the sandbox shell, one pytest, no workers): peak about
4 processes and under 400 MB, plus the copy (about 2 MB per mutant, removed with its temporary
directory). Each child is bounded at 300 s in its own process group, killed whole on expiry.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd()
SPEC = ROOT / 'spec' / 'surface-fixture-after-a-surface-change'
SANDBOX = ROOT / 'bin' / 'sandbox.sh'
FIXTURE = 'tests/fixtures/served_surface.json'
REPORT = SPEC / 'verify' / 'sweep-report.txt'
MARK = 'snapshot-sweep-child'
COPIED = ('tests', 'bin', '.github', 'README.md', 'AGENTS.md', 'pyproject.toml', 'uv.lock')
ERAS = ('legacy', 'modern')
ENVIRON = {k: v for k, v in os.environ.items() if k not in ('UPDATE_SURFACE', 'MCP_BASE_URL')}

sys.path.insert(0, str(ROOT / 'tests'))
import mutants  # noqa: E402 - the runner's verdict on a child pytest's JUnit report

TS = 'tests/test_surface.py'
T = 'test_surface.py::'
DEPTH = T + 'test_a_field_changed_at_depth_fails_naming_its_entry_and_field'
TYPE, GAINED, LOST = f'{DEPTH}[changed-type]', f'{DEPTH}[gained]', f'{DEPTH}[lost]'
WHITESPACE, TWO = f'{DEPTH}[whitespace]', f'{DEPTH}[two-entries]'
UPDATE_CONTROL = T + 'test_update_mode_regenerates_a_conflicted_fixture'
BASELINE = T + 'test_served_surface_matches_baseline'
VERSION = T + 'test_version_source_names_exactly_one_distribution'
ONE, NONE, SEVERAL = f'{VERSION}[one]', f'{VERSION}[none]', f'{VERSION}[several]'
RECORDER = T + 'test_recorder_sees_what_the_server_starts_serving'
PROMPT, TEMPLATE = f'{RECORDER}[prompt]', f'{RECORDER}[resource-template]'

RAISED = 'DID NOT RAISE'
# Each depth row's expected line carries its kind of change: the failing assertion prints it.
ROW_WHY = {TYPE: 'changed: ', GAINED: ': added', LOST: ': removed'}


def rows(*targets: str) -> tuple[tuple[str, str], ...]:
    return tuple((target, ROW_WHY[target]) for target in targets)


def each(why: str, *targets: str) -> tuple[tuple[str, str], ...]:
    return tuple((target, why) for target in targets)


@dataclass(frozen=True)
class Mutant:
    id: str
    decision: str
    old: str
    new: str
    targets: tuple[tuple[str, str], ...]
    equivalent: str | None = None


SWITCH = "    surface_check(FIXTURE, serialized(), update=os.environ.get(UPDATE) == '1')\n"
VERDICT = "    if expected != served:\n"
ADDED = "            if key not in old:\n                lines.append(f'- {render_path(path + (key,))}: added')\n"
REMOVED = "            elif key not in new:\n                lines.append(f'- {render_path(path + (key,))}: removed')\n"
LEAF = "    return [] if was == now else"
DESCEND = "    if isinstance(old, dict) and isinstance(new, dict):\n"
PATH_LOOP = "    text = ''\n    for key in path:\n"
QUOTED = "            text += f\"['{key}']\"\n"
NORMALIZE = "    info['version'] = {'distribution': version_source(info.get('version'), installed)}\n"
ONLY_ONE = "    if len(found) != 1:\n"
MATCH = "if isinstance(served, str) and version is not None and version == served]"
SOURCES = "VERSION_SOURCES = ('cluster-mcp', 'fastmcp-slim')\n"
CANDIDATES = "{len(found)} of the candidates ({candidates}), so"
ERA_LOOP = "        for era in ERAS:\n            surfaces[(era, param.id)]"
SET_LOOP = "    for param in test_capabilities.SETS:\n"
SET_SERVER = "        server = create_mcp_server('none', site=SITE, capabilities=tuple(loaded[name] for name in names))\n"
LISTING = "                listing = out.setdefault(key, {})\n"
KEYED = "                    listing.setdefault(identity, {}).setdefault(era, {})[set_id] = entry\n"
REPORT_LINES = (r"    return '\n'.join([header, *(lines or ['- the fixture is not in canonical form (no field differs)'])])"
                '\n')
DICT_LINES = '        return lines\n    was, now'

MUTANTS: tuple[Mutant, ...] = (
    # The comparison: whether it runs.
    Mutant('switch-not-equal', 'the update mode is on only when the variable is exactly 1', SWITCH,
           SWITCH.replace("== '1'", "!= '1'"), each(RAISED, UPDATE_CONTROL)),
    Mutant('switch-default-on', 'the update mode is off when the variable is unset', SWITCH,
           SWITCH.replace("os.environ.get(UPDATE)", "os.environ.get(UPDATE, '1')"), each(RAISED, UPDATE_CONTROL)),
    Mutant('switch-presence', 'a set variable that is not 1 leaves the update mode off', SWITCH,
           SWITCH.replace("os.environ.get(UPDATE) == '1'", 'UPDATE in os.environ'), each(RAISED, UPDATE_CONTROL)),
    # The comparison: its verdict.
    Mutant('verdict-always-equal', 'the verdict is the bytes', VERDICT, '    if False:\n',
           each(RAISED, TYPE, GAINED, LOST)),
    Mutant('verdict-parsed', 'the verdict is type-strict (bytes, not parsed values)', VERDICT,
           '    if expected is None or json.loads(expected) != json.loads(served):\n', each(RAISED, TYPE)),
    Mutant('verdict-stripped', 'surrounding whitespace is part of the verdict', VERDICT,
           '    if expected is None or expected.strip() != served.strip():\n',
           (*rows(TYPE, GAINED, LOST), (UPDATE_CONTROL, RAISED), (BASELINE, 'is not the served surface')),
           equivalent='canonical bytes start with `{` and end in exactly one newline, so the update mode never '
                      'writes a fixture whose stripped bytes equal another\'s; only a hand-edit reaches it'),
    # The comparison: its report.
    Mutant('report-skips-added', 'a key only in the served surface is reported', ADDED,
           '            if key not in old:\n                pass\n', rows(GAINED)),
    Mutant('report-skips-removed', 'a key only in the fixture is reported', REMOVED,
           '            elif key not in new:\n                pass\n', rows(LOST)),
    Mutant('report-python-leaves', 'leaves are compared as JSON text, type-strict', LEAF,
           '    return [] if old == new else', rows(TYPE)),
    Mutant('report-no-descent', 'the report descends dicts to the field', DESCEND, '    if False:\n',
           rows(TYPE, GAINED, LOST)),
    Mutant('report-labels-swapped', 'added and removed are labelled as they are', ADDED + REMOVED,
           ADDED.replace(': added', ': removed') + REMOVED.replace(': removed', ': added'), rows(GAINED, LOST)),
    Mutant('report-drops-era-and-set', 'the path names the era and the set', PATH_LOOP,
           "    text = ''\n    for key in [k for k in path if k not in ERAS and k not in ('both', 'slurm')]:\n",
           rows(TYPE, GAINED, LOST)),
    Mutant('report-quoted-key-empty', 'a quoted key is rendered as itself', QUOTED, '            text += "[\'\']"\n',
           rows(LOST)),
    # The normalization.
    Mutant('normalization-skipped', 'the served version is recorded as its source', NORMALIZE,
           "    info['version'] = info.get('version')\n", each('serverInfo.legacy.both.version: changed', BASELINE)),
    Mutant('normalization-bare-name', 'the source is recorded as {"distribution": ...}', NORMALIZE,
           "    info['version'] = version_source(info.get('version'), installed)\n",
           each('serverInfo.legacy.both.version: changed', BASELINE)),
    Mutant('version-first-match', 'several matching candidates fail', ONLY_ONE, '    if len(found) < 1:\n',
           each(RAISED, SEVERAL)),
    Mutant('version-no-match-accepted', 'no matching candidate fails', ONLY_ONE, '    if len(found) > 1:\n',
           each('IndexError', NONE)),
    Mutant('version-match-not-equal', 'the match is equality', MATCH,
           'if isinstance(served, str) and version is not None and version != served]', each('ValueError', ONE)),
    Mutant('version-match-in', 'the match is exact, not containment', MATCH,
           'if isinstance(served, str) and version is not None and served in version]', each('ValueError', ONE)),
    Mutant('version-match-startswith', 'the match is exact, not a prefix', MATCH,
           'if isinstance(served, str) and version is not None and version.startswith(served)]',
           each('ValueError', ONE)),
    Mutant('version-match-endswith', 'the match is exact, not a suffix', MATCH,
           'if isinstance(served, str) and version is not None and version.endswith(served)]',
           each('ValueError', ONE)),
    Mutant('version-none-matches-none', 'an uninstalled candidate never matches', MATCH,
           'if version == served]', each(RAISED, NONE)),
    Mutant('sources-lose-fastmcp-slim', 'the source FastMCP reads its version from is a candidate', SOURCES,
           "VERSION_SOURCES = ('cluster-mcp',)\n", each('serverInfo.version: the served version', BASELINE)),
    Mutant('sources-lose-cluster-mcp', 'the core is a candidate', SOURCES, "VERSION_SOURCES = ('fastmcp-slim',)\n",
           each('is not the served surface', BASELINE),
           equivalent='the core\'s version is not served until the rename cycle, whose one-field fixture diff '
                      'would show the source switch'),
    Mutant('error-omits-candidates', 'the failure names every candidate', CANDIDATES,
           '{len(found)} of the candidates, so', each('assert ', NONE, SEVERAL)),
    # The serializer.
    Mutant('serializer-drops-an-era', 'every era is serialized', ERA_LOOP,
           ERA_LOOP.replace('in ERAS:', 'in ERAS[:1]:'), each(': removed', BASELINE)),
    Mutant('serializer-drops-a-set', 'every set is serialized', SET_LOOP,
           '    for param in test_capabilities.SETS[1:]:\n', each(': removed', BASELINE)),
    Mutant('serializer-one-server', 'each set is served by a server of its own', SET_SERVER,
           "        server = create_mcp_server('none', site=SITE)\n", each(': added', BASELINE)),
    Mutant('serializer-drops-empty-listing', 'an empty listing is serialized as {}', LISTING,
           '                if not value:\n                    continue\n' + LISTING,
           (*each(': added', PROMPT, TEMPLATE), (BASELINE, ': removed'))),
    Mutant('serializer-listing-era-first', 'a listing is keyed by identity first', KEYED,
           '                    listing.setdefault(era, {}).setdefault(identity, {})[set_id] = entry\n',
           (*each(': added', PROMPT, TEMPLATE), (BASELINE, ': removed'))),
    # Amendment 2026-11-12 (the re-shape's review 1, F1-F3): the five survivors of the reviewer's
    # sweep, killed by the whitespace and two-entry depth rows and the version table's decoys.
    Mutant('cmp-verdict-ignores-whitespace', 'whitespace inside a string is part of the verdict', VERDICT,
           '    if expected is None or expected.split() != served.split():\n', each(RAISED, WHITESPACE)),
    Mutant('report-first-line-only', 'the report names every differing field', REPORT_LINES,
           REPORT_LINES.replace('*(lines or', '*(lines[:1] or'), each(': removed', TWO)),
    Mutant('diff-first-only', 'every differing field of a dict is reported', DICT_LINES,
           '        return lines[:1]\n    was, now', each(': removed', TWO)),
    Mutant('ver-prefix-match', 'the match is exact, not a prefix of the served value', MATCH,
           'if isinstance(served, str) and version is not None and served.startswith(version)]',
           each('ValueError', ONE)),
    Mutant('ver-substring-match', 'the match is exact, not a part of the served value', MATCH,
           'if isinstance(served, str) and version is not None and version in served]', each('ValueError', ONE)),
)


def git(*args: str, **kw: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(['git', *args], capture_output=True, env=dict(ENVIRON), **kw)  # type: ignore[call-overload]


def copy_tree(dest: Path) -> Path:
    """The index's copied paths, checked out under `dest/repo/`."""
    repo = dest / 'repo'
    listed = git('ls-files', '-z', '--', *COPIED)
    if listed.returncode != 0 or not listed.stdout:
        raise SystemExit(f'sweep: cannot list the index: {listed.stderr.decode().strip()}')
    done = git('checkout-index', '-z', '--stdin', f'--prefix={repo}/', input=listed.stdout)
    if done.returncode != 0:
        raise SystemExit(f'sweep: cannot check the index out: {done.stderr.decode().strip()}')
    return repo


def plant(repo: Path, mutant: Mutant) -> None:
    path = repo / TS
    text = path.read_text()
    count = text.count(mutant.old)
    if count != 1:
        raise SystemExit(f'sweep: {mutant.id}: the anchor occurs {count} times in {TS}: {mutant.old[:80]!r}')
    path.write_text(text.replace(mutant.old, mutant.new))


def bounded(argv: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run `argv` in its own process group, killing the whole group on expiry."""
    process = subprocess.Popen(argv, env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               start_new_session=True)
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        out, err = process.communicate()
        err += f'\nsweep: killed after {timeout} s'
    return subprocess.CompletedProcess(argv, process.returncode, out, err)


def era_verdict(repo: Path, mutant: Mutant, era: str, scratch: Path) -> list[str]:
    junit = scratch / f'junit-{era}.xml'
    targets = [target for target, _ in mutant.targets]
    child = bounded([str(SANDBOX), 'sh', '-c', 'cd "$1" || exit 96; shift; "$@"', MARK, str(repo), sys.executable,
                     '-m', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={junit}',
                     *[f'tests/{t}' for t in targets]], {**ENVIRON, 'CLUSTER_MCP_TEST_ERA': era}, 300)
    report = junit.read_text() if junit.exists() else None
    problems = []
    for target, why in mutant.targets:
        problems += mutants.mutation_violations(child.returncode, report, [target], why)
    if report is None:
        problems.append(f'no report: {child.stderr.strip()[-300:]!r}')
    return sorted(set(problems))


def run(mutant: Mutant, staged: bytes) -> tuple[str, str]:
    """(verdict, detail): `killed` when every target fails for its reason in both eras, else
    `equivalent` for a mutant marked so, else `survived`."""
    with tempfile.TemporaryDirectory(prefix=f'snapshot-sweep-{mutant.id}-') as name:
        scratch = Path(name)
        repo = copy_tree(scratch)
        if (repo / FIXTURE).read_bytes() != staged:
            raise SystemExit(f'sweep: the copy\'s fixture is not the staged one ({mutant.id})')
        plant(repo, mutant)
        found = []
        for era in ERAS:
            problems = era_verdict(repo, mutant, era, scratch)
            if (repo / FIXTURE).read_bytes() != staged:
                problems.append('the fixture was written')
                (repo / FIXTURE).write_bytes(staged)
            found.append((era, problems))
    if all(not problems for _, problems in found):
        return 'killed', 'killed in both eras'
    detail = '; '.join(f'{era}: ' + ('; '.join(problems) if problems else 'killed') for era, problems in found)
    if mutant.equivalent is not None:
        return 'equivalent', f'{mutant.equivalent} (observed: {detail})'
    return 'survived', detail


def main(argv: list[str]) -> int:
    chosen = [m for m in MUTANTS if not argv or m.id in argv]
    unknown = sorted(set(argv) - {m.id for m in MUTANTS})
    if unknown or not chosen:
        print(f'sweep: no such mutant: {unknown}', file=sys.stderr)
        return 2
    shown = git('show', f':{FIXTURE}')
    if shown.returncode != 0:
        print(f'sweep: cannot read the staged {FIXTURE}', file=sys.stderr)
        return 2
    lines = ['# The aimed sweep of the comparison and the normalization (PLAN section 6), both eras', '']
    failed = []
    for mutant in chosen:
        start = time.monotonic()
        verdict, detail = run(mutant, shown.stdout)
        print(f'sweep: {verdict:10} {mutant.id} ({time.monotonic() - start:.0f} s): {detail}', file=sys.stderr)
        lines.append(f'{verdict:10} {mutant.id}: {mutant.decision}')
        lines.append(f'           {detail}')
        if verdict == 'survived':
            failed.append(mutant.id)
    counts = {v: sum(line.startswith(v) for line in lines) for v in ('killed', 'survived', 'equivalent')}
    lines += ['', f'{len(chosen)} mutants: {counts["killed"]} killed, {counts["survived"]} survived, '
                  f'{counts["equivalent"]} equivalent']
    if not argv:
        REPORT.write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    if failed:
        print(f'sweep: FAIL: survived: {", ".join(failed)}', file=sys.stderr)
        return 1
    print('sweep: ok: every mutant killed in both eras or recorded as equivalent', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
