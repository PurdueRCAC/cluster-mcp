# 02 — What the sibling cycles' stops reach, and what they assume about the sandbox home

Read-only brief, 2026-11-09. Sibling paths are in their own branches: `fix/mutant-child-outlives-timeout`
(GOAL, PLAN, TECH, `verify/gate.py` under `spec/mutant-child-outlives-timeout/`, cited "MC") and
`ci/mutants-workflow-timeout` (GOAL only, cited "WT"). Base is `0bfacae`.

## 1. What the sibling's stop reaches

- **Start.** `run_child` becomes `Popen(..., start_new_session=True)`, so the `bin/sandbox.sh`
  wrapper leads a new session and process group (MC PLAN:32-39).
- **Walk rule.** `run_members` adds every process whose **parent is a known pid** or whose **pgid
  is a known group**, plus that process's group, to a fixpoint (MC PLAN:57-63). The table is
  `pid=,ppid=,pgid=,stat=` (MC PLAN:51-55): **sessions are not read or walked**. The runner's own
  pid and group are never added.
- **Order** (MC PLAN:65-93): block INT/TERM/HUP; `killpg(wrapper, SIGSTOP)`; then the fixpoint,
  taking a table, SIGSTOPping each new pid and group, and taking a new table until one adds nothing.
  Every table is taken **after** the first freeze. Then SIGKILL in reverse discovery order, the
  wrapper's group last, with a `finally` that kills whatever was found. Then `_wait_gone`, and
  only after that `proc.wait()`.
- **`_wait_gone`** (MC PLAN:86-91): until `GONE_WITHIN = 10` s, poll every 0.1 s. Each poll
  re-walks a fresh table with `run_members`, so a process with a member parent or a run group is
  added late. It drops absent and `Z` members and returns `[]` when no member is left. It waits for
  run members only, never for a pipe EOF: the stdout/stderr pipes are closed unread (MC PLAN:41-43,
  194-196).
- **The settled reach** (MC GOAL:96-101, PLAN D1:168): a process that "left every group of the run
  (`setsid`, `setpgid`) and lost its parent before the stop … is not found".

**(a)+(b), a watcher in its own session and group whose parent is pid 1 (or a subreaper outside
the run): not found.** Its ppid is no member, its pgid is no run group, and the sid is never read.
It also gets no signal from the stop, since the stop only `kill`s or `killpg`s found members.

**Linux caveat.** An orphan is reparented to the nearest `PR_SET_CHILD_SUBREAPER` ancestor, not
always pid 1. If such an ancestor were a run member, the watcher's ppid would be a member and the
watcher would be found. The usual subreapers (systemd --user, tini, docker `--init`) sit above the
runner. macOS reparents to launchd (pid 1).

**The race window.** During detach, the intermediate is a child of the wrapper, and the watcher
is its child or sits in the wrapper's group until `setsid()`. In that state both are reachable
through the walk (by ppid or by group), and so is the `killpg(SIGSTOP)`. The window runs from the
wrapper's fork to the intermediate's exit plus the grandchild's `setsid()`. That is a fork plus an
exec of a `setsid` helper: about 1–5 ms on an idle host, tens of ms under load, and roughly
20–50 ms more if the helper is an interpreter. **macOS ships no `setsid(1)`** (checked on this
host: only `perl` and `python3` exist). The sibling's stop fires at `LIMIT` (300 s; 8 s in its
integration row), and the whole child takes about 1.5 s to get ready (MC PLAN:228-231). Against
the sibling the window is therefore closed by four orders of magnitude, not by structure. It
matters for a caller that SIGKILLs a group within milliseconds of its start. That is closed
structurally only if the wrapper does not proceed until the watcher reports it has detached. Even
better, the detached watcher makes the directory itself and hands its path back, so a kill before
the hand-off still ends in EOF and removal.

## 2. Assertions a per-sandbox watcher could trip

- **Leftover process check.** The `rows` mode runs `pgrep -f 'mutant-hang-'` after the test run and
  fails on any match (MC gate.py:17, 51, 287; `rows_violations` :275-276). The runner's scratch
  prefix is `mutant-{case.id}-` (`tests/mutants.py:5751`), so the integration row's `hang` case
  puts `mutant-hang-…` into the wrapper's argv (`src_root`, `junit`). **The watcher's argv must
  never copy the wrapper's `"$@"`, its junit path or its src path.** Otherwise a watcher still
  alive at `pgrep` time fails the gate.
