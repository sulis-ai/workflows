"""The spec §8 expression grammar: a tokenizer, a recursive-descent parser, a type
checker against declared inputs/host inputs/state channels/step outputs, and a pure
evaluator. Expressions appear in `if`, `precondition`, `person_required_when` and
fitness thresholds (spec §8); this module implements the grammar generically, once,
for every one of those sites to reuse — "hold conventions once" (CLAUDE.md).

No ``sulis.`` import, no vendor SDK (WP-01 A5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, Union

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.model import GateNode, Process, StepNode
from sulis_workflows.definition.registry import Registry

__all__ = [
    "ABSENT",
    "Path",
    "Literal",
    "ExistsCall",
    "LenCall",
    "Not",
    "And",
    "Or",
    "Compare",
    "Expr",
    "parse",
    "TString",
    "TInteger",
    "TNumber",
    "TBoolean",
    "TAny",
    "TEnum",
    "TList",
    "TMap",
    "TProfile",
    "Type",
    "parse_type",
    "TypeContext",
    "infer_type",
    "evaluate",
]

# --------------------------------------------------------------------------- lexer --

# `ident` allows an internal hyphen so a path segment can name a node id — every
# node id in this format's own examples is kebab-case (e.g. `after-interrogate`),
# and `steps.<node>.*` paths need to be able to reference one. The grammar (§8)
# never shows a hyphenated path segment because its own worked expressions only
# read `state.*` channels, which happen to be written snake_case — but nothing in
# §8 restricts `ident` to that, and there is no subtraction operator in this
# grammar for a hyphen to collide with.
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
    |(?P<number>\d+\.\d+|\d+)
    |(?P<string>"(?:[^"\\]|\\.)*")
    |(?P<op>==|!=|<=|>=|<|>)
    |(?P<punct>[()\[\],.])
    |(?P<ident>[A-Za-z_][A-Za-z0-9_-]*)
    """,
    re.VERBOSE,
)

_KEYWORDS = {"and", "or", "not", "in", "true", "false", "null", "exists", "len"}


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str  # number | string | op | punct | ident | keyword | end
    text: str
    pos: int


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match:
            raise DefinitionError(f"unexpected character {text[pos]!r} at position {pos} in {text!r}", rule="V5")
        pos = match.end()
        if match.lastgroup == "ws":
            continue
        kind = match.lastgroup
        value = match.group(kind)
        if kind == "ident" and value in _KEYWORDS:
            kind = "keyword"
        tokens.append(_Token(kind=kind, text=value, pos=match.start()))
    tokens.append(_Token(kind="end", text="", pos=len(text)))
    return tokens


def _unescape_string(literal: str) -> str:
    body = literal[1:-1]
    return body.replace('\\"', '"').replace("\\\\", "\\")


# ----------------------------------------------------------------------------- AST --


@dataclass(frozen=True, slots=True)
class Path:
    segments: tuple[Union[str, int], ...]

    def __str__(self) -> str:  # pragma: no cover - debug convenience
        out = ""
        for seg in self.segments:
            if isinstance(seg, int):
                out += f"[{seg}]"
            else:
                out += f".{seg}" if out else seg
        return out


@dataclass(frozen=True, slots=True)
class Literal:
    value: Any  # str | int | float | bool | None | list


@dataclass(frozen=True, slots=True)
class ExistsCall:
    path: Path


@dataclass(frozen=True, slots=True)
class LenCall:
    path: Path


@dataclass(frozen=True, slots=True)
class Not:
    operand: "Expr"


@dataclass(frozen=True, slots=True)
class And:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True, slots=True)
class Or:
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True, slots=True)
class Compare:
    left: "Expr"
    op: str | None  # ==, !=, <, <=, >, >=, in — None means "bare value, no comparison"
    right: "Expr | None"


Expr = Union[Or, And, Not, Compare, Path, Literal, ExistsCall, LenCall]


# ---------------------------------------------------------------------------- parser --


