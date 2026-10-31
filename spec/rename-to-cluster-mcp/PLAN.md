# PLAN — Rename rcac-mcp to cluster-mcp

> **Status:** Draft for review · **Last updated:** 2026-10-29
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/). Every design element traces to a GOAL R-ID.

## 1. Summary

One move puts the tree into a uv workspace: `src/rcac_mcp` becomes the core member's
`cluster_mcp.core`, and the Slurm and Purdue tools move into a Slurm member and an RCAC member under
one pure PEP 420 `cluster_mcp` namespace. The root `pyproject.toml` becomes a code-less compat
distribution `rcac-mcp`, so the install line every existing user has keeps working and reaches the
deprecated `rcac-mcp` command. Four small slices follow on the moved tree: the `CLUSTER_MCP_*`
variables behind one resolver, with the sandbox unsetting both names; `cluster://` resources with
derived `rcac://` aliases; the instructions split into a generic core, a Slurm snippet and an
RCAC-specific overlay, with the server named `cluster-mcp`; and the repository's text (URLs, SPDX,
the README's deprecation section, the release recipe). Five phases, each gated against the 0.1.4
release so that nothing it had is lost.

## 2. Design

### Layout (R1, R9, R10)

```
pyproject.toml                    rcac-mcp 0.2.0: the workspace root and the compat distribution
README.md                         the user documentation (also the compat distribution's readme)
packages/cluster-mcp/             cluster-mcp: src/cluster_mcp/core/ (everything src/rcac_mcp had,
                                  less tools/slurm.py and tools/rcac.py), README.md, pyproject.toml
packages/cluster-mcp-slurm/       cluster-mcp-slurm: src/cluster_mcp/slurm/{__init__,tools,instructions}.py
packages/cluster-mcp-rcac/        cluster-mcp-rcac: src/cluster_mcp/rcac/{__init__,tools,instructions}.py
tests/  bin/  spec/  issues/      unchanged locations
```

- **No `cluster_mcp/__init__.py` anywhere** (pure namespace). Each member's wheel takes
  `only-include = ["src/cluster_mcp/<cap>"]`, `sources = ["src"]`; its sdist keeps the furniture
  `exclude` list as defence in depth. Each member has a short `README.md` of its own.
- **Dependencies:** core → `cluster-mcp-slurm`, `cluster-mcp-rcac`; each member → `cluster-mcp`;
  root → `cluster-mcp`. Every internal requirement is a bare name with a `{ workspace = true }`
  source, so a git install builds every member from the commit it was given. One version across the
  four distributions (0.2.0 is the release's call; the build keeps 0.1.4 until then), pinned by
  `tests/test_packaging.py`.
- **Root compat distribution** `rcac-mcp`: `dependencies = ["cluster-mcp"]`, `[project.scripts]
  rcac-mcp = "cluster_mcp.core:legacy_main"`, wheel `bypass-selection = true`, sdist
  `only-include = ["pyproject.toml", "README.md"]`; it also carries `[tool.uv.workspace] members =
  ["packages/*"]`, the `dev` group, `[tool.uv] required-version` and the pytest options. The core
  installs only `cluster-mcp` → `cluster_mcp.core:main`, so no two distributions claim one script.
- **Module moves.** `tools/slurm.py` → `cluster_mcp.slurm.tools` minus `slist`/`sfeatures`, which
  move with their docstrings byte-identical to `cluster_mcp.rcac.tools` (from `tools/rcac.py`), so
  the Purdue tools live in the RCAC member under their current names (R9). The core's
  `tools/__init__.py` keeps §7's import-list mechanism, importing `cluster_mcp.rcac.tools` and
  `cluster_mcp.slurm.tools` at its bottom in today's order (shell, filesystem, transfer, rcac, slurm,
  context), after `TOOL_REGISTRY` and `mcp_tool`. Members import only names defined before that
  list. `cluster_mcp/core/__main__.py` runs `main` for `python -m cluster_mcp.core`.
- `__version__ = get_version('cluster-mcp')`; `__website__ = 'https://github.com/PurdueRCAC/cluster-mcp'`.

### Names and the command (R2, R3)

