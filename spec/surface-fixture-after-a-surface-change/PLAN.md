# PLAN — The served-surface fixture follows a deliberate surface change

> **Status:** Draft for review · **Last updated:** 2026-11-12
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Every design element traces to a GOAL R-ID.
> **Re-planned 2026-11-12** for the GOAL's re-shape to a plain snapshot test (GOAL, Clarifications).
> The recorder design that review cycles 1–3 graded is kept unedited, with its gate scripts, under
> [`research/superseded/`](research/superseded/PLAN.md); no other `research/` (lean path, by the
> maintainer's ruling: the design is the standard snapshot pattern and the repo's own code).

## 1. Summary

`tests/test_surface.py` becomes a plain snapshot test. It serializes what the server serves, in
both protocol eras and under every capability set in `test_capabilities.SETS`, through the harness's
existing raw recorder (`served_surface`, kept as built), into one canonical JSON text, and compares
those bytes with `tests/fixtures/served_surface.json`. On any difference it fails with one line per
differing field, each naming the entry and the field path. The serializer holds the one
normalization, `serverInfo.version` recorded as the distribution it comes from (R9). Setting
`UPDATE_SURFACE=1` turns the same test into the update mode: it writes the fixture from the live
server and never reads the old one. `bin/record_surface.py` and everything that served only it go;
so do the tolerance-era carve-outs, the per-set check and the generated controls. What stays is one
depth control, one update-mode control, one version control and the recorder rows (R2). The fixture
is re-baselined once, in one explicit step, and the R6 check proves the full set serves in each era
what `0bfacae` pinned but for the five former kinds. Two phases; no file under `packages/` changes.

## 2. Design

### 2.1 The fixture (`tests/fixtures/served_surface.json`)

The serialization, written as `json.dumps(serialization, indent=1, sort_keys=True) + '\n'` (R5: the
layout today's fixture already has, so `tests/mutants.py`'s anchors keep their indentation). It is
keyed **field first, then era, then set** (deviation row 1):

| Top-level key | Holds |
|---|---|
| `tools`, `resources`, `resourceTemplates`, `prompts` | `{identity: {era: {set: entry}}}`: each entry as `served_surface` records it (every key at any depth but its identity), under each era and each set that serves it; a set that does not serve it has no key |
| `instructions`, `serverInfo`, `capabilities` (and any other key `surface_record` returns) | `{era: {set: value}}` |

Eras are `legacy` and `modern` (`harness.ERAS`); sets are `test_capabilities.SETS`' ids (`both`,
`both-reversed`, `core-only`, `rcac`, `slurm`). `serverInfo.<era>.<set>.version` is
`{"distribution": "fastmcp-slim"}` today (R9). Measured on a prototype (§ 4): 355,886 bytes, 11,503
lines, byte-identical across two runs; today's fixture is 46,719 bytes.

Why field first: a deliberate change to one tool shows in `git diff` as one hunk under that tool's
name (its copies in each era and set adjacent), a rename as one entry removed and one added; and
`tests/mutants.py`'s fixture plants, which need an anchor that occurs once, still find one
(`"run_command": {` occurs once here, ten times in an era-first layout).

### 2.2 The serializer (`tests/test_surface.py`)

- `served_surfaces() -> dict[(era, set_id), surface]`: for each set in `test_capabilities.SETS`
  (imported, not copied) a server `create_mcp_server('none', site=SITE, capabilities=…)`, and for each
  era in `ERAS` `served_surface(server, era=era)`. The harness's recorder is unchanged: raw listings
  through `send_request` with a plain-dict `TypeAdapter`, every page, every key, server info and
  capabilities from the raw `initialize` (legacy) or `server/discover` (modern). Its docstring drops
  the sentence naming `bin/record_surface.py`.
