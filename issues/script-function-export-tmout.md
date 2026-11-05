---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A profile's sub-second `TMOUT` may drop the functions a script inherits

## Problem

A `run_command` script runs in a fresh non-login bash that inherits the login initialisation's
functions (`module` among them). The program exports them first, one name per line
(`launch.SCRIPT`):

    while IFS= read -r cluster_mcp_fn; do export -f -- "$cluster_mcp_fn"; done < <(compgen -A function)

That `read` runs in the login bash, after every startup file, so a profile's `TMOUT` is its
default timeout, and a readonly `TMOUT` cannot be undone. bash 4 and later accept a fractional
`TMOUT` for `read` (bash 3.2 takes whole seconds only). If `compgen`'s process substitution has not
written a line when the timeout passes, `read` fails, the loop ends, and every function not yet
exported is missing from the script's bash, which then cannot run `module`. A site's `TMOUT` of
minutes never comes near it; only a sub-second one could.

**Unmeasured.** It is read from bash's source, not seen: the development host has bash 3.2 only,
where `TMOUT` is at least one second and `compgen` answers in milliseconds.

**Pre-existing:** yes. `SCRIPT`'s loop is on `develop` at `c8843b2`. `timeout-process-cleanup`
removed the same hazard from its own watchdog, which no longer waits on `read`; this loop is the
program's other `read`.

## Why it was deferred

Found while scoping `timeout-process-cleanup`'s review finding F1 (a profile's `TMOUT` ending the
watchdog's wait). It is not a timeout's stop, it was not measured, and the export loop is pinned by
its own rows (§ Invariants §2), so it is a change of its own.

## Outcome / vision

Every function the login initialisation defines reaches a `run_command` script's bash, whatever
`TMOUT` a startup file sets.

## Sketch of the acceptance criteria

Left unshaped. The measurement a shaping step needs first, on bash 4.4 and 5.x (the CI runner, or
a container), in `local`, `delegate` and `ssh` through the suite's fixtures:

- a `.bash_profile` that defines a few dozen functions, `module` last, and sets a readonly `TMOUT`
  of `0.001`, `0.01`, `0.1` and `1`;
- `run_command 'type module'` a few hundred times per value, quiet and under CPU load, counting the
  runs where `module` is missing;
- the time from the loop's start to `compgen`'s first line, to size the risk against real values.

- **R1** — WHEN a startup file sets any `TMOUT`, readonly or not, a `run_command` script SHALL see
  every function the login initialisation defined.

## Notes

- Related: [`timeout-stop-limits.md`](timeout-stop-limits.md) (what the watchdog still cannot stop);
  `AGENTS.md` § Invariants §2 (the function export).
- Found by: `timeout-process-cleanup` review-cycle-1 remediation (F1's class), 2026-11-02.
