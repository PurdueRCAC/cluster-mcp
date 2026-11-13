"""The frozen gate for sandbox-dirs-left-on-kill: `bin/sandbox.sh` as the index holds it.

Usage, from the root of the tree under test, with the repo's interpreter:

    uv run python -I spec/sandbox-dirs-left-on-kill/verify/keeper.py MODE...

Modes (PLAN.md section 6 maps each to its R-IDs):

    kill     R1, R6 and the plan's reach constraint: SIGKILL of the wrapper's group; of the wrapper
             alone (the command lives on with its directory), the command 1 s or 6 s later; a
             freeze, a walk by parent and group that must not reach the keeper, and SIGKILL of
             every group and pid found; the wrapper in the caller's group; a group USR1 the command
             survives, held to develop's outcome in the same shell; the caller's pipes ending with
             the wrapper; a background job outliving both; a nested sandbox. Every keeper is
             looked for while its sandbox runs, and its command line must not show the caller's
             environment or argv.
    race     R1 at start-up: 64 group SIGKILLs at 0-80 ms and 24 freeze-walk-kills at 0-20 ms.
    exit     R3, R6: the command's exit, and HUP, INT and TERM to the wrapper while it runs, five
             times each, and a builtin that ends the wrapper; the keeper gone at the wrapper's exit.
    share    R4: two sandboxes in one TMPDIR and in two; one is killed or ends (the older of two
             too), the other's directory is untouched while its command runs.
    decoys   R5: directories and files planted in TMPDIR (old sandbox names among them) survive
             every exit path, byte for byte.
    same     R7 (and R5 for odd TMPDIRs): develop's wrapper (0bfacae) and the index's, side by side,
             on every observable the GOAL lists, for commands, builtins, failing commands, perl's
             variables, a broken locale and a newline or relative TMPDIR.
    suite    R2: one pytest run of the rows that SIGKILL a sandbox, under a fresh TMPDIR.
    mutants  R2: tests/mutants.py over one case, then the same case with its child past a
             patched 1 s limit (asserted to have fired), under a fresh TMPDIR.
    verify   R2: the profile's verify command (read from AGENTS.md), under a fresh TMPDIR.
    rows     The new module's rows by id with its unit controls, and the rows that pin the wrapper.
    files    Only the cycle's paths change against the merge base with origin/develop.
    ledger   Every deferral phrase in PLAN, TECH and the branch's commit bodies names a seed.
    controls Develop's wrapper put in the tree's place: kill and race must go red.

Run the process modes (kill to same) twice: as is, and with SDLK_SH=/bin/dash, which installs both
wrappers with /bin/dash in place of /bin/sh (Ubuntu's /bin/sh, the CI runner's).

Footprint: one mode at a time, at most 3 sandboxes (each a wrapper, a keeper and one `sleep`)
alive at once outside `suite`, `mutants` and `verify`, which run one pytest or one runner. Memory
is a few MB outside those three. Every process the gate starts carries TOKEN in its argv, and each
mode ends by asserting none is left.
"""

import os
import random
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

DEVELOP = '0bfacae'
TOKEN = 'sdlk-gate-7f3c'
NAME = re.compile(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}$')
KEEPER = 'cluster-mcp-sandbox-keeper'
# Planted in every sandbox's environment: no keeper's command line may show it, nor the gate token.
PLANTED = ('SDLK_PLANTED_VALUE', 'sdlk-planted-4e1d')

# The proposed bound (PLAN.md section 3, D1): from the moment the wrapper and its command have both
# ended until the directory is gone. The maintainer sets the figure; a ruling changes it here.
BOUND = 2.0
SETTLE = 10.0          # how long a kill gets to take every killed process down
STARTED = 10.0         # how long a sandbox gets to start its command

ROOT = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True,
                           check=True).stdout.strip())
ENV = dict(os.environ)
failures: list[str] = []


def fail(message: str) -> None:
    failures.append(message)
    print(f'FAIL  {message}', flush=True)


def ok(message: str) -> None:
    print(f'ok    {message}', flush=True)


def install(lab: Path, rev: str | None) -> Path:
    """Write bin/sandbox.sh from the index (rev None) or from rev into lab/<name>/bin."""
    spec = f'{rev}:bin/sandbox.sh' if rev else ':bin/sandbox.sh'
    text = subprocess.run(['git', 'show', spec], cwd=ROOT, capture_output=True, check=True).stdout
    home = lab / ('develop' if rev else 'tree') / 'bin'
    home.mkdir(parents=True, exist_ok=True)
    script = home / 'sandbox.sh'
    # SDLK_SH runs both wrappers under another sh (/bin/dash: Ubuntu's /bin/sh, the CI runner's).
    if os.environ.get('SDLK_SH'):
        text = text.replace(b'/bin/sh', os.environ['SDLK_SH'].encode())
    script.write_bytes(text)
    script.chmod(0o755)
    return script


def table() -> list[tuple[int, int, int, str, str]]:
    out = subprocess.run(['ps', '-A', '-o', 'pid=,ppid=,pgid=,stat=,command='], capture_output=True,
                         text=True, check=True, env=ENV).stdout
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) >= 4:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3],
                         parts[4] if len(parts) == 5 else ''))
    return rows


def alive(pid: int) -> bool:
    """A pid that exists and is not a zombie."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    out = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True).stdout
    return bool(out.strip()) and not out.strip().startswith('Z')


def quick_alive(pid: int) -> bool:
    """kill 0 alone: no process is started before it answers."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_until(test, limit: float, step: float = 0.02) -> float | None:
    """Poll `test` until true; return the seconds it took, or None past `limit`."""
    start = time.monotonic()
    while True:
        if test():
            return time.monotonic() - start
        if time.monotonic() - start > limit:
            return None
        time.sleep(step)