- **The one normalization, named beside the code with its cause (R9):** `VERSION_SOURCES =
  ('cluster-mcp', 'fastmcp-slim')`; `version_source(served, installed) -> str` returns the one
  candidate whose installed version (`installed: Mapping[str, str | None]`, read with
  `importlib.metadata` by the caller) equals `served` exactly (string equality; an uninstalled
  candidate, `None`, never matches, and a served value that is not a string matches nothing), and
  raises `ValueError` naming the served value and every candidate with its version when none or
  more than one matches. Cause: the served
  version is FastMCP's today (`fastmcp/__init__.py` reads `fastmcp-slim`) and the core's after the
  rename cycle, and moves with every lock bump and release; recording its source keeps a bump out of
  the diff and makes the rename's switch a one-field diff (M1). `fastmcp` is not a candidate: it is
  installed at the same version as `fastmcp-slim`, so a search of every distribution could not choose.
  The serializer replaces `serverInfo['version']` in each surface, and nothing else.
- `serialization(surfaces) -> dict`: the field-first layout of 2.1, generic over the top-level keys
  (a listing named in `harness.SURFACE_LISTINGS` is keyed by identity; every other key by era and
  set), so a key or entry the server begins to serve appears with no serializer change (R2). Every
  top-level key of every surface appears, an empty listing as `{}` (never back-filled from a fixed
  list).
- `canonical(obj) -> bytes` (2.1's form) and `serialized() -> bytes`, cached for the session: one
  build of the ten surfaces per process (measured 0.15 s with the twelve the prototype built).

### 2.3 The comparison and the update mode (`tests/test_surface.py`)

- `surface_check(fixture: Path, served: bytes, update: bool) -> None`:
  - `update`: `fixture.write_bytes(served)` and return. The old file is never opened, so a fixture
    holding conflict markers, a deleted one, or one naming an uninstalled distribution is
    regenerated without error (R1).
  - otherwise `assert fixture.read_bytes() == served, report(…)`. **The verdict is plain equality of
    bytes** (R3): type-strict by construction (`false` is not `0`), no tolerance list, no exemption,
    and a hand-edited fixture out of canonical form fails too.
- `report(expected: bytes, served: bytes) -> str`, evaluated only on failure: a header naming the
  fixture and the update invocation, then `differences(json.loads(expected), json.loads(served))`,
  one line each. A fixture that is not JSON yields the header and that fact. The report never
  decides the verdict.
- `differences(old, new, path=()) -> list[str]`: descends dicts only; a key only in `new` is
  `- <path>: added`, only in `old` `- <path>: removed` (not descended further), in both and both
  dicts recursed, else compared as JSON text (`json.dumps(…, sort_keys=True)`, type-strict) and
  reported `- <path>: changed: <old> -> <new>`, each value its JSON cut to 60 characters. Lists are
  leaves. No depth parameter. `<path>` joins keys matching `[A-Za-z_][\w-]*` with `.` and quotes any
  other as `['…']`: `tools.run_command.legacy.both.annotations.readOnlyHint`,
  `resources['cluster://storage'].modern.slurm`. Since the identity comes first, every line names
  the entry, then the era and set, then the field (R3).
- `test_served_surface_matches_baseline`: `surface_check(FIXTURE, serialized(), update=os.environ.get
  ('UPDATE_SURFACE') == '1')`, the variable and the module-level `FIXTURE` read when the test runs.
  The module reads no file when it is imported. The only writer of the fixture, and only with the variable set. It runs
  in each era's suite pass and serializes both eras each time (R4). The documented invocation
  (§ Commands, 2.6): `bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && UPDATE_SURFACE=1 uv run pytest
  -q tests/test_surface.py::test_served_surface_matches_baseline'` (the sandbox unsets
  `MCP_BASE_URL`, which `serverInfo.icons[0].src` follows; § 5).

### 2.4 The controls (`tests/test_surface.py`, all `unit`)

- **The depth control (R7), one test, three rows:**
  `test_a_field_changed_at_depth_fails_naming_its_entry_and_field[changed-type|gained|lost]`. Each
  row writes to `tmp_path` the canonical bytes of the real serialization with one plant at depth
  inside a tool entry, chosen from the serialization itself: `changed-type` turns the deepest
  boolean or integer leaf of a tool's copy under the last era and set in sort order (`modern`,
  `slurm`) into its type twin (`false`→`0`, `n`→`float(n)`); `gained` adds a key to the deepest dict
  of a tool's copy under `legacy`, `both`; `lost` removes `mimeType` from
  `resources['cluster://context'].modern.slurm`, so one row's path takes the quoted form and the
  plants span both eras and two sets. Each asserts that `surface_check(tmp, serialized(),
  update=False)` raises `AssertionError` and that the report's lines after the header are exactly the
  one line naming that path and that change. A row that finds no plant site fails; it never skips. One row per way a field can differ, because one plant
  cannot tell a verdict that drops type from one that drops gains (deviation row 2).
