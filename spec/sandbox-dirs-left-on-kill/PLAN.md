# PLAN — The suite and the mutation runner leave no sandbox directory behind

> **Status:** Draft for review (re-plan) · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). This re-plan replaces the keeper design of
> `8520d9c`, which the maintainer rejected (GOAL Q4). That plan's `research/00`, `02`–`04` and
> `verify/keeper.py` stay as the record of the rejected design; only
> [`research/01-callers-and-contract.md`](research/01-callers-and-contract.md), the survey of
> callers at `0bfacae`, still informs this one. Every design element traces to a GOAL R-ID.

## 1. Summary

`bin/sandbox.sh` stays as it is (R5). A suite run points `TMPDIR`, for every process it starts, at a
directory of its own, made when the session starts; when the session ends it removes every
`cluster-mcp-sandbox.*` directory left there or in the session's pytest temporary directory, unless
a process still uses it. The mutation runner gives each case's child run the case's scratch
directory as its `TMPDIR`, so the scratch removal the runner already does takes everything the
child's sandboxes made, however the child ended. Three small changes in `tests/`, one new helper
module and its rows; nothing in the package, the harnesses' stops or the wrapper.

## 2. Design

### The suite side (R1, R3, R4)

**`tests/sandbox_dirs.py`** (new, beside `harness.py` and `ssh_server.py`; not collected):

- `SANDBOX_NAME = re.compile(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}')`, the name `bin/sandbox.sh`'s
  `mktemp -d "…/cluster-mcp-sandbox.XXXXXX"` makes (six characters on macOS and GNU coreutils), and
  `RUN_PREFIX = 'cluster-mcp-run.'`.
- `leftovers(roots) -> list[Path]`: walks each root (`os.walk`, links not followed) and returns every
  directory whose name fully matches `SANDBOX_NAME` and that is not a symlink, without descending
  into one it found. Regular files, links and other names are never returned.
- `in_use(candidates, table) -> set[Path]`, pure: a candidate is in use when some row of `table`
  (one `(cwd, environment)` pair per process) has its working directory equal to or below the
  candidate, or names the candidate anywhere in its environment text; each candidate is compared by
  its own path and its `realpath` (macOS reports `/private/var/…` for a `TMPDIR` under `/var/…`).
- `processes() -> list[tuple[str, str]]`: on Linux, read in process from `/proc/<pid>/cwd` and
  `/proc/<pid>/environ` for every process the account can read (no launch). Elsewhere (macOS): two
  launches through `bin/sandbox.sh`, as the suite's rail requires of every launch in `tests/*.py`:
  `/usr/sbin/lsof -b -a -d cwd -u <uid> -n -P -Fn` (every working directory of the account's
  processes) and `/bin/ps -E -ww -U <uid> -o command=` (each process's command line with its
  environment, where macOS shows it; § 3 row D2). A probe that cannot run raises, naming both exit
  statuses: the sweep never guesses that a directory is free.
- `sweep(roots) -> list[Path]`: `leftovers(roots)`; when there is none, return at once (no probe);
  otherwise read `processes()` once, `shutil.rmtree` every leftover not `in_use`, return those kept.