class _Parser:
    def __init__(self, tokens: list[_Token], source: str) -> None:
        self._tokens = tokens
        self._i = 0
        self._source = source

    def _peek(self) -> _Token:
        return self._tokens[self._i]

    def _advance(self) -> _Token:
        token = self._tokens[self._i]
        self._i += 1
        return token

    def _expect(self, kind: str, text: str | None = None) -> _Token:
        token = self._peek()
        if token.kind != kind or (text is not None and token.text != text):
            raise DefinitionError(
                f"expected {text or kind!r} but found {token.text or '<end>'!r} at position {token.pos} "
                f"in {self._source!r}",
                rule="V5",
            )
        return self._advance()

    def parse_expr(self) -> Expr:
        node = self._parse_or()
        self._expect("end")
        return node

    def _parse_or(self) -> Expr:
        left = self._parse_and()
        while self._peek().kind == "keyword" and self._peek().text == "or":
            self._advance()
            left = Or(left, self._parse_and())
        return left

    def _parse_and(self) -> Expr:
        left = self._parse_not()
        while self._peek().kind == "keyword" and self._peek().text == "and":
            self._advance()
            left = And(left, self._parse_not())
        return left

    def _parse_not(self) -> Expr:
        if self._peek().kind == "keyword" and self._peek().text == "not":
            self._advance()
            return Not(self._parse_not())
        return self._parse_cmp()

    _COMPARE_OPS = {"==", "!=", "<", "<=", ">", ">="}

    def _parse_cmp(self) -> Expr:
        left = self._parse_value()
        token = self._peek()
        op: str | None = None
        if token.kind == "op" and token.text in self._COMPARE_OPS:
            op = self._advance().text
        elif token.kind == "keyword" and token.text == "in":
            op = self._advance().text
        if op is None:
            return Compare(left, None, None)
        right = self._parse_value()
        return Compare(left, op, right)

    def _parse_value(self) -> Expr:
        token = self._peek()
        if token.kind == "punct" and token.text == "(":
            self._advance()
            inner = self._parse_or()
            self._expect("punct", ")")
            return inner
        if token.kind == "keyword" and token.text == "exists":
            self._advance()
            self._expect("punct", "(")
            path = self._parse_path()
            self._expect("punct", ")")
            return ExistsCall(path)
        if token.kind == "keyword" and token.text == "len":
            self._advance()
            self._expect("punct", "(")
            path = self._parse_path()
            self._expect("punct", ")")
            return LenCall(path)
        if token.kind == "keyword" and token.text in ("true", "false"):
            self._advance()
            return Literal(token.text == "true")
        if token.kind == "keyword" and token.text == "null":
            self._advance()
            return Literal(None)
        if token.kind == "string":
            self._advance()
            return Literal(_unescape_string(token.text))
        if token.kind == "number":
            self._advance()
            return Literal(float(token.text) if "." in token.text else int(token.text))
        if token.kind == "punct" and token.text == "[":
            return self._parse_list_literal()
        if token.kind == "ident":
            return self._parse_path()
        raise DefinitionError(
            f"unexpected token {token.text or '<end>'!r} at position {token.pos} in {self._source!r}", rule="V5"
        )

    def _parse_list_literal(self) -> Literal:
        self._expect("punct", "[")
        items: list[Any] = []
        if not (self._peek().kind == "punct" and self._peek().text == "]"):
            items.append(self._parse_literal_value())
            while self._peek().kind == "punct" and self._peek().text == ",":
                self._advance()
                items.append(self._parse_literal_value())
        self._expect("punct", "]")
        return Literal(items)

    def _parse_literal_value(self) -> Any:
        token = self._peek()
        if token.kind == "keyword" and token.text in ("true", "false"):
            self._advance()
            return token.text == "true"
        if token.kind == "keyword" and token.text == "null":
            self._advance()
            return None
        if token.kind == "string":
            self._advance()
            return _unescape_string(token.text)
        if token.kind == "number":
            self._advance()
            return float(token.text) if "." in token.text else int(token.text)
        if token.kind == "punct" and token.text == "[":
            return self._parse_list_literal().value
        raise DefinitionError(
            f"expected a literal value but found {token.text or '<end>'!r} at position {token.pos} "
            f"in {self._source!r}",
            rule="V5",
        )

    def _parse_path(self) -> Path:
        segments: list[Union[str, int]] = [self._expect("ident").text]
        while True:
            token = self._peek()
            if token.kind == "punct" and token.text == ".":
                self._advance()
                segments.append(self._expect("ident").text)
            elif token.kind == "punct" and token.text == "[":
                self._advance()
                index_token = self._expect("number")
                if "." in index_token.text:
                    raise DefinitionError(
                        f"a path index must be an integer, got {index_token.text!r} in {self._source!r}", rule="V5"
                    )
                self._expect("punct", "]")
                segments.append(int(index_token.text))
            else:
                break
        return Path(tuple(segments))


