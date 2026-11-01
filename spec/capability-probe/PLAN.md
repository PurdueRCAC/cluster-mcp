# PLAN — Probe the cluster before advertising an installed capability

> **Status:** Draft for review · **Last updated:** 2026-11-01
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/) ([`00-digest.md`](research/00-digest.md) first). Every design element
> traces to a GOAL R-ID.

## 1. Summary

A capability declares the commands it needs as data (`Capability.commands`), never as code. At
startup in `ssh` and `local` modes the core looks every declared name up at once, with one
registered fixed script through the shared executor (`type -P`, which finds what a tool's `exec`
runs). The lookup runs on a daemon thread under one 10 s deadline, after the site read and the budget
check, so every startup refusal still comes first (R9). A capability with a missing command is served
as if not installed. Every other ending
serves it with a stderr line (Q2), and so does a lookup that has not answered by the deadline.
`delegate` mode and the operator override (`--skip-probes`, `CLUSTER_MCP_SKIP_PROBES`) run no probe,
with one stderr line saying so. Since no capability code runs at probe time, a probe cannot raise, exit,
hang in Python or return a malformed value. A malformed declaration is refused at load, through the
§7 refusal that already exists. Big appetite, three phases: the contract and the runner, startup,
then the whole cycle's checks.

## 2. Design

Paths: `C` = `packages/cluster-mcp/src/cluster_mcp/core/`, `S` = `packages/cluster-mcp-slurm/src/cluster_mcp/slurm/`,
`RC` = `packages/cluster-mcp-rcac/src/cluster_mcp/rcac/`.

### 2.1 The declaration: `C/capabilities.py`

- `Capability` gains a last field, `commands: tuple[str, ...] = ()`, after `resources`. Construction
  with four or five positional arguments, or by keyword, is unchanged, and `()` declares no probe (Q1).
  `Loaded` is unchanged.
- `COMMAND: Final = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.+-]{0,254}')`, a plain file name.
- `_checked()` requires `commands` to be exactly a `tuple` (`type(...) is tuple`), so a bare string
  (iterable, and so five one-letter names) is refused, and so is a subclass. Each element must then be
  exactly a `str`, match `COMMAND` in full, and appear once. Exact types, not `isinstance`: the probe
  iterates and hashes the names after the load, outside its guard, so a subclass's `__iter__` or
  `__hash__` would run capability code there (review finding 3). Each failure is an `_Invalid` worded `its commands is a …`, `one of its commands is a …`,
  `its command '…' is not a command name` or `its command '…' is declared twice`. The existing path
  turns it into `CapabilityLoadError` naming the distribution, before the mode ladder (§4, §7). Nothing
  else in the load changes.

### 2.2 The runner: `C/probes.py` (new)

```python
PROBE_TIMEOUT: Final = 10.0          # one figure for every probe together; read at call time; no setting
LOOKUP: Final = fixed(               # registered in scripts.FIXED_SCRIPTS
    'unset -f type\n'
    'for n do if type -P -- "$n" >/dev/null 2>&1; then printf "1\\n"; else printf "0\\n"; fi; done\n'
    'printf "end %s\\n" "$#"\n')

@dataclass(frozen=True)
class Verdict:                       # loaded, served: bool, reason: str | None
class Pending:                       # verdicts() -> tuple[Verdict, ...], decided once, memoized
def start(executor, capabilities, timeout=None) -> Pending
def unprobed(capabilities) -> Pending  # every one served, no reason; nothing runs
```

- `start()` takes the declared names of every capability, in load order, deduplicated. With none it
  starts nothing and runs no command (R5). Otherwise it takes `deadline = now + bound` and starts one
  daemon thread. The thread calls `executor.run(script_argv(LOOKUP, 'cluster-mcp-probe', *names),
  timeout=bound)`, so the command is stopped at the bound where the executor can stop it. The thread
  catches `BaseException` and posts a reason for it.
