# PLAN — The dependency audit and the suite work under every supported uv

> **Status:** Draft for review · **Last updated:** 2026-10-17
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Lean path (`appetite: small`, `kind: fix`):
> no `research/`; the prototype evidence is summarised in § 4.

## 1. Summary

The wrapper stops inferring "offline" from uv's wording and decides it itself: it reads `UV_OFFLINE`
by uv's boolean rules, passes `--offline` to uv as a flag, and reports any non-finding result of an
offline audit as "advisory source unreachable". The integration test proves R8 with a counting
loopback proxy (a canary) instead of uv's refusal text, and a second, online row through the same
canary is the positive control that shows the canary sees this uv's requests. `pyproject.toml`
declares the floor as `[tool.uv] required-version = ">=0.12.17"`, which uv itself enforces. Three
small phases; the last runs the profile's full `verify` under a pinned uv 0.12.17 and 0.13.1.

## 2. Design

### 2.1 `bin/audit_lock.py`: the wrapper decides offline

- **`offline_requested(environ) -> bool`** (new): `UV_OFFLINE` unset → online; set to a value uv reads
  as false (`0 false f no n off`, case-insensitive, no stripping: uv rejects `' 0'`) → online; **any
  other value, the empty string, padded and garbage values included, → offline**. uv itself rejects
  an unparseable value with exit 2; mapping it to offline keeps that fail-closed and makes no request. This is the only
  offline channel: `--no-config` already blocks a `uv.toml` `offline = true`, and `child_env` drops
  every other `UV_*`.
- **`command(environ) -> list[str]`** (new; `COMMAND` becomes `ARGS`, the argv after the executable):
  the executable is `environ['UV']` when set, else `uv` on `PATH`; then `ARGS`; then `--offline` when
  `offline_requested(environ)`. `uv run` sets `UV` to its own executable, so the audit runs under the
  very uv that launched the gate and enforced the floor, not whatever `uv` comes first on `PATH`
  (review finding 1). `main()` derives argv and environment from one `environ` snapshot.
- **`UV_ALLOWED`**: drop `UV_OFFLINE` (the flag carries it now, so the wrapper's reading is the only
  one and uv cannot read the variable differently); add `UV_HTTP_RETRIES` (§ 3 deviation: it lets the
  positive-control row fail in 0.1 s instead of 21 s; it selects no project, group or service, and
  fewer retries can only make the audit fail sooner, never pass).