def parse(text: str) -> Expr:
    """Parse a spec §8 expression. Refuses (rule V5) anything that doesn't match
    the grammar — an unexpected character, an incomplete comparison, an
    unterminated call or list."""

    if not text or not text.strip():
        raise DefinitionError("an expression must not be empty", rule="V5")
    return _Parser(_tokenize(text), text).parse_expr()


# ------------------------------------------------------------------------------ types --


@dataclass(frozen=True, slots=True)
class TString:
    pass


@dataclass(frozen=True, slots=True)
class TInteger:
    pass


@dataclass(frozen=True, slots=True)
class TNumber:
    pass


@dataclass(frozen=True, slots=True)
class TBoolean:
    pass


@dataclass(frozen=True, slots=True)
class TAny:
    pass


@dataclass(frozen=True, slots=True)
class TEnum:
    members: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TList:
    item: "Type"


@dataclass(frozen=True, slots=True)
class TMap:
    item: "Type"


@dataclass(frozen=True, slots=True)
class TProfile:
    ref: str


Type = Union[TString, TInteger, TNumber, TBoolean, TAny, TEnum, TList, TMap, TProfile]

_ENUM_RE = re.compile(r"^enum\[\s*([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)*)\s*\]$")


def parse_type(type_string: str) -> Type:
    """Parse a spec §2.1 type string into a :class:`Type`. The JSON Schema layer
    (schema/*.v1.schema.json) already constrains the syntax; this just structures
    it for the type checker below."""

    if type_string == "string":
        return TString()
    if type_string == "integer":
        return TInteger()
    if type_string == "number":
        return TNumber()
    if type_string == "boolean":
        return TBoolean()
    if type_string == "any":
        return TAny()
    match = _ENUM_RE.match(type_string)
    if match:
        return TEnum(tuple(m.strip() for m in match.group(1).split(",")))
    if type_string.startswith("list<") and type_string.endswith(">"):
        return TList(parse_type(type_string[len("list<") : -1]))
    if type_string.startswith("map<") and type_string.endswith(">"):
        return TMap(parse_type(type_string[len("map<") : -1]))
    if type_string.startswith("profile:"):
        return TProfile(type_string[len("profile:") :])
    raise DefinitionError(f"not a recognised type string: {type_string!r}", rule="V5")


# ------------------------------------------------------------------------ type context --


