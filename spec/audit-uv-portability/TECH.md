---
slug: audit-uv-portability
title: The dependency audit and the suite work under every supported uv
kind: fix
appetite: small
status: done
branch: fix/audit-uv-portability
base: develop
current_phase: done
last_updated: '2026-10-18'
phases:
- id: P1
  name: The wrapper decides offline; the tests pin the wrapper and count requests
  status: done
  satisfies:
  - R1
  - R2
  - R3
  - R7
  - R8
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run --no-project --isolated --with uv==0.12.17 sh -c 'uv --version |
    grep -qF 0.12.17 && uv run pytest -q tests/test_audit.py::test_audit_check_accepts_a_clean_audit
    tests/test_audit.py::test_audit_check_catches tests/test_audit.py::test_offline_audit_is_unreachable_whatever_uv_says
    tests/test_audit.py::test_offline_setting_reaches_uv_as_a_flag tests/test_audit.py::test_offline_audit_with_findings_still_exits_unreachable
    tests/test_audit.py::test_main_runs_the_command_and_env_it_derives tests/test_audit.py::test_audit_env_drops_uv_selectors
    tests/test_audit.py::test_audit_names_this_checkout_whatever_uv_project_says tests/test_audit.py::test_audit_fails_closed_offline
    tests/test_audit.py::test_audit_fails_closed_unreachable tests/test_audit.py::test_wrapper_reads_uv_offline_as_uv_does
    && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_audit.py' && uv run
    --no-project --isolated --with uv==0.13.1 sh -c 'uv --version | grep -qF 0.13.1
    && uv run pytest -q tests/test_audit.py::test_audit_check_accepts_a_clean_audit
    tests/test_audit.py::test_audit_check_catches tests/test_audit.py::test_offline_audit_is_unreachable_whatever_uv_says
    tests/test_audit.py::test_offline_setting_reaches_uv_as_a_flag tests/test_audit.py::test_offline_audit_with_findings_still_exits_unreachable
    tests/test_audit.py::test_main_runs_the_command_and_env_it_derives tests/test_audit.py::test_audit_env_drops_uv_selectors
    tests/test_audit.py::test_audit_names_this_checkout_whatever_uv_project_says tests/test_audit.py::test_audit_fails_closed_offline
    tests/test_audit.py::test_audit_fails_closed_unreachable tests/test_audit.py::test_wrapper_reads_uv_offline_as_uv_does
    && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q tests/test_audit.py'
