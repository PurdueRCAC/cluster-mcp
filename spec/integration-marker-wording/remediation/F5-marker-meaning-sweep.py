"""Review cycle 2, finding 1: every place in AGENTS.md that says what a marker means, or what an
`integration` or `unit` test is or does in general, says it in pyproject.toml's terms.

Found by a search over the whole file, not a list of places: every sentence whose subject is the
tests of a marker in general ("integration tests", "an `integration` test", "a unit test", with or
without backticks, after "a", "an", "every", "each", "all" or nothing) is read. Sentences about one
module's rows or cases ("the `integration` rows", "`integration` cases") name no test in general and
are not read. A read sentence fails when it says an integration test drives the CLI (or drives no
CLI by exception), or calls a unit test fast. The search must find the sentences R4 names: the
statement's two lines in § Testing and § Conventions, and the commands block's per-launch rule.

Run from the worktree root, after staging, through remediation/checks.sh (or alone):

    uv run --no-sync python -I spec/integration-marker-wording/remediation/F5-marker-meaning-sweep.py

Reads the index. Prints each sentence read and exits 1 on any that fails. One process; under 50 MB.
"""
from __future__ import annotations

import re
import subprocess
import sys


def staged(name: str) -> str:
    return subprocess.run(['git', 'show', f':{name}'], capture_output=True, text=True, check=True).stdout


GENERAL = re.compile(r'(?i)(?:^|(?<=\s))(?:(?:an?|every|each|all)\s+)?`?(integration|unit)`?\s+tests?\b')
CLI = re.compile(r'(?i)\bdrives?\b[^.]*\bCLI\b|\bdrives? no CLI\b|\bdrive(?:s)? (?:the|a) CLI\b')
FAST = re.compile(r'(?i)\bfast\b')
# The sentences R4 names, which the search must reach.
MUST = ('a unit test is refused (a process, a network connection or name lookup, or the real HOME)',
        'every process an integration test launches goes through bin/sandbox.sh')


def prose(text: str) -> str:
    """The file with each fenced block's code dropped and its shell comments kept as prose, a heading
    its own paragraph."""
    out, fenced = [], False
    for line in text.splitlines():
        if line.startswith('```'):
            fenced = not fenced
            out.append('')
        elif fenced:
            out.append(line.split('#', 1)[1] if '#' in line else '')
        else:
            out += ['', line, ''] if line.startswith('#') else [line]
    return '\n'.join(out)


def sentences(text: str) -> list[str]:
    """The file's sentences: paragraphs and list items flattened, split after a full stop or semicolon."""
    blocks = re.split(r'\n\s*\n|\n(?=\s*(?:[-*+]|\d+\.) )', prose(text))
    flat = [' '.join(line.strip() for line in block.splitlines()) for block in blocks]
    return [s.strip() for block in flat for s in re.split(r'(?<=[.;])\s+(?=[A-Z`(*-])', block) if s.strip()]


def main() -> int:
    agents = staged('AGENTS.md')
    read = [s for s in sentences(agents) if GENERAL.search(s)]
    bad = []
    for sentence in read:
        kinds = {m.lower() for m in GENERAL.findall(sentence)}
        if 'integration' in kinds and CLI.search(sentence):
            bad.append(f'defines an integration test by the CLI: {sentence!r}')
        if 'unit' in kinds and FAST.search(sentence):
            bad.append(f'calls a unit test fast: {sentence!r}')
    missing = [m for m in MUST if not any(m in s for s in read)]
    if missing:
        bad.append(f'the search did not reach: {missing}')
    for sentence in read:
        print(f'read: {sentence[:150]}{"…" if len(sentence) > 150 else ""}')
    for line in bad:
        print(line)
    print(f'F5: {len(read)} sentences read; {"ok" if not bad else f"{len(bad)} failed"}')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
