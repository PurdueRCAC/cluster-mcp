# Draft: the check and its rows as the plan dry-ran them, inserted into tests/test_hygiene.py after
# test_unit_guard_redirects_home (with `import tomllib`). Build writes the real code from it; the
# mutant sweep (../marker_mutants.py) keys its substitutions to this text, and gate.sh `wording`
# runs marker_statement_violations from here on the staged files. Not collected by any suite.


# The markers' meaning, as AGENTS.md § Testing and § Conventions each state it: a line reading exactly
# MARKERS_STATED (indentation aside), then one item per marker, `- `<name>`: <description>`, at that
# line's indentation, its wrapped lines two spaces deeper. A wrap is the only freedom the statement
# has: joined at each line break by one space, the items say word for word, in the same order, what
# the `markers` entries of pyproject.toml say. Case, punctuation, markup and spacing all count. The
# statement ends at the section's end, at a list item less indented than its own, or at a blank line
# followed by text no deeper than its items that starts no item there: anything else would render as
# part of the last description, or as another marker.
MARKERS_STATED = 'Each marker means what its description in `pyproject.toml` says, word for word:'
MARKER_ITEM = re.compile(r'- `([^`]*)`: (.*)')
LIST_ITEM = re.compile(r'(?:[-*+]|[0-9]+[.)])(?: |$)')


def described_markers(pyproject: str) -> list[tuple[str, str]]:
    """Each entry of pyproject.toml's pytest `markers`, split at its first `: ` into name and description."""
    entries = tomllib.loads(pyproject).get('tool', {}).get('pytest', {}).get('ini_options', {}).get('markers', [])
    return [(entry.split(': ', 1)[0], entry.split(': ', 1)[1]) if ': ' in entry else (entry, '') for entry in entries]


def stated_markers(section: str) -> tuple[list[tuple[str, str]], list[str]]:
    """The markers `section` states after its MARKERS_STATED line, and what keeps it from stating them."""
    lines = section.split('\n')
    at = [n for n, line in enumerate(lines) if line.lstrip(' ') == MARKERS_STATED]
    if len(at) != 1:
        return [], [f'{len(at)} lines read {MARKERS_STATED!r}, not one']
    indent = ' ' * (len(lines[at[0]]) - len(MARKERS_STATED))
    items: list[list[str]] = []
    rest = lines[at[0] + 1:]
    end = len(rest)
    for n, line in enumerate(rest):
        if line.startswith(indent + '- '):
            item = MARKER_ITEM.fullmatch(line[len(indent):])
            if item is None:
                return [], [f'not a `- `<name>`: <description>` item: {line.strip()!r}']
            items.append([item[1], item[2]])
        elif items and line.startswith(indent + '  ') and line[len(indent) + 2:][:1] not in ('', ' '):
            items[-1][1] += ' ' + line[len(indent) + 2:]
        else:
            end = n
            break
    return [(name, text) for name, text in items], statement_end_problems(rest[end:], indent)


def statement_end_problems(after: list[str], indent: str) -> list[str]:
    """Why the lines after a statement would render as part of it: a lazy continuation of its last
    item, a paragraph inside it, or a further item."""
    if not after or not after[0].strip():
        following = next((line for line in after if line.strip()), None)
        if following is None:
            return []
        depth = len(following) - len(following.lstrip())
        if depth < len(indent) or (depth == len(indent) and not LIST_ITEM.match(following.lstrip())):
            return []
        return [f'a line after a blank one joins the statement: {following.strip()!r}']
    depth = len(after[0]) - len(after[0].lstrip())
    if depth < len(indent) and LIST_ITEM.match(after[0].lstrip()):
        return []
    return [f'a line after the statement continues it: {after[0].strip()!r}']


def agents_section(agents: str, heading: str) -> str:
    """The AGENTS.md section under `heading`, up to the next heading of its level or higher."""
    start = agents.index(f'\n{heading}\n')
    level = heading.split(' ', 1)[0]
    ends = [agents.find(f'\n{"#" * n} ', start + 1) for n in range(1, len(level) + 1)]
    return agents[start:min([e for e in ends if e != -1], default=len(agents))]


def marker_statement_violations(pyproject: str, agents: str) -> list[str]:
    """Where AGENTS.md § Testing or § Conventions does not state the markers as pyproject.toml describes them."""
    described = described_markers(pyproject)
    violations = [] if described else ['pyproject.toml describes no markers']
    for where, heading in (('§ Testing', '## Testing'), ('§ Conventions', '### Conventions (same-commit rules)')):
        stated, problems = stated_markers(agents_section(agents, heading))
        violations += [f'{where}: {problem}' for problem in problems]
        for n in range(max(len(stated), len(described))):
            said = stated[n] if n < len(stated) else None
            meant = described[n] if n < len(described) else None
            if said != meant:
                violations.append(f'{where}, marker {n + 1}: states {said!r}; pyproject.toml describes {meant!r}')
    return violations