- **The update-mode control (R1, R5, R7):** `test_update_mode_regenerates_a_conflicted_fixture`,
  one test in three steps on `tmp_path` files: (1) a fixture holding merge-conflict markers around
  two JSON halves: `surface_check(…, update=True)` writes exactly `serialized()`, and
  `surface_check(…, update=False)` then passes; (2) a missing fixture: with the update off it fails
  and creates no file, with it on it writes `serialized()`; (3) the switch itself: the real
  `test_served_surface_matches_baseline`, called with `UPDATE_SURFACE` deleted and `FIXTURE`
  monkeypatched to a file holding a planted difference, raises `AssertionError` and leaves the
  file's bytes unchanged (the only holder in the suite of R1's "while not enabled, nothing writes";
  review finding 1). The update mode gets this control and no sweep (GOAL Non-goals;
  `method/mutation-testing.md` rule 2: dev tooling gets a control for each documented use and no
  sweep).
- **The version control (R9):** `test_version_source_names_exactly_one_distribution[one|none|several]`,
  on `version_source` with planted `installed` mappings whose versions share prefixes and suffixes
  (`4.1.4`, `4.1.40`, `14.1.4`) and include an uninstalled candidate (`None`): one exact match
  returns its name; none and two raise naming each candidate.
- **The recorder rows (R2), kept from the built tree, trimmed:** `RECORDER` /
  `test_recorder_sees_what_the_server_starts_serving` (a tool's `icons` and `_meta`, a tool with
  annotations, a resource's `title` and `annotations`, a prompt, a resource template, an
  experimental capability, a server version and website URL), `test_recorder_follows_every_page`,
  `test_recorder_refuses_a_name_served_twice`, `test_record_keeps_keys_no_model_declares`. Each
  keeps its "recorded as served" assertion; the old one against the fixture (`expected_surface`,
  `surface_violations`) becomes an end-to-end one: `differences` between the `serialization` of the
  unplanted and the planted surface, each under one era and a set id of the row's own, is exactly
  the one line naming the plant as added (`- prompts.planted_prompt: added`,
  `- tools.run_command.legacy.planted.icons: added`). They guard what equality cannot: that a key or
  entry the server starts serving reaches the serialization at all, the listings empty today
  included (review finding 4).
- **Removed** (each guarded something plain equality now guards, or served only the command): the
  N2 generated controls (`test_every_key_the_fixture_holds_is_compared`,
  `test_set_check_compares_every_key_the_fixture_holds`, `test_former_tolerated_kinds_are_differences`,
  `test_inlined_output_definitions_are_a_difference`; R7) and with them `key_sites`/`key_plants`; the
  `DRIFT` and `SET_DRIFT` matrices and `test_controls_reach_past_the_fixtures_extent` (replaced by the
  depth control: with bytes as the verdict, no key, depth, listing or era can be skipped);
  `test_surface_fixture_is_the_commands_form` (the baseline compares bytes, so a non-canonical
  fixture already fails); the two carve-out tests, `test_era_check_refuses_every_other_difference`,
  `test_delta_lists_every_changed_path` and `test_recorder_serves_each_eras_own_surface` (the
  baseline fails in either era's pass if the recorder ignored the era: each era's capabilities differ
  in the fixture); `test_every_capability_set_serves_the_fixtures_entries` (every set is in the
  serialization); and every command test, scan and helper (R10, 2.5).

### 2.5 Removed with the command (R10)

`bin/record_surface.py`; in `tests/test_surface.py`: `command_main`, `command_arguments`,
`command_refusal`, `command_base`, `command_head`, `command_record`, `command_result`,
`CommandEffects`, `CommandRefusal`, `CommandResult`, `fixture_problems`, `FIXTURE_NAME`, the no-run
scan (`command_runs`, `python_runs`, `workflow_commands`, `profile_commands`, `toml_values`,
`command_sources`, `test_nothing_runs_the_surface_command`, `test_command_scan_catches_planted_runs`),
the no-choice scan (`command_choices`, `test_the_surface_command_makes_no_choice`,
`test_command_choice_scan_catches_planted_choices`) and the `_Stand` effects tests
(`test_command_lists_the_delta_against_*`, `test_command_writes_the_fixture_by_default`,
`test_command_refuses_*`, `test_command_result_*`). With them go `surface_differences`,
`surface_violations`, `expected_surface`, `era_violations`, `to_fixture`, `delta_lines`,
`set_violations`, `fixture_bytes` and the two carve-out constants. The module is written fresh
around 2.2–2.4; git history holds the rest.

