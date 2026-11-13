# Research 01 — the module cache under a failed load, and the candidate eviction

Scope: `core/capabilities.py` `load()` (`:290-388`), the two members, and import semantics. Every
claim below is from the source (file:line) or from a standalone probe run against this worktree's
code (Python 3.14.6). The probe planted `aaa-good` and a `bbb-broken`, built the `EntryPoint`s from
planted dist-info, and ran a first load, a retry, and a retry without `bbb`, each in a fresh process.

## Verdict

The candidate (evict new modules below `ep.module`, `capability.tools`, and the defining modules of
named strays) fixes the GOAL's case and every family whose registrations come from the capability's
entry-point module, its tools module, or a module that defines a stray tool. It **fails R1 for
registrations made by a module outside those roots**, and fails **open**: the retry *loads* the
capability the first load refused. The realistic shape is a sibling helper in the capability's own
package (as the RCAC member's `resources.py` and `instructions.py` sit beside its `capability.py`).
Two widenings fix it, each local to the snapshot and the cut-back:

- **Package root (P):** widen each root to its top-most ancestor that was not in `sys.modules` at
  the snapshot (`bbb.capability` → `bbb`; `cluster_mcp.rcac.capability` → `cluster_mcp.rcac`, since
  the `cluster_mcp` namespace is already imported). Fixes in-package helpers; still misses a helper
  that is a separate top-level module.
- **H, snapshot after `_scratch()`:** evict every module new since the snapshot. Passed every probe.
  Taking the snapshot after `_scratch()` (`:319`) keeps the core's own lazy import out
  (`fastmcp.server.middleware.dereference`, imported by `FastMCP()` at its server module, line 521, is the only module
  new during `_scratch()` in a fresh process). Its residual risk: it also evicts third-party
  dependencies a capability first imported, which the GOAL's non-goals do not require undoing.

## Probe results (retry line; first-load message in brackets)

| bbb fails by | first load | candidate | P | H |
|---|---|---|---|---|
| tools module registers, then raises | `RuntimeError: boom` | same | same | same |
| listing violation after its tools imported | `its instructions list ['b_more'], which it does not register` | same | same | same |
| stray from a module its tools import directly | `loading it registered ['h_echo'], which are outside bbb.tools` | same | same | same |
| stray via an intermediate top-level module | same stray | **loads bbb** | **loads bbb** | same |
| stray via an intermediate in-package module | same stray | **loads bbb** | same | same |
| odd entry appended by a top-level module the ep imports | `loading it registered a object, not a FunctionTool` | **loads bbb** | **loads bbb** | same |
| odd entry appended by an in-package module | same odd | **loads bbb** | same | same |
| ep module imports a registering helper, then raises | `ValueError: ep boom` | same | same | same |
| tools package `__init__` imports a registering submodule, then raises | `RuntimeError: pkg boom` | same | same | same |

Today's code (all rows): first load names `bbb-broken`; the retry names `aaa-good: its instructions
list ['a_echo'], which it does not register`; the retry without `bbb` "succeeds" with `aaa-good`
holding **no tools**. Under every variant the retry without `bbb` returns `aaa-good` with
`['a_echo']`, registered once (R2), except where the variant already loaded `bbb` on the retry.

## 1. Import semantics

- A module that raises during import is removed from `sys.modules` by the import system; submodules it
  imported first stay, and the parent gains no attribute for it. Probe: after `pk.tools/__init__`
  imported `pk.tools.sub` and raised, `sys.modules` held `pk` and `pk.tools.sub`, and `pk` had no
  `tools` attribute. So today a raising module re-executes on retry. Its already-imported submodules
  and helpers do not.
- After eviction, `import_module(name)` re-executes and **rebinds** the parent's attribute (probe:
  `parent.leaf is new`). But `from parent import child` with the child evicted returns the **stale**
  object through the parent's attribute without re-executing it (probe: `stale old object? True`).
  The load path is safe, since `ep.load()` and `:329` both go through `import_module` by full name.
  Still, the fix should also drop the parent's attribute when it is the evicted module object.
- Thread safety: `load()` is already not thread-safe (`TOOL_REGISTRY` is a bare list). Inside the
  handler, never iterate `sys.modules` at Python level: another thread's import resizes it, and a
  `RuntimeError` there would replace the refusal. Take the copy in C (`set(sys.modules) - known`) and
  use `sys.modules.pop(name, None)`. Evicting a module another thread is mid-importing is outside
  any model this loader has. Say so in the docstring rather than guard it.

## 2. Each refusal family under the candidate

These reproduce the first message, because the code that decides them re-executes under the
candidate's roots: nameless (no code runs), ep.load raises, `_Invalid`, tools import raises, a
stray named directly, name taken (`names` is rebuilt per load), registered twice, a name in
core/owners (`owners` is rebuilt, and earlier capabilities re-register), resource checks, the
listing violation, serve failures (a fresh `_scratch()` per load), and the catch-all.

These do not: **odd** (no `fn`, so no defining module to root on) and **stray reached through a
module outside the roots**. Both let the retry accept what the first load refused (table rows 4-7).
Likelihood: low for top-level helpers, moderate for in-package helpers, because members already
split a capability across sibling modules.

A module imported before the load began is never evicted and never cut (its registrations precede
`start`, `:312`), so the first load and the retry agree. That is not a retry divergence.

One ordering hazard applies to every variant: `:387` calls `_cause(exc)` (an exception's `__str__`,
which is capability code) **after** `:384`. With eviction, a lazy import in that `__str__`
re-executes an evicted module, and its tools stay registered after the failed load (R4). Today the
hole exists only for the module that raised. Build the cause text before the cut-back and eviction,
and keep the cut-back in a `finally`, because `_cause` re-raises `KeyboardInterrupt` (`:170`).

## 3. R4: the first load is unchanged

Eviction runs only in the `except` at `:383`, after the refusal is decided, so what a first load
accepts or refuses, and with what text, is untouched. A successful load evicts nothing. Probe
(fresh process, members): a second `load()` after a successful one registered 0 tools and imported
nothing new. The `:341` scan of the whole registry finds the first load's tools, which is what the
footgun note's "registers nothing new" relies on. With the suite, `conftest`'s `installed()`
imports the members before any test's load, so they are in the snapshot and never evicted.

## 4. What the members import during a load

In a fresh process, `load()` with both members imported exactly nine new modules after
`_scratch()`: `cluster_mcp.{rcac,slurm}` and their `capability`, `instructions` and `tools`, plus
`cluster_mcp.rcac.resources`. There were no extension modules and nothing outside the members. The
candidate would evict only `*.capability` and `*.tools`; P and H evict all nine.

There is one lazy import: the RCAC storage handler imports `cluster_mcp.rcac.tools` inside the
handler (`rcac/resources.py:26`). It resolves through `sys.modules` by full name, so it binds to
whatever the retry imported. Between a failed load and its retry, no server holds that handler,
because a failed load returns nothing and its scratch server is dropped. The core's own lazy imports
(`core/__init__.py:209-343`) sit below `cluster_mcp.core`, which is in the snapshot and never a
root. Re-importing an evicted Rust extension that a planted dependency could pull in (tested with
one) succeeded, so the extension hazard of H is library-specific and was not reproduced.

## 5. KeyboardInterrupt

The handler at `:383` catches it, so the eviction also runs for an interrupted load (a bonus, not
contracted: GOAL Non-goals). It does not cover these windows: an interrupt inside the handler itself
(before `:384`, or partway through the eviction loop); one between recording a root and the
import it guards, which is harmless; and one landing in the import system's own cleanup of a
failing module. `issues/capability-reload-after-interrupt.md` owns these.

## 6. Lines touched, against the sibling cycle

The sibling cycle changes `:330-334` and `:341`, and its range runs to `:349`.

- **H:** one snapshot line between `:319` and `:320`, plus the handler `:383-387`. It touches nothing
  of the sibling's.
- **P:** the same, plus recording `ep.module` before `:325`/`:326` and `capability.tools` between
  `:328` and `:329`, all outside `:330-349`.
- **Candidate as specified:** it records the strays' modules at `:333-337`, **inside** the sibling's
  range. Computing them in the handler from `TOOL_REGISTRY[start:]` instead would avoid that, but it
  reads `.fn.__module__` off entries the sibling is retyping, and could raise inside the handler.
  P and H need neither.

Several `tests/mutants.py` anchors sit in `:383-387`. Any variant moves them (GOAL Notes).

## 7. Weighing G (replay)

Replay needs module-level state that outlives a load: for each entry point, the registry slice its
`ep.load()` and its tools import produced. It must also avoid double registration when the module
that raised re-executes on retry (the import system already dropped it), and it depends on order
when a helper shared between capabilities was first imported under a different one. That is more
state and more cases than eviction, for the same outcome.
