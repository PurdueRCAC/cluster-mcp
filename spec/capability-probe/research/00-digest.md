# Research digest — capability-probe

Four briefs, run in parallel at plan time (2026-11-01), all read-only:
[`01-probe-contract.md`](01-probe-contract.md), [`02-startup-integration.md`](02-startup-integration.md),
[`03-testing-and-budget.md`](03-testing-and-budget.md), [`04-gate-scripts.md`](04-gate-scripts.md).
Below is each decision they settle, and how the planner settled the places where they disagree.
The prototype that dry-ran the gates (a detached worktree off the shape commit, removed after the
PLAN/TECH sign-off) confirmed the decisions marked *(prototype)*.

## Decisions

1. **A probe is data, not code** (01 §1).
   - A capability declares `commands: tuple[str, ...] = ()` on its `Capability`, after `resources`.
   - The core looks every declared name up at once, through one fixed script, on the shared executor.
   - No capability code runs at probe time, so a probe cannot raise, exit, hang in Python or return a
     malformed value.
   - A malformed declaration is refused at load with the existing §7 refusal: "whatever a capability
     declares fails at the load or not at all" stays true.
   - The types are exact (`type(...) is tuple`, `is str`). The review showed a subclass's `__iter__` or
     `__hash__` would run at probe time.
   - A callable or a script per capability would move capability failures to probe time, where
     they could only fail open, and would cost one round trip each.

2. **The lookup is `type -P`, in a registered fixed script** (01 §2).
   - `type -P` finds exactly what the tools' `exec` runs. `command -v` would count a profile
     function or a builtin as present.
   - The script undoes a `type` function first. Names reach it only as positional parameters. It
     prints one `0`/`1` line per name, then `end N`, and echoes no name.
   - Names are validated at load against `[A-Za-z0-9_][A-Za-z0-9_.+-]{0,254}`.
   - *(prototype)* `lookups.py` showed the following through the real login bash: a stub file counts
     as present; a missing name, an exported function and a non-executable file count as absent; an
     exported `type` function forges nothing.

3. **One deadline, on a daemon thread, after the site read** (02 §1–2, 01 §3; amended by the review).
   - `PROBE_TIMEOUT = 10.0` is one figure, read at call time and not a setting.
   - The executor gets the same timeout, so the remote command is stopped at the bound.
   - The outer deadline still holds where the executor's own timeout does not: an SSH reconnect
     (up to 45 s) and opening a session (up to 30 s).
   - 02 proposed starting the probe before the site read and joining it after, which keeps the worst
     case after the connect at 10 s. Both executors take a second concurrent `run`.
   - **Amended at the adversarial review.** Overlap runs a probe before a budget refusal, and that
     refusal needs the site's text. R9 puts every existing refusal before any probe. So the lookup
     follows the site read and the budget check. The probe still adds at most 10 s (R5).
   - *(prototype)* `startup_order.py`: the events run executor, site read, probe, server. A hung probe
     is held to its bound.

4. **Every ending is decided on one path** (01 §3, 02 §2, 03 §3).
   - A well-formed answer with every name `1` serves the capability; a `0` for any name withholds it.
   - Every other ending serves it with a reason (Q2): the timeout, not-started and connection-lost
     codes, any other exit, an answer that does not parse, a result that is not a `CommandResult`,
     and anything raised (the worker catches `BaseException`).
   - The deadline passing with no answer is decided the same way.
   - The verdicts are decided once and memoized. *(prototype)* `lookups.py` caught a first draft
     whose second call to `verdicts()` waited out the bound again and changed its answer.
   - The parser splits on `\n` alone and needs the final newline: a CRLF answer is malformed.

5. **The served set reaches `create_mcp_server(capabilities=…)`** (02 §3).
   - Nothing serves `TOOL_REGISTRY` or `RESOURCE_REGISTRY` directly, so a withheld capability's
     tools cannot leak.
   - `installed()` still loads everything, so refusals at load are unchanged (R9).
   - `capabilities=None` still means "every installed one", so `test_served_surface_matches_baseline`
     needs no edit (03 §1).

6. **The budget holds every installed capability's text** (02 §3).
   - Without this, a budget between the two minimums would start or refuse depending on how the
     cluster answered.
   - `run()` checks the budget against the full installed base, then builds the server from the
     served set.

