---
status: adopted:resource-reads-without-executor
kind: fix
appetite: small
lane: public
---

# Resource reads never receive an executor

## Problem

Both executor middlewares set the per-request executor in `on_call_tool` and nowhere else
(`SharedExecutorMiddleware` and `AuthExecutorMiddleware`, `src/rcac_mcp/middleware.py`). A resource
read is not a tool call, so its request context holds no executor, and a resource handler that
calls `get_executor()` raises. `rcac://context` (`_cluster_context_resource`, `resources.py`) does
exactly that, so reading it fails in every execution mode:

```
tool call: Outcome(is_error=False, text='{"stdout":"probe|echo hi", …}')
resource error: MCPError Error reading resource 'rcac://context': No executor configured. Set executor via set_executor() first.
```

That is a `shared_server(RecordingExecutor(...))` from `tests/harness.py`, in memory: the tool call
on the same connection reaches the executor, the read does not, and the executor records only the
tool call. The same holds in both protocol eras on FastMCP 4, and the `stack-upgrade` research
probed it on FastMCP 2.14 with the same result (`spec/stack-upgrade/research/03-executor-contextvar.md`).

`SERVER_INSTRUCTIONS` advertises `rcac://context`, so a client that reads it gets an error for a
capability the server claims. Nothing in the suite reads a resource. (`rcac://storage` fails earlier,
on a separate defect: `storage-paths-resource-typeerror`.)

## Why it was deferred

Found by `stack-upgrade`'s research while checking that § Invariants §1 holds under FastMCP 4's
per-message middleware. Fixing it was outside that cycle: it changes what the executor middlewares
hook, in the coupled core, and a refactor that keeps every contract intact was the wrong vehicle. It
fails closed (nothing runs, and no request reaches another's executor), so it is filed in the
public lane.

**Pre-existing:** yes, present on `develop` at `3d010ec` and on `main`.

## Outcome / vision

Reading `rcac://context` returns the cluster context through the executor of the request that read
it, exactly as a tool call would: shared in `ssh`/`local` mode, the mapped user's in `delegate`
mode, and a refusal naming the reason when the request carries no identity. A test reads each
resource through a harness client and asserts what ran and as whom.

One ordering constraint: once a read reaches an executor in `delegate` mode, the process-global
context cache (`AGENTS.md` § Invariants §8, `context-cache-cross-user`) becomes reachable across
users through the resource. Retire the cache first, or in the same cycle (`agents-d-instructions`
absorbs it and reads the files once at startup, which may settle this seed too).

## Sketch of the acceptance criteria

- **R1** — WHEN a client reads `rcac://context` on a server in `ssh` or `local` mode, the handler
  SHALL run through the server's executor and return its result.
- **R2** — WHEN a client reads a resource in `delegate` mode, the read SHALL run as the user its
  token maps to, and IF the request carries no token or an unmapped identity, THEN it SHALL be
  refused with the same reason a tool call gets, with nothing run.
- **R3** — Two concurrent reads under different delegate identities SHALL each run as their own
  user (the § Invariants §1 contract, extended to reads).
- **R4** — A test SHALL read each served resource through a harness client, so a handler that
  cannot reach an executor fails the suite.

## Notes

- Related: `issues/context-cache-cross-user.md`, `issues/agents-d-instructions.md`,
  `issues/storage-paths-resource-typeerror.md`; `spec/stack-upgrade/research/03-executor-contextvar.md`.
- FastMCP 4's `Middleware` has a read-resource hook beside `on_call_tool`; whether the executor
  middlewares should take it, or the handlers get their executor another way, is the plan's call.
- Found by: `stack-upgrade` research (2026-10-17), filed at P7.
- 2026-10-17: absorbs [`storage-paths-resource-typeerror.md`](storage-paths-resource-typeerror.md)
  in `ROADMAP.md`: that handler needs a read's executor too, so R4's read of each served resource
  covers both fixes.
- 2026-10-26: `agents-d-instructions` settled `rcac://context` (served from the startup read, no
  executor; the cache retired). The remainder is `rcac://storage`, which still calls a tool object
  and needs an executor (`storage-paths-resource-typeerror`, absorbed).
