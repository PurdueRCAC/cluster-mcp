# GOAL — `cluster-mcp[rcac]` alone brings the Slurm tools

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** rcac-extra-brings-slurm
- **kind:** fix
- **appetite:** small

## Problem

A user at an RCAC cluster who installs the extra named for their center, `cluster-mcp[rcac]`, gets a
server with no Slurm tools. The core's `rcac` extra installs the RCAC member alone
(`packages/cluster-mcp/pyproject.toml:21`, `rcac = ["cluster-mcp-rcac"]`), and that member depends
on the core alone (`packages/cluster-mcp-rcac/pyproject.toml:7`). So the server serves `jobinfo`,
`jobcmd`, `jobenv` and `jobscript`, each of which takes a Slurm job id, plus `slist`, `sfeatures`,
`showpartitions` and `average_wait`, but no `sbatch`, `squeue`, `scancel`, `sacct`, `sinfo` or
`scontrol_*` to submit or find the job. That is the served surface the fixture records as the `rcac`
capability set (`tests/fixtures/served_surface.json`). Every RCAC cluster runs Slurm, so this install
is never what an RCAC user wants. Today the docs work around it by telling the user to name both
extras (`README.md:28-29`, `:45`; `packages/cluster-mcp-rcac/README.md:6`; `docs/rcac/README.md:3-4`),
and `AGENTS.md` § Packaging (`:1694-1697`) records the RCAC member's independence from the Slurm
member as the design.

The maintainer has since set the rule (maintainer decision, 2026-11-12): **a center's extra installs
every extra its center's clusters need.** RCAC is a Slurm shop, so `[rcac]` alone must serve what
`[slurm,rcac]` serves today. The rest of the `[rcac]` bundle (LMOD, xdu, shell, the site interfaces)
stays where Part II of `ROADMAP.md` orders it.

