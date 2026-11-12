"""Mutant sweep of the stop: plant each mutant into tests/mutants.py (or tests/test_mutations.py), run the rows it
names, and report killed (every named row red) or SURVIVED. Run from anywhere:

    uv run --no-project python spec/mutant-child-outlives-timeout/verify/sweep.py WORKTREE SCRATCH [MUTANT_ID...]

SCRATCH is a directory outside the worktree for the backups and JUnit reports; each file is restored from
its backup after every mutant and byte-compared at the end. Its record is sweep.md beside it.
"""
import shutil, subprocess, sys, os, xml.etree.ElementTree as ET
from pathlib import Path

WT = Path(sys.argv[1])
SCR = Path(sys.argv[2])
only = set(sys.argv[3:])
R = WT / 'tests' / 'mutants.py'
T = WT / 'tests' / 'test_mutations.py'
M = 'tests/test_mutations.py::'
INTEG = M + 'test_a_child_past_its_limit_is_stopped_whole_and_reported'
def rm(p): return M + 'test_run_members_follow_parents_and_groups[' + p + ']'
def gone(p): return M + 'test_gone_waits_until_every_process_ends[' + p + ']'
FREEZE = M + 'test_stop_run_freezes_then_kills_the_whole_run'
def cut(p): return M + 'test_stop_run_kills_what_it_found_when_it_is_cut_short[' + p + ']'
FIG = M + 'test_the_stop_figures'
def reason(p): return M + 'test_a_timeout_reason_names_the_limit[' + p + ']'
RETURNS = M + 'test_run_child_returns_what_the_child_returned'
def early(p): return M + 'test_run_child_stops_the_run_on_every_early_exit[' + p + ']'
def sig(p): return M + 'test_a_runner_signal_exits_through_the_stop[' + p + ']'
SCRIPT = M + 'test_the_script_installs_the_signal_stop'
WAITS = M + 'test_stop_run_waits_for_every_process_it_found'
def reports(p): return M + 'test_run_child_reports_a_stop_that_could_not_finish[' + p + ']'
SWEEP_ON = M + 'test_a_stop_that_could_not_finish_is_reported_and_the_sweep_goes_on'
FAILED_PS = M + 'test_a_failed_ps_is_an_error_not_an_empty_table'
def launch(p): return M + 'test_a_child_that_cannot_start_is_reported_and_the_sweep_goes_on[' + p + ']'
LAUNCHES = [launch('process-limit'), launch('subprocess-error')]

