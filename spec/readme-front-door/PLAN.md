# PLAN — The README is a front door

> **Status:** Draft for review · **Last updated:** 2026-11-12
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). There is no `research/`: the cycle was
> planned with `skip research` (a docs-only cycle whose content is the repository's own text), and
> no prototype was built (the foreman's ruling). Every design element traces to a GOAL R-ID.

## 1. Summary

The README keeps what a reader needs to decide and to start: an opening, Quick Start, a table of the
core and the two extras, a table of the three run modes, § Upgrading from rcac-mcp as it is,
Development and License. Everything else moves one level down, to three new docs pages
(`docs/core/README.md`, `docs/slurm/README.md`, `docs/rcac/README.md`) and to `SECURITY.md`, and is
rewritten there in short sentences with its figures in lists. The two tests that read the README's
text read `docs/core/README.md` instead; `AGENTS.md` gains § Documentation and points every
reference to a moved section at its new home. The gate is one script, `verify/docs-gate.py`, and a
fact map, `verify/facts.yaml`, that places every baseline fact. Two phases: the pages and their
tests, then `AGENTS.md` and the full gate.

## 2. Design

### The pages

The headings below are fixed by this plan, because the gate finds the parts of each page by them.
Prose under them is the builder's, within § Documentation's rule (R8) and the fact map.

**`README.md`** (at most 120 lines, aiming at about 100; R1, R2):

```
# cluster-mcp
<opening: two or three sentences — what the server is, how it runs (SSH for one user, a shared host for many)>
## Quick Start
  <one sentence: the desktop clients>; the JSON client configuration, as at the baseline;
  <one sentence: stdio, over SSH with your ~/.ssh/config>;
  one install line (the baseline's `uvx --from '…' cluster-mcp --help`, in a bash fence), one
  sentence on naming the extras; one sentence on the client's instructions limit, linking
  docs/core/README.md#<the heading that says how to raise it>
## Capabilities
  | Capability | Install | What it adds | Docs |  — three rows: the core, `[slurm]`, `[rcac]`
  (with `[slurm]`); each links docs/<member>/README.md; the `[rcac]` row carries one line linking
  docs/rcac/README.md#rcac-documentation (the documentation service)
## Run modes
  | Mode | For | How it runs |  — three rows: `ssh` (the default, stdio), `local` (development),
  `delegate` (many users, through sudo, JWT or OIDC); each links its SECURITY.md section
## Upgrading from rcac-mcp
  byte for byte as at the baseline (its test and the mutation plants read it in place; `readme`
  compares it with the baseline section)
## Development
## License
```

No figure appears outside § Upgrading: no digit (outside a link target), no number word with a
unit, no multiple ("three times"), no signal name, no `-N`. The README lists no tool by name, so
§9's same-commit rule has one human-facing home per tool: its docs page.

**Each docs page** (R3), `docs/<member>/README.md`, holds an H1, a lead of a sentence or two, and
these level-2 sections:

- `## Tools` — one list line per tool the member registers, in the baseline's form
  (`` - `name(args)` — what it does ``), carrying the baseline's one-line descriptions. The core's
  page may keep the baseline's "Shell and files:" and "Site context:" labels as prose between the
  lines; every list line in the section names a tool.
- `## What it needs on the cluster` — the core: a login bash (`/bin/bash -l`), and over `ssh` an SSH
  server with SFTP and your SSH configuration; the Slurm page: `sbatch`, `squeue`, `scancel`,
  `sacct`, `sinfo`, `scontrol`, each a code span; the RCAC page: `findscratch`, `myquota`, and the
  Slurm extra beside it (several tools take a Slurm job id). Each page says a member missing a
  command is withheld, linking the core page's probe section.
- `## How it behaves` — what the member does, in short sentences.

`docs/core/README.md` adds `## Install` (the extras, quoting the requirement, the workspace and
PyPI note — "the README's install note" of the release recipe — and `CLUSTER_MCP_SSH_HOST`), and
under § How it behaves: the connection (connect errors, reconnection, a silent link), commands
(the login bash, output, exit codes, timeouts and the stop), file writes, which capabilities are
served (the probe), and the cluster's rules in the instructions (site rules, delegate readability,
the budget, raising the client's limit) (R4, Q2). Every line of this page that states a figure is
a list item or a table row (R4): each bound in seconds, the signal order (TERM, a second, then
KILL), each exit code (`-1001`, `-1002`, `-1003`, `-N`), the budget and Claude Code's limits. The
strings the repointed tests check keep their exact words here: `the transfer may be partly made`
and the `issues/ssh-write-staging-leftover.md` link; `15 s of quiet`, `15 s after a call's start`,
`29 s after a background probe`, `44.45 s`, `within 29 s`, `every 44 s`, `45 s`; `by SFTP to a
private temporary file`; `a background job started by the remote login shell's own rc file`.

Three limits are named, each in one sentence linking its seed (R6): the staging directory a lost
write leaves (`issues/ssh-write-staging-leftover.md`), the remote rc file's background job
(`issues/startup-background-jobs.md`), and what a timeout cannot stop
(`issues/timeout-stop-limits.md`). The baseline's long list of what the stop does not reach
(a process outside the group, a hanging startup file, an SSH server that ignores `signal`,
shadowed builtins, a clock step) is not repeated: the seed states each case (fact map rows
`shadowed-builtins`, `not-stopped`), and `AGENTS.md` §3 holds the contract. Links from a docs page
into the repository are relative (`../../issues/…`, `../../SECURITY.md#…`); the test strings still
match, being substrings.

`docs/rcac/README.md` adds `## RCAC documentation`: this server does not search RCAC
documentation; the separate `rcac-docs-mcp` service does, at its baseline URL, added alongside
(Q3). `docs/slurm/README.md` carries the `extra_args` rule (a list, one argument per element; a
string is refused) and `sbatch`'s byte-for-byte script.

**`SECURITY.md`** (R5) keeps every section it has. Every baseline line outside its overview
(baseline lines 6–14) stays a line of the page, word for word; new lines go between them. Its overview becomes the place that says how to run the service: the three run modes, with
the README's one-line descriptions of each (`ssh` the default for stdio, `local` for
development/testing only, `delegate` multi-user through `sudo`, with JWT or OIDC), all inside that
one level-2 section. A new level-2 section, `## Hosted HTTP server`, takes the README's three
recipes under their baseline headings, `### Basic HTTP Server`, `### With JWT Authentication`,
`### Docker Compose with TLS` (AGENTS.md § Packaging points at the last), before § Recommendations.

**The package READMEs** (R7) each end by linking their docs page by its repository URL,
`https://github.com/PurdueRCAC/cluster-mcp/blob/main/docs/<member>/README.md`, in place of
"The full documentation is the repository's README". A package README ships inside each
distribution's metadata, where a relative link would not resolve; `main` carries the pages from the
release this cycle ships in (0.2.1). Each keeps its install line; none links the repository root or
its README.

### The tests (R9)

`tests/test_ssh_liveness.py` (one read) and `tests/test_ssh_exec.py` (two reads) change exactly the
path expression: `(root / 'README.md')` becomes `(root / 'docs' / 'core' / 'README.md')`. The dict
label `'README.md'` in `test_ssh_exec.py` may become `'docs/core/README.md'`, since it names the
file; the constants (`README_TRANSFER`, `README_FIGURES`, `CONTENT_RULE`, `EXCEPTION`), every
assertion and every message stay as they are, and comments may name the new file. The comment
above `EXPECTED_TOOLS` in `tests/test_registry.py` names "its member's docs page" in place of "the
README". `tests/test_deprecation_window.py`, `tests/mutants.py` and `tests/harness.py` do not change.

### AGENTS.md (R8)

- A new `## Documentation`, after § Packaging and before § Working on this codebase as an agent:
  what `README.md` holds (the R1 list), what each docs page holds (its tools, one line each; what
  its member needs on the cluster; how it behaves; the core's page also install, connection,
  timeouts, writes, the probe and the site rules), what `SECURITY.md` holds (how to run the
  service, its security model); short sentences that say what a thing does and how to use it; a
  limit named only where a user would otherwise get hurt, in one sentence linking its `issues/`
  seed; exact figures on the docs page in a list or table, none in the README outside § Upgrading;
  edge cases in `issues/` or `AGENTS.md`, linked from the docs; the tests that read a page's text.
- §9: "The same commit also updates the tool inventory in `README.md`" names the tool's docs page,
  `docs/<member>/README.md`, instead.
- Code moves verbatim: every line inside a baseline fence (the client configuration, the install
  line, the probe's stderr line, the hosting recipes, Development's commands) is a line of its home.
- The pointers to moved text, each to its new home: § Testing's `EXPECTED_TOOLS` note (line 352 at
  the baseline: its docs page), the `rcac-docs-mcp` note (358: the README's `[rcac]` row and
  `docs/rcac/README.md`), the SFTP-route note (1171), the doc pin of the liveness figures (1382),
  §3's separation exception (2501): `docs/core/README.md`; § Packaging's `README.md`
  § *Docker Compose with TLS* (1732: `SECURITY.md`) and its "same same-commit rule as the
  instructions texts and the README" (1734: names `docs/<member>/README.md`, the docs pages); the release recipe's "the README's
  install note" (1879: `docs/core/README.md`). The `rcac-docs-mcp` note says truthfully that two
  places point to the service: the README's `[rcac]` row and `docs/rcac/README.md`. § Repository map names `docs/` and § Documentation.