- **Process counts and ps assertions.** The integration row checks only the pids it recorded (the
  pytest, the wrapper, three sleepers carrying the token, and two sentinels), as gone, a zombie,
  or "running and not stopped" (MC PLAN:294-316). Nothing counts processes or matches `sandbox`
  in argv. Unrecorded watchers are invisible to it.
- **Pipe EOF.** On a child that ends within its limit, `communicate()` reads stdout and stderr to
  EOF (MC PLAN:32-37). A watcher holding the wrapper's stdout or stderr would hold that read
  open, and would change the `within-limit` gate's timing and possibly its text (MC gate.py:18-21).
  **The watcher's stdio must be `/dev/null`.**
- **Sandbox starts per stop.** `_processes()` runs `bin/sandbox.sh ps -A -o …` once per table,
  about 30 ms each (D6, MC PLAN:173, 188). A stop takes at least 2 fixpoint tables plus at least 1
  `_wait_gone` table. That is about 3–4 sandbox starts per timed-out case ("two or three tables at
  about 30 ms, one confirmation look", MC PLAN:221-222), plus 1 per extra poll, and 0 extra for a
  case within its limit. The per-start cost of this fix multiplies across those starts, and also
  across every nested sandbox a case's targets start (for example `LoopbackSSH` execs), which
  inherit the host `TMPDIR` because `run_child` passes `os.environ` through
  (`tests/mutants.py:5692-5699`). The sibling's D3 "about 0.1 s" after the limit shifts by about
  4× the watcher spawn cost.
- **Harmless.** Watchers of earlier `ps` sandboxes appear in later tables, but their parent is
  pid 1 and their group is their own, so they are not members.

## 3. The integration row and sandbox homes

The row sets "`TMPDIR` … to a directory under `tmp_path` for the row, so the sandbox homes the
killed wrappers leave go with `tmp_path`, not into the host's temporary directory" (MC
PLAN:300-301; reason in PLAN:388). It **asserts nothing about sandbox directories**. Its "scratch
directory empty" check is on the patched `tempfile.tempdir` (the runner's `mutant-*` copies), not
on `TMPDIR` (MC PLAN:303, 312). It does not rely on a home existing, so our fix leaves its outcome
unchanged.

One latent coupling: if a build pointed `tempfile.tempdir` and `TMPDIR` at the same directory, the
"empty" assertion would race the watcher's removal. Base already fails that way, so the sibling
must already keep them apart. The PLAN does not say so explicitly.

Sentences that state the home stays after the stop:

- MC PLAN:95-98: "The wrapper's `trap` does not run, so its sandbox home stays, which the GOAL leaves
  to `issues/sandbox-dirs-left-on-kill.md`; no second cleanup is built here."
- MC TECH:115-117: "…the whole run SIGKILLed, `bin/sandbox.sh` included); its home is still left,
  which is that seed's."
- MC GOAL:23-25 describe base ("never removes its throwaway home either"). That stays true as
  history.

## 4. mutants-workflow-timeout

WT is GOAL-only: no PLAN, and Q1–Q4 are open (WT GOAL:96-122). It may split the run into shards
or run cases concurrently (WT GOAL:108). It sets no `TMPDIR`, kills nothing itself, and leaves
`run_child`'s timeout to MC (WT GOAL:83-85). `mutants.yml` sets no `TMPDIR` (`mutants.yml:21-45`),
so sandboxes go to `/tmp` on `ubuntu-24.04`. Concurrency multiplies live sandboxes, which makes R4
(no cross-sandbox removal) and per-start cost matter more.

On a cancelled or timed-out job, the Actions runner signals the step's process tree (SIGINT, then
SIGTERM, then a kill; this is recalled runner behaviour, not verified here). At job end it also
"cleans up orphan processes" by the `RUNNER_TRACKING_ID` it puts in every step's environment, and
`bin/sandbox.sh` does not blank that variable. A detached watcher would therefore usually be
killed at job end, but **it does not matter**: the hosted VM is discarded with its `/tmp`. What
does matter on CI is stdio: a background process holding the step's stdout can keep a step open,
which is one more reason for `/dev/null`.

## 5. Shared files and merge order

