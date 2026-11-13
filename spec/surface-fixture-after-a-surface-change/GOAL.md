# GOAL — The served-surface fixture follows a deliberate surface change

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** surface-fixture-after-a-surface-change
- **kind:** test
- **appetite:** small

## Problem

`tests/fixtures/served_surface.json` pins what the server serves (`AGENTS.md` § Invariants §9,
a human gate). It is the surface `3d010ec` served on FastMCP 2, written by
`spec/stack-upgrade/verify/snapshot.py`, a retained record under `spec/` rather than a maintained
tool. `test_served_surface_matches_baseline` (`tests/test_surface.py:276`) compares the live surface
with it through `surface_violations` (`:265`), which accepts five named kinds of FastMCP 4 metadata
(`TOLERATED`, `:64`; the seed says four, a fifth, `derived-title`, landed since), and
`test_surface_fixture_is_the_baseline_shape` (`:288`) rejects a fixture that carries that metadata.
So the fixture cannot be re-taken on the current stack. Every deliberate change since the move
(`safe-execution`, `agents-d-instructions`, `sbatch-script-name-collision`, `rename-to-cluster-mcp`)
landed as a scripted hand-edit of named deltas into the 2.x-shaped JSON, which nothing checks
against what the server actually serves, and §9 still calls the long-term method an open question.