MUTANTS = [
 ('new-session-dropped', R, [("text=True, start_new_session=True)", "text=True)")], [RETURNS, INTEG]),
 ('members-ignore-pgid', R, [("not (ppid in seen or pgid in gset)", "not (ppid in seen)")], [rm('orphan-in-the-group'), rm('new-session-group'), INTEG]),
 ('members-ignore-ppid', R, [("not (ppid in seen or pgid in gset)", "not (pgid in gset)")], [rm('child'), rm('grandchild'), rm('new-session-group'), INTEG]),
 ('own-group-not-excluded', R, [("if pgid > 1 and pgid != own_group and pgid not in gset:", "if pgid > 1 and pgid not in gset:")], [rm('runner-group')]),
 ('freeze-dropped', R, [("            _send(killpg, proc.pid, signal.SIGSTOP)\n", "")], [FREEZE]),
 ('member-freeze-dropped', R, [("                    _send(kill, pid, signal.SIGSTOP)\n", "")], [FREEZE]),
 ('group-kill-dropped', R, [("            for send, target in reversed(order):\n                _send(send, target, signal.SIGKILL)\n",
                             "            for send, target in reversed(order):\n                if send is kill:\n                    _send(send, target, signal.SIGKILL)\n")], [FREEZE]),
 ('kill-in-discovery-order', R, [("for send, target in reversed(order):", "for send, target in order:")], [FREEZE]),
 ('wrapper-group-not-last', R, [("for send, target in reversed(order):", "for send, target in [order[0], *reversed(order[1:])]:")], [FREEZE]),
 ('mask-not-blocked', R, [("    mask(signal.SIG_BLOCK, HELD_SIGNALS)\n", "")], [FREEZE, cut('table-fails')]),
 ('mask-not-unblocked', R, [("        mask(signal.SIG_UNBLOCK, HELD_SIGNALS)\n", "")], [FREEZE, cut('table-fails')]),
 ('finally-kill-dropped', R, [("        finally:\n            for send, target in reversed(order):\n                _send(send, target, signal.SIGKILL)\n",
                               "        except BaseException:\n            raise\n        for send, target in reversed(order):\n            _send(send, target, signal.SIGKILL)\n")], [cut('table-fails')]),
 ('first-stop-lookup-not-ignored', R, [("            _send(killpg, proc.pid, signal.SIGSTOP)\n", "            killpg(proc.pid, signal.SIGSTOP)\n")], [cut('wrapper-gone')]),
 ('wait-before-confirmation', R, [("        return _wait_gone(pids, groups,", "        proc.wait()\n        return _wait_gone(pids, groups,"),
                                  ("    finally:\n        proc.wait()\n        mask(signal.SIG_UNBLOCK, HELD_SIGNALS)\n", "    finally:\n        mask(signal.SIG_UNBLOCK, HELD_SIGNALS)\n")], [FREEZE]),
 ('gone-returns-at-once', R, [("        if not members:\n            return []\n", "        return []\n")], [gone('gone-after-polls'), gone('new-member-in-a-group'), gone('still-running')]),
 ('gone-ignores-zombie', R, [(" or 'Z' in table[pid][2])", ")")], [gone('zombie-is-gone')]),
 ('gone-never-rewalks', R, [("        members, known = run_members(table, members, known, own)\n", "")], [gone('new-member-in-a-group')]),
 ('gone-rekills-a-reused-number', R, [("        table = {pid: row for pid, row in processes().items() if pid not in gone}\n", "        table = processes()\n"),
                                      ("        gone.update(pid for pid in members if pid not in table or 'Z' in table[pid][2])\n",
                                       "        gone = {pid for pid in members if pid not in table or 'Z' in table[pid][2]}\n")], [gone('still-running')]),
 ('gone-within-1', R, [("GONE_WITHIN = 10\n", "GONE_WITHIN = 1\n")], [FIG, gone('still-running')]),
 ('gone-poll-1', R, [("GONE_POLL = 0.1\n", "GONE_POLL = 1\n")], [FIG, gone('gone-after-polls')]),
 ('limit-30', R, [("LIMIT = 300\n", "LIMIT = 30\n")], [FIG]),
 ('communicate-300', R, [("proc.communicate(timeout=LIMIT)", "proc.communicate(timeout=300)")], [RETURNS, INTEG]),
 ('except-base-dropped', R, [("    except BaseException:\n        stop_run(proc)\n        proc.stdout.close()\n        proc.stderr.close()\n        raise\n", "")], [early('interrupt'), early('signal')]),
 ('except-narrowed-to-interrupt', R, [("    except BaseException:\n        stop_run(proc)\n", "    except KeyboardInterrupt:\n        stop_run(proc)\n")], [early('signal')]),
 ('pipes-drained', R, [("        # Closed unread: a process the stop could not reach may still hold the write end.\n",
                        "        proc.communicate()\n        # Closed unread: a process the stop could not reach may still hold the write end.\n")], [early('timeout')]),
 ('run-case-no-catch', R, [("        except ChildTimeout as exc:\n", "        except ValueError as exc:\n")], [INTEG]),
 ('reason-omits-limit', R, [("ran past its {exc.limit} s limit and", "ran past its limit and")], [reason('gone'), reason('left'), INTEG]),
 ('scratch-kept', R, [("tempfile.TemporaryDirectory(prefix=f'mutant-{case.id}-')", "tempfile.TemporaryDirectory(prefix=f'mutant-{case.id}-', delete=False)")], [INTEG]),
 ('handler-returns', R, [("    raise RunnerSignal(signum)\n", "    return None\n")], [sig('term'), sig('hup')]),
 ('die-by-exit-status', R, [("    os.kill(os.getpid(), signum)\n", "")], [sig('term'), sig('hup')]),
 ('main-no-stop-on-signals', R, [("if __name__ == '__main__':\n    stop_on_signals()\n", "if __name__ == '__main__':\n")], [SCRIPT]),
 ('main-no-die-by', R, [("        die_by(caught.signum)\n", "        raise SystemExit(1)\n")], [SCRIPT]),
 # Review cycle 1's survivors, pinned by the remediation rows.
 ('sr-wait-gone-wrapper-only', R, [("        return _wait_gone(pids, groups,", "        return _wait_gone([proc.pid], [proc.pid],")], [WAITS]),
 ('rm-single-pass', R, [("    while added:\n", "    for _ in (1,):\n")], [rm('found-later-in-the-table')]),
 ('rm-own-group-seeded', R, [("g for g in groups if g > 1 and g != own_group", "g for g in groups if g > 1")], [rm('runner-group')]),
 ('rm-pid1-included', R, [("if pid in seen or pid <= 1 or", "if pid in seen or pid < 1 or")], [rm('never-init-or-kernel')]),
 ('rm-pid0-and-1-included', R, [("if pid in seen or pid <= 1 or", "if pid in seen or")], [rm('never-init-or-kernel')]),
 ('rm-group-1-added', R, [("            if pgid > 1 and pgid != own_group", "            if pgid > 0 and pgid != own_group")], [rm('never-init-or-kernel')]),
 ('wg-gone-not-filtered', R, [("        table = {pid: row for pid, row in processes().items() if pid not in gone}\n", "        table = processes()\n")], [gone('gone-numbers-never-followed')]),
 ('wg-groups-not-pruned', R, [("        known = [group for group in known if group in live]\n", "")], [gone('gone-numbers-never-followed')]),
 ('wg-strict-end', R, [("        if clock() >= end:\n", "        if clock() > end:\n")], [gone('still-running')]),
 # Additive mutants: code added, nothing removed.
 ('add-sigcont-before-kill', R, [("        finally:\n            for send, target in reversed(order):\n",
                                  "        finally:\n            _send(killpg, proc.pid, signal.SIGCONT)\n            for send, target in reversed(order):\n")], [FREEZE, cut('table-fails')]),
 ('add-wait-before-walk', R, [("            _send(killpg, proc.pid, signal.SIGSTOP)\n", "            _send(killpg, proc.pid, signal.SIGSTOP)\n            proc.wait()\n")], [FREEZE]),
 ('add-extra-look-before-confirm', R, [("        return _wait_gone(pids, groups,", "        processes()\n        return _wait_gone(pids, groups,")], [FREEZE, WAITS]),
 ('add-own-group-kill', R, [("            for send, target in reversed(order):\n                _send(send, target, signal.SIGKILL)\n",
                             "            for send, target in reversed(order):\n                _send(send, target, signal.SIGKILL)\n            _send(killpg, os.getpgrp(), signal.SIGKILL)\n")], [FREEZE, cut('table-fails'), cut('wrapper-gone')]),
 ('add-own-pid-to-members', R, [("    found = list(dict.fromkeys(pids))\n", "    found = list(dict.fromkeys([*pids, own_pid]))\n")], [rm('runner-group')]),
 ('add-sleep-before-first-look', R, [("    end = clock() + GONE_WITHIN\n", "    end = clock() + GONE_WITHIN\n    sleep(GONE_POLL)\n")], [gone('gone-at-once'), gone('zombie-is-gone')]),
 ('add-left-line-always', R, [("    if exc.left:\n", "    if True:\n")], [reason('gone'), INTEG]),
 ('add-sigint-handler', R, [("        for signum in (signal.SIGTERM, signal.SIGHUP):\n", "        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):\n")], [sig('term'), sig('hup')]),
 ('add-rewait-after-unblock', R, [("        mask(signal.SIG_UNBLOCK, HELD_SIGNALS)\n", "        mask(signal.SIG_UNBLOCK, HELD_SIGNALS)\n        proc.wait()\n")], [FREEZE, WAITS]),
 # Review cycle 2: a stop that could not finish (F4), the ps look, and the deadline's origin.
 ('wg-end-absolute', R, [("    end = clock() + GONE_WITHIN\n", "    end = GONE_WITHIN\n")], [gone('clock-not-at-zero')]),
 ('f4-no-catch', R, [("            left = stop_run(proc)\n        except Exception as exc:\n", "            left = stop_run(proc)\n        except ZeroDivisionError as exc:\n")],
  [reports('ps-cannot-start'), reports('ps-fails-mid-walk'), SWEEP_ON]),
 ('f4-catch-base', R, [("            left = stop_run(proc)\n        except Exception as exc:\n", "            left = stop_run(proc)\n        except BaseException as exc:\n")],
  [reports('interrupt-during-stop')]),
 ('f4-claims-stopped', R, [("    if exc.unfinished is not None:\n", "    if False:\n")], [reason('unfinished'), SWEEP_ON]),
 ('f4-cause-dropped', R, [("    return [f'timeout: the child ran past its {exc.limit} s limit',\n                f'the stop could not finish ({exc.unfinished}): ",
                           "    return [f'timeout: the child ran past its {exc.limit} s limit',\n                f'the stop could not finish: ")], [reason('unfinished'), SWEEP_ON]),
 ('ps-check-false', R, [("                         capture_output=True, text=True, check=True)\n", "                         capture_output=True, text=True, check=False)\n")], [FAILED_PS]),
 ('ps-unsandboxed', R, [("    ran = subprocess.run([str(SANDBOX), 'ps', '-A',", "    ran = subprocess.run(['ps', '-A',")], [FAILED_PS]),
 # Additive (review cycle 2): the error swallowed silently, "stopped" claimed after a failed look, the sweep halting.
 ('add-f4-error-swallowed', R, [("            unfinished = f'{type(exc).__name__}: {exc}'\n", "            unfinished = f'{type(exc).__name__}: {exc}'\n            unfinished = None\n")],
  [reports('ps-cannot-start'), reports('ps-fails-mid-walk'), SWEEP_ON]),
 ('add-f4-claims-stopped', R, [("    return [f'timeout: the child ran past its {exc.limit} s limit',\n", "    return [f'timeout: the child ran past its {exc.limit} s limit and was stopped',\n")],
  [reason('unfinished'), SWEEP_ON]),
 ('add-f4-sweep-halts', R, [("            unfinished = f'{type(exc).__name__}: {exc}'\n", "            unfinished = f'{type(exc).__name__}: {exc}'\n            raise\n")],
  [reports('ps-cannot-start'), reports('ps-fails-mid-walk'), SWEEP_ON]),
 ('add-f4-left-claimed-empty', R, [("        raise ChildTimeout(LIMIT, left, unfinished) from None\n", "        raise ChildTimeout(LIMIT, left, unfinished if left else unfinished and None) from None\n")],
  [reports('ps-cannot-start'), reports('ps-fails-mid-walk'), SWEEP_ON]),
 # Review cycle 2, the gate's ruling (b): a child that cannot launch is its case's own FAILED line.
 ('launch-no-catch', R, [("    except (OSError, subprocess.SubprocessError) as exc:\n        raise ChildNotStarted(",
                          "    except ZeroDivisionError as exc:\n        raise ChildNotStarted(")], LAUNCHES),
 ('launch-catch-oserror-only', R, [("    except (OSError, subprocess.SubprocessError) as exc:\n        raise ChildNotStarted(",
                                    "    except OSError as exc:\n        raise ChildNotStarted(")], [launch('subprocess-error')]),
 ('launch-case-no-catch', R, [("        except ChildNotStarted as exc:\n", "        except ZeroDivisionError as exc:\n")], LAUNCHES),
 ('launch-cause-dropped', R, [("            return [f'could not start: {exc.cause}']\n", "            return ['could not start']\n")], LAUNCHES),
 ('add-launch-swallowed-as-killed', R, [("            return [f'could not start: {exc.cause}']\n",
                                         "            return []\n            return [f'could not start: {exc.cause}']\n")], LAUNCHES),
 ('add-launch-sweep-halts', R, [("        raise ChildNotStarted(f'{type(exc).__name__}: {exc}') from None\n",
                                 "        raise\n        raise ChildNotStarted(f'{type(exc).__name__}: {exc}') from None\n")], LAUNCHES),
 ('orphan-not-waited', T, [("while os.getppid() == spawner and time.monotonic() < end:", "while False:")], [INTEG]),
]

