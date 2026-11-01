# Research 02 — startup integration, the bound, delegate, the override

Read-only research for the plan step. Paths are relative to `packages/cluster-mcp/src/cluster_mcp/core/`
unless they start with `tests/`, `bin/` or a file at the repo root.

## Findings

**1. Where the probe fits; overlap with the site read.**
- The slot is inside `run()`'s `try`, after `_resolve_budget()` (`__init__.py:215`, so a bad budget
  still refuses before any remote command) and around `_read_site` (`:216`), before
  `create_mcp_server` (`:217`). The executor exists by then (`:206-209`), and a failed connect has
  already raised `StartupFailure` (`:300-305`).
- `SSHExecutor` already takes concurrent `run` calls from several threads. FastMCP runs sync tools on
  worker threads (AGENTS.md §1). The executor's lock guards only bookkeeping, "never across a connect
  or a close" (`executor/ssh.py:691-694`). Each `run` opens its own session channel and closes it in
  `finally` (`ssh.py:979-994`). A live transport is captured per call (`ssh.py:866-868`), and
  concurrent reconnects join one attempt (`ssh.py:874-899`). Pinned by
  `tests/test_ssh_exec.py:1488` and `:1518`.
- `LocalShellExecutor` keeps no state: each `run` is its own `Popen` with `start_new_session=True`
  (`executor/shell.py:33-78`, `executor/launch.py:588-589`). Overlap is safe there too.
- **What overlap buys.** Run sequentially, the worst case is connect + 10 s + B. Overlapped under one
  deadline, it is connect + max(10 s, B). With B = 10 s, overlap adds nothing to today's worst case.
  Run sequentially, it doubles the wait a stdio client sits through.
- **What overlap costs.** One deadline taken before both start, and one join. Probes should also run
  in parallel with each other (one daemon thread each). Otherwise one hung probe starves the rest,
  which breaks R5's "whatever the number of installed capabilities". In `ssh` mode that is N+1
  channels at once on one connection. OpenSSH's `MaxSessions` (default 10) is per connection, so it
  is fine for today's two members but worth a line for the downstream seeds. A design where probes
  are data (lookups) the core batches into one remote script would use a single channel. That
  choice belongs to topic 01.
- **Bound.** Use 10 s, equal to `READ_TIMEOUT` (`site.py:68`). Overlapped, a shorter figure saves no
  worst-case time, because the site read still takes up to 10 s, and it makes fail-open (Q2) more
  common on a loaded login node. Hold it as a module constant (for example `PROBE_TIMEOUT = 10.0`)
  that is read at call time, as `READ_TIMEOUT` is (`site.py:64-65`), so tests can shrink it the way
  `tests/test_site_startup.py:107` shrinks `READ_TIMEOUT`. It is not a setting.

**2. Abandoned work at the deadline.**
- An abandoned probe thread cannot hold the lock (bookkeeping only). It cannot share a channel (one
  per call). If it found the link lost, the first tool call joins its reconnect attempt
  (`ssh.py:883-884`), which is the designed path.
- **Pass `timeout=` to `run` (the time left before the deadline).** Over ssh, `_collect` then sends
  TERM to the remote command at the deadline (`ssh.py:249-255`). Locally, `run_process` signals the
  process group (`launch.py:604`). A hung probe then frees its sshd session instead of holding one
  for the life of the process. `timeout` still does not bound `open_session` (`OPEN_TIMEOUT` 30 s,
  `ssh.py:92`) or a reconnect (45 s window, `ssh.py:945-946`). So the outer thread deadline stays,
  as `read_bounded`'s does (`site.py:586`).
- `close()` takes no lock and nulls `_conn` (`ssh.py:724-728`). A thread still in `_collect` sees its
  channel close without EOF and returns `CONNECTION_LOST` (`ssh.py:243-246`). A thread inside
  `_ensure_connected` can start a fresh reconnect after the close. That is pre-existing and also true
  of an in-flight tool call. At process exit the daemon threads die.
