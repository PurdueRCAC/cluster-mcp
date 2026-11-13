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

## Review cycle 2 — changes-requested (2026-11-10)

- **Reviewed commit:** 89f34b8e70093011ceef5e4bc43f6a6950f7e3c4 · **Base:** develop (merge base `e378c33`;
  `origin/develop` is now `146cbc6`) · **Date:** 2026-11-10
- **Verdict:** changes-requested · **Cycle:** 2 of ≤3
- **Contract:** `GOAL.md` at HEAD, as in cycle 1 (the only post-shape commit is `2258691`, the
  GOAL-gate clarifications).
- **Mode:** a fresh blind pass over the full spec-excluded diff, by one reviewer at effort xhigh,
  which also checked cycle 1's findings 1–4 as properties. The reviewer's evidence is in the gitignored
  `.local/review2/reviewer/`, and the orchestrator's gate log is in `.local/review2/orchestrator/`.

### Verification run

- **The orchestrator's spec-held gates** ran before the reviewer started (`gates.log`). Both exited 0:
  - `verify/gate.sh prepush`: wording, slice (213 passed per era), ids, sweep (51 drift rows, 4
    accept rows, 74 mutants, 0 not killed), scope P3 and ledger;
  - `remediation/checks.sh F1 F2 F4`: 66 drift rows, 4 accept rows, 0 survivors, ledger 209 lines.

  The reviewer's own sweep then found 69 surviving mutants (finding 4). These gates grade only the
  mutants their author listed, so they did not observe the classes below. Their green result is
  not evidence that R5's carve-out property holds.
- **The profile's full `verify`, both eras** (`verify.log`): every command exited 0.
  - Each era: 44 + 154 + 507 + 4440 passed, 14 skipped. Every skip is a pre-existing
    `need_shell` row (`skips.log`).
  - `uv sync --locked`, `uv lock --check` and `bin/sandbox.sh uv run cluster-mcp --help`: ok.
- **The new tests ran:** 73 passed under a `-k` filter that names them (`focused-marker-tests.log`).
- **Guard probe:** a throwaway `unit` test was copied into `tests/`, run, and removed, along with its
  bytecode (`guard_probe.json`, `guard_probe.log`).
- **Static probe of `sandbox_violations`:** `static_probe.log`.
- **CommonMark probe of the R5 check:** markdown-it-py (`markdown_probe.log`).
- **Mutant sweep of the R5 check:** decision mutants plus additive ones (`mutants.py`,
  `mutants.log`). Each survivor named below has a concrete wrong pass in `witness.log`.
- **Spec ids:** none in the added `tests/`, `pyproject.toml` or `AGENTS.md` lines (`spec-id-grep.log`).
- **Tree:** `git status --porcelain` was empty on hand-back, and `git diff --quiet HEAD` passed. No
  ignored build state was mutated beyond the probe's bytecode, which was removed and asserted gone.

### Requirement → evidence matrix

No R-ID's deliverable is a `spec/` artifact. The blind reviewer verified every row, and the
orchestrator re-read the cited logs.

| R-ID | Status | Verified how (by the reviewer) |
|------|--------|--------------------------------|
| R1 | ✅ | `pyproject.toml:51` has no "fast" and names process, connection (name lookup included) and real HOME. Its "except on the open routes AGENTS.md § Testing names" holds: every route § Testing names reproduced, and every refused route was refused (`guard_probe.json`). |
| R2 | ✅ | `pyproject.toml:52`: "needs what a unit test is refused", keeps the sandbox rule, no CLI. |
| R3 | ✅ | The nine kinds each need a process or a connection, "itself or through a fixture or helper". A test needing none falls to `unit`. |
| R4 | ⚠️ finding 1 | § Testing, § Conventions and the commands block are restated, and the "drives no CLI" note is gone. `AGENTS.md:1650` (§ Testing) still defines integration tests as driving the installed CLI. |
| R5 | ⚠️ findings 2, 4 | The test is `unit`, passing, and has every planted row R5 names. The broad carve-outs are killed. A whitespace-form bug and narrower carve-outs survive. |

