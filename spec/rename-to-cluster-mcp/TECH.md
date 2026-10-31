---
slug: rename-to-cluster-mcp
title: Rename rcac-mcp to cluster-mcp
kind: refactor
appetite: big
status: done
branch: refactor/rename-to-cluster-mcp
base: develop
current_phase: done
last_updated: '2026-10-30'
phases:
- id: P1
  name: The workspace, the namespace and the command names
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R8
  - R9
  - R10
  - R15
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/rename-to-cluster-mcp/verify/p1.sh
- id: P2
  name: CLUSTER_MCP_* variables, the legacy names honoured, the sandbox fails closed on both
  status: done
  satisfies:
  - R2
  - R4
  - R5
  - R6
  - R15
  - R16
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 1
  verify: sh spec/rename-to-cluster-mcp/verify/p2.sh
- id: P3
  name: cluster:// resources with derived rcac:// aliases
  status: done
  satisfies:
  - R7
  - R8
  - R15
  depends_on:
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/rename-to-cluster-mcp/verify/p3.sh
- id: P4
  name: The instructions split and the server's name
  status: done
  satisfies:
  - R2
  - R8
  - R11
  - R12
  - R15
  depends_on:
  - P3
  parallel: false
  hammerable: false
  hill: uphill
  verify: sh spec/rename-to-cluster-mcp/verify/p4.sh
- id: P5
  name: Repository text, the release recipe on this head, the deferral ledger
  status: done
  satisfies:
  - R8
  - R13
  - R14
  - R15
  - R16
  depends_on:
  - P4
  parallel: false
  hammerable: false
  hill: uphill
  attempts: 3
  verify: sh spec/rename-to-cluster-mcp/verify/p5.sh && uv run python spec/rename-to-cluster-mcp/remediation/F6-F9-upgrading-source-and-one-warning.py && uv run python spec/rename-to-cluster-mcp/remediation/F5-tool-title-pinned.py
review:
  last_reviewed_commit: f8d6af1
  verdict: approved
  blocked_reason: ''
  cycle: 3
---

# TECH.md — Rename rcac-mcp to cluster-mcp