- **Exceptions in the probe thread.** `read_bounded` catches only `Exception` (`site.py:594`). A
  `SystemExit` in a thread is swallowed by `threading` and leaves the box empty, so the start waits
  out the full bound. The probe worker must catch `BaseException`, as the load does
  (`capabilities.py:14-15`), and post "could not run: SystemExit" at once.
- A late result is discarded. The decision is fixed at the deadline.

**3. Which capabilities are served.**
- The served set comes from `_tools_of(loaded)` and `_resources_of(loaded)` alone
  (`server.py:84-103`, `:147`). `TOOL_REGISTRY` is read only by `load()`
  (`capabilities.py:258-330`) and to freeze `CORE_TOOLS` (`tools/__init__.py:85-89`).
  `RESOURCE_REGISTRY` holds only the core's entries; a capability's resources live on its
  `Capability` (`capabilities.py:69`). So a withheld capability's tools cannot leak.
- Nothing in `middleware.py`, `site.py` or `tools/context.py` reads anything per capability.
  `OPEN_RESOURCES` derives from the core's registry (`resources.py:78-80`), and `cluster_context`
  reads only `site_of(server)` (`site.py:688-690`).
- **Docstring.** `create_mcp_server` says "No flag or environment variable reaches it: installation
  is the switch" (`server.py:122-123`). That becomes something like: "`run()` passes the installed
  capabilities its probes kept (§4); None serves every installed one". AGENTS.md §7 gains the probe
  field and its outcomes. §9 gains "the base is composed from the capabilities served, not
  installed". §4 gains the step.
- **Budget.** `compose` raises when `budget < minimum_budget(base, site)` (`site.py:656-658`), and
  the minimum grows with the base (`site.py:641`). Withholding only lowers it: a budget that serves
  the full set serves every subset. But a budget between the two minimums would start or refuse
  depending on how the cluster answers.
  - `tests/test_site_startup.py:154-158` drives `-e local` and expects the full base's minimum. A
    local probe on the development host or the CI runner, which has no Slurm, would withhold and
    change that minimum.
  - **Recommend:** check the budget against the base of every installed capability, then compose
    the served base. The refusal then never depends on a probe.

**4. Delegate mode.** Put the line in the delegate branch beside `__init__.py:204`, or in the one probe
step keyed on mode. No executor exists there (`:197`, `:200-204`). Instructions are composed once
(`server.py:131`), and the middleware hooks only `on_call_tool` and `on_read_resource`
(`middleware.py:214`, `:224`), with no list hook. Every user therefore gets one tool list. R7 needs
no new mechanism, only a test that delegate starts run no probe callable.

**5. The override.**
- `env_setting` cannot read a variable without a legacy twin: `LEGACY_ENV[name]` raises `KeyError`
  (`deprecation.py:67`). Change it to `LEGACY_ENV.get(name)`, skip the legacy branch when that is
  None, and add a twinless row to `tests/test_env.py`. Do not invent an `RCAC_` twin, since no
  window covers it.
- **Flag.** Declare it like `--generate-token`: a class attribute plus
  `interface.add_argument(..., action='store_true')` (`__init__.py:160-161`). Add it to `APP_USAGE`
  (`:65-71`), to Options, and to "Environment Variables" (`:95-119`).
- **Values.** Existing practice is that empty means unset (`deprecation.py:64`) and that a bad value
  is a `ValueError` naming the variable, exiting `bad_argument` (`__init__.py:266-273`, `:173`).
  "Any non-empty value is on" would make `…=0` mean on. **Recommend:** strip and lowercase, then
  `1|true|yes|on` → on, `0|false|no|off` → off, and anything else →
  `ValueError('<VAR> must be …, not …')`. The flag wins over the variable.
- **`compose.yml`.** It pins `-t http -a jwt` (`compose.yml:21`). That resolves to `delegate`, which
  never probes, and a new flag renames or re-defaults nothing, so the file need not change.
