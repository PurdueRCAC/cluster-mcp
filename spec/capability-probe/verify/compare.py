# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Compare two surfaces surface.py wrote: BASE (today's) and HEAD. Usage: compare.py BASE.json HEAD.json

Everything surface.py records must be equal: the server name; the instructions, byte for byte; the
three instruction texts, each as its module holds it; every tool and every resource, whole (every
field the wire carries); the order in which tools and resources are listed; the resource templates,
the prompts and the server capabilities. Each difference is named. Footprint: one process, no
network, under 100 MB.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

KEYS = ('server_name', 'instructions', 'texts', 'tools', 'resources', 'resource_templates', 'prompts',
        'capabilities')


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit('usage: compare.py BASE.json HEAD.json')
    base, head = (json.load(open(p)) for p in sys.argv[1:])
    bad: list[str] = []
    if not base.get('tools') or not base.get('resources') or not base.get('instructions'):
        sys.exit('compare: the base lists no tools, resources or instructions: the comparison would be blind')
    for key in KEYS:
        if key not in base or key not in head:
            bad.append(f'{key}: missing from {"base" if key not in base else "head"}')
    for what, field in (('tools', 'name'), ('resources', 'uri')):
        b, h = base.get(what, []), head.get(what, [])
        for name, n in Counter(i[field] for i in h).items():
            if n > 1:
                bad.append(f'head lists {what[:-1]} {name!r} {n} times')
        bi, hi = {i[field]: i for i in b}, {i[field]: i for i in h}
        for name in sorted(bi.keys() - hi.keys()):
            bad.append(f'{what[:-1]} lost: {name}')
        for name in sorted(hi.keys() - bi.keys()):
            bad.append(f'{what[:-1]} added: {name}')
        for name in sorted(bi.keys() & hi.keys()):
            if bi[name] != hi[name]:
                fields = sorted(k for k in set(bi[name]) | set(hi[name]) if bi[name].get(k) != hi[name].get(k))
                bad.append(f'{what[:-1]} {name}: differs in {fields}')
        if [i[field] for i in b] != [i[field] for i in h] and set(bi) == set(hi):
            bad.append(f'{what} listed in another order:\n  today {[i[field] for i in b]}\n  head  {[i[field] for i in h]}')
    for key in ('server_name', 'instructions', 'resource_templates', 'prompts', 'capabilities'):
        if base.get(key) != head.get(key):
            bad.append(f'{key} differs from today\'s')
    for name, text in (base.get('texts') or {}).items():
        if (head.get('texts') or {}).get(name) != text:
            bad.append(f'{name} differs from today\'s (the split between the texts moved)')
    print(*bad, sep='\n', file=sys.stderr)
    if not bad:
        print(f"compare: ok ({len(head['tools'])} tools, {len(head['resources'])} resources, "
              f"{len(head['instructions'])} characters of instructions)", file=sys.stderr)
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
