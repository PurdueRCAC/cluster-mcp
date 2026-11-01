# 04 — The previous cycle's gate scripts, and what to reuse

Paths are relative to `spec/capability-extras/` unless rooted. `V` = `verify/`, `R` = `remediation/`.

## 1. Structure

- **Modes.** Each `pN.sh` takes `phase|mutants|full|full-legacy|full-modern|all` (`V/p1.sh:21-22`);
  the last phase adds `ledger|recipe` (`V/p5.sh:21`). `phase` runs the independent checks, then the
  phase's named pytest ids in both eras via `pytest_both` (`V/lib.sh:25-36`; a missing id exits 4,
  so a gate never passes on an unwritten test). `mutants` = every case planting into the files the
  phase rewrites plus named new ids (`cases_for`, `V/lib.sh:40-52`; `run_mutants --self-check`,
  `:56-59`). `full` is split into `full_legacy`/`full_modern` "so a caller with a 10 min command cap
  can split it" (`V/lib.sh:64-66`). `ledger` and `recipe`: `V/p5.sh:37-42`.
- **Footprint headers.** Every script states processes, memory and wall time in its header
  (`V/p1.sh:10-18`, `V/coreonly.sh:22-23`, `V/planted.sh:39-40`, `R/F7-mutant-alternatives.py:36-47`).
  `lib.sh` promises one process tree at a time, nothing backgrounded, no self-deletion — scratch lives
  in the sandbox HOME that `bin/sandbox.sh` removes (`V/lib.sh:5-7`).
- **Process groups.** The capability-extras gates contain **no** `set -m`, `kill -- -pid` or `pgrep`
  (grep of `verify/` and `remediation/` is empty). Process-group hygiene lived in Python: the suite's
  transport drives (`tests/test_transports.py:82-132`, `start_new_session` + `os.killpg` + a
  leftover assert) and the CLI drives F4 runs "each in its own process group" (`R/F4-load-refusal.sh:18-19`).
  The one gate-level HTTP drive uses `subprocess.run(timeout=60)` with no process group
  (`V/planted.sh:140-149`), which kills only the direct child. The pattern to copy is the earlier
  cycle's `spec/agents-d-instructions/verify/serve_gate.py:125-180` (`start_new_session=True`,
  `os.killpg(SIGKILL)` in `finally`) and its end-of-run `pgrep -f <shim>` must-be-empty assert (`:360-361`).
- **Self-sandboxing.** Shell gates re-exec themselves under `bin/sandbox.sh` when
  `CLUSTER_MCP_SANDBOX` is unset (`V/planted.sh:44-46`, `V/coreonly.sh:25-27`); `served.py` refuses
  to run outside it (`V/served.py:42-43`).
- **Dry-run and red-first.** At plan time each gate was dry-run on the then-current tree: `baseline.sh`
  passed and caught a planted control; the others failed "for the reasons each phase must remove"
  (`PLAN.md:329-332`). Every class checker and amended step was "seen red first" on a planted defect
  or the unfixed tree (`TECH.md:615`, `:640`). Gates are frozen once committed; a red the foreman
  rules a gate defect is fixed by a wrapper under `remediation/`, not an edit (`TECH.md:678`,
  `R/P5-ledger-headings.py:4-12`).
- **Recorded times.** Each `Verify` line is followed by an italic *Observed (date), on tree X* record
  with counts per step and era (`TECH.md:635-646`); steps whose inputs did not change "stand in" from
  an earlier run, and the record says which (`TECH.md:693`). Red runs are recorded as *Attempt n*
  and bump `attempts:` in the frontmatter (`TECH.md:23`, `:322-326`, `:490`, `:597`, `:669`).

## 2. Reuse

Nearly as they are (change `V=`, `SPEC=` and `BASE_REF`):
- `lib.sh` whole (`pytest_both`, `cases_for`, `run_mutants`, full halves).
- `baseline.sh` + `surface.py` + `compare.py` + `kept.py` + `retired.txt` — R3's "nothing changes when
  every probe reports present" and the fixture/`test_surface.py` byte-identity (`V/baseline.sh:52-55`).
  Caveat: `surface.py` builds the server in process (`V/surface.py:8-10`) and so never runs a probe;
  R3 needs a CLI drive with probes stubbed present as well.
- `served.py` + `expect.py`: a stdio listing of tools, resources and the base, cross-checked
  (`V/served.py:49-59`). This is the right check for R1/R3's withheld sets. `expect.py` needs a
  "drop capability X" input.
