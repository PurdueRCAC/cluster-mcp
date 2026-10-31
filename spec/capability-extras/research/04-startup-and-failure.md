# 04 — The startup path, and how R8's load failure is detected and reported

Scope: R2 (discovery at server start), R4 (core-only start), R8 (load failure exits naming the
distribution). Paths are relative to `packages/cluster-mcp/src/cluster_mcp/core/` unless rooted.

## 1. Startup order today, and where loading belongs

- **Import is registration today.** `__init__.py:24` imports `create_mcp_server` from `server.py`;
  `server.py:24` imports `TOOL_REGISTRY` from `tools/__init__.py`, whose bottom imports (`:78-83`)
  pull in `cluster_mcp.rcac.tools` (`:81`) and `cluster_mcp.slurm.tools` (`:82`); `server.py:27-28`
  also imports both members' `instructions`. So `import cluster_mcp.core` registers every tool.
  Confirmed under `bin/sandbox.sh`: after `import cluster_mcp.core`, `cluster_mcp.rcac.tools` is in
  `sys.modules`.
- **`--help` and `--version` import the tools.** The console script (`cluster_mcp.core:main`) imports
  the package before `cmdkit`'s `Application.main` parses argv. `HelpOption` and `VersionOption`
  return `exit_status.success` before `run()` is ever called (cmdkit `app.py`, `main`). Confirmed:
  shadowing `cluster_mcp/rcac/` with a package that raises `ImportError` (a `PYTHONPATH` entry, under
  the sandbox) makes **`cluster-mcp --help` print a traceback and exit 1**. That is the failure mode
  today: no named distribution, no stdio answer, and `--help` dies too.
- **`run()` order** (`__init__.py:177-223`): `--generate-token` returns at `:179-186`;
  `_resolve_exec_mode()` `:189`; `_create_executor()` `:204` (the SSH connect, `SSHExecutor(...)`
  at `:283`, wrapped `:282-287`); then `_resolve_budget()` `:211`, `_read_site()` `:212`, and
  `create_mcp_server(...)` `:213`, which iterates `TOOL_REGISTRY` (`server.py:109-110`) and composes
  `SERVER_INSTRUCTIONS` (`server.py:71`, used at `:95`).

**Recommendation.** Discover and load capabilities in `run()`, right after the `--generate-token`
branch and before `_resolve_exec_mode()` / `_create_executor()`:

- A load failure is then reported before any SSH connection opens and before `/etc/agents.d` is read.
- `--help` and `--version` keep working with a broken capability installed, because cmdkit handles
  them before `run()`. Keep it that way: nothing in the import chain of `cluster_mcp.core` may
  import a capability. The R3 grep enforces that.
- `--generate-token` keeps working. It needs no tool, and a token-minting admin on a box with a
  broken member should not be blocked. Loading after that branch costs nothing.
- Loading before the mode ladder means the sandbox's fail-closed default (stdio, no host) reports
  the capability failure, not "SSH host required". That gives the R8 subprocess test a clean
  surface: no host, no `-e local`.
- Loading must come before anything that composes instructions or checks the budget
  (`_resolve_budget` and `site.compose` both see the composed base). `SERVER_INSTRUCTIONS` cannot
  stay a module-level `Final` computed at import (that is research 02/03's question; it is flagged
  here because the order is fixed by it).
- Make loading **idempotent per process** (`functools.cache` on the loader, or a payload that is data
  rather than a side effect). Tests call `create_mcp_server` many times in one process, and §8 allows
  two servers in one process. Re-registering must not duplicate tools.

## 2. How startup failures are reported today; which treatment fits R8

`exit_status` (cmdkit 2.7.7): success 0, usage 1, bad_argument 2, bad_config 3,
keyboard_interrupt 4, runtime_error 5, uncaught_exception 6. The `exceptions` map (`__init__.py:170-175`) is checked in
insertion order:

| Raised | Handler | Exit | stderr |
|---|---|---|---|
| `StartupFailure` (a `RuntimeError`, `startup.py:37`) | `exit_reported` (`:48`) | 5 | already logged by `_report_startup_failure` |
| `ValueError` (missing host `:279`, budget `:255-257`) | `print_exception` (`:42`) | 2 | `log.critical(str(exc))` |
| `RuntimeError` | `print_exception` | 5 | the message |
| other `Exception` | `print_exception` | 6 | the message |

