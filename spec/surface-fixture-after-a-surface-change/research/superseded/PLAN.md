# PLAN — The served-surface fixture follows a deliberate surface change

> **Superseded 2026-11-12.** This is the recorder design (a surface command, a type-strict walk with
> two carve-outs, a per-set projection check) that review cycles 1–3 graded in `../../REVIEW.md`.
> The maintainer re-shaped the GOAL to a plain snapshot test the same day (`../../GOAL.md`,
> Clarifications); the current design is `../../PLAN.md`. Kept unedited below this note, with its
> gate scripts in `verify/` beside it; paths it names under `spec/…/verify/` are now here.

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). No `research/` (lean path, `appetite:
> small`); the feasibility probes are recorded in § 4. Every design element traces to a GOAL R-ID.

## 1. Summary

The harness's `served_surface` becomes a whole-surface recorder: it takes each listing as the raw
JSON the client receives (every key, any depth) plus the server info and the capabilities object.
A maintained command, `bin/record_surface.py`, records the surface in both protocol eras under
`bin/sandbox.sh`, refuses when the eras differ, writes the fixture in one canonical byte form and
prints the delta against the committed fixture as commit-body lines. `tests/test_surface.py` drops
`TOLERATED` and the shape test for one generic, type-strict deep comparison with two named
carve-outs: the server-info version, read from a recorded distribution (M1), and the capabilities
object, recorded per era (deviation row 1). The fixture is re-baselined once from the command, and a
check proves it adds nothing but the five tolerated kinds to what `0bfacae` pinned. Four phases; no
file under `packages/` changes.

## 2. Design

### 2.1 The fixture (`tests/fixtures/served_surface.json`)

Written only by the command, as `json.dumps(fixture, indent=1, sort_keys=True) + '\n'` (today's
layout, so the mutation runner's text anchors keep their indentation). Top-level keys:

| Key | Holds |
|---|---|
| `instructions` | the served instructions, as today |
| `tools` | `{name: entry}`: each `tools/list` entry as received, every key at any depth, the `name` moved to the map key |
| `resources` | `{uri: entry}`: each `resources/list` entry, the `uri` moved to the map key |
| `resourceTemplates` | `{uriTemplate: entry}` from `resources/templates/list` (empty today) |
| `prompts` | `{name: entry}` from `prompts/list` (empty today) |
| `serverInfo` | every field literally, but `version`, recorded as `{"distribution": "<dist>"}` (M1) |
| `capabilities` | `{"legacy": {…}, "modern": {…}}`: the advertised capabilities object per era (deviation row 1) |

Entries are keyed, so listing order is not pinned (Non-goal; `tests/test_capabilities.py` pins it).
Today's run puts `"_meta": {"fastmcp": {"tags": []}}` first in each tool and resource entry, and
`serverInfo` is `{name: cluster-mcp, icons: [{src: /static/purdue-favicon.ico, …}], version: …}`.

### 2.2 The recorder (`tests/harness.py`)

`served_surface(server, era=None) -> dict` keeps its name and its consumers' keys (`tools`,
`resources`, `instructions`; `tests/test_capabilities.py`, `test_literal_args.py`,
`test_storage_resource.py`, `test_probe_startup.py` read only those). Over `in_memory(server, era)`:

