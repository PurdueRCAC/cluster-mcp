# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The dispatched mutation run's split and ledger (`mutants.py --matrix`, `--shard`, `--ledger`).

A dispatched run asks the runner for its shards, runs each in a job of its own, and checks each
job's report with the ledger, a separate process that reads the report however the runner ended.
These rows pin that every case this platform defines runs in exactly one shard, that every job
computes the same split, and that the ledger fails a shard for each case without exactly one kill
and each control that did not pass. No child runs: `run_case` is faked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import mutants
from mutants import CONTROLS, SHARD_SIZE, parse_shard, report_violations, shard_count, shard_ids

# A report line per control, as `self_check` prints it when the control passes.
CONTROL_LINES = [f'control  {text}: [...]' for text in CONTROLS]


def killed(case_id: str) -> str:
    return f"killed  {case_id}: test_isolation.py::test_a failed with 'ran as'"


def fake_run_case(ran: list[str]):
    """A `run_case` that kills every case and lets each control see what it must, recording the cases it ran."""
    def run_case(case, src_override=None, omit=None):
        if case is mutants.SURVIVOR_CONTROL:
            if src_override is None and omit is None:
                return ['the mutant survived: every target passed']
            return ['wrong import origin: the child did not import the mutated copy']
        ran.append(case.id)
        return []
    return run_case


def defined() -> list[str]:
    return [case.id for case in mutants.CASES]


@pytest.mark.unit
def test_the_shards_hold_every_case_once() -> None:
    assert shard_count([]) == 0
    assert shard_count([f'case-{n}' for n in range(10)], size=4) == 3
    for total, count in ((1, 1), (14, 1), (15, 1), (16, 2), (29, 2), (30, 2), (31, 3), (1164, 78), (1165, 78)):
        ids = [f'case-{n:04d}' for n in range(total)]
        assert shard_count(ids) == count, total
        shards = [shard_ids(ids, number, count) for number in range(1, count + 1)]
        held = [case_id for shard in shards for case_id in shard]
        assert sorted(held) == sorted(ids) and len(held) == len(set(held)), total
        sizes = [len(shard) for shard in shards]
        assert min(sizes) >= 1 and max(sizes) <= SHARD_SIZE and max(sizes) - min(sizes) <= 1, (total, sizes)


@pytest.mark.unit
def test_every_job_shards_the_cases_alike_whatever_their_order() -> None:
    # Each job imports the runner afresh: the split must not follow the order the cases were built in,
    # nor anything that differs between processes.
    ids = ['kilo', 'alpha', 'juliet', 'delta', 'hotel', 'bravo', 'india', 'echo', 'charlie', 'golf', 'foxtrot']
    expected = [['alpha', 'delta', 'golf', 'juliet'], ['bravo', 'echo', 'hotel', 'kilo'], ['charlie', 'foxtrot', 'india']]
    for order in (ids, list(reversed(ids)), tuple(sorted(ids)), ids[5:] + ids[:5]):
        assert [shard_ids(order, number, 3) for number in (1, 2, 3)] == expected


