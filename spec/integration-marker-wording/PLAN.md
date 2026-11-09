# PLAN — The test markers say what the unit guard enforces

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). No `research/` (lean path); the gates and
> the drafts they were dry-run on are in [`verify/`](verify/). Every design element traces to a GOAL R-ID.

## 1. Summary

Rewrite the two `markers` descriptions in `pyproject.toml` as the rule each marker carries (a `unit`
test starts no process, opens no network connection, a name lookup included, and sees no real HOME;
an `integration` test needs one of those, and every process it launches goes through
`bin/sandbox.sh`), state them word for word in `AGENTS.md` § Testing and § Conventions, point the
development commands at them, and drop the exception note. One `unit` test in
`tests/test_hygiene.py` holds both `AGENTS.md` statements to `pyproject.toml`, with 51 planted
drifts, each the row that kills a named mutant of the check: a mutated decision, or a carve-out the
check could grow (34 mutants). Every claim the wording makes about the guard was proven by an
executed probe against `tests/conftest.py`; the routes the probe found open are named beside the
guard and filed as the seed `issues/marker-rule-gaps.md`. Three phases, test and docs only: it fits
`small`.

## 2. Design

### The descriptions (`pyproject.toml`, R1–R3)

```toml
markers = [
    "unit: starts no process, opens no network connection (a name lookup included) and sees no real HOME; the unit guard holds it to that",
    "integration: needs what a unit test is refused (a process, a network connection or name lookup, or the real HOME), itself or through a fixture or helper; every process it launches goes through bin/sandbox.sh",
]
```

`unit` names the three things R1 lists and no speed (Q2). "The unit guard holds it to that" names
the enforcer without claiming it closes every route (§ 3, row 3). `integration` is defined by need,
not by what the test drives (R2), keeps the per-launch sandbox rule word for word as the suite's
rails state it, and says "itself or through a fixture or helper" so R3's kind 8 is in the text, not
inferred. `pytest --markers` prints both lines as written.

**R3, each kind against the wording.** Kinds 1–6 and 9 start a process (a CLI drive, git or a login
shell, a child interpreter, an `hdiutil` stand-in, the `executes` backends' bash, a stdio server, a
killed or timed-out sandboxed child); kind 7 opens a network connection (loopback TCP: the probe
shows the guard refuses `create_connection`, `socket.connect` and `asyncio.open_connection` to
127.0.0.1); kind 8 is "itself or through a fixture or helper". Each needs "what a unit test is
refused", so each is `integration` with no exception clause. A test that needs none of them, and so
sees no real HOME, matches `unit` and not `integration`.

### `AGENTS.md` (R4)

- **§ Testing, the marker bullet** (today `:304–307`): after "each select a real subset" it adds that
  a test that is not `unit` is `integration` (the guard is inactive for it), then the statement:

  ```
    Each marker means what its description in `pyproject.toml` says, word for word:
    - `unit`: starts no process, opens no network connection (a name lookup included) and sees no
      real HOME; the unit guard holds it to that
    - `integration`: needs what a unit test is refused (a process, a network connection or name
      lookup, or the real HOME), itself or through a fixture or helper; every process it launches
      goes through bin/sandbox.sh
  ```

  then a blank line and one line naming the test that holds it (without the blank line, CommonMark
  renders that line as part of the `integration` item; review finding 1). No backticks inside the
  descriptions: they are `pyproject.toml`'s text, which has none, and markup counts.
- **§ Conventions, the marker bullet** (today `:3122–3125`): the same statement, verbatim, after its
  last sentence.
- **The development commands** (`:108–118`): the `-m unit` comment adds "each means what its
  pyproject.toml description says (§ Testing)"; the sandboxed `-m integration` example adds that
  wrapping the whole run is a choice for a manual run, and the rule the suite enforces is per launch:
  "every process an integration test launches goes through bin/sandbox.sh". The block restates no
  description (deviation row 1).
- **§ Testing, the `tests/test_registry.py` entry** (`:342`): "is `integration` although it drives no
  CLI, and" becomes "is `integration`, and".
