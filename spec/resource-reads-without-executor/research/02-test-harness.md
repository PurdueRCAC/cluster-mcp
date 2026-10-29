# 02 — Test harness for reading `rcac://storage`

Research for `code-plan`. Paths are relative to the worktree. "Probed" means a script run against
`develop` + this branch (unchanged source), with the fix simulated by monkeypatching. The scripts are in
the session scratchpad and are not committed.

## 1. Delegate mode end to end

- **Route.** `serving(delegate_server(map_path, *extra))` + `http_client(app, mint(SECRET, sub=…), era=…)`
  (`harness.py:282,288,544,702`). A real JWT goes through the real `JWTVerifier` and
  `AuthExecutorMiddleware`. `call_http` (`:346`) connects and calls in one step. A tokenless delegate
  request is `in_memory(delegate_server(...))` (`test_no_executor.py:166`). `user_map(tmp_path, text)`
  (`:552`). The test sets `JWT_SECRET` itself (`test_identity.py:91`).
- **Faking sudo.** The `launches` fixture (`conftest.py:270`) swaps `subprocess.Popen` for
  `RecordedPopen` (`:209`). That records argv `['sudo','-n','-H','-u',<user>,'/bin/bash',…,<program>]`
  and answers `<user>|<command>` inside the launcher's sentinels. `launched_script(argv)`
  (`harness.py:569`) recovers the command (a list for an argv launch). The user is
  `argv[argv.index('-u')+1]` (`test_isolation.py:57`, `test_no_executor.py:82`).
  `delegation_violations` (`test_identity.py:41`) and the prefix check
  `argv[:4]==['sudo','-n','-H','-u']` (`test_isolation.py:82`) assert "as whom".
- **Problem for storage:** the plain recorder answers `ualice|findscratch` and `ualice|myquota`, so
  `_parse_myquota_output` raises. Probed result: `Error reading resource 'rcac://storage': No home
  directory found in myquota output`. Launches are still recorded per user, so "who ran" is visible
  but no summary comes back. Two ways to fix the answer:
  - **(a) Recommended.** Give `RecordedPopen` an answer hook, a class attribute like `answer_code`,
    which `test_executors.py:174` already monkeypatches. A probed subclass answering
    `findscratch` → `/scratch/test/<user>` and `myquota` → a table for `<user>` worked in both eras,
    with the real `DelegatingExecutor` and real sudo argv. The framing is
    `marks.start + text + marks.end + b'x0.'`, as `RecordedPopen.__init__` builds it. Putting the hook
    in conftest keeps that framing in one place.
  - **(b) Weaker.** `StubDelegate` (`test_context.py:48`, swapped in via
    `monkeypatch.setattr(middleware,'DelegatingExecutor',…)` at `:92`), using a responder keyed on
    `local_user`. It proves which user the middleware mapped, but not the sudo argv.
- **`RecordingExecutor`** (`harness.py:597`) records `('run', ['findscratch'], None, None)` and answers
  `<name>|<cmd>` unless it is given a responder. `test_tools.py:54,72` already has `QUOTA_TABLE` and
  `quota_and_scratch` for the shared mode.

## 2. Concurrency isolation (§1)

- Pattern: `delegate_server(map, Rendezvous(2))`, then two `http_client`s (alice and bob), then
  `asyncio.gather`. Then `isolation_violations(expected, ran, results)` (`test_isolation.py:28,63`).
  The shared variant uses two `shared_server`s with one `Rendezvous` (`:87`). The sequential
  alternating variant is at `:128`. The modern-era copy is `test_protocol.py:286`.
- **`Rendezvous` hooks only `on_call_tool`** (`harness.py:657`), and `Raises` does the same (`:673`),
  so neither holds a read. A read barrier must be added in `harness.py`: stack-import hygiene puts all
  middleware there. One option is `Rendezvous.on_read_resource`. That is safe today:
  `read_resource` is used only in `test_context.py` and `test_ssh_exec.py:2564`, and neither uses
  `Rendezvous`. Update the harness docstring's touchpoint list (`harness.py:14`) as well.
