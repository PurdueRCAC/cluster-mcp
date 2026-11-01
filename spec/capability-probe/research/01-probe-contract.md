# Research 01 — the probe contract and how a probe executes

Paths are under `packages/cluster-mcp/src/cluster_mcp/core/` unless stated.

## 1. What a probe can declare

| | Capability code at probe time | Can raise / exit / hang / be malformed | Thread bound contains it? |
|---|---|---|---|
| (a) data: command names | none: the core runs one fixed script for all capabilities | Python side: no (validated at load). Remote side: hang (timeout), bad output (strict parse) | yes |
| (b) a script string each | none in Python. Arbitrary remote text | remote: hang, forged or garbled output, `exit` taking other probes down if scripts are joined, side effects (writes) at startup in the user's account | yes, but the core can't check the script is read-only. A `str` command is "only `run_command`" (`executor/base.py:83`) and isn't a registered fixed script (`scripts.py:30-37`) |
| (c) a callable over the executor | arbitrary Python | any `Exception`; `SystemExit` silently ends a thread (`read_bounded` catches only `Exception`, `site.py:589-592`), so it costs the whole bound; a Python spin holds the GIL against the server; returns a non-bool (or a `__bool__` that raises); can call `write`; N round trips | only for wall-clock time: an abandoned thread keeps running |

Only (a) keeps the rule that whatever a capability declares fails at load or not at all (`capabilities.py:17-18`, AGENTS §7). (b) and (c) move capability failures to probe time, where they can only fail open.

**Seeds.** The Slurm, RCAC and site-extra members run argv commands (`exec 'name' …`, `executor/launch.py:299`), so a name lookup covers them exactly. **xdu should declare no probe.** Its tools are meant to be served when `xdu` is missing, to offer the install (`issues/xdu-storage.md:43-44`, R2 `:74`), so withholding them defeats that. **LMOD is not covered.** `module` is a function, and its tools would run `$LMOD_CMD` (`issues/lmod-tool-group.md:51-54`), which needs a variable or function lookup, not `PATH`. Name the field for what it checks (commands), so the LMOD cycle can add a second data field (such as variables that must name an executable) to the same fixed script. That is a core edit in that cycle and should be recorded as such.

## 2. How a fixed probe script runs

- `executor.run(script_argv(SCRIPT, name, *names))` gives `exec /bin/bash --norc --posix -c FIXED_RESET+SCRIPT name …` (`launch.py:416-422`, `scripts.py:40-42`). Like every argv, it runs inside the subshell of the pinned login bash `/bin/bash -l`, after `/etc/profile.d` (`launch.py:80-81`, `:189`, `:197-199`; the program at `:277-312`). So the PATH is exactly what a tool's `exec` sees, and POSIX mode is on.
- **Function visibility.** The POSIX bash sees a login-shell function only if the profile *exported* it. The `run_command` path re-exports every function (`SCRIPT`, `launch.py:152-154`), but fixed scripts don't.
- **Lookups**, verified locally with `/bin/bash` 3.2 in `--posix` mode, with an exported function and an alias set up first:
  - `command -v` finds a function, a builtin and a `PATH` file.
  - `type -t` gives `function`, `builtin` or `file`.
  - `type -P` finds only `PATH` files.
  - An alias is invisible to all three: aliases aren't inherited, and the program runs `\unalias -a` (`launch.py:139`).

  `type -P` matches `exec` exactly. `command -v` would report a profile function named `squeue` as present, while `exec squeue` would fail. Bash 4 and 5 aren't available on this host, so a plan test should re-check this there.
- **Shadowing.** `FIXED_RESET` doesn't unset `type` or `command` (`launch.py:205`), so the script must start `unset -f type`, as `READ_SITE` does for its own words (`site.py:107-108`). Verified: an exported `type` function is undone.
- **Passing names.** Pass names only as positional parameters (`scripts.py:8-10`). At load, refuse anything that doesn't match `^[A-Za-z0-9_][A-Za-z0-9_.+-]{0,254}\Z`. That rules out empty names, `/`, whitespace, NUL, a leading `-` or `.`, and non-ASCII.
- **Candidate script** (verified locally):
  ```
  unset -f type
  for n do if type -P -- "$n" >/dev/null 2>&1; then printf '1\n'; else printf '0\n'; fi; done
  printf 'end %s\n' "$#"
  ```
  The answer is one `0`/`1` line per name, in the order sent, then `end N`. No name is echoed, so no name can forge a line. Login chatter is already cut by the sentinels (`launch.py:23-31`, `separate` at `:345-396`).
- **Malformed** means anything other than exactly N lines of `0`/`1` followed by `end N`, where N is the count sent. That includes extra lines, such as a background job started by a remote rc file (`executor/base.py:60-63`).

## 3. Every outcome of `executor.run`