- `_ask()` maps the result:
  - `TIMEOUT_EXIT_CODE` → `did not answer within 10 s`;
  - `CONNECTION_LOST_EXIT_CODE` → `lost the connection`;
  - `NOT_STARTED_EXIT_CODE` → `could not run: the command did not start`;
  - any other nonzero exit → `could not run: it exited N`;
  - exit 0 → `_parse()`, which needs exactly N lines of `0`/`1` then `end N`, each ended by `\n`
    alone (split on `\n`, never `splitlines`). Anything else → `gave an answer that does not parse`.
  - A result that is not a `CommandResult` raises in the thread → `could not run: <Type>: <text>`.
- `Pending.verdicts()` waits on the queue until the deadline, at most. An empty queue means `did not
  answer within 10 s`. It then decides each capability:
  - no commands → served, no reason;
  - an answer with a `0` for any of its names → withheld, the reason `missing a, b` naming exactly
    those;
  - an answer with every name `1` → served, no reason;
  - any reason instead of an answer → served with that reason (Q2).

  The decision is memoized. A late answer, after the deadline, changes nothing, and the abandoned
  thread is a daemon, so it never holds the process open.
- Why data and why `type -P`: [01](research/01-probe-contract.md) §1–2. The script undoes a `type`
  function first, as `READ_SITE` does for its words, and `FIXED_RESET` already undoes `printf`. Names
  reach it only as positional parameters. It echoes no name, so no name can forge a line.

### 2.3 The members

- `S/capability.py`: `commands=('sbatch', 'squeue', 'scancel', 'sacct', 'sinfo', 'scontrol')`, the
  Slurm client commands its tools run (`whoami`, coreutils, is not one).
- `RC/capability.py`: `commands=('findscratch', 'myquota')`, the two its storage resource needs, which
  also mark the site. Why not every command: [01](research/01-probe-contract.md) §5. A cluster lacking
  one RCAC site script, `average_wait` say, would otherwise lose all ten tools and the resource. A tool
  whose own command is missing at call time keeps its call-time error (GOAL non-goal).

### 2.4 Startup: `C/__init__.py` (`MCPServerApp`)

```text
run():  --generate-token branch (unchanged)
        _load_capabilities()                 # unchanged: refuses before the ladder (R9)
        _resolve_exec_mode()                 # unchanged
        executor / middleware per mode       # unchanged: ssh connects or refuses here (R9)
        try:
          budget  = _resolve_budget()        # unchanged
          skipped = _resolve_skip_probes()   # new
          site    = _read_site(mode, executor)                    # unchanged
          compose(base_instructions(installed()), site, budget)   # new: refuses a budget before any probe,
                                                                  # whatever the answer would be
          served  = _served(_probe(mode, executor, skipped))      # new: the lookup, or one skip line; waits
                                                                  # until the deadline at most; one line per
                                                                  # withheld or unanswered capability
          create_mcp_server(..., capabilities=served)             # was: none (every installed one)
          mcp.run(...)
```

- `--skip-probes` is a `store_true` flag on `MCPServerApp`, added to `APP_USAGE`, Options and
  Environment Variables in `APP_HELP` (§ Conventions).
- `_resolve_skip_probes()` returns `'--skip-probes'` when the flag is given. Otherwise it reads
  `env_setting('CLUSTER_MCP_SKIP_PROBES')` and returns the variable's name when the value is non-empty,
  and None when it is not. The value is never parsed: § Configuration counts an empty value as unset
  and strips nothing, so R8's "is set" is "non-empty", `0` included (the convention `NO_COLOR` uses;
  [digest](research/00-digest.md) decision 10).
- `_probe()`:
  - `delegate` → one line, `Capability probes skipped in delegate mode: every installed capability
    is served`, and `unprobed(installed())`. This holds whether or not the override is also set, so
    a start logs exactly one skip line.
  - The override → one line, `Capability probes skipped (<--skip-probes | CLUSTER_MCP_SKIP_PROBES>):
    every installed capability is served`, and `unprobed(...)`.
  - Otherwise `probes.start(executor, installed())`.
- `_served()` logs, on the `cluster_mcp.core` logger:
  - for each withheld capability, at INFO, `Capability <distribution> withheld: the cluster is missing
    <a>, <b>`;
  - for each one served without an answer, at WARNING, `Capability <distribution> served without a
    probe answer: the probe <reason>`.

  It returns the served capabilities in load order.
