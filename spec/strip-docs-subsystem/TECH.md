---
slug: strip-docs-subsystem
title: Remove the documentation search subsystem
kind: refactor
appetite: big
status: done
branch: refactor/strip-docs-subsystem
base: develop
current_phase: done
last_updated: '2026-10-16'
phases:
- id: P1
  name: Remove the documentation tools and every agent- and human-facing mention of
    them, behind an instructions-registry cross-check
  status: done
  satisfies:
  - R1
  - R4
  - R5
  - R6
  depends_on: []
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run pytest -q && bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run
    pytest -q -rA -m unit tests/test_registry.py tests/test_instructions.py > "$HOME/out";
    s=$?; cat "$HOME/out" >&2; test $s -eq 0 && for t in "test_registry.py::test_registry_matches_expected_tools"
    "test_registry.py::test_served_tools_match_registry" "test_registry.py::test_registry_check_catches_drift[added-doc]"
    "test_registry.py::test_registry_check_catches_drift[missing]" "test_registry.py::test_registry_check_catches_drift[duplicate]"
    "test_instructions.py::test_instructions_match_registry[constant]" "test_instructions.py::test_instructions_match_registry[served]"
    "test_instructions.py::test_instructions_md_has_no_docs_guidance" "test_instructions.py::test_cross_check_catches_mutation[doc-entry]"
    "test_instructions.py::test_cross_check_catches_mutation[unknown-entry]" "test_instructions.py::test_cross_check_catches_mutation[missing-entry]"
    "test_instructions.py::test_cross_check_catches_mutation[ticked-doc]" "test_instructions.py::test_cross_check_catches_mutation[unknown-snake]"
    "test_instructions.py::test_cross_check_catches_mutation[allowlist-launder]" "test_instructions.py::test_cross_check_catches_mutation[allowlist-stale]"
    "test_instructions.py::test_cross_check_catches_mutation[user-guides]" "test_instructions.py::test_cross_check_catches_mutation[docs-word]";
    do grep -q -F "PASSED tests/$t" "$HOME/out" || exit 1; done && ! grep -q -E "^(SKIPPED|XFAIL|XPASS)"
    "$HOME/out"' && uv run python -c "import sys; sys.path.insert(0, 'tests'); from
    test_instructions import instruction_violations as v, guidance_violations as g;
    from rcac_mcp.server import SERVER_INSTRUCTIONS as t; from rcac_mcp.tools import
    TOOL_REGISTRY as r; n = [x.name for x in r]; md = open('INSTRUCTIONS.md').read();
    assert v(t, n) == [] and g(md) == []; assert v(t + '\n- doc_find:\tLook up RCAC
    user guides', n); assert v(t + '\n- job_magic:\tRun a job', n); assert v(t.replace('\n-
    sinfo:', '\n'), n); assert v(t + '\nConsult the RCAC user guides with the guides
    tool.', n); assert g(md + '\nDocs\x3a Before advising on any RCAC-specific topic,
    search the RCAC user guides at docs.rcac.purdue.edu.')" && uv run python -c "import
    sys; sys.path.insert(0, 'tests'); from test_registry import registry_violations
    as g, EXPECTED_TOOLS as e; assert len(e) == 23 and not g(sorted(e)); assert g(sorted(e)
    + ['doc_search']); assert g(sorted(e - {'sinfo'})); assert g(sorted(e) + ['sinfo'])"
    && test ! -e src/rcac_mcp/tools/docs.py && ! grep -n -E 'doc_search|doc_load|Documentation
    Search|RCAC_DOCS_DB|index-docs|docs-path|docs-output' src/rcac_mcp/server.py src/rcac_mcp/tools/__init__.py
    INSTRUCTIONS.md README.md && ! grep -n -i -E 'documentation|rcac-docs-mcp|user.?guide'
    INSTRUCTIONS.md src/rcac_mcp/server.py && grep -q rcac-docs-mcp README.md && grep
    -q docs.rcac.purdue.edu/mcp README.md
- id: P2
  name: Remove the indexing CLI flags, behind a sandboxed removed-flag integration
    test
  status: done
  satisfies:
  - R2
  - R3
  depends_on:
  - P1
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run pytest -q && bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run
    pytest -q -rA tests/test_cli.py > "$HOME/out"; s=$?; cat "$HOME/out" >&2; test
    $s -eq 0 && for t in "test_cli.py::test_removed_flag_is_rejected[index-docs]"
    "test_cli.py::test_removed_flag_is_rejected[docs-path]" "test_cli.py::test_removed_flag_is_rejected[docs-output]"
    "test_cli.py::test_removed_flag_is_rejected[all-three]" "test_cli.py::test_removed_flag_is_rejected[local-index-docs]"
    "test_cli.py::test_flag_check_rejects_a_known_flag" "test_cli.py::test_flag_check_catches_silent_accept[started]"
    "test_cli.py::test_flag_check_catches_silent_accept[ssh-host]" "test_cli.py::test_flag_check_catches_silent_accept[db-written]"
    "test_cli.py::test_flag_check_catches_silent_accept[stdout]"; do grep -q -F "PASSED
    tests/$t" "$HOME/out" || exit 1; done && ! grep -q -E "^(SKIPPED|XFAIL|XPASS)"
    "$HOME/out"' && uv run python -c "import sys; sys.path.insert(0, 'tests'); from
    test_cli import flag_violations as f; ok = 'CRITICAL [rcac_mcp] unrecognized arguments\x3a
    --index-docs'; assert not f(2, '', ok, ['--index-docs']); assert f(0, 'banner',
    'INFO [rcac_mcp] Execution mode\x3a local', ['--index-docs']); assert f(2, '',
    'CRITICAL [rcac_mcp] SSH host required', ['--index-docs']); assert f(2, '', ok
    + '\nDBFILE\x3a /tmp/x/docs.db', ['--index-docs']); assert f(2, 'x', ok, ['--index-docs'])"
    && bin/sandbox.sh sh -c 'uv run rcac-mcp --help > help.txt 2>&1 && grep -q --
    --ssh-host help.txt && ! grep -E -- "--index-docs|--docs-path|--docs-output|Documentation
    Indexing" help.txt' && bin/sandbox.sh sh -c 'uv run rcac-mcp -e local --index-docs
    < /dev/null > out.txt 2> err.txt; s=$?; cat err.txt >&2; test $s -eq 2 && grep
    -q "unrecognized arguments:.--index-docs" err.txt && ! grep -q "Execution mode"
    err.txt && test ! -s out.txt' && ! grep -n -E 'index.docs|docs.path|docs.output|_run_index_docs|Documentation
    Indexing' src/rcac_mcp/__init__.py && uv run python -c "import ast,subprocess;
    old=subprocess.run(['git','show','3cb2853:src/rcac_mcp/__init__.py'],capture_output=True,text=True,check=True).stdout;
    new=open('src/rcac_mcp/__init__.py').read(); f=lambda s:{n.name:n for c in ast.parse(s).body
    if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef)};
    o,n=f(old),f(new); assert all(ast.dump(o[k])==ast.dump(n[k]) for k in ('_resolve_exec_mode','_create_executor')),
    'exec-mode ladder changed'; assert [ast.dump(x) for x in o['run'].body[2:]]==[ast.dump(x)
    for x in n['run'].body[1:]], 'run() changed beyond the indexing branch'"
