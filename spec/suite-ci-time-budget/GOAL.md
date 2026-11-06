# GOAL — Each CI era job keeps a margin under its timeout, and every row keeps its proof

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** suite-ci-time-budget
- **kind:** test
- **appetite:** small

## Problem

Each protocol era's suite runs in one CI job with a 20-minute timeout (`.github/workflows/ci.yml`:
`suite-legacy`, "suite (handshake era)", and `suite-modern`, "suite (modern era)"). The two jobs
were split out of one so that neither nears its timeout (`AGENTS.md` § Conventions, "CI mirrors the
gate"). They are nearing it again. `ssh-half-open-link` added real-time loopback rows whose waits
are built in, not slack: about 5 s for a call in flight, about 4.1 s for a gone host, about 7–8 s for
a slow transfer, and about 7 s for an idle or quiet command. Its PLAN (§6) set a trim threshold of
+180 s per era, and the cycle passed it. The rows it added since the seed was written raised the
default suite to 4979 rows locally (plus 14 skipped there) and 4996 on CI.

**CI, pytest's own time per era**, on the cycle-branch runs of `ssh-half-open-link`:

| Commit | handshake | modern |
|---|---|---|
| `ac4909a` | 732 s | 723 s |
| `e2ad380` | 871 s | 848 s |
| `4b4ad28` | 782 s | 810 s |
| `43dcc8a` | 755 s | 860 s |

- Before that cycle (plan head `7bf9666`) the eras took 555 s and 524 s.
- The era jobs ran about 13–15 minutes of their 20.
- On `develop` after it landed, two runs a docs-only commit apart (`885fdd8`, `629c78e`, both
  2026-11-06) took 13:46 and 12:33 wall time for the handshake job, 14:51 and 13:01 for the modern
  one. A job's wall time adds checkout, the shell install and `uv sync` to pytest's.
- **Runner variance is large.** The same tree can differ by about 100 s between runs, so a margin
  measured on one run proves little.
- An earlier sighting: before the eras were split into separate jobs, two consecutive gate runs
  took 16.4 and 16.75 minutes, during `capability-probe`.

A further cycle of `ssh-half-open-link`'s size would bring an era job near its timeout, and a job
that times out reads as red, so every later cycle that adds tests is at risk.

**Pre-existing:** the budget is shared with every earlier real-time row (the stalling and slow-link
rows took 4–11 s each before that cycle). The growth past the threshold is `ssh-half-open-link`'s.

The fix must not buy time by weakening the suite. Each row is the proof of a contract, and several
rows are the subject of develop-fails or red-first gates in earlier cycles' `spec/*/verify/` and
`spec/*/remediation/`, or the target of a mutation case in `tests/mutants.py`. A row that is
shortened, moved to another job or process, or put behind a variable CI never sets can stop
failing when its contract breaks, and nothing would say so.

## Outcome / vision

Each era's suite finishes on CI with a clear, measured margin under its timeout, robust to runner
variance, so later cycles can add rows without nearing it. CI still runs every row it runs today,
and every row still fails where it failed before. CI and the profile's gate stay one set of
commands.

## Acceptance criteria (the contract)

A row the change **touches** is a default-suite test id whose test code, parametrisation, fixtures,
or the helpers and constants it reads (a bound, a wait, a loopback server, a hop) change, or that
runs in a different CI job or process than before.

- **R1 — Margin.** Each CI job that runs an era's suite SHALL complete within
  [NEEDS CLARIFICATION: Q1 — the budget and its measure; recommended: 10 minutes of wall time, job
  start to completion as `gh run view --json jobs` reports it, on GitHub's hosted `ubuntu-24.04`
  runner, in the slowest of at least three push runs of the cycle branch's final tree, with each
  job's `timeout-minutes` unchanged at 20].
- **R2 — Every row still runs on CI.** For each era, every test id that CI collects and runs on the
  cycle's base (`origin/develop` at `5f6e984`) SHALL be collected and run by CI's job or jobs for
  that era on this tree, at least once: none dropped, newly skipped or deselected, and none moved
  behind `CLUSTER_MCP_TEST_EVERY_KIND=1` or any other variable, marker or option CI does not set.
  A row whose id changes counts as dropped, unless the PLAN maps the old id to the ids that now
  carry its assertions, and R3 then holds for those.
- **R3 — Touched rows still fail where they failed.** For each touched row whose own code,
  parameters or waits change, every develop-fails or red-first gate in `spec/*/verify/` or
  `spec/*/remediation/` that names it, and every `tests/mutants.py` case that targets it, SHALL give
  the same verdict on this tree as on the base: the row fails where it failed, for the reason the
  gate or case checks. Where such a gate cannot run on this tree as written, an equivalent the
  PLAN names SHALL show the same thing against the same base. A row of this kind that no gate or
  case names SHALL be shown red against a planted break of the contract it pins, recorded in
  `spec/suite-ci-time-budget/`.
- **R4 — Process-wide fixtures still apply wherever a row runs.** Where the change runs rows in a
  different job or process than before, every session-scoped or autouse fixture and collection
  hook in `tests/conftest.py` (among them `path_shim`, `skip_probes`, the `guard` fence,
  `main_context_holds_no_executor`, and `pytest_collection_modifyitems`, which fails an unmarked
  test) SHALL still be in force for each row, shown by each one's standing negative control, or a
  planted violation where it has none, failing under CI's new arrangement as it fails under the
  old.
- **R5 — The measured runs are green.** Each run counted for R1 SHALL be green in every job of the
  workflow. [NEEDS CLARIFICATION: Q3 — how a failure of a row that
  `issues/stalled-reconnect-test-timing.md` lists, in a counted run, is treated.]
- **R6 — CI mirrors the gate.** The profile's `verify`, the release recipe's `gate` and
  `.github/workflows/ci.yml` SHALL stay in step as `AGENTS.md` § Conventions binds them, changed
  in the same commit, and for each era the profile's `verify` SHALL run the same set of test ids as
  CI's job or jobs for that era. § Conventions, the § Factory `ci` row and the workflow's header
  comment SHALL describe the jobs as they then are.
- **R7 — The budget is a profile baseline.** [NEEDS CLARIFICATION: Q2 — whether this cycle adds
  it; recommended: yes.] The `AGENTS.md` § Factory profile SHALL carry a row stating R1's per-job
  budget and its measure, and the baseline measured at landing: each era job's slowest wall time
  over R1's runs, with the commit.

## Non-goals (no-gos)

- **Raising a job's `timeout-minutes`**, or moving to a larger or paid runner, as a way to meet
  R1. The runner stays the hosted `ubuntu-24.04`, and the workflow keeps § Conventions' least
  privilege: no caches, no uploads, no secrets.
- **Moving any row behind `CLUSTER_MCP_TEST_EVERY_KIND=1`** or another opt-in CI never sets,
  skipping it, or deselecting it by marker (R2). That would drop the row's proof from CI, which
  the seed's outcome rules out.
- **The load sensitivity of wall-clock-bound rows**:
  [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md) stays
  its own, unshaped cycle. This cycle does not sweep or loosen those bounds. If the PLAN runs rows
  concurrently, the rows that seed lists are a known hazard, which R5 and the PLAN's risk section
  must face, not fix.
- **The mutation workflow's time**, `.github/workflows/mutants.yml`:
  [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md).
- **Product code.** Nothing under `packages/` changes; a product bound such as the SSH connect
  timeout is not shortened to speed the suite. Test-side bounds and waits are in scope, under R3.
- **Local verify time.** No budget is set for the profile's `verify` on a developer's machine,
  though a change may shorten it.
- **The `gate` job's time.** It takes well under a minute and is not in R1.

## Clarifications

- **Q:** Slug, kind and appetite? — **A:** `suite-ci-time-budget`, `test`, `small`, settled by the
  foreman; the cycle runs next, right after `ssh-half-open-link`, so that later cycles adding tests
  don't push an era job past its 20-minute timeout (resolved 2026-11-06).
- [NEEDS CLARIFICATION: Q1 — R1's budget and measure: the figure, wall time or pytest time, how
  many runs and which statistic (slowest, median), and whether `timeout-minutes` stays 20.]
- [NEEDS CLARIFICATION: Q2 — whether this cycle adds the profile row R7 describes, or seeds it for
  a later one.]
- [NEEDS CLARIFICATION: Q3 — R5's treatment of a failure, in a counted run, of a row that
  `issues/stalled-reconnect-test-timing.md` lists.]

## Related materials

- Seed: [`issues/suite-ci-time-budget.md`](../../issues/suite-ci-time-budget.md)
- [`spec/ssh-half-open-link/`](../ssh-half-open-link/): PLAN §6 (the CI budget and its +180 s
  threshold), TECH P3; `verify/silent-gate.py`, which names each silent-link row by id
- [`issues/stalled-reconnect-test-timing.md`](../../issues/stalled-reconnect-test-timing.md),
  [`issues/mutants-workflow-timeout.md`](../../issues/mutants-workflow-timeout.md)
- `.github/workflows/ci.yml`; `AGENTS.md` § Factory (`ci`, `verify`, Release recipe `gate`),
  § Conventions ("CI mirrors the gate"), § Testing
- `tests/conftest.py`, `tests/mutants.py`, `tests/test_mutations.py`; process-wide state a row
  patches for itself, such as `threading.excepthook` in `tests/test_ssh_exec.py`, which the seed
  names for a check before any concurrent run
- Develop-fails and red-first gates of earlier cycles, for example
  `spec/timeout-process-cleanup/verify/develop-fails.py`
