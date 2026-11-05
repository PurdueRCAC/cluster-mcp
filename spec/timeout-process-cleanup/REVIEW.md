# REVIEW — A timed-out command, and what it started, is stopped in every mode

> Adversarial QA by `code-review`, run in an isolated/clean context (subagents). The correctness pass
> grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only**
> — it does not see `PLAN.md`/`TECH.md`. Every finding cites an **executed** command, not an
> assertion.

- **Reviewed commit:** `386efa3`  ·  **Base:** `c8843b2` (the branch's merge-base with `develop`)  ·  **Date:** 2026-11-02
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`

## How it ran

The debate variant: the diff touches `core/executor/launch.py` and `core/executor/ssh.py`, both
high-blast-radius. Two blind reviewers, ship and block, each in its own clone of `386efa3`, with only
the GOAL's text, the rubric's text, the spec-excluded diff and the repository. Both left their clones
clean and killed, by pid, every process their drives left.

**Contract drift.** None: `GOAL.md` is unchanged since `649bbf6`, the foreman's ruling on Q6.

## Verification run

Both reviewers, independently: `uv sync --locked` and `uv lock --check` ok; `uv run pytest -q` and
`CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` 4701 passed, 14 skipped (the bash 4.1 rows CI runs),
7.5–8.1 min per era; `bin/sandbox.sh uv run cluster-mcp --help` exit 0. CI on `386efa3`: 4714 passed
per era (8.1 / 9.5 min per job). Live drives: the real CLI under `bin/sandbox.sh` in `local`
(`run_command` with trees, TERM-ignorers, holding and not holding output, hostile and hanging
profiles), and the suite's `executes` fixture with `LoopbackSSH` and the sudo stand-ins for `ssh`,
root and non-root `delegate`; HEAD's tests run against the base launcher; sampled author mutants.

## Requirement → evidence matrix

| R-ID | Verified how (both reviewers unless noted) | Status |
|------|--------------------------------------------|--------|
| R1 | `ssh-bash` stop rows pass in both eras; every login shell under `EVERY_KIND` (43/43); trees, TERM-ignorers, startup-file rows and the hanging login stopped | ❌ F1; F2 |
| R2 | CLI drives in `local`: tree gone at +0.06 s, ignorers at +1.04 s (base: alive at +2.3 s); hostile profiles (`set -euCm`, traps, aliases and functions named like builtins); root `delegate` rows | ❌ F1 |
| R3 | `RELAY` stand-in relays TERM alone from its own session; tree, ignores-holding and an ad-hoc ignores-none row stopped; no sudo change | ❌ F1 |
| R4 | 2 × `GRACE` in §3; worst stop ≈1.04 s after the deadline; return times match base per shape; 28/28 under load 17 (block) | ✅ |
| R5 | Timeout-test assertions unchanged but the ruled one; near-deadline records (0.80–0.95 s of 1.2 s) × 4 settings 12/12; odd-profile drive's exit codes, argv, stdin and descriptors equal base | ❌ F1 |
| R6 | 28 pid-checked rows; HEAD's tests on the base launcher: 12 fail, exactly where base leaves a process running, 16 pass | ✅ (F4 coverage) |
| R7 | §2, §3, §5, footguns, Testing, README, SECURITY.md updated; limits link `issues/timeout-stop-limits.md` | ❌ F3 |

Clarifications Q1–Q6: each verified as ruled; F2 bears on Q6.

## Findings

### F1 [CRITICAL/CONFIRMED] A profile's `TMOUT` makes the watchdog kill a live command, in every mode, with or without a timeout
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/executor/launch.py:173-175` (`WATCHDOG`: the second `read -r cluster_mcp_w || { kill -s TERM 0; …; kill -s KILL 0; }`).
- **Failure scenario:** bash applies `TMOUT` as the default timeout of `read`, pipes included, and a `readonly TMOUT` (a common hardening line in `/etc/profile.d`) cannot be unset. The watchdog is forked after the login's startup files, inherits `TMOUT`, and its wait for the release times out while the program lives; it takes that for the program's death and stops the group. Any command that outlives `TMOUT` is killed, its output lost, a delegated copy's destination truncated; `run_command`'s default is no timeout.
- **Evidence (both reviewers):** `TMOUT=1; { sleep 3; echo x; } | { read -r v; }` → status 1 after 1 s (bash 3.2). Real CLI, `local`, profile `readonly TMOUT=2; export TMOUT`, `run_command '/bin/sleep 4; echo done'`: HEAD returned at 2.07 s (no timeout) and 2.02–2.10 s (`timeout` 20/30), exit -15, stdout empty, the unfinished note; base `c8843b2` returned `done`, 0, at 4.0–4.4 s. Through the suite's fixtures, `local`, `delegate`, root `delegate` and `ssh-bash` all returned at ≈2.0 s with 143 and the note, the command's background job killed; base `done`, 0, job alive. Non-root delegated `put` of a slow source onto an existing file: HEAD failed at 2.05 s with the destination truncated to its first half; base succeeded (ship). A mutant adding `-t` to the read fails only text-pinning rows (45 and 11 of 4701): no behaviour row runs a command past a few seconds with the watchdog armed.
- **Touches:** § Invariants §3 ("There is no timing rule; only the timeout bounds a call whose records do not come"), the new §2 watchdog bullet ("if the program dies"), R5, the non-goal "a call with no `timeout`". `launch.py` is high-blast-radius and §3 is a `[human gate]`.
- **Routed as the property:** the watchdog acts only on the program's death or its release, never on time: under any startup file, `TMOUT` (readonly included) or other shell setting that bounds or interrupts a builtin's wait, a command that has not reached its deadline, or has no timeout, is never signalled by it. Pin it beside every mode: a profile with `readonly TMOUT` below a command's run time, with and without a `timeout`, the command completing with its output and its background job alive; and a CLI representative. Sweep every alternative of the new wait.

### F2 [HIGH/CONFIRMED by reading; PLAUSIBLE on a real sshd] The KILL request goes out on a channel the client has already closed
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/executor/ssh.py:265` (`_signal(chan, 'KILL')` after `_stopped`).
- **Failure scenario:** in the common case the command dies at the TERM, the channel closes during `_stopped`, and Paramiko has exchanged CLOSE before the KILL request is sent. OpenSSH's server answers a channel request for a channel it has freed with `ssh_packet_disconnect` ("unknown channel"), which would drop the shared connection after every such timeout (sibling calls and SFTP get -1003, the next call reconnects); a late request on a reused channel id would reach another session.
- **Evidence (ship reviewer, loopback probe wrapping `ssh._signal`):** `tree` and `ignores-none` sent `('KILL', closed=True, eof=True, status=True)`; the test server, which drops messages for dead channels, dispatched only TERM. `ignores-holding` sent KILL on an open channel and it was delivered. Guarding the send with `if not chan.closed` made the frozen `test_a_timeout_drains_what_follows_the_term` (whose fake channel closes at 0.55 s) fail, since it asserts `['TERM', 'KILL']`. The real sshd behaviour is read from source, not run; the test server does not model the disconnect.
- **Ruling (foreman, as judge): fix.** The client can close-and-send without a round trip to find out, and a dropped shared connection on every ssh timeout is worse than the leak R1 removes.
- **Routed as the property:** no `signal` request is sent on a channel the client has closed or begun to close; the KILL still goes out while the launch may be alive (the case Q6 exists for). The test SSH server answers a request on a closed or unknown channel by disconnecting, as sshd does, so a regression drops the connection in the suite. Q6 and R5 are amended (`GOAL.md`, 2026-11-02): the drains test, whose channel has closed by then, keeps `c8843b2`'s assertion unchanged (`['TERM']`), and the KILL is pinned by rows whose channel is open after the grace.
- **Also:** the confirmation run on the test cluster (Q1) checks that the connection survives a timed-out call (a second call on the same connection).

### F3 [MEDIUM/CONFIRMED] The docs say a hanging login is stopped over `ssh`; one whose child ignores TERM is not
- **Where:** `AGENTS.md` § Invariants §3 (≈2209-2213, "is stopped in `local`, under a root `delegate` server and over `ssh`"), `README.md` (≈131-133), `issues/timeout-stop-limits.md` (≈20-26), the ROADMAP entry.
- **Evidence (block):** a `.bash_profile` running, in the foreground, `/bin/sh -c 'trap "" <every catchable signal>; …; exec /bin/sleep 30'`, the login bash not ignoring TERM, `run('echo never', timeout=1)`: stopped in `local` and under root `delegate`; under non-root `delegate` (documented) and over `ssh-bash` still running 2.5 s after the deadline. sshd's TERM ends the login shell, the session is gone, the KILL is refused, and the child runs on. Base behaves the same (pre-existing; not graded); the new text says it is fixed. Ship reviewer, non-root `delegate`: a profile `trap '' TERM; /bin/sleep 1.5` with timeout 1.0 lets the command itself start after the deadline and run unbounded; README and SECURITY.md say only "a startup file that hangs".
- **Routed as the property:** every statement of what is and is not stopped (AGENTS §2, §3, §5, README, SECURITY.md, the limits seed and its ROADMAP entry) matches what the drives show, per mode, including a hanging startup file's TERM-ignoring child over `ssh` and a command started after the deadline under non-root `delegate`.

### F4 [LOW/CONFIRMED] Two coverage gaps
- No behaviour row pins that the watchdog never fires on a live call (F1's mutant survives every behaviour row); F1's pins close it.
- Non-root `delegate` has no `ignores-none` row (ship ran it ad hoc: stopped). Add it beside the other settings.

### F5 [LOW/CONFIRMED] A feature-scoped spec id in the suite
- **Where:** `tests/mutants.py` (`# The KILL request (GOAL Q6): …`). § Conventions bars spec ids in code; `Q#` is the same class as `R#`/`P#`, which `tests/test_hygiene.py` catches and `Q#` it does not.
- **Routed:** drop the id from the comment, and widen the hygiene check to `Q#`.

### Noted, not counted
- A command with a TERM handler gets TERM twice (documented in the limits seed); its output was complete.
- Per-era suite time is ≈7.5–9.5 min per CI job against the 20-minute timeout.

## Human-gate triggers

- **Triggered:** F1 (CRITICAL) in `core/executor/launch.py` and § Invariants §3, and F2 (HIGH) in `core/executor/ssh.py`, both on the high-blast-radius list. Under the effort's autonomy decision the foreman is judge at human gates; it ruled both fixes (routed above), amended Q6 for F2, and reported to Geoffrey on 2026-11-02. The trigger stays recorded until publish.

## Optional completeness sub-pass

Not run.

## Review cycle 2 — changes-requested (2026-11-04)

A fresh blind debate (ship and block, xhigh, each in its own clone) over `50a1ad3`, the cycle-1 remediation (`47154af`, `35b6773`, `d071c9d`, `437e13d`, `50a1ad3`), with the GOAL as amended for cycle 1's F2. CI green on `50a1ad3`: 4750 passed per era (≈8 min per job). Both reviewers: `uv sync --locked`, `uv lock --check`, both eras 4737 passed and 14 skipped (the bash 4.1 rows CI runs), `--help` in the sandbox; the stop module under `CLUSTER_MCP_TEST_EVERY_KIND=1` (67 passed) and twice under load 27 (41 passed); the 37 limit rows (`CLUSTER_MCP_TEST_LIMITS=1`) all behave as documented. Cycle 1's F1–F5 verified fixed: under a readonly `TMOUT` completed calls keep output, exit and background jobs in every mode; a timed-out `ssh` call leaves the shared connection usable (16 timeouts, 1 connection), and the KILL goes only on an open channel.

### Matrix

| R-ID | Verified how (both reviewers unless noted) | Status |
|------|--------------------------------------------|--------|
| R1 | `ssh-bash` stop, startup-file and hanging-login rows; zsh, sh, tcsh under `EVERY_KIND`; 18 timed-out rows under 6 hostile profiles (ship) | ✅ |
| R2 | `local` and root `delegate` rows; 36 hostile-profile rows (ship) | ❌ F1, F4 |
| R3 | non-root `delegate` rows pass; late start and fork window run on (limit rows) | ❌ F3 |
| R4 | §3 states 2 × `GRACE`; pids gone by deadline + 2.5 s; `run` returns as base | ✅ |
| R5 | existing timeout assertions unchanged; completed calls signalled nothing (16 `ssh` calls); a TERM handler's output changes | ❌ F2 |
| R6 | the branch's stop module against base: fails exactly where base leaves a process running | ✅ (F5 coverage) |
| R7 | §2, §3, §5, README, SECURITY.md updated; absolute claims false (F1), double TERM understated (F2), Q# rule absent (F6) | ❌ |

### F1 [HIGH/CONFIRMED] A startup file that shadows `unset` makes the watchdog stop a command at once, with or without a timeout
- **Where:** `core/executor/launch.py:180` (`WATCHDOG`'s `unset -f /bin/cat /bin/sleep`); `AGENTS.md` §3 (≈2222-2225) and `README.md` (≈131-132), which promise that no function named like a path the watchdog runs can make it signal a command.
- **Evidence (block):** `.bash_profile` with `unset() { :; }` (or `enable -n unset`) and `/bin/cat() { printf '\n'; }`, `_job + '/bin/sleep 2; echo done'`, no timeout: stopped after 0.03 s (`local`), 0.05 s (`delegate`), 0.11 s (`ssh-bash`), 143, job killed; base `done`, 0. With `/bin/sleep() { :; }` the KILL follows the TERM at once. Base's own prologue can be subverted the same way, and such a profile only ever affects its own user's commands.
- **Ruling (Geoffrey, 2026-11-04): document the limit; close only the cheap cases.** Route: every statement of what the stop promises is true under a startup file that shadows the launch's own builtins or the paths it runs (it does not promise immunity); cheap hardening such as posix mode, where special builtins take precedence over functions, where it holds in bash 3.2–5.x; the limit recorded in §3, README and [`issues/timeout-stop-limits.md`](../../issues/timeout-stop-limits.md), with a limit row.

### F2 [HIGH/CONFIRMED] The watchdog's second TERM cuts short a graceful stop
- **Where:** `launch.py:180` (`kill -s TERM 0`).
- **Evidence (block):** a counting handler saw 2 TERMs in 15 of 15 runs in `local`, root `delegate` and `ssh-bash` (base 1); a handler that stops gracefully on the first TERM and exits at once on the second printed `second TERM: exiting now` on HEAD and `stopped cleanly` on base, in all three. §3's "has `GRACE` to print as it stops" is false for such commands; "may get it twice" understates it.
- **Ruling (Geoffrey, 2026-11-04): KILL only, after the grace.** The watchdog never sends TERM: it waits `GRACE` and sends KILL to the group. Where the deadline's TERM reached the group (`local`, root `delegate`, `ssh`) a graceful stop keeps its full grace; under a non-root `delegate` server the rest of the group gets KILL without a TERM first. Route: one TERM per process at a timeout in every mode; the double-TERM limit removed from the docs and the seed; pins replacing the counting rows.

### F3 [HIGH/CONFIRMED] R3 narrowed without Q3's precondition: late start and the fork window run on under a non-root `delegate` server
- **Where:** `launch.py:180` (`trap '' TERM` around the fork); `AGENTS.md` §3 limits (≈2257, ≈2266) and §5 (≈2377: "Neither needs a `sudo` right beyond the rule `SECURITY.md` documents"); SECURITY.md; the limits seed.
- **Evidence (both):** limit rows `late-start-delegate` and `fork-window-delegate` show the command running at deadline + 2.5 s; both are stopped in `local`, root `delegate` and `ssh-bash`. The fork window is introduced by this cycle; late start predates it. Q3(c) narrows R3 only where a privilege beyond the documented sudo rule is needed, and the docs say none is.
- **Ruling (foreman, as judge): fix.** Route: under a non-root `delegate` server a TERM that reaches the program at any point, the fork included, and a deadline that passes while a login initialisation runs, both end in the command's processes stopped within the bound, with no right beyond SECURITY.md's rule (for example: a handler, not an ignore, around the fork, re-raised after it; and a check of the deadline before the command starts). If a case cannot be closed without such a right, STOP and report it for a PLAN-gate record. A login initialisation that ignores TERM *and* shadows the launch's builtins falls under F1's ruling.

### F4 [MEDIUM/CONFIRMED] `enable -n trap` in a startup file leaves children running in `local` and root `delegate`
- **Evidence (block):** limit rows `enable-n-trap-local` and `enable-n-trap-delegate-root` show the child and grandchild running on.
- **Ruling:** F1's class (a startup file shadowing the launch's builtins); documented in [`issues/timeout-stop-limits.md`](../../issues/timeout-stop-limits.md), with the cheap hardening F1 routes.

### F5 [LOW/CONFIRMED] The key-exchange wait in `_signal` is unpinned
- **Evidence (block):** dropping `clear_to_send.wait` and its check, sending under `chan.lock` only, survived 182 rows. A request mid key exchange breaks RFC 4253 §7.1.
- **Route:** pin it (a fake transport mid key exchange) and sweep it.

### F6 [MEDIUM/CONFIRMED] AGENTS.md does not state the widened spec-id rule
- **Where:** `AGENTS.md` § Testing (≈928) and § Conventions (≈2788) name only `R#`, `P#`; `tests/test_hygiene.py` now rejects `Q#` too.
- **Route:** say so in both places.

### F7 [LOW/CONFIRMED] A lost reader stops the jobs a finished command left
- **Evidence (ship):** with the launch's stdout and stderr closed mid-run, the program dies of SIGPIPE writing its end record, before the release; the watchdog stops the group's background jobs (base leaves them). The triggers (a killed server, a lost link) are non-goals.
- **Route:** README's "never signalled by the stop" and §3 say exactly this case; no code change required.

### F8 [LOW/PLAUSIBLE] One zombie per call in the shipped image
- **Evidence (ship, by reading and kqueue order):** a completed call's watchdog exits after the program, orphaned; the `Dockerfile` runs `cluster-mcp` as PID 1 with no init and defaults to `local` mode, so orphans would re-parent to it unreaped. Not run in a Linux container.
- **Route:** the shipped image reaps orphans (an init as PID 1, or the server reaping), pinned by a text check of the image recipe and, where CI can, a count of zombies after many calls.

### Bound
Review cycle 2 with changes requested: the bound. Escalated to Geoffrey on 2026-11-04.

### Geoffrey's rulings at the bound (2026-11-04)
- **"Fix + scoped review":** one remediation of F1–F8, then a narrow blind review (cycle 3) limited to the watchdog and what this remediation changes.
- **Double TERM: "KILL only, after grace"** (F2, routed above).
- **Hostile startup files: "Document the limit"**, closing only the cheap cases (F1, F4, routed above).

## Review cycle 3 — changes-requested (2026-11-04)

**Mode: scoped,** by Geoffrey's ruling at the cycle-2 bound ("Fix + scoped review").
- **The pass:** a fresh blind debate (ship and block, xhigh, each in its own clone) over `c16f19b`. It covered the remediation `e63e926..c16f19b` (`3129168`, `09b4e0b`, `d6cd8f8`, `c16f19b`), with the whole branch as context.
- **Inputs:** the GOAL, cycle 2's findings with the rulings, and the rubric.
- **CI green on `c16f19b`:** 4809 passed per era, about 9 min per job.
- **Both reviewers ran:**
  - `uv sync --locked`;
  - both eras: 4796 passed, 14 skipped (the bash 4.1 rows that CI runs);
  - `--help` in the sandbox;
  - the stop module under `CLUSTER_MCP_TEST_EVERY_KIND=1` and `CLUSTER_MCP_TEST_LIMITS=1` (block: 122 passed; ship: 93 + 29).
- **The red side:** HEAD's new pins, laid over `50a1ad3`'s source, fail where the findings said. Block counts 21 failures; the 5 that pass are the ssh late-start row and `kill-alias`, as expected.
- **Verdicts:** ship argued ship (three LOW findings); block argued block (one HIGH finding).

### Matrix (cycle 2's findings)

| F | Closed per ruling | Pinned, red on `50a1ad3` | Note |
|---|---|---|---|
| F1 | ✅ cheap cases closed; limit stated | ✅ 4/4 | |
| F2 | ✅ KILL only, after `GRACE` | ✅ | |
| F3 | ✅ late start and fork window in the parent | ✅ 7/8 (ssh row green on base, as expected) | introduced B1, B3 |
| F4 | ✅ | ✅ 3/3 | `kill-alias` pins nothing (see below) |
| F5 | pinned | partly | B4 |
| F6 | ✅ | hygiene | |
| F7 | ✅ docs | prose | |
| F8 | ✅ tini | text only | B6 |

| R-ID | Status |
|------|--------|
| R1, R2 | ✅ (B3 in principle) |
| R3 | ✅, wider than cycle 2 |
| R4 | ❌ the bound is met; the clause "`run` SHALL return a timed-out call no later than it does today" is not (B1) |
| R5 | ✅ in the suite (B2, B5 at the edge) |
| R6 | ✅ |
| R7 | ❌ §3 states B1's sentence |

### B1 [HIGH/CONFIRMED] The deadline check's `GRACE` wait makes a timed-out call return later than develop
- **Where:** `launch.py:212-215` (`DEADLINE_CHECK`: `/bin/sleep {grace}; kill -s TERM $$; …`); `AGENTS.md` §3 (≈2255: "`run` returns no later than it did before the watchdog"); R4's last sentence.
- **Mechanism:** a login initialisation ignores TERM and ends after the deadline. The server's TERM has already been spent. The check refuses the command, then waits a full `GRACE` for a TERM that will not come.
- **Evidence (block):** profile `trap '' TERM; /bin/sleep 1.3`, command `echo ran`, timeout 1.

  | Mode | develop | `50a1ad3` | HEAD |
  |---|---|---|---|
  | `local` | 1.33 s | 1.33 s | 2.00 s |
  | root `delegate` | 1.41 s | 1.37 s | 2.01 s |
  | non-root `delegate` | 1.41 s | 1.36 s | 2.36 s |

  No late-start row checks the return time.

### B2 [LOW/CONFIRMED, both] `cluster_mcp_n` leaks into a command under a profile's `set -a`
- **Where:** `launch.py:212`. The prologue does not clear `-a`, and the variable is never unset.
- **Scope:** `local` and `delegate` calls with a timeout. It is not present on `50a1ad3` or develop.

### B3 [LOW/CONFIRMED with a planted window] The watchdog child is born with TERM at its default
- **Where:** `launch.py:197`. `trap - TERM; exec 46>| >(trap '' TERM; …)`: from the fork to the child's first statement, a TERM to the group kills the watchdog. The parent does not wait, so it can start the command meanwhile.
- **Evidence (block):** a 1.5 s window planted before the child's `trap`. HEAD left the child and grandchild running at deadline + 2.5 s; the same plant on `50a1ad3` left nothing running. The fork-window rows plant only in the parent.
- **Unplanted:** the window is microseconds wide.

### B4 [LOW/CONFIRMED] A `_signal` mutant survives F5's pins
- **Mutant:** `ssh.py:194`, `with transport.clear_to_send_lock:` dropped, the `is_set()` check kept. Check-then-send is no longer atomic against a key exchange starting.
- **Evidence (block):** it survived the key-exchange pins and all 161 ssh rows. `tests/mutants.py` has no such case.

### N1 [LOW/CONFIRMED] Giving ssh no deadline check is an unpinned decision
- **Mutant:** `ssh.py:992` passes `timeout=` to `launch.program`. It survives 549 + 47 rows.
- **Reachable:** `_ensure_connected` delayed 1.5 s, with `run('echo ran', timeout=1)`. The mutant returned `-1001`, never having run; HEAD returned `ran`, 0 (ship).

### B6 [LOW/CONFIRMED] F8's pin is text only
- **Gap:** the route's "where CI can, a count of zombies after many calls" was not added. No image is built anywhere.

### B5 [LOW/PLAUSIBLE] The deadline check compares against the wall clock; the server's deadline is monotonic
- **Where:** `launch.py:367` (`time.time_ns()`) against `:668` (`time.monotonic()`).
- **Failure modes:**
  - A forward step during login refuses a command whose server deadline is far off: simulated, it returned `-1002` "did not start" in 1.04 s with a timeout of 5.
  - A backward step lets a late start through.
- **Docs:** §3's "on the server's clock … to the nanosecond" glosses over this.

### N3 [LOW/PLAUSIBLE, read from bash source] Leaving posix mode leaves `inherit_errexit` on in bash ≥ 4.4
- **Reach:** a completed command sees it only through an exported `BASHOPTS`. Not run: this host has bash 3.2 only, and building bash was refused.

### Noted, not counted
- **`kill-alias` pins nothing:** leaving posix mode turns `expand_aliases` off in bash 3.2–5.3, per both reviewers (block read `posix_initialize`). The row passes on `50a1ad3`, and with the second `\unalias -a` removed.
- **The seconds-only `date` fallback:** it could let a command start up to 1 s late under a non-root server, on a `date` without `%N`. Not reproducible on either host (ship).

### Bound
Review cycle 3 with changes requested: past the ≤3-cycle bound. Escalated to Geoffrey on 2026-11-04.

### Geoffrey's rulings past the bound (2026-11-04)
- **"Fix, I verify, land":** one remediation of B1–B6, N1 and N3. The foreman verifies it against the reviewers' reproductions, with no fourth blind review. Then the approved confirmation run, then publish.
- **B1, "Reword R4 to the bound":** the GOAL's R4 now promises that `run` returns a timed-out call within 2 × `GRACE` of the deadline, on the server's clock and, over `ssh`, excluding the link's own delay. Q2's note is amended to match. The check's `GRACE` wait stays.
  - **Route:** §3 (≈2255) and any statement of "no later than before" are made true to the amended R4.
  - The late-start rows assert the return time against that bound in every setting.
- **B5, "Document the limit":** a wall-clock step during the login initialisation can refuse a command early (`-1002`) or let a late one start. That limit is stated in §3 and in [`issues/timeout-stop-limits.md`](../../issues/timeout-stop-limits.md). §3's "on the server's clock … to the nanosecond" becomes exact: the program's deadline is wall-clock; the server's is monotonic; macOS `date` gives microseconds.

### Foreman's routes for the rest (judge, under "Fix, I verify")
- **B2:** no variable of the program's reaches a command, under any startup-file option such as `set -a`. The route is the class: every name the prologue, the watchdog line and the check set.
- **B3:** the watchdog is never, at any instant, a process that a TERM to the group can end before it ignores TERM. The F3 fork-window property holds as well: a TERM that reaches the program from the prologue on ends it before its command starts, or the command never starts.
  - **Suggested shape, not binding:** ignore TERM across the fork, so the child is born ignoring it. Take the default back after the fork, and let the deadline check, which follows, refuse the start where a TERM was lost in that window: the server's TERM only ever comes at the deadline.
  - **Pins:** windows planted in both the parent and the child, in every setting.
- **B4, N1:** both mutants become cases in `tests/mutants.py`, killed by behaviour rows. The `_signal` lock is pinned by a fake transport that starts a key exchange between the check and the send. ssh's lack of a deadline check is pinned by a slow-connect row.
- **N3 (PLAUSIBLE, triaged fix):** the prologue's posix round trip leaves the shell options a completed command sees as they were, `inherit_errexit` and `expand_aliases` included.
  - A text pin where this host's bash 3.2 cannot run it, plus a row that CI's bash 5 runs.
- **B6, deferred:** building the image and counting zombies in CI is out of this cycle's appetite. It goes to a seed ([`issues/image-init-reaping.md`](../../issues/image-init-reaping.md)) with a ROADMAP entry. The text pin stays.
- **`kill-alias`:** the row is removed, since it pins nothing on any bash 3.2–5.3. The text check of the second `\unalias -a` stays, recorded as an equivalent.

## Foreman verification of remediation 3 — approved (2026-11-04)

**Mode:** foreman verification, under Geoffrey's ruling past the bound ("Fix, I verify, land"). This is not a blind review. The FSM counts the `--verdict` call as cycle 4. The code verified is `7e4e584` and `6c4df4e` (remediation 3), `c3b0501` (the foreman's fix to the shell-options row's test), and `49d0026`, `5d83fd4`, `3a4db66` (the inert N3 restore removed).

### What I ran
- **Commits:** all signed with the agent subkey, no trailers. `verify/`, GOAL and REVIEW were untouched by the builds; the diffs carry no site-private names.
- **New pins, at the head and over `c16f19b`'s source** (HEAD's `tests/` laid over the reviewed code):
  - B2 `test_no_variable_of_the_program_reaches_the_command` fails in local, delegate-root and delegate, and passes over ssh, which has no check.
  - B3 `test_a_deadline_while_the_watchdog_starts[*-watchdog]` fails in local, delegate-root and ssh-bash.
  - Every new pin passes at the head (22 rows).