- id: P3
  name: Delete the docs package and the docs-only suite; leave a marker-enforced suite
    that checks R1, R3 and R4
  status: done
  satisfies:
  - R1
  - R9
  depends_on:
  - P1
  - P2
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv run pytest -q && sh -c 'uv run pytest -q --noconftest --collect-only
    -m "not unit and not integration" > /dev/null; test $? -eq 5' && test ! -e src/rcac_mcp/docs
    && test ! -e tests/test_database.py && test ! -e tests/test_indexer.py && test
    ! -e tests/test_tools.py && uv run python -c "import importlib.util as u; assert
    u.find_spec('rcac_mcp.docs') is None and u.find_spec('rcac_mcp.tools.docs') is
    None" && ! grep -rnI -E 'rcac_mcp.docs|DocsIndexer|DocsDatabase|RCAC_DOCS_DB|requires_submodule|RCAC-Docs'
    src tests/conftest.py && bin/sandbox.sh sh -c 'cd "$CLUSTER_MCP_REPO" && uv run
    pytest -q -rA > "$HOME/out"; s=$?; cat "$HOME/out" >&2; test $s -eq 0 && for t
    in "test_registry.py::test_registry_matches_expected_tools" "test_registry.py::test_served_tools_match_registry"
    "test_registry.py::test_registry_check_catches_drift[added-doc]" "test_registry.py::test_registry_check_catches_drift[missing]"
    "test_registry.py::test_registry_check_catches_drift[duplicate]" "test_registry.py::test_docs_modules_absent[rcac_mcp.docs]"
    "test_registry.py::test_docs_modules_absent[rcac_mcp.tools.docs]" "test_registry.py::test_absence_check_catches_namespace_leftover"
    "test_registry.py::test_absence_message_for_leftover_bytecode[empty-pycache]"
    "test_registry.py::test_absence_message_for_leftover_bytecode[pycache-pyc]" "test_registry.py::test_absence_message_for_leftover_bytecode[nested-pyc]"
    "test_registry.py::test_absence_message_for_leftover_bytecode[bare-pyc]" "test_registry.py::test_absence_message_for_readded_source[init]"
    "test_registry.py::test_absence_message_for_readded_source[module]" "test_registry.py::test_absence_message_for_readded_source[data]"
    "test_registry.py::test_absence_message_for_readded_source[nested-module]" "test_registry.py::test_absence_message_for_readded_source[module-file]"
    "test_instructions.py::test_instructions_match_registry[constant]" "test_instructions.py::test_instructions_match_registry[served]"
    "test_instructions.py::test_instructions_md_has_no_docs_guidance" "test_instructions.py::test_cross_check_catches_mutation[doc-entry]"
    "test_instructions.py::test_cross_check_catches_mutation[unknown-entry]" "test_instructions.py::test_cross_check_catches_mutation[missing-entry]"
    "test_instructions.py::test_cross_check_catches_mutation[ticked-doc]" "test_instructions.py::test_cross_check_catches_mutation[unknown-snake]"
    "test_instructions.py::test_cross_check_catches_mutation[allowlist-launder]" "test_instructions.py::test_cross_check_catches_mutation[allowlist-stale]"
    "test_instructions.py::test_cross_check_catches_mutation[user-guides]" "test_instructions.py::test_cross_check_catches_mutation[docs-word]"
    "test_cli.py::test_removed_flag_is_rejected[index-docs]" "test_cli.py::test_removed_flag_is_rejected[docs-path]"
    "test_cli.py::test_removed_flag_is_rejected[docs-output]" "test_cli.py::test_removed_flag_is_rejected[all-three]"
    "test_cli.py::test_removed_flag_is_rejected[local-index-docs]" "test_cli.py::test_flag_check_rejects_a_known_flag"
    "test_cli.py::test_flag_check_catches_silent_accept[started]" "test_cli.py::test_flag_check_catches_silent_accept[ssh-host]"
    "test_cli.py::test_flag_check_catches_silent_accept[db-written]" "test_cli.py::test_flag_check_catches_silent_accept[stdout]";
    do grep -q -F "PASSED tests/$t" "$HOME/out" || exit 1; done && ! grep -q -E "^(SKIPPED|XFAIL|XPASS)"
    "$HOME/out"' && uv run python -c "import sys, inspect; sys.path.insert(0, 'tests');
    import test_registry as t; assert t.absence_violations('rcac_mcp.docs') == []
    and t.absence_violations('rcac_mcp.tools.docs') == []; assert 'absence_violations(name)'
    in inspect.getsource(t.test_docs_modules_absent)"
