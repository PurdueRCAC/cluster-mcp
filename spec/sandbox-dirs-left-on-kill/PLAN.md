# PLAN — A sandbox killed with SIGKILL leaves no directory behind

> **Status:** Draft for review · **Last updated:** 2026-11-09
> **Authoritative technical design.** The *how*. Vision/contract is [`GOAL.md`](GOAL.md);
> the phased executable roadmap is [`TECH.md`](TECH.md). Backing detail is in
> [`research/`](research/) ([`00-digest.md`](research/00-digest.md) first). Every design element
> traces to a GOAL R-ID.

## 1. Summary

`bin/sandbox.sh` gains a **keeper**: a small perl process, detached from the wrapper (a double fork,
a process group of its own, parent pid 1, stdio on `/dev/null`), that makes the sandbox directory,
waits on a pipe whose write end only the wrapper holds, and on that pipe's end of file waits for the
command to end, then removes the directory as its last act. SIGKILL of the wrapper, alone or with its
group, is an end of file like any other, so the directory goes within a bound after the wrapper and
its command have both ended (R1, R2); every exit path the trap covered still removes it before the
wrapper exits (R3). Nothing else moves: the command keeps its stdin, group, environment, status and
signals (R7). Where no keeper can start (no perl, an odd `TMPDIR`) the wrapper runs exactly as on
develop (D5). The change is one file
of code, its contract paragraph in `AGENTS.md`, and one test module, which fits `appetite: small`;
research ran because `bin/sandbox.sh` is a high-blast-radius path.

## 2. Design

### The wrapper, in order (`bin/sandbox.sh`)

1. **`set -eu`, then the re-run under perl.** The script reads and unsets
   `CLUSTER_MCP_SANDBOX_KEEPER` before anything else. When it was empty, a perl is found
   (`command -v perl`, else `/usr/bin/perl`), and `template` (develop's
   `"${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX"`) is absolute and holds no newline, the script
   execs `perl -e '<the starter>' "$0" "$template" <7 saved> "$@"`. Otherwise it runs develop's path
   (D5). Perl's own variables would change how it starts (`PERL5OPT`, `PERL5LIB`, `PERLLIB`,
   `PERLIO`, `PERL_UNICODE`, `PERL_BADLANG`, and `LC_ALL` against a broken locale's warning): the
   script passes each one's state as an argument (`"${V+x$V}"`: empty when unset), exports a neutral
   value, and every perl puts the caller's back, unset or set, before it execs anything. The pid stays
   the caller's child and the group leader the caller made, with its stdio.
2. **The starter (perl, builtins only).** `$^F = 255`, so the pipes it opens survive `exec`. It opens
   two pipes, *up* (wrapper → keeper) and *down* (keeper → wrapper). If either fails, or any of the
   three descriptors the wrapper will hold (up's two ends, down's read end) is above 9 (dash
   redirects single digits only), it closes them and execs `/bin/sh "$0" "$@"` with the variable
   deleted: develop's path. Otherwise it forks a **middle** child and waits for it (a caller that
   ignores SIGCHLD makes the wait return early, which the starter accepts). The middle forks the
   **keeper** and exits at once. The starter closes down's write end, sets
   `CLUSTER_MCP_SANDBOX_KEEPER="<its pid> <up-r> <up-w> <down-r> <its perl>"` and execs
   `/bin/sh "$0" "$@"`.