- **Mutants planted by hand at the head, then restored:**
  - B4: `_signal` without `clear_to_send_lock`, killed by `test_a_signal_request_never_goes_as_a_key_exchange_starts`.
  - N1: ssh's `program` given `timeout=`, killed by `test_a_slow_connect_leaves_an_ssh_command_its_whole_timeout`.
- **B1 and B5 docs:** no "no later than before" statement remains. §3 states the 2 × `GRACE` return bound and both clocks.
- **The confirmation run Geoffrey approved, on a test cluster** (OpenSSH 8.0, bash 4.4): a dev server from `6c4df4e`, ssh mode, port 54111, timeout 3 s. Scratch files were cleaned up by literal path.
  - A: a plain tree, gone; returned in 3.06 s.
  - B: a TERM-ignoring tree (4 pids), gone; returned in 4.05 s. This is the case the fix exists for: it survived on develop.
  - C/D: exactly one TERM per process, group-wide, and the graceful handler's `stopped cleanly` was returned.
  - E: the shared connection answered in 0.30 s after the three timeouts.
- **CI on `6c4df4e`: red.** The bash-5 shell-option rows printed the expected options, but `shopt -p` with names exits 1 when one is off. Fixed in the test (`c3b0501`); CI then green, 4852 per era.
- **N3: not reproduced.**
  - A throwaway CI branch with the restore dropped passed the four behaviour rows on bash 5.2.
  - Read-only probes on two test clusters (bash 4.4.20 and 5.1.8) show the posix round trip changes the program's own options but does not refresh `BASHOPTS`, so a command's fresh bash gets the login's options. An argv command is `exec`ed, so it never runs in the program's shell.
  - The restore was inert, and it is removed (`49d0026`). The behaviour row stays as the pin that the program refreshes no `BASHOPTS`.
- **The N3-revert gate:** P3's sweep went red once. `tpc-command-sleep` survived the ssh-bash grace row under the sweep's load. Run alone three times it was killed 3/3 in all three settings, so I ruled it a flake, in the same class as remediation 1's ruling on that case. Both eras' sweeps were then green: 166 cases, 20/20 equivalents. Whole suite: 4819 passed and 14 skipped per era.
- **CI on `3a4db66`:** green: 4836 passed per era (legacy 8.4 min, modern 10.0 min of the 20-minute job limit), gate green.

### Rulings on the builders' questions
- **B3 over ssh:** a TERM lost while the watchdog starts lets the command start. The KILL request stops it at about D + GRACE, within the bound, matching ssh's late-start path. Accepted.
- A TERM from anything other than the server, with no deadline near, is lost in the fork window. Accepted: only the server sends one.

### Verdict
Approved. B1, B2, B3, B4 and N1 are fixed and pinned. B5 is documented as a limit. N3 was not reproduced, and its inert fix is removed. B6 is deferred to [`issues/image-init-reaping.md`](../../issues/image-init-reaping.md). No human-gate trigger is open: Geoffrey ruled at both bounds, and his "Fix, I verify, land" is the sign-off for this cycle.