### 2.6 `tests/mutants.py` and the documentation

- **Mutation cases (R7):** `RUN_COMMAND_ENTRY` becomes `'  "run_command": {\n   "legacy": {\n
  "both": {\n     "_meta": {'` (once in the file, § 4), and `recorded()` inserts `"annotations":
  {hints},` before that `"_meta"`, so the four fixture-planting cases (`annotations-removed`,
  `annotation-hint-flipped`, `-dropped`, `-added`) plant into `run_command`'s legacy `both` entry.
  The `why` of all eleven surface cases follows 2.3's lines: for example `annotation-hint-flipped` is
  `tools.run_command.legacy.both.annotations.readOnlyHint: changed: false -> true`,
  `annotations-on-every-tool` is `annotations: added`, `title-on-one-tool` is
  `tools.run_command.legacy.both.title: changed: "Run Command" -> "Run a command"`, and
  `tool-description-summary-only` is `description: changed`. The comments above the two groups say
  the plant reaches one era and set and the code change all of them. The retarget's reason goes in
  the P1 commit body (§ Testing). The runner and its sweep are untouched.
- **`AGENTS.md` (R8):** §9's pin bullet and § Testing's `tests/test_surface.py` entry describe the
  snapshot test: what the serialization records (every era, every set, field first), the one
  normalization and its cause, plain equality of bytes, the update mode, and that a deliberate change
  lands as the update mode's fixture diff, `git diff` on the fixture its delta list in the commit
  body, reviewed under the high-blast-radius gate. § Commands replaces the command's block with the
  update invocation. The repository map loses `bin/record_surface.py` ("Six repo-level paths" becomes
  five). The harness entry's `served_surface` sentence stays (the recorder is unchanged). No line
  describes the command, its flags, its base, a tolerance list or the hand-edit rule
  (`snapshot_checks.py docs`).

### 2.7 The re-baseline (the fixture step, R5, R6)

One explicit step, the last of P1, and the only write of the fixture in the cycle:

1. With 2.2–2.6 in place, delete the working-tree fixture and run the documented update invocation
   (R1's missing case, through the documented use). Stage the result. Then overwrite the working copy
   with merge-conflict markers around two halves and run it again: `git diff --exit-code` on the
   fixture against the staged copy must be empty (R1's conflicted case and its byte-identical
   rewrite, across processes).
2. Run the baseline in both eras (no update) and `verify/rebaseline_check.py` (reads the staged
   fixture: R6's report, with the five kinds per era, the 72 argument descriptions, and every field,
   era and set entering as served).
3. Commit body (P1): the R6 report verbatim, `git diff --stat` on the fixture, the new fixture's
   blob hash, and the note that the format changed wholesale, so the delta list for this change is
   the whole file.
4. **The landing commit's body carries `git diff --stat` on the fixture, the R6 report and the new
   fixture's blob hash**, with a sentence that the format changed wholesale (deviation row 3, the
   maintainer's ruling of 2026-11-12). The whole `git diff` (measured on the prototype: 12,519
   lines, 402 KB) goes to the maintainer as a compare link at the publish sign-off: the fixture is
   on the high-blast-radius list. Step 3's P1 commit body follows the same rule.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1 | `surface_check`'s update branch (never reads); `UPDATE_SURFACE`; the update-mode control; `test_no_workflow_or_script_turns_the_update_mode_on` (added 2026-11-12, § 5 open question 1); 2.7.1's two runs; gate `fixture_untouched` around every step and `snapshot_checks.py no-enable`; `gate.sh` unsets the variable |
