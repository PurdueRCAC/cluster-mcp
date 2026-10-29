# GOAL — Reading rcac://storage returns the user's storage paths

> **Origin spec.** The *what* and *why*, the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Edit requirements here; do **not** silently drift them during build.

- **slug:** resource-reads-without-executor
- **kind:** fix
- **appetite:** small

## Problem

The server advertises two resources in its instructions, `rcac://context` and `rcac://storage`.
Since `agents-d-instructions` (landed on `develop` 2026-10-26), `rcac://context` answers in every
mode: it serves the text read once at startup and runs nothing. `rcac://storage` still fails on
every read, in every mode and both protocol eras, so a client gets an error for a capability the
server claims to have.

It fails in two layers, both confirmed on `develop` at `bd89d72` (0.1.3) through an in-memory
harness client over `shared_server(RecordingExecutor('probe'))`, with a `run_command` call on the
same connection reaching the executor:

```
storage read: Error reading resource 'rcac://storage': 'FunctionTool' object is not callable
```

1. The handler (`_storage_paths_resource`, `src/rcac_mcp/resources.py`, the call at line 67) calls
   `storage_paths` from `rcac_mcp.tools.rcac`, which `@mcp_tool` has replaced with a
   `FunctionTool`, an object Python cannot call (`AGENTS.md` § Invariants §7).
2. With the tool's undecorated function patched in for the probe, the same read fails next with
   `No executor configured. Set executor via set_executor() first.`: `storage_paths` runs its
   commands through `get_executor()`, and both executor middlewares (`SharedExecutorMiddleware`,
   `AuthExecutorMiddleware`, `src/rcac_mcp/middleware.py`) install the request's executor in
   `on_call_tool` only, so a resource read carries none. The executor recorded only the tool call.

Fixing the first layer alone would swap one error for the other. Fixing the second must not
weaken § Invariants §1: in `delegate` mode a read that runs commands has to run them as the user
the request's token maps to, never as the server or another user.

**Pre-existing:** yes. Both layers predate the factory: the handler's call landed in `3d30e33`
(2026-02-03) and the tool-call-only middleware hook in `717f636` / `8cc7839` (2026-01-30, 2026-02-01),
none of them in a cycle. Nothing in the suite reads `rcac://storage`.

## Outcome / vision

Reading `rcac://storage` returns the user's storage summary, produced through the executor of the
request that read it, exactly as a `storage_paths` tool call on that request would be: the shared
executor in `ssh` and `local` mode, the mapped user's in `delegate` mode, and in `delegate` mode a
refusal naming the reason when the request carries no usable identity. `rcac://context` and every
tool keep their current behaviour. A test reads `rcac://storage` through a harness client and
asserts what ran and as whom, so the resource cannot silently break again.

## Acceptance criteria (the contract)

- **R1** — WHEN a client reads `rcac://storage` on a server in `ssh` or `local` mode, in either
  protocol era, the read SHALL succeed, run its commands through the server's executor, and return
  the summary in the resource's current text format, naming the same home, scratch and depot paths
  the `storage_paths` tool returns over that executor.
- **R2** — WHEN a client reads `rcac://storage` on a server in `delegate` mode with a token whose
  identity is in the user map, the read SHALL run its commands as the user that identity maps to;
  and WHEN two reads under different mapped identities run concurrently, each SHALL run only as its
  own user (§ Invariants §1, extended to resource reads).
- **R3** — IF a `delegate`-mode read of `rcac://storage` carries no token, a token with no usable
  identity claim, or an identity absent from the user map, THEN the read SHALL fail with an error
  naming the same reason a tool call from that request is refused with, and no command SHALL run.
- **R4** — `rcac://context` SHALL keep its current behaviour: in every mode and both eras it
  returns the text read at startup and runs nothing, and in `delegate` mode it still answers any
  client that can connect, unmapped identities included (§ Invariants §8).
- **R5** — The `storage_paths` tool SHALL be served unchanged: the same name, input schema,
  description and result for the same executor output.
- **R6** — The suite SHALL read `rcac://storage` through a harness client in both protocol eras,
  in shared-executor and `delegate` mode, asserting what ran and as whom, so a handler that cannot
  reach its request's executor fails `verify`.
- **R7** — `AGENTS.md` § Invariants SHALL describe what is true after the fix: §8 no longer records
  `rcac://storage` as a known defect, and §1 states how a resource read gets its request's executor.

## Non-goals (no-gos)

- Generalizing storage discovery beyond the current `findscratch` / `myquota` logic
  (`generalize-storage-discovery`), site extras, or `xdu`: they stay on the roadmap. This cycle may
  leave the undecorated seam that cycle needs, but does not design for it.
- Changing what `rcac://storage` reports or its text format, or adding resources.
- Changing `rcac://context`, the startup site read, or the instructions (settled by
  `agents-d-instructions`).
- Changing how tool calls get their executor or are refused, beyond what sharing that path with
  resource reads requires.
- Cutting release 0.1.4: the release recipe runs after this lands, as its own step.

## Clarifications

- **Q:** The primary seed's criteria target `rcac://context`; is that still in scope? — **A:** No.
  `agents-d-instructions` settled it (2026-10-26, `ROADMAP.md` entry and the seed's own note): it
  needs no executor and the cross-user cache is retired, so the seed's ordering constraint is
  cleared. The seed's R1 is replaced by `rcac://storage`'s; its R2–R4 carry over to that resource.
  R4 here pins `rcac://context`'s current contract so the fix does not regress it. (resolved
  2026-10-28, from the seeds and current `develop`)
- **Q:** Does the absorbed seed's R4 (fix every other module that calls a decorated tool) need its
  own criterion? — **A:** No. A grep of `src/` for imports from `rcac_mcp.tools` outside the tools
  package finds `resources.py` (this fix) and `server.py` (which imports `TOOL_REGISTRY`, not a
  tool); there is no other call site to fix. (resolved 2026-10-28, confirmation read)
- **Q:** Should a `delegate`-mode refusal now also close `rcac://context` to unmapped identities?
  — **A:** No: § Invariants §8 records that as intended (the text is identical for every user and
  readable by every account), and exempting or tightening it is a §5 change outside this seed. R4
  holds it. (resolved 2026-10-28, from the profile; flagged for the gate)
- Drift since filing: the seeds cite `resources.py:151` and `:172`; on `bd89d72` the call is at
  line 67 and the registration at 88, and the primary seed's `rcac://context` traceback no longer
  reproduces (that read now succeeds).

## Related materials

- Seed: [`issues/resource-reads-without-executor.md`](../../issues/resource-reads-without-executor.md)
  (primary); [`issues/storage-paths-resource-typeerror.md`](../../issues/storage-paths-resource-typeerror.md)
  (absorbed).
- `ROADMAP.md`: "Neither advertised resource can be read" and its "Absorbed" sub-entry; Part 0's
  last item, release 0.1.4.
- `AGENTS.md` § Invariants §1 (per-request executor isolation), §5 (delegate mode), §7 (decorated
  tools are not callable), §8 (resources).
- Source: `src/rcac_mcp/resources.py`, `src/rcac_mcp/middleware.py`, `src/rcac_mcp/context.py`,
  `src/rcac_mcp/tools/rcac.py` (`storage_paths`).
- Prior art: `spec/stack-upgrade/research/03-executor-contextvar.md`, `spec/agents-d-instructions/`.
