# 03 — A non-hollow instructions↔registry cross-check (R4)

Scope: how a test extracts tool names from `SERVER_INSTRUCTIONS` robustly, what it compares them
to, how it fails, and what happens when a later cycle composes the instructions dynamically.
Prototyped against the base text on 2026-10-16.

## What "naming a tool" looks like in the text today

`SERVER_INSTRUCTIONS` (`server.py:64–130`) names tools in three shapes:

1. **List entries** `- name: description`, one per tool, under the family headings (General Tools,
   RCAC-Specific Tools, Slurm …). All 25 registered tools appear exactly this way.
2. **Backticked prose** — `` `doc_search` ``, `` `doc_load` ``, `` `myquota` ``,
   `` `storage_paths` ``, and one non-tool: `` `findscratch` `` (a shell command on the cluster).
3. **Bare snake_case** tokens inside descriptions (`doc_search results`).

Lines that look like entries but are not tools: `- Home: /home/<user>`, `- Scratch: …`,
`- Depot: …` (capitalised) and `- rcac://context: …` (the identifier is followed by `//`, not
whitespace).

## Extraction (prototyped)

```python
listed = set(re.findall(r'^- ([a-z_][a-z0-9_]*):(?=\s)', text, re.M))
ticked = set(re.findall(r'`([^`\s]+)`', text))
snake  = set(re.findall(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', text))
```

On the base text: `listed == registry` (25 = 25, both directions empty), `ticked =
{myquota, findscratch, doc_search, storage_paths, doc_load}`, `snake − registry = ∅`. The
lowercase-only, whitespace-lookahead entry pattern excludes `Home`/`Scratch`/`Depot` and
`rcac://context`. `CLUSTER_SCRATCH` is uppercase and never matches the snake pattern.

## The assertions, and what each catches

| Assertion | Catches |
|---|---|
| `registry ⊆ listed` | a registered tool the instructions omit (R4 "list every tool"); also an extraction that silently finds nothing (fails red, not green) |
| `(listed ∪ ticked ∪ snake) − registry ⊆ NON_TOOL_TERMS` | an instruction naming an unregistered tool in any of the three shapes (R4 "name no tool absent") — the exact post-strip failure: text still says `doc_search`, registry does not |
| `NON_TOOL_TERMS ∩ registry = ∅` and every `NON_TOOL_TERMS` entry occurs in the text | the allowlist being used to launder a tool name, or rotting |
| no match of `(?i)\bdoc(?:s|umentation)?\b` nor `\bdoc_` | residual documentation-search guidance (R4 "no documentation-search guidance"), even as prose without a tool name |
| `len(TOOL_REGISTRY) == len({t.name …})` and registry non-empty | duplicate registration masking a dropped one; an import-order bug that empties the registry |

`NON_TOOL_TERMS = {'findscratch'}` today.

## Which text to check

FastMCP exposes what clients receive as `FastMCP.instructions`; `create_mcp_server('none')
.instructions == SERVER_INSTRUCTIONS` today (verified), and `AUTH_MODES['none']()` returns `None`, so
construction needs no secret and no network. The test runs every assertion over **both** the
`SERVER_INSTRUCTIONS` constant (R4's wording) and the served `create_mcp_server('none').instructions`
(what a model reads), parametrised. If a later cycle composes the served text, the served case keeps
guarding what clients actually get.

## Mutation evidence (what proves it is not hollow)

On the base tree, the cross-check is red only on the guidance assertion (doc words present) and
green on set equality — correct, because the base is internally consistent. The build must show it
red in each failure direction before trusting green:

- remove `from rcac_mcp.tools import docs` but leave the text → `listed − registry = {doc_search,
  doc_load}` → red;
- delete one non-docs entry line (e.g. `- sinfo: …`) → `registry ⊄ listed` → red;
- add `` use `doc_search` `` back in prose → red (ticked + doc-word assertions).

## Limits (accepted, recorded)

- A tool whose name is a plain lowercase word (`slist`, `sinfo`, `myquota`) mentioned **unticked in
  prose** after it is removed cannot be distinguished from English. The list-entry format is the
  contract; the `rename-to-cluster-mcp` and `agents-d-instructions` cycles own any restructuring.
- **Dynamic composition** (`agents-d-instructions`): appending administrator-written
  `/etc/agents.d` text would feed backticked shell commands (`` `module load` ``) into the ticked set
  and break the allowlist model; the planned "short generic core" naming *tool families* would break
  `registry ⊆ listed`. That cycle must scope the cross-check to the server-authored core and restate
  "list every tool" for its new shape. The test needs no hook for it now (no speculative
  preparation, AGENTS.md § Direction); the seed gets a one-line note so the constraint is not
  rediscovered.
