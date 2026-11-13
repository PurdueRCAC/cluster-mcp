# GOAL — The README is a front door

> **Origin spec.** The *what* and *why*: the locked contract the review grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by the plan step).

- **slug:** readme-front-door
- **kind:** docs
- **appetite:** small
- **review:** the maintainer reads the rendered pages on the branch. No mutation sweep and no blind
  review loop this cycle (see Review mode).
- **ships as:** 0.2.1

## Problem

People open the README for two reasons: to decide whether to use the server, and to get it running.
The README on `main` (and on `develop`, which matches it) does neither quickly. It is about 300 lines
of dense prose, long on what things are and are not. The Quick Start runs into connection
internals, timing figures and failure modes. § Execution Modes is one paragraph of more than 30
lines on timeouts, signals and transfers. The tool list and the hosting recipes sit below all of it.

Facts a user needs once they run the server are mixed in with facts a reader deciding whether to
install it never needs. `SECURITY.md` already documents the three ways to run the server, but the
README repeats part of it and holds the hosting recipes itself. Each package README sends its
reader back to the repository README, the longest page.

## Outcome / vision

A reader decides and gets running from one short page. `README.md` says what the server is, how to
install and configure it, what each part offers, and how it can run. It links one level down for
the rest:

- `docs/core/README.md`, `docs/slurm/README.md`, `docs/rcac/README.md`: one page for the core and
  for each extra. Each lists its tools, the cluster commands it needs, and how it behaves.
- `SECURITY.md`: how to run the service, in one place.

Each page uses short sentences and says what a thing does and how to use it. Exact figures sit in a
list or table on the docs page. A limit is named only where a user would otherwise get hurt, in one
sentence linking its issue. Edge cases stay in `issues/` or `AGENTS.md`, linked from the docs.
`AGENTS.md` keeps the rule, so later cycles write to it.

## Acceptance criteria (the contract)

The baseline is `origin/develop` at `2719b7a`, which is where this cycle's branch starts. "Docs
page" means one of the three `docs/*/README.md` files.

- **R1** — `README.md` SHALL hold these level-2 sections, in this order, and no others: an opening
  that says what the server is in two or three sentences; Quick Start, with the client
  configuration, one install line, and one sentence on the client's instructions limit linking to
  where `docs/core/README.md` says how to raise it; a table of the core and each extra, one row
  each, linking to its docs page, with the `[rcac]` row carrying one line that links to the
  documentation service on `docs/rcac/README.md`; a table of the three run modes (`ssh`, `local`,
  `delegate`), one row each, linking to `SECURITY.md`; § Upgrading from rcac-mcp; Development;
  License. § *The cluster's rules, in the instructions* moves to `docs/core/README.md` and
  § *RCAC Documentation* to `docs/rcac/README.md` (Q2, Q3).
- **R2** — `README.md` SHALL be at most 120 source lines, aiming at about 100 (Q1). Outside § Upgrading from rcac-mcp, which keeps its version window, it SHALL state
  no exact figure: no duration, timeout, byte rate, exit code or signal name.
- **R3** — Each docs page SHALL list its member's tools, one line per tool; the commands its member
  needs on the cluster; and how its member behaves. Every tool the server registers (the
  `EXPECTED_TOOLS` set in `tests/test_registry.py`) SHALL be listed on exactly one docs page, the
  page of the member that registers it.
- **R4** — `docs/core/README.md` SHALL carry what README § Quick Start and § Execution Modes say at
  the baseline about the connection (connect errors, reconnection, a silent link), timeouts and the
  stop, exit codes, and file writes, and what § *Which capabilities are served* says about the
  capability probe, and what § *The cluster's rules, in the instructions* says about site rules,
  the instructions budget and raising the client's limit. Its exact figures (each bound in seconds, the signal order, each exit code)
  SHALL sit in a list or table.
- **R5** — `SECURITY.md` SHALL describe how to run the service: the three run modes, and the hosted
  HTTP server (basic, with JWT, and Docker Compose with TLS) moved from the README. It SHALL keep
  what it covers at the baseline: OIDC, request isolation in delegate mode, sudoers, the user map and
  identity claims, the recommendations, and reporting a security issue.
- **R6** — Every fact that `README.md` or `SECURITY.md` states at the baseline SHALL be stated on
  the branch, in `README.md`, a docs page, `SECURITY.md`, `AGENTS.md`, or an `issues/` seed that a
  docs page links. Where a docs page names a limit, it SHALL do so in one sentence that links the
  limit's `issues/` seed.
- **R7** — Each package README (`packages/cluster-mcp/README.md`, `packages/cluster-mcp-slurm/README.md`,
  `packages/cluster-mcp-rcac/README.md`) SHALL link to its docs page, and SHALL NOT link to the
  repository README as its documentation.