3. **The keeper (the middle's child).** `setpgrp(0, 0)` first; HUP and PIPE ignored; stdin and stdout
   to `/dev/null`; it closes up's write end, down's read end and every other descriptor from 3 to
   255; its environment is cut to `PATH`. It then writes `ready` to down and reads up for `go`, which
   the wrapper writes once it has read `ready` (step 4); end of file instead ends it, with nothing
   made. By `go` the keeper has no parent link to the run: the starter waited for the middle's exit
   before it became the shell that answers, so the keeper is pid 1's (or a subreaper's) by then. A stop that freezes the wrapper before it looks (the sibling's) and found the keeper while
   it was still in the run froze the wrapper before `go`, so the keeper never makes a directory that
   stop could orphan by killing it late. Only then does it run `mktemp -d "$template"` (list form, its stderr still the
   wrapper's, so mktemp's own message reaches the caller as on develop), check that the result is one
   line naming a directory, write it to down, send stderr to `/dev/null`, `chdir "/"`, and re-exec
   perl as `cluster-mcp-sandbox-keeper -e <the waiter> <dir> <up-r> <down-w>`, with an environment of
   `PATH` alone: its command line shows its name, its code and its directory, and nothing of the
   caller's argv or environment. The waiter ignores HUP and PIPE and reads up line by line to end of
   file, keeping each line that is a pid and noting a `now` line. End of file comes when every holder
   of up's write end is gone: the wrapper (by any death) and, for the moment between its fork and its
   close, the shim (step 6). Unless it read `now`, it then waits until each pid is gone (`kill 0`
   fails other than with EPERM, or, on Linux, the state after the last `)` of `/proc/<pid>/stat` is
   `Z`), polling at 5 ms doubling to 0.1 s, and `exec rm -rf -- <dir>` with down's write end still
   open: down's end of file means the directory is removed.
4. **The second run.** `trap : HUP INT TERM` first. If `CLUSTER_MCP_SANDBOX_KEEPER` read
   `"$$ <d> <d> <d> <perl>"` with three digits 3–9, the script reads `ready` from down, writes `go`
   to up, and reads the directory from down, each with `IFS= read -r` (retried while a trapped signal interrupts it; any other failure exits 1, as a
   failed `mktemp` does on develop); otherwise it runs develop's `mktemp -d` itself. HOME, XDG,
   `UV_PROJECT`, `UV_CACHE_DIR`, the unsets, `CLUSTER_MCP_SANDBOX`, `CLUSTER_MCP_REPO` and the `cd`
   are develop's lines, unchanged.
5. **Traps.** The `EXIT` trap is inline (no function, so no command name can call it): with a
   keeper, if the command may still be running (`running` set: a signal no trap names, which
   bash-as-sh lets run this trap at once), it first writes `now` to up, so the keeper removes the
   directory at once, as develop's trap did; it closes up's two ends, reads down to end of file
   (retried while interrupted: the keeper has exited, its removal done), closes down, and runs
   develop's `rm -rf "$sandbox"`. `HUP INT TERM` trap `:`: as on develop they wait for the
   foreground command, and the script then ends through `EXIT`, so the directory is gone before the
   wrapper exits. Under dash an untrapped signal runs no trap; the wrapper dies and the keeper removes
   the directory once the command ends (develop left it).
6. **The command.** With a keeper:
   - when `command -v "$1"` gives a path (found on `PATH` or given by path), `"$@"` becomes
     `<perl> -e '<the shim>' "$0" "$found" <up-w> <up-r> <down-r> <7 saved> "$@"`, with perl's
     variables exported neutral as in step 1. The **shim** puts the caller's perl variables back,
     writes its pid to up, closes the three pipe ends, and `exec { $found } @ARGV`: it becomes the
     command, still the wrapper's child, in its group, with its stdin, descriptors and signal
     dispositions; the wrapper reaps it as on develop (its "Killed" line included). If that `exec`
     fails (a directory, a missing `#!` interpreter, any other reason), the shim execs
     `/bin/sh -c '"$@"' "$0" "$@"`, which fails as the wrapper's own `"$@"` would have, with the
     shell's message and status;
   - when `"$1"` is `exec`, it runs as on develop, in the wrapper, pipes and all: the program it
     becomes holds up until it and its children end, and the keeper removes the directory then
     (develop's trap never ran there, and left it);
   - any other builtin, a function or a missing command runs in a subshell that reports its pid
     (`/bin/sh -c 'printf "%s\n" "$PPID"' >&<up-w>`), closes the three pipe ends with a plain `exec`, and
     runs `"$@"`. Closing them with redirections on the builtin itself would not do: bash-as-sh
     keeps saved copies of redirected descriptors open in the programs a builtin starts (prototype:
     descriptors 10–12).

   The script then runs `status=0; running=yes`, the command, `|| status=$?; running=; exit
   "$status"`. Without a keeper it is develop's `"$@"`.

### The contract text

`AGENTS.md` § Factory → Throwaway environment, the sentence "the state directory is a `mktemp -d`
under `$TMPDIR`, removed by a trap" becomes: the state directory is a `mktemp -d` under `$TMPDIR`
made by a keeper the script starts under perl (by the script itself without perl), removed by the
script's exit trap before it exits, and, when the wrapper is killed outright, by the keeper once the
wrapper and its command have both ended; the keeper runs detached (a process group of its own, parent
pid 1, stdio on `/dev/null`), holds none of the caller's descriptors, and exits as it removes the
directory. It names the new test
module as the pin. The script's header gets the same paragraph in place of "removed on exit (any
path)". The numbered contract list is unchanged (item 2 already says "every exit path").

### The test module (`tests/test_sandbox_keeper.py`)

Linux evidence comes from CI at landing, which runs the suite on `ubuntu-24.04` (dash as `/bin/sh`):
the module's rows run there with no phase waiting on a hosted run. It follows § Testing: a pure
check, `keeper_violations(record) -> list[str]`, over a record of one stop (the directory's state
after the bound, the keepers found while the sandbox ran, the keepers alive after removal, whether
the command outlived the wrapper with its directory), with standing `unit` controls that plant each
broken record; and `integration` rows that drive the real wrapper with `TMPDIR` under `tmp_path`,
launch only through `SANDBOX` (the hygiene rail), and read `ps` through it too:

- `test_a_killed_sandbox_leaves_no_directory[group]`, `[wrapper-then-command]`, `[frozen-then-killed]`,
  `[pipes]`, `[background]` (R1, R6; the third also asserts that a walk by parent and group from the
  wrapper finds no keeper; the fourth that the caller's pipes end while the command, which closed its
  own, still runs; the fifth that a background job outliving both does not hold the directory);
- `test_an_ending_sandbox_removes_its_directory_first[exit]`, `[TERM]` (R3, R6);
- `test_a_sandbox_leaves_other_directories_alone` (R4, R5: a running neighbour and planted
  `cluster-mcp-sandbox.*` decoys, through a kill and an exit beside them);
- `test_keeper_violations_rejects[...]` (`unit`, one id per planted broken record).

`BOUND = 2.0` lives in the module and in the gate, as one figure (D1); a ruling changes both.

### Requirement → design map

| R-ID | Design element(s) that satisfy it |
|------|-----------------------------------|
| R1   | The keeper (§ 2.3): end of file on up when the wrapper dies by any signal, then a wait for the command's pid (the shim's, which becomes the command, § 2.6), then `rm`. Gate `kill`, `race`; rows `test_a_killed_sandbox_leaves_no_directory[*]`. |
| R2   | R1 for every start, and the keeper out of every caller's stop: no parent link and no group shared with a run, and none of a run's descriptors (§ 2.3). Gate `suite`, `mutants` (the runner within its limit and past a patched one), `verify` (the profile's whole `verify` under a fresh `TMPDIR`). |
| R3   | `EXIT` waits for the keeper's exit, then removes; `HUP INT TERM` defer as on develop and end through `EXIT`; a signal no trap names, where the shell runs `EXIT` at once (bash-as-sh), sends `now` so the directory goes before the wrapper exits, as develop's did (§ 2.5). Gate `exit` (and a builtin that ends the wrapper), `kill` (USR1 against develop); rows `test_an_ending_sandbox_removes_its_directory_first[*]`. |
| R4   | Each keeper removes only the path its own `mktemp` printed; sandboxes share no pipe, file or pid list. Gate `share`; row `test_a_sandbox_leaves_other_directories_alone`. |
| R5   | `rm -rf -- <its dir>` is the only removal the keeper makes, and the wrapper's is develop's; no glob, no sweep. Gate `decoys`; the same row. |
| R6   | The keeper's last act is `exec rm`; the wrapper's `EXIT` waits for down's end of file before its own removal; the middle child is gone before the wrapper runs; `mktemp` is reaped by the keeper. Every gate mode checks the keeper it found while the sandbox ran is gone once the directory is. |
| R7   | Develop's environment lines unchanged and the variable unset first; stdout of every new process is `/dev/null` or the pipe; the command keeps the wrapper's stdin, group and default signal dispositions, gets no new descriptor, and its status passes through `status`; no signal is forwarded (§ 2.5, § 2.6). Gate `same` compares develop's wrapper and the tree's on each listed observable, in bash-as-sh and dash. |

## 3. Invariant gate (AGENTS.md constitution check)

Checked against `AGENTS.md` § Invariants before research and again against this design.

- **§ Invariants, high-blast-radius paths** — `bin/sandbox.sh` is on the list: research ran
  (`research/`), and a CONFIRMED review finding in it needs the maintainer's sign-off before landing
  (GOAL Clarifications).
- **§ Factory, Throwaway environment** — all seven contract items hold; item 2 is what this cycle
  makes true for SIGKILL. The paragraph that says how ("removed by a trap") changes in the same
  commit as the script (§ 2, the contract text). Protection 1 (fail closed on SSH), 2 (HOME is the
  sandbox) and 3 (auth env blank) are develop's lines, unchanged, and still run before the command;
  the keeper re-executes with an environment of `PATH` alone and an argv of its own, so it holds
  and shows none of the auth environment (gate: a planted variable and the caller's argv token never
  appear on a keeper's command line).
- **§ Conventions, "A CLI drive … never touches the developer's real home"** — every drive still
  goes through the wrapper; the unset list is unchanged, so
  `tests/test_hygiene.py::test_sandbox_unsets_both_names` and its four anchors (each exactly once)
  hold; the perl text names none of them.
- **§ Conventions, "CI mirrors the gate"** — no list changes: the new module joins the fourth suite
  command (every other module) of each era with no edit to `verify`, the recipe or the workflow, and
  `tests/test_suite_parts.py` is untouched.
- **§ Conventions, comments and spec ids** — the script's comments and the module's text are
  declarative, with no R/P/Q/F ids (`test_no_spec_ids_in_the_package_or_the_suite`).
- **§ Conventions, markers** — every new test carries `unit` or `integration`; no gate is a marker
  selection (the gate names test ids).
- **§ Testing, pure checks with negative controls** — `keeper_violations` and its planted records.
- **§ Testing, the suite's rails** — every launch in the module is `[str(SANDBOX), …]`, `ps`
  included; `tests/test_registry.py`'s `SANDBOX_NEEDS` row runs the wrapper on a `PATH` of
  `dirname`, `mktemp`, `mkdir` and `rm` alone: the keeper starts from `/usr/bin/perl` and itself
  needs only `mktemp` and `rm` from `PATH`, so the row stays green unedited and its comment ("what
  bin/sandbox.sh needs on PATH to start") stays true.
- **Numbered sections §1–§9** — none touched: nothing under `packages/`.

### Deviation justifications

| Deviation | Why needed | Simpler alternative rejected because |
|-----------|-----------|--------------------------------------|
| **D1 — R1's bound and the keeper's poll (the maintainer's figures).** Proposed: the directory is gone within **2.0 s** of the moment the wrapper and its command have both ended; the keeper polls the command's pid at **5 ms doubling to 0.1 s**. Before (develop): never removed. After, measured on the final prototype (2026-11-09, macOS, gate `kill`, bash-as-sh and dash): 21–122 ms after the gate saw both had ended, in every scenario (group kill, wrapper alone then the command 1 s or 6 s later, freeze-walk-kill, caller's group, USR1, a background job outliving both); the gate's own 20 ms poll and a `ps` per check make each figure up to ~40 ms late or early. Brief 03 measured 3.5–21 ms from kill to removal with the backoff. Rederived from the rule: after both have ended the keeper needs at most one poll (≤ 0.1 s), one `rm -rf` of a skeleton (a few ms) and the reaping of an orphan by pid 1 (0.4–1.3 ms, 03 § 4): ~0.11 s worst case on an idle host, so 2.0 s leaves ~18× for a loaded CI runner. | R1 needs a figure (GOAL Q1); the poll is what the figure rests on. | A bound of 1 s or less: within the idle-host worst case's slack, but the CI runner's load is unmeasured, and the rows run there. A fixed 0.1 s poll: its tail is one interval (03 § 6). |
| **D2 — Cost per sandbox start (the maintainer's call).** Medians of 30 starts, three rounds, the planner's macOS host, 2026-11-09 (the final prototype; other worktrees' gates ran on the host meanwhile). `bin/sandbox.sh sh -c 'exit 0'` (a command through the shim, the common case): bash-as-sh **18.4 → 33.3 ms (+14.9)**, dash **15.2 → 27.8 ms (+12.6)**. `bin/sandbox.sh true` (a builtin, through the reporting subshell): bash-as-sh **14.7 → 31.0 ms (+16.3)**, dash **11.4 → 24.8 ms (+13.4)**. A full pytest run makes **3,356** starts (03 § 6, counted): about **+42–55 s** if every start were serial, ~5–6% of that run's 888 s. The profile's whole `verify` (the suite in both eras), measured: **1,542 → 1,610 s (+68 s, +4.4%)** (§ 5). The sibling's stop starts 3–4 sandboxes per timed-out case (`ps` tables, 02 § 2): about +45–65 ms a case. | Two perl starts (the starter, ~4 ms; the shim, ~4 ms), the second `/bin/sh` (~2–4 ms), the `ready`/`go` exchange and `command -v` (~1 ms) are the price of a detached keeper and of knowing when the command ends; the keeper's own re-exec and `mktemp` overlap the wrapper's start. | `perl -MPOSIX` (`setsid`, `dup2`): +6 ms more a start. A `/bin/sh` shim: cheaper by ~1–2 ms, but it changes failed commands' statuses (D3). A keeper started only when the caller asks: every caller would have to ask, which R2 and the GOAL ("every caller") rule out. |
| **D3 — Where the command runs, for the commands `exec` does not start (needs the maintainer's reading of R7 at the sign-off).** A command found as a file is the shim's `exec`: the wrapper's child, same pid as the shim, as on develop. Two kinds of command run one process further down: (a) one whose `exec` fails is retried by `/bin/sh -c '"$@"'` named as the wrapper, which prints the shell's own message and exits with its own status, as develop's `"$@"` does, but the message's line number reads 1 (develop's reads the script's line, which any edit to the script moves too); (b) a program a builtin starts (`command sh …`, `eval '…'`) runs in a subshell of the wrapper, so its parent is that subshell. R7 lists its observables after a colon (status, stdout, HOME/XDG/cwd, the environment, no forwarding), and these keep all of them; the parent pid and a line number are not on the list, and no test reads either (01 § 2). Gate `same` compares a missing command, a directory, a missing `#!` interpreter, a directory as interpreter, a shebang-less script, `exit`, `eval` and `command`, in both shells. If "every other observable" is read to include the parent pid of a builtin's program, (b) is a deviation. | The keeper must know the command's pid to wait for it after the wrapper has gone, and only a process the wrapper starts on purpose can report it. | A `/bin/sh` shim that `exec`s (03's sketch): a failed `exec` ends that shell with another status (bash-as-sh, a missing interpreter: 126 → 1); pre-checking the `#!` line in sh cost dash ~6 ms a start. A shim that runs the command without `exec`: it holds the caller's stdout, stderr and passed descriptors for the command's life (gate `kill`, pipes, red on that form). Builtins in the wrapper with the pipes closed by redirection: bash-as-sh leaks its saved copies to the builtin's programs (prototype). No shim: after a lone SIGKILL of the wrapper the keeper cannot tell a live command from a dead one. |
| **D4 — R6, read as one act (needs the maintainer's reading at the sign-off).** The keeper's last act is `exec rm -rf -- <dir>`: the process that removes the directory is the keeper's pid, and it exits as `rm` returns, so for the microseconds between the last unlink and that exit the "upkeep process" still exists. On every path that runs the wrapper's `EXIT` trap the keeper has exited before the wrapper's own `rm` (gate `exit` looks at the instant the wrapper is reaped). A command that removes its own `HOME` is not an exit path of `bin/sandbox.sh`; the keeper then waits for that command as usual. | R6 cannot be met more strictly: any remover is a process that exits after its last unlink. | A keeper that removes in-process and then exits: the same instant, one step later. |
| **D5 — Where no keeper starts, R1 does not hold (needs the maintainer's ruling at the sign-off: R1 says "by any caller").** The keeper needs a perl (on `PATH` or `/usr/bin/perl`), an absolute `TMPDIR` without a newline, and three free descriptors among 3–9 in the caller's process; without one, the wrapper is develop's, trap only, and a SIGKILL leaves the directory as today. macOS ships perl and `perl-base` is Essential on Ubuntu; in the suite only `tests/test_registry.py`'s `SANDBOX_NEEDS` row runs with a reduced `PATH`, and `/usr/bin/perl` still serves it; it kills nothing. A relative `TMPDIR` is broken on develop already (HOME is relative to the directory the script then leaves), and a newline in one made the prototype remove a directory it did not make, which R5 forbids. | No POSIX shell primitive detaches a process portably (03 § 1), and dash redirects only single-digit descriptors. | Fail closed without a keeper: a behaviour change for every such caller, against R7. `setsid(1)`: absent on macOS. `set -m`: no new group under dash. `python3`: a Command Line Tools stub on a bare Mac, 32 ms. |
| **D6 — The suite gains a module** (`tests/test_sandbox_keeper.py`, `integration` rows plus `unit` controls), about 5–8 s per era on a development host (projected; P1 measures it), in each era's fourth command. | The GOAL needs the fix on Linux, and no phase may wait on a hosted run: rows in the suite are what the landing CI run, on `ubuntu-24.04` with dash, checks. | The frozen gate alone: macOS evidence only, and nothing guards the keeper after landing. |

## 4. Rabbit holes (resolved)

- **How to detach on macOS and under dash** → perl builtins: a double fork and `setpgrp(0, 0)`;
  `setsid(1)`, `set -m`, `python3` and `POSIX` rejected with measurements
  ([`03`](research/03-detach-primitives.md) § 1–2).
- **What the sibling's stop reaches** → parent and group links from the wrapper, never sessions; a
  keeper re-parented and in its own group is not found; its integration row asserts nothing on
  sandbox homes ([`02`](research/02-sibling-stops.md)).
- **Every caller's contract** → six caller groups, the EOF waiters, `group_alive` rows, stdin and
  group membership as load-bearing, `test_cli`'s byte-identical stderr, `SANDBOX_NEEDS`
  ([`01`](research/01-callers-and-contract.md)).
- **The start-up window** → the keeper makes the directory after it has left the wrapper's group and
  parent, and only after a `ready`/`go` exchange with the running wrapper, so neither a group kill
  nor a freeze-walk-kill at any moment leaks one (gate `race`: 64 kills at 0–80 ms and 24
  freeze-walk-kills at 0–20 ms, none left, both shells, 12 repetitions; develop leaves 12 of 24).
  Without the exchange, a freeze-walk-kill that saw the keeper inside the run and killed it by pid
  after it had left left one directory in about 400 kills; without ignoring SIGPIPE before it
  reports, a keeper whose wrapper had died at once left 26 in 150 (prototype).
- **FIFOs vs pipes** → the re-run under perl opens anonymous pipes before the shell runs: nothing in
  HOME, no blocking open ([`00`](research/00-digest.md) 4).
- **The shim's shape** → a few lines of perl that report the pid, close the pipes and `exec` the
  command, falling back to `/bin/sh -c '"$@"'` when that fails (D3). Three earlier forms failed on the
  prototype: a `/bin/sh` shim running the command without `exec` held the caller's descriptors for
  the command's life (gate pipes scenario); a `/bin/sh` shim with `exec` changed bash-as-sh's status
  for a missing interpreter (126 → 1); pre-checking the `#!` line cost dash ~6 ms a start. Bash-as-sh's
  `exec` with redirections and a command also leaks saved descriptors 10–12 into the command, which
  a perl shim never meets. In perl, `open(my $h, …) and close $h` acts on a global `$h`, not the new
  lexical (the prototype's pid report was silently lost so); the shim and keeper use `if (open(my
  $h, …)) { … }`.
- **A deadlock on bash-as-sh** → its `EXIT` trap runs at once on an untrapped fatal signal, with the
  command not yet reaped; a keeper waiting on that zombie and a wrapper waiting on the keeper hung.
  The trap now writes `now` first when the command may be running, so the keeper removes at once, as
  develop's trap did (§ 2.5; R3 as worded).
- **The prototype** the gate was dry-run against is kept as
  [`research/04-prototype.sh`](research/04-prototype.sh), for the build to read; the build writes
  `bin/sandbox.sh` from this section, with comments of its own.
- **Adversarial review** → see § 7.

## 5. Risks & open questions

- **For the maintainer (D1, D2):** the 2.0 s bound, the 5 ms → 0.1 s poll, and the per-start cost
  (+12.6–16.3 ms; about +42–55 s serial projection per full pytest run). The profile's whole
  `verify` under a fresh `TMPDIR`, gate mode `verify`, the planner's macOS host, 2026-11-09, run back
  to back with other worktrees' gates on the host: develop **1,542 s, 219 `cluster-mcp-sandbox.*`
  directories left** (counted anywhere under the `TMPDIR`, pytest's `tmp_path` trees included);
  the final prototype **1,610 s (+68 s, +4.4%), none left** (an earlier prototype: 1,617 s, none
  left). TECH P2 measures the final tree again and records its figure here.
- **The planner's figures are one host's.** The suite's per-command times moved by up to 14 s
  between the two runs above (the fourth command 196 → 216 s in the handshake era), so the +68 s
  carries that noise.
- **Linux is checked only by CI at landing.** Re-parenting to a subreaper, `/proc` zombie reads and
  dash's redirections are exercised by the new rows on `ubuntu-24.04`, not by any phase gate (no
  phase waits on a hosted run). A Linux subreaper inside a run would adopt the keeper and expose it to
  a run-wide stop; nothing in the repo sets one (03 § 2).
- **PID reuse.** After the wrapper dies the keeper waits on the command's bare pid; a recycled pid makes
  it wait for that process instead. Within the 5 ms–0.1 s poll this needs the kernel to cycle through
  the pid space; accepted.
- **Zombies on macOS** are read only by `kill 0`: an orphan is reaped by launchd within ~1 ms
  (03 § 4). A non-reaping parent would hold the directory until it reaps.
- **Stops that reach the keeper on purpose** (`pkill -f cluster-mcp-sandbox-keeper`, a cgroup or
  scope kill, the CI runner's orphan cleanup at job end) leave the directory, as today's SIGKILL does.
- **The sibling cycles.** `mutant-child-outlives-timeout`'s PLAN (lines 95–98, 300–301, 388, D4) and
  TECH (115–117) say the sandbox home stays after its stop; once this lands that is no longer true,
  and its seed sentence edit conflicts with the GOAL's Clarification (research 02 § 5). Its frozen
  gate pins `BASE = 71a3a49` and fails any path outside its list, so landing it first is simpler; this
  cycle's `files` mode diffs against the merge base with `origin/develop`, so it rebases either way.
  The seed's "last three" referent is fixed at the second landing (GOAL Clarifications). Overlap with
  `tests/test_hygiene.py` (skip-check-fence-gaps): none; this cycle does not edit it.
- **A process the command starts that leaves the group and outlives it** is not waited for (GOAL
  non-goal); its own leftovers are [`issues/local-command-outlives-server.md`](../../issues/local-command-outlives-server.md).

## 6. Verification strategy

The frozen gate is [`verify/keeper.py`](verify/keeper.py) (its docstring lists the modes), run with
the repo's interpreter (`uv run python -I`). It installs `bin/sandbox.sh` from the **index** and
develop's from `0bfacae` into a scratch lab, never the working copy; `SDLK_SH=/bin/dash` runs both
under dash (Ubuntu's `/bin/sh`). Every process it starts carries a token in its argv and each mode
ends by asserting none is left.

- `kill`: group SIGKILL; the wrapper alone, the command outliving it with its directory, then the
  command (1 s later, and 6 s later); SIGSTOP of the group, a walk by parent and group (the
  sibling's rule) that must not reach the keeper, SIGSTOP and SIGKILL of every group found; the
  wrapper in the caller's group; a group USR1 the command survives, held to develop's outcome in the
  same shell; the caller's stdout, stderr and a passed pipe reaching end of file while the command
  (which closed its own) still runs; a background job outliving both; a nested sandbox. Each: the
  directory gone within `BOUND` of both having ended, the keeper found while it ran (polled), its
  command line free of a planted variable and the gate's argv token, and gone after (R1, R6, the
  reach constraint).
- `race`: 64 group kills at 0–80 ms after start, and 24 freeze-walk-kills at 0–20 ms; a command a
  fork carried past its kill is killed as a harness's re-walk would; none left (R1).
- `exit`: the command's exit, and HUP, INT, TERM while it runs, five times each, and a builtin that
  ends the wrapper (`eval '… exit 5'`): removed before the wrapper exits, status 5 passed, the keeper
  gone at the instant the wrapper is reaped (R3, R6).
- `share`: a kill and an exit beside a running sandbox, in one `TMPDIR` and in two, and the older of
  two killed beside the newer (R4).
- `decoys`: old-named directories, a file and a symlink of the sandbox pattern, and another directory,
  byte-identical after four exit paths (R5).
- `same`: develop's wrapper and the tree's on a probe of HOME, cwd, XDG, the markers, stdin, HOME's
  listing, descriptors, parent and group, signal dispositions and the sorted environment, and on the
  statuses and stderr of exit 0, exit 3, a killed command, a missing one, a directory, `exit`, a
  missing interpreter, a directory as interpreter, a shebang-less script, `eval` and `command` (D3's
  parent allowed for those two), perl's variables set, a broken locale, a newline `TMPDIR` (with a
  planted directory that must survive) and a relative one (line numbers, pids and sandbox names
  normalised); TERM not forwarded; a group TERM to a command that ignores it waited for (R7, R5).
- `controls`: develop's wrapper installed in the tree's place must fail `kill` and `race`.
- `rows`: the new module's ids, its planted controls, `tests/test_hygiene.py`, the `tests/test_cli.py`
  sandbox row, `tests/test_transports.py` and `tests/test_registry.py`'s `SANDBOX_NEEDS` row.
- `suite`, `mutants`, `verify`: R2 for a pytest run of the rows that SIGKILL sandboxes, for
  `tests/mutants.py` over one case within its limit and past a patched 1 s limit (the runner
  imported, only its child run's `subprocess.run` given the limit, or the sibling's `LIMIT` set;
  the timeout asserted; the file not edited), and for the profile's whole `verify`; each under a
  fresh `TMPDIR`, with no `cluster-mcp-sandbox.*` directory anywhere under it `BOUND` after the last
  keeper of the run has gone.
- `files`, `ledger`: the cycle's paths against the merge base with `origin/develop`; every deferral
  phrase in PLAN, TECH and the branch's commit bodies names an `issues/` seed indexed in `ROADMAP.md`.

**The mutant sweep** (P1 writes it, as code-build Step 4 says; the planner's spot check of the same
list on the prototype is § 7): plant each into a scratch copy of the staged `bin/sandbox.sh` and run
the mode named, in both shells; each must go red.

| Mutant | Mode |
|---|---|
| the keeper keeps the wrapper's group (no `setpgrp`) | `kill` |
| `setpgrp` after `mktemp` | `race` (freeze-walk-kill) |
| the middle child becomes the keeper (no second fork; the starter does not wait) | `kill` (the walk) |
| the keeper does not ignore SIGPIPE before it reports the directory | `race` |
| the keeper keeps the caller's argv (no clean re-exec) | every mode (the planted check) |
| the keeper keeps the caller's environment | every mode on Linux (`/proc/<pid>/environ`); macOS shows no process's environment to `ps`, so there it survives |
| the keeper keeps the caller's stdout, or other inherited descriptors | `kill` (pipes) |
| the shim keeps the keeper's pipes open for the command | `same` (descriptors) |
| the shim's pid report dropped | `kill` (wrapper alone) |
| the keeper removes on end of file without waiting for the pids | `kill` (wrapper alone) |
| the poll's ceiling 0.1 → 5 s, or the back-off uncapped (values, not nodes) | `kill` (6 s case) |
| `EXIT` does not wait for the keeper's end of file | `exit` (kqueue exit order); survived the planner's spot check, where the keeper still exited first: both remove the same two thousand files at once |
| `EXIT` does not write `now` while the command runs | `kill` (USR1, bash-as-sh) |
| `HUP INT TERM` not deferred | `exit` |
| builtins run in the wrapper, not in a reporting subshell | `same` (eval, command: descriptors) |
| the keeper does not wait for `go` | `race`; the window it opens showed once in ~400 freeze-walk-kills, so a single run can pass it |
| the shim's `/bin/sh` fallback dropped | `same` (a directory, a missing interpreter) |
| `command -v` dropped (every command through the shim) | `same` (a builtin) |
| perl's variables not neutralised, or not put back | `same` (perl variables, broken locale) |
| the template's absolute-and-one-line check dropped | `same` (newline and relative `TMPDIR`) |
| `read` without `IFS=` | `same` (newline `TMPDIR`) |
| the keeper removes `<dir>/..` | `decoys` |
| the variable is not unset before the command | `same` |

A mutant that every mode passes is recorded as a survivor with its reason. The planner's spot check on
the final prototype (bash-as-sh; § 7) went red on every row but four: `EXIT` not waiting, the
environment kept (macOS), `go` not awaited, and the shim's closes (red only in `same`, as listed).

## 7. Adversarial review

One fresh reviewer (2026-11-09) read GOAL, this design, the prototype and the drafted gate, and probed
the prototype in a lab on macOS. Every finding was folded in, and the gate re-run on the new
prototype in both shells (§ 6, the planner's run in the report).

- **HIGH — the keeper's command line.** The prototype renamed its `$0` in place; the keeper now
  re-executes perl with its own argv and an environment of `PATH` alone, before it waits (§ 2.3), and
  every gate `Box` asserts a planted variable and the gate's argv token are absent from it.
- **A newline or a relative `TMPDIR`** made the prototype read the wrong directory (and remove one it
  did not make) or remove a relative path from `/`. Such a template now takes develop's path (D5),
  the wrapper reads with `IFS= read -r`, and gate `same` compares both against develop with a planted
  directory.
- **Builtins as the command** (`eval '… exit 3'`, `command sh …`): R3 failed (the trap returned
  early), the pipes leaked to the builtin's programs, and a background job of theirs held the
  directory. Builtins now run in a subshell that reports its pid and closes the pipes; `exec` runs as
  on develop; the trap is inline. Gate: `exit` (eval), `same` (eval, command).
- **Perl's own environment** (`PERL5OPT` stopped the command; a broken locale printed a warning on
  every start): neutral values for every perl here, the caller's restored before any `exec`
  (§ 2.1). Gate `same`: both cases.
- **R3 on bash-as-sh's untrapped signals.** The prototype deferred removal to the command's end;
  R3 says every path that removed the directory on develop still does. The trap now tells the keeper
  `now` (§ 2.5); gate `kill` compares the USR1 path with develop's in each shell.
- **A start-up race the review's new gate case exposed**: the freeze-walk-kill at 0–20 ms left a
  directory about once in 400 kills (a keeper seen in the run, killed by pid after it left) and, before
  that, a keeper killed by SIGPIPE writing to a dead wrapper. The `ready`/`go` exchange and an early
  SIGPIPE ignore closed both (§ 2.3, § 4).
- **Gate blind spots**: an over-long poll (new 6 s case), the keeper found by one `ps` snapshot (now
  polled), start-up only by `killpg` (a freeze-walk-kill race added), the newest sandbox always the
  one killed (the older of two now), `settle_lab` waiting on argv (now on keepers), the mutation
  runner's limit patched on every `subprocess.run` (now only the child run's, and the timeout
  asserted), and no negative control (mode `controls`: develop's wrapper fails `kill` and `race`).
  The test module gains `[pipes]` and `[background]` rows, where Linux differs most.
- **LOW, folded**: `kill 0`'s EPERM read as alive; the `/proc` state read after the last `)`; the
  trap's read retried; the keeper closes descriptors 3–255 instead of reading `/dev/fd`; a caller
  that ignores SIGCHLD; `/usr/bin/perl` when `PATH` lacks perl.
- **Deviation rows**: D4 (an untrapped signal) was a bend of R3 and is gone; D3, D4 (R6 as one
  act) and D5 (R1 where no keeper starts) go to the sign-off as readings or rulings.
- **Accepted, not changed**: a keeper without `chdir "/"`, without ignoring HUP, or a wrapper not
  holding up's read end would pass every mode (each is hygiene against a stop that never comes: a
  cwd held on a mount, a hangup to a group that is not in the foreground, a keeper killed from
  outside); PID reuse; a caller running the script under another shell explicitly (no caller does).

---

*Backing research: [`research/00-digest.md`](research/00-digest.md).*