- **`audit_violations(returncode, output, lock_text, offline=False)`**: **when `offline`**, decided
  first: `EXIT_UNREACHABLE` with `advisory source unreachable: the audit ran offline (uv audit exited
  N)`, whatever uv printed and whatever it exited, 0 and 1 included (an offline audit never consulted
  the source, so it can never be green, and R1 says it exits 2); any findings uv printed are named in
  a second reason. Online, findings (a parsed finding or exit 1) win and exit 1, and the
  text-marker logic is unchanged: R2's online wording ("error sending request" / "Request failed
  after N retries") is printed by both 0.12.17 and 0.13.1 and is already in `UNREACHABLE`; `requires
  network access` stays as a harmless marker.
- Docstring: the `UV_OFFLINE` sentence becomes "read here and passed as `--offline`"; the exit-status
  paragraph gains "an offline audit exits 2". Comments stay declarative, no spec ids.

### 2.2 `tests/test_audit.py`: pin the wrapper, not uv

- `OFFLINE_REFUSAL` and every assertion on uv's text go. The planted `id='offline'` row of
  `test_audit_check_catches` (uv 0.13's wording, `offline` unset) is replaced by
  `test_offline_audit_is_unreachable_whatever_uv_says`: `offline=True` with a made-up uv wording, an
  empty output, and a clean exit-0 summary, each → exactly `(2, ['advisory source unreachable: the
  audit ran offline (uv audit exited N)'])`.
- `test_offline_setting_reaches_uv_as_a_flag` (unit, parametrised over unset / true-ish / false-ish /
  empty / padded `' 0'` / garbage): `offline_requested`, `'--offline' in command(…)` and
  `'UV_OFFLINE' not in child_env(…)` agree. `test_offline_audit_with_findings_still_exits_unreachable`
  (unit) pins the offline-first precedence.
- `test_main_runs_the_command_and_env_it_derives` (unit; review finding 2): `subprocess.run` in the
  loaded module is replaced by a recorder and `main()` runs with `os.environ` set to each of: online
  with `UV`, offline with `UV`, offline without `UV`. The recorded argv is exactly `command(environ)`
  (its first element `UV`, else `uv`) and the environment exactly `child_env(environ)`, so the
  wrapper builds one environment in both modes, proxies included. This is what lets the online
  canary row vouch for the offline row's zero. `test_audit_env_drops_uv_selectors` moves `UV_OFFLINE` to `dropped` and
  `UV_HTTP_RETRIES` to `kept`.
- **The canary** (test helper class): a `socket.create_server(('127.0.0.1', 0))` listener on a
  daemon thread that counts accepted connections and closes each. `accept` runs on a short timeout
  in a loop that checks a stop event; `close()` sets the event, joins the thread, then closes the
  socket, so it never relies on a close waking a blocked `accept` (it does not on Linux). Every proxy variable (upper and
  lower case `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`) points at it; `NO_PROXY`/`no_proxy` and any
  inherited `UV_OFFLINE` are removed; `UV_HTTP_RETRIES=0`; `TMPDIR` is the test's `tmp_path`. The
  real script runs under `bin/sandbox.sh`, as today.
- **`test_audit_fails_closed_offline`** (integration, name kept: the GOAL and the stack-upgrade record
  cite it): `UV_OFFLINE=1`; `offline_violations(returncode, stderr, connections)` (name kept, gains
  `connections`) requires exit 2, the wrapper's own `audit_lock: advisory source unreachable`, and
  **zero** canary connections.
- **`test_audit_fails_closed_unreachable`** (integration, new): no `UV_OFFLINE`;
  `unreachable_violations(returncode, stderr, connections)` requires exit 2, the same wrapper message,
  and **at least one** canary connection. This is R2's evidence under the uv in use and the positive
  control for R8: the zero above means something only because this row shows the canary sees the
  requests this uv makes through this wrapper. Both rows run every planted negative first (exit 0;
  the reason missing; offline with a connection; online with none), as the current row does.
- Module docstring and `AGENTS.md` § Testing's `tests/test_audit.py` entry are rewritten to match
  (same commit: the § Testing entry names `offline_violations` and the allowlist).

### 2.3 The floor: `pyproject.toml`

```toml
[tool.uv]
# The oldest uv this project supports; an older uv refuses to sync, lock or run it.
required-version = ">=0.12.17"
```

No upper bound ("through the current release" cannot be enumerated ahead). `uv.lock` does not record
it: `uv lock --check` passes unchanged under 0.12.17 and 0.13.1 with the table added. `AGENTS.md`
§ Commands gains one line beside "Supported Python is 3.14+": "Supported uv is 0.12.17+; the floor is
`[tool.uv] required-version` in `pyproject.toml`, which uv enforces." README's Development block is
left alone (it names no version today; pointing, not restating).

### 2.4 Where each uv release comes from

Every pinned uv is the `uv` wheel from PyPI, installed by the local uv into an ephemeral environment
in uv's own cache, never into the tree:

```sh
uv run --no-project --isolated --with uv==X.Y.Z sh -c '<commands>'
```

`uv run` puts that environment's `bin/` first on `PATH`, so every `uv` inside `<commands>`, including
the one `bin/audit_lock.py` launches from the integration rows, is X.Y.Z; each gate starts with
`uv --version | grep -qF X.Y.Z` so a wrong `uv` on `PATH` cannot pass silently. Releases: **0.12.17**
(the floor), **0.13.1** (the current release, PyPI's latest at 2026-10-17), **0.12.16** (the release
just below the floor, for R6). Network to PyPI is needed once per release to fill the cache; the gates
themselves make no other request.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `offline_requested` + the `offline` branch of `audit_violations` (text-free); `test_audit_fails_closed_offline` under 0.12.17 and 0.13.1 |
| R2 | Online `UNREACHABLE` markers (both ends print `error sending request`); `test_audit_fails_closed_unreachable` under both ends |
| R3 | `audit_violations`' online fall-through unchanged (`cannot-run` row); offline can never exit 0 |
| R4 | P3: the full profile `verify` under `uv==0.12.17` |
| R5 | P3: the full profile `verify` under `uv==0.13.1` |
| R6 | `[tool.uv] required-version = ">=0.12.17"`; P2 drives `uv sync --locked` and `uv run` under `uv==0.12.16` |
| R7 | Tests assert exit status and `audit_lock:` messages only; `OFFLINE_REFUSAL` removed; offline unit rows use a made-up uv wording |
| R8 | `--offline` passed by the wrapper to the launching uv (`UV`); the canary counts zero connections offline; the online row is the positive control, and `test_main_runs_the_command_and_env_it_derives` shows both rows get the same environment |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before design (intent) and again against this draft. No numbered § Invariants section (§1–§9)
is touched: no `src/` file changes, and no path on the high-blast-radius list (`bin/sandbox.sh` is used,
not edited).

- **§ Conventions, sandbox rule** — both integration rows drive the real script under
  `bin/sandbox.sh`, as today; the R6 and matrix gates run `uv sync`/`uv run` in the worktree's own
  project, and their only CLI drive is the profile's `bin/sandbox.sh uv run rcac-mcp --help`.
- **§ Conventions, tests** — every new test carries `unit` or `integration`; gates name test files and
  ids, never a bare marker selection. `offline_violations` and `test_audit_fails_closed_offline` keep
  their names (§ Testing: names are a contract).
- **§ Conventions, comments** — declarative, no `R#`/`P#` in code or tests.
- **§ Conventions, version single-sourced** — `required-version` constrains uv, not the project
  version; `project.version` is untouched.
- **§ Packaging** — no dependency change, so no `uv lock`; `uv lock --check` stays green under both
  ends (prototype). The sdist excludes are unaffected.
- **§ Factory, release recipe `audit` caveat** — still true: frozen, `--no-config`, `--project`,
  allowlisted `UV_*`, fails closed, never in `verify`. The caveat names no allowlist members, so it
  needs no edit; § Testing's entry does (above).
- **Profile `verify`** — unchanged; it stays offline-capable and deterministic. The new rows contact
  only a loopback listener the test owns.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| The wrapper parses `UV_OFFLINE` and passes `--offline` (two small functions) | R1/R7 must hold whatever uv prints offline; the defect is the wrapper keying its verdict on uv's wording | Appending 0.12's "Network connectivity is disabled" to `UNREACHABLE`: one line, but the offline verdict stays hostage to uv's text, and the next rewording reopens this exact defect (GOAL outcome) |
| The audit launches `UV` (the launching uv), falling back to `PATH`'s `uv` | Under a pinned `uv run`, `PATH` may name another uv, one below the floor included, and `uv audit --no-config` skips `required-version` (review finding 1) | Keeping the bare `uv`: the gate then tests whichever uv `PATH` happens to name, not the one under test |
| `UV_HTTP_RETRIES` joins `UV_ALLOWED` | The online positive-control row otherwise waits out uv's three retries: 21 s per run, 42 s per `verify` (both eras), measured under both ends | Accepting the delay: costs every build and review run; the knob cannot select a project, group or service and fewer retries only fail sooner |

## 4. Rabbit holes (resolved)

All settled by prototype on a copy of `813ec20`, uv from PyPI (§ 2.4), 2026-10-17:

- **Does uv 0.12 serve an offline audit from a warm cache?** → No. After a clean online audit
  (94 packages) under each end, `UV_OFFLINE=1` and `--offline` both refuse with exit 2 (0.12.17:
  "Network connectivity is disabled, but the requested data wasn't found in the cache"; 0.13.1:
  "requires network access"). The design does not rely on it anyway: offline is never green.
- **Is `--offline` accepted by `uv audit` at both ends?** → Yes, same refusal as the variable.
- **How does uv read `UV_OFFLINE`?** → `0/false/FALSE` online; `1/TRUE/yes/on` offline; `garbage` and
  the empty string are parse errors (exit 2) at both ends, and so are padded values (`' 0'`).
  `offline_requested` mirrors that and maps errors to offline.
- **Do both ends honour the proxy variables, and what do they print?** → Yes: through a loopback proxy
  both print `error sending request for url (https://api.osv.dev/v1/querybatch)`; with default
  retries, `Request failed after 3 retries` after ~21 s and ~370 canary connections. A reply that is
  not a tunnel (RST, 403, non-TLS bytes) is retried just the same, hence the `UV_HTTP_RETRIES`
  deviation.
- **Does `required-version` do R6's job?** → Yes, for every command that reads `[tool.uv]`. Under 0.12.16, `uv sync --locked`, `uv run true`,
  `uv lock --check` and `uv run --no-project true` (from the project) each exit 2 with "Required uv
  version `>=0.12.17` does not match the running version `0.12.16`", before reading the lock.
  `--no-config` commands (the audit's own `uv audit --no-config`) skip it, hence `UV` in § 2.1.
- **Full `verify` under both ends with the prototype** → see § 6 (green, both eras, both ends).
- **Adversarial design review** (trigger 3) → ran; see § 4.1.

### 4.1 Adversarial review

Ran 2026-10-17: a fresh reviewer given only GOAL, this draft and a copy of the prototype, mutating
the copy and running the suite under uv 0.12.17 and 0.13.1. Caught by the drafted gate, at both
ends: `--offline` dropped from `command()`; `main()` bypassing it; the verdict keyed on uv's text
again; `UV_OFFLINE` kept in the allowlist; a canary that never counts or is never wired; a weakened
zero assertion; the online marker removed; exit 2 read as findings. R6's refusal passes for the right
reason (it names `>=0.12.17` for `sync`, `run`, `lock --check`, `run --no-project`, `pip list`); the
integration rows ran 15 times per uv with no flake. Findings, each folded:

1. **MED, confirmed: the wrapper ran the `PATH` uv, and `--no-config` skips the floor.** Under a
   pinned `uv run`, `PATH` can still resolve to another uv (one below the floor passed both rows). →
   § 2.1 `command()` launches `UV` (set by `uv run` to itself), else `PATH`'s `uv`; a unit row pins
   it. The reviewer also proposed a floor check inside the wrapper; not taken: the GOAL puts the floor
   where uv enforces it, and the launching uv has already enforced it (§ 5).
2. **MED, confirmed: the online control vouched only for the online environment.** A `main()` that
   dropped `--offline` and pointed the proxies at a dead port when offline passed every row. →
   `test_main_runs_the_command_and_env_it_derives` (§ 2.2); the same mutant now fails two rows.
3. **LOW, confirmed: `.strip()` disagreed with uv on padded values.** → no stripping; `' 0'` row.
4. **LOW, paper: closing a socket does not wake `accept` on Linux.** → stop event + accept timeout.
5. **LOW, paper: offline + exit 1 reported findings, not exit 2.** → offline decided first (§ 2.1).
6. **LOW, paper: the online row still depends on one uv phrase; an inherited `UV_HTTP_RETRIES=0` can
   make a release audit fail on one transient error.** → both named in § 5.

After the fold, the prototype passes P1's and P3's `verify:` as parsed from `TECH.md`: the full
`verify` (444 tests) is green in both eras under 0.12.17 and 0.13.1.

## 5. Risks & open questions

- **"Current uv" moves.** R5 is gated on 0.13.1, PyPI's latest today. Review and publish re-run P3's
  gate with the then-latest release if a newer one exists; a red there is a new finding, not a waiver.
- **Releases between the ends** (0.12.18–0.12.24, 0.13.0) are supported but not exercised; the GOAL
  names the two ends as what a gate exercises. The offline verdict no longer depends on their wording.
- **The canary sees only HTTP(S) via the proxy.** A uv that bypassed proxy variables would show zero
  connections in both rows, and the online row turns red, so the gate fails loudly rather than
  greenly. A DNS lookup is not observed; no supported uv performs one when offline or behind a proxy.
- **The online verdict still reads one uv phrase.** R2's "advisory source unreachable" online rests
  on `error sending request` / `Request failed` (printed by both ends). A uv that rewords it turns
  the online row red, correctly: the wrapper would then misreport, and R2 is about that report. The
  offline verdict no longer reads uv's text at all.
- **`UV_HTTP_RETRIES` passes through.** An inherited `0` makes a release audit fail on one transient
  error: a nuisance, never a false green.
- **The floor is uv's, not the wrapper's.** `python3 bin/audit_lock.py` run without `uv run` (no `UV`)
  audits with `PATH`'s uv, unchecked. The documented and gated invocation is `uv run python
  bin/audit_lock.py`.
- **No standing mutant for the audit.** `tests/mutants.py` copies only the package, never `bin/`;
  the planted negatives in `offline_violations`/`unreachable_violations` and the review's mutation
  pass are the guard. Not deferred: the runner's scope is a pre-existing design choice, not a defect.
- **CI.** `ci-workflow` (held) pins 0.12.17; this cycle makes its first run green without touching
  `.github/`.

## 6. Verification strategy

- **Slice gates name test ids** under both ends: `tests/test_audit.py` in full (unit and the two
  integration rows), in both protocol eras, with `uv --version` asserted first.
- **R6** drives uv 0.12.16 against the real project: `uv sync --locked` and `uv run true` must each
  fail and name `0.12.17`; uv 0.12.17 must accept `uv lock --check`.
- **R4/R5**: the profile's full `verify`, verbatim, inside each pinned uv (§ 2.4). Prototype result
  (2026-10-17): green, below.
- Prototype result (2026-10-17, before the review fold): all three phase `verify:` strings, as
  parsed from `TECH.md`, exit 0 against the prototype; P3's full `verify` is green in both eras under
  0.12.17 and 0.13.1. After the fold, P1 and P3 were re-run and are green (§ 4.1).