- **R8** — `AGENTS.md` SHALL hold a § Documentation that states the rule this cycle follows: what
  `README.md`, each docs page and `SECURITY.md` hold; short sentences that say what a thing does and
  how to use it; a limit named only where a user would otherwise get hurt, in one sentence linking
  its issue; exact figures on the docs page in a list or table, none in the README; edge cases in
  `issues/` or `AGENTS.md`, linked from the docs. §9's same-commit rule SHALL name the tool's docs
  page where it now names the README's tool inventory, and every other `AGENTS.md` reference to a
  README section this cycle moves SHALL name that section's new home, including § Packaging's
  pointer to README § *Docker Compose with TLS* (`AGENTS.md:1732` at the baseline, now
  `SECURITY.md`) and the release recipe's "the README's install note" (`AGENTS.md:1879`, now the
  page that carries the note).
- **R9** — The branch SHALL change no file under `packages/*/src/` and no
  `tests/fixtures/served_surface.json`; the served tools, resources and instructions are unchanged.
  A test that reads `README.md` today SHALL read the file that holds its text on the branch, with
  the strings it checks unchanged. In particular, `tests/test_ssh_liveness.py`
  (`README_TRANSFER`, `README_FIGURES`, lines 658–697 at the baseline) and `tests/test_ssh_exec.py`
  (`CONTENT_RULE` and the remote rc exception, lines 365–393) SHALL read `docs/core/README.md`, with
  only the file path moved. `tests/test_deprecation_window.py` keeps reading `README.md`. The
  profile's `verify` SHALL pass.

## Non-goals (no-gos)

- No change to code, the served surface, the served instructions, `INSTRUCTIONS.md`, the CLI or
  `compose.yml`.
- No new behaviour documented: the pages carry what the baseline states, reorganised and rewritten.
- No change to the deprecation window or to § Upgrading from rcac-mcp beyond what the move needs
  (its tests and mutation plants read it in place).
- No published docs site, no generator, no docs build or link checker in CI.
- The version bump to 0.2.1, the tag and the release notes belong to the release recipe, not this
  cycle.
- `spec/`, `issues/` and `ROADMAP.md` records are not rewritten (an `issues/` seed may gain a link
  target, not new text).
- `issues/rename-in-docs.md` stays as it is (`unshaped`), and the example hosts
  (`cluster.rcac.purdue.edu`, `mcp.rcac.dev`) are carried as they are (Q4).

## Review mode

The review is the maintainer reading the rendered pages on the branch (`README.md`, the three docs
pages, `SECURITY.md`, the package READMEs, `AGENTS.md` § Documentation) and the profile's `verify`
run green. No mutation sweep and no blind review loop run this cycle. R1–R3 and R7–R9 are checkable
by reading or by a script (line count, section headings, the tool-to-page map, links, the diff's
paths). R4–R6 are checked against a fact map the plan writes: each fact of the baseline `README.md`
and `SECURITY.md` and the place it lives on the branch.

## Clarifications

- **Q1:** "About two screens": what line ceiling does R2 set for `README.md`? — **A:** 2026-11-12 ·
  foreman ruling at GOAL sign-off: at most 120 source lines, aiming at about 100; the maintainer
  still judges "two screens" at review.
- **Q2:** Where does § *The cluster's rules, in the instructions* go? — **A:** 2026-11-12 · foreman
  ruling at GOAL sign-off: `docs/core/README.md` takes the section; Quick Start gets one sentence
  and a link for the client's instructions limit, since otherwise the cut is silent.
- **Q3:** Where does § *RCAC Documentation* go? — **A:** 2026-11-12 · foreman ruling at GOAL
  sign-off: `docs/rcac/README.md` carries the documentation service, and the README's `[rcac]` row
  gets one line linking to it.
- **Q4:** Does this cycle take on `issues/rename-in-docs.md` (labelling the Purdue example hosts)?
  — **A:** 2026-11-12 · foreman ruling at GOAL sign-off: no; leave the seed alone and carry the
  example hosts as they are.
- **Q:** Do test edits fit a docs-only cycle? — **A:** Yes: tests that read the README follow its
  text wherever it moves and stay green (the cycle request, 2026-11-12).
- **Q:** What review does this cycle get? — **A:** The maintainer reads the rendered pages on the
  branch; no mutation sweep, no blind review loop (the cycle request, 2026-11-12).

## Related materials

- Baseline: `README.md`, `SECURITY.md` and the three package READMEs at `origin/develop` `2719b7a`
  (same text as release 0.2.0, tag `0.2.0` = `ea1b2c4`).
- Tests that read `README.md` today: `tests/test_deprecation_window.py` (§ Upgrading, stays),
  `tests/test_ssh_liveness.py` (`README_TRANSFER`, `README_FIGURES`), `tests/test_ssh_exec.py`
  (`CONTENT_RULE`, the remote rc exception); `tests/mutants.py` plants in § Upgrading.
- `AGENTS.md` §9 (the same-commit README tool inventory), § Packaging (§ *Docker Compose with TLS*,
  the install note), the release recipe's README install line.
- `issues/rename-in-docs.md` (overlapping seed, left alone, Q4).