@pytest.mark.unit
def test_the_markers_are_stated_as_pyproject_describes_them() -> None:
    root = Path(__file__).resolve().parent.parent
    violations = marker_statement_violations((root / 'pyproject.toml').read_text(), (root / 'AGENTS.md').read_text())
    assert violations == [], 'AGENTS.md does not state the markers as pyproject.toml describes them:\n' + '\n'.join(violations)


# A small pyproject.toml and AGENTS.md in the shapes the check reads, for the planted rows below.
PLANTED_ALPHA = 'alpha: Opens no door (a window included), reads no x/y.sh; the guard holds it to that'
PLANTED_OMEGA = 'omega: needs what alpha is refused, itself or through a helper; every one goes through bin/x.sh'
PLANTED_BLOCK = (
    '  Each marker means what its description in `pyproject.toml` says, word for word:\n'
    '  - `alpha`: Opens no door (a window included), reads no x/y.sh; the guard holds\n'
    '    it to that\n'
    '  - `omega`: needs what alpha is refused, itself or through a helper; every one goes\n'
    '    through bin/x.sh\n')


def planted(pyproject: str = '', testing: str = '', conventions: str = '') -> tuple[str, str]:
    """The planted pair, after each `old=>new` replacement given for a place (each must apply once)."""
    def edit(text: str, change: str) -> str:
        for one in filter(None, change.split('||')):
            old, new = one.split('=>')
            assert text.count(old) == 1, (old, text)
            text = text.replace(old, new)
        return text
    toml = edit(f'[tool.pytest.ini_options]\nmarkers = [\n    "{PLANTED_ALPHA}",\n    "{PLANTED_OMEGA}",\n]\n', pyproject)
    agents = ('# AGENTS.md\n\n## Testing\n\n- The markers are real.\n' + edit(PLANTED_BLOCK, testing)
              + '- The next bullet.\n\n## Packaging\n\n- Built.\n\n## Invariants\n\n'
              '### Conventions (same-commit rules)\n\n- Tag every test.\n' + edit(PLANTED_BLOCK, conventions)
              + '- The next bullet.\n\n## After\n\n' + PLANTED_BLOCK)
    return toml, agents


@pytest.mark.unit
@pytest.mark.parametrize('change', [
    pytest.param({}, id='as-planted'),
    pytest.param({'testing': ' holds\n    it to that=> holds it to that||every one goes\n    through=>every\n    one goes through'},
                 id='rewrapped'),
    pytest.param({'conventions': 'holds\n    it=>holds it||goes\n    through=>goes through'}, id='unwrapped'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n\n  A paragraph of the bullet.\n'},
                 id='paragraph-after-a-blank'),
])
def test_marker_statement_check_accepts_a_rewrapped_statement(change: dict[str, str]) -> None:
    assert marker_statement_violations(*planted(**change)) == []


