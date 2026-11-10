# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""A stand-in for `hdiutil`, played by a Python script, for the disk-image fixture's rows.

    python -I hdiutil_standin.py STATE VERB ARGS...

It makes no disk image and attaches nothing: it keeps what `hdiutil` would have made in the
directory `STATE`, and it forks, never launching a program. It runs only through `bin/sandbox.sh`
(its working directory is the sandbox the script made), and refuses to run otherwise.

`STATE/plan.json` maps each verb to a list of plans, one per call of that verb, in order; a call past
the end of its list is a plain success. A plan's keys, each optional:

- `image`: write the image file (the last argument) first;
- `device`: record a device made from the image (the last argument) first, mounted at the
  `-mountpoint` argument when there is one;
- `child`: then fork a child that runs until it is killed;
- `garbled`: answer with text that is not a listing;
- `end`: `ok` (the default: do what `hdiutil` does), `fail` (exit 1 with `hdiutil`'s failure line
  last on standard error), or `hang` (run until killed).

What the plan does before its ending is the same for every verb. A process that hangs, the child
included, keeps running through TERM and records it; a child drops its standard streams, so the
step's own exit is seen while the child runs. Every process it runs appends `PID KIND VERB END` to
`STATE/pids` (`KIND` is `step` or `child`), and keeps the argv it was started with, `STATE` in it.

`STATE/devices.json` lists the devices: each a whole device (`dev-entry`), the image it was made
from (`image-path`) and its mount point (`mount-point`, or null). `info -plist` answers with a
listing shaped as `hdiutil`'s, each image named by a path with `/./` in it (equal to the image's path
by `realpath`, not by string), its whole device and one slice, the slice carrying the mount point.
`detach` takes a whole device or a mount point, as `hdiutil` does, and fails on anything else.
"""

from __future__ import annotations

import json
import os
import plistlib
import signal
import sys
import time
from pathlib import Path
from typing import Any, NoReturn

DEPRECATED = "'hdiutil {verb}' is deprecated. Please use 'diskutil image {verb}' instead."


def record(state: Path, line: str) -> None:
    """Append one line to `STATE/pids`."""
    with open(state / 'pids', 'a') as pids:
        pids.write(line + '\n')


def calls(state: Path, verb: str) -> int:
    """How many times `verb` has run before this call."""
    pids = state / 'pids'
    lines = pids.read_text().splitlines() if pids.exists() else []
    return sum(1 for line in lines if line.split()[1:3] == ['step', verb])


def devices(state: Path) -> list[dict[str, Any]]:
    """The devices recorded in `STATE/devices.json`."""
    path = state / 'devices.json'
    return json.loads(path.read_text()) if path.exists() else []


def keep(state: Path, listed: list[dict[str, Any]]) -> None:
    """Write the device list back."""
    (state / 'devices.json').write_text(json.dumps(listed, indent=1))


def option(args: list[str], name: str) -> str | None:
    """The value after `name` in `args`, if it is there."""
    return args[args.index(name) + 1] if name in args[:-1] else None


def make_device(state: Path, image: str, mount_point: str | None) -> None:
    """Record a device made from `image`, numbered after every device recorded."""
    listed = devices(state)
    number = 1 + max((int(d['dev-entry'].removeprefix('/dev/standin')) for d in listed), default=0)
    listed.append({'dev-entry': f'/dev/standin{number}', 'image-path': image, 'mount-point': mount_point})
    keep(state, listed)


def run_forever(state: Path) -> NoReturn:
    """Run until killed; a TERM is recorded and outlived."""
    signal.signal(signal.SIGTERM, lambda signum, frame: record(state, f'term {os.getpid()}'))
    while True:
        time.sleep(60)


def fork_child(state: Path, verb: str, end: str) -> None:
    """Fork a child that drops its standard streams and runs until killed; record it."""
    pid = os.fork()
    if pid == 0:
        null = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(null, fd)
        run_forever(state)
    record(state, f'{pid} child {verb} {end}')


def fail(verb: str, why: str) -> NoReturn:
    """Exit as `hdiutil` does on a failure: the deprecation warning first, the failure line last."""
    sys.stderr.write(DEPRECATED.format(verb=verb) + '\n' + f'hdiutil: {verb} failed - {why}\n')
    sys.exit(1)


def listing(state: Path) -> bytes:
    """`hdiutil info -plist`'s answer for the recorded devices."""
    images = []
    for device in devices(state):
        image = Path(device['image-path'])
        entities: list[dict[str, Any]] = [{'dev-entry': device['dev-entry']}, {'dev-entry': device['dev-entry'] + 's1'}]
        if device['mount-point'] is not None:
            entities[1]['mount-point'] = device['mount-point']
        images.append({'image-path': f'{image.parent}/./{image.name}', 'system-entities': entities})
    return plistlib.dumps({'framework': 'stand-in', 'images': images})


def succeed(state: Path, verb: str, args: list[str]) -> None:
    """Do what `hdiutil` does for `verb`, or fail as it fails."""
    if verb == 'create':
        Path(args[-1]).write_bytes(b'stand-in image\n')
    elif verb == 'attach':
        if not Path(args[-1]).exists():
            fail(verb, 'No such file or directory')
        make_device(state, args[-1], option(args, '-mountpoint'))
    elif verb == 'detach':
        listed = devices(state)
        kept = [d for d in listed if args[-1] not in (d['dev-entry'], d['mount-point'])]
        if len(kept) == len(listed):
            fail(verb, 'No such file or directory')
        keep(state, kept)
        print(f'"{args[-1]}" ejected.')
    elif verb == 'info':
        sys.stdout.buffer.write(listing(state))
    else:
        fail(verb, f'unknown verb {verb!r}')


def main(argv: list[str]) -> None:
    state, verb, args = Path(argv[0]), argv[1], argv[2:]
    sandbox = os.environ.get('CLUSTER_MCP_SANDBOX')
    if not sandbox or os.path.realpath(os.getcwd()) != os.path.realpath(sandbox):
        sys.stderr.write('hdiutil stand-in: not run through bin/sandbox.sh\n')
        sys.exit(2)
    plans = json.loads((state / 'plan.json').read_text()).get(verb, [])
    n = calls(state, verb)
    plan = plans[n] if n < len(plans) else {}
    end = plan.get('end', 'ok')
    record(state, f'{os.getpid()} step {verb} {end}')
    sys.stderr.write(DEPRECATED.format(verb=verb) + '\n')
    sys.stderr.flush()
    if plan.get('image'):
        Path(args[-1]).write_bytes(b'stand-in image\n')
    if plan.get('device'):
        make_device(state, args[-1], option(args, '-mountpoint'))
    if plan.get('child'):
        fork_child(state, verb, end)
    if end == 'hang':
        run_forever(state)
    if end == 'fail':
        fail(verb, 'stand-in failure')
    if plan.get('garbled'):
        print('this is not a listing')
        return
    succeed(state, verb, args)


if __name__ == '__main__':
    main(sys.argv[1:])