- **§ Testing, the rails' unit-guard bullet** (`:1472`): one sentence naming the routes the probe
  found open (what was bound before the test or sits below the replaced names: an early-bound
  `Popen` class such as `conftest.REAL_POPEN`; a `_socket` connect, a UDP `sendto`, an early-bound
  `getaddrinfo`; the `gethostbyname` family; a wider fixture's launch) and the seed
  `issues/marker-rule-gaps.md`. **§ Testing, the `tests/test_hygiene.py` entry** (`:950`): `test_cli_drives_are_sandboxed`
  does not read a call through `conftest.REAL_POPEN`, which `_host` uses for `hdiutil`, outside the
  sandbox (the seed); in P2, the new check's name, test and controls.

The exact text is [`verify/draft/apply_edits.py`](verify/draft/apply_edits.py), the edits the gates
passed on.

### The check (`tests/test_hygiene.py`, R5)

Inserted after `test_unit_guard_redirects_home` (`:395`), plus `import tomllib`; nothing existing
changes. Reference text: [`verify/draft/check_block.py`](verify/draft/check_block.py).

- `MARKERS_STATED` — the statement line, matched as a whole line after its indentation, exactly once
  per section.
- `described_markers(pyproject)` — each `markers` entry split at its first `": "` into name and
  description, in order; an entry without `": "` keeps an empty description (so `"unit:x"` drifts).
  No stripping.
- `stated_markers(section)` — after the statement line, items `` - `<name>`: <description> `` at the
  line's own indentation, each continued by lines exactly two spaces deeper whose next character is
  not a space; each line break becomes one space. A line at item indentation starting `- ` that is
  not that shape is a violation. **Line wrapping is the only freedom**: case (names too),
  punctuation, markup, a no-break space, a decomposed character, a tab, a doubled or trailing space
  and an over-indented wrap all count.
- `statement_end_problems(after, indent)` — the statement must end where Markdown ends it: at the
  section's end, at a list item less indented than its own, or at a blank line followed by text no
  deeper than its items that starts no item there. Any other line (a lazy continuation at any
  indentation, a paragraph or an item after a blank, a `*`, `+` or numbered bullet) would render as
  part of the last description or as another marker, and is a violation.
- `agents_section(agents, heading)` — from `## Testing` / `### Conventions (same-commit rules)` to
  the next heading of that level or higher.
- `marker_statement_violations(pyproject, agents)` — no markers described is a violation; for § Testing
  and § Conventions each, the section's problems, then the stated and described lists compared item
  by item in order, one line per position that differs (a missing, extra, reordered or repeated
  marker each shows there).
- `test_the_markers_are_stated_as_pyproject_describes_them` (`unit`) — the live files, no violations.
- `test_marker_statement_check_accepts_a_rewrapped_statement` (`unit`, 4 rows: `as-planted`,
  `rewrapped`, `unwrapped`, `paragraph-after-a-blank`) — positive controls on a planted pair.
- `test_marker_statement_check_catches_planted_drift` (`unit`, 51 rows) — negative controls on the
  same planted pair (a small `pyproject.toml` and an `AGENTS.md` with § Testing, § Packaging,
  § Conventions and a later section, each block holding two markers whose descriptions carry a
  capital, parentheses, a comma, a semicolon, a path and a wrap). Every row is the named killer of at
  least one mutant below; R5's rows map as: pyproject alone `changed-in-pyproject`; `AGENTS.md` alone
  `changed-in-testing`, `changed-in-conventions`; either missing `missing-from-testing`,
  `missing-from-conventions`, `missing-from-pyproject`, `one-missing-from-*`,
  `statement-without-items`; a third marker `third-marker-in-pyproject`, `third-marker-in-testing`;
  additive clauses `clause-at-{start,middle,end}-in-{pyproject,testing}`; and the carve-out rows
  (`case-*`, `punctuation-*`, `double-space-*`, `tab-in-testing`, `trailing-space-*`,
  `two-spaces-after-name-in-testing`, `no-space-after-name-in-pyproject`,
  `over-indented-wrap-in-testing`, `no-break-space-in-testing`, `markup-in-testing`,
  `emphasis-in-testing`, `reordered-in-testing`, `repeated-in-*`, `stated-twice`,
  `statement-line-reworded`, `name-changed-in-testing`, `item-without-backticks-in-testing`,
  `item-over-indented-in-testing`, `name-case-in-testing`, `trailing-period-in-testing`,
  `decomposed-in-testing`, `statement-line-trailing-space-in-testing`,
  `statement-line-tab-indented-in-testing`); and the statement's end
  (`clause-lazy-after-last-item`, `clause-at-item-indent-after-last-item`,
  `clause-over-indented-after-last-item`, `clause-after-a-blank-in-last-item`,
  `third-marker-after-a-blank-in-testing`, `third-marker-other-bullet-in-testing`). The ids are
  [`verify/drift-ids.txt`](verify/drift-ids.txt).

### The mutant sweep (R5, `verify/marker_mutants.py`)

34 mutants, each a source substitution on the staged `tests/test_hygiene.py`, run in a scratch tree
from the index with no bytecode written; each must turn every row it names red (failed or errored:
skipped is not killed), must leave the accept row `as-planted` green unless it names an accept row
(a mutant that breaks everything proves nothing about its rows), and every drift row must be named by
some mutant (a row no mutant needs is one R5 does not admit). Dry run on the prototype's P2 tree: 34 of 34 killed (about 50 s).

| Kind | Mutant | Killed by |
|---|---|---|
| decision | `testing-only`, `conventions-only` (one section read) | `changed-in-conventions`, `missing-from-conventions`; `changed-in-testing`, `missing-from-testing` |
| decision | `whole-file-first-statement` (first statement anywhere) | `missing-from-testing`, `changed-in-conventions` |
| decision | `section-runs-to-end` | accept row `as-planted` |
| decision | `first-of-several` (two statement lines allowed) | `stated-twice` |
| decision | `names-only` | `changed-in-*` |
| decision | `item-indent-free` | `item-over-indented-in-testing` |
| additive: either side missing | `silent-section-passes`, `silent-pyproject-passes` | the `missing-*` rows, `statement-without-items`, `statement-line-reworded`, `item-without-backticks-in-testing` |
| additive: a third marker | `extra-stated-ignored`, `extra-stated-ignored-too`, `extra-described-ignored`, `two-markers-only` | `third-marker-in-*`, `one-missing-from-*` |
| additive: order, repeats | `order-free`, `mapping` | `reordered-in-testing`, `repeated-in-*` |
| additive: case | `casefold` | `case-in-pyproject`, `case-in-testing` |
| additive: punctuation | `punctuation-free` | `punctuation-in-*` |
| additive: markup | `markup-free` (backticks, asterisks) | `markup-in-testing`, `emphasis-in-testing` |
| additive: whitespace beyond wrapping | `whitespace-free` (the id-rule check's own normalisation), `unicode-compatible` (NFKC), `wrap-indent-free`, `separator-free` (pytest's own `:` split and strip) | `double-space-*`, `tab-in-testing`, `trailing-space-*`, `two-spaces-after-name-in-testing`, `no-break-space-in-testing`, `decomposed-in-testing`, `over-indented-wrap-in-testing`, `no-space-after-name-in-pyproject` |
| additive: a clause | `trailing-clause` (prefix), `leading-clause` (suffix), `middle-clause` (word subsequence) | `clause-at-end-*`; `clause-at-start-*`; all six `clause-*` |
| additive: the statement line and names | `statement-line-free`, `statement-line-whitespace-free`, `name-stripped`, `name-shape-free`, `name-casefold` | `statement-line-reworded`, `statement-line-trailing-space-in-testing`, `statement-line-tab-indented-in-testing`, `name-changed-in-testing`, `item-without-backticks-in-testing`, `name-case-in-testing` |
| additive: punctuation, unicode | `trailing-period-free`, `composed-equal` (NFC) | `trailing-period-in-testing`, `decomposed-in-testing` |
| additive: a clause or marker after the statement | `statement-end-free` (the statement ends silently anywhere), `blank-ends-statement` | the six end rows; `clause-after-a-blank-in-last-item`, `third-marker-after-a-blank-in-testing` |

Each one-sided carve-out (on the `AGENTS.md` side only, or `pyproject.toml` only) is killed by a row
planted on the other side or by `as-planted`, whose descriptions carry a capital and punctuation.

### The probe (`verify/guard_claims.py`)

Run against `tests/conftest.py` itself (`pytest -p conftest`, outside `tests/`, so no suite collects
it). Proven refused in a `unit` test: `subprocess.run`, `os.system`, `os.fork`, `os.posix_spawnp`,
`multiprocessing` (fork and spawn), a process pool, `asyncio.create_subprocess_exec`;
`create_connection`, `socket.connect` and `asyncio.open_connection` to a listening 127.0.0.1 port;
`getaddrinfo` and asyncio's; HOME, `Path.home()`, `~` and the three XDG variables under `tmp_path`,
`BLANKED_ENV` unset. Proven inactive for an `integration` test. **Found open** (each row asserts it
stays open, so a fixed guard turns the probe red and the wording is revisited): a `Popen` class
bound before the test (`subprocess` binds `_posixsubprocess.fork_exec` at import, so neither
attribute patch reaches it) including `conftest.REAL_POPEN`; a `_socket.socket` connect to
127.0.0.1, a UDP `sendto`, an early-bound `getaddrinfo` (review finding 7); `gethostbyname`,
`gethostbyname_ex`, `gethostbyaddr`, `getnameinfo`; a module-scoped fixture's launch; the password
database's home. And `sandbox_violations` does not read a `REAL_POPEN` call. The probe also asserts each phrase the
descriptions claim appears in them and the refused words do not ("fast"; "CLI", "drives").

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | the `unit` description; probe rows for each claim; `test_the_descriptions_make_the_proven_claims[unit]` (no "fast") |
| R2 | the `integration` description; probe `[integration]` row (no "CLI", "drives"; keeps the sandbox clause) |
| R3 | both descriptions read together, kind by kind (above); kind 8 named in the text |
| R4 | § Testing and § Conventions statements; the development commands' pointer and per-launch sentence; the `test_registry.py` note dropped; `gate.sh wording` |
| R5 | `marker_statement_violations` and its three tests; 51 drift rows each killing a named mutant; 34 mutants in `verify/marker_mutants.py` |

## 3. Invariant gate (AGENTS.md constitution check)

Checked against `AGENTS.md` § Invariants before design and again after this design was drafted. No
numbered section (§1–§9) is touched: nothing under `packages/`, and no path on the high-blast-radius
list (`bin/sandbox.sh` is read, never changed). Research triggers 1 and 2 do not fire; trigger 3 does
(R5's check is a gate), so the adversarial review ran (§ 4).

- **§ Conventions, markers** — the three new tests are `unit`; no gate is a marker selection (the
  gate names every id it depends on, `verify/drift-ids.txt`).
- **§ Conventions, pure check functions with standing negative controls** — `marker_statement_violations`
  and its planted rows; the names and row ids are a contract.
- **§ Conventions, no spec ids** — none in code, strings or row ids (`test_no_spec_ids_…` reads the module).
- **§ Conventions, same commit** — each phase's `AGENTS.md` § Testing text lands with the code it
  describes; P2's test entry with the check.
- **§ Conventions, CI mirrors the gate** — no suite command changes; the tests join
  `tests/test_hygiene.py` in each era's fourth command.
- **§ Testing, the rails** — the guard, the collection hook, `sandbox_violations` and `bin/sandbox.sh`
  are unchanged (non-goal); the new code launches nothing and reaches no host.
- **§ Factory, `ci budget`** — cost below (§ 5), for the maintainer.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **1 — R4 in the development commands is a pointer, not a restatement.** The block's comment says each marker means what its `pyproject.toml` description says (§ Testing), and states the sandbox rule in the description's own words ("every process an integration test launches goes through bin/sandbox.sh"); it does not copy either description. **A reading of R4 for the sign-off.** | The block is shell comments, which the check does not parse; a full copy there is a third statement nothing holds to the other two. The block's only claim about meaning today is the wrapped `-m integration` run, which R4's problem names; the new sentence settles that reading. | A verbatim copy in comments: an unchecked duplicate that drifts. Extending the check to parse shell comments: a second statement format, with its own carve-outs to kill, for a pointer's worth of content. |
| **2 — The check holds § Conventions too**, beyond R5's § Testing. | R4 names § Conventions' marker bullet as a place that says what a marker means; holding it as the id-rule precedent holds both sections keeps R4 from drifting there. | § Testing only: § Conventions would carry an unchecked copy, or no statement and an R4 reading. |
| **3 — The descriptions state rules the guard does not close on every route.** The probe found open in a `unit` test: an early-bound `Popen` class (`conftest.REAL_POPEN`); a `_socket` connect, a UDP send and an early-bound `getaddrinfo`; the `gethostbyname` family; a wider fixture's launch. The `unit` description says the guard "holds it to that", not that it refuses every route; § Testing names the open routes beside the guard; the seed `issues/marker-rule-gaps.md` (R1–R4) closes them. | R1 requires "a name lookup included" and "starts no process"; the guard may not change here (non-goal). | Narrowing the wording to the routes refused (`getaddrinfo`, attribute-bound `Popen`): R1 fails as worded, and a description listing entry points is not a rule a reader can apply. Claiming the guard refuses every route: false, by the probe. |
| **4 — The `integration` sandbox clause is broken today by `_host`**, which runs `hdiutil` through `conftest.REAL_POPEN` outside `bin/sandbox.sh`, a call `sandbox_violations` does not read; `full-volume-fixture-leaks-hdiutil` plans its 16 stand-in rows the same way. R2 keeps the clause; § Testing's `tests/test_hygiene.py` entry now says what the static check does not read; the seed `issues/marker-rule-gaps.md` carries the fix. R3's kind 4 is classified `integration` by the wording (it starts a process), which is all R3 asks. **For the foreman: the sibling's design contradicts the clause this cycle settles.** | R2 requires the clause; the non-goals forbid changing `sandbox_violations`, and `_host` belongs to the sibling's fixture. | An exception clause for host tools: R3 forbids it. Dropping the clause: R2 forbids it. Routing `_host` through the sandbox here: outside this cycle's paths and the sibling's region. |
| **5 — Order counts, and repeats count.** The statement lists the markers in `pyproject.toml`'s order; a repeated entry on either side is drift. | "Word for word" of a list includes its order; a mapping comparison collapses a repeat and lets one side list a marker twice. | Order-free mapping: the `order-free` and `mapping` mutants are then the check, and a repeated or shuffled statement passes. |
| **6 — Positive controls are a test of their own** (`…accepts_a_rewrapped_statement`, 4 rows; corrected from "3 rows" at the PLAN/TECH gate, 2026-11-09). | R5 says each row of the drift controls is one a carve-out mutant passes; an accept row is not, so it does not sit among them. Wrapping must still be pinned as allowed, or a stricter mutant (raw-line compare) survives. | Accept rows mixed into the drift table: they would be rows no mutant names. |
| **7 — The probe and the draft check live in `spec/…/verify/`, not the suite.** | The probe asserts routes stay open, a fact about the guard the non-goals keep, not a rule to pin; moving it in is the seed's R4 (`issues/marker-rule-gaps.md`). | A suite test pinning open routes: it would go red on the fix the seed asks for. |
| **8 — The gate's oracles are frozen at the plan commit.** After it, a phase may change no file under `spec/…/verify/` but `mutant-sweep.md`, and `tests/test_hygiene.py` may only add lines, never binding an existing top-level name again (`scope-P<n>`). Build writes the check so the sweep's substitutions apply; one that cannot is a stop for the foreman, not a re-key. | Review finding 5: a build free to edit `drift-ids.txt`, the mutant table or the draft could drop a row and its mutant together and stay green, and an added `def sandbox_violations(...)` would neuter a kept rail while `ids` still passes. | Re-keying by build (the first draft's rule): the gate would grade a design the gate's author no longer controls. |
| **9 — The statement ends where Markdown ends it**, and a blank line follows § Testing's statement. | Review findings 1 and 2: a line right after the last item, at any indentation, is a CommonMark lazy continuation of it (the first draft's own § Testing text rendered its trailing sentence inside the `integration` description), and an item after a blank line, or a `*` bullet, renders as a third marker. | Ending the statement at any unread line (the first draft): the check passed a clause rendered inside the last description, and a third marker. |

## 4. Rabbit holes (resolved)

- **What the guard refuses, against the wording.** Settled by an executed probe, not by reading:
  three routes are open (deviation row 3), and `_host` breaks the sandbox clause (row 4). The probe's
  output is gated (`gate.sh wording`).
- **What "word for word" tolerates.** Only line wrapping, defined exactly (a break plus the item's
  continuation indent is one space). The id-rule precedent's `' '.join(text.split())` is itself a
  carve-out here (`whitespace-free`), killed by six rows.
- **Rows that pass for the wrong reason.** The sweep found two on its first run: rows whose planted
  change failed the check for a reason other than the one they name (a clause row that also changed
  case; a comparator mutant applied to a tuple's `repr`). Both were fixed, and every drift row is
  now required to be some mutant's named killer.
- **Adversarial review.** See § 4a.

### 4a. Adversarial design review

One fresh reviewer, one pass (appetite small), given the GOAL, this PLAN, every drafted gate, the
drafts and the prototype tree. It reported two HIGH and five MEDIUM findings, and all are folded in:

1. **HIGH** — the check ended the statement silently at any unread line, so a clause after the last
   item (a CommonMark lazy continuation) passed, and the draft's own § Testing text rendered its
   trailing sentence inside the `integration` description. → `statement_end_problems`, a blank line
   in § Testing, four end rows, mutants `statement-end-free` and `blank-ends-statement` (row 9).
2. **HIGH** — a third marker after a blank line, or as a `*`/`+` bullet, passed. → the same end
   rule; rows `third-marker-after-a-blank-in-testing`, `third-marker-other-bullet-in-testing`.
3. **MEDIUM** — additive carve-outs no row killed: names' case, a trailing period, a stripped or
   tab-indented statement line, NFC. → five rows and mutants `name-casefold`,
   `trailing-period-free`, `statement-line-whitespace-free`, `composed-equal`.
4. **MEDIUM** — the ledger flagged PLAN § 6's own description and missed the real deferrals. → it
   now reads "seed" and "filed" too, and checks this cycle's seeds (`issues/marker-rule-gaps.md`,
   `issues/integration-marker-check.md`) committed, unshaped and indexed whatever the prose says.
5. **MEDIUM** — scope let build edit the gate's oracles, and "only adds" let an added line rebind a
   kept rail. → row 8.
6. **MEDIUM** — the pytest parts read the working copy while the checks read the index. → every gate
   part first refuses a tree with unstaged or untracked changes.
7. **MEDIUM** — the probe missed open routes (`_socket` connect, UDP `sendto`, early-bound
   `getaddrinfo`). → probe rows, § Testing's sentence and the seed `issues/marker-rule-gaps.md` name them.
8. **LOW** — sweep mechanics (skipped counted as killed; a mutant breaking everything counted;
   bytecode staleness). → fixed as above. **LOW** — `prepush`/`P3` skipped `slice`; the R4 note check
   matched one literal; `slice` read one marker line. → fixed. Left as design: the statement line
   cannot wrap (fails safe); a copy elsewhere in `AGENTS.md` is unchecked (row 1); the wording does
   not name `BLANKED_ENV` (R1 does not ask it).

The reviewer found sound: the draft equal to the staged block, TOML string forms compared as parsed
values, every in-item carve-out the first table named, legitimate rewraps, the `executes` fence for
kind 5, the gate's shell structure, the `ids` junit parse, and all 28 first-draft mutants killed.

## 5. Risks & open questions

- **CI cost (maintainer's figure).** 56 new `unit` cases in `tests/test_hygiene.py`, in
  `suite-legacy-4` and `suite-modern-4` (baseline 7:22 and 7:33). Measured on a development Mac
  (mac-m2), two runs each: the module took 2.08 s and 2.10 s before (84 cases) and 1.98 s and 2.07 s
  after (140 cases); the 56 new cases alone 0.11–0.44 s over three runs. Before → after per job: the
  module's share moves by under half a second, inside run-to-run noise; no job's 10-minute budget
  is approached by it. The maintainer's call.
- **Overlaps.** `AGENTS.md` § Testing is edited by `annotation-check` (a `tests/test_annotations.py`
  entry), `full-volume-fixture-leaks-hdiutil` (the `tests/test_ssh_exec.py` entry),
  `mutant-child-outlives-timeout` and `sandbox-dirs-left-on-kill` (their module entries); this cycle
  edits the marker bullet, the `test_registry.py` note, the `test_hygiene.py` entry and the rails'
  guard bullet, so conflicts are textual and local. `tests/test_hygiene.py` is edited by
  `skip-check-fence-gaps` around the id-rule check and `test_only_need_shell_skips` (`:696`, `:862`);
  this cycle inserts after `:405` and adds one import, so the hunks are disjoint, and its new code has
  no skip for `skip_violations` to read. `ROADMAP.md`'s three entry counts are edited by
  `skip-check-fence-gaps` too (26 → 28); whichever lands second recounts. The sandbox clause and
  `full-volume-fixture-leaks-hdiutil`'s `REAL_POPEN` rows: deviation row 4.
- **A mutated wording passes the probe's phrase check** if it keeps the phrases and adds a claim the
  probe does not test (a new clause). The word-for-word check does not catch that (it compares two
  copies); review does, against the probe's list.
- **The sweep is keyed to the draft's text** and frozen (row 8): build writes the check so every
  substitution applies once, or stops; the sweep's `STALE` line is red.

## 6. Verification strategy

No CLI behaviour changes; the proof is text and tests. Each phase's gate is
[`verify/gate.sh`](verify/gate.sh) (`main "$@"; exit $?`), reading the index:

- `wording` — the probe on `tests/conftest.py` (claims proven, open routes still open, claimed
  phrases present, refused words absent), then the drafted check run on the staged `pyproject.toml`
  and `AGENTS.md`, plus the development commands' two sentences, the § Testing gap sentences and the
  removed note.
- `slice` — `tests/test_hygiene.py` in both eras; `pytest --markers` prints the new `unit` line.
- `ids` — junit in both eras: the live test, the 4 accept rows, the 51 drift rows of
  `drift-ids.txt` exactly, and the kept rails (`test_the_id_rule…`, `test_no_spec_ids…`,
  `test_cli_drives_are_sandboxed`, `test_only_need_shell_skips`) all passed.
- `sweep` — 34 of 34 mutants killed by their named rows, `as-planted` green under each; no idle
  drift row.
- `scope-P<n>` — files changed since the plan commit: P1 `pyproject.toml`, `AGENTS.md`; P2 adds
  `tests/test_hygiene.py`, which only gains lines and binds no existing top-level name again; P3 may
  add `ROADMAP.md` and an `issues/` file; `pyproject.toml` changes exactly two lines; no
  gate file but `verify/mutant-sweep.md`; never `tests/conftest.py`, `bin/sandbox.sh`, `packages/`,
  `.github/`, `uv.lock`.
- `ledger` — every PLAN and TECH paragraph or item that mentions a seed, a filing or a deferral names
  a committed `issues/` seed with a ROADMAP entry, and this cycle's two seeds
  (`issues/marker-rule-gaps.md`, `issues/integration-marker-check.md`) are committed, unshaped and
  indexed.
- Every part refuses a tree with unstaged or untracked changes, so pytest and the index agree.
- `full` — the profile's `verify`, word for word.

Dry runs on a detached prototype worktree (`integration-marker-wording-proto`, removed after), each
on a signed stand-in plan commit carrying these files, cut back per phase and staged:

- **Base tree (no edits), `gate.sh P1`:** red, as it must be: `wording`'s claim rows fail on the old
  descriptions (`fast`, `drives the installed CLI`).
- **P1 tree, `gate.sh P1`:** green, 8 s.
- **P2 tree, `gate.sh P2`:** green, 61 s (`sweep` about 50 s). Its first run after the review found
  two rows red for the wrong reason (`stated-twice` tripped the new end rule before the
  second-statement rule; `decomposed-in-testing` left § Conventions drifted), so their mutants
  survived; both rows were fixed and the sweep then killed 34 of 34.
- **P2 tree plus the last phase's record (`verify/mutant-sweep.md`), `gate.sh prepush`:** green after
  the ledger flagged four PLAN and TECH lines that named no `issues/marker-rule-gaps.md` path, now
  fixed. 65 s.
- **The gate's own refusals:** an unstaged edit is refused before any part runs; a staged edit to
  `tests/conftest.py`, to `verify/drift-ids.txt`, or an appended `def sandbox_violations` each turn
  `scope-P3` red.
- **The full suite, once:** the profile's `verify`, word for word, on the prototype as first drafted
  (before the review's text changes, which touch only `tests/test_hygiene.py`, run whole by `slice`
  and `ids`, and `AGENTS.md` prose): green, 1,545 s (25:45) on mac-m2; both eras' four commands
  passed (4,355 + 507 + 154 + 44 cases per era, 14 skips each, the suite's off-CI `need_git` /
  `need_shell` skips).
