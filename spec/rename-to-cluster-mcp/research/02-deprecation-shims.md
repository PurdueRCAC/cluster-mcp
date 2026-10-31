# 02 — Deprecation shims: env vars, `rcac-mcp`, `rcac://` aliases, sandbox (R3–R7, R16; R8)

Line numbers are from the pre-rename tree (`src/rcac_mcp/…`).

## Recommendations

1. **One env resolver, read lazily, empty means unset, never stripped.** Put it in a new core module
   (`cluster_mcp/core/deprecation.py`). That module also holds `WINDOW = 'deprecated in 0.2.0, removed no
   earlier than 0.4.0'`, `LEGACY_ENV = {'CLUSTER_MCP_SSH_HOST': 'RCAC_SSH_HOST', …USER_MAP, …INSTRUCTIONS_BUDGET}`
   and `LEGACY_COMMAND = 'rcac-mcp'`. Signature: `env_setting(name: str) -> tuple[str | None, str]`, which
   returns the value and the variable it came from.
   - The replacement wins whenever it is non-empty. Otherwise a non-empty legacy value is returned and the
     resolver logs `log.warning(f'{legacy} is {WINDOW}; set {name} instead')`.
   - When both are set, also warn once that `{legacy}` is ignored. That is harmless, and it flags stale
     client configs.
   - Warn **once per process per legacy name** through a module-level set. Rung 3 and `_create_executor`
     both read the SSH host in one run. A unit-guard fixture clears the set.
   - **Never `.strip()` in the resolver.** Today a whitespace-only `RCAC_SSH_HOST` is truthy, so rung 3
     resolves to `ssh`. Stripping it would make `-t http` fall through to `local`, which widens §4. Only the
     budget caller strips, as it does today.
2. **`rcac-mcp` = `legacy_main(argv=None) -> int`**, beside `main` in the core. It logs the warning
   (naming `cluster-mcp` and `WINDOW`), then `return main(argv)`. Register both console scripts in
   `packages/cluster-mcp/pyproject.toml`.
3. **URI aliases: option (a), with the alias entries *derived* from their targets** in `resources.py`.
   Append them before the unchanged `OPEN_RESOURCES` derivation:
   `RESOURCE_REGISTRY += [{**e, 'uri': e['uri'].replace('cluster://', 'rcac://', 1)} for e in list(RESOURCE_REGISTRY)]`.
   Write no `executor` literal by hand. `middleware.py` does not change.
4. **Alias descriptions stay identical to the target's** to keep strict R8 (deltas: instructions, URIs,
   server name). The fixture then gains only the `cluster://` keys. Marking the aliases deprecated in
   their description is better UX but adds a description delta that R8's list does not name. Do it only
   if GOAL/§ Testing names it, as `agents-d-instructions` named `resources.rcac://context.description`.
5. **Sandbox:** unset all four names. Pin it with a static test and a 2×2 drive (§5 below).

## Evidence

**Env read sites (all lazy, after import-time `logging.basicConfig` → root `StreamHandler` on stderr,
`cmdkit/logging.py:133-139`):**

