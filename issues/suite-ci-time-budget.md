---
status: unshaped
kind: test
appetite: small
lane: public
---

# Each CI era job spends more than PLAN's growth threshold on real-time loopback rows

## Problem

Each protocol era's suite runs as one CI job with a 20-minute timeout (`.github/workflows/ci.yml`,
`suite-legacy` and `suite-modern`). `ssh-half-open-link` added 41 real-time loopback rows,
which pin a silent SSH link at a 2 s connect bound. Their waits are built in, not slack:
- a call in flight waits out the background verdict, about 3B − 1 = 5 s;
- a call to a gone host waits out the verdict and a 2 s banner timeout, about 4.1 s;
- a slow transfer must outlast 3B, so about 7–8 s;
- an idle or quiet command must stay quiet past 3B, about 7 s.

The cycle's PLAN (§6) set a trim threshold of +180 s per era. The cycle passed it.

**Measured, pytest's own time per era:**

| Tree | CI handshake | CI modern | Local handshake | Local modern |
|---|---|---|---|---|
| plan head (`7bf9666`, the suite as on `develop` `13c0e83`) | 555 s | 524 s | 542 s | 546 s |
| after P1 (`925d459`) | 697 s | 629 s | 618 s | 619 s |
| after P2 (`8ff5108`) | 739 s | 735 s | 765 s | 713 s |
| after P3 (the sweep's unit rows added) | — | — | 790 s | 753 s |
| `develop` (`13c0e83`), run back to back with the P3 row | — | — | 581 s | 521 s |
| review cycle 2's remediation (`82b1f0e`), run back to back | — | — | 740 s | 730 s |
| after it (this tree's last phase), run back to back | — | — | 768 s | 776 s |

- CI's era jobs took about 12 and 13.8 minutes on `8ff5108`, of the 20-minute timeout.
- Back to back on this Mac, at P3, the cycle's tree took 209 s (handshake) and 232 s (modern) more
  than `develop`.
- The local runs were on macOS, 10 cores. The P2 handshake figure ran beside another session's
  suites, at load 2–4, so it is an upper bound.
- P2's rows alone took about 103 s per era locally.
- The slowest new rows:
  - `test_a_slow_transfer_is_not_taken_for_a_silent_link[put|get|write]`, 8.0–8.6 s each;
  - `test_a_quiet_command_is_not_taken_for_a_silent_link[slow-link]`, 9.3 s;
  - the idle, quiet and silent-spell rows, about 7 s each;
  - the nine `test_a_transfer_on_a_link_that_goes_silent_may_be_partly_made` shapes, 5.0–5.3 s each;
  - the gone-host rows, 4.1–4.25 s each.

- 2026-11-05: review cycle 2's remediation adds 4 real-time rows to the default suite (two late
  reconnects onto a link that goes silent again, under a 3 s connect bound, about 9 s each; two onto
  a live link, about 4 s each) and 19 fast ones. Back to back on this Mac, base first, load about 2:
  +28 s handshake (740 s to 768 s, 3.7%) and +46 s modern (730 s to 776 s, 6.3%). A first handshake
  pair, its base run begun at load 5.7, read 769 s and 770 s and was re-run once. At CI's rate the
  era jobs would go from about 12.5 to about 13–13.3 of their 20 minutes.

A further cycle of the same size would bring an era job near its timeout.

**Pre-existing:** the budget is shared with every earlier real-time row (the stalling and slow-link
rows took 4–11 s each before this cycle). The growth past the threshold is `ssh-half-open-link`'s.

## Why it was deferred

The growth was measured at `ssh-half-open-link`'s P2, and its P3 is the sweep and the ledger. The
frozen gate (`spec/ssh-half-open-link/verify/silent-gate.py`) names each default row by id, so no
row could move behind `CLUSTER_MCP_TEST_EVERY_KIND=1` there. A trim is a CI and suite change of its
own, which belongs to a cycle of its own.

## Outcome / vision

Each era job keeps a clear margin under its timeout as cycles add rows, without dropping a row's
proof.

Directions to weigh (none chosen):
- **A parallel runner** (for example, pytest-xdist), with each loopback server, hop and sandbox
  already per test. The fixtures that bind process-wide state need checking first: the `guard`
  fence, the session-scoped PATH shim, and `threading.excepthook`.
- **Each era split into two CI jobs**, by module or by marker, keeping `ci.yml` and the profile's
  `verify` in step (`AGENTS.md` § Conventions, "CI mirrors the gate").
- **Shorter built-in waits.** For example:
  - a smaller connect bound for the silent rows. B = 1 leaves no room for a reconnect after a
    verdict (`spec/ssh-half-open-link/PLAN.md` §4.1, finding 1), so this needs the arithmetic
    redone;
  - a slower hop for the slow-transfer rows, so less data outlasts 3B;
  - sharing one idle period across the R4 rows.

## Sketch of the acceptance criteria

- **R1** — Each era's CI job SHALL finish with at least a set margin under its timeout, measured on
  the runner.
- **R2** — Every row the trim touches SHALL still fail where it failed before, shown by the cycles'
  develop-fails gates or an equivalent.

## Notes

- Related: `spec/ssh-half-open-link/` (PLAN §6, TECH P3);
  [`stalled-reconnect-test-timing.md`](stalled-reconnect-test-timing.md) (load sightings of
  real-time rows); [`mutants-workflow-timeout.md`](mutants-workflow-timeout.md).
- Found by: `ssh-half-open-link` P2 and its CI runs, 2026-11-05; filed by its P3.