- **`bin/sandbox.sh`.**
  - Unset the variable (`bin/sandbox.sh:75`) and add it to `SANDBOX_UNSET`
    (`tests/test_hygiene.py:408`), plus `BLANKED_ENV` (`tests/conftest.py:75`). Otherwise an
    exported value makes every probe test pass vacuously.
  - **Consequence.** Sandboxed CLI drives that expect the full tool list in `-e local` mode
    (`tests/test_transports.py:114`, `:143`, `:169-170`, via `EXPECTED_TOOLS`) must then pass the
    flag. The variable cannot be passed in, because the sandbox unsets it. Without the flag those
    drives see the members withheld on any host without Slurm.
- **Name pair:** `--skip-probes` / `CLUSTER_MCP_SKIP_PROBES`.

**6. R9 orderings.**
- `--help` and `--version` are handled by cmdkit's `Interface` before `run()`
  (`__init__.py:132-133`).
- `--generate-token` returns at `:180-187`.
- The capability load (`:190`) and the connect (`:208` → `:300-305`) both precede the slot.
- Tests that pin this order: `tests/test_startup.py:558` (load before ladder), `:522` and `:549`
  (broken capability; help with one), `:343` and `:360` (connect failure on stdio and HTTP; `run_app`
  fails if a server is built, `:307`), `tests/test_exec_mode.py:214` (ladder), and
  `tests/test_tokens.py:134`, `:141`.
- Add a "no probe ran" assertion to each.
- **Hazard.** In-process unit drives of `local` mode (`tests/test_exec_mode.py:75-82`,
  `tests/test_site_startup.py:79-105`) would now `Popen` through `LocalShellExecutor`. The unit guard
  refuses that and fails the test at teardown (`tests/conftest.py:160-163`, `:220-221`). In `ssh`
  mode, `FakeTransport.open_session` raises (`tests/test_executors.py:550-551`), which gives a
  fail-open line in the logs these tests read. Give the probe step one seam (a method such as
  `_probe`, like `_read_site`) that those harnesses stub.

**7. The stderr lines.**
- The module `log` is `Logger.default(name='cluster_mcp.core')` (`__init__.py:40`), in cmdkit's
  default format, `LEVEL [name] message`.
- Unit tests filter `caplog.records` on `r.name == 'cluster_mcp.core'` (`tests/test_exec_mode.py:198`,
  `tests/test_startup.py:569`). Integration tests read `result.stderr`.
- Log from that logger, not from a new module logger, or those filters miss the lines.
- Suggested lines:
  - `INFO`: `capability <dist> withheld: <what is missing>`
  - `WARNING`: `capability <dist> served unprobed: its probe <did not finish within 10 s | could not
    run: <cause> | lost the connection>`
  - `INFO`: `capability probes skipped in delegate mode: every installed capability is served`
  - `INFO`: `capability probes skipped (<--skip-probes | CLUSTER_MCP_SKIP_PROBES>): every installed
    capability is served`
- When several reasons apply, log exactly one skip line, the first that applies: delegate first,
  then the override.

## Recommendation

One probe step, `MCPServerApp._probe(exec_mode, executor)`, in `__init__.py`:

1. Resolve the budget (as now).
2. If the mode is delegate, or the override is set, log the one skip line and serve everything.
   Otherwise take `deadline = now + PROBE_TIMEOUT` and start one daemon thread per declared probe.
   Each thread calls the probe with the executor and `timeout = deadline - now`, catches
   `BaseException`, and posts present, absent(reason) or unknown(reason).
3. Run the site read as today. It overlaps the probes.
4. Join each probe box until the shared deadline. Log one line per withheld or unprobed capability.
5. Check the budget against the full installed base, then call
   `create_mcp_server(..., capabilities=served)`.

The worst case stays connect + 10 s. No probe runs when none is declared. The step has one stub
point for the existing in-process harnesses.