- `own_tmp(basetemp)`, a context manager: `run = tempfile.mkdtemp(prefix=RUN_PREFIX)` in the
  `TMPDIR` the process was given (which also settles `tempfile`'s own directory for the process, so
  in-process temporary files never move); save `TMPDIR`, set `os.environ['TMPDIR'] = run`; on exit
  `sweep([run, basetemp])` while `TMPDIR` still names the run directory (so the probe's own
  sandboxes, even one a probe timeout kills, land there and not in the host's `TMPDIR`), then, in a
  `finally`, put the saved value back (or remove the variable); then, unless the sweep kept a
  sandbox directory inside the run directory (one still in use), `shutil.rmtree(run,
  ignore_errors=True)`: the run directory goes with whatever this run's own processes left in it
  besides sandboxes (`uv` keeps a lock file in `TMPDIR`; links are removed, never followed). A run
  directory holding a sandbox still in use is left whole (R4; § 3 row D3 for the reading).

**`tests/conftest.py`**: one session `autouse` fixture beside `path_shim` and `skip_probes`,
`sandbox_tmp(tmp_path_factory)`, which enters `own_tmp(tmp_path_factory.getbasetemp())` and yields
the run directory. Every harness inherits `os.environ` at launch (the loopback server's `_launch`
and `sftp` Popens, `launch.run_process` through the `executes` fixture and `_sandboxed`, the MCP
stdio client, the group-stopped servers, every `subprocess.run([SANDBOX, …])`; each `env=` the
suite builds starts from `os.environ`: `child_env`, `git_env`, `broken_env`, `drive_env`, the
`outside_hook` and `test_cli` maps, surveyed 2026-11-09), so each sandbox they start makes its
directory in the run directory. The three sites that already pass `TMPDIR=tmp_path`
(`tests/test_transports.py`, `tests/test_probe_startup.py`'s `drive_env`, `tests/test_audit.py`)
keep it: their directories land in the session's basetemp, which the sweep covers, and
`test_transports`' immediate glob of its `tmp_path` is unchanged (GOAL constraint 1). The basetemp is
resolved by the fixture argument before `TMPDIR` changes, so `tmp_path` stays where it was. Session
fixtures tear down in reverse order of set-up, so every session fixture a test requests (set up after
the autouse ones) has stopped its sandboxes before the sweep runs; module and function fixtures end
earlier still. The module docstring names the new fixture with the others.

**Path lengths (GOAL constraint 2).** A sandbox's directory, and so its `HOME`, moves from
`$T/cluster-mcp-sandbox.XXXXXX` (75 bytes under this host's `$T` of 49) to
`$T/cluster-mcp-run.XXXXXXXX/cluster-mcp-sandbox.XXXXXX` (100 bytes). Nothing in the package or
the suite makes a Unix socket under `TMPDIR` or a sandbox's `HOME`: the one `AF_UNIX` bind
(`tests/test_registry.py` `make_special`) binds by name from inside its directory, in `tmp_path`,
which does not move; the loopback SSH server, the transports and the probes use TCP on loopback;
`ssh` is the PATH shim's stand-in. The planner's full prototype run passed in both eras (§ 4). A
child run of the mutation runner nests one level deeper (`$T/mutant-<case>-XXXXXXXX/…`); the
22-case sample and the controls print what develop printed (§ 4).

### The runner side (R2)

**`tests/mutants.py`**, four touch points, all outside the lines `mutant-child-outlives-timeout`
changes (its PLAN § 2: the import block's `signal` and `time`, the new run-child block before
`run_child`, `run_child`'s body, the `child = run_child(...)` line of `run_case`, one line of
`__main__`):

1. Imports: `import contextlib` after `import argparse`; `from typing import Iterator, Sequence` in
   place of `from typing import Sequence`; `import sandbox_dirs` after `import cluster_mcp.slurm`
   (the runner runs from `tests/`, and the suite imports it with `tests/` on the path).
2. `run_case`: its first line, `with tempfile.TemporaryDirectory(prefix=f'mutant-{case.id}-') as scratch:`,
   becomes `with case_scratch(case.id) as scratch:`. Nothing else in `run_case` changes.
3. New, between `run_case` and `self_check`: `case_scratch(case_id)`, a `contextlib.contextmanager`:
   `scratch = tempfile.mkdtemp(prefix=f'mutant-{case_id}-')` (the name `TemporaryDirectory` gave it),
   `os.environ['TMPDIR'] = scratch` for the block; in a `finally`, the saved value back (or the
   variable removed), then `left = sandbox_dirs.leftovers([scratch])`: when some of `left` is
   `in_use` (one process-table read, only when a sandbox directory is there at all), the scratch is
   kept and one line on stderr names it ("kept …: a process of the child run still uses a sandbox
   directory in it"); otherwise `shutil.rmtree(scratch)`. stdout, the verdict lines, never changes.

`run_child` builds its child's environment from `os.environ` at call time (`{**os.environ, …}`, today
and in the sibling's rewrite), so the child's `bin/sandbox.sh` makes its directory in the scratch, and
the child pytest inherits that `TMPDIR`: its basetemp, its own run directory and every sandbox its
tests start land there too. A child that ends normally sweeps its own (the suite side); a child the
runner stops, which never reaches its session's end (GOAL constraint 3), has all of it removed with
the scratch, which the runner removes once the stop has left nothing running (the sibling's
`_wait_gone`, then `case_scratch`'s exit). A child that ends normally but leaves a sandbox running
(its own sweep keeps that directory, in use) gets its scratch kept rather than removed under it (R4;
the adversarial review's finding 1). The same check keeps R4 on the timeout path before the sibling
lands: today's runner kills the wrapper alone and the child pytest runs on, its environment naming
its sandbox, so the scratch is kept. The sibling's own `ps` launches during the stop
take the scratch as `TMPDIR` too, and exit normally (their trap removes them). The runner is one
thread; `case_scratch` changes `os.environ` for one case at a time.

Merging: `git merge-file` of this change and the sibling's planned change (simulated from its
PLAN § 2) is clean in both orders, with the same result; the gate's `rebase` mode repeats the check
against the sibling's real branch (or `origin/develop` once it has landed). Landing order: § 3 row D5.

### Docs, same commit (§ Conventions)

- `AGENTS.md` § Factory → Throwaway environment: after "removed by a trap", one sentence: a SIGKILL
  skips the trap, so the suite points `TMPDIR` at a directory of the run's own and sweeps it at the
  session's end (`tests/sandbox_dirs.py`), the mutation runner makes each case's scratch its child's
  `TMPDIR`, and a caller outside those runs that kills a sandbox outright leaves its directory.
- `AGENTS.md` § Testing: a bullet for the `sandbox_tmp` fixture beside `skip_probes`' (what it sets,
  what the sweep removes and keeps, pinned by `tests/test_sandbox_dirs.py`); a module bullet for
  `tests/test_sandbox_dirs.py`; in the mutation runner bullet, one clause: a case's scratch is its
  child's `TMPDIR`.
- `tests/conftest.py`'s module docstring lists the fixture. Comments are declarative and carry no
  spec, phase or finding id.

### The suite's own rows: `tests/test_sandbox_dirs.py` (new)

- `unit` `test_leftovers_are_directories_with_a_sandbox_name`: names of six characters only, nested
  ones found, a file, a link and other names never.
- `unit` `test_a_directory_in_use_is_kept[...]`: `in_use` against fake tables: a working directory in
  it, below it, by its real path; beside it (not in use); its path in an environment; only its
  parent named (not in use); unrelated.
- `integration` `test_this_run_points_its_sandboxes_at_a_directory_of_its_own`: `TMPDIR` is a
  `cluster-mcp-run.*` directory, and a sandbox's `CLUSTER_MCP_SANDBOX` is in it.
- `integration` `test_the_sweep_keeps_a_running_sandbox_and_removes_it_once_killed`: a real sandbox
  under `tmp_path` that wrote a file under its `HOME`: kept while it runs, left by a group SIGKILL,
  removed by the next sweep.
- `integration` `test_the_sweep_keeps_a_sandbox_whose_command_runs_on_elsewhere`: a Python command
  that left its sandbox's directory, its wrapper SIGKILLed alone: the sweep keeps the directory by
  the command's environment. On CI's Linux this is the row that reads `/proc/<pid>/environ`.
- `integration` `test_own_tmp_redirects_children_only_and_puts_tmpdir_back`: inside `own_tmp`,
  `TMPDIR` is the run directory and `tempfile.gettempdir()` is unchanged; after it, `TMPDIR` is put
  back and the run directory (holding only a sandbox directory) is gone.

All run in each era's fourth suite command (§ 3 row D4).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | `sandbox_tmp` → `own_tmp`: every sandbox a suite run starts inherits `TMPDIR` = the run directory, or is given the test's `tmp_path` (or a directory in it); at the session's end `sweep([run, basetemp])` removes every sandbox directory in both, at any depth, that no process uses. Each harness kind of § Problem items 1–5 is a row of the gate's `kinds` mode; each of the profile `verify`'s eight suite commands is checked by the `suite` mode. Reading in § 3 row D2. |
| R2   | `case_scratch`: the child run's `TMPDIR` is the case scratch (for a case on the package and one planting a repository copy alike), so the child's own sandbox, its tests' sandboxes, its run directory and its basetemp are all inside the scratch; the scratch is removed when `run_case` leaves it, after a normal end (the child's own sweep has run) or after the sibling's stop (the `runner`, `runner-timeout` modes). Readings in § 3 rows D3, D5. |
| R3   | The sweep looks only in the run directory it made (new, so nothing in it predates the run, and no other run uses it) and the session's own basetemp (`pytest-N`, numbered for this session); in the basetemp it removes only real directories named exactly as `bin/sandbox.sh` names them; the run directory itself, which only this run's processes were given, goes whole unless a sandbox in it is still in use (§ 3 row D3). Gate: `guards` (a concurrent run, directories left before the run in three places, a file, a link, a wrongly named directory, other files). Runner side: § 3 row D3. |
| R4   | The sweep runs only once the session's tests and fixtures are done, and keeps every directory a process still has as its working directory or names in its environment (`in_use`, with both path spellings); `case_scratch` keeps a scratch holding such a directory. Gate: `guards` (a running wrapper; a command still running outside its directory after its wrapper was killed), `runner` (a child that ends normally leaving a sandbox running), `units` (the Linux `/proc` row). Reading in § 3 row D2. |
| R5   | `bin/sandbox.sh` is not edited; the `files` mode compares it with `0bfacae`, in the index and the tree. |
| R6   | No harness's signals, order or graces change, `tmp_path` does not move, and no assertion changes. The full `verify` passes in both eras with the same skips as develop on this host (`suite` mode; the planner's prototype run, § 4); the mutation sample and the controls print what develop's runner printed (`sample`; § 3 row D6). |

## 3. Invariant gate (AGENTS.md constitution check)

Checked before the design (Step 2) and again against it. The change touches no numbered section
(§1–§9): nothing under `packages/` changes, and `bin/sandbox.sh`, on the high-blast-radius list, is
only run (R5). The sections it touches:

- **§ Factory → Throwaway environment.** The contract (seven points) is unchanged; one sentence names
  the suite's and the runner's cleanup and the limitation for other callers, in the same commit as the
  fixture.
- **§ Testing.** A session fixture beside `skip_probes` and `path_shim`, the same shape (sets an
  environment variable for every test and child, puts the caller's value back); a new module bullet;
  the mutation runner bullet; § Testing's internals-bound item 5 (`tests/mutants.py` and its anchors):
  no case and no anchor moves (`test_mutation_anchor_applies` stays green). Every new test carries
  `unit` or `integration`; unit rows launch nothing; every launch in `tests/*.py`, the sweep's `lsof`
  and `ps` included, starts with `str(SANDBOX)` (`test_cli_drives_are_sandboxed`). No row skips
  (the `need_shell`/`need_git` rule).
- **§ Factory, `ci budget`.** The new module runs in each era's fourth command; the session sweep runs
  in each of the eight; their cost is row D4.
- **§ Conventions.** Declarative comments, no spec ids (`test_no_spec_ids_in_the_package_or_the_suite`),
  no `Co-Authored-By`, docs in the same commit, a rule pointed to rather than restated.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **D1 — One run directory for every harness, set once in the session's environment**, rather than a `TMPDIR` each harness passes. Q4 names the mechanism ("each harness … points the sandbox's `TMPDIR` into a directory it owns"); here the directory is owned by the run, and every harness gets it by inheriting `os.environ`. The three sites that already pass `tmp_path` keep it. | Every harness of items 1–5 and every `env=` the suite builds start from `os.environ` (surveyed, § 2), so one fixture covers ~45 launch sites and any site added later; a harness edited one by one is a carve-out waiting to be missed (the gate's additive mutant `ssh-drops-tmpdir` is exactly that). | Passing `TMPDIR` at each of the eight harness kinds and ~25 `subprocess.run` sites: three times the diff, each new site must remember it, and the session sweep is needed anyway for `tmp_path` and for the sites' own leftovers. |
| **D2 — R1/R4 reading (needs the sign-off): "still running" is what the host shows the account.** A directory is in use while some process has its working directory in it or the directory's path in its environment, as `/proc` (Linux, every process of the account) or `lsof` and `ps -E` (macOS) show them; in use, it is kept, and R1 is read as covering a sandbox none of whose processes is seen using its directory at the session's end. macOS shows no environment for a system binary (`/bin/sh`, `/bin/sleep`, `/usr/bin/git`; measured 2026-11-09), and `env -i` commands carry none of the sandbox's variables. So one case is not seen: a sandbox whose wrapper was SIGKILLed **alone**, whose command still runs at the session's end (or, in the runner, at the case's end), outside the sandbox's directory, as such a process. Its directory is removed while it runs. A sandbox still running at the session's end is kept and removes its own directory when its command ends (its trap): `test_launch`'s split-end-record row does that on purpose, leaving `sleep 8` running past its test, so each era's third command ends with one running (the gate's `suite` mode lets such sandboxes end, up to 30 s, before it judges R1). A wrapper dies alone on a `subprocess.run` timeout (which fails its test; `need_git` skips instead, but its `git` keeps its working directory in the sandbox and is seen), on a loopback `signal` request the command ignores (QUIT, USR1, USR2), and under the delegate stand-in, which runs the command in a session of its own; the harness kills each of these before the session ends (`close()`, the pid-file teardowns). | Without changing `bin/sandbox.sh` (R5), nothing ties a process to a sandbox but its working directory and its environment; the wrapper itself always has its working directory there, and a command started there keeps it unless it changes directory. The gap needs a test that has already failed by timeout and a command that both left the directory and hides its environment, still running when the whole session ends. | (a) Keep every leftover while any process with an unreadable environment exists: on macOS that is always (every system daemon), so R1 would never hold there. (b) Wait at the session's end for orphans to finish: there is no way to tell which orphans are a sandbox's, and it is a timing figure for an unbounded wait. (c) A marker or lock inside the wrapper: R5. |
| **D3 — R3 reading (needs the sign-off): a directory the run made for its own processes' `TMPDIR` goes whole.** The suite's run directory and the runner's case scratch are each given only to this run's processes; each is removed with whatever those processes left in it, sandbox directories or not, unless a sandbox directory in it is still in use (`own_tmp`, `case_scratch`). R3's "anything that is not a sandbox directory" is read as anything this run did not make for itself; in the basetemp (tests' `tmp_path`, which the developer may inspect) and everywhere else, only sandbox directories are removed. | `uv` keeps a lock file (`uv-<hash>.lock`) in `TMPDIR`: under the strict reading a run directory holding one could never go, and the prototype's first full run, with `rmdir` only, left 4 of its 8 run directories behind, two holding that lock (a new leftover per session, where today one shared lock sits in `$T`). Q4 names "the mutation runner's own scratch"; a stopped child never runs its own sweep (constraint 3); and today a child's basetemp lands in the developer's `$T/pytest-of-<user>/`, where its rotation deletes the developer's older basetemps. | The strict reading: `rmdir` only; a `cluster-mcp-run.*` directory left per session that ran `uv`, and on the runner side a leftover per case (the child's basetemp). |
| **D4 — Timing figures for the maintainer** (before → after, measured 2026-11-09 on this host; § 5 names the runs). **Session sweep:** none → 0.15–0.23 s in six of each `verify`'s eight sessions, 1.46–2.19 s in the two catch-all sessions (each era's fourth command), whose basetemp holds a built environment (a walk of ~92,000 entries takes about 1.1 s); synthetic: 10 ms with no leftover, about 0.23 s with 60 (the `cost` mode). **Whole `verify`:** 1,637.8 s (develop) → 1,592 s (the prototype's second run); the sweeps add up to about 4.3 s of that run, and the difference between the runs is noise. The `suite` mode itself waited up to 6 s after a command for a sandbox still running to end. **Mutation child session:** none → 0.4–2.3 ms (9 children of an 8-case sample); `case_scratch` reads the process table only when a sandbox directory is left in the scratch (about 0.2 s: a timed-out case or a stray). **New rows** (`tests/test_sandbox_dirs.py`, each era's fourth command): about 1.5 s per era. **Leftovers per `verify`** (develop, the same run): legacy 11 + 42 + 18 + 8, modern 14 + 44 + 17 + 17, 171 in all → 0. **P3's gate run** (2026-11-12, the built tree at `bca649e`, the `suite` mode under a fresh `TMPDIR`, host load about 5–6 against the planner's quieter host): legacy 212, 145, 212, 216 s and modern 213, 146, 223, 219 s, 1,586 s for the eight commands (the planner's prototype run: 1,592 s for the whole `verify`); 0 sandbox directories left after each command, the settle window used for up to 6 s (legacy command 3, `test_launch`'s split-end-record row); two empty `cluster-mcp-run.*` directories; the 28 skips are develop's. The `mutants` mode before it took about 4.3 minutes for 26 plants. | The sweep walks the run directory and the basetemp and, only when it finds a leftover, reads the process table once. | Not sweeping: R1. A walk of the basetemp limited to `tmp_path` and one level below (the depth every site uses today) would bring the catch-all sessions to the others' ~0.2 s, but misses a sandbox put deeper (the gate's `group-kill-nested` row; the additive mutant `top-level-only`): the maintainer's call. |
| **D5 — Landing order (needs the foreman): P2 builds on `mutant-child-outlives-timeout`'s stop.** Build rebases onto `develop` once the sibling has landed and before P2; until then P2's `runner-timeout` mode is red by design ("no LIMIT"). The text merges cleanly in either order (`rebase` mode). | R2 on the timeout path holds only with the sibling's stop (GOAL constraint 3): today's runner kills the wrapper alone and the child runs on. R4 holds in either order (`case_scratch` keeps a scratch a running child still uses), but the timeout row that shows R2 needs the sibling's patchable `LIMIT`; at 300 s it would cost five minutes per run. | Landing first with P2's timeout row deferred: the row is R2's only evidence on the path the GOAL names ("a case whose child run passes its time limit included"). |
| **D6 — R6 for the mutation runner is shown by a 22-case sample and the three `--self-check` controls**, against develop's runner on this host (`verify/sample.expected`), not a sweep of all 1,165 cases. Same sample and reading as the sibling's D7 (settled there at its PLAN/TECH gate, 2026-11-09). | The runner's change is one environment variable for the child; the sample covers every family of child (executors, loopback SSH, launcher, startup, probes, timeout stop, repository plants), and its deeper paths. A full sweep is 49–97 minutes, twice. | The full sweep per phase: past the 10-minute command cap, for a `small` appetite. |
| **D7 — On macOS the sweep launches `lsof` and `ps` through `bin/sandbox.sh`**, only when it found a leftover: about 0.1 s for the two, plus each wrapper (measured 2026-11-09). | The rail requires every launch in `tests/*.py` to go through the sandbox; Linux needs no launch (`/proc`). | Exempting `tests/sandbox_dirs.py` from the rail loosens a gate for every later change. |

Each row was read against R1–R6's wording. D2 and D3 read an R-ID in a way its words do not settle
(R4's "still running", R1's "however … ended"; R3's "anything that is not a sandbox directory" on the
runner side): both go to the sign-off as GOAL clarifications. D5 is a sequencing question for the
foreman. D4 holds figures for the maintainer.

## 4. Rabbit holes (resolved)

The lean path (`kind: fix`, `appetite: small`, root cause known): no fan-out. Trigger 2 does not fire
(no high-blast-radius path is touched; R5); trigger 3 fires (the deliverable is test infrastructure),
so the adversarial review ran (below). `research/01` (callers at `0bfacae`) still holds; the other
briefs are the rejected design's record.

- **Does every harness inherit the session's environment?** Yes: every launch site of items 1–5 passes
  no `env` or one built from `os.environ` at call time; only three set `TMPDIR`, to `tmp_path`.
  The planner's prototype (a detached worktree, removed before the report; its diff is
  [`verify/prototype.diff`](verify/prototype.diff)) proved it per kind: the
  gate's `kinds` mode passed on it, every row's directory made in the run directory (or `tmp_path`, or
  a directory nested in it) and left by its kill; on develop the same mode fails every kind (a
  control run).
