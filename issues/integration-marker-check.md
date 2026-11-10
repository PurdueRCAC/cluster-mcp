---
status: unshaped
kind: test
appetite: big
lane: public
---

# Nothing checks that an `integration` test needs what a `unit` test is refused

## Problem

Once `integration-marker-wording` lands, the two marker descriptions in `pyproject.toml` state the
line the unit guard draws: a `unit` test starts no process, opens no connection and sees no real
HOME; an `integration` test is one that needs one of those, and every process it launches goes
through `bin/sandbox.sh`. Nothing checks the second half. The collection hook
(`tests/conftest.py`, `pytest_collection_modifyitems`) only requires one of the two markers, and the
`guard` fixture is inactive for every test that is not `unit`. So a test that needs none of what
the guard refuses can carry `integration`, and then runs without the guard's protections: the real
HOME and XDG directories, and the cluster, identity-map and secret variables `BLANKED_ENV` would
blank, all reach it, and nothing refuses a process or a connection it was never meant to make.

A check that every `integration` test does need what `unit` forbids has to classify every kind of
`integration` test the suite has, and those the 0.2.0 gate cycles add:

1. a drive of the installed CLI;
2. another program run through `bin/sandbox.sh` (git, a login shell, a script run for real);
3. a child Python interpreter run through `bin/sandbox.sh` (a sibling cycle's planned annotation
   check, which launches a child interpreter through the sandbox);
4. a stand-in program launched in place of a host tool (`full-volume-fixture-leaks-hdiutil`'s
   `hdiutil` stand-in);
5. the `local` and `delegate` backends run for real under the `executes` fixture;
6. a server started in its own process and reached over stdio (`stdio_tools`, `stdio_refusal`);
7. a connection to a loopback server (the loopback SSH server, `url_tools`);
8. a launch or connection made by a fixture or a helper module rather than the test body;
9. a real sandboxed child that is killed, or that outlives a timeout (`mutant-child-outlives-timeout`,
   `sandbox-dirs-left-on-kill`).

Kind 8 is the trap. A launch made by a session-scoped fixture (`core_only`, the core-only install
in `tests/test_core_only.py`) happens before the test body runs, and once for many tests; a launch
or connection made in a helper module (`tests/harness.py`'s `stdio_tools` and `url_tools`,
`tests/ssh_server.py`'s loopback SSH server, `tests/mutants.py`) is outside the test module. A
check that watches only the test body, or only the test's own module, misclassifies them, and the
pins for such a check tend to be found one layer at a time in review.

## Why it was deferred

Ruled out of `integration-marker-wording` at its GOAL gate, 2026-11-09 (Q1, option C): that cycle
is `small` and settles the wording plus a word-for-word check that `AGENTS.md` § Testing states the
markers as `pyproject.toml` does. A classification check over every `integration` test is a
separate, bigger piece of work, and may need a recording pass over the integration suite whose CI
cost is the maintainer's call.

**Pre-existing:** yes. No check has ever tied the `integration` marker to what a test does.

## Outcome / vision

A test that carries `integration` but needs nothing the unit guard refuses fails the run, naming
the test, and every kind above passes, with no carve-out the marker descriptions lack.

## Sketch of the acceptance criteria

- **R1** — IF a collected test carries `integration` and launches no process, opens no connection
  and reads no real HOME, whether in its body, its fixtures of any scope or a helper module, THEN
  the suite SHALL fail, naming the test.
- **R2** — The check SHALL pass each of the nine kinds above, each pinned by a planted row.
- **R3** — The check's negative controls SHALL include additive mutants: a version of the check
  that grows a carve-out the marker descriptions lack (a fixture name, a module, a marker, a kind
  passed without looking) SHALL be killed by a named planted row.
- **R4** — Any CI-time cost SHALL be reported before and after, for the maintainer's ruling against
  the profile's `ci budget`.

## Notes

- Related: `spec/integration-marker-wording/` (GOAL, Q1); `issues/integration-marker-wording.md`;
  `tests/conftest.py` (`guard`, `pytest_collection_modifyitems`); `tests/test_hygiene.py`
  (`sandbox_violations`).
- Found by: `integration-marker-wording` shaping, 2026-11-09; deferred at its GOAL gate.
