# Research 04: instructions split and served surface (R2, R8, R11, R12; R15/R16 text side)

## Recommendations

1. **Three texts, one composed base, and the base keeps its name.** Each member exports its own text
   constant: `cluster_mcp.core` has `CORE_INSTRUCTIONS`, `cluster_mcp.slurm` has
   `SLURM_INSTRUCTIONS`, and `cluster_mcp.rcac` has `RCAC_INSTRUCTIONS`, the overlay. Each should
   sit in a leaf module that imports nothing, such as `<member>/instructions.py`, so that no member
   import can make a cycle. Compose them at the same point where the default install assembles
   `TOOL_REGISTRY`, joined by `'\n\n'` in the order core, Slurm, RCAC, and call the result
   `SERVER_INSTRUCTIONS`. The overlay comes last, so it sits directly above
   `## Site context (/etc/agents.d)`. Keeping the name `SERVER_INSTRUCTIONS` keeps §9's wording true
   ("`SERVER_INSTRUCTIONS` is the base"). It also keeps working, unedited, every consumer that
   imports it: `test_instructions`, `test_site`, `test_site_startup`, `test_context:271`,
   `test_protocol:48`, `test_transports:30`, `mutants.py:1268` (whose anchor is the
   `instructions=compose(SERVER_INSTRUCTIONS, site, budget),` line, so keep that line verbatim), and
   the fixture script. This works with capability-extras and does not pre-build it: that cycle only
   swaps the static join for "the texts of the members that loaded".
2. **Slurm tools go in a Slurm snippet that the Slurm member owns, not in the core text.** R11 would
   allow them in the core. The trouble comes in capability-extras: once Slurm becomes optional, a
   core text that names `sbatch` names a tool that may not register, which breaks R12's "name every
   tool that registers" in reverse. It is cheap to own the snippet now, since the tools move into
   that member anyway.
3. **`Resources:`** The core names only `cluster://context`, which `site.py` and `resources.py`
   in the core back. The overlay names `cluster://storage`, which is backed by
   `resolve_storage_paths` (`tools/rcac.py:343`, `findscratch` and `myquota`) and so goes with the
   RCAC member. **Do not name the `rcac://` aliases.** They are deprecated (R16 puts that in the
   README), naming them invites new use, and lowercase `rcac` in the core would make R11 ambiguous.
4. **Server name (R2):** `FastMCP(name='cluster-mcp')`. The fixture gets no new key. Pin the name
   with a new unit test in each era instead (below).
5. **Icon: keep it in the core, byte-identical** (`/static/purdue-favicon.ico`, its route, and
   `ICON_URL`). R11 governs only the instructions, and R2 governs only the name. Moving the icon to
   the RCAC member needs a hook that lets a member register routes and icons, which is
   capability-extras or site-extras work. The icon is also HTTP surface that clients may have
   cached. Record the tension with the Outcome's "core reads as generic" as a note for `site-extras`.
   Packaging risk: the core wheel must still ship `static/purdue-favicon.ico`. With hatch
   `packages = [...]` that happens only if `static/` moves with `server.py`.

## Draft texts (UTF-16 units measured with `site.units`)

Core, 559 units:

```
cluster-mcp: tools for working on an HPC cluster. Prefer a dedicated tool
below to run_command when one fits. The site context section after this one
carries the cluster's own rules; follow them.

Shell and files:
- run_command: Execute a shell command
- list_directory: List a directory
- read_file: Read a file
- write_file: Write a file
- upload_file: Copy a file to the cluster
- download_file: Copy a file from the cluster

Site:
- cluster_context: The cluster's rules from /etc/agents.d, in full

Resources: cluster://context (the site context in full).
```

Slurm snippet, 304 units:

```
Slurm jobs:
- sbatch: Submit a batch job (script path or content)
- squeue: View the job queue
- scancel: Cancel jobs
- sacct: Job accounting history
- scontrol_show_job: Slurm's view of a job

Slurm cluster status:
- sinfo: Cluster and partition status
- scontrol_show_node: Node details for diagnostics
```

RCAC overlay, 507 units:

```
RCAC-specific tools:
- storage_paths: Resolve home, scratch and depot paths
- myquota: Storage spaces, usage and quotas
- jobinfo: Detailed job information
- jobcmd: The command a job was submitted with
- jobenv: A job's environment variables
- jobscript: A job's submission script
- showpartitions: Partitions and their status
- average_wait: Queue wait time statistics
- slist: Slurm accounts and usage
- sfeatures: Node features and constraints

Resources: cluster://storage (what storage_paths returns).
```

