# PLAN — Remove the documentation search subsystem

> **Status:** Draft for review · **Last updated:** 2026-10-16
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

Remove the subsystem in four behavioural slices. Each slice lands its replacement test before it
retires any of the old suite:

1. the two tools and every agent- and human-facing mention of them, guarded by a new
   instructions↔registry cross-check;
2. the three CLI flags, guarded by a sandboxed CLI integration test;
3. the `rcac_mcp.docs` package and the docs-only test suite, replaced by a marker-enforcing
   conftest;
4. the packaging leftovers (dependencies, submodule) and the `AGENTS.md` record.

Nothing is added to the server. The only new code is three test files and a conftest hook. Each
test file puts its check in a pure function, runs that function against known-bad inputs as a
standing negative control, and exposes it to the `verify:` gates, which feed it their own mutated
inputs. The `big` appetite goes on making those lasting gates fail red when they should, not on
the deletions.

## 2. Design

### 2.1 Tools and the agent-facing surface (R1, R4, R5, R6)

- Delete `src/rcac_mcp/tools/docs.py` and the `from rcac_mcp.tools import docs` line at the bottom
  of `src/rcac_mcp/tools/__init__.py` (§7: the import list *is* the registry). `TOOL_REGISTRY` drops
  from 25 to 23.
- `src/rcac_mcp/server.py`: delete the `IMPORTANT — Documentation Search` block and the
  `Documentation Search:` list from `SERVER_INSTRUCTIONS`. Every other line stays byte-identical
  (non-goal: no restructuring). No pointer to `rcac-docs-mcp` is added.
