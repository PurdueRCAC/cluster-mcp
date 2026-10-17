# 04 — Test scaffolding after the docs suite goes

Scope: conftest after the docs fixtures go, markers and their enforcement, the R3 integration test
under `bin/sandbox.sh` with pytest's rootdir handled, and how a `verify:` proves the suite is real.
pytest 9.0.2, pytest-asyncio 1.3.0 (locked).

## pytest facts that matter

- `[tool.pytest.ini_options] addopts = "--strict-markers"`, markers `unit` and `integration`; no
  `testpaths`, so collection walks from the rootdir (the repo, when pytest is started there).
- **A fully deselected run exits 5** (verified: `pytest -q --collect-only -m unit` on the base →
  exit 5, "no tests collected (81 deselected)"). So
  `pytest -q --collect-only -m 'not unit and not integration'` exits **5 iff every collected test
  carries a marker** — an independent, non-hollow check of R9's marker clause.
- Run from the sandbox's cwd, pytest roots itself in the throwaway dir and loses `pyproject.toml`
  (and `--strict-markers`); a sandboxed pytest drive must `cd "$CLUSTER_MCP_REPO"` first (AGENTS.md
  § Conventions).
- No test in the post-strip suite is async; `pytest-asyncio` stays installed and inert.

## conftest

The docs fixtures, `requires_submodule` and `FIXTURES_DIR` all go. What remains worth having is
**marker enforcement**: a `pytest_collection_modifyitems` hook that raises `pytest.UsageError`
listing every collected item carrying neither `unit` nor `integration`. It turns R9's "every
collected test carries a marker" from a one-time check into a standing rule for the
`restore-test-coverage` cycle that follows, at ~10 lines. The `--collect-only -m 'not unit and not
integration'` exit-5 check stays in `verify:` as the independent witness (the hook could be
mis-registered; the exit-5 check cannot be satisfied by an unmarked test).

Hook ordering: pytest's own `-m` deselection also runs in `pytest_collection_modifyitems`; whether
ours sees deselected items or not, an unmarked test is caught by the unfiltered run, which every
`verify:` includes.

## The R3 integration test: run the CLI *through* the sandbox

The profile's `verify` runs `uv run pytest -q` **outside** the sandbox, and the sandboxed form runs
it inside. A test that only works in one of them (or skips in the other) is hollow in that one. The
robust shape: the test itself invokes `bin/sandbox.sh` around each CLI drive (subprocess argv, no
shell quoting), so every drive is contained whether pytest runs inside the sandbox (nested sandbox:
verified to work, `sandbox.sh` resolves its root from its own path and nests a fresh `mktemp -d`)
or not. This satisfies both AGENTS.md rules at once: "a CLI drive … wrap it in `bin/sandbox.sh`" and
"integration tests … run under `bin/sandbox.sh`".

- **Binary:** the installed console script next to the interpreter,
  `Path(sys.executable).with_name('rcac-mcp')` — the "installed CLI" the `integration` marker names.
  The project is an editable install (`src_editable_impl_rcac_mcp.pth`), so it runs this tree.
  Assert it exists (fail, never skip).
- **Repo root:** `Path(__file__).resolve().parents[1]`; assert `bin/sandbox.sh` is executable.
- **Drive:** `[sandbox, 'sh', '-c', SCRIPT, 'sh', cli, *argv]` where `SCRIPT` runs `"$@"` with
  stdin from `/dev/null`, captures its status, then prints `DBFILE: <path>` to stderr for every
  `*.db` under the sandbox `HOME`, and exits with the CLI's status. `subprocess.run(…, timeout=60,
  capture_output=True, text=True, cwd=tmp_path)`.
- **Cases** (parametrised): `--index-docs`; `--docs-path <tmp_path>`; `--docs-output
  <tmp_path>/docs.db`; `--index-docs --docs-path <tmp_path> --docs-output <tmp_path>/docs.db` (the
  README's old invocation); `-e local --index-docs` (a silent-accept regression would start the
  server and exit 0 — brief 01 §3).
- **Assertions per case:** `returncode == exit_status.bad_argument` (imported from `cmdkit.app`, no
  literal); stderr matches `unrecognized arguments:.*<flag>` for each removed flag in argv;
  `'Execution mode' not in stderr`; `stdout == ''`; `'DBFILE:' not in stderr`;
  `not (tmp_path / 'docs.db').exists()`.

## The R1 checks (unit)

- `{t.name for t in TOOL_REGISTRY} == EXPECTED_TOOLS` (the 23 names, written out), with
  `len(TOOL_REGISTRY) == 23` and no name starting `doc_`.
- `importlib.util.find_spec('rcac_mcp.docs') is None` **and** `importlib.import_module` raises
  `ModuleNotFoundError` whose `.name == 'rcac_mcp.docs'` — the `.name` check stops a broken
  `rcac_mcp` import from passing for the wrong reason; `find_spec is None` catches the namespace-package
  footgun of brief 02. Same pair for `rcac_mcp.tools.docs`.

## Verify shapes (prototyped where marked)

- Marker witness: `uv run pytest -q --collect-only -m 'not unit and not integration'; test $? -eq 5`.
- Sandboxed integration run with no skips, one pytest run, output kept inside the sandbox `HOME`:
  `bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run pytest -q -rA -m integration > "$HOME/out"; s=$?; cat "$HOME/out" >&2; test $s -eq 0 && grep -q "^PASSED tests/test_cli.py::" "$HOME/out" && ! grep -q -E "^(SKIPPED|XFAIL|XPASS)" "$HOME/out"'`.
- Posture-ladder guard (prototyped: green on the ladder, red on `run()` until the branch goes): a
  one-line `uv run python -c` comparing `ast.dump` of `_resolve_exec_mode`/`_create_executor`
  against `git show 3cb2853:src/rcac_mcp/__init__.py`, and `run().body[2:]` (old) against
  `run().body[1:]` (new).