| R2 | `served_surfaces` over `SETS` × `ERAS` through the unchanged raw recorder; `serialization` generic over keys; the recorder rows |
| R3 | bytes equality in `surface_check`; `report`/`differences`; no tolerance list; the depth control |
| R4 | both eras serialized in every run; the baseline in each era's suite pass (gate `both_eras`) |
| R5 | `canonical` (indented, sorted); the update control; 2.7's commit bodies; the fixture stays on the high-blast-radius list |
| R6 | `verify/rebaseline_check.py`, its report in the P1 and landing commit bodies |
| R7 | depth control, update control, version control; N2 controls removed; `tests/mutants.py` re-anchored, its 11 surface cases killed in both eras; the aimed sweep (§ 6) |
| R8 | `AGENTS.md` §9, § Testing, § Commands, repository map (2.6); `snapshot_checks.py docs` |
| R9 | `VERSION_SOURCES`, `version_source`, named beside the serializer; the version control |
| R10 | 2.5; gate `absent` names and `[ ! -e bin/record_surface.py ]` |
| R11 | P2: the `--out` seed and its ROADMAP entry retired; `issues/surface-pin-completeness.md` re-checked (2.8); counts; `snapshot_checks.py seeds` |

### 2.8 The completeness seed, re-checked (R11)

Of `issues/surface-pin-completeness.md`'s items, under this shape:

- the comparison's depth bound: **dropped** (the verdict is bytes; the renderer has no bound);
- the recorder's `execution` row and its repeated-cursor guard: **kept** (the recorder is unchanged;
  a key it dropped would pass equality only after an update had blessed it);
- the version source accepting a version two candidates share: **dropped** (R9 and its control
  pin it here);
- the per-set loop and cut: **dropped** (no per-set check; a one-server mutant fails the baseline);
- the no-run scan's file domain: **dropped** (no scan, R10).

So the seed is kept, re-written to the recorder's two items (its Problem, Outcome and acceptance
sketch, with Pre-existing and the source note), and its `ROADMAP.md` entry follows. The `--out`
seed and its entry are retired. Part I's counts follow: 30 entries, thirteen gates, and the gates
group's description drops "its command's relative `--out`".

## 3. Invariant gate (AGENTS.md constitution check)