| Read | Site | Semantics today |
|---|---|---|
| `RCAC_SSH_HOST` | rung 3, `__init__.py:231` | `self.ssh_host or os.environ.get(…)`: `''` = unset, no strip |
| `RCAC_SSH_HOST` | `_create_executor`, `:271`; error `:274` | same; missing → `ValueError` → exit 2 (`bad_argument`) before `mcp.run`, so stdin is never read |
| `RCAC_INSTRUCTIONS_BUDGET` | `_resolve_budget`, `:243`; error `:249` | `.get(…, '').strip()`, blank → default; the non-int `ValueError` names the var. **Name the variable actually read** (the resolver's second return value) |
| `RCAC_USER_MAP` | `AuthExecutorMiddleware.__init__`, `middleware.py:147`; error `:150` | `arg or os.environ.get(…)`: `''` = unset |
| — | `site.py:206` (`BudgetError`) | text names `RCAC_INSTRUCTIONS_BUDGET` → replacement |
| help | `APP_HELP` `__init__.py:114-116` | list the replacements; legacy names go to README (R16) |

- **Rung 3** becomes `elif self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]:`. It keeps the same
  position, the same truthiness and the same meaning, so §4's order is untouched.
- **§5** keeps one read at middleware construction and changes only the name, so it still loads once.
- **Outside the server, nothing reads these names except:** `bin/sandbox.sh:68`, the docs (README:24,60,
  SECURITY:39,102, AGENTS:118,209-214,548,1242,1655,1688,1930) and the tests: `conftest.py:57`
  `BLANKED_ENV`, `test_hygiene.py:399`, `test_exec_mode.py:171-249`, `test_site_startup.py:60-140`,
  `test_cli.py:112` and the `mutants.py:1060-1120` anchors.
- `compose.yml`, the `Dockerfile` (`ENTRYPOINT ["rcac-mcp"]`, an R15 rename) and `ci.yml` read none of them.

**cmdkit (`cli.py:62-104`, `app.py:94-139`):**
- `Interface(APP_NAME, …)` passes `prog=` explicitly, and `error()` raises the message without prog, so
  `sys.argv[0]` never reaches output.
- `APP_USAGE`/`APP_HELP` interpolate `APP_NAME` at import. Set it to `cluster-mcp` and
  `rcac-mcp --help` is byte-identical.
- Help and version print to **stdout** (`handle_help`/`handle_version`), as they do for `cluster-mcp`.
  Read R3's "nothing it prints" as the wrapper's own output. TECH should state that reading.
- The console script does `sys.exit(legacy_main())`, so the status passes through.
- `main(argv or sys.argv[1:])` already handles `None`.

**FastMCP 4.1.4 (`.venv`):**
- The middleware sees `ReadResourceRequestParams.uri: str` (`mcp_types/_types.py:885`).
- `call_next` re-reads `str(context.message.uri)` (`server.py:1606-1621`).
- The transforms are namespace, catalog, prompts_as_tools, resources_as_tools, search, tool_transform,
  version_filter and visibility. There is **no alias feature**.
- Probe (scratch, not committed): one handler registered under `cluster://context` and `rcac://context`
  with the same `name` lists both and reads both. Each content's `uri` echoes the requested URI.

**Options vs the coupled core:**
- **(a) derived registry entries.**
  - `OPEN_RESOURCES` = {`cluster://context`, `rcac://context`} by the existing derivation
    (`resources.py:102-103`).
  - The §1 exact-string membership (`middleware.py:234`) is unchanged.
  - "An alias keeps its target's handling" holds by construction: a flip of the target's flag flips the
    alias.
  - Both URIs appear in `resources/list`. The fixture goes from 2 to 4 keys.
- **(b) rewrite in middleware.**
  - It is a scheme normalisation, which §1 forbids by name ("no … scheme normalisation") and which ~35
    mutants exist to kill.
  - It must run before the executor middleware in *both* modes, so it needs a new always-on middleware
    in `server.py`/`middleware.py` (both human-gated), and it depends on order.
  - The aliases drop out of `resources/list`. Reject.
- **(c) a FastMCP `Transform.get_resource` mapping.**
  - It runs *after* the read hook, so `rcac://context` would miss `OPEN_RESOURCES` and be refused in
    delegate mode (an R7 break). Fixing that means a hand-kept second open set, which can drift.
  - It is also coupled to the 4.x API. Reject.

**Placement caveat:** `OPEN_RESOURCES` is a `Final` frozenset computed at import, and the alias
derivation has to run over the full registry before it. If the storage entry moves to the RCAC member
and is appended later, `rcac://storage` gets no alias. Keep all registry entries, aliases and
`OPEN_RESOURCES` in one module. The storage handler's lazy import (`resources.py:67`) already allows this.

## Carrying URI tests and mutants to both schemes

**Tests naming the URIs.** Hard-code `CONTEXT_URIS`/`STORAGE_URIS` in `harness.py`, and parametrize with
ids `cluster`/`rcac`. Never derive them from the registry: a dropped alias would then pass.
- `test_context.py`: `:75, :91, :128, :145, :173, :198, :239, :289`.
- `test_protocol.py`: `:162, :474`.
- `test_storage_resource.py`: every storage read (`:218, :239, :254, :297, :317, :340, :421, :562, :587`).
  Turn `URI`/`OPEN_URI` (`:60, :74`) into sets.
- `test_ssh_exec.py:2554`.
- `test_surface.py:237, :278`.
- **New**, a structural pin:
  - The registry holds exactly the four URIs.
  - Each `rcac://` entry `is`-shares its target's `handler` and equals it except `uri`.
  - `OPEN_RESOURCES == {cluster://context, rcac://context}`.
  - Each alias read returns its target's text.

**Near-open shapes.**
- `NOT_OPEN` (`test_storage_resource.py:80-102`) is a hand table of rcac shapes. Generate it per scheme
  (`CLUSTER://context`, `xcluster://context`, `cluster:context`, …). Add cross-scheme shapes such as
  `cluster://rcac://context` and `rcac+cluster://context`.
- `NEAR_OPEN` (`:150`) is already generated from the registry and widens by itself to about 11.4k reads.
  `test_near_open_read_is_refused` has `timeout=120`, sized for 5.7k: split it per served URI, or raise
  the timeout.
- `test_near_open_shapes_cover_every_served_uri` scales `2500 * len(served)` by itself.

**Mutants (`mutants.py`).**
- Anchors that must be re-texted:
  - `read-hook-resolves-storage-only` (`:248`, hard-codes `rcac://storage` → `cluster://storage`; the
    alias rows then kill it).
  - `storage-read-left-open` (`:435`) and `context-read-closed` (`:440`).
  - The scheme-specific `read-hook-rcac-scheme-only`. It needs a **twin** `read-hook-cluster-scheme-only`,
    which would let every non-open `cluster://` shape through, `cluster://storage` included.
  - Each `let_through('rcac://…')` URI-shape case: duplicate it per scheme, so the `cluster://`
    neighbourhood has its own kill.
  - The ladder cases `:1060-1120` (`os.environ.get('RCAC_SSH_HOST')` → the resolver call).
- G1/L1's **equivalent** `read-hook-open-by-equality` is no longer equivalent. Its stated reason was that
  `OPEN_RESOURCES` holds one URI, and it now holds two. Make it a real case, killed by the rcac rows of
  `test_any_client_reads_the_context_in_delegate_mode`.
- New alias cases:
  - **alias-flag-hand-set-open:** `'executor': False` in the derivation. Killed by
    `test_storage_read_refused[unmapped-rcac-*]`.
  - **alias-flag-hand-set-closed:** killed by the `OPEN_TO_REFUSED` rcac rows.
  - **open-set-before-aliases:** the derivation moved above the alias append. Same kill.
  - **open-set-target-scheme-only:** `if … and e['uri'].startswith('cluster://')`.
  - **alias-handler-differs:** a lambda, or the other target's handler. Killed by the content-equality
    and refused rows.
  - **alias-missing:** -32602 on the rcac rows.
- Env cases:
  - legacy wins over the replacement;
  - legacy ignored;
  - replacement ignored;
  - no warning;
  - resolver strips (the whitespace-host ladder row).
- `mutants.py` copies `rcac_mcp.__file__`'s parent (`:2016`, `CHILD` at `:55`). It must copy
  `cluster_mcp/core` and still import the other members.

**Gate.** Write a new `spec/rename-to-cluster-mcp/verify/` checker rather than editing the records.
`sweep.py` hard-codes `src/rcac_mcp` (`:24, :86`).
1. Re-point `MIDDLEWARE` and `cases_editing`. `DERIVATION` must still appear exactly once in
   `resources.py`, or `cases_editing` exits.
2. Run the parametrized pin set in both eras with the `COUNT` recomputed.
3. Sweep `cases_editing(MEMBERSHIP) + cases_editing(DERIVATION, 'resources.py')` + the alias-derivation
   fragment.
4. Require G1's 26 + L1's 12 + every per-scheme twin + the alias cases, all killed in both eras, with
   fragments naming a shape of the right scheme.

## Sandbox (R6)

- **Edit `bin/sandbox.sh:68`:**
  `unset CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST CLUSTER_MCP_USER_MAP RCAC_USER_MAP JWT_SECRET \`.
  The OIDC line stays.
- **Header:** lines 16-19 and 24 (the message now names `CLUSTER_MCP_SSH_HOST`) and the usage at
  lines 29-30 (`cluster-mcp`).
- POSIX `unset` of an unset name returns 0, so `set -eu` is safe.
- **No existing test pins the sandbox's unset list.** `test_hygiene.py:391-401` pins only the unit
  guard's `BLANKED_ENV`.
- Add `CLUSTER_MCP_SSH_HOST`/`CLUSTER_MCP_USER_MAP` to `BLANKED_ENV` and that test.
  `test_exec_mode.resolve`/`test_site_startup.start` must `delenv` both names. Otherwise a developer's
  exported replacement breaks the ladder rows.

**Gate** (in the style of `test_cli.drive`: `sandbox.sh sh -c '"$@" </dev/null' sh CLI`):
- For each var in {`CLUSTER_MCP_SSH_HOST`, `RCAC_SSH_HOST`}, export `var=leak.invalid` in the *calling*
  env. For each CLI in {`.venv/bin/cluster-mcp`, `.venv/bin/rcac-mcp`}, run it bare and assert:
  - rc == `exit_status.bad_argument` (2);
  - stderr has `SSH host required` and `CLUSTER_MCP_SSH_HOST`;
  - stderr has no `cannot connect` and no `leak.invalid`;
  - stdout is empty.
- The 2×2 rows plus a both-exported row.
- **Seen-red control:** set the var *inside* the sandbox (`sandbox.sh env CLUSTER_MCP_SSH_HOST=leak.invalid
  CLI`). Expect rc 1 and `cannot connect to leak.invalid`, which proves the assertions discriminate.
- Add a static row that the joined `unset` statement names all four.

**R3/R5 stdout cleanliness.**
- For argv in {`[]`, `--help`, `--version`, `--bogus`}, both CLIs under the sandbox must give equal rc and
  byte-equal stdout. `rcac-mcp`'s stderr is exactly one warning line plus `cluster-mcp`'s stderr.
- A raw stdio row: `rcac-mcp -e local -t stdio` with `RCAC_INSTRUCTIONS_BUDGET=8192`, fed one `initialize`
  line then EOF. Every stdout line parses as JSON-RPC, and stderr carries both warnings.
- Also `stdio_tools([SANDBOX, rcac-mcp, …])` in both eras.

## Risks

- The test runtime for the near-open neighbourhood roughly doubles.
- Duplicate resource `name`s in `resources/list` are untested against real clients.
- Warn-once state leaks across in-process tests unless it is reset.
- The `BudgetError` text and the `CRITICAL [rcac_mcp]` logger-name assertions (`test_cli.py:110-112`)
  change with the package path.
- The alias derivation must stay in the module that computes `OPEN_RESOURCES`. Members that register
  resources later would otherwise get no alias. If they are open, they would silently stay refused,
  which fails closed.