The **context engine and finite-state machine** for building this refactor. The YAML
frontmatter above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/rename-to-cluster-mcp/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md).
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch (prefix per GOAL `kind`, from the profile's `branches`) and the
  profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`).
  **Artifact-deliverable R-IDs.** Some requirements are met by a *committed document* — a research
  audit, a protocol doc, an assessment — not by CLI-observable behaviour. Attach such an R-ID to the
  phase that produces and commits the artifact, and give that phase a content `verify:`
  (`test -f …`, a `grep -q` for the sections that must exist) rather than forcing a CLI drive.
  **Say so in the phase body**, because it changes who can grade it: `code-review` blinds its reviewer
  to all of `spec/`, so an R-ID whose evidence lives there is graded by the *orchestrator*, not the
  blind reviewer. Naming it in `TECH.md` is what lets the review skill route it correctly instead of
  reporting an unverifiable requirement.
- `depends_on`: phase ids that must be `done` first (a phase is actionable only when met).
- `parallel`: `true` only for genuinely independent, non-coupled work (docs, tests, isolated leaf
  modules). Any phase touching the profile's `coupled core` is always `false`.
- `hammerable`: `false` marks a correctness/security phase that scope-hammering must **never** cut.
- `hill`: `uphill` (still figuring it out) → `crest` (unknowns resolved) → `downhill` (just
  executing). A phase stuck `uphill` across builds is a raised hand → escalate to the human.
- `attempts`: durable failed-verify counter (absent = 0), bumped by `set_phase.py --phase P<n>
  --record-attempt` on every red verify gate; `next_phase.py` warns at ≥3 — the circuit breaker
  runs on this file, not on session memory.
- `verify`: the exact command that proves the phase (prefer driving the real CLI, not just tests —
  wrap CLI drives in the profile's `throwaway environment` helper, `<helper> sh -c "…"`, so they hit
  a disposable instance, never the developer's real data). A gate carrying `$( )` or quoting the
  calling shell would mangle is set with `set_phase.py --verify-file PATH`, not `--verify`.
- `review.cycle`: completed review passes, auto-incremented by every `set_phase.py --verdict …`;
  REVIEW.md's "Cycle {n}" mirrors it and the ≤3-cycle bound is graded against it. `--verdict approved`
  also clears `review.blocked_reason` unless one is passed explicitly.

## Conventions (apply to every phase)

- Commit conventions, code style, and load-bearing invariants come from the repo's `AGENTS.md` — it
  is the constitution. Walk the sections of its § Invariants that this change touches; that is the
  curated footgun checklist.
- One phase per `code-build` invocation by default; one atomic commit containing **both** the code and
  the `TECH.md` state change. The branch commit subject is code-build's (`$KB/skill/code-build.md` →
  Step 6), not restated here; branch commits are squashed away at `code-publish` per the profile's
  `landing`. Trailers follow the profile's `branch commits`.
- The last phase carries the standing last-phase items: the deferral ledger (`code-plan` Step 6.8),
  and every item the previous cycle's last phase carried for a project-level obligation (mpsearch's
  `## Times` quote, taken as `code-build` Step 4 says). A plan that drops one says why in `PLAN.md`.
- A PR body (when the profile's `landing` opens one) ends with an attribution naming the actual
  harness, model, and variant.
- A CLI/feature change obeys the profile's `same-commit rules` (§ Conventions in `AGENTS.md`): the
  help text, docs, or generated files it names change **in the same commit**.

**This cycle's own rules, every phase:**

- Every new file is born with `# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors` and
  `# SPDX-License-Identifier: MIT` (P5 rewrites the existing ones).
- Never a blind tree-wide substitution: `spec/` records (but their SPDX header lines, P5), `issues/`
  seed prose and `ROADMAP.md` history keep the old names (GOAL non-goal), and so do the JWT
  `ISSUER`/`AUDIENCE` (`'rcac-mcp'`, deferred), `tests/test_writes.py`'s `RCAC_MCP_EOF` test data,
  the `code rcac-mcp …` lines in AGENTS.md (the operator KB's repo key), the 0.1.4-era records in
  §9/§ Testing that name past deltas, and `INSTRUCTIONS.md` (Purdue content, not served, names no
  identifier of the server).
- The gates read the 0.1.4 tag (`baseline.sh`, `fixture_deltas.py`): `git fetch --tags` once if
  `git rev-parse 0.1.4` fails. They need PyPI on a cold uv cache.
- Each gate's modes split it for a 10 min command cap: run `phase`, then `mutants`, then
  `full-legacy`, then `full-modern` (P5: `docs`, `release`, `carry`, `mutants`, `full-legacy`,
  `full-modern`), and record each run's result; the phase is green only when every mode is.
- Seen red first, as code-build Step 4 says, on this phase's own checks (`phase` mode), not on `all`.
- Mutation cases keep their 0.1.4 plant, `why` and target functions, module paths remapped
  (`verify/compare.py`). A case that must change more is named in `verify/replants.txt` (id, phase,
  reason) in the same commit, and the commit body says why; the plan pre-lists the five it knows.

---

## Phase P1 — The workspace, the namespace and the command names
**Satisfies:** R1, R2 (the CLI's own name), R3, R8 (nothing moves out of the served surface), R9, R10,
R15 (for what P1 moves) · **Depends on:** —
**Goal:** the tree is a uv workspace of three members under a pure `cluster_mcp` namespace with a
compat root, `cluster-mcp` and `rcac-mcp` run from it, the git subdirectory install builds the
members from one commit, and every 0.1.4 test, mutation case and served tool is still there.

- [x] Move with `git mv` (history follows): `src/rcac_mcp/` → `packages/cluster-mcp/src/cluster_mcp/core/`;
      `tools/slurm.py` → `packages/cluster-mcp-slurm/src/cluster_mcp/slurm/tools.py`;
      `tools/rcac.py` → `packages/cluster-mcp-rcac/src/cluster_mcp/rcac/tools.py`; then move
      `slist` and `sfeatures` (decorated functions and docstrings byte-identical, their helpers with
      them) from the Slurm member's `tools.py` to the RCAC member's. New `slurm/__init__.py`,
      `rcac/__init__.py` (a module docstring only). No `cluster_mcp/__init__.py` anywhere.
- [x] Imports, most specific first and reviewed hunk by hunk (research/03 §5): `rcac_mcp.tools.slurm`
      → `cluster_mcp.slurm.tools`, `rcac_mcp.tools.rcac` → `cluster_mcp.rcac.tools`, the
      `from rcac_mcp.tools import slurm|rcac` forms by hand, then `rcac_mcp` → `cluster_mcp.core`
      (imports, `monkeypatch` targets, `__import__` strings in mutant anchors, logger names in
      stderr assertions). The core's `tools/__init__.py` import list imports the two member modules
      at its bottom in today's order (shell, filesystem, transfer, rcac, slurm, context). The storage
      resource's lazy import names `cluster_mcp.rcac.tools`.
- [x] `pyproject.toml` files per PLAN § 2 Layout: the root compat distribution `rcac-mcp` (workspace
      root, `dev` group, `required-version`, pytest options; script `rcac-mcp =
      "cluster_mcp.core:legacy_main"`; wheel `bypass-selection`; sdist `only-include` of
      `pyproject.toml` and `README.md`), and the three members (`only-include` + `sources = ["src"]`,
      the sdist furniture `exclude` list, a short `README.md` each, bare-name internal requirements
      with `{ workspace = true }` sources). Every distribution keeps version `0.1.4` (the release
      bumps them together). `uv lock`; `uv sync --locked`.
- [x] `cluster_mcp/core/__init__.py`: `__version__ = get_version('cluster-mcp')`; `__website__ =
      'https://github.com/PurdueRCAC/cluster-mcp'`; `__description__`, `APP_NAME = 'cluster-mcp'`,
      `APP_VERSION = f'cluster-mcp v{__version__} (…)'` and `APP_HELP`'s opening describe an MCP server
      for HPC clusters (no RCAC, no Purdue; the variable list is P2's). `legacy_main(argv=None)`:
      `legacy_warning('the rcac-mcp command', 'cluster-mcp')`, then `return main(argv)`. New
      `cluster_mcp/core/deprecation.py` with `WINDOW` and `legacy_warning` only (the resolver is P2's):
      one `log.warning` on stderr naming the old and new names and `WINDOW`, once per process per old
      name. `cluster_mcp/core/__main__.py` imports `main` from `cluster_mcp.core`.
- [x] `tests/mutants.py`: every `Case.file` namespace-relative (`core/…`, `slurm/tools.py`,
      `rcac/tools.py`; the `slist`/`sfeatures` cases follow them); `apply()` copies all three member
      portions under `src_root/cluster_mcp/` and writes no `__init__.py`; `CHILD`'s origin check
      requires `cluster_mcp.core`, `.slurm` and `.rcac` all under the copy; a `--self-check` control
      that a copy missing one portion is reported as a wrong origin. Re-plant only what moved; name
      each re-planted case and why in the commit body. New cases: `legacy-command-silent` (no
      warning; killed by `test_legacy_command_warns_then_runs_cluster_mcp`),
      `legacy-command-exit-swallowed` (`return 0`), `legacy-warning-to-stdout` (killed by
      `test_legacy_command_keeps_stdout_clean_on_stdio`). `tests/test_mutations.py`:
      `test_mutation_case_files_name_a_member`; the anchor test reads
      `src_root / 'cluster_mcp' / case.file`.
- [x] New `tests/test_packaging.py` (`unit`): `test_no_member_ships_a_namespace_init`,
      `test_namespace_check_catches_a_stray_init` (a planted tree), `test_each_member_holds_only_its_own_subpackage`,
      `test_every_distribution_carries_one_version` (all four `pyproject.toml`),
      `test_version_check_catches_drift`, `test_version_comes_from_the_installed_metadata`,
      `test_console_scripts_are_cluster_mcp_and_the_legacy_alias`.
- [x] `tests/test_cli.py` (`integration`, sandboxed): `test_legacy_command_warns_then_runs_cluster_mcp`
      (argv none/`--help`/`--version`/`--bogus`: same exit and stdout, stderr one warning line plus
      `cluster-mcp`'s), `test_legacy_command_keeps_stdout_clean_on_stdio`,
      `test_python_m_runs_the_entry_point`, `test_version_identifies_as_cluster_mcp`; the console
      script path becomes `cluster-mcp`, with `LEGACY_CLI` beside it.
- [x] `tests/test_hygiene.py`: the spec-id scan covers every portion of `cluster_mcp.__path__` and
      asserts there are three (`test_spec_id_scan_covers_every_member`); stack and import fences
      follow the new paths. `tests/test_registry.py`: the docs-absence rows become
      `cluster_mcp.core.docs`, `cluster_mcp.core.tools.docs` and a bare `rcac_mcp` row (a leftover
      `src/rcac_mcp/__pycache__` imports as a namespace package; research/03). `tests/test_sdist_hygiene.py`,
      `tests/test_audit.py`: synthetic names follow; the audit fixture gains the members if
      `bin/audit_lock.py` counts per project.
- [x] `bin/sdist_hygiene.py` docstring example; `bin/sandbox.sh` header and usage name `cluster-mcp`
      (the unset line is P2's).
- [x] Same commit (R15): `.github/workflows/ci.yml` (`bin/sandbox.sh uv run cluster-mcp --help`;
      `uv build --all-packages --no-sources -o dist/`), `.github/workflows/mutants.yml` (header, and
      its id listing works), `Dockerfile` (copy `pyproject.toml uv.lock README.md` and `packages/`,
      `uv pip install --system -e .`, `ENTRYPOINT ["cluster-mcp"]`), `compose.yml`
      (`container_name: cluster-mcp`), README's commands that drive the CLI. AGENTS.md: § Project
      (package, scripts, `python -m cluster_mcp.core`), § Commands, § Repository map (per member),
      § Packaging (the workspace, the compat root, the namespace rule, `--all-packages`), Profile
      (`verify`, `coupled core`), the release recipe (version source, bump, lockstep, diff rule, gate
      build, tag message, `post_verify` per PLAN § 2, caveats `no-sources`, `lock`,
      `install-probe`, `ci-mirror-no-index`; the recipe's `clean_paths` stays `[dist/]`),
      § Throwaway environment, the high-blast list (each
      moved file's new home added, every old entry kept), § Conventions (version source), and every
      `src/rcac_mcp` path and `rcac_mcp` module name elsewhere (§ Testing included), a new
      invariant line that no member ships `cluster_mcp/__init__.py`.
- **Verify:** `sh spec/rename-to-cluster-mcp/verify/p1.sh` (modes `phase`, `mutants`, `full-legacy`,
  `full-modern`).
- **Touches:** `pyproject.toml`, `uv.lock`, `packages/**`, `src/rcac_mcp/**` (moved), `tests/**`,
  `bin/sdist_hygiene.py`, `bin/sandbox.sh` (comments), `.github/workflows/*.yml`, `Dockerfile`,
  `compose.yml`, `README.md`, `AGENTS.md`.

## Phase P2 — CLUSTER_MCP_* variables, the legacy names honoured, the sandbox fails closed on both
**Satisfies:** R2 (`--help`'s variable list), R4, R5, R6, R15, R16 (the warnings' window) ·
**Depends on:** P1
**Goal:** the server reads `CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP` and
`CLUSTER_MCP_INSTRUCTIONS_BUDGET` through one resolver, honours each legacy name with a warning, and
the sandbox fails closed whichever SSH-host name the calling shell exports.

- [x] `deprecation.py`: `LEGACY_ENV` and `env_setting(name) -> tuple[str | None, str]` per PLAN § 2
      Environment (replacement wins when non-empty, its ignored legacy twin warned; legacy honoured
      with its warning; empty is unset; never stripped; returns the variable read). Read sites:
      rung 3 (same position and truthiness), `_create_executor` (message
      `SSH host required: use --ssh-host or set CLUSTER_MCP_SSH_HOST`), `_resolve_budget` (strips as
      today; the error names the variable read), `AuthExecutorMiddleware.__init__`, `site.py`'s
      `BudgetError` text. No module but `deprecation.py` names a legacy variable; no module but it
      reads a replacement from the environment.
- [x] `APP_HELP`'s variable list names the three replacements (the legacy names go to the README,
      P5), and its example host is generic: `--help` carries no RCAC or Purdue.
- [x] `bin/sandbox.sh`: `unset CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST CLUSTER_MCP_USER_MAP RCAC_USER_MAP
      JWT_SECRET \` (the OIDC line unchanged), and before it `unset UV_ENV_FILE` with
      `UV_NO_ENV_FILE=1` exported, a comment saying why (uv would otherwise load a variable back from
      an env file after the unset); protection 1 and 3 in the header name both names and the env file.
- [x] Tests: new `tests/test_env.py` (`unit`): `test_replacement_is_read`,
      `test_legacy_is_honoured_with_a_warning`, `test_replacement_wins_over_legacy`,
      `test_empty_counts_as_unset`, `test_whitespace_host_is_not_stripped`,
      `test_warning_fires_once_per_name`, `test_warning_names_replacement_and_window` (each
      parametrized over the three variables where it applies; a fixture resets the warn-once set).
      `tests/test_exec_mode.py`: `test_env_host_selects_ssh` over both names, the primary rows on
      the new names, legacy and both-set rows; `resolve`/`start` fixtures `delenv` both names.
      `tests/test_hygiene.py`: `test_sandbox_unsets_both_names` (the joined `unset` names all four);
      `BLANKED_ENV` and its test gain both new names. `tests/test_cli.py`, `tests/test_site_startup.py`,
      `tests/test_identity.py`: the messages and variables follow.
- [x] `tests/mutants.py`: re-plant the ladder cases on the resolver call; new `env-legacy-wins`,
      `env-legacy-ignored`, `env-replacement-ignored`, `env-no-warning`, `env-warning-to-stdout`,
      `env-host-stripped` (killed by `test_whitespace_host_is_not_stripped` and the ladder's
      whitespace row), `user-map-legacy-ignored`, `budget-legacy-ignored`.
- [x] Same commit (R15): AGENTS.md § Configuration (the replacements, the legacy names honoured with
      a warning through the window), § Commands' sandbox paragraph, §4 rung 3, §5's map variable,
      § Throwaway environment, § Conventions' sandbox rule, the high-blast list gains
      `packages/cluster-mcp/src/cluster_mcp/core/deprecation.py`; `SECURITY.md`'s variables;
      README's configuration lines (the deprecation section itself is P5's).
- **Verify:** `sh spec/rename-to-cluster-mcp/verify/p2.sh`.
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/{deprecation,__init__,middleware,site}.py`,
  `bin/sandbox.sh`, `tests/**`, `AGENTS.md`, `SECURITY.md`, `README.md`.

## Phase P3 — cluster:// resources with derived rcac:// aliases
**Satisfies:** R7, R8 (the resource delta), R15 · **Depends on:** P2
**Goal:** both resources are served as `cluster://`, each `rcac://` alias is derived from its target
and keeps its executor handling in every mode, and the last cycle's URI neighbourhood holds for
both schemes.

- [x] `resources.py`: the two entries on `cluster://`; the derived alias append (PLAN § 2 Resources)
      before the unchanged `OPEN_RESOURCES` line; no `executor` literal on an alias; the module
      docstring and `site.py`'s mention follow. `middleware.py` unchanged.
- [x] Tests: `tests/harness.py` gains hard-coded `CONTEXT_URIS`/`STORAGE_URIS` (never derived from
      the registry). Parametrize every read in `tests/test_context.py`, `tests/test_storage_resource.py`,
      `tests/test_protocol.py`, `tests/test_ssh_exec.py`, `tests/test_surface.py` over both schemes
      (ids `cluster`, `rcac`). `NOT_OPEN`/`NORMALISED` keep every `rcac://` shape and add the
      `cluster://` twins and cross-scheme shapes (`cluster://rcac://context`, `rcac+cluster://context`).
      `test_near_open_read_is_refused` is parametrized per served URI so each row keeps its timeout.
      New: `test_aliases_are_derived_from_their_targets` (exactly four URIs; each alias `is`-shares its
      target's handler and equals it but for `uri`), `test_open_resources_are_the_context_uris`,
      `test_alias_read_returns_target_content` (both resources, all three modes, both eras).
- [x] `tests/mutants.py`: re-text `read-hook-resolves-storage-only`, `storage-read-left-open`,
      `context-read-closed` to `cluster://`; `read-hook-rcac-scheme-only` keeps its scheme and gains
      the twin `read-hook-cluster-scheme-only`; each `let_through('rcac://…')` shape case gains a
      `cluster://` twin; `read-hook-open-by-equality` becomes a real case (killed by the `rcac` rows of
      `test_any_client_reads_the_context_in_delegate_mode`); new `alias-flag-hand-set-open`,
      `alias-flag-hand-set-closed`, `open-set-before-aliases`, `open-set-target-scheme-only`,
      `alias-handler-differs`, `alias-missing`. Every `why` fragment still names a shape of its scheme.
- [x] The fixture: `uv run python spec/rename-to-cluster-mcp/verify/fixture_deltas.py apply p3`; the
      commit body lists the delta (two `cluster://` keys, copies of the `rcac://` entries);
      `tests/test_surface.py`'s shape assertion, `resource-dropped` drift case and docstring follow.
- [x] Same commit (R15): AGENTS.md §1 (URIs), §7 (the storage resource), §8 (`cluster://`, the
      derived aliases, `OPEN_RESOURCES`), §9's fixture-delta record, § Testing's entries,
      § Architecture; `SECURITY.md`'s resource lines; README's resource line.
- **Verify:** `sh spec/rename-to-cluster-mcp/verify/p3.sh`.
- **Touches:** `packages/cluster-mcp/src/cluster_mcp/core/{resources,site}.py`, `tests/**`,
  `tests/fixtures/served_surface.json`, `AGENTS.md`, `SECURITY.md`, `README.md`.
- **Amendment (build, 2026-10-30).** `cluster_mcp/rcac/tools.py` is touched too: the docstring of
  `resolve_storage_paths()` (an undecorated helper, not served) named `rcac://storage`, which
  `checks.py uris-p3` allows only in `tests/`, `AGENTS.md`, `resources.py` and `server.py`.
  `storage-read-left-open` and `context-read-closed` plant on the storage entry's flag and on the
  open-set line, which name no URI, so their plants and `why` stay as 0.1.4 had them (no
  `replants.txt` line) and "re-text" lands as their targets: every row they name now runs under both
  schemes. "All three modes" in `test_alias_read_returns_target_content` is the three ways a server
  installs executors: none (bare), one shared executor (`local` and `ssh` mode), one per request
  from its token (`delegate`). The `cluster://` twins are generated from `mutants.CLUSTER_TWINS`
  (33, each `<id>-cluster`), and `read-hook-defaults-scheme`'s twin plants the `cluster://`
  default. `test_near_open_read_is_refused` rows are `<row>-<scheme>-<resource>`.

## Phase P4 — The instructions split and the server's name
**Satisfies:** R2 (the server name), R8 (the instructions delta), R11, R12, R15 · **Depends on:** P3
**Goal:** the served base is a generic core, the Slurm snippet and an RCAC-specific overlay, every
registered tool named once, and the server identifies as `cluster-mcp` in both eras.

- [x] `cluster_mcp/core/instructions.py` (`CORE_INSTRUCTIONS`), `cluster_mcp/slurm/instructions.py`
      (`SLURM_INSTRUCTIONS`), `cluster_mcp/rcac/instructions.py` (`RCAC_INSTRUCTIONS`, first line
      `RCAC-specific tools:`), import-free, texts from research/04 (each line keeps today's wording
      less "(RCAC)"). `server.py`: `SERVER_INSTRUCTIONS = '\n\n'.join((CORE_INSTRUCTIONS,
      SLURM_INSTRUCTIONS, RCAC_INSTRUCTIONS))`, the `instructions=compose(SERVER_INSTRUCTIONS, site,
      budget),` line verbatim, `FastMCP(name='cluster-mcp', …)`.
- [x] Tests: `tests/test_instructions.py`: `test_core_instructions_are_generic` (no `(?i)rcac|purdue`,
      no RCAC-member tool), `test_overlay_is_labelled_and_lists_the_rcac_member`,
      `test_slurm_snippet_lists_the_slurm_member`, `test_base_is_core_slurm_then_overlay`;
      `tests/test_protocol.py::test_server_identifies_as_cluster_mcp` (both eras: legacy
      `serverInfo.name`, modern `_meta` stamp). Mutants: `overlay-dropped`, `core-names-rcac-tool`,
      `server-name-rcac`.
- [x] The fixture: `fixture_deltas.py apply p4`; the commit body lists the deltas (instructions; the
      server name is not in the fixture and is pinned by the new test).
- [x] Same commit (R15): AGENTS.md §9 (the base is three texts; the delta record:
      `rename-to-cluster-mcp` changed `instructions` and added the `cluster://` resource keys),
      § Testing, the repository map's instructions modules; README's tool inventory regrouped Core /
      Slurm / RCAC-specific (and its `extra_args` paragraph moved out of the Slurm list).
- **Verify:** `sh spec/rename-to-cluster-mcp/verify/p4.sh`.
- **Touches:** `packages/*/src/cluster_mcp/*/instructions.py`, `packages/cluster-mcp/src/cluster_mcp/core/server.py`,
  `tests/**`, `tests/fixtures/served_surface.json`, `AGENTS.md`, `README.md`.
- **Amendment (build, 2026-10-30).** The texts are research/04's verbatim. Beyond the named tests,
  `test_instructions.py` gains `test_every_tool_belongs_to_a_member` (every registered tool comes
  from the core, the Slurm or the RCAC member, so no tool escapes the three listings) and
  `test_member_text_checks_catch_drift` (a control per way `core_violations`, `listing_violations`
  and `base_violations` must fire), and `test_protocol.py` gains `test_identity_check_catches_drift`
  (the same for `identity_violations`); the core test also requires the core to list exactly the
  core's tools. `test_server_identifies_as_cluster_mcp` runs one row per era (`[legacy]`,
  `[modern]`) whatever era the run selects, as `test_client_era_is_served` does; the modern row
  reads the `_meta` stamp on a `tools/list` result and the session identity drawn from the
  discover stamp, the legacy row the `InitializeResult` and the absence of a stamp. Mutation
  targets: `overlay-dropped` → `test_base_is_core_slurm_then_overlay`; `core-names-rcac-tool` →
  `test_core_instructions_are_generic`; `server-name-rcac` → both rows of
  `test_server_identifies_as_cluster_mcp`. No 0.1.4 case is re-planted (no `replants.txt` line).
  The base's text left `server.py`, a high-blast path, so the high-blast list gains the three
  `instructions.py` modules, with a line saying they hold text, not commands (code-build: the list
  only widens when code moves). README's inventory opens with one sentence naming the three groups.

## Phase P5 — Repository text, the release recipe on this head, the deferral ledger
**Satisfies:** R8 (cumulative), R13, R14, R15, R16 · **Depends on:** P4
**Goal:** the repository's text names the new project everywhere outside the records, the README
states the deprecations once, the release recipe's gate passes on this head, and every earlier
check holds.

- [x] SPDX (R14): every `SPDX-FileCopyrightText` header line in every tracked file, `spec/` records
      included, reads `SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors`; no
      `SPDX-License-Identifier` line changes. A header-only edit (the commit body says so).
- [x] URLs (R13): every repository URL outside `spec/` names `https://github.com/PurdueRCAC/cluster-mcp`;
      the README's install and client-config examples use the `#subdirectory=packages/cluster-mcp`
      form and `cluster-mcp`; title and opening describe the new project.
- [x] README `## Upgrading from rcac-mcp` (R16; draft in research/05): the three deprecations, their
      replacements, the window verbatim as `WINDOW` states it ("deprecated in 0.2.0, removed no
      earlier than 0.4.0"), that a new variable wins over its old twin, that the old install line
      keeps running `rcac-mcp` through the window (without quoting the old URL: R13). No legacy
      name anywhere else in the README.
- [x] The release recipe gains the caveat `repo-rename-first` (PLAN § 5), and its `pypi` caveat says
      that the internal requirements are bare names unregistered on PyPI, so only a uv install from
      git resolves them safely (the README's install note says the same); AGENTS.md § Direction drops
      the rename bullet (now true; § Project says it) and re-anchors the tools bullet to the members;
      the § Invariants preface no longer says the rename is in progress. `SECURITY.md`,
      `INSTRUCTIONS.md` (unchanged unless it names an identifier) and `compose.yml` comments checked.
- [x] Deferral ledger: walk every earlier phase body and commit body for deferral phrases (those
      `checks.py ledger` reads); each deferral has an `issues/` seed and a ROADMAP entry. This
      plan filed `issues/rename-leftover-identity-strings.md` (JWT issuer/audience, `serverInfo.version`,
      the favicon, the dev hostname) with its ROADMAP entry; any new deferral gets the same.
- [x] The release recipe's gate on this head (R15): `p5.sh release` runs its steps in order,
      the dependency audit included (network), plus the install probe.
- **Verify:** `sh spec/rename-to-cluster-mcp/verify/p5.sh` (modes `docs`, `release`, `carry`,
  `mutants`, `full-legacy`, `full-modern`). R14's evidence is the tree itself; the blind reviewer can
  grade it. The ledger's evidence (`issues/`, `ROADMAP.md`) is outside `spec/` too.
- **Touches:** every file with an SPDX header, `README.md`, `AGENTS.md`, `SECURITY.md`, `compose.yml`,
  `issues/`, `ROADMAP.md`.

### P5 amendment — review 1 remediation (2026-10-30)

Review 1 (`REVIEW.md`) found two LOW gaps, each routed as a property with a mutant sweep in both
eras: F1, nothing pins the deprecation window (R16), and F2, nothing pins the tools' annotations
(R8). P5 satisfies both R-IDs, so P5 is reopened rather than a phase added; it is the latest phase,
so its frozen gate needs no retune. The fix is pinning only: no `packages/*/src/` change, and no
pin exposed a defect (both reviewers found the behaviour correct). `verify/` stays frozen at the
plan commit; the class checkers are in `remediation/`.

- [x] **F1 — the deprecation window is one string.** Property: the window is "deprecated in 0.2.0,
      removed no earlier than 0.4.0", and every place a user reads it says exactly that: `WINDOW`,
      every warning naming it (the `rcac-mcp` command, each legacy variable honoured, each twin
      ignored), and README § Upgrading from rcac-mcp, which exists once and pairs each of the three
      deprecations with its replacement. The tests compare with the literal, `harness.DEPRECATION_WINDOW`,
      never with `WINDOW`: new `tests/test_deprecation_window.py` (`test_window_is_the_published_one`;
      `upgrading_violations` with `test_readme_states_each_deprecation_and_the_window` and eleven
      drift controls); `test_env.py::test_warning_names_replacement_and_window[<name>-honoured|ignored]`
      captures the window from each message and compares it; `test_cli.py`'s `legacy_violations` and
      `stdio_violations` do the same for the command's warning (`window_violations`), with
      `no-window` and `other-window` drift rows and a stdio window control.
- [x] **F2 — every tool's annotations are 0.1.4's.** Property: the served surface of every tool,
      annotations included (each hint's presence and value), equals 0.1.4's, which served none
      (0.1.4 and `3d010ec` register no annotations; `verify/baseline.sh` compared them live).
      `harness.served_surface` records `annotations` only for a tool served with them, each hint
      sent with its value (`exclude_unset`), so a tool without them keeps the fixture's shape and
      **the fixture does not change** (R8's delta list stays the three named deltas).
      `test_surface.py`'s `surface_violations` compares annotations hint by hint; annotations on one
      side only show as a tool entry gaining or losing the key. `test_surface_check_catches_annotation_drift`
      plants each way (added to every tool, to one, empty, removed, a hint flipped, dropped, added,
      nulled, all hints emptied), either side.
- [x] **Mutants** (`tests/mutants.py`). The runner gains `repo_edits`: a case may plant into
      `README.md` or the served-surface fixture (`REPO_FILES`), its child running in a copy of
      `tests/`, `bin/` and the top-level files; `test_mutations.py` applies those anchors too. New
      cases: `deprecation-window-altered`, `legacy-warning-omits-window`, `ignored-warning-omits-window`,
      `legacy-command-own-window`, `env-legacy-own-warning`, `env-ignored-own-warning`,
      `readme-window-altered`, `readme-upgrading-deleted`, `readme-command-row-dropped`,
      `readme-variables-row-dropped`, `readme-resources-row-dropped`, `readme-replacement-dropped`,
      `readme-replacements-swapped`; `annotations-on-every-tool`, `empty-annotations-on-every-tool`,
      `annotations-on-one-tool`, `annotations-removed`, and, planting the product and the fixture
      together (0.1.4 has no hint to flip or drop), `annotation-hint-flipped`,
      `annotation-hint-dropped`, `annotation-hint-added`. No existing case is retargeted.
- [x] `AGENTS.md`: § Configuration (the window is one string, pinned against the literal), § Testing
      (`test_deprecation_window.py`, `test_env.py`, `test_cli.py`, `test_surface.py`, the runner's
      repository plants), §9 (annotations in the pinned surface).
- [x] `issues/rename-leftover-identity-strings.md`: a dated note adding the request-state keys
      `rcac_user` and `rcac_local_user` (`middleware.py`, never served); no code change.
- [x] Class checkers: `remediation/F1-deprecation-window-pinned.py` and
      `remediation/F2-tool-annotations-pinned.py` (shared `remediation/sweep.py`). Each runs its
      pinning tests in both eras, then its sweep under `CLUSTER_MCP_TEST_ERA` unset and `modern`. The
      sweep is found by evaluating where each case's anchor sits: F1, the `WINDOW` assignment,
      `legacy_warning` and `ignored_warning`, and every call of either anywhere in the namespace, plus
      every `README.md` plant; F2, every `Tool.from_function` call in the namespace plus every fixture
      plant. Equivalent mutants are recorded in the checkers with their reasons.
- **Verify (amended):** the frozen `verify/p5.sh` (modes `docs`, `release`, `carry`, `mutants`,
  `full-legacy`, `full-modern`, each its own command under a 10-minute cap; `mutants` runs as one
  background command), then the two checkers. `full-legacy` and `full-modern` are the profile's
  `verify`. Run on this tree (2026-10-30): `docs` 13 s, `release` 634 s (audit clean over 84
  packages; 2541 passed, 14 skipped per era; 8 artifacts PASSED; sdist hygiene clean; probe ok),
  `carry` 36 s, `mutants` 1040 s (381 killed, 0 failed, three controls), `full-legacy` 304 s (2541
  passed, 14 skipped), `full-modern` red twice on the tracked flake
  `test_a_stalled_reconnect_is_abandoned_against_a_real_handshake` ("0 reconnect workers ran, not
  one"; passes alone, and in `release`'s modern pass on the same tree), green on the third
  identical-tree run (2541 passed, 14 skipped, 299 s); both reds recorded as attempts. F1 checker
  153 s (31 pins per era, 17/17 killed per era), F2 checker 38 s (28 pins per era, 8/8 killed per era).
- **Touches (amended):** `tests/harness.py`, `tests/test_deprecation_window.py`, `tests/test_env.py`,
  `tests/test_cli.py`, `tests/test_surface.py`, `tests/mutants.py`, `tests/test_mutations.py`,
  `AGENTS.md`, `issues/rename-leftover-identity-strings.md`, `spec/rename-to-cluster-mcp/remediation/`.

### P5 amendment — review 2 remediation (2026-10-30)

Review 2 (`REVIEW.md` § Review cycle 2) found three LOW gaps in the review-1 pins, routed as two
properties with mutant families in both eras: F3 and F4, README § Upgrading from rcac-mcp as a reader
sees it and the command's warning whole (R16; R3 through the warning), and F5, a tool's top-level
`title` (R8, ruled in by the foreman). P5 satisfies both R-IDs and is the latest phase, so it is
reopened again and its frozen gate needs no retune. Tests only: nothing under `packages/` changes,
and no pin exposed a product defect. `verify/` stays frozen; the checkers are in `remediation/`.

- [x] **F3 + F4 — the upgrade section as read, the command's warning whole.**
      `test_deprecation_window.py`'s `upgrading_violations` reads the README with every HTML comment
      removed (`rendered`; an unclosed one hides the rest). `table_pairs` lists every replacement
      each deprecated name is given, so a name paired twice (the same replacement or another, before
      or after the right row) fails whatever the row order, and a name outside the six fails.
      `version_violations`: every version the section names (`\d+(?:\.\d+)+\S*`, trailing
      punctuation dropped: a superset of the routing's three-part literal, so "0.3" fails too) is
      `0.2.0` or `0.4.0`, and the window appears as the whole phrase bounded at tokens (`BOUNDED`),
      so "0.4.0-alpha", "0.4.0.1", "un…" and "0.4.0 (0.3.0 for …)" fail. Fifteen new drift controls,
      and four read-the-same controls that must pass (a contradiction inside a comment, rows
      reordered, the window ending a sentence, the window rewrapped). `test_cli.py`'s
      `COMMAND_WARNING` matches the whole stderr line from its start (the padded level, the logger's
      name, the message); `WARNED` is the line as printed; drift rows `prefixed`, `before-the-level`,
      `suffixed`, and a prefixed stdio control.
- [x] **F5 — every tool's title is 0.1.4's.** The routing's premise that an unset title is absent
      on the wire does not hold: FastMCP 4.1.4, the stack 0.1.4 already ran on (its lock pins the
      same version), serves every tool that sets no title one derived from its name ("Run
      Command"). So `harness._tool_entry` records `title` whenever one is served, and
      `test_surface.py` accepts, only where the snapshot has none, exactly that derived title (a
      fifth `TOLERATED` kind, `derived-title`, the derivation written out as `derived_title`); a
      title gained other than it, a snapshot title lost or changed, or (in the baseline test) a tool
      served untitled fails. The fixture does not change. Seven title drift controls
      (`test_surface_check_catches_title_drift`) and two tolerated rows.
- [x] **Mutants** (`tests/mutants.py`), thirteen new cases: `readme-contradicting-row-before`,
      `readme-contradicting-row-after`, `readme-row-repeated`, `readme-removed-in-other-words`,
      `readme-kept-until-other-version`, `readme-window-suffixed`, `readme-window-extra-component`,
      `readme-window-parenthetical`, `readme-upgrading-commented`, `legacy-command-prefixed-warning`,
      `title-on-one-tool`, `title-on-every-tool`, `title-at-add-tool`. Red first: each planted into a
      throwaway detached worktree of `c057851` (its own tests), both eras, after a no-op control of
      the same command: twelve survived in both eras; `readme-contradicting-row-after` was already
      failed by the old check with another message (as the review found), so the runner reports it
      killed for the wrong reason. The same thirteen through the runner there, with its controls:
      the same verdicts. After the pins: all thirteen killed in both eras.
- [x] `AGENTS.md`: § Configuration (the section pairs each name with exactly one replacement, as
      read), § Testing (`test_deprecation_window.py`, `test_cli.py`, `test_surface.py`, the fifth
      tolerated kind), §9 (tool titles in the pinned surface).
- [x] Class checkers: `remediation/F3-F4-upgrading-section-as-read.py` and
      `remediation/F5-tool-title-pinned.py`, on the shared `remediation/sweep.py`. They supersede
      `F1-deprecation-window-pinned.py` and `F2-tool-annotations-pinned.py`, which stay as the
      record: those count their pins exactly (31, 28), and these pins add drift controls to the
      files they count, so both went red on the count alone (53 and 37 passed; every swept case
      still killed, 27/27 and 10/10 per era). The new checkers run the old ones' pins at the new
      counts and read the old ones' required cases and equivalents; F3-F4 sweeps F1's domain (the
      `WINDOW` assignment, every `legacy_warning` / `ignored_warning` call or definition, every
      `README.md` plant), F5 sweeps F2's widened by `add_tool` (every `Tool.from_function` or
      `add_tool` call, every fixture plant).
- **Verify (amended):** the frozen `verify/p5.sh` (its modes as before), then the two new checkers,
  which replace F1's and F2's in the gate. Run on this tree before this paragraph was written
  (2026-10-30), each mode its own command, one at a time: `docs` 13 s, `release` 673 s (audit clean;
  2585 passed, 14 skipped per era; 8 artifacts PASSED; sdist hygiene clean; probe ok), `carry` 36 s,
  `mutants` 1064 s (394 killed, 0 failed, three controls), `full-legacy` 305 s (2585 passed, 14
  skipped), `full-modern` 310 s (2585 passed, 14 skipped; the tracked reconnect flake did not
  occur). F3-F4 checker 202 s (53 pins per era, 27/27 killed per era), F5 checker 50 s (37 pins per
  era, 11/11 killed per era). `docs` re-run after this paragraph and the state change.
- **Touches (amended):** `tests/harness.py`, `tests/test_deprecation_window.py`, `tests/test_cli.py`,
  `tests/test_surface.py`, `tests/mutants.py`, `AGENTS.md`, `spec/rename-to-cluster-mcp/remediation/`.

### P5 amendment — review 3 remediation (2026-10-30)

Review 3 (`REVIEW.md` § Review cycle 3) found four LOW gaps in the README and command-warning pins
and reached the review bound; Geoffrey ruled a scoped fix taking the reviewer's prototype rules and
the F9 pin, verified by the foreman, with no fourth review, and accepted two residuals (§ Ruling at
the bound). P5 satisfies R8 and R16 (R3 through the command's warning) and is the latest phase, so
it is reopened a third time; its frozen gate needs no retune. Tests only: nothing under `packages/`
changes, and no pin exposed a product defect.

- [x] **F6 — every table-ish line is read, each name is named once.** `table_line_violations`:
      every line of the section holding a `|` is the header, the delimiter, or a two-cell row with
      code spans in both cells (plain, bold, escaped, `<code>`, three-cell and no-leading-pipe rows
      fail). With HTML tags, entities, backslash escapes and `*` removed (`plain`), each `RCAC_*`
      variable and `rcac://` URI is named once in the section, so a bullet or sentence mapping fails.
      **Deviation from the brief:** `rcac-mcp` is not counted. The section names the old project by
      it four times (heading, the rename sentence, its row, the compatibility sentence), so "exactly
      once" would need a README change outside this tests-only remediation; the reviewer's prototype
      also counted only the variables and URIs. A bullet or sentence pairing the command with another
      name stays uncaught, recorded as a residual in the checker and in `AGENTS.md`.
- [x] **F7 — no comment marker in the section.** The section is read from the README's source; it
      fails on any `<!--` or `-->`, wherever a reader would see one (a code span, a fenced block, a
      comment across paragraphs). `rendered()` stays only to ask whether a comment elsewhere hides
      the section's heading (it over-hides, so it can only make the check stricter); the README-wide
      window counts read the source with markup removed, comments included. The read-the-same control
      `hidden-comment` flips to a drift control (a comment in the section now fails, even one a reader
      would not see), and F3-F4's recorded equivalent `readme-contradiction-in-a-comment` becomes a
      killed case. Out-of-scope coupling fixed: `second-window` now plants before the section and
      `section-twice` just after it, and every drift control also runs on a README ending in an
      unclosed comment (`readme-unclosed-comment-at-the-end` rows); new read-the-same controls: the
      window emphasised, a comment before the section, an unclosed comment at the end.
- [x] **F8 — versions read with markup removed.** Versions and the window are matched in the section
      with `*` and `_` emphasis removed too; every version literal is `0.2.0` or `0.4.0`, and outside
      the window the only one is a single `0.2.0` ("removed in 0.2.0", "removed in 0.4.0" fail).
      Residuals accepted by the ruling, not chased: no version literal; a contradiction outside the
      section.
- [x] **F9 — one command warning.** `test_cli.py`'s `naming_violations`: in the four legacy drives
      and on the serving path (`stdio_violations`) exactly one stderr line names `rcac-mcp`, and it
      fully matches `COMMAND_WARNING` (`fullmatch`). Drift rows `second-warning` and
      `second-line-naming-the-command`, and four doubled-warning stdio controls.
- [x] `tests/test_surface.py`: `_Comparison.tool` no longer reports a changed title twice (the
      reviewer's out-of-scope note; `title()` already reports it).
- [x] **Mutants** (`tests/mutants.py`), 23 new cases: `readme-{plain,bold,escaped,html-code,three-cells,no-leading-pipe}-row-{before,after}`,
      `readme-bullet-mapping`, `readme-prose-mapping`, `readme-comment-in-code-spans`,
      `readme-comment-fenced`, `readme-comment-across-paragraphs`, `readme-version-escaped-dots`,
      `readme-version-entity-dots`, `readme-version-bold-component`, `readme-removed-in-the-rename`,
      `readme-contradiction-in-a-comment`, `legacy-command-second-warning-when-serving`. Red first:
      each planted into a throwaway detached worktree of `dd6dafa` with its own environment, after a
      no-op control of the same files in the same era (`test_deprecation_window.py` 32 passed,
      `test_cli.py` 35 passed, each era): all 23 survived in both eras; the serving-only plant was
      confirmed to land by a sandboxed `rcac-mcp -e local` printing both warnings. After the pins: all
      23 killed in both eras through the runner, each for its stated reason.
- [x] `AGENTS.md` § Configuration and § Testing state exactly what is pinned and what is not (the
      reviewer found the old text overstated: it said any contradicting row was caught).
- [x] Class checker `remediation/F6-F9-upgrading-source-and-one-warning.py`, on the shared
      `remediation/sweep.py`. It counts its own named tests (135 per era: each must be reported passed,
      and nothing collected may fail or skip), never a file's pass total, so later tests in the same
      files leave it green. It supersedes `F3-F4-upgrading-section-as-read.py`, which stays as the
      record (its 53-pass count over whole files no longer holds); it runs F3-F4's pins, reads its
      required cases and equivalents (less the one now killed), and sweeps its domain.
- **Verify (amended):** the frozen `verify/p5.sh` (its modes as before), then the F6-F9 checker,
  which replaces F3-F4's in the gate, then the F5 checker. Run on this tree before this paragraph
  was written (2026-10-30), each mode its own command, one at a time: `docs` 13 s; `release` **red at
  its step 2**, the dependency audit: it reports a known advisory published since the review-2 run
  against a dependency the lock pins, and `origin/develop` locks the same version, so the red is
  carried from the base, outside this cycle, and reported to the foreman (Step 1.3); the recipe stops
  there, so its build, hygiene and probe steps did not run in this mode. Recorded as an attempt
  (`attempts: 3`). `carry` 36 s; `mutants` 1115 s (417 killed, 0 failed, three controls);
  `full-legacy` 304 s (2690 passed, 14 skipped); `full-modern` 300 s (2690 passed, 14 skipped; the
  tracked reconnect flake did not occur). F6-F9 checker 306 s (135 named pins per era, 50/50 killed
  per era); F5 checker 50 s (37 pins per era, 11/11 killed per era). F3-F4's checker, superseded, is
  red on its count alone (135 passed, expected 53) and on its equivalent now a case; every case it
  sweeps is killed (50/50 per era). P5 stays `in_progress` on the red release step, for the
  foreman's ruling.
- **Touches (amended):** `tests/test_deprecation_window.py`, `tests/test_cli.py`,
  `tests/test_surface.py`, `tests/mutants.py`, `AGENTS.md`, `spec/rename-to-cluster-mcp/remediation/`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[{category}]` commit; stop and report.
