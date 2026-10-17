# 05 — The dependency audit: tool, failure modes, proof

Public-lane note: this brief names no advisory and makes no claim about any locked version.
Which advisories the probes below reported, against which versions, is recorded in the build log
the foreman keeps, not here.

## Candidates

- **`uv audit`** — native in the installed uv 0.13.1 and in 0.12.17 (the version the in-flight CI
  workflow pins; checked with `uvx uv@0.12.17 audit --help`). Reads `uv.lock` directly
  (`--frozen`: no re-lock), queries OSV, prints per package `<name> <version> has N known
  vulnerabilities:` followed by each advisory id, summary and fixed versions. Experimental: it
  warns unless `--preview-features audit-command` is passed.
- `pip-audit` via `uvx`, over `uv export --frozen --format requirements-txt`: an extra tool
  download per run, a second resolver reading an export instead of the lock, and its own
  network-failure semantics.

**Pick `uv audit`.** It audits exactly the tree `uv.lock` resolves, with the uv the gate already
requires, and needs no export step.

## Exit statuses (probed)

| Situation | Exit | Output |
|---|---|---|
| clean lock | 0 | `Found no known vulnerabilities and no adverse project statuses in 85 packages` |
| a locked version with a published advisory | 1 | package, version, advisory id and summary per finding |
| `--offline` or `UV_OFFLINE=1` | 2 | `Auditing requires network access and cannot be performed in offline mode` |
| advisory service refused (`--service-url http://127.0.0.1:9/`) | 2 | `Request failed after 3 retries … Connection refused` |
| service black-holed (`--service-url http://10.255.255.1/`) | 2 | `… deadline has elapsed` |
| dead proxy (`HTTPS_PROXY`/`ALL_PROXY` at port 9) | 2 | `… Connection refused` |

So `uv audit` already fails closed when the source is unreachable. What it does not guard
against: an audit that silently covers fewer packages than the lock pins (a config file adding
`--no-dev`-like options, `--ignore` entries, or a different service URL). `uv audit` takes
`--ignore`/`--ignore-until-fixed` and `--service-url`; a `uv.toml` could carry settings.

## The gate step: `bin/audit_lock.py`

A stdlib script (the CI workflow's `bin/sdist_hygiene.py` is the house pattern: one definition the
release gate and CI both run). It runs
`uv audit --frozen --no-config --preview-features audit-command` from the repository root and
decides with a pure function, `audit_violations(returncode, output, lock_text)`:

- exit 1 → red, the findings printed as uv printed them (package, version, advisory);
- exit 2 or any other non-zero → red, classified: "advisory source unreachable" when the output
  says so (offline, request failed, deadline), else "the audit could not run" (e.g. a uv without
  `audit`);
- exit 0 → green only if the summary line reports no vulnerabilities **and** its package count
  equals the number of registry packages in `uv.lock` (every `[[package]]` except the project's
  own editable/virtual entry: 86 entries, 85 audited, on the prototype lock); a missing or
  different summary is red (fail closed if uv changes its wording).

`--no-config` keeps a user or system `uv.toml` from injecting ignores or a service URL. The script
takes no arguments that could weaken it: no waiver path (a GOAL non-goal).

**Review finding (2026-10-17):** `uv audit` follows `UV_PROJECT`, which `bin/sandbox.sh` exports, so
the unpinned command audited whatever tree that named (a planted lock went green). The script now
passes `--project <its own checkout>` and runs uv with every `UV_*` removed except `UV_CACHE_DIR`,
`UV_OFFLINE`, `UV_NATIVE_TLS`, `UV_SYSTEM_CERTS`; probed: planted lock with `UV_PROJECT` elsewhere →
exit 1; shipped lock → 0; `UV_NO_DEV=1` → still 0 (dropped); offline with dead proxies → 2 with uv's
own offline message.

## Where it runs

The release recipe's `gate` (after `uv lock --check`), and CI's `gate` job as its own step if
`.github/workflows/ci.yml` exists on the base when this cycle lands (the ci-workflow cycle's "CI
mirrors the gate" rule: one step per gate command, verbatim, same order, same commit). Never the
profile's `verify`.

## Tests (offline, deterministic)

- unit: `audit_violations` fed planted outputs: a finding (must be red and name package/version),
  offline text with exit 2, an unknown exit-2 text, exit 0 with a short count, exit 0 with no
  summary, and the clean shape (must be green).
- integration: the real script under `bin/sandbox.sh` with `UV_OFFLINE=1` exits non-zero and says
  the advisory source is unreachable. No network, so it belongs in the suite.

## Proofs for R10 (networked, so a separate gate mode, run by build)

- green on the shipped lock;
- red on a planted lock: a scratch project outside the repo whose `uv.lock` pins a version with a
  published advisory (which one: the build log), exit 1 with package, version and advisory named;
- red with the network cut (`UV_OFFLINE=1`), exit non-zero, "unreachable".

The red output goes to the private build log only; no commit body, PR body or spec file carries
it.