`APP_NAME = 'cluster-mcp'`; `APP_VERSION = f'cluster-mcp v{__version__} (…)'`; `APP_HELP` and
`__description__` describe "an MCP server for HPC clusters" with a generic example host. The help's
variable list names the `CLUSTER_MCP_*` variables (P2). `legacy_main(argv=None)` beside `main`:
`legacy_warning('the rcac-mcp command', 'cluster-mcp')`, then `return main(argv)`; cmdkit passes
its program name explicitly, so the output is `cluster-mcp`'s byte for byte. R3's "nothing it prints
SHALL go to stdout" is the wrapper's own text: `--help` and `--version` print to stdout for both
commands alike, as cmdkit does. The FastMCP server name becomes `cluster-mcp` (`server.py`, P4).

### Environment (R4, R5, R6, R16)

New core module `cluster_mcp/core/deprecation.py` (joins the high-blast list: it resolves the SSH
host the §4 ladder reads). P1 creates it with `WINDOW` and `legacy_warning`, which the `rcac-mcp`
command needs; P2 adds the resolver:

- `WINDOW = 'deprecated in 0.2.0, removed no earlier than 0.4.0'`;
  `LEGACY_ENV = {'CLUSTER_MCP_SSH_HOST': 'RCAC_SSH_HOST', 'CLUSTER_MCP_USER_MAP': 'RCAC_USER_MAP',
  'CLUSTER_MCP_INSTRUCTIONS_BUDGET': 'RCAC_INSTRUCTIONS_BUDGET'}`.
- `legacy_warning(old, new)`: one `log.warning` on stderr naming `old`, `new` and `WINDOW`, once per
  process per `old`.
- `env_setting(name) -> tuple[str | None, str]`: the replacement when non-empty (and, if the legacy
  name is also non-empty, a warning that it is ignored); else the legacy value when non-empty, with
  its warning; else `None`. The variable read is returned so an error can name it. Empty means
  unset; nothing is stripped (a whitespace-only host is truthy today and must keep selecting
  `ssh`).
- Read sites: `_resolve_exec_mode` rung 3 (`self.ssh_host or env_setting('CLUSTER_MCP_SSH_HOST')[0]`,
  same position and truthiness), `_create_executor`, `_resolve_budget` (strips, as today, and names
  the variable it read), `AuthExecutorMiddleware.__init__` (user map), and the `BudgetError` text in
  `site.py`. The "SSH host required" message names `CLUSTER_MCP_SSH_HOST`. No other module reads
  these names.
- `bin/sandbox.sh` unsets `CLUSTER_MCP_SSH_HOST RCAC_SSH_HOST CLUSTER_MCP_USER_MAP RCAC_USER_MAP`
  with the rest, and also unsets `UV_ENV_FILE` and exports `UV_NO_ENV_FILE=1`, so `uv run` cannot
  load a variable back from an env file after the sandbox has unset it (the review showed it could,
  and the profile's verify, CI and every documented drive go through `uv run`; uv 0.12.17 has the
  variable). Its header and usage name `cluster-mcp`. `tests/conftest.py` `BLANKED_ENV` gains
  both new names; ladder and startup fixtures delete both names.

### Resources (R7, R8)

`resources.py` registers `cluster://context` (`executor: False`) and `cluster://storage`
(`executor: True`, its handler importing `resolve_storage_paths` from `cluster_mcp.rcac.tools`
inside the handler), then, before the unchanged `OPEN_RESOURCES` line:

```python
RESOURCE_REGISTRY += [{**entry, 'uri': entry['uri'].replace('cluster://', 'rcac://', 1)}
                      for entry in list(RESOURCE_REGISTRY)]
```

Each alias shares its target's handler, name, description and `executor` flag by construction, so
`OPEN_RESOURCES == {cluster://context, rcac://context}`, the delegate read hook's exact-string
membership (`middleware.py`, unchanged) lets both context URIs through and refuses both storage
URIs to an unmapped caller, and `rcac://storage` runs on the request's executor. Both schemes are
listed; the fixture gains a `cluster://` twin of each `rcac://` entry, which stays as it was.

### Instructions (R11, R12) and the served surface (R8)

Import-free leaf modules: `cluster_mcp/core/instructions.py` `CORE_INSTRUCTIONS` (generic: shell and
file tools, `cluster_context`, `cluster://context`), `cluster_mcp/slurm/instructions.py`
`SLURM_INSTRUCTIONS` (the Slurm job and status tools), `cluster_mcp/rcac/instructions.py`
`RCAC_INSTRUCTIONS` (opens `RCAC-specific tools:`; the ten RCAC tools; `cluster://storage`). Draft
texts are in [research/04](research/04-instructions-and-surface.md); each line keeps today's wording
less the "(RCAC)" suffixes. `server.py` keeps `SERVER_INSTRUCTIONS` as their `'\n\n'` join and the
`instructions=compose(SERVER_INSTRUCTIONS, site, budget),` line verbatim. Tool docstrings move
byte-identical. The fixture changes by script only (`verify/fixture_deltas.py`): `instructions`, and
the two `cluster://` resource keys.