| Outcome | Meaning |
|---|---|
| exit 0, well-formed: all `1` / any `0` | definite present / **definite absent** (one `0` withholds the capability) |
| exit 0, malformed | no definite answer: fail open (R6) |
| exit 1..255, or −N (signal) | no answer (the script only ever exits 0) |
| `TIMEOUT_EXIT_CODE` −1001, `NOT_STARTED_EXIT_CODE` −1002, `CONNECTION_LOST_EXIT_CODE` −1003 (`executor/base.py:20-30`) | no answer |
| `TypeError`/`ValueError` before start (`base.py:121-125`) | can't happen with names validated at load. Treat as no answer |
| local: `OSError` from `Popen` (`launch.py:587`) | no answer |
| ssh: `SSHException`/`EOFError`/`OSError` from `open_session` or a refused `exec_command` on a live link (`ssh.py:981-991`) | no answer |
| `KeyboardInterrupt` | propagate |

**Hangs the executor timeout does not bound:**
- ssh: the reconnect window is `RECONNECT_FACTOR`×connect bound, 45 s (`ssh.py:61`, `:104`, `:954`), and `open_session` waits up to 30 s (`ssh.py:92`, `:980`). The `timeout` bounds the command only once it's sent (`ssh.py:945-946`).
- local: a timeout drains for up to 2×`GRACE` plus a `GRACE` wait (`launch.py:599-618`).

So run the probe on a daemon thread with a wall-clock deadline, as `read_bounded` does (`site.py:581-598`). Pass an executor timeout below the deadline, and treat an empty box as no answer. Catch `Exception` in the thread. A thread that dies of anything else leaves the box empty and is read as a timeout. The probe runs before `mcp.run` (`__init__.py:215-218`), so it behaves the same on stdio, stdio with stdin closed, and HTTP. A local launch never inherits the server's stdin (`launch.py:575`, `:587`), and ssh sends EOF at once (`ssh.py:982`).

## 4. The declaration on `Capability`

- Add `commands: tuple[str, ...] = ()` after `resources` (`capabilities.py:65-69`). Positional and keyword construction with 4 or 5 arguments keeps working (both members use keywords, `rcac/capability.py:23`, `slurm/capability.py:19`), and `()` means no probe (Q1).
- In `_checked` (`capabilities.py:164-179`), add `('commands', tuple)` to the type loop at `:168`. A `str` must be refused: it is iterable, so `'sinfo'` would become five one-letter names. Then check each element: it must be a `str`, match the regex, and appear only once (as `resource … declared twice`, `:299-300`). Optionally cap the count, say at 64.
- Every failure raises `_Invalid`, which becomes `CapabilityLoadError` (`:273-274`), so a malformed declaration is the existing §7 refusal.
- R5: if the union of all declared names is empty, `executor.run` is never called.

## 5. What each member should declare

- **Slurm** (`slurm/tools.py`) runs `sbatch` (`:180`), `squeue` (`:254`), `scancel` (`:314`), `sacct` (`:374`), `whoami` (`:378`), `sinfo` (`:432`) and `scontrol` (`:464`, `:492`), plus `executor.write` for a job script. Slurm's client commands ship together, so declare all six Slurm commands. `whoami` is coreutils: leave it out.
- **RCAC** (`rcac/tools.py`) runs `myquota` (`:54`, `:362`), `jobinfo` `jobcmd` `jobenv` `jobscript` (`:81`, `:108`, `:135`, `:162`), `showpartitions` (`:186`), `average_wait` (`:221`), `findscratch` (`:356`), `slist` (`:407`) and `sfeatures` (`:431`). The storage resource needs `findscratch` and `myquota` (`rcac/resources.py:26-28`, `tools.py:340-366`).
- **Trade-off.** Declaring every command means one missing site script, `average_wait` say, hides all ten tools and the resource. That is a worse failure than over-advertising one tool, whose call-time error the GOAL leaves to each tool (non-goal). A minimal marker set `('findscratch', 'myquota')` asks "is this the site?" and covers the resource exactly.

## Recommendation

Use (a): a data-only `commands` tuple, validated in `_checked`.
- **One round trip** for the union of names: the registered fixed script above, run once through the shared executor on a daemon thread with one wall-clock deadline of at most `READ_TIMEOUT`.
- **Strict parse**; per capability, absent iff any of its names answered `0`.
- **Members:** Slurm declares its six commands; RCAC declares `findscratch` and `myquota`. xdu declares none.

**Failure modes this removes:**
- capability Python running at probe time, and every raise, exit or hang in it;
- names injected into script text;
- per-capability round trips;
- false "present" from functions, builtins or aliases;
- forged answers from echoed names;
- probe failures that only show up at startup, after a clean load.

**What remains:**
- An unexported function or an extra profile step can make a command look absent wrongly. The Q4 override is the remedy.
- A slow link makes fail-open common (Q2).
- One bad answer fails every probing capability open together.
- A thread abandoned at the deadline may still finish later against the shared executor (read-only).
- LMOD needs a second data kind in its own cycle.
- Bash 4 and 5 behaviour in POSIX mode should be re-checked in a test, since only 3.2 was available here.