- `planted.sh`'s `dist`/`capability` helpers (`V/planted.sh:58-85`): a dist-info plus module first on
  `PYTHONPATH`, no tree edit.
- `docs.py` (section reader, `V/docs.py:21-23`) with new phase rules for §4, §7, §9, § Configuration
  and the README (R10).
- `ledger.py` with the heading fix folded in (see §3).
- The F7 sweep's shape (`coverage|cases|equivalents`, per-member-set rows, `SET_EQUIVALENT`;
  `R/F7-mutant-alternatives.py:33-47`, `:521-571`).

Need a new form:
- **A planted capability with a probe**: present, absent, raises, `SystemExit`, hangs past the bound,
  returns something malformed, and no probe at all. Each is driven on stdio, with stdin closed and
  over HTTP, asserting exactly one stderr line and the served surface.
- **A stub-command `PATH`** for `local` mode. Copy the suite's `path_shim` (`tests/conftest.py:171-190`):
  a login bash rebuilds `PATH`, so the stub dir must also come back through `BASH_ENV`. Stubs should
  append to an invocation log, so that "no probe ran" (R5, R7, R8, R9) is checked on the log, not
  inferred from the output.
- **A slow or broken executor** for the bound and fail-open (R5, R6): hang, lost connection, could not
  run. Build it in-process from `tests/harness.py:658` (`RecordingExecutor`, `responder`). At the CLI
  level, use a stub that sleeps, timed to the first stdio answer, with process-group kill and a
  `pgrep` leftover assert.
- **`ssh` mode** drives only through the suite's `ssh` stand-in (`tests/conftest.py:171-181`). Never
  use a real host.

## 3. Defects found in or behind the gates, and their lessons

1. **Mixed resolution modes.** `probe.sh` compared a lock-free install with a locked baseline, and a
   newer cached dependency turned it red with no product change (`TECH.md:597-616`, `PLAN.md:269-275`).
   *Lesson: both sides of an install-form compare resolve alike* — lock-free vs lock-free (same run,
   same cache), and lock-pinned vs locked.
2. **The ledger read a Markdown heading as a deferral.** The review template's `### Out of scope`
   heading failed the frozen `ledger.py` (`TECH.md:669-687`; fix: `R/P5-ledger-headings.py:8-12`).
   *Lesson: deferral-ledger checks skip heading lines.*
3. **The checker's child lost `HOME`.** F7 read the environment after clearing it (`TECH.md:322-324`).
   *Lesson: a checker that swaps `os.environ` copies it first* (`R/F7-mutant-alternatives.py:541-549`).
4. **An "equivalent" was killable.** `partition-halves-exchanged` died beside the core alone
   (`TECH.md:324-327`). *Lesson: run every recorded equivalent's targets, per member set.*
5. **A collection-time failure counted as a survivor.** `conftest` stopped collection when the
   capabilities failed to load, so a mutant that refused them could not be killed (`TECH.md:299-304`).
   *Lesson: no capability-dependent work at import or collection time.*
6. **The cycle-1 checker caught the new load.** It hashed entry points and read `metadata.get('Name')`
   (`TECH.md:490-495`). *Lesson: rerun earlier class checkers on every remediation.*
7. **CLI drive cost blew the CI job.** 147 drives added about 4 min per era, and the CI job was
   cancelled at 20 min (`TECH.md:519-528`, `REVIEW.md:203-208`). The fix: one kind per family in the
   suite, every kind behind `CLUSTER_MCP_TEST_EVERY_KIND=1` in the checkers (`R/F4-load-refusal.sh:25-30`).
   *Lesson: this cycle's hang and bound drives must be counted against the CI budget up front.*
8. **One mutant per decision left siblings alive** (REVIEW cycle 1 F2, cycle 2 F4: `REVIEW.md:81-86`,
   `:154-171`). *Lesson: mutate every alternative.*
9. **A load refusal escaped on `SystemExit` or `BaseException`** (REVIEW cycle 2 F1-F3, `REVIEW.md:136-152`).
   *Lesson: the probe's outcome map must cover `BaseException`, a hang and a malformed return,
   with `KeyboardInterrupt` kept.*
