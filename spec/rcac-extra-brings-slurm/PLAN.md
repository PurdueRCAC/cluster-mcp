# PLAN — `cluster-mcp[rcac]` alone brings the Slurm tools

> **Status:** Draft for review · **Last updated:** 2026-11-13
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Lean path (`kind: fix`, `appetite: small`):
> no `research/`. Every design element traces to a GOAL R-ID.

## 1. Summary

One line of packaging carries the fix: the core's `rcac` extra lists both members,
`rcac = ["cluster-mcp-rcac", "cluster-mcp-slurm"]`, and nothing else in any distribution's metadata
moves. `uv lock` adds the two lines that record it. `tests/test_packaging.py` pins the rule in the
declarations and the installed metadata through one check that names the extra it finds broken.
Every RCAC install line becomes `cluster-mcp[rcac]`, the fixture's `rcac` set is reread as the RCAC
member registered alone, and the ROADMAP and the seed record the rule. Two phases: the rule with its
pin and every text that restates it, then the records.

## 2. Design

**The rule (R1, R2, R3, R5).** `packages/cluster-mcp/pyproject.toml`:

```toml
[project.optional-dependencies]
slurm = ["cluster-mcp-slurm"]
rcac = ["cluster-mcp-rcac", "cluster-mcp-slurm"]
```

Distribution names, not a self-referencing `cluster-mcp[slurm]`: the seed's 2026-11-09 note settles
that the alias lists distribution names, and both names already have a `{ workspace = true }`
source, so `[tool.uv.sources]` does not change. The members' `pyproject.toml` files do not change
(Q2): each depends on the core alone. The comment above the table states the rule. Installed
metadata gains `Requires-Dist: cluster-mcp-slurm; extra == 'rcac'` beside the two lines it has.

- R1: a `[rcac]` install now holds the three distributions a `[slurm,rcac]` install holds. Which
  capabilities a server serves depends only on the distributions installed (§7: `installed()` loads
  every entry point in the group, in (distribution, name) order), so the two serve the same surface.
- R2: `[slurm,rcac]` and `[rcac,slurm]` resolve to the same three distributions as before. The root
  `pyproject.toml` (`cluster-mcp[slurm,rcac]`) and the Dockerfile do not change; `uv sync` installs
  the root's closure, which already held both members. `uv.lock` changes by exactly two added lines
  inside the `cluster-mcp` package entry (its `optional-dependencies.rcac` list and its
  `requires-dist`); no version, no other package moves (dry run: `Resolved 88 packages`, two lines).
- R3: `[slurm]` and the bare core keep their requirements; no extra other than `rcac` names
  `cluster-mcp-rcac`.

**The pin (R5).** In `tests/test_packaging.py`:

- `EXTRAS` becomes the rule as data: each extra and the member distributions it installs,
  `{'slurm': ('cluster-mcp-slurm',), 'rcac': ('cluster-mcp-rcac', 'cluster-mcp-slurm')}`, with a
  comment stating the rule. Membership is compared as sets: the order of an extra's list is free.
- `extra_violations(installs)` returns one line per break, each naming its extra: `the rcac extra
  does not install cluster-mcp-slurm`, `the slurm extra installs cluster-mcp-rcac, which it must
  not`, a missing extra, or a workspace distribution under an extra that is not a capability extra
  (or under none).
