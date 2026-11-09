# GOAL — The test markers say what the unit guard enforces

> **Origin spec.** The *what* and *why* — the locked contract `code-review` grades against.
> The *how* lives in [`PLAN.md`](PLAN.md) and [`TECH.md`](TECH.md) (written by `code-plan`).

- **slug:** integration-marker-wording
- **kind:** test
- **appetite:** small

## Problem

`pyproject.toml` describes the suite's two pytest markers (`[tool.pytest.ini_options]`, the
`markers` list): `unit` is "fast and isolated; no subprocess, no network, no real cluster", and
`integration` is "drives the installed CLI; run it under bin/sandbox.sh". Neither line states the
rule the suite enforces:

- **What `unit` means** is drawn by the unit guard (`tests/conftest.py`, the `guard` fixture): in a
  `unit` test it refuses every process entry point (`PROCESS_ENTRY_POINTS`) and every connection and
  name lookup (`NETWORK_ENTRY_POINTS`), and it replaces HOME and the XDG directories with scratch
  ones and blanks the cluster, identity-map and secret variables (`BLANKED_ENV`). Nothing enforces
  "fast".
- **What `integration` means** is "not `unit`": the collection hook (`pytest_collection_modifyitems`)
  requires every test to carry one of the two, and the guard is inactive for every test that is
  not `unit`.
- **The sandbox rule** the suite enforces is per launch: `tests/test_hygiene.py::test_cli_drives_are_sandboxed`
  (`sandbox_violations`) requires every launch in `tests/*.py` outside a `unit`-marked function to
  start with `bin/sandbox.sh`. "Run it under bin/sandbox.sh" can also be read as wrapping the whole
  `-m integration` run, which `AGENTS.md`'s development commands show for a manual run; the profile's
  `verify` and CI run the suite unwrapped.

