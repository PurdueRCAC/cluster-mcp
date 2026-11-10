# GOAL — The suite and the mutation runner leave no sandbox directory behind

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** sandbox-dirs-left-on-kill
- **kind:** fix
- **appetite:** small

## Problem

`bin/sandbox.sh` is the throwaway environment every drive, test and gate runs in (`AGENTS.md`
§ Factory, Throwaway environment). It makes its directory with
`mktemp -d "${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"` (`bin/sandbox.sh:59`) and removes it from a
trap, `trap 'rm -rf "$sandbox"' EXIT HUP INT TERM` (`bin/sandbox.sh:60`). A signal the trap does
not run on ends the wrapper without it: SIGKILL always, and QUIT, USR1 or USR2 today. The directory
then stays, holding the skeleton the script makes (`.config`, `.cache`, `.local/share`) and
sometimes FastMCP's `version_cache.json`.

The repository's own harnesses stop sandboxes that way. Each of these SIGKILLs a sandbox on some
path (sites as surveyed at `0bfacae` in [`research/01-callers-and-contract.md`](research/01-callers-and-contract.md)):

1. **The loopback SSH server** (`tests/ssh_server.py`): `LoopbackSSH.close()` SIGKILLs the group of
   every exec still running (`:629`), and an SSH `signal` request passes KILL, QUIT, USR1 or USR2 to
   the exec's group (`:549`). Its sandboxes take the host's `TMPDIR`; it is the one measured below.
2. **The executor's launcher** (`launch.run_process`), which SIGKILLs the group after TERM's grace
   (`packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py:706-713`): every launch through the
   `executes` fixture (`tests/conftest.py`), `tests/test_launch.py` `_sandboxed`, and
   `tests/test_hygiene.py`'s direct launch.
3. **The MCP stdio client** (`tests/harness.py` `stdio_tools`, `stdio_refusal`), which SIGKILLs the
   group when it outlives its stop.
4. **Long-running servers stopped by group:** `tests/test_startup.py` `run_bounded` (on a timeout),
   `tests/test_transports.py` (after TERM's grace), `tests/test_probe_startup.py` `over_http`.
5. **Every `subprocess.run([SANDBOX, …], timeout=…)` in the suite** (about 25 sites, `need_git` in
   `tests/conftest.py` among them): on a timeout Python SIGKILLs the wrapper alone.
6. **The mutation runner,** `tests/mutants.py` `run_child` (`:5692-5699`): it kills its sandbox
   outright too, on its 300 s timeout, where `subprocess.run` SIGKILLs the `bin/sandbox.sh` it
   started. The cycle `mutant-child-outlives-timeout` (not yet on `develop`) changes that path to
   SIGKILL the whole run, wrapper included, and builds no sandbox cleanup of its own. Each case's
   child pytest runs suite tests that start sandboxes of their own, so a child killed at its limit
   also leaves theirs.

`tests/test_transports.py`, `tests/test_probe_startup.py` and one `tests/test_audit.py` site already
point the sandbox's `TMPDIR` at the test's own `tmp_path`; the rest take the host's. The seed's
fifth site, `spec/capability-probe/verify/drives.py:325`, SIGKILLs a bare `uv run` inside a gate's
outer sandbox, not a sandbox of its own, so it leaves nothing.

Observed on a developer Mac, 2026-11-01: the host's `TMPDIR` held 18,061 `cluster-mcp-sandbox.*`
directories, the oldest from 2026-10-17. One full-suite run, alone on the host, left 59 in the
handshake era and 58 in the modern era; a mutation sweep leaves many more (a build reported 346 in
two hours). Every leftover is clutter in a shared temporary directory, and a run cannot tell its own
leftovers from another run's.

**Pre-existing:** yes. The trap came in with the sandbox wrapper itself, before the factory, and
every harness named above predates `capability-probe`, where it was found.

## Outcome / vision

The repository's own runs, meaning a pytest run of the suite, the profile's `verify` and the mutation
runner, leave no `cluster-mcp-sandbox.*` directory behind, however a sandbox they started was
stopped. Each run cleans up only what its own sandboxes made: never another run's, and never the
leftovers already on a host. `bin/sandbox.sh` itself does not change, so a caller outside those runs
that kills a sandbox outright still leaves its directory (a known limitation).

## Acceptance criteria (the contract)

- **R1** — WHEN a pytest run of any part of the suite runs to its end (each of the profile
  `verify`'s suite commands included), no `cluster-mcp-sandbox.*` directory made by a sandbox that
  the run started SHALL still exist, in the host's `TMPDIR` or anywhere else (the run's own pytest
  temporary directories included), however that sandbox ended: its command's exit, a signal the
  trap runs on, or a kill it does not run on through any harness in § Problem's items 1–5.
- **R2** — WHEN `tests/mutants.py` runs to its end over any cases, a case whose child run passes its
  time limit included, no `cluster-mcp-sandbox.*` directory made by a child run's sandbox, or by any
  sandbox that child's tests started, SHALL still exist, in the host's `TMPDIR` or anywhere else.
- **R3** — The cleanup that R1 and R2 add SHALL remove only directories made by sandboxes its own run
  started. It SHALL NOT remove another run's sandbox directory (a concurrent pytest run, mutation
  sweep or other caller on the same host, whatever `TMPDIR` that run uses), a
  `cluster-mcp-sandbox.*` directory that existed before the run began (the leftovers already on a
  host), or anything that is not a sandbox directory.