10. **Never name a script after a Python module.** No in-tree record of the incident was found;
    confirmed here by experiment (Python 3.14, the floor): a gate named `signal.py` run without `-I`
    is re-imported as `signal` by `subprocess` and runs twice, and one named `types.py` dies with
    `ImportError … has the same name as the standard library module`. With `-I` both run correctly.
    Names this cycle might reach for and must avoid: `signal`, `select`, `site`, `trace`, `code`,
    `inspect`, `platform`, `secrets`, `stat`, `timeit`, `cmd`, `profile`, `token`. Of these, `site`,
    `select`, `signal`, `inspect` and `platform` are already imported once `fastmcp` and the server
    are loaded.
11. **Run gate Python with `-I`.** It is used throughout (`V/baseline.sh:41-50`, `V/probe.sh:71-184`,
    `V/registry.py:12-13`). The exception is where `PYTHONPATH` must carry a plant (`V/planted.sh:113`
    runs `served.py` without it). For that case use `-P`, which keeps `PYTHONPATH` but not the script
    directory, or a name that cannot collide.

## 4. Times

| Step | Time | Source |
|---|---|---|
| p1/p2/p3/p4/p5 `phase` | ~4 / 4 / 3 / 6 / 8 min warm | `V/p1.sh:10`, `V/p2.sh:10`, `V/p3.sh:9`, `V/p4.sh:10`, `V/p5.sh:10` |
| baseline / probe / coreonly / planted | ~1 min / 2 min / 20 s / 45 s | headers |
| p5 `mutants` | ~15 min (66 cases at first; 299 at the end) | `V/p5.sh:15`, `TECH.md:644`, `:686` |
| F2 cases / equivalents | ~8 / 5 min | `R/F2-mutant-sweep.py:15-20` |
| F7 cases / equivalents | ~25 / 8 min | `R/F7-mutant-alternatives.py:39-42` |
| F4 / F1 checker | 10 s + ~3 min per era / 5 s + ~1 min per era | `R/F4-load-refusal.sh:11-17`, `R/F1-contribution-refusal.sh:10-14` |
| Suite, per era (local) | 361/341 s → 489/483 s → 357/366 s | `TECH.md:559-561` (commit `82d2f2b` body) |

**Sizing under the 10-min command cap.** This was done by splitting modes, never by sharding cases.
`full` runs as two halves (`V/lib.sh:64`). F7 runs as three modes, and its `cases` step is one
`tests/mutants.py` call per era (`R/F7-mutant-alternatives.py:521-535`). A child runs only its case's
targets (`tests/mutants.py:10-22`), so the cost scales with the targets. Modes longer than 10 min
(`p5 mutants`, F7 `cases`) had to run in the background. The commits record no shard. A recorded
`Observed` line counts each mode.

## Recommendation: `spec/capability-probe/verify/`

Shared:
- `lib.sh`: copied, with `V` and this cycle's `BASE_REF` (its shape commit). Every drive unsets
  the override variable (R8's name, still to be chosen), so an operator's setting cannot leak in.
- `pN.sh`: modes `phase|mutants|full|full-legacy|full-modern|all`, with `ledger|recipe` on the last
  phase. Each has a footprint header.

Independent checks, none of them the suite's own:
- `baseline.sh`, `surface.py`, `compare.py`, `kept.py`, `retired.txt`: reused (R3, every probe
  present, surface whole; nothing lost).
- `withheld.sh`: planted probe capabilities beside each member set. It covers absent, present, no
  probe, raises, `SystemExit`, malformed, and two capabilities at once. It drives stdio, closed stdin
  and HTTP under a stub `PATH`. It runs `served.py`/`expect.py` and asserts that the base names
  exactly the tools served, and checks one stderr line per outcome naming the distribution (R1-R3, R6).
- `stall_gate.py`: stubs that hang or die, timed from launch to the first stdio answer. All probes
  together stay within the bound plus a stated slack, whatever the number of capabilities. It checks
  fail-open, kills by process group and makes a `pgrep` leftover assert (R5, R6).
- `modes_gate.py`: reads the stub invocation log, which must be empty for `delegate` (plus its one
  line), the flag, the variable, `--help`, `--version`, `--generate-token`, a load refusal and a
  failed connect through the `ssh` stand-in. It also checks that `local` probes exactly once (R4,
  R7-R9).
- `docs_gate.py`: R10's sections.
- `ledger.py`: skips headings, and the spec path is a constant.
- `alternatives.py`: the F7-style sweep over the probe's decisions: the outcome map, mode gating,
  override, bound and placement after the executor.

Run every script with `-I`, or with `-P` where a plant needs `PYTHONPATH`. None of these names is a
stdlib or installed module (checked with `sys.stdlib_module_names` and `find_spec`). Avoid `probe.*`,
which collides with the earlier install probe by name.