- The budget check composes the base of every installed capability with the site. A budget too small
  for it is refused as today (`BudgetError`, exit `bad_argument`) before any probe starts, so the
  refusal is an existing startup refusal that precedes the probe (R9). It never depends on what the
  probe would answer ([02](research/02-startup-integration.md) §3). The server is then built from the
  served set.
- **Sequential, not beside the site read.** Research proposed starting the lookup before the site read
  and joining it after, to keep the worst case at connect plus 10 s
  ([02](research/02-startup-integration.md) §1). The adversarial review showed that this runs a probe,
  waits out its bound and logs for it before a budget refusal that needs the site's text (§5). R9 puts
  every existing refusal first. The probe still adds at most 10 s (R5); the worst case after the
  connect is the site read's 10 s plus the probe's 10 s, the cost Q5's trade-off names.
- `_read_site`, `_create_executor`, `_resolve_exec_mode` and `_load_capabilities` are not edited.
  Neither is `middleware.py`: in `delegate` mode no executor exists at startup and every user is served
  the same list (R7).

### 2.5 `C/deprecation.py`

`LEGACY_ENV` gains `'CLUSTER_MCP_SKIP_PROBES': None` (typed `dict[str, str | None]`). Its comment says
None is a variable that came after the rename and has no legacy name. `env_setting` returns
`(value or None, name)` for such a variable, with no legacy branch and no warning, so it stays the one
reader of every variable (§ Configuration, Q4). `LEGACY_ENV[name]` still raises for an unknown name.

### 2.6 `C/server.py`

`create_mcp_server`'s docstring for `capabilities` changes. "No flag or environment variable reaches
it: installation is the switch" becomes "`run()` passes the installed capabilities the probes kept
(§4); None serves every installed one". The code does not change.

### 2.7 Tests (new files and edits)

- `tests/conftest.py`: a session `autouse` fixture `skip_probes`, beside `path_shim`, sets
  `CLUSTER_MCP_SKIP_PROBES=1` for every test and child, whatever the calling shell exported, and
  restores the variable afterwards. A test of the probe removes it (`monkeypatch.delenv`, or a child
  environment without it). `tests/test_hygiene.py::test_the_suite_skips_probes_by_default` pins the
  fixture.
- `tests/harness.py`: a `ProbeExecutor`. Its responder returns a `CommandResult`, returns anything else,
  raises, or blocks on an `Event`. The tests set the event in `finally`.
- New `tests/test_probes.py` (P1): the runner's outcomes and the lookup.
  - The outcome rows run beside each member set (`MEMBER_SETS`, as `test_capabilities.py` builds them)
    with the bound patched small.
  - `test_the_lookup_finds_only_what_exec_runs` (`integration`) runs `LOOKUP` through
    `LocalShellExecutor` with a stub directory on PATH. Under `need_shell`-style rules it fails on CI
    rather than skip, and CI's bash 5 re-checks what research saw on bash 3.2.
  - `test_the_lookup_over_ssh` (`integration`) uses `LoopbackSSH` with `home/bin` stand-ins
    (present, absent) and `DroppingSSH` (lost).
- `tests/test_capabilities.py` (P1): the malformed declarations, refused at load; a planted capability
  with commands needs no core edit; the members' declarations.
- New `tests/test_probe_startup.py` (P2):
  - **In process.** `MCPServerApp.main` with `_create_executor` returning a `ProbeExecutor`,
    `create_mcp_server` recording its `capabilities`, and the site read stubbed. It covers order,
    modes, override, refusals, budget, the bound and the R3 cross-check: the real `create_mcp_server`
    over each served set, the instructions against the tools.
  - **CLI drives** (`integration`) under `bin/sandbox.sh` with the variable removed and a
    `.bash_profile` that stubs PATH: a withheld member (each, both); a fast no-answer from a profile
    that ends the login before the command; stdin closed; HTTP.
- Edited, not weakened: `tests/test_env.py`. Its `test_every_variable_has_its_legacy_name` iterates
  `LEGACY_ENV` and skips `None` entries, which a new `test_a_variable_without_a_legacy_name` covers.
  `tests/mutants.py` gains the alternatives' cases (§6).

