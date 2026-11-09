# GOAL — A sandbox killed with SIGKILL leaves no directory behind

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** sandbox-dirs-left-on-kill
- **kind:** fix
- **appetite:** small

## Problem

`bin/sandbox.sh` is the throwaway environment every drive, test and gate runs in (`AGENTS.md`
§ Factory, Throwaway environment). Its contract says it "creates a fresh state directory and removes
it on every exit path". It makes that directory with
`mktemp -d "${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"` (`bin/sandbox.sh:59`) and removes it from a
trap, `trap 'rm -rf "$sandbox"' EXIT HUP INT TERM` (`bin/sandbox.sh:60`). SIGKILL is an exit path
no trap runs on: when the wrapper is killed outright, alone or with its process group, the
directory stays, holding the skeleton the script makes (`.config`, `.cache`, `.local/share`) and
sometimes FastMCP's `version_cache.json`.

Several harnesses stop a sandbox that way:

- `LoopbackSSH.close()` (`tests/ssh_server.py:629`, `os.killpg(proc.pid, signal.SIGKILL)` for every
  exec still running), whose sandboxes take the host's `TMPDIR`; the one measured below.
- `tests/test_startup.py` `run_bounded` (`:608`, on a timeout); `tests/test_transports.py` (`:90`,
  after SIGTERM's grace); `tests/test_probe_startup.py` `over_http` (`:834`);
  `spec/capability-probe/verify/drives.py` (`:325`). The last three point the sandbox's `TMPDIR` at
  the test's own directory, so what they leave goes with it.
- The mutation runner, `tests/mutants.py` `run_child` (`:5692-5699`): on its 300 s timeout,
  `subprocess.run` SIGKILLs the `bin/sandbox.sh` it started. The cycle
  `mutant-child-outlives-timeout` (not yet on `develop`) changes that path to
  SIGKILL the whole run, wrapper included, and builds no sandbox cleanup of its own; the home is
  this cycle's.

Observed on a developer Mac, 2026-11-01: the host's `TMPDIR` held 18,061 `cluster-mcp-sandbox.*`
directories, the oldest from 2026-10-17. One full-suite run, alone on the host, left 59 in the
handshake era and 58 in the modern era; a mutation sweep leaves many more (a build reported 346 in
two hours). Every leftover is clutter in a shared temporary directory, and a drive or gate cannot
tell its own leftovers from another run's.

**Pre-existing:** yes. The trap came in with the sandbox wrapper itself, before the factory, and
every harness named above predates `capability-probe`, where it was found.

## Outcome / vision

However a sandbox is stopped, the directory it made does not outlive it: a drive, test, gate or
mutation sweep leaves no `cluster-mcp-sandbox.*` directory in the `TMPDIR` it ran under. Every
caller of `bin/sandbox.sh` gets that, not only the harnesses named above. Nothing else about the
sandbox changes, and the directories already on a host are the developer's to remove.

## Acceptance criteria (the contract)

- **R1** — WHEN `bin/sandbox.sh` is killed with SIGKILL, alone or with its process group, by any
  caller, the directory it made SHALL no longer exist once the wrapper and the command it started
  have both ended, [NEEDS CLARIFICATION: by when? (a) before the killing caller's own wait on the
  wrapper returns; (b) within a fixed time after both have ended, the figure set by the maintainer
  at the plan gate (before: never; after: the plan proposes one with its measured cost); (c) by the
  end of the drive, suite or sweep that started it; (d) at the latest when the next
  `bin/sandbox.sh` starts on that host].
- **R2** — WHEN the profile's `verify` command, a single pytest run of any part of the suite, or
  `tests/mutants.py` over any cases (a case whose child run passes its time limit included) runs to
  its end, the `TMPDIR` it ran under SHALL hold no `cluster-mcp-sandbox.*` directory that the run
  created, within the same bound as R1.
- **R3** — WHEN `bin/sandbox.sh` ends on any path that removes its directory on `develop` at
  `0bfacae` (its command exits, or the wrapper gets HUP, INT or TERM), it SHALL still remove the
  directory before the wrapper exits.
- **R4** — WHILE one sandbox's command is running, no other `bin/sandbox.sh`, on any exit path,
  SHALL remove or alter that sandbox's directory, whether the two share a `TMPDIR` or not.
- **R5** — `bin/sandbox.sh` SHALL NOT remove any directory it did not make: neither a
  `cluster-mcp-sandbox.*` directory made before this change (the leftovers already in a host's
  `TMPDIR`) nor anything else in `TMPDIR`.
- **R6** — Once a sandbox's directory has been removed, on any exit path, no process that
  `bin/sandbox.sh` started for its own upkeep (as opposed to the command it runs) SHALL still be
  running.
- **R7** — Every other observable of `bin/sandbox.sh` SHALL be as on `develop` at `0bfacae`: the
  command's exit status passed through, nothing of the script's own on stdout, `HOME`, the XDG
  directories and the working directory inside the sandbox, the environment it blanks and pins
  (`AGENTS.md` § Factory, Throwaway environment), and no signal forwarded to its command.

## Non-goals (no-gos)

- **The leftovers already on a host.** The 18,061 directories, and any made before this lands, are
  the developer's to remove; nothing here deletes them (R5).
- **How a harness stops its process.** No harness changes its signals, its order or its graces to
  make this hold; in particular `tests/mutants.py`'s stop belongs to `mutant-child-outlives-timeout`
  (and its sweep arrangement to `mutants-workflow-timeout`). This cycle's fix has to hold under the
  stops those cycles make, the runner's SIGSTOP-then-SIGKILL of every group of a run included.
- **Signal forwarding.** `bin/sandbox.sh` keeps not forwarding SIGTERM to its command (R7); the
  harnesses that rely on that, such as `tests/test_transports.py`, are unchanged.
- **A command that escapes its sandbox.** A process the command starts that leaves the sandbox's
  process group and outlives the command (the `local` executor's own groups) is
  [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md); R1
  waits for the command the wrapper started, not for such a process.
- **Any timing figure set here.** The per-case 300 s limit, the suite's timeouts and graces, and
  any bound R1 needs are untouched or set by the maintainer at the plan gate, with before-and-after.
- **Kills that take the host down** (a reboot, a full `TMPDIR`): out of scope.

## Clarifications

None resolved yet; R1's bound is open (it also sets R2's).

## Related materials

- Seed: [`issues/sandbox-dirs-left-on-kill.md`](../../issues/sandbox-dirs-left-on-kill.md)
- Roadmap: `ROADMAP.md` Part I, "A sandbox killed with SIGKILL leaves its directory behind"
- `bin/sandbox.sh` (a high-blast-radius path, `AGENTS.md` § Invariants: the plan runs research and
  a CONFIRMED finding there needs the human gate); `AGENTS.md` § Factory, Throwaway environment
- Harnesses: `tests/ssh_server.py` (`LoopbackSSH.close`), `tests/test_startup.py` (`run_bounded`),
  `tests/test_transports.py`, `tests/test_probe_startup.py` (`over_http`),
  `spec/capability-probe/verify/drives.py`, `tests/mutants.py` (`run_child`)
- Where it was found: [`spec/capability-probe/`](../capability-probe/) (TECH P3)
- Neighbouring cycles: `mutant-child-outlives-timeout` (whose GOAL leaves this home here) and
  `mutants-workflow-timeout`, both on their own branches
- Related seed: [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md)
