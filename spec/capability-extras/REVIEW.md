# REVIEW — Capabilities you don't have shouldn't be tools you see

> Adversarial QA by `code-review`, run in an isolated/clean context (a subagent; where the runtime
> has none, `code-review`'s sequential fallback). The correctness pass grades the branch diff against
> [`GOAL.md`](GOAL.md) + the repo's `AGENTS.md` § Invariants **only** — it does not see
> `PLAN.md`/`TECH.md` (avoids grading-its-own-homework / plan-sycophancy). Every finding cites an
> **executed** command, not an assertion.

- **Reviewed commit:** `cedd98a`  ·  **Base:** `ad70cc0` (`origin/develop`)  ·  **Date:** 2026-10-31
- **Verdict:** changes-requested
- **Cycle:** 1 of ≤3 — mirrors `review.cycle` in `TECH.md`

## How it ran

The debate variant: the diff touches `core/server.py`, in the profile's `coupled core`. Two blind
reviewers ran at once, one arguing ship and one block, each in its own clone of `cedd98a`, with only
the GOAL's text, the rubric's text, the spec-excluded diff and the repository (its `AGENTS.md`
included). Both left their clones clean (`git status --porcelain` empty, every mutant reverted and
re-checked). No R-ID is an artifact deliverable: R10's documents are in the diff, so the reviewers
graded every R-ID.

**Contract drift.** `GOAL.md` changed once after the shape commit: `ec497ee` added Clarification Q5
(R8's stdio exit), ruled by the foreman at the PLAN/TECH sign-off. The foreman, as judge under the
effort's autonomy decision, confirmed it as a legitimate post-shape clarification before grading.

## Verification run

Both reviewers, independently, in their own clones:

- `uv sync --locked`, `uv lock --check` → ok.
- `uv run pytest -q` → 2765 passed, 14 skipped; `CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` →
  2765 passed, 14 skipped. The skips are the existing need-shell and need-git rows; the new and
  touched test files ran with `-rs` at 232 passed, 0 skipped. (One run of the block reviewer's
  mutant suite also failed `test_a_stalled_reconnect_is_abandoned_against_a_real_handshake`, the
  seeded load-flaky reconnect test, in an untouched subsystem.)
- `bin/sandbox.sh uv run cluster-mcp --help` → exit 0.
- `tests/mutants.py`: every new or changed case killed (ship: 18; block: the 11 new ones).
- Fresh environments from the clone, by path and by `git+file://` URL: core alone, `[slurm]`,
  `[rcac]`, `[slurm,rcac]`, the compat root, an editable root (the container image's form), and
  `uv build --all-packages --no-sources` metadata.
- Live drives under `bin/sandbox.sh` over stdio and HTTP: each install's tools, resources and base
  instructions; the compat root and the `[slurm,rcac]` install against `ad70cc0`'s compat install,
  byte for byte (initialize result, tools with schemas, annotations and titles, resources,
  templates, prompts); planted third-party capabilities that load, that raise on import, whose tools
  module is missing, and whose resources are malformed.
- Reviewer mutants: killed — load order from discovery, listing order, alias placement, no
  rollback, the CLI swallowing a load failure, the RCAC alias dropped, the RCAC order moved, an
  unpartitioned resource list. Survived — see F2.

## Requirement → evidence matrix

| R-ID | Implemented by | Verified how (both reviewers unless noted) | Status |
|------|----------------|--------------------------------------------|--------|
| R1 | `packages/cluster-mcp/pyproject.toml`, `uv.lock` | Fresh installs give exactly core, +slurm, +rcac, all three; built metadata has `Provides-Extra` and `extra ==` markers only | ✅ |
| R2 | `core/capabilities.py`, both `capability.py`, member `pyproject.toml` entry points | No member module imported before the load; loaded set equals installed set; a planted third-party capability is discovered and served | ✅ |
| R3 | `core/tools/__init__.py`, `core/server.py`, `core/resources.py` | No member import in the core (grep, `test_core_imports_no_member`); a planted capability served with no core edit | ✅ |
| R4 | as R1–R3 | Core-only install: exactly the 7 core tools, only the context resources, stdio drive exit 0 | ✅ |
| R5 | `core/capabilities.py`, `core/server.py` | Base equals the core text plus each loaded capability's, under five capability sets and a real core-only install; listed equals served | ✅ (one guard unpinned, F2) |
| R6 | as above | Compat root and `[slurm,rcac]` byte-identical to `ad70cc0`'s compat install; fixture and `test_surface.py` untouched | ✅ |
| R7 | `rcac/resources.py`, `rcac/capability.py`, `core/resources.py` | Storage URIs served only with the RCAC member; capability resources never open | ✅ |
| R8 | `core/__init__.py`, `core/capabilities.py`, `core/startup.py` | Import and tools-module failures: stdio answers each request naming the distribution and exits 5, closed stdin exits 5 at once, HTTP exits 5 before binding, `--help`/`--version` unaffected. **Resource registration failures do not** | ❌ F1 |
| R9 | root `pyproject.toml` | Compat git install pulls all three and serves the base surface; the old `uvx` line warns once and runs | ✅ |
| R10 | `AGENTS.md`, `README.md`, member READMEs | §7, §9, § Packaging rewritten; README line `cluster-mcp[slurm,rcac]`; inventory headings by extra. §7's "malformed resource is refused" overstates (F1) | ✅ (wording follows F1) |

Clarifications: Q1–Q4 verified as ruled. Q5 verified for import and tools-module failures, contradicted by F1.

Unmapped changes: the `capability-probe` and `unlocked-install-floors` seeds and their entries
(deferral homes; the second corrects a false § Packaging claim, reproduced: a fresh install resolved
a newer pydantic than the lock pins), `tests/harness.py`'s `Listed.resources`, the Dockerfile
comment, and one ROADMAP intro edit (F3).

## Findings

### F1 [MEDIUM/CONFIRMED] A capability resource FastMCP rejects passes the load and fails outside R8's refusal path
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:119-130` (`_check_resource` checks shape only); surfaces in `core/server.py:150-155`; the startup order in `core/__init__.py`.
- **Failure scenario:** a capability declares a resource that is well-formed by the loader's checks but that FastMCP refuses: a URI that is not a URL (`'planted storage'`), or a handler with a parameter on a static URI. The load accepts it; the server runs the mode ladder and then fails while building the server, with exit 2, a message that does not name the distribution, and on stdio no answer to any request. In `ssh` mode the connection and the remote site read happen first (by reading the startup order; not driven).
- **Evidence (block reviewer):** a venv with `cluster-mcp[slurm,rcac] @ git+file://<clone>@cedd98a#subdirectory=packages/cluster-mcp` plus planted `planted-badres` and `planted-badhandler`. `bin/sandbox.sh …/cluster-mcp -e local </dev/null` → `CRITICAL 1 validation error … Input should be a valid URL`, exit 2; with one `initialize` piped in, stdout empty, exit 2; `-t http` → exit 2; badhandler → `CRITICAL URI template must contain at least one parameter`, exit 2. Controls (`planted-broken`, `planted-badtools`) take the refusal path: exit 5, each request answered `cannot load capability …`.
- **Touches:** R8, Clarification Q5; `AGENTS.md` §7's own statement that a malformed resource is refused.
- **Routed as the property, over its domain:** every way a capability's declared contribution (its tools, its instructions, its resources) can be rejected while the server is assembled is decided by the load, before the mode ladder, and refused naming the distribution, so nothing a capability declares can fail later on another path. Pin it with planted cases for each kind of contribution FastMCP itself can reject, on stdio, closed stdin and HTTP, and narrow §7's wording to what the load decides.

### F2 [LOW/CONFIRMED] Three documented load refusals survive behaviour-changing mutants
- **Where:** `core/capabilities.py` — the stray-tool refusal (`if stray:`, ~:182-186), the same-capability duplicate-tool refusal, and attribution of tools to "that module or below it" (§7).
- **Failure scenario:** with the stray-tool refusal disabled, a capability whose tools module imports a sibling defining a tool loads, registers that tool, and serves it unnamed in the base instructions, breaking R5's registry↔instructions relation.
- **Evidence:** ship reviewer: `if stray:` disabled → `tests/test_capabilities.py tests/test_core_only.py` 54 passed; same-capability duplicate disabled → 51 passed; exact-module attribution → 51 passed. Block reviewer: `if stray:` → `if False:` → 382 passed over every capability-related test file; the full handshake suite passed but for the seeded reconnect flake; planted `planted_stray` loads under the mutant and is refused without it. The unmutated loader refuses each case (both reviewers' plants).
- **Touches:** R5 (the guard that keeps the registry equal to what the base names); § Invariants §7.
- **Routed as a mutant sweep** over every decision in `core/capabilities.py`, each mutant run under every capability set the GOAL names (core only, each member, both) and both protocol eras, equivalent mutants recorded with the reason (the ship reviewer's dropped-cache mutant is one: a second load re-imports cached modules and registers nothing new).

### F3 [LOW/CONFIRMED] The roadmap contradicts itself on the timeout measurement
- **Where:** `ROADMAP.md` Part I intro ("its measurement now approved", from `f62e3b5`) against the entry "A timed-out command may keep running after its call returns" ("Its measurement needs Geoffrey's approval first"; Horizon "the measurement needs Geoffrey's approval").
- **Evidence:** block reviewer, by reading both lines at `cedd98a`.
- **Fact for the fix:** Geoffrey approved the measurement on 2026-10-29. The entry is the stale side; make it agree with the intro.

### Out of scope (recorded, not blocking)
- **A retried load after a failure registers nothing and names the wrong distribution** (ship reviewer, reproduced with planted `aaa-good`/`bbb-broken`). No R-ID covers a retry, and the command line never retries (a load failure exits 5). Seeded as [`issues/capability-reload-after-failure.md`](../../issues/capability-reload-after-failure.md) with its `ROADMAP.md` entry, committed before this verdict.
- Dropped by the ship reviewer as pre-existing: an entry-point line with no `=` fails inside the import with a traceback, identically on `ad70cc0`.

## Human-gate triggers

- **Triggered:** F1 is CONFIRMED in files on § Invariants' high-blast-radius list
  (`core/capabilities.py`, `core/server.py`, `core/__init__.py`). Under the effort's autonomy
  decision the foreman is judge at human gates; it ruled F1 a fix (routed above) and reported it to
  Geoffrey on 2026-10-31. The trigger stays recorded until publish.

## Optional completeness sub-pass

Not run.

## Review cycle 2 — changes-requested (2026-10-31)

- **Reviewed commit:** `2c5ceda`  ·  **Base:** `ad70cc0` (`origin/develop`)
- **Mode:** a fresh blind pass over the full spec-excluded diff (the default), debate variant: two
  reviewers, ship and block, each in its own clone of `2c5ceda`, with the same inputs as cycle 1
  (GOAL unchanged since `ec497ee`). Neither saw cycle 1's findings. Both left their clones clean and
  no process of theirs running.

### Verification run

Both reviewers, independently: `uv sync --locked` and `uv lock --check` ok; `uv run pytest -q` and
`CLUSTER_MCP_TEST_ERA=modern uv run pytest -q` 3043 passed, 14 skipped each (the bash 4.1 rows);
`bin/sandbox.sh uv run cluster-mcp --help` exit 0. CI on `2c5ceda`: 3057 passed per era. Fresh
environments from `git+file://` URLs of the clone: core alone, `[slurm]`, `[rcac]`, `[slurm,rcac]`,
the compat root, an editable root. Live drives under `bin/sandbox.sh` over stdio, closed stdin, HTTP
and SSE in both eras, with planted third-party capabilities, well-formed and malformed. With every
member installed, the full ordered surface is byte-identical (`cmp`) to `ad70cc0`'s in both eras.

### Requirement → evidence

| R-ID | Status |
|------|--------|
| R1–R7, R9, R10 | ✅ both reviewers, on executed evidence (installs, imports, drives, byte comparison) |
| R8 | ❌ F1, F2, F3: the refusal path holds for every capability that raises an `Exception`; the cycle-1 resource class is closed (each planted kind refused at load, exit 5, distribution named) |
| Q1–Q5 | ✅, Q5 except as R8 |

### Findings

#### F1 [MEDIUM/CONFIRMED] A capability that exits while loading bypasses the refusal
- **Where:** `packages/cluster-mcp/src/cluster_mcp/core/capabilities.py:206-213` (`except Exception`), `core/__init__.py:236-241`.
- **Failure scenario:** a capability module calls `sys.exit(...)` at import (a platform guard, say). `SystemExit` is not an `Exception`, so neither the load nor the CLI turns it into the refusal: the server exits 0 (or 1 with the bare exit text), names no distribution, and answers nothing on stdio.
- **Evidence (block reviewer):** planted `cap-sysexit` (`raise SystemExit(0)`) beside `[slurm,rcac]`: one `initialize` over stdio → exit 0, empty stdout and stderr; `-t http` → exit 0. `sys.exit("this capability needs Linux")` → exit 1, stderr only that text. Controls raising `RuntimeError` and `ModuleNotFoundError` take the refusal path, exit 5.
- **Touches:** R8, Q5.

#### F2 [MEDIUM/CONFIRMED] The stray-tool and non-tool guards depend on when the tools are imported
- **Where:** `capabilities.py:210` (`before` is taken after `ep.load()`).
- **Failure scenario:** a capability whose entry-point module imports its own tools module registers its tools during `ep.load()`, before `before` is taken. A tool its tools module's import registers outside the declared module is then neither refused nor served: the server starts with it silently missing, and `TOOL_REGISTRY` holds a tool the base does not name.
- **Evidence (block reviewer):** two plants identical but for one import in `capability.py`. Without it, `cap-stray3` → exit 5, `importing cap_stray3.tools registered ['helper_tool'], which are outside it`. With it, `cap-stray2` → exit 0, `listed_2` served, `helper_tool` not. Confirmed by the foreman by reading the line order.
- **Touches:** R8 (not silently missing), R5 (registry equals what the base names).

#### F3 [LOW/CONFIRMED] Ordering the capabilities runs outside the refusal path
- **Where:** `capabilities.py:192` (the `sorted(...)` call, before the `try`).
- **Failure scenario:** an installed dist-info with no `Name` (corrupt metadata) and an entry point in the group: the sort raises `TypeError`, the server exits 6 with `'<' not supported between instances of 'NoneType' and 'str'`, no distribution named, no stdio answer. Alone in a core-only env it is refused but named `None`.
- **Evidence:** both reviewers, independently, with a hand-made dist-info. The ship reviewer rated it MEDIUM on an edge path; it is LOW here, since no conformant installer writes it.
- **Touches:** R8, Q5.

#### F4 [LOW/CONFIRMED] Four behaviour-changing mutants survive
- `capabilities.py:292`: `composed()` tie-broken by `capability.name` instead of `distribution` → 311 passed (the tie test's names and distributions sort alike). §9 documents "ties by distribution name".
- `capabilities.py:284-285`: `installed()` caching a failed load as `()`, so a later call serves the core only → 317 passed. Its docstring says a failed load is not cached.
- `core/__init__.py:180-190`: the capability load moved above the `--generate-token` branch → 354 passed. AGENTS places it right after that branch.
- `core/tools/__init__.py:85`: `_OPENING` taken above the `transfer` import, so `upload_file` and `download_file` are served after every capability tool → 3043 passed, 14 skipped. The suite builds its expected order from `CORE_TOOLS`/`CLOSING_TOOLS` themselves, and the baseline compares dicts.
- **Evidence:** block reviewer (first three), ship reviewer (fourth), each mutant reverted and the restore verified.
- **Touches:** R5, R6 (served order), R8, §9.

### Observations (not findings)

- A capability whose text pushes the base past the budget is refused when the server is built (exit 2, distribution not named). §7 documents this as deliberate, per the foreman's cycle-1 ruling.
- A third-party resource with a scheme other than `cluster://` is listed among the `rcac://` aliases (`cluster://context, cluster://storage, rcac://context, acme://hello, rcac://storage`). No R-ID orders third-party resources.
- Both reviewers reproduced the seeded `capability-reload-after-failure` and `unlocked-install-floors` claims; both seeds are accurate.

### Routing

- **F1–F3 as one property:** every failure from discovering, ordering or loading a capability, of any kind a capability's own code can raise or exit with, is refused before the mode ladder, naming the distribution (or the entry point, when the distribution has no name). And whether a registration is checked never depends on when a capability's code imported its tools module: the guards see everything registered since that capability's load began. Pin each kind (an `Exception`, `SystemExit` with 0, an int, a string; a missing `Name`; tools imported from the entry-point module, from a sibling, at both times) on stdio, closed stdin and HTTP. `KeyboardInterrupt` keeps its meaning.
- **F4 as a mutant sweep** over every decision in `core/capabilities.py`, the load's placement in `core/__init__.py` and the opening/closing partition in `core/tools/__init__.py`. Each decision is mutated to **every** alternative it could take, not one: each other sort key, each other cache value, each other placement. Run each mutant under every capability set and both eras, with equivalents recorded and why. Cycle 1's sweep killed one mutant per decision, and the siblings above survived.

### Human-gate triggers

- **Triggered:** F1 and F2 are CONFIRMED in `core/capabilities.py` and `core/__init__.py`, on § Invariants' high-blast-radius list. This verdict reaches the review bound (`review.cycle` 2 of ≤3), so the remediation route goes to Geoffrey.
