# 02 — Removal inventory

Scope: every reference to the documentation subsystem in tracked files at `fce97d9` (= `3cb2853`
plus the GOAL), outside `spec/`. Method: `git grep -i` over `doc_search|doc_load|index.docs|
docs.path|docs.output|RCAC_DOCS_DB|docs\.db|rcac_mcp\.docs|RCAC-Docs|submodule|documentation search|
DocsIndexer|DocsDatabase|jinja|yaml`, then reading each hit; `git ls-files -s` for gitlinks;
`git config --list --show-origin` and `$(git rev-parse --git-common-dir)/modules` for local
submodule state.

## Code (delete)

| Path | What | Coupling |
|---|---|---|
| `src/rcac_mcp/docs/` (`__init__.py`, `database.py`, `indexer.py`, `schema.sql`) | FTS5 DB, walker, snippet + Jinja2 macro rendering | imported only by `tools/docs.py` and `__init__.py:_run_index_docs` |
| `src/rcac_mcp/tools/docs.py` | `doc_search`, `doc_load`, `RCAC_DOCS_DB` resolution | imports `rcac_mcp.docs.database`; nothing imports it except `tools/__init__.py` |
| `src/rcac_mcp/tools/__init__.py:32` | `from rcac_mcp.tools import docs` | the registration import (§7) |

**Footgun:** `src/rcac_mcp/docs/__pycache__/` exists in working trees. `git rm` leaves it, and a
directory holding only `__pycache__` imports as a **namespace package** (verified: `import pkg.sub`
succeeds with `<module 'pkg.sub' (namespace)>`). The directory must go entirely (`del
src/rcac_mcp/docs`), or `import rcac_mcp.docs` keeps succeeding locally. A stale
`tools/__pycache__/docs.*.pyc` is harmless: sourceless bytecode inside `__pycache__` is never
imported.

## CLI (`src/rcac_mcp/__init__.py`) — same commit as `APP_USAGE`/`APP_HELP`

- `APP_USAGE` line 58: `[--index-docs --docs-path PATH] [--docs-output PATH]`.
- `APP_HELP` lines 107–113 (the `Documentation Indexing:` block) and line 120 (the last example;
  the preceding example line's trailing `\` continuation must move onto the new last line).
- Attributes + `add_argument` lines 161–168.
- `run()`: docstring ("…or build docs index") and the `if self.index_docs_flag:` branch (180–182).
- `_run_index_docs()` (228–252).
- Untouched: `_resolve_exec_mode()` and `_create_executor()` (§4 posture ladder).

## Agent-facing surface — same commit as the tool removal (§9)

- `server.py:68–72` `IMPORTANT — Documentation Search` block; `:116–125` the `Documentation
  Search:` list. Removing both leaves the remaining sections intact; nothing else names `doc_*`.
- `INSTRUCTIONS.md:13` the `Documentation:` paragraph (the only docs mention in the file).
- `README.md:79–93` § *Documentation Search Index* (names both tools, `--index-docs`,
  `--docs-path`, `--docs-output`, `RCAC_DOCS_DB`, `docs.db`); `:129–132` `### Documentation`
  inventory subsection. No other README mention; § Development says only `pytest`.

## Tests (all 81 are docs tests)

`tests/conftest.py` (docs fixtures + `requires_submodule`), `test_cli.py` (`--index-docs` flows),
`test_database.py`, `test_indexer.py`, `test_tools.py` (imports `rcac_mcp.docs.*` and tests
`doc_*` registration). On this host the submodule is not initialised: `uv run pytest -q` → 55
passed, 26 skipped. Old tests import from `conftest` directly (`from conftest import …`).
`tests/test_tools.py` depends on `tools/docs.py`; `test_database`/`test_indexer`/`test_cli` depend
only on `rcac_mcp.docs` and the CLI flags.

## Submodule

- `.gitmodules` (only entry: `tests/fixtures/RCAC-Docs`, `git@github.com:PurdueRCAC/RCAC-Docs.git`).
- Gitlink `160000 1e3d3d7… tests/fixtures/RCAC-Docs` (uninitialised here: `git submodule status`
  prints `-1e3d3d7…`).
- No `submodule.*` keys in any git config; no `.git/modules/`. Nothing local to clean.
- `pyproject.toml` sdist `exclude` keeps `/tests/fixtures` (GOAL clarification).

## Packaging

- `pyproject.toml [project.dependencies]`: `pyyaml>=6.0`, `jinja2>=3.1`. The only importers are
  `src/rcac_mcp/docs/indexer.py:24–25`; nothing else under `src/` mentions `yaml` or `jinja`.
- `uv.lock` `rcac-mcp` entry lists both. After `uv lock`: **`jinja2` (and `markupsafe`) leave the
  lock; `pyyaml` stays**, pulled transitively by `fastmcp → jsonschema-path`. An R8 check must
  therefore inspect `[project.dependencies]` (with `uv lock --check`), never "pyyaml absent from
  uv.lock".
- `pytest-asyncio` (dev) has no async user after the strip; it stays (`[dependency-groups]` is out
  of R8, and `restore-test-coverage` will need it).

## No change needed

`Dockerfile` (copies `pyproject.toml README.md src/`; no flag, no submodule), `compose.yml`
(argv `-t http -H 0.0.0.0 -p 8000 -a jwt`), `nginx-dev.conf`, `SECURITY.md`, `.gitignore`,
`bin/sandbox.sh`.

## `AGENTS.md` (R10) — statements that become false

- § Repository map row `docs/ + tools/docs.py` ("Being removed…").
- § Testing: "No existing test carries one … deselect all 81", "`tests/conftest.py` currently
  provides only docs-index fixtures … every test … is a docs test", the `RCAC-Docs` submodule bullet,
  the PyYAML bullet's "runtime docs indexer" clause.
- § Commands: the `-m unit` NOTE ("selects NOTHING today").
- § Invariants → Conventions: "No existing test carries a marker, so `-m unit`/`-m integration`
  deselect everything today" (the rule against marker-only gates stays).

## Seeds that drift (issues/)

- `issues/restore-test-coverage.md` describes the post-strip state as an empty conftest and zero
  tests; after this cycle there are three marked test files and a marker-enforcing conftest.
- `issues/agents-d-instructions.md` will recompose the served instructions; the new
  instructions↔registry test (brief 03) constrains it.
- `issues/strip-docs-subsystem.md` (`adopted:strip-docs-subsystem`) and its `ROADMAP.md` entry are
  retired by `code rcac-mcp roadmap` after landing, not by this cycle.
