# 00 — Research digest

Four briefs, written sequentially by the planner (no subagents available to a foreman's planner:
the spec's no-subagent fallback). Trigger 2 fired (`server.py`, `__init__.py` are high-blast-radius);
trigger 3 fires too (R4's cross-check and R9's tests are lasting gates), so an adversarial design
review follows the draft.

| Brief | Question | Decision |
|---|---|---|
| [01](01-cmdkit-unknown-flag.md) | What does a removed flag do? | Deleting the `add_argument` calls is sufficient: cmdkit returns `exit_status.bad_argument` (2) with `unrecognized arguments: <flag …>` on stderr, before `run()`. No custom handling. |
| [02](02-removal-inventory.md) | What exactly goes? | The full inventory; nothing in `Dockerfile`/`compose.yml`/`SECURITY.md`/git config. `jinja2` leaves `uv.lock`, `pyyaml` stays transitively. |
| [03](03-instructions-registry-crosscheck.md) | How is R4's cross-check not hollow? | Three extraction shapes (list entries, backticks, snake_case) against `TOOL_REGISTRY`, a self-checking allowlist (`findscratch`), a doc-word ban, both directions of set inclusion, over the constant and the served text. |
| [04](04-test-scaffolding.md) | What does the suite look like after? | Three files (`test_registry.py` unit, `test_instructions.py` unit, `test_cli.py` integration), a marker-enforcing conftest, the CLI drive wrapped in `bin/sandbox.sh` by the test itself. |

## Consolidated decisions

1. **Exit status is necessary, never sufficient.** `ValueError` shares `bad_argument`, so every R3
   check asserts the `unrecognized arguments:` message naming the flag, the absence of
   `Execution mode`, empty stdout, and no `*.db` written; one case adds `-e local` so a
   silent-accept regression exits 0 (01 §2–3, 04).
2. **The R3 test sandboxes its own drives.** It invokes `bin/sandbox.sh` around the installed
   `rcac-mcp`, so it is contained (and passes) both under the profile's bare `uv run pytest -q` and
   under the sandboxed pytest form. No skip path exists (04). This resolves the only cross-brief
   tension: 01 drives the CLI under the sandbox; 04 needs the test to run in the profile verify,
   which is not sandboxed. Wrapping inside the test satisfies both.
3. **The docs package is deleted as a directory, not as tracked files**, or its `__pycache__` keeps
   `import rcac_mcp.docs` alive as a namespace package (02). R1's test uses `find_spec(...) is None`
   plus `ModuleNotFoundError.name == 'rcac_mcp.docs'`.
4. **R4's test reads both texts** (`SERVER_INSTRUCTIONS` and `create_mcp_server('none').instructions`)
   and carries no hook for dynamic composition; the `agents-d-instructions` seed gets a one-line
   constraint note instead (03).
5. **R8 is checked at `[project.dependencies]` + `uv lock --check` + `uv tree --depth 1`**, never by
   absence from `uv.lock` (pyyaml stays transitively, 02).
6. **R9's marker clause has two witnesses**: a conftest hook that rejects unmarked tests (standing),
   and `pytest --noconftest --collect-only -m "not unit and not integration"` exiting 5 (independent of
   any conftest, 04; `--noconftest` added by the adversarial review).
7. **§4 is guarded mechanically**: an AST comparison of `_resolve_exec_mode`/`_create_executor` and
   of `run()` minus its first branch against `3cb2853` (04, prototyped).
8. **AGENTS.md drift beyond R10 is fixed in the same phase**: the marker notes ("no existing test
   carries one", "all 81") become false the moment the new tests land; the code is ground truth (02).

## After the adversarial review (2026-10-16)

The review's nine findings are folded into `PLAN.md` § 4. In short: each check is a pure function
with standing negative controls that the `verify:` gates import and feed fixed mutations; every
named test id must show `PASSED`; `user guides` joins the docs-guidance ban, which also covers
`INSTRUCTIONS.md`; the marker witness runs with `--noconftest`; greps skip binaries (`-I`); and
the last phase re-runs every check and runs the suite on a fresh clone with `UV_PROJECT=$PWD`.
