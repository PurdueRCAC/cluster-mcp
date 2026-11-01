---
status: unshaped
kind: fix
appetite: small
lane: public
---

# A sandbox killed with SIGKILL leaves its directory behind

## Problem

`bin/sandbox.sh` makes its throwaway HOME with `mktemp -d "${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"`
(`bin/sandbox.sh:59`) and removes it from a trap, `trap 'rm -rf "$sandbox"' EXIT HUP INT TERM`
(`bin/sandbox.sh:60`). SIGKILL cannot be trapped, so when a caller kills the sandbox's process group
with SIGKILL the shell dies without running the trap, and the directory stays: the skeleton the
script makes (`.config`, `.cache`, `.local/share`), sometimes with FastMCP's `version_cache.json`.

Several test harnesses stop a sandboxed process that way. The one measured here is
`LoopbackSSH.close()` (`tests/ssh_server.py`, `os.killpg(proc.pid, signal.SIGKILL)` for every exec it
started that is still running), whose sandboxes take the host's `TMPDIR`. Others that SIGKILL a
sandbox group on some path: `tests/test_startup.py` (`run_bounded`, on a timeout),
`tests/test_transports.py` (after SIGTERM's grace), `tests/test_probe_startup.py` (`over_http`) and
`spec/capability-probe/verify/drives.py`. The last three point the drive's `TMPDIR` at the test's
own directory, so what they leave is removed with it, and `test_transports.py` asserts the sandbox
was removed on its SIGTERM path.

Observed on a developer Mac, 2026-11-01:

- The host's `TMPDIR` held 18,061 `cluster-mcp-sandbox.*` directories, the oldest from 2026-10-17;
  12 of them hold a file, the rest only the skeleton.
- One full-suite run, alone on the host, left 59 in the handshake era and 58 in the modern era.
- Every mutation case runs a slice of the suite, so a mutation sweep leaves many more (a build
  reported 346 in two hours).

**Pre-existing:** yes. The trap and every harness named above predate `capability-probe`. That
cycle's own drives were measured on its finished tree: `drives.py all` and the integration rows of
`tests/test_probe_startup.py` left none in the host's `TMPDIR` in either era;
`test_the_lookup_over_ssh` (`tests/test_probes.py`) left one or two per run, through
`LoopbackSSH.close()`.

## Why it was deferred

Found while building `capability-probe`; it sits outside that cycle's GOAL. The fix touches
`bin/sandbox.sh`, the throwaway environment every drive and gate runs in, or the shared test
harness, and either one is a change of its own.

## Outcome / vision

A drive, test or gate leaves no `cluster-mcp-sandbox.*` directory in the host's `TMPDIR`, however the
sandbox is stopped. The directories already there are the developer's to remove; nothing here
deletes them.

## Sketch of the acceptance criteria

Left unshaped. Shapes a fix might take, none of them chosen:

- the harnesses stop a sandbox group with SIGTERM first and SIGKILL only after a grace, as
  `test_transports.py` does;
- every harness points the sandbox's `TMPDIR` at the test's own directory, as `test_probe_startup.py`
  does, so whatever is left goes with it;
- a session-scoped fixture gives the whole suite one `TMPDIR` and removes it at the end;
- `bin/sandbox.sh` keeps its sandboxes under one parent it sweeps of entries whose owner is gone.

- **R1** — WHEN the suite runs to its end, the host's `TMPDIR` SHALL hold no `cluster-mcp-sandbox.*`
  directory the run created.

## Notes

- Related: [`local-command-outlives-server.md`](local-command-outlives-server.md) (a killed server's
  `local` process group runs on).
- Found by: `capability-probe` P2 build, measured at P3, 2026-11-01.
