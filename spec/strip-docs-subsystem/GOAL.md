# GOAL — Remove the documentation search subsystem

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** strip-docs-subsystem
- **kind:** refactor
- **appetite:** big

## Problem

Agentic documentation retrieval moved to a separate `rcac-docs-mcp` service, hosted at
`docs.rcac.purdue.edu/mcp`. Documentation work evolves there and is no longer this repository's
responsibility, but the whole subsystem is still here. All of it is **pre-existing**, on `develop`
at `3cb2853` (and on `main` since `2def4a4`):

- `src/rcac_mcp/docs/`: an FTS5 index, a markdown walker, pymdownx snippet resolution, and a Jinja2
  macro renderer that loads `main.py` out of the RCAC-Docs repository.
- `src/rcac_mcp/tools/docs.py`: the `doc_search` and `doc_load` tools, and the `RCAC_DOCS_DB` →
  `~/.config/rcac-mcp/docs.db` resolution.
- Three CLI flags on `MCPServerApp` (`--index-docs`, `--docs-path`, `--docs-output`), their usage
  and help text (`src/rcac_mcp/__init__.py:58`, `:108–120`, `:161–168`), and the
  `_run_index_docs()` branch that short-circuits `run()` before the server starts (`:180`, `:228`).
- `SERVER_INSTRUCTIONS` opens with an `IMPORTANT — Documentation Search` block telling every
  connecting model to call `doc_search` before advising on anything RCAC-specific
  (`src/rcac_mcp/server.py:68–72`), and lists both tools again under `Documentation Search`
  (`:116–125`).
- `INSTRUCTIONS.md:13` carries the same instruction as a standalone system-prompt paragraph.
- `README.md` § *Documentation Search Index* (`:79`) documents the build step, and its tool
  inventory has a `### Documentation` subsection (`:129`).
- `tests/fixtures/RCAC-Docs`, a git submodule (`.gitmodules`) that exists only for the docs tests.
- `pyyaml` and `jinja2` in `[project.dependencies]`, added for the indexer.

One of these is worse than dead weight. The `SERVER_INSTRUCTIONS` block steers every agent towards a
capability this server should not own, and once the tools go it would name tools that do not exist:
the server inducing its own hallucination (§ Invariants §9).

The removal is larger than it looks. It spans the CLI, the agent-facing instructions, the packaging
metadata, a submodule, and the entire test suite: all 81 tests are docs tests, and `tests/conftest.py`
provides only docs fixtures. It touches two high-blast-radius paths (`server.py` and `__init__.py`,
§ Invariants → High-blast-radius paths), so the plan step runs research.

## Outcome / vision

The server starts, registers every tool it registered before except the two documentation tools,
and mentions documentation search nowhere in its agent-facing surface. Its CLI no longer knows the
indexing flags. A user who wants RCAC documentation reads in the README that it is served by the
`rcac-docs-mcp` service at `docs.rcac.purdue.edu/mcp`, because a silent removal reads as a
regression. A fresh clone needs no submodule. The indexer's runtime dependencies are gone, and the
profile's `verify` still runs a real, non-empty test suite.

## Acceptance criteria (the contract)

- **R1** — The `rcac-mcp` package SHALL register in `TOOL_REGISTRY` exactly the tools it registered
  at `3cb2853` (25) minus `doc_search` and `doc_load`, so no registered tool name begins `doc_`; and
  `import rcac_mcp.docs` SHALL fail with `ModuleNotFoundError`.
- **R2** — WHEN `rcac-mcp --help` is run, the output SHALL NOT mention `--index-docs`,
  `--docs-path`, or `--docs-output`.
- **R3** — IF any of `--index-docs`, `--docs-path`, or `--docs-output` is passed to `rcac-mcp`, THEN
  it SHALL exit with `exit_status.bad_argument` and an error naming the unrecognized flag, without
  starting the server or writing a database file.
- **R4** — `SERVER_INSTRUCTIONS` SHALL name no tool absent from `TOOL_REGISTRY`, SHALL list every tool
  in `TOOL_REGISTRY`, and SHALL carry no documentation-search guidance; a test SHALL cross-check the
  instructions against the registry.
- **R5** — `INSTRUCTIONS.md` SHALL carry no instruction to search documentation and SHALL name neither
  `doc_search` nor `doc_load`.
- **R6** — `README.md` SHALL have no *Documentation Search Index* section, no documentation tools in
  its tool inventory, and no mention of the removed flags or `RCAC_DOCS_DB`; and it SHALL tell a
  reader who wants RCAC documentation to use the `rcac-docs-mcp` service at
  `docs.rcac.purdue.edu/mcp`.
- **R7** — The repository SHALL have no `.gitmodules` file and no `tests/fixtures/RCAC-Docs` gitlink,
  so a fresh `git clone` needs no `git submodule update` and `git submodule status` prints nothing.
