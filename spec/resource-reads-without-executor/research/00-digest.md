# 00 — Digest

Two briefs, fanned out because the fix touches `src/rcac_mcp/middleware.py`, a high-blast-radius
path (code-plan trigger 2): [`01-fastmcp-resource-read.md`](01-fastmcp-resource-read.md) (FastMCP
4.1.4's `resources/read` path) and [`02-test-harness.md`](02-test-harness.md) (how the suite can read
the resource in every mode and era). They agree; the decisions below settle the two places each left
a choice open.

1. **Hook: `on_read_resource`, in both executor middlewares.** It runs before lookup and before the
   handler, and a value set there reaches a sync handler through AnyIO's copied context, per request
   and isolated under concurrency, in both eras (01 §1–2). `check_resource_access` is rejected: it is
   an authorization hook and cannot wrap the handler.
2. **A read-side error boundary is required.** A `PermissionError` or `RuntimeError` raised from
   `on_read_resource` reaches a modern-era client as `Internal server error`; raised as
   `ResourceError(str(exc))` its text survives in both eras (01 §3, 02 §4). `ToolErrorMiddleware`
   gains `on_read_resource`, re-raising `FastMCPError` and wrapping any other `Exception`.
3. **One resolution path, shared.** The delegate middleware's token → identity → map → executor
   steps move into one private method both hooks call, so a read is refused with exactly a tool
   call's text, and every mutation anchor in `middleware.py` stays unique (02 §7). The same holds for
   the shared middleware's set and the boundary's try/except.
4. **`rcac://context` stays open by an exact URI compare.** `context.message.uri` is a `str`, and
   FastMCP resolves concrete resources by exact string, so `uri in OPEN_RESOURCES` exempts exactly
   the reads that reach the context handler and no other (01 §5). The set is declared in
   `resources.py`, beside the registry, so a resource says itself whether it needs an executor.
5. **A read with no token passes through, as a tool call does** (01 §6, 02 §4): the handler fails at
   `get_executor()` with `No executor configured`, the reason the tool call from that request
   carries. Refusing it early would change the tool path's reason or split the two (GOAL non-goal).
6. **Storage logic: one undecorated helper** in `tools/rcac.py`, called by the tool and the
   resource. The served tool is unchanged as long as name, docstring and `-> StoragePaths` stay
   (02 §6, probed).
7. **Test harness.** `RecordedPopen` (conftest) gains an answer hook so a real `DelegatingExecutor`
   behind real sudo argv returns a parseable `findscratch`/`myquota` per user; `Rendezvous`
   (harness) gains `on_read_resource` so two reads are held in flight together (02 §1–2).
   Refusals are asserted by the reason, not the prefix (`Error calling tool …` vs `Error reading
   resource …`).
8. **R4's open gaps get a test**: a delegate-mode `rcac://context` read with no token, no identity
   claim, an unmapped and a mapped identity, in both pinned eras (02 §3).
9. **Mutants** pin each new contract, and the existing `middleware.py` cases are re-planted against
   the refactored text in the same commit (02 §7).
