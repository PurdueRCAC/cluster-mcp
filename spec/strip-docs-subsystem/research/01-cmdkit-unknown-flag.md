# 01 — What `rcac-mcp --index-docs` does once the flag is gone

Scope: R3. How cmdkit 2.7.7 (the locked version) reports an unrecognized flag, which exit status it
returns, and what else exits with the same status. Driven under `bin/sandbox.sh` on 2026-10-16 with
stand-in flags (`--no-such-flag`, `--no-such x`), since the real flags still exist on the base.

## The mechanism

- `cmdkit.cli.Interface` subclasses `argparse.ArgumentParser` and overrides `error()` and `exit()` to
  raise `cmdkit.cli.ArgumentError` instead of printing usage and calling `sys.exit`
  (`.venv/.../cmdkit/cli.py:95–100`). `print_usage` is a no-op.
- `Application.main()` catches `ArgumentError`, calls `cls.log_critical(error)` and returns
  `exit_status.bad_argument` (`cmdkit/app.py:125–127`). `exit_status.bad_argument == 2`
  (`app.py:35`). This happens inside `parse_args`, before `MCPServerApp.__init__` or `run()`, so no
  server, executor or indexer code runs.
- argparse's message for leftovers is `unrecognized arguments: <every leftover token>`. A value flag
  carries its value along: `--no-such x` → `unrecognized arguments: --no-such x`; `--opt=value`
  stays one token.

## Observed (sandbox)

| argv | stdout | stderr | exit |
|---|---|---|---|
| `--no-such-flag` | empty | `CRITICAL [rcac_mcp] unrecognized arguments: --no-such-flag` | 2 |
| `--no-such x -e local` | empty (0 bytes) | `CRITICAL [rcac_mcp] unrecognized arguments: --no-such x` | 2 |
| *(bare, no flags)* | — | `INFO … Execution mode: ssh` then `CRITICAL … SSH host required: use --ssh-host or set RCAC_SSH_HOST` | **2** |
| `-e local --docs-path x` (base: flag still known) | MCP banner | `Execution mode: local`, `Starting MCP server 'RCAC' with transport 'stdio'`; exits 0 on stdin EOF | 0 |
| `--index` (base) | — | `--docs-path is required when using --index-docs` | 2 |

The log line goes to **stderr**; stdout stays empty.

## Consequences for the design

1. **R3's exit status is met by construction.** Deleting the three `interface.add_argument` calls
   is enough: cmdkit yields `exit_status.bad_argument` with a message naming the flag. No custom
   handling is needed or wanted (a bespoke "this flag was removed" message would be a new CLI
   surface, outside the GOAL).
2. **Exit 2 alone is a hollow assertion.** `ValueError` also maps to `exit_status.bad_argument`
   (`MCPServerApp.exceptions`), so a regression that *accepted and ignored* the flag would, under
   the sandbox's unset `RCAC_SSH_HOST`, still exit 2 with `SSH host required`. A check must assert
   the message (`unrecognized arguments:` followed by the flag) and the absence of
   `Execution mode` (logged first thing in `run()`), not just the status.
3. **`-e local` makes a silent-accept regression loud.** With `-e local` and stdin from
   `/dev/null`, an accepted flag starts the stdio server and exits 0, which fails any status
   assertion outright. Keep at least one drive with `-e local`.
4. **Abbreviation is not a trap.** argparse `allow_abbrev` maps a *prefix* of a known long option
   onto it (`--index` → `--index-docs` today). After removal no remaining long option begins with
   `--index` or `--docs`, so none of the removed spellings or their prefixes resolve to a surviving
   flag. (`--d`/`--do` etc. are unrecognized too.)
5. **"Without writing a database file"**: the only writer is `_run_index_docs()` → `DocsIndexer`,
   both deleted. Observable proof: pass `--docs-output <tmp>/docs.db` and assert the file is absent,
   and list `*.db` under the sandbox `HOME` (the old default was `~/.config/rcac-mcp/docs.db`) before
   the sandbox is torn down.
6. **Under the sandbox, stdout is the CLI's alone** (`bin/sandbox.sh` writes nothing to stdout), so
   "stdout is empty" is a valid assertion that no server banner or MCP traffic appeared.
