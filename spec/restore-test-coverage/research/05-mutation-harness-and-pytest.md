# 05 — Planted violations as standing controls (R12), pytest-asyncio mode, markers

## R12: where the planted violation lives

R12 allows "a standing negative control in the suite or a recorded mutation in the build record",
with nothing planted in `src/`. Three shapes were weighed:

| Shape | Verdict |
|---|---|
| Recorded mutations in commit bodies | Rejected as the primary: proven once at build time, never again; `stack-upgrade` inherits nothing it can run. |
| Runtime monkeypatch plants (replace `_extract_identity` with a reordered copy, etc.) | Rejected as the primary: the plant is a reimplementation, not the source the GOAL names ("`-n` dropped", "two rungs swapped"). Several plants (`-n`, the ladder) would mean rewriting whole methods in the test. |
| **Source mutation of a package copy, run as a child pytest** | **Chosen.** Exactly the GOAL's examples, standing in the suite, and it re-runs on every verify. |

### Mechanics (executed in `prototypes/mutation_child.py`, 2026-10-16)

1. Copy the imported package (`Path(rcac_mcp.__file__).parent`, which in a fresh clone is the
   clone's) to `tmp_path/src/rcac_mcp` with `ignore_patterns('__pycache__')`.
2. Apply the case's `(old, new)` edits. Each `old` must occur exactly once, or the case fails,
   naming the contract whose anchor moved.
3. Run a child under `bin/sandbox.sh`, stepping back into the repo (`cd "$CLUSTER_MCP_REPO"`), with
   `PYTHONPATH=<copy>/src` and `PYTHONDONTWRITEBYTECODE=1`:
   - first an origin pre-check, `sys.executable -c "import rcac_mcp, sys; …"`, that exits `97`
     unless `rcac_mcp.__file__` resolves under the copy;
   - then `sys.executable -m pytest -q -rA -p no:cacheprovider <targets>`.
   The editable install is a plain `.pth` path entry (`_editable_impl_rcac_mcp.pth` → `src`), so
   `PYTHONPATH` precedes it. The console script `rcac-mcp` honours the inherited `PYTHONPATH` too,
   so a target that drives the CLI under its own nested sandbox also runs the mutant.
4. `mutation_violations(returncode, report, targets)` (pure): the child must exit `1`, and every
   target must have a `FAILED tests/<target>` line. Exit `0` is a surviving mutant; `2`/`3`/`4`/`5`
   (interrupted, internal, usage, nothing collected) and `97` (wrong origin) are harness failures;
   a target that passed or is missing is named. A target reported only as a teardown `ERROR` does
   not count as killed.
5. The real package is never edited: the gate checks `src/` is byte-identical to the merge base and
   that `git status --porcelain -- src` is empty.

The prototype's child run (cwd in the sandbox) reported ids relative to the sandbox. Running from
the repo root gives `tests/…` ids, which is why the child steps back in.

### Standing controls on the harness itself

- `test_mutation_check_flags_survivors[...]` (unit): synthetic `(returncode, report)` pairs: all
  passed, one target passed, collection error, usage error, target missing, wrong origin. Each must
  produce a violation, and a clean kill must produce none.
- `test_mutation_anchor_applies[<case>]` (unit, one per case): every anchor occurs once in the
  current source and the mutant compiles. This is the fast "contract moved" signal for
  `stack-upgrade`/`safe-execution`.
- `test_surviving_mutant_is_reported` (integration): a semantics-free edit (the `context.py` module
  docstring) with an isolation target. The child exits 0, and `mutation_violations` must report
  survival. This proves the runner really runs the child and reads its report.
- `test_wrong_origin_is_reported` (integration): pre-check against a directory the child does not
  import from → exit 97 → violation.

### Case table

`prototypes/mutation_cases.py` holds 38 cases across the ten contracts, each with exact anchors and
named target ids. Running it checked every anchor (exactly one occurrence) and compiled every
mutant: "38 cases: every anchor occurs once and every mutant compiles". The build ports it into
`tests/test_mutations.py` slice by slice. It may add cases; it removes or retargets one only with a
recorded reason (a target that does not go red is a hollow test until shown otherwise).

### Cost

The child pays pytest start-up plus the FastMCP import (~2–3 s); 38 cases plus 2 controls make a
mutation pass of roughly 1.5–2 minutes. Acceptable with no CI. `ci-workflow` inherits the number.

## pytest-asyncio mode

pytest-asyncio 1.3.0 is installed, and no `asyncio_mode` is configured, so it runs in strict mode
(only `@pytest.mark.asyncio` tests are run as coroutines). The design uses **no async tests**: every
drive is a sync test calling `harness.drive(coro)`, which is
`contextvars.Context().run(asyncio.run, asyncio.wait_for(coro, timeout))`. This matches the existing
suite (`asyncio.run` in `test_served_tools_match_registry`), gives each drive a fresh context
(brief 02), and avoids event-loop fixture scope entirely. The `asyncio` marker is never applied, so
the strict-markers registration question does not arise.

## Markers

- `unit`: in-process, under the guard (brief 03). That covers the ASGI HTTP route, the in-memory
  client, the ladder drive and the pure checks.
- `integration`: anything that launches a process. That is the CLI drives (R8/R9), which go through
  `bin/sandbox.sh`, and the mutation children, also under `bin/sandbox.sh`. `pyproject.toml`
  describes the marker as "drives the installed CLI"; a mutation child runs pytest rather than the
  CLI, but it is still a sandboxed subprocess. `AGENTS.md` § Testing says so; the marker text is
  left alone.
- `tests/conftest.py` keeps its collection hook unchanged. The guard fixture reads markers but never
  adds one, and the `--noconftest --collect-only -m "not unit and not integration"` → exit 5 witness
  (the strip cycle's) stays in every gate.


## Amendment (2026-10-16, adversarial design review)

- The runner moved out of the collected suite into `tests/mutants.py`, run by every phase gate and
  recorded in each phase commit (finding 5, foreman's ruling). Only the anchor checks and the
  `mutation_violations` controls stay in `tests/test_mutations.py`.
- A kill now needs a JUnit `<failure>` carrying the case's kill reason (`why`). Exit 1 and a
  `FAILED` summary line are not enough, because a `NameError` mutant passed that (finding 3). The table
  has 43 cases, five of them from the review.
- `drive` no longer uses a fresh context (see the amendment to brief 02).