- id: P2
  name: Declare the uv floor where uv enforces it
  status: done
  satisfies:
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: '! git grep -qiE ''older uv (release )?refuses|uv older than [^ ]+ refuses''
    -- '':!spec/'' && grep -qF ''0.5.13 and earlier'' AGENTS.md && grep -qF ''0.5.13
    and earlier'' pyproject.toml && uv run --no-project --isolated --with uv==0.5.14
    sh -c ''uv --version | grep -qF 0.5.14 && ! uv sync --locked && ! uv run true
    && uv sync --locked 2>&1 | grep -qF 0.12.17 && uv run true 2>&1 | grep -qF 0.12.17''
    && uv run --no-project --isolated --with uv==0.5.13 sh -c ''uv --version | grep
    -qF 0.5.13 && out=$(uv run --locked true 2>&1) && printf "%s\n" "$out" | grep
    -qF "unknown field \`required-version\`"'' && uv run --no-project --isolated --with
    uv==0.12.16 sh -c ''uv --version | grep -qF 0.12.16 && ! uv sync --locked && !
    uv run true && uv sync --locked 2>&1 | grep -qF 0.12.17 && uv run true 2>&1 |
    grep -qF 0.12.17'' && uv run --no-project --isolated --with uv==0.12.17 sh -c
    ''uv --version | grep -qF 0.12.17 && uv lock --check && uv sync --locked'''
- id: P3
  name: The full verify, both eras, at both ends of the supported range
  status: done
  satisfies:
  - R4
  - R5
  depends_on:
  - P1
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run --no-project --isolated --with uv==0.12.17 sh -c 'uv --version |
    grep -qF 0.12.17 && uv lock --check && uv run pytest -q && CLUSTER_MCP_TEST_ERA=modern
    uv run pytest -q && bin/sandbox.sh uv run rcac-mcp --help' && uv run --no-project
    --isolated --with uv==0.13.1 sh -c 'uv --version | grep -qF 0.13.1 && uv lock
    --check && uv run pytest -q && CLUSTER_MCP_TEST_ERA=modern uv run pytest -q &&
    bin/sandbox.sh uv run rcac-mcp --help'
review:
  last_reviewed_commit: 4fe1030753cbf792eeea6b7d917eba86e200f74d
  verdict: approved
  blocked_reason: ''
  cycle: 4
---

# TECH.md — The dependency audit and the suite work under every supported uv

The **context engine and finite-state machine** for building this fix. The YAML frontmatter above is
the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/audit-uv-portability/TECH.md`); the
per-phase checklists below are the work. `code-build` executes the next actionable phase, runs its
`verify:` command, updates state via `uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`,
and makes one atomic code+state commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md). Lean path: no `research/`; the prototype evidence
  is PLAN § 4.

## Frontmatter field reference

See the KB template (`skill/_templates/TECH.md`); nothing here departs from it.

## Conventions (apply to every phase)

- `AGENTS.md` is the constitution. This cycle touches § Conventions, § Packaging, § Testing (the
  `tests/test_audit.py` entry) and § Commands; no numbered § Invariants section and no
  high-blast-radius path.
- One phase per `code-build` invocation; one atomic `[fix] Build audit-uv-portability P<n>: …` commit
  holding the code and the `TECH.md` state change. No `Co-Authored-By` trailer.
- **Pinned uv releases** come from PyPI through `uv run --no-project --isolated --with uv==X.Y.Z sh -c
  '…'`, run from the worktree root: the wheel lands in uv's cache, never in the tree, and that
  environment's `bin/` is first on `PATH`, so every `uv` inside, including the one the audit wrapper
  launches, is X.Y.Z. Each gate asserts `uv --version` first. The `VIRTUAL_ENV … does not match the
  project environment` warning the inner `uv run` prints is expected and harmless.
- Comments and docstrings are declarative and carry no `R#`/`P#`.

---

## Phase P1 — The wrapper decides offline; the tests pin the wrapper and count requests
**Satisfies:** R1, R2, R3, R7, R8 · **Depends on:** —
**Goal:** an offline audit exits 2 as "advisory source unreachable" whatever uv prints, passes
`--offline` to uv, and is shown to make no request by a counting loopback proxy whose online twin
shows it does see this uv's requests; under uv 0.12.17 and 0.13.1, in both eras.

- [x] `bin/audit_lock.py`: add `FALSE_VALUES`, `offline_requested(environ)` (unset or a false value,
      case-insensitive, unstripped → online; anything else, empty, padded and garbage included →
      offline) and `command(environ)` (`COMMAND` becomes `ARGS`; the executable is `UV` when set,
      else `uv`; `--offline` appended when offline). `main()` takes one `environ` snapshot, runs
      `command(environ)` with `child_env(environ)`, and passes `offline` to `audit_violations`.
- [x] `audit_violations(returncode, output, lock_text, offline=False)`: offline decided first →
      `EXIT_UNREACHABLE` with `advisory source unreachable: the audit ran offline (uv audit exited
      N)` for any return code, findings named in a second reason; online unchanged (findings → 1).
- [x] `UV_ALLOWED`: remove `UV_OFFLINE`, add `UV_HTTP_RETRIES` (PLAN § 3 deviation). Update the module
      docstring: how offline is decided and passed, and that an offline audit exits 2.
- [x] `tests/test_audit.py`: remove `OFFLINE_REFUSAL`, `DEAD_PROXY` and the planted `id='offline'`
      row; add `test_offline_audit_is_unreachable_whatever_uv_says` (unit: a made-up wording, empty
      output, a clean exit-0 summary) and `test_offline_setting_reaches_uv_as_a_flag` (unit:
      unset, `1 true TRUE yes on`, empty, garbage, `0 false False no off`); move `UV_OFFLINE` to
      `dropped` and add `UV_HTTP_RETRIES` to `kept` in `test_audit_env_drops_uv_selectors`; the
      `' 0'` row; `test_offline_audit_with_findings_still_exits_unreachable` (unit);
      `test_main_runs_the_command_and_env_it_derives` (unit: `subprocess.run` recorded, `main()` run
      online with `UV`, offline with `UV`, offline without; argv is exactly `command(environ)` and
      env exactly `child_env(environ)`). `test_audit_names_this_checkout…` reads `command(…)`.
- [x] Add the canary (a `127.0.0.1:0` listener on a daemon thread that counts and closes each
      connection; `accept` on a short timeout in a loop on a stop event, `close()` sets it, joins,
      then closes the socket: a close does not wake a blocked `accept` on Linux) and one runner that drives the real script under `bin/sandbox.sh` with every proxy
      variable at the canary, `NO_PROXY`/`no_proxy` and inherited `UV_OFFLINE` removed,
      `UV_HTTP_RETRIES=0`, `TMPDIR=tmp_path`.
- [x] `test_audit_fails_closed_offline` (name kept) with `offline_violations(returncode, stderr,
      connections)` (name kept): exit 2, `audit_lock: advisory source unreachable`, zero connections.
      New `test_audit_fails_closed_unreachable` with `unreachable_violations(…)`: exit 2, the same
      message, at least one connection. Each runs its planted negatives before the real drive.
- [x] Rewrite the module docstring and `AGENTS.md` § Testing's `tests/test_audit.py` entry (it names
      `offline_violations`, the allowlist and uv's offline refusal) in this commit.
- [x] Check against PLAN § 4.1: each folded review finding is in the code above.
- [x] **Amendment (review cycle 1, F1, routed as its class).** Reopened for remediation: every value
      `main()` derives on its way to the verdict is pinned on the wrapper's own exit status and
      `audit_lock:` lines, so a wiring fault in `main()` fails under each supported uv on its own.
      Members: argv (and working directory), the child environment, the offline decision, the lock
      text, the combined output classified (and uv's exit status within it), and the lines printed
      and their streams (uv's passthrough, each reason, the success line, the exit status).
      `test_main_runs_the_command_and_env_it_derives` (name kept, so the stored gate is unchanged)
      becomes eight planted runs through a fake `subprocess.run` that answers only the expected
      launch; each compares `(status, stdout, stderr)` exactly. The integration rows now require
      their own mode's message (offline: "…: the audit ran offline"; online: "… (uv audit exited
      N)"), each with the other mode's message as a planted negative. Test module docstring and
      `AGENTS.md` § Testing entry updated in the same commit; `bin/audit_lock.py` unchanged (no seam
      needed). Eighteen `main()` mutants, all red under uv 0.13.1 alone (eleven passed before).
- [x] **Amendment (review cycle 2, F1, routed as its class).** Reopened for remediation: the
      wrapper's reading of `UV_OFFLINE` agrees with uv's for every value of uv's boolean vocabulary,
      in every case form, and for values outside it (read as offline), and the suite pins that
      agreement under each supported uv on its own; then a mutant sweep over every decision in
      `bin/audit_lock.py`.
      - **Vocabulary, confirmed from uv itself:** `uv audit` (the wrapper's argv) driven under
        `bin/sandbox.sh` with every proxy at a refused loopback port and `UV_HTTP_RETRIES=0`, once
        per value, under uv 0.12.17 and 0.13.1 separately; 101 values (unset, every case form of
        the twelve words, eighteen outside values). Both releases agree exactly: every case form of
        `1 t true y yes on` → offline (uv's offline refusal), of `0 f false n no off` → online (a
        connect error), and every outside value (empty, padded `' 0'`/`'0 '`/`'\t0'`/`'off\n'`,
        `garbage`, `2`, `00`, `tru`, `falſe`, fullwidth `ＴＲＵＥ`, …) → refused before any request
        ("Failed to parse environment variable `UV_OFFLINE` … expected a boolish value").
      - **Tests** (`bin/audit_lock.py` unchanged, no seam needed): the vocabulary is spelled out in
        `tests/test_audit.py`; `test_offline_setting_reaches_uv_as_a_flag` (name kept) covers every
        case form and fourteen refused values; new integration row
        `test_wrapper_reads_uv_offline_as_uv_does` hands each value to the running uv on the
        wrapper's argv and environment and requires a request exactly for the false words and
        exactly where the wrapper reads online. The sweep's pins: verdicts compared whole with
        literal exit statuses 1/2/3; argv and `UV_ALLOWED` pinned exactly (`UV=''` included); the
        fake `subprocess.run` also requires `capture_output`/`text`; new verdict rows (two findings,
        12 vulnerabilities, unparsed exit-1 report, mid-line phrase, each unreachable marker, a
        non-2 unreachable exit, a killed uv, a long count, empty and other locks, summary
        mid-line or with trailing text, prefix/suffix lines around a clean summary).
      - **Gate tightened** (both blocks): the new id joins P1's named ids; P2/P3 byte-identical.
      - **Sweep:** 131 mutants, each in a scratch copy under 0.12.17 alone and 0.13.1 alone, with
        the same verdict per mutant under both: 86 killed before, 37 newly killed, 8 equivalent
        (no observable change): `root-no-resolve` (`__file__` is already absolute and the unresolved
        path names the same directory to uv), `env-prefix-upper` (uv reads only upper-case
        `UV_*` names), `false-add-False` (`lower()` never yields it), `offl-default-0` (unset and
        `'0'` are both online), `main-cmd-os`/`main-env-os`/`main-offline-osenv` (`environ` is an
        unmodified snapshot of `os.environ`), `main-success-cond` (`status == 0` exactly when
        `reasons` is empty).
      Test docstring and `AGENTS.md` § Testing entry updated in the same commit.
- [x] **Amendment (review cycle 3, F1, Geoffrey's ruling at the review bound).** Reopened for
      remediation: `main()` decides offline exactly once and both uses consume that one value.
      - **Structure:** `offline = offline_requested(environ)` in `main()`; `command(launcher,
        offline)` takes the launching uv (`environ.get('UV')`) and the decision, never the
        environment, and `audit_violations(..., offline=offline)` takes the same value. No second
        computation exists. Module docstring, `command`/`main` docstrings and the `AGENTS.md`
        § Testing entry say so.
      - **Pins:** `test_main_runs_the_command_and_env_it_derives` (name kept, so the stored gate is
        byte-identical) gains a clean planted run under every case form of uv's vocabulary and
        every refused value (96 rows). The expected `--offline` comes from the vocabulary table,
        never from the wrapper, and each row asserts the argv's `--offline` presence equals the
        verdict's "ran offline" before comparing the whole output. Unit callers of `command` move
        to the new signature; the integration row passes `False`.
      - **Mutants** (a scratch copy each, `tests/test_audit.py` whole, under 0.12.17 alone and
        0.13.1 alone; same count under both): cycle 3's three as written replaced
        `offline_requested(environ)` in the verdict call, a site that no longer exists, and
        `command()` can no longer re-read the environment; so each was re-expressed at the three
        sites that remain, the decision, the verdict's argument and the argv's argument: all nine
        red (38/49/50 failed per expression). Nearest expressible: decision inverted (107 failed),
        verdict or argv discarding (51) or forcing (56) the decision, `command` inverting the flag
        (206). Baseline 234 passed under each.
- **Verify:** `tests/test_audit.py` by named ids, handshake era, then the whole file in the modern
  era, under uv 0.12.17 and then uv 0.13.1 (frontmatter).
- **Touches:** `bin/audit_lock.py`, `tests/test_audit.py`, `AGENTS.md` (§ Testing entry).

## Phase P2 — Declare the uv floor where uv enforces it
**Satisfies:** R6 · **Depends on:** —
**Goal:** every uv from 0.5.14 (the first to read `required-version`) up to 0.12.16 refuses to sync or
run the project, naming 0.12.17; 0.12.17 accepts it and the lock is unchanged.

- [x] `pyproject.toml`: a `[tool.uv]` table with `required-version = ">=0.12.17"` and a one-line
      declarative comment. No upper bound.
- [x] Confirm `uv.lock` is unchanged (`git diff --exit-code uv.lock`).
- [x] `AGENTS.md` § Commands: one line beside "Supported Python is 3.14+" saying the supported uv is
      0.12.17 and later, enforced by `[tool.uv] required-version` (point to it; don't restate the
      range elsewhere).
- [x] **Amendment (review cycle 3, F2, GOAL clarification `81c303d`).** Reopened for remediation: R6
      reaches every uv that reads `required-version`, 0.5.14 and later. The `pyproject.toml` comment
      and `AGENTS.md` § Commands now say exactly that: 0.5.14 up to 0.12.16 refuse and name 0.12.17;
      0.5.13 and earlier predate the field, warn and run; no uv-native mechanism reaches them. No
      code change is possible for those. Swept outside `spec/`: no other text claimed every older uv
      refuses (`bin/audit_lock.py`, `tests/test_audit.py` and `AGENTS.md`'s other "refuses" are
      about `UV_OFFLINE` values). **Gate tightened** (`--verify-file`, byte-identical on read-back):
      the false claim's phrases are absent outside `spec/`, both texts name "0.5.13 and earlier",
      uv 0.5.14 refuses `sync --locked` and `run` naming 0.12.17, uv 0.5.13 runs with the
      unknown-field warning; then the previous 0.12.16 and 0.12.17 blocks unchanged. Seen red on a
      re-planted claim in each text.
- **Verify:** the claim is absent outside `spec/` and both texts state the reach; uv 0.5.14 and
  0.12.16 fail `uv sync --locked` and `uv run true`, each naming 0.12.17; uv 0.5.13 runs, warning of
  the unknown field; uv 0.12.17 passes `uv lock --check` and `uv sync --locked` (frontmatter).
- **Touches:** `pyproject.toml`, `AGENTS.md` (§ Commands).

## Phase P3 — The full verify, both eras, at both ends of the supported range
**Satisfies:** R4, R5 · **Depends on:** P1, P2
**Goal:** the profile's `verify`, verbatim, is green under uv 0.12.17 and under uv 0.13.1 (the current
release on 2026-10-17), with the floor in place.

- [x] Run the gate. If PyPI's latest uv is newer than 0.13.1 when this phase runs, run the same
      block under it too and record the release in the commit body; a red there is a finding for
      this cycle, not a waiver.
- [x] Re-read `AGENTS.md` § Testing, § Commands and the release recipe's `audit` caveat against the
      built code; fix any drift in this commit.
- [x] **Deferral ledger.** Walk P1–P3 for "do not fix here", "known limitation", "follow-up" or any
      deferral; each needs an `issues/{slug}.md` (from the KB `ISSUE.md` template, `status: unshaped`)
      and a `ROADMAP.md` entry, or `.security/` if sensitive. None is planned; an unrecorded one fails
      this phase.
- **Verify:** the profile's full `verify` under uv 0.12.17, then under uv 0.13.1 (frontmatter).
- **Touches:** none planned beyond doc drift fixes.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[fix]` commit; stop and report.