### 2.8 Documents (R10), in the phase that makes each true

- **P1.**
  - §7 gives the record as `Capability(name, order, tools, instructions, resources, commands)`, says
    how the commands are looked up (`type -P`), and that a malformed declaration is refused at load.
  - The high-blast-radius list and the footguns gain `core/probes.py`: it decides which installed
    capabilities are served, as `capabilities.py` does.
- **P2.**
  - §4 gets the probe step: where it sits (after the site read and the budget check, before the server
    is built; every refusal first), `PROBE_TIMEOUT` (10 s), fail open,
    `delegate` none, `--skip-probes`.
  - §9: the base is composed from the capabilities served, which a probe may have withheld.
  - § Configuration: the `CLUSTER_MCP_SKIP_PROBES` row, any non-empty value.
  - § Testing: the suite's default and how a probe test opts in.
  - README: an installed capability is served only where the cluster has what it needs, the
    `withheld` line, and `--skip-probes`.
  - `APP_HELP`.
- **P3.** The downstream seeds' notes (§5) and the deferral ledger.

The cycle lands as one squash commit (profile `landing: squash-local`), which is "the same commit"
R10 names.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | §2.2 a `0` withholds; §2.4 `_served` drops it from `capabilities=` and logs one INFO line naming the distribution and each missing command; `create_mcp_server` serves only what it is given (§9). `drives.py` (stdio, closed stdin, HTTP), `startup_order.py`, `test_a_withheld_capability_is_not_served_over_stdio` |
| R2   | §2.1 `commands` on the entry point's `Capability`, validated at load with no core edit; §2.3 both members declare; `test_probes.py` drives each against `ProbeExecutor` present and absent; `()` is no probe. `declared.py`, `lookups.py` |
| R3   | `capabilities=None` keeps meaning every installed one, so `test_served_surface_matches_baseline` passes unedited (`baseline.sh`: fixture byte-identical to `c520432`'s). That test builds in process and never probes; "every probe present → unchanged" through `run()` is `drives.py`'s every-present drive, which compares every tool and resource whole and in order with an unprobed server's. `test_the_served_instructions_name_exactly_the_served_tools` cross-checks with each member withheld and both |
| R4   | §2.4 `_probe` after `_create_executor`, before `create_mcp_server`, through the executor the middleware shares; one `start()` per process, nothing re-probes. `startup_order.py` (one call, order), `drives.py` (one login per start) |
| R5   | §2.2 one deadline, `PROBE_TIMEOUT = 10.0`, ≤ `READ_TIMEOUT`, one lookup for every capability together, so the probes add at most 10 s whatever their number; no declared name → no command. `startup_order.py` (a hung probe held to its bound; none declared), `drives.py` (a real hang: first answer within the bound plus 6 s) |
| R6   | §2.2 every ending but a well-formed answer serves with a reason; the worker catches `BaseException`; the deadline decides an unanswered lookup; §2.4 one WARNING line each. `lookups.py` (24 endings × three capability sets), `drives.py` (hang on stdio and with stdin closed) |
| R7   | §2.4 `delegate` → one line, `unprobed`; no executor exists and the middleware hooks only calls and reads. `startup_order.py` (no `start()`, one line, override also set) |
| R8   | §2.4 `--skip-probes` and `CLUSTER_MCP_SKIP_PROBES` (non-empty) through `env_setting` (§2.5): no probe, every installed capability served. `drives.py`, `startup_order.py` |
| R9   | §2.4 the load, the connect and every budget refusal precede `_probe`, the first two unedited; `--help`/`--version` never reach `run()`, `--generate-token` returns first. `drives.py` (no login for each, behind a profile that would hang a probe), `startup_order.py` (`start()` never called) |
| R10  | §2.8; `docs_gate.py p1`, `p2` (the bound and the withheld line read from the code, not restated) |

## 3. Invariant gate (AGENTS.md constitution check)

**Gate #1 (before research).** The intent touches:

- §4, the startup path in `__init__.py` [human gate];
- §7, the capability record;
- §9, what the base is composed from [human gate];
- § Configuration, a new variable read through `env_setting` in `deprecation.py` (high-blast-radius);
- § Testing and § Conventions: same-commit, help text, markers, sandbox and comments.

It touches the high-blast-radius paths `core/__init__.py`, `core/capabilities.py`,
`core/deprecation.py`, the two members' `capability.py` and `core/server.py` (a docstring), so research
trigger 2 fired. §1 and §5 are touched only by reading `delegate` mode, which the design must not change
(GOAL non-goal), and §8 is touched only because the probe follows the site read. Nothing in the GOAL is
at odds with an invariant.

**Gate #2 (after design):**

- §1 (executor isolation): untouched. The probe uses the shared executor of `ssh` and `local` modes from
  a startup thread. It never sets `executor_var` and holds no request's executor, and `delegate` is not
  probed.
- §2 (Executor protocol): the probe is an argv `run` of a registered fixed script (`scripts.fixed`), as
  `READ_SITE` is, with a timeout in range. No new method.
- §3 (`CommandResult` codes): each sentinel code has its defined reading (§2.2). No code is added.
- §4 [human gate]: the ladder, the connect refusal and the load refusal are unchanged and precede the
  probe. `run()` gains the probe step inside its `try`, after the budget's resolution, the site read and
  the budget check, so every budget refusal still comes before any probe command.
- §5 (delegate): untouched. No probe runs, and no executor is built at startup.
- §7: the record gains `commands`. "Whatever a capability declares fails at the load or not at all"
  stays true: the declaration is checked at load, and probing runs no capability code.
- §8: the site read is not edited. It runs as before; the lookup follows it.
- §9 [human gate]: the base and the listings are composed from the served capabilities, in the same
  orders. With every probe present the surface is byte-identical (R3).
- High-blast-radius list: it widens with `core/probes.py` (it decides which capabilities are served).
  Nothing is removed.
- § Configuration: one variable, read through `env_setting`, documented in the table.
- § Conventions:
  - The flag is in `APP_USAGE` and `APP_HELP` in the same commit.
  - `compose.yml` needs no change: it pins `-t http -a jwt`, which resolves to `delegate`, and it
    renames and re-defaults nothing.
  - `bin/sandbox.sh` is not edited (§2.7 says why).
  - Comments carry no spec ids, and new tests carry markers.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| `create_mcp_server(capabilities=…)` was documented as a test seam that no flag or variable reaches ("installation is the switch", `server.py:122-123`, capability-extras PLAN §2.3); `run()` now passes the probed set, and the override reaches it indirectly | R1 requires a withheld capability's tools, resources and text to be absent from what is served, and the served set is composed only in `create_mcp_server` | Filtering inside `create_mcp_server` would make it probe, so every in-process server built by a test or library caller would run a remote command. Read against R1: it serves exactly the probed set. Against R3: `None` still serves every installed one, so the baseline test is unedited. Against R4: the probe stays in `run()`, after the executor exists |
| The suite sets `CLUSTER_MCP_SKIP_PROBES=1` for every test by default (session fixture), and probe tests opt in | About 60 in-process starts would otherwise `Popen` a probe that the unit guard forbids, and every `local` CLI drive would see both members withheld on a test host | Stubs on PATH for every drive cannot help the in-process starts, and cost a login bash per drive. Editing `bin/sandbox.sh` (a high-blast-radius file) to unset the variable would push the flag into every drive that needs the full list. Read against R2 and R3: the probe tests and the gates remove the variable and drive the probe for real, present and absent. A mutant that ignores the override turns every existing `local` drive red |
| The budget is checked against every installed capability's base, not only the served one | A budget between the two minimums would otherwise start on a cluster lacking a member and refuse on one that has it: the refusal would depend on the answer | Letting `compose` decide on the served base is one line fewer. Read against R1: a withheld capability still contributes no tool, resource or text to what is served, and the check only decides whether to start, as it does today for every installed capability. Against R3: with every probe present the minimum is today's |
| `env_setting` takes a variable with no legacy twin (`LEGACY_ENV` value None) | § Configuration makes it the one reader of every variable, and Q4 says the override is "read through `env_setting` like the others" | Reading `os.environ` directly would break the single-reader rule. Inventing an `RCAC_SKIP_PROBES` twin would promise a deprecation window for a name that never existed. Read against R8: the variable is read as the others are, empty counting as unset |
| The override is "set" when its value is non-empty, any value (`0` included) | R8's "WHERE the override … is set", with § Configuration's "an empty value counts as unset" and its resolver that strips nothing | A strict boolean (`1/true/yes/on`, refuse anything else) would make `=0` a set variable that still probes, which reads against R8's wording, and adds a refusal path R8 does not name. The cost, `=0` skipping probes, is stated in § Configuration and `--help` |

## 4. Rabbit holes (resolved)

- **What a probe declares, and how capability code is kept off the probe path.** Data, not a callable
  or a script. One lookup for every capability; every Python-side failure removed; a malformed
  declaration refused at load ([01](research/01-probe-contract.md) §1, §4).
- **What "present" means.** `type -P`, so it matches `exec`. A function or a builtin is not present,
  and an alias is invisible. `type` is undone first ([01](research/01-probe-contract.md) §2).
- **The bound.** Executor timeouts do not cover an SSH reconnect (45 s) or opening a session (30 s), so
  a daemon-thread deadline holds it, with the executor timeout passed as well
  ([01](research/01-probe-contract.md) §3, [02](research/02-startup-integration.md) §2).
- **Overlap with the site read.** Research found it safe on both executors
  ([02](research/02-startup-integration.md) §1). The review then showed it would probe ahead of a
  budget refusal, so the design runs the lookup after the site read and the budget check (§2.4).
- **`SystemExit` on a worker thread** silently ends it, so `read_bounded`'s pattern would wait out the
  bound. The worker catches `BaseException` ([02](research/02-startup-integration.md) §2,
  [03](research/03-testing-and-budget.md) §3).
- **Which tests would go red, and how the suite stays green** ([03](research/03-testing-and-budget.md)
  §1–2; deviation table, row 2).
- **The budget's dependence on the answer** ([02](research/02-startup-integration.md) §3; deviation
  row 3).
