# ROADMAP

The ordered index of work that is **not yet in flight**. One entry per `issues/{slug}.md` seed; the
seed holds the evidence and the draft criteria, this file holds the order and the reasoning about
order. Nothing here is a contract — the factory's feature step promotes a seed into a `spec/{slug}/GOAL.md`, and
that promotion is where appetite, non-goals and the R-IDs get negotiated with a human.

The first three Parts each end in a release. **Part 0** made the server safe and useful as it stood:
it shipped as 0.1.3, and its last fix, the resource read `rcac://storage`, ships in 0.1.4. **Part I**
is the arc this project is actually on — becoming a general `cluster-mcp` rather than a
Purdue-specific `rcac-mcp` — and ships as 0.2.0. **Part II** is the hosted mode that comes after.
**Part III** holds infrastructure work that no release waits on.

The order was revised on 2026-10-16. Users install `main` directly, so fixes for today's users ship
first, under the name they already have, before the rename. The dependency stack moves before any
mechanism — registration, composed instructions, annotations — is built on it, so each is built
once. And every cycle starts from and lands on `develop`; a release fast-forwards `main` to a
released `develop` commit, so nothing reaches users between releases.

A seed that another cycle **absorbs** keeps a short entry under that cycle, so every file in
`issues/` stays indexed until the absorbing cycle retires it.

Read `AGENTS.md` § *Direction* before starting anything in Part I; it states the destination that
these entries are steps toward. `AGENTS.md` § Factory describes the lifecycle that consumes these
seeds; its method lives in the operator's KB.

---

# Part 0 — Safe and useful as it stands

