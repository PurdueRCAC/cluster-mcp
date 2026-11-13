---
status: unshaped
kind: refactor
appetite: small
lane: public
---

# Identity strings the rename left: JWT issuer and audience, serverInfo.version

## Problem

`rename-to-cluster-mcp` renamed what its GOAL named: the distribution, the commands, the module
path, the variables, the resource URIs, the server's name and its instructions. Three identity
strings it found are outside those requirements, and each is a judgement call rather than a rename.
This seed carries the first two, the ones a client or a token sees, into release 0.2.0; the third,
the favicon, waits for member routes and moves to `issues/site-extras.md`:

- **JWT `ISSUER` and `AUDIENCE`** are both `'rcac-mcp'` (`token.py`, mirrored in the verifier in
  `auth.py`; `SECURITY.md` documents them). Every token a `jwt` or delegate deployment has minted
  carries them, so renaming them invalidates every issued token at once. So they move under a
  window: the verifier accepts both names, the minter signs the new one, and no token already
  minted breaks.
- **`serverInfo.version`** is FastMCP's own version (4.1.4 when this was found), not this
  distribution's: FastMCP fills it when the server is built without a `version`. A client reading it
  sees the framework, not `cluster-mcp`. Setting it is a served-surface change (§9) the GOAL did not
  list among R8's deltas.
- **The Purdue favicon** (`static/purdue-favicon.ico`, its `/static/purdue-favicon.ico` route and
  `ICON_URL`) stays in the core member, though the core is meant to read as generic. Moving it to the
  RCAC member needs a way for a member to register routes and icons. `capability-extras` landed
  without one (its GOAL non-goals). *Moved 2026-11-09:* it is no longer this seed's; the `[rcac]`
  cycle (`issues/site-extras.md`) adds member routes in 0.3.0 and moves the favicon with them.

The dev hostname `mcp.rcac.dev` in `compose.yml`, `nginx-dev.conf` and the README's TLS section is a
local development name, not an identity the server reports; `issues/rename-in-docs.md` handles it
in the docs.

## Why it was deferred

Out of the GOAL's R-IDs (R2 covers the server name in server info and the `--help`/`--version`
output; R8 forbids surface deltas beyond the named three), and the JWT strings carry a compatibility
cost the rename cycle was not shaped to weigh. **Pre-existing**: all three are present in `develop`
before the rename.

## Outcome / vision

The server identifies as `cluster-mcp` everywhere a client or a token can see it, and no token a
deployment has minted stops working: the old issuer and audience are accepted through a window
announced the way the rename's own deprecations are, and `serverInfo.version` reports this server's
version.

## Sketch of the acceptance criteria

- **R1** — WHEN a client connects, the server SHALL report this distribution's version in
  `serverInfo.version`.
- **R2** — WHEN a token minted with the `rcac-mcp` issuer and audience is presented within a stated
  window, the server SHALL accept it; tokens it mints SHALL carry the `cluster-mcp` values.
- **R3** — The window SHALL be stated where the rename's own window is (the README and its
  deprecation warning), and `SECURITY.md` SHALL describe both names in the same commit.

## Notes

- Open for shaping: whether the claims' window is the rename's own (deprecated in 0.2.0, removed no
  earlier than 0.4.0) or one of its own, and whether accepting the old claims warns.
- Related: `issues/rename-in-docs.md` (the docs half of the rename), `issues/site-extras.md` (the
  favicon), `spec/capability-extras/`, `spec/rename-to-cluster-mcp/`
- Found by: `rename-to-cluster-mcp` plan (research briefs 03, 04, 05)
- 2026-10-30: the request-state keys `rcac_user` and `rcac_local_user` (set in `middleware.py` for
  a delegate call or read) still carry the old name too. They are never served, so nothing outside
  the process sees them; rename them with the strings above (`rename-to-cluster-mcp` review 1).
- 2026-11-12: the served-surface snapshot test (`tests/test_surface.py`) records
  `serverInfo.version` as the installed distribution it comes from, among `VERSION_SOURCES`
  (`cluster-mcp`, `fastmcp-slim`). Setting it here switches the source to `cluster-mcp`: a one-field
  fixture diff, re-taken with the update mode. A mutant that drops `cluster-mcp` from the candidates
  (`ver-sources-drop-core`) survives today and fails loudly, naming the candidates, only once the
  server serves its own version; this cycle's sweep should show it killed
  (`surface-fixture-after-a-surface-change`, the re-shape's review 1).