- **CI budget.** At c520432 the suite takes 359.6 s (handshake) and 359.5 s (modern) locally, 3520
  passed. The previous cycle's CLI drives cost about 1.6 s each on CI. This cycle adds about 10 CLI
  drives per era and never drives the real 10 s bound in the suite ([03](research/03-testing-and-budget.md)
  §4; §6 below).
- **Mutation coverage under the command cap.** Each phase sweeps its own decisions (93 and 79
  alternatives), split by era and half ([04](research/04-gate-scripts.md); §6).
- **Gate-script lessons** applied ([04](research/04-gate-scripts.md) §3):
  - No gate is named after a module, and `probe.*` is avoided too.
  - Gate Python runs with `-I`.
  - Drives reap their process groups and assert nothing is left over.
  - The ledger skips headings.
  - No install-form compare is needed: the surface compare (`baseline.sh`) builds both sides in their
    own locked environments, as before.
- **Adversarial design review** (trigger 3: the cycle delivers test infrastructure and gate scripts).
  It ran as a fresh child against the GOAL, this design, the drafted gates and the prototype, in a
  scratch copy. It found four MEDIUM, two LOW–MEDIUM and four LOW findings, each folded in:
  - **M1, the budget refusal followed the probe** (against R9). Fixed: the lookup now follows the site
    read and the budget check (§2.4). `startup_order.py` checks the order and that no probe starts on a
    budget of 0, an unparsable one, or one short of every capability. `drives.py` adds a budget refusal
    behind a hanging profile.
  - **M2, the override was checked in `local` mode only.** Fixed: `startup_order.py` runs the flag and
    the variable in `ssh` mode too.
  - **M3, a `tuple` or `str` subclass passed the load and ran its code at probe time.** Fixed: exact
    types (§2.1); `declared.py` refuses both.
  - **M4, the overlap over SSH was never driven.** Moot: the lookup no longer overlaps the site read.
  - **LM5, the line counts used a keyword filter.** An extra line, or a resolver warning, slipped
    through. Fixed: `startup_order.py` allows only the start's own lines, and `drives.py` counts each
    stdio drive's lines beyond a plain start's.
  - **LM6, a worker catching only `Exception` passed.** Fixed: `lookups.py` needs each raise decided
    within half the bound, its reason naming the type.
  - **L7, a server killed mid-probe leaves the probe's process group running.** Pre-existing for every
    `local` call: recorded as [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md)
    (§5).
  - **L8, R3 through `run()` compared names only.** Fixed: `drives.py`'s every-present drive compares
    every tool and resource whole, in order, with an in-process server's.
  - **L9, loose docs checks.** Fixed: `docs_gate.py` needs `core/probes.py` as a list item of its own,
    §4's order (after the site read, before the server, refusals first), and § Testing's opt-in.
  - **L10, the ports this host keeps for other servers.** Restored: the drives never pick them.

  The reviewer also confirmed what the gates caught: `command -v`, a dropped `unset -f type`,
  withholding on a timeout, a sequential site-then-probe (since adopted on purpose), a deadline taken at
  the join, lines logged at DEBUG, and probing only in `ssh` mode.

