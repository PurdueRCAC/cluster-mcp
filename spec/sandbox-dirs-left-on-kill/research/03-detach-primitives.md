# 03 — Detach primitives for a SIGKILL-proof sandbox cleanup

Measured 2026-11-09 on macOS 27 (arm64; `/bin/sh` = bash 3.2.57 in sh mode; `/bin/dash`; perl 5.34.1),
every probe in a throwaway `mktemp -d` lab, prototypes outside the repo. Ubuntu facts are from package
contents, not runs (no Linux host was used). Medians of ≥ 20 runs unless stated.

## 1. A new process group (or session) from POSIX sh

| Primitive | Result |
|---|---|
| `setsid(1)` | absent on macOS; util-linux on Ubuntu. Not portable. |
| `set -m` in a non-interactive, tty-less sh | bash-as-sh: yes, each `&` job gets its own pgid. **dash: no**, `&` jobs stay in the shell's group. Not portable. |
| `perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV'` | works on both; **10.7 ms** a start (loading POSIX.pm costs ~6.5 ms of it) |
| `perl -e 'setpgrp(0,0); exec …'` (builtin, no module) | works on both; **4.2 ms** (bare `perl -e 1`) |
| `/usr/bin/python3 -I -S -c 'import os; os.setsid()'` | **32.4 ms**; on macOS a Command Line Tools stub: on a Mac without CLT it opens an install dialog. Reject. |

perl ships with macOS; on ubuntu-24.04 `perl-base` is Essential, and the recommended watcher loads **no
module at all** (builtins only), so perl-base suffices. **Recommend perl builtins (`setpgrp(0,0)`), with
the fallback rule: `command -v perl` fails → no watcher, today's behaviour (trap only).** A new
group is enough here. It is not a new session, but a terminal hangup or `^C` goes to the
foreground group only, and the watcher also ignores HUP and INT.

## 2. Double fork

`( cmd & )`: the grandchild's ppid was already 1 at its first instruction (perl saw `getppid()==1`
with 0 polls, 5/5 runs in each shell). Reparenting completes before the grandchild finishes its exec
(< ~4 ms). Seen in `ps` during a run: watcher `PPID 1`, `PGID` = its own PID; with `setsid` it is also a
session leader (`s`). A live-parent/group walk from the wrapper does not reach it. **Caveat:** a
Linux *subreaper* ancestor (container init, systemd user unit, a runner using
`PR_SET_CHILD_SUBREAPER`) would adopt it instead of PID 1. None in this repo (grep for `prctl` and
`subreaper` finds nothing).

## 3. FIFO handshake

- `exec 9>fifo` / `exec 8<fifo` work in both shells. An open blocks until the other end opens. Unlink
  after both opens is fine (reads and writes continue).
- Reader EOF after SIGKILL of the writer alone: **0.5 ms** (bash-sh), **0.7 ms** (dash), when the child
  ran with `9>&-`. A child that inherits fd 9 held EOF off for **2.8 s**, its whole life. So `9>&-`
  (and `8<&-`) on the command is mandatory. With it, the command saw no fd above 2 (probe over fds 3–9,
  same as today).
- dash execs the last simple command of a `-c` string in place (it does not do that for a script file):
  a probe must keep that in mind, and the wrapper itself is unaffected.
- `set -eu`: the handshake reads sit in `if read …` / `|| :`. A failed `exec 9>…` exits through the
  trap like any other error.

## 4. Zombies

`kill -0` **succeeds on a zombie** (both shells). `ps -o stat= -p PID` shows `Z…` (here `ZN`), and an empty
result means gone. Cost: **2.6–3.2 ms** from sh, **2.4 ms** from perl list-form `open '-|'`, and **6.2 ms**
through perl backticks (they add a `/bin/sh`). After `killpg(SIGKILL)` of wrapper and command, the
command's PID stopped answering `kill -0` (reaped by launchd) in a median of **0.4–1.0 ms**, max 1.3 ms.

## 5. Sleep and poll loop

Fractional `sleep` works on macOS (`sleep 0.05` = **58–59 ms**, `sleep 0.1` = **108 ms**). Ubuntu's
coreutils `sleep` accepts fractions, and dash has no builtin `sleep`. `kill -0` costs **0.07–0.08 ms**.
A full sh iteration (`kill -0` + `ps` + `sleep 0.1`) costs **111–114 ms**. The perl watcher avoids `sleep`
(it uses `select`).

## 6. Costs

Per-start wall time of `bin/sandbox.sh true` (`TMPDIR` in the lab, n = 40, two repeats agreeing within
1 ms):