- `installed_extras(requires)` reads the installed `Requires-Dist` lines into the same shape.
- `test_core_declares_the_capability_extras` asserts `extra_violations` is empty for the declared
  table and for the installed metadata (each with its own assertion message), beside the existing
  pins (no unconditional member, the sources, the members' own dependencies, `Provides-Extra`). pytest prints the list on failure, so either direction fails naming the extra, in either
  layer.
- `test_extra_check_names_the_extra_that_breaks_the_rule` feeds both checks planted breaks in both
  forms (the repo's synthetic-control pattern).
- The module docstring (`:15-19`) states the new rule; `test_compat_root_installs_every_capability`
  iterates the members, not the extras.

**The `rcac` set (R4).** `tests/fixtures/served_surface.json` and `tests/mutants.py` do not change
(Q1 (a)). The reread goes where the set is named: the `SETS` comment in
`tests/test_capabilities.py`, the `tests/test_surface.py` docstring, and the `tests/test_surface.py`
entry in `AGENTS.md` § Testing, each saying the set is "the RCAC member registered alone", the state
the startup probe leaves on a cluster without Slurm's client commands, not an install. The
`MEMBER_SETS` comments (`tests/test_capabilities.py:666`, `tests/test_probes.py:50`) already say
"each member alone" and stay.

**The install lines (R6).** Every line R6 names, rewritten to `cluster-mcp[rcac]` alone, plus the
texts that restate the old one-member-per-extra rule, so no copy goes stale (§ Conventions, "a rule
restated in N places"):

- `README.md`: the opening (`:5-6`), the Quick Start `args` (`:18`) and shell line (`:33`), the
  sentence `:28-29`, the Capabilities row `:45`. `:75` (the compat distribution) stays.
- `packages/cluster-mcp/README.md:8-13`, `packages/cluster-mcp-rcac/README.md:6`.
- `docs/core/README.md:12`, `:19-22`, and `:25-26` ("Each extra installs one member", now false).
- `docs/rcac/README.md:3-4`, and `:23` (§ What it needs on the cluster: "The Slurm extra beside it"
  becomes the Slurm tools `[rcac]` installs).
- The comment at `packages/cluster-mcp/pyproject.toml:17-18`.
- `AGENTS.md:22-23`, `:68-72`, `:157`, § Testing's `test_packaging` entry (`:624-628`), § Packaging
  `:1694-1700` (now stating the rule, its citation, and that it lives in the core's extras alone)
  and `:1752`, and the release recipe: the `post_verify` README line (`:1914`) becomes
  `cluster-mcp[rcac] @ …@{v}#subdirectory=packages/cluster-mcp`, the `ci-mirror-no-index` caveat
  (`:1928`) names the same requirement, and the `install-probe` caveat (`:1977`) names the extra
  `[rcac]` and says the compat-root line keeps `cluster-mcp[slurm,rcac]` exercised (the foreman's
  ruling). The recipe's YAML still parses (checked in the dry run).
- `SECURITY.md:267` names no extra and stays.

**The records (R7).** One added paragraph in each of `ROADMAP.md`'s site-interfaces entry and
`[rcac]` entry, before its `*Horizon:*` line, and one dated note appended to
`issues/site-extras.md`: each states the rule in the GOAL's words, cites "maintainer decision,
2026-11-12", and says `[rcac]` brings `[slurm]` from 0.2.2. Additions only: no existing line,
horizon or heading changes, and the seed stays `unshaped` (the bundle's other members remain).

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | `rcac` lists both members (`packages/cluster-mcp/pyproject.toml`); §7's load of every installed entry point |
| R2   | `slurm,rcac`/`rcac,slurm` resolve unchanged; root `pyproject.toml`, Dockerfile untouched; `uv.lock` +2 lines inside `cluster-mcp` only; fixture `both`/`both-reversed` bytes unchanged |
| R3   | `slurm` extra and the bare core unchanged; `extra_violations` refuses the RCAC member under `slurm` |
| R4   | Fixture and `tests/mutants.py` untouched; the `SETS` comment, the `test_surface.py` docstring and `AGENTS.md` § Testing read `rcac` as the RCAC member registered alone |
| R5   | `EXTRAS`, `extra_violations`, `installed_extras` and the two tests in `tests/test_packaging.py`; members' `pyproject.toml` unchanged |
| R6   | The install lines and restatements listed under "The install lines" |
| R7   | The two ROADMAP paragraphs and the seed's dated note |

## 3. Invariant gate (AGENTS.md constitution check)

Walked at Step 2 against the GOAL and again against this design. Sections touched:

- **§7 Tool registration through the entry-point group.** Unchanged code. The fix relies on its
  contract: a member installed registers, one not installed is never imported. A `[rcac]` install
  now holds the Slurm member, so it registers; the load order and the composition order are the
  ones `[slurm,rcac]` already gets.
- **§9 The agent-facing surface is part of the API [human gate].** No served tool, text, resource or
  server-info field changes for any capability set; the fixture's bytes do not change (gated by
  sha256 in every mode). What a `[rcac]` install serves does change, from the `rcac` set to the
  `both` set: that is R1, the change the GOAL contracts. §9's pin is by capability set, not by
  install, so no fixture diff follows.
- **§4 / probes (`probes.py`).** Untouched. The RCAC-alone state remains reachable through the probe
  (R4), which is why the `rcac` set stays.
- **§ Packaging** (not a numbered invariant, but the contract the change edits): rewritten in the
  same commit as the extra; `uv.lock` in the same commit (§ Conventions); `cluster_mcp` stays a pure
  namespace; one version (no bump: the release recipe bumps to 0.2.2).
- **§ Conventions.** No spec ids in tests (`test_no_spec_ids_in_the_package_or_the_suite` runs in
  P2's gate); every copy of the restated rule changes in P1's commit.
- **High-blast-radius list.** No path on it is edited. `tests/fixtures/served_surface.json` is read,
  never written; the publish gate's human sign-off on the fixture outcome (bytes unchanged) stands.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| — | — | — |

## 4. Rabbit holes (resolved)

- **Does a path or git `#subdirectory` install of the core resolve the members through the
  workspace sources?** Yes: in the dry run, `uvx --isolated --from 'cluster-mcp[rcac] @ file://<tree>/packages/cluster-mcp'`
  built `cluster-mcp-rcac` (and, after the change, `cluster-mcp-slurm`) from the same tree. The git
  form clones, then builds the same subdirectory the same way; the release recipe's `post_verify`
  README line exercises it against the tag.
- **Does `uv lock` move anything else?** No: two added lines, no version change.
- **Can a server's surface be compared across installs without a cluster?** Yes:
  `cluster-mcp -e local --skip-probes` over stdio, under `bin/sandbox.sh`, listed with the harness's
  raw-listing client in both eras. On the base, `[rcac]` and `[slurm,rcac]` differ (seven Slurm
  tools); on the prototype they are identical, and every other form is identical to the base.
- **Adversarial review (trigger 3).** The deliverable includes an assertion (R5's pin) and gate
  scripts, so one reviewer pass ran (appetite small) against GOAL, this design, `verify/` and the
  staged prototype, and reproduced four of its eight findings in a scratch clone. Each is folded:
  1. HIGH, `install-lines` passed R6-breaking text (a "does not bring the Slurm member" sentence, a
     spaced `[slurm, rcac]`, a compat line swapped for an install line at an unchanged per-file
     count, a `--with 'cluster-mcp[slurm]'` line). Now: the lines naming both extras are pinned per
     file by their exact text, the pattern matches any spacing and any longer list, and three
     patterns refuse those claims in the texts a reader installs from (`.md`, `.toml`, `.yml`,
     Dockerfile; the suite's own messages name the breaks it refuses). Replayed: all four red.
  2. MEDIUM, `extra_mutants.py` credited the declarations layer on any output holding the message,
     and pytest's traceback prints every assertion's source. Now only pytest's `E` lines are read:
     `AssertionError: <layer's message>` and the extra's line. Replayed with a vacuous declarations
     pin: red at the declarations layer.
  3. MEDIUM, pytest reads the working tree while the checks read the index. Now every mode refuses
     unstaged changes first.
  4. MEDIUM, `tests/test_surface.py` and `tests/test_capabilities.py` were free to change, so the
     snapshot comparison could be emptied. Now `files` requires their syntax trees, docstrings
     removed, to equal the base's. Replayed (the fixture compared with itself): red.
  5. MEDIUM, `full` read the verify row from the AGENTS.md the cycle edits. Now it reads the base's
     row and refuses an index whose row differs.
  6. LOW, `roadmap` matched words anywhere. Now one sentence must carry `0.2.2`, `[rcac]`, "brings"
     and `[slurm]`, in both entries and in the seed; the internal-reference scan matches
     `\bboard\b` and names no person.
  7. LOW, `ledger` read single lines. Now it folds each paragraph, list item and table row, and
     reads PLAN.md too.
  8. LOW, an equivalent declaration in another order or layout was refused. The order-sensitive
     table equality is gone (`extra_violations` compares sets exactly), and `extra_mutants.py`
     plants and confirms through the parsed TOML.
  Held, per the reviewer: the metadata layer really runs on stale metadata; the install check is
  not vacuous (real uvx installs, distinct tree paths, base-side controls); nothing finds a commit
  by subject; the fixture's bytes are checked at every step.

## 5. Risks & open questions

- **The install check needs uv's cache warm, or the network.** `install_surfaces.py` resolves each
  form unlocked (both trees alike, one cache, one run). With a cold cache and no network it fails
  red, not green.
- **The install check compares against the base, not the fixture.** That is what R1 and R2 say
  ("what `[slurm,rcac]` serves", "what it serves on `916cecf`"), and it compares like with like
  (both unlocked, one run). The fixture is a second, independent pin of the sets.
- **Unlocked resolution moves FastMCP** (4.1.8 in the dry run, 4.1.4 locked). Both trees resolve the
  same versions in one run, so the comparison holds; a FastMCP release between two runs is no
  surface change of this cycle.
- **The publish gate.** The fixture is on the high-blast-radius list; publishing takes the
  maintainer's sign-off on its outcome (bytes unchanged), as the GOAL states.

## 6. Verification strategy

All gates live in `verify/` and diff against `BASE=${GATE_BASE:-$(git merge-base HEAD origin/develop)}`,
never a commit found by its subject, so they survive publish's squash. Every check reads the index
(the phase stages its work first), and every mode checks the fixture's sha256
(`2e0dc91f…6561`) and that it equals the base's.

- `gate.sh files`: the fixture, and the cycle's changed paths: only the allowed set; never the
  fixture, the root `pyproject.toml`, the Dockerfile, `compose.yml`, the members' `pyproject.toml`
  or `src/`, or `tests/mutants.py`.
- `gate.sh p1`: `files`; `uv lock --check`; the lock's diff is exactly the two lines; the install
  lines (`text_checks.py install-lines`: required lines present, `[slurm,rcac]` left only on the
  compat-root lines, counted per file, and none of the old phrasings, read with line breaks folded);
  the extras tests by id, then `tests/test_packaging.py`, `tests/test_surface.py`,
  `tests/test_core_only.py`, `tests/test_deprecation_window.py`; `install_surfaces.py` (six forms ×
  base and index × two eras, driving the real CLI under the sandbox); `extra_mutants.py` (two
  planted breaks, each red at the declarations' assertion and, with the declarations restored over a
  stale environment, at the installed metadata's, naming the extra; an unplanted control green).
  Dry run on the prototype (all of P1 and P2 staged): green in 73 s. On the pre-change tree,
  `install-lines` and `install_surfaces.py` are red (31 and 5 failures).
- `gate.sh p2`: `files`; the `rcac` set's reading; the ROADMAP and seed (added lines only, both
  entries carry the rule, the citation, `0.2.2` and `[slurm]`, horizons and section order unchanged,
  nothing internal); the deferral ledger; `tests/test_capabilities.py`, `tests/test_surface.py`,
  `tests/test_hygiene.py`. Dry run on the prototype: green in 18 s; on the pre-change tree
  `rcac-set` and `roadmap` are red.
- `gate.sh full`: the profile's whole `verify`, read from the base's `AGENTS.md` § Factory (the
  index's row must equal it), with the fixture checked before and after. Scheduled by the foreman,
  not run in build, and not dry-run in planning (the foreman schedules heavy runs).
- Every mode refuses unstaged changes. After landing, HEAD is on `origin/develop` and the merge
  base is HEAD itself, so a re-run then sets `GATE_BASE=916cecf`.

---

*Lean path: no `research/`.*