### Cycle-1 findings

| Cycle 1 | Status at `89f34b8` | Evidence |
|---|---|---|
| 1. The `unit` description overclaims the guard | **Open as a property** (finding 3). Every guard claim now made holds under the probe, including the `XDG_*` note. The diff's statements about the static launch check still name one gap where many exist, and the tab form of the cycle-1 "exception after a blank" note survives (finding 2). | `guard_probe.json`, `static_probe.log`, `markdown_probe.log` |
| 2. The "not an item" branch has no row | **Closed.** The `continue` and keep-items mutants are killed by named rows. The `break` variant is equivalent. | `mutants.log` |
| 3. Narrower carve-outs survive | **Open as a property** (finding 4) | `mutants.log`, `witness.log` |
| 4. The seed misstates a fixture's scope | **Closed.** The fixture-scope claim is now true, and `c7da4dd` is an ancestor of HEAD. The `ROADMAP.md` counts, statuses and links hold. | reviewer report. The timing line's load figure cites `spec/` and was not verifiable blind. |

### Findings

#### 1. [MEDIUM/CONFIRMED] `AGENTS.md` § Testing still defines integration tests as driving the installed CLI
- **Where:** `AGENTS.md:1650`, in § Testing (lines 298–1657). The diff does not touch it.
- **Failure scenario.** The line reads "Integration tests drive the installed CLI, and each one
  wraps its own drives in `bin/sandbox.sh`". This is the definition R2 removed from
  `pyproject.toml`. R4 requires the new terms wherever § Testing says what a marker means, so a
  reader choosing a marker meets two contradictory definitions in one section. Counterexample:
  `test_docs_modules_absent` (`tests/test_registry.py:366`) is `integration` and drives no CLI.
- **Evidence:** `r4-counterexample.log`. The orchestrator also confirmed the line with
  `git grep -n 'drive the installed CLI' -- . ':(exclude)spec/'`.
- **Touches:** R4.

#### 2. [MEDIUM/CONFIRMED] The R5 check misreads tab and no-break-space indentation, so a clause Markdown renders inside the last description passes
- **Where:** `tests/test_hygiene.py`, `statement_end_problems`, the indentation computed as
  `len(line) - len(line.lstrip())`. That counts a tab as one column, where CommonMark counts four,
  and it counts a no-break space as indentation, which CommonMark does not.
- **Failure scenario.** On the real `AGENTS.md` § Testing, the check passes each of these, and
  CommonMark places the added text inside the `integration` item:
  - a tab-indented `- except a test that needs nothing…` directly after the item;
  - a blank line, then a tab-indented exception paragraph.

  Planted forms also pass: a tab-indented third marker, a no-break space before `- except a gate`
  (a lazy continuation), and a ten-digit "ordered item" (also lazy). The controls behave correctly
  with spaces: a two-space paragraph after a blank line stays outside the item, and a four-space one
  is refused.

  So R5's "a clause … at the end" has a reachable form no row pins, and the hygiene entry's "the
  statement ends only where Markdown ends it" is false for these inputs.
- **Evidence:** `markdown_probe.log` (markdown-it-py renders, check verdicts).
- **Touches:** R5. This is the same property as cycle 1's "exception paragraph after a blank" note,
  fixed for spaces only.

#### 3. [MEDIUM/CONFIRMED] The diff's statements about the static launch check name one gap where many exist (cycle 1 finding 1, as a property)
- **Where:** three statements, each true only for the one gap it names:
  - `AGENTS.md:120-122` (the commands block): "its static check does not read a launch through
    conftest.REAL_POPEN";
  - `AGENTS.md:963-966` (the hygiene entry): it "does not read a call through `conftest.REAL_POPEN`";
  - `issues/marker-rule-gaps.md:36-40` (item 4): `sandbox_violations` "reads `subprocess`, `os`
    and `asyncio` calls and bare names imported from them".