- **What does macOS show of another process?** `lsof -a -d cwd` lists every working directory of the
  account's processes (`/private/var/…` spellings; about 0.1 s for ~870 processes); `ps -E` shows the
  environment of the account's processes except system binaries (D2). Linux's `/proc` shows both.
- **Path lengths** → no socket under `TMPDIR` or a sandbox's `HOME` anywhere (§ 2); the full prototype
  run passed in both eras, and the mutation sample with its deeper child paths printed exactly what
  develop printed.
- **Does a run leave anything else in its run directory?** Yes: `uv`'s lock file (two of eight run
  directories in the prototype's first full run), and in each era's third command one sandbox still
  running at the session's end (`test_launch`'s split-end-record row, by design), whose own trap
  removes it seconds later. Hence D3's reading and the `suite` mode's settle window.
- **Merging with the sibling** → three touch points, each at least one unchanged line from the
  sibling's planned hunks (git conflicts on adjacent changes; checked with `git merge-file`).
- **Adversarial review** (one reviewer, appetite small, 2026-11-09; it ran the gate's quick modes on
  the prototype and on planted copies). Nine findings, all folded:
  1. HIGH: a child that ends normally leaving a sandbox running had its directory removed with the
     scratch (R4), a path D5 did not cover → `case_scratch` checks before removing, and the `runner`
     mode gained the row (§ 2).
  2. An additive mutant, "remove only skeleton-only leftovers", passed every quick mode (no row's
     leftover held a file) → the group-kill rows, the run-timeout row and the suite row write under
     `HOME` first; plant `skeleton-only`.
  3. An R3 mutant, "also sweep the given `TMPDIR` for directories made since the run began", passed →
     `guards` has an ad hoc caller's leftover made top level during the run; plant `sweep-since`.
  4. No mode exercised the Linux `/proc` branch → the env-kept row moved into the suite, which CI
     runs on Linux.
  5. The `suite` mode could not see a launch that drops `TMPDIR` (it falls to `/tmp`) → it now fails
     on a new sandbox directory in `/tmp` during a command.
  6. D2 named only one way a wrapper dies alone → reworded (three ways).
  7. No mode ran with `TMPDIR` unset, as CI does → `units` runs twice, set and unset.
  8. A probe timeout would leak the probe's own sandbox into the host's `TMPDIR` → the sweep runs
     before `TMPDIR` is put back; `lsof -b`.
  9. `runner` drove only a case on the package → it also drives one planting a repository copy.
  Refuted by the reviewer: the socket-path limit, an `env=` not built from `os.environ`, launches at
  collection, a session fixture outliving the sweep, anchor drift, threads racing `os.environ`.