def leftovers(lab: Path, keep: set[Path] = frozenset()) -> list[Path]:
    """Every sandbox-named directory anywhere under lab, decoys excepted."""
    return [p for p in lab.rglob('cluster-mcp-sandbox.*') if p.is_dir() and p not in keep]


class Box:
    """One sandbox: a wrapper running `sh -c` that records its pid and HOME, then sleeps."""

    def __init__(self, script: Path, tmpdir: Path, tag: str, new_session: bool = True,
                 inner: str = 'exec sleep 60'):
        self.out = tmpdir.parent / f'{tag}.{TOKEN}'
        self.out.mkdir()
        env = {**ENV, 'TMPDIR': str(tmpdir), PLANTED[0]: PLANTED[1]}
        body = (f'printf "%s\\n" "$$" > "$1/pid"; printf "%s\\n" "$HOME" > "$1/home.tmp"; '
                f'mv "$1/home.tmp" "$1/home"; {inner}')
        self.proc = subprocess.Popen([str(script), 'sh', '-c', body, TOKEN, str(self.out)], env=env,
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=new_session)
        if wait_until(lambda: (self.out / 'home').exists(), STARTED) is None:
            raise RuntimeError(f'{tag}: the sandbox never started its command')
        self.home = Path((self.out / 'home').read_text().strip())
        self.command = int((self.out / 'pid').read_text().strip())
        self.keepers = []
        # Develop's wrapper starts no keeper; the tree's must, and is looked for until it shows.
        if script.parent.parent.name == 'tree':
            wait_until(self.find_keepers, STARTED, 0.05)
        for pid, _, _, _, cmd in table():
            if pid in self.keepers and (PLANTED[1] in cmd or TOKEN in cmd):
                fail(f'{tag}: the keeper\'s command line shows the caller\'s environment or argv: {cmd[:200]!r}')
        for pid in self.keepers:
            if PLANTED[1] in environment(pid):
                fail(f'{tag}: the keeper holds the caller\'s environment')

    def find_keepers(self) -> bool:
        self.keepers = keepers_of(self.home)
        return bool(self.keepers)

    def ended(self) -> bool:
        return self.proc.poll() is not None and not alive(self.command)


def environment(pid: int) -> str:
    """A process's environment as the host shows it to its owner (Linux /proc, else ps -E)."""
    try:
        return Path(f'/proc/{pid}/environ').read_bytes().decode(errors='replace')
    except OSError:
        return subprocess.run(['ps', '-E', '-ww', '-o', 'command=', '-p', str(pid)], capture_output=True,
                              text=True).stdout


def keepers_of(home: Path) -> list[int]:
    """Keepers whose command line names this sandbox directory."""
    return [pid for pid, _, _, stat, cmd in table()
            if cmd.startswith(KEEPER) and home.name in cmd and not stat.startswith('Z')]


def check_gone(box: Box, label: str) -> None:
    """Both ended: the directory goes within BOUND, and no keeper of it is left (R1, R6)."""
    if wait_until(box.ended, SETTLE) is None:
        fail(f'{label}: the wrapper or its command outlived the kill by {SETTLE} s')
        return
    took = wait_until(lambda: not box.home.exists(), BOUND)
    if took is None:
        fail(f'{label}: {box.home.name} still exists {BOUND} s after the wrapper and its command ended')
    else:
        ok(f'{label}: directory gone {took * 1000:.0f} ms after both ended')
    left = [pid for pid in box.keepers if alive(pid)]
    if left or not box.keepers:
        fail(f'{label}: keepers found {box.keepers}, alive after removal {left}')


def killpg(group: int, sig: int) -> None:
    """killpg; macOS answers EPERM for a group whose only members are zombies, which is done."""
    deadline = time.monotonic() + 1.0
    while True:
        try:
            os.killpg(group, sig)
            return
        except ProcessLookupError:
            return
        except PermissionError:
            rows = [r for r in table() if r[2] == group]
            if all(r[3].startswith('Z') for r in rows):
                return
            print(f'note  EPERM signalling group {group}: {rows}', flush=True)
            if time.monotonic() > deadline:
                raise
            time.sleep(0.01)


def walk(root: int) -> set[int]:
    """Every pid reachable from root through live parents or group membership (the sibling's stop)."""
    pids, groups = {root}, set()
    while True:
        rows = table()
        groups |= {pgid for pid, _, pgid, _, _ in rows if pid in pids}
        more = {pid for pid, ppid, pgid, _, _ in rows if ppid in pids or pgid in groups} - pids
        if not more:
            return pids
        pids |= more