- **Failure scenario.** Outside a `unit` function, `sandbox_violations` reads none of these launch
  forms:
  - `conftest.REAL_POPEN`;
  - a launcher bound by assignment, `getattr(subprocess, 'run')`, or a `Popen` subclass;
  - `pty.spawn` or `pty.fork`;
  - `os.fork` or `os.forkpty`, which falsifies the seed's "`os` … calls";
  - `multiprocessing.Process`, `posix.system`, or `_posixsubprocess.fork_exec`;
  - `loop.subprocess_exec`, which falsifies its "`asyncio` calls".

  All of these are latent: no `tests/*.py` uses one outside a `unit` function.

  On the guard side, every claim now made holds. `posix.system`, `posix.posix_spawn`, a ctypes
  `system` and `_socket.getaddrinfo` go through, but § Testing's general "what was bound before the
  test or sits below them is not refused" covers them. Two further routes reproduced and are not
  named where the seed lists the guard's gaps:
  - `site.USER_BASE` and `site.getuserbase()` return the real `~/.local`;
  - an exported non-XDG variable naming a real-home path (`GNUPGHOME`) reaches the test unchanged.

  The seed is the home that cycle 1 asked to "name every gap the wording now qualifies".
- **Evidence:** `static_probe.log`, `guard_probe.json`.
- **Touches:** R1/R4 through the wording that qualifies the rules. This is the ledger accuracy of
  `issues/marker-rule-gaps.md`.

#### 4. [LOW/CONFIRMED] Narrower carve-outs still survive the R5 rows (cycle 1 finding 3, as a property)
- **Where:** `tests/test_hygiene.py`, the R5 check (`described_markers`, `stated_markers`,
  `statement_end_problems`, the comparison) and its planted rows.
- **Failure scenario.** The reviewer's sweep left 69 survivors. Each one below has a concrete drift
  that the unmutated check refuses and the mutant passes (`witness.log`):
  - **Single punctuation ignored.** Any one of `; : ( ) ' " ’ ‘ “ ” _ ! ? [ ] § & — – < > # = + @ ~
    | \ {} $ % ^`. Of these, `;`, a lone `(` or `)`, and `§` appear in the real descriptions. The
    classes the rows do kill are the `()` pair, `/`, `-`, `,`, `.`, all quotes together, and the
    curly-quote fold.
  - **Folds and strips:** the double-quote class; folding en and em dashes to a hyphen; parentheses
    turned into commas; dropping zero-width or format characters; stripping Markdown links or HTML
    comments.
  - **Clause drops:** a trailing or leading parenthetical; text after an em dash, after ` -- `, or
    after a last `: `; a trailing `, except …`; a sentence in the middle.
  - **Structural:**
    - `entry.split(': ')` without maxsplit in `described_markers`, so pyproject can add
      `: except a gate`;
    - an entry with no `': '` read as `(entry, entry)`;
    - a statement repeated with the last one winning;
    - over-indented and whitespace-only continuation lines;
    - after a blank line, a line one column deeper than the items;
    - `LIST_ITEM` variants: no space after the marker, digits without a delimiter, `\s` after the
      marker, and a shallower line starting with a code span.

  R5 requires every carve-out "ignoring case, punctuation, whitespace beyond line wrapping, or a
  trailing clause" to be killed by a named row. These are reachable carve-outs of those kinds.
- **Evidence:** `mutants.log` (SURVIVED rows), `witness.log`.
- **Touches:** R5.

### Coverage observations and equivalent mutants (not findings)

- **Survivors with no wrong pass:**
  - `sm-rstrip`: its row refuses through the indentation shift, not the carve-out;
  - `sm-indent-fixed2` and `sm-cont-tab`: lenient, but consistent with Markdown;
  - stricter mutants with no accept row: `se-blank-following-none`, `se-blank-lt-needs-nonitem`,
    `re-list-only-dash`, `re-list-no-ordered`;
  - `re-list-hash`: correct for CommonMark;
  - `se-blank-tabs-as-1`: subsumed by finding 2.
