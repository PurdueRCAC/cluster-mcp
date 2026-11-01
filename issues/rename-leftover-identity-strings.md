---
status: unshaped
kind: refactor
appetite: small
lane: public
---

# Identity strings the rename left: JWT issuer and audience, serverInfo.version, the Purdue favicon

## Problem

`rename-to-cluster-mcp` renamed what its GOAL named: the distribution, the commands, the module
path, the variables, the resource URIs, the server's name and its instructions. Three identity
strings it found are outside those requirements, and each is a judgement call rather than a rename:

- **JWT `ISSUER` and `AUDIENCE`** are both `'rcac-mcp'` (`token.py`, mirrored in the verifier in
  `auth.py`; `SECURITY.md` documents them). Every token a `jwt` or delegate deployment has minted
  carries them, so renaming them invalidates every issued token at once. A rename needs a window of
  its own (accept both, sign the new) or a stated hard break with an upgrade note.
- **`serverInfo.version`** is FastMCP's own version (4.1.4 when this was found), not this
  distribution's: FastMCP fills it when the server is built without a `version`. A client reading it
  sees the framework, not `cluster-mcp`. Setting it is a served-surface change (§9) the GOAL did not
  list among R8's deltas.
- **The Purdue favicon** (`static/purdue-favicon.ico`, its `/static/purdue-favicon.ico` route and
  `ICON_URL`) stays in the core member, though the core is meant to read as generic. Moving it to the
  RCAC member needs a way for a member to register routes and icons. `capability-extras` landed
  without one (its GOAL non-goals), so `site-extras` (`issues/site-extras.md`) or this seed adds it.

The dev hostname `mcp.rcac.dev` in `compose.yml`, `nginx-dev.conf` and the README's TLS section is a
local development name, not an identity the server reports; it changes with the favicon, if at all.

## Why it was deferred

Out of the GOAL's R-IDs (R2 covers the server name in server info and the `--help`/`--version`
output; R8 forbids surface deltas beyond the named three), and the JWT strings carry a compatibility
cost the rename cycle was not shaped to weigh. **Pre-existing**: all three are present in `develop`
before the rename.

## Outcome / vision

The server identifies as `cluster-mcp` everywhere a client or a token can see it, with any break
announced and windowed the way the rename's own deprecations are.

## Sketch of the acceptance criteria

- **R1** — WHEN a client connects, the server SHALL report this distribution's version in
  `serverInfo.version`.
- **R2** — WHEN a token minted with the `rcac-mcp` issuer and audience is presented within a stated
  window, the server SHALL accept it; tokens it mints SHALL carry the new values.
- **R3** — The core member SHALL serve no Purdue-branded asset; a site member SHALL supply its own.

## Notes

- Related: `issues/site-extras.md`, `spec/capability-extras/`, `spec/rename-to-cluster-mcp/`
- Found by: `rename-to-cluster-mcp` plan (research briefs 03, 04, 05)
- 2026-10-30: the request-state keys `rcac_user` and `rcac_local_user` (set in `middleware.py` for
  a delegate call or read) still carry the old name too. They are never served, so nothing outside
  the process sees them; rename them with the strings above (`rename-to-cluster-mcp` review 1).