def mode_kill(lab: Path) -> None:
    script = install(lab, None)
    tmp = lab / 'tmp'
    tmp.mkdir()

    box = Box(script, tmp, 'group')
    killpg(box.proc.pid, signal.SIGKILL)
    box.proc.wait(timeout=SETTLE)
    check_gone(box, 'group SIGKILL')

    box = Box(script, tmp, 'alone')
    os.kill(box.proc.pid, signal.SIGKILL)
    box.proc.wait(timeout=SETTLE)
    time.sleep(1.0)
    if not alive(box.command) or not box.home.is_dir():
        fail('wrapper SIGKILL alone: the command or its directory did not outlive the wrapper')
    else:
        ok('wrapper SIGKILL alone: the command and its directory outlive the wrapper')
    os.kill(box.command, signal.SIGKILL)
    check_gone(box, 'wrapper SIGKILL alone, then the command')

    # A command that outlives its wrapper by 6 s: the poll's ceiling shows (an uncapped back-off would
    # next look ~10 s after the wrapper died).
    box = Box(script, tmp, 'alone-late')
    os.kill(box.proc.pid, signal.SIGKILL)
    box.proc.wait(timeout=SETTLE)
    time.sleep(6.0)
    os.kill(box.command, signal.SIGKILL)
    check_gone(box, 'wrapper SIGKILL alone, the command 6 s later')

    box = Box(script, tmp, 'freeze')
    killpg(box.proc.pid, signal.SIGSTOP)
    found = walk(box.proc.pid)
    reached = [pid for pid in box.keepers if pid in found]
    if reached or not box.keepers:
        fail(f'freeze-then-kill: a walk by parent and group reaches keepers {reached} (found {box.keepers})')
    else:
        ok(f'freeze-then-kill: the walk finds {len(found)} processes and no keeper')
    groups = {pgid for pid, _, pgid, _, _ in table() if pid in found}
    for group in groups:
        try:
            killpg(group, signal.SIGSTOP)
        except ProcessLookupError:
            pass
    for group in groups:
        try:
            killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    box.proc.wait(timeout=SETTLE)
    check_gone(box, 'freeze-then-kill')

    box = Box(script, tmp, 'caller-group', new_session=False)
    os.kill(box.proc.pid, signal.SIGKILL)
    os.kill(box.command, signal.SIGKILL)
    box.proc.wait(timeout=SETTLE)
    check_gone(box, 'caller-group SIGKILL of wrapper and command')

    # A signal no trap names, which the command survives: where develop's wrapper removes the
    # directory as it dies (bash-as-sh runs the exit trap), the tree's must too (R3); where it
    # leaves it (dash), the tree's goes once the command ends (R1).
    develop = install(lab, DEVELOP)
    probe = Box(develop, tmp, 'usr1-develop', inner='trap "" USR1; exec sleep 60')
    killpg(probe.proc.pid, signal.SIGUSR1)
    probe.proc.wait(timeout=SETTLE)
    removes = not probe.home.exists()
    os.kill(probe.command, signal.SIGKILL)
    shutil.rmtree(probe.home, ignore_errors=True)
    box = Box(script, tmp, 'usr1', inner='trap "" USR1; exec sleep 60')
    killpg(box.proc.pid, signal.SIGUSR1)
    box.proc.wait(timeout=SETTLE)
    if removes:
        if box.home.exists():
            fail('group USR1: develop removes the directory as the wrapper dies; the tree does not')
        else:
            ok('group USR1: removed as the wrapper dies, as on develop')
        os.kill(box.command, signal.SIGKILL)
        wait_until(lambda: not keepers_of(box.home), SETTLE)
        if keepers_of(box.home):
            fail('group USR1: a keeper outlives the removal')
    else:
        time.sleep(0.5)
        if not alive(box.command) or not box.home.is_dir():
            fail('group USR1: the surviving command lost its directory when the wrapper died')
        else:
            ok('group USR1: the wrapper dies, the command survives and keeps its directory')
        os.kill(box.command, signal.SIGKILL)
        check_gone(box, 'group USR1, then the command')

    # The keeper holds none of the caller's descriptors: once the wrapper is dead and the command has
    # closed its own, the caller's stdout, stderr and a passed pipe reach end of file while the
    # command still runs.
    read_end, write_end = os.pipe()
    env = {**ENV, 'TMPDIR': str(tmp)}
    inner = ('echo up; exec </dev/null >/dev/null 2>&1; '
             'exec perl -e \'for my $fd (3 .. 255) { if (open(my $h, "<&=", $fd)) { close $h } } exec "sleep", 60\'')
    proc = subprocess.Popen([str(script), 'sh', '-c', inner, TOKEN], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, pass_fds=(write_end,),
                            start_new_session=True)
    os.close(write_end)
    proc.stdout.readline()
    time.sleep(0.3)
    os.kill(proc.pid, signal.SIGKILL)
    start = time.monotonic()
    try:
        proc.communicate(timeout=SETTLE)
        os.set_blocking(read_end, True)
        extra = os.read(read_end, 1)
        took = time.monotonic() - start
        if extra or took > BOUND:
            fail(f'pipes: the caller\'s pipes reached end of file {took:.2f} s after the wrapper died')
        else:
            ok(f'pipes: stdout, stderr and a passed pipe end with the wrapper ({took * 1000:.0f} ms)')
    except subprocess.TimeoutExpired:
        fail(f'pipes: a pipe of the caller was still open {SETTLE} s after the wrapper died')
    finally:
        os.close(read_end)
        killpg(proc.pid, signal.SIGKILL)

    # A background job of the command that outlives it does not hold the directory.
    box = Box(script, tmp, 'background', inner=f'sh -c "exec sleep 30" {TOKEN}-bg </dev/null >/dev/null 2>&1 & '
                                              'exec sleep 60')
    os.kill(box.proc.pid, signal.SIGKILL)
    os.kill(box.command, signal.SIGKILL)
    box.proc.wait(timeout=SETTLE)
    check_gone(box, 'a background job outlives the wrapper and its command')

    box = Box(script, tmp, 'nested', inner=f'exec "{script}" sh -c "exec sleep 60" {TOKEN}')
    inner = wait_until(lambda: len(leftovers(tmp)) >= 2, STARTED)
    homes = leftovers(tmp)
    killpg(box.proc.pid, signal.SIGKILL)
    box.proc.wait(timeout=SETTLE)
    if inner is None:
        fail('nested: the inner sandbox never started')
    wait_until(lambda: not stragglers(), SETTLE)
    took = wait_until(lambda: not any(h.exists() for h in homes), BOUND)
    if took is None:
        fail(f'nested: {[h.name for h in homes if h.exists()]} left after a group SIGKILL')
    else:
        ok(f'nested: {len(homes)} directories gone {took * 1000:.0f} ms after the kill')
    if leftovers(tmp):
        fail(f'kill: left in TMPDIR {leftovers(tmp)}')