- **Equivalent on every input:**
  - `sm-notitem-break`: the following line always starts a `- ` item at the statement's indent, so
    `statement_end_problems` flags it either way;
  - `re-item-search`: `.match` and `.fullmatch` agree, because `(.*)` ends the pattern and lines
    hold no newline;
  - `sm-cont-no-items-guard`: it raises instead of returning a violation, so the check fails
    either way.

### Unmapped changes

- The line added to `issues/stalled-reconnect-test-timing.md`.
- The `issues/marker-rule-gaps.md` seed and its `ROADMAP.md` entry. This is filing only, within
  the non-goals.

### Routing (to `code build`)

- **Finding 1 (property).** Every place in `AGENTS.md` that says what a marker means, or what an
  `integration` test is or does, states it in `pyproject.toml`'s terms. That includes prose outside
  the three named blocks. Find each by a search over the whole file, not by a list of locations.
- **Finding 2 (property).** The R5 check ends the statement exactly where CommonMark ends the last
  list item, for every whitespace form a line can start with: spaces, tabs, mixed, and Unicode
  spaces that Markdown does not count as indentation. Pin both sides:
  - a clause rendered inside the item is refused;
  - text that CommonMark places outside the item is accepted, with an accept row for each
    whitespace form.
- **Finding 3 (property).** Every statement the diff makes about what a hygiene check or the guard
  reads or refuses is true of the code over its whole domain. Where a statement names gaps, it
  either names them all or says it is not exhaustive and points at the seed. The seed's account of
  `sandbox_violations` and of the guard's open routes must survive an executed probe of every launch
  and every lookup form. Wording and ledger only, within the non-goals.
- **Finding 4 (surviving mutants).**
  - Run a mutant sweep over every decision of the R5 check, plus the additive carve-outs, each
    survivor killed by a named row or recorded as equivalent with the reason.
  - The single-character class is open-ended. The property is that the comparison ignores no
    character at all, so pin it over the whole domain rather than one character at a time.
  - The skill's structural rule applies: one decision, made once.

### Human-gate triggers

- **Not triggered.** No CONFIRMED finding touches a path on § Invariants' high-blast-radius list,
  and none violates a section tagged `[human gate]`.

### Escalation

- Cycle 2 has not converged. Cycle 1's findings 1 and 3 are open again as properties. The spec-held
  gates were green on classes the blind sweep then broke.
- Per the skill, this goes to the maintainer before a third build round. In particular, finding 4's
  open-ended character class asks whether R5's "every such carve-out is killed by a named row"
  should be met by one whole-domain property rather than per-carve-out rows. That is a contract
  reading, so it is his call.

## Review cycle 3 — changes-requested (2026-11-12)

- **Reviewed commit:** 3dcf07ee61d6c2ebd5f57755f9d5887583ebfdc5 · **Base:** develop · **Date:** 2026-11-12
- **Verdict:** changes-requested · **Cycle:** 3 of ≤3
- **Contract:** `GOAL.md` at HEAD, as in cycles 1 and 2. The only commit after the shape commit is
  `2258691`, the GOAL-gate clarifications.
- **Maintainer's readings applied to this cycle:**
  - R5 is one property over its whole domain: the comparison ignores nothing but line wrapping.
  - Mutants are graded by the mutation method's rule for a finished review. A survivor that pins a
    deeper layer of a class already pinned is a coverage observation, and it is seeded. Where R5's
    per-row wording is stricter than that rule, the rule governs.
- **Mode:** a fresh blind pass over the full spec-excluded diff by one reviewer at effort xhigh. It
  also re-checked cycle 2's findings 1–3 as properties. The gap statements were checked by an
  executed probe of the routes they name, not by a sweep. Evidence:
  - the reviewer's, in the gitignored `.local/review3/reviewer/`;
  - the orchestrator's gate log, in `.local/review3/orchestrator/gates.log`.

### Verification run

