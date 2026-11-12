# ROADMAP

The ordered index of work that is **not yet in flight**. One entry per `issues/{slug}.md` seed; the
seed holds the evidence and the draft criteria, this file holds the order and the reasoning about
order. Nothing here is a contract — the factory's feature step promotes a seed into a `spec/{slug}/GOAL.md`, and
that promotion is where appetite, non-goals and the R-IDs get negotiated with a human.

The project is on a three-release arc. **Part 0** is released: the 0.1.x releases made the server
safe and useful as it stood, and **0.2.0** shipped `develop` as it stood on 2026-11-12, with the
rename, the uv workspace, the capability extras and probe, and the hardening that had landed.
**Part I** holds the hardening, robustness and safety items still open, and the rest of the rename;
30 entries, each of which ships in the first release after it lands. **Part II** ships as
**0.3.0**: the capabilities behind package extras, each tool family defined so another
implementation is a contribution; 14 entries, eleven cycles and three absorbed seeds. It starts
once three Part I entries have landed (a fourth, the mutation run's hung child, is cleared: landed
on `develop` 2026-11-12), and 0.3.0 ships when Part II has landed, without waiting for the rest of
Part I. **Part III** ships as **0.4.0**: records of every call, audit logging, and
lexing and steering on the shell; two entries. Four more entries come after 0.3.0 and are not yet
ordered. Within a Part, scope is never cut for pace.

The order was revised on 2026-11-12. Every cycle starts from and lands on `develop`; a release
fast-forwards `main` to a released `develop` commit, so nothing reaches users between releases.

A seed that another cycle **absorbs** keeps a short entry under that cycle, so every file in
`issues/` stays indexed until the absorbing cycle retires it.

Read `AGENTS.md` § *Direction* before starting anything in Part II; it states the destination that
these entries are steps toward. `AGENTS.md` § Factory describes the lifecycle that consumes these
seeds; its method lives in the operator's KB.

---

# Part 0 — Released

Done; it holds no entries. **0.1.1** (2026-10-18) carried the dependency-stack upgrade to FastMCP 4
and the MCP SDK 2, the docs strip, the test suite and the both-era gates. **0.1.2** (2026-10-22)
carried the CI workflow, the sdist hygiene fix and a lock past two dependency advisories. **0.1.3**
(2026-10-27) carried the safe executor — byte-exact writes, literal paths, `sbatch` arguments, one
shell's semantics — with clear connection errors, a call that fails rather than hangs when the
connection drops, job scripts that never overwrite each other, and the site's rules from
`/etc/agents.d` in the instructions. **0.1.4** (2026-10-29) made a read of `rcac://storage` return
the user's storage paths. **0.1.5** (2026-10-30) carried a lock past a further dependency advisory.