- What stays: every mention of § Upgrading from rcac-mcp, `REPO_FILES`, the README's install line
  (the recipe's `post_verify` comment and its `install-probe` caveat), the root sdist's `README.md`,
  the package READMEs, and "the README says to install `[rcac]` with `[slurm]`" (its `[rcac]` row
  says so).
- Edits inside §2 and §3 keep the sentences the tests pin there (`SECTION_2_TRANSFER`,
  `CONTENT_RULE`, `EXCEPTION`).

### The gate

`verify/docs-gate.py` reads the index, the GOAL's baseline (`2719b7a`) and the cycle's base (the
parent of the shape commit, found by subject), never the working copy. Its modes:

| Mode | Checks | R-IDs |
|---|---|---|
| `readme` | level-2 sections, in order, no others; an opening of two or three sentences; one client configuration, one install line, one link to the docs/core heading that holds `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH`; three capability rows, each linking its docs page, the `[rcac]` row linking the heading that names `rcac-docs-mcp`; three run-mode rows (`ssh`, `local`, `delegate`), each linking `SECURITY.md`; at most 120 lines; no figure outside § Upgrading, and § Upgrading the baseline's byte for byte | R1, R2 |
| `pages` | each docs page's three sections; every `EXPECTED_TOOLS` tool on one list line of exactly one page's § Tools, its member's (members' tools and declared commands read from the installed package, whose source R9 freezes); each declared command a code span in § What it needs on the cluster; every figure line of `docs/core/README.md` in a list or table; `SECURITY.md`'s three hosting headings; every relative or repository link on every page resolves, anchors included; no HTML comment outside code on any page | R3, R4, R5 |
| `facts` | the fact map (below); every baseline `SECURITY.md` line outside its overview still a line of it | R4, R5, R6 |
| `packages` | each package README links its docs page by repository URL and never the repository root, its README, or the old repository | R7 |
| `agents` | one § Documentation naming its rule's terms; §9's bullet names `docs/`, not `README.md`; each moved reference's old words gone (and present at the base, so the list cannot go stale) and its block naming the new home; § Repository map names `docs/`; any other README mention is about what the README keeps | R8 |
| `paths` | the cycle changes only its pages, `AGENTS.md`, the two repointed tests, the `test_registry.py` comment and `spec/readme-front-door/`; each repointed test, with its new path mapped back, is the base's syntax tree exactly, and reads the new path as many times as the base read the README; `test_registry.py`'s tree is unchanged | R9 |
| `prepush` | a clean tree; no site-private text in the cycle's added lines but the hosts and addresses the baseline pages already carry (Q4); the ledger | — |
| `controls` | each decision above on planted data | — |