class TypeContext:
    """Resolves a §8 :class:`Path` to its declared :class:`Type` within one Process
    — `inputs.*`, `host.*`, `state.*`, and `steps.<node>.*` (spec §2.2). Building
    `steps.<node>.output.<name>`'s type means resolving that node's Tool through
    the registry, so this context needs one."""

    def __init__(self, process: Process, registry: Registry) -> None:
        self._process = process
        self._registry = registry

    def resolve(self, path: Path) -> Type:
        segments = path.segments
        if not segments or not isinstance(segments[0], str):
            raise DefinitionError(f"not a resolvable path: {path}", rule="V5")
        root = segments[0]
        rest = segments[1:]

        if root == "inputs":
            return self._from_input_map(self._process.inputs, rest, path)
        if root == "host":
            return self._from_input_map(self._process.host_inputs, rest, path)
        if root == "state":
            return self._from_state(rest, path)
        if root == "steps":
            return self._from_steps(rest, path)
        raise DefinitionError(f"unrecognised path root {root!r} in {path}", rule="V5")

    def _from_input_map(self, inputs: Mapping[str, Any], rest: Sequence[Any], path: Path) -> Type:
        if not rest or not isinstance(rest[0], str) or rest[0] not in inputs:
            raise DefinitionError(f"undeclared path: {path}", rule="V5")
        return parse_type(inputs[rest[0]].type)

    def _from_state(self, rest: Sequence[Any], path: Path) -> Type:
        if not rest or not isinstance(rest[0], str) or rest[0] not in self._process.state:
            raise DefinitionError(f"undeclared state channel in path: {path}", rule="V5")
        return parse_type(self._process.state[rest[0]].type)

    def _from_steps(self, rest: Sequence[Any], path: Path) -> Type:
        if len(rest) < 2 or not isinstance(rest[0], str):
            raise DefinitionError(f"a steps.* path needs a node id and a field: {path}", rule="V5")
        node_id, field = rest[0], rest[1]
        node = self._process.nodes.get(node_id)
        if node is None:
            raise DefinitionError(f"unknown node {node_id!r} in path: {path}", rule="V5")

        if field == "attempt":
            return TInteger()
        if field == "decided_by":
            return TString()
        if field == "controls":
            if len(rest) != 4 or rest[3] != "passed":
                raise DefinitionError(f"steps.<node>.controls.<control>.passed is the only shape: {path}", rule="V5")
            return TBoolean()
        if field == "verdict":
            if isinstance(node, GateNode):
                return TEnum(("PERMIT", "DENY", "INDETERMINATE"))
            raise DefinitionError(
                f"steps.{node_id}.verdict has no declared type for a non-GATE node: {path}", rule="V5"
            )
        if field == "output":
            if len(rest) != 3 or not isinstance(rest[2], str):
                raise DefinitionError(f"steps.<node>.output.<name> is the only shape: {path}", rule="V5")
            if not isinstance(node, StepNode):
                raise DefinitionError(f"steps.{node_id}.output.* only exists on a STEP node: {path}", rule="V5")
            tool = self._registry.resolve("TOOL", node.tool)
            output_name = rest[2]
            if output_name not in tool.output:
                raise DefinitionError(
                    f"tool {node.tool!r} has no output {output_name!r} (path: {path})", rule="V5"
                )
            return parse_type(tool.output[output_name].type)
        raise DefinitionError(f"unrecognised steps.* field {field!r} in path: {path}", rule="V5")


# ----------------------------------------------------------------------- type checker --

_ORDERING_OPS = {"<", "<=", ">", ">="}
_EQUALITY_OPS = {"==", "!="}
_NUMERIC_TYPES = (TInteger, TNumber)


def _literal_type(value: Any) -> Type:
    if isinstance(value, bool):
        return TBoolean()
    if isinstance(value, int):
        return TInteger()
    if isinstance(value, float):
        return TNumber()
    if isinstance(value, str):
        return TString()
    if value is None:
        return TAny()
    if isinstance(value, list):
        return TList(TAny())
    raise DefinitionError(f"not a representable literal: {value!r}", rule="V5")


def _check_enum_membership(left: Expr, left_t: Type, right: Expr, right_t: Type) -> None:
    for enum_expr, enum_t, other_expr in ((left, left_t, right), (right, right_t, left)):
        if isinstance(enum_t, TEnum) and isinstance(other_expr, Literal) and isinstance(other_expr.value, str):
            if other_expr.value not in enum_t.members:
                raise DefinitionError(
                    f"{other_expr.value!r} is not a member of enum[{', '.join(enum_t.members)}]", rule="V5"
                )


