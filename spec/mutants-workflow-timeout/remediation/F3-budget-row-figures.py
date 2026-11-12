"""The frozen `runs --final` mode, run unchanged, then the budget row's wave figures and run commits (F3).

Covers review cycle 1, F-a and F-b. The `mutants budget` row's whole-run test ("while its shards, run
in waves of the account's concurrent jobs, still finish within the 15 minutes") held no concurrency,
no wave count and no time per wave, so a cycle that adds cases could not tell where it stands
without dispatching (F-a). And the row named one commit for three runs made at three (F-b).

This wrapper:
  1. runs `verify/mutants-gate.py runs --runs-file spec/mutants-workflow-timeout/runs.txt --final`
     unchanged, prints its output, and is red unless it ends `runs: ok` with exit 0;
  2. from that output (each run's wall and most jobs at once, the baseline, the refit's inputs and
     its row for the runner's shard size) and each run's head commit (`gh run view --json headSha`),
     builds the two sentences the row must carry after the baseline: each run's head, with the
     measured code shown the same (`git diff --name-only` holds only the cycle's records); and the
     waves, the time per wave and the case at which the run would cross the envelope, at the
     measured rate and at the refit's worst-case rate;
  3. requires the staged row to end with the baseline followed by exactly those two sentences;
  4. runs its own controls on planted rows: the reviewed row, two heads swapped, a wrong wave count,
     a wrong crossing wave, a wrong concurrency. Each plant must land once and be refused.

Run from the cycle worktree root, after staging (the row is read from the index):

    UV_PYTHON=3.14 uv run -q python -I spec/mutants-workflow-timeout/remediation/F3-budget-row-figures.py

Footprint: the frozen `runs` mode (one gh call per run and per job log, one export of the measured
commit), then one `gh run view --json headSha` per run and in-process checks. Reads only; nothing
is dispatched, re-run or cancelled.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / 'verify' / 'mutants-gate.py'
RUNS_FILE = HERE.parent / 'runs.txt'
# The reviewed commit of review cycle 1: its row predates both fixes.
REVIEWED = '30231aa'
RECORDS = ('spec/', 'issues/')

spec = importlib.util.spec_from_file_location('mutants_gate', GATE)
gate = importlib.util.module_from_spec(spec)
sys.modules['mutants_gate'] = gate
spec.loader.exec_module(gate)  # type: ignore[union-attr]


def mmss(seconds: float) -> str:
    n = int(seconds + 0.5)
    return f'{n // 60}:{n % 60:02d}'


def ordinal(n: int) -> str:
    suffix = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


def run_frozen() -> tuple[list[str], list[str]]:
    cmd = [sys.executable, '-I', str(GATE), 'runs', '--runs-file', str(RUNS_FILE.relative_to(Path.cwd())), '--final']
    ran = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(ran.stdout)
    sys.stderr.write(ran.stderr)
    lines = ran.stdout.splitlines()
    found = []
    if ran.returncode != 0 or not lines or lines[-1] != 'runs: ok':
        found.append(f'the frozen `runs --final` is not green (exit {ran.returncode})')
    return lines, found


def figures(lines: list[str], size: int) -> tuple[dict, list[str]]:
    fig: dict = {'runs': []}
    for line in lines:
        if m := re.match(r'^run (\d+): (\d+) s from dispatch to its last job, (\d+) jobs at once at most$', line):
            fig['runs'].append((m.group(1), int(m.group(2)), int(m.group(3))))
        elif line.startswith('baseline: '):
            fig['baseline'] = line[len('baseline: '):]
        elif m := re.match(r'^refit: ([\d.]+) s a child \(slowest\), (\d+) s overhead \(largest\), (\d+) jobs at once '
                           r'\(fewest\), plan done (\d+) s after dispatch \(longest\)$', line):
            fig['child'], fig['over'], fig['at_once'], fig['plan'] = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        elif m := re.match(rf'^refit: +{size} +(\d+) +(\d+) +(\d+) +\d+ +(\d+) +\d+ ', line):
            fig['refit_shards'], fig['refit_waves'], fig['job'], fig['refit_run'] = map(int, m.groups())
    missing = [k for k in ('baseline', 'child', 'job') if k not in fig]
    if len(fig['runs']) != 3:
        missing.append('three run lines')
    return fig, [f'the frozen output lacks {k}' for k in missing]


def heads(ids: list[str]) -> dict[str, str]:
    out = {}
    for rid in ids:
        ran = subprocess.run(['gh', 'run', 'view', rid, '--json', 'headSha'], capture_output=True, text=True, check=True)
        out[rid] = json.loads(ran.stdout)['headSha']
    return out


def attribution(measured: str, ids: list[str], head: dict[str, str]) -> tuple[str, list[str]]:
    found = []
    if head[ids[0]] != measured:
        found.append(f'run {ids[0]} ran at {head[ids[0]][:7]}, not the measured commit {measured[:7]}')
    others = ids[1:]
    for rid in others:
        if head[rid] == measured:
            found.append(f'run {rid} ran at the measured commit itself; the sentence names it as another')
        names = gate.git('diff', '--name-only', measured, head[rid]).split()
        code = [n for n in names if not (n.startswith(RECORDS) or n == 'ROADMAP.md')]
        if code:
            found.append(f'run {rid} at {head[rid][:7]} differs from {measured[:7]} beyond the records: {code}')
    text = (f'`{measured[:7]}` is the measured commit, the head of run {ids[0]}; runs {others[0]} and {others[1]} ran at '
            f'`{head[others[0]][:7]}` and `{head[others[1]][:7]}`, which differ from it only in `spec/`, `issues/` and '
            f'`ROADMAP.md`, so the three runs measured the same code.')
    return text, found


def waves_text(fig: dict, size: int) -> tuple[str, list[str]]:
    found = []
    at_once = {c for _, _, c in fig['runs']}
    if len(at_once) != 1 or at_once != {fig['at_once']}:
        found.append(f'the runs differ in jobs at once ({sorted(at_once)}): "each counted run held at most" needs rewording')
    c = fig['at_once']
    cost = re.match(r'^(\d[\d,]*) cases in (\d+) shards, the run (\d+:\d\d) from dispatch', fig['baseline'])
    if not cost:
        return '', found + ['the baseline holds no cases, shards and run']
    shards = int(cost.group(2))
    wall = max(w for _, w, _ in fig['runs'])
    if mmss(wall) != cost.group(3):
        found.append(f'the worst run {mmss(wall)} is not the baseline\'s {cost.group(3)}')
    waves = math.ceil(shards / c)
    if shards != fig['refit_shards'] or waves != fig['refit_waves']:
        found.append(f'{shards} shards in {waves} waves, but the refit row says {fig["refit_shards"]} in {fig["refit_waves"]}')
    per = wall / waves
    k = math.floor(gate.ENVELOPE / per) + 1
    s = c * (k - 1) + 1
    plan, job = fig['plan'], fig['job']
    kw = math.floor((gate.ENVELOPE - plan) / job) + 1
    sw = c * (kw - 1) + 1
    if plan + waves * job != fig['refit_run']:
        found.append(f'plan {plan} s + {waves} x {job} s is not the refit row\'s run, {fig["refit_run"]} s')
    text = (f'Waves: each counted run held at most {c} jobs at once (the account\'s concurrent-job limit, shared with any '
            f'other run of the account), so a run takes ⌈shards ÷ {c}⌉ waves, with ⌈cases ÷ {size}⌉ shards: {waves} waves '
            f'for the {shards}. The worst run, {mmss(wall)} over its {waves} waves, took about {mmss(per)} a wave, its plan '
            f'and queueing included. At that rate the run crosses {mmss(gate.ENVELOPE)} at its {ordinal(k)} wave, from the '
            f'{ordinal(s)} shard (case {size * (s - 1) + 1:,}): {k - 1} waves project {mmss((k - 1) * per)}, '
            f'{int(gate.ENVELOPE - (k - 1) * per)} s inside, and {k} project {mmss(k * per)}. Projected instead with every '
            f'job as slow as the slowest seen ({fig["child"]} s a case and {fig["over"]} s of setup, {job} s a job with its '
            f'{len(gate.CONTROL_TEXTS)} controls, after the plan\'s {plan} s), it crosses at its {ordinal(kw)} wave, from '
            f'the {ordinal(sw)} shard (case {size * (sw - 1) + 1:,}): {kw - 1} waves project {mmss(plan + (kw - 1) * job)}, '
            f'{kw} project {mmss(plan + kw * job)}.')
    return text, found


def row_violations(row: str, tail: str) -> list[str]:
    if not row:
        return ['§ Factory: no `mutants budget` row']
    if not row.endswith(tail):
        return ['the `mutants budget` row does not end with the baseline, each run\'s head and the wave figures']
    return []


def controls(agents: str, row: str, tail: str) -> list[str]:
    found = []

    def expect(label: str, planted: str | None) -> None:
        if planted is None or planted == row:
            print(f'BAD {label}: the plant did not land')
            found.append(f'control {label}: the plant did not land')
            return
        refused = row_violations(planted, tail)
        print(f'{"ok " if refused else "BAD"} {label}: {refused[:1] or "accepted"}')
        if not refused:
            found.append(f'control {label}: accepted, wanted refused')

    def plant(old: str, new: str) -> str | None:
        return row.replace(old, new) if row.count(old) == 1 else None

    expect('reviewed row', gate.budget_row(gate.at(REVIEWED, 'AGENTS.md')))
    swapped = re.search(r'ran at `(\w{7})` and `(\w{7})`', row)
    expect('heads swapped', plant(swapped.group(0), f'ran at `{swapped.group(2)}` and `{swapped.group(1)}`') if swapped else None)
    expect('wave count', plant(' waves for the ', ' waves and one for the ') if ' waves for the ' in row else None)
    wave = re.search(r'crosses 15:00 at its (\d+)th wave', row)
    expect('crossing wave', plant(wave.group(0), f'crosses 15:00 at its {int(wave.group(1)) + 1}th wave') if wave else None)
    expect('concurrency', plant('held at most 20 jobs at once', 'held at most 25 jobs at once'))
    ok = not row_violations(row, tail)
    print(f'{"ok " if ok else "BAD"} staged row: {"accepted" if ok else "refused"}')
    return found


def main() -> int:
    lines, found = run_frozen()
    runner = gate.staged(gate.RUNNER)
    size_m = re.search(r'^SHARD_SIZE = (\d+)$', runner, re.M)
    if not size_m:
        found.append(f'{gate.RUNNER} holds no SHARD_SIZE')
    else:
        size = int(size_m.group(1))
        fig, missing = figures(lines, size)
        found += missing
        if not missing:
            text = RUNS_FILE.read_text().splitlines()
            measured = next(line.split()[1] for line in text if line.startswith('sha '))
            ids = [line.split()[1] for line in text if line.startswith('run ')]
            head = heads(ids)
            for rid in ids:
                print(f'run {rid}: head {head[rid][:7]}')
            said, bad = attribution(measured, ids, head)
            found += bad
            waves, bad = waves_text(fig, size)
            found += bad
            tail = f'{fig["baseline"]}. {said} {waves}'
            agents = gate.staged('AGENTS.md')
            row = gate.budget_row(agents)
            found += row_violations(row, tail)
            found += controls(agents, row, tail)
    for line in found:
        print(f'FAILED  {line}')
    print(f'runs and the row\'s figures: {"ok" if not found else f"{len(found)} failed"}')
    return 1 if found else 0


if __name__ == '__main__':
    sys.exit(main())
