# 06 — The lock: how far to move it, and uv compatibility

## Minimal bump vs whole tree

`uv lock` after changing only the pin (`fastmcp>=4,<5`) moves `fastmcp` (2.14.4 → 4.1.0, plus
`fastmcp-slim`), `mcp` (1.26.0 → 2.3.0, plus `mcp-types`), swaps `httpx` for `httpx2`/`httpcore2`,
drops the 2.x-only dependencies (`pydocket`, `redis`, `typer`, …) and **keeps every other pin**
(`pyjwt`, `anyio`, `cryptography`, `pytest`, … stay where they were). `uv lock --upgrade`
regenerates every pin to the newest release the constraints allow.

R10 requires the audit to pass on the lock this cycle ships. **Decision (foreman's ruling after the
design review):** move only the stack (`--upgrade-package fastmcp --upgrade-package mcp`), what the
resolver forces, and each package the audit then reports (`--upgrade-package <name>`, repeated until
clean). On the prototype this converges in one round and audits clean at 94 packages. Its major moves:
`fastmcp`, `mcp`, `starlette` (forced by fastmcp 4), and outside the stack `cryptography` and
`paramiko` (why each was selected is recorded privately).
`paramiko` carries the `ssh` executor through `fabric` (unchanged at 3.2.2): an in-process
loopback smoke (`prototypes/ssh_smoke.py`) returns the same `CommandResult` on paramiko 5.0.0 and
4.0.0. The suite passes 296/296 in both eras on this lock. The whole-tree regeneration below was the
first choice and is kept for the record. Notable rides-along, all exercised by the suite on the prototype:

| Package | From | To |
|---|---|---|
| fastmcp | 2.14.4 | 4.1.0 |
| mcp | 1.26.0 | 2.3.0 |
| starlette | 0.52.1 | 1.8.0 |
| pyjwt | 2.10.1 | 2.15.1 |
| pytest | 9.0.2 | 9.1.1 |
| pytest-asyncio | 1.3.0 | 1.4.0 |
| fabric / cmdkit | 3.2.2 / 2.7.7 | 3.2.3 / 2.7.7 |

On that lock the suite passes 295/296 before the `get_tools` rewrite and 296/296 after, in both
eras; the only warning is PyJWT's key-length warning for the deliberately HS512-signed mismatch
token in `test_tokens.py` (harmless; the row expects a 401).

Lock content is time-dependent: a later `uv lock --upgrade` may pick newer releases. P1 runs it
once and commits the result; later phases do not re-run it (a re-lock is a change to the shipped
tree and re-runs the audit proof). `exclude-newer` is not used (it would freeze advisories too).

## uv versions

- Lock format: `version = 1`, `revision = 5` before and after (uv 0.13.1 writes revision 5).
- uv 0.12.17 (the CI workflow's pin) reads the new lock: `uvx uv@0.12.17 lock --check` →
  "Resolved 86 packages", exit 0; and `uvx uv@0.12.17 audit --frozen --no-config
  --preview-features audit-command` → clean, 85 packages.
- `uv audit` needs network; `uv lock --check` and `uv sync --locked` do not once the cache is warm.

## R1's checks

`pyproject.toml` reads `fastmcp>=4,<5`; the lock resolves `fastmcp` 4.x and `mcp` 2.x; `uv lock
--check` and `uv sync --locked` pass on Python 3.14 (the only supported version).