**The fact map** (`verify/facts.yaml`, 58 facts, 297 phrases) is the GOAL's Review-mode map. Each
fact names the baseline lines that state it, its one home on the branch, and short phrases of the
baseline text that carry it. The `facts` mode checks that every phrase is in its fact's baseline
lines (the map invents nothing); that every baseline line but blanks, headings, fence markers and
table delimiters lies in some fact (every fact is mapped); that every phrase is in the fact's home,
all of them inside one level-2 section; that an `issues/` home is linked from a docs page; and
that every line inside a baseline fence the fact maps is, stripped, a line of its home. Matching
drops backticks and `*`, reads a link as its text and target, and collapses whitespace. A phrase
matches whole, never inside a longer word or number (`45 s` is not found in `44.45 s`, `MIT` not in
"limit"); a phrase with two capitals in a row (`TERM`, `MIT`, `JWT or OIDC`) matches its case, and
any other ignores case. The builder keeps each phrase verbatim and writes around it. Homes, by count:

| Home | Facts |
|---|---|
| `README.md` | opening, opening-extras, quickstart-clients, quickstart-config, quickstart-stdio, install-extras, install-line, upgrading, modes-readme, see-security, development, license |
| `docs/core/README.md` | install-core-alone, install-quote, install-workspace, ssh-host-env, connect-errors, reconnect, silent-link, never-cut, transfer-cut, site-rules, site-delegate, budget, login-bash, output-end, signal-exit, writes, timeout-stop, never-signalled, not-stopped-link, lost-1003, probe, probe-timeout, tool-groups-core, core-tools |
| `docs/slurm/README.md` | slurm-tools |
| `docs/rcac/README.md` | rcac-docs, tool-groups, rcac-tools |
| `SECURITY.md` | modes-security, hosted-intro, hosted-basic, hosted-jwt, hosted-compose, and its own eleven (sec-intro … sec-reporting) |
| `issues/timeout-stop-limits.md` | shadowed-builtins, not-stopped (the seed already states both; it gains a link, not text) |

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | README's six level-2 sections and opening; Quick Start's configuration, install line and limit sentence; the capabilities and run-modes tables; `readme` |
| R2 | README at most 120 lines; no figure outside § Upgrading; `readme` |
| R3 | each docs page's § Tools, § What it needs on the cluster, § How it behaves; `pages` |
| R4 | `docs/core/README.md`'s § Install and § How it behaves; its figures in lists; fact rows connect-errors … probe-timeout, site-rules, site-delegate, budget; `pages`, `facts` |
| R5 | `SECURITY.md`'s overview as the run-modes home and its new § Hosted HTTP server; its own facts kept; `pages`, `facts` |
| R6 | the fact map, every baseline line placed; three limits, one sentence each, linking their seeds; `facts` |
| R7 | each package README's repository-URL link to its docs page; `packages` |
| R8 | `AGENTS.md` § Documentation, §9's bullet, the pointer repoints; `agents` |
| R9 | the path-only test edits; the changed-path allowlist; the profile's full `verify` in P2; `paths` |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before the design (gate #1) and against it (gate #2). No path on § Invariants'
high-blast-radius list is touched, so research trigger 2 does not fire (and `skip research` would
override it).