Every cycle Part 0 holds has landed. **Release 0.1.3** carried all but the last, ending with
`ssh-reconnect-loop` on 2026-10-27 ([`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/)),
after `sbatch-script-name-collision` and `agents-d-instructions` on 2026-10-26. The last,
`resource-reads-without-executor`, landed on 2026-10-29
([`spec/resource-reads-without-executor/`](spec/resource-reads-without-executor/)): reading
`rcac://storage` now returns the user's storage paths through the executor of the request that read
it, and it ships in **release 0.1.4**, as decided on 2026-10-27. `stack-upgrade` landed
on `develop` on 2026-10-17 ([`spec/stack-upgrade/`](spec/stack-upgrade/)), and `ci-workflow` on
2026-10-18 ([`spec/ci-workflow/`](spec/ci-workflow/)), so the release gate now runs on every push.
`safe-execution` landed on 2026-10-23 ([`spec/safe-execution/`](spec/safe-execution/)): every
tool passes exactly what it was given, under one bash, and these cycles build on it to fix what
today's users still hit.

*Corrected 2026-10-23: release 0.1.2 was cut on 2026-10-22 from `develop` `90b0938`, before
`safe-execution` landed. It carried the CI workflow, the sdist hygiene fix and a lock past two
dependency advisories, so the release that closes Part 0, and the first to carry its executor
fixes, is now 0.1.3.*

*Corrected 2026-10-18: release 0.1.1 was cut early, on 2026-10-18 from `develop` `c68adaa`, before
any of Part 0's fixes landed. It carried the dependency-stack upgrade, the docs strip, the test
suite and the both-era gates, so the release that closes Part 0 is now 0.1.2.*

*Corrected 2026-10-17: `stack-upgrade` landed before `ci-workflow`, so the release recipe's `gate`
gained the dependency audit first; `ci-workflow`, landing next, mirrors that gate — audit
included — through its "CI mirrors the gate" check.*

*Corrected 2026-10-17: two small fixes that `safe-execution` found and deferred joined Part 0, right
after that cycle: a lost SSH connection hangs every later call, and concurrent `sbatch` submissions
can overwrite each other's script. Both are what today's users hit, and both are small, so they ship
in the release that closes Part 0 (now 0.1.3) rather than wait for Part I.*

*Corrected 2026-10-17: the `rcac://storage` fix moved under the resource-read entry below. Its
handler runs `findscratch` and `myquota` through the request's executor, which a read does not get
yet, so fixing the `TypeError` alone would only change the error a client sees.*

**Release 0.1.3.** `main` fast-forwards to the released `develop` commit, and everyone who installs
`main` gets byte-exact writes, literal paths, `sbatch` arguments, one shell's semantics, clear
connection errors, a call that fails rather than hangs when the connection drops, job scripts that
never overwrite each other, and the site's rules in the instructions — under the name they already use.
Pages outside this repository that name its tools or install line — RCAC-Docs
`docs/agentic-ai/mcp_servers.md` and `docs/agentic-ai/running_agents/local.md` — are updated when
the release lands.

---

# Part I — Becoming cluster-mcp

Eleven cycles, after the rename, the capability extras, the capability probe, the timeout stop, the
silent-link check and the CI time budget, that take this from *the Purdue RCAC MCP server* to *an
MCP server for HPC clusters, with Purdue as one supported site*, ending in **release 0.2.0**. The
rename to `cluster-mcp` and the uv-workspace restructure landed on `develop` on 2026-10-30
([`spec/rename-to-cluster-mcp/`](spec/rename-to-cluster-mcp/)), keeping the old names through a
deprecation window. The capability extras landed on 2026-11-01
([`spec/capability-extras/`](spec/capability-extras/)): a bare `cluster-mcp` is the core alone,
`[slurm]` and `[rcac]` each install a member that registers through one entry-point group, and the
served instructions are composed from what loaded. The capability probe landed the same day
([`spec/capability-probe/`](spec/capability-probe/)): in `ssh` and `local` modes an installed
capability is served only where the cluster has the commands it declares, looked up once at startup
within a 10 s bound, while `delegate` mode and `--skip-probes` serve every installed capability. The
timeout stop landed on 2026-11-04
([`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/)): a timed-out command and
everything in its process group have exited within 2 × `GRACE` of the deadline in every mode, by a
watchdog that sends KILL after the grace, with the remaining limits recorded in
`issues/timeout-stop-limits.md`. The silent-link check landed on 2026-11-06
([`spec/ssh-half-open-link/`](spec/ssh-half-open-link/)): over `ssh`, a link that goes silent
without a reset is noticed within the reconnect bound and treated as a lost connection, and a call
in flight on it ends within that bound, with the floor below which a live link reads as dead
recorded in `issues/ssh-liveness-message-gap.md`. The CI time budget landed the same day
([`spec/suite-ci-time-budget/`](spec/suite-ci-time-budget/)): each era's suite runs as four CI
jobs, every row still runs in one of them, and each job finishes within 10 minutes of its 20-minute
timeout, a budget `AGENTS.md` § Factory holds with its landing baseline. What remains builds the
bespoke tools, makes the shell a capability a deployment chooses, then builds each capability on
the extras mechanism — Slurm first, then LMOD and xdu as the new capabilities that prove it
generalizes — and finally the site extra that bundles them. Ahead of the tool families sit the
executor fixes: the three that `ssh-reconnect-loop` deferred on the SSH connection, the liveness
floor, and a reconnect test whose wall-clock bound measures load as well as behaviour.

## The rename left three identity strings behind

The JWT issuer and audience are still `rcac-mcp`, so every token a deployment has minted keeps
working, and renaming them is a break of its own that needs a window. `serverInfo.version` reports
FastMCP's version rather than this server's. The core member still serves the Purdue favicon, which
waits for a way for a member to register its own routes and icons.

*Horizon: after 0.2.0 · Depends on: the rename (landed names; cleared: landed on `develop` 2026-10-30), capability-extras or site-extras (for the favicon; capability-extras cleared: landed on `develop` 2026-11-01 without member routes) · Refs: `issues/site-extras.md`*
**Seed:** [`issues/rename-leftover-identity-strings.md`](issues/rename-leftover-identity-strings.md) · *status: unshaped*

## The legacy names outlive their window

The rename kept every old name working through a deprecation window: the `rcac-mcp` command and its
compat distribution, the `RCAC_SSH_HOST`, `RCAC_USER_MAP` and `RCAC_INSTRUCTIONS_BUDGET` variables,
and the `rcac://` resource URIs. The README states the window, deprecated in 0.2.0 and removed no
earlier than 0.4.0, and the command and each variable warn with it; the aliases do not. Removing
them breaks every client config that still names one, so it ships in a release whose notes say so,
and the window's own tests and README section go with it.

*Horizon: 0.4.0 at the earliest · Depends on: release 0.2.0 (the window opens there) · Refs: [`spec/rename-to-cluster-mcp/`](spec/rename-to-cluster-mcp/) (GOAL non-goals); `core/deprecation.py`*
**Seed:** [`issues/remove-legacy-names.md`](issues/remove-legacy-names.md) · *status: unshaped*

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

*Horizon: later · Depends on: timeout-process-cleanup (cleared: landed on `develop` 2026-11-04) · Refs: `AGENTS.md` § Invariants §3; [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) PLAN §5*
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

*Horizon: later · Depends on: ssh-half-open-link (cleared: landed on `develop` 2026-11-06) · Refs: [`spec/ssh-half-open-link/`](spec/ssh-half-open-link/) PLAN §3 Deviation 3, research 01 §5*
**Seed:** [`issues/ssh-liveness-message-gap.md`](issues/ssh-liveness-message-gap.md) · *status: unshaped*

## A write whose host is lost after staging leaves its staging directory behind

Over `ssh` a write stages its content in a fresh 0700 directory beside the target and removes it
on the same SFTP session. When the host is lost after staging, that session is dead and the
directory stays, holding the user's own content: the write returns `-1002` with the target
untouched, or, if the host is back at once, succeeds and leaves the checksum file. Pre-existing;
found by `ssh-reconnect-loop`'s review, 2026-10-26, which corrected the texts and deferred the
cleanup.

- 2026-11-05: `spec/ssh-half-open-link/` P2: such a write now raises `TransferLost` naming the staging directory left; the cleanup is still this seed's.

*Horizon: later · Depends on: ssh-reconnect-loop (cleared: landed on `develop` 2026-10-27) · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/) REVIEW.md cycle 1; `AGENTS.md` § Invariants §2*
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

*Horizon: later · Depends on: ssh-reconnect-loop (cleared: landed on `develop` 2026-10-27) · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/) PLAN §5*
**Seed:** [`issues/ssh-reconnect-stuck-step.md`](issues/ssh-reconnect-stuck-step.md) · *status: unshaped*

## Nothing pins that a reconnect's abort and release reach every ProxyJump hop

A reconnect attempt that is abandoned or fails closes every ProxyJump hop it made, but the suite
never builds a chain: its fake connection has no gateway, so a change that stops at the first hop
passes. The bound still holds; a hop could be left running unnoticed. Found by
`ssh-reconnect-loop`'s final review, 2026-10-27, as a missing pin.

- 2026-11-05: `spec/ssh-half-open-link/`'s liveness close goes outermost hop first, pinned on a fake chain only; the seed records it.

*Horizon: later · Depends on: ssh-reconnect-loop (cleared: landed on `develop` 2026-10-27) · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/) REVIEW.md cycle 3*
**Seed:** [`issues/ssh-gateway-hops-unpinned.md`](issues/ssh-gateway-hops-unpinned.md) · *status: unshaped*

## A real-time reconnect test fails under full-suite load

The stalled-reconnect test checks the call gives up within its window plus 0.5 s, by wall clock. It
failed once in a full local run and passed alone and on re-run, so it measures load as well as
behaviour. Seen in `resource-reads-without-executor`'s final gate, 2026-10-28.

- 2026-10-29: a second loopback test (`test_startup_output_is_separated[tcsh]`, `EOFError`) failed
  once on CI and passed on re-run; the seed records it.
- 2026-11-02: a third, `test_timeout_stop.py`'s signal-death survival row over an `sh` login shell
  (every-login-shell runs only), failed once locally under load and passed on re-runs; the seed
  records it.
- 2026-11-05: the reconnect row failed once more with "0 reconnect workers ran" in a local full run
  during `spec/ssh-half-open-link/` P2, and passed three times alone; the seed records it.
- 2026-11-05: `test_a_reconnect_worker_that_cannot_start_frees_the_attempt` failed on CI a second time
  (0.3 s against a 0.1 s bound); under the same load it fails as often on `develop` as on
  `spec/ssh-half-open-link/`'s branch; the seed records both rates.

*Horizon: later · Depends on: — · Refs: [`spec/ssh-reconnect-loop/`](spec/ssh-reconnect-loop/); `tests/test_ssh_exec.py`*
**Seed:** [`issues/stalled-reconnect-test-timing.md`](issues/stalled-reconnect-test-timing.md) · *status: unshaped*

## Bespoke tools first, the shell last

The file tools are too thin — `list_directory` costs a round trip per entry, `read_file` has no
offset, and there is no edit, stat, find or grep — so agents fall back to `run_command`, which no
client can reason about from its name. The cycle builds the `file_*` family (`file_list`,
`file_read`, `file_write`, `file_edit`, `file_stat`, a bounded `file_find`, `file_grep`, plus
transfer), gives every tool honest MCP annotations and a response budget, and keeps `run_command`
as the last resort with `shlex`-based guard rails that steer toward the right tool — documented
as a net for mistakes, not a security boundary. A `--profile read-only` registers only the
read-only tools. Aliases versus a clean break for the old names, and names a client can allow-list
by pattern, are open shaping questions.

*Horizon: mid-term · Depends on: capability-extras (the core distribution it lands in; cleared: landed on `develop` 2026-11-01), safe-execution (the argv executor; cleared: landed on `develop` 2026-10-23) · Refs: sets the naming, annotation and budget rules every capability follows; absorbs `list-directory-parsing`*
**Seed:** [`issues/tool-surface.md`](issues/tool-surface.md) · *status: unshaped*

### Absorbed: `list_directory` misreads some entries

`list_directory` parses the column text of `ls -l`, so a name with a newline is split, a symbolic
link's name carries its `-> target`, a name loses its leading spaces, and a device file's
`major, minor` size fails the whole call. Parsing a NUL-terminated form fixes all four.
Pre-existing. Found by `safe-execution`'s planning research, 2026-10-17. The `file_*` family
rewrites `list_directory` as `file_list`, so the parse is fixed once, in the rewrite, rather than
patched in a tool about to be replaced.

*Horizon: with tool-surface · Depends on: — · Refs: absorbed by `tool-surface`; [`spec/safe-execution/`](spec/safe-execution/) research 04 §4, PLAN risk 7*
**Seed:** [`issues/list-directory-parsing.md`](issues/list-directory-parsing.md) · *status: unshaped*

## The shell is a capability a deployment chooses

Every server serves `run_command`, so an operator can't offer the cluster through named tools alone.
Moving it out of the core into a member installed by a `[shell]` extra makes the shell a choice made
at installation, like Slurm or the site's storage. The executor stays in the core, the instructions
stop naming `run_command` when it is absent, and the `rcac-mcp` compatibility distribution pulls
`[shell]` so existing installs serve what they serve today. Absence is a choice of scope, not
containment (`file_write` reaches startup files, job scripts run anything), so the docs name the
combination that does confine: no shell plus `--profile read-only`. It follows `tool-surface`, which
makes a shell-less server useful, and precedes 0.2.0, the one release where the bare default can be
set without breaking anyone. Ruled 2026-11-04: a bare install serves no shell, and the docs present
`[shell]` as the obvious opt-in for a user running their own server.

*Horizon: with or right after tool-surface, before 0.2.0 · Depends on: tool-surface (the `file_*` family and profiles), capability-extras (the member mechanism; cleared: landed on `develop` 2026-11-01) · Refs: Part II (hosted `delegate` mode); `issues/site-extras.md`*
**Seed:** [`issues/shell-extra.md`](issues/shell-extra.md) · *status: unshaped*

## A job_* family that accepts what a model naturally sends

Found while submitting and watching test jobs through the server: `gpus` must be a string, a single
job id must be wrapped in a list, a purged id is an error rather than an empty result, and five
tools answer "tell me about this job". The `job_*` family — `job_submit` with `args`, `modules` and
typed resources accepting an int or a string, `job_list` and `job_history` accepting a scalar or a
list, a consolidated `job_info`, `job_output`, `job_cancel`, and a bounded `job_wait` considered —
lands in the Slurm capability distribution, with validation errors that say what to send.

*Horizon: mid-term · Depends on: capability-extras (cleared: landed on `develop` 2026-11-01), tool-surface, safe-execution (cleared: landed on `develop` 2026-10-23) · Refs: rebuilds the Slurm member, an extra since capability-extras*
**Seed:** [`issues/slurm-capability.md`](issues/slurm-capability.md) · *status: unshaped*

## Module systems are the other half of "can I run this"

Every tool here is about jobs; none is about software. On an LMOD cluster an agent cannot discover
what is installed, what versions exist, or what a module load would do to the environment — so it
guesses, and `INSTRUCTIONS.md` has to compensate with prose. `module avail`, `module spider`,
`module list` and `module show` are the missing capability group, and they are the first capability
written for the extras mechanism rather than moved onto it, which is what proves the mechanism
generalizes past the members it was shaped around. Module state does not persist between calls, so
a `modules=[…]` parameter on `run_command` and job submission is part of the idea.

*Horizon: mid-term · Depends on: capability-extras (strictly; cleared: landed on `develop` 2026-11-01), tool-surface (`run_command`'s parameters) · Refs: `slurm-capability` takes the same `modules=[…]`*
**Seed:** [`issues/lmod-tool-group.md`](issues/lmod-tool-group.md) · *status: unshaped*

## Answer storage questions from an index, not a walk

"What's filling my scratch" and "find every `*.h5` here" end today in a recursive `find` or `du` on
a parallel filesystem — the long metadata walk login-node rules forbid. The xdu capability detects
[xdu](https://github.com/xdu-project/xdu), installs a pinned, checksum-verified release into a
private prefix under `~/.local` only with explicit consent, keeps indexes in scratch rather than
home, indexes large trees through the scheduler and small ones at low priority, and serves
`storage_spaces`, `storage_index`, `file_find` routed to the index, and `storage_usage` — typed
operations only, never caller-written SQL. Byte-sum rollups are an upstream request to xdu.

*Horizon: mid-term · Depends on: capability-extras (cleared: landed on `develop` 2026-11-01), tool-surface (`file_find`), slurm-capability (indexing jobs) · Refs: the second capability written for the extras mechanism*
**Seed:** [`issues/xdu-storage.md`](issues/xdu-storage.md) · *status: unshaped*

## A site extra is shorthand plus a point of view

`cluster-mcp[rcac]` should mean "the right capability extras for Purdue, plus Purdue's own tools and
context" — one install target a user can name without knowing that Gautschi runs Slurm and LMOD.
That makes it both a dependency alias and the home for the `cluster-mcp-rcac` member: Purdue's tools
and the Purdue part of the instructions. Getting the boundary right here is what makes
`cluster-mcp[alcf]`, `[ncsa]` and `[tacc]` a matter of contribution rather than redesign, so this
cycle should produce a documented pattern, not just a Purdue special case. It absorbs storage
discovery, whose site implementation needs exactly the hook this cycle establishes.

*Horizon: mid-term · Depends on: capability-extras (strictly; cleared: landed on `develop` 2026-11-01); lmod-tool-group and xdu-storage (the extra pulls them in) · Refs: absorbs `generalize-storage-discovery`; sets the pattern other centers copy*
**Seed:** [`issues/site-extras.md`](issues/site-extras.md) · *status: unshaped*

### Absorbed: not every cluster has a Lustre scratch and a myquota

`storage_paths()` parses the output of `myquota`, and scratch discovery shells out to `findscratch` —
both Purdue commands, and neither degrades on a cluster that lacks them. Since `capability-probe`
the RCAC member is withheld on such a cluster in `ssh` and `local` modes, but `delegate` mode,
`--skip-probes` and a probe that gives no answer still serve it there. The `rcac://storage`
resource is built on the same assumption. Generalizing means a discovery protocol with a site-provided
implementation and an honest "unknown" rather than a parse failure — and the site hook is what
`site-extras` builds. Found by the harness port, 2026-08-26.

*Horizon: with site-extras · Depends on: — · Refs: absorbed by `site-extras`; the helper seam it needs, the undecorated `resolve_storage_paths()`, exists (`resource-reads-without-executor`, landed on `develop` 2026-10-29)*
**Seed:** [`issues/generalize-storage-discovery.md`](issues/generalize-storage-discovery.md) · *status: unshaped*

**Release 0.2.0.** The new names, the capability extras and the new tool families reach `main`
together. Legacy `RCAC_*` variables and `rcac://` URIs keep working through the deprecation window;
the distribution names and the repository's home are settled before it ships.

---

# Part II — Hosted

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

*Horizon: after 0.2.0 · Depends on: release 0.2.0, stack-upgrade (the HTTP transport; cleared: landed on `develop` 2026-10-17), safe-execution (cleared: landed on `develop` 2026-10-23) · Refs: adds a mode to the execution-mode ladder (`AGENTS.md` § Invariants §4)*
**Seed:** [`issues/https-token-mode.md`](issues/https-token-mode.md) · *status: unshaped*

---

# Part III — Infrastructure

## The surface pin cannot follow a deliberate surface change

`tests/fixtures/served_surface.json` is the surface `3d010ec` served, taken on FastMCP 2, and
`tests/test_surface.py` rejects a fixture re-taken on FastMCP 4 because it carries the new stack's
schema metadata. After a deliberate change to a tool, an argument or the instructions there is no
FastMCP 2 build of the new surface to snapshot, so the only way to update the pin is to hand-edit
it, unchecked. A maintained snapshot command on the current stack, with a one-time re-baseline that
retires the tolerated-difference list, settles it. Found by `stack-upgrade` P3, 2026-10-17.

*Horizon: before the next cycle that changes the served surface · Depends on: — · Refs: `AGENTS.md` § Invariants §9 says the question is open; `safe-execution` changed the surface first and hand-edited its deltas into the fixture (`AGENTS.md` § Testing); next needed by `tool-surface` or `agents-d-instructions`, whichever lands first*
**Seed:** [`issues/surface-fixture-after-a-surface-change.md`](issues/surface-fixture-after-a-surface-change.md) · *status: unshaped*

## Nothing would catch the next silently wrong annotation

`auth.py`'s `AUTH_MODES` carried a slice inside its annotation's subscript for months:
`typing.get_type_hints` and eager evaluation both accepted it, in a high-blast-radius module, and it
was fixed only because `stack-upgrade` happened to rewrite the file (R7). Nothing in the suite or
the gate checks any other annotation. A gate step or standing test that type-checks every member's
`src/`, or at least rejects an annotation under `cluster_mcp` that resolves to a non-type, closes
it; the tool is the plan's call. Found by `stack-upgrade`'s GOAL non-goals, carried at retirement,
2026-10-17.

*Horizon: later · Depends on: — · Refs: runs where the gate runs, so CI picks it up through its mirror of the gate (`ci-workflow`; cleared: landed on `develop` 2026-10-18); [`spec/stack-upgrade/`](spec/stack-upgrade/) pins the one annotation*
**Seed:** [`issues/annotation-check.md`](issues/annotation-check.md) · *status: unshaped*

## A startup file's background job can delay a result, or reach it over SSH

Startup output never reaches a result, but a background process a startup file leaves running holds
the call open until it exits or the timeout, and over SSH a job the remote login shell's own rc file
starts can write into the channel after the sentinel. Neither is separable without a PTY or a
server-owned session. Found by `safe-execution`'s focused review, 2026-10-17.

- 2026-10-18: the first case is fixed in `safe-execution` (a bounded grace once the command has
  exited, in all three modes); the SSH rc-file case remains, stated as the documented exception.
- 2026-10-18 (review cycle 2): the first case now stops once nothing has arrived for the grace,
  not a fixed grace after the exit, and the result carries a note saying so.
- 2026-10-22: the first case has no timing rule any more: the call returns at the command's end
  records on both streams; the SSH rc-file case remains for what such a job writes before them.

It stays here because no release waits on it: neither case shows with the clusters' default
startup files (`safe-execution` research 01), and the fix is a different launch (a PTY, or a
session the server owns), larger than a small cycle.

*Horizon: later · Depends on: safe-execution (cleared: landed on `develop` 2026-10-23) · Refs: [`spec/safe-execution/`](spec/safe-execution/) PLAN §2.2a, risk 5*
**Seed:** [`issues/startup-background-jobs.md`](issues/startup-background-jobs.md) · *status: unshaped*

## One very large site file can cost every site rule

The startup read takes each `/etc/agents.d/*.md` file whole, with no size limit, inside one 10 s
bound. A file of tens of megabytes can push the `ssh` read past it, and then no site rule is served
at all; when the read finishes, `cluster_context` returns the whole file. A per-file limit that
leaves an oversize file out and names it, as the budget does, fixes it. Found by
`agents-d-instructions`' planning, 2026-10-19.

It stays here because the convention's files are a few kilobytes, so it takes a mistake in the
directory to show.

*Horizon: later · Depends on: agents-d-instructions (the startup read it bounds) · Refs: [`spec/agents-d-instructions/`](spec/agents-d-instructions/) PLAN § 5; `AGENTS.md` § Invariants §8*
**Seed:** [`issues/site-file-size-cap.md`](issues/site-file-size-cap.md) · *status: unshaped*

## Every start asks the package index for FastMCP's latest version

FastMCP's banner, on by default, checks PyPI for a newer FastMCP at every start (cached for 12
hours) unless `FASTMCP_CHECK_FOR_UPDATES=off`, so the server makes an outbound request nobody asked
for and can advise upgrading a dependency `uv.lock` pins. Turning the check off (or the banner) at
startup fixes it. Pre-existing. Noted by `agents-d-instructions`' planning, 2026-10-19.

It stays here because no release waits on it: the request is bounded at 2 s and fails silently.

*Horizon: later · Depends on: — · Refs: [`spec/agents-d-instructions/`](spec/agents-d-instructions/) PLAN § 5*
**Seed:** [`issues/fastmcp-update-check.md`](issues/fastmcp-update-check.md) · *status: unshaped*

## The `integration` marker says it drives the CLI, and not every integration test does

`pyproject.toml` describes `integration` as "drives the installed CLI", but `test_docs_modules_absent`
and the git-backed absence-message controls in `tests/test_registry.py` are `integration` only
because they start git, which the unit guard forbids in a `unit` test. In practice the marker means
"not `unit`"; its description states a narrower rule, and `AGENTS.md` § Testing notes the mismatch
instead of fixing it. Rewording both markers to the line the unit guard draws settles it. Found by
the `absence-check-leftover-classification` plan, 2026-10-19.

*Horizon: later · Depends on: — · Refs: [`spec/absence-check-leftover-classification/`](spec/absence-check-leftover-classification/) (PLAN §5)*
**Seed:** [`issues/integration-marker-wording.md`](issues/integration-marker-wording.md) · *status: unshaped*

## The static skip check admits a skip it should catch

`test_only_need_shell_skips` keeps a test from skipping on CI unseen, but it admits a skip inside an
allowed helper that is nested or redefined in conftest, inside any module whose name ends in
`conftest.py`, and a skip called as `pytest.skip.__call__`. None exists today; any would let a row
vanish from CI without failing. Found by the landing-merge check of
`absence-check-leftover-classification`, 2026-10-23.

*Horizon: later · Depends on: — · Refs: [`spec/absence-check-leftover-classification/`](spec/absence-check-leftover-classification/) (REVIEW, landing merge)*
**Seed:** [`issues/skip-check-fence-gaps.md`](issues/skip-check-fence-gaps.md) · *status: unshaped*

## A version the lock lifts never reaches a user who installs from git

`uv.lock` pins what `uv sync` installs (development, CI). A `git+…` or `uvx --from` install, and the
container image's `uv pip install`, resolve fresh within the declared ranges and never read it, so a
fix that only lifts a locked version changes what the tests run and nothing a user receives. Where
the newer version matters, the declared requirement needs a floor. Pre-existing. Found by
`capability-extras` P4, whose install probe resolved a newer dependency than the lock pins,
2026-10-31.

It stays here because no release waits on it.

*Horizon: later · Depends on: — · Refs: [`spec/capability-extras/`](spec/capability-extras/) (TECH P4, PLAN §5); `AGENTS.md` § Packaging*
**Seed:** [`issues/unlocked-install-floors.md`](issues/unlocked-install-floors.md) · *status: unshaped*

## A retried capability load after a failure registers nothing and blames the wrong distribution

A failed load cuts the tool registry back but leaves the imported tools modules cached, so a second
load in the same process registers nothing for a capability that had loaded cleanly, and the error
names it instead of the broken one. The command line never retries, so only a library caller sees it.

*Horizon: later · Depends on: capability-extras (cleared: landed on `develop` 2026-11-01) · Refs: [`spec/capability-extras/`](spec/capability-extras/) (REVIEW, cycle 1)*
**Seed:** [`issues/capability-reload-after-failure.md`](issues/capability-reload-after-failure.md) · *status: unshaped*

## The on-demand mutation run no longer fits its 30-minute job

`.github/workflows/mutants.yml` runs every mutation case serially in one 30-minute job. At about 660
cases and 2.5–5 s each, it reaches the timeout and is cancelled before it reports, and § Testing's
"all cases about 3 minutes" is stale. `capability-probe` adds 271 cases (931 in all). Pre-existing; it gates
nothing, so no release waits on it.

- 2026-11-02: `timeout-process-cleanup` adds 101 more (1,032 in all), about 11 minutes per era.

*Horizon: later · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (research 03 §5, PLAN §6)*
**Seed:** [`issues/mutants-workflow-timeout.md`](issues/mutants-workflow-timeout.md) · *status: unshaped*

## A mutant's child run outlives its timeout

`tests/mutants.py` runs each case's targets through `subprocess.run(timeout=300)`, which kills the
sandbox wrapper and not the pytest below it: a case whose target hangs leaves that pytest running,
reparented to init, and the runner raises out of the sweep instead of reporting the case. Seen on
2026-11-05. Pre-existing; it gates nothing. The fix starts the child in a session of its own and
kills its process group.

*Horizon: later · Depends on: — · Refs: `tests/mutants.py` (`run_child`); [`spec/ssh-half-open-link/`](spec/ssh-half-open-link/)*
**Seed:** [`issues/mutant-child-outlives-timeout.md`](issues/mutant-child-outlives-timeout.md) · *status: unshaped*

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

*Horizon: later · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (PLAN §5, REVIEW); `AGENTS.md` § Invariants §2, §3*
**Seed:** [`issues/local-command-outlives-server.md`](issues/local-command-outlives-server.md) · *status: unshaped*

## A connection reset while a call opens its channel escapes as a raw exception

In `ssh` mode a call opens its channel before the guard that turns a lost connection into a result,
so a link that resets just then raises Paramiko's `ConnectionResetError` out of `SSHExecutor.run`
instead of reporting that the command was not run. Seen once against a test server that dropped the
connection, 2026-11-02. Pre-existing; the SFTP paths were not checked.

- 2026-11-05: `spec/ssh-half-open-link/` now reconnects a channel or SFTP-session open that a lost connection cut short; a reset at that instant is still unpinned; the seed records it.

*Horizon: later · Depends on: — · Refs: [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) (TECH P2 remediation); `core/executor/ssh.py` (`_exec`)*
**Seed:** [`issues/ssh-open-session-reset-raises.md`](issues/ssh-open-session-reset-raises.md) · *status: unshaped*

## A profile's sub-second `TMOUT` may drop the functions a script inherits

A `run_command` script inherits the login's functions through a `read` loop, and a profile's `TMOUT`
bounds that `read`. bash 4 and later accept a fractional `TMOUT`, so a sub-second one could end the
loop before `module` is exported. Read from bash's source, not measured (the development host has
bash 3.2 only). Pre-existing.

*Horizon: later · Depends on: — · Refs: [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) (TECH P1 remediation, F1); `core/executor/launch.py` (`SCRIPT`); `AGENTS.md` § Invariants §2*
**Seed:** [`issues/script-function-export-tmout.md`](issues/script-function-export-tmout.md) · *status: unshaped*

## The image's init is pinned by its recipe, not by what it reaps

The shipped image runs `tini` as PID 1 so the orphaned watchdog of each completed `local` call is
reaped, but only a text check of the `Dockerfile` pins it. A CI job that builds the image and counts
zombies after many calls would pin the behaviour. Not measured (no container runtime on the
development host).

*Horizon: later · Depends on: — · Refs: [`spec/timeout-process-cleanup/`](spec/timeout-process-cleanup/) (REVIEW cycle 3, B6); `Dockerfile`; `tests/test_packaging.py`*
**Seed:** [`issues/image-init-reaping.md`](issues/image-init-reaping.md) · *status: unshaped*

## A sandbox killed with SIGKILL leaves its directory behind

`bin/sandbox.sh` removes its throwaway HOME from a trap, which SIGKILL never runs, and several test
harnesses stop a sandbox's process group with SIGKILL. Each such stop leaves a bare
`cluster-mcp-sandbox.*` directory in the host's `TMPDIR`: about 60 per full-suite era, many more
per mutation sweep, and 18,061 on one developer Mac. Pre-existing; `capability-probe`'s own drives
add one or two per run, through the shared SSH test server. It gates nothing.

*Horizon: later · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (TECH P3); `bin/sandbox.sh`; `tests/ssh_server.py`*
**Seed:** [`issues/sandbox-dirs-left-on-kill.md`](issues/sandbox-dirs-left-on-kill.md) · *status: unshaped*

## A capability's registered tool objects can run its code when they are read

The load takes each tool a capability registers by `isinstance(entry, FunctionTool)`, so a subclass, or
a field the capability sets after construction to a value of a type of its own, runs the capability's
code whenever the core or FastMCP reads it: at the load's scratch registration, again when the server
is built, and on every listing. The capability record itself is exact since `capability-probe`; its tools are the one part
still taken by `isinstance`. The outcome: every tool exactly a `FunctionTool` with exact field values,
decided at load, the handler excepted. Pre-existing; no code changes until its cycle.

*Horizon: later · Depends on: — · Refs: [`spec/capability-probe/`](spec/capability-probe/) (REVIEW, cycle 2 rulings); `AGENTS.md` § Invariants §7; `core/capabilities.py`*
**Seed:** [`issues/capability-tool-objects-inert.md`](issues/capability-tool-objects-inert.md) · *status: unshaped*

## A disk-image step that hangs outlives its test

On macOS the full-filesystem write test builds a real 4 MB volume with `hdiutil`. Its fixture waits
120 s for each step and, at the timeout, fails the test without stopping the step: one stalled
`hdiutil create` and its formatter stayed with a half-made device for about a day on a developer
Mac. Pre-existing; macOS only, since the CI runner never calls `hdiutil`. It gates nothing.

*Horizon: later · Depends on: — · Refs: `tests/test_ssh_exec.py` (`_host`, `full_volume`); [`spec/safe-execution/`](spec/safe-execution/)*
**Seed:** [`issues/full-volume-fixture-leaks-hdiutil.md`](issues/full-volume-fixture-leaks-hdiutil.md) · *status: unshaped*

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

---

# A note on security work

This server executes arbitrary shell commands, and in `delegate` mode it does so **as other people**,
from a privileged process, on shared research infrastructure. Deferrals that describe an
*unremediated* weakness — a live path to running a command as the wrong user, on the wrong host, or
without the intended authentication — do **not** appear in this file. They go to `.security/issues/`
and `.security/ROADMAP.md`, which are gitignored: a public, ordered index of live vulnerabilities is
an attacker's work plan. The *fixes* land as ordinary public commits and PRs when they ship.

`context-cache-cross-user` above is in the public lane deliberately, and the judgement is worth
recording: the cached content is world-readable administrative markdown that every user could read
anyway, so there is no exploitable disclosure to conceal — only a caching bug whose *shape* is
cross-user. Had it cached anything user-private, it would have gone to the hidden lane instead. When
in doubt, use `.security/` and ask.
