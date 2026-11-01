# GOAL — Probe the cluster before advertising an installed capability

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** capability-probe
- **kind:** feature
- **appetite:** big

## Problem

After `capability-extras`, installation is the only switch. Every capability distribution that is
installed registers its tools, its resources and its part of the served instructions, whatever the
cluster behind the server has. One install that serves several clusters — the primary deployment,
a user's own machine with one client config per cluster — advertises the Slurm member's seven tools
on a cluster with no Slurm, and the RCAC member's ten tools and its storage resources on a cluster
that is not Purdue's. The model is invited to compose a workflow that cannot run, which is the
failure `capability-extras` fixed for capabilities that are not installed. **Pre-existing:** n/a —
new work, deferred from `capability-extras` (its GOAL, Q2).

Startup today, in the order a probe has to fit into:

- `run()` loads every installed capability first, before the mode ladder
  (`packages/cluster-mcp/src/cluster_mcp/core/__init__.py:189-190`, calling `installed()`,
  `core/capabilities.py:341`); a capability that cannot load stops startup there (§ Invariants §4).
  The load runs no remote command: it only imports and checks.
- The ladder resolves the mode (`__init__.py:193`). In `ssh` and `local` modes one shared executor is
  built (`__init__.py:206-209`), and `SSHExecutor`'s constructor connects at once
  (`core/executor/ssh.py:697-698`), so in `ssh` mode the remote link exists before anything is
  served. In `delegate` mode no executor exists at startup: `AuthExecutorMiddleware` builds a
  `DelegatingExecutor` per request from the token's identity (`__init__.py:200-204`,
  `core/middleware.py:206-207`), and it hooks only tool calls and resource reads
  (`middleware.py:214`, `:224`), so every user is served the same tool list.
- The site context is then read once, bounded: over the shared executor in `ssh` mode, in this
  process in `local` and `delegate` modes, and in `delegate` mode as the server, keeping only what
  every account can read (`__init__.py:216`, `:278-286`). The bound is `READ_TIMEOUT`, 10 s
  (`core/site.py:68`), enforced by `read_bounded` (`site.py:581`); a read past it is abandoned and the
  server starts without site rules. This is the one remote round trip on the startup path today.