Walked before design (gate #1) and against this draft (gate #2). Touched: §9 (the served surface,
human gate), § Testing, § Conventions, and the high-blast-radius list's
`tests/fixtures/served_surface.json` entry (the re-baseline rewrites that file, so publish takes
the maintainer's sign-off whatever the verdict). Research trigger 2 is overridden by the
maintainer's ruling (lean path); the file's contract is this cycle's own GOAL.

- **§9.** Nothing served changes (Non-goal): no file under `packages/`, `uv.lock` or
  `pyproject.toml` changes (`gate.sh files`), and R6's check shows the full set serves what `0bfacae`
  pinned. §9's same-commit rules are untouched: no tool changes. The pin bullet is rewritten (R8).
  `test_server_identifies_as_cluster_mcp` stays: it pins the modern era's per-result stamp, which
  the serialization does not record (a listing's envelope is protocol, not surface).
- **§9, the base is composed from the capabilities served.** Each set's instructions are now in the
  fixture; `test_instructions.py` and `test_capabilities.py` keep their own checks.
- **§7/§8, the listings keep their own order.** Entries are keyed, so order is not pinned (Non-goal);
  `test_capabilities.py` pins it.
- **§ Conventions.** Every test `@pytest.mark.unit`; no spec ids in `tests/`; declarative comments;
  `tests/harness.py` stays the only module importing the stack; the verify, gate and CI lists do not
  change (the module runs in the fourth command of each era); a mutation case retarget records its
  reason in the commit body.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| 1. **R2's "for each era and each set, the surface served" read as a field-first layout:** `{identity: {era: {set: entry}}}` per listing, `{era: {set: value}}` per other key. Every entry is recorded whole and literally under every era and set that serves it; nothing is merged, dropped or normalized. | `tests/mutants.py` refuses an anchor that occurs more than once, and in an era-first layout every tool's text occurs ten times, identical up to the `capabilities` block thousands of lines above, so the four fixture-planting cases R7 keeps could not apply. Field first, `"run_command": {` occurs once. It also groups a change's `git diff` under the entry it changes. | Era first (`{era: {set: surface}}`) needs the mutation runner to accept repeated anchors, a change to its plant contract that sibling cycles own. Separate files per era and set break R1's one fixture path. |
| 2. **R7's "one control" for depth read as one test with three rows** (`changed-type`, `gained`, `lost`), one plant each. | A single plant cannot kill both a verdict that compares parsed values (`False == 0`) and a renderer that drops gained or lost keys: whichever plant is used, the other mutant passes it. | One plant leaves a non-equivalent comparison mutant alive, against R7's first sentence. Lists are leaves of the renderer, so no list row is needed. |

| 3. **R5's "the change's commit body carries" the delta list read, for this one re-baseline, as `git diff --stat`, the R6 report and the new fixture's blob hash** in the P1 and landing commit bodies, the whole `git diff` going to the maintainer as a compare link at the publish sign-off (the maintainer's ruling, 2026-11-12). | The format changes wholesale, so `git diff` on the fixture is 12,519 lines (402 KB): every line changes, and as a commit body it names nothing a reviewer can act on that the stat, the R6 report and the hash do not. | The whole diff in the body (§ 5, open question 2 as first drafted): a 402 KB commit message, readable only as the compare view the sign-off uses anyway. Later surface changes carry `git diff` as R5 says. |

Rows 1–2 were accepted at the plan sign-off, 2026-11-12; row 3 is that sign-off's ruling. They read
R-IDs without changing what they require; none bends a CRITICAL invariant.
Readings the design carries without a row: the version control (R9's "fail naming the candidates"
needs one to kill its normalization's mutants, R7); the recorder rows kept (R7 removes N2's
generated controls only, and these guard R2's "appears with no serializer change", which equality
cannot); R1's "no gate step or CI job SHALL enable it" held by a gate check, not a suite test (§ 5).

## 4. Rabbit holes (resolved)

Lean path, research skipped by the maintainer's ruling; trigger 3 fires (the deliverable is a gate),
so the adversarial review below ran. Probes, in a throwaway lab under `$TMPDIR` against this
worktree's locked environment (FastMCP 4.1.4, SDK 2), with the harness's fence held by a refusing
`Popen`:

- **Cost and determinism.** A prototype of 2.2's serializer built the ten surfaces (plus the two
  default-server ones) in 0.12–0.15 s after a 0.75 s import; two runs wrote byte-identical files of
  355,886 bytes. The current branch's `tests/test_surface.py` (214 rows) takes 3.1 s per era; the
  new module has about 20 rows and one ten-surface build per process.
- **`both` is the full set.** In each era, the surface of `create_mcp_server('none', site=SITE)`
  equals set `both`'s, version normalized: R6's "full capability set" is set `both`.
- **R6 on the prototype.** `verify/rebaseline_check.py` on the prototype fixture: in each era, no
  difference beyond the five kinds (`additional-properties` and `derived-title` on 24 tools,
  `argument-description` on 18, `output-defs-inlined` on 2, `output-model-description` on none);
  each of the 72 argument descriptions is its `Args:` line; entering as served: `capabilities`,
  `prompts`, `resourceTemplates`, `serverInfo`, `_meta` on every tool and resource, and the sets
  `both-reversed`, `core-only`, `rcac`, `slurm` in each era. Teeth: a description planted in the
  modern era only, and an argument description planted in the legacy era only, each turn it red.
- **The mutation anchor.** In the prototype the new `RUN_COMMAND_ENTRY` occurs once; `"run_command":
  {` occurs once (ten times in an era-first layout).
- **Adversarial design review** (trigger 3, one pass at `appetite: small`, a fresh subagent given
  GOAL, this PLAN, the drafted gates and the prototype; it probed in its own lab). Eleven findings,
  all folded: 1 (HIGH) the update switch was unguarded, and `!= '1'` or a default of `'1'` would make
  the baseline write and pass in CI: the update control now calls the real test with the variable
  deleted (2.4), and the sweep carries three switch mutants (§ 6); 2 a missing fixture was never
  controlled: the update control's missing-file step, and the fixture step starts from a deleted
  fixture (2.7); 3 `rebaseline_check.py` passed a `false`→`0` default and a gained `required: []`
  (the old comparison reads with `==` and `.get` defaults; confirmed on a plant): a type-strict pass
  added, red on that plant, green on the prototype; 4 serializer mutants on the listings empty today
  survived: recorder rows go through `serialization` (2.4), a sweep row added; 5 every depth row
  planted dot-safe paths under the first era and set: the `lost` row is a resource under
  `modern`/`slurm`, the type row under `modern`/`slurm`; 6 `surface-cases` required only one
  planting case: it pins the eleven and the four; 7 `no-enable` scanned too little: every staged
  file but the snapshot test, the docs and `spec/`, and `gate.sh` turns uv env files off; 8 `gate.sh`
  now unsets `MCP_BASE_URL`; 9 `plan_commit` matched a body line: it compares the subject whole; 10
  version rows used distinct versions: prefix-sharing ones and a `None` (2.4), `None` never matches
  (2.2); 11 a row with no plant site could skip: it fails, and `absent` reads the index. Checked
  and holding: determinism over six runs (three processes per era), per-era capabilities, `both` as
  the full set, the anchor's uniqueness and the four planting cases' path-level kill, the bytes
  verdict's type strictness, the two equivalence claims, the gate scripts' error propagation.

## 5. Risks & open questions

- **Open question 1 — R1's CI clause.** "No gate step or CI job SHALL enable it" is held by
  `snapshot_checks.py no-enable` in the phase gates (every staged file but the snapshot test, the
  docs and `spec/`, plus the profile's `verify` row and the release `gate:` list), and `gate.sh`
  unsets the variable. Nothing in the suite holds it after landing; the suite does hold that the
  test compares, and writes nothing, while the variable is unset (the update control's third step).
  A one-function suite scan could hold the CI clause too; it was left out to keep the module to the
  snapshot pattern. The maintainer's call. **Answered 2026-11-12:** add it
  (`test_no_workflow_or_script_turns_the_update_mode_on`: no file under `.github/workflows/` or
  `bin/` sets or exports the variable), since `no-enable` stops guarding once the cycle lands.
- **Open question 2 — the landing body's size.** Per the ruling, the landing commit's body carries
  `git diff` on the fixture: 12,519 lines (402 KB) for this re-shape, since the format changes
  wholesale. Later surface changes are small diffs. If the maintainer prefers, this one landing can
  carry `git diff --stat`, the R6 report and the fixture's blob hash instead. **Answered
  2026-11-12:** that, with the whole diff sent as a compare link at the publish sign-off (§ 3,
  deviation row 3; 2.7).
- **A change shows up to ten times.** A tool's docstring change rewrites its copy in each era and set
  (ten lines, one hunk); an instructions change rewrites each set's text. This is R2's "every era,
  every set" as served; the field-first layout keeps the copies together.
- **Raised per the Non-goals: `serverInfo.icons[0].src` follows `MCP_BASE_URL`**, which `oidc`
  auth requires and `server.py` reads at import. The fixture holds the unset value; the documented
  update invocation runs under `bin/sandbox.sh`, which unsets it. A shell exporting it fails the
  baseline at that path. Unchanged from the superseded plan, where the maintainer accepted it.
- **A lock bump that changes what FastMCP serves** is a surface change: the update mode lands it as a
  reviewed fixture diff. A version bump alone is not (R9).
- **Overlaps with sibling cycles.** `AGENTS.md` § Testing and §9 (a rebase at landing merges with
  siblings' edits); `tests/mutants.py` (one anchor, one helper, eleven `why` strings and two
  comments; nothing in the runner).
- **The first user,** `rename-leftover-identity-strings`: its version-source switch is the one-field
  diff `serverInfo.<era>.<set>.version.distribution` in ten places.
- **Suite time (a figure for the maintainer, no bound changes).** Before: the current branch's module
  3.1 s per era (214 rows); `develop`'s 0.24 s (37 rows). P2 measures the after-figure for
  `tests/test_surface.py` in each era and quotes it against `suite-legacy-4` 7:22 and
  `suite-modern-4` 7:33 (the § Factory `ci budget` baseline). Expected: about a second.

## 6. Verification strategy

Phase gates are `spec/…/verify/gate.sh <mode>` (shell, body in `main`, `main "$@"; exit $?`, the
update variable unset), with Python helpers under `-I` reading the index, never the working copy.
Drafted at plan time and dry-run up to build's artifacts:

| Mode | Checks | Dry run on the plan tree |
|---|---|---|
| `files` | nothing under `packages/`, `uv.lock` or `pyproject.toml` differs from the plan commit | passes (against the previous plan commit until this one lands) |
| every mode | the working tree's fixture equals the staged one at the start and after each step | — |
| `p1` | lock; `bin/record_surface.py` gone and the retired names absent from the index; the snapshot test and its controls by id, both eras; the module and every surface consumer with `test_mutations.py` and `test_hygiene.py`, both eras; `rebaseline_check.py`; the 11 surface mutation cases per era; `no-enable`; `docs` | stops at `bin/record_surface.py still exists` (build's); `rebaseline_check.py` passes on the prototype fixture and goes red on two plants; `surface-cases` lists exactly the 11 (4 planting); `no-enable` passes; `docs` red on today's text, as it should be |
| `p2` | `seeds`; `ledger`; `sweep.py` (written by P2); no sweep child left | `seeds` red on today's seeds (as it should be); its count check red on a ROADMAP with an entry removed and the counts left; `ledger` passes; the sweep is build's |
| `full` | the profile's whole `verify` | not run at plan time (the maintainer's ruling: no full-suite run before the sign-off) |

**The aimed sweep** (`spec/…/verify/sweep.py`, written in P2 from this list, reusing the superseded
sweep's runner: a copy of the index's `tests/`, `bin/` and top-level files per mutant, one plant
whose anchor occurs once, the real repo's sandbox and environment, one child at a time marked
`snapshot-sweep-child`, `tests/test_surface.py` judged by `mutants.mutation_violations`). Every
mutant runs in **both** eras and must be killed in each (R7). It writes `verify/sweep-report.txt`
(verdicts only). The update mode is not swept (Non-goal). Mutation findings at review follow
`method/mutation-testing.md` § When a review is done: the review's diff-sweep survivor list is the
enumeration, and a hand-made mutant of a deeper layer of a class pinned here is a coverage
observation, seeded, not a finding.

| Mutant | Decision | Kills it |
|---|---|---|
| verdict always equal | comparison | every depth row |
| the switch reads `!= '1'`, defaults to `'1'`, or tests presence (`in os.environ`) | comparison (whether it runs) | update control step 3 |
| verdict on parsed values | comparison | `changed-type` |
| verdict strips surrounding space from both sides (`.strip()`) | comparison | **equivalent on every fixture the update mode writes** (canonical bytes end in one newline and start with `{`); only a hand-edit reaches it, recorded with that reason |
| renderer skips keys only in `new` | comparison report | `gained` |
| renderer skips keys only in `old` | comparison report | `lost` |
| renderer compares leaves as Python values | comparison report | `changed-type` |
| renderer treats dicts as leaves (no descent) | comparison report | every row (the exact line names the deep path) |
| renderer labels swapped (added ↔ removed) | comparison report | `gained`, `lost` |
| renderer drops the era or set from the path | comparison report | every row |
| renderer's quoted-key branch renders a wrong or empty key | comparison report | `lost` (a quoted resource path) |
| normalization skipped (served version kept) | normalization | baseline |
| `version_source` takes the first match | normalization | `several` |
| `version_source` accepts no match | normalization | `none` |
| `version_source` match by `!=` | normalization | `one`, baseline |
| `version_source` match by `in` / `startswith` / `endswith` | normalization | `one`, `several` (prefix- and suffix-sharing versions) |
| `version_source` lets `None` match a missing served version | normalization | `none` (a `None` candidate) |
| `VERSION_SOURCES` loses `fastmcp-slim` | normalization | baseline (no candidate matches) |
| `VERSION_SOURCES` loses `cluster-mcp` | normalization | **equivalent today**: the core's version is not served until the rename cycle, whose fixture diff would show it |
| the normalization writes the served value, not `{"distribution": …}` | normalization | baseline |
| error omits the candidates | normalization | `none`, `several` |
| serialization drops an era / a set / builds one server for every set | serializer | baseline |
| serialization drops, or mis-keys, a listing empty today (`prompts`, `resourceTemplates`) | serializer | the `prompt` and `resource-template` recorder rows |

The last phase also runs the profile's full `verify` (about 26 minutes, in the background). No
phase depends on hosted CI.