### Repository text (R13–R16)

- Every repository URL outside `spec/` names `https://github.com/PurdueRCAC/cluster-mcp`; the
  README's install form becomes `uvx --from "git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp" cluster-mcp …`.
- Every `SPDX-FileCopyrightText` header line, `spec/` included, reads
  `SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors` ([digest](research/00-digest.md) #12);
  new files are born with it.
- README `## Upgrading from rcac-mcp` (draft in [research/05](research/05-repo-text-ci-release.md)):
  the three deprecations, their replacements, `WINDOW`'s two versions, and that the old install
  line still runs `rcac-mcp` through the window. It is the only place the README names a legacy name.
- Release recipe: `version.source: packages/cluster-mcp/pyproject.toml project.version`;
  `bump.files` the four `pyproject.toml` and `uv.lock`; `lockstep` the other three; `diff_rule` the
  four version lines and the four version entries in `uv.lock`; gate build
  `uv build --all-packages --no-sources -o dist/`; `tag.message: "cluster-mcp {v}"`;
  `post_verify` the subdirectory install running `cluster-mcp --help` and the root install running
  `rcac-mcp --help`; caveats `no-sources`, `lock`, `install-probe`, `ci-mirror-no-index` rewritten,
  and a new `repo-rename-first` (§5).
- Profile: `verify` drives `cluster-mcp`; `coupled core` names the files under
  `packages/cluster-mcp/src/cluster_mcp/core/`; the high-blast list gains each moved file's new home
  and `deprecation.py`, and keeps every old entry. CI's `gate` job, `Dockerfile` (copies the
  workspace, installs the root, `ENTRYPOINT ["cluster-mcp"]`) and `compose.yml`
  (`container_name: cluster-mcp`) change in the same commits as what they mirror.

### Requirement → design map