| | bash-sh | dash |
|---|---|---|
| (a) today | 13.5–15.5 ms | 10.6–11.6 ms |
| (b1) sh watcher + `perl -MPOSIX` setsid + shim + 2 FIFOs | 35.5–39.4 (**+22–24**) | 29.5–31.8 (**+19–20**) |
| (b2) all-perl watcher (builtins), wrapper makes dir and FIFOs | 25.3–25.6 (**+11.8–11.9**) | 20.6–20.7 (**+10.1**) |
| (b3) recommended: the watcher makes the dir (see §8) | 26.1–26.2 (**+12.5–12.6**) | 21.3 (**+10.7–10.9**) |

(c) From `killpg(SIGKILL)` to the directory being gone (n = 25 a cell; no leak, no watcher left in any run):

| watcher | poll 0.05 s | 0.1 s | 0.25 s |
|---|---|---|---|
| b1: sh watcher, fixed interval | med 3.2–3.5 ms, max 64–68 ms | med 3.2 ms, max 116 ms | med 3.5 ms, max 266–270 ms |
| b2: perl, fixed interval | med 3.5–3.8, p90 62–68 ms | med 3.8–3.9, p90 115 ms | med 3.8–4.1, p90 267–271 ms |
| b2: perl, backoff from 5 ms to the interval | med 3.5–3.8, max 19 ms | med 3.5–3.8, max 20–21 ms | med 3.6–3.8, max 19 ms |

The tail is one poll interval: the watcher sees EOF before the killed command is reaped, gets
`kill -0` = alive, and sleeps. A 5 ms-doubling backoff removes it. b3, with the same backoff at 0.1 s: med 16.4–18.1 ms, max 20.3 ms (n = 25 a shell). Wrapper killed **alone** (command
`sleep 1` runs on): the directory went 33–130 ms after the command's PID went (interval 0.1 s, n = 5–8), so the bound
there is the interval plus `ps` and `rm`.

(d) Idle watcher during a 5 s command: **0:00.00 CPU** (blocked in `read`), RSS ≈ 4 MB.

**Suite projection (estimate):** a full `pytest` run of this worktree (5016 passed, 14 skipped, 888 s, macOS, `TMPDIR` in the lab) made **3356** sandbox starts, counted by a lab `mktemp` shim on `PATH` (one call per start). At +11–13 ms a start, that is **+37–42 s** of wrapper time if fully serial (≈ 4–5 % of 888 s), and less where the suite overlaps starts. Mutation sweeps not counted. The same run, with today's script, left **90** `cluster-mcp-sandbox.*` directories in its `TMPDIR` (probes ran alongside it, so the host was not idle).

## 7. Edge cases (all measured on both shells, prototype vs. today)

- **Exit status passes through** (`exit 3` → 3, `true` → 0). Stdout: only the command's (`echo hi` → `hi`).
- **HUP, INT and TERM to the wrapper while the command runs:** deferred until the command ends in both
  shells, for today's script and the prototypes alike. The command (1 s, signalled at 0.3 s) finished, and the wrapper exited 731–803 ms after the signal
  with the command's status (7), not a signal status. The directory was present 200 ms after the
  signal and gone at exit, with no watcher left.
- **perl missing** (`command -v` fails) **and perl that exits at once** (`/usr/bin/false`): the command
  runs, its status passes (4, 5, 6), and the trap still removes the directory.
- **Command not found:** status 127 in both cases. The message changes: `sh: line 0: exec: X: not found`
  (bash-sh) and `sh: 1: exec: X: not found` (dash) in place of `<path>/bin/sandbox.sh: line 88: X: command not found`.
  **Not executable:** today bash-sh exits **1** (dash 126); through the shim both give **126**, and bash-sh
  prints two lines. Passing the wrapper's `$0` as the shim's name (as the sketch does) should bring back the script-path prefix; that variant was not measured.
- **Handshake window:** with the wrapper making the directory before the watcher has left the group,
  a group SIGKILL in the first ~5–18 ms leaked: **15/100** (bash-sh) and **14/100** (dash) of kills at
  U(0, 40 ms). With the watcher making the directory after `setpgrp` (§8): **0/150 leaked and 0
  orphans in each shell**. Kills that land before the wrapper has opened the FIFO are caught by the watcher's
  1 s `alarm` check of the wrapper's PID; cleanup then took **1.04–1.13 s** (21 of 300 runs).
