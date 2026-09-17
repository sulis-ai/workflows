"""Resolves `id@version` references (spec §1.2) over an in-memory set of loaded
definitions — rule V2. Purely in-memory: this module does no file I/O of its own
(ports and adapters — reading definitions off disk is `load.py`'s job; the registry
only holds what it's given via :meth:`Registry.add`).

No ``sulis.`` import, no vendor SDK (WP-01 A5).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.definition.model import Definition

__all__ = ["ParsedRef", "Registry", "parse_ref"]

_REF_RE = re.compile(
    r"^(?P<id>[a-z][a-z0-9]*(?:-[a-z0-9]+)*)@(?P<caret>\^?)(?P<version>\d+(?:\.\d+){0,2})$"
)

Version = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ParsedRef:
    """One `id@version` reference, parsed but not yet resolved against a registry."""

    id: str
    caret: bool
    version: tuple[int, ...]  # 1-3 components, exactly as given


def parse_ref(ref: str) -> ParsedRef:
    """Parse `id@version` or `id@^version` (spec §1.2). Refuses (rule V2) anything
    that isn't that shape — a missing `@`, a non-kebab-case id, a non-numeric
    version — before any registry lookup is attempted. `version` may be partial
    (1-3 components); see :meth:`Registry.resolve` for how that resolves (D11)."""

    match = _REF_RE.match(ref)
    if not match:
        raise DefinitionError(f"not a valid id@version reference: {ref!r}", rule="V2")
    parts = tuple(int(p) for p in match.group("version").split("."))
    caret = match.group("caret") == "^"
    return ParsedRef(id=match.group("id"), caret=caret, version=parts)


def _caret_bounds(requested: tuple[int, ...]) -> tuple[Version, Version]:
    """node-semver caret-range semantics (github.com/npm/node-semver, "Caret
    Ranges") — not part of Semantic Versioning 2.0.0 itself, which defines version
    precedence and format but no range syntax. Cited here as the de facto
    convention spec §1.2's `^1.2` example matches; see spec §16/§18 (D10).

    ^1.2.3 := >=1.2.3 <2.0.0   ^0.2.3 := >=0.2.3 <0.3.0   ^0.0.3 := >=0.0.3 <0.0.4
    ^1.2   := >=1.2.0 <2.0.0   ^0.0   := >=0.0.0 <0.1.0   ^0     := >=0.0.0 <1.0.0
    The trailing zeros a short reference omits are wildcards, not zeros — that is
    what makes ^0.0 (precision 2) wider than ^0.0.3 (precision 3).
    """

    precision = len(requested)
    major = requested[0]
    minor = requested[1] if precision >= 2 else 0
    patch = requested[2] if precision >= 3 else 0
    lower: Version = (major, minor, patch)

    if major > 0:
        return lower, (major + 1, 0, 0)
    if precision >= 2 and minor > 0:
        return lower, (0, minor + 1, 0)
    if precision == 3:  # ^0.0.patch
        return lower, (0, 0, patch + 1)
    if precision == 2:  # ^0.0
        return lower, (0, 1, 0)
    return lower, (1, 0, 0)  # ^0


def _format_version(v: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in v)


class Registry:
    """An in-memory set of loaded definitions, resolvable by kind and `id@version`."""

    def __init__(self, definitions: Iterable[Definition] = ()) -> None:
        self._by_kind_id: dict[tuple[str, str], dict[Version, Definition]] = {}
        for definition in definitions:
            self.add(definition)

    def add(self, definition: Definition) -> None:
        header = definition.header
        version = tuple(int(p) for p in header.version.split("."))
        assert (
            len(version) == 3
        )  # the schema already enforces a full X.Y.Z header version
        self._by_kind_id.setdefault((header.kind, header.id), {})[version] = definition

    def __contains__(self, item: tuple[str, str]) -> bool:
        return item in self._by_kind_id

    def all(self, kind: str) -> Iterable[Definition]:
        """Every registered definition of `kind`, all versions. Used by checks
        that need the whole registered set rather than one resolved reference —
        e.g. V10's cross-process call-graph walk."""

        for (registered_kind, _id), versions in self._by_kind_id.items():
            if registered_kind == kind:
                yield from versions.values()

    def resolve(self, kind: str, ref: str) -> Definition:
        """Resolve `ref` (`id@version`, `id@partial`, or `id@^partial`) to the
        definition of the given `kind`. Refuses (rule V2) an unparseable
        reference, an id never registered under this kind, or a version/range
        nothing registered satisfies.

        A full three-component version with no `^` is an exact pin. Anything
        else — a caret range, or a bare partial version with no `^` at all —
        resolves to the *highest* registered version satisfying that precision
        (spec §1.2, D11): `^` only changes behaviour in front of a full version;
        in front of a partial one it is redundant, so `echo@1` and `echo@^1`
        resolve identically.
        """

        parsed = parse_ref(ref)
        key = (kind, parsed.id)
        versions = self._by_kind_id.get(key)
        if not versions:
            raise DefinitionError(
                f"{kind} '{parsed.id}' is not registered (reference {ref!r})", rule="V2"
            )

        is_exact_pin = not parsed.caret and len(parsed.version) == 3
        if not is_exact_pin:
            lower, upper = _caret_bounds(parsed.version)
            satisfying = sorted(v for v in versions if lower <= v < upper)
            if not satisfying:
                raise DefinitionError(
                    f"no registered version of {kind} '{parsed.id}' satisfies "
                    f"{ref!r} (registered: {', '.join(_format_version(v) for v in sorted(versions))})",
                    rule="V2",
                )
            return versions[satisfying[-1]]

        exact = versions.get(parsed.version)  # type: ignore[arg-type]
        if exact is None:
            raise DefinitionError(
                f"{kind} '{parsed.id}' version {_format_version(parsed.version)} is not registered "
                f"(reference {ref!r}; registered: {', '.join(_format_version(v) for v in sorted(versions))})",
                rule="V2",
            )
        return exact
