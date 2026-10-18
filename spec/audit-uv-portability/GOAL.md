# GOAL — The dependency audit and the suite work under every supported uv

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).
> Keep this at the right altitude: solved and bounded, but not over-specified — leave design
> freedom for the plan. Edit requirements here; do **not** silently drift them during build.

- **slug:** audit-uv-portability
- **kind:** fix
- **appetite:** small

## Problem

`develop`'s suite is red under uv 0.12.x, and the repo never says which uv it supports. The
`ci-workflow` cycle (cycle 3, not landed) pins uv 0.12.17 in CI, because a 14-day supply-chain
cooldown rules out uv 0.13.0 (released 2026-10-09) until 2026-10-23; the local uv is 0.13.1. So CI's
first run would fail on a defect the local gate cannot see.

The failure is the offline row of the release gate's dependency audit (`bin/audit_lock.py`). Told
to audit offline, uv 0.12 prints "Network connectivity is disabled, but the requested data wasn't
found in the cache", where uv 0.13 prints "…requires network access and cannot be performed in
offline mode". uv exits 2 either way and the wrapper still exits 2, so the audit does fail closed,
but under 0.12 it reports "the audit could not run" instead of "advisory source unreachable": the
wrapper's reason is wrong for a supported uv, and the test that pins 0.13's wording fails.

Reproduced at shaping (2026-10-17, from this worktree on `2b006fa`, uv 0.12.17 first on `PATH`,
`uv run --locked pytest -q tests/test_audit.py -k offline`): `test_audit_fails_closed_offline`
fails in **both** protocol eras, with `error: Network connectivity is disabled, but the requested
data wasn't found in the cache for: https://api.osv.dev/v1/querybatch` / `audit_lock: the audit
could not run (uv audit exited 2)`. The foreman's evidence from the `ci-workflow` build: the same
failure under 0.12.19, and every other gate step (`uv lock --check`, `uv sync --locked`, the online
audit, clean over 94 packages) works under 0.12.17.

The defect is pre-existing. It shipped with `stack-upgrade` (`acbdfd7`, "[refactor] Move to FastMCP
4 and MCP SDK 2"), which introduced `bin/audit_lock.py` and `tests/test_audit.py` with uv 0.13's
offline wording as the only one recognised and the one the test pins.

## Outcome / vision

The project declares the uv range it supports: a floor of 0.12.17 through the current release, and
uv itself refuses an older release with a message naming the version required. Across that range,
the full `verify` is green in both protocol eras, and the audit means the same thing: fails closed,
and an advisory source it cannot reach is reported as unreachable. The tests guard the wrapper's own
contract, so a future uv rewording a message cannot turn the suite red while the audit still
behaves.

## Acceptance criteria (the contract)

"Supported uv" means every release from 0.12.17 through the current one (0.13.1 at shaping); the
two ends are what a phase or review exercises.

- **R1** — WHEN the dependency audit runs offline under any supported uv, the audit SHALL exit 2 and
  report the advisory source as unreachable (today, under uv 0.12, it reports "the audit could not
  run").
- **R2** — IF the advisory source cannot be reached over the network under any supported uv, THEN
  the audit SHALL exit 2 and report the advisory source as unreachable.
- **R3** — IF `uv audit` exits nonzero for a reason the audit does not recognise, THEN the audit
  SHALL still exit nonzero (fails closed; unchanged).
- **R4** — WHEN the profile's full `verify` runs under uv 0.12.17, it SHALL pass in both protocol
  eras (today the offline audit test fails in both).
- **R5** — WHEN the profile's full `verify` runs under the current uv release, it SHALL pass in both
  protocol eras.
- **R6** — WHEN a uv release older than 0.12.17 is used to sync or run the project, uv SHALL
  refuse, with a message naming 0.12.17 as the required version.
- **R7** — The audit's tests SHALL pin the audit's own exit status and its own messages, and SHALL
  NOT require uv output text that a supported uv release does not print.
- **R8** — WHEN the dependency audit runs offline under any supported uv, it SHALL make no network
  request: the offline setting reaches uv. Today only uv 0.13's wording shows this, so under 0.12
  the suite cannot tell an offline audit from one whose offline setting was dropped and whose
  request then failed.

## Non-goals (no-gos)

- CI's uv pin and the supply-chain cooldown: the `ci-workflow` cycle owns both.
- New audit features, and any waiver mechanism for advisories.
- Moving the floor above 0.12.17, or supporting any uv below it.
- Running the audit inside `verify`: phase gates stay offline-capable and deterministic (profile,
  release-recipe `audit` caveat).

## Clarifications

- **Q:** Which uv releases are supported? — **A:** A floor of 0.12.17 (CI's pin: the lowest release
  shown to run the whole gate) through the current release. The full `verify` must be green, in both
  eras, under the floor and under the current release. The floor is declared where uv itself
  enforces it, so an older uv refuses with a message naming the required version; the plan picks the
  mechanism. (Foreman ruling, resolved 2026-10-17.)
- **Q:** Does the audit's contract change? — **A:** No. It fails closed on any nonzero uv exit. An
  offline or unreachable advisory source exits 2 and names the source as unreachable under every
  supported uv. Unrecognised failures still exit nonzero. (Foreman ruling, resolved 2026-10-17.)
- **Q:** What do the tests pin? — **A:** The wrapper's own contract: exit status and its own
  message. They do not pin a uv message string that a supported release lacks. (Foreman ruling,
  resolved 2026-10-17.) Shaping reads this as covering the integration row's current check for uv's
  own offline refusal (`OFFLINE_REFUSAL`, which 0.12 does not print). Keeping the row offline by
  construction (no advisory request attempted) remains the plan's job, by means that hold under every
  supported uv. Foreman, at the GOAL gate (2026-10-17): the no-request property is a requirement,
  R8, not only a plan concern. It is the check that catches the offline setting being dropped before
  it reaches uv, which an exit status of 2 alone cannot.
- **Q:** What is out of scope? — **A:** CI's pin and the cooldown (cycle 3 owns those), new audit
  features, waivers, and moving the floor above 0.12.17. (Foreman ruling, resolved 2026-10-17.)
- **Q:** How are the criteria phrased? — **A:** As the observable broken→fixed behaviour, never the
  mechanism (`kind: fix`). (Foreman ruling, resolved 2026-10-17.)
- **Q:** How far does R6's refusal reach? — **A:** To every uv release that reads `[tool.uv]
  required-version`, which is 0.5.14 and later: each of those, when older than 0.12.17, refuses and
  names 0.12.17. Releases 0.5.13 and earlier predate the field; they warn about an unknown field and
  run, and no uv-native mechanism reaches them, so the project's texts say exactly that rather than
  claiming every older uv refuses. (Geoffrey's ruling at the review-bound escalation, with a fourth
  review cycle scoped to verifying this and `main()`'s single offline decision, 2026-10-18.)

## Related materials

- Source: `bin/audit_lock.py` (the `UNREACHABLE` markers, lines 50–52, and `audit_violations`);
  `tests/test_audit.py` (`OFFLINE_REFUSAL`, line 58; `offline_violations` and
  `test_audit_fails_closed_offline`, lines 114–144); `pyproject.toml`.
- Profile: `AGENTS.md` § Factory → `verify`, and the release recipe's `audit` caveat.
- Origin of the defect: `spec/stack-upgrade/` (landed as `acbdfd7`).
- Cross-cycle: the `ci-workflow` cycle (cycle 3), whose build surfaced the failure under uv 0.12.17.