**0.2.0** (2026-11-12) shipped the eight cycles that had landed on `develop` since 0.1.5. The rename
to `cluster-mcp` and the uv-workspace restructure landed on 2026-10-30
([`spec/rename-to-cluster-mcp/`](spec/rename-to-cluster-mcp/)), keeping the old names through a
deprecation window. The capability extras landed on 2026-11-01
([`spec/capability-extras/`](spec/capability-extras/)): a bare `cluster-mcp` is the core alone,
`[slurm]` and `[rcac]` each install a member that registers through one entry-point group, and the
served instructions are composed from what loaded. The capability probe landed the same day
([`spec/capability-probe/`](spec/capability-probe/)): in `ssh` and `local` modes an installed
capability is served only where the cluster has the commands it declares. The timeout stop landed on
2026-11-04 ([`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/)): a timed-out command
and everything in its process group have exited within 2 × `GRACE` of the deadline in every mode.
The silent-link check landed on 2026-11-06 ([`spec/ssh-half-open-link/`](spec/ssh-half-open-link/)):
over `ssh`, a link that goes silent without a reset is noticed within the reconnect bound. The CI
time budget landed the same day ([`spec/suite-ci-time-budget/`](spec/suite-ci-time-budget/)): each
era's suite runs as four CI jobs, each within 10 minutes, a budget `AGENTS.md` § Factory holds.
The skip check's fence closed on 2026-11-09
([`spec/skip-check-fence-gaps/`](spec/skip-check-fence-gaps/)): it admits a skip only inside the
single top-level `need_shell` and `need_git` in `tests/conftest.py`, and reports a skipper reached
through an attribute or an outcome raised directly.
The real-time rows were fixed on 2026-11-10
([`spec/stalled-reconnect-test-timing/`](spec/stalled-reconnect-test-timing/)): the stalled reconnect,
the worker that cannot start, the probe's raised endings and the bounded start now fail on
behaviour, not on a busy host, with their bounds unchanged.
The legacy `RCAC_*` variables, `rcac://` URIs and the `rcac-mcp` command keep working through the
deprecation window. A bare install still serves the shell and the file tools; Part II narrows it.

Each cycle's account is its `spec/{slug}/`.

---

# Part I — hardening, and the rename finished

Thirty entries: every open hardening, robustness and safety item, and the rest of the rename in
code and docs. No capability is reshaped here; that is Part II. Each entry ships in the first
release after it lands.

They come in six groups, in this order:

- **Before Part II** (three entries), because Part II rests on them: the surface fixture, which must
  land before the first cycle that changes the served surface, and the two gaps in the capability
  load every family registers through. Part II starts once all three have landed; the fourth it
  waited on, the mutation run's hung child, is cleared (landed on `develop` 2026-11-12). The
  mutation run's own job (the first gate below) lands before core extraction's review.
- **Gates** (thirteen), because every later gate rests on them: the mutation run, the pins its
  stop path still lacks and the case cleanup a second signal can cut short, the two gaps the skip check still leaves and the pins it still lacks, the
  waits the timing rows still miss, an annotation check, the test harnesses' leftovers and those of a sandbox killed outside them, the marker
  wording, and the image's init.
- **The executor** (seven): what `ssh-reconnect-loop`, `capability-probe` and `timeout-process-cleanup`
  left on the SSH connection and the `local` launch, and the loopback SSH link that breaks under load.
- **Safety** (three): the site files' size, the startup update check, and the floors a git install
  resolves against.
- **Redesigns and trade-offs** (two): limits the timeout stop and the liveness check recorded. Fix what can be fixed; what can't becomes `accepted-behaviour` only on the
  maintainer's ruling.
- **The rename finished** (two): the identity strings a client or a token sees, and the docs.

## The surface pin cannot follow a deliberate surface change

`tests/fixtures/served_surface.json` is the surface `3d010ec` served, taken on FastMCP 2, and
`tests/test_surface.py` rejects a fixture re-taken on FastMCP 4 because it carries the new stack's
schema metadata. After a deliberate change to a tool, an argument or the instructions there is no
FastMCP 2 build of the new surface to snapshot, so the only way to update the pin is to hand-edit
it, unchecked. A maintained snapshot command on the current stack, with a one-time re-baseline that
retires the tolerated-difference list, settles it. Found by `stack-upgrade` P3, 2026-10-17.

*Horizon: before Part II, the last gate before the first cycle that changes the served surface · Depends on: — · Refs: `AGENTS.md` § Invariants §9 says the question is open; `safe-execution` changed the surface first and hand-edited its deltas into the fixture (`AGENTS.md` § Testing); every Part II family changes the surface*
**Seed:** [`issues/surface-fixture-after-a-surface-change.md`](issues/surface-fixture-after-a-surface-change.md) · *status: unshaped*

## A capability's registered tool objects can run its code when they are read

The load takes each tool a capability registers by `isinstance(entry, FunctionTool)`, so a subclass, or
a field the capability sets after construction to a value of a type of its own, runs the capability's
code whenever the core or FastMCP reads it: at the load's scratch registration, again when the server
is built, and on every listing. The capability record itself is exact since `capability-probe`; its tools are the one part
still taken by `isinstance`. The outcome: every tool exactly a `FunctionTool` with exact field values,
decided at load, the handler excepted. Pre-existing; no code changes until its cycle.

*Horizon: before Part II, safety · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (REVIEW, cycle 2 rulings); `AGENTS.md` § Invariants §7; `core/capabilities.py`*
**Seed:** [`issues/capability-tool-objects-inert.md`](issues/capability-tool-objects-inert.md) · *status: unshaped*

## A retried capability load after a failure registers nothing and blames the wrong distribution

A failed load cuts the tool registry back but leaves the imported tools modules cached, so a second
load in the same process registers nothing for a capability that had loaded cleanly, and the error
names it instead of the broken one. The command line never retries, so only a library caller sees it.

*Horizon: before Part II, safety · Depends on: capability-extras (cleared: landed on `develop` 2026-11-01) · Refs: [`spec/capability-extras/`](spec/capability-extras/) (REVIEW, cycle 1)*
**Seed:** [`issues/capability-reload-after-failure.md`](issues/capability-reload-after-failure.md) · *status: unshaped*

## The on-demand mutation run no longer fits its 30-minute job

`.github/workflows/mutants.yml` runs every mutation case serially in one 30-minute job. At about 660
cases and 2.5–5 s each, it reaches the timeout and is cancelled before it reports, and § Testing's
"all cases about 3 minutes" is stale. `capability-probe` adds 271 cases (931 in all). Pre-existing;
it gates nothing yet, and every later mutation gate rests on it.

- 2026-11-02: `timeout-process-cleanup` adds 101 more (1,032 in all), about 11 minutes per era.

*Horizon: Part I, gates first; before core extraction's review · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (research 03 §5, PLAN §6)*
**Seed:** [`issues/mutants-workflow-timeout.md`](issues/mutants-workflow-timeout.md) · *status: unshaped*

## The mutation runner's stop path is pinned for its main layer, not its deeper ones

`mutant-child-outlives-timeout` gave `tests/mutants.py` a stop path that finds every process of a
hung or signalled run, stops it and waits for it to be gone. Every R-ID's check is pinned, but its
review left 13 survivors, each a deeper layer of a pinned class: a zombie in the walk, a look that
fails inside the wait, a narrowed or widened catch, a signal type on the wrong base, an extra
statement in `main`. The code is correct on each; a change of that kind would pass every row.
Found by that cycle's review, cycle 3, 2026-11-10.

*Horizon: Part I, gates · Depends on: — · Refs: [`spec/mutant-child-outlives-timeout/`](spec/mutant-child-outlives-timeout/) (REVIEW cycle 3, mutant sweep); `tests/mutants.py` (`stop_run`, `run_members`, `_wait_gone`); `tests/test_mutations.py`*
**Seed:** [`issues/mutant-runner-stop-pins.md`](issues/mutant-runner-stop-pins.md) · *status: unshaped*

## A second signal to the mutation runner can cut a case's cleanup short

The runner cleans up each case on its way out of `run_case` (`case_scratch`: `TMPDIR` put back, the
case's scratch removed, or kept and named while a sandbox in it is in use). A SIGTERM, SIGHUP or
Ctrl-C reaches that cleanup after the stop, which holds those signals; the cleanup holds none, so a
second one while it runs stops it part-way and leaves the scratch, with the run's sandbox
directories, in the runner's `TMPDIR`. Pre-existing: the old `TemporaryDirectory` cleanup was cut
short the same way. Found by `sandbox-dirs-left-on-kill`'s P2 build, 2026-11-12.

*Horizon: Part I, gates · Depends on: sandbox-dirs-left-on-kill · Refs: [`spec/sandbox-dirs-left-on-kill/`](spec/sandbox-dirs-left-on-kill/) (TECH, P2); `tests/mutants.py` (`case_scratch`, `stop_run`)*
**Seed:** [`issues/mutant-case-cleanup-interrupted.md`](issues/mutant-case-cleanup-interrupted.md) · *status: unshaped*

## A sandbox killed outright outside the repository's own runs leaves its directory

`bin/sandbox.sh` removes its directory from a trap a SIGKILL skips. `sandbox-dirs-left-on-kill`
cleans up after the suite and the mutation runner and leaves the wrapper as it is, so a person or
another tool that SIGKILLs a sandbox (a shell's `kill -9`, a gate script, a step cancelled outright)
still leaves its directory in that caller's `TMPDIR`. That cycle's GOAL records it as a known
limitation; pre-existing.

*Horizon: Part I, gates · Depends on: sandbox-dirs-left-on-kill · Refs: [`spec/sandbox-dirs-left-on-kill/`](spec/sandbox-dirs-left-on-kill/) (GOAL non-goals, Q4); `bin/sandbox.sh`*
**Seed:** [`issues/sandbox-dirs-outside-repo-runs.md`](issues/sandbox-dirs-outside-repo-runs.md) · *status: unshaped*

## The static skip check admits a renamed skipper and a subclassed outcome type

The skip check reads a skip by the word it is spelled with, so `from pytest import skip as go`
then `go("x")` passes it, and so does a class that subclasses `pytest.skip.Exception`, raised. Both
are statically visible, and both pass the check before and after `skip-check-fence-gaps`. None
exists today. Found while planning that cycle, 2026-11-09.

*Horizon: Part I, gates · Depends on: skip-check-fence-gaps (cleared: landed on `develop` 2026-11-09) · Refs: [`spec/skip-check-fence-gaps/`](spec/skip-check-fence-gaps/) (PLAN §5, Q1)*
**Seed:** [`issues/skip-check-import-aliases.md`](issues/skip-check-import-aliases.md) · *status: unshaped*

## A conftest can drop rows from a CI run without skipping them

`collect_ignore`, a `pytest_collection_modifyitems` that removes items, or
`pytest.exit(..., returncode=0)` make rows vanish from a passing CI run as surely as a skip, and the
skip check does not look for them (`pytest.exit` with its default return code fails the run). None
does so today. Raised by the adversarial review of `skip-check-fence-gaps`'s plan, 2026-11-09.

*Horizon: Part I, gates · Depends on: — · Refs: [`spec/skip-check-fence-gaps/`](spec/skip-check-fence-gaps/) (PLAN §4a, §5, Q2); `tests/conftest.py`*
**Seed:** [`issues/skip-check-deselection.md`](issues/skip-check-deselection.md) · *status: unshaped*

## The static skip check's behaviour is pinned for some forms and positions, not all

`skip-check-fence-gaps` leaves three pin gaps its third review found: the "defined again"
report is pinned for some module-scope binding forms, a raised `or` for its last operand only, and
some admitted values and non-bindings not at all. The check behaves correctly on each; a mutant can
change it and pass every row. The fix is one planted row per binding form, raise operand position
and admitted value position, and a mutant sweep with additive mutants. Seeded by the maintainer's
landing ruling, 2026-11-09.

*Horizon: Part I, gates · Depends on: skip-check-fence-gaps (cleared: landed on `develop` 2026-11-09) · Refs: [`spec/skip-check-fence-gaps/`](spec/skip-check-fence-gaps/) (REVIEW cycle 3, G1–G3)*
**Seed:** [`issues/skip-check-pin-completeness.md`](issues/skip-check-pin-completeness.md) · *status: unshaped*

## Two timing rows miss a wait made outside the clock they control

The probe's raised-ending rows and the worker-cannot-start row now measure on a clock the test
controls. Each misses a wait its clock does not route: a probe that sleeps out its deadline through
`time.sleep` bound at import, and a call that waits on its attempt's event directly instead of
through `_await`. Both are deeper variants of faults the rows already catch. Found by a blind
review's hand-planted faults, 2026-11-10; introduced with those clocks.

*Horizon: Part I, gates · Depends on: — · Refs: [`spec/stalled-reconnect-test-timing/`](spec/stalled-reconnect-test-timing/); `tests/test_probes.py`; `tests/test_ssh_exec.py`*
**Seed:** [`issues/timing-rows-unrouted-waits.md`](issues/timing-rows-unrouted-waits.md) · *status: unshaped*

## Nothing would catch the next silently wrong annotation

`auth.py`'s `AUTH_MODES` carried a slice inside its annotation's subscript for months:
`typing.get_type_hints` and eager evaluation both accepted it, in a high-blast-radius module, and it
was fixed only because `stack-upgrade` happened to rewrite the file (R7). Nothing in the suite or
the gate checks any other annotation. A gate step or standing test that type-checks every member's
`src/`, or at least rejects an annotation under `cluster_mcp` that resolves to a non-type, closes
it; the tool is the plan's call. Found by `stack-upgrade`'s GOAL non-goals, carried at retirement,
2026-10-17.

*Horizon: Part I, gates · Depends on: — · Refs: runs where the gate runs, so CI picks it up through its mirror of the gate (`ci-workflow`; cleared: landed on `develop` 2026-10-18); [`spec/stack-upgrade/`](spec/stack-upgrade/) pins the one annotation*
**Seed:** [`issues/annotation-check.md`](issues/annotation-check.md) · *status: unshaped*

## A sandbox killed with SIGKILL leaves its directory behind

`bin/sandbox.sh` removes its throwaway HOME from a trap, which SIGKILL never runs, and several test
harnesses stop a sandbox's process group with SIGKILL. Each such stop leaves a bare
`cluster-mcp-sandbox.*` directory in the host's `TMPDIR`: about 60 per full-suite era, many more
per mutation sweep, and 18,061 on one developer Mac. Pre-existing; `capability-probe`'s own drives
add one or two per run, through the shared SSH test server.

*Horizon: Part I, gates · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (TECH P3); `bin/sandbox.sh`; `tests/ssh_server.py`*
**Seed:** [`issues/sandbox-dirs-left-on-kill.md`](issues/sandbox-dirs-left-on-kill.md) · *status: adopted:sandbox-dirs-left-on-kill*

## A disk-image step that hangs outlives its test

On macOS the full-filesystem write test builds a real 4 MB volume with `hdiutil`. Its fixture waits
120 s for each step and, at the timeout, fails the test without stopping the step: one stalled
`hdiutil create` and its formatter stayed with a half-made device for about a day on a developer
Mac. Pre-existing; macOS only, since the CI runner never calls `hdiutil`.

*Horizon: Part I, gates · Depends on: — · Refs: `tests/test_ssh_exec.py` (`_host`, `full_volume`); [`spec/safe-execution/`](spec/safe-execution/)*
**Seed:** [`issues/full-volume-fixture-leaks-hdiutil.md`](issues/full-volume-fixture-leaks-hdiutil.md) · *status: unshaped*

## The `integration` marker says it drives the CLI, and not every integration test does

`pyproject.toml` describes `integration` as "drives the installed CLI", but `test_docs_modules_absent`
and the git-backed absence-message controls in `tests/test_registry.py` are `integration` only
because they start git, which the unit guard forbids in a `unit` test. In practice the marker means
"not `unit`"; its description states a narrower rule, and `AGENTS.md` § Testing notes the mismatch
instead of fixing it. Rewording both markers to the line the unit guard draws settles it. Found by
the `absence-check-leftover-classification` plan, 2026-10-19.

*Horizon: Part I, gates · Depends on: — · Refs: [`spec/absence-check-leftover-classification/`](spec/absence-check-leftover-classification/) (PLAN §5)*
**Seed:** [`issues/integration-marker-wording.md`](issues/integration-marker-wording.md) · *status: unshaped*

## The image's init is pinned by its recipe, not by what it reaps

The shipped image runs `tini` as PID 1 so the orphaned watchdog of each completed `local` call is
reaped, but only a text check of the `Dockerfile` pins it. A CI job that builds the image and counts
zombies after many calls would pin the behaviour. Not measured (no container runtime on the
development host).

*Horizon: Part I, gates · Depends on: — · Refs: [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) (REVIEW cycle 3, B6); `Dockerfile`; `tests/test_packaging.py`*
**Seed:** [`issues/image-init-reaping.md`](issues/image-init-reaping.md) · *status: unshaped*

## A write whose host is lost after staging leaves its staging directory behind

Over `ssh` a write stages its content in a fresh 0700 directory beside the target and removes it
on the same SFTP session. When the host is lost after staging, that session is dead and the
directory stays, holding the user's own content: the write returns `-1002` with the target
untouched, or, if the host is back at once, succeeds and leaves the checksum file. Pre-existing;
found by `ssh-reconnect-loop`'s review, 2026-10-26, which corrected the texts and deferred the
cleanup.

- 2026-11-05: `spec/ssh-half-open-link/` P2: such a write now raises `TransferLost` naming the staging directory left; the cleanup is still this seed's.

*Horizon: Part I, executor · Depends on: ssh-reconnect-loop (cleared: landed on `develop` 2026-10-27) · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/) REVIEW.md cycle 1; `AGENTS.md` § Invariants §2*
**Seed:** [`issues/ssh-write-staging-leftover.md`](issues/ssh-write-staging-leftover.md) · *status: unshaped*

## A reconnect stuck in DNS or the SSH agent blocks fresh reconnects until it returns

At most one connect attempt is in flight, so while one is stuck in a step the executor cannot end (a
DNS lookup, a `Match exec` command, the TCP connect, which have no transport to close yet, or an
SSH-agent query, whose transport the abort closes while the worker still waits on the agent), every
new call fails at its own bound even if the host is back; once the step returns, the next call
reconnects. Found by `ssh-reconnect-loop`'s plan, 2026-10-23 (PLAN §5 risk 3), the accepted cost of
its one-attempt rule.

- 2026-10-26: corrected. As first filed, the SSH-agent query was listed among the steps with nothing
  to close; the abort closes its transport, and the worker's late outcome is discarded.

*Horizon: Part I, executor · Depends on: ssh-reconnect-loop (cleared: landed on `develop` 2026-10-27) · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/) PLAN §5*
**Seed:** [`issues/ssh-reconnect-stuck-step.md`](issues/ssh-reconnect-stuck-step.md) · *status: unshaped*

## Nothing pins that a reconnect's abort and release reach every ProxyJump hop

A reconnect attempt that is abandoned or fails closes every ProxyJump hop it made, but the suite
never builds a chain: its fake connection has no gateway, so a change that stops at the first hop
passes. The bound still holds; a hop could be left running unnoticed. Found by
`ssh-reconnect-loop`'s final review, 2026-10-27, as a missing pin.

- 2026-11-05: `spec/ssh-half-open-link/`'s liveness close goes outermost hop first, pinned on a fake chain only; the seed records it.

*Horizon: Part I, executor · Depends on: ssh-reconnect-loop (cleared: landed on `develop` 2026-10-27) · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/) REVIEW.md cycle 3*
**Seed:** [`issues/ssh-gateway-hops-unpinned.md`](issues/ssh-gateway-hops-unpinned.md) · *status: unshaped*

## A connection reset while a call opens its channel escapes as a raw exception

In `ssh` mode a call opens its channel before the guard that turns a lost connection into a result,
so a link that resets just then raises Paramiko's `ConnectionResetError` out of `SSHExecutor.run`
instead of reporting that the command was not run. Seen once against a test server that dropped the
connection, 2026-11-02. Pre-existing; the SFTP paths were not checked.

- 2026-11-05: `spec/ssh-half-open-link/` now reconnects a channel or SFTP-session open that a lost connection cut short; a reset at that instant is still unpinned; the seed records it.

*Horizon: Part I, executor · Depends on: — · Refs: [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) (TECH P2 remediation); `core/executor/ssh.py` (`_exec`)*
**Seed:** [`issues/ssh-open-session-reset-raises.md`](issues/ssh-open-session-reset-raises.md) · *status: unshaped*

## Loopback SSH rows break under load, with no time bound missed

Three loopback SSH rows (`test_startup_output_is_separated[tcsh]` and `[bash]`, and
`test_timeout_stop.py`'s signal-death row over an `sh` login shell) have failed on a busy host with
Paramiko's `EOFError` or a socket error, then passed alone and on re-run: twice on CI, twice
locally, 2026-10-29 to 2026-11-02. None checks a time bound; the link itself broke, by a mechanism
nobody has found, in the test server, Paramiko or the executor. Pre-existing; split out of
`stalled-reconnect-test-timing` at its GOAL gate, 2026-11-09.

*Horizon: Part I, executor · Depends on: — · Refs: [`spec/stalled-reconnect-test-timing/`](spec/stalled-reconnect-test-timing/); `issues/ssh-open-session-reset-raises.md`; `tests/ssh_server.py`*
**Seed:** [`issues/loopback-ssh-breaks-under-load.md`](issues/loopback-ssh-breaks-under-load.md) · *status: unshaped*

## A local command in flight can outlive the server that launched it

In `local` mode each command runs in a process group of its own, which only its call ever signals. A
server killed mid-command leaves the group running to its own end, as is true of any tool call today.
A server that exits normally can leave one too: the startup probe's worker, a daemon thread abandoned
at the probe's deadline, dies with the interpreter between its timeout's SIGTERM and SIGKILL, so a
group behind a login profile that ignores SIGTERM and hangs runs on. `capability-probe`'s startup
probe adds both instances. Pre-existing.

- 2026-11-02: the call is no longer a group's only signaller: `timeout-process-cleanup`'s watchdog
  stops the group once the program dies with its command unreported. Both cases remain (a killed
  server's program has not died; the probe's hang comes before the watchdog exists).

*Horizon: Part I, executor · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (PLAN §5, REVIEW); `AGENTS.md` § Invariants §2, §3*
**Seed:** [`issues/local-command-outlives-server.md`](issues/local-command-outlives-server.md) · *status: unshaped*

## A profile's sub-second `TMOUT` may drop the functions a script inherits

A `run_command` script inherits the login's functions through a `read` loop, and a profile's `TMOUT`
bounds that `read`. bash 4 and later accept a fractional `TMOUT`, so a sub-second one could end the
loop before `module` is exported. Read from bash's source, not measured (the development host has
bash 3.2 only). Pre-existing.

*Horizon: Part I, executor · Depends on: — · Refs: [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) (TECH P1 remediation, F1); `core/executor/launch.py` (`SCRIPT`); `AGENTS.md` § Invariants §2*
**Seed:** [`issues/script-function-export-tmout.md`](issues/script-function-export-tmout.md) · *status: unshaped*

## One very large site file can cost every site rule

The startup read takes each `/etc/agents.d/*.md` file whole, with no size limit, inside one 10 s
bound. A file of tens of megabytes can push the `ssh` read past it, and then no site rule is served
at all; when the read finishes, `cluster_context` returns the whole file. A per-file limit that
leaves an oversize file out and names it, as the budget does, fixes it. Found by
`agents-d-instructions`' planning, 2026-10-19. The convention's files are a few kilobytes, so it
takes a mistake in the directory to show.

*Horizon: Part I, safety · Depends on: agents-d-instructions (the startup read it bounds; cleared: shipped in 0.1.3) · Refs: [`spec/agents-d-instructions/`](spec/agents-d-instructions/) PLAN § 5; `AGENTS.md` § Invariants §8*
**Seed:** [`issues/site-file-size-cap.md`](issues/site-file-size-cap.md) · *status: unshaped*

## Every start asks the package index for FastMCP's latest version

FastMCP's banner, on by default, checks PyPI for a newer FastMCP at every start (cached for 12
hours) unless `FASTMCP_CHECK_FOR_UPDATES=off`, so the server makes an outbound request nobody asked
for and can advise upgrading a dependency `uv.lock` pins. Turning the check off (or the banner) at
startup fixes it. Pre-existing. Noted by `agents-d-instructions`' planning, 2026-10-19. The request
is bounded at 2 s and fails silently.