The recorder also sees less than the server serves. `served_surface` (`tests/harness.py:449`)
builds each tool entry from a fixed list of fields (`_tool_entry`, `:434`: description, input and
output schemas, annotations, title) and each resource from three (`:457`: name, description, MIME
type), and lists neither resource templates nor prompts nor server info. A tool or resource that
gained a field outside those lists (`_meta`, `icons`, a resource's title or annotations), a
template or prompt added, or a server-info change would pass unseen; the server's name is pinned
only by a separate test (`tests/test_protocol.py:401`). And `TOLERATED['argument-description']`
accepts any argument `description` where the 2.x snapshot had none, so an argument description
that drifted from its docstring line would pass too.

This matters now. The release's "gates first" group puts this fixture before the first cycle that
changes the served surface: `rename-leftover-identity-strings` (`serverInfo.version`) in 0.2.0,
then 0.3.0's tool-family reshaping and capability extras, each of which adds, removes, renames or
re-describes tools. Each needs a way to land its change that is explicit and reviewable, and a check
that catches everything else. **Pre-existing:** no; introduced by `stack-upgrade` P3.

## Outcome / vision

The served surface is pinned by a plain snapshot test (re-shaped 2026-11-12, see Clarifications).
The test serializes what the server serves, canonically (keys sorted), in both protocol eras and
under every capability set, and compares that with `tests/fixtures/served_surface.json` by plain
equality; on any difference it fails with a diff naming the entry and the field. The only
normalizations live in the serializer, each named with its cause; today that is
`serverInfo.version` alone. There is no tolerance list, no exemption and no separate command.
Re-baselining is an opt-in update mode of the same test: it writes the fixture from the live server
and never reads the old one, so a conflicted or deleted fixture regenerates cleanly. A deliberate
change lands as that fixture diff, `git diff` on the fixture is its delta list, and it is reviewed
as a surface change. A one-time re-baseline moves the fixture to the current stack's shape, shown to
change nothing the old fixture pinned beyond the formerly tolerated metadata.

## Acceptance criteria (the contract)

R-IDs as amended 2026-11-12 (the re-shape Clarification lists what was kept, changed, added and
removed).

- **R1** — Re-baselining SHALL be an opt-in update mode of the surface test, enabled by an
  environment variable (such as `UPDATE_SURFACE=1`) or a pytest flag. In that mode the test SHALL
  write `tests/fixtures/served_surface.json` from the live server and SHALL NOT read the existing
  fixture, so a fixture that holds merge-conflict markers, is missing, or names a distribution no
  longer installed is regenerated without error. Two update runs with no change between them SHALL
  write byte-identical files. WHILE the mode is not enabled, nothing in the suite SHALL write the
  fixture, and no gate step or CI job SHALL enable it.
- **R2** — The serialization SHALL record, for each protocol era and for each capability set in
  `SETS`, the surface served under the harness's site context and auth mode `none`, as the whole
  objects a client receives: the instructions; every key of each tool's `tools/list` entry at any
  depth (title, description, input schema with argument descriptions, output schema, annotations,
  and any other key such as `_meta`, `icons` or `execution`); every key of each resource's
  `resources/list` entry; the resource template and prompt listings (empty today); the advertised
  server capabilities object; and the server info, every field literally but those R9 names. It
  SHALL be canonical: keys sorted and the output stable, so one served surface always serializes to
  the same bytes. A key or entry the server begins to serve SHALL appear in it with no change to the
  serializer.
- **R3** — `test_served_surface_matches_baseline` SHALL compare the serialization with the fixture by
  plain equality. WHEN they differ in any way (an entry added, removed, or renamed, a rename shown as
  one removed and one added; a key gained, lost or changed at any depth; a description, instruction,
  capability or server-info field changed), it SHALL fail with a diff naming each differing entry
  and the path of each differing field. The comparison SHALL carry no tolerated-difference list and
  no exemption.
- **R4** — WHILE the suite runs in either protocol era, the test SHALL compare the same
  serialization, both eras included, with the same fixture. A surface the two eras serve
  differently is recorded per era as served, not refused.
- **R5** — WHEN a surface change is made deliberately, running the test in update mode SHALL write
  the fixture with which the test then passes. The fixture SHALL be written indented with its keys
  sorted, so that `git diff` on it is the change's delta list, which the change's commit body
  carries. A fixture change SHALL reach `develop` only as a reviewed surface change: the fixture
  stays on § Invariants' high-blast-radius list, so publish needs the maintainer's sign-off.
- **R6** — The re-baseline SHALL be shown, by a check whose output the commit body that lands it
  records, to serve under the full capability set in each era what the fixture at `origin/develop`
  `0bfacae` records, but for the five formerly `TOLERATED` kinds in the fields that fixture
  records. Fields it did not record enter as served, each listed in that commit body.
- **R7** — Mutation testing SHALL aim at the gate: every non-equivalent mutant of the comparison and
  of each serializer normalization SHALL be killed in both eras, each equivalent recorded with its
  reason. One control SHALL show that a field changed at depth fails, naming its entry and field.
  The update mode SHALL carry one control, that from a fixture holding merge-conflict markers it
  writes the fixture with which the test then passes, and no mutation sweep. The generated controls
  added for cycle 2's N2 SHALL be removed, but any that guards something plain equality does not,
  each kept one naming what it guards. Every `tests/mutants.py` case that plants into the fixture
  (`REPO_FILES`, `SURFACE`) SHALL still apply to the fixture and be killed. The shape test that
  rejected current-stack metadata stays retired.
- **R8** — `AGENTS.md` §9 and § Testing SHALL describe the snapshot test (what the serialization
  records, its named normalizations, plain equality, the update mode, and how a deliberate change
  lands with `git diff` on the fixture as its delta list), and § Commands SHALL give the update
  mode's invocation. No line SHALL describe the surface command, its flags, its base selection, a
  tolerance list or the hand-edit rule.
- **R9** — Normalizations SHALL live only in the serializer, each named beside it with its cause.
  Today there is one: `serverInfo.version` is recorded as the installed distribution whose version
  the server serves (M1), not as its value. IF the served version matches no candidate distribution,
  or more than one, THEN serialization SHALL fail naming the candidates, never pick one. Any other
  normalization is a change to this GOAL.
- **R10** — `bin/record_surface.py` SHALL be removed with its base selection, and with it everything
  in the suite that served only the command (its main routine and helpers, its effects interface,
  the scan that it makes no choice and the scan that nothing runs it, and their controls).
- **R11** — The seed `issues/record-surface-relative-out.md` SHALL be retired with its `ROADMAP.md`
  entry, and the review observations about the command (cycle 3's CO3, CO4, CO6 and the relative
  `--against`) are not seeded. `issues/surface-pin-completeness.md` SHALL be re-checked against this
  shape: each item that still applies kept, each that does not dropped, and the seed retired with
  its `ROADMAP.md` entry if none applies. `ROADMAP.md`'s counts SHALL follow.

## Non-goals (no-gos)

- Changing the served surface. The re-baseline re-shapes the pin; it changes no tool, schema,
  description, instruction or resource.
- `serverInfo.version`'s value and the JWT issuer and audience: `rename-leftover-identity-strings`
  owns them. This cycle only makes the fixture able to take that change (M1, R9).
- Pinning listing order in the fixture: `tests/test_capabilities.py` already pins load order (§9).
- Pinning real sites' context text, instruction-budget cuts, or per-auth-mode and per-execution-mode
  surfaces. The fixture uses the harness's site and auth mode `none`. If the plan finds that a tool,
  resource or instruction varies with auth or execution mode, it raises that before build.
- Mechanically enforcing §9's same-commit rule for the instructions text and the README inventory.
- Editing `spec/stack-upgrade/verify/snapshot.py`, which stays as that cycle's record.
- A separate re-baselining command or script, a tolerated-difference list, or an exemption.
- A mutation sweep of the update mode: it is development tooling, held by R7's one control.
- Any timing or CI-cost bound. If the plan's rows (both eras and every set serialized in each run
  included) change a suite job's time, it brings before-and-after figures against the profile's
  `ci budget` baseline for the maintainer to decide.

