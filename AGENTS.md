# AGENTS.md

Guidance for coding agents (Claude Code and others) working in this repository.
`CLAUDE.md` is a symlink to this file — edit `AGENTS.md`, never a separate copy. The factory's
method and skills live in the operator's KB, not in this repository; this file carries the repo's
side of it (§ Factory, § Invariants).

This document is the operating manual: the architecture, the load-bearing invariants, and
the process rules an autonomous agent needs to make correct, safe changes here without
rediscovering them each session. When something below disagrees with the code, **the code is
ground truth — fix this file.**

---

## Project

An **MCP server for HPC clusters**. It exposes shell execution, filesystem access, Slurm job
management, and site-specific tooling to AI agents over the Model Context Protocol, so a coding
agent can actually work on a cluster instead of guessing about one. The package is `rcac_mcp`; the
console entry point (`pyproject.toml [project.scripts]`) is **`rcac-mcp`** → `rcac_mcp:main`, and
`python -m rcac_mcp` works via `__main__.py`.

The server is built on **FastMCP 2.x** with a **cmdkit** CLI, and speaks three transports (`stdio`,
`sse`, `http`) against three execution backends (`ssh`, `local`, `delegate`).

**The primary supported deployment is local + ephemeral over SSH keys:** the user runs the server on
their own machine in `stdio` mode, and it executes on the cluster over their existing
`~/.ssh/config`. `SECURITY.md` documents all three modes; treat that one as the recommended path and
the others as real but secondary.

### Direction — this is becoming `cluster-mcp`

**Nothing in this section is true yet.** It is the agreed trajectory, recorded so a change can be
made *with the grain* rather than against it. Do not code against it, cite it as an invariant, or
"prepare" for it speculatively — the cycles in `ROADMAP.md` are how it lands.

- **Rename and generalize `rcac-mcp` → `cluster-mcp`.** Nothing here should assume Purdue RCAC.
- **Capabilities become packaging extras.** `cluster-mcp[slurm,lmod]` installs the schedulers and
  module systems you actually have; a site extra like `cluster-mcp[rcac]` is shorthand for the right
  capability extras *plus* that center's specific tools and context. Others follow
  (`cluster-mcp[alcf]`, `[ncsa]`, `[tacc]`).
- **The long game is any HPC cluster** — not necessarily Slurm, not necessarily LMOD, not necessarily
  a Lustre scratch. Today's `tools/slurm.py` and `tools/rcac.py` are the *first* implementations of
  what become pluggable capability groups, not the shape of the final thing.
- **`/etc/agents.d/*.md` stays and gets evangelized.** It is a deliberate cross-vendor convention —
  administrators drop markdown there, any conforming client picks it up — and the intent is to get
  other centers to adopt it. See § Invariants §8 below; it is an invariant *today*, not just direction.

## Environment & working rules

- **`del`, not `rm`** — use `del <path>` (reversible trash; directories work with no flags). A
  deleted `issues/` seed is otherwise unrecoverable outside git history.
- **Commit only when explicitly asked.** When you do, branch per § Factory → Profile (`base:
  develop`). `main` is the default branch and the release channel: it moves only at a release, by
  fast-forward to a released `develop` commit, so `uvx git+https://…` installs the last release.
- **Squash-only merges.** Commit subjects follow `[category] Imperative summary`. Categories in use:
  `feature`, `fix`, `docs`, `refactor`, `test`, `harness` (the factory's footprint here: § Factory
  and § Invariants), `release` (version bumps), `ci`. The set is **not closed** — coin a new
  lowercase category when one genuinely fits. **Do not add a `Co-Authored-By:` trailer** — a
  deliberate repo convention (we don't want the authoring model recorded on every line of the
  commit log). End PR **bodies** with the Claude Code generation line.
- The version, agent-facing-surface and sandbox rules live in § Invariants (§9 and § Conventions).

## Commands

Dependency management is `uv` (`uv.lock`, `[dependency-groups] dev` syncs by default).

```bash
uv sync                                  # install all deps (incl. dev)
uv run rcac-mcp --help                   # the CLI
uv run rcac-mcp -e local                 # run locally (development only)

uv run pytest -v                         # full suite
uv run pytest -v -k "pattern"            # by name
uv run pytest -v -m unit                 # marker: unit | integration (--strict-markers)
                                         #   NOTE: selects NOTHING today — the markers are
                                         #   registered but no test carries one yet. See the
                                         #   restore-test-coverage seed in ROADMAP.md.

# Drive the CLI safely: throwaway HOME, blank auth env, unreachable cluster.
bin/sandbox.sh uv run rcac-mcp --help
bin/sandbox.sh sh -c "uv run rcac-mcp -e local --generate-token"

# A test drive must step back into the repo: the sandbox cd's out of it, and pytest would
# otherwise set rootdir to the throwaway dir and never load pyproject.toml (losing
# --strict-markers and every registered marker). HOME/auth/SSH isolation is unaffected.
bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run pytest -v -m integration'
```

**Supported Python is 3.14+** (`requires-python = ">=3.14"`). Do not reintroduce compatibility shims
for older interpreters.