- **R8** — WHERE nothing under `src/` outside the removed subsystem imports `yaml` or `jinja2`,
  `[project.dependencies]` SHALL list neither `pyyaml` nor `jinja2`, and `uv lock --check` SHALL exit
  0.
- **R9** — WHEN the profile's `verify` runs, `uv run pytest -q` SHALL collect at least one test and
  exit 0, every collected test SHALL carry `@mark.unit` or `@mark.integration`, and the collected
  tests SHALL include checks for R1, R3 and R4.
- **R10** — `AGENTS.md` SHALL describe no documentation subsystem, documentation tool, docs CLI flag,
  docs test fixture, or `RCAC-Docs` submodule as present in the repository.

## Non-goals (no-gos)

- **Rebuilding test coverage** for the executor, middleware or tool core: the
  [`restore-test-coverage`](../../issues/restore-test-coverage.md) seed owns it. This cycle's only
  tests are the ones R9 names.
- **The rename** to `cluster-mcp`: [`rename-to-cluster-mcp`](../../issues/rename-to-cluster-mcp.md).
- **Any tool-surface or `SERVER_INSTRUCTIONS` restructuring** beyond removing the documentation
  guidance and the two tools: `agents-d-instructions` and `rename-to-cluster-mcp` own those. Neither
  `SERVER_INSTRUCTIONS` nor `INSTRUCTIONS.md` gains a pointer to `rcac-docs-mcp`.
- **Any change to `rcac-docs-mcp`** itself.
- **Deleting a user's existing `~/.config/rcac-mcp/docs.db`.** The server stops reading it and leaves
  it on disk.
- **Downstream pages that name this server's tools** (e.g. RCAC-Docs): kept whole at release time,
  not in this cycle.

## Clarifications

- **Q:** The seed's R5 required the factory's FSM scripts to keep resolving PyYAML. Does it still
  apply? — **A:** No. The repository moved to the KB-hosted factory on 2026-10-16, which runs those
  scripts with `uv run --with pyyaml`, and the dev pin was dropped at adoption. R5 is dropped, and this
  GOAL numbers its R-IDs afresh (resolved 2026-10-16).
- **Q:** Do `pyyaml` and `jinja2` go? — **A:** If and only if nothing else imports them (R8). A grep
  of `src/` at `3cb2853` found no import of `yaml` or `jinja2` outside `src/rcac_mcp/docs/`, so both
  are expected to go; the `[project.dependencies]` edit and its `uv lock` land in the same commit
  (§ Conventions) (resolved 2026-10-16).
- **Q:** Removing the subsystem removes all 81 tests, and `pytest` exits 5 when it collects none. What
  keeps `verify` meaningful? — **A:** The cycle's own tests: the registry and import check (R1), the
  removed-flag CLI check (R3, an integration test under `bin/sandbox.sh`), and the
  instructions↔registry cross-check (R4). Each carries `@mark.unit` or `@mark.integration` per
  § Conventions, so `-m unit`/`-m integration` select something too (resolved 2026-10-16).
- **Q:** Which edits must share a commit? — **A:** Removing the tools updates `SERVER_INSTRUCTIONS`,
  `INSTRUCTIONS.md` and the README tool inventory and docs section in the same commit (§ Invariants
  §9, § Conventions). Removing the flags updates `APP_USAGE`/`APP_HELP` in the same commit; no flag
  appears in `compose.yml` or the `Dockerfile` (resolved 2026-10-16).
- **Q:** Does the sdist exclude for `/tests/fixtures` stay? — **A:** It stays. § Packaging names
  `tests/fixtures/` among the paths the sdist must never ship, `restore-test-coverage` may bring
  fixtures back, and dropping the line would be a packaging-invariant edit outside this cycle
  (resolved 2026-10-16).
- **Q:** How are a refactor's criteria phrased? — **A:** As behaviour a user, a client or the CLI
  observes, not as implementation steps (resolved 2026-10-16).

All answers came from the cycle's foreman, which the maintainer made judge at every gate for this
effort.

## Related materials

- Seed: [`issues/strip-docs-subsystem.md`](../../issues/strip-docs-subsystem.md); roadmap entry in
  [`ROADMAP.md`](../../ROADMAP.md).
- Related seeds: [`restore-test-coverage`](../../issues/restore-test-coverage.md),
  [`rename-to-cluster-mcp`](../../issues/rename-to-cluster-mcp.md).
- `AGENTS.md` § Invariants §7 (tool registration), §9 (agent-facing surface), § Packaging,
  § Conventions, § Testing.
- Source: `src/rcac_mcp/docs/`, `src/rcac_mcp/tools/docs.py`, `src/rcac_mcp/tools/__init__.py`,
  `src/rcac_mcp/__init__.py`, `src/rcac_mcp/server.py`, `INSTRUCTIONS.md`, `README.md`,
  `.gitmodules`, `tests/`, `pyproject.toml`, `uv.lock`.