## Clarifications

- **Q (M1):** How is `serverInfo.version` pinned, given that today it is FastMCP's version (it moves
  with the lock) and the rename cycle will make it this distribution's (it moves every release)?
  — **A:** The fixture records which installed distribution the version comes from, and the
  comparison checks the served value equals that distribution's installed version; a release or a
  lock bump is no surface change, and the rename's switch of source is a one-field fixture diff
  (2026-11-09, foreman ruling at the GOAL gate).
- **Q (M2):** Are the surfaces of capability subsets, probe-withheld ones included, pinned?
  — **A:** Yes, by a projection check: under every set in `SETS`, each served tool and resource
  entry equals the fixture's entry for it, with the same additive controls as R7; one fixture
  (2026-11-09, foreman ruling at the GOAL gate).
- **Q (M3):** How is review of a fixture change forced? — **A:** (b) for this cycle: the command's
  delta list in the commit body and ordinary review. Whether `tests/fixtures/served_surface.json`
  joins § Invariants' high-blast-radius paths is asked of the maintainer (2026-11-09); if he says
  yes, build adds that one line.
- **Q (M4):** Is the advertised server capabilities object in the fixture? — **A:** Yes, under
  R4's both-eras rule (2026-11-09, foreman ruling at the GOAL gate).
- **Q (M4, refined):** The protocol advertises a different capabilities object per revision for the
  same server; how does R4 apply to it? — **A:** The advertised capabilities object is recorded per
  protocol era (`capabilities: {legacy, modern}`), each era compared with its own entry. R4's
  refusal excepts that one key; every other field still refuses on any era difference. Recorded
  2026-11-09, foreman ruling at the PLAN/TECH gate (refines M4).
- **Q (M3, answered):** Does `tests/fixtures/served_surface.json` join § Invariants'
  high-blast-radius paths? — **A:** Yes, (a): the maintainer's answer, 2026-11-09. The fixture is
  added to the list, so any change to it, a re-baseline included, triggers the review's human gate.
  This supersedes M3's status quo of (b) alone; the delta list in the commit body still applies.
