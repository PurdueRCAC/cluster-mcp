---
status: unshaped
kind: test
appetite: small
lane: public
---

# The checks behind the marker rules miss routes the rules forbid

## Problem

Once `integration-marker-wording` lands, the marker descriptions in `pyproject.toml` state two
rules: a `unit` test starts no process, opens no network connection (a name lookup included) and
sees no real HOME, which the unit guard holds it to except on the open routes `AGENTS.md`
§ Testing names, and every process an `integration` test launches goes through `bin/sandbox.sh`.
An executed probe against `tests/conftest.py` (`spec/integration-marker-wording/verify/guard_claims.py`,
2026-11-09) found routes each rule's check leaves open:

1. **A `Popen` class bound before the test launches in a `unit` test.** The unit guard replaces
   `subprocess.Popen` and `_posixsubprocess.fork_exec` by name, but `subprocess` binds
   `fork_exec` at import (`from _posixsubprocess import fork_exec as _fork_exec`), so a class
   reference taken earlier still forks: `conftest.REAL_POPEN`, or a module-level
   `from subprocess import Popen`. `subprocess.run`,
   `os.system`, `os.fork`, `posix_spawn`, `multiprocessing` (fork and spawn), a process pool and
   `asyncio.create_subprocess_exec` are all refused.
2. **A connection or lookup below, or bound before, the replaced names reaches the network in a
   `unit` test.** The guard refuses `socket.socket.connect`, `connect_ex`, `create_connection` and
   `socket.getaddrinfo` (asyncio's connections and lookups go through them, and are refused), but
   a `_socket.socket` connects below them, a UDP `sendto` needs no connect, a `getaddrinfo`
   bound before the test (`from socket import getaddrinfo`) is the original, and
   `socket.gethostbyname`, `gethostbyname_ex`, `gethostbyaddr` and `getnameinfo` resolve in C, past
   `getaddrinfo`.
3. **A fixture of wider scope launches before the guard is active.** The guard is a function-scoped
   fixture, so a session- or module-scoped fixture a `unit` test uses has already run whatever it
   launched.
4. **A launch through `conftest.REAL_POPEN` is outside `bin/sandbox.sh` and unread by the static
   check.** `tests/test_ssh_exec.py`'s `_host` runs `hdiutil` that way for the macOS full-volume
   fixture, and `sandbox_violations` (`test_cli_drives_are_sandboxed`) reads `subprocess`, `os` and
   `asyncio` calls and bare names imported from them, not a call through a name bound to the class
   elsewhere.
5. **An `XDG_*` variable other than the three the guard sets reaches a `unit` test unchanged.**
   The guard points `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_DATA_HOME` under
   `tmp_path`; an `XDG_STATE_HOME` (or `XDG_RUNTIME_DIR`, `XDG_CONFIG_DIRS`, `XDG_DATA_DIRS`) the
   shell exported keeps the value the shell gave it. Probed by
   `spec/integration-marker-wording/remediation/F1-guard-wording.py`.

Whether any `unit` test reaches the first three or the fifth today was not surveyed; the fourth is
in use. The password database (`pwd.getpwuid(...).pw_dir`) still names the real home in a `unit`
test; `AGENTS.md` § Testing names it beside the guard with the fifth.

## Why it was deferred

`integration-marker-wording` states the rules and may not change the unit guard, the collection
hook, `sandbox_violations` or `bin/sandbox.sh` (its non-goals), and moving `_host` belongs with the
fixture's own cycle.

**Pre-existing:** yes. Each route predates the wording.

## Outcome / vision

Each rule the marker descriptions state is refused by its check on every route the probe found:
the guard refuses a launch through any `Popen` class, every connection and every name lookup,
points every `XDG_*` base directory under `tmp_path`, and either catches a wider fixture's
launch or the rule says it does not; the static check reads a call through a name
bound to a launcher, and every such launch in `tests/` goes through `bin/sandbox.sh`.

## Sketch of the acceptance criteria

- **R1** — IN a `unit` test, a launch through a `Popen` class bound before the test SHALL be
  refused and recorded, as a launch through `subprocess.Popen` is.
- **R2** — IN a `unit` test, a `_socket` connect, a UDP send, an early-bound `getaddrinfo`, and
  `gethostbyname`, `gethostbyname_ex`, `gethostbyaddr` and `getnameinfo` SHALL be refused and
  recorded.
- **R3** — `sandbox_violations` SHALL flag a call through a name bound to a launcher class or
  function (`REAL_POPEN`), and `_host` SHALL launch through `bin/sandbox.sh` or carry a stated,
  checked exception the marker description names.
- **R4** — Each of the above SHALL have a standing planted control, and the marker descriptions'
  probe (`guard_claims.py`) SHALL move into the suite.
- **R5** — IN a `unit` test, every `XDG_*` base-directory variable SHALL point under `tmp_path`
  or be unset, with a standing planted control, and the probe of it
  (`F1-guard-wording.py`) SHALL move into the suite with R4's.

## Notes

- Related: `spec/integration-marker-wording/` (PLAN, deviation table); `issues/integration-marker-check.md`;
  `issues/full-volume-fixture-leaks-hdiutil.md`; `tests/conftest.py` (`guard`, `UnitGuard`,
  `PROCESS_ENTRY_POINTS`, `NETWORK_ENTRY_POINTS`, `REAL_POPEN`); `tests/test_hygiene.py`
  (`sandbox_violations`); `tests/test_ssh_exec.py` (`_host`).
- Found by: `integration-marker-wording` plan, 2026-11-09.