*Horizon: Part I, safety · Depends on: — · Refs: [`spec/agents-d-instructions/`](spec/agents-d-instructions/) PLAN § 5*
**Seed:** [`issues/fastmcp-update-check.md`](issues/fastmcp-update-check.md) · *status: unshaped*

## A version the lock lifts never reaches a user who installs from git

`uv.lock` pins what `uv sync` installs (development, CI). A `git+…` or `uvx --from` install, and the
container image's `uv pip install`, resolve fresh within the declared ranges and never read it, so a
fix that only lifts a locked version changes what the tests run and nothing a user receives. Where
the newer version matters, the declared requirement needs a floor. Pre-existing. Found by
`capability-extras` P4, whose install probe resolved a newer dependency than the lock pins,
2026-10-31.

*Horizon: Part I, safety · Depends on: — · Refs: [`spec/capability-extras/`](spec/capability-extras/) (TECH P4, PLAN §5); `AGENTS.md` § Packaging*
**Seed:** [`issues/unlocked-install-floors.md`](issues/unlocked-install-floors.md) · *status: unshaped*

## What a timeout still cannot stop

`timeout-process-cleanup`'s watchdog starts after the login initialisation and keys on the deadline's
TERM reaching the launch. A startup file that hangs leaves what it started running under a non-root
`delegate` server, and in every mode a process it started that ignores TERM and holds none of the
call's output (over SSH, one that holds it too, once the login shell has died of the TERM); an SSH
server that ignores the `signal` request stops nothing; a startup file that shadows the
launch's builtins past what the prologue undoes can make the stop fail and stop a command early; and
a step of the server's wall clock while a startup file runs can refuse a command early, or let a late
one start, which under a non-root `delegate` server runs on. Found by `timeout-process-cleanup`'s
planning research, 2026-11-01, and its reviews, 2026-11-02 and 2026-11-04.