def infer_type(expr: Expr, ctx: TypeContext) -> Type:
    """Infers `expr`'s type, type-checking every path it touches against `ctx`
    along the way. Raises :class:`DefinitionError` (rule V5) for an untyped path
    or a value compared against a type it cannot be compared with — including
    spec §8's named case, an enum path compared with a value outside it."""

    if isinstance(expr, Literal):
        return _literal_type(expr.value)
    if isinstance(expr, Path):
        return ctx.resolve(expr)
    if isinstance(expr, ExistsCall):
        ctx.resolve(expr.path)
        return TBoolean()
    if isinstance(expr, LenCall):
        ctx.resolve(expr.path)
        return TInteger()
    if isinstance(expr, Not):
        infer_type(expr.operand, ctx)
        return TBoolean()
    if isinstance(expr, (And, Or)):
        infer_type(expr.left, ctx)
        infer_type(expr.right, ctx)
        return TBoolean()
    if isinstance(expr, Compare):
        left_t = infer_type(expr.left, ctx)
        if expr.op is None:
            return left_t
        right_t = infer_type(expr.right, ctx)  # type: ignore[arg-type]
        if expr.op in _EQUALITY_OPS:
            _check_enum_membership(expr.left, left_t, expr.right, right_t)  # type: ignore[arg-type]
        elif expr.op in _ORDERING_OPS:
            both_numeric = isinstance(left_t, _NUMERIC_TYPES) and isinstance(right_t, _NUMERIC_TYPES)
            both_string = isinstance(left_t, TString) and isinstance(right_t, TString)
            if not (both_numeric or both_string):
                raise DefinitionError(
                    f"cannot order-compare {left_t!r} and {right_t!r} with {expr.op!r} — "
                    "this expression cannot be evaluated",
                    rule="V5",
                )
        elif expr.op == "in":
            if not isinstance(right_t, TList):
                raise DefinitionError(
                    f"the right side of 'in' must be a list, got {right_t!r} — this expression cannot be evaluated",
                    rule="V5",
                )
        return TBoolean()
    raise DefinitionError(f"not a recognised expression node: {expr!r}", rule="V5")


# --------------------------------------------------------------------------- evaluator --

ABSENT = object()
"""Sentinel: a path resolves to nothing (spec §8 — absent, never an error)."""


def _resolve_path_value(path: Path, state: Mapping[str, Any]) -> Any:
    current: Any = state
    for segment in path.segments:
        if isinstance(segment, int):
            if not isinstance(current, (list, tuple)) or not (-len(current) <= segment < len(current)):
                return ABSENT
            current = current[segment]
        else:
            if not isinstance(current, Mapping) or segment not in current:
                return ABSENT
            current = current[segment]
    return current


def evaluate(expr: Expr, state: Mapping[str, Any]) -> Any:
    """Pure evaluation of an already type-checked expression against run state
    (nested dicts/lists matching the paths' segments — the same shape whatever the
    root prefix, since `inputs`/`host`/`state`/`steps` are ordinary top-level keys
    to this function, not something it treats specially).

    Comparing an absent value is false, never an error (spec §8); `exists(p)` is
    true only when `p` is present and not null."""

    if isinstance(expr, Literal):
        return expr.value
    if isinstance(expr, Path):
        value = _resolve_path_value(expr, state)
        return None if value is ABSENT else value
    if isinstance(expr, ExistsCall):
        value = _resolve_path_value(expr.path, state)
        return value is not ABSENT and value is not None
    if isinstance(expr, LenCall):
        value = _resolve_path_value(expr.path, state)
        if value is ABSENT:
            return 0
        return len(value)
    if isinstance(expr, Not):
        return not bool(evaluate(expr.operand, state))
    if isinstance(expr, And):
        return bool(evaluate(expr.left, state)) and bool(evaluate(expr.right, state))
    if isinstance(expr, Or):
        return bool(evaluate(expr.left, state)) or bool(evaluate(expr.right, state))
    if isinstance(expr, Compare):
        left_value = _resolve_path_value(expr.left, state) if isinstance(expr.left, Path) else evaluate(
            expr.left, state
        )
        if expr.op is None:
            return None if left_value is ABSENT else left_value
        right_value = (
            _resolve_path_value(expr.right, state) if isinstance(expr.right, Path) else evaluate(expr.right, state)
        )
        if left_value is ABSENT or right_value is ABSENT:
            return False
        if expr.op == "==":
            return left_value == right_value
        if expr.op == "!=":
            return left_value != right_value
        if expr.op == "<":
            return left_value < right_value
        if expr.op == "<=":
            return left_value <= right_value
        if expr.op == ">":
            return left_value > right_value
        if expr.op == ">=":
            return left_value >= right_value
        if expr.op == "in":
            return left_value in right_value
        raise DefinitionError(f"unknown comparison operator {expr.op!r}", rule="V5")
    raise DefinitionError(f"not a recognised expression node: {expr!r}", rule="V5")
