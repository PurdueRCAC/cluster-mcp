# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""The annotations Python keeps at run time, in every workspace member's `src/`, are types.

An annotation that resolves to something other than a type passes silently: `typing.get_type_hints`
returns `Final[slice(Dict[...], None, None)]` for `Final[Dict[...]:]` without complaint, and so does
eager evaluation. This module is the standing check against that class of defect.

`workspace_violations` finds the members from the root `pyproject.toml`'s `[tool.uv.workspace]` and
their modules from each member's `src/`, so a member or module added later is checked on arrival.
`annotation_positions` reads each module's syntax tree for the annotations Python keeps: module
variables and class attributes declared by a simple annotated name, the fields of a functional class
form written as one name assigned a call with its fields written out, and every function's and
method's parameters and return, at any depth. A functional class form written any other way is a
position the check cannot read, and is refused as one. Each readable position is evaluated as
`typing.get_type_hints` evaluates a postponed annotation, in the imported module's namespace (a class
attribute's in its class's), and `type_expression_violations` walks what it resolved to. An
annotation that does not resolve, resolves to a non-type, or reads a name an enclosing class body or
function binds (where eager and postponed evaluation can disagree) is refused, one line each:
`{module}:{line}: {qualified name}: {text as written!r}: {why}`.

The check over the real tree runs in a fresh interpreter under `bin/sandbox.sh`: in process, the
unit guard replaces `subprocess.Popen`, and an annotation naming it would resolve to the guard's
refuser. There `runtime_positions` reads what Python itself keeps on the imported modules, and every
position it finds must be one the syntax reader read. The controls plant scratch workspaces under
`tmp_path` and run in process.
"""

from __future__ import annotations

import annotationlib
import ast
import collections.abc
import dataclasses
import enum
import gc
import importlib
import json
import os
import signal
import subprocess
import sys
import textwrap
import tomllib
import types
import typing
import uuid
from pathlib import Path
from typing import Any, Iterator

import pytest

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
SANDBOX = ROOT / 'bin' / 'sandbox.sh'

# The kinds of position, and the qualifiers each one admits at its top.
VARIABLE, ATTRIBUTE, PARAMETER, RETURN = 'variable', 'attribute', 'parameter', 'return'
QUALIFIERS: tuple[tuple[Any, str, frozenset[str]], ...] = (
    (typing.Final, 'Final', frozenset({VARIABLE, ATTRIBUTE})),
    (typing.ClassVar, 'ClassVar', frozenset({VARIABLE, ATTRIBUTE})),
    (typing.TypeAlias, 'TypeAlias', frozenset({VARIABLE, ATTRIBUTE})),
    (typing.Required, 'Required', frozenset({ATTRIBUTE})),
    (typing.NotRequired, 'NotRequired', frozenset({ATTRIBUTE})),
    (typing.ReadOnly, 'ReadOnly', frozenset({ATTRIBUTE})),
    # A dataclass's `_: KW_ONLY` marks the fields after it keyword-only.
    (dataclasses.KW_ONLY, 'KW_ONLY', frozenset({ATTRIBUTE})),
)
# Special forms that are types on their own.
BARE_TYPES = (typing.Any, typing.Never, typing.NoReturn, typing.Self, typing.LiteralString)
# Special forms that are not types until subscripted. `typing.Union` is a class since 3.14, so it is
# matched here by identity before any class is accepted.
BARE_FORMS = (typing.Union, typing.Optional, typing.Literal, typing.Annotated, typing.Concatenate,
              typing.Unpack, typing.TypeGuard, typing.TypeIs, typing.Generic, typing.Protocol)
TYPE_PARAMETERS = (typing.TypeVar, typing.ParamSpec, typing.TypeVarTuple,
                   typing.ParamSpecArgs, typing.ParamSpecKwargs)
LITERAL_VALUES = (int, str, bytes, bool, enum.Enum)
# The calls that build a class whose annotations Python keeps, by the name they are called by, bare,
# as an attribute, or by the alias a `from … import … as …` of that name gives it, from any module.
# `type` counts only when called with three arguments, and `new_class` only with a body callback.
FUNCTIONAL_FORMS = frozenset({'TypedDict', 'NamedTuple', 'make_dataclass', 'type', 'new_class'})
# The keywords a functional form takes that hold no annotation (every `NamedTuple` keyword is a field).
FORM_KEYWORDS = {'TypedDict': frozenset({'total', 'closed'}),
                 'make_dataclass': frozenset({'fields', 'bases', 'init', 'repr', 'eq', 'order', 'unsafe_hash',
                                              'frozen', 'match_args', 'kw_only', 'slots', 'weakref_slot',
                                              'module', 'decorator'})}
# The keys of a class namespace that set its annotations.
ANNOTATION_KEYS = frozenset({'__annotations__', '__annotate__'})
UNREADABLE = 'a functional class form the check cannot read'
TYPE_PARAMETER_KINDS = {'TypeVar': typing.TypeVar, 'ParamSpec': typing.ParamSpec,
                        'TypeVarTuple': typing.TypeVarTuple}

# The tree check's child: it imports this module from `tests/` and prints the report, alone, on its
# last line of standard output (an imported module's own output goes to standard error).
REPORT_MARK = 'annotation report: '
CHILD = textwrap.dedent(f"""\
    import json, sys
    from pathlib import Path
    root = Path(sys.argv[1])
    sys.path.insert(0, str(root / 'tests'))
    out, sys.stdout = sys.stdout, sys.stderr
    import test_annotations
    report = test_annotations.workspace_report(root)
    report['kept'] = test_annotations.runtime_positions(
        [name for modules in report['members'].values() for name in modules])
    out.write({REPORT_MARK!r} + json.dumps(report) + '\\n')
    """)
CHILD_TIMEOUT = 300


@dataclasses.dataclass(frozen=True)
class Position:
    """One annotation Python keeps, as the syntax tree gives it.

    `name` is the qualified name a refusal shows (`C.x`, `C.m(x)`, `f.g() ->`); `text` is the
    annotation as written and `expr` what is evaluated (a string annotation's content). `owner` is
    the qualified name of the class whose namespace an attribute is evaluated in, empty for every
    other position and for a class defined inside a function (`local_class`), which no namespace
    reaches. `type_params` are the PEP 695 parameters in scope, `shadowed` the names it reads that an
    enclosing class body or function binds, and `line` where it is written. `unreadable` is why a
    functional class form's call or reference cannot be read, which is its refusal; its `text` is
    the call or reference as written, and it is never evaluated.
    """

    module: str
    line: int
    name: str
    kind: str
    text: str
    expr: str
    owner: tuple[str, ...] = ()
    local_class: bool = False
    type_params: tuple[tuple[str, str], ...] = ()
    shadowed: tuple[str, ...] = ()
    unreadable: str = ''


def _is_type_checking(test: ast.expr) -> bool:
    return ((isinstance(test, ast.Name) and test.id == 'TYPE_CHECKING')
            or (isinstance(test, ast.Attribute) and test.attr == 'TYPE_CHECKING'))


def _type_params(node: ast.AST) -> tuple[tuple[str, str], ...]:
    return tuple((p.name, type(p).__name__) for p in getattr(node, 'type_params', ()))


def _scope_bindings(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> frozenset[str]:
    """The names a class body or function binds in its own scope: what a nested scope could read."""
    names: set[str] = set()
    declared: set[str] = set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = node.args
        for arg in [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]:
            if arg is not None:
                names.add(arg.arg)

    def visit(n: ast.AST) -> None:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
            return
        if isinstance(n, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            return
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, ast.alias) and n.name != '*':
            names.add((n.asname or n.name).split('.')[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
            names.add(n.name)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            names.add(n.rest)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            declared.update(n.names)
        for child in ast.iter_child_nodes(n):
            visit(child)

    for statement in node.body:
        visit(statement)
    return frozenset(names - declared)


def _names_read(node: ast.expr) -> set[str]:
    """Every name an annotation reads, inside its string forward references too.

    A `Literal`'s values and an `Annotated`'s metadata are values, not references, so they are not read.
    """
    names: set[str] = set()

    def visit(n: ast.AST) -> None:
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            try:
                visit(ast.parse(n.value.strip(), mode='eval').body)
            except SyntaxError:
                pass
        elif isinstance(n, ast.Subscript):
            visit(n.value)
            head = n.value.id if isinstance(n.value, ast.Name) else (
                n.value.attr if isinstance(n.value, ast.Attribute) else None)
            if head == 'Literal':
                return
            if head == 'Annotated' and isinstance(n.slice, ast.Tuple) and n.slice.elts:
                visit(n.slice.elts[0])
                return
            visit(n.slice)
        else:
            for child in ast.iter_child_nodes(n):
                visit(child)

    visit(node)
    return names


@dataclasses.dataclass(frozen=True)
class _Scope:
    kind: str
    name: str
    bound: frozenset[str]
    type_params: tuple[tuple[str, str], ...]


def annotation_positions(source: str, module: str, path: str | Path = '<unknown>') -> list[Position]:
    """Every annotation Python keeps at run time in `source`, read from its syntax tree.

    Module and class bodies give their simple variable annotations (inside `if`, `try`, `with`,
    `for`, `while` and `match` blocks too, never inside an `if TYPE_CHECKING:` body, which never
    runs) and the fields of a class built by a call (`TypedDict` and `NamedTuple`, the latter's
    keyword form included, `dataclasses.make_dataclass`, and a three-argument `type` whose namespace
    holds `__annotations__`), whether the call names it bare, as an attribute or by an imported
    alias; every function and method, at any depth, gives its annotated parameters and its return.
    A function body's own variable annotations are never evaluated, so they are not read; nor is an
    annotated attribute or subscript target, which Python does not keep.

    A functional form is read only as `Name = Form('Name', <fields>)`, one name assigned at module
    or class level, with its fields written out as a literal. Every other call of one (in a function
    body, as a base class, with a chained, tuple or attribute target, its fields in a variable or
    unpacked), every reference to one that is not a call or a class statement's base (the factory
    bound to another name or passed as a value), a factory's name as a string, and every spelling of
    `__annotations__` or `__annotate__` outside a read `type` call's namespace, is returned as a
    position whose `unreadable` says why: the check cannot find the annotations it builds, so it
    refuses it.
    """
    tree = ast.parse(source, str(path))
    forms = {name: name for name in FUNCTIONAL_FORMS}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            forms.update((a.asname, a.name) for a in node.names if a.name in FUNCTIONAL_FORMS and a.asname)
    found: list[Position] = []
    # The calls read as functional forms, and the namespace dicts (and their keys) of the `type`
    # calls among them.
    read: set[int] = set()

    def add(annotation: ast.expr, name: str, kind: str, scopes: list[_Scope], where: str,
            own_params: tuple[tuple[str, str], ...] = ()) -> None:
        params = tuple(p for s in scopes for p in s.type_params) + own_params
        local_class = any(s.kind == 'function' for s in scopes)
        in_class_body = where == 'class'
        owner = tuple(s.name for s in scopes) if in_class_body and not local_class else ()
        # An attribute of a reachable class is evaluated in its class's namespace, as Python does;
        # every other enclosing scope is one only eager evaluation would read.
        enclosing = scopes[:-1] if in_class_body and not local_class else scopes
        read = _names_read(annotation) - {p for p, _ in params}
        shadowed = tuple(sorted(n for n in read if any(n in s.bound for s in enclosing)))
        text = ast.get_source_segment(source, annotation) or ast.unparse(annotation)
        expr = (annotation.value if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str)
                else ast.unparse(annotation))
        found.append(Position(module, annotation.lineno, name, kind, text, expr, owner, local_class,
                              params, shadowed))

    def prefix(scopes: list[_Scope]) -> str:
        return ''.join(f'{s.name}.' for s in scopes)

    def functional(statement: ast.Assign, scopes: list[_Scope], where: str) -> None:
        call = statement.value
        if (not isinstance(call, ast.Call) or len(statement.targets) != 1
                or not isinstance(statement.targets[0], ast.Name)):
            return
        func = call.func
        form = (forms.get(func.id) if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) and func.attr in FUNCTIONAL_FORMS else None)
        if form is None or not _builds_a_class(form, call) or _unreadable_call(form, call):
            return
        read.add(id(call))
        keywords = {k.arg: k.value for k in call.keywords if k.arg}
        pairs: list[tuple[str, ast.expr]] = []
        if form == 'type':
            namespace = call.args[2] if len(call.args) == 3 else None
            if isinstance(namespace, ast.Dict):
                read.add(id(namespace))
                read.update(id(key) for key in namespace.keys if key is not None)
                for key, value in zip(namespace.keys, namespace.values):
                    if isinstance(key, ast.Constant) and key.value == '__annotations__':
                        pairs += _field_pairs(value)
        elif form is not None:
            fields = call.args[1] if len(call.args) > 1 else keywords.get('fields') if form == 'make_dataclass' else None
            if fields is not None:
                pairs += _field_pairs(fields)
            if form == 'NamedTuple':
                pairs += list(keywords.items())
        target = statement.targets[0].id
        for field, value in pairs:
            add(value, f'{prefix(scopes)}{target}.{field}', ATTRIBUTE, scopes, where)

    def function(node: ast.FunctionDef | ast.AsyncFunctionDef, scopes: list[_Scope]) -> None:
        own = _type_params(node)
        name = f'{prefix(scopes)}{node.name}'
        args = node.args
        for arg in [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]:
            if arg is not None and arg.annotation is not None:
                add(arg.annotation, f'{name}({arg.arg})', PARAMETER, scopes, 'function', own)
        if node.returns is not None:
            add(node.returns, f'{name}() ->', RETURN, scopes, 'function', own)
        body(node.body, [*scopes, _Scope('function', node.name, _scope_bindings(node), own)], 'function')

    def body(statements: list[ast.stmt], scopes: list[_Scope], where: str) -> None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function(statement, scopes)
            elif isinstance(statement, ast.ClassDef):
                inner = _Scope('class', statement.name, _scope_bindings(statement), _type_params(statement))
                body(statement.body, [*scopes, inner], 'class')
            elif isinstance(statement, ast.AnnAssign):
                if where != 'function' and statement.simple and isinstance(statement.target, ast.Name):
                    kind = VARIABLE if where == 'module' else ATTRIBUTE
                    add(statement.annotation, f'{prefix(scopes)}{statement.target.id}', kind, scopes, where)
            elif isinstance(statement, ast.Assign):
                if where != 'function':
                    functional(statement, scopes, where)
            elif isinstance(statement, ast.If):
                if not _is_type_checking(statement.test):
                    body(statement.body, scopes, where)
                body(statement.orelse, scopes, where)
            else:
                for block in _blocks(statement):
                    body(block, scopes, where)

    body(tree.body, [], 'module')
    for node, name, why in _unread_forms(tree, forms, read):
        text = ast.get_source_segment(source, node) or ast.unparse(node)
        found.append(Position(module, node.lineno, name, ATTRIBUTE, _shortened(text), '', unreadable=why))
    return found


def _shortened(text: str) -> str:
    return text if len(text) <= 200 else text[:197] + '...'


def _builds_a_class(form: str, call: ast.Call) -> bool:
    """Whether a call of a functional form's name builds a class: `type` only with three arguments
    (or arguments unpacked into it), `new_class` only with a body callback; the others always."""
    unpacked = any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords)
    if form == 'type':
        return unpacked or len(call.args) == 3
    if form == 'new_class':
        return unpacked or len(call.args) > 3 or any(k.arg == 'exec_body' for k in call.keywords)
    return True


def _unreadable_call(form: str, call: ast.Call) -> str:
    """Why the fields of a functional form's call cannot be read from its syntax, or '' when they can."""
    if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
        return 'its arguments are unpacked with * or **'
    if form == 'new_class':
        return 'new_class sets its namespace in a callback'
    if form == 'type':
        namespace = call.args[2]
        if not isinstance(namespace, ast.Dict):
            return 'its namespace is not written out as a dict literal'
        keys = [k.value if isinstance(k, ast.Constant) and isinstance(k.value, str) else None for k in namespace.keys]
        if None in keys:
            return 'its namespace has a key that is not written out as a string'
        if '__annotate__' in keys:
            return 'its namespace sets __annotate__'
        held = [v for k, v in zip(keys, namespace.values) if k == '__annotations__']
        return _unreadable_fields('TypedDict', held[0]) if held else ''
    if len(call.args) > 2:
        return 'it takes more positional arguments than a name and its fields'
    keywords = {k.arg: k.value for k in call.keywords}
    allowed = FORM_KEYWORDS.get(form)
    if allowed is not None:
        extra = sorted(k for k in keywords if k not in allowed)
        if extra:
            return f'it takes the keyword {extra[0]}, which the check does not read'
    fields = call.args[1:2] or [v for k, v in keywords.items() if k == 'fields' and form == 'make_dataclass']
    return _unreadable_fields(form, fields[0]) if fields else ''