**`bin/sandbox.sh` is the only safe way to drive this CLI in a check.** It gives the
run a throwaway `HOME` (so `~` expansion inside a tool call cannot touch yours), blanks
`JWT_SECRET` / `OIDC_*` / `RCAC_USER_MAP`, and unsets `RCAC_SSH_HOST` — which makes a bare
`rcac-mcp` **fail closed** with "SSH host required" instead of opening a session on production. In
`local` mode this server runs arbitrary shell as you; the sandbox is what keeps a verify command from
being a mistake you cannot undo.

## Repository map

Top-level package `src/rcac_mcp/`:

| Path | Responsibility |
|------|----------------|
| `__init__.py` | `MCPServerApp` (cmdkit `Application`) — all CLI wiring, `APP_HELP`, defaults, `_resolve_exec_mode()`, `_create_executor()`, `main()`. **There is no `cli/` package.** |
| `__main__.py` | `python -m rcac_mcp` shim. |
| `server.py` | `create_mcp_server()` — builds the `FastMCP` instance, attaches auth, registers tools/resources/middleware/custom routes. Home of **`SERVER_INSTRUCTIONS`**, the agent-facing contract. |
| `context.py` | `executor_var` (`ContextVar`) + `get_executor()`/`set_executor()`. **The isolation primitive.** Tiny and load-bearing. |
| `middleware.py` | `SharedExecutorMiddleware` (ssh/local) and `AuthExecutorMiddleware` (delegate) — both set the per-request executor in `on_call_tool`. |
| `auth.py` | `AUTH_MODES` registry: `none` → `None`, `jwt` → `JWTVerifier`, `oidc` → `OIDCProxy`. Enforces the `JWT_SECRET` minimum. |
| `token.py` | `ISSUER`/`AUDIENCE`/`ALGORITHM` constants + `generate_token()` (the `--generate-token` path). Signer side of the JWT contract. |
| `resources.py` | `RESOURCE_REGISTRY` — `rcac://context` (loads `/etc/agents.d/*.md` from the cluster) and `rcac://storage`. |
| `executor/base.py` | `Executor` `Protocol` + the `CommandResult` dataclass. The contract all backends satisfy. |
| `executor/ssh.py` | `SSHExecutor` — Fabric `Connection`, `~/.ssh/config`-aware, reconnect with exponential backoff. |
| `executor/shell.py` | `LocalShellExecutor` — `subprocess` via `$SHELL`. Development only. |
| `executor/delegate.py` | `DelegatingExecutor` + `load_user_map()` — `sudo -n -H -u <user>` on behalf of an authenticated identity. |
| `tools/__init__.py` | `TOOL_REGISTRY`, the `@mcp_tool` decorator, and the **import list that makes registration happen**. |
| `tools/{shell,filesystem,transfer}.py` | Generic backend-agnostic tools: `run_command`, directory/file read+write, `upload_file`/`download_file`. |
| `tools/slurm.py` | Slurm tools: `sbatch`, `squeue`, `scancel`, `sacct`, `sinfo`, `scontrol_show_*`, plus RCAC's `slist`/`sfeatures`. |
| `tools/rcac.py` | Purdue-specific: `myquota`, `storage_paths`, `jobinfo`/`jobcmd`/`jobenv`/`jobscript`, `showpartitions`, `average_wait`. |
| `docs/` + `tools/docs.py` | **Being removed.** The documentation search index moved to the separate `rcac-docs-mcp` service (live at `docs.rcac.purdue.edu/mcp`). See the `strip-docs-subsystem` seed in `ROADMAP.md`; do not build on it. |

Two repo-level paths sit outside the package: **`bin/sandbox.sh`** — the throwaway-environment
helper every CLI drive runs under (§ Factory → Throwaway environment); and **`spec/{slug}/`** — the
committed, dated per-feature design records (`GOAL.md`/`PLAN.md`/`TECH.md`/`REVIEW.md`) the
factory produces and **retains on merge**. `AGENTS.md` remains ground truth; `spec/{slug}/` is a
point-in-time record of intent. The factory's method and skills live in the operator's KB; see
§ Factory.

Two more repo-level paths carry work that is **not yet in flight**:

```
issues/{slug}.md   # deferred code work, pre-shaped; the feature step promotes one into a GOAL
ROADMAP.md         # the ordered index of future cycles — one entry per issue
```

Where each kind of deferral goes is fixed: § Factory → Where deferred work goes.

## Architecture & data flow

```
MCP client ──stdio│sse│http──▶ FastMCP ──▶ middleware.on_call_tool ──▶ set_executor(ContextVar)
                                                                            │
                                              tool fn ──get_executor()──────┘
                                                  │
                                                  ▼
                              Executor.run(cmd) ──▶ ssh │ local $SHELL │ sudo -u <user>
                                                  │
                                                  ▼
                                       CommandResult(stdout, stderr, exit_code, hostname)
```

Every tool follows the same three-line shape: `get_executor()`, run something, return a
`CommandResult` or a formatted string. Tools are backend-agnostic by construction — that is the whole
point of the `Executor` protocol, and it is why `run_command` works identically over SSH, locally,
and under `sudo`.

The contracts each piece keeps — request isolation, the executor protocol, the execution-mode
ladder, delegation and auth, tool registration, resources, and the agent-facing surface — are
§ Invariants §1–§9.

## Configuration

There is no config file and no config singleton — everything is CLI flags plus environment:

| Variable | Used for |
|---|---|
| `RCAC_SSH_HOST` | default SSH target (`--ssh-host` overrides) |
| `RCAC_USER_MAP` | path to the delegate-mode identity → local-user map |
| `JWT_SECRET` | HS256 shared secret (≥ 32 chars) |
| `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `MCP_BASE_URL` | OIDC proxy (all four required together) |
| `MCP_BASE_URL` | also used to build the absolute icon URL in `server.py` |

`MCP_BASE_URL` is read **at import time** in `server.py` to compute `ICON_URL`; setting it after
import has no effect.

## Testing

- `uv run pytest`. Only **`@mark.unit`** and **`@mark.integration`** are real markers under
  `--strict-markers` — tag every new test. **No existing test carries one**, so `-m unit` and
  `-m integration` currently deselect all 81 and report "no tests ran"; the rule is forward-looking
  until the `restore-test-coverage` cycle lands.
- Integration tests drive the installed CLI and must run under `bin/sandbox.sh`,
  stepping back into the repo first (`cd "$CLUSTER_MCP_REPO"`) so pytest finds `pyproject.toml`.
- `tests/conftest.py` currently provides only docs-index fixtures, and **every test in the suite
  today is a docs test** — removing the docs subsystem removes the whole suite. Rebuilding coverage
  for the executor/middleware/tool core is a tracked seed, not an optional nicety.
- The `tests/fixtures/RCAC-Docs` git submodule exists only for the docs index and goes with it.
- **PyYAML is not a dev pin.** The factory FSM scripts live in the operator's KB, which runs them
  with `uv run --with pyyaml`; nothing in this repository needs YAML outside the runtime docs
  indexer, so dropping the runtime `pyyaml` dependency with the docs subsystem needs no harness
  accommodation.

## Packaging

- `hatchling`; the wheel ships only `src/rcac_mcp`.
- **`uv.lock` is tracked.** This server is installed straight from `git+https://…`, so the lock is the
  only thing pinning the transitive tree a user actually receives. A change to `[project.dependencies]`
  or `[dependency-groups]` runs `uv lock` and commits the result **in the same commit**; the release
  recipe's `bump.files` stages it alongside the version bump. `uv lock --check` exits nonzero when
  the two have drifted.
- **The sdist must not ship `bin/`, `spec/`, `issues/`, `.security/`, or `tests/fixtures/`.**
  `[tool.hatch.build.targets.sdist]` excludes them and the release recipe's `gate` re-checks the
  tarball — a `.security/` path in a published artifact would publish an inventory of unremediated
  weaknesses.
- There is **no CI, no publish workflow, and no published container image**, and the project is not
  on PyPI — users install from `git+https://github.com/purduercac/rcac-mcp`. The release recipe cuts
  a tag and a GitHub release and says so plainly. Wiring CI is a tracked seed.
- A **container build does exist locally**: `Dockerfile` + `compose.yml` (+ `nginx-dev.conf` for the
  TLS dev proxy), documented in `README.md` § *Docker Compose with TLS*. `compose.yml` pins the
  server's argv (`-t http -H 0.0.0.0 -p 8000 -a jwt`), so a change to a CLI flag name or default is
  a change to those files too — same same-commit rule as `SERVER_INSTRUCTIONS` and the README.

## Working on this codebase as an agent