- **§9, the agent-facing surface.** The served tools, resources and instructions do not change: no
  file under `packages/*/src/`, no fixture (R9, `paths`; `test_surface.py` in the full verify). Only
  §9's prose pointer to the README's inventory moves to the docs page; the same-commit rule keeps
  its force, now naming the docs page.
- **§2 and §3** carry sentences `tests/test_ssh_liveness.py` and `tests/test_ssh_exec.py` pin. The
  §3 edit (the separation exception's list of texts) keeps `EXCEPTION`; §2 is not edited.
- **§ Conventions (same-commit rules).** Docs that a code change names change with it: unchanged
  in force; the docs pages are now where a tool change lands its human-facing line (§9). "CI
  mirrors the gate" is untouched: no CI or verify list changes.
- **§ Testing.** The two doc pins keep their strings and assertions; only the file they read moves.
  § Testing's prose describing them names the new file.
- **§ Packaging and the release recipe.** No packaging change. The package READMEs are each
  distribution's long description; they stay Markdown with one more link. The recipe's
  `post_verify` comment ("the README line") stays true: the README keeps the install line.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| No prototype: the gate is dry-run on the baseline (every mode red for the reasons expected, the fact map's baseline-side checks green) and on its controls, not on a tree that passes it | The foreman's ruling for this cycle (no research fan-out, no prototype) | A prototype is the build itself here; P1's first `verify:` is the first tree that can pass, and a check that contradicts another surfaces there, before any review |
| R1's "opening" is the lead under the H1, not a level-2 heading; the two table sections are named `Capabilities` and `Run modes`, Quick Start drops "(Desktop Clients)" | R1 lists the opening among "level-2 sections" but names no heading for it or for the tables; the gate needs fixed names | A `## About` heading over two sentences adds a heading to a page meant to be short; the names are one constant each in the gate if the maintainer wants others |
| "The README's install note" (the PyPI note, R8's `AGENTS.md:1879`) lives on `docs/core/README.md` § Install | R8 leaves its home to "the page that carries the note"; R1's Quick Start has room for one install line, not the note | Keeping it in the README would add a paragraph Quick Start does not hold under R1 |
| The package READMEs link `…/blob/main/docs/<member>/README.md`, which resolves once the release lands the pages on `main` | A package README is read off the repository (an index page, installed metadata), where only an absolute URL resolves | `blob/develop` points a released package at unreleased text; a relative link resolves nowhere outside the repository |
| The repointed tests keep their messages ("the README does not state …") | R9: "with only the file path moved" | Rewording a message is more than the path; the dict label may name the file, since it is the path |
| The comment above `EXPECTED_TOOLS` changes | It restates §9's rule, which R8 repoints | Leaving it would leave the one stale pointer outside `AGENTS.md`; the `paths` mode allows the file only with an unchanged syntax tree |
| No mutation gate | The GOAL's Review mode: the maintainer reads the pages, and the profile's `verify` runs green | — |

## 4. Rabbit holes (resolved)

- **The mutation runner's repository copy.** A case with `repo_edits` runs in a copy holding
  `tests/`, `bin/`, `README.md`, `AGENTS.md` and `pyproject.toml`, not `docs/`; a repointed test run
  there would fail on a missing file and read as a kill. No such case targets the repointed tests
  (the README plants target `test_deprecation_window.py` only; the two text-route cases plant into
  package source and run in the repository itself), and `tests/mutants.py` does not change.
- **§ Upgrading's test** reads the section from its heading to the next level-2 heading and the
  whole README for windows; R1's order keeps the section whole, and its last sentence ("the Quick
  Start form above") stays true.
- **The site-rules header `<!-- Source: name.md -->`** is a code span at the baseline and moves to
  `docs/core/README.md`; the hidden-comment check ignores code spans and fences, so the two do not
  contradict.
- **The site-private scan and Q4.** The cycle's added lines carry the baseline's example hosts and
  addresses (Q4); `prepush` allows exactly the strings the baseline README and SECURITY.md hold,
  and still refuses a new one (a control plants one).
- **The doc-pin figures sit in lists.** The figures `test_ssh_liveness.py` checks are matched with
  whitespace collapsed, so a list item holding them passes both the test and R4's list check.
- **The adversarial review** (trigger 3: the deliverable includes two assertions' edits and the
  cycle's mechanical gate) ran once, on the GOAL, this design and the drafted gate scripts, probing
  the gate's functions on planted text. It found the repointed tests' check, the mutation runner's
  copy, R2 against the README's facts, the figure-bearing facts in lists, the run-mode anchors and
  the install URL sound. Its findings, each folded, each with a control that plants it:
  1. HIGH: `agents` refused the wording this plan prescribes (the `rcac-docs-mcp` note naming the
     README's `[rcac]` row; "the docs pages" for the `compose.yml` clause, where the gate looks for
     `docs/`). Now "`[rcac]` row" is a kept context, and the plan names `docs/<member>/README.md`
     in that clause.
  2. MEDIUM: phrases matched as case-folded substrings (`45 s` inside `44.45 s`, `MIT` inside
     "limit", `TERM` inside "determines", `sudo` inside "pseudo"). Now whole matches, with case kept
     for capitalised phrases.
  3. MEDIUM: text the plan keeps was guarded only by phrases: § Upgrading, `SECURITY.md`, and code
     lines (`export JWT_SECRET=…`, `mkdir -p certs`), and three facts had no phrase (the non-root
     delegate stop, the clock step, a write refusing what `cat >` refuses). Now § Upgrading is
     compared byte for byte, every baseline `SECURITY.md` line outside its overview and every
     baseline code line must be carried as a line, and the three facts have phrases.
  4. LOW: the single-string form `root / 'docs/core/README.md'` read as an unmoved path. Fixed; the
     plan's three-part form was never affected.
  5. LOW: figure patterns missed teens, tens, `s`/`ms` units and lowercase `sigterm`, and flagged
     "a second" as an ordinal. Widened, and "a second" counts only as a span of time.
  6. LOW: a code span `uvx` in Quick Start prose counted as an install line. Only fenced lines count.
  7. LOW: the package scan missed a lowercase repository URL and a `?plain=1` README link; the
     private scan allowed any substring of the baseline (a new, shorter address inside the
     baseline's reporting address). Case-insensitive with query strings; allowed matches are the
     baseline's matches.
  8. LOW: a heading or a lone `|` line after a list item counted as list text, and a nested tool
     line escaped the one-page count. A list item ends at a heading, a table needs its delimiter,
     and nested tool lines count.
  9. LOW: `pages` imports the editable install, the one read of the working copy. Noted in the
     script; `paths` and `prepush` make the two agree.

## 5. Risks & open questions

- **The fact map is a net, not a proof.** A phrase present in its home says the words survived, not
  that the sentence around them still says the same; the maintainer's read of the rendered pages is
  the judge (GOAL Review mode). Co-location within one level-2 section narrows it; on
  `docs/core/README.md` § How it behaves is one section, so the narrowing is weak there.
- **Verbatim phrases constrain the prose.** 297 phrases, most of them names, figures and code; a
  few are clauses ("never cut while the cluster answers"). A builder who finds one that cannot sit
  in a short sentence stops and asks: the map is frozen with the plan.
- **The sentence counter** splits at `.`, `!` or `?` before whitespace, so an abbreviation such as
  "e.g." in the opening miscounts; the opening avoids them.
- **The package links are dead until the release.** They name `main`, which takes the pages at
  0.2.1's release. The release recipe's `twine check --strict` reads the long descriptions; the
  phase gates do not run it (no network in a phase gate).
- **The verbatim rules bind the rewrite.** Code lines and `SECURITY.md`'s lines outside its
  overview move word for word; a builder who needs to change one stops and asks.

## 6. Verification strategy

There is no CLI behaviour to drive: the served surface is frozen (R9). Each phase runs the gate's
modes for its requirements, then the tests that read the pages, in both protocol eras:
`tests/test_ssh_liveness.py::test_liveness_texts_state_the_monitor`,
`tests/test_ssh_exec.py::test_content_texts_state_the_sftp_route`,
`tests/test_ssh_exec.py::test_separation_texts_state_the_remote_rc_exception`,
`tests/test_deprecation_window.py` and `tests/test_registry.py` (about 20 s per era, measured on
the baseline, 2026-11-12). P2 runs every mode, `prepush`, and the profile's full `verify`. Measured
on the baseline: each gate mode under 2 s, `controls` under 1 s.