The SSH precedent (`:282-287`, AGENTS.md §4 last bullet, `startup.py` docstring) works as follows.
`connect_failure_message` builds `cannot connect to <host>: <cause>`. `_report_startup_failure`
(`:295-303`) logs it once at CRITICAL on stderr. On stdio it then calls `answer_until_eof`
(`startup.py:61-79`), which answers **every** JSON-RPC request with `{"code": -32603, "message": <msg>}`
until EOF. It skips notifications, reads nothing from a TTY, and stops on a closed stdout. Then
`raise StartupFailure(message) from exc` exits 5. `http`/`sse` log and exit at once.

**Recommendation: reuse this path for R8.** Catch the loader's error in `run()`, call
`self._report_startup_failure(message)`, and `raise StartupFailure(message) from exc`.

- **The tension.** On stdio the process lives until the client closes stdin. That is still "exit at
  startup" in the sense R8 needs. The server never builds a FastMCP instance, registers nothing,
  serves no tool, opens no connection, and exits 5 the moment the client lets go. For a TTY or
  `< /dev/null` it exits at once. A bare log-and-exit would leave a stdio client that discards
  stderr with only "connection closed", the exact problem `startup.py` was written to solve. The
  docstring's reason holds here too: a 2026-07-28 client swallows the `server/discover` error and
  retries with `initialize`. One reporting path for every startup refusal is also the smaller
  contract.
- If the plan rejects this, the fallback is a plain `RuntimeError` reaching the map, which gives exit
  5 and a stderr line but no stdio answer. Say so in TECH.md as a decision, not by accident.
- Update `startup.py`'s module docstring, which today speaks only of the SSH failure, and AGENTS.md
  §4's last bullet (or a new bullet near §7) in the same commit.

## 3. What counts as "fails to load", and the error shape

Experiment (scratch dist-infos under `$TMPDIR` on `PYTHONPATH`, the worktree venv, Python 3.14.6):
`importlib.metadata.entry_points(group=…)` sees every scratch entry point, and `ep.dist.name` is the
`Name:` field **as written** (`broken-cap`, and `badtype_cap` kept its underscore, unnormalized).
The installed members' METADATA say `cluster-mcp-slurm` / `cluster-mcp-rcac`, so the message names
them as users install them. Observed `ep.load()` outcomes:

- module body raises → that exception (`RuntimeError: boom in module body`);
- missing module → `ModuleNotFoundError: No module named '…'`;
- missing attribute → `AttributeError: module 'cluster_mcp.rcac' has no attribute 'NOPE'`;
- wrong payload (`os:sep`) → **loads fine** as a `str`, so the loader must type-check it itself.

Treat all of the following as R8 failures of the distribution that owns the entry point:

1. `ep.load()` raising **any `Exception`**, not only `ImportError`. `SyntaxError` is an `Exception`;
   let `KeyboardInterrupt`/`SystemExit` through.
2. A payload that is not the declared capability type, or a registration callable that raises when
   called.
3. A tool name (or resource URI, for R7) already registered by the core or by an earlier
   capability. FastMCP's default `on_duplicate` is `"warn"` (`fastmcp/server/server.py:358`), which
   would silently replace a tool, so the loader must check it. Name both owners.
4. Partial registration. A module whose decorators appended to `TOOL_REGISTRY` before it raised
   leaves tools behind. Snapshot and roll back, or have the payload declare its tools so nothing is
   appended until the whole payload validates. The CLI exits anyway, but in-process tests share the
   module-level registry.

**Error type.** Raise a dedicated `CapabilityLoadError(RuntimeError)` from the loader, which has no
CLI or stdio knowledge. Carry `.distribution` and the message, chained `from` the cause. `run()`
converts it to `StartupFailure` after reporting. Do **not** subclass `StartupFailure`: that class
means "already reported", and a loader called outside `run()` (tests, a future second entry point)
has reported nothing. A stray `CapabilityLoadError` still falls to the map's `RuntimeError` row,
which gives exit 5 and the message logged once.