- **Seed `issues/sandbox-dirs-left-on-kill.md`.** Both branches carry the **identical** hunk at
  :23-25 ("The mutation runner kills its sandbox outright too: `tests/mutants.py` `run_child`, on
  its 300 s timeout, where `subprocess.run` SIGKILLs the `bin/sandbox.sh` it started."), so that
  hunk merges cleanly. That sentence now separates the list from "The last three point the
  drive's `TMPDIR` at the test's own directory" (:25), which meant `test_transports.py`,
  `test_probe_startup.py` and `drives.py`, so the referent is broken.
- **A contradiction.** Our GOAL's Clarification says the sentence is carried "verbatim from
  `mutant-child-outlives-timeout`'s shape commit, whose build does not rewrite it". But MC
  PLAN:121-123 and TECH:114-117 schedule P1 to rewrite it to the new mechanism. If both branches
  edit that paragraph, they conflict. If ours retires (deletes) the seed at landing, a later MC
  build edit becomes a modify/delete conflict.
- **MC's frozen gate pins `BASE = 71a3a49`** (gate.py:44). `untouched` fails any path outside
  `ALLOWED` (and `spec/<slug>/`) with status ≠ `M`, diffed against that fixed BASE, and fails any
  `AGENTS.md` change outside the mutation-runner bullet (gate.py:229-252). **If we land first**
  and MC rebases, our `bin/sandbox.sh`, `ROADMAP.md`, `spec/` and any § Throwaway environment edit
  trip MC's `untouched`. A deleted seed shows as `D` and trips it too. The gate is "never edit"
  (MC TECH:57-60), so that becomes a foreman stop. Landing MC first avoids this; our gate should
  diff against the merge-base, not a pinned commit.
- **`ROADMAP.md`.** The edits are in separate sections (MC :100-103, ours :155-158), so they
  merge cleanly.
- **`tests/mutants.py`.** Only MC edits it.
- **`AGENTS.md`.** MC edits only the § Testing bullet. Ours, if any, is in § Factory, Throwaway
  environment: text-disjoint, but subject to the gate issue above.

## Implications for the design

- Detach completely before the stop can ever see the watcher: double fork, new **process group
  and session**, intermediate exits. The walk needs only a non-member parent and a non-run pgid,
  but `setsid` also keeps it clear of session-leader and terminal SIGHUP. Ignore HUP in the
  watcher anyway.
- macOS has no `setsid(1)`. Choose the detach primitive deliberately (perl or python `setsid`, or
  another route) and measure its spawn cost. That cost multiplies by about 3–4 per timed-out case
  (MC's `ps` tables) and by every nested sandbox.
- Close the start-up race structurally. The wrapper should not run the command until the watcher
  confirms it has detached, ideally with the watcher creating the directory itself.
- The watcher's stdio must be `/dev/null` and its cwd `/`. It must inherit no fd except its pipe
  end, and the command must not inherit the pipe's write end, or escapees delay EOF.
- The watcher's argv must hold only the sandbox path, never the wrapper's `"$@"` (MC's
  `pgrep -f mutant-hang-` gate).
- Wait on pipe EOF, not on the wrapper's pid: MC reaps the wrapper only after `_wait_gone`, so the
  wrapper lingers as a zombie for up to 10 s. Treat a zombie command as gone, as MC does.
- R2's mutation-runner row can be observed without editing `tests/mutants.py`. Run the runner
  with `TMPDIR` pointed at a fresh empty directory (`run_child` passes `os.environ` through), then
  check the directory after the bound. For the timeout path, run MC's integration row with
  `--basetemp=<dir>` and glob `cluster-mcp-sandbox.*` under it afterwards. Before MC lands, use a
  driver that imports `mutants`, patches `CASES` to a hang case and the timeout, and calls `main`.
  This depends on landing order.
- Stale after landing: MC PLAN:95-98, MC TECH:115-117, MC PLAN:300-301 and :388 ("homes the killed
  wrappers leave"), and MC D4's rejection rationale (PLAN:171). Also MC GOAL:100-101 and PLAN D1:168
  ("in the suite only the rows that make such an escape on purpose do that"): every sandbox now
  makes one, as upkeep.
- Resolve the seed-sentence contradiction and the "last three" referent with the foreman. Prefer
  MC landing first, given its BASE-pinned frozen gate.