## 5. Risks & open questions

- **A wrong "absent".** A command that appears only after a step the probe's login shell does not take
  (an unexported function, an interactive-only profile line) withholds a capability that would work.
  The remedy is `--skip-probes`, as Q4 intends. The stderr line names what was missing, so the operator
  can see why.
- **A cluster with the marker commands but not the rest** (RCAC: `findscratch` and `myquota` present,
  `jobinfo` missing) serves all ten tools. Each tool keeps its call-time error (GOAL non-goal).
- **One lookup for every capability.** One unanswered lookup fails every probing capability open
  together. That is the ruled outcome (Q2), and it costs one round trip instead of N.
- **A remote rc file's background job** can write into a result over SSH
  ([`issues/startup-background-jobs.md`](../../issues/startup-background-jobs.md)). The parser then
  reads the answer as malformed and fails open; it never withholds on a forged line.
- **The abandoned thread** may finish against the shared executor after startup. It only reads, and
  its result is discarded.
- **A server killed during the probe** leaves the probe's `local` process group running, as it would any
  `local` command in flight. Pre-existing: [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md).
- **Startup is slower in the worst case.** After the connect it is the site read's bound plus the
  probe's, 20 s, with each bounded on its own. The probe's own command normally answers in one round
  trip.
- **Human gate.** A CONFIRMED review finding in `core/__init__.py`, `core/capabilities.py`,
  `core/deprecation.py`, `core/server.py`, `core/probes.py` (added to the list in P1) or a member's
  `capability.py` needs a human decision before landing.