**Message shape**, mirroring `cannot connect to <host>: <cause>`:
`cannot load capability <dist.name>: <cause>`, where `<cause>` is `<ExcType>: <text>` (or the type
alone when the text is empty), collapsed to one line. A `SyntaxError` text can span lines, and
`refusal` puts the message on the wire. Examples:
`cannot load capability cluster-mcp-rcac: ModuleNotFoundError: No module named 'x'`;
`… : entry point rcac = cluster_mcp.rcac:CAPABILITY is a str, not a Capability`;
`… : tool 'sinfo' is already registered by cluster-mcp-slurm`.
Report the **first** failure and stop, as the SSH path does. Iterate in a deterministic order:
discovery order follows `sys.path` and directory listing. Note that R6's instruction order (core,
Slurm, RCAC) is not alphabetical, so order needs an explicit rule. That belongs to research 02/03,
but it touches which failure gets reported first.

**A gap R8 cannot see.** An installed member whose dist-info has *no* entry point in the group, such
as a pre-cycle member wheel beside a new core, is silently absent. Discovery has nothing to fail on.
The extras (R1) pinning the member to the core's exact version closes most of that. Worth one line
in TECH.md.

## 4. Test patterns to mirror

- **Subprocess, under the sandbox:** `tests/test_startup.py:195-202`
  (`subprocess.run([SANDBOX, CLI, '--ssh-host', host], input=…, capture_output=True, timeout=60)`,
  checked by `raw_wire_violations` `:172-192`: exit 5, exactly one stderr line, one error per request
  on stdout). `test_startup_failure_is_answered[legacy|modern]` (`:215-221`) drives a real client
  through `harness.stdio_refusal`. `tests/test_cli.py:72-80` `drive()` and
  `tests/test_site_startup.py:149-156` pass `env=` through the sandbox. **`bin/sandbox.sh` does not
  unset `PYTHONPATH`** (confirmed). `CLI` is the venv console script (`test_cli.py:34-35`), whose
  shebang is the venv python, without `-I`.
- **Injecting a broken capability into a subprocess (verified):** write
  `<tmp>/site/broken_cap-0.0.1.dist-info/{METADATA,entry_points.txt}` with
  `Name: broken-cap` and `[<group>]\nbroken = broken_cap_mod:CAPABILITY`, plus
  `<tmp>/site/broken_cap_mod.py` that raises. Then run the sandbox with
  `env={**os.environ, 'PYTHONPATH': '<tmp>/site'}`. To break an *installed* member instead, a
  scratch `cluster_mcp_rcac-9.9.9.dist-info` earlier on the path **shadows** the real one
  (`importlib.metadata` keeps the first distribution per normalized name; `version('cluster-mcp-rcac')`
  read `9.9.9`). Expected for R8: exit 5, one stderr line starting
  `cannot load capability broken-cap: `, one error per stdio request carrying it, and no
  "Execution mode" or "SSH host required" line (loading precedes the ladder). Also assert
  `cluster-mcp --help` still exits 0 with the broken dist present.
- **In-process:** `test_startup.py:284-301` `run_app` stubs `create_mcp_server`, swaps `sys.stdin`
  and `sys.stdout` for `StringIO`, and calls `MCPServerApp.main(argv)` under the `guard` fixture. For
  R8 units, make the loader take its entry points as an injectable iterable (default
  `entry_points(group=…)`). `importlib.metadata.Distribution.at(Path(dist_info)).entry_points`
  builds real `EntryPoint`s with `.dist` set from a `tmp_path` dist-info, with no `PYTHONPATH` and no
  subprocess (verified). Use `os:sep` for the wrong-type case and a missing module for the import
  case. That covers the http path (`:341-357` analogue: exit 5, nothing read from stdin, server not
  built) and the registry rollback.

## 5. `legacy_main` and R9

`legacy_main` (`__init__.py:311-314`) only warns and calls `main`. It needs **no change**: it
inherits loading, the R8 report and the exit status. The deprecation warning simply precedes the load
error on stderr. R9 is a packaging change in the root `pyproject.toml`: `dependencies =
["cluster-mcp"]` (`:10`) must install Slurm and RCAC too, either `cluster-mcp[slurm,rcac]` or the
members listed, with `[tool.uv.sources]` (`:18-19`) gaining workspace sources for any member named
directly. `tests/test_packaging.py:126,132` pin the script mapping, which stays unchanged. One R8
test row through `LEGACY_CLI` is cheap and proves the compat command fails the same way.