- **Use the factory for non-trivial work.** A feature/fix/refactor flows through the spec-driven
  lifecycle hosted in the operator's KB, run as `code rcac-mcp …` from that KB — feature (shape
  `GOAL.md`, or promote an `issues/{slug}.md`) → plan (research + `PLAN.md`/`TECH.md`) → build
  (execute phases) → review (blind, externally-verified QA) → publish (the profile's `landing`),
  each on a branch named by the profile's `branches`, with artifacts committed under
  `spec/{slug}/`. The KB's `method/agentic-engineering.md` is the *why*; § Invariants is the
  curated footgun checklist that plan and review read. Ceremony scales to appetite: a one-sentence
  change may skip the lifecycle entirely. Harness friction (not code issues) is a `friction` line
  in the operator's KB inbox, never a file here; `code harness` applies those fixes to the KB's
  skills — and never weakens a non-negotiable gate on a finding's say-so.
- **Retire what shipped with `code rcac-mcp roadmap`** (operational, **not** a lifecycle step). It
  finds every `issues/{slug}.md` carrying `status: adopted:{slug}`, confirms the cycle actually
  reached the profile's `base` on `origin`, because the marker only proves a cycle *started*, and
  after a human-gated preview deletes the seed and its `ROADMAP.md` entry — then repairs the drift
  the removal leaves. It is deliberately **not** folded into publish: retirement writes outside
  `spec/`, which is exactly what publish's staleness gate exists to notice.
- **Cut releases with `code rcac-mcp release`** (also operational): it follows § Factory → Release
  recipe — bumps the single version source, runs the gate (pytest, `uv build`, `twine check --strict`,
  sdist hygiene), signs a tag, and publishes a GitHub release — rehearsed in a `git worktree` dry-run
  and gated on an explicit human OK before any irreversible push.
- **Parallelizing agent work:** the subsystems safe to touch independently are the leaf tool modules
  (`tools/slurm.py`, `tools/rcac.py`, `tools/filesystem.py`), docs, and tests. The coupled core —
  `context.py`, `middleware.py`, `auth.py`, `token.py`, `executor/*`, `server.py` — shares the
  contracts above and should be changed with a single coherent view; parallel edits there conflict on
  *contracts*, not just lines. When in doubt, fan out to read/understand and serialize the edit.
- **This file is the map, but it drifts.** For a deep change, re-verify the specific invariant
  against the source before relying on it, and update this file when the code moves.

## Factory

This repo is built by the spec-driven factory: GOAL → PLAN/TECH → build → blind review → publish. The method and the skills live in the operator's KB (`method/agentic-engineering.md`, `skill/code-*.md`). The cycle's records live here: `spec/{slug}/` for work in flight, `issues/` and `ROADMAP.md` for deferred work. Inside this repo, its own rules win.

### Profile

| Key | Value |
|---|---|
| base | `develop`, the branch every cycle starts from and lands on; `main` moves only at a release, by fast-forward to a released `develop` commit |
| branches | `feature/{slug}`, `fix/{slug}`, `refactor/{slug}`, `docs/{slug}`, `test/{slug}`, `ci/{slug}`: the prefix is the GOAL's `kind`; the set is open |
| commit categories | `[feature]` `[fix]` `[docs]` `[refactor]` `[test]` `[ci]` `[release]` `[harness]`: lowercase, an open set (coin one when it fits). Branch commits take the GOAL's `kind` verbatim; landing subjects use these categories |
| branch commits | `[{kind}] Build {slug} P<n>`; no `Co-Authored-By:` trailer (existing repo convention) |
| landing | `squash-local`: squash onto `origin/develop` in the cycle worktree as one `[category] What changed` commit, then push `develop` |
| ci | none yet (the `ci-workflow` seed adds it) |
| setup | `uv sync --locked`: dependency refresh, run before any verify |
| verify | `uv lock --check && uv run pytest -q && bin/sandbox.sh uv run rcac-mcp --help`: the full gate. Phases narrow it; publish and release run all of it |
| throwaway environment | `bin/sandbox.sh <cmd…>` (contract below) |
| coupled core | `src/rcac_mcp/context.py`, `middleware.py`, `auth.py`, `token.py`, `executor/*`, `server.py` |
| same-commit rules | see § Conventions |
| high-blast-radius paths | see § Invariants |
| security lane | on: unremediated security findings go to the gitignored `.security/`, never `issues/` |
| release | see Release recipe (`release.trigger`) |

### Release recipe

```yaml
release:
  trigger: on-demand
  version:
    source: pyproject.toml project.version
    scheme: pep440
    tag_format: "{v}"
    prerelease_syntax: '^\d+\.\d+\.\d+(a|b|rc)\d+$'
    propose_next: by-kind
  bump:
    lock: uv lock
    lockstep: []
    files: [pyproject.toml, uv.lock]
    diff_rule: only project.version in pyproject.toml and the rcac-mcp version entry in uv.lock change
    subject: "[release] Version {v}"
  gate:
    - uv lock --check
    - uv run pytest -q
    - uv build -o dist/
    - uvx twine check --strict dist/*
    # Sdist hygiene: fails on any repository furniture in a built sdist, or when there is no sdist.
    - >-
      python3 -c 'import glob, sys, tarfile;
      bad = (".security", "spec", "issues", "tests/fixtures", "bin", ".agents");
      ts = glob.glob("dist/*.tar.gz");
      rel = [(t, (m.split("/", 1) + [""])[1]) for t in ts for m in tarfile.open(t).getnames()];
      hits = [t + ": " + r for t, r in rel for d in bad if r == d or r.startswith(d + "/")];
      [print(h, file=sys.stderr) for h in hits];
      sys.exit(1 if hits or not ts else 0)'
  tag:
    message: "rcac-mcp {v}"
    signed: true
  notes: git-log-by-category
  modes:
    release:
      base: develop
      prerelease: forbidden
      final: true
      inputs: []
      work_branch: in-place
      branch_ops: []
      merge_into: main          # FAST-FORWARD only (git merge --ff-only), never --no-ff: main never takes a commit that is not on develop
      tag_on: bump
      back_merge_into: none
      push: [HEAD:develop, HEAD:main, "{v}"]   # each its own approval
      publish: gh release create {v} --verify-tag
  post_verify:
    - bin/sandbox.sh uvx --from git+https://github.com/purduercac/rcac-mcp@{v} rcac-mcp --help
  caveats:
    main-fast-forward: >-
      merge_into main is a fast-forward to the released develop commit, never a merge commit; main
      never takes a commit that is not on develop. If main cannot fast-forward, STOP.
    no-ci-no-index: >-
      There is no CI, no publish workflow, no published container image, and no PyPI project. A
      release is a signed tag plus a GitHub release, and users install from
      git+https://github.com/purduercac/rcac-mcp@{v}. The push fires no CI; say so rather than
      waiting for a run. Until ci-workflow lands, this gate is the only thing between a bad build
      and a permanent tag.
    pypi: >-
      A PyPI upload (uvx twine upload dist/*) is out of scope unless Geoffrey opts in for that
      release; a version string on a package index can never be reused.
    twine: >-
      twine check --strict runs although nothing is uploaded: it validates the metadata a future
      publish depends on and catches a broken long description before it is baked into a tag.
    no-sources: >-
      The old gate built with uv build --no-sources. pyproject.toml has no [tool.uv.sources] today,
      so uv build -o dist/ is equivalent; add --no-sources if a source override is ever added.
    security-in-sdist: >-
      A .security/ path in the sdist is a hard stop. Tell Geoffrey plainly: it would publish an
      inventory of unremediated weaknesses. The hygiene check lists what the sdist does contain.
    lock: >-
      uv.lock is tracked and pins the transitive tree a git+https install receives; a bump that
      leaves it stale ships a version the lock disagrees with. If anything besides pyproject.toml
      and uv.lock wants staging in the bump, STOP and look.
    versions: >-
      PEP 440, no v prefix, and no hyphen in a prerelease (0.2.0a1, not 0.2.0-a1). The version must
      be strictly greater than the latest tag and not already a tag.
    first-release: >-
      No tag exists yet; the first release's notes draw from the beginning of history.
    install-probe: >-
      post_verify runs under bin/sandbox.sh so the probe cannot pick up the working tree or reach a
      real cluster.
  clean_paths: [dist/]
```

### Throwaway environment

`bin/sandbox.sh <cmd…>` runs `<cmd…>` against a disposable instance of the app. It:

1. runs from the repo or worktree root;
2. creates a fresh state directory and removes it on every exit path;
3. redirects all app state (database, config, index, logs, keys) into that directory, so real data is never touched;
4. runs the command inside it, so relative writes can't reach the worktree;
5. exercises the current tree: rebuild or run from source, never a stale binary;
6. pins tool discovery back to the repo;
7. writes its own output to stderr and passes the command's exit status through.

Here: the root is the checkout the script lives in; the state directory is a `mktemp -d` under
`$TMPDIR`, removed by a trap; `HOME` and XDG point into it, the auth environment is blanked, and
`RCAC_SSH_HOST` is unset so the default stdio→`ssh` path fails closed; `uv run` runs this tree from
source, with `UV_PROJECT` and `CLUSTER_MCP_REPO` pinning discovery back to the repo.

### Where deferred work goes

**Where a deferral goes — five homes, one rule each.** A pass that decides *not* to fix something
must still record it, and the destination is not a matter of taste:

| File | Holds | Written by |
|------|-------|------------|
| `issues/{slug}.md` | **Deferred code work**, pre-shaped from the KB's `ISSUE.md` template, `status: unshaped` | whoever defers it |
| `ROADMAP.md` | the **ordered index** — one entry per issue, `**Seed:**` pointing at the `issues/` file | whoever defers it |
| `.security/issues/{slug}.md` + `.security/ROADMAP.md` | the same two things for **unremediated security findings** — gitignored, never published | whoever defers it |
| `spec/{slug}/` | work **actually in flight** | the lifecycle skills |
| the KB inbox | **Harness/skill feedback only** — "was this the *factory's* fault", as `friction` lines. Never code follow-ups. | the lifecycle skills |

An `issues/{slug}.md` is a *candidate, not a contract*: the feature step promotes it into
`spec/{slug}/GOAL.md`, and that promotion is where appetite, non-goals and the R-IDs get negotiated
with a human. **Never copy one into a `GOAL.md` verbatim** — the review step grades a GOAL, and a
proposal nobody accepted is not a contract. The `status:` field is the guard: `unshaped` (raw
deferral — evidence captured, nothing agreed), `shaped` (already negotiated with a human, but **not
yet accepted into a cycle**), `adopted:{slug}` (promoted; `spec/{slug}/` owns it now, and the record
stays *while the cycle is in flight* so the ROADMAP index does not dangle). Two further values close
a deferral **without** shipping — `declined` and `accepted-behaviour` — and those are terminal
records, indexed under `ROADMAP.md` § *Settled questions* rather than as cycles.

**A deferral is retired, not kept forever.** When the cycle that adopted a seed lands on the
profile's `base`, `code rcac-mcp roadmap` deletes the seed and removes its `ROADMAP.md` entry:
`spec/{slug}/` is the retained account and git history holds the file. Retire only on evidence the
cycle *landed* — an `adopted:{slug}` marker proves a cycle started, never that it finished. The
security lane inverts this: nothing under `.security/` is ever deleted, because it is gitignored and
a deletion there leaves no history to recover from.

**The security lane is not optional here.** This is a multi-user command-execution service that runs
as root in one of its modes, on shared research infrastructure. A deferral describing an
*unremediated* weakness — a live path to running a command as the wrong user, on the wrong host, or
without the intended authentication — goes in `.security/`, which is gitignored along with `.local/`.
Publishing a standing roadmap of live vulnerabilities hands an attacker a work plan. The *fixes* land
as ordinary public commits and PRs when they ship; only the inventory of what is still open stays
private. When in doubt which lane an item belongs to, use `.security/` and ask.

This coexists with the **GitHub tracker**: a GH issue is the public-facing ticket, `issues/{slug}.md`
is the pre-shaped spec behind it, and the two may link to each other. Neither replaces the other.

## Invariants

The gate for every plan and the footgun list for every review. A plan walks only the sections its change touches. A review grades every violation of a numbered section, lettered subsections included, as CRITICAL; a violation of § Conventions is HIGH.

Only invoke the sections relevant to the change — do not manufacture findings against untouched
subsystems.

**This section describes what is true today, not what is planned.** The project is mid-generalization
from `rcac-mcp` to `cluster-mcp` (see `ROADMAP.md`); when a cycle lands a new contract — packaging
extras, a plugin registry, a capability-probe protocol — it adds the section here in the same commit
that lands the contract. Do not pre-write invariants for work that has not shipped.

### High-blast-radius paths (human gate)

A CONFIRMED finding in any of these files needs a human decision before the cycle lands; a plan touching one always runs research. The list only widens: when code moves, add the new home and never remove the old entry. Skills and templates cite this list and never copy it.

- `src/rcac_mcp/context.py`
- `src/rcac_mcp/middleware.py`
- `src/rcac_mcp/auth.py`
- `src/rcac_mcp/token.py`
- `src/rcac_mcp/executor/base.py`
- `src/rcac_mcp/executor/delegate.py`
- `src/rcac_mcp/executor/ssh.py`
- `src/rcac_mcp/server.py`
- `src/rcac_mcp/__init__.py` — `_resolve_exec_mode()`, the execution-mode posture ladder (§4)
- `bin/sandbox.sh` — the throwaway environment; a mistake there turns a verify into a command
  against a real home or a production cluster

These are the files where a mistake executes someone else's command, executes as the wrong user, or
executes on the wrong machine. Everything else in the tree is a leaf.

#### Footguns (quick reference)

The two leaf files at the end of this list are footguns, not human-gated paths.

- **`context.py`** — 47 lines, the highest blast radius in the repo. A module global here is
  cross-user command execution.
- **`middleware.py`** — where identity becomes an executor. Claim precedence, the user-map check, and
  `return await call_next(context)` are all load-bearing.
- **`executor/delegate.py`** — the `sudo` argv, `-n`, `shlex.quote` on `cwd` only, the server's
  `$SHELL`.
- **`auth.py` / `token.py`** — the 32-char minimum in two places; the issuer/audience/algorithm
  triple that must match across signer and verifier. Note `auth.py`'s `AUTH_MODES` annotation carries
  a stray `:` that only parses because of PEP 563 — see the `auth-modes-annotation-typo` seed.
- **`executor/ssh.py`** — reconnect backoff; the *uncaught* Fabric timeout that makes `run()`'s
  contract differ from the other two backends.
- **`__init__.py`** — `_resolve_exec_mode()`, the posture ladder.
- **`server.py`** — `SERVER_INSTRUCTIONS` (what every model reads) and import-time `MCP_BASE_URL`.
- **`tools/__init__.py`** — the bottom-of-file import list; a missing entry silently drops a tool.
- **`resources.py`** — the process-global context cache keyed by a non-unique hostname.

### 1. Per-request executor isolation (`context.py` + `middleware.py`) — highest blast radius [human gate]

- **The current executor lives in a `ContextVar` (`context.py`), never a module-level global.**
  `executor_var` is task-local; async tasks (one per HTTP request under FastMCP/Starlette) each get
  their own copy, so each request gets its own executor. Replacing it with a plain module global is a
  **cross-user command-execution vulnerability** — user A's request would run as user B.
  `SECURITY.md` § *Request Isolation in Delegate Mode* states the contract and shows the unsafe form
  explicitly — read it before touching this. The three bullets below are its consequences that are
  easy to get wrong.
- **`set_executor()` is called per tool call, from middleware `on_call_tool`** — not at server
  construction, not once per connection. `SharedExecutorMiddleware` re-sets the *same* instance every
  call precisely because a ContextVar set in one task is invisible to the next.
- **Tools never construct an executor.** They call `get_executor()`, which raises `RuntimeError` when
  unset. A tool that instantiates its own executor bypasses delegation entirely.
- **Any new middleware must not swallow the call chain** (`return await call_next(context)`), above
  all one that runs *before* the executor middleware, or the executor is never set for that request.

### 2. Executor Protocol contract (`executor/base.py`) [human gate]

- `Executor` is a `@runtime_checkable` `Protocol` with **eight** members: `hostname` (property),
  `run`, `put`, `get`, `open`, `close`, `__enter__`, `__exit__`.
- **Three implementations move together:** `SSHExecutor`, `LocalShellExecutor`, `DelegatingExecutor`.
  Adding or changing a Protocol member means editing all three in the same commit — there is no base
  class to inherit a default from, and `runtime_checkable` `isinstance` checks **method presence
  only, never signatures**, so a mismatched signature fails at call time, not at registration.
- `open()`/`close()` are **no-ops** for the local and delegating executors and real for SSH. Code
  that depends on `close()` releasing something must not assume it did.

### 3. `CommandResult` and exit-code semantics [human gate]

- Every executor returns `CommandResult(stdout, stderr, exit_code, hostname)`. Tools format it; they
  do not invent their own result shape.
- **`exit_code = -1` is overloaded.** `LocalShellExecutor.run` and `DelegatingExecutor.run` return
  `-1` on `subprocess.TimeoutExpired`, which collides with a real subprocess return code of `-1`
  (killed by SIGHUP). Do not add new sentinels in the signal range `-1..-64`; if a distinct "never
  ran" signal is needed, pick a value below `-1000` and document it here first.
- **Timeout behavior is asymmetric across executors.** Local and delegate *catch* the timeout and
  return a `CommandResult`; `SSHExecutor.run` passes `timeout` to Fabric and does **not** catch —
  Invoke raises `CommandTimedOut`, which propagates to the caller. A change that assumes one shape
  breaks the other mode. Reproduce against both before relying on either.
- `hostname` differs by mode: the SSH target for `SSHExecutor`, `socket.gethostname()` for the local
  and delegating executors. It is **not** a user-distinguishing key: in delegate mode every user
  reports the same value (see §8).

### 4. Execution-mode resolution (`__init__.py`) — read before touching `__init__.py` or `middleware.py` [human gate]

`MCPServerApp._resolve_exec_mode()` is a **security posture ladder**; changing its order changes who
runs what, where. The current order is:

1. explicit `-e/--exec-mode` wins;
2. `transport == 'stdio'` → `ssh`;
3. `--ssh-host` or `RCAC_SSH_HOST` set → `ssh` (regardless of transport);
4. `auth == 'none'` → `local`;
5. otherwise → `delegate`.

- **`local` mode executes as the server process owner with no authentication**, and — read rung 4
  carefully — it **is** what a bare `rcac-mcp -t http` or `-t sse` resolves to today, because
  `DEFAULT_AUTH` is `'none'` and rung 3 only preempts when an SSH host is configured. That is the
  documented out-of-the-box posture (`APP_HELP`: "default for http with auth=none"; `SECURITY.md`
  § *Mode 2*), not a defect to report. The invariant is: **never widen it.** Do not make `local`
  reachable when authentication *is* configured, and do not add a rung that reaches it earlier.
- **`delegate` mode requires authentication.** `AuthExecutorMiddleware` is only installed for
  `exec_mode == 'delegate'`; the other modes install `SharedExecutorMiddleware`. Never wire delegate
  behavior into the shared path.

What each mode means:

| Mode | Runs as | Auth | Notes |
|---|---|---|---|
| `ssh` | the SSH user, on the cluster | none at the MCP layer | The recommended path. The security boundary *is* the SSH connection. |
| `local` | the server process owner, on this box | none | **Development only.** Anyone who reaches the endpoint runs commands as you. |
| `delegate` | the mapped local user, via `sudo` | jwt or oidc, **required** | Server runs privileged; OS controls (sudoers/PAM) are the real enforcement. |

### 5. Delegate mode — sudo wrapping, user map, identity claims (`executor/delegate.py` + `middleware.py`) [human gate]

- **Identity claim precedence is `sub` → `email` → `preferred_username`**, first non-empty wins
  (`AuthExecutorMiddleware._extract_identity`). Reordering silently re-maps users. No claim → hard
  `RuntimeError`, never a fallback identity.
- **An identity absent from the user map is a `PermissionError`, never a default user.** The map is
  loaded once at middleware construction from `RCAC_USER_MAP`; `DelegatingExecutor.__init__` re-checks
  and raises `KeyError`. Keep both checks — the executor is constructible outside the middleware.
- Commands run as `sudo -n -H -u <local_user> <shell> -c <command>`. **`-n` (non-interactive) is
  required** — there is no TTY, so dropping it turns a missing sudoers rule into a hang instead of an
  error. `cwd` is `shlex.quote`d; `command` deliberately is not (it *is* a shell command).
- `DelegatingExecutor._shell` is the **server process's** `$SHELL`, not the target user's. It is
  chosen at construction; do not read it per-command from an attacker-influenced environment.
- **The user map file format is `<identity> <local-user>`, one per line**, `#` comments, first
  whitespace splits. A malformed line raises `ValueError` naming the line number — a partial map is
  worse than no map.

### 6. Auth providers and token claims (`auth.py` + `token.py`) [human gate]

- **`JWT_SECRET` must be at least 32 characters.** Enforced in *two* places — `create_jwt_auth()` and
  the `--generate-token` path in `MCPServerApp.run()`. Never weaken either; never weaken or fix
  one and leave the other.
- **`ISSUER`, `AUDIENCE`, `ALGORITHM` are single-sourced in `token.py`** and consumed by
  `create_jwt_auth()`. Signer and verifier must agree; changing one alone silently rejects every
  token.
- `AUTH_MODES` maps `'none' | 'jwt' | 'oidc'` to provider factories, where `'none'` returns `None`
  (FastMCP's "no auth"). A new auth mode is a new entry **plus** the `-a/--auth` `choices` list in
  `MCPServerApp` — they are not derived from each other.
- OIDC requires all four of `OIDC_CONFIG_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `MCP_BASE_URL`;
  the all-or-nothing check exists so a half-configured proxy fails at startup, not at first request.

### 7. Tool registration is an import-time side effect (`tools/__init__.py`)

- `TOOL_REGISTRY` and `mcp_tool` are defined **first**, then each tool module is imported at the
  bottom of the file. `@mcp_tool` appends at decoration time, so **a tool module missing from that
  import list registers nothing and fails silently** — no error, just an absent tool.
- **`@mcp_tool` replaces the function with a `fastmcp.tools.tool.FunctionTool`, which is not
  callable.** Other Python code cannot invoke a decorated tool directly; `storage_paths()` from
  `resources.py` raises `TypeError: 'FunctionTool' object is not callable`. When logic must be shared
  between a tool and something else, factor it into an undecorated helper and have both call that.
  (`resources.py` currently gets this wrong — see the `storage-paths-resource-typeerror` seed.)
- Tool return values are serialized by FastMCP. Returning a `@dataclass` (`CommandResult`,
  `StoragePaths`) is supported and used; returning an arbitrary object is not.

### 8. Resources and the `/etc/agents.d/*.md` convention (`resources.py`)

- `RESOURCE_REGISTRY` (`resources.py`) exposes `rcac://context` and `rcac://storage`.
- **`/etc/agents.d/*.md` is a deliberate, external, cross-site convention** — cluster administrators
  drop markdown there and any conforming client picks it up. Files are found with a `maxdepth 1`
  glob and concatenated in `sort` order with a `<!-- Source: {filename} -->` header each. Do not
  change the path, the glob, the ordering, or the header format without treating it as a
  compatibility break; the intent is to get *other* centers to adopt it.
- A missing directory or empty result is **not an error** — it caches and returns `''`.
- **`_cluster_context_cache` is a process-global dict keyed by `executor.hostname`.** In delegate mode
  every user's executor reports the same `socket.gethostname()`, so the first user's context is served
  to all subsequent users. That is a known defect with a filed seed, not a design choice — do not
  build new per-user state on this cache, and do not key any new cache on `hostname` alone.

### 9. The agent-facing surface is part of the API (`server.py`) [human gate]

- `SERVER_INSTRUCTIONS` (`server.py`) is what every connecting model reads before choosing a tool.
  **Adding, renaming, or removing a tool — any tool change — updates `SERVER_INSTRUCTIONS` in the
  same commit** — a tool the instructions do not mention is a tool agents will not reach for, and an
  instruction naming a tool that no longer exists is a hallucination the server itself induced.
- The same commit also updates the tool inventory in `README.md`, which is what a human reads before
  installing. Both are user-visible contracts.
- Tool **docstrings** are the per-tool schema description sent over MCP, which every model reads;
  they are API surface, not internal notes. Keep the `Args:` / `Returns:` / `Examples:` shape the
  existing tools use.

### Conventions (same-commit rules)

- **Version is single-sourced from `pyproject.toml`**, the release recipe's `version.source` —
  `rcac_mcp.__version__` reads it via `importlib.metadata.version('rcac-mcp')`. Never hardcode a
  version anywhere else. The release recipe's `gate` mirrors CI.
- **Supported Python is 3.14+** (`requires-python = ">=3.14"`). Do not add compatibility shims for
  older interpreters.
- A change to `[project.dependencies]` or `[dependency-groups]` and its `uv lock` land in the same
  commit, and a CLI flag name or default moves `compose.yml` with it: § Packaging.
- **Put logic where it belongs:** command execution behind the `Executor` protocol; identity →
  executor in middleware; per-request state in a `ContextVar`. **Reuse `cmdkit.app.exit_status`
  constants for return codes** — do not invent integer literals. A new CLI flag is an
  `interface.add_argument` on `MCPServerApp` plus its entry in `APP_USAGE` / `APP_HELP`, in the same
  commit.
- **Tests: only `@mark.unit` and `@mark.integration` are real markers** under `--strict-markers`. Tag
  every new test. **No existing test carries a marker**, so `-m unit`/`-m integration` deselect
  everything today — do not write a `verify:` gate whose only assertion is a marker selection, or it
  passes green over zero tests. (Tracked: the `restore-test-coverage` seed.)
- **A CLI drive — any verify or test drive — never touches the developer's real home, config, or a
  real cluster.** Wrap it in
  `bin/sandbox.sh`, which unsets `RCAC_SSH_HOST` so the default stdio→ssh path fails
  closed instead of connecting to production. The sandbox `cd`s out of the repo, so a **pytest** drive
  must step back in — `sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run pytest …'` — or pytest roots
  itself in the throwaway dir, never reads `pyproject.toml`, and silently loses `--strict-markers`.
- **Verify by driving the CLI, not just tests — in the sandbox.** After a change, exercise the real
  flow: `bin/sandbox.sh sh -c "uv run rcac-mcp -e local --help"`. **Exit 0 is not
  enough** — assert the post-condition you actually care about (the tool is in the registry, the
  error message and exit status are the intended ones, the file landed where you expected).
- **Comments (and docstrings) are declarative statements of the invariant or the *why*** —
  capitalized sentences (`# Non-interactive: there is no TTY to prompt on.`), not lowercase
  fragments, and **never** a feature-scoped spec id (`R#`, `P#`): those restart per feature, live in
  `spec/{slug}/`, and collide across branches. Requirement provenance lives in the commit, the PR,
  and the retained `spec/{slug}/`. Referencing stable things (a real symbol, a documented invariant,
  an `/etc/agents.d` path) is fine.
- **No `Co-Authored-By` trailer** on any commit (repo convention). PR *bodies* end with the Claude
  Code generation line.
- Point to a rule; don't restate it. A rule restated in N places is a same-commit obligation in all N.
- Prose and commit voice follow § Environment & working rules (commit subjects) and the comment
  rules above; voice is hygiene, not a review finding.