- Probed: with the read hook simulated, two concurrent delegate reads interleaved even without a
  barrier (`ualice findscratch`, `ubob findscratch`, …), each returning its own `/home/u<who>`. Still
  use the barrier, so the result does not depend on scheduling.
- `isolation_violations` assumes one distinct command per owner. Storage reads run the same two argvs
  for every user, so they need their own check. For each user: `findscratch` and `myquota` each ran
  once as that user, the text names `/home/<u>`, `/scratch/test/<u>` and `/depot/lab-<u>`, and
  nothing of the other user appears. Pair the check with a parametrized drift control, following
  the suite's convention (e.g. `test_isolation_check_catches_crossing`, `:185`).

## 3. `rcac://context` regression guards (R4)

| Test id (`tests/…`) | Mode / route | Eras |
|---|---|---|
| `test_context.py::test_tool_and_resource_serve_the_startup_text[{bare,shared}-{empty,files,missing,timeout,unreadable}-{legacy,modern}]` | in-memory, asserts no executor call | both (param) |
| `test_context.py::test_delegate_users_get_identical_text[legacy\|modern]` | delegate HTTP, mapped alice and bob, `StubDelegate`, `launches==[]` | both |
| `test_context.py::test_an_unmapped_user_reads_the_resource_and_is_refused_the_tool` | delegate HTTP, `sub='mallory'` | **selected era only** |
| `test_context.py::test_delegate_serves_only_what_every_account_can_read[<row>-<era>]` (12) | delegate HTTP, alice | both |
| `test_context.py::test_each_server_keeps_its_own_site[legacy\|modern]` | bare | both |
| `test_context.py::test_nothing_reads_the_site_after_construction`, `::test_a_changed_directory_changes_nothing_served` | bare | selected |
| `test_ssh_exec.py::test_a_reconnect_failure_never_changes_the_cluster_context` | shared | selected |

**Not covered today:** reading `rcac://context` in delegate mode with **no token** (in-memory) or with a
**token that has no identity claim**, and the unmapped read in a pinned modern era. A read hook that
refused those requests (or wrapped them in the 3rd case below) would break §8 unseen on the default
pass. Recommended new test:
`test_context.py::test_any_client_reads_the_context_in_delegate_mode[<who>-<era>]` with
who ∈ {no-token, no-claim, unmapped, mapped}, asserting the startup text and `launches == []`.

## 4. Refusals and what the client sees

Tool-call rows: `test_identity.py:103` (no-claims, all-empty), `:113` (unmapped), `:123`
(first-claim-unmapped), and `test_no_executor.py:158` (no token). They are checked with
`refusal_violations(outcome, calls, launches, reason)` (`test_no_executor.py:46`): `is_error`,
a case-insensitive fragment, no executor call and no launch. Fragments: `NO_EXECUTOR='No executor
configured'` (`test_no_executor.py:36`), `NO_IDENTITY='Could not extract'` and
`NOT_AUTHORIZED='not authorized'` (`test_identity.py:37-38`).

Probed, both eras:

| Case | Tool call text | Read text today (hook simulated by raising in `on_read_resource`) |
|---|---|---|
| no token | `Error calling tool 'storage_paths': No executor configured. Set executor via set_executor() first.` | `Error reading resource 'rcac://storage': No executor configured. …` (pass-through; handler errors are not masked in either era) |
| no claim | `Could not extract user identity from token claims. Token must contain sub, email, or preferred_username claim.` | legacy: same text. **modern: `Internal server error`** |
| unmapped | `User 'ghost' is not authorized. Contact administrator to request access.` | legacy: same text. **modern: `Internal server error`** |

So in the modern era, a `PermissionError` or `RuntimeError` raised from `on_read_resource` is masked.
`ToolErrorMiddleware` (`middleware.py:44`) wraps only `on_call_tool`. Probed: raising
`fastmcp.exceptions.ResourceError(str(exc))` (or `ToolError`, or `MCPError`) keeps the text in both
eras. A read-side boundary that catches `Exception` but lets `FastMCPError` through restored
`User 'ghost' is not authorized.` in the modern era. **The fix needs that boundary.** R3's modern rows
are what catch its absence. Prefixes differ (`Error calling tool …` vs `Error reading resource …`),
so assert the reason fragment, not the full text.