7. **`delegate` and the override skip by mode, each with one line** (02 §4–5).
   - `delegate` is decided first, then the override, and only one line is logged.
   - The override is `--skip-probes` and `CLUSTER_MCP_SKIP_PROBES`, read through `env_setting`.
   - `env_setting` raises `KeyError` for a variable with no legacy twin. `LEGACY_ENV` gains the
     entry `CLUSTER_MCP_SKIP_PROBES: None`, and the resolver skips the legacy branch for it. No
     `RCAC_` twin is invented.

8. **The suite skips probes by default; dedicated tests opt in** (03 §1–2, against 02 §5).
   - **The disagreement.** 02 proposes that `bin/sandbox.sh` unset the variable, so drives that
     need every tool would pass the flag. 03 proposes a session fixture that sets the variable, with
     the sandbox left alone.
   - **Settled for 03:**
     - About 60 in-process starts would otherwise trip the unit guard, which forbids `Popen`. A
       PATH stub cannot help them.
     - `bin/sandbox.sh` is on the high-blast-radius list, and nothing requires editing it.
     - A mutant that ignores the override turns every existing `local` drive red.
     - The calling shell's value cannot mask a probe test: each probe test, and every gate, removes
       the variable explicitly (`env -u` in `lib.sh`, `os.environ.pop` in the gates).
   - The fixture sits beside `path_shim` in `tests/conftest.py`, and a hygiene test pins it.

9. **What the members declare** (01 §5).
   - **Slurm:** its six client commands (`sbatch squeue scancel sacct sinfo scontrol`).
   - **RCAC:** `findscratch` and `myquota`, the two its storage resource needs. They also mark the
     site.
   - Declaring every RCAC command would let one missing site script hide all ten tools and the
     resource.

10. **The override's value: any non-empty value turns it on** (02 §5 proposed a strict boolean).
    - **Settled against 02.** R8 reads "WHERE the override … is set". § Configuration says an empty
      value counts as unset and the resolver strips nothing. Read together, a set variable is a
      non-empty one, `0` included, as `NO_COLOR` treats its value.
    - A strict parse would make `CLUSTER_MCP_SKIP_PROBES=0` probe while set, which reads against
      R8's wording.
    - The trade-off is that `=0` skips probes. § Configuration and `--help` say so.

## Testing and budget (03, 04)

- **In process, fast, every decision.**
  - A harness `ProbeExecutor` answers present, absent, each sentinel code, raises (`Exception`,
    `SystemExit` with 0, an int and a string, a `BaseException`), returns a malformed value, or hangs
    until an `Event`. The bound is patched small.
  - Rows run beside each member set (`MEMBER_SETS`), so the alternatives sweep can require a row per
    set.
- **`ssh` mode** is driven in process against `tests/ssh_server.py`'s `LoopbackSSH`. A CLI drive
  cannot reach it.
- **CLI drives.** About 10 per era, each unsetting the override. The sandbox HOME's `.bash_profile`
  puts stubs first on PATH and logs each login. In `local` mode the site read is in process, so the
  log counts the probe launches exactly.
  - The suite never drives the real 10 s bound. A profile that exits at once gives a fast "could not
    run" ending instead. Only the gate (`drives.py`) drives a real hang, twice.
- **Mutants.** `alternatives.py` follows the capability-extras F7 shape. Each phase runs its own
  cases, split by era to fit the 10-minute command cap.
  - `.github/workflows/mutants.yml` already sits at its 30-minute timeout, running about 660 cases
    serially. That is pre-existing, and this cycle adds about 200 cases: recorded in
    [`issues/mutants-workflow-timeout.md`](../../../issues/mutants-workflow-timeout.md).
- **Gate scripts.**
  - No gate is named after a Python module. `probe.*` is avoided as well, because of the earlier
    cycle's install probe.
  - Gate Python runs with `-I`. `lib.sh` holds the interpreter in `$PY`.
  - The ledger skips Markdown headings and reads PLAN, TECH and REVIEW. It does not read the GOAL,
    whose words on deferral describe where the cycle came from.
  - Drives reap their servers by process group, and `pgrep` asserts that nothing is left over.

## Not settled here (for the downstream cycles' seeds)

- **LMOD** (`module` is a shell function, and its tools run `$LMOD_CMD`) needs a second kind of data
  declaration. That is a core edit in its own cycle. P3 records it on
  [`issues/lmod-tool-group.md`](../../../issues/lmod-tool-group.md).
- **xdu** must declare no probe: its tools offer the install where `xdu` is missing. P3 records this
  on [`issues/xdu-storage.md`](../../../issues/xdu-storage.md).