- id: P4
  name: Drop the indexer's runtime dependencies and relock
  status: done
  satisfies:
  - R8
  depends_on:
  - P3
  parallel: true
  hammerable: false
  hill: uphill
  verify: uv lock --check && uv sync --locked && uv run python -c "import tomllib;
    d = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; bad
    = [x for x in d if x.lower().startswith(('pyyaml', 'jinja2'))]; assert not bad,
    bad" && ! uv tree --depth 1 --no-dev | grep -E '(pyyaml|jinja2) v' && ! grep -rnI
    -E '^[[:space:]]*(import|from)[[:space:]]+(yaml|jinja2)' src && uv run pytest
    -q && bin/sandbox.sh uv run rcac-mcp --help > /dev/null
- id: P5
  name: Remove the RCAC-Docs fixture submodule
  status: done
  satisfies:
  - R7
  depends_on:
  - P3
  parallel: true
  hammerable: false
  hill: uphill
  verify: test ! -e .gitmodules && test ! -e tests/fixtures/RCAC-Docs && ! git ls-files
    -s | grep -q '^160000' && ! git submodule status 2>&1 | grep -q . && grep -q '"/tests/fixtures"'
    pyproject.toml && uv run pytest -q
- id: P6
  name: Make AGENTS.md and the seeds describe the post-strip repository; re-run every
    check on a fresh clone; own the deferral ledger
  status: done
  satisfies:
  - R10
  - R9
  - R7
  - R8
  - R2
  depends_on:
  - P4
  - P5
  parallel: false
  hammerable: false
  hill: uphill
  verify: uv lock --check && uv run pytest -q && bin/sandbox.sh uv run rcac-mcp --help
    > /dev/null && sh -c 'uv run pytest -q --noconftest --collect-only -m "not unit
    and not integration" > /dev/null; test $? -eq 5' && ! sed -e 's#src/rcac_mcp/docs/__pycache__/##g'
    -e 's#del src/rcac_mcp/docs`##g' AGENTS.md | grep -n -E 'doc_|FTS5|indexer|doc_search|doc_load|index-docs|docs-path|docs-output|RCAC-Docs|RCAC_DOCS_DB|tools/docs|rcac_mcp/docs|`docs/`|docs.index|submodule|all
    81|No existing test carries|selects NOTHING' && ! git grep -n -E 'doc_search|doc_load|RCAC_DOCS_DB|index-docs'
    -- src INSTRUCTIONS.md README.md && test ! -e src/rcac_mcp/tools/docs.py && !
    grep -n -E 'doc_search|doc_load|Documentation Search|RCAC_DOCS_DB|index-docs|docs-path|docs-output'
    src/rcac_mcp/server.py src/rcac_mcp/tools/__init__.py INSTRUCTIONS.md README.md
    && ! grep -n -i -E 'documentation|rcac-docs-mcp|user.?guide' INSTRUCTIONS.md src/rcac_mcp/server.py
    && grep -q rcac-docs-mcp README.md && grep -q docs.rcac.purdue.edu/mcp README.md
    && ! grep -n -E 'index.docs|docs.path|docs.output|_run_index_docs|Documentation
    Indexing' src/rcac_mcp/__init__.py && uv run python -c "import ast,subprocess;
    old=subprocess.run(['git','show','3cb2853:src/rcac_mcp/__init__.py'],capture_output=True,text=True,check=True).stdout;
    new=open('src/rcac_mcp/__init__.py').read(); f=lambda s:{n.name:n for c in ast.parse(s).body
    if isinstance(c,ast.ClassDef) for n in c.body if isinstance(n,ast.FunctionDef)};
    o,n=f(old),f(new); assert all(ast.dump(o[k])==ast.dump(n[k]) for k in ('_resolve_exec_mode','_create_executor')),
    'exec-mode ladder changed'; assert [ast.dump(x) for x in o['run'].body[2:]]==[ast.dump(x)
    for x in n['run'].body[1:]], 'run() changed beyond the indexing branch'" && bin/sandbox.sh
    sh -c 'uv run rcac-mcp --help > help.txt 2>&1 && grep -q -- --ssh-host help.txt
    && ! grep -E -- "--index-docs|--docs-path|--docs-output|Documentation Indexing"
    help.txt' && bin/sandbox.sh sh -c 'uv run rcac-mcp -e local --index-docs < /dev/null
    > out.txt 2> err.txt; s=$?; cat err.txt >&2; test $s -eq 2 && grep -q "unrecognized
    arguments:.--index-docs" err.txt && ! grep -q "Execution mode" err.txt && test
    ! -s out.txt' && uv run python -c "import sys; sys.path.insert(0, 'tests'); from
    test_instructions import instruction_violations as v, guidance_violations as g;
    from rcac_mcp.server import SERVER_INSTRUCTIONS as t; from rcac_mcp.tools import
    TOOL_REGISTRY as r; n = [x.name for x in r]; md = open('INSTRUCTIONS.md').read();
    assert v(t, n) == [] and g(md) == []; assert v(t + '\n- doc_find:\tLook up RCAC
    user guides', n); assert v(t + '\n- job_magic:\tRun a job', n); assert v(t.replace('\n-
    sinfo:', '\n'), n); assert v(t + '\nConsult the RCAC user guides with the guides
    tool.', n); assert g(md + '\nDocs\x3a Before advising on any RCAC-specific topic,
    search the RCAC user guides at docs.rcac.purdue.edu.')" && uv run python -c "import
    sys; sys.path.insert(0, 'tests'); from test_registry import registry_violations
    as g, EXPECTED_TOOLS as e; assert len(e) == 23 and not g(sorted(e)); assert g(sorted(e)
    + ['doc_search']); assert g(sorted(e - {'sinfo'})); assert g(sorted(e) + ['sinfo'])"
    && uv run python -c "import sys; sys.path.insert(0, 'tests'); from test_cli import
    flag_violations as f; ok = 'CRITICAL [rcac_mcp] unrecognized arguments\x3a --index-docs';
    assert not f(2, '', ok, ['--index-docs']); assert f(0, 'banner', 'INFO [rcac_mcp]
    Execution mode\x3a local', ['--index-docs']); assert f(2, '', 'CRITICAL [rcac_mcp]
    SSH host required', ['--index-docs']); assert f(2, '', ok + '\nDBFILE\x3a /tmp/x/docs.db',
    ['--index-docs']); assert f(2, 'x', ok, ['--index-docs'])" && test ! -e src/rcac_mcp/docs
    && test ! -e tests/test_database.py && test ! -e tests/test_indexer.py && test
    ! -e tests/test_tools.py && uv run python -c "import importlib.util as u; assert
    u.find_spec('rcac_mcp.docs') is None and u.find_spec('rcac_mcp.tools.docs') is
    None" && ! grep -rnI -E 'rcac_mcp.docs|DocsIndexer|DocsDatabase|RCAC_DOCS_DB|requires_submodule|RCAC-Docs'
    src tests/conftest.py && uv run python -c "import tomllib; d = tomllib.load(open('pyproject.toml',
    'rb'))['project']['dependencies']; bad = [x for x in d if x.lower().startswith(('pyyaml',
    'jinja2'))]; assert not bad, bad" && ! uv tree --depth 1 --no-dev | grep -E '(pyyaml|jinja2)
    v' && ! grep -rnI -E '^[[:space:]]*(import|from)[[:space:]]+(yaml|jinja2)' src
    && bin/sandbox.sh sh -c 'unset VIRTUAL_ENV; git clone -q "$CLUSTER_MCP_REPO" c
    && cd c && UV_PROJECT="$PWD" && export UV_PROJECT && test ! -e .gitmodules &&
    ! git ls-files -s | grep -q "^160000" && ! git submodule status 2>&1 | grep -q
    . && test ! -e src/rcac_mcp/docs && ! grep -q -i -E "^[[:space:]]*.(pyyaml|jinja2)[^a-z0-9_]"
    pyproject.toml && uv sync --locked -q && uv lock --check && uv run python -c "import
    os, rcac_mcp; assert os.path.realpath(rcac_mcp.__file__).startswith(os.path.realpath(os.getcwd())
    + os.sep), rcac_mcp.__file__" && uv run pytest -q -rA > "$HOME/out"; s=$?; cat
    "$HOME/out" >&2; test $s -eq 0 && for t in "test_registry.py::test_registry_matches_expected_tools"
    "test_registry.py::test_served_tools_match_registry" "test_registry.py::test_registry_check_catches_drift[added-doc]"
    "test_registry.py::test_registry_check_catches_drift[missing]" "test_registry.py::test_registry_check_catches_drift[duplicate]"
    "test_registry.py::test_docs_modules_absent[rcac_mcp.docs]" "test_registry.py::test_docs_modules_absent[rcac_mcp.tools.docs]"
    "test_registry.py::test_absence_check_catches_namespace_leftover" "test_registry.py::test_absence_message_for_leftover_bytecode[empty-pycache]"
    "test_registry.py::test_absence_message_for_leftover_bytecode[pycache-pyc]" "test_registry.py::test_absence_message_for_leftover_bytecode[nested-pyc]"
    "test_registry.py::test_absence_message_for_leftover_bytecode[bare-pyc]" "test_registry.py::test_absence_message_for_readded_source[init]"
    "test_registry.py::test_absence_message_for_readded_source[module]" "test_registry.py::test_absence_message_for_readded_source[data]"
    "test_registry.py::test_absence_message_for_readded_source[nested-module]" "test_registry.py::test_absence_message_for_readded_source[module-file]"
    "test_instructions.py::test_instructions_match_registry[constant]" "test_instructions.py::test_instructions_match_registry[served]"
    "test_instructions.py::test_instructions_md_has_no_docs_guidance" "test_instructions.py::test_cross_check_catches_mutation[doc-entry]"
    "test_instructions.py::test_cross_check_catches_mutation[unknown-entry]" "test_instructions.py::test_cross_check_catches_mutation[missing-entry]"
    "test_instructions.py::test_cross_check_catches_mutation[ticked-doc]" "test_instructions.py::test_cross_check_catches_mutation[unknown-snake]"
    "test_instructions.py::test_cross_check_catches_mutation[allowlist-launder]" "test_instructions.py::test_cross_check_catches_mutation[allowlist-stale]"
    "test_instructions.py::test_cross_check_catches_mutation[user-guides]" "test_instructions.py::test_cross_check_catches_mutation[docs-word]"
    "test_cli.py::test_removed_flag_is_rejected[index-docs]" "test_cli.py::test_removed_flag_is_rejected[docs-path]"
    "test_cli.py::test_removed_flag_is_rejected[docs-output]" "test_cli.py::test_removed_flag_is_rejected[all-three]"
    "test_cli.py::test_removed_flag_is_rejected[local-index-docs]" "test_cli.py::test_flag_check_rejects_a_known_flag"
    "test_cli.py::test_flag_check_catches_silent_accept[started]" "test_cli.py::test_flag_check_catches_silent_accept[ssh-host]"
    "test_cli.py::test_flag_check_catches_silent_accept[db-written]" "test_cli.py::test_flag_check_catches_silent_accept[stdout]";
    do grep -q -F "PASSED tests/$t" "$HOME/out" || exit 1; done && ! grep -q -E "^(SKIPPED|XFAIL|XPASS)"
    "$HOME/out"' && awk '/^## Testing/{f=1;next} /^## /{f=0} f' AGENTS.md | grep -q
    -F 'src/rcac_mcp/docs/__pycache__/' && awk '/^## Testing/{f=1;next} /^## /{f=0}
    f' AGENTS.md | grep -q -F 'del src/rcac_mcp/docs' && awk '/^## Testing/{f=1;next}
    /^## /{f=0} f' AGENTS.md | grep -q -F 're-added' && uv run python -c "import sys,
    inspect; sys.path.insert(0, 'tests'); import test_registry as t; assert t.absence_violations('rcac_mcp.docs')
    == [] and t.absence_violations('rcac_mcp.tools.docs') == []; assert 'absence_violations(name)'
    in inspect.getsource(t.test_docs_modules_absent)" && uv run python -c "import
    re, glob; u = [('ROADMAP.md', s, '*Corrected 2026-10-16:') for s in re.split(r'(?m)^(?=#)',
    open('ROADMAP.md').read())] + [(f, open(f).read(), '- 2026-10-16:') for f in sorted(glob.glob('issues/*.md'))
    if f != 'issues/strip-docs-subsystem.md']; c = [(r'All 81 tests|81 of 81|docs-only
    suite|suite is documentation tests', 'test_registry.py'), (r'What remains here
    is a\s+whole FTS5', 'removed'), (r'Today 25 tools', '23 tools'), (r'about 3K',
    '2.1K')]; h = [(f, p, k, t[t.find(m):] if m in t else '') for f, t, m in u for
    p, k in c if re.search(p, t)]; bad = [(f, p) for f, p, k, r in h if k not in r];
    assert len(h) >= 8 and not bad, (len(h), bad)"