backups = {R: SCR / 'mutants.py.good', T: SCR / 'test_mutations.py.good'}
for f, b in backups.items():
    shutil.copy2(f, b)
env = {k: v for k, v in os.environ.items() if k not in ('VIRTUAL_ENV', 'CLUSTER_MCP_TEST_ERA', 'PYTEST_ADDOPTS')}
results = []
try:
    for name, f, edits, rows in MUTANTS:
        if only and name not in only:
            continue
        text = backups[f].read_text()
        for old, new in edits:
            assert text.count(old) == 1, (name, old)
            text = text.replace(old, new, 1)
        try:
            compile(text, str(f), 'exec')
        except SyntaxError as exc:
            line = f'BOTCHED  {name}: the planted file does not compile ({exc.msg}, line {exc.lineno})'
            print(line, flush=True)
            results.append(line)
            continue
        f.write_text(text)
        assert f.read_text() != backups[f].read_text(), name  # the mutation landed
        junit = SCR / f'{name}.xml'
        ids = sorted(set(rows))
        run = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', f'--junitxml={junit}', *ids],
                             cwd=WT, env=env, capture_output=True, text=True, timeout=400)
        tags = {}
        if junit.exists():
            for case in ET.fromstring(junit.read_text()).iter('testcase'):
                mod = case.get('classname', '').split('.')
                nid = '/'.join(mod[:-1] + [mod[-1] + '.py']) + '::' + case.get('name', '')
                tags[nid] = [c.tag for c in case]
        red = [r for r in ids if any(t in ('failure', 'error') for t in tags.get(r, []))]
        missing = [r for r in ids if r not in tags]
        verdict = 'killed' if set(red) == set(ids) else 'SURVIVED'
        line = f'{verdict:8} {name}: red {len(red)}/{len(ids)}' + (f' missing {missing}' if missing else '') + \
               ('' if verdict == 'killed' else f' green {[r.split("::")[1] for r in ids if r not in red]}')
        print(line, flush=True)
        results.append(line)
        shutil.copy2(backups[f], f)
finally:
    for f, b in backups.items():
        shutil.copy2(b, f)
        assert f.read_bytes() == b.read_bytes(), f'{f} not restored'
print('restored ok')