def mode_race(lab: Path) -> None:
    script = install(lab, None)
    tmp = lab / 'tmp'
    tmp.mkdir()
    env = {**ENV, 'TMPDIR': str(tmp)}
    procs = []
    spread = random.Random(7)
    for delay in [0, 0.001, 0.002, 0.005, 0.01, 0.02, 0.04, 0.08] + [spread.uniform(0, 0.04) for _ in range(56)]:
        proc = subprocess.Popen([str(script), 'perl', '-e', 'sleep 60', TOKEN], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        time.sleep(delay)
        killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=SETTLE)
        procs.append(proc)
    # The sibling's stop at start-up: freeze, walk by parent and group, kill every group found.
    for delay in [spread.uniform(0, 0.02) for _ in range(24)]:
        proc = subprocess.Popen([str(script), 'perl', '-e', 'sleep 60', TOKEN], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        time.sleep(delay)
        killpg(proc.pid, signal.SIGSTOP)
        found = walk(proc.pid)
        groups = {pgid for pid, _, pgid, _, _ in table() if pid in found}
        for group in groups:
            killpg(group, signal.SIGSTOP)
        for group in groups:
            killpg(group, signal.SIGKILL)
        for pid in found:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait(timeout=SETTLE)
        procs.append(proc)
    # A fork racing the kill can leave a command running (no signal reaches a process not yet in
    # the table); a harness's re-walk kills it, and R1 counts from its end. Do the same here.
    escaped = stragglers()
    for row in escaped:
        try:
            os.kill(row[0], signal.SIGKILL)
        except ProcessLookupError:
            pass
    if escaped:
        print(f'note  race: {len(escaped)} commands outlived their kill (a fork racing it), killed now', flush=True)
    wait_until(lambda: not stragglers(), SETTLE)
    took = wait_until(lambda: not leftovers(tmp), BOUND)
    if took is None:
        for home in leftovers(tmp):
            rows = [r for r in table() if home.name in r[4]]
            print(f'note  left {home.name}: holds {sorted(x.name for x in home.iterdir())}, '
                  f'mtime {home.stat().st_mtime:.3f}, processes naming it '
                  f'{[(r[0], r[1], r[2], r[3], r[4][:40]) for r in rows]}', flush=True)
            for r in rows:
                fds = subprocess.run(['lsof', '-a', '-p', str(r[0]), '-d', '0-255'], capture_output=True, text=True).stdout
                print(f'note  {r[0]} descriptors: {fds.strip()[-600:]!r}', flush=True)
        fail(f'race: {len(leftovers(tmp))} of {len(procs)} directories left after a SIGKILL at start-up')
    else:
        ok(f'race: {len(procs)} start-up kills (24 of them freeze-walk-kill), none left ({took * 1000:.0f} ms)')


def mode_exit(lab: Path) -> None:
    script = install(lab, None)
    tmp = lab / 'tmp'
    tmp.mkdir()
    runs = 0
    for name, sig in [('exit', None), ('HUP', signal.SIGHUP), ('INT', signal.SIGINT),
                      ('TERM', signal.SIGTERM)] * 5:
        runs += 1
        # Two thousand files in HOME make the keeper's removal take long enough to see a wrapper
        # that exits without waiting for it.
        many = 'mkdir "$HOME/many"; i=0; while [ $i -lt 2000 ]; do : > "$HOME/many/$i"; i=$((i + 1)); done; '
        box = Box(script, tmp, f'exit-{name}-{runs}', inner=many + 'sleep 1; exit 5')
        order = exit_order(box.proc.pid, box.keepers)
        if sig:
            os.kill(box.proc.pid, sig)
        status = box.proc.wait(timeout=SETTLE)
        # Looked at the instant the wrapper is reaped: a keeper still exiting then is a failure.
        first = [pid for pid in box.keepers if quick_alive(pid)]
        bad = []
        if order is not None and order() != 'keeper first':
            bad.append(f'the keeper did not exit before the wrapper ({order()})')
        if box.home.exists():
            bad.append(f'{box.home.name} exists when the wrapper has exited')
        left = [pid for pid in first if alive(pid)]
        if left or not box.keepers:
            bad.append(f'keepers found {box.keepers}, alive at the wrapper\'s exit {left}')
        if status != 5:
            bad.append(f'the wrapper exited {status}, not the command\'s 5')
        for message in bad:
            fail(f'{name}: {message}')
        if not bad:
            ok(f'{name}: removed before the wrapper exited, status 5, no keeper left')


    # A builtin as the command, which ends the wrapper itself (eval ... exit).
    for runs in range(3):
        out = tmp.parent / f'eval-{runs}.{TOKEN}'
        out.mkdir()
        proc = subprocess.Popen([str(script), 'eval', f'printf "%s\\n" "$HOME" > "{out}/home"; sleep 0.5; exit 5'],
                                env={**ENV, 'TMPDIR': str(tmp)}, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        status = proc.wait(timeout=SETTLE)
        home = Path((out / 'home').read_text().strip()) if (out / 'home').exists() else None
        if home is None or home.exists() or status != 5:
            fail(f'eval exit: status {status}, directory {home} still there at the wrapper\'s exit')
        else:
            ok('eval exit: a builtin ending the wrapper still removes the directory first, status 5')


def exit_order(wrapper: int, keepers: list[int]):
    """On a kqueue host, a callable naming which of wrapper and keeper the kernel saw exit first."""
    if not hasattr(select, 'kqueue') or len(keepers) != 1:
        return None
    queue = select.kqueue()
    watch = [select.kevent(pid, select.KQ_FILTER_PROC, select.KQ_EV_ADD, select.KQ_NOTE_EXIT)
             for pid in (wrapper, keepers[0])]
    try:
        queue.control(watch, 0, 0)
    except OSError:
        return None
    seen: list[int] = []

    def order() -> str:
        deadline = time.monotonic() + SETTLE
        while len(seen) < 2 and time.monotonic() < deadline:
            seen.extend(e.ident for e in queue.control(None, 2, 0.1) if e.ident not in seen)
        if len(seen) < 2:
            return f'exits seen {seen}'
        return 'keeper first' if seen[0] == keepers[0] else 'wrapper first'
    return order


def mode_share(lab: Path) -> None:
    script = install(lab, None)
    one = lab / 'one'
    two = lab / 'two'
    one.mkdir()
    two.mkdir()
    for place, label in ((one, 'shared TMPDIR'), (two, 'separate TMPDIRs')):
        keep = Box(script, one, f'keep-{label[:3]}', inner='echo kept > "$HOME/mark"; exec sleep 60')
        wait_until(lambda: (keep.home / 'mark').exists(), STARTED)
        before = sorted(str(p.relative_to(keep.home)) for p in keep.home.rglob('*'))
        for how in ('kill', 'end'):
            other = Box(script, place, f'other-{how}-{label[:3]}',
                        inner='exec sleep 60' if how == 'kill' else 'exit 0')
            if how == 'kill':
                killpg(other.proc.pid, signal.SIGKILL)
            other.proc.wait(timeout=SETTLE)
            wait_until(lambda: not other.home.exists(), BOUND)
            time.sleep(0.3)
        after = sorted(str(p.relative_to(keep.home)) for p in keep.home.rglob('*'))
        if after != before or (keep.home / 'mark').read_text() != 'kept\n':
            fail(f'{label}: the running sandbox\'s directory changed: {before} -> {after}')
        else:
            ok(f'{label}: a kill and an exit beside a running sandbox leave its directory as it was')
        killpg(keep.proc.pid, signal.SIGKILL)
        keep.proc.wait(timeout=SETTLE)
        check_gone(keep, f'{label}: the kept sandbox, killed last')
    # The older of two is killed: the newer one's directory stays while its command runs.
    older = Box(script, one, 'older')
    newer = Box(script, one, 'newer', inner='echo kept > "$HOME/mark"; exec sleep 60')
    killpg(older.proc.pid, signal.SIGKILL)
    older.proc.wait(timeout=SETTLE)
    check_gone(older, 'the older of two, killed')
    if not (newer.home / 'mark').exists():
        fail('the older of two killed: the newer one\'s directory changed')
    else:
        ok('the older of two killed: the newer one\'s directory is as it was')
    killpg(newer.proc.pid, signal.SIGKILL)
    newer.proc.wait(timeout=SETTLE)
    check_gone(newer, 'the newer of two, killed last')


def snapshot(where: Path) -> dict[str, tuple]:
    out = {}
    for p in sorted(where.rglob('*')):
        st = p.lstat()
        out[str(p.relative_to(where))] = (st.st_mode, st.st_size, st.st_mtime_ns,
                                          p.read_bytes() if p.is_file() and not p.is_symlink() else None)
    return out


def mode_decoys(lab: Path) -> None:
    script = install(lab, None)
    tmp = lab / 'tmp'
    tmp.mkdir()
    decoys = [tmp / 'cluster-mcp-sandbox.OLDaaa', tmp / 'cluster-mcp-sandbox.OLDbbb', tmp / 'other']
    for d in decoys:
        (d / '.config').mkdir(parents=True)
        (d / '.config' / 'keep').write_text(d.name)
    (tmp / 'cluster-mcp-sandbox.file').write_text('a file, not a directory')
    (tmp / 'cluster-mcp-sandbox.link').symlink_to(decoys[0])
    before = snapshot(tmp)
    for how in ('exit', 'TERM', 'group', 'alone'):
        box = Box(script, tmp, f'decoy-{how}', inner='exit 0' if how == 'exit' else 'exec sleep 60')
        if how == 'TERM':
            os.kill(box.proc.pid, signal.SIGTERM)
            os.kill(box.command, signal.SIGKILL)
        elif how == 'group':
            killpg(box.proc.pid, signal.SIGKILL)
        elif how == 'alone':
            os.kill(box.proc.pid, signal.SIGKILL)
            os.kill(box.command, signal.SIGKILL)
        box.proc.wait(timeout=SETTLE)
        wait_until(box.ended, SETTLE)
        wait_until(lambda: not box.home.exists(), BOUND)
    after = snapshot(tmp)
    if after != before:
        changed = sorted(set(before) ^ set(after) | {k for k in before if k in after and before[k] != after[k]})
        fail(f'decoys: TMPDIR changed beyond the sandboxes it made: {changed}')
    else:
        ok(f'decoys: {len(before)} planted entries unchanged across four exit paths')


PROBE = r'''
printf 'status-probe\n' >&2
printf 'home=%s\n' "$HOME" "cwd=$(pwd -P)" "xdg=$XDG_CONFIG_HOME|$XDG_CACHE_HOME|$XDG_DATA_HOME"
printf 'sandbox=%s repo=%s\n' "$CLUSTER_MCP_SANDBOX" "$CLUSTER_MCP_REPO"
printf 'stdin=%s\n' "$(cat)"
printf 'listing=%s\n' "$(ls -A "$HOME" | tr '\n' ' ')"
printf 'fds=%s\n' "$(ls /dev/fd | tr '\n' ' ')"
printf 'pids=%s %s %s\n' "$PPID" "$(ps -o ppid= -p $PPID | tr -d ' ')" "$(ps -o pgid= -p $$ | tr -d ' ')"
printf 'signals=%s\n' "$(perl -e 'print join ",", map { "$_=" . ($SIG{$_} // "") } qw(HUP INT QUIT TERM PIPE USR1)')"
env | LC_ALL=C sort | sed 's/^/env=/'
'''


def run_probe(script: Path, tmp: Path | str, argv: list[str], stdin: bytes = b'', extra: dict | None = None,
              cwd: Path | None = None) -> tuple[int, str, str]:
    env = {**ENV, 'TMPDIR': str(tmp), 'CLUSTER_MCP_SSH_HOST': 'blanked.example', 'JWT_SECRET': 'x',
           'UV_ENV_FILE': '/nonexistent', **(extra or {})}
    proc = subprocess.Popen([str(script), *argv], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True, cwd=cwd)
    out, err = proc.communicate(stdin, timeout=60)
    # The shell's own messages carry the script's line number and a pid: neither is the contract.
    norm = lambda s: re.sub(r'(line \d+:|: \d+:)(\s+\d+ )?', ': N:', s.decode().replace(str(script.parent.parent), '<root>'))
    text = re.sub(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}', 'cluster-mcp-sandbox.XXXXXX', norm(out))
    text = '\n'.join(l for l in text.splitlines()
                     if not re.match(r'env=(_|SHLVL|OLDPWD|PWD)=', l))
    # The command's parent and group, as the wrapper's pid sees them.
    def where(m: re.Match) -> str:
        parent, grandparent, group = (int(x) for x in m.groups())
        up = 'wrapper' if parent == proc.pid else 'one shell down' if grandparent == proc.pid else 'other'
        return f'parent={up} group={"wrapper" if group == proc.pid else "other"}'
    text = re.sub(r'pids=(\d+) (\d+) (\d+)', where, text)
    err_text = re.sub(r'cluster-mcp-sandbox\.[A-Za-z0-9]{6}', 'cluster-mcp-sandbox.XXXXXX', norm(err))
    return proc.returncode, text, err_text


def show_diff(name: str, a: tuple, b: tuple) -> None:
    for part, x, y in (('status', str(a[0]), str(b[0])), ('stdout', a[1], b[1]), ('stderr', a[2], b[2])):
        if x != y:
            xs, ys = x.splitlines(), y.splitlines()
            print(f'note  {name} {part}: develop only {[l for l in xs if l not in ys][:4]} '
                  f'tree only {[l for l in ys if l not in xs][:4]}', flush=True)


def mode_same(lab: Path) -> None:
    old, new = install(lab, DEVELOP), install(lab, None)
    tmp = lab / 'tmp'
    tmp.mkdir()
    probe = ['sh', '-c', PROBE]
    for name, body in (('orphan.sh', '#!/nonexistent/interpreter\nexit 0\n'), ('plain.sh', 'exit 6\n'),
                       ('dirinterp.sh', f'#!{lab}\nexit 0\n')):
        (tmp / name).write_text(body)
        (tmp / name).chmod(0o755)
    cases = {
        'probe': (probe, b'from stdin'),
        'exit 0': (['true'], b''),
        'exit 3': (['sh', '-c', 'exit 3'], b''),
        'killed': (['sh', '-c', 'kill -9 $$'], b''),
        'not found': (['cluster-mcp-no-such-command'], b''),
        'not executable': ([str(lab)], b''),
        'builtin': (['exit', '4'], b''),
        'no interpreter': ([str(lab / 'tmp' / 'orphan.sh')], b''),
        'no shebang': ([str(lab / 'tmp' / 'plain.sh')], b''),
        'directory interpreter': ([str(lab / 'tmp' / 'dirinterp.sh')], b''),
        'eval': (['eval', PROBE], b'from stdin'),
        'command': (['command', 'sh', '-c', PROBE], b'from stdin'),
        'perl variables': (probe, b'from stdin', {'PERL5OPT': '-MNoSuchModule', 'PERL5LIB': '/nonexistent',
                                                  'PERLIO': ':crlf', 'PERL_UNICODE': 'SDL'}),
        'broken locale': (probe, b'from stdin', {'LC_ALL': 'xx_YY.NOPE', 'LANG': 'xx_YY.NOPE'}),
    }
    for name, (argv, stdin, *more) in cases.items():
        extra = more[0] if more else None
        a = run_probe(old, tmp, argv, stdin, extra)
        b = run_probe(new, tmp, argv, stdin, extra)
        same = a == b
        # A builtin's program runs in a subshell of the wrapper on the tree (PLAN.md section 3, D3).
        if name in ('eval', 'command') and not same:
            same = (a[0], a[1].replace('parent=wrapper', 'parent=one shell down'), a[2]) == b
        if same:
            ok(f'same: {name} (status {a[0]})')
        else:
            show_diff(name, a, b)
            fail(f'same: {name} differs: develop {a!r} tree {b!r}'[:600])
    # A TMPDIR with a newline, and a relative one: as on develop, and nothing outside the sandbox
    # directory removed (the directory named by the TMPDIR's first line is planted with a file).
    odd = lab / 'odd'
    (odd / 'nl').mkdir(parents=True)
    (odd / 'nl' / 'precious').write_text('keep')
    (odd / 'nl\nx').mkdir()
    (odd / 'rel').mkdir()
    for name, where in (('newline TMPDIR', str(odd / 'nl\nx')), ('relative TMPDIR', 'rel')):
        a = run_probe(old, where, probe, b'x', cwd=odd)
        b = run_probe(new, where, probe, b'x', cwd=odd)
        if a != b:
            show_diff(name, a, b)
        if a != b or not (odd / 'nl' / 'precious').exists():
            fail(f'same: {name} differs or removed a directory it did not make: develop {a[:1]} tree {b[:1]}')
        else:
            ok(f'same: {name} (status {a[0]})')
    # No signal forwarded: a TERM to the wrapper leaves the command running to its end.
    for script, label in ((old, 'develop'), (new, 'tree')):
        box = Box(script, tmp, f'term-{label}', inner='trap "echo got >\\"$1/got\\"" TERM; sleep 1; exit 0')
        os.kill(box.proc.pid, signal.SIGTERM)
        status = box.proc.wait(timeout=SETTLE)
        if (box.out / 'got').exists() or status != 0:
            fail(f'same: {label}: TERM reached the command or changed the status ({status})')
        else:
            ok(f'same: {label}: TERM not forwarded, status {status}')
    # A group TERM to a command that ignores it: the wrapper waits for the command, as on develop.
    for script, label in ((old, 'develop'), (new, 'tree')):
        box = Box(script, tmp, f'group-term-{label}', inner='trap "" TERM; sleep 1; exit 0')
        start = time.monotonic()
        killpg(box.proc.pid, signal.SIGTERM)
        status = box.proc.wait(timeout=SETTLE)
        took = time.monotonic() - start
        if took < 0.5 or status != 0 or box.home.exists():
            fail(f'same: {label}: group TERM, the wrapper exited {status} after {took:.2f} s')
        else:
            ok(f'same: {label}: group TERM to a command that ignores it, the wrapper waits ({took:.2f} s)')
    if leftovers(tmp):
        fail(f'same: left in TMPDIR {leftovers(tmp)}')


SUITE_ROWS = [
    'tests/test_probes.py::test_the_lookup_over_ssh',
    'tests/test_transports.py',
    'tests/test_cli.py::test_sandbox_fails_closed_with_either_host_exported',
]


def mode_suite(lab: Path) -> None:
    tmp = lab / 'tmp'
    tmp.mkdir()
    env = {**ENV, 'TMPDIR': str(tmp)}
    proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', *SUITE_ROWS], cwd=ROOT,
                          env=env, capture_output=True, text=True)
    print(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-400:], flush=True)
    if proc.returncode != 0:
        fail(f'suite: pytest exited {proc.returncode}')
    settle_lab(tmp, 'suite')