- `INSTRUCTIONS.md`: delete the `Documentation:` paragraph (the file's only docs mention). No
  pointer is added.
- `README.md`: delete § *Documentation Search Index* and the `### Documentation` inventory
  subsection. Add a short `## RCAC Documentation` section where the old section was. It says that
  this server does not search RCAC documentation, and that the `rcac-docs-mcp` service at
  `https://docs.rcac.purdue.edu/mcp` does and should be added to the MCP client alongside this
  server. The section names no removed flag, tool or `RCAC_DOCS_DB`, and invents no client
  configuration this repository does not own.
- All of the above land in **one commit** (§9, § Conventions).

### 2.2 The CLI (R2, R3)

In `src/rcac_mcp/__init__.py`, remove:

- the three `interface.add_argument` calls and their class attributes (`index_docs_flag`,
  `docs_path`, `docs_output`);
- the `[--index-docs …] [--docs-output …]` line of `APP_USAGE`;
- the `Documentation Indexing:` block and the `--index-docs` example of `APP_HELP`, moving the
  closing `\` onto the new last example line;
- the `if self.index_docs_flag:` branch at the top of `run()`, and its clause in the docstring;
- `_run_index_docs()`.

All of it lands in one commit.

No replacement handling is needed. cmdkit's `Interface.error()` raises `ArgumentError`, and
`Application.main()` logs `unrecognized arguments: <flag …>` and returns
`exit_status.bad_argument` before `run()` is reached. The server therefore cannot start and no file
can be written ([01](research/01-cmdkit-unknown-flag.md)). `_resolve_exec_mode()` and
`_create_executor()` are not touched (§4). A verify guard, run in P2 and again in P6, compares the
AST of both functions, and of `run()` minus its first branch, with `3cb2853`.

### 2.3 The package, the test suite, and the gates' contract (R1, R3, R4, R5, R9)

- Delete the whole `src/rcac_mcp/docs/` directory with `del`, including its untracked
  `__pycache__/`. If that cache is left behind, `import rcac_mcp.docs` keeps working as a namespace
  package ([02](research/02-removal-inventory.md)). Also delete `tests/test_database.py` and
  `tests/test_indexer.py`.
- Rewrite `tests/conftest.py` to hold one hook: `pytest_collection_modifyitems` raises
  `pytest.UsageError` naming every collected item that carries neither `unit` nor `integration`.
  The independent witness runs **with `--noconftest`**, so a conftest that adds markers itself
  cannot satisfy it.

Each test file exposes a **pure check function**. Its tests run that function on the real
artifact, expecting no violations, and on mutated inputs, expecting violations; these are the
standing negative controls. The `verify:` gates import the same function (`sys.path.insert(0,
'tests')`) and feed it mutations written into `TECH.md` itself. A hollow function, or a test file
replaced by `assert True`, therefore fails a gate whose inputs the builder does not control. The
gates also require a `PASSED` line for **every named test id** below (fixed strings), and no
`SKIPPED`/`XFAIL`/`XPASS`.

| File | Contract (names are load-bearing: the gates grep them) |
|---|---|
| `tests/test_registry.py` | `EXPECTED_TOOLS` (frozenset of the 23 names); `registry_violations(names: Sequence[str]) -> list[str]` (missing, extra, duplicate, `doc_`-prefixed); `module_absent(name: str) -> bool` (`find_spec` is `None`, a missing parent counting as absent). Tests: `test_registry_matches_expected_tools` (over `TOOL_REGISTRY`); `test_served_tools_match_registry` (the names `asyncio.run(create_mcp_server('none').get_tools())` serves == `EXPECTED_TOOLS`); `test_registry_check_catches_drift[added-doc, missing, duplicate]`; from P3 on, `test_docs_modules_absent[rcac_mcp.docs, rcac_mcp.tools.docs]` (`module_absent` and `ModuleNotFoundError` whose `.name` is that module), and `test_absence_check_catches_namespace_leftover` (a temporary `pkg/sub/__pycache__/`-only tree on `sys.path`: `module_absent('pkg.sub')` is `False`). All `unit`. |
| `tests/test_instructions.py` | `NON_TOOL_TERMS = frozenset({'findscratch'})`; `DOCS_GUIDANCE = (?i)\bdoc(?:s\|umentation)?\b\|\bdoc_\w*\|\buser[\s_-]?guides?\b`; `guidance_violations(text) -> list[str]`; `instruction_violations(text, names, allow=NON_TOOL_TERMS) -> list[str]` (the cross-check below, plus `guidance_violations`). Tests: `test_instructions_match_registry[constant, served]` (`SERVER_INSTRUCTIONS` and `create_mcp_server('none').instructions`); `test_instructions_md_has_no_docs_guidance` (`guidance_violations` over `INSTRUCTIONS.md`, the standing form of R5); `test_cross_check_catches_mutation[doc-entry, unknown-entry, missing-entry, ticked-doc, unknown-snake, allowlist-launder, allowlist-stale, user-guides, docs-word]`. All `unit`. |
| `tests/test_cli.py` | `flag_violations(returncode: int, stdout: str, stderr: str, flags: Sequence[str]) -> list[str]` (status ≠ `exit_status.bad_argument`; no `unrecognized arguments:.*<flag>` for some flag; `Execution mode` in stderr; non-empty stdout; a `DBFILE:` line). Tests: `test_removed_flag_is_rejected[index-docs, docs-path, docs-output, all-three, local-index-docs]` (`integration`); `test_flag_check_rejects_a_known_flag` (`integration`: a real sandboxed drive of the *accepted* `--generate-token`, which exits 2 with `JWT_SECRET … required`; `flag_violations` must be non-empty); `test_flag_check_catches_silent_accept[started, ssh-host, db-written, stdout]` (`unit`, synthetic results). |

**R4 cross-check** (`instruction_violations`). It extracts:

- `listed`: names matching `^- ([a-z_][a-z0-9_]*):(?=\s)` (multiline);
- `ticked`: names matching `` `([^`\s]+)` ``;
- `snake`: names matching `\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b`.

It reports a violation when any of these holds:

- the registry is empty, or has duplicate names;
- a registered tool is missing from `listed`;
- `(listed ∪ ticked ∪ snake) − registry − allow` is non-empty;
- `allow` contains a registered tool name;
- an `allow` term does not occur in the text;
- `DOCS_GUIDANCE` matches.

([03](research/03-instructions-registry-crosscheck.md); prototyped on a simulated post-change text:
no violations on the clean text, at least one on every mutation.)

**R3 drive.** The test runs `subprocess.run([<repo>/bin/sandbox.sh, 'sh', '-c', SCRIPT, 'sh',
<cli>, *argv], capture_output=True, text=True, timeout=60, cwd=tmp_path)`.

- `<cli>` is `Path(sys.executable).with_name('rcac-mcp')`, asserted to exist.
- `SCRIPT` runs `"$@"` with stdin from `/dev/null`, prints `DBFILE: <path>` to stderr for each
  `*.db` under the sandbox `HOME`, and exits with the CLI's status.
- Each case asserts `flag_violations(...) == []` and that `<tmp>/docs.db` does not exist.

Because the test itself runs the drive through the sandbox, it stays contained both under the
profile's unsandboxed `uv run pytest -q` and under the sandboxed form. It has no skip path.

### 2.4 Packaging (R7, R8)

- `pyproject.toml`: remove `pyyaml>=6.0` and `jinja2>=3.1` from `[project.dependencies]`, run
  `uv lock`, and commit both files together. `jinja2` and `markupsafe` leave the lock; `pyyaml`
  stays as a transitive dependency of `fastmcp`, which is correct. The sdist `exclude` keeps
  `/tests/fixtures`.
- `git rm tests/fixtures/RCAC-Docs` (the gitlink) and `git rm .gitmodules`; remove the empty
  `tests/fixtures/` directory left behind.

### 2.5 The record (R10, plus drift) and the committed-state gate

`AGENTS.md` changes:

- Drop the repository-map row for `docs/` + `tools/docs.py`.
- Rewrite § Testing for the new suite: three marked files with pure check functions, a
  marker-enforcing conftest, and no fixture submodule. PyYAML is not a dependency of this repo.
- Rewrite the § Commands `-m unit` note.
- Rewrite the § Invariants → Conventions marker bullet. Keep its rule against marker-only gates;
  drop "no existing test carries a marker".

`AGENTS.md` may say that documentation search lives in `rcac-docs-mcp`. It never describes a docs
subsystem, tool, flag, fixture or submodule as present. It never uses the words "submodule",
"FTS5" or "indexer", and never names a `doc_` identifier.

Seeds:

- `issues/restore-test-coverage.md`: correct its description of the post-strip state.
- `issues/agents-d-instructions.md`: add a one-line note that `tests/test_instructions.py` must be
  rescoped when the served instructions are composed, and record the prose-word limit there.

**P6 also re-runs every earlier single-phase check** (R2's `--help` drive, R3's direct drive, the
§4 AST guard, the R5/R6 greps, the R1/R3/R4 gate-level negative controls). It then **verifies the
committed state**: inside the sandbox it runs `git clone` on the branch, then
`unset VIRTUAL_ENV`, `UV_PROJECT=$PWD`, `uv sync --locked`, `uv lock --check`, and asserts that
`rcac_mcp.__file__` resolves inside the clone (the sandbox's own `UV_PROJECT` would otherwise
silently run the original tree). It finishes with the full `-rA` run and its per-id `PASSED` greps,
plus the R7/R8 checks on the clone. A file left on disk but missing from a commit fails there.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | §2.1 tool removal (23 tools); §2.3 package deleted as a directory; `test_registry.py` (registry, served tools, module absence, negative controls) |
| R2 | §2.2 `APP_USAGE`/`APP_HELP` edits; sandboxed `--help` drive in P2 and P6 |
| R3 | §2.2 flag removal (cmdkit's own `bad_argument` path); `test_cli.py` through `bin/sandbox.sh`, with a real known-flag control |
| R4 | §2.1 `SERVER_INSTRUCTIONS` edits; `test_instructions.py` cross-check over the constant and the served text; gate-level mutations |
| R5 | §2.1 `INSTRUCTIONS.md` paragraph deleted; `test_instructions_md_has_no_docs_guidance` |
| R6 | §2.1 README sections deleted, `rcac-docs-mcp` pointer added; greps in P1 and P6 |
| R7 | §2.4 gitlink and `.gitmodules` removed; fresh-clone check in P6 |
| R8 | §2.4 dependency edit + `uv lock` in one commit; checked again on the clone |
| R9 | §2.3 three marked test files covering R1/R3/R4; conftest hook; `--noconftest` exit-5 witness; suite run on the clone |
| R10 | §2.5 `AGENTS.md` rewrite |

## 3. Invariant gate (AGENTS.md constitution check)

The gate was walked twice: from the GOAL before research, and again against this design (after the
adversarial review). Sections touched: §4, §7, §9 and § Conventions, plus § Packaging and
§ Testing (non-invariant sections that the conventions cite). High blast radius: `server.py` and
`__init__.py`. Untouched: §1–§3, §5, §6, §8 and `bin/sandbox.sh`.

- **§4 Execution-mode resolution** — `_resolve_exec_mode()` and `_create_executor()` are not
  edited; `run()` loses only its first branch. An AST comparison against `3cb2853` enforces this in
  P2 and P6.
- **§7 Tool registration** — one import line is removed together with the module it imports. The
  registry test pins the 23 survivors, and the served-tools test pins what FastMCP actually
  exposes.
- **§9 Agent-facing surface** — tool removal, `SERVER_INSTRUCTIONS`, `INSTRUCTIONS.md` and the
  README inventory share one commit (P1). From here on, the cross-check makes the rule executable.
  No tool docstring changes.
- **§ Conventions**:
  - CLI flags and `APP_USAGE`/`APP_HELP` share a commit (P2); `compose.yml` and the `Dockerfile`
    carry no docs flag.
  - Dependencies and `uv.lock` share a commit (P4).
  - Every new test carries a marker.
  - Every CLI drive runs under `bin/sandbox.sh`, and sandboxed pytest drives `cd
    "$CLUSTER_MCP_REPO"`.
  - Tests use `exit_status.bad_argument`, never a literal.
  - Test comments and docstrings cite no `R#`/`P#`.
  - No `Co-Authored-By` trailer.
- **§ Packaging** — `uv.lock` stays tracked and is regenerated with the dependency edit. The sdist
  exclude list is unchanged (GOAL clarification).
- **§ Testing** — the new integration test drives the installed CLI under `bin/sandbox.sh`. P6
  rewrites the section so it describes the new suite.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| A conftest hook that rejects unmarked tests (test infrastructure beyond the tests R9 names) | R9 requires *every* collected test to carry a marker. The hook keeps that true for the `restore-test-coverage` cycle that rebuilds the suite next | A verify-only check (`--noconftest --collect-only -m "not unit and not integration"` → exit 5) proves it once and then decays. It stays as the independent witness |
| Negative-control tests (`…_catches_…`, `test_flag_check_rejects_a_known_flag`) beyond the bare R1/R3/R4 checks | They are part of those checks, not new coverage. Without them a hollow check passes every gate (adversarial review finding 1) | Mutations recorded only in commit bodies prove the gate once, at build time, and never again |

## 4. Rabbit holes (resolved)

- Does a removed flag exit with `bad_argument` and name itself? → Yes, through cmdkit's
  `ArgumentError` path, before `run()`. But `ValueError` shares status 2, so the status alone cannot
  witness R3 ([01](research/01-cmdkit-unknown-flag.md)).
- What exactly references the subsystem? → The full inventory is in the brief. Container files and
  git config are clean, and `pyyaml` stays in the lock transitively
  ([02](research/02-removal-inventory.md)).
- Does `import rcac_mcp.docs` fail after deletion? → Not if `__pycache__` is left behind: the
  directory then imports as a namespace package. Delete the directory, and test with `find_spec`
  plus a standing namespace-leftover control ([02](research/02-removal-inventory.md)).
- How is the instructions cross-check not hollow? → Three extraction shapes, both inclusion
  directions, a self-checking allowlist, and a docs-guidance ban, checked over both the constant
  and the served text ([03](research/03-instructions-registry-crosscheck.md)).
- How does an integration test stay contained when the profile's verify runs pytest unsandboxed?
  → The test wraps its own drives in `bin/sandbox.sh`; nesting was verified
  ([04](research/04-test-scaffolding.md)).
- **Adversarial design review (trigger 3) — ran 2026-10-16.** The foreman ran a fresh reviewer. It
  built a correct P1–P6 in a scratch clone and ran every verify string, byte-identical to the YAML,
  under both sh and zsh. Its verdict: fit once findings 1–6 were folded in; the foreman ruled to
  fold in all nine. What each finding changed:
  1. **HIGH: hollow test files passed every gate** (executed: `assert True` plus a
     `- doc_find:` entry → P1 green). → Each check is now a pure function with standing
     negative-control tests (§2.3 table). The gates import those functions and feed them mutations
     fixed in `TECH.md`, and require a `PASSED` line for every named test id. R1 and R3 get the
     same shape: registry drift and namespace-leftover controls, and a real sandboxed
     `--generate-token` drive plus synthetic silent-accept results.
  2. **HIGH: R5 ban too narrow** ("search the RCAC user guides at docs.rcac…" passed). →
     `DOCS_GUIDANCE` now also bans `user guides`, and runs over `INSTRUCTIONS.md` in a standing
     test (`test_instructions_md_has_no_docs_guidance`). The gate-level control feeds it exactly
     that sentence.
  3. **HIGH: a conftest could add markers itself and satisfy the witness.** → The witness runs
     with `--noconftest` (executed by the reviewer: red with an unmarked test, exit 5 on the clean
     tree).
  4. **HIGH: gates read the working tree, not the commit** (a file dropped from the commit but
     left on disk passed). → P6 runs the suite and the R7/R8 checks inside a fresh `git clone`,
     with `UV_PROJECT=$PWD` and an assertion that `rcac_mcp` imports from the clone. Without that
     override, the sandbox's `UV_PROJECT` silently runs the original tree.
  5. **MEDIUM: P3 grep hit the stale binary `tools/__pycache__/docs.*.pyc`.** → `grep -rnI` (text
     files only) in P3, P4 and P6.
  6. **MEDIUM: single-phase checks never came back.** → P6 repeats the §4 AST guard, the R2
     `--help` drive, R3's direct drive, the R5/R6 greps, and the R1/R3/R4 gate-level controls.
     *Not adopted:* a standing `--help` test for R2. GOAL's non-goals say "this cycle's only tests
     are the ones R9 names" (R1, R3, R4), and a `--help` test would be a new check for R2. It is a
     one-test addition if the foreman rules R2 in; until then R2 is gated by the P2 and P6 drives.
  7. **LOW: search guidance with no doc-words passed.** → Narrowed by the `user guides` ban. The
     plain-word limit stays recorded (§5).
  8. **LOW: the served tool list was unchecked.** → `test_served_tools_match_registry`.
  9. **LOW: the R10 grep missed `doc_*`, "FTS5", "indexer".** → Added to P6's `AGENTS.md`
     pattern.

## 5. Risks & open questions

- **Prose-word tool names are invisible to the cross-check.** A removed tool whose name is a plain
  word (`slist`) still passes when prose mentions it without backticks, as does guidance that avoids
  both doc-words and "user guides". The list-entry format is the contract. The limitation is
  recorded in the `agents-d-instructions` seed, which reshapes the instructions.
- **The cross-check binds future instruction work.** `agents-d-instructions` (composed text, tool
  families) and `rename-to-cluster-mcp` will have to amend `test_instructions.py`. That is the gate
  doing its job; P6 records it in the seed.
- **`EXPECTED_TOOLS` is a hard-coded list.** Every future tool change edits it in the same commit.
  That matches §9's same-commit rule and is intended.
- **The gates import test modules** (`sys.path.insert(0, 'tests')`). Renaming a check function or a
  test id breaks a gate loudly, never silently. The names in §2.3 are a contract.
- **Cost.** The R3 test runs about six sandboxed process launches (~1 s each), and P6's clone run
  adds ~6 s. Acceptable; there is no CI.
- **Builder's local tree.** A worktree that keeps `src/rcac_mcp/docs/__pycache__` fails the R1 test
  red (never green), so `del` the whole directory.
- **Open for the foreman:** whether R2 should get a standing `--help` test despite the non-goal
  (finding 6, not adopted).

## 6. Verification strategy

**How each slice is built.** The slice writes its tests first and shows them red against the
unchanged tree. It then makes the change and shows them green.

**What every gate checks:**

- The suite: `uv run pytest -q`.
- A sandboxed pytest run with `-rA`, its output kept in the sandbox `HOME`. The run must contain a
  fixed-string `PASSED tests/<file>::<id>` line for every named id, and no
  `SKIPPED`/`XFAIL`/`XPASS`.
- Gate-level negative controls: the verify string imports the pure check functions and asserts
  that they reject mutations written into `TECH.md`.
- Direct CLI drives under `bin/sandbox.sh`. `--help` lacks the removed flags and still lists
  `--ssh-host`. `-e local --index-docs` exits 2 with `unrecognized arguments: --index-docs`, no
  `Execution mode`, and empty stdout.
- The §4 AST guard.
- `grep -I` / `git grep` for leftover mentions.
- `uv lock --check`, `uv tree --depth 1 --no-dev`, and a `tomllib` read of
  `[project.dependencies]`.
- The `--noconftest` exit-5 marker witness.

**The last phase** repeats every single-phase check and runs the suite and packaging checks inside
a fresh `git clone` of the branch, so that the committed state is what passes.

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
