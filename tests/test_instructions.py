# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The agent-facing instructions name exactly the registered tools and carry no documentation search.

The base is the generic core's text (`CORE_INSTRUCTIONS`), which names no site and no tool of the
RCAC member, then the text of each loaded capability, read from the capabilities themselves: the
Slurm snippet, then the overlay, labelled RCAC-specific on its first line, in composition order
(each capability's order, then its distribution). Each lists exactly the tools its member registers,
a tool's member being the `cluster_mcp.<member>` module its function was defined in, and the base
(`SERVER_INSTRUCTIONS` here, as `base_instructions` composes it) is the texts joined by a blank line
in that order, so the overlay sits directly above the site context.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pytest

from harness import SITE, served_instructions
from cluster_mcp.core.capabilities import installed
from cluster_mcp.core.instructions import CORE_INSTRUCTIONS
from cluster_mcp.core.server import base_instructions, create_mcp_server
from cluster_mcp.core.site import HEADING, compose, units
from cluster_mcp.core.tools import TOOL_REGISTRY


# Every loaded capability in composition order, read here rather than through the composer under
# test: lower order first, ties by distribution.
CAPABILITIES = tuple(sorted(installed(), key=lambda loaded: (loaded.capability.order, loaded.distribution)))

# Each member's text, as its capability carries it.
TEXTS = {loaded.capability.name: loaded.capability.instructions for loaded in CAPABILITIES}
SLURM_INSTRUCTIONS = TEXTS['slurm']
RCAC_INSTRUCTIONS = TEXTS['rcac']

# The served base, as the server composes it from every installed capability.
SERVER_INSTRUCTIONS = base_instructions(installed())


REPO_ROOT = Path(__file__).resolve().parents[1]

# Backticked or snake_case terms in the instructions that are not tools (none today). Every entry
# must occur in the text and must not be a registered tool.
NON_TOOL_TERMS: frozenset[str] = frozenset()

# Documentation-search guidance: the words doc, docs, documentation, any doc_ identifier, and
# "user guide(s)". Documentation search is served by a separate service, not by this server.
DOCS_GUIDANCE = re.compile(r'(?i)\bdoc(?:s|umentation)?\b|\bdoc_\w*|\buser[\s_-]?guides?\b')

# A tool list entry: "- name: description", lowercase snake_case followed by whitespace.
LISTED = re.compile(r'^- ([a-z_][a-z0-9_]*):(?=\s)', re.MULTILINE)
TICKED = re.compile(r'`([^`\s]+)`')
SNAKE = re.compile(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b')


def guidance_violations(text: str) -> list[str]:
    """Return every documentation-search phrase in `text`; an empty list means none."""
    return [f'documentation guidance: {m.group(0)!r}' for m in DOCS_GUIDANCE.finditer(text)]


def _occurs(term: str, text: str) -> bool:
    return re.search(rf'(?<![\w]){re.escape(term)}(?![\w])', text) is not None


def instruction_violations(text: str, names: Sequence[str],
                           allow: Iterable[str] = NON_TOOL_TERMS) -> list[str]:
    """Cross-check instruction text against registered tool names; an empty list means consistent."""
    violations: list[str] = []
    allow = frozenset(allow)
    registry = set(names)
    if not names:
        violations.append('tool registry is empty')
    if len(registry) != len(names):
        violations.append(f'tool registry has duplicate names: {sorted(names)!r}')
    listed = set(LISTED.findall(text))
    ticked = set(TICKED.findall(text))
    snake = set(SNAKE.findall(text))
    for name in sorted(registry - listed):
        violations.append(f'registered tool not listed: {name!r}')
    for name in sorted((listed | ticked | snake) - registry - allow):
        violations.append(f'unregistered name in instructions: {name!r}')
    for term in sorted(allow & registry):
        violations.append(f'allowlist names a registered tool: {term!r}')
    for term in sorted(allow):
        if not _occurs(term, text):
            violations.append(f'allowlist term absent from instructions: {term!r}')
    violations.extend(guidance_violations(text))
    return violations


def _registered() -> list[str]:
    return [tool.name for tool in TOOL_REGISTRY]


def _served_instructions() -> str:
    # The base part of what a client in the selected protocol era receives when it connects: the
    # site context after it is the site's text, which this check does not govern.
    served = served_instructions(create_mcp_server('none', site=SITE)) or ''
    assert served == compose(SERVER_INSTRUCTIONS, SITE), 'served instructions are not the composed text'
    return served.partition(f'\n\n{HEADING}\n\n')[0]


def _drop_sinfo(text: str) -> str:
    return re.sub(r'^- sinfo:.*\n', '', text, flags=re.MULTILINE)


@pytest.mark.unit
@pytest.mark.parametrize('source', [
    pytest.param(lambda: SERVER_INSTRUCTIONS, id='constant'),
    pytest.param(_served_instructions, id='served'),
])
def test_instructions_match_registry(source: Callable[[], str]) -> None:
    text = source()
    assert text, 'instructions are empty'
    assert instruction_violations(text, _registered()) == []


@pytest.mark.unit
def test_instructions_md_has_no_docs_guidance() -> None:
    text = (REPO_ROOT / 'INSTRUCTIONS.md').read_text()
    assert text.strip(), 'INSTRUCTIONS.md is empty'
    assert guidance_violations(text) == []


# Each case: (mutated text, extra allowlist terms, the violation the mutation must produce).
MUTATIONS = [
    pytest.param(SERVER_INSTRUCTIONS + '\n- doc_search: Search RCAC documentation\n', (),
                 "unregistered name in instructions: 'doc_search'", id='doc-entry'),
    pytest.param(SERVER_INSTRUCTIONS + '\n- job_magic: Run a job\n', (),
                 "unregistered name in instructions: 'job_magic'", id='unknown-entry'),
    pytest.param(_drop_sinfo(SERVER_INSTRUCTIONS), (),
                 "registered tool not listed: 'sinfo'", id='missing-entry'),
    pytest.param(SERVER_INSTRUCTIONS + '\nBefore answering, call `doc_search` first.\n', (),
                 "unregistered name in instructions: 'doc_search'", id='ticked-doc'),
    pytest.param(SERVER_INSTRUCTIONS + '\nThen call slurm_magic to finish.\n', (),
                 "unregistered name in instructions: 'slurm_magic'", id='unknown-snake'),
    pytest.param(SERVER_INSTRUCTIONS, ('myquota',),
                 "allowlist names a registered tool: 'myquota'", id='allowlist-launder'),
    pytest.param(SERVER_INSTRUCTIONS, ('qstat_legacy',),
                 "allowlist term absent from instructions: 'qstat_legacy'", id='allowlist-stale'),
    pytest.param(SERVER_INSTRUCTIONS + '\nBefore answering, search the RCAC user guides.\n', (),
                 "documentation guidance: 'user guides'", id='user-guides'),
    pytest.param(SERVER_INSTRUCTIONS + '\nWhen unsure, see the docs.\n', (),
                 "documentation guidance: 'docs'", id='docs-word'),
]


@pytest.mark.unit
@pytest.mark.parametrize('text, extra_allow, expected', MUTATIONS)
def test_cross_check_catches_mutation(text: str, extra_allow: tuple[str, ...], expected: str) -> None:
    names = _registered()
    assert text != SERVER_INSTRUCTIONS or extra_allow, 'the mutation changed nothing'
    assert instruction_violations(SERVER_INSTRUCTIONS, names) == []
    violations = instruction_violations(text, names, NON_TOOL_TERMS | set(extra_allow))
    assert expected in violations, violations


@pytest.mark.unit
def test_base_leaves_room_for_the_site() -> None:
    # The base is never cut; at the default budget it must leave room for a site file and the note.
    assert units(SERVER_INSTRUCTIONS) <= 1500, units(SERVER_INSTRUCTIONS)


# The members that register tools, each owning one text of the base: the core and every loaded
# capability.
MEMBERS = ('core', *(loaded.capability.name for loaded in CAPABILITIES))

# Words that name a site; the generic core carries none of them, in any case.
SITE_NAMES = re.compile(r'(?i)rcac|purdue')

# The overlay's first line, which labels everything under it RCAC-specific.
OVERLAY_LABEL = 'RCAC-specific tools:'


def tools_by_member() -> dict[str, set[str]]:
    """Each registered tool's name under its member: the `cluster_mcp.<member>` module defining it."""
    by: dict[str, set[str]] = {}
    for tool in TOOL_REGISTRY:
        module = getattr(tool.fn, '__module__', '') or ''
        match = re.fullmatch(r'cluster_mcp\.(\w+)(?:\..+)?', module)
        by.setdefault(match.group(1) if match else f'outside cluster_mcp ({module})', set()).add(tool.name)
    return by


def listing_violations(text: str, names: set[str]) -> list[str]:
    """Every way `text` fails to list exactly `names`, each once; an empty list means it does."""
    if not names:
        return ['the member registers no tool']
    listed = LISTED.findall(text)
    violations = [f'registered by the member, not listed: {name!r}' for name in sorted(names - set(listed))]
    violations += [f'listed, not registered by the member: {name!r}' for name in sorted(set(listed) - names)]
    violations += [f'listed twice: {name!r}' for name in sorted({n for n in listed if listed.count(n) > 1})]
    return violations


def core_violations(text: str, rcac_tools: set[str]) -> list[str]:
    """Every site the core text names, and every tool of the RCAC member it names; empty means generic."""
    violations = [f'the core names a site: {m.group(0)!r}' for m in SITE_NAMES.finditer(text)]
    violations += [f'the core names the RCAC tool {name!r}' for name in sorted(rcac_tools) if _occurs(name, text)]
    return violations


def base_violations(base: str, served: str) -> list[str]:
    """Every way `base` is not core, Slurm then overlay, or `served` does not open with it, uncut, above the site.

    The expected base is the core's text, then each loaded capability's in composition order, its
    last text the overlay.
    """
    violations = []
    texts = [loaded.capability.instructions for loaded in CAPABILITIES]
    if not texts or texts[-1].splitlines()[0] != OVERLAY_LABEL:
        violations.append('the last capability in composition order is not the overlay')
    if base != '\n\n'.join((CORE_INSTRUCTIONS, *texts)):
        violations.append('the base is not core, Slurm then overlay, joined by a blank line')
    if not served.startswith(f'{base}\n\n{HEADING}\n\n'):
        violations.append('the served instructions do not open with the whole base directly above the site context')
    return violations


@pytest.mark.unit
def test_every_tool_belongs_to_a_member() -> None:
    by = tools_by_member()
    assert sorted(by) == sorted(MEMBERS), sorted(by)


@pytest.mark.unit
def test_core_instructions_are_generic() -> None:
    by = tools_by_member()
    violations = core_violations(CORE_INSTRUCTIONS, by.get('rcac', set()))
    violations += listing_violations(CORE_INSTRUCTIONS, by.get('core', set()))
    assert violations == [], violations


@pytest.mark.unit
def test_overlay_is_labelled_and_lists_the_rcac_member() -> None:
    first = RCAC_INSTRUCTIONS.splitlines()[0]
    assert first == OVERLAY_LABEL, f'the overlay opens {first!r}, not {OVERLAY_LABEL!r}'
    violations = listing_violations(RCAC_INSTRUCTIONS, tools_by_member().get('rcac', set()))
    assert violations == [], violations


@pytest.mark.unit
def test_slurm_snippet_lists_the_slurm_member() -> None:
    violations = listing_violations(SLURM_INSTRUCTIONS, tools_by_member().get('slurm', set()))
    assert violations == [], violations


@pytest.mark.unit
def test_base_is_core_slurm_then_overlay() -> None:
    served = served_instructions(create_mcp_server('none', site=SITE)) or ''
    violations = base_violations(SERVER_INSTRUCTIONS, served)
    assert violations == [], violations


@pytest.mark.unit
@pytest.mark.parametrize(('check', 'fragment'), [
    pytest.param(lambda: core_violations(CORE_INSTRUCTIONS + '\nOn RCAC clusters, ask first.', set()),
                 "the core names a site: 'RCAC'", id='core-names-rcac'),
    pytest.param(lambda: core_violations(CORE_INSTRUCTIONS + '\nSee Purdue policy.', set()),
                 "the core names a site: 'Purdue'", id='core-names-purdue'),
    pytest.param(lambda: core_violations(CORE_INSTRUCTIONS + '\nTry myquota.', {'myquota'}),
                 "the core names the RCAC tool 'myquota'", id='core-names-rcac-tool'),
    pytest.param(lambda: listing_violations(_drop_sinfo(SLURM_INSTRUCTIONS + '\n'), {'sinfo', 'sbatch'}),
                 "registered by the member, not listed: 'sinfo'", id='member-tool-unlisted'),
    pytest.param(lambda: listing_violations(SLURM_INSTRUCTIONS, {'sbatch'}),
                 "listed, not registered by the member: 'squeue'", id='other-member-listed'),
    pytest.param(lambda: listing_violations(SLURM_INSTRUCTIONS + '\n- sbatch: again', {'sbatch'}),
                 "listed twice: 'sbatch'", id='listed-twice'),
    pytest.param(lambda: listing_violations(SLURM_INSTRUCTIONS, set()),
                 'the member registers no tool', id='empty-member'),
    pytest.param(lambda: base_violations('\n\n'.join((CORE_INSTRUCTIONS, SLURM_INSTRUCTIONS)),
                                         f'{CORE_INSTRUCTIONS}\n\n{SLURM_INSTRUCTIONS}\n\n{HEADING}\n\n'),
                 'not core, Slurm then overlay', id='overlay-dropped'),
    pytest.param(lambda: base_violations('\n\n'.join((CORE_INSTRUCTIONS, RCAC_INSTRUCTIONS, SLURM_INSTRUCTIONS)),
                                         f'{CORE_INSTRUCTIONS}\n\n{RCAC_INSTRUCTIONS}\n\n{SLURM_INSTRUCTIONS}\n\n{HEADING}\n\n'),
                 'not core, Slurm then overlay', id='overlay-not-last'),
    pytest.param(lambda: base_violations(SERVER_INSTRUCTIONS, f'{SERVER_INSTRUCTIONS[:-10]}\n\n{HEADING}\n\n'),
                 'do not open with the whole base', id='base-cut'),
])
def test_member_text_checks_catch_drift(check: Callable[[], list[str]], fragment: str) -> None:
    violations = check()
    assert any(fragment in v for v in violations), violations