Each line keeps today's wording. The only changes are the dropped "(RCAC)" suffixes, which the
section label replaces.

**Lengths.** Measured in a scratch script against the current tree:

- **Base:** the composed base is **1,374 units**, against **1,333** today (+41).
- **Cap test:** `test_base_leaves_room_for_the_site`, which caps the base at ≤1,500, still passes
  with 126 units to spare.
- **Minimum budget:** every term of `minimum_budget` is `units(_head(base))` plus a constant, so
  the minimum rises by exactly +41 for every site state. With no files (`harness.SITE`) it goes from
  **1,524 to 1,565**.
- **Pinned numbers:** no live file pins 1,333 or 1,524. They appear only in the retained `spec/`
  records (`agents-d-instructions/PLAN.md:135`, `REVIEW.md:34,53`), and every test derives the
  minimum at runtime. The default budget of 4,096 is unaffected.

**Checks.**

- **Registry:** `instruction_violations(new, EXPECTED_TOOLS)` returns `[]`.
- **R11:** the core contains no `rcac` or `Purdue` (case-insensitive) and no RCAC tool name.
- **Mutation tests:** the `_drop_sinfo` mutation still works, because `- sinfo:` sits in the Slurm
  snippet.
- **New tests to add to `test_instructions.py`:**
  - (R11) the core has no `(?i)rcac|purdue` and does not name any tool the RCAC member registers;
  - (R12) the overlay's first line contains `RCAC-specific`, and its `LISTED` names equal the RCAC
    member's registry;
  - `SERVER_INSTRUCTIONS == '\n\n'.join(...)`;
  - the Slurm snippet's `LISTED` names equal the Slurm member's registry.

## Evidence

- **Q2, the mapping is complete.** `EXPECTED_TOOLS` (`tests/test_registry.py:33`) has 24 tools,
  which split as follows:
  - core, 7: the 6 shell and file tools plus `cluster_context`;
  - Slurm, 7: `sbatch`, `squeue`, `scancel`, `sacct`, `sinfo`, `scontrol_show_job`,
    `scontrol_show_node`;
  - RCAC, 10: `storage_paths`, `myquota`, `jobinfo`, `jobcmd`, `jobenv`, `jobscript`,
    `showpartitions`, `average_wait`, `slist`, `sfeatures`.

  Each tool is listed exactly once, and the cross-check over the joined text is clean. Today's base
  is `server.py:66-104`, and `name='RCAC'` is at `:127`.
- **Q4, server info.** The `name` passed to FastMCP 4.1.4 becomes the low-level server's
  `server_info` (`mcp/server/lowlevel/server.py:640`). It reaches the client in two ways:
  - **legacy era:** `InitializeResult.serverInfo.name` (`mcp/server/runner.py:435`);
  - **modern era (2026-07-28):** the `_meta` serverInfo stamp on every result
    (`runner.py:396-417`).

  Probe, run with a plain FastMCP `Client` (no cluster): `('legacy','2025-11-25','RCAC','4.1.4',
  ['/static/purdue-favicon.ico'])` and `('auto','2026-07-28','RCAC',…)`. Neither the fixture nor
  `test_surface.py` carries the name:
  - `harness._surface` (`tests/harness.py:410-423`) captures only `instructions`, `tools` and
    `resources`;
  - the shape test asserts `sorted(snapshot) == ['instructions','resources','tools']`
    (`test_surface.py:226`);
  - nothing in `tests/` reads `server_info`.

  So R8's "server name" delta is **zero bytes of fixture**. The commit body should state that, and
  the name should be pinned by a new test: connect in the selected era (CI runs both) and assert
  `client.server_info.name == 'cluster-mcp'`. It could go in `test_protocol.py` beside `Negotiated`,
  or into `Negotiated` itself. Adding a `server_name` key to the fixture would break the shape test.
  It would also break the fixture's story as the `3d010ec` snapshot, since that commit served `RCAC`.
  Side finding: `serverInfo.version` is FastMCP's own `4.1.4`, not ours. R2 does not require
  changing it, and changing it would be a further delta, so leave it.
- **Q5, descriptions.** In the fixture, only `slist` and `sfeatures` mention RCAC, as "Show Slurm
  accounts and current usage (RCAC-specific)." and "Show available node features and constraints
  (RCAC-specific)." (`tools/slurm.py:509,533`). No served description or resource description names
  `rcac://` or Purdue. The other hits are not served: module docstrings (`tools/rcac.py:4-8`,
  `tools/slurm.py:7`) and the helper docstring at `tools/rcac.py:343`. Every docstring must move
  **byte-identical**: the fixture pins `description`, and R8 allows no tool delta. No tool carries
  annotations today; nothing in `src/` sets `annotations=`. The fixture does not pin annotations, so
  R8's annotations clause holds trivially as long as none are added.