review:
  last_reviewed_commit: 2edfcc003e615bf343ad68e356d0108c85b8d8e0
  verdict: approved
  blocked_reason: ''
  cycle: 3
---

# TECH.md — Remove the documentation search subsystem

The **context engine and finite-state machine** for building this change. The YAML frontmatter
above is the resume ground-truth (read it from the cycle worktree with
`uv run --with pyyaml python "$KB/bin/factory/next_phase.py" spec/strip-docs-subsystem/TECH.md`);
the per-phase checklists below are the work. `code-build` executes the next actionable phase, runs
its `verify:` command, updates state via
`uv run --with pyyaml python "$KB/bin/factory/set_phase.py" …`, and makes one atomic code+state
commit.

- **Vision / requirements (locked):** [`GOAL.md`](GOAL.md) — R-IDs are the contract.
- **Authoritative design:** [`PLAN.md`](PLAN.md) — §2.3's table is the contract for test-module
  function names and test ids; the `verify:` gates grep and import them.
- **Backing research:** [`research/00-digest.md`](research/00-digest.md) + briefs.

## Frontmatter field reference

- `status` (top): `planned | in_progress | blocked | in_review | done` (`done` is stamped by
  `code-publish` after confirmation, just before landing — the terminal state of the retained record)
- `appetite`: `small | big` — caps phase count and build-iteration budget (circuit breaker).
- `branch`, `base`: the cycle's branch and the profile's `base`.
- phase `status`: `pending | in_progress | done | blocked`
- `satisfies`: GOAL R-IDs this phase delivers (traceability anchor for `code-review`). No R-ID in
  this cycle is met by a document under `spec/`; R10's evidence is `AGENTS.md`, which the blind
  reviewer can read.