def settle_lab(tmp: Path, label: str) -> None:
    """The run has ended: wait for any process naming the lab, then BOUND for the directories."""
    # A keeper still running waits for a command that has not ended; R2 counts from its end.
    gone = wait_until(lambda: not [r for r in table() if r[4].startswith(KEEPER) and str(tmp) in r[4]], 600, 0.2)
    if gone is None:
        fail(f'{label}: keepers of the lab still wait 600 s after the run')
    # One scan, BOUND after the last keeper: a scan of a whole run's TMPDIR takes seconds itself.
    time.sleep(BOUND)
    left = leftovers(tmp)
    if left:
        fail(f'{label}: {len(left)} sandbox directories left in TMPDIR: '
             f'{[str(p.relative_to(tmp)) for p in left][:5]}')
    else:
        ok(f'{label}: no sandbox directory left in TMPDIR, {BOUND} s after the last keeper')


MUTANT_CASE = 'ssh-append-overwrites'
LIMITED = r'''
import functools, importlib.util, subprocess, sys
spec = importlib.util.spec_from_file_location('mutants', 'tests/mutants.py')
mutants = importlib.util.module_from_spec(spec)
sys.modules['mutants'] = mutants
spec.loader.exec_module(mutants)
limit = float(sys.argv[1])
if hasattr(mutants, 'LIMIT'):
    mutants.LIMIT = limit
else:
    class Limited:
        # Only the runner's child run gets the limit; every other call is untouched.
        def __getattr__(self, name):
            return getattr(subprocess, name)
        def run(self, *args, **kwargs):
            if args and str(args[0][0]) == str(mutants.SANDBOX):
                kwargs['timeout'] = limit
            return subprocess.run(*args, **kwargs)
    mutants.subprocess = Limited()
try:
    status = mutants.main(sys.argv[2:])
except subprocess.TimeoutExpired as exc:
    print(f'timed out: {exc}')
    status = 3
sys.exit(status)
'''


