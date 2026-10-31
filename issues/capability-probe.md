---
status: unshaped
kind: feature
appetite: big
lane: public
---

# Probe the cluster before advertising an installed capability

## Problem

After `capability-extras`, installation is the only switch: a capability distribution that is
installed registers its tools and names them in the served instructions, whether or not the cluster
behind the server has what they need. One install that serves several clusters — a user's own
machine with one client config per cluster, say — advertises the Slurm tools on a cluster with no
Slurm, and the RCAC tools on a cluster that is not Purdue's. The model is invited to compose a
workflow that cannot run, which is the same failure `capability-extras` fixes for capabilities that
are not installed.

A runtime probe — asking the cluster whether, say, `sinfo` exists — would let an installed
capability with nothing behind it advertise nothing.

## Why it was deferred

Ruled out of `capability-extras` at its GOAL gate (2026-10-31), so that cycle could land the
registration mechanism without a remote dependency on its startup path. A probe is not cheap, and
each cost needs its own design:

- **A remote round trip at startup.** The `ssh` executor connects eagerly, and the served
  instructions are composed once at startup, so a probe there puts one or more remote commands
  between launch and the first answer a client gets, and has to decide what a slow or failed probe
  means.
- **`local` mode** runs on the cluster itself, so a probe there is a local lookup with different
  failure modes from the same probe over SSH.
- **`delegate` mode over HTTP** serves many users from a shared host with a per-request executor.
  At startup there is no user to probe as, and a per-user answer conflicts with instructions
  composed once per process.

**Pre-existing:** n/a — new work.

## Outcome / vision

An installed capability whose prerequisites the cluster lacks registers no tools and is not named
in the served instructions, in every execution mode, with a cost at startup that is bounded and
stated.

## Sketch of the acceptance criteria

- **R1** — WHERE a capability is installed but its probe reports the cluster lacks it, the server
  SHALL register none of its tools and SHALL name none of them in the served instructions.
- **R2** — The probe's cost on the startup path SHALL be bounded, and IF a probe cannot complete,
  THEN the server SHALL behave in a documented way, never by silently guessing.
- **R3** — The behaviour in `local` and `delegate` modes SHALL be specified, including what is
  probed when there is no user at startup.

## Notes

- Related: [`spec/capability-extras/`](../spec/capability-extras/) (the mechanism a probe extends;
  its GOAL records the deferral as Q2), [`site-extras.md`](site-extras.md) (a site extra's members
  are the other natural probe target).
- Found by: `capability-extras` shaping, 2026-10-31.