## 5. Era selection

`ERA = select_era(os.environ)` (`harness.py:125-143`): legacy by default, modern via
`CLUSTER_MCP_TEST_ERA=modern`, and any other value is refused. `in_memory`, `http_client` and
`call_http` take `era=` and fall back to `ERA`. They connect through `_EraClient`, which checks the
negotiated era (`:202-232`). `read_resource(client, uri)` (`:327`) is a verb on an already-connected
client, so it honours whichever era the client was built with. It returns `Outcome(True, str(exc))`
on error. Pin both eras with `@pytest.mark.parametrize('era', ['legacy','modern'])` and pass
`era=era`, as `test_context.py:34,70` does. `verify` runs the whole suite in both eras
(`AGENTS.md` § Testing, about line 924).

## 6. Served surface (R5)

`tests/fixtures/served_surface.json` pins `tools.storage_paths` (description = full docstring;
`inputSchema` `{}`; `outputSchema` `StoragePaths`/`StorageSpace`). It also pins
`resources.rcac://storage` `{name:'storage_paths', description:"User's resolved storage paths for home,
scratch, and depot spaces", mimeType:'text/plain'}`. Checked by
`test_surface.py::test_served_surface_matches_baseline` (`:224`), green in both eras now.
`@mcp_tool` serves `inspect.getdoc(func)` and FastMCP derives the schemas from the signature and
return annotation (`tools/__init__.py:59-72`). Probed: a `storage_paths() -> StoragePaths` with the
same docstring, whose body only calls a helper, serves an identical name, description, parameters and
`output_schema`.

To keep the surface unchanged:
- Keep the tool's name, docstring and `-> StoragePaths` annotation.
- Don't edit the `StoragePaths`/`StorageSpace` docstrings. The tolerated
  `output-model-description` difference carries them.
- Keep the resource handler parameterless (a parameter would turn it into a template) and returning
  `str`, which gives `text/plain`.
- Name and description come from `RESOURCE_REGISTRY`, not from the handler's docstring.

## 7. `test_tools.py` and mutations

- `TOOL_CASES['storage_paths']` (`test_tools.py:141`) feeds
  `test_tool_reaches_only_the_installed_executor[storage_paths]`. `SLURM_ARGVS['storage-paths']`
  (`:367`) feeds `test_slurm_and_site_argvs[storage-paths]`, which pins the argvs to exactly
  `['findscratch']`, then `['myquota']`. Both are R5 guards and stay unchanged.
- **How mutations work.** `tests/mutants.py:61` defines `Case(id, file, edits, targets, why)`.
  `apply` (`:1629`) requires each `old` to occur **exactly once** in the copied file. A case is killed
  only if every target fails with `why` in its message. `test_mutations.py:39` re-applies every
  anchor in the suite.
- **Anchor hazards** (`middleware.py` strings that must stay unique, or be re-planted in the same
  commit): `set_executor(self._executor)\n        return await call_next(context)\n`,
  `executor = DelegatingExecutor(identity, self._user_map)\n` (and the same line followed by
  `set_executor(executor)\n`), the `# No auth - …` block, `self._user_map = load_user_map(…)\n`,
  `super().__init__()\n        self._executor = executor\n`, `CLAIM_ORDER`,
  `if claim in claims and claims[claim]:`, `if identity not in self._user_map:\n            raise PermissionError(`,
  both `set_state(…)` lines, `except FastMCPError:\n            raise\n`,
  `except Exception as exc:\n            raise ToolError(`, and `raise ToolError(str(exc)) from exc`.
  Copying a tool hook's body into a read hook, or copying the boundary, duplicates these. One shared
  private method that both hooks call keeps them unique, and lets the existing cases cover reads
  once their targets are extended.
