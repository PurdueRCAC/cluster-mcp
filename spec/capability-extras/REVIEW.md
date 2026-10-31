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