- `depends_on`: phase ids that must be `done` first.
- `parallel`: `true` only for genuinely independent, non-coupled work. P4 (dependencies) and P5
  (submodule) are independent leaf packaging edits; everything else touches the coupled core or a
  high-blast-radius path and is `false`.
- `hammerable`: `false` throughout — every phase carries a contract R-ID.
- `hill`: `uphill` → `crest` → `downhill`.
- `attempts`: durable failed-verify counter, bumped by `set_phase.py --phase P<n> --record-attempt`.
- `verify`: the exact command that proves the phase. A literal `2` in a shell gate is
  `exit_status.bad_argument` (research/01); code and tests use the constant. The gates' Python
  strings write `\x3a` for a colon followed by a space, `\n` and `\t` for newline and tab (Python
  reads the escapes; the shell and YAML pass them through). The strings were generated, then
  syntax-checked under `sh -n` and `zsh -n`, and round-tripped through YAML.
- `review.cycle`: completed review passes, auto-incremented by `set_phase.py --verdict …`.

## Conventions (apply to every phase)

- `AGENTS.md` is the constitution; walk § Invariants §4, §7, §9 and § Conventions for every phase.
- One phase per `code-build` invocation; one atomic commit holding the code and the `TECH.md` state
  change, subject `[refactor] Build strip-docs-subsystem P<n>: …`, no `Co-Authored-By` trailer.
- **Same-commit rules:** P1 removes the tools *and* edits `SERVER_INSTRUCTIONS`, `INSTRUCTIONS.md`
  and the README together (§9); P2 removes the flags *and* edits `APP_USAGE`/`APP_HELP` together;
  P4 edits `[project.dependencies]` *and* commits the `uv lock` result together. Remediation of
  review cycle 1 reopens P3 and P6 and commits them as one: the stale-checkout remedy is stated in
  both the R1 test's failure message (P3) and `AGENTS.md` § Testing (P6), and a rule restated in N
  places changes in all N in the same commit (`AGENTS.md` § Conventions). Remediation of review
  cycle 2 (F3) reopens P3 and P6 again and commits them as one for the same reason: which contents
  get the stale-checkout remedy is stated in the message (P3) and in `AGENTS.md` § Testing (P6).
- **Tests first, shown red.** Each phase that adds a test runs it against the unchanged tree first
  and records the failure in the commit body.
- **Names are a contract.** The pure check functions (`registry_violations`, `module_absent`,
  `absence_violations`, `EXPECTED_TOOLS`, `instruction_violations`, `guidance_violations`,
  `NON_TOOL_TERMS`, `flag_violations`) and every test id in PLAN §2.3 are imported or grepped by the gates. Do not
  rename them; parametrise with exactly the listed ids (`pytest.param(..., id='doc-entry')`).
- Test comments and docstrings are declarative and cite no `R#`/`P#` (§ Conventions). Every test
  carries `@pytest.mark.unit` or `@pytest.mark.integration`.
- Delete with `del`, never `rm`; use `git rm` (or `git add -A` after `del`) so the index matches.
- Every CLI drive runs under `bin/sandbox.sh`; a sandboxed pytest run steps back with
  `cd "$CLUSTER_MCP_REPO"`.

