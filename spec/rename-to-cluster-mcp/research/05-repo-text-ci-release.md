# 05 — Repository text, CI, release (R13–R16)

## Recommendations

**0. Blocking for packaging (not this brief's call, but it decides R3/R16).** With a *virtual* workspace
root, the only documented install line (`README.md:15`, `uvx git+https://github.com/purduercac/rcac-mcp`)
breaks at 0.2.0: uv falls back to a legacy build of the root and prints ``Package `packages` does not
provide any executables`` (prototyped on uv 0.13.6, scratch). Every existing user's config then fails
outright, and the `rcac-mcp` alias never reaches them. A *non-virtual* root that is a thin compat
distribution `rcac-mcp` (depends on `cluster-mcp` via `{ workspace = true }`, exposes `rcac-mcp`) makes
the old line run `rcac-mcp` from the same commit (prototyped: works; `#subdirectory=packages/cluster-mcp`
form also works). Cost: a fourth distribution in lockstep, and the root sdist ships the whole repo unless
the existing `[tool.hatch.build.targets.sdist] exclude` stays (it then stays load-bearing, and
`sdist_hygiene.py` catches a miss). Recommend the compat root. Otherwise R16 must say the old install
line stops working at 0.2.0.

**1. SPDX (R14): rewrite all 93 header lines, spec/ included, in a header-only phase that runs first.**
The inventory has 93 `# SPDX-FileCopyrightText:` lines in 93 files, in two forms only. `2025 Purdue University`
appears 21 times (19 in `src/rcac_mcp/`, plus `tests/conftest.py` and `tests/test_cli.py`). `2026 Purdue University`
appears 72 times: 43 outside spec/ and 29 in spec/, the old cycles' verify, remediation and prototype scripts. `issues/` has no
header, only prose. All 93 `SPDX-License-Identifier` lines are `MIT`. Headerless tracked files are the
`*.md` docs, Dockerfile, compose.yml, nginx-dev.conf, pyproject.toml, .gitignore, uv.lock, the fixture
JSON and the favicon. Nothing enforces REUSE, so none of them needs a header.
R14 has no spec/ carve-out (R13 has one). The GOAL's 93 count includes spec/'s 29. The non-goal covers
records "that quote the old names", and a copyright header is file metadata, not a quotation. A
mixed tree would also need an exception list. Every new file (members' `.py`, verify scripts) is born
with the new header. Check:
```
git grep -nE '^# SPDX-FileCopyrightText:' | grep -v ': 2026 Purdue RCAC and Contributors$'      # empty
git grep -hE '^# SPDX-License-Identifier:' | sort | uniq -c                                       # only MIT, count = header count
git grep -c '^# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors$' | wc -l              # >= 93 files (93 today, 29 in spec/; + new files)
git ls-files '*.py' '*.sh' '*.yml' ':!spec/' | while read f; do grep -q '^# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors$' "$f" || print -r -- "$f"; done   # empty
```
The `^# ` anchor skips the prose mentions in `GOAL.md:36,123-124,170-171` and `issues/rename-to-cluster-mcp.md:81`.
If the planner reads the non-goal as covering spec/, add `-- ':!spec/'` to line 1 and state the 29
exceptions in the commit body. Either way, confirm it with the human at plan time: one line.

**2. URLs (R13): five sites outside spec/, all `purduercac/rcac-mcp` → `PurdueRCAC/cluster-mcp`.**
They are README.md:15, `__init__.py:34` (`__website__`'s successor in `cluster_mcp.core`), and AGENTS.md:1074 (§ Packaging),
1179 (`post_verify`) and 1190 (`ci-mirror-no-index`). Compose, Dockerfile, nginx, SECURITY and ROADMAP
carry no repository URL. The `mcp.rcac.dev` dev hostname (compose.yml:20, nginx-dev.conf:16,19,
README:127-135) is not a repository URL. Leave it, or change all four places together. Seed prose
stays as written: `issues/rename-to-cluster-mcp.md:48` already says `purduercac/cluster-mcp`, and `:77`
is prose, not a URL. Check:
```
git grep -niE 'github\.com[/:]purduercac/rcac-mcp' -- ':!spec/'                                  # empty
git grep -niE 'github\.com/purduercac/' -- ':!spec/' ':!issues/' | grep -v 'github\.com/PurdueRCAC/cluster-mcp'   # empty (exact case)
```

**3. Release recipe** (virtual root shown; with the compat root add `rcac-mcp`/root `pyproject.toml` as a fourth lockstep member):
```yaml
version:  { source: packages/cluster-mcp/pyproject.toml project.version, … unchanged }
bump:
  lock: uv lock
  lockstep:
    - { cmd: "uv version --package cluster-mcp-slurm {v} --no-sync", files: [packages/cluster-mcp-slurm/pyproject.toml, uv.lock] }
    - { cmd: "uv version --package cluster-mcp-rcac {v} --no-sync",  files: [packages/cluster-mcp-rcac/pyproject.toml, uv.lock] }
  files: [packages/cluster-mcp/pyproject.toml, packages/cluster-mcp-slurm/pyproject.toml, packages/cluster-mcp-rcac/pyproject.toml, uv.lock]
  diff_rule: only project.version in the three member pyproject.toml files and the cluster-mcp, cluster-mcp-slurm and cluster-mcp-rcac version entries in uv.lock change
gate: [uv lock --check, uv run python bin/audit_lock.py, uv run pytest -q, CLUSTER_MCP_TEST_ERA=modern uv run pytest -q,
       uv build --all-packages --no-sources -o dist/, uvx twine check --strict dist/*, uv run python bin/sdist_hygiene.py dist/]
tag: { message: "cluster-mcp {v}" }
post_verify:
  - bin/sandbox.sh uvx --from 'git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp' cluster-mcp --help
  - bin/sandbox.sh uvx --from 'git+https://github.com/PurdueRCAC/cluster-mcp@{v}#subdirectory=packages/cluster-mcp' rcac-mcp --help
```
- `uv version --package X {v} --no-sync` relocks, so it runs correctly *after* `bump.lock`, as the release
  skill orders it. `--frozen` would leave uv.lock stale.
- Plain `uv build -o dist/` **fails** at a virtual root and leaves a junk `packages-0.0.0.tar.gz`/
  `unknown-0.0.0` wheel in `dist/`. `--all-packages` builds all six artifacts on uv 0.12.17 and 0.13.6.
  `twine check --strict` and `sdist_hygiene.py` (it globs every `*.tar.gz`) pass over all of them as they are.
- `no-sources` caveat: the caveat's own trigger has fired (workspace sources now exist), so add
  `--no-sources`. It only affects build-dependency resolution (hatchling from the index), and the output
  was identical in the prototype. Rewrite the caveat to say this.
- uv **drops `==` pins on workspace members from uv.lock**, so `uv lock --check` cannot catch a member
  version drift. Add a unit test that the member pyprojects carry one version, which keeps the gate list
  unchanged. Pin internal deps loosely or not at all. Exact pins would put dependency lines in the bump
  diff, and `diff_rule` must then say so.
- Caveats: edit `lock` ("besides the member pyproject.toml files and uv.lock"), `install-probe` (subdirectory form)
  and `ci-mirror-no-index` (URL). Add:
  ```
  repo-rename-first: >-
    post_verify installs from PurdueRCAC/cluster-mcp, which resolves only after the GitHub repository is
    renamed from rcac-mcp (a separate, human-approved action). At 0.2.0 the rename happens before
    post_verify; a release cut from develop after this cycle lands and before the rename fails post_verify.
  ```
- "Gate passes on the cycle's head" (R15): the profile's `ci` key already requires a green push run of
  the head commit before landing, and that run is every gate step including the networked audit. That
  run is the proof. Review re-runs the offline subset (`uv lock --check`, both suites, build/twine/
  hygiene into a fresh `dist/`; uv's cache supplies hatchling and twine). The audit stays network-only
  by design (caveat `audit`).

**4. CI / container.**
- `ci.yml`: change two steps. `bin/sandbox.sh uv run cluster-mcp --help` mirrors verify, and the build
  step becomes `uv build --all-packages --no-sources -o dist/`. Both land in the same commit as the
  profile/recipe edit (§ Conventions). `uv sync --locked` at a virtual root installs every member on
  0.12.17 (checked). Verify keeps one CLI drive. The suite proves the alias.
- `mutants.yml`: header only. Risk: `tests/mutants.py:10,38,55` copies the imported `rcac_mcp` package
  and checks `__file__`. A PEP 420 `cluster_mcp` has no `__file__`, so it must copy
  `cluster_mcp.core` (+ the RCAC member for the `:224` case).
- `Dockerfile`: `COPY pyproject.toml uv.lock README.md ./` + `COPY packages/ packages/`, then either
  `uv sync --locked --no-dev --no-editable` with `ENV PATH=/app/.venv/bin:$PATH` (lock-faithful), or
  `uv pip install --system ./packages/cluster-mcp` (honours workspace sources, as checked, but ignores
  the lock, as today). `ENTRYPOINT ["cluster-mcp"]`. Nothing builds it in CI.
- `compose.yml:17` `container_name: cluster-mcp`. The service name `mcp` stays (nginx `proxy_pass http://mcp:8000`).

**5. README (R16).** Put one `## Upgrading from rcac-mcp` section between Quick Start's subsections
and `## Execution Modes` (before line 66). The Quick Start example becomes
`"cluster": {"command": "uvx", "args": ["--from", "git+https://github.com/PurdueRCAC/cluster-mcp#subdirectory=packages/cluster-mcp", "cluster-mcp", "--ssh-host", …]}`.
Other changes: `:24` `CLUSTER_MCP_SSH_HOST`, `:56` `cluster://context`, `:60` `CLUSTER_MCP_INSTRUCTIONS_BUDGET`,
and `:103,110,113,187` `cluster-mcp`. The `# RCAC MCP Server` title and line 3 follow R2/pyproject `description`.
```
## Upgrading from rcac-mcp

In 0.2.0 the server was renamed from `rcac-mcp` to `cluster-mcp`. The old names are deprecated in
0.2.0 and will be removed no earlier than 0.4.0. Until then they keep working:

| Deprecated | Replacement |
|---|---|
| the `rcac-mcp` command | `cluster-mcp` |
| `RCAC_SSH_HOST`, `RCAC_USER_MAP`, `RCAC_INSTRUCTIONS_BUDGET` | `CLUSTER_MCP_SSH_HOST`, `CLUSTER_MCP_USER_MAP`, `CLUSTER_MCP_INSTRUCTIONS_BUDGET` |
| the `rcac://context` and `rcac://storage` resources | `cluster://context` and `cluster://storage` |

The command and each old variable print a warning on stderr naming the replacement; when an old and
a new variable are both set, the new one wins. An `rcac://` URI returns the same content as its
`cluster://` replacement. Update your MCP client configuration to the Quick Start form above.
```
Do not claim a warning for URI reads: R7 asks for none.

## Same-commit doc map (R15), by the code change each passage describes

AGENTS.md sections and their sizes: Project 15–49 (35 lines), Direction 50–67 (18), Commands 83–122 (40),
Repo map 123–171 (49), Architecture 172–202, Configuration 203–218 (16), Testing 219–1051 (~830),
Packaging 1052–1080 (29), Working 1081–1110, Profile 1115–1133, Recipe 1134–1227 (94), Throwaway 1228–1244,
Invariants 1286–1898 (high-blast 1298–1318), Conventions 1899–1949 (51).

| Change | Passages |
|---|---|
| Package/module move | AGENTS 19–21, 59–61, Repo map 125–162 (the whole table is rewritten per member; add `packages/` to the repo-level paths), 429, 558, 561, 924, 1022–1026, 1040–1042, 1054, 1063–1067, 1101–1106, Profile `coupled core` 1128 → `packages/cluster-mcp/src/cluster_mcp/core/{context,middleware,auth,token,server}.py, executor/*`, high-blast 1302–1312 (append the same ten files under `packages/cluster-mcp/src/cluster_mcp/core/`, keep the old ones; consider adding the new legacy-env resolver, which picks the SSH host), 1901–1903 (version source); Dockerfile 9–13; ci.yml build step; recipe version/bump/diff/gate |
| CLI rename + alias | AGENTS 20, 89–100, 118–119, 841, verify 1126, 1162, 1179, 1660, 1935, preface 1294; README 103–113, 187; SECURITY 23, 37, 40, 54, 66, 81, 103, 125, 212–219 (sudoers example user), 102/106 (`/etc/rcac-mcp/users.map`); Dockerfile 16; compose 17; ci.yml verify step; sandbox.sh comments 16–18, 29–30 |
| Env vars | AGENTS 118, 209–214, 548, 1242, 1655, 1688, 1930; README 24, 60; SECURITY 39, 102; sandbox.sh 68 (code) |
| URIs | AGENTS 138, 149, 191, 197, 338, 385, 399, 406, 618, 835, 1416, 1435, 1755, 1769–1771, 1838, 1846, 1849, 1859, 1863 (1896 records a past delta: keep); README 56; SECURITY 170, 173 |
| Instructions split | AGENTS 133 (server.py row), §9 1868–1898, Testing's 5 `SERVER_INSTRUCTIONS` lines, 1078; README "Available Tools" 143–181 (mirror the overlay label). `INSTRUCTIONS.md` names no package, command, variable or URI, so it needs no change. Do not move it: `tests/test_instructions.py:100` reads it at the root |
| URLs | §2 above |
| SPDX | header lines only; no doc describes them |

**§ Direction** needs: delete the rename bullet (56), since it is now true, and move the fact into
§ Project 19–21. Re-anchor the tools bullet (59–61) to the Slurm/RCAC members. The remaining bullets
(extras, any cluster, agents.d) keep "Nothing in this section is true yet" honest. The Invariants
preface (1293–1296) changes from "mid-generalization from rcac-mcp" to "the rename landed in 0.2.0; extras
continue". The PEP 420 rule (no `cluster_mcp/__init__.py`) and the deprecation window are new
contracts, so they get their own § Invariants/Conventions entry in the commit that lands them.

## Risks

- **Out of R-IDs, and must not be swept by a blind replace:** JWT `ISSUER`/`AUDIENCE = 'rcac-mcp'`
  (`token.py:22-23`, AGENTS 1015, SECURITY 243–244). Renaming them invalidates every issued token. The
  `code rcac-mcp …` lines (AGENTS 1084, 1093, 1099, 1269) are the operator KB's repo key and change only
  with the KB.
- Seeds `issues/{annotation-check,generalize-storage-discovery,site-file-size-cap}.md` cite
  `src/rcac_mcp/…` paths. They stay as written (non-goal) and go stale.
- No `cluster-mcp*` or `rcac-mcp` project exists on PyPI (checked 2026-10-29). A non-uv install of the core
  wheel would resolve members from the index, where anyone could register the names (non-goal, but
  note it in the `pypi` caveat).
- A stale `dist/` artifact gets checked by twine and hygiene, so build into a fresh directory.