def _unreadable_fields(form: str, fields: ast.expr) -> str:
    """Why a functional form's fields argument cannot be read from its syntax, or '' when it can.

    `TypedDict` (and a `type` namespace's `__annotations__`) take a dict literal with string keys;
    `NamedTuple` a list or tuple of `(name, annotation)` pairs; `make_dataclass` a list or tuple of
    names, pairs and `(name, annotation, field)` triples.
    """
    if form == 'TypedDict':
        if not isinstance(fields, ast.Dict):
            return 'its fields are not written out as a dict literal'
        bad = [k for k in fields.keys if not (isinstance(k, ast.Constant) and isinstance(k.value, str))]
        return f'a field name it cannot read: {ast.unparse(bad[0]) if bad[0] else "**"}' if bad else ''
    if not isinstance(fields, (ast.List, ast.Tuple)):
        return 'its fields are not written out as a list or tuple literal'
    sizes = (2, 3) if form == 'make_dataclass' else (2,)
    for element in fields.elts:
        if form == 'make_dataclass' and isinstance(element, ast.Constant) and isinstance(element.value, str):
            continue
        if not (isinstance(element, (ast.Tuple, ast.List)) and len(element.elts) in sizes
                and isinstance(element.elts[0], ast.Constant) and isinstance(element.elts[0].value, str)):
            return f'a field it cannot read: {ast.unparse(element)}'
    return ''