- **Downstream seeds.** P3's checklist records two facts on their seeds:
  - [`issues/lmod-tool-group.md`](../../issues/lmod-tool-group.md): `module` is a function and the
    tools run `$LMOD_CMD`, so that cycle needs a second kind of declared data, a core edit there.
  - [`issues/xdu-storage.md`](../../issues/xdu-storage.md): its tools are meant to offer the install
    where `xdu` is missing, so it should declare no probe.
- **The on-demand mutation workflow** already exceeds its 30-minute job, and this cycle adds about
  200 cases. Pre-existing and gating nothing: recorded as
  [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md).
- Open questions: none. The one reading the GOAL leaves (what "set" means for the override) follows
  § Configuration's own convention, and the deviation table records it against R8's wording.

## 6. Verification strategy

Each phase's `verify:` is `sh spec/capability-probe/verify/p<n>.sh <mode>`, sourcing `lib.sh`, and
removing the calling shell's `CLUSTER_MCP_SKIP_PROBES` from every child.

**The independent checks** (none of them the suite's own tests):

- `declared.py` (P1, 1 s):
  - planted third-party capabilities, five well-formed declarations and 23 malformed ones (subclasses
    of `tuple` and `str` included);
  - each malformed one refused at load, for its declaration (never, say, an unexpected keyword),
    naming the distribution, with the registry unchanged;
  - the members' declarations.
- `lookups.py` (P1, 5 s, in `bin/sandbox.sh`):
  - the runner over three capability sets and 24 endings;
  - one call, the registered script, every name once in load order, the timeout within the bound;
  - verdicts within the bound plus 0.5 s, decided once;
  - the real lookup through the login bash: a stub file, a missing name, an exported function, an
    exported `type`, a file that is not executable.
- `startup_order.py` (P2, 2 s): in-process `main`, covering:
  - order, modes (the override in `local` and `ssh`), the bound, none declared, delegate, refusals,
    budget, and no line but the start's own and the probe's;
  - `PROBE_TIMEOUT` is 10 s and no more than `READ_TIMEOUT`.
- `drives.py` (P2, 41 s `all`, 7 s `quick`): the real CLI in `local` mode under `bin/sandbox.sh`, with a
  stub PATH and a login log.
  - Every member present, each absent, both, and one command absent.
  - A real 10 s hang on stdio and with stdin closed.
  - HTTP, the override, and every refusal.
  - Each server is reaped by process group, and a leftover check follows.
- `docs_gate.py` (P1, P2, 3 s): R10's sections. The bound's figure and the withheld line are read from
  the code.
- `alternatives.py`: every decision the cycle adds, mutated to every alternative.
  - Counts: 93 in P1 (`probes.py`, the commands checks), 79 in P2 (the probe step, its placement at
    every boundary of `run()`, the override, the `env_setting` branch), 172 in all.
  - `coverage` (6 s) requires a `tests/mutants.py` case for each, with a row beside each member set.
  - `cases` runs them per era and per half (`K/N` shards), at about 6 s a case: three existing cases
    measured together on the prototype took 18.7 s. That is about 4.7 min (P1) and 4 min (P2) per
    shard, under the 10-minute command cap.
- `baseline.sh` (P3, 11 s warm): the surface against `c520432`'s, whole. Also: the fixture and
  `test_surface.py` byte-identical, no test function or case lost, no more skips.
- `ledger.py` (P3, seconds).

**Measured** on the plan's prototype (macOS, warm, with another session's suite running at the same
time):