- **R4** — WHILE a sandbox's command is still running, the cleanup SHALL NOT remove or alter that
  sandbox's directory.
- **R5** — `bin/sandbox.sh` SHALL be byte-identical to `develop` at `0bfacae`.
- **R6** — Every test in the suite SHALL pass, fail or skip as on `develop` at `0bfacae`, in both
  protocol eras, and every mutation case and `--self-check` control SHALL keep its verdict.

## Non-goals (no-gos)

- **Callers outside the repository's own runs (known limitation).** A developer's shell, a cycle's
  `spec/*/verify/` gate script (such as `spec/agents-d-instructions/verify/serve_gate.py`, which
  SIGKILLs a sandboxed server), or any other ad hoc caller that kills a sandbox outright still leaves
  its directory, because `bin/sandbox.sh` is unchanged (R5). Earlier cycles' gate scripts are
  records and are not edited.
- **A run that is itself killed (known limitation).** If the pytest run or the mutation runner is
  killed before its end (SIGKILL, a cancelled CI job), its own cleanup does not run, and what its
  sandboxes made stays in the location the run gave them.
- **The leftovers already on a host.** The 18,061 directories, and any made before this lands, are
  the developer's to remove; nothing here deletes them (R3).
- **How a harness stops its process.** No harness changes its signals, its order or its graces;
  `tests/mutants.py`'s stop belongs to `mutant-child-outlives-timeout`, and its sweep arrangement to
  `mutants-workflow-timeout`. The cleanup has to hold under the stops those cycles make.
- **A command that escapes its sandbox.** A process that leaves the sandbox's process group and
  outlives the command (the `local` executor's own groups) is
  [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md).
- **Any timing figure set here.** The per-case 300 s limit and the suite's timeouts and graces are
  untouched; any wait or added cost the cleanup brings is the maintainer's call at the plan gate,
  with before-and-after.
- **Kills that take the host down** (a reboot, a full `TMPDIR`): out of scope.

## Clarifications

- **Q1:** By when must a SIGKILLed sandbox's directory be gone (R1, and through it R2)? Options
  weighed: before the killing caller's own wait on the wrapper returns; within a fixed time after
  the wrapper and its command have both ended; by the end of the drive, suite or sweep that started
  it; at the latest when the next `bin/sandbox.sh` starts. — **A:** Within a fixed time after the
  wrapper and the command it started have both ended, with the fix in or around `bin/sandbox.sh`
  so every caller gets it. The figure is a timing bound and the maintainer's: the plan proposes it
  with its before (never removed) and after (the figure and its measured cost), and the maintainer
  sets it at the PLAN/TECH gate (2026-11-09, foreman ruling at the GOAL gate; the figure is the
  maintainer's at the PLAN/TECH gate). *Superseded by Q4.*
- **Q:** Who reviews a finding in `bin/sandbox.sh`? — **A:** It is a high-blast-radius path
  (`AGENTS.md` § Invariants, High-blast-radius paths), so a CONFIRMED review finding there needs
  the maintainer's sign-off before the cycle lands, and the plan runs research (2026-11-09, foreman
  ruling at the GOAL gate). Under Q4, R5 keeps the file unchanged.
- **Q:** Who owns the seed `issues/sandbox-dirs-left-on-kill.md` while both cycles are open? —
  **A:** This cycle. Its sentence on the mutation runner's timeout path is carried verbatim from
  `mutant-child-outlives-timeout`'s shape commit, whose build does not rewrite it; the "last three"
  referent after that sentence is fixed by whichever cycle lands second, at its landing
  (2026-11-09, foreman ruling at the GOAL gate).
- **Q4:** The first plan (`8520d9c`) answered Q1 with a keeper process inside `bin/sandbox.sh`. Keep
  that, or re-shape? — **A:** Re-shape. `bin/sandbox.sh` stays as it is. Each harness that SIGKILLs
  a sandbox points the sandbox's `TMPDIR` into a directory it owns (the test's `tmp_path`, the
  mutation runner's own scratch, and so on), and a suite-session sweep removes what the run's
  sandboxes left. The contract narrows to the repository's own runs (the suite, `verify`, the
  mutation runner); an ad hoc caller that SIGKILLs a sandbox still leaks, recorded as a known
  limitation. A timing figure the sweep adds comes back to the maintainer (2026-11-09, maintainer
  at the PLAN/TECH gate: (b) re-shape).