## 5. Risks & open questions

- **Questions for the sign-off:** D2 and D3 (readings of R1/R4 and R3), D5 (landing order), D4 (the
  figures). And whether the GOAL's known limitation (callers outside the repository's runs) wants a
  record beyond `AGENTS.md`'s sentence: the seed `issues/sandbox-dirs-left-on-kill.md` is retired
  when this lands. The plan filed no new seed; the build filed two, on the foreman's rulings
  (2026-11-12): `issues/sandbox-dirs-outside-repo-runs.md`, the GOAL's two known limitations (a
  caller outside the repository's runs that SIGKILLs a sandbox; the run itself SIGKILLed), and `issues/mutant-case-cleanup-interrupted.md`
  (a second signal during a mutation case's cleanup); both pre-existing.
- **The seed's "last three" referent** (GOAL Clarifications): fixed by whichever of this cycle and
  the sibling lands second, at its landing; P3 carries the item.
- **An empty run directory per era.** Each era's third command ends with `test_launch`'s
  split-end-record sandbox still running, so its run directory is kept (D3) and, once that sandbox's
  trap has removed its own directory, stays empty: two empty `cluster-mcp-run.*` directories in `$T`
  per `verify` (the prototype's second run), where develop leaves 171 sandbox directories.
- **A session killed outright** keeps its run directory and what is in it (GOAL non-goal). It is one
  `cluster-mcp-run.*` directory per killed session in `$T`, where today it is the sandbox
  directories themselves.
- **pytest-xdist or another plugin that runs tests in other processes** would give each worker its own
  session and run directory; none is installed.
- **Figures named by run.** Before: develop at `4ea17e0` (`0bfacae` plus `spec/`), the profile's
  eight suite commands under a fresh `TMPDIR`, 2026-11-09 17:41. After: the planner's prototype of
  this design at the same base, the gate's `suite` mode: a first run (18:08, part of the design
  still changing during it: the source of D3 and the settle window) and a second on the final
  prototype (2026-11-09 evening), whose figures D4 quotes. P3's `suite` mode prints each
  command's time and leftover count again.

## 6. Verification strategy

The frozen gate is [`verify/cleanup.py`](verify/cleanup.py); its docstring lists the modes. Every
planted mode runs in a copy of the index (what the phase staged), under a gate-owned `TMPDIR`, with a
planted test module that drives the repository's own harnesses; it never edits the worktree.

- **P1** `files units kinds guards`, then the narrowed suite: `tests/test_sandbox_dirs.py`,
  `tests/test_transports.py` (constraint 1), `tests/test_hygiene.py` (the rail, the unset anchors),
  `tests/test_suite_parts.py` (the partition).
- **P2** `files rebase runner runner-timeout sample`, then `tests/test_mutations.py`.
- **P3** `files ledger mutants`, then `suite` (the whole `verify`, both eras, about 26 minutes, in the
  background).

**The mutant sweep** (P3 writes `verify/mutants.json`; the `mutants` mode applies each plant to a
staged copy and requires the named mode to fail with the named message). Decisions it must cover
(the gate's `DECISIONS`), each with at least one plant; the planner's draft against the prototype,
[`verify/mutants.draft.json`](verify/mutants.draft.json), was dry-run against the final prototype ([`verify/prototype.diff`](verify/prototype.diff)): all 24 plants killed, each by its named mode and message:

| Decision | A plant | Killed by |
|---|---|---|
| `redirect-set` | `own_tmp` never sets `TMPDIR`; the fixture not autouse | `kinds` |
| `redirect-pinned` | `tempfile.tempdir = None` after the redirect | `units` |
| `redirect-restored` | `TMPDIR` not put back | `units` |
| `sweep-run-dir`, `sweep-basetemp` | the sweep skips one location (additive) | `guards` (skipped, the run directory would go with a sandbox in it still in use), `kinds` |
| `sweep-nested` | the walk stops below a depth (additive) | `kinds` (`group-kill-nested`) |
| `name-exact` | any length after the dot; a prefix match | `guards` |
| `name-dir-only`, `no-links` | links taken; files taken; links followed | `guards` |
| `live-cwd`, `live-env`, `live-realpath` | each half of `in_use` dropped; the literal path only; no probe | `guards` |
| `run-dir-rmdir`, `run-dir-kept` | the run directory never removed; removed even while a sandbox in it is in use | `kinds`, `guards` |
| `runner-tmpdir`, `runner-restored`, `runner-live` | `case_scratch` sets no `TMPDIR`; never puts it back; removes a scratch still in use | `runner` |
| `sweep-content` | only leftovers holding no file are removed (additive) | `kinds` |
| `no-outside-sweep` | an extra sweep of the given `TMPDIR` for directories made during the run | `guards` |
| `harness-not-redirected` | the loopback server's launch drops `TMPDIR` (additive) | `kinds` |
| `runner-unlisted` (added at P2's build) | `case_scratch` raises, or removes the scratch, when the process listing fails | `units` |

---

*Backing research: [`research/01-callers-and-contract.md`](research/01-callers-and-contract.md)
(callers at `0bfacae`). `research/00`, `02`–`04` and `verify/keeper.py` are the rejected design's
record (`8520d9c`).*