The `integration` description is already wrong for many tests that drive no CLI, not only the one
the seed found: `test_docs_modules_absent` and the git-backed absence-message controls in
`tests/test_registry.py` start git; the `executes` fixture runs the `local` and `delegate` backends
for real; `stdio_tools` and `stdio_refusal` start a server in its own process; the loopback SSH
server and `url_tools` reach a host; login-shell rows and the site and audit scripts run real
programs. `AGENTS.md` § Testing notes the mismatch in the `tests/test_registry.py` entry ("So
`test_docs_modules_absent` is `integration` although it drives no CLI") instead of fixing it.

It matters now because the 0.2.0 gate cycles in flight add more `integration` tests that drive no
CLI: a child interpreter through `bin/sandbox.sh` (`annotation-check`, in a new
`tests/test_annotations.py`), a stand-in for `hdiutil` (`full-volume-fixture-leaks-hdiutil`), and
possibly real sandboxed children that are killed or outlive a timeout
(`mutant-child-outlives-timeout`, `sandbox-dirs-left-on-kill`). A reader choosing a marker for any
of them is left to guess.

**Pre-existing:** partly. The description predates `absence-check-leftover-classification`, which
added the first `integration` tests whose own `AGENTS.md` entry says the description misfits them.

## Outcome / vision

The two marker descriptions in `pyproject.toml` state the line the unit guard draws: a `unit` test
starts no process, opens no connection and sees no real HOME; an `integration` test is any test that
needs one of those, and every process it launches goes through `bin/sandbox.sh`. Every kind of
`integration` test the suite has, and every kind the 0.2.0 gate cycles add, fits that text with no
exception clause. `AGENTS.md` states the markers in the same terms and drops its note about the
mismatch.

## Acceptance criteria (the contract)

- **R1** — The `unit` marker's description in `pyproject.toml` SHALL state what the unit guard
  enforces on a `unit` test: it starts no process, opens no network connection (a name lookup
  included) and sees no real HOME. [NEEDS CLARIFICATION: Q2, whether "fast" stays in the `unit`
  description.]
- **R2** — The `integration` marker's description in `pyproject.toml` SHALL say the marker is for a
  test that needs what a `unit` test is refused, and SHALL keep the rule the suite enforces on it:
  every process the test launches goes through `bin/sandbox.sh`. It SHALL NOT describe the marker
  as driving the CLI.
- **R3** — Read together, the two descriptions SHALL classify each of these kinds of test as
  `integration`, by their wording alone, with no exception clause:
  1. a drive of the installed CLI;
  2. another program run through `bin/sandbox.sh` (git, a login shell, a script run for real);
  3. a child Python interpreter run through `bin/sandbox.sh` (`annotation-check`);
  4. a stand-in program launched in place of a host tool (`full-volume-fixture-leaks-hdiutil`'s
     `hdiutil` stand-in);
  5. the `local` and `delegate` backends run for real under the `executes` fixture;
  6. a server started in its own process and reached over stdio (`stdio_tools`, `stdio_refusal`);
  7. a connection to a loopback server (the loopback SSH server, `url_tools`);
  8. a launch or connection made by a fixture or a helper module rather than the test body;
  9. a real sandboxed child that is killed, or that outlives a timeout (`mutant-child-outlives-timeout`,
     `sandbox-dirs-left-on-kill`);

  and SHALL classify a test that does none of these, and reads no real HOME, as `unit`.
- **R4** — `AGENTS.md` SHALL state the markers in the same terms as `pyproject.toml` wherever it
  says what a marker means (§ Testing; the development-commands block; § Conventions' marker
  bullet), and SHALL NOT keep the note that an `integration` test drives no CLI by exception (the
  `tests/test_registry.py` entry in § Testing).
- **R5** — [NEEDS CLARIFICATION: Q1, whether this cycle adds a check, and which.] Draft for the
  recommended option (B): a `unit` test SHALL hold `AGENTS.md` § Testing's statement of the two
  markers to the `pyproject.toml` descriptions word for word, as
  `test_the_id_rule_is_stated_as_the_check_enforces_it` does for the spec-id rule. Its standing
  negative controls SHALL include planted rows for: a description changed in `pyproject.toml`
  alone; a statement changed in `AGENTS.md` alone; either statement missing; a third marker added
  in one place; and additive drifts, a clause (such as an exception) present in one place and
  absent from the other, at the start, the middle and the end of a description. Each row SHALL be
  one that a version of the check carrying an extra carve-out (ignoring case, punctuation,
  whitespace beyond line wrapping, or a trailing clause) would wrongly pass, so every such carve-out
  is killed by a named row.

## Non-goals (no-gos)

- No change to the unit guard, the collection hook, `sandbox_violations` or `bin/sandbox.sh`.
- No test changes marker in this cycle. A test this cycle finds mismarked by the new wording is
  filed as a seed.
- No new rule on `integration` tests beyond what the suite enforces today (for example
  "loopback hosts only" or "never the real HOME"): the descriptions state existing rules.
- No check that every `integration` test needs what `unit` forbids (option C under Q1) unless Q1
  chooses it; otherwise it is filed as a seed.
- The sibling gate cycles' own tests: this cycle settles the wording they are checked against.
- No change to `verify`, the CI jobs or their split, and no timing or CI-cost bound.
- Docstrings in `tests/` are not part of the contract; the plan may align the `guard` fixture's if
  it restates a marker's meaning.

## Clarifications

- **Q1** — [NEEDS CLARIFICATION: does the cycle add a check?] (A) wording only: R1–R4, reviewed by
  reading against R3's kinds; (B) wording plus a static `unit` check that holds `AGENTS.md` §
  Testing's statement to `pyproject.toml` word for word (R5 as drafted); (C) B plus a check that
  every `integration` test needs what the guard refuses, classifying every kind in R3 (each kind a
  planted row, kind 8 the hardest, since a launch in a fixture of wider scope or in `harness.py`,
  `ssh_server.py` or `mutants.py` happens outside the test body), with additive mutants for each
  carve-out a check could grow; its CI cost would need before-and-after figures. Open.
- **Q2** — [NEEDS CLARIFICATION: does "fast" stay in the `unit` description?] (a) drop it: `unit`
  is defined only by what the guard refuses, and nothing enforces speed; (b) keep it as a
  non-binding note beside the rule; (c) make it a rule, which needs a bound (the maintainer's call,
  with figures). Open.

## Related materials

- Seed: [`issues/integration-marker-wording.md`](../../issues/integration-marker-wording.md)
- Origin: [`spec/absence-check-leftover-classification/`](../absence-check-leftover-classification/) (PLAN §5, P1)
- Source: `pyproject.toml` (`[tool.pytest.ini_options]` `markers`); `tests/conftest.py` (`guard`,
  `UnitGuard`, `PROCESS_ENTRY_POINTS`, `NETWORK_ENTRY_POINTS`, `BLANKED_ENV`,
  `pytest_collection_modifyitems`); `tests/test_hygiene.py` (`sandbox_violations`,
  `test_cli_drives_are_sandboxed`, `test_the_id_rule_is_stated_as_the_check_enforces_it`);
  `AGENTS.md` § Testing, § Conventions, development commands.
- Sibling 0.2.0 gate seeds whose tests R3 names: `issues/annotation-check.md`,
  `issues/full-volume-fixture-leaks-hdiutil.md`, `issues/mutant-child-outlives-timeout.md`,
  `issues/sandbox-dirs-left-on-kill.md`.