- **The orchestrator's spec-held gates** ran on `3dcf07e` before the reviewer started. Both exited 0:
  - `verify/gate.sh prepush` ran wording, slice (248 passed in each era), ids, sweep, scope and
    ledger. The sweep had 51 drift rows, 4 accept rows and 34 mutants, none left alive.
  - `remediation/checks.sh F1 F4 F5 F6 F7 F8` reported, by checker:
    - F5: 7 sentences read;
    - F6: 2,600 planted cases;
    - F8: 220 mutants (215 killed, 3 equivalent, 2 seeded, 0 not accounted for).
- **The profile's full `verify`** was not re-run in this cycle. It ran green on both eras in
  1,560 s (`.local/build3/full.log`, each era 4475 passed and 14 skipped). That run was on
  `7529196`'s tree. `3dcf07e` changes only this spec's `TECH.md`, so the tree outside `spec/` is
  the same.
- **The reviewer's runs:**
  - `uv lock --check`;
  - `tests/test_hygiene.py` in both eras, 248 passed each;
  - `-m unit` over the other files that read `AGENTS.md` or `pyproject.toml`, 849 passed;
  - a whole-suite collect under `--strict-markers` (5194 collected);
  - `bin/sandbox.sh uv run cluster-mcp --help`, exit 0;
  - the 106 marker tests (`01-marker-tests.log`).

  It did not use its one full-suite run.
- **CommonMark oracle:** markdown-it-py 4.0.0 in strict CommonMark mode. 45,600 cases cover each
  whitespace form, content, blank and nesting (`09-p2-oracle.log`, `10-p2-summary.log`). All 27 rows
  of `test_marker_statement_ends_where_markdown_ends_it` agree with it (`25-p2-rows-vs-commonmark.log`).
- **Probes of the claimed gaps** (`07-p3-static-probe.log`, `08-p3-guard-probe.log`):
  - static check: 12 forms are claimed unread and all 12 are unread; 13 are claimed read and all
    13 are flagged;
  - unit guard: 26 routes are claimed to pass and all 26 pass; 14 are claimed refused and all 14
    are refused.
- **Mutant sweep of the R5 check:** 119 mutants plus a baseline, at most 2 workers
  (`r5_mutants.py`, `13-r5-mutants.log`, `22-r5-killed-by.log`). 107 were killed, every one by a
  real test failure, and 12 survived. One "kill" in the first run was an artifact of the harness's
  `-k` filter; the reviewer fixed the runner and re-ran the whole sweep.
- **Spec ids:** none in the added lines of `tests/`, `pyproject.toml` or `AGENTS.md`
  (`06-spec-id-grep.log`).
- **Tree:** `git status --porcelain` was empty on hand-back. The temporary guard probe in `tests/`
  was removed and left no bytecode. No build state was mutated.

### Requirement → evidence matrix

No R-ID's deliverable is a `spec/` artifact. The blind reviewer verified every row, and the
orchestrator re-read the cited logs for finding 1.

| R-ID | Status | Verified how (by the reviewer) |
|------|--------|--------------------------------|
| R1 | ✅ | `pyproject.toml:51` names no process, no connection (a name lookup included) and no real HOME, and says nothing of "fast". The "except on the open routes" clause holds under the guard probe (`08`, `16-collect-only.log`). |
| R2 | ✅ | `pyproject.toml:52`: "needs what a unit test is refused"; keeps the sandbox rule; says nothing of a CLI. |
| R3 | ✅ | Kinds 1–6 and 9 each need a process; kind 7 needs a connection; kind 8 is "itself or through a fixture or helper". There is no exception clause, and a test needing none of these fits `unit`. |
| R4 | ✅ | § Testing, the commands block, § Conventions and `AGENTS.md:1670-1673` restate the markers. No text left in the file defines an `integration` test as a CLI drive (whole-file greps `02`–`04`). The "drives no CLI" note is gone. |
| R5 | ⚠️ finding 1 | `tests/test_hygiene.py:409-826`, a `unit` test with every row R5 names. The unmutated check accepts no drift CommonMark renders into the statement. It refuses one clean end CommonMark accepts. |

### Cycle-2 findings