def mode_mutants(lab: Path) -> None:
    tmp = lab / 'tmp'
    tmp.mkdir()
    env = {**ENV, 'TMPDIR': str(tmp)}
    case = os.environ.get('SDLK_MUTANT_CASE', MUTANT_CASE)
    for label, argv in (('within its limit', ['uv', 'run', 'python', 'tests/mutants.py', case]),
                        ('past a 1 s limit', ['uv', 'run', 'python', '-c', LIMITED, '1', case])):
        proc = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True)
        print(f'{label}: exit {proc.returncode}: {proc.stdout.strip()[-200:]}', flush=True)
        timed_out = 'timed out' in proc.stdout or 'timeout' in proc.stdout.lower()
        if label.startswith('past') and not timed_out:
            fail(f'mutants: the child run never passed its patched limit: {proc.stdout.strip()[-200:]!r}')
        if label.startswith('within') and proc.returncode != 0:
            fail(f'mutants: the case was not killed within its limit: {proc.stdout.strip()[-200:]!r}')
        settle_lab(tmp, f'mutants, {label}')


def mode_verify(lab: Path) -> None:
    tmp = lab / 'tmp'
    tmp.mkdir()
    text = (ROOT / 'AGENTS.md').read_text()
    row = re.search(r'^\| verify \| `([^`]+)`', text, re.M)
    if not row:
        fail('verify: no verify row in AGENTS.md')
        return
    start = time.monotonic()
    proc = subprocess.run(['sh', '-c', row.group(1)], cwd=ROOT, env={**ENV, 'TMPDIR': str(tmp)})
    print(f'verify: exit {proc.returncode} in {time.monotonic() - start:.0f} s', flush=True)
    if proc.returncode != 0:
        fail(f'verify: the profile\'s verify exited {proc.returncode}')
    settle_lab(tmp, 'verify')


