# REVIEW — Rename rcac-mcp to cluster-mcp

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** 81c3820  ·  **Base:** develop (0.1.4, `403e491`)  ·  **Date:** 2026-10-30
- **Verdict:** changes-requested (cycles 1–3); approved at the bound by Geoffrey's ruling after a scoped fix — see § Review cycle 3
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md` (escalate to human on non-convergence)
- **Mode:** debate variant (the diff touches the coupled core: `server.py`, `middleware.py`,
  `context.py`, `auth.py`, `token.py`, `executor/*`, all moved). Two blind reviewers, "ship" and
  "block", each in its own clones of `81c3820`, ran at the same time; the foreman reconciled.

## Verification run

Both reviewers ran the profile's `verify` in their clones:

- `uv lock --check` → ok.
- `uv run pytest -q` → 2498 passed, 14 skipped (both). The 14 are the existing
  `bash 4.1 or later is not installed here` skips; CI ran them (2512 per era on `81c3820`).
- `CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` → 2498 passed, 14 skipped (both).
- `bin/sandbox.sh uv run cluster-mcp --help` → exit 0.
- The release gate (ship): audit clean over 84 packages, 8 artifacts built, `twine check --strict`
  8 PASSED, sdist hygiene clean. Block ran the same minus the networked audit; the third-party lock
  set is unchanged from 0.1.4.
- `tests/mutants.py --self-check` over all 361 cases → 361 killed, controls correct (block).
- Planted mutants of their own: ship 26 (24 killed, 2 survived: F1, F2); block several, one
  surviving (F1).
- Real-program drives under `bin/sandbox.sh`:
  - Both install forms from a `git+file://` clone at `81c3820`: `#subdirectory=packages/cluster-mcp`
    builds the Slurm and RCAC members from the same commit and runs `cluster-mcp --help`; the old
    root form runs `rcac-mcp`. Block counted 0 package-index lookups for any `cluster*` name across
    152 index requests, with uv 0.13.6, the uv 0.12.17 floor, `uv pip install`, and the Dockerfile
    path.
  - `rcac-mcp -e local` over stdio: stdout holds only JSON-RPC; the warning names `cluster-mcp` and
    the window on stderr. Same stdout and exit status as `cluster-mcp` for no arguments, `--help`,
    `--version` and `--bogus`.
  - Sandbox fail-closed: `cluster-mcp` and `rcac-mcp` with the new host variable, the legacy one,
    both, or a `UV_ENV_FILE` setting both → exit 2, empty stdout, "SSH host required … set
    CLUSTER_MCP_SSH_HOST". Positive control: outside the sandbox the env file does inject the hosts.
  - All four resource URIs plus near variants, in bare, shared and delegate modes, both eras: each
    `rcac://` read matches its `cluster://` target; context runs nothing; storage runs on the
    request's executor; delegate refusals identical for both schemes; no variant served.
  - Served surface vs a 0.1.4 clone, both eras: the same 24 tools with identical names, schemas,
    descriptions, meta and title; `serverInfo.name` `RCAC` → `cluster-mcp`.

## Requirement → evidence matrix

| R | Implemented | Verified by (reviewer) |
|---|---|---|
| R1 | yes | No built wheel has `cluster_mcp/__init__.py`; entry point `cluster-mcp = cluster_mcp.core:main`; `__version__` from metadata; `python -m cluster_mcp.core --version` (both) |
| R2 | yes | serverInfo `cluster-mcp` in both eras; `--help`/`--version` free of RCAC/Purdue; mutants killed (both) |
| R3 | yes | `rcac-mcp` vs `cluster-mcp` stdout/exit identical; warning on stderr only; stdio clean (both) |
| R4 | yes | Every 0.1.4 read site goes through `env_setting` (both) |
| R5 | yes | Legacy alone honoured with a warning; both set → replacement wins with an "ignored" warning; host, map and budget (both) |
| R6 | yes | Eight sandboxed runs incl. a uv env file, all fail closed (both) |
| R7 | yes | Aliases derived before `OPEN_RESOURCES`; reads and refusals identical per scheme (both) |
| R8 | yes, annotations unpinned | Tools, schemas, descriptions, meta, title identical to 0.1.4; nothing tests annotations (F2) |
| R9 | yes | Three members; all ten Purdue tools in `cluster_mcp.rcac.tools` (both) |
| R10 | yes | Both git install forms from one commit; no index lookups for internal names (both) |
| R11 | yes | Core text has no RCAC/Purdue and names no RCAC tool (both) |
| R12 | yes | All 24 tools named; overlay labelled and last; base uncut before the site context (both) |
| R13 | yes | Every repo URL outside `spec/` names `PurdueRCAC/cluster-mcp` (both) |
| R14 | yes | Every header exactly the new line; license lines unchanged (both) |
| R15 | yes | Docs, Dockerfile, compose, ci.yml, profile and recipe moved; gate green at the head; bump rehearsal meets the diff rule (both) |
| R16 | yes, unpinned | README section and warnings agree today; nothing ties them (F1) |

## Findings

### [LOW/CONFIRMED] F1 — Nothing pins the deprecation window (R16)
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/deprecation.py:28` (`WINDOW`);
  `README.md:75-91` (§ Upgrading from rcac-mcp).
- **Failure scenario:** the warnings and the README name different windows, or the README section
  goes, and every gate stays green. `tests/test_cli.py` and `tests/test_env.py` compare each warning
  with the `WINDOW` constant itself, whatever its value; no test reads the README section.
- **Evidence:** both reviewers changed `WINDOW` to "removed no earlier than 0.3.0"; block also
  deleted the README section. The full suite stayed green (`2498 passed, 14 skipped`, block); the
  targeted files gave `153 passed` (ship) and `572 passed` (block). `grep` for `0.4.0`, `removed no
  earlier` or `Upgrading` under `tests/` finds nothing.
- **Touches:** R16; R3 and R5 through the window they name.

### [LOW/CONFIRMED] F2 — R8's "annotations" clause is not tested
- **Where:** `tests/harness.py:421-430` (`_surface` records `description`, `inputSchema`,
  `outputSchema` only); no test reads tool annotations.
- **Failure scenario:** a change adds, drops or alters a tool's annotations and the served-surface
  comparison stays green, against R8's "the same tools, schemas and annotations as 0.1.4".
- **Evidence:** ship added `annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False)`
  to `mcp_tool`; `run_command` served them, and `test_surface`, `test_registry`, `test_tools`,
  `test_instructions` gave `242 passed` (modern surface `19 passed`). Today neither 0.1.4 nor the
  head serves annotations, so the behaviour is correct.
- **Touches:** R8. The fixture's shape predates this cycle, but R8 names annotations, so the pin
  belongs to this cycle's contract.

### Dropped after refutation
- An empty `CLUSTER_MCP_*` value counts as unset, so the legacy value is honoured: 0.1.4's
  empty-is-unset semantics, documented.
- A whitespace-only replacement budget beats a legacy one, then strips to the default: consistent
  with "the replacement wins".
- The lock's `revision` drops on a bump under the uv 0.12.17 floor: pre-existing (0.1.4's lock is
  also revision 5); the diff rule holds under uv 0.13.6.
- `compose.yml`'s delegate mode lacks a user map: pre-existing.
- `python -m rcac_mcp` is gone: not one of the GOAL's three deprecations.

### Observations (not findings)
- `tools/list` order changed: `slist` and `sfeatures` now follow `storage_paths`, before the Slurm
  tools, because R9 moved them into the RCAC member. No R-ID covers order; names, schemas,
  descriptions, meta and title are identical.
- The base instructions grew from 1333 to 1374 UTF-16 units, 41 fewer for site text under the
  default budget.
- Request-state keys `rcac_user` / `rcac_local_user` remain in `middleware.py`; never served, and not
  in the identity-strings seed.
- The JWT issuer and audience stay `rcac-mcp`, deliberately, under
  `issues/rename-leftover-identity-strings.md`.

### Out of Scope, seeded
- None.

## Routing

**F1, as a property over its domain:** the deprecation window is one string, the GOAL's
"deprecated in 0.2.0, removed no earlier than 0.4.0", and every place a user reads it says exactly
that: the `WINDOW` constant, every warning that names it (the `rcac-mcp` command, each legacy
variable, each ignored-twin warning), and README § Upgrading from rcac-mcp. The README section must
exist and name each of the three deprecations with its replacement. Pin the literal, not the
constant. Mutant families to sweep, each in both eras: `WINDOW` altered; the README window altered;
the README section deleted; a deprecation row or its replacement dropped from the README; a warning
emitter that omits the window.

**F2, as a property over its domain:** the served surface of every tool, its annotations included
(each hint's presence and value), equals 0.1.4's. Record annotations in the surface comparison and
fail on any difference, with a key missing on one side counting as a difference. Mutant families to
sweep, each in both eras: an annotation added to every tool (the decorator), to one tool, a hint's
value flipped, an annotation removed.

Both route to a reopened P5, which satisfies R8 and R16. Note the `rcac_user` / `rcac_local_user`
observation in the identity-strings seed while there.

## Human-gate triggers

- Triggered: the diff moves every file on the high-blast-radius list and edits `bin/sandbox.sh`
  and the coupled core. The foreman, judge under decision 2026-10-16-cluster-mcp-autonomous, signs
  it off for remediation (2026-10-30).

## Optional completeness sub-pass (separate reviewer; may see TECH.md)

- Not run.

## Review cycle 2 — changes-requested (2026-10-30)

- **Reviewed commit:** 22cc36e (remediation `e3431a2`, plus a docs-only seed note) · **Mode:** scoped
  to verifying F1 and F2's remediation, as the remediation changed only tests (`git diff --stat
  1190973..22cc36e -- packages` is empty). One blind reviewer in its own clone, planting its own
  mutants for both families in both eras.
- **Verify (reviewer's clone):** `uv lock --check` ok; handshake era 2541 passed, 14 skipped; modern
  era 2541 passed, 14 skipped (the known reconnect flake did not occur); sandboxed `cluster-mcp
  --help` exit 0 with no RCAC or Purdue strings. CI on `e3431a2` and on `22cc36e`: success, 2555 per
  era.
- **Remediation checkers:** F1 printed "ok" (31 pins per era, 17/17 killed in both eras); F2 printed
  "ok" (28 pins per era, 8/8 killed in both eras).
- **Runner extension:** an anchor matching 0 or 4 times, or a path outside `REPO_FILES`, raises and
  errors the run; a no-op plant or a stray edit is caught by the existing mutation tests; the child
  still runs under the repo's `bin/sandbox.sh` with the import-origin check.

### F2 — resolved
Eight planted annotation mutants were killed in both eras: a hint on one tool, `title` alone, all
four hints set explicitly to their spec defaults, `readOnlyHint=None`, an extra hint, the Slurm
member only, at `server.add_tool`, and `readOnlyHint=False` on every tool. A probe showed
`exclude_unset` records every hint that reaches the wire, defaults included.

### F1 — resolved for the constant and the warnings; F3 and F4 remain
Nine of ten warning and constant plants were killed in both eras: punctuation and case drift in
`WINDOW`, an emitter or the ignored shape stating its own window, an extra stderr line, a windowless
command warning, a warning on stdout. The README section is pinned only in part.

### [LOW/CONFIRMED] F3 — The README pairing check depends on row order
- **Where:** `tests/test_deprecation_window.py` `table_pairs`, which keeps the last row naming a
  deprecated name (`pairs.update(zip(old, new))`).
- **Failure scenario:** the README pairs `RCAC_SSH_HOST` with two replacements, a wrong row first.
  A user following the first row sets a variable the server never reads, and the suite is green.
- **Evidence:** inserting `` | `RCAC_SSH_HOST` | `CLUSTER_SSH_HOST` | `` above the variables row:
  `13 passed` in both eras. The same row after it is killed (12 failed).
- **Touches:** R16.

### [LOW/CONFIRMED] F4 — A second, contradicting window passes when it is worded differently
- **Where:** `upgrading_violations` recognises a stated window only by the phrase "removed no earlier
  than" (`WINDOW_END`) and checks the published window by unbounded substring; it reads raw
  Markdown. `tests/test_cli.py` matches the command warning with an unanchored `search`.
- **Failure scenario:** the README says the old names go in 0.3.0 while the table says 0.4.0, or
  the window reads "0.4.0-alpha", or the whole section sits in an HTML comment no reader sees; or the
  command warning carries a contradicting prefix. Every gate stays green.
- **Evidence, each surviving in both eras:** appending "The old names will be removed in 0.3.0."
  (`13 passed`); "…and keeps working until 0.3.0:" (`13 passed`); "removed no earlier than
  0.4.0-alpha" (`13 passed`); the section wrapped in `<!-- … -->` (`13 passed`);
  `legacy_warning('removed in 0.3.0; the rcac-mcp command', …)` (`88 passed`). Called directly,
  `upgrading_violations` also accepts "0.4.0.1" and "0.4.0 (0.3.0 for the command)".
- **Touches:** R16; R3 through the command warning.

### [LOW/CONFIRMED] F5 — A tool's `title` is not compared
- **Where:** `tests/harness.py` `_tool_entry` records description, schemas and annotations, not the
  tool's top-level `title`.
- **Failure scenario:** a change gives a tool a display title, which clients show in place of its
  name; the served-surface comparison against 0.1.4 stays green.
- **Evidence:** planting `title=` on `run_command` passed `test_surface`, `test_registry`,
  `test_tools` and `test_protocol` (`299 passed` in both eras).
- **Ruling:** the reviewer listed this as out of scope because R8 names annotations only. The
  foreman rules it in: cycle 1's routing stated F2's property as the served surface of every tool
  equalling 0.1.4's, cycle 1 verified `title` as identical, and the fix follows the annotations
  pattern (record it when served), so the 0.1.4 fixture keeps its shape.
- **Touches:** R8.

### Dropped or already covered
- A sandboxed `cluster-mcp -e local` start fetched FastMCP's update-check URL from PyPI. The lock's
  FastMCP is unchanged from 0.1.4, and `issues/fastmcp-update-check.md` already covers it.
- Environment-variable warnings are checked through log records rather than a real process's
  stderr. This predates the cycle, and the reviewer's drive showed the real stderr is correct.

### Routing
**F3 and F4, as one property over the README section and every warning:** the section a reader sees
(HTML comments removed) maps each deprecated name to exactly one replacement, whatever the row
order; every version literal in it (`\d+\.\d+\.\d+\S*`) is exactly `0.2.0` or `0.4.0`; and the
window appears as the whole published phrase, bounded at tokens. The command warning is matched
anchored at its start, as the variable warnings already are (`fullmatch`). Mutant families to sweep,
each in both eras: a contradictory row before or after the right one; a second window in other
words; a version suffix or extra component; the section hidden in a comment; a prefix on the
command warning.

**F5, completing F2's property:** a tool's top-level `title` is recorded when served and compared
like annotations. Mutant families: a title on one tool, on every tool, at `server.add_tool`.

All three route to a reopened P5, tests only.

### Human-gate triggers
- Still triggered (the cycle moves the coupled core). The foreman, judge under decision
  2026-10-16-cluster-mcp-autonomous, signs it off for remediation (2026-10-30). Cycle 3 is the last
  under the bound.

## Review cycle 3 — changes-requested, at the bound (2026-10-30)

- **Reviewed commit:** 9f507cb (remediation of F3–F5, tests only; `git diff --stat 1190973..9f507cb
  -- packages` is empty) · **Mode:** scoped, one blind reviewer in its own clone, planting its own
  mutants for every family in both cycles' routing, in both eras.
- **Verify (reviewer's clone):** `uv lock --check` ok; handshake era 2585 passed, 14 skipped; modern
  era 2585 passed, 14 skipped; sandboxed `cluster-mcp --help` exit 0. CI on `9f507cb`: success,
  2599 per era. No earlier pin was weakened; the drift lists only grew.

### F1, F2, F5 — resolved
- F1: `WINDOW`, each emitter, the README window, heading, rows and replacements: all killed in both
  eras.
- F2: annotation plants all killed in both eras.
- F5: 0.1.4 and the head, each in both eras, serve byte-identical tool lists, with every title the
  one FastMCP derives from the name and no annotations. `derived_title` matches FastMCP 4.1.4's
  derivation over 14 names. Eleven title plants killed in both eras. The equivalents are a hand-set
  derived title and `title=''`, which FastMCP replaces with the derived one.

### F3, F4 — resolved for the routed members; F6–F9 remain
Order dependence is gone, and every routed member of F4 is killed (also `v0.3.0`, `0.3`, `0.3.x`,
`0.4.0a1`, full-width digits).

### [LOW/CONFIRMED] F6 — A contradicting row not written in code spans is not parsed
- **Where:** `tests/test_deprecation_window.py` `table_pairs`, which skips a row with no code spans,
  more than two cells, or no leading pipe.
- **Evidence:** `| RCAC_SSH_HOST | CLUSTER_SSH_HOST |` before or after the right row, and the bold,
  escaped, `<code>`, three-cell and no-leading-pipe forms: `32 passed` in both eras. markdown-it
  renders each as a table row. `AGENTS.md` claims a row contradicted before or after is caught.

### [LOW/CONFIRMED] F7 — Comment stripping hides text a reader sees
- **Where:** `rendered()`'s `<!--.*?(?:-->|\Z)` matches inside code spans, fenced code, and across
  paragraphs, where CommonMark renders no comment.
- **Evidence:** a "removed in 0.3.0" sentence between a code-span `<!--` and `-->`, across two
  paragraphs, or in a fenced block: survives in both eras.

### [LOW/CONFIRMED] F8 — Versions outside the window are checked by spelling only
- **Evidence, each surviving in both eras:** "The `rcac-mcp` command is removed in 0.2.0." (allowed
  versions only); `0\.3\.0`, `0&#46;3&#46;0`, `0.**3**.0`.
- **Residual, not routed:** a contradiction with no version ("removed in the next minor release"),
  and one outside the section (README line 33, or at the end of the file). R16 asks for one place,
  and the routing scoped the check to the section.

### [LOW/CONFIRMED] F9 — A second command warning on the serving path passes
- **Where:** `tests/test_cli.py` `stdio_violations` accepts any one matching stderr line.
- **Evidence:** a second warning naming 0.3.0, emitted only with `-e`: `35 passed` in both eras; a
  real sandboxed `rcac-mcp -e local` printed both warnings on stderr.

### Out of scope
- The README drift controls plant into the live README, so an unclosed comment after the section
  turns two of them red when no reader sees a change.
- `_Comparison.tool` reports a changed title twice. Harmless.

### Ruling at the bound
Cycle 3 is the last under `review.cycle`. The foreman escalates to Geoffrey. Behaviour is correct
throughout. Every open finding is a test pin over README text or the serving-path warning.
The reviewer prototyped a cheap fix, about 25 lines, which kills 25 of the 28 surviving README
mutants:
- every `|` line is the header, the delimiter, or a two-cell code-span row;
- each deprecated name appears once in the section;
- versions are read after markup is removed, with only one `0.2.0` outside the window;
- the section holds no comment markers.

For F9, exactly one stderr line names `rcac-mcp`.

**Geoffrey's ruling (2026-10-30): scoped fix, foreman verifies, land; no fourth review.** The
remediation takes the prototype's four rules and the F9 pin. The foreman verifies it with its own
mutants in both eras. The two residuals (no version literal; a contradiction outside the section) are
accepted.

### Remediation (f8d6af1) and foreman verification
- **The fix, tests only** (`git diff --stat dd6dafa..14f4623 -- packages` is empty):
  - every `|` line in the section is the header, the delimiter or a two-cell code-span row;
  - each `RCAC_*` variable and `rcac://` URI appears once, after markup is removed;
  - the section holds no comment markers;
  - versions are read after markup is removed, and outside the window only one `0.2.0` may appear;
  - exactly one stderr line names `rcac-mcp`, and it fully matches the warning, on every legacy drive
    and on the serving path.
  - 23 new mutants, each shown surviving on `dd6dafa` and killed after in both eras; 417 killed in
    all. The F6–F9 checker counts its own 135 named tests.
  - Residual recorded by the builder: `rcac-mcp` is not count-pinned, because the section names it four
    times by design.
- **Rebase:** the branch was rebased onto `develop` `5b00169`, a lock-only fix for a dependency
  advisory published during this remediation. The pre-rebase `14f4623` is `f8d6af1`, and the only
  tree difference is that lock entry. P5's `release` mode was red on the audit before the rebase and
  is green after.
- **The foreman's own mutants**, run against `14f4623` in both eras, targeting
  `tests/test_deprecation_window.py` and `tests/test_cli.py`, with no-op controls green first
  (112 and 37 passed):
  - **Killed in both eras, each for its stated reason:** a `<details>` note naming 0.3.0; a prose
    sentence giving `RCAC_USER_MAP` a second replacement; `0._3_.0`; `&#48;.3.0`; a zero-width space
    inside `0.3.0`; a footnote on the window naming 0.3.0; the command warning also printed on stdout
    when serving.
  - **Survived in both eras:** a second stderr line, emitted only when serving, stating "removed in
    0.3.0" without naming the command (37 passed). Accepted as a residual of the kind the ruling
    accepts: a contradiction that names nothing the check keys on. Pinning every log line's text
    would bind the test to unrelated server output.
- **Gate on `f8d6af1`:**
  - `docs` and `carry` ok;
  - `release`: audit clean; 2690 passed, 14 skipped per era; every artifact `twine` PASSED; sdist
    hygiene clean;
  - F6–F9 and F5 checkers ok.
  - `mutants`, `full-legacy` and `full-modern` were green on `14f4623`, and the tree differs only by
    the lock entry.
- **Verdict:** approved under Geoffrey's ruling at the bound.

### Human-gate triggers
- Triggered: non-convergence at the bound, plus the coupled-core trigger carried from cycle 1.
  Geoffrey ruled (2026-10-30); the foreman verified the scoped fix.

## Publish: the 0.1.5 version carry (foreman override of the staleness gate)

0.1.5 was released from `develop` (`d243aaf`) before this cycle landed, and it bumped the root
`pyproject.toml` version line, which this branch rewrote. The squash onto `develop` conflicted on
that line alone. `7d65b00` moves all four dists' version lines, and their lock entries, from 0.1.4
to 0.1.5, so the squash resolves to the branch's tree. It touches code after `f8d6af1`, so the
staleness gate fires. The foreman, as judge at publish, overrides it: the change is version lines
only, no behaviour moves, and the full gate and CI were read green on `7d65b00` before landing.
