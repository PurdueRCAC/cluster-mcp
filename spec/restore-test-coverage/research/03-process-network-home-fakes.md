# 03 — Process, network and HOME fakes: the delegate argv (R6), SSH construction (R10), and the unit guard (R3, R11)

**Question.** How do tests record the `sudo` argv without running `sudo`, capture `$SHELL` at
construction, construct `SSHExecutor` without a connection, and *prove* that a unit test launched
nothing, reached no host and never touched the real `HOME`?

## Recording the delegate argv at the stdlib boundary

`executor/delegate.py` does `import subprocess` and calls `subprocess.run(sudo_cmd,
capture_output=True, text=True, timeout=timeout)`. Three places to intercept were evaluated:

| Intercept | Verdict |
|---|---|
| Replace `rcac_mcp.executor.delegate.subprocess` with a namespace | Narrow, but binds to the module's import style; a `from subprocess import run` in `safe-execution` would bypass it silently. |
| Patch `subprocess.run` | Misses any launch that is not `run` (`Popen`, `check_output`, asyncio subprocesses). |
| **Patch `subprocess.Popen`** | **Chosen.** Every stdlib launch path (`run`, `call`, `check_*`, `asyncio.create_subprocess_*` on Unix) builds a `Popen` from the module global, so one fake sees them all, whatever the caller's import style. |

`subprocess.run` (3.14) needs only `with Popen(...) as p`, `p.communicate(input, timeout=...)`,
`p.poll()`, plus `kill()`/`wait()` on its error paths; `CompletedProcess(p.args, retcode, stdout,
stderr)` is built from them. The fake records `list(args)` and the kwargs, returns `str` when
`text=True` (else bytes), and answers with a marker naming the `-u` user and the last argv element,
so a tool result can be traced to the exact launch (brief 02). Executed in
`prototypes/isolation_over_http.py`: recorded argvs were exactly `['sudo', '-n', '-H', '-u',
'ualice', '/bin/zsh', '-c', 'echo A']`.

**`$SHELL` capture.** `DelegatingExecutor.__init__` reads `os.environ.get('SHELL', '/bin/sh')` once
into `_shell`. The test sets `SHELL=/opt/test-shell-a` with `monkeypatch.setenv`, constructs the
executor, sets `SHELL=/opt/test-shell-b`, then runs; the argv must carry `test-shell-a`. A planted
per-call read (`shell-read-per-call` in `prototypes/mutation_cases.py`) turns it red.

**`cwd` quoting.** `run` does `os.path.expanduser(cwd)` and then `f'cd {shlex.quote(cwd)} &&
{command}'`. Cases use absolute paths only (`~` expansion is a non-goal and reads `HOME`):
`/data/my dir` (spaces) and `/data/x; rm -rf / $(id) 'q'` (metacharacters and a quote). Assert
the exact argv, and that `shlex.split(argv[-1])[:3] == ['cd', cwd, '&&']`, which is "a single word".
The command carries `$HOME`, `;` and `*` and must appear verbatim after `&& `, unquoted. The no-`cwd`
case asserts `argv[-1] == command`.

## Constructing `SSHExecutor` without a connection

`SSHExecutor.__init__` calls `self.open()`, which builds `fabric.Connection(host, **kw)` from the
module global `Connection` and calls `.open()`. The test replaces `rcac_mcp.executor.ssh.Connection`
with a fake class (`host`, `is_connected`, `open()`, `close()`, `run()`, `put()`, `get()`) and
records that it was constructed and opened. Same fake in the ladder tests (brief 04), where the
`ssh` rung must not connect either. This binding is internal to `rcac_mcp`, not FastMCP: it
survives `stack-upgrade` and is rewritten knowingly by `safe-execution`.

## The unit guard (conftest extension)

An autouse fixture in `tests/conftest.py` that acts only on items carrying `@mark.unit` (the marker
already says "no subprocess, no network, no real cluster"; the guard makes that executable). It never
adds or reads markers for any other purpose, so it cannot launder the marker check.

- **HOME:** `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME` → under `tmp_path`;
  `RCAC_SSH_HOST`, `RCAC_USER_MAP`, `JWT_SECRET`, `OIDC_*`, `MCP_BASE_URL` unset (the same blanking
  `bin/sandbox.sh` does). `~` expansion and Fabric's `~/.ssh/config` read then land in the temporary
  directory.
- **Processes:** `subprocess.Popen`, `os.system`, `os.posix_spawn`, `os.posix_spawnp`, `os.fork`
  replaced by refusers that record the attempt and raise `OSError`.
- **Network:** `socket.socket.connect`, `socket.socket.connect_ex`, `socket.create_connection`,
  `socket.getaddrinfo` refused the same way. In-process ASGI, anyio memory streams and the asyncio
  self-pipe (`socketpair`) use none of these: executed in `prototypes/unit_guard.py`, the full
  HTTP delegate flow ran with zero refusals, and `SSHExecutor('cluster.example.org')` was refused at
  `getaddrinfo`.
- **Teardown:** a test whose refusals list is non-empty fails, listing what it tried. Tests that
  expect a launch request a `launches` fixture that swaps the refusing `Popen` for the recorder.
  Contract tests also assert `guard.refused == []` *inside the body*. A raise inside a tool turns
  into a tool error, which an R2-style test expects, so only an in-body assertion makes the test
  itself fail (`FAILED`, not a teardown `ERROR`); the mutation harness counts only `FAILED` (brief 05).
- **Standing controls** (`tests/test_hygiene.py`): a unit test that tries `subprocess.run(['true'])`,
  `socket.create_connection(('example.org', 80))` and `os.path.expanduser('~')` sees the refusals and
  the temporary `HOME`, then clears the list it provoked.

## Integration tests

They run subprocesses on purpose, so the guard skips them. R11's "every CLI drive goes through
`bin/sandbox.sh`" is made static: `sandbox_violations(source, filename)` walks a test file's AST and
flags every `subprocess.*`/`os.system` call whose argv is not a list or tuple literal starting with
`SANDBOX` or `str(SANDBOX)`, and every bare imported `run`/`Popen`. It runs over every
`tests/*.py`, with negative controls on synthetic sources. Calls lexically inside a function
decorated `@pytest.mark.unit` are exempt, because the runtime guard already refuses them there; this
is what lets the guard's own self-test call `subprocess.run(['true'])`. Every other call, including
module-level helpers such as `test_cli.drive`, is checked.