| Cycle 2 | Status at `3dcf07e` | Evidence |
|---|---|---|
| 1. `AGENTS.md` still defines `integration` as a CLI drive | **Closed.** The remaining mentions describe particular tests truly (`:608`, `:659`, `:1105`). | `02`–`04-*.log` |
| 2. The statement end misreads tab and no-break-space indent | **Drift side closed. Accept side open** (finding 1). | `09`, `10`, `11`, `12`, `25` |
| 3. The gap statements name one gap where many exist | **Closed.** Every claimed route behaves as claimed, and each gap statement says it is not exhaustive and points at the seed. One ledger sentence is still inexact (finding 3). | `07`, `08` |
| 4. Narrower carve-outs survive | **Closed under the maintainer's reading.** No survivor is CONFIRMED. Ten are deeper layers of pinned classes; two of those are already seeded and eight are still to be seeded. The other two survivors are equivalent for drift. | `13`, `17`, `19`, `22`, `24` |

### Findings

#### 1. [MEDIUM/CONFIRMED] The R5 check refuses a clean statement end that CommonMark accepts: text one column deeper than the items after a blank line
- **Where:** `tests/test_hygiene.py:481-483`, `statement_end_problems`, the branch for a line after a
  blank one. It accepts text that starts no item only when that text is no deeper than the items.
- **Failure scenario.** After a blank line, take text that starts no item and sits exactly one
  column deeper than the statement's items:
  - 3 spaces at the top level;
  - 5 columns nested, written as 5 spaces, `' \t '`, `'\t '` or `'    '`.

  CommonMark renders it as a paragraph of the enclosing bullet, after the list. The check refuses
  it with "a line after a blank one joins the statement". No drift gets through. The error is a
  false red on a valid layout.