- **Proposed mutants** (all fit the mechanism):
  - `shared-read-sets-no-executor`: drop the set in `SharedExecutorMiddleware.on_read_resource`.
  - `auth-read-sets-no-executor`.
  - `auth-read-executor-cached` or `delegate-read-uses-shared-executor`; target the concurrent-read
    test, why `ran as`.
  - `read-no-token-fallback-identity`.
  - `read-hook-refuses-context`; target the new R4 test.
  - `read-boundary-dropped`; target the modern refusal rows, why `error lacks reason`.
  - `resource-calls-decorated-tool`: re-plant the `FunctionTool` call in `resources.py`.
  - Extend `isolation-module-global` (`context.py`) to target the concurrent-read test as well.

## 8. Hygiene rules for a new test

- Every test is `@pytest.mark.unit` or `@pytest.mark.integration` (`conftest.py:45`, `--strict-markers`
  in `pyproject.toml:56`).
- No `\b[RP][0-9]{1,2}\b` anywhere in `tests/*.py` or `src/`: comments, docstrings, messages, param
  ids (`test_hygiene.py:559-573`).
- No `fastmcp`, `mcp`, `mcp_types`, `httpx`, `httpx2` or `httpcore2` import outside `harness.py`
  (`:203-264`). So no `ResourceError` and no `Middleware` subclass in a test module.
- No `skip`, `skipif`, `xfail` or `importorskip` (`:590-612`).
- A launch outside a unit function must go through `bin/sandbox.sh` (`:87`). Assigning to
  `subprocess.Popen` with `monkeypatch.setattr` is not a call, so it is allowed.
- Harness fence: request `launches` (or mark the test `unit`) before any server call
  (`harness.py:256`), and build servers inside the coroutine passed to `drive` (`:264`).
- Convention: end with `assert guard.refused == []`. Autouse `main_context_holds_no_executor`
  (`conftest.py:435`) fails any test that leaves an executor in the main context. Start the module
  with the SPDX header and a docstring stating the contract, and add a module entry to
  `AGENTS.md` § Testing.

## Recommended placement and names

New module **`tests/test_storage_resource.py`** (unit). It imports `refusal_violations`, `report` and
`NO_EXECUTOR` from `test_no_executor`, `NO_IDENTITY` and `NOT_AUTHORIZED` from `test_identity`, and
`QUOTA_TABLE` and `quota_and_scratch` from `test_tools`.

| Test | Covers |
|---|---|
| `test_storage_read_runs_on_the_shared_executor[legacy\|modern]`: read and `storage_paths` call on one in-memory client; the exact current text; `executor.calls` = findscratch, then myquota; the same paths as the tool | R1, R6 shared |
| `test_storage_read_without_executor_middleware_fails[legacy\|modern]` (`bare_server`, `NO_EXECUTOR`) | §1 for reads |
| `test_storage_read_runs_as_the_mapped_user[legacy\|modern]` (`launches` + answer hook; sudo prefix; `/home/ualice`) | R2, R6 delegate |
| `test_concurrent_storage_reads_stay_isolated[legacy\|modern]` (delegate + read-capable `Rendezvous(2)`) | R2 |
| `test_sequential_storage_reads_each_get_their_executor` (alice, bob, alice) | per-read set |
| `test_storage_read_refused[{no-token,no-claims,all-empty,unmapped,first-claim-unmapped}-{legacy,modern}]`: same fragment as a `storage_paths` call on the same request; `launches==[]` | R3 |
| `test_storage_check_catches_crossing[…]` (drift control) | check honesty |
| `test_context.py::test_any_client_reads_the_context_in_delegate_mode[{no-token,no-claim,unmapped,mapped}-{legacy,modern}]` | R4 |

**Gate node ids:**
- Per phase: `tests/test_storage_resource.py`.
- R4: `tests/test_context.py` (44 fast tests).
- R5: `tests/test_surface.py::test_served_surface_matches_baseline`,
  `"tests/test_tools.py::test_tool_reaches_only_the_installed_executor[storage_paths]"`,
  `"tests/test_tools.py::test_slurm_and_site_argvs[storage-paths]"`.
- Every phase that touches `middleware.py`: `tests/test_mutations.py::test_mutation_anchor_applies`.
- Also `tests/test_hygiene.py::test_no_spec_ids_in_the_package_or_the_suite` and
  `tests/test_hygiene.py::test_only_the_harness_imports_the_stack`.
- Run once with `CLUSTER_MCP_TEST_ERA=modern` as well.