**Pre-existing:** yes. The one-member `rcac` extra landed with `capability-extras` (`4e772ec`,
2026-11-01), which left a Slurm dependency to its plan (that GOAL's Q4) and recorded `[rcac]` as
half of `issues/site-extras.md` R1.

## Outcome / vision

`cluster-mcp[rcac]` is the one install line an RCAC user needs, and every doc says so. A user who
already names `[slurm,rcac]` sees no change at all, so this ships as 0.2.2, a patch.

## Acceptance criteria (the contract)

- **R1** — WHEN a user installs `cluster-mcp[rcac]` (the core with the `rcac` extra and no other, in
  the README's `#subdirectory=packages/cluster-mcp` git form), the install SHALL include the Slurm
  member, and the server it starts SHALL serve the same tools, instructions and resources that a
  `cluster-mcp[slurm,rcac]` install serves.
- **R2** — WHEN a user installs `cluster-mcp[slurm,rcac]` (in either order), the root compat
  distribution `rcac-mcp`, or the development environment `uv sync` builds, the server SHALL serve
  exactly what it serves on `916cecf`: no served tool, instruction, resource or server-info field
  changes. The fixture's `both` and `both-reversed` entries are the evidence.
- **R3** — WHEN a user installs `cluster-mcp[slurm]` alone, or the bare core, the install SHALL
  include no RCAC member, as on `916cecf`.
- **R4** — WHILE the RCAC member is registered without the Slurm member (as when the startup probe
  withholds the Slurm member on a cluster without Slurm's client commands), the server SHALL serve
  what the fixture's `rcac` set records on `916cecf`, and `tests/fixtures/served_surface.json` SHALL
  NOT change in this cycle; the tests and docs that name the `rcac` set SHALL describe it as the
  RCAC member registered alone, the state the probe can reach, not as the `[rcac]` install (Q1).
- **R5** — IF the `rcac` extra stops installing the Slurm member, or the `slurm` extra starts
  installing the RCAC member, THEN a test in the suite SHALL fail, naming the extra. The packaging
  test that today pins each extra to exactly one member (`tests/test_packaging.py:155`,
  `test_core_declares_the_capability_extras`, and its module docstring `:15-19`) SHALL pin the new
  rule instead, in the declarations and in the installed metadata. The rule SHALL live in the core's
  `[project.optional-dependencies]` alone: its `rcac` extra lists both members, and each member keeps
  depending on the core alone (Q2).
- **R6** — Every install line for an RCAC cluster SHALL name `cluster-mcp[rcac]` alone, and no
  in-repo text SHALL say that `[rcac]` must be installed with `[slurm]` or that the RCAC member does
  not bring the Slurm member. The lines today: `README.md:5-6`, `:18`, `:28-29`, `:33`, `:45`;
  `packages/cluster-mcp/README.md:9-13`; `packages/cluster-mcp-rcac/README.md:6`;
  `docs/core/README.md:12`, `:19-22`; `docs/rcac/README.md:3-4`; the comment at
  `packages/cluster-mcp/pyproject.toml:17-18`; `AGENTS.md:23`, `:68-71`, `:157-159`, § Packaging
  `:1694-1700` and `:1752`, and the release recipe's `post_verify` line marked "the README line"
  (`:1914`) with its `ci-mirror-no-index` and `install-probe` caveats (`:1928`, `:1977`).
  `SECURITY.md:267` names no extra (it points to the Quick Start), so it SHALL keep pointing there.
  Lines that describe the compat distribution's own `cluster-mcp[slurm,rcac]` dependency
  (`README.md:75`, `AGENTS.md:629`, `:1706`, `:1710`, the root `pyproject.toml`, `Dockerfile:12`)
  stay true and need not change.
- **R7** — `ROADMAP.md`'s `[rcac]` entry (`:649`) and site-interfaces entry (`:625`), and
  `issues/site-extras.md`, SHALL state the rule "a center's extra installs every extra its center's
  clusters need", cite it as "maintainer decision, 2026-11-12", and record that `[rcac]` brings
  `[slurm]` from 0.2.2. The `[rcac]` entry's other items, its horizon and its place in Part II's
  order SHALL NOT change. No internal path, board id or person's name SHALL appear.

**Publish gate.** `tests/fixtures/served_surface.json` is on `AGENTS.md` § Invariants'
high-blast-radius list. Publishing this cycle takes the maintainer's sign-off on the fixture
outcome: its bytes unchanged, as R4 requires.

## Non-goals (no-gos)

- **The baseline part of the 2026-11-12 decision**: a center's extra also implementing the site
  interfaces every named center provides. Site-interfaces shaping will propose it.
- **The rest of the `[rcac]` entry**: `[lmod]`, `[files-xdu]` and `[shell]` in the bundle, the site
  interfaces over `myquota` and `mybalance`, member routes and the favicon, the contributor contract
  for a new center's extra, and the composition of packaged site context with `/etc/agents.d`. Each
  stays in Part II's order.
- **Any change to what a server serves** for any install that works today (R2), including renaming,
  re-describing or removing a tool.
- **A dependency of the RCAC member on the Slurm member**, so that installing the member
  distribution by its own name also brings Slurm (Q2).
- **The compat root `rcac-mcp`, `uv sync` and the `Dockerfile`**: they keep depending on
  `cluster-mcp[slurm,rcac]`.
- **Other centers' extras**, publishing to PyPI, and any change to the startup probe.

## Clarifications

- **Q:** Which release, and what may it change? — **A:** 0.2.2, a patch release; it must not change
  any served tool for `[slurm,rcac]` users (maintainer decision, 2026-11-12).
- **Q:** Is the baseline part of the decision (a center's extra implementing the site interfaces
  every named center provides) in scope? — **A:** No; site-interfaces shaping will propose it
  (maintainer decision, 2026-11-12).
- **Q:** `fix` or `feature`? — **A:** `fix`, for the 0.2.2 patch target: the release recipe proposes
  a minor version when a `feature` cycle has landed since the last tag (ruled by the foreman,
  2026-11-13).
- **Q:** May R6 change the release recipe's `post_verify` README line to `[rcac]`? — **A:** Yes; the
  compat-root line keeps `[slurm,rcac]` exercised (ruled by the foreman, 2026-11-13).
- **Q1:** After this change no extra installs the RCAC member without the Slurm member, so what does
  the fixture's `rcac` capability set (`tests/test_capabilities.py:88`, read by
  `tests/test_surface.py` `served_surfaces`) stand for? The set remains a served state: the startup
  probe withholds the Slurm member on a cluster without `sbatch`, `squeue`, `scancel`, `sacct`,
  `sinfo` and `scontrol` while serving the RCAC member, whose commands are `findscratch` and
  `myquota` (`tests/test_probe_startup.py:814-818`). Options:
  (a) keep the set and its fixture entries byte for byte, and reread it as "the RCAC member
  registered alone", reachable through the probe and no longer through an extra (R4 as written; no
  fixture diff);
  (b) rename the set (say `rcac-alone`), a fixture diff across every RCAC entry plus every test id
  and `tests/mutants.py:330` `MEMBER_SETS` row that names it;
  (c) redefine `rcac` as the install, core + RCAC + Slurm, which duplicates `both-reversed` and
  drops the only coverage of the RCAC member registered alone;
  (d) drop the set, which loses that coverage too.
  — **A:** (a). The fixture's `rcac` set stays byte for byte and is read and documented as "the
  RCAC member registered alone", the probe-reachable state; no fixture diff (ruled by the foreman,
  2026-11-13).
- **Q2:** Should the RCAC member distribution itself depend on the Slurm member, so that
  `uvx --from` naming `cluster-mcp-rcac` also brings Slurm? Evidence: no member is a supported
  install target on its own (`packages/cluster-mcp-rcac/README.md:6`,
  `packages/cluster-mcp-slurm/README.md:5`: "not on its own"); `AGENTS.md` § Packaging and
  `tests/test_packaging.py:162` pin that each member depends on the core alone; and the
  site-extra design keeps the dependency alias in the core's extras and the site's point of view in
  its member (`issues/site-extras.md`, Problem and its 2026-11-09 note: the `rcac` alias lists
  distribution names). A member dependency would also make R4's state reachable only through the
  probe. — **A:** No. The rule goes in the core's optional-dependencies only, with `rcac` listing
  both members; the members keep depending on the core alone, and a member dependency is a non-goal
  (ruled by the foreman, 2026-11-13).

## Related materials

- Seed context: [`issues/site-extras.md`](../../issues/site-extras.md) (R1 and R7, which this
  cycle meets in part), [`issues/site-interfaces.md`](../../issues/site-interfaces.md).
- Prior cycles: [`spec/capability-extras/`](../capability-extras/) (Q4 left the Slurm dependency to
  its plan), [`spec/surface-fixture-after-a-surface-change/`](../surface-fixture-after-a-surface-change/)
  (the fixture and its update mode).
- Sources: `packages/cluster-mcp/pyproject.toml`, `packages/cluster-mcp-rcac/pyproject.toml`,
  `tests/test_packaging.py`, `tests/test_capabilities.py`, `tests/test_surface.py`,
  `tests/fixtures/served_surface.json`, `AGENTS.md` § Packaging, § Invariants and the release recipe.