- **2026-11-12 · re-shape to (c), a plain snapshot test, by the maintainer's ruling.** Review cycle 3
  (`REVIEW.md`, Finding A, MEDIUM) found that the surface command imports the test module, which
  reads the fixture at import, so the command cannot re-take a conflicted, deleted or
  uninstalled-distribution fixture; the review loop ended its third cycle without converging. The
  maintainer ruled for (c), the standard snapshot pattern: serialize the served surface canonically
  (sorted keys, both protocol eras, every capability set) and compare it with the fixture by plain
  equality, a failure printing a diff that names the entry and the field; normalizations live in
  the serializer, each named (today `serverInfo.version` only), with no tolerance list and no
  exemption; re-baselining is an opt-in update mode of the test that never reads the existing
  fixture; `bin/record_surface.py` and its base selection are removed, and the commit body's delta
  list is `git diff` on the fixture; rigor in proportion, mutants aimed at the comparison and the
  normalizations, the update mode held by one control. The fixture stays on the high-blast-radius
  list and publish needs the maintainer's sign-off. One review follows the build: a LOW-only verdict
  lands under the standing rule, anything higher goes back to the maintainer.
  - **R-ID delta.** *Kept:* R6 in substance (the five kinds, the `0bfacae` base, new fields listed
    in the landing commit body), re-pointed at the new fixture's full-set entries per era.
    *Changed:* R1 (the command → the test's update mode, which never reads the fixture), R2 (the
    per-set projection folded into the serialization, every era and set; the version's rule moved
    to R9), R3 (plain equality and a diff; the carve-out clause dropped), R4 (both eras serialized as
    served; the refusal dropped), R5 (the delta list is `git diff` on the fixture; the
    high-blast-radius gate stated), R7 (rigor in proportion: mutants on the comparison and
    normalizations, one depth control, one update-mode control, N2's generated controls removed
    unless one guards what equality does not), R8 (the `AGENTS.md` lines rewritten for the snapshot
    test, the command's lines gone). *Added:* R9 (normalizations only in the serializer; an
    ambiguous version fails), R10 (`bin/record_surface.py` and the suite code serving only it
    removed), R11 (the `--out` seed retired, the completeness seed re-checked). *Removed:* none by
    number; the command (old R1, R5), the era refusal (old R4) and the per-set additive controls
    (old R7) are gone in substance.
  - **Superseded:** M2's projection check (each set's surface is now in the serialization, R2);
    M4 and M4 refined (each era is serialized whole, so no per-era carve-out or refusal exception,
    R4); M3's command delta list (now `git diff`, R5). M1 stands as R9's one normalization; M3
    answered (the high-blast-radius list) stands.
  - **Derived, for the gate to confirm:** R9's failure when the served version matches no
    candidate or several (M1 records "which distribution", which neither case can answer), and R5's
    indented, key-sorted layout (what makes `git diff` a delta list naming entry and field).

## Related materials

- Seed: [`issues/surface-fixture-after-a-surface-change.md`](../../issues/surface-fixture-after-a-surface-change.md)
- `ROADMAP.md`: "The surface pin cannot follow a deliberate surface change" (0.2.0, the last gate);
  the release brief's "gates first" group
- `AGENTS.md` § Invariants §9, § Testing (`tests/test_surface.py`), § Commands, high-blast-radius
  paths; mutation runner (`tests/mutants.py`, `REPO_FILES`, `SURFACE`, `SURFACE_TEST`)
- `tests/test_surface.py`, `tests/harness.py` (`served_surface`, `_tool_entry`, `_surface`),
  `tests/test_protocol.py` (`test_server_identifies_as_cluster_mcp`), `tests/test_capabilities.py`
- [`spec/stack-upgrade/`](../stack-upgrade/) (P3, `verify/snapshot.py`)
- [`REVIEW.md`](REVIEW.md) cycle 3, Finding A (the re-shape's cause); `bin/record_surface.py` (removed
  by R10)
- Seeds this cycle filed and the re-shape revisits: `issues/record-surface-relative-out.md`,
  `issues/surface-pin-completeness.md` (R11)
- Next surface changers: `issues/rename-leftover-identity-strings.md`, `issues/tool-surface.md`,
  `issues/site-extras.md`, `issues/shell-extra.md`, `issues/files-xdu-extra.md`