*Horizon: Part I, redesign · Depends on: timeout-process-cleanup (cleared: landed on `develop` 2026-11-04) · Refs: `AGENTS.md` § Invariants §3; [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) PLAN §5; a case that can't be fixed becomes `accepted-behaviour` only on the maintainer's ruling*
**Seed:** [`issues/timeout-stop-limits.md`](issues/timeout-stop-limits.md) · *status: unshaped*

## A live link that answers nothing for longer than its liveness verdict reads as dead

The silent-link detection `ssh-half-open-link` added calls a link dead when a probe goes unanswered,
with nothing at all heard since, past its verdict: a background probe two connect bounds less
`VERDICT_MARGIN` after it went (29 s at the default bound), and, while a call starts, one bound after
that call's start (15 s). A live link on which nothing arrives for that long, such as a quiet command
whose peer answers nothing for 29 s (an outage of about 25 s), or an SFTP upload slower than about
0.75 KB/s, is cut and reported as lost. While another call starts on the connection, the floor is
that call's 15 s verdict. The floor is the price of a verdict inside the reconnect bound;
a longer bound lowers it. Not pre-existing: it is that cycle's recorded limit.

*Horizon: Part I, trade-off · Depends on: ssh-half-open-link (cleared: landed on `develop` 2026-11-06) · Refs: [`spec/ssh-half-open-link/`](spec/ssh-half-open-link/) PLAN §3 Deviation 3, research 01 §5; what can't be lifted becomes `accepted-behaviour` only on the maintainer's ruling*
**Seed:** [`issues/ssh-liveness-message-gap.md`](issues/ssh-liveness-message-gap.md) · *status: unshaped*