| Gate | Prototype tree | Today's tree |
|------|----------------|--------------|
| `p1.sh phase` | 8 s, green to its coverage step, which fails for want of build's cases (93 gaps) | red at `declared.py`: `commands` is an unexpected keyword |
| `p2.sh phase` | 45 s, green to its coverage step (79 gaps); `drives.py all` 41 s of it | red at import: no `probes` module |
| `p2.sh pre-push` | 7 s | red |
| `baseline.sh` | 11 s, green | — |
| `p3.sh ledger` + `recipe` | about 1 s each, green | — |

A P1-only cut of the prototype ran `p1.sh` to the same point, and `startup_order.py` was red there for
want of the startup step. So each phase's gate bites on its own tree.

**Suite growth, projected per era against `c520432` (359.6 s / 359.5 s local).**

| Phase | Added | Local | CI (×1.6) |
|-------|-------|-------|-----------|
| P1 | about 150 in-process rows at ≈10 ms; the hang rows at a 0.3 s bound, one per member set; 2 bash integration rows; 3 `LoopbackSSH` rows at ≈1–2 s | ≈ +8 s | ≈ +13 s |
| P2 | about 60 in-process rows; about 10 CLI drives at ≈1 s, none waiting out the real bound | ≈ +12 s | ≈ +20 s |
| **Total** | | **≈ +20 s (≈ 6 %)** | **≈ +35 s** |

The prototype's product change, with no new tests, ran the handshake-era suite in 372.2 s (3515
passed). It ran beside the gates' dry runs. Its five failures are all expected:
- `test_env.py::test_every_variable_has_its_legacy_name`, which PLAN §2.7 edits;
- three `test_mutation_anchor_applies` rows whose anchors `run()`'s new statements move, which TECH
  P2 re-anchors;
- the seeded load-flaky reconnect test
  ([`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md)).

That keeps both eras well inside the CI job's 20 minutes. A drive at ≈2 s with a sandboxed `uv run`
measured 2.0 s on the prototype; the suite's harness drives measure about 1 s
([03](research/03-testing-and-budget.md) §4).

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
