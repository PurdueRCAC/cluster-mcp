# 00 — Digest: the decisions the briefs settle

Five briefs, fanned out 2026-10-29: [01 workspace packaging](01-workspace-packaging.md),
[02 deprecation shims](02-deprecation-shims.md), [03 tests and mutants](03-tests-and-mutants.md),
[04 instructions and surface](04-instructions-and-surface.md),
[05 repository text, CI, release](05-repo-text-ci-release.md). 01 and 05 ran throwaway uv labs on
uv 0.12.17 (the floor and CI's pin) and 0.13.6; the planner then built a prototype of the move in a
detached worktree and dry-ran this cycle's gates on it (PLAN § 4).

## Decisions

1. **The root is a project: the compat distribution `rcac-mcp`.** 01 recommended a virtual root;
   05 found that a virtual root breaks the one install line the README has documented since 0.1.1
   (`uvx git+https://github.com/purduercac/rcac-mcp`: uv finds no executable at the root), so every
   existing user's client config would fail at 0.2.0 and never reach the `rcac-mcp` warning, against
   the GOAL's Outcome ("an existing user's `rcac-mcp` command … keep working through a stated
   deprecation window"). **Resolved for 05:** the root `pyproject.toml` is a fourth, code-less
   distribution `rcac-mcp` (depends on `cluster-mcp`; installs only the `rcac-mcp` script →
   `cluster_mcp.core:legacy_main`; wheel `bypass-selection`, sdist `only-include` of its
   `pyproject.toml` and `README.md`) and also the workspace root. Prototyped: `uv sync --locked`
   installs every member, the old line runs `rcac-mcp` from the same commit, and the
   `#subdirectory=packages/cluster-mcp` line runs `cluster-mcp`. Core installs only `cluster-mcp`, so
   no two distributions claim one script. 03's worry that `uv sync --locked` installs no members at
   a virtual root is moot (and was wrong per 01 and 05's labs).
2. **Members and dependencies (01).** `packages/cluster-mcp` (`cluster_mcp.core`),
   `packages/cluster-mcp-slurm` (`cluster_mcp.slurm`), `packages/cluster-mcp-rcac`
   (`cluster_mcp.rcac`). A declared cycle: core depends on both members, each member on core, all
   through `{ workspace = true }` sources. Internal requirements carry **no version pin** (05): uv
   drops them from the lock anyway, and unpinned names keep the release's bump diff to version
   lines. One version across all four distributions, pinned by a unit test (uv does not check it).
3. **Hatch: `only-include = ["src/cluster_mcp/<cap>"]` + `sources = ["src"]`** (01, lab: `packages =`
   ships a stray `cluster_mcp/__init__.py`). Each member has its own short `README.md` (a readme
   outside the member fails the sdist build). The favicon ships in the core wheel unchanged (04).
4. **Build: `uv build --all-packages --no-sources -o dist/`.** Plain `uv build` fails at the
   workspace root. 01 said to drop `--no-sources`, 05 to add it; the recipe's own `no-sources`
   caveat says to add it once a source override exists, and the prototype built identical artifacts
   with it (build dependencies from the index; workspace sources never reach wheel metadata), so it
   is added and the caveat rewritten to say what it does now.
5. **Env (02).** One resolver, `cluster_mcp.core.deprecation.env_setting(name) -> (value, source)`,
   with `WINDOW` ("deprecated in 0.2.0, removed no earlier than 0.4.0") and the legacy map in the
   same module. Replacement wins when non-empty; a non-empty legacy value is honoured with a stderr
   warning, once per process per name; both set: replacement wins and the ignored legacy name draws
   its warning too. **Never strip** (a whitespace-only host is truthy today and selects `ssh`).
6. **`rcac-mcp` (02):** `legacy_main(argv)` beside `main`: warning on stderr, then `return main(argv)`.
   `APP_NAME = 'cluster-mcp'`, so help is byte-identical. R3's "nothing it prints SHALL go to stdout"
   is read as the wrapper's own output: `--help`/`--version` print to stdout for both commands alike.
7. **URI aliases (02, against 04's preference):** derived `RESOURCE_REGISTRY` entries
   (`{**entry, 'uri': …'rcac://'…}`) appended before the unchanged `OPEN_RESOURCES` derivation, so
   `OPEN_RESOURCES == {cluster://context, rcac://context}` and an alias cannot drift from its target's
   `executor` flag; `middleware.py` is untouched. The aliases are listed: 04 preferred unlisted ones,
   but every unlisted route is either a middleware rewrite (scheme normalisation, which §1 forbids)
   or a FastMCP transform that runs after the read hook and would refuse `rcac://context` in
   delegate mode. Alias descriptions equal their targets' (R8 names no description delta).
8. **Storage resource stays in core `resources.py`** with its lazy import moved to
   `cluster_mcp.rcac.tools`; the alias derivation must see every entry before `OPEN_RESOURCES`
   (02's placement caveat). Moving it is capability-extras' business.
9. **Instructions (04):** `CORE_INSTRUCTIONS`, `SLURM_INSTRUCTIONS`, `RCAC_INSTRUCTIONS` in
   import-free `instructions.py` leaves of each member; `server.py` keeps the name
   `SERVER_INSTRUCTIONS` for their `'\n\n'` join. Slurm lines live in the Slurm member, not the core.
   The core names `cluster://context`, the overlay `cluster://storage`; neither names an alias. Base
   1,374 units (+41).
10. **Server name `cluster-mcp`** (`FastMCP(name=…)`), pinned by a new test in both eras: the fixture
    has no name slot (04), so R8's server-name delta is zero bytes of fixture.
11. **Tests stay in root `tests/`; mutation cases name files namespace-relative** (`core/…`,
    `slurm/…`, `rcac/…`) and the runner copies all three portions and checks all three origins (03).
12. **SPDX: all header lines, `spec/` included** (03, 05): R14 has no carve-out and the GOAL's 93
    count includes spec/'s 29; the history non-goal protects quoted old names, and a header is file
    metadata.
13. **Not renamed, deferred:** the JWT `ISSUER`/`AUDIENCE` `'rcac-mcp'` (renaming invalidates every
    minted token), `serverInfo.version` (FastMCP's own), and the Purdue favicon in core →
    `issues/rename-leftover-identity-strings.md` + its ROADMAP entry.

## Contradictions resolved

| Between | On | Resolution |
|---|---|---|
| 01 / 05 | virtual root | compat root `rcac-mcp` (decision 1) |
| 01 / 05 | `--no-sources` | added, caveat rewritten (decision 4) |
| 01 / 05 | `==` pins between members | none; a one-version unit test (decision 2) |
| 02 / 04 | aliases listed or not | listed, derived (decision 7) |
| 03 / 01, 05 | `uv sync --locked` at the root | installs every member (labs); moot with a project root |