- **Q:** What does R4's "still running" mean, and so which sandbox does R1's "however that sandbox
  ended" cover, when nothing but a process's working directory and environment ties it to a sandbox
  (R5)? — **A:** What the host shows the account. A sandbox directory is in use while some process
  has its working directory in it or the directory's path in its environment, as `/proc` (Linux)
  or `lsof` and `ps -E` (macOS) show them; in use, it is kept. R1 covers a sandbox none of whose
  processes is seen using its directory at the run's end. The one case not seen: a sandbox whose
  wrapper was SIGKILLed alone and whose command still runs at the run's end, outside the sandbox's
  directory, as a process whose environment the host does not show (on macOS, a system binary, or
  an `env -i` command); its directory is removed while it runs (2026-11-09, foreman ruling at the
  PLAN/TECH gate; PLAN § 3 row D2).
- **Q:** Does R3's "anything that is not a sandbox directory" cover the directory a run makes to be
  its own processes' `TMPDIR`? — **A:** No. A directory the run made for its own processes'
  `TMPDIR` (the suite's run directory, the mutation runner's case scratch) is given only to this
  run's processes, and is removed whole with whatever they left in it, sandbox directories or not,
  unless a sandbox directory in it is still in use. Everywhere else (the run's pytest temporary
  directories included) the cleanup removes only sandbox directories (2026-11-09, foreman ruling at
  the PLAN/TECH gate; PLAN § 3 row D3).

## Related materials

- Seed: [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md)
- Roadmap: `ROADMAP.md` Part I, "A sandbox killed with SIGKILL leaves its directory behind"
- **Superseded design.** `PLAN.md`, `TECH.md`, `research/` and `verify/` as committed in `8520d9c`
  are the record of the rejected design (a keeper inside `bin/sandbox.sh`, Q4). The re-plan
  replaces them; `research/01-callers-and-contract.md`'s survey of callers still holds at `0bfacae`.
- `bin/sandbox.sh` (unchanged, R5); `AGENTS.md` § Factory, Throwaway environment
- Harnesses: `tests/ssh_server.py`, `executor/launch.py` with `tests/conftest.py` (`executes`),
  `tests/test_launch.py`, `tests/test_hygiene.py`, `tests/harness.py`, `tests/test_startup.py`,
  `tests/test_transports.py`, `tests/test_probe_startup.py`, `tests/mutants.py` (`run_child`)
- Where it was found: [`spec/capability-probe/`](../capability-probe/) (TECH P3)
- Neighbouring cycles: `mutant-child-outlives-timeout` (whose GOAL leaves this directory here; its
  stop and its removal of the runner's own scratch touch `run_child` too) and
  `mutants-workflow-timeout` (`tests/mutants.py`), both on their own branches; `skip-check-fence-gaps`
  edits `tests/test_hygiene.py`
- Related seed: [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md)
- **Constraints for the plan** (not requirements of their own):
  - `tests/test_transports.py` globs its `tmp_path` for sandbox directories right after the wrapper
    exits and asserts the TERM path removed it; that check stays as it is (R6).
  - Moving a sandbox's `TMPDIR` deeper lengthens every path under it, and a Unix socket path on
    macOS is capped at 104 bytes; any socket a sandboxed command makes under `TMPDIR` needs checking.
  - A child run the mutation runner stops never reaches its own session's end, so its sweep never
    runs there; R2 holds only if the runner's side removes what the child's sandboxes made.
