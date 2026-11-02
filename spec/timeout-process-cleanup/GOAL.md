# GOAL — Stop a timed-out command, and what it started, in every mode

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** timeout-process-cleanup
- **kind:** fix
- **appetite:** small

## Problem

Since `safe-execution`, a command that exceeds its `timeout` returns a result in every mode: the
output captured before the deadline and while it stopped, and `TIMEOUT_EXIT_CODE`, with no raise
(`AGENTS.md` § Invariants §3, "One timeout contract in every backend"). That contract says the
command "is stopped", but §3 also records that it may not be ("A timed-out command may outlive the
call"). What is at stake is not the result but a process left running on a shared login node, under
the user's account, after the call that started it has returned. Tool families that lean on bounded
calls make a timeout a routine outcome there rather than an accident (ROADMAP).

What the code does at the deadline today, in the order a fix has to fit into:

- **`ssh`.** `_collect` (`core/executor/ssh.py:249-255`) sends one RFC 4254 `signal` channel request
  for TERM (`_signal`, `ssh.py:162`), reads for `launch.GRACE` (1 s, `launch.py:85`) while the
  command stops (`_stopped`, `ssh.py:203`), and returns; `_exec` then closes the channel
  (`ssh.py:993-994`). No KILL follows. Closing a non-PTY channel does not stop the remote command:
  its pipes close, so it dies on its next write or runs to its end (`spec/safe-execution/` research
  02 §2: `sleep 60` survived). Whether the test cluster's OpenSSH acts on the `signal` request, and
  on what (the session's process, or its group), is unmeasured; research 02 believes it signals the
  session's process group but did not verify it. A command that never writes again (`sleep 3600`)
  may run to its end, and one that ignores TERM is never asked again.
- **`local`, and `delegate` under a root server.** `run_process` (`core/executor/launch.py:571`)
  starts the launch in a new session and, at the deadline, signals the whole process group TERM,
  reads for `GRACE`, then KILL, reads for `GRACE` again (`launch.py:602-610`). The KILL is skipped
  when the command's output has ended during the first read (`launch.py:609`), so whether a
  descendant that ignores TERM but holds neither output stream is reached is untested. A process
  that leaves the group is not reached, and the call stays bounded (`tests/test_launch.py`,
  `test_timeout_is_bounded_when_a_process_leaves_the_group`).
- **`delegate` under a non-root server.** The launch is `sudo -n -H -u <user> …`
  (`core/executor/delegate.py:24`, `:143`) through the same `run_process`. A non-root, sudo-capable
  service account (which `SECURITY.md` allows) can signal `sudo` but not the command, which runs as
  the mapped user; `sudo` relays TERM to the command, and KILL cannot be relayed, so killing `sudo`
  orphans the command (research 06 A2). A command that ignores TERM, and what it started, can
  outlive the call. A root server reaches them all.

**Pre-existing:** yes. The first executors (before any factory cycle) left a timed-out command
running the same way: the SSH backend closed the channel and raised, and the delegate backend killed
only `sudo`. `safe-execution` rewrote the timeout path (the `signal` request, the group's TERM then
KILL), found the remaining gap in its planning research and adversarial review, and recorded it
(PLAN risk 4, review M4) rather than fixing it, because measuring it needs a long-running process on
a login node, outside that cycle's read-only dogfood class. The maintainer approved that measurement
on 2026-10-29 (Q1).

## Outcome / vision

A command that times out is stopped on the host it runs on, together with what it started, within
one stated bound after its deadline, in every mode — `ssh`, `local`, and `delegate` under a root or
a non-root server — including a command that ignores TERM. The result a caller gets is unchanged. A
test with no real host pins it in each mode; `AGENTS.md` and the operator docs say what is stopped,
within what bound, and what is not.

## Acceptance criteria (the contract)

"The command's processes" below means the command, the children and grandchildren it started, and
any of them that ignores TERM, except a process that has left the command's process group
[NEEDS CLARIFICATION: Q4 — whether such a process is out of scope].
"The bound" is R4's. Each requirement that leans on a clarification names it.

- **R1** — WHEN a command run in `ssh` mode is still incomplete at its deadline, the command's
  processes SHALL all have exited on the host the command ran on within the bound. The plan step's
  measurement on a login node records what the test cluster's OpenSSH does today and informs the
  design; the requirement holds whatever it shows [NEEDS CLARIFICATION: Q1 — how the measurement
  bears on R1, and whether a post-fix run is part of it].
- **R2** — WHEN a command run in `local` mode, or in `delegate` mode by a server running as root, is
  still incomplete at its deadline, the command's processes SHALL all have exited within the bound,
  whether or not a process that ignores TERM still holds the command's output streams.
- **R3** — WHEN a command run in `delegate` mode by a server that is not root is still incomplete at
  its deadline, the command's processes SHALL all have exited within the bound
  [NEEDS CLARIFICATION: Q3 — whether a documented limit may stand in for this, and when].
- **R4** — The bound SHALL be one figure, the same in every mode, stated in `AGENTS.md` § Invariants
  §3 [NEEDS CLARIFICATION: Q2 — the figure, and whether the stop must finish before `run`
  returns]. `run` SHALL return a timed-out call no later than it does today.
- **R5** — The result contract SHALL be unchanged: a timed-out call returns `TIMEOUT_EXIT_CODE` with
  the output captured before the deadline and while the command stopped, and raises nothing; over
  `ssh`, a command whose exit status arrived before its output keeps `launch.LATE_NOTE`; a call
  whose end records both arrive before its deadline signals nothing, so what a completed command
  left running is untouched (§3, "A result is complete exactly when both end records have arrived").
  The existing timeout tests in `tests/test_executors.py`, `tests/test_launch.py` and
  `tests/test_ssh_exec.py` SHALL pass with no change to their assertions.
- **R6** — Each of R1, R2 and R3 SHALL be pinned by tests that need no real host, no real `sudo` and
  no network: for each mode, a command that starts a child and a grandchild, and a command that
  ignores TERM, each process checked gone by its pid once the bound has passed. For R3 the test's
  stand-in for `sudo` SHALL, like a non-root server's `sudo`, be the only process the server can
  signal and pass on TERM alone. Each test SHALL fail against the code on `develop` at `c8843b2`
  wherever that code leaves a process running in the test's setting.
- **R7** — In the same commit as the code it describes: `AGENTS.md` § Invariants §3 SHALL replace
  "A timed-out command may outlive the call" with what is stopped, the bound, and every limit that
  remains (Q4, and Q3's if it applies), and §2 and §5 SHALL describe any change to the launch or to
  the delegated argv; `README.md`'s timeout sentence SHALL say the command is stopped and name what
  is not; and, if a limit remains for a non-root `delegate` server (Q3), `SECURITY.md`'s multi-user
  section SHALL state it where an operator choosing a service account reads it.

## Non-goals (no-gos)

- **A server that exits or is killed while a command runs**, and the startup probe's abandoned
  worker: a different trigger, `issues/local-command-outlives-server.md`. A design that happens to
  cover it is welcome, but it is not graded here.
- **A connection lost before or at the deadline** over `ssh`: the call reports
  `CONNECTION_LOST_EXIT_CODE` and the command may still be running; not this trigger
  [NEEDS CLARIFICATION: Q5 — whether it is in scope].
- **A dead link that reads as connected, a stuck reconnect, a write's staging left behind**:
  `issues/ssh-half-open-link.md`, `issues/ssh-reconnect-stuck-step.md`,
  `issues/ssh-write-staging-leftover.md`. Each is its own trigger or its own leftover.
- **Background jobs a login startup file starts**, over `ssh` or not:
  `issues/startup-background-jobs.md`. The command did not start them.
- **A process that has left the command's process group** (`setsid`, a daemon)
  [NEEDS CLARIFICATION: Q4].
- **What a completed command left running**, and a call with no `timeout`: neither is a timeout.
  §3's rule that nothing a completed command left running is signalled stands (R5).
- **A scheduler job a timed-out command submitted** (`sbatch`): it is Slurm's, not a process the
  command started on the node.
- **Changing `TIMEOUT_EXIT_CODE`, `GRACE`'s value, or the result's shape.**
- **A post-fix run on a login node** as part of the contract: the host-free tests are the contract
  [NEEDS CLARIFICATION: Q1].

## Clarifications

Open: each awaits the foreman's ruling, as judge under the effort's autonomy decision, and is
reported to the maintainer after. The **Recommended** option is the shaping's proposal, not a
ruling.

- **Q1:** How does the approved login-node measurement (2026-10-29) bear on R1? Options: **(a)** the
  plan step measures today's behaviour once, run by the foreman only, through the server's real
  `ssh` path with a short timeout — a long-running command, one with a child and a grandchild, and
  one that ignores TERM, checked afterwards for survivors — and the same for a non-root `delegate`
  server where one can be measured; the findings go into the plan's research and choose the design,
  and R1 is graded on the host-free tests (R6); a confirmation run of the same measurement on the
  built branch is offered to the maintainer at the review gate as a separate approval. **(b)** as
  (a), with no confirmation run. **(c)** as (a), with the confirmation run made under the 2026-10-29
  approval. — **Recommended: (a).** The measurement decides the mechanism (whether the `signal`
  request reaches the group, whether a remote wrapper is needed), which is the plan's; the contract
  must not rest on a host the tests cannot reach. A confirmation run is the strongest evidence for
  R1, but whether the approval covers a second run is the maintainer's to say, not the factory's to
  assume. *Trade-off:* without a confirmation run, an `ssh` fix is proven against the in-process SSH
  server only, whose fidelity to OpenSSH's signal handling is the plan's to establish.
- **Q2:** What is the bound, and must the stop finish before `run` returns? Options: **(a)** one
  figure in `GRACE` terms: every process in reach has exited within 2 × `GRACE` of the deadline (2 s
  today: TERM at the deadline, KILL no later than `GRACE` after), on the server's clock and, over
  `ssh`, excluding the link's own delay; the stop may finish after `run` returns, and `run`'s return
  bound is unchanged (R4). **(b)** the same figure, and the stop must be complete before `run`
  returns. **(c)** a configurable bound. — **Recommended: (a).** It is the bound the `local` backend
  already intends and the call already returns within, so it adds no wait. Requiring the stop before
  return (b) needs, over `ssh`, a further round trip to observe the remote host, and lengthens every
  timed-out call. A setting (c) adds configuration for a number few operators would change.
  *Trade-off:* under (a) a caller that reads the result at once may briefly see the command still
  running on the host.
- **Q3:** Under a non-root `delegate` server, must R3 hold, or may the limit be documented instead
  (the seed's R2)? Options: **(a)** R3 holds, with no exception. **(b)** documenting the limit
  (R7) satisfies R3. **(c)** R3 holds, unless the plan shows that stopping a TERM-ignoring command
  and its descendants needs a privilege beyond the `sudo` rule `SECURITY.md` documents for the
  service account; then the PLAN gate says so, R3 narrows to what TERM reaches, and the limit is
  documented (R7). — **Recommended: (c).** The fix should not be traded for a sentence where a
  mechanism exists inside the rights the server already has, but widening a service account's
  `sudo` rule is a security decision for a human gate, not for this cycle. *Trade-off:* (c) leaves
  the outcome open until the PLAN gate; (a) could force a sudoers change; (b) makes the fix
  optional in the mode where processes run as other users.
- **Q4:** Is a descendant that has left the command's process group (`setsid`, a daemonising
  program) in scope? Options: **(a)** no: it is a documented limit (R7), and the call stays
  bounded as today. **(b)** yes: every descendant, however it detached. — **Recommended: (a).** A
  process that leaves its group has detached on purpose, the way a user starts something meant to
  outlive a session; reaching it needs a walk of the process tree that races the forks it walks, or
  a control group the server does not own, and `local` mode already records it as a limit.
  *Trade-off:* a command that daemonises a child can still leave it running after a timeout.
- **Q5:** Is a command whose `ssh` connection is lost before or at its deadline in scope? Options:
  **(a)** no: a non-goal; a design that covers it incidentally is welcome but not graded, and a seed
  is filed if it is wanted. **(b)** yes: such a command is also stopped within the bound after its
  deadline. — **Recommended: (a).** The trigger is the timeout over a working link; a lost link
  is a different trigger, like a server that exits (`issues/local-command-outlives-server.md`),
  and requiring it would force a remote-side mechanism the plan should be free to choose or not.
  *Trade-off:* a command whose link drops keeps running, as today.

## Related materials

- Seed: [`issues/timeout-process-cleanup.md`](../../issues/timeout-process-cleanup.md)
- ROADMAP: Part I, "A timed-out command may keep running after its call returns"
- Prior cycle: [`spec/safe-execution/`](../safe-execution/) (PLAN risk 4, review M4 and M17;
  research 02 §2, research 06 A2)
- Neighbouring seeds (non-goals):
  [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md),
  [`issues/ssh-half-open-link.md`](../../issues/ssh-half-open-link.md),
  [`issues/ssh-reconnect-stuck-step.md`](../../issues/ssh-reconnect-stuck-step.md),
  [`issues/ssh-write-staging-leftover.md`](../../issues/ssh-write-staging-leftover.md),
  [`issues/startup-background-jobs.md`](../../issues/startup-background-jobs.md)
- `AGENTS.md` § Invariants §2 (the launch), §3 (the timeout contract and its recorded limit), §5
  (the delegated argv); `README.md` (the timeout sentence); `SECURITY.md` (multi-user production)
- Source: `packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py` (`_signal`, `_stopped`,
  `_collect`, `SSHExecutor._exec`), `core/executor/launch.py` (`GRACE`, `run_process`,
  `BOOTSTRAP`, `bash_argv`), `core/executor/delegate.py` (`SUDO`, `DelegatingExecutor._run`),
  `core/executor/shell.py`
- Tests: `tests/test_launch.py`, `tests/test_executors.py`, `tests/test_ssh_exec.py`,
  `tests/ssh_server.py`