ROWS = [
    'tests/test_sandbox_keeper.py::test_a_killed_sandbox_leaves_no_directory[group]',
    'tests/test_sandbox_keeper.py::test_a_killed_sandbox_leaves_no_directory[wrapper-then-command]',
    'tests/test_sandbox_keeper.py::test_a_killed_sandbox_leaves_no_directory[frozen-then-killed]',
    'tests/test_sandbox_keeper.py::test_a_killed_sandbox_leaves_no_directory[pipes]',
    'tests/test_sandbox_keeper.py::test_a_killed_sandbox_leaves_no_directory[background]',
    'tests/test_sandbox_keeper.py::test_an_ending_sandbox_removes_its_directory_first[exit]',
    'tests/test_sandbox_keeper.py::test_an_ending_sandbox_removes_its_directory_first[TERM]',
    'tests/test_sandbox_keeper.py::test_a_sandbox_leaves_other_directories_alone',
    'tests/test_hygiene.py',
    'tests/test_cli.py::test_sandbox_fails_closed_with_either_host_exported',
    'tests/test_transports.py',
    'tests/test_registry.py::test_a_missing_git_fails_on_ci_and_skips_elsewhere',
]
CONTROLS = 'tests/test_sandbox_keeper.py::test_keeper_violations_rejects'