@pytest.mark.unit
def test_a_shard_outside_the_run_is_refused(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    ids = [f'case-{n:02d}' for n in range(40)]
    assert parse_shard('2/3', ids) == (2, 3)
    for number in (0, 4):
        with pytest.raises(ValueError, match='is not one of 1 to 3'):
            shard_ids(ids, number, 3)
    for text, why in (('2/4', 'is not the 3 shards'), ('1/2', 'is not the 3 shards'), ('2', 'NUMBER/COUNT'),
                      ('x/3', 'NUMBER/COUNT'), ('1/', 'NUMBER/COUNT')):
        with pytest.raises(ValueError, match=why):
            parse_shard(text, ids)
    ran: list[str] = []
    monkeypatch.setattr(mutants, 'run_case', fake_run_case(ran))
    count = shard_count(defined())
    for text in (f'0/{count}', f'{count + 1}/{count}', f'1/{count + 1}'):
        with pytest.raises(SystemExit) as exc:
            mutants.main(['--shard', text])
        assert exc.value.code == 2, text
    assert ran == []
    assert 'is not one of 1 to' in capsys.readouterr().err


@pytest.mark.unit
def test_the_run_holds_every_case_this_platform_defines(monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    cases = defined()
    assert cases, 'no case is defined'
    assert mutants.main(['--matrix']) == 0
    out, err = capsys.readouterr()
    count = shard_count(cases)
    assert json.loads(out) == list(range(1, count + 1))
    listed = err.splitlines()
    assert [line.split(':', 1)[0] for line in listed] == [f'shard {n} of {count}' for n in range(1, count + 1)]
    ran_all: list[str] = []
    for number, line in zip(range(1, count + 1), listed):
        ran: list[str] = []
        monkeypatch.setattr(mutants, 'run_case', fake_run_case(ran))
        assert mutants.main(['--shard', f'{number}/{count}']) == 0
        capsys.readouterr()
        # The plan's log names exactly what the shard runs, in the order it runs them.
        assert line.split(': ', 1)[1].split() == ran, number
        assert 1 <= len(ran) <= SHARD_SIZE, number
        ran_all += ran
    assert sorted(ran_all) == sorted(cases) and len(ran_all) == len(set(ran_all))


@pytest.mark.unit
def test_the_ledger_accepts_a_shard_whose_every_case_was_killed() -> None:
    lines = ['', killed('case-b'), 'Traceback (most recent call last):', killed('case-a'), *CONTROL_LINES,
             '  File "x.py", line 1', killed('case-c')]
    assert report_violations(['case-a', 'case-b', 'case-c'], lines) == []


@pytest.mark.unit
def test_the_ledger_names_each_case_without_a_kill() -> None:
    lines = [killed('case-a'),                      # killed once: sound
             killed('case-c'), killed('case-c'),    # run twice
             "FAILED  case-d: test_isolation.py::test_a: passed, so the mutant survived it",
             killed('case-e'),
             killed('case-z'),                      # another shard's case
             f'control  {CONTROLS[0]}: [...]', f'control  {CONTROLS[0]}: [...]',
             f'FAILED  {CONTROLS[1]}: []']          # and CONTROLS[2] never reported
    assert sorted(report_violations(['case-a', 'case-b', 'case-c', 'case-d', 'case-e'], lines)) == sorted([
        'case-b: no verdict reported',
        'case-c: reported 2 times',
        'case-d: not killed (its FAILED line in the report says why)',
        'case-z: not a case of this shard',
        f'control {CONTROLS[0]}: reported 2 times',
        f'control {CONTROLS[1]}: failed',
        f'control {CONTROLS[2]}: not reported',
    ])


@pytest.mark.unit
def test_the_ledger_refuses_a_run_with_no_cases() -> None:
    assert report_violations([], [killed('case-a'), *CONTROL_LINES]) == ['no mutation cases found']


@pytest.mark.unit
def test_the_ledger_reads_the_runner_s_own_lines(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                                tmp_path: Path) -> None:
    # The real `main` and `self_check` write the report, so a reworded verdict or control line is red here.
    ran: list[str] = []
    monkeypatch.setattr(mutants, 'run_case', fake_run_case(ran))
    count = shard_count(defined())
    shard = f'{count}/{count}'
    assert mutants.main(['--self-check', '--shard', shard]) == 0
    report = tmp_path / 'report.txt'
    report.write_text(capsys.readouterr().out)
    assert ran and len(report.read_text().splitlines()) == len(ran) + len(CONTROLS)
    assert mutants.main(['--ledger', str(report), '--shard', shard]) == 0
    assert capsys.readouterr().out == (f'ledger  shard {count} of {count}: {len(ran)} cases killed, '
                                       f'{len(CONTROLS)} controls passed\n')


@pytest.mark.unit
def test_cases_and_a_shard_together_are_refused(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    ran: list[str] = []
    monkeypatch.setattr(mutants, 'run_case', fake_run_case(ran))
    count = shard_count(defined())
    for argv, why in ((['--shard', f'1/{count}', defined()[0]], 'name cases or a shard, not both'),
                      (['--ledger', str(tmp_path / 'report.txt')], '--ledger checks one shard')):
        with pytest.raises(SystemExit) as exc:
            mutants.main(argv)
        assert exc.value.code == 2, argv
        assert why in capsys.readouterr().err, argv
    assert ran == []


@pytest.mark.unit
def test_the_ledger_fails_the_shard_and_names_each_case(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    count = shard_count(defined())
    shard = shard_ids(defined(), 1, count)
    report = tmp_path / 'report.txt'
    report.write_text('\n'.join([killed(case_id) for case_id in shard[1:]] + CONTROL_LINES) + '\n')
    assert mutants.main(['--ledger', str(report), '--shard', f'1/{count}']) == 1
    assert capsys.readouterr().out == f'FAILED  {shard[0]}: no verdict reported\n'
    # A runner stopped before it wrote anything: every case and control of the shard is named.
    assert mutants.main(['--ledger', str(tmp_path / 'never-written.txt'), '--shard', f'1/{count}']) == 1
    assert capsys.readouterr().out.splitlines() == (
        [f'FAILED  {case_id}: no verdict reported' for case_id in shard]
        + [f'FAILED  control {text}: not reported' for text in CONTROLS])


@pytest.mark.unit
def test_a_run_with_no_cases_names_no_shard(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(mutants, 'CASES', ())
    assert mutants.main(['--matrix']) == 1
    out, err = capsys.readouterr()
    assert out == ''
    assert err == 'no mutation cases found in tests/mutants.py\n'