---

## Phase P1 — Remove the documentation tools and their agent-facing mentions
**Satisfies:** R1 (registry half), R4, R5, R6 · **Depends on:** —
**Goal:** the server registers and serves 23 tools, its instructions name exactly those and carry
no documentation guidance, `INSTRUCTIONS.md` and the README agree, and a cross-check with standing
negative controls makes §9 executable. Design: PLAN §2.1, §2.3; research/03.

- [x] Write `tests/test_registry.py` (`unit`) per PLAN §2.3: `EXPECTED_TOOLS` (`average_wait
      download_file jobcmd jobenv jobinfo jobscript list_directory myquota read_file run_command
      sacct sbatch scancel scontrol_show_job scontrol_show_node sfeatures showpartitions sinfo slist
      squeue storage_paths upload_file write_file`), `registry_violations`, `module_absent`;
      `test_registry_matches_expected_tools`, `test_served_tools_match_registry`,
      `test_registry_check_catches_drift[added-doc|missing|duplicate]`.
- [x] Write `tests/test_instructions.py` (`unit`) per PLAN §2.3: `NON_TOOL_TERMS`,
      `DOCS_GUIDANCE`, `guidance_violations`, `instruction_violations`;
      `test_instructions_match_registry[constant|served]`,
      `test_instructions_md_has_no_docs_guidance`, and
      `test_cross_check_catches_mutation[…]` with exactly these ids:
      `doc-entry` (append `- doc_search: …`), `unknown-entry` (append `- job_magic: …`),
      `missing-entry` (drop the `- sinfo:` entry), `ticked-doc` (`` `doc_search` `` in prose),
      `unknown-snake` (`slurm_magic` in prose), `allowlist-launder` (`allow` plus `myquota`),
      `allowlist-stale` (`allow` plus a term not in the text), `user-guides` ("search the RCAC user
      guides"), `docs-word` ("see the docs").
- [x] Run both on the unchanged tree: record red (registry has 25; doc words present).
- [x] Delete `src/rcac_mcp/tools/docs.py` and its import line in `src/rcac_mcp/tools/__init__.py`.
- [x] `src/rcac_mcp/server.py`: delete the `IMPORTANT — Documentation Search` block and the
      `Documentation Search:` list; leave every other line byte-identical.
- [x] `INSTRUCTIONS.md`: delete the `Documentation:` paragraph; add nothing.
- [x] `README.md`: delete § *Documentation Search Index* and `### Documentation`; add the
      `## RCAC Documentation` pointer of PLAN §2.1 (names `rcac-docs-mcp` and
      `https://docs.rcac.purdue.edu/mcp`; no removed flag, tool or `RCAC_DOCS_DB`).
- [x] Delete `tests/test_tools.py` (it tests the removed tools). The other docs tests and the docs
      conftest stay until P3.
- **Verify:** see frontmatter. Covers: the suite is green. A sandboxed `-m unit -rA` run shows
  `PASSED` for every P1 id and no skips. The gate-level controls hold: `instruction_violations` and
  `guidance_violations` are clean on the real texts and non-empty on the `doc_find` entry, the
  `job_magic` entry, the missing `sinfo` entry, the user-guides prose and the "Docs: … user guides …
  docs.rcac" `INSTRUCTIONS.md` addition; `registry_violations` is clean on `EXPECTED_TOOLS` and
  non-empty on added, missing and duplicate names. Greps show no residue in `server.py`,
  `tools/__init__.py`, `INSTRUCTIONS.md` or the README. The README carries the pointer; neither
  instruction text does.
- **Touches:** `src/rcac_mcp/tools/docs.py`, `src/rcac_mcp/tools/__init__.py`,
  `src/rcac_mcp/server.py`, `INSTRUCTIONS.md`, `README.md`, `tests/test_tools.py`,
  `tests/test_registry.py`, `tests/test_instructions.py`.

## Phase P2 — Remove the indexing CLI flags
**Satisfies:** R2, R3 · **Depends on:** P1
**Goal:** `rcac-mcp` no longer knows `--index-docs`, `--docs-path` or `--docs-output`; passing any
of them exits `exit_status.bad_argument` naming the flag, before the server starts or a file is
written; `--help` does not mention them. Design: PLAN §2.2, §2.3 *R3 drive*; research/01, /04.

- [x] Replace `tests/test_cli.py` per PLAN §2.3: `flag_violations`;
      `test_removed_flag_is_rejected[index-docs|docs-path|docs-output|all-three|local-index-docs]`
      (`integration`, each drive through `bin/sandbox.sh` by the test itself);
      `test_flag_check_rejects_a_known_flag` (`integration`, a sandboxed `--generate-token` drive
      whose result `flag_violations` must reject);
      `test_flag_check_catches_silent_accept[started|ssh-host|db-written|stdout]` (`unit`,
      synthetic results). The binary and `bin/sandbox.sh` are asserted to exist; no skip path.
- [x] Run it on the unchanged CLI: record red (the flags are accepted; `--docs-path is required`).
- [x] `src/rcac_mcp/__init__.py`: remove the three `add_argument` calls and attributes, the
      `APP_USAGE` line, the `Documentation Indexing:` block and last example of `APP_HELP` (keep
      the closing `\`), the `run()` branch and docstring clause, and `_run_index_docs()`. Do not
      touch `_resolve_exec_mode()` or `_create_executor()` (§4; the verify's AST guard enforces it).
- **Verify:** see frontmatter. Covers: the suite is green. A sandboxed `-rA` run of
  `tests/test_cli.py` shows `PASSED` for every id and no skips. The gate-level controls hold:
  `flag_violations` accepts a correct rejection and rejects the silent-accept, SSH-host,
  `DBFILE` and non-empty-stdout results. The sandboxed `--help` lacks the flags and still shows
  `--ssh-host`. A sandboxed `-e local --index-docs` drive exits 2 with the message, no
  `Execution mode` and empty stdout. `__init__.py` holds no residue. The AST guard against
  `3cb2853` passes.
- **Touches:** `src/rcac_mcp/__init__.py`, `tests/test_cli.py`.

## Phase P3 — Delete the docs package and the docs-only suite
**Satisfies:** R1 (import half), R9 · **Depends on:** P1, P2
**Goal:** `rcac_mcp.docs` cannot be imported; the suite is the three marked files; the conftest
rejects unmarked tests. Design: PLAN §2.3; research/02, /04.

- [x] Add to `tests/test_registry.py` (`unit`):
      `test_docs_modules_absent[rcac_mcp.docs|rcac_mcp.tools.docs]` (`module_absent` is true and
      `importlib.import_module` raises `ModuleNotFoundError` whose `.name` is that module) and
      `test_absence_check_catches_namespace_leftover` (a unique temporary package with only
      `sub/__pycache__/` on `sys.path` via `monkeypatch.syspath_prepend`; `module_absent` is false;
      clean `sys.modules` afterwards). Run on the unchanged tree: red.
- [x] `del src/rcac_mcp/docs` (the whole directory, including `__pycache__/`), `del
      tests/test_database.py tests/test_indexer.py`.
- [x] Rewrite `tests/conftest.py` to hold only the `pytest_collection_modifyitems` hook that raises
      `pytest.UsageError` listing every collected item without a `unit` or `integration` marker.
- [x] Show, then revert: a temporary unmarked `def test_x(): pass` makes the run fail with the
      hook's error, and makes the `--noconftest` witness exit with something other than 5.
- [x] *Remediation, review cycle 1, F2.* Add `absence_violations(name)` to `tests/test_registry.py`
      (empty when the module is absent; otherwise one message per location naming the directory,
      what it holds, why git left it, and `del <path>`), make it the failure message of
      `test_docs_modules_absent`, and extend `test_absence_check_catches_namespace_leftover` to
      assert the message names the leftover path, its `__pycache__` and the `del` remedy. The
      verdict is unchanged: a leftover `src/rcac_mcp/docs/__pycache__/` still fails the test.
- [x] *Remediation, review cycle 2, F3.* `absence_violations` reads what the location holds. Only
      bytecode (`__pycache__/`, `*.pyc`, at any depth, or a bare `.pyc` module) gets the
      stale-checkout explanation and the `del` remedy. Any other file (`__init__.py`, any `.py`,
      `schema.sql`, a re-added `docs.py` module) means the module was re-added: the message names
      those files, says so, and offers no `del`. The verdict stays FAIL in both cases. Standing
      controls: `test_absence_message_for_leftover_bytecode[empty-pycache|pycache-pyc|nested-pyc|bare-pyc]`
      and `test_absence_message_for_readded_source[init|module|data|nested-module|module-file]`.
- **Verify:** see frontmatter. Covers: the suite is green. The `--noconftest` exit-5 marker
  witness holds. The removed files are gone and `find_spec` is `None` for both modules. `grep -rnI`
  shows no residue in `src` or `conftest.py`. A sandboxed full `-rA` run shows `PASSED` for every
  id across all three files and no skips. `absence_violations` is empty for both real modules, and
  the R1 test's source uses it as its failure message. Cycle 2 adds the nine F3 control ids to
  the `-rA` list.
- **Touches:** `src/rcac_mcp/docs/`, `tests/conftest.py`, `tests/test_database.py`,
  `tests/test_indexer.py`, `tests/test_registry.py`.

## Phase P4 — Drop `pyyaml` and `jinja2` from the runtime dependencies
**Satisfies:** R8 · **Depends on:** P3
**Goal:** `[project.dependencies]` lists neither; `uv.lock` agrees; nothing under `src/` imports
either. Design: PLAN §2.4; research/02.

- [x] Confirm the WHERE clause first: `grep -rnI -E '^[[:space:]]*(import|from)[[:space:]]+(yaml|jinja2)' src`
      prints nothing. If it prints anything, STOP: R8's condition is false and the dependency stays.
- [x] Remove `pyyaml>=6.0` and `jinja2>=3.1` from `pyproject.toml`; run `uv lock`; `uv sync --locked`.
      Expect `jinja2`/`markupsafe` to leave the lock and `pyyaml` to stay (transitive via `fastmcp`).
- [x] Commit `pyproject.toml` and `uv.lock` together.
- **Verify:** see frontmatter. Covers: `uv lock --check`; a `tomllib` read of
  `[project.dependencies]`; `uv tree --depth 1 --no-dev` shows neither package as a direct
  dependency; `grep -rnI` finds no import in `src`; the suite is green after the environment drops
  `jinja2`; the sandboxed `--help` still runs.
- **Touches:** `pyproject.toml`, `uv.lock`.

## Phase P5 — Remove the `RCAC-Docs` fixture submodule
**Satisfies:** R7 · **Depends on:** P3
**Goal:** no `.gitmodules`, no gitlink; `git submodule status` prints nothing. Design: PLAN §2.4.

- [x] `git rm tests/fixtures/RCAC-Docs` and `git rm .gitmodules`; remove the empty
      `tests/fixtures/` directory if one remains.
- [x] Leave the sdist `exclude` entry `/tests/fixtures` in `pyproject.toml` (GOAL clarification).
- **Verify:** see frontmatter. Covers: no `.gitmodules`, no path, and no `160000` entry in the
  index; `git submodule status` is silent, stderr included; the sdist exclude is still present; the
  suite is green. The committed state is checked on a fresh clone in P6.
- **Touches:** `.gitmodules`, `tests/fixtures/RCAC-Docs`.

## Phase P6 — Bring `AGENTS.md` and the seeds up to date; re-check everything on a fresh clone; own the deferral ledger
**Satisfies:** R10, R9 (final), R7 and R8 (committed state), R2 (re-run) · **Depends on:** P4, P5
**Goal:** `AGENTS.md` describes the repository as it now is; the two seeds the change affects say
so; every deferral is recorded; every earlier single-phase check passes again; and the committed
branch, freshly cloned, passes the suite and the packaging checks. Design: PLAN §2.5.

- [x] `AGENTS.md`: remove the § Repository map row for `docs/` + `tools/docs.py`. Rewrite
      § Testing: three marked files with pure check functions that the gates import; the conftest
      rejects unmarked tests; the integration test wraps its drives in `bin/sandbox.sh`; PyYAML is
      not a dependency of this repository. Also rewrite the § Commands `-m unit` note and the
      § Invariants → Conventions marker bullet, keeping the rule against marker-only gates. It may
      say that documentation search lives in `rcac-docs-mcp`. It must not use the words
      "submodule", "FTS5" or "indexer", name a `doc_` identifier, a removed flag or a fixture, or
      say "all 81", "No existing test carries" or "selects NOTHING".
- [x] `issues/restore-test-coverage.md`: correct its description of the post-strip state (the
      suite is `test_registry.py`, `test_instructions.py`, `test_cli.py` and a marker-enforcing
      conftest, not an empty conftest).
- [x] `issues/agents-d-instructions.md`: add a one-line note that `tests/test_instructions.py`
      cross-checks the served instructions against `TOOL_REGISTRY`. It must be rescoped to the
      server-authored core when site context is composed in, and it cannot see a plain-word tool
      name, or doc-word-free search guidance, written in prose (PLAN §5).
- [x] **Deferral ledger.** Walk P1–P5 above and their commit bodies for "do not fix here", "known
      limitation", "follow-up" or "deferred". Each must have an `issues/{slug}.md` and a
      `ROADMAP.md` entry (`.security/` if sensitive). Known at plan time: the prose-word limit,
      recorded in the existing `agents-d-instructions` seed (above), and no other deferral. An
      unrecorded deferral is a phase failure.
- [x] Run the profile's full `verify` (`uv lock --check && uv run pytest -q && bin/sandbox.sh uv run
      rcac-mcp --help`).
- [x] *Remediation, review cycle 1, F1.* Every `ROADMAP.md` entry and seed whose present-tense
      description this cycle made false carries a dated `2026-10-16` correction; the historical
      text stays. Predicate: a claim that the docs subsystem, the docs-only suite or the pre-strip
      tool and instruction sizes are present. Sites: `ROADMAP.md` (the adopted docs-subsystem
      entry, "Every test in the suite is a docs test", "Nothing runs on push"),
      `issues/ci-workflow.md` (docs-only suite), `issues/storage-paths-resource-typeerror.md`
      ("the whole suite is documentation tests"), `issues/tool-surface.md` ("Today 25 tools …
      25.6K characters"), `issues/agents-d-instructions.md` (`SERVER_INSTRUCTIONS` "about 3K");
      `issues/restore-test-coverage.md` already had one. Evaluated and left: the adopted
      `issues/strip-docs-subsystem.md` (the cycle's own problem statement, owned by `spec/`), and
      `issues/rename-to-cluster-mcp.md`'s `RCAC_DOCS_DB` ("going away with the docs strip", true).
- [x] *Remediation, review cycle 1, F2.* `AGENTS.md` § Testing names the stale-checkout trap
      (`src/rcac_mcp/docs/__pycache__/` makes the package import as an empty namespace package and
      fails `test_docs_modules_absent[rcac_mcp.docs]`) and its remedy (`del src/rcac_mcp/docs`),
      and lists `absence_violations` among `test_registry.py`'s check functions.
- [x] *Remediation, review cycle 2, F3.* `AGENTS.md` § Testing no longer says every import is a
      stale checkout with a remedy: bytecode alone is the stale checkout, and any other file means
      the module was re-added, which the message says instead of offering a remedy.
- **Verify:** see frontmatter. Covers: the full profile gate; the `--noconftest` marker witness;
  the `AGENTS.md` residue grep; no residue in `src`, `INSTRUCTIONS.md` or the README; the README
  pointer. It re-runs P1–P4's single-phase checks: the §4 AST guard, the `--help` and
  `--index-docs` drives, the R1/R3/R4 gate-level controls, the package and dependency checks. It
  finishes with a sandboxed `git clone` of the branch, using `UV_PROJECT=$PWD` and an assertion
  that `rcac_mcp` imports from the clone. The clone must have no `.gitmodules`, no gitlink, a silent
  `git submodule status`, no docs package and no pyyaml/jinja2 dependency; `uv sync --locked` and
  `uv lock --check` must pass; and the full `-rA` run must show `PASSED` for every id with no
  skips. Remediation adds: the `AGENTS.md` residue grep runs with the two allowed stale-checkout
  strings removed first; § Testing names the leftover path and `del` remedy; P3's
  `absence_violations` checks; and a predicate over every `ROADMAP.md` section and seed (the
  adopted one aside): each that still states a false claim carries a dated correction holding the
  corrected fact. Cycle 2 adds the nine F3 control ids to the clone's `-rA` list and asserts
  § Testing states the re-added case. The clone reads committed state, so before the commit the
  gate runs in a throwaway `git worktree add --detach` holding the work committed there.
- **Touches:** `AGENTS.md`, `ROADMAP.md`, `issues/restore-test-coverage.md`,
  `issues/agents-d-instructions.md`, `issues/ci-workflow.md`,
  `issues/storage-paths-resource-typeerror.md`, `issues/tool-surface.md`.

---

## How `code-build` drives this

1. `next_phase.py` prints the next actionable phase (statuses are authoritative; the
   `current_phase` pointer is reconciled against them).
2. Pre-flight: the cycle worktree is clean, on `branch`, and `base` is reachable.
3. Execute every `[ ]` in the phase (consult `PLAN.md` / `research/` for detail).
4. Run the phase's `verify:` command — never advance on a checkbox alone.
5. Amend this file freely if reality diverges (regenerate frontmatter with `set_phase.py`; note the
   amendment in the commit body). STOP and escalate only on a **`GOAL.md` contradiction**.
6. Mark the phase `done`, advance `current_phase`, `--touch`; one `[refactor]` commit; stop and report.
