# REVIEW — The test markers say what the unit guard enforces

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent). The correctness
> pass grades the branch diff against [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants
> **only**. Every finding cites an **executed** command, not an assertion.

- **Reviewed commit:** 0efe6bf35805b5536979513defed75d214e7832f · **Base:** develop (`e378c33`) · **Date:** 2026-11-09
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3
- **Contract:** `GOAL.md` at HEAD, which carries one commit after the shape commit (`2258691`, the
  GOAL-gate clarifications Q1 and Q2). Those are rulings recorded at the gate, so this review grades
  against them.
- **Mode:** one fresh blind reviewer, full spec-excluded diff. Its evidence (probe scripts and logs)
  is in the worktree's gitignored `.local/review1/`.

## Verification run

All commands ran with Python 3.14 and exited 0:

- **`uv lock --check`:** ok.
- **The profile's `verify`, both eras:** p1 44 passed, p2 154, p3 507, p4 4425 (14 skipped). That
  is 5144 tests collected per era. Logs: `verify-*.log`, `verify-part4-legacy.log`, `collect.log`.
- **`tests/test_hygiene.py`:** 198/198 per era (`hygiene-legacy.log`, `hygiene-modern.log`).
- **The new check's own tests:** 56 passed (`marker-tests-verbose.log`), 4 accept rows and 51
  reject rows.
- **`bin/sandbox.sh uv run cluster-mcp --help`:** ok (`sandbox-help.log`).
- **`pytest --markers`:** shows the new descriptions (`pytest-markers.log`).
- **Guard probe.** A throwaway `unit` test was placed in `tests/` so that `tests/conftest.py`
  applied, then removed (`guard-probe.jsonl`, `guard-probe2.jsonl`, `static_probe.log`).
- **Mutant sweep of the R5 check:** 71 mutants, 13 survivors (`mutants.py`, `mutants.log`).
- **The R5 drifts applied to the real files:** every one flagged (`real_drifts.log`).
- **Spec ids:** the grep over the diff's code and `AGENTS.md` lines finds none (`spec-id-grep.log`).
- **Tree:** `git status --porcelain` was empty on hand-back. No build state was mutated.

## Requirement → evidence matrix

No R-ID's deliverable is a `spec/` artifact, so the blind reviewer verified every row. The
orchestrator re-read the cited logs.

| R-ID | Status | Verified how |
|------|--------|--------------|
| R1 | ❌ finding 1 | `pyproject.toml:51` states the three refusals and no longer says "fast" (`marker-meaning-grep.log`). Its closing claim "the unit guard holds it to that" is disproved by the guard probe. |
| R2 | ✅ | `pyproject.toml:52`: "needs what a unit test is refused", keeps "every process it launches goes through bin/sandbox.sh", no mention of the CLI |
| R3 | ✅ | Each of the nine kinds is classified by the wording alone (table below). No exception clause. A test that does none of them and reads no real HOME falls under `unit`. |
| R4 | ✅ | `AGENTS.md:110-111`, `:119-121`, `:310-320`, `:3151-3156` state the markers in pyproject's terms. The "drives no CLI" note is gone. `stated-markers-real.log` shows both sections parse identically to pyproject. |
| R5 | ⚠️ findings 2, 3 | The check is `unit`, holds § Testing and § Conventions word for word, and plants every drift R5 names. Narrower forms of two carve-outs survive. |

R3, kind by kind (the classifying clause of the `integration` description):

| Kind | Classifying clause |
|------|--------------------|
| 1. drive of the installed CLI | "(a process" |
| 2. another program through the sandbox | "(a process" |
| 3. child interpreter through the sandbox | "(a process" |
| 4. stand-in for a host tool | "(a process" |
| 5. `local`/`delegate` under `executes` | "a process … through a fixture" (the fixture's sandboxed launcher, `tests/conftest.py:464`) |
| 6. stdio server in its own process | "a process" + "through a fixture or helper" (`tests/harness.py:544`) |
| 7. loopback server connection | "a network connection" (the probe shows the guard refuses loopback connects) |
| 8. fixture or helper launch | "itself or through a fixture or helper" |
| 9. killed or outliving sandboxed child | "(a process" |

Unmapped changes (harmless, ledger and map upkeep):
- the guard-gap paragraph at `AGENTS.md:1485-1490`;
- the `_host` note in the hygiene entry;
- the `issues/marker-rule-gaps.md` and `issues/integration-marker-check.md` seeds and their
  `ROADMAP.md` entries;
- the timing-ledger line in `issues/stalled-reconnect-test-timing.md`.

The `ROADMAP.md` counts hold: Part I has 30 entries and the gates 14. Every entry points at an
existing seed with a matching status, and `marker-rule-gaps` claims 1–4 all reproduce.

## Findings

### 1. [MEDIUM/CONFIRMED] The `unit` description claims the guard enforces more than it does
- **Where:** `pyproject.toml:51`, copied word for word to `AGENTS.md:313-314` and
  `AGENTS.md:3152-3153`. A second instance is at `AGENTS.md:120-121`.
- **Failure scenario.** The description ends "the unit guard holds it to that". In a `unit` test,
  each of the following still goes through:
  - `socket.gethostbyname`, `gethostbyname_ex`, `gethostbyaddr` and `getnameinfo` resolve names;
  - a `_socket.socket.connect` to a loopback listener connects;
  - a UDP `sendto` delivers;
  - an early-bound `from socket import getaddrinfo` resolves;
  - `conftest.REAL_POPEN` and a module-level `from subprocess import Popen` launch `/usr/bin/true`
    (rc 0);
  - a module-scoped fixture's launch runs before the guard is active.

  The same diff's guard-gap paragraph (`AGENTS.md:1485-1490`) lists these exceptions, so § Testing
  contradicts its own word-for-word statement. Second instance: `AGENTS.md:120-121` calls the
  sandbox rule "the rule the suite enforces", but `sandbox_violations` passes a `REAL_POPEN` launch
  outside the sandbox (`tests/test_ssh_exec.py:777`, `_host`, pre-existing).
- **Evidence:** `guard-probe.jsonl` (each "WENT THROUGH" row), `guard-probe-run.log`,
  `guard-probe2.jsonl`, `static_probe.log`.
- **Touches:** R1 ("SHALL state what the unit guard enforces"); R4 through the copies.

### 2. [LOW/CONFIRMED] The R5 check's "not an item" branch has no planted row
- **Where:** `tests/test_hygiene.py:441`, the branch of `stated_markers` that rejects a line that is
  not a `` - `<name>`: <description> `` item.
- **Failure scenario.** A mutant that replaces the rejection with `continue` passes all 55 planted
  rows and the real-file test. It wrongly passes two drifts that the real check flags:
  - an exception bullet after the items (`  - except a gate, which needs nothing`);
  - a third marker without backticks (`  - beta: a third`).

  These are R5's "a clause … at the end" and "a third marker added in one place", in shapes no row
  plants.
- **Evidence:** `mutants.log` (SURVIVED `skip-bad-item-line`, plus its DEMONSTRATIONS);
  `real_drifts.log`.
- **Touches:** R5.

### 3. [LOW/CONFIRMED] Narrower forms of R5's named carve-outs survive the planted rows
- **Where:** the planted rows at `tests/test_hygiene.py:542-609`.
- **Failure scenario.** Each of these mutants passes a concrete drift that the unmutated check
  flags:
  - ignoring `(` and `)`;
  - ignoring `/` and `-`;
  - folding curly quotes to straight ones;
  - ignoring a trailing sentence after `. `;
  - ignoring parenthesised text: "(a window excluded)" passes against "(a window included)". In
    the real descriptions that slot holds R1's "(a name lookup included)".

  The canonical form of every carve-out R5 names is killed (case, all punctuation, commas,
  semicolons, periods, whitespace forms, NBSP, NFC/NFD/NFKC, prefix, containment,
  after-semicolon).
- **Evidence:** `mutants.log` (the SURVIVED rows and DEMONSTRATIONS).
- **Touches:** R5 ("every such carve-out is killed by a named row").

### 4. [LOW/CONFIRMED] The new seed misstates a fixture's scope
- **Where:** `issues/integration-marker-check.md:38-39`.
- **Failure scenario.** The seed names "the loopback SSH server" as a launch by a session- or
  module-scoped fixture. That does not match the code:
  - the only wider-scope fixtures are `tests/conftest.py:170` and `:202`, which launch nothing, and
    `tests/test_core_only.py:68`;
  - the loopback server's fixtures are function-scoped (`tests/test_ssh_exec.py:114`,
    `tests/test_ssh_liveness.py:503`, `tests/test_timeout_stop.py:169`) or are built in test
    bodies;
  - its launches are in `tests/ssh_server.py:400` and `:608`, which is the helper-module case the
    seed's next sentence already covers.
- **Evidence:** `fixture-scope.log`.
- **Touches:** ledger prose in the graded diff (rubric: a seed that misstates the repository).

### Coverage observations (not findings)
These are surviving mutants whose drift is caught elsewhere or changes no rendered word:
- **`drop-no-markers-line`:** with no markers in `pyproject.toml`, `--strict-markers` already fails
  collection (`no-markers-strict.log`, exit 2).
- **`other-bullets-are-items` and `lazy-wrap-joins`:** the rendered words are identical.
- **The four statement-line mutants (`lstrip`, substring, prefix, casefold):** they alter how the
  anchor sentence is found, never a description.

### Notes routed with the findings
These were reproduced but are not counted. Each belongs to a finding's property class and goes to
build with it:
- **With finding 1:**
  - an exported `XDG_STATE_HOME` reaches a `unit` test unchanged (`guard-probe.jsonl`), which the
    guard paragraph's "`XDG_*` point under `tmp_path`" and its new gap list both omit;
  - `AGENTS.md:989-990` says "a clause added anywhere" counts, yet the check by design accepts an
    exception paragraph after a blank line at the parent bullet's indent (`real_drifts.log`).
- **With finding 4:** the line added to `issues/stalled-reconnect-test-timing.md` cites `7ca3d01`,
  a pre-rebase commit that HEAD cannot reach.

## Routing (to `code build`)

- **Finding 1 (property).**
  - The rule: every statement this diff makes about what the unit guard or a hygiene check enforces
    is true of the code. Fix the wording only, within the non-goals: no change to the guard,
    `sandbox_violations` or `bin/sandbox.sh`.
  - Where it applies: the marker descriptions and their `AGENTS.md` copies, the commands-block
    sentence, the guard paragraph (including its `XDG_*` claim and the gap list), and the
    description of the R5 check.
  - The guard's actual gaps stay with `issues/marker-rule-gaps.md`, which should name every gap
    the wording now qualifies.
- **Findings 2 and 3 (surviving mutants).**
  - Run a mutant sweep over every decision in `stated_markers`, `statement_end_problems`,
    `described_markers` and `marker_statement_violations`. Include the additive carve-outs (case,
    each punctuation class, quotes, whitespace, a clause at start/middle/end and after the
    statement, lazy continuation, bullet styles, a third or missing marker, order, repeats, Unicode
    forms).
  - Every survivor must be killed by a named planted row, or recorded as equivalent with the
    reason.
- **Finding 4 (property).** Every factual claim in the ledger files this diff adds or edits (seeds,
  `ROADMAP.md` entries, the timing line) must be proven against the code or the history it cites.

## Human-gate triggers

- **Not triggered.** No CONFIRMED finding touches a path on § Invariants' high-blast-radius list,
  and none violates a section tagged `[human gate]`. The diff touches no § Invariants section.