# Each row is a drift the check must refuse, and each is the one that refuses a check carrying a
# carve-out it could grow: ignoring a section, a statement, an order, a repeat, a third marker, case,
# punctuation, markup, spacing beyond a wrap, or a clause at the start, the middle or the end.
@pytest.mark.unit
@pytest.mark.parametrize('change', [
    pytest.param({'pyproject': 'no door=>no gate'}, id='changed-in-pyproject'),
    pytest.param({'testing': 'no door=>no gate'}, id='changed-in-testing'),
    pytest.param({'conventions': 'no door=>no gate'}, id='changed-in-conventions'),
    pytest.param({'testing': PLANTED_BLOCK + '=>'}, id='missing-from-testing'),
    pytest.param({'conventions': PLANTED_BLOCK + '=>'}, id='missing-from-conventions'),
    pytest.param({'pyproject': f'    "{PLANTED_ALPHA}",\n    "{PLANTED_OMEGA}",\n=>'}, id='missing-from-pyproject'),
    pytest.param({'testing': '  - `omega`: needs what alpha is refused, itself or through a helper; every one goes\n'
                             '    through bin/x.sh\n=>'}, id='one-missing-from-testing'),
    pytest.param({'pyproject': f'    "{PLANTED_OMEGA}",\n=>'}, id='one-missing-from-pyproject'),
    pytest.param({'testing': '- `alpha`=>- `alpha `'}, id='name-changed-in-testing'),
    pytest.param({'testing': '  - `alpha`: Opens no door (a window included), reads no x/y.sh; the guard holds\n'
                             '    it to that\n  - `omega`: needs what alpha is refused, itself or through a helper; every one goes\n'
                             '    through bin/x.sh\n=>'}, id='statement-without-items'),
    pytest.param({'testing': 'word for word:=>word for word, mostly:'}, id='statement-line-reworded'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n\n' + PLANTED_BLOCK.replace('no door', 'no gate')},
                 id='stated-twice'),
    pytest.param({'pyproject': '\n]\n=>\n    "beta: a third",\n]\n'}, id='third-marker-in-pyproject'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n  - `beta`: a third\n'}, id='third-marker-in-testing'),
    pytest.param({'pyproject': f'\n]\n=>\n    "{PLANTED_ALPHA}",\n]\n'}, id='repeated-in-pyproject'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n' + PLANTED_BLOCK.split('\n', 1)[1].split('  - `omega`')[0]},
                 id='repeated-in-testing'),
    pytest.param({'testing': '  - `alpha`: Opens no door (a window included), reads no x/y.sh; the guard holds\n'
                             '    it to that\n=>||through bin/x.sh\n=>through bin/x.sh\n'
                             '  - `alpha`: Opens no door (a window included), reads no x/y.sh; the guard holds\n'
                             '    it to that\n'}, id='reordered-in-testing'),
    pytest.param({'pyproject': 'alpha: Opens=>alpha: Except for a gate Opens'}, id='clause-at-start-in-pyproject'),
    pytest.param({'testing': '`alpha`: Opens=>`alpha`: Except for a gate Opens'}, id='clause-at-start-in-testing'),
    pytest.param({'pyproject': 'no door (a=>no door except a gate (a'}, id='clause-in-middle-in-pyproject'),
    pytest.param({'testing': 'no door (a=>no door except a gate (a'}, id='clause-in-middle-in-testing'),
    pytest.param({'pyproject': 'goes through bin/x.sh=>goes through bin/x.sh except a gate'}, id='clause-at-end-in-pyproject'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh except a gate\n'}, id='clause-at-end-in-testing'),
    pytest.param({'pyproject': 'alpha: Opens=>alpha: opens'}, id='case-in-pyproject'),
    pytest.param({'testing': '`alpha`: Opens=>`alpha`: opens'}, id='case-in-testing'),
    pytest.param({'pyproject': 'included), reads=>included) reads'}, id='punctuation-in-pyproject'),
    pytest.param({'testing': 'x/y.sh; the=>x/y.sh, the'}, id='punctuation-in-testing'),
    pytest.param({'pyproject': 'no door=>no  door'}, id='double-space-in-pyproject'),
    pytest.param({'testing': 'no door=>no  door'}, id='double-space-in-testing'),
    pytest.param({'pyproject': 'alpha: Opens=>alpha:Opens'}, id='no-space-after-name-in-pyproject'),
    pytest.param({'testing': '`alpha`: Opens=>`alpha`:  Opens'}, id='two-spaces-after-name-in-testing'),
    pytest.param({'pyproject': 'holds it to that=>holds it to that '}, id='trailing-space-in-pyproject'),
    pytest.param({'testing': 'the guard holds\n=>the guard holds \n'}, id='trailing-space-at-wrap-in-testing'),
    pytest.param({'testing': '\n    it to that=>\n     it to that'}, id='over-indented-wrap-in-testing'),
    pytest.param({'testing': 'no door=>no\tdoor'}, id='tab-in-testing'),
    pytest.param({'testing': 'through bin/x.sh\n=>through `bin/x.sh`\n'}, id='markup-in-testing'),
    pytest.param({'testing': '- `alpha`:=>- alpha:'}, id='item-without-backticks-in-testing'),
    pytest.param({'testing': '  - `omega`=>    - `omega`'}, id='item-over-indented-in-testing'),
    pytest.param({'testing': 'no door=>no\u00a0door'}, id='no-break-space-in-testing'),
    pytest.param({'testing': 'Opens no door=>Opens **no** door'}, id='emphasis-in-testing'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\nexcept a gate\n'}, id='clause-lazy-after-last-item'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n  except a gate\n'},
                 id='clause-at-item-indent-after-last-item'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n        except a gate\n'},
                 id='clause-over-indented-after-last-item'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n\n    except a gate\n'},
                 id='clause-after-a-blank-in-last-item'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n\n  - `beta`: a third\n'},
                 id='third-marker-after-a-blank-in-testing'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh\n  * `beta`: a third\n'},
                 id='third-marker-other-bullet-in-testing'),
    pytest.param({'testing': '- `alpha`=>- `Alpha`'}, id='name-case-in-testing'),
    pytest.param({'testing': 'through bin/x.sh\n=>through bin/x.sh.\n'}, id='trailing-period-in-testing'),
    pytest.param({'testing': 'word for word:\n=>word for word: \n'}, id='statement-line-trailing-space-in-testing'),
    pytest.param({'testing': '  Each marker=>\tEach marker'}, id='statement-line-tab-indented-in-testing'),
    pytest.param({'pyproject': 'no door=>no caf\u00e9 door', 'testing': 'no door=>no cafe\u0301 door',
                  'conventions': 'no door=>no caf\u00e9 door'},
                 id='decomposed-in-testing'),
])
def test_marker_statement_check_catches_planted_drift(change: dict[str, str]) -> None:
    assert marker_statement_violations(*planted(**change)) != []