- **Q6, the fixture hand-edit.** Copy the pattern of `spec/agents-d-instructions/verify/fixture_deltas.py`:
  `apply|check [BASE_REF]` rebuilds the expected fixture from the merge base, then `check` fails on
  any stray path and any unapplied delta. Write this cycle's version as
  `spec/rename-to-cluster-mcp/verify/fixture_deltas.py`. Its `DELTAS`:
  - `instructions` = `compose(SERVER_INSTRUCTIONS, harness.SITE)`;
  - `resources`: the key `rcac://context` becomes `cluster://context`, and `rcac://storage` becomes
    `cluster://storage`. The values (`name`, `description`, `mimeType`) are unchanged.

  `test_surface.py` compares resources by key set (`resource missing` / `resource added`) and then
  field by field (`:193-201`). Test code that must change with it:
  - the shape assertion (`:229`);
  - the `resource-dropped` drift case, which pops `'rcac://storage'` (`:256`);
  - the docstring's delta list (`:12-17`).

  The aliases depend on the resources worker's choice:
  - **unlisted** (routed in middleware or by lookup): the fixture has exactly the two `cluster://`
    keys. I prefer this, because `resources/list` stays free of duplicate `name`s.
  - **listed:** the fixture also keeps both `rcac://` keys, and the shape test expects four. Any
    alias description that differs from today's counts as a further delta, which R8 forbids for
    anything but URIs.

  The squash commits on `develop` (`09ce3af`, etc.) have empty bodies, so the delta list lives in
  the cycle's commit body plus § Testing and §9.
- **Q7, README and INSTRUCTIONS.md.** The README tool inventory (`README.md:143-181`) should be
  regrouped Core / Slurm / RCAC-specific to mirror the texts: `slist` and `sfeatures` move under the
  RCAC heading, and the "(RCAC-specific)" suffixes go. Other README fixes:
  - **Line 56:** change `rcac://context` to `cluster://context`.
  - **Line 61:** change `RCAC_INSTRUCTIONS_BUDGET` to `CLUSTER_MCP_INSTRUCTIONS_BUDGET`.
  - **Title** (`:1`): `RCAC MCP Server`.
  - **Formatting bug:** the `extra_args` paragraph at `:177` splits the Slurm list.

  `INSTRUCTIONS.md` is a separate Purdue system-prompt document. It is not served, and the only
  thing tied to it is the docs-guidance check (`test_instructions.py:97`). It names none of the
  server's old identifiers (its `$RCAC_SCRATCH` is a site variable), so for R15 it needs no rename.
  It should keep its Purdue content.

### Draft § Testing / §9 delta sentence

> `rename-to-cluster-mcp` changed `instructions` (the base is now the generic core, the Slurm
> snippet and the RCAC-specific overlay, composed with `harness.SITE`) and renamed the resource keys
> `rcac://context` → `cluster://context` and `rcac://storage` → `cluster://storage`, each entry's
> name, description and MIME type unchanged; the server name (`cluster-mcp`) is not in the fixture,
> whose shape is `instructions`, `resources`, `tools`, and is pinned in both eras by
> `test_server_identifies_as_cluster_mcp`.

## Risks

- **Circular imports.** If the core composes by importing the members, while the members import
  core modules (executor, `mcp_tool`), the text constants must sit in import-free leaf modules. The
  composition should also be wherever `TOOL_REGISTRY` is aggregated, which the packaging worker
  decides.
- **Shrinking headroom.** The headroom under the 1,500 cap shrinks to 126 units. A future overlay
  line costs about 50.
- **Alias listing ripples.** The choice of listed versus unlisted aliases ripples into the fixture,
  the shape test and `mutants.py`'s many `rcac://context` URI mutants (`:248-390`). Those mutants
  test `OPEN_RESOURCES` matching, and each needs re-anchoring to `cluster://context`, or to both
  URIs.
- **`fixture_deltas.py` and the moved fixture.** The script reads `harness`, `SERVER_INSTRUCTIONS`
  and `RESOURCE_REGISTRY` from their new import paths. If the fixture also moves (for example to
  `packages/cluster-mcp/tests/`), `git show ${ref}:path` must use the base's old path.
- **Server version.** `serverInfo.version` reports FastMCP's version. That is harmless but
  misleading, so note it for a later cycle rather than fixing it here.