def mode_rows(lab: Path) -> None:
    """The new module's rows by id, its unit controls, and the rows that pin the wrapper today."""
    collected = subprocess.run(['uv', 'run', 'pytest', '-q', '--collect-only', CONTROLS], cwd=ROOT, env=ENV,
                               capture_output=True, text=True)
    controls = [l for l in collected.stdout.splitlines() if l.startswith(CONTROLS + '[')]
    if len(controls) < 4:
        fail(f'rows: expected at least 4 planted records under {CONTROLS}, found {len(controls)}')
    proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:cacheprovider', '-rs', *ROWS, *controls],
                          cwd=ROOT, env=ENV, capture_output=True, text=True)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-400:]
    print(tail, flush=True)
    if proc.returncode != 0 or ' skipped' in tail or 'deselected' in tail:
        fail(f'rows: pytest exited {proc.returncode}: {tail}')
    else:
        ok(f'rows: {tail}')


ALLOWED = {'bin/sandbox.sh', 'AGENTS.md', 'tests/test_sandbox_keeper.py'}
SECTION = '### Throwaway environment'


def mode_files(lab: Path) -> None:
    """Only the cycle's paths change, and AGENTS.md only inside its Throwaway environment section."""
    base = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/develop'], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    changed = subprocess.run(['git', 'diff', '--cached', '--name-status', base], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    for row in changed:
        status, name = row.split('\t', 1)
        if name.startswith('spec/sandbox-dirs-left-on-kill/'):
            continue
        if name not in ALLOWED or (status != 'M' and name != 'tests/test_sandbox_keeper.py'):
            fail(f'files: {status} {name} is outside the cycle\'s paths')
    old = subprocess.run(['git', 'show', f'{base}:AGENTS.md'], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    new = subprocess.run(['git', 'show', ':AGENTS.md'], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout

    def outside(text: str) -> str:
        start = text.index(SECTION)
        end = text.index('\n### ', start + len(SECTION))
        return text[:start] + text[end:]

    if outside(old) != outside(new):
        fail('files: AGENTS.md changes outside its Throwaway environment section')
    if not failures:
        ok(f'files: {len(changed)} paths changed against {base[:7]}, all the cycle\'s')


DEFERRAL = re.compile(r'follow-up|follow up|known limitation|do not fix here|deferred to|left for a later', re.I)


def mode_ledger(lab: Path) -> None:
    """Every deferral phrase in PLAN, TECH and the branch's commit bodies names an indexed seed."""
    base = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/develop'], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    bodies = subprocess.run(['git', 'log', '--format=%b', f'{base}..HEAD'], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout
    roadmap = (ROOT / 'ROADMAP.md').read_text()
    texts = {'commit bodies': bodies}
    for name in ('PLAN.md', 'TECH.md'):
        texts[name] = (ROOT / 'spec' / 'sandbox-dirs-left-on-kill' / name).read_text()
    found = 0
    for name, text in texts.items():
        for block in re.split(r'\n\s*\n|\n(?=\s*[-*|] )', text):
            if block.lstrip().startswith('#') or not DEFERRAL.search(block):
                continue
            found += 1
            seeds = re.findall(r'issues/([a-z0-9-]+)\.md', block)
            good = [s for s in seeds if (ROOT / 'issues' / f'{s}.md').exists() and f'issues/{s}.md' in roadmap]
            if not good:
                fail(f'ledger: {name}: a deferral names no indexed seed: {block.strip()[:120]!r}')
    if not failures:
        ok(f'ledger: {found} deferral passages, each naming an indexed seed')


def mode_controls(lab: Path) -> None:
    """Develop's wrapper installed as the tree's: kill and race must find leftovers."""
    global install
    real = install
    install = lambda where, rev: real(where, rev or DEVELOP) if rev is None else real(where, rev)
    before = len(failures)
    try:
        for mode in (mode_kill, mode_race):
            sub = lab / mode.__name__
            sub.mkdir()
            mode(sub)
    finally:
        install = real
    caught = len(failures) - before
    del failures[before:]
    if caught == 0:
        fail('controls: develop\'s wrapper passed kill and race')
    else:
        ok(f'controls: develop\'s wrapper fails kill and race ({caught} findings)')


MODES = {'kill': mode_kill, 'race': mode_race, 'exit': mode_exit, 'share': mode_share,
         'decoys': mode_decoys, 'same': mode_same, 'suite': mode_suite, 'mutants': mode_mutants,
         'verify': mode_verify, 'rows': mode_rows, 'files': mode_files, 'ledger': mode_ledger,
         'controls': mode_controls}


def stragglers() -> list[tuple]:
    return [r for r in table() if TOKEN in r[4] and r[0] != os.getpid()]


def main(argv: list[str]) -> int:
    if not argv or any(m not in MODES for m in argv):
        print(f'usage: keeper.py MODE... ({", ".join(MODES)})', file=sys.stderr)
        return 2
    for mode in argv:
        lab = Path(tempfile.mkdtemp(prefix=f'sdlk-{mode}-'))
        try:
            MODES[mode](lab)
        except Exception as exc:
            fail(f'{mode}: {type(exc).__name__}: {exc}')
            traceback.print_exc()
        finally:
            for row in stragglers():
                try:
                    os.kill(row[0], signal.SIGKILL)
                except ProcessLookupError:
                    pass
            shutil.rmtree(lab, ignore_errors=True)
        if wait_until(lambda: not stragglers(), SETTLE) is None:
            fail(f'{mode}: processes carrying the gate token outlived the mode')
    print('FAILED' if failures else 'PASSED', flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