- Each listing through `client.session.send_request(<List…Request>(cursor=…), TypeAdapter(dict[str,
  Any]))`, following `nextCursor` until none: the raw result dict, so a key no SDK model declares is
  still recorded (a parsed `Tool` drops unknown keys: `extra` is unset on `mcp.types.Tool`). Each
  entry goes into its map by its identity field, which the entry then omits; an identity served twice
  raises `ValueError` naming it (a dict would otherwise hide the duplicate). Entries keep served order
  (`test_storage_is_served_only_with_the_rcac_capability` reads the resources' order).
- Listing envelopes (`nextCursor`, the modern era's `_meta` serverInfo stamp, `cacheScope`, `ttlMs`,
  `resultType`) are not recorded: they are per-response protocol fields, not entries (deviation row 6;
  the stamp's name stays pinned by `test_server_identifies_as_cluster_mcp`).
- `serverInfo` and `capabilities` from the raw result too, never a parsed model (`Implementation` and
  `ServerCapabilities` leave `extra` unset and would drop an undeclared key; review finding 1): in the
  legacy era a raw `initialize` re-sent on the connected session through the same `send_request`
  route, its `serverInfo` and `capabilities`; in the modern era a raw `server/discover`, its
  `capabilities` and the `io.modelcontextprotocol/serverInfo` entry of its `_meta`, where that
  revision delivers the server info. Both routes were probed (§ 4). The raw-to-record step is a pure
  function (`surface_record(listings, identity, era)`) so a unit row can feed it planted raw results
  carrying undeclared keys at any depth.
- Pagination: `nextCursor` is followed until absent; a recorder row builds a server with
  `list_page_size=1` (FastMCP 4.1.4 accepts it) and requires the whole of each listing (review
  finding 2).
- Through `json.loads(json.dumps(…))`, as today. The docstring's touchpoint list gains
  `ClientSession.send_request` with a `TypeAdapter`, `Client.server_info`, `Client.server_capabilities`
  and the four list request types. `CONTEXT_URIS`, `SITE`, `STORAGE_URIS`, `scheme` stay exported:
  the R6 check imports the old `tests/test_surface.py`, which imports them.

### 2.3 The comparison (`tests/test_surface.py`, pure functions)

One engine, `surface_differences(expected, served) -> list[Difference]` (path, kind
`added|removed|changed`, old, new), recursing through every dict key and list index:

- **Type-strict:** values are equal only when their JSON types match (`bool` is not `int`, `1` is not
  `1.0`, `null` is not a missing key); dicts by key union; lists by position, a longer or shorter list
  reported item by item.
- **No tolerated list, no key, depth, listing or era skipped.** Every top-level key is compared,
  known or not.
- **Rendering** (`surface_violations(expected, served) -> list[str]`): an entry added or missing is
  `tool added: X` / `tool missing: X` (`resource`, `resource template`, `prompt` likewise; a rename
  is one missing and one added); inside an entry, `<label>: tool entry gained 'K'` / `lost 'K'` at its
  root, else `<label>: <path> gained 'K'`, `lost 'K'`, `differs: <old> -> <new>` (values as `repr`,
  cut to 60 characters); `instructions differ`; `serverInfo: …`, `capabilities: …`; `surface gained
  top-level key 'K'` / `lost`. `<label>` is the tool name, `resource <uri>`, `resource template <t>`,
  `prompt <name>`. Paths join identifier keys with `.`, quote any other key as `['…']` and index lists
  as `[i]`.
- **Delta** (`delta_lines(old, new) -> list[str]`): one `- <path from the root>: added|removed|changed`
  line per difference, entry-level differences collapsed to the entry (`- resources['rcac://storage']:
  removed`), sorted, no values: a commit body's list. Empty means `- no difference`.
- **The two carve-outs, named beside the comparison with their causes** (R3), applied by
  `expected_surface(fixture, era) -> (expected, problems)` before comparing:
  1. `VERSION_SOURCE` (M1): the fixture's `serverInfo.version` must be `{"distribution": d}`; the
     expected value is `importlib.metadata.version(d)`. A literal there, an unknown key in it, or `d`
     not installed is a problem, never a pass. It resolves that one path only.
  2. `ERA_CAPABILITIES` (deviation row 1): the fixture's `capabilities` must be keyed by exactly
     `legacy` and `modern`; the expected value is the entry for `era`. Only that path.
- `version_source(served_version) -> str`: the one distribution of `VERSION_SOURCES = ('cluster-mcp',
  'fastmcp-slim')` installed at the served version (FastMCP reads its own from `fastmcp-slim`; the
  rename cycle will serve the core's); none or both raise, naming the value and the candidates.
- `era_violations(legacy, modern) -> list[str]`: the two records compared with the comparison above,
  `capabilities` excepted on both sides (the second carve-out's other face; nothing else is).
- `to_fixture(legacy, modern) -> dict`: the legacy record with `capabilities` keyed by era and
  `serverInfo.version` replaced by `{"distribution": version_source(…)}`; `fixture_bytes(fixture)`
  is the canonical form.
- `set_violations(expected, served) -> list[str]`: the per-set check (R2's last sentence, M2):
  `instructions` dropped from both (they vary by set and are pinned by `test_instructions.py` and
  `test_capabilities.py`); each listing of `expected` cut to the entries `served` has; everything else
  compared whole. An entry the set serves that the fixture lacks is `added`; an entry the set does
  not serve is not a difference.

### 2.4 The command (`bin/record_surface.py`)

Documented form (§ Commands): `bin/sandbox.sh uv run --locked --exact python "$PWD/bin/record_surface.py"`
(`--exact`: an extra distribution in the environment would be served and recorded; finding 13).
It sits beside `bin/audit_lock.py` and `bin/sdist_hygiene.py`; outside `tests/`, the suite's
static launch check does not read it, and it launches only `git` (before anything else).

1. Refuses, writing nothing, unless `CLUSTER_MCP_SANDBOX` names a directory (outside the sandbox,
   naming `bin/sandbox.sh`) and unless `PYTEST_CURRENT_TEST` is unset (naming that variable).
2. Reads the base: `--against FILE`, else `git -C <repo> show HEAD:tests/fixtures/served_surface.json`
   (absent at HEAD: an empty base, every path added).
3. Replaces `subprocess.Popen` with a refuser carrying `test_fence = True` (the unit guard's posture:
   the harness fence opens, nothing can launch), then `record(era)` for `legacy` and `modern`:
   `served_surface(create_mcp_server('none', site=SITE), era=era)`, the full installed capability set.
   `record` is a module-level seam the cycle's drive replaces.
4. `era_violations` non-empty: refuse, printing each differing path, exit 1, write nothing (R4).
   `version_source` finding none or both: refuse, naming `serverInfo.version`, the served value and
   both candidates.
5. `to_fixture`; then, for each era, `surface_violations(expected_surface(fixture, era), record)`
   must be empty (the fixture it writes passes, R5), else refuse.
6. Writes `fixture_bytes(fixture)` to `--out FILE` (default the fixture path, from the script's own
   location; the sandbox moved the working directory), prints `delta_lines(base, fixture)` on stdout
   and a one-line summary on stderr. Exit statuses follow `bin/audit_lock.py`.

The command never runs in the suite, the profile's `verify`, the release recipe's `gate` or CI (R1):
`test_nothing_runs_the_surface_command` reads invocations, not prose (finding 5: the docstrings R8
rewrites name the command): in `tests/*.py`, by AST, any call or import that reaches the command
(an argv or shell string naming its file in a `subprocess`/`os`/`asyncio` launch, `runpy`, an
`import record_surface`, an `importlib` load of it), docstrings and comments exempt; in
`.github/workflows/*.yml`, every `run:` line; in `AGENTS.md`, the profile's `verify` cell and the
release recipe's `gate:` list; in `pyproject.toml`, every value. A control plants an invocation in
each kind of place, and a docstring mention that must pass (`test_command_scan_catches_planted_runs`).
Nothing in the suite writes the fixture either: every gate mode checks the working tree's fixture
against the staged one before and after each step (finding 4).

### 2.5 The suite (`tests/test_surface.py`), all `unit`

- `test_served_surface_matches_baseline`: `surface_violations(expected_surface(load_fixture(), ERA),
  served_surface(create_mcp_server('none', site=SITE)))` is empty, and the carve-out problems are
  empty. Replaces the untitled-tools assertion (titles are in the fixture now).
- `test_surface_fixture_is_the_commands_form`: the file's bytes are `fixture_bytes(load_fixture())`,
  `serverInfo.version` is the distribution form, `capabilities` is keyed by exactly the two eras.
  Replaces `test_surface_fixture_is_the_baseline_shape`, which is retired (R7).
- `test_surface_check_catches_drift` (R7): one matrix, parameter ids `<kind>-<change>`, every kind
  R3 names planted as an addition and as a removal or change, on the served side or the fixture side
  (`spec/…/verify/surface_checks.py` lists the required ids): tool, argument, schema key at depth,
  annotation hint, tool-entry key (`icons`, `_meta`, `execution`), resource, resource key, resource
  template, prompt, server-info field, capabilities field, top-level key, description, instructions,
  value type (`false` to `0`), list order, list item. Each row asserts the plant landed, both sides
  compare clean with themselves, and a violation names the entry and the field path.
- `test_set_check_catches_drift` (R7's last sentence): the same rows through `set_violations`,
  but for removing a whole entry (a set may lack one) and the instructions, plus `subset-passes`.
- `test_recorder_sees_what_the_server_starts_serving` (R2): servers built by `create_mcp_server` and
  planted through FastMCP's public API or a listing middleware, never by touching the recorder: a tool
  with `icons`, `meta` or `annotations`; a resource with a `title` or `annotations`; a prompt; a
  resource template; a server `version` or `website_url`; an `experimental` capability; a server
  with `list_page_size=1` (every entry still recorded). Each appears in `served_surface` and as a
  violation against the fixture. A listing that serves a name twice makes the recorder raise. And
  `surface_record` fed raw results with an undeclared key in a tool entry, a resource entry, the
  server info, the capabilities and inside `capabilities.tools` keeps each (the server shares the
  client's models, so no server can be planted to send one; the pure step is what a raw route buys).
- `test_version_carve_out_accepts_only_the_served_version` and
  `test_era_carve_out_accepts_only_the_capabilities`: each accepts its own path and value, and fails
  a wrong value, a literal fixture value, a missing era or distribution, and the same shape at any
  other path.
- `test_era_check_refuses_every_other_difference` (R4): eras differing only in `capabilities` pass;
  differing in a tool, a resource, `serverInfo` or `instructions` fail, naming the path.
- `test_delta_lists_every_changed_path` (R5): added, removed and changed paths, one line each.
- `test_nothing_runs_the_surface_command`, `test_command_scan_catches_planted_runs` (R1).
- `test_every_capability_set_serves_the_fixtures_entries` (R2, M2): for each set in
  `test_capabilities.SETS` (imported, not copied), `set_violations(expected_surface(fixture, ERA),
  served)` is empty; the loop asserts it saw every set id, so a set dropped from it fails.

### 2.6 `tests/mutants.py` — only what R7 needs (sibling cycles own its runner and sweep)

- `RUN_COMMAND_ENTRY` and `recorded()` re-anchor on the new entry's first key: `'  "run_command":
  {\n   "_meta": {'`, the plant inserting `"annotations": …,` before `"_meta"`.
- The `why` of six cases follows the new messages: `annotation-hint-flipped` (`run_command:
  annotations.readOnlyHint differs: False -> True`), `annotation-hint-dropped` (`annotations lost
  'destructiveHint'`), `annotation-hint-added` (`annotations gained 'idempotentHint'`), and
  `title-on-one-tool`, `title-on-every-tool`, `title-at-add-tool` (`run_command: title differs: 'Run
  Command' -> …`: the fixture holds the derived title now, so a set title is a change, not a gain).
  The comments above the two groups follow. The retarget's reason goes in the P1 commit body
  (§ Testing). The other five surface cases keep their `why` (`description differs`, `tool entry
  gained 'annotations'`, `tool entry lost 'annotations'`).

### 2.7 The re-baseline and its record (R5, R6)

P1 writes the fixture with the command. `spec/…/verify/rebaseline_check.py` (drafted, dry-run on a
prototype record) imports `tests/test_surface.py` as it was at `0bfacae`, projects the new fixture
onto the fields that version recorded, and requires its `surface_violations` to be empty; it prints
the five kinds' occurrences, checks each of the 72 argument descriptions against its `Args:` line,
and lists every field entering as served (`capabilities`, `prompts`, `resourceTemplates`,
`serverInfo`, `tools.<each>._meta`, `resources.<each>._meta`). Its output and the command's delta
against HEAD go in the P1 commit body, and **the landing squash commit's body carries both** (R5:
the change reaches `develop` with its delta list).

### 2.8 Documentation (R8)

`AGENTS.md` §9's pin bullet and § Testing's `tests/test_surface.py` entry describe the method (the
command, what the fixture records, the two carve-outs, a change lands as the command's fixture diff
with its delta list in the commit body) in place of the hand-edit rule, the delta history and the
open question; § Commands lists the command; the `test_protocol.py` entry stops saying the server's
name is outside the fixture. The docstrings of `tests/harness.py` and `tests/test_surface.py` follow.
If the maintainer answers M3 with (a), one line joins § Invariants' high-blast-radius list, after
the `probes.py` entry: `- tests/fixtures/served_surface.json — the served-surface pin (§9); a change
here re-pins what every client is served`, and P4 carries it.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `bin/record_surface.py` (2.4), sandbox and pytest refusals; `fixture_bytes`; the no-run scan; `command_drive.py` determinism and refusal drives |
| R2 | raw-listing recorder (2.2), fixture keys (2.1), `VERSION_SOURCE` carve-out, `test_recorder_sees_what_the_server_starts_serving`; per set: `set_violations`, `test_every_capability_set_serves_the_fixtures_entries` |
| R3 | `surface_differences` / `surface_violations` (2.3), no `TOLERATED`; carve-outs named with causes and pinned by their two controls |
| R4 | `era_violations` and the command's refusal; the baseline test runs in each era's suite pass; the era proof (`surface_checks.py era-proof`) |
| R5 | `delta_lines`; `--against`; the command's self-check that its fixture passes; `command_drive.py delta`; the landing body (2.7) |
| R6 | `rebaseline_check.py` (2.7), its output in the P1 commit body |
| R7 | `test_surface_check_catches_drift` and `test_set_check_catches_drift` (required ids in `surface_checks.py`), shape test retired, `tests/mutants.py` re-anchored (2.6) and its surface cases re-run; the sweep (§ 6) |
| R8 | `AGENTS.md` §9, § Testing, § Commands (2.8); `docs_check.py docs` |

## 3. Invariant gate (AGENTS.md constitution check)

Walked before design (gate #1) and against this draft (gate #2). Touched: §9 (the served surface,
human gate) and § Conventions. No path on the high-blast-radius list is touched (`tests/`,
`bin/record_surface.py`, the fixture and docs only; `bin/sandbox.sh` is used, not edited), so
research trigger 2 does not fire; `server.py` and the `instructions.py` texts are not edited.

- **§9, the served surface is part of the API.** Nothing served changes (Non-goal): no file under
  `packages/` changes in any phase (`gate.sh files`), and R6's check proves the re-baseline pins the
  same names, schemas, descriptions, resources and instructions. §9's same-commit rules (instructions
  text and README inventory) are untouched because no tool changes. The pin's bullet is rewritten to
  the method (R8); the server's name, which §9 says only `test_server_identifies_as_cluster_mcp`
  pins, is now also in the fixture's `serverInfo`, and the test stays (it pins the modern era's
  per-result stamp, which the fixture does not record).
- **§9's base composed from the capabilities served.** The per-set check compares entries only;
  the instructions per set stay with `test_instructions.py` and `test_capabilities.py`.
- **§7/§8 listings keep their own order.** The fixture keys entries; served order stays pinned by
  `test_capabilities.py`, and `served_surface` keeps served order for it.
- **§ Conventions.** Every new test carries `@pytest.mark.unit` (in-memory clients, no launch);
  no spec ids in `tests/` or `bin/`; comments declarative; `tests/harness.py` stays the only test
  module importing the stack (the command imports only `harness` and `test_surface`); a CLI drive
  runs under `bin/sandbox.sh` (the command refuses otherwise); the verify, gate and CI lists do not
  change, and the new rows run in the fourth command of each era (`tests/test_surface.py`, not one
  of the named modules); a retarget of a mutation case records its reason in the commit body.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| 1. **The capabilities object is recorded per era** (`capabilities: {legacy, modern}`), and R4's refusal excepts that one key. **Needs a GOAL clarification at sign-off: it bends R4 as worded and M4's "under R4's both-eras rule".** | The stack advertises a different object per protocol revision for the same server: legacy `listChanged: true` on prompts, resources and tools; modern `listChanged: false` and `extensions: {"io.modelcontextprotocol/ui": {}}` (FastMCP's low-level server: the SDK's pre-2026 sieve strips `extensions`; probed on every set in `SETS`, § 4). Under R4 as worded the command could never write the fixture. | Leaving capabilities out drops M4. Normalising the fields loses the modern `extensions`. Changing the server is a Non-goal and the difference is the protocol's. Recording both keeps every field pinned in its era, and every other field still refuses on any era difference. |
| 2. R1's "no … gate step SHALL run the command" read as the profile's `verify`, the release recipe's `gate` and CI. | The cycle's phase gates (`spec/…/verify/`) must drive the command to show R1, R4 and R5; they write only to a scratch `--out`, never the fixture. | Proving R1/R4/R5 from unit rows alone would leave the command's glue undriven (code-plan: verify by driving the CLI). |
| 3. `VERSION_SOURCES = ('cluster-mcp', 'fastmcp-slim')`, a named candidate list. | M1 records "the installed distribution it comes from"; `fastmcp` and `fastmcp-slim` are both installed at the served version, so a search of every distribution cannot choose. | A literal version pin is ruled out by M1; a preference order would attribute a coinciding version silently, where two matches here refuse. |
| 4. Listings, server info and capabilities recorded from raw results (`send_request` with a `dict` `TypeAdapter`; a re-sent raw `initialize` in the legacy era, a raw `server/discover` in the modern), new harness touchpoints. | `mcp.types.Tool`, `Resource`, `Implementation` and `ServerCapabilities` leave `extra` unset, so a parsed object drops a key its model lacks; R2 wants a key the server begins to serve to show with no recorder change. | Dumping parsed models (today's route) is equivalent only while client and server share an SDK model. |
| 5. Each entry's identity field (`name`, `uri`, `uriTemplate`) is recorded as its map key, not inside the entry. R2 read as "every key", the identity recorded once. | `test_aliases_follow_every_primary_uri` compares an alias's entry with its target's; with `uri` inside they always differ. A rename still shows as one removed and one added. | Keeping it inside would rewrite a §8 test outside this cycle's scope. |
| 6. Listing envelopes (`nextCursor`, modern `_meta`, `cacheScope`, `ttlMs`, `resultType`) are not recorded. R2's list read as entries, listings, capabilities and server info. | They are per-response protocol fields, era-specific by revision; the modern `_meta` stamp's name is pinned by `test_server_identifies_as_cluster_mcp`. | Recording them would trip R4 on every run (they exist in one era only). |

Rows 2–6 read R1 and R2 without changing what they require; row 1 changes what R4 requires for one
key and goes to the sign-off as a GOAL clarification. No row bends a CRITICAL invariant.

## 4. Rabbit holes (resolved)

Lean path: no fan-out (`appetite: small`; triggers 1 and 2 do not fire). Trigger 3 fires (the
deliverable is a gate): the adversarial review below ran. Probes, run in a throwaway lab under
`$TMPDIR` against this worktree's locked environment (FastMCP 4.1.4, SDK 2):

- **What the stack serves beyond the old recorder.** Every tool and resource entry carries
  `_meta: {fastmcp: {tags: []}}`; `serverInfo` is `{name, version: 4.1.4, icons}` in both eras;
  templates and prompts are empty; no listing paginates. Tools, resources, instructions and server
  info are identical in the two eras; **the capabilities object is not** (deviation row 1), on every
  set in `SETS`, and is the same across sets.
- **Can the client see a key its model lacks?** Not through parsed models (`extra` unset); through
  `session.send_request(…, TypeAdapter(dict))`, the raw result: deviation row 4. The same route
  returns the raw `initialize` result on a connected legacy session (`protocolVersion`,
  `capabilities`, `serverInfo`, `instructions`) and the raw `server/discover` result in the modern
  era (`capabilities`, `supportedVersions`, the serverInfo stamp in `_meta`).
- **Where FastMCP's version comes from.** `fastmcp/__init__.py` reads `fastmcp-slim`, falling back to
  `fastmcp`: deviation row 3.
- **Does a prototype record satisfy R6?** A prototype recorder in the planned shape wrote 46,719
  bytes, byte-identical across two runs; `rebaseline_check.py` on it: no difference beyond the five
  kinds (`additional-properties` and `derived-title` on 24 tools, `argument-description` on 18,
  `output-defs-inlined` on 2, `output-model-description` on none); all 72 argument descriptions are
  their `Args:` lines; six field groups enter as served. The mutation anchor `"run_command": {\n
  "description":` does not survive the re-shape (`_meta` sorts first), hence 2.6.
- **Adversarial design review** (trigger 3, one pass at `appetite: small`, a fresh subagent given
  GOAL, this PLAN and the drafted gates). Thirteen findings, all folded:
  1 (HIGH) server info and capabilities were to come from parsed models, blind to an undeclared key:
  now raw (2.2, row 4) with pure-step rows; 2 pagination unexercised: a `list_page_size=1` row and a
  sweep mutant; 3 the ids gate counted skipped or xfailed rows: `surface_checks.py ids` now requires
  each id to pass, in both eras, from a JUnit report; 4 nothing caught the suite or a drive writing
  the fixture: every gate mode checks it against the staged copy around each step, and two sweep
  mutants plant such a write; 5 the no-run scan would trip on R8's docstrings: it reads invocations
  only; 6 `files` watched only `packages/`: it covers `uv.lock` and `pyproject.toml` too; 7 the version
  drive could not tell the candidates apart: a `version-core` drive and a specific refusal phrase; 8
  missing sweep mutants: added to § 6; 9 `both_eras` inherited the shell's era: each pass names its
  era; 10 `test_probe_startup.py` joins p1; 11 a `grep` error read as absence: `absent` checks the
  status; the sweep marker is an argv word; 12 the re-baseline delta depended on when the gate ran:
  the drive prints it against the `0bfacae` fixture; 13 `uv run --locked` keeps extra packages:
  `--exact` in the documented command and the drive. Checked and holding: determinism (FastMCP sorts
  `_meta.fastmcp.tags`), the per-set check on all five sets, the sandbox's environment for the
  drives, the 11 mutation cases' re-plant and new `why` strings, R6's projection, deviation rows.

## 5. Risks & open questions

- **GOAL clarification (R4/M4):** deviation row 1. If the maintainer prefers otherwise (drop the
  capabilities, or a different record), only `ERA_CAPABILITIES`, `to_fixture` and their controls move.
- **Raised per the Non-goals: `serverInfo.icons[0].src` varies with `MCP_BASE_URL`**, which `oidc`
  auth requires; `server.py` reads it at import. The fixture pins the unset value (the sandbox unsets
  it; the unit guard blanks it only after import), so a developer shell exporting it fails
  `test_served_surface_matches_baseline` at `serverInfo.icons[0].src`. Not changed here (Non-goal:
  per-auth-mode surfaces); the § Testing entry says so.
- **M3 pending** with the maintainer: the plan proceeds on (b); 2.8 says where the line goes for (a).
- **A FastMCP release that changes its own metadata** (`_meta.fastmcp`, derived titles, schema
  shapes, capabilities) now reads as a surface change: a lock bump re-runs the command and lands its
  delta, reviewed. A version bump alone is no diff (M1).
- **Overlaps with sibling cycles.** `AGENTS.md` § Testing (P4 rewrites the `test_surface.py` entry
  and one sentence of the `test_protocol.py` entry; a rebase at landing merges with the siblings'
  edits); `tests/mutants.py` (2.6: one anchor constant and six `why` strings, nothing in the runner
  or the sweep); `tests/test_hygiene.py` and `pyproject.toml` are not touched (the command sits in
  `bin/`, outside the hygiene scans; no marker is added).
- **The first user,** `rename-leftover-identity-strings` (0.2.0): its version-source switch is the
  one-line delta `- serverInfo.version.distribution: changed`, which fits a commit body.
- **Suite time (a figure for the maintainer).** Before: `tests/test_surface.py` 37 rows in 0.24 s
  (legacy) and 0.22 s (modern) on this host. The new rows are in-memory and add about 80 unit rows
  and about 15 server builds; P4 measures the after-figure (`--durations=0`, both eras) and quotes
  it against `suite-legacy-4` 7:22 and `suite-modern-4` 7:33 (the § Factory `ci budget` baseline).
  Expected: seconds, not minutes.
- **What no plant can reach.** The server and the recorder share the SDK's models in one process,
  so no server can be made to send an undeclared key; the raw route's value there is shown on the
  pure step only, and the sweep records "recorder dumps parsed models" as equivalent unless a plant
  reaches it.

## 6. Verification strategy

Phase gates are `spec/…/verify/gate.sh <mode>` (shell, body in `main`, `main "$@"; exit $?`), with
Python helpers run under `-I`; drafted at plan time and dry-run up to build's artifacts:

| Mode | Checks | Dry run on the plan tree |
|---|---|---|
| `files` | nothing under `packages/`, `uv.lock` or `pyproject.toml` differs from the plan commit | stops: no plan commit yet (first run after it) |
| `ids full\|sets` | `surface_checks.py`: every required `<kind>-<change>` row ran and passed, both eras (JUnit) | runs; red, naming the 39 missing rows (the tests are build's) |
| every mode | the working tree's fixture equals the staged one at the start and after each step | — |
| `p1` | lock; retired names gone (`absent`, grep status checked); baseline and form tests and every `served_surface` consumer (with `test_probe_startup.py`), both eras; era proof; `command_drive.py all` (determinism, refusals, eras, version, version-core, delta); `rebaseline_check.py`; every surface mutation case killed (11 cases, 28 s today) | `rebaseline_check.py` passes on today's fixture and on a prototype record; `surface-cases` lists 11 cases; `command_drive.py` stops at the missing command |
| `p2` | the control tests by name, both eras, and the whole module | stops: the tests are build's |
| `p3` | the per-set test and its controls, both eras, with `test_capabilities.py` | stops: the tests are build's |
| `p4` | `command_drive.py`, `rebaseline_check.py`, `docs_check.py docs` and `ledger`, the sweep, no sweep child left | `docs_check.py docs` red on today's text, as it should be; the sweep is build's |

**The comparison and recorder sweep** (`spec/…/verify/sweep.py`, written in P4 by this decision
list; a fresh copy of `tests/`, `bin/` and the top-level files per mutant, the real repo's sandbox and
environment, one child at a time marked `surface-sweep-child`; a pytest target judged by
`mutants.mutation_violations`, a drive target by its exit status and message; era-sensitive mutants
run in both eras). Each row names the decision it attacks and what must kill it:

| Mutant | Kills it |
|---|---|
| comparison ignores added keys (reports only lost and changed) | every `-added` row, full and per set |
| comparison ignores lost keys | every `-removed` row |
| recursion capped at depth 3 | `schema-key-at-depth-*` |
| one key name skipped (`_meta`) | `tool-entry-key-changed`, the baseline test against a planted `_meta` |
| one listing skipped (`prompts`; `resourceTemplates`) | `prompt-*`, `resource-template-*`, recorder rows |
| top-level keys outside a known set skipped | `top-level-key-added` |
| loose equality (`==`) | `value-type-changed` |
| lists compared as sets | `list-order-changed` |
| lists zipped (length ignored) | `list-item-added`, `list-item-removed` |
| version carve-out widened: any served version, or any `version` key resolved | version carve-out control rows |
| era carve-out widened: `capabilities` ignored, or resolved at any path | era carve-out control rows, `capabilities-field-*` |
| `era_violations` excepts `serverInfo` too | `test_era_check_refuses_every_other_difference`, `command_drive.py` eras |
| per-set check skips entries the fixture lacks | `test_set_check_catches_drift[tool-added]` |
| per-set loop slices `SETS` | the loop's every-set-id assertion |
| recorder drops `_meta` / records a fixed key list | baseline test, recorder rows |
| recorder lists no prompts or templates | recorder rows |
| recorder collapses a duplicate name | recorder duplicate row |
| recorder records parsed models | recorder rows if a plant reaches a key the model drops; otherwise recorded as equivalent, with the reason |
| command writes without `sort_keys` | `command_drive.py` determinism (bytes against the staged fixture) |
| command skips the era check | `command_drive.py` eras |
| `delta_lines` omits added paths | `test_delta_lists_every_changed_path`, `command_drive.py` delta |
| `expected_surface` ignores `era` (always the legacy capabilities); era-sensitive, run in both eras | the baseline test in the modern era, era carve-out rows |
| comparison skips `serverInfo`, or all of it but `version` | `server-info-field-*` |
| comparison ignores leaf value changes | every `-changed` row |
| `set_violations` drops `serverInfo` or `capabilities` | `test_set_check_catches_drift[server-info-field-*]`, `[capabilities-field-*]` |
| recorder reads the first page only | the `list_page_size=1` recorder row |
| recorder takes server info or capabilities from parsed models | the pure-step rows if the mutant reaches them; else recorded as equivalent, with the reason |
| baseline test writes the served surface into the fixture | the gate's staged-copy check |
| command writes the default fixture path as well as `--out` | the gate's staged-copy check after the drive (the delta plant writes different bytes) |
| `version_source` takes the first candidate unchecked | `command_drive.py` version-core and determinism |

The last phase also runs the profile's full `verify` (about 26 minutes, in the background). No
phase depends on hosted CI.

---

*No `research/`: lean path. Feasibility probes are summarised in § 4.*
