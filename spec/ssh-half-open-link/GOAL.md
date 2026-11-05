# GOAL — A dead SSH link that still reads as connected is noticed within a bound

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** ssh-half-open-link
- **kind:** fix
- **appetite:** small

## Problem

In `ssh` mode, the default, the server keeps one connection to the cluster for its whole life.
`ssh-reconnect-loop` bounded what happens once that connection is *noticed* as lost. A link that
dies silently is never noticed: no reset arrives, so the connection still reads as connected. That
happens when a NAT entry expires, a laptop sleeps through a network change, or a login node is
powered off mid-session. Every call then goes out on a dead link:

- **File transfers** (`write_file`, `upload_file`, `download_file`, and `sbatch` with
  `script_content`, which write over SFTP) wait about an hour, in effect for ever, on a channel open
  and on replies that never come.
- **Commands** (`run_command`, the Slurm tools) wait about 30 s for a channel and then fail with an
  error that names neither the host nor the cause, unlike a failed reconnect. Every later call pays
  the same, until the kernel gives up on the socket (on the order of 15 minutes on Linux).
- **A command already running** as the link dies, called with no timeout (the default for
  `run_command` and `sbatch`), waits without limit.
- **One stalled write** can hold the connection's write path and stall a concurrent call.

The agent sees calls that hang or fail obscurely, and nothing tells it or its user that the cluster
is unreachable, not slow. A laptop that comes back on a new network stays stuck on the dead link,
when a fresh connection would work.

**Confirmed on `develop` (`13c0e83`), 2026-11-04,** at the seed's anchors:
- `SSHExecutor._ensure_connected` (`core/executor/ssh.py:878`) reuses any connection whose
  `is_connected` is true (`:743`);
- the SFTP tools open their client with `transport.open_sftp_client()`, with no timeout
  (`:1068`, `:1155`, `:1183`);
- `OPEN_TIMEOUT` is 30 s (`:92`);
- `_collect` takes `timeout=None` (`:240`).

The seed's offline probe, against Paramiko 5.0.0 and Fabric 3.2.2, used a loopback proxy that stops
forwarding without closing either socket (`spec/ssh-reconnect-loop/research/03-tests-and-half-open.md`
§B). **Pre-existing:** present before any factory cycle.

## Outcome / vision

A silent link is noticed within the same bound a lost connection already has. A call that meets it
behaves as it would after any noticed loss:
- it reconnects, if the host can be reached again;
- otherwise it fails as a failed reconnect does, with an error naming the host and the cause, and
  the command not run.

Calls already in flight end within that bound too, reported as what they are. Nothing that is merely
quiet is mistaken for dead: a live command that prints nothing for a long while, or a slow transfer,
runs to its end.

## Acceptance criteria (the contract)

"The bound" is the reconnect bound `AGENTS.md` § Invariants already states for `executor/ssh.py`:
three times the connect bound after the call began, 45 s with the default 15 s `CONNECT_TIMEOUT`,
raised by a longer ssh_config `ConnectTimeout` (Q1).

- **R1** — WHEN a call starts while the published connection's link has gone silent without a reset,
  the call SHALL end within the bound, in every tool that uses the connection, in one of two ways:
  - IF the host is reachable again, it SHALL complete over a new connection;
  - IF it is not, it SHALL fail as a failed reconnect does: the command not run, and an error naming
    the host and the cause (Q2).
- **R2** — WHEN a file transfer (`write`, `put`, `get`, and the SFTP write behind `sbatch`'s
  `script_content`) is in flight as the link goes silent, it SHALL end within the bound after the
  link went silent, with an error naming the host that says the transfer may be partly made (Q3).
- **R3** — WHEN a command is running as the link goes silent, the call SHALL end no later than the
  earlier of its own timeout and the bound after the link went silent. If its end was not received,
  it SHALL be reported as `CONNECTION_LOST_EXIT_CODE` (the command may have run). This SHALL hold
  for a call with no timeout as well.
- **R4** — WHILE the link is live, no call SHALL be ended or reported lost because it is quiet: a
  command that prints nothing for longer than the bound, and a transfer whose replies are slow but
  arrive, SHALL run to their end with their results unchanged (Q4).
- **R5** — WHEN one call's traffic is stalled on a silent link, a concurrent call on the same server
  SHALL still end within the bound, as R1 says.
- **R6** — `AGENTS.md` § Invariants and the `executor/ssh.py` footgun SHALL state how a silent link
  is noticed, the bound, and what R2 and R3 report, in the same commit as the code.
- **R7** — The tests SHALL reproduce a silent link without a real host: a loopback that stops
  forwarding without closing either socket, in front of the suite's SSH server, in both protocol
  eras. Each of R1–R5 SHALL be pinned by a test that fails on `develop` where `develop` misbehaves.

## Non-goals (no-gos)

- Changing the reconnect itself: its loop, its bound and its error text are `ssh-reconnect-loop`'s,
  and this cycle feeds them, not changes them.
- Noticing a silent link while no call is in flight. Detection is required at a call, and during
  one. A background watcher is the plan's choice, not a requirement.
- A user-facing setting for keepalive intervals or a separate bound: the bound follows the existing
  `ConnectTimeout`-derived figure (Q1).
- The server side of the link (sshd's `ClientAliveInterval`), and `local` and `delegate` modes, which
  have no SSH link.
- Resuming or retrying a transfer that a silent link cut short.

## Clarifications

Ruled by the foreman as judge under the standing autonomy for this effort (2026-11-04), as proposed;
Geoffrey may overrule at the GOAL gate.

- **Q1:** What is the bound? Options:
  - **(a)** the reconnect bound already stated (3 × the connect bound, 45 s by default);
  - **(b)** a separate, shorter detection figure;
  - **(c)** a new setting.

  — **Ruled: (a).** One figure the docs already state and a reader already knows. It follows
  `ConnectTimeout` for slow links, and keeps detection and reconnect inside one budget, so a call
  that meets a dead link still ends within it. *Trade-off:* a silent link costs a call up to 45 s,
  not seconds.
- **Q2:** Should a call that finds a dead link reconnect, or fail? The seed's outcome says it
  "fails the way a failed reconnect does". — **Ruled: it is treated as a noticed loss,** so the
  existing reconnect runs, and it fails only when that reconnect fails. A laptop back on a new
  network then gets a working call rather than an error, and the seed's failure is the unreachable
  case.
- **Q3:** What does an interrupted transfer report? — **Ruled: an error naming the host that says
  the transfer may be partly made.** The file tools report failure as an error, not an exit code.
  Neither a whole remote file nor its absence is promised: the plan states what each tool can leave
  behind (a staging file, a truncated target), and the seed
  `issues/ssh-write-staging-leftover.md` already covers staging cleanup.
- **Q4:** Is R4 required alongside the bound? — **Ruled: yes.** A liveness fix ships with a pin on
  the completeness side ("return once only holders remain; never cut the command's own output",
  `safe-execution` review cycle 2). A detector that reads silence as death would cut every quiet
  `sbatch --wait` or long compile.

## Related materials

- Seed: `issues/ssh-half-open-link.md`
- `spec/ssh-reconnect-loop/` (the bounded reconnect this feeds; its GOAL's first non-goal and Q5
  deferred this), and its `research/03-tests-and-half-open.md` §B (the offline probe)
- `spec/safe-execution/` (`CONNECTION_LOST_EXIT_CODE`, −1003, and the connect bound)
- `AGENTS.md` § Invariants (the `executor/ssh.py` reconnect bound), and the high-blast-radius list
  (`executor/ssh.py`)
- `issues/ssh-write-staging-leftover.md` (staging left by a lost write)