- `create_mcp_server` composes the instructions once per process from the capabilities it is given,
  or every installed one when given none (`core/server.py:112`, `:128-131`; the base is the core's
  text and then each capability's, `server.py:69-76`), and `run()` gives it none
  (`__init__.py:217`). Nothing re-composes them for the life of the process.

So a probe has three costs the seed names and this GOAL has to bound. In `ssh` mode it is a second
remote round trip between launch and the first answer a stdio client gets, and something has to say
what a slow or failed one means. In `local` mode it is a lookup on this host, with different failure
modes. In `delegate` mode there is no user to probe as at startup, and a per-user answer cannot
reach instructions composed once per process.

## Outcome / vision

On a cluster that lacks what an installed capability needs, that capability is served as if it were
not installed: none of its tools, none of its resources, none of its instructions text. The
operator sees one line saying which capability was withheld and why. The probe's cost at startup
has a stated bound, a probe that cannot answer has a documented outcome, and every execution mode
has a specified behaviour. On a cluster that has everything installed, nothing a client sees
changes.

## Acceptance criteria (the contract)

Each requirement that leans on a clarification names it, with the ruled answer in parentheses.

- **R1** — WHERE an installed capability's probe reports that the cluster lacks what the capability
  needs, the server SHALL register none of its tools and none of its resources, the served
  instructions SHALL carry none of its text, and the server SHALL log one line on stderr naming the
  capability's distribution and what the probe found missing.
- **R2** — A capability distribution SHALL be able to declare a probe in what its entry point names
  (§ Invariants §7), with no edit to any core module. The Slurm and RCAC members SHALL each declare
  one, and tests SHALL drive each against an executor that reports what it needs as present and as
  absent, with no cluster. A capability that declares no probe SHALL be treated as Q1 rules
  (served whenever it is installed, as today).
- **R3** — WHERE every installed capability's probe reports present, the served surface SHALL be
  unchanged: `test_served_surface_matches_baseline` passes with no fixture edit. Under any set the
  probes withhold, the served instructions SHALL name exactly the tools served, verified by a test
  that cross-checks the two with at least one capability withheld.
- **R4** — WHEN the server starts in `ssh` or `local` mode (Q3: `local`
  probes), it SHALL run each declared probe once, through the shared executor the tools use, after
  that executor exists and before it answers any request, and SHALL NOT probe again for the life of
  the process.
- **R5** — The probes SHALL together add no more than a documented bound to startup, whatever the
  number of installed capabilities (Q5: one fixed figure, no more
  than the site read's 10 s). WHERE no installed capability declares a probe, the server SHALL run no
  probe command.
- **R6** — IF a probe does not give a definite answer — it has not finished within the bound, its
  command could not run, or the connection was lost — THEN the server SHALL treat the capability as
  Q2 rules (serve it, as if the probe reported present), SHALL log one line on stderr
  naming the capability's distribution and why, and SHALL keep starting.
- **R7** — WHILE the server runs in `delegate` mode, it SHALL behave as Q3 rules (run no
  probe, serve every installed capability, and log one line on stderr saying probing is skipped in
  that mode), and every user SHALL be served the same tools and instructions.
- **R8** — WHERE the operator override Q4 rules on is set (one process-wide switch, a
  flag and an environment variable under § Configuration's conventions), the server SHALL run no
  probe and SHALL serve every installed capability.
- **R9** — The existing startup refusals SHALL be unchanged and SHALL precede any probe: a
  capability that cannot load stops startup before the ladder, and a failed SSH connect is answered
  as § Invariants §4 describes, with no probe run. `--help`, `--version` and `--generate-token` SHALL
  run no probe.
- **R10** — In the same commit that lands the probe, `AGENTS.md` § Invariants §4 (startup order),
  §7 (the capability record and its probe) and §9 (what the base is composed from), and
  § Configuration if Q4 adds a setting, SHALL describe it, and `README.md` SHALL say that an
  installed capability is served only where the cluster has what it needs, and how to tell when one
  was withheld.

## Non-goals (no-gos)

- **Per-user probing or per-user tool lists in `delegate` mode.** Instructions are composed once per
  process and the tool list is the same for every user (`middleware.py:214`, `:224`). Not planned:
  ruled out here (Q3).
- **Probing again during the process**, or changing the tool list after startup (a
  `tools/list_changed` notification). Not planned: the answer is fixed at startup (R4).
- **Caching a probe result across restarts.** Not planned: ruled out here (Q6).
- **Withholding individual tools of a capability.** A probe answers for its whole capability; a
  capability that needs finer grain splits into two distributions. Not planned.
- **Cross-capability dependencies** (withholding the RCAC member because the Slurm member was
  withheld). Each probe answers for its own capability. Not planned.
- **A per-capability force-on or force-off switch.** At most the one process-wide override of Q4.
  Not planned.
- **Probing the core.** The core's tools and resources are always served.
- **Probes for capabilities that do not exist yet**: the LMOD group (`lmod-tool-group`), the xdu
  group (`xdu-storage`), the `job_*` family (`slurm-capability`) and a site extra's members
  (`site-extras`) each declare their own probe in their own cycle, against the contract R2 lands.
- **What an advertised tool does when its command is missing at call time** (the LMOD seed's own R5).
  That stays each capability's concern: a probe that answered "present", or could not answer (R6),
  does not change a tool's call-time errors.
- **Changing the mode ladder, the delegate executor or the site read** (§ Invariants §4, §5, §8).
  The probe fits around them.

## Clarifications

Ruled by the foreman, as judge under the effort's autonomy decision, on 2026-11-01, each as the
shaping proposed; the trade-offs stay as the record. Reported to Geoffrey the same day.

- **Q1:** Must every capability declare a probe? — **Ruled:** no. A probe is optional; a
  capability that declares none is served whenever it is installed, as today, and the Slurm and RCAC
  members declare one each (R2). What a probe declares — a command to look up, a script, a callable
  over the executor — is the plan's design. *Trade-off:* a capability written without a probe keeps
  today's over-advertising. A mandatory probe would change the capability record `capability-extras`
  just landed for every capability written against it, and force one on a capability that needs
  nothing from the cluster.
- **Q2:** What does a probe that times out or errors mean: advertise, withhold, or refuse to start?
  — **Ruled:** advertise (fail open), with one stderr line naming the capability and why (R6).
  *Trade-off:* on a cluster that really lacks the capability, a probe that also times out leaves
  today's over-advertising. Withholding would hide working tools for the whole session on a slow
  login node, with no recovery short of a restart, since the instructions are composed once.
  Refusing to start would turn a slow login node into an outage, and a probe failure is not a broken
  install (unlike § Invariants §4's load refusal).
- **Q3:** What do `local` and `delegate` modes do? — **Ruled:** `local` probes, through its
  shared executor, as `ssh` does: it runs as the same owner on the same host its tools run on, so the
  answer is exact and costs no round trip. `delegate` runs no probe and serves every installed
  capability, with one stderr line saying so (R7). A `delegate` install lives on the one host it
  serves, so installation is already the per-cluster switch there; the seed's motivating case, one
  install serving several clusters, is `ssh` mode. *Trade-off:* a `delegate` host with a capability
  installed but nothing behind it over-advertises, as today. The alternative — probing once at
  startup as the server process, as the site read does (`__init__.py:285-286`) — runs capability
  code's commands at startup in a process that runs privileged (§ Invariants §4, §5, a human gate),
  in the server's own environment rather than a mapped user's, so its answer can differ from what a
  user's login shell finds, and it is wrong for every user at once when it does.
- **Q4:** Is there an operator override? — **Ruled:** yes, one process-wide switch that skips
  every probe and serves every installed capability (R8): a flag and a `CLUSTER_MCP_`-prefixed
  variable, read through `env_setting` like the others in § Configuration. *Trade-off:* it adds a
  setting. Without it, a probe that answers "absent" wrongly — a command that appears only after a
  step the probe's shell does not take — has no remedy but patching the code: installation, the only
  other switch (`capability-extras`, its Q3), cannot turn a withheld capability back on.
  Per-capability switches stay a non-goal.
- **Q5:** What is the startup bound? — **Ruled:** one fixed figure for all probes together, no
  more than the site read's `READ_TIMEOUT` (10 s, `site.py:68`), stated in `AGENTS.md`; not
  configurable. Whether the probes overlap the site read is the plan's. *Trade-off:* a short bound
  makes fail-open (Q2) common on a loaded login node, which is today's behaviour; a long one delays
  every stdio start, and a client waits for the first answer through connect, site read and probes.
  Making it configurable adds a setting for a number few operators would change.
- **Q6:** Is a probe result cached across restarts? — **Ruled:** no; every start probes afresh
  (Non-goals). *Trade-off:* the bounded cost is paid on every start, and a stdio server starts once
  per client session. A cache would add on-disk state keyed by host and capability, a staleness rule,
  and a file to secure, and a stale "absent" would hide tools the cluster has gained.

## Related materials

- Seed: [`issues/capability-probe.md`](../../issues/capability-probe.md)
- ROADMAP: Part I, "An installed capability with nothing behind it still advertises its tools"
- Prior cycle: [`spec/capability-extras/`](../capability-extras/) (the mechanism this extends; GOAL
  Q2 defers the probe here, Q3 makes installation the only switch, Q5 the startup refusal path)
- Downstream seeds that will declare probes:
  [`issues/slurm-capability.md`](../../issues/slurm-capability.md),
  [`issues/lmod-tool-group.md`](../../issues/lmod-tool-group.md) (`module` is a shell function, so its
  probe cannot be a plain command lookup),
  [`issues/site-extras.md`](../../issues/site-extras.md),
  [`issues/xdu-storage.md`](../../issues/xdu-storage.md)
- `AGENTS.md` § Project (the primary deployment), § Configuration, § Invariants §4, §5, §7, §8, §9
- Source: `packages/cluster-mcp/src/cluster_mcp/core/__init__.py` (`run`, `_read_site`,
  `_create_executor`), `core/capabilities.py` (`Capability`, `installed`), `core/server.py`
  (`create_mcp_server`, `base_instructions`), `core/site.py` (`read_bounded`, `READ_TIMEOUT`),
  `core/middleware.py` (`AuthExecutorMiddleware`), `core/executor/ssh.py` (`SSHExecutor`)
- Tests: `tests/test_surface.py`, `tests/test_instructions.py`, `tests/test_capabilities.py`,
  `tests/test_startup.py`