def _unread_forms(tree: ast.Module, forms: dict[str, str], read: set[int]) -> list[tuple[ast.AST, str, str]]:
    """Every functional class form in `tree` the reader did not read: the node, its qualified name
    and why. An `if TYPE_CHECKING:` body never runs, so nothing in it is a form Python builds."""
    found: list[tuple[ast.AST, str, str]] = []
    allowed: set[int] = set()

    def form_of(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            return forms.get(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) and node.attr in FUNCTIONAL_FORMS:
            # An attribute named `type` is a form only as `builtins.type`: `self.type(...)` is common.
            if node.attr != 'type' or (isinstance(node.value, ast.Name) and node.value.id == 'builtins'):
                return node.attr
        return None

    def visit(node: ast.AST, prefix: str) -> None:
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for statement in node.orelse:
                visit(statement, prefix)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if isinstance(node, ast.ClassDef):
                allowed.update(id(base) for base in node.bases)
            inside = {id(statement) for statement in node.body}
            for child in ast.iter_child_nodes(node):
                if id(child) not in inside:
                    visit(child, prefix)
            for statement in node.body:
                visit(statement, f'{prefix}{node.name}.')
            return
        if isinstance(node, ast.Call) and (form := form_of(node.func)) is not None:
            allowed.add(id(node.func))
            if id(node) not in read and _builds_a_class(form, node):
                # What its arguments spell is refused with it, not again on its own.
                allowed.update(id(n) for arg in [*node.args, *node.keywords] for n in ast.walk(arg))
                why = _unreadable_call(form, node) or 'it is not assigned to one name at module or class level'
                found.append((node, f'{prefix}{ast.unparse(node.func)}(...)',
                              f'{UNREADABLE}: {why}; only `Name = {form}("Name", <fields written out>)` at module or '
                              'class level is read, so the annotations of the class it builds would go unchecked'))
        elif (form := form_of(node)) is not None and form != 'type' and id(node) not in allowed:
            found.append((node, f'{prefix}{ast.unparse(node)}',
                          f'{UNREADABLE}: {form} is referenced other than by a call or as a base class, so a class '
                          'built through that reference cannot be found; call it by its own name'))
        elif id(node) not in read and id(node) not in allowed and (spelled := _spelled(node)) is not None:
            found.append((node, f'{prefix}{spelled}',
                          f'{UNREADABLE}: {spelled} is spelled outside a call the check reads, so the annotations '
                          'set or built through it cannot be found'))
        for child in ast.iter_child_nodes(node):
            visit(child, prefix)

    for statement in tree.body:
        visit(statement, '')
    return found


def _spelled(node: ast.AST) -> str | None:
    """The name a node spells that sets a class's annotations or reaches a factory by a string:
    `__annotations__` or `__annotate__` as a string, a keyword, an attribute or a name, and a
    functional form's name as a string (`getattr(typing, 'TypedDict')`)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        named = node.value
        return named if named in ANNOTATION_KEYS or named in FUNCTIONAL_FORMS - {'type'} else None
    named = (node.arg if isinstance(node, ast.keyword) else node.attr if isinstance(node, ast.Attribute)
             else node.id if isinstance(node, ast.Name) else None)
    if named not in ANNOTATION_KEYS:
        return None
    return ast.unparse(node) if isinstance(node, ast.Attribute) else named


def _field_pairs(fields: ast.expr) -> list[tuple[str, ast.expr]]:
    """The (name, annotation) pairs a functional class form's fields literal gives.

    A dict literal maps names to annotations; a list or tuple holds `(name, annotation)` pairs, or
    `(name, annotation, field)` triples for `make_dataclass`. A bare name has no annotation.
    """
    if isinstance(fields, ast.Dict):
        return [(k.value, v) for k, v in zip(fields.keys, fields.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
    if isinstance(fields, (ast.List, ast.Tuple)):
        return [(e.elts[0].value, e.elts[1]) for e in fields.elts
                if isinstance(e, (ast.Tuple, ast.List)) and len(e.elts) in (2, 3)
                and isinstance(e.elts[0], ast.Constant) and isinstance(e.elts[0].value, str)]
    return []


def _blocks(statement: ast.stmt) -> list[list[ast.stmt]]:
    """The statement lists a compound statement runs in its own scope (not a def's or a class's)."""
    if isinstance(statement, ast.If):
        return [statement.body, statement.orelse]
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        return [statement.body, statement.orelse]
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return [statement.body]
    if isinstance(statement, (ast.Try, ast.TryStar)):
        return [statement.body, *(h.body for h in statement.handlers), statement.orelse, statement.finalbody]
    if isinstance(statement, ast.Match):
        return [case.body for case in statement.cases]
    return []


def _shown(value: Any) -> str:
    try:
        text = repr(value)
    except Exception as exc:
        text = f'<{type(value).__name__} whose repr raised {type(exc).__name__}>'
    return text if len(text) <= 200 else text[:197] + '...'


def type_expression_violations(hint: Any, kind: str) -> list[str]:
    """Why `hint`, an annotation of a `kind` position resolved, is not a valid type expression.

    Empty for a type. Special forms are compared by identity, never hashed: `P.args` and a list
    argument are unhashable. A `type` alias is walked into its value and a `NewType` into its
    supertype, each once. A qualifier (`Final`, `ClassVar`, `TypeAlias`, `Required`, `NotRequired`,
    `ReadOnly`, `InitVar`, and the dataclass marker `KW_ONLY`) is valid only at the top, and only in
    its kind of position. A slice in an `Annotated`'s metadata is refused: it drops that metadata as
    silently as a slice drops a type.
    """
    found: list[str] = []
    walked: list[Any] = []

    def bad(why: str, value: Any, top: bool) -> None:
        found.append(f'{"resolves to" if value is hint and top else "holds"} {why}: {_shown(value)}')

    def qualifier(value: Any) -> tuple[str, frozenset[str]] | None:
        for form, label, kinds in QUALIFIERS:
            if value is form:
                return label, kinds
        return None

    def placed(label: str, kinds: frozenset[str], top: bool) -> bool:
        if top and kind in kinds:
            return True
        where = 'below the top' if not top else f'on a {kind}'
        found.append(f'holds the qualifier {label} {where}, where it is not valid')
        return False

    def walk(h: Any, top: bool) -> None:
        if h is None or h is type(None):
            return
        if (q := qualifier(h)) is not None:
            placed(*q, top)
            return
        if any(h is form for form in BARE_FORMS):
            bad('an unsubscripted special form, not a type', h, top)
            return
        if any(h is form for form in BARE_TYPES) or isinstance(h, TYPE_PARAMETERS):
            return
        if isinstance(h, typing.TypeAliasType):
            if not any(h is w for w in walked):
                walked.append(h)
                walk(h.__value__, False)
            return
        if isinstance(h, typing.NewType):
            if not any(h is w for w in walked):
                walked.append(h)
                walk(h.__supertype__, False)
            return
        if isinstance(h, dataclasses.InitVar):
            if placed('InitVar', frozenset({ATTRIBUTE}), top):
                walk(h.type, False)
            return
        origin = typing.get_origin(h)
        if origin is not None:
            generic(h, origin, typing.get_args(h), top)
            return
        if h is Ellipsis:
            bad('an Ellipsis outside tuple[X, ...] and a Callable\'s parameters', h, top)
        elif isinstance(h, type):
            return
        elif isinstance(h, (str, typing.ForwardRef)):
            bad(f'a {type(h).__name__} left unresolved, not a type', h, top)
        elif isinstance(h, (list, tuple)):
            bad(f'a {type(h).__name__}, valid only as the parameters of a Callable, a Concatenate '
                'or a generic over a ParamSpec', h, top)
        else:
            bad(f'a {type(h).__name__}, not a type', h, top)

    def generic(h: Any, origin: Any, args: tuple[Any, ...], top: bool) -> None:
        if origin is typing.Annotated:
            walk(args[0], top)
            for meta in args[1:]:
                if isinstance(meta, slice):
                    found.append(f'holds a slice in its Annotated metadata: {_shown(meta)}')
            return
        if (q := qualifier(origin)) is not None:
            if placed(*q, top):
                for arg in args:
                    walk(arg, True)
            return
        if origin is typing.Literal:
            for arg in args:
                if not (arg is None or isinstance(arg, LITERAL_VALUES)):
                    found.append(f'holds a {type(arg).__name__} in a Literal, not a literal value: {_shown(arg)}')
            return
        if origin is collections.abc.Callable:
            if args:
                parameters(args[0])
                walk(args[-1], False)
            return
        if origin is typing.Concatenate:
            for arg in args[:-1]:
                walk(arg, False)
            if args and not (args[-1] is Ellipsis or isinstance(args[-1], typing.ParamSpec)):
                found.append(f'holds {_shown(args[-1])} as the last argument of a Concatenate, '
                             'not a ParamSpec or ...')
            return
        if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
            walk(args[0], False)
            return
        if isinstance(origin, typing.TypeAliasType):
            walk(origin, False)
        declared = getattr(origin, '__parameters__', ())
        over_paramspec = isinstance(declared, tuple) and any(isinstance(p, typing.ParamSpec) for p in declared)
        for arg in args:
            if isinstance(arg, (list, tuple)) and over_paramspec:
                for item in arg:
                    walk(item, False)
            else:
                walk(arg, False)

    def parameters(given: Any) -> None:
        if given is Ellipsis or isinstance(given, typing.ParamSpec):
            return
        if typing.get_origin(given) is typing.Concatenate:
            walk(given, False)
        elif isinstance(given, list):
            for item in given:
                walk(item, False)
        else:
            walk(given, False)

    walk(hint, True)
    return found


def _resolved(position: Position, globalns: dict[str, Any], localns: dict[str, Any]) -> Any:
    """What `typing.get_type_hints` gives for the position, as a postponed annotation.

    A one-string holder carries it: a module for a variable or attribute, a function for a parameter
    or return. Its type parameters are bound fresh, as their own scope binds them.
    """
    scope = dict(localns)
    for name, kind in position.type_params:
        scope[name] = TYPE_PARAMETER_KINDS[kind](name)
    key = 'return' if position.kind == RETURN else 'annotated'
    holder: Any
    if position.kind in (PARAMETER, RETURN):
        def holder() -> None: ...
    else:
        holder = types.ModuleType('annotation holder')
    holder.__annotations__ = {key: position.expr}
    return typing.get_type_hints(holder, globalns=globalns, localns=scope, include_extras=True)[key]


def _verdict(position: Position, globalns: dict[str, Any], localns: dict[str, Any]) -> str | None:
    """Why the position is refused, or None when it resolves to a type."""
    if position.unreadable:
        return position.unreadable
    if position.shadowed:
        return (f'reads {", ".join(position.shadowed)}, which an enclosing class body or function binds: '
                'eager evaluation reads it there and postponed evaluation does not, so which object it '
                'names depends on the module\'s mode (bind it at module level)')
    try:
        hint = _resolved(position, globalns, localns)
    except Exception as exc:
        return f'does not resolve: {type(exc).__name__}: {exc}'
    try:
        reasons = type_expression_violations(hint, position.kind)
    except Exception as exc:
        return f'could not be checked: {type(exc).__name__}: {exc}, resolving to {_shown(hint)}'
    return '; '.join(reasons) or None


def _refusal(position: Position, why: str) -> str:
    return f'{position.module}:{position.line}: {position.name}: {position.text!r}: {why}'


def _class_namespace(position: Position, globalns: dict[str, Any]) -> dict[str, Any] | str:
    """The namespace an attribute is evaluated in, or why its class cannot be reached as itself."""
    if not position.owner:
        return {}
    qualname = '.'.join(position.owner)
    found: Any = globalns.get(position.owner[0])
    for part in position.owner[1:]:
        found = getattr(found, part, None)
    if (not isinstance(found, type) or getattr(found, '__qualname__', None) != qualname
            or getattr(found, '__module__', None) != position.module):
        return (f'its class {qualname} cannot be reached as itself: {position.module}.{qualname} is '
                f'{_shown(found)}, so the check will not evaluate it in another namespace')
    return dict(vars(found))


def _innermost_statement(statements: list[ast.stmt], line: int) -> ast.stmt | None:
    """The innermost statement run in the module's own frame that spans `line`."""
    for statement in statements:
        start = min([statement.lineno, *(d.lineno for d in getattr(statement, 'decorator_list', ()))])
        if start <= line <= (statement.end_lineno or statement.lineno):
            for block in _blocks(statement):
                inner = _innermost_statement(block, line)
                if inner is not None:
                    return inner
            return statement
    return None


def _failed_import(module: str, path: Path, source: str, positions: list[Position],
                   exc: BaseException) -> list[str]:
    """The refusals for a module whose import raised.

    The module is refused naming the exception. The innermost statement its frame stopped at has
    its positions evaluated in the namespace the module had reached; a class attribute there takes
    its class's namespace from the traceback (the class body's frame, or the namespace a metaclass
    was handed), when the traceback holds one.
    """
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ''
    frames: list[tuple[types.FrameType, int]] = []
    tb = exc.__traceback__
    while tb is not None:
        frames.append((tb.tb_frame, tb.tb_lineno))
        tb = tb.tb_next
    resolved = path.resolve()
    own = [(f, n) for f, n in frames
           if f.f_code.co_name == '<module>' and Path(f.f_code.co_filename).resolve() == resolved]
    if not own:
        return [f'{module}: the import raised {type(exc).__name__}: {message}']
    frame, line = own[-1]
    refusals = [f'{module}:{line}: the import raised {type(exc).__name__}: {message}']
    statement = _innermost_statement(ast.parse(source, str(path)).body, line)
    if statement is None:
        return refusals
    start = min([statement.lineno, *(d.lineno for d in getattr(statement, 'decorator_list', ()))])
    end = statement.end_lineno or statement.lineno
    for position in positions:
        if not start <= position.line <= end:
            continue
        localns: dict[str, Any] | str = {}
        if position.owner:
            localns = _traceback_namespace(position, frames)
            if localns is None:
                reached = _class_namespace(position, frame.f_globals)
                localns = reached if isinstance(reached, dict) else {}
        why = _verdict(position, frame.f_globals, localns)
        if why:
            refusals.append(_refusal(position, why))
    return refusals


def _traceback_namespace(position: Position, frames: list[tuple[types.FrameType, int]]) -> dict[str, Any] | None:
    qualname = '.'.join(position.owner)

    def matches(candidate: Any) -> bool:
        try:
            return (candidate.get('__qualname__') == qualname
                    and candidate.get('__module__') == position.module)
        except Exception:
            return False

    for frame, _ in reversed(frames):
        names = frame.f_locals
        if matches(names):
            return dict(names)
        for value in list(names.values()):
            if isinstance(value, dict) and matches(value):
                return dict(value)
    return None


def module_check(module: str, path: Path) -> tuple[list[Position], list[str]]:
    """The positions of one module, and the refusals among them.

    A module with no positions is never imported. A `__main__` module with positions is refused
    unimported, every position named: it runs its program on import, so its namespace cannot be
    had without running it. Any other module is imported by name, and the file it was imported from
    must be the file read.
    """
    source = path.read_text()
    try:
        positions = annotation_positions(source, module, path)
    except SyntaxError as exc:
        return [], [f'{module}:{exc.lineno}: the module does not parse: {exc.msg}']
    if not positions:
        return positions, []
    if module.rsplit('.', 1)[-1] == '__main__':
        why = 'not evaluated: a __main__ module runs its program when imported, so the check cannot resolve it'
        return positions, [_refusal(p, why) for p in positions]
    try:
        loaded = importlib.import_module(module)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        return positions, _failed_import(module, path, source, positions, exc)
    file = getattr(loaded, '__file__', None)
    if file is None or Path(file).resolve() != path.resolve():
        return positions, [f'{module}: importing it loads {file}, not {path}, so the check would read '
                           'one file and evaluate another']
    globalns = vars(loaded)
    refusals = []
    for position in positions:
        localns = _class_namespace(position, globalns)
        why = localns if isinstance(localns, str) else _verdict(position, globalns, localns)
        if why:
            refusals.append(_refusal(position, why))
    return positions, refusals


def workspace_members(root: Path) -> list[Path]:
    """The workspace's members, from the root `pyproject.toml`'s `[tool.uv.workspace]`, the root included.

    A `members` glob gives each directory it matches that holds a `pyproject.toml`, less any an
    `exclude` glob matches.
    """
    root = root.resolve()
    config = tomllib.loads((root / 'pyproject.toml').read_text())
    workspace = config.get('tool', {}).get('uv', {}).get('workspace', {})
    excluded = {p.resolve() for pattern in workspace.get('exclude', []) for p in root.glob(pattern)}
    members = {root}
    for pattern in workspace.get('members', []):
        for found in root.glob(pattern):
            if found.is_dir() and (found / 'pyproject.toml').is_file() and found.resolve() not in excluded:
                members.add(found.resolve())
    return sorted(members)


def member_modules(member: Path) -> list[tuple[str, Path]]:
    """Every module under `member`'s `src/`, by its dotted name from `src/` (`__init__` dropped)."""
    src = member / 'src'
    modules = []
    for file in sorted(src.rglob('*.py')):
        parts = file.relative_to(src).with_suffix('').parts
        if parts and parts[-1] == '__init__':
            parts = parts[:-1]
        if parts:
            modules.append(('.'.join(parts), file))
    return modules


def workspace_report(root: Path) -> dict[str, Any]:
    """The check over a workspace: each member's modules, every position read, and every refusal.

    A member other than the root with no `src/` is refused: its modules cannot be found, so it would
    otherwise pass unread.
    """
    root = root.resolve()
    report: dict[str, Any] = {'members': {}, 'positions': [], 'violations': []}
    for member in workspace_members(root):
        label = member.relative_to(root).as_posix() if member != root else '.'
        if not (member / 'src').is_dir():
            report['members'][label] = []
            if member != root:
                report['violations'].append(f'{label}: a workspace member with no src/, so none of its '
                                            'modules can be found to check')
            continue
        modules = member_modules(member)
        report['members'][label] = [name for name, _ in modules]
        for name, file in modules:
            positions, refusals = module_check(name, file)
            report['positions'] += [f'{p.module}:{p.name}' for p in positions]
            report['violations'] += refusals
    return report


def workspace_violations(root: Path) -> list[str]:
    """Every refusal of the check over the workspace at `root`; empty when every kept annotation is a type."""
    return workspace_report(root)['violations']


def runtime_positions(modules: list[str]) -> dict[str, list[str]]:
    """The positions Python itself keeps at run time in `modules`, found without the syntax reader.

    Each module is imported (a `__main__` module never is: it runs its program). Its own annotations,
    those of every class reachable from its namespace that names it as its module, and those of
    every function alive in the interpreter whose code was compiled from its file, are read with
    `annotationlib` as strings, so nothing is evaluated. Each is named as the reader names its
    position (`<locals>` dropped from a qualified name). A class's annotations that a base also holds
    are left out (a `TypedDict` merges its bases'), and so is a function that wraps another
    (`__wrapped__`) or whose qualified name is not its code's: its annotations are another function's.
    Synthesized members (a `NamedTuple`'s `__new__`, a dataclass's `__init__`) are compiled from no
    module's file, so they are never found. What cannot be read is returned under `unreadable`.
    """
    kept: set[str] = set()
    unreadable: list[str] = []

    def annotations(obj: Any, label: str) -> dict[str, Any]:
        try:
            return annotationlib.get_annotations(obj, format=annotationlib.Format.STRING)
        except Exception as exc:
            unreadable.append(f'{label}: {type(exc).__name__}: {exc}')
            return {}

    def quietly(obj: Any) -> dict[str, Any]:
        try:
            return annotationlib.get_annotations(obj, format=annotationlib.Format.STRING)
        except Exception:
            return {}

    files: dict[str, str] = {}
    for name in modules:
        if name.rsplit('.', 1)[-1] == '__main__':
            continue
        try:
            module = importlib.import_module(name)
        except KeyboardInterrupt:
            raise
        except BaseException as exc:
            unreadable.append(f'{name}: the import raised {type(exc).__name__}: {exc}')
            continue
        if getattr(module, '__file__', None) is None:
            unreadable.append(f'{name}: it has no file, so no function compiled from it can be found')
            continue
        files[os.path.realpath(module.__file__)] = name
        kept.update(f'{name}:{key}' for key in annotations(module, name))
        pending, seen = list(vars(module).values()), set()
        while pending:
            obj = pending.pop()
            if not isinstance(obj, type) or id(obj) in seen or getattr(obj, '__module__', None) != name:
                continue
            seen.add(id(obj))
            qualname = obj.__qualname__.replace('<locals>.', '')
            inherited = {key for base in obj.__mro__[1:] for key in quietly(base)}
            kept.update(f'{name}:{qualname}.{key}' for key in annotations(obj, f'{name}:{qualname}')
                        if key not in inherited)
            pending.extend(vars(obj).values())
    gc.collect()
    compiled: dict[str, str | None] = {}
    for obj in gc.get_objects():
        if not isinstance(obj, types.FunctionType):
            continue
        code = obj.__code__
        if code.co_filename not in compiled:
            compiled[code.co_filename] = files.get(os.path.realpath(code.co_filename))
        name = compiled[code.co_filename]
        if name is None or '__wrapped__' in vars(obj) or obj.__qualname__ != code.co_qualname:
            continue
        qualname = obj.__qualname__.replace('<locals>.', '')
        for key in annotations(obj, f'{name}:{qualname}'):
            kept.add(f'{name}:{qualname}() ->' if key == 'return' else f'{name}:{qualname}({key})')
    return {'positions': sorted(kept), 'unreadable': unreadable}


# The tree.

@pytest.mark.integration
def test_every_kept_annotation_in_the_workspace_is_a_type() -> None:
    proc = subprocess.Popen([str(SANDBOX), sys.executable, '-I', '-c', CHILD, str(ROOT)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    try:
        out, err = proc.communicate(timeout=CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        # bin/sandbox.sh does not exec, so the interpreter is its child: the whole group goes.
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        pytest.fail(f'the check did not finish within {CHILD_TIMEOUT} s', pytrace=False)
    lines = [line for line in out.splitlines() if line.startswith(REPORT_MARK)]
    assert proc.returncode == 0 and len(lines) == 1, f'the check exited {proc.returncode}:\n{err[-4000:]}'
    report = json.loads(lines[0][len(REPORT_MARK):])
    assert report['violations'] == [], '\n'.join(['annotations that are not types:', *report['violations']])
    expected = {m.relative_to(ROOT.resolve()).as_posix() if m != ROOT.resolve() else '.': (m / 'src').is_dir()
                for m in workspace_members(ROOT)}
    assert sorted(report['members']) == sorted(expected)
    unread = [m for m, has_src in expected.items() if has_src and not report['members'][m]]
    assert len(expected) > 1 and unread == [], f'members with a src/ and no module read: {unread}'
    assert 'cluster_mcp.core.auth:AUTH_MODES' in report['positions'], 'AUTH_MODES was not among the positions read'
    # Every `.py` file under every member's `src/`, found by a walk of its own, is a module the check
    # listed: none was left out by depth, by being a package's `__init__`, or by its member's place.
    files: dict[str, Path] = {}
    for member in workspace_members(ROOT):
        for folder, _, names in os.walk(member / 'src'):
            for name in names:
                if name.endswith('.py'):
                    file = Path(folder, name)
                    dotted = file.relative_to(member / 'src').with_suffix('').parts
                    files['.'.join(dotted[:-1] if dotted[-1] == '__init__' else dotted)] = file
    listed = sorted(m for modules in report['members'].values() for m in modules)
    assert listed == sorted(files)
    # Every annotation Python keeps on what the imported modules hold is a position the check read.
    # The positions expected come from the interpreter, not from the syntax reader being checked.
    kept = report['kept']
    assert kept['unreadable'] == [], '\n'.join(['annotations Python keeps that could not be read:', *kept['unreadable']])
    missed = sorted(set(kept['positions']) - set(report['positions']))
    assert missed == [], '\n'.join(['annotations Python keeps that the check did not read:', *missed])
    # The oracle is not vacuous: it found every kind of position, in more than one member.
    holding = {member for member, modules in report['members'].items()
               for p in kept['positions'] if p.split(':', 1)[0] in modules}
    assert len(holding) > 1, f'Python keeps annotations in only {sorted(holding)}'
    names = [p.split(':', 1)[1] for p in kept['positions']]
    assert any('.' not in n and '(' not in n for n in names), 'no module variable among the kept positions'
    assert any('.' in n and '(' not in n for n in names), 'no class attribute among the kept positions'
    assert any(n.endswith(')') for n in names) and any(n.endswith(') ->') for n in names), \
        'no parameter or no return among the kept positions'


@pytest.mark.unit
def test_the_members_are_the_locked_workspace() -> None:
    locked = tomllib.loads((ROOT / 'uv.lock').read_text())['manifest']['members']
    found = [tomllib.loads((m / 'pyproject.toml').read_text())['project']['name'] for m in workspace_members(ROOT)]
    assert len(found) > 1
    assert sorted(found) == sorted(locked)


# The controls: scratch workspaces, imported in process and forgotten afterwards.

class Scratch:
    """A workspace under `tmp_path`: a root `pyproject.toml` and members with their own `src/`.

    Each package name is unique to its case, so nothing collides with `cluster_mcp` or another case.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True)
        self.workspace()

    def workspace(self, members: tuple[str, ...] = ('packages/*',), exclude: tuple[str, ...] = ()) -> None:
        (self.root / 'pyproject.toml').write_text(
            '[project]\nname = "scratch-root"\nversion = "0"\n\n[tool.uv.workspace]\n'
            f'members = {json.dumps(list(members))}\nexclude = {json.dumps(list(exclude))}\n')

    @staticmethod
    def package() -> str:
        return f'scratch_{uuid.uuid4().hex[:12]}'

    def member(self, directory: str, files: dict[str, str], src: bool = True) -> Path:
        home = self.root / 'packages' / directory
        home.mkdir(parents=True)
        (home / 'pyproject.toml').write_text(f'[project]\nname = "{directory}"\nversion = "0"\n')
        if src:
            for name, text in files.items():
                target = home / 'src' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(textwrap.dedent(text))
            self.importable(home / 'src')
        importlib.invalidate_caches()
        return home

    def importable(self, src: Path) -> None:
        """Put `src` on `sys.path` through a symbolic link, as an installed tree's path may differ
        from the path the check reads: frames and `__file__` then name the link, not the file read."""
        links = self.root.parent / 'links'
        links.mkdir(exist_ok=True)
        link = links / uuid.uuid4().hex
        link.symlink_to(src.resolve(), target_is_directory=True)
        sys.path.insert(0, str(link))

    def module(self, source: str, postponed: bool, directory: str | None = None) -> str:
        """A one-module member holding `source`, in `directory` (its package name when None); the module's name."""
        package = self.package()
        head = 'from __future__ import annotations\n' if postponed else ''
        self.member(directory or package,
                    {f'{package}/__init__.py': '', f'{package}/mod.py': head + textwrap.dedent(source)})
        return f'{package}.mod'

    def root_files(self, files: dict[str, str]) -> None:
        """Files under the root's own `src/`: the root is a member too."""
        for name, text in files.items():
            target = self.root / 'src' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(text))
        self.importable(self.root / 'src')
        importlib.invalidate_caches()

    def report(self) -> dict[str, Any]:
        importlib.invalidate_caches()
        return workspace_report(self.root)


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Scratch]:
    saved = list(sys.path)
    before = set(sys.modules)
    made = Scratch(tmp_path / 'workspace')
    try:
        yield made
    finally:
        sys.path[:] = saved
        root = str(made.root.resolve())
        for name in set(sys.modules) - before:
            file = getattr(sys.modules[name], '__file__', None) or ''
            if os.path.realpath(file).startswith(root) or name.startswith('scratch_'):
                del sys.modules[name]
        importlib.invalidate_caches()


MODES = [pytest.param(True, id='postponed'), pytest.param(False, id='eager')]
SLICE = 'dict[str, int:]'

# A slice in each kind of position: the source, and the qualified name its refusal must show.
PLANTS = [
    ('variable', f'held: {SLICE} = {{}}\n', 'held'),
    ('conditional-variable', f'if True:\n    held: {SLICE} = {{}}\n', 'held'),
    ('attribute', f'class Planted:\n    held: {SLICE}\n', 'Planted.held'),
    ('nested-attribute', f'class Planted:\n    class Inner:\n        held: {SLICE}\n', 'Planted.Inner.held'),
    ('local-class-attribute', f'def make():\n    class Local:\n        held: {SLICE}\n    return Local\n',
     'make.Local.held'),
    ('functional-typeddict', f'from typing import TypedDict\nPlanted = TypedDict("Planted", {{"held": {SLICE}}})\n',
     'Planted.held'),
    ('functional-namedtuple', f'import typing\nPlanted = typing.NamedTuple("Planted", [("held", {SLICE})])\n',
     'Planted.held'),
    ('parameter', f'def planted(given: {SLICE}) -> None: ...\n', 'planted(given)'),
    ('positional-only', f'def planted(given: {SLICE}, /) -> None: ...\n', 'planted(given)'),
    ('keyword-only', f'def planted(*, given: {SLICE}) -> None: ...\n', 'planted(given)'),
    ('varargs', f'def planted(*given: {SLICE}) -> None: ...\n', 'planted(given)'),
    ('kwargs', f'def planted(**given: {SLICE}) -> None: ...\n', 'planted(given)'),
    ('return', f'def planted() -> {SLICE}: ...\n', 'planted() ->'),
    ('async-return', f'async def planted() -> {SLICE}: ...\n', 'planted() ->'),
    ('method-parameter', f'class Planted:\n    def run(self, given: {SLICE}) -> None: ...\n', 'Planted.run(given)'),
    ('method-return', f'class Planted:\n    def run(self) -> {SLICE}: ...\n', 'Planted.run() ->'),
    ('static-method', f'class Planted:\n    @staticmethod\n    def run(given: {SLICE}) -> None: ...\n',
     'Planted.run(given)'),
    ('nested-function', f'def planted() -> None:\n    def inner(given: {SLICE}) -> None: ...\n',
     'planted.inner(given)'),
    ('replaced-function', f'def replace(fn):\n    return 42\n@replace\ndef planted(given: {SLICE}) -> None: ...\n',
     'planted(given)'),
    ('private-name', f'_held: {SLICE} = {{}}\n', '_held'),
    ('string-annotation', f'held: "{SLICE}" = {{}}\n', 'held'),
    ('multi-line', 'held: dict[\n    str,\n    int:\n] = {}\n', 'held'),
    ('else-block', f'if False:\n    pass\nelse:\n    held: {SLICE} = {{}}\n', 'held'),
    ('try-block', f'try:\n    held: {SLICE} = {{}}\nexcept ImportError:\n    pass\n', 'held'),
    ('except-block', f'try:\n    pass\nexcept ImportError:\n    held: {SLICE} = {{}}\n', 'held'),
    ('try-else-block', f'try:\n    pass\nexcept ImportError:\n    pass\nelse:\n    held: {SLICE} = {{}}\n', 'held'),
    ('finally-block', f'try:\n    pass\nfinally:\n    held: {SLICE} = {{}}\n', 'held'),
    ('with-block', f'import contextlib\nwith contextlib.suppress(ImportError):\n    held: {SLICE} = {{}}\n', 'held'),
    ('for-block', f'for _ in range(1):\n    held: {SLICE} = {{}}\n', 'held'),
    ('while-block', f'while False:\n    held: {SLICE} = {{}}\n', 'held'),
    ('match-block', f'match 0:\n    case _:\n        held: {SLICE} = {{}}\n', 'held'),
    ('class-block', f'class Planted:\n    if True:\n        held: {SLICE}\n', 'Planted.held'),
    ('dataclass-field', f'import dataclasses\n@dataclasses.dataclass\nclass Planted:\n    held: {SLICE} | None = None\n',
     'Planted.held'),
    ('aliased-functional-typeddict', f'from typing import TypedDict as Shape\nPlanted = Shape("Planted", {{"held": {SLICE}}})\n',
     'Planted.held'),
    ('aliased-functional-namedtuple', f'from typing import NamedTuple as Row\nPlanted = Row("Planted", [("held", {SLICE})])\n',
     'Planted.held'),
    ('keyword-namedtuple', f'import typing\nPlanted = typing.NamedTuple("Planted", held={SLICE})\n', 'Planted.held'),
    ('make-dataclass', f'import dataclasses\nPlanted = dataclasses.make_dataclass("Planted", [("held", {SLICE})])\n',
     'Planted.held'),
    ('make-dataclass-field', 'import dataclasses\nPlanted = dataclasses.make_dataclass("Planted", '
     f'["bare", ("held", {SLICE}, dataclasses.field(default=None))])\n', 'Planted.held'),
    ('aliased-make-dataclass', 'from dataclasses import make_dataclass as build\n'
     f'Planted = build("Planted", fields=[("held", {SLICE})])\n', 'Planted.held'),
    ('type-namespace', f'Planted = type("Planted", (), {{"__annotations__": {{"held": {SLICE}}}}})\n', 'Planted.held'),
    ('class-functional', f'import typing\nclass Holder:\n    Planted = typing.NamedTuple("Planted", [("held", {SLICE})])\n',
     'Holder.Planted.held'),
    ('union-member', f'held: int | {SLICE} = 0\n', 'held'),
    ('callable-parameters', f'from collections.abc import Callable\nheld: Callable[[{SLICE}], int] | None = None\n', 'held'),
    ('callable-return', f'from collections.abc import Callable\nheld: Callable[[int], {SLICE}] | None = None\n', 'held'),
    ('homogeneous-tuple', f'held: tuple[{SLICE}, ...] = ()\n', 'held'),
    ('concatenate-prefix', 'from collections.abc import Callable\nfrom typing import Concatenate\n'
     f'def planted[**P](fn: Callable[Concatenate[{SLICE}, P], int]) -> None: ...\n', 'planted(fn)'),
    ('paramspec-list', f'class Over[**P]:\n    pass\nheld: Over[[int, {SLICE}]] | None = None\n', 'held'),
    ('initvar', 'import dataclasses\n@dataclasses.dataclass\nclass Planted:\n'
     f'    held: dataclasses.InitVar[{SLICE}] = None\n', 'Planted.held'),
    ('final-argument', f'from typing import Final\nheld: Final[{SLICE}] = {{}}\n', 'held'),
    ('annotated-type', f'from typing import Annotated\nheld: Annotated[{SLICE}, "meta"] = {{}}\n', 'held'),
    ('alias-value', f'type Sliced = {SLICE}\nheld: Sliced = {{}}\n', 'held'),
    ('generic-alias-value', 'type Sliced[T] = dict[T, int:]\nheld: Sliced[str] = {}\n', 'held'),
    ('newtype-supertype', f'from typing import NewType\nSliced = NewType("Sliced", {SLICE})\nheld: Sliced = {{}}\n', 'held'),
]


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
@pytest.mark.parametrize(('source', 'where'), [pytest.param(s, w, id=i) for i, s, w in PLANTS])
def test_a_planted_slice_is_refused_naming_where(scratch: Scratch, source: str, where: str, postponed: bool) -> None:
    module = scratch.module(source, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1, violations
    assert violations[0].startswith(f'{module}:') and f': {where}: ' in violations[0], violations
    assert 'slice' in violations[0].split(f': {where}: ', 1)[1].split("': ", 1)[1], violations


FORMS_HEAD = 'import dataclasses\nimport functools\nimport types\nimport typing\nfrom typing import NamedTuple, TypedDict\n'
# A functional class form spelled where the reader does not read it, most holding a slice Python keeps
# on the class it builds: the source, and the qualified name its one refusal must show.
UNREADABLE_FORMS = [
    ('annotated-assignment', f'Planted: type = TypedDict("Planted", {{"held": {SLICE}}})\n', 'TypedDict(...)'),
    ('chained-targets', f'Planted = Other = NamedTuple("Planted", [("held", {SLICE})])\n', 'NamedTuple(...)'),
    ('tuple-target', f'Planted, other = TypedDict("Planted", {{"held": {SLICE}}}), 1\n', 'TypedDict(...)'),
    ('walrus', f'(Planted := TypedDict("Planted", {{"held": {SLICE}}}))\n', 'TypedDict(...)'),
    ('base-class', f'class Planted(NamedTuple("Base", [("held", {SLICE})])):\n    pass\n', 'NamedTuple(...)'),
    ('attribute-target', f'class Holder:\n    pass\nHolder.Planted = NamedTuple("Planted", [("held", {SLICE})])\n',
     'NamedTuple(...)'),
    ('function-body', f'def make():\n    Planted = NamedTuple("Planted", [("held", {SLICE})])\n    return Planted\n',
     'make.NamedTuple(...)'),
    ('function-return', f'def make():\n    return TypedDict("Planted", {{"held": {SLICE}}})\n', 'make.TypedDict(...)'),
    ('method-body', 'class Holder:\n    def build(self):\n'
     f'        return dataclasses.make_dataclass("Planted", [("held", {SLICE})])\n',
     'Holder.build.dataclasses.make_dataclass(...)'),
    ('class-body-chained', f'class Holder:\n    Planted = Other = NamedTuple("Planted", [("held", {SLICE})])\n',
     'Holder.NamedTuple(...)'),
    ('fields-in-a-variable', f'fields = [("held", {SLICE})]\nPlanted = NamedTuple("Planted", fields)\n', 'NamedTuple(...)'),
    ('fields-from-a-call', f'Planted = TypedDict("Planted", dict(held={SLICE}))\n', 'TypedDict(...)'),
    ('field-in-a-variable', f'pair = ("held", {SLICE})\nPlanted = NamedTuple("Planted", [("other", int), pair])\n',
     'NamedTuple(...)'),
    ('unpacked-fields', f'more = {{"held": {SLICE}}}\nPlanted = NamedTuple("Planted", **more)\n', 'NamedTuple(...)'),
    ('make-dataclass-namespace', 'Planted = dataclasses.make_dataclass("Planted", [("other", int)], '
     f'namespace=dict(__annotations__={{"held": {SLICE}}}))\n', 'dataclasses.make_dataclass(...)'),
    ('type-namespace-in-a-variable', 'space = {"held": 0}\nPlanted = type("Planted", (), space)\n', 'type(...)'),
    ('type-namespace-unpacked', f'base = {{}}\nPlanted = type("Planted", (), {{**base, "__annotations__": {{"held": {SLICE}}}}})\n',
     'type(...)'),
    ('type-annotate', f'Planted = type("Planted", (), {{"__annotate__": lambda format: {{"held": {SLICE}}}}})\n', 'type(...)'),
    ('namespace-dict', f'space = {{"__annotations__": {{"held": {SLICE}}}}}\n', '__annotations__'),
    ('namespace-keyword', f'space = dict(__annotations__={{"held": {SLICE}}})\n', '__annotations__'),
    ('annotations-assigned', f'class Holder:\n    pass\nHolder.__annotations__ = {{"held": {SLICE}}}\n',
     'Holder.__annotations__'),
    ('annotations-in-a-class-body', f'class Holder:\n    __annotations__ = {{"held": {SLICE}}}\n', 'Holder.__annotations__'),
    ('factory-named-by-a-string', f'Planted = getattr(typing, "TypedDict")("Planted", {{"held": {SLICE}}})\n', 'TypedDict'),
    ('new-class', 'Planted = types.new_class("Planted", (), {}, '
     f'lambda ns: ns.update(__annotations__={{"held": {SLICE}}}))\n', 'types.new_class(...)'),
    ('assigned-alias', f'Shape = typing.TypedDict\nPlanted = Shape("Planted", {{"held": {SLICE}}})\n', 'typing.TypedDict'),
    ('passed-as-a-value', f'Build = functools.partial(NamedTuple, "Planted")\nPlanted = Build([("held", {SLICE})])\n',
     'NamedTuple'),
]


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
@pytest.mark.parametrize(('source', 'where'), [pytest.param(s, w, id=i) for i, s, w in UNREADABLE_FORMS])
def test_an_unreadable_functional_form_is_refused(scratch: Scratch, source: str, where: str, postponed: bool) -> None:
    module = scratch.module(FORMS_HEAD + source, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1, violations
    assert violations[0].startswith(f'{module}:') and f': {where}: ' in violations[0], violations
    assert UNREADABLE in violations[0].split(f': {where}: ', 1)[1], violations


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
@pytest.mark.parametrize(('source', 'where', 'error'), [
    pytest.param('held: Missing = 0\n', 'held', 'NameError', id='undefined'),
    pytest.param('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from decimal import Decimal\n'
                 'def planted(given: Decimal) -> None: ...\n', 'planted(given)', 'NameError', id='type-checking-only'),
    pytest.param('held: int | "str" = 0\n', 'held', 'TypeError', id='union-with-a-string'),
    pytest.param('held: "dict[str," = {}\n', 'held', 'SyntaxError', id='malformed-string'),
    pytest.param('def planted() -> list["Missing"]: ...\n', 'planted() ->', 'NameError', id='nested-forward-reference'),
])
def test_an_unresolvable_annotation_is_refused(scratch: Scratch, source: str, where: str, error: str,
                                               postponed: bool) -> None:
    module = scratch.module(source, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1, violations
    assert violations[0].startswith(f'{module}:') and f': {where}: ' in violations[0], violations
    assert f'does not resolve: {error}' in violations[0], violations


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
@pytest.mark.parametrize(('source', 'where', 'why'), [
    pytest.param('Mode = dict[str, int]\nclass Holder:\n    Mode = dict[str, int:]\n'
                 '    def run(self, given: Mode) -> None: ...\n', 'Holder.run(given)', 'reads Mode',
                 id='class-alias-shadowing-a-global'),
    pytest.param('def outer() -> None:\n    Local = int\n    def inner(given: Local) -> None: ...\n',
                 'outer.inner(given)', 'reads Local', id='enclosing-function-local'),
    pytest.param('def outer() -> None:\n    from decimal import Decimal as Local\n    def inner(given: Local) -> None: ...\n',
                 'outer.inner(given)', 'reads Local', id='enclosing-function-import'),
    pytest.param('def outer(Local: type) -> None:\n    def inner(given: Local) -> None: ...\n',
                 'outer.inner(given)', 'reads Local', id='enclosing-function-parameter'),
    pytest.param('def outer() -> None:\n    class Local:\n        pass\n    def inner() -> Local: ...\n',
                 'outer.inner() ->', 'reads Local', id='enclosing-function-class'),
    pytest.param('Mode = int\nclass Holder:\n    Mode = str\n    def run(self, given: "Mode") -> None: ...\n',
                 'Holder.run(given)', 'reads Mode', id='class-alias-read-through-a-string'),
    pytest.param('Mode = int\nclass Holder:\n    Mode = str\n    def run(self, given: list[Mode]) -> None: ...\n',
                 'Holder.run(given)', 'reads Mode', id='class-alias-read-inside-a-subscript'),
    pytest.param('def make() -> None:\n    Alias = int\n    class Local:\n        held: Alias\n',
                 'make.Local.held', 'reads Alias', id='local-class-reading-its-function'),
    pytest.param('class Planted:\n    held: int\nclass Other:\n    held: int\nPlanted = Other\n',
                 'Planted.held', 'cannot be reached as itself', id='rebound-class-name'),
    pytest.param('def boxed(cls):\n    return [cls]\n@boxed\nclass Planted:\n    held: int\n',
                 'Planted.held', 'cannot be reached as itself', id='decorator-returning-a-non-class'),
])
def test_a_scope_dependent_annotation_is_refused(scratch: Scratch, source: str, where: str, why: str,
                                                 postponed: bool) -> None:
    module = scratch.module(source, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1, violations
    assert violations[0].startswith(f'{module}:') and f': {where}: ' in violations[0], violations
    assert why in violations[0], violations


@pytest.mark.unit
def test_a_class_rebound_from_another_module_is_refused(scratch: Scratch) -> None:
    # Same name, a class, but another module's: the attribute is not evaluated in its namespace.
    package = scratch.package()
    scratch.member(package, {f'{package}/__init__.py': '', f'{package}/other.py': 'class Planted:\n    pass\n',
                             f'{package}/mod.py': f'class Planted:\n    held: int\nfrom {package}.other import Planted\n'})
    violations = scratch.report()['violations']
    assert len(violations) == 1 and violations[0].startswith(f'{package}.mod:2: Planted.held: '), violations
    assert 'cannot be reached as itself' in violations[0], violations


@pytest.mark.unit
def test_a_member_without_src_is_refused(scratch: Scratch) -> None:
    package = scratch.package()
    scratch.member(package, {}, src=False)
    report = scratch.report()
    assert report['members'][f'packages/{package}'] == []
    assert report['violations'] == [f'packages/{package}: a workspace member with no src/, so none of its '
                                    'modules can be found to check']


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
def test_a_type_checking_only_declaration_is_not_read(scratch: Scratch, postponed: bool) -> None:
    module = scratch.module(
        'import typing\nfrom typing import TYPE_CHECKING\n'
        'if TYPE_CHECKING:\n    held: Missing\n    def planted(given: Missing) -> None: ...\n'
        '    Hidden = typing.NamedTuple("Hidden", fields)\n'
        'else:\n    kept: int = 0\n'
        'if typing.TYPE_CHECKING:\n    other: Missing\n    Alias = typing.TypedDict\n', postponed)
    report = scratch.report()
    assert report['violations'] == []
    assert [p for p in report['positions'] if p.startswith(f'{module}:')] == [f'{module}:kept']


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
@pytest.mark.parametrize(('source', 'where', 'qualifier'), [
    pytest.param('from typing import Final\ndef planted(given: Final[int]) -> None: ...\n', 'planted(given)',
                 'Final on a parameter', id='final-parameter'),
    pytest.param('from typing import ClassVar\ndef planted() -> ClassVar[int]: ...\n', 'planted() ->',
                 'ClassVar on a return', id='classvar-return'),
    pytest.param('from typing import Required\nheld: Required[int] = 0\n', 'held', 'Required on a variable',
                 id='required-variable'),
    pytest.param('from dataclasses import InitVar\nheld: InitVar[int] = 0\n', 'held', 'InitVar on a variable',
                 id='initvar-variable'),
    pytest.param('from typing import Final\nheld: list[Final[int]] = []\n', 'held', 'Final below the top',
                 id='final-nested'),
    pytest.param('from dataclasses import KW_ONLY\nheld: KW_ONLY = None\n', 'held', 'KW_ONLY on a variable',
                 id='kw-only-variable'),
    pytest.param('from dataclasses import KW_ONLY\ndef planted(given: KW_ONLY) -> None: ...\n', 'planted(given)',
                 'KW_ONLY on a parameter', id='kw-only-parameter'),
    pytest.param('import dataclasses\n@dataclasses.dataclass\nclass Planted:\n    held: list[dataclasses.KW_ONLY]\n',
                 'Planted.held', 'KW_ONLY below the top', id='kw-only-nested'),
])
def test_a_qualifier_out_of_its_place_is_named(scratch: Scratch, source: str, where: str, qualifier: str,
                                               postponed: bool) -> None:
    module = scratch.module(source, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1, violations
    assert violations[0].startswith(f'{module}:') and f': {where}: ' in violations[0], violations
    assert f'qualifier {qualifier}' in violations[0], violations


# A decorator that raises at import, as a tool decorator building a schema does.
RAISING_DECORATOR = 'def tool(fn):\n    raise TypeError("cannot build a schema")\n'
# A metaclass that refuses a slice in a field while its class is built, as a pydantic model does.
REFUSING_METACLASS = '''\
import typing
class Model(type):
    def __new__(mcs, name, bases, namespace):
        made = super().__new__(mcs, name, bases, namespace)
        for hint in typing.get_type_hints(made).values():
            if any(isinstance(arg, slice) for arg in typing.get_args(hint)):
                raise TypeError(f"{name}: a field is not a type")
        return made
'''


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
@pytest.mark.parametrize(('source', 'named'), [
    pytest.param(f'{RAISING_DECORATOR}def fine(given: int) -> None: ...\n@tool\ndef planted(given: {SLICE}) -> None: ...\n',
                 ['planted(given)'], id='decorated-tool'),
    pytest.param(f'{RAISING_DECORATOR}if True:\n    other: {SLICE} = {{}}\n    @tool\n    def planted(given: {SLICE}) -> None: ...\n',
                 ['planted(given)'], id='inside-an-if-block'),
    pytest.param(f'{RAISING_DECORATOR}@tool\ndef planted(given: int) -> str: ...\n', [], id='good-annotations'),
    pytest.param(f'{REFUSING_METACLASS}class Planted(metaclass=Model):\n    held: {SLICE}\n',
                 ['Planted.held'], id='refusing-metaclass'),
    pytest.param(f'{REFUSING_METACLASS}class Planted(metaclass=Model):\n    Alias = {SLICE}\n    held: Alias\n',
                 ['Planted.held'], id='refusing-metaclass-class-alias'),
    pytest.param(f'{RAISING_DECORATOR}@tool\ndef planted(given: {SLICE}, other: {SLICE}) -> None: ...\n',
                 ['planted(given)', 'planted(other)'], id='two-positions'),
])
def test_a_failed_import_names_the_statement_that_raised(scratch: Scratch, source: str, named: list[str],
                                                         postponed: bool) -> None:
    module = scratch.module(source, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1 + len(named), violations
    assert violations[0].startswith(f'{module}:') and ': the import raised TypeError: ' in violations[0], violations
    for line, where in zip(violations[1:], named):
        assert line.startswith(f'{module}:') and f': {where}: ' in line, violations
        assert 'slice' in line.split(f': {where}: ', 1)[1].split("': ", 1)[1], violations


@pytest.mark.unit
def test_a_failed_package_import_names_the_module(scratch: Scratch) -> None:
    # The package's `__init__` raises, so the traceback holds no frame of the module checked.
    package = scratch.package()
    scratch.member(package, {f'{package}/__init__.py': 'import scratch_no_such_module_anywhere\n',
                             f'{package}/mod.py': 'held: int = 0\n'})
    violations = scratch.report()['violations']
    assert violations == [f'{package}.mod: the import raised ModuleNotFoundError: '
                          "No module named 'scratch_no_such_module_anywhere'"]


# A generic whose origin raises when the check reads its parameters: the walk itself fails.
UNWALKABLE = '''\
import types
class Meta(type):
    @property
    def __parameters__(cls):
        raise RuntimeError("no parameters")
class Odd(metaclass=Meta):
    def __class_getitem__(cls, item):
        return types.GenericAlias(cls, item)
held: Odd[int] | None = None
'''


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
def test_a_hint_the_check_cannot_walk_is_refused(scratch: Scratch, postponed: bool) -> None:
    module = scratch.module(UNWALKABLE, postponed)
    violations = scratch.report()['violations']
    assert len(violations) == 1 and violations[0].startswith(f'{module}:'), violations
    assert ': held: ' in violations[0] and 'could not be checked: RuntimeError: no parameters' in violations[0], violations


VALID = '''\
import dataclasses
import enum
import types
from collections.abc import Callable
from dataclasses import KW_ONLY
from typing import (Annotated, ClassVar, Concatenate, Final, Literal, NamedTuple, NewType, NotRequired,
                    Optional, Protocol, ReadOnly, Required, Self, TypeAlias, TypedDict)


class Color(enum.Enum):
    RED = 1


UserId = NewType('UserId', int)
type Pairs[T] = list[tuple[T, T]]
LIMIT: Final = 3
NAMES: Final[list[str]] = []
Number: TypeAlias = int | float
uid: UserId = UserId(1)
pairs: Pairs[int] = []
shade: Literal['a', 1, True, None, b'x', Color.RED] = 'a'
described: Annotated[int, 'meta'] = 0
empty: tuple[()] = ()
many: tuple[int, ...] = ()
maybe: Optional[dict[str, list[int]]] = None
handler: Callable[[int, str], bool] | Callable[..., None] | Callable[[], int] | None = None


class Movie(TypedDict):
    title: Required[str]
    year: NotRequired[int]
    rating: ReadOnly[float]


Point = TypedDict('Point', {'x': int, 'y': 'int'})
Built = type('Built', (), {'count': 0})
Empty = types.new_class('Empty', ())
KIND = type(0)


class Pair(NamedTuple):
    left: int
    right: 'Pair | None'


@dataclasses.dataclass(frozen=True)
class Settings:
    count: ClassVar[int] = 0
    seed: dataclasses.InitVar[int] = 0
    _: KW_ONLY
    name: str = ''


@dataclasses.dataclass
class Options:
    path: str
    _: dataclasses.KW_ONLY
    verbose: 'bool' = False


class Closer(Protocol):
    def close(self) -> None: ...


class Holder:
    Alias = int
    held: Alias = 0


class Box[T]:
    item: T

    def get(self) -> T:
        return self.item

    def copy(self) -> Self:
        return self


def first[T](items: list[T]) -> T:
    return items[0]


def logged[**P, R](fn: Callable[P, R]) -> Callable[P, R]:
    def inner(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)
    return inner


def with_int[**P, R](fn: Callable[Concatenate[int, P], R]) -> Callable[P, R]: ...


def later(given: Later) -> 'Later': ...


class Later:
    pass
'''
# The positions VALID holds: 11 module variables; the attributes of Movie, Point, Pair, Settings,
# Options, Holder and Box; and the parameters and returns of close, get, copy, first, logged, inner,
# with_int and later.
VALID_POSITIONS = 11 + (3 + 2 + 2 + 4 + 3 + 1 + 1) + (1 + 1 + 1 + 2 + 2 + 3 + 2 + 2)


@pytest.mark.unit
@pytest.mark.parametrize('postponed', MODES)
def test_valid_shapes_pass(scratch: Scratch, postponed: bool) -> None:
    module = scratch.module(VALID, postponed)
    report = scratch.report()
    assert report['violations'] == []
    assert len([p for p in report['positions'] if p.startswith(f'{module}:')]) == VALID_POSITIONS


@pytest.mark.unit
def test_a_main_module_is_never_imported(scratch: Scratch) -> None:
    quiet, annotated = scratch.package(), scratch.package()
    scratch.member(quiet, {f'{quiet}/__init__.py': '', f'{quiet}/__main__.py': 'raise SystemExit("ran")\n'})
    scratch.member(annotated, {f'{annotated}/__init__.py': '',
                               f'{annotated}/__main__.py': 'held: int = 0\ndef run(given: str) -> None: ...\n'
                                                           'raise SystemExit("ran")\n'})
    violations = scratch.report()['violations']
    assert f'{quiet}.__main__' not in sys.modules and f'{annotated}.__main__' not in sys.modules
    assert [v.split(': ', 2)[1] for v in violations] == ['held', 'run(given)', 'run() ->'], violations
    assert all(v.startswith(f'{annotated}.__main__:') and 'a __main__ module' in v for v in violations), violations


@pytest.mark.unit
@pytest.mark.parametrize('directory', ['a-later', 'z-later'])
def test_a_member_added_later_is_checked(scratch: Scratch, directory: str) -> None:
    # The member added later sorts before the first one, then after it: it is checked in either place.
    first = scratch.module('held: int = 0\n', postponed=True, directory='m-first')
    assert scratch.report()['violations'] == []
    module = scratch.module(f'held: {SLICE} = {{}}\n', postponed=True, directory=directory)
    report = scratch.report()
    assert sorted(report['members']) == sorted(['.', 'packages/m-first', f'packages/{directory}'])
    assert {f'{first}:held', f'{module}:held'} <= set(report['positions'])
    assert len(report['violations']) == 1 and report['violations'][0].startswith(f'{module}:'), report['violations']


@pytest.mark.unit
@pytest.mark.parametrize('planted', ['a-member', 'm-member', 'z-member'])
def test_every_member_is_checked_whatever_its_place(scratch: Scratch, planted: str) -> None:
    modules = {d: scratch.module(f'held: {SLICE if d == planted else "int"} = 0\n', postponed=True, directory=d)
               for d in ('a-member', 'm-member', 'z-member')}
    report = scratch.report()
    assert {f'{m}:held' for m in modules.values()} <= set(report['positions'])
    assert len(report['violations']) == 1 and report['violations'][0].startswith(f'{modules[planted]}:2: held: '), \
        report['violations']


@pytest.mark.unit
@pytest.mark.parametrize(('files', 'module'), [
    pytest.param({'{p}/__init__.py': f'held: {SLICE} = {{}}\n'}, '{p}', id='package-init'),
    pytest.param({'{p}/__init__.py': '', '{p}/one/__init__.py': '', '{p}/one/two/__init__.py': '',
                  '{p}/one/two/three/__init__.py': '', '{p}/one/two/three/mod.py': f'held: {SLICE} = {{}}\n'},
                 '{p}.one.two.three.mod', id='depth-five'),
    pytest.param({'{p}/one/two/mod.py': f'held: {SLICE} = {{}}\n'}, '{p}.one.two.mod', id='namespace-packages'),
    pytest.param({'{p}/__init__.py': '', '{p}/_private.py': f'held: {SLICE} = {{}}\n'}, '{p}._private',
                 id='private-module'),
    pytest.param({'{p}/__init__.py': '', '{p}/broken.py': 'def (:\n'}, '{p}.broken', id='does-not-parse'),
])
def test_every_module_of_a_member_is_read(scratch: Scratch, files: dict[str, str], module: str) -> None:
    package = scratch.package()
    scratch.member(package, {name.format(p=package): text for name, text in files.items()})
    violations = scratch.report()['violations']
    assert len(violations) == 1 and violations[0].startswith(f'{module.format(p=package)}:'), violations
    assert 'slice' in violations[0] or 'does not parse' in violations[0], violations


@pytest.mark.unit
def test_the_root_and_every_members_glob_are_read(scratch: Scratch) -> None:
    rooted, extra = scratch.package(), scratch.package()
    scratch.root_files({f'{rooted}/__init__.py': '', f'{rooted}/mod.py': f'held: {SLICE} = {{}}\n'})
    home = scratch.root / 'extra' / 'more'
    (home / 'src' / extra).mkdir(parents=True)
    (home / 'pyproject.toml').write_text('[project]\nname = "more"\nversion = "0"\n')
    (home / 'src' / extra / '__init__.py').write_text('')
    (home / 'src' / extra / 'mod.py').write_text(f'held: {SLICE} = {{}}\n')
    scratch.importable(home / 'src')
    scratch.workspace(members=('packages/*', 'extra/*'))
    report = scratch.report()
    assert sorted(report['members']) == ['.', 'extra/more']
    assert sorted(v.split(':', 1)[0] for v in report['violations']) == sorted([f'{rooted}.mod', f'{extra}.mod'])


@pytest.mark.unit
def test_an_excluded_member_is_not_checked(scratch: Scratch) -> None:
    kept = scratch.module('held: int = 0\n', postponed=True)
    left = scratch.module(f'held: {SLICE} = {{}}\n', postponed=True)
    scratch.workspace(exclude=(f'packages/{left.split(".")[0]}',))
    report = scratch.report()
    assert report['violations'] == []
    assert sorted(report['members']) == ['.', f'packages/{kept.split(".")[0]}']


@pytest.mark.unit
def test_a_module_imported_from_elsewhere_is_refused(scratch: Scratch) -> None:
    home = scratch.member(scratch.package(), {'json.py': 'held: int = 0\n'})
    violations = scratch.report()['violations']
    assert violations == [f'json: importing it loads {json.__file__}, not {home.resolve() / "src" / "json.py"}, so the check '
                          'would read one file and evaluate another']


def _recursive_alias() -> Any:
    namespace: dict[str, Any] = {}
    exec('type Tree = list[Tree] | int', namespace)
    return namespace['Tree']


P = typing.ParamSpec('P')


class OverParamSpec(typing.Generic[P]):
    pass


@pytest.mark.unit
@pytest.mark.parametrize(('hint', 'kind', 'fragment'), [
    pytest.param(slice(int, None, None), VARIABLE, 'resolves to a slice, not a type', id='slice'),
    pytest.param(3, VARIABLE, 'resolves to a int, not a type: 3', id='number'),
    pytest.param(len, PARAMETER, 'resolves to a builtin_function_or_method, not a type', id='function'),
    pytest.param('str', RETURN, 'resolves to a str left unresolved', id='leftover-string'),
    pytest.param(typing.ForwardRef('Missing'), RETURN, 'resolves to a ForwardRef left unresolved', id='forward-ref'),
    pytest.param(Ellipsis, VARIABLE, 'resolves to an Ellipsis outside', id='ellipsis'),
    pytest.param([int], PARAMETER, 'resolves to a list, valid only as the parameters', id='bare-list'),
    pytest.param(dict[str, slice(int, None, None)], VARIABLE, 'holds a slice, not a type', id='nested-slice'),
    pytest.param(typing.Final[slice(int, None, None)], VARIABLE, 'holds a slice, not a type', id='final-slice'),
    pytest.param(dict[str, [int]], VARIABLE, 'holds a list, valid only as the parameters', id='unhashable-list'),
    pytest.param(dict[P.args, slice(int, None, None)], VARIABLE, 'holds a slice', id='beside-paramspec-args'),
    pytest.param(typing.Annotated[int, slice(1, None, None)], PARAMETER, 'slice in its Annotated metadata',
                 id='annotated-metadata-slice'),
    pytest.param(typing.Annotated[slice(1, None, None), 'meta'], PARAMETER, 'holds a slice, not a type',
                 id='annotated-slice'),
    pytest.param(typing.Literal[1.5], VARIABLE, 'holds a float in a Literal', id='literal-float'),
    pytest.param(typing.Union, VARIABLE, 'unsubscripted special form', id='bare-union'),
    pytest.param(typing.Optional, VARIABLE, 'unsubscripted special form', id='bare-optional'),
    pytest.param(typing.Literal, VARIABLE, 'unsubscripted special form', id='bare-literal'),
    pytest.param(collections.abc.Callable[[slice(1, None, None)], int], PARAMETER, 'holds a slice', id='callable-slice'),
    pytest.param(typing.TypeAliasType('Sliced', dict[str, slice(int, None, None)]), VARIABLE, 'holds a slice',
                 id='alias-value'),
    pytest.param(typing.NewType('Sliced', slice(int, None, None)), VARIABLE, 'holds a slice', id='newtype-supertype'),
    pytest.param(typing.Final[int], PARAMETER, 'qualifier Final on a parameter', id='final-parameter'),
    pytest.param(typing.ClassVar[int], RETURN, 'qualifier ClassVar on a return', id='classvar-return'),
    pytest.param(typing.Required[int], VARIABLE, 'qualifier Required on a variable', id='required-variable'),
    pytest.param(list[typing.Final[int]], VARIABLE, 'qualifier Final below the top', id='qualifier-nested'),
    pytest.param(dataclasses.InitVar[int], PARAMETER, 'qualifier InitVar on a parameter', id='initvar-parameter'),
    pytest.param(dataclasses.KW_ONLY, PARAMETER, 'qualifier KW_ONLY on a parameter', id='kw-only-parameter'),
    pytest.param(list[dataclasses.KW_ONLY], ATTRIBUTE, 'qualifier KW_ONLY below the top', id='kw-only-nested'),
])
def test_non_types_are_named(hint: Any, kind: str, fragment: str) -> None:
    found = type_expression_violations(hint, kind)
    assert any(fragment in why for why in found), found
    # The valid neighbours of the shapes above pass, an unhashable ParamSpec part and a recursive alias included.
    for valid in (int, None, typing.Any, typing.Self, P, P.args, P.kwargs, list[int], int | None,
                  typing.Literal['a', 1, None], collections.abc.Callable[..., int],
                  collections.abc.Callable[P, int], collections.abc.Callable[typing.Concatenate[int, P], int],
                  tuple[int, ...], tuple[()], OverParamSpec[[int, str]], _recursive_alias(),
                  typing.Annotated[int, 'meta'], typing.NewType('UserId', int)):
        assert type_expression_violations(valid, PARAMETER) == [], valid
    for valid in (typing.Final, typing.Final[int], typing.ClassVar[int], typing.Required[int],
                  dataclasses.InitVar[int], dataclasses.KW_ONLY):
        assert type_expression_violations(valid, ATTRIBUTE) == [], valid