## The rename left two identity strings a client or a token sees

The JWT issuer and audience are still `rcac-mcp`, so every token a deployment has minted keeps
working. They move under a window that accepts both names, signing the new one, so no minted token
breaks. `serverInfo.version` reports FastMCP's version rather than this server's, and is set to this
server's. The third string the rename left, the Purdue favicon, waits for member routes and moved to
`[rcac]` in Part II.

*Horizon: Part I, rename · Depends on: the rename (landed names; cleared: landed on `develop` 2026-10-30) · Refs: `issues/rename-in-docs.md` (`SECURITY.md`'s claims move with it); the favicon in `issues/site-extras.md`*
**Seed:** [`issues/rename-leftover-identity-strings.md`](issues/rename-leftover-identity-strings.md) · *status: unshaped*

## Every in-repo doc says cluster-mcp

The rename renamed names, and most docs now say `cluster-mcp`; in places they still read as a
Purdue server's documentation rather than a general server's, with Purdue as one site. Every tracked
doc outside `spec/` presents the project as `cluster-mcp`, keeping the old name only where it
describes the deprecation window or the compat distribution, and Purdue only where it describes
`[rcac]` or labels a Purdue example. The legacy-name window stands: deprecated in 0.2.0, removed no
earlier than 0.4.0.

*Horizon: Part I, rename · Depends on: — · Refs: `issues/rename-leftover-identity-strings.md` (the token claims in `SECURITY.md`); [`spec/rename-to-cluster-mcp/`](spec/rename-to-cluster-mcp/)*
**Seed:** [`issues/rename-in-docs.md`](issues/rename-in-docs.md) · *status: unshaped*

**Releases.** Every entry here ships in the first release after it lands, whichever Part that
release closes. The legacy names keep their window: deprecated in 0.2.0, removed no earlier than
0.4.0.

---

# Part II — 0.3.0: capabilities behind package extras

Fourteen entries: eleven cycles and three absorbed seeds, which take the installed surface from one
fixed set of tools to the families a deployment chooses. The core keeps the machinery and serves no
family of its own; `[shell]` and `[files]` make the shell and the file family choices; the jobs and
modules interfaces each get a first implementation, `[slurm]` and `[lmod]`; `[files-xdu]` answers the
file family from an index; the site interfaces give a center abstract tools to implement; and
`[rcac]` bundles them for Purdue.

**The pattern.** Each interface is defined so that a second implementation (PBS or Flux;
Environment Modules; another center's extra) is a contribution, not a redesign. The pattern is
documented for other centers; second implementations are not built here.

**The rules.** Every family follows `issues/tool-surface.md`: names a client can allow-list by
pattern, honest annotations, response budgets, and `--profile read-only`. Today's tool names don't
survive 0.3.0 as aliases: it is a clean break, and the 0.3.0 notes give each new name and the new
install line.

**Compat.** The `rcac-mcp` distribution and command keep installing what today's users have
through their window: deprecated in 0.2.0, removed no earlier than 0.4.0.

**When it starts.** Once the three entries Part I puts before it have landed: the surface fixture
and the two capability-load fixes. The fourth, the mutation run's hung child, is cleared (landed on
`develop` 2026-11-12).

The suggested order is the one below: core extraction with `[shell]` and `[files]`, then jobs and
`[slurm]`, then modules and `[lmod]`, then `[files-xdu]`, then the site interfaces and `[rcac]`.

## The core serves no tool family of its own

Since `capability-extras` a bare `cluster-mcp` is the core alone, but the core still registers
`run_command` and the file tools beside `cluster_context`, so every extra adds to a shell and a file
family rather than defining what is served. The core becomes the executor and its modes (`ssh`,
`local`, `delegate`), the transports, the capability loader and probe, and the instructions with
`/etc/agents.d` in them. It keeps `cluster_context` and serves no tool family of its own: a bare
install serves no command tool.

*Horizon: 0.3.0, first · Depends on: release 0.2.0 (cleared: released 2026-11-12); the three entries Part I puts before Part II; mutant-child-outlives-timeout (cleared: landed on `develop` 2026-11-12); mutants-workflow-timeout, before this cycle's review; capability-extras and capability-probe (cleared: landed on `develop` 2026-11-01) · Refs: shaped with `issues/shell-extra.md` and `issues/files-extra.md`, or just ahead of them*
**Seed:** [`issues/core-extraction.md`](issues/core-extraction.md) · *status: unshaped*

## Every tool family follows one set of rules

No tool carries MCP annotations, no tool has a response budget, and nothing narrows what is served,
so a client can't tell a reader from a writer without reading prose, and a family a client could
pre-approve needs names a pattern can select. The rules — names a client can allow-list by pattern,
honest annotations, response budgets, `--profile read-only` — are set by the `[shell]` and `[files]`
cycles, which split this seed between them, and every later family follows them. The file family
first sketched here moved to `[files]`, and `run_command`'s steering to Part III.

*Horizon: 0.3.0, with `[shell]` and `[files]` · Depends on: core-extraction; safe-execution (the argv executor; cleared: landed on `develop` 2026-10-23) · Refs: split across `issues/shell-extra.md` and `issues/files-extra.md`; a clean break, no aliases (decided 2026-11-12)*
**Seed:** [`issues/tool-surface.md`](issues/tool-surface.md) · *status: unshaped*

## `[shell]`: a remote shell, and nothing about HPC

Every server serves `run_command`, so an operator can't offer the cluster through named tools alone.
Moving it out of the core into a member installed by a `[shell]` extra makes the shell a choice made
at installation, like Slurm or the site's storage: `run_command` over the SSH bridge, with
instructions that say nothing about HPC, so `cluster-mcp[shell]` alone is a remote shell. No lexing
or filtering yet; that is Part III. The instructions stop naming `run_command` when it is absent.
Absence is a choice of scope, not containment (file writes reach startup files, job scripts run
anything), so the docs name the combination that does confine: no shell plus `--profile read-only`.
Ruled 2026-11-04: a bare install serves no shell, and the docs present `[shell]` as the obvious
opt-in for a user running their own server.

*Horizon: 0.3.0, with core-extraction · Depends on: core-extraction, tool-surface (the rules and profiles), capability-extras (the member mechanism; cleared: landed on `develop` 2026-11-01) · Refs: `issues/shell-rails.md` (Part III); `issues/site-extras.md` (`[rcac]` pulls it)*
**Seed:** [`issues/shell-extra.md`](issues/shell-extra.md) · *status: unshaped*

## `[files]`: the POSIX file family

The file tools are too thin — `list_directory` misreads some entries, `read_file` has no offset, and
there is no stat, find, grep, edit, move or copy — so agents fall back to the shell. `cluster-mcp[files]`
serves list, find, grep, stat, read, write, edit, move and copy, and SFTP put and get, each
structured, bounded and annotated by the rules above. A byte-exact round trip needs no shell.

*Horizon: 0.3.0, with core-extraction · Depends on: core-extraction, tool-surface; safe-execution (cleared: landed on `develop` 2026-10-23) · Refs: absorbs `list-directory-parsing`; conflicts with `issues/files-xdu-extra.md`*
**Seed:** [`issues/files-extra.md`](issues/files-extra.md) · *status: unshaped*

### Absorbed: `list_directory` misreads some entries

`list_directory` parses the column text of `ls -l`, so a name with a newline is split, a symbolic
link's name carries its `-> target`, a name loses its leading spaces, and a device file's
`major, minor` size fails the whole call. Parsing a NUL-terminated form fixes all four.
Pre-existing. Found by `safe-execution`'s planning research, 2026-10-17. The `[files]` family
rewrites `list_directory`, so the parse is fixed once, in the rewrite, rather than patched in a tool
about to be replaced.

*Horizon: with files-extra · Depends on: — · Refs: absorbed by `files-extra`; [`spec/safe-execution/`](spec/safe-execution/) research 04 §4, PLAN risk 7*
**Seed:** [`issues/list-directory-parsing.md`](issues/list-directory-parsing.md) · *status: unshaped*

## A `job_*` interface a scheduler extra implements

The job tools are Slurm's programs one to one, so an agent that learns them has learned Slurm, and
a cluster on PBS or Flux would need a second set under other names. The `job_*` family is defined
once — names, parameters, results, annotations, error forms — and a scheduler extra implements it.
Large trees are indexed through it later in this Part.

*Horizon: 0.3.0, after core extraction · Depends on: core-extraction, tool-surface · Refs: `[slurm]` (next entry) is its first implementation; planning decides whether the two are one cycle*
**Seed:** [`issues/jobs-interface.md`](issues/jobs-interface.md) · *status: unshaped*

## `[slurm]`: the first `job_*` implementation, accepting what a model naturally sends

Found while submitting and watching test jobs through the server: `gpus` must be a string, a single
job id must be wrapped in a list, a purged id is an error rather than an empty result, and five
tools answer "tell me about this job". `[slurm]` implements the interface so that resources accept
an int or a string, ids a scalar or a list, one `job_info` replaces the five, and every validation
error says what to send instead.

*Horizon: 0.3.0, with jobs-interface · Depends on: jobs-interface, tool-surface, capability-extras (cleared: landed on `develop` 2026-11-01), safe-execution (cleared: landed on `develop` 2026-10-23) · Refs: rebuilds the Slurm member, an extra since capability-extras*
**Seed:** [`issues/slurm-capability.md`](issues/slurm-capability.md) · *status: unshaped*

## A `module_*` interface a module-system extra implements

None of the tools is about software: an agent can't discover what is installed or what loading a
module would change, and module state does not persist between calls. The `module_*` family is
defined once — search, list, show, and modules loaded into a call's environment, as a `modules`
parameter on `run_command` and job submission — and a module-system extra implements it.

*Horizon: 0.3.0, after jobs · Depends on: core-extraction, tool-surface · Refs: `[lmod]` (next entry) is its first implementation; `modules` reaches `issues/shell-extra.md`'s and `issues/jobs-interface.md`'s tools*
**Seed:** [`issues/modules-interface.md`](issues/modules-interface.md) · *status: unshaped*

## `[lmod]`: module systems are the other half of "can I run this"

On an LMOD cluster an agent cannot discover what is installed, what versions exist, or what a
module load would do to the environment — so it guesses, and `INSTRUCTIONS.md` has to compensate
with prose. `module avail`, `module spider`, `module list` and `module show` carry nearly all the
value, behind the `module_*` interface. `module` is a shell function, not a binary, so the tools run
`$LMOD_CMD` and the probe needs a declaration beside `commands`; and `module avail` writes to stderr
and runs to thousands of lines, so filtering and truncation are part of the tool.

*Horizon: 0.3.0, with modules-interface · Depends on: modules-interface; capability-extras (strictly; cleared: landed on `develop` 2026-11-01) · Refs: a core edit to the capability record and the probe (`AGENTS.md` § Invariants §7)*
**Seed:** [`issues/lmod-tool-group.md`](issues/lmod-tool-group.md) · *status: unshaped*

## `[files-xdu]`: the file family answered from an index where one helps

"What's filling my scratch" and "find every `*.h5` here" end today in a recursive `find` or `du` on
a parallel filesystem — the long metadata walk login-node rules forbid. `cluster-mcp[files-xdu]`
serves the same family as `[files]`, answered from xdu's index where a cached index helps: find,
usage, and listing large trees. It conflicts with `[files]`: the conflict is declared in packaging,
and since pip and `uvx` never read uv's conflict declaration, the load also refuses when both
distributions arrive, naming both. It uses the system xdu, detected, never installed; installing
anything into a user's home is ruled out. Indexes live in scratch, large trees are indexed through
the jobs interface, and the tools take typed operations only, never SQL from the caller.

*Horizon: 0.3.0, after modules · Depends on: files-extra (the family), jobs-interface (indexing jobs) · Refs: absorbs `xdu-storage`; `[rcac]` pulls it*
**Seed:** [`issues/files-xdu-extra.md`](issues/files-xdu-extra.md) · *status: unshaped*

### Absorbed: the xdu index behind `[files-xdu]`

[xdu](https://github.com/xdu-project/xdu) indexes a tree into Parquet and queries it through
embedded DuckDB, with no I/O throttle on indexing and no byte-sum rollup on the query side; the
rollup is an upstream request. The seed keeps the xdu evidence and the index's mechanics — detect,
keep in scratch, build politely, query by typed operation. As first filed it installed xdu into the
user's home with consent and reported quotas; both are out.

*Horizon: with files-xdu-extra · Depends on: — · Refs: absorbed by `files-xdu-extra`*
**Seed:** [`issues/xdu-storage.md`](issues/xdu-storage.md) · *status: unshaped*

## Site interfaces: abstract tools a center implements in its own extra

How much storage is left and how much allocation is left to spend have site-specific answers, and
today the only answers are Purdue's commands wrapped as Purdue tools. Abstract site tools, starting
with storage quota and allocation balance (working names `site_quota` and `site_balance`, open to
better ones; planning proposes the starting surface and names), are defined once and implemented in
a center's extra. A site can also add custom tools that work with its `/etc/agents.d`.

*Horizon: 0.3.0, after `[files-xdu]` · Depends on: core-extraction, tool-surface · Refs: absorbs `generalize-storage-discovery`; `[rcac]` is its first implementation*
**Seed:** [`issues/site-interfaces.md`](issues/site-interfaces.md) · *status: unshaped*

### Absorbed: not every cluster has a Lustre scratch and a myquota

`storage_paths()` parses the output of `myquota`, and scratch discovery shells out to `findscratch` —
both Purdue commands, and neither degrades on a cluster that lacks them. Since `capability-probe`
the RCAC member is withheld on such a cluster in `ssh` and `local` modes, but `delegate` mode,
`--skip-probes` and a probe that gives no answer still serve it there. The `rcac://storage`
resource is built on the same assumption. Generalizing means a discovery protocol with a site-provided
implementation and an honest "unknown" rather than a parse failure — which is the storage-quota
interface. Found by the harness port, 2026-08-26.

*Horizon: with site-interfaces · Depends on: — · Refs: absorbed by `site-interfaces`; the helper seam it needs, the undecorated `resolve_storage_paths()`, exists (`resource-reads-without-executor`, landed on `develop` 2026-10-29)*
**Seed:** [`issues/generalize-storage-discovery.md`](issues/generalize-storage-discovery.md) · *status: unshaped*

## `[rcac]`: a site extra is shorthand plus a point of view

`cluster-mcp[rcac]` means `cluster-mcp[slurm,lmod,files-xdu,shell]` plus RCAC's implementations of
the site interfaces (over `myquota` and `mybalance`), and Purdue's member routes and favicon — one
install target a user can name without knowing that a cluster runs Slurm and LMOD. That makes it
both a dependency alias and the home for the `cluster-mcp-rcac` member: Purdue's tools and the
Purdue part of the instructions. Getting the boundary right here is what makes another center's
extra a matter of contribution rather than redesign, so this cycle produces a documented pattern,
not just a Purdue special case.

*Horizon: 0.3.0, last · Depends on: slurm-capability, lmod-tool-group, files-xdu-extra, shell-extra, site-interfaces; capability-extras (strictly; cleared: landed on `develop` 2026-11-01) · Refs: adds member routes for the favicon from `issues/rename-leftover-identity-strings.md`; sets the pattern other centers copy*
**Seed:** [`issues/site-extras.md`](issues/site-extras.md) · *status: unshaped*

**Release 0.3.0.** A deployment installs the families it wants: a bare `cluster-mcp` serves
`cluster_context` alone, `cluster-mcp[shell]` is a remote shell, and `cluster-mcp[rcac]` is the
Purdue bundle. The `rcac-mcp` distribution still installs what today's users have, and the legacy
names still work through their window.

---

# Part III — 0.4.0: observability, audit logging, and rails on the shell

Two entries. Every call leaves a record on the machine where its command ran, and `run_command`
steers a command toward the tool that fits. The records' design covers the hosted single-user token
mode, though that mode is not yet ordered.

## A record of every call, kept where the command ran

The server keeps no record of what it did: a user can't see what their agent ran, and an operator
can't see what ran as whom. Records live on the machine where commands run: in `ssh` mode on the
destination cluster under `$XDG_DATA_HOME/cluster_mcp/` (by default `~/.local/share/cluster_mcp/`);
in `local` mode and the single-user token mode, the same path, as the user; in `delegate` mode each
user's records in their own path, written as that user, plus a server-side copy of every user's
records and a system event log, whose place planning proposes. Cluster tests point `XDG_DATA_HOME`
into a scratch directory.

*Horizon: 0.4.0 · Depends on: release 0.3.0 (the surface it records) · Refs: must cover `issues/https-token-mode.md`; a `delegate` write path is `AGENTS.md` § Invariants §5 work*
**Seed:** [`issues/observability-audit.md`](issues/observability-audit.md) · *status: unshaped*

## Rails on `run_command` that steer toward the tool that fits

An agent with a shell can still ignore the families 0.3.0 builds. `run_command` lexes each command
with `shlex` and checks it against site-extensible rules that steer toward the bespoke tools — a
recursive walk to the bounded find or the index, a bare `module load` to the `modules` parameter, an
`sbatch` flood to HyperShell's `hs submit`. The rails are a net for mistakes, not a security
boundary, and the docs say so.

*Horizon: 0.4.0 · Depends on: release 0.3.0 (the tools it steers toward), shell-extra · Refs: first sketched in `issues/tool-surface.md`; the HyperShell rule needs no HyperShell capability*
**Seed:** [`issues/shell-rails.md`](issues/shell-rails.md) · *status: unshaped*

**Release 0.4.0.** Every call leaves a record where it ran, and the shell steers. It is the earliest
release the legacy names may be removed in.

---

# After 0.3.0 — not yet ordered

Four entries whose order among themselves and against Part III is the maintainer's.

## Run your own server on the cluster, behind a token

A single-user Streamable HTTP server, Jupyter-style: the user starts it on a login node or in a
batch job, and it runs as them. A JWT (`aud` bound to the server URI, `sub` the Unix user, `exp`
required) is printed at startup and written to a `0600` runtime file, or minted ahead with
`token new --lifetime` and passed by environment variable or file — never in argv or a URL. The
default listener is a `0600` unix socket for `ssh -L` forwarding; TCP is opt-in and always
token-gated; `Origin` and `Host` are validated; an idle timeout ends it. Commands then run next to
the data, with no SSH round trip per call.

A shared multi-user endpoint — one server that many users authenticate to — is out of scope for
now.

*Horizon: after 0.3.0, not yet ordered · Depends on: release 0.3.0, stack-upgrade (the HTTP transport; cleared: landed on `develop` 2026-10-17), safe-execution (cleared: landed on `develop` 2026-10-23) · Refs: adds a mode to the execution-mode ladder (`AGENTS.md` § Invariants §4); Part III's records design covers it*
**Seed:** [`issues/https-token-mode.md`](issues/https-token-mode.md) · *status: unshaped*

## A HyperShell capability

An agent with many small tasks reaches for a loop of job submissions; HyperShell runs them under one
submission. Nothing in the server knows about it beyond the note Part III's rails return. Filed as
a placeholder so this entry has a seed; it is unshaped.

*Horizon: after 0.3.0, not yet ordered · Depends on: release 0.3.0 · Refs: `issues/shell-rails.md`; `issues/jobs-interface.md` (the interface pattern)*
**Seed:** [`issues/hypershell-capability.md`](issues/hypershell-capability.md) · *status: unshaped*

## The legacy names outlive their window

The rename kept every old name working through a deprecation window: the `rcac-mcp` command and its
compat distribution, the `RCAC_SSH_HOST`, `RCAC_USER_MAP` and `RCAC_INSTRUCTIONS_BUDGET` variables,
and the `rcac://` resource URIs. The README states the window, deprecated in 0.2.0 and removed no
earlier than 0.4.0, and the command and each variable warn with it; the aliases do not. Removing
them breaks every client config that still names one, so it ships in a release whose notes say so,
and the window's own tests and README section go with it.

*Horizon: 0.4.0 at the earliest, not yet ordered · Depends on: release 0.2.0 (the window opens there) · Refs: [`spec/rename-to-cluster-mcp/`](spec/rename-to-cluster-mcp/) (GOAL non-goals); `core/deprecation.py`*
**Seed:** [`issues/remove-legacy-names.md`](issues/remove-legacy-names.md) · *status: unshaped*

## Over SSH, a login rc file's background job can write into a result

The accepted behaviour below has a later fix: the bootstrap tags each line of the command's output
with the per-call nonce, and the backend keeps only tagged lines. It costs about a third more bytes,
an encoder on the login node and line-by-line streaming, and whether a tagged line can be torn past
`PIPE_BUF` is open. A PTY is ruled out.

*Horizon: after 0.3.0, not yet ordered · Depends on: release 0.3.0 · Refs: `issues/startup-background-jobs.md` (accepted-behaviour 2026-11-12); [`spec/safe-execution/`](spec/safe-execution/) PLAN §2.2a*
**Seed:** [`issues/startup-output-nonce-tagging.md`](issues/startup-output-nonce-tagging.md) · *status: unshaped*

---

# Settled questions

Deferrals closed **without** shipping — `declined` (considered and not taken on as debt) and
`accepted-behaviour` (reported as a defect, judged intended). They keep their `issues/` files because
nothing else in the repository records that the question was asked. Shipped work leaves no entry
here: `spec/{slug}/` holds that account and the code itself refutes a re-filing.

- **The factory has no front door** — *declined 2026-10-16.* The factory's front door is the
  operator's KB, where its method and skills now live; this repository carries only its profile
  (`AGENTS.md` § Factory). Record: [`issues/factory-onboarding-page.md`](issues/factory-onboarding-page.md).
- **A job name of 220–236 characters no longer fits the script's file name** — *accepted-behaviour
  2026-10-26.* The per-call token that keeps same-second scripts apart costs 17 characters of the
  255-byte name; such a call fails loudly before submitting, and truncating would break the name
  rule. Record: [`issues/sbatch-long-job-name.md`](issues/sbatch-long-job-name.md).
- **Over SSH, a login rc file's background job can write into a result** — *accepted-behaviour
  2026-11-12.* What such a job writes before the command's end record reaches the result; it is
  documented in `AGENTS.md` §3, the README and the `run_command` description, and pinned. The case of
  a startup file's job holding the call was fixed by the end records (2026-10-22). The later fix is
  seeded after 0.3.0. Record: [`issues/startup-background-jobs.md`](issues/startup-background-jobs.md).

---

# A note on security work

This server executes arbitrary shell commands, and in `delegate` mode it does so **as other people**,
from a privileged process, on shared research infrastructure. Deferrals that describe an
*unremediated* weakness — a live path to running a command as the wrong user, on the wrong host, or
without the intended authentication — do **not** appear in this file. They go to `.security/issues/`
and `.security/ROADMAP.md`, which are gitignored: a public, ordered index of live vulnerabilities is
an attacker's work plan. The *fixes* land as ordinary public commits and PRs when they ship.

`context-cache-cross-user`, since shipped, was in the public lane deliberately, and the judgement is
worth recording: the cached content was world-readable administrative markdown that every user could
read anyway, so there was no exploitable disclosure to conceal — only a caching bug whose *shape* was
cross-user. Had it cached anything user-private, it would have gone to the hidden lane instead. When
in doubt, use `.security/` and ask.