| R-ID | Design element(s) that satisfy it | Phase |
|------|-----------------------------------|-------|
| R1 | `packages/cluster-mcp` → `cluster_mcp.core`, script `cluster-mcp`, namespace with `only-include`, `__version__` from metadata, `__main__.py` | P1 |
| R2 | `APP_NAME`/`APP_VERSION`/`APP_HELP` (P1, P2's variable list); `FastMCP(name='cluster-mcp')` (P4) | P1, P2, P4 |
| R3 | root compat `rcac-mcp` script → `legacy_main` | P1 |
| R4 | `env_setting` at every read site | P2 |
| R5 | `env_setting`'s precedence and warnings, `WINDOW` | P2 |
| R6 | `bin/sandbox.sh` unsets four names; message names `CLUSTER_MCP_SSH_HOST` | P2 |
| R7 | derived alias entries before `OPEN_RESOURCES` | P3 |
| R8 | tools moved byte-identical; fixture deltas by script; baseline surface comparison | P1, P3, P4 |
| R9 | three members; Purdue tools incl. `slist`/`sfeatures` in `cluster_mcp.rcac.tools` | P1 |
| R10 | workspace sources; probe from a committed snapshot | P1 |
| R11 | `CORE_INSTRUCTIONS` | P4 |
| R12 | core + Slurm snippet + `RCAC-specific` overlay as the base | P4 |
| R13 | URLs, `__website__`, recipe | P1 (recipe), P5 |
| R14 | every header line | P5 |
| R15 | each phase's same-commit doc edits; P5's sweep, recipe gate on head | P1–P5 |
| R16 | README section; `WINDOW` in both warnings | P2, P5 |

## 3. Invariant gate (AGENTS.md constitution check)

Checked against § Invariants before research and again on this design. Sections touched:

- **High-blast list (§ Invariants).** Every listed file moves (all under `packages/cluster-mcp/src/cluster_mcp/core/`) and `bin/sandbox.sh` is edited: research ran (trigger 2). The list gains the new homes and `deprecation.py` and keeps every old entry ("the list only widens").
- **§1 isolation.** `context.py` moves unchanged. No middleware is added; the aliases are registry entries, so no URI is normalised before the read hook (§1's "no scheme normalisation").
- **§2, §3, §6 (executor protocol, `CommandResult`, auth).** Moves only. JWT `ISSUER`/`AUDIENCE` keep `'rcac-mcp'` (deferred, §5), so the signer/verifier triple stays matched.
- **§4 ladder.** Rung 3 reads the replacement, else the legacy name, with today's truthiness; order unchanged; no rung reaches `local` earlier. A whitespace-only host still selects `ssh` (pinned by a test and a mutant).
- **§5 delegate.** The user map is read once at middleware construction, by name through the resolver; the map check, claim precedence and `call_next` untouched.
- **§7 registration.** The import list stays the mechanism, now importing two member modules; `test_registry.py`'s `EXPECTED_TOOLS` pins the set. A member imports only what `tools/__init__.py` defines above its import list.
- **§8 resources.** Path, glob, ordering, header untouched. `OPEN_RESOURCES` stays derived and exact; each alias inherits its target's flag structurally. `cluster_context` and both context URIs run nothing in every mode.
- **§9 surface.** A deliberate instructions and resource-URI change by scripted hand-edit, listed in § Testing and the commit body; tool names, descriptions and schemas byte-identical (checked against 0.1.4's served surface, not only the fixture); README inventory and `SERVER_INSTRUCTIONS` move together.
- **§ Conventions.** Version single-sourced from the core's `pyproject.toml` with three lockstep copies (below); CI mirrors the gate; drives under `bin/sandbox.sh`; no spec ids in code or tests; no `Co-Authored-By`.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| A fourth distribution, `rcac-mcp`, at the root | Keeps the documented `uvx git+https://github.com/purduercac/rcac-mcp` line working through the window (GOAL Outcome; R3's command must be reachable from an existing config) | A virtual root breaks every existing client config at 0.2.0 ("does not provide any executables"); the GOAL promises the old command works through the window |
| The version lives in four `pyproject.toml` files, kept equal by a test and the recipe's `lockstep` (§ Conventions says "single-sourced") | Hatchling reads a version only inside each member; a shared file outside it is absent from the sdist | A dynamic shared version file fails the sdist build (research/01); the source of truth stays the core's file, the others are lockstep copies the recipe bumps together |
| The core imports its two members (core → member and member → core) | R8: a default install serves every tool, while R9 puts them in members; capability-extras replaces the import list | Members declaring no dependency on core ship metadata that hides a hard import and must be reversed next cycle |
| JWT issuer/audience, `serverInfo.version` and the favicon keep their names | Outside the R-IDs; the JWT rename invalidates every minted token | Deferred with a seed (`issues/rename-leftover-identity-strings.md`), not silently left |

Read against the R-IDs: no row changes what an R-ID SHALL do. R1's "no built wheel contains
`cluster_mcp/__init__.py`" holds for the root wheel too (it ships no code). R3 holds for the
`rcac-mcp` script wherever it is installed from (the root distribution); a bare
`#subdirectory=packages/cluster-mcp` install has no `rcac-mcp`, which no R-ID requires.

## 4. Rabbit holes (resolved)

- **Namespace packaging and the git subdirectory install** → only-include, a declared cycle, workspace sources; uv 0.12.17 builds the siblings from the same commit ([01](research/01-workspace-packaging.md)). The planner's prototype confirmed it with a probe that commits a snapshot of the tree and checks each member's `direct_url.json` commit id; a planted `cluster_mcp/__init__.py` turned it red.
- **The old install line** → a virtual root breaks it; the compat root keeps it ([05](research/05-repo-text-ci-release.md), [digest](research/00-digest.md) #1); prototyped.
- **Aliases against the exact-string read hook** → derived registry entries; middleware untouched; rewrite and transform options rejected ([02](research/02-deprecation-shims.md)).
- **Carrying the last cycle's URI tests and mutants** → parametrize over both schemes from hard-coded URI sets (never derived from the registry), keep the `rcac://` near-open shapes (31 `why` fragments quote them) and add `cluster://` twins, split the near-open read per served URI (its read count doubles), re-plant the scheme-specific cases with twins, and make `read-hook-open-by-equality` a real case now that the open set has two URIs ([02](research/02-deprecation-shims.md), [03](research/03-tests-and-mutants.md)).
- **Mutation runner under PEP 420** → case files namespace-relative; copy all three portions; origin check over all three; a self-check control for a missing portion ([03](research/03-tests-and-mutants.md)).
- **Instructions budget** → base +41 units, headroom 126 under the 1,500 cap; no live test pins the number ([04](research/04-instructions-and-surface.md)).
- **Adversarial design review** (trigger 3): ran on this PLAN, the GOAL, the drafted gates and the prototype; findings and what changed are in § 4a.

### 4a. Adversarial review

A fresh reviewer read the GOAL, this design and the drafted gates, and attacked the prototype. It
found 4 HIGH, 6 MEDIUM and 4 LOW problems; each changed the plan:

- **H1** `surface.py` dumped tools by field name, so under MCP SDK 2 the schemas were missing on both
  sides and compared equal. Now dumped by wire name (`by_alias`), any missing field fails the run,
  and P1/P2 also check that the fixture is untouched (`fixture_deltas.py check p1`).
- **H2** `bin/sandbox.sh` could be bypassed through `UV_ENV_FILE`: `uv run` reloaded the host from an
  env file after the unset (demonstrated, exit 5 at the connect step). The sandbox now turns env files
  off (§ 2 Environment), and `failclosed.sh` drives `uv run --frozen` as well as the venv binary,
  adds an env-file row, and checks the sandboxed environment carries none of the names.
- **H3** nothing pinned which member registers which tool (R9). New `members.py` pins the three
  sets, from P1 on; `instructions.py` uses the same sets.
- **H4** nothing read the `Dockerfile` or `compose.yml` (R15). New `checks.py container`: the
  entry point, every `COPY` source tracked, `packages/` copied, `container_name`.
- **M1** the `python -m` probe compared only `--help` stdout. It now compares exit status, stdout and
  stderr for `--help`, `--version` and `--bogus`.
- **M2** P5 ran its own copy of the release gate. `recipe_gate.sh` now reads `release.gate` from
  AGENTS.md and runs it verbatim, honouring `clean_paths`.
- **M3** the URL check flagged seed prose. It now matches URL forms only, outside `spec/` and
  `issues/`; the README's deprecation section still may not quote the old URL (R13).
- **M4** an `env` control planted into a comment. Re-anchored on the `unset` line.
- **M5** mutation cases were compared by id only. `compare.py` now requires each 0.1.4 case's file
  (as moved), plant and `why` (module path remapped) and target functions unchanged, unless
  `verify/replants.txt` names the case with a phase and a reason; a builder who must re-plant
  another case adds its line in the same commit and the commit body.
- **M6** nothing checked the window. The command warning, the budget warning and the README section
  must each carry `WINDOW` verbatim.
- **L1** `checks.py env` now also requires `BLANKED_ENV` to blank both names and the sandbox's
  env-file lines; `failclosed.sh` checks the sandboxed environment. **L2** P1 lands `WINDOW` and
  `legacy_warning` (the probe and the wheel scan expect them). **L3** dependency confusion: § 5.
  **L4** resource titles and annotations join the surface comparison; the README install-line rule
  now requires the subdirectory form and finds a stray `rcac-mcp` drive line by line.

What held: the install probe (commit ids per member, a later-commit marker, a fresh HOME per run so
no cache entry is reused across content) and the alias design (the read hook gates only on exact
membership in the derived open set; the shared middleware installs an executor for every read).

## 5. Risks & open questions

- **Release order (for 0.2.0, not this cycle).** `post_verify` and the README point at `PurdueRCAC/cluster-mcp`, which exists only after the GitHub rename. At 0.2.0 the rename must happen before `post_verify` runs, and a release cut from `develop` after this cycle lands and before the rename fails `post_verify`. Recorded as the recipe caveat `repo-rename-first`.
- **For sign-off: the compat root.** The design keeps the old install line working by shipping a code-less `rcac-mcp` distribution through the window, removed with the other legacy names no earlier than 0.4.0. The alternative is a virtual root and a README note that the old line stops working at 0.2.0, which contradicts the GOAL's Outcome; it would also need R16 reworded.
- **For sign-off: SPDX in `spec/`.** Headers in the 29 retained `spec/` scripts are rewritten with the rest (R14 has no carve-out; the history non-goal covers quoted names, not headers).
- **Duplicate resource names in `resources/list`.** Each alias carries its target's `name` (R8 allows no description or name delta). FastMCP lists and reads both; real clients are untested against duplicate names.
- **Network.** `probe.sh` and `baseline.sh` need PyPI on a cold uv cache; the profile's `verify` stays offline-capable. P5's `release` mode runs the dependency audit, which needs the network by design.
- **Gate length.** P1 and P5 run every mutation case (6–10 min) and the full verify (about 8 min); each gate offers modes so a caller with a 10 min command cap can run it in parts.
- **pip** cannot install the members from git (workspace sources are uv-only); the README's install lines stay `uv`/`uvx`.
- **Dependency confusion.** Every internal requirement is a bare name, and none of `cluster-mcp`, `cluster-mcp-slurm`, `cluster-mcp-rcac` is registered on PyPI. A pip install, or any install with sources disabled, resolves them from the index, where anyone could register them. P5 states it in the recipe's `pypi` caveat and the README's install note; registering the names is the 0.2.0 release's PyPI decision (a GOAL non-goal here).
- **No install check before the tag.** The recipe's gate builds and checks artifacts but never installs from git; `post_verify` does, after the push. The cycle's own gate runs `probe.sh` on every phase from P1, so the head is probed; adding a probe step to the recipe is a release-process change this cycle does not make.

## 6. Verification strategy

Each phase has a frozen gate under [`verify/`](verify/) (`p1.sh` … `p5.sh`, modes `phase`, `mutants`,
`full`, `all`; P5 `docs`, `release`, `carry`), built on drives that hold against the 0.1.4 tag:

- `checks.py`: static checks (layout, names, URLs, SPDX, CI mirror, profile and recipe, README,
  ledger, AGENTS.md per phase), each with planted controls (`checks.py controls`).
- `probe.sh` (R1, R3, R10): the tree committed to a throwaway repository; the subdirectory install
  builds all three members from that commit (each `direct_url.json` commit id; a later commit's
  marker absent; imports from site-packages; no `cluster_mcp.__file__`); `python -m
  cluster_mcp.core --help` equals `cluster-mcp --help`; the root install's `rcac-mcp --help` equals
  it too, plus the warning.
- `legacy_cli.sh` (R2, R3, R5): both commands under the sandbox for four argvs: same exit, same
  stdout, `rcac-mcp`'s stderr exactly one warning line plus `cluster-mcp`'s; no RCAC or Purdue in
  `--help`/`--version`; a stdio session whose stdout is only JSON-RPC.
- `failclosed.sh` (R6): each SSH-host variable, and both, exported in the calling shell, and a uv
  env file carrying both; both commands bare under the sandbox, by the venv binary and by
  `uv run --frozen`, exit 2 with "SSH host required" naming `CLUSTER_MCP_SSH_HOST`; seen-red
  controls with the host set inside; the sandboxed environment carries none of the four names.
- `members.py` (R9): each tool is registered by the member that owns it, against pinned sets.
- `recipe_gate.sh` (R15): the release recipe's gate, read from AGENTS.md, run verbatim.
- `baseline.sh` + `compare.py` + `surface.py` (R8, and the regression net): from the 0.1.4 tag in its
  own environment and from this tree, every 0.1.4 test function keeps at least its id count, every
  0.1.4 mutation case survives with its plant, `why` and target functions (module paths remapped;
  `replants.txt` names the exceptions), the tools are served byte-for-byte alike, schemas included, resources are
  0.1.4's (P1) then 0.1.4's plus a `cluster://` twin of each (P3 on), the server name `cluster-mcp`
  (P4 on).
- `fixture_deltas.py` (R8): the fixture differs from 0.1.4's only by the named deltas, each exactly.
- `instructions.py` (R11, R12): core/Slurm/overlay composition and membership, read from the members
  themselves.
- Named new tests in both eras, every mutation case touching the phase's files plus the phase's new
  cases, and the profile's verify.

Dry-run on the prototype (a detached worktree with the P1 skeleton, P2's resolver and sandbox, P3's
aliases): `checks.py source` and `container` with their controls, the build with the wheel scan,
twine and sdist hygiene, `probe.sh`, `failclosed.sh` (after the env-file hardening),
`legacy_cli.sh p1`/`p2`, `baseline.sh p1`/`p3` and `fixture_deltas.py` went green where the
prototype carried the change, and red on a plant for each (a stray namespace `__init__.py`, a
sandbox that forgets the new name, an env file carrying the host, help still naming RCAC, a dropped
test, a reworded tool, a changed resource description, unmoved mutation-case files, `slist` left in
the Slurm member, the unsplit instructions). The suite-level parts (named test ids, mutation runs)
need the builder's tests and run first in build.