- **What it contradicts.**
  - The accept side of the property cycle 2 routed ("text that CommonMark places outside the item
    is accepted").
  - The test's own comment at `tests/test_hygiene.py:709-711`.
  - `AGENTS.md:1003-1006`, whose "Two shapes are read otherwise than Markdown renders them" reads
    as the whole list and is not.
- **Evidence:**
  - `12-p2-one-deeper.log`: the rendered HTML beside the check's verdict, re-read by the
    orchestrator;
  - `09-p2-oracle.log`, `10-p2-summary.log`, `11-p2-nbsp-over.log`.

  Mutant `end-blank-plus-one` accepts up to the items' depth plus one for text that starts no item.
  It passes all 106 marker tests and lets no drift through under the oracle
  (`18-r5-accept-side-mutants.log`).
- **Touches:** R5. This is the same property as cycle 2's finding 2, on the accept side.

#### 2. [LOW/CONFIRMED] The deeper-carve-outs seed's title and roadmap entry call a test-coverage gap a fault of the check
- **Where:** `issues/marker-statement-deeper-carve-outs.md:8` (title) and `ROADMAP.md:239-243`.
- **Failure scenario.** Both say the check "passes three shapes CommonMark renders differently".
  The first shape, an em dash against a hyphen, is refused by the unmutated check. Only a
  dash-folding mutant passes it, and it is not a rendering difference. The seed's body states it
  correctly ("a check that folds…").
- **Evidence:** `17-r5-survivor-drifts.log` (`cmp-dash-fold`: the unmutated check refuses).
- **Touches:** the ledger. This is a seed that misstates its defect (rubric, *What the reviewer sees*).

#### 3. [LOW/CONFIRMED] The marker-rule-gaps seed says only one unread launch form is in use
- **Where:** `issues/marker-rule-gaps.md:50-52`, "Only the first is in use … The rest are latent".
- **Failure scenario.** Two more unread forms are in use outside a `unit` function:
  - a launcher bound by assignment (`tests/test_hygiene.py:971-973`), which the `executes` fixture
    refuses at run time;
  - `Popen` subclasses that launch (`tests/conftest.py:483`, `:491`), which enforce the sandbox at
    run time.

  None of them launches outside `bin/sandbox.sh`, so the seed's point holds: only `_host` does.
  But the seed's own fix, flagging a launch by each route it lists, would flag these three sites
  too, and the seed does not say so.
- **Evidence:** `05-unread-forms-in-use.log`, `07-p3-static-probe.log`.
- **Touches:** the ledger, as cycle 2's finding 3 did.

### Surviving mutants (none CONFIRMED)

| Survivor | Drift it passes | Classification |
|---|---|---|
| `cmp-dash-fold` | an em dash against a hyphen | deeper layer of the Unicode-fold class; seeded (`issues/marker-statement-deeper-carve-outs.md` item 1) |
| `sm-rstrip` | trailing spaces on the statement line move the items' indent | seeded (same seed, item 2) |
| `cmp-strip-arrows` | `→` inserted | deeper layer of the insertion class `EDIT_ALPHABET` pins (a character outside the alphabet); to seed |
| `cmp-strip-cjk-punct` | `、` inserted | same as `cmp-strip-arrows`; to seed |
| `desc-name-only-skipped` | a bare `"beta"` added to `markers` | deeper layer of the third-marker rows; to seed |
| `sm-strip-quote-marker` | the statement line inside a blockquote | deeper layer of `statement-line-quoted`; to seed |
| `sm-blank-wrap-ok` | a line of spaces splitting a description | deeper layer of the blank-wrap and whitespace rows; to seed |
| `end-follow-next-line-only` | two blank lines, then a clause in the last item | deeper layer of `clause-after-a-blank-in-last-item`; to seed |
| `li-no-eol` | a bare `-` line that renders a third item | deeper layer of the third-marker-after-a-blank rows; to seed |
| `sec-any-level` | a second, drifted statement under a `###` in § Testing | deeper layer of `stated-twice`; to seed |
| `end-blank-plus-one` | none | equivalent for drift; it is finding 1's fix |
| `li-dot-only` | none | equivalent for drift; it only moves accept-side refusals |

### Coverage observations (not findings)

- **Over-claimed control.** `AGENTS.md:1013-1016` says
  `test_marker_statement_check_refuses_every_edit` "holds the comparison to ignoring nothing but line
  wrapping". The unmutated comparison does ignore nothing else. The control, though, does not kill
  every mutant that ignores something: the fold survivor and the two out-of-alphabet survivors
  show it. The wording should say what the control proves when those survivors are seeded.
- **Block-starter refusals.** Some block starters that CommonMark places outside the list are
  refused by the check: `> x`, a fence, a thematic break, an HTML comment, ` # x`, and `* item` at
  the items' indent. These fall outside the whitespace property, and in part the
  `third-marker-other-bullet` row asks for them.

### Unmapped changes

- The dated line added to `issues/stalled-reconnect-test-timing.md`.
- The new seeds and their `ROADMAP.md` entries: filing only. `issues/integration-marker-check.md`
  is the one Q1 requires.

### Routing (to the maintainer; MEDIUM stops for routing)

- **Finding 1 (property).** The statement ends exactly where CommonMark ends the last item. A line
  after a blank one that starts no item joins the statement only at or past the items' text
  column (indent + 2 for `- `), never at indent + 1. Pin the accept side for every whitespace form
  at that depth, nested and top level. Then correct `AGENTS.md:1003-1006` so that its list of open
  shapes is exact or says it is not exhaustive.
- **Findings 2 and 3 (ledger).** Retitle the seed and its roadmap entry: one coverage gap and two
  rendering shapes. Name the three in-use sites the seed's fix would also flag.
- **Survivors.** Seed the eight unseeded deeper layers, either into
  `issues/marker-statement-deeper-carve-outs.md` or into a sibling seed with its own `ROADMAP.md`
  entry. Reword the over-claimed control at the same time.

### Human-gate triggers

- **Not triggered.** No CONFIRMED finding touches a path on § Invariants' high-blast-radius list,
  and none violates a section tagged `[human gate]`.

### Escalation

- This is the third and last cycle the bound allows, and it has not converged: one MEDIUM finding
  is open. It is the accept side of cycle 2's finding 2, and it lets no drift through. Whether a
  fourth build round runs, and how finding 1 is routed, is the maintainer's call.