- **A fork can outlive `killpg(SIGKILL)` on macOS.** After the b2 early-kill run, one forked copy of the
  wrapper (the `( … & )` grandchild, still in the killed group, ppid 1) was alive 17 min later, blocked in
  its redirect `open` of the FIFO. Its argv held no lab path, so the run's own orphan count (0) had missed
  it: at least 1 orphan in 200. It was a fork that raced the kill. In b3 such an escapee is perl itself:
  it makes the directory, finds the wrapper gone at the next alarm tick, and removes it.

## 8. Recommended mechanism (sketch)

```sh
watching= sandbox=
cleanup() {
  if [ -n "$watching" ]; then watching=
    { printf 'done\n' >&9; } 2>/dev/null || :; exec 9>&-
    read -r _ <&8 || :; exec 8<&-          # EOF when the watcher's rm has exited
  fi
  [ -z "$sandbox" ] || rm -rf "$sandbox"
}
trap cleanup EXIT HUP INT TERM
if command -v perl >/dev/null 2>&1; then
  sandbox="$( (exec perl -e "$WATCH" "${TMPDIR:-/tmp}" "$$" </dev/null 2>/dev/null &) )" || sandbox=
  if [ -n "$sandbox" ]; then
    exec 9>"$sandbox/.w-a" 8<"$sandbox/.w-b"
    if read -r ok <&8 && [ "$ok" = ready ]; then watching=1; else exec 9>&- 8<&-; fi
  fi
fi
[ -n "$sandbox" ] || sandbox="$(mktemp -d "${TMPDIR:-/tmp}/cluster-mcp-sandbox.XXXXXX")"
# … HOME/XDG/env exactly as today; cd "$sandbox" …
if [ -n "$watching" ]; then
  /bin/sh -c 'printf "%s\n" "$$" >&9; exec 9>&-; exec "$@"' "$0" "$@" 8<&-
else "$@"; fi
# $WATCH (perl, builtins only): setpgrp(0,0); chdir "/"; ignore HUP INT PIPE;
#   mkdir "$tmp/cluster-mcp-sandbox.XXXXXX" 0700 (random [A-Za-z0-9]{6}, retry on EEXIST);
#   system mkfifo .w-a .w-b; print dir; close STDOUT;
#   open .w-a for read, then .w-b for write, each under alarm 1 → if the wrapper PID is gone or a zombie: exec rm;
#   unlink both; write "ready"; read the PID line, then lines until EOF ("done" = normal exit);
#   no "done": while kill 0 PID and ps stat !~ Z: select(5 ms doubling to 0.1 s);
#   exec "rm","-rf","--",$dir       # its last act; closes .w-b, which releases the wrapper
```

| Figure | Value |
|---|---|
| per-start overhead (b3) | +10.7–10.9 ms (dash), +12.5–12.6 ms (bash-sh) |
| killpg → dir gone (backoff) | b2: med 3.5–3.8 ms, max ≤ 21 ms; b3: med 16.4–18.1 ms, max 20.3 ms |
| wrapper killed alone → dir gone after the command ends | ≤ poll + ~30 ms (0.1 s: 33–130 ms) |
| kill before the FIFOs are open → dir gone | ≤ ~1.1 s (the alarm tick) |
| idle watcher CPU | 0 |
| leaks / orphans | b3: 0 / 0 over 300 early and 50 timed group kills; b1 and b2: 0 leaks over ~600 timed kills |

## Risks

- **Redirect-opened FIFOs (b2) can block forever** in a grandchild that escaped the kill (§7). Open the
  FIFOs inside perl, under an alarm that checks the wrapper's PID, as b3 does.
- **PID reuse:** after a SIGKILL the watcher waits on a bare PID. If it is recycled to the same user's
  process, cleanup waits for that process. Rare, and bounded by that process's life.
- **Subreaper hosts** (§2) adopt the watcher, so it becomes a live descendant that a run-wide stop could reach.
- **Session-wide or cgroup kills** (a `pkill -s`, a systemd scope stop, the CI runner's orphan reaper
  at job end) do reach the watcher. Out of scope, but say so.
- **No perl** (Alpine, minimal images): silently today's behaviour. Say so in the script.
- **Observable changes:** the command-not-found message text, and on macOS bash-sh the status of a
  non-executable command, 1 → 126 (R7 review). `.w-a` and `.w-b` exist in the directory for about a
  millisecond before the command starts, and the directory's name comes from perl's `rand`, not `mktemp`'s generator.
- The wrapper's `exec 9>` blocks if perl reports a directory and then dies before opening the FIFO.
  That takes a broken perl, and the earlier redirect-based variant (opens done by `sh` before
  `exec perl`) trades this for the leak window in §7.
