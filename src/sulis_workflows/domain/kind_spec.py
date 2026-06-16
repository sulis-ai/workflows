"""Typed in-memory shape of a parsed Kind YAML (WP-1).

A Kind YAML on disk is user-authored YAML. The Kind compiler (WP-3)
operates on the typed, validated shape declared in this module. The
parser at :mod:`sulis_workflows.domain.kind_yaml_parser` is what
turns the bytes into one of these.

Shapes mirror ``.specifications/kinds-and-tools/KIND_SCHEMA.md`` §4-§10:

- :class:`KindSpec` — top-level document.
- :class:`KindMetadata` — the ``metadata`` block.
- :class:`KindSpecBody` — the ``spec`` block (the four-stage variant).
- :class:`FindStage`, :class:`GenerateStage`, :class:`EvaluateStage`,
  :class:`DecideStage` — the four stage blocks.
- :class:`Maturity` — alpha / beta / stable, aligned with the
  manifest engine's apiVersion suffix convention.

All shapes are frozen dataclasses. ``list`` fields are normalised to
``tuple`` on construction so the spec is hashable end-to-end. Nested
mappings (e.g., ``output_artifacts`` entries) are stored as plain
dicts because heterogeneous downstream consumers want the dict shape;
shallow normalisation is enough for slice-1 immutability needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

__all__ = [
    "DecideStage",
    "EvaluateStage",
    "FindStage",
    "GenerateStage",
    "KindMetadata",
    "KindSpec",
    "KindSpecBody",
    "Maturity",
    "StagePrimitiveName",
]


# A stage-primitive name as referenced by ``spec.find.toolkit``. Kept as
# a plain string alias for slice-1 — WP-5 and WP-6 publish the catalogue
# that future maturity will validate against.
StagePrimitiveName = str


class Maturity(str, Enum):
    """Concrete-Kind maturity (alpha/beta/stable).

    Aligns with the manifest engine's apiVersion suffix convention. Per
    KIND_SCHEMA.md §3, this is the studio version's stability band, not
    the meta-schema version.
    """

    ALPHA = "alpha"
    BETA = "beta"
    STABLE = "stable"


@dataclass(frozen=True)
class KindMetadata:
    """The ``metadata`` block of a Kind YAML (KIND_SCHEMA §5).

    Attributes
    ----------
    name:
        Required. Instance name (snake_case or kebab-case). Together with
        ``apiVersion`` + ``kind`` uniquely identifies the Kind YAML.
    version:
        Required. The Kind's own semver version (e.g., ``1.0.0``).
        Distinct from ``apiVersion``'s studio version.
    description:
        Declared. Free-form markdown description.
    maturity:
        Declared in slice 1. Derived from the apiVersion's version
        suffix (``v1alpha1`` → :attr:`Maturity.ALPHA`, etc.). Materialised
        here so consumers don't need to re-parse the apiVersion string.
    owner:
        Declared. Team or person responsible.
    status:
        Declared. Author-declared lifecycle status (``draft`` /
        ``provisional`` / ``stable`` / ``deprecated``).
    """

    name: str
    version: str
    description: str | None = None
    maturity: Maturity = Maturity.ALPHA
    owner: str | None = None
    status: str | None = None


@dataclass(frozen=True)
class FindStage:
    """The ``spec.find`` block (KIND_SCHEMA §7).

    Attributes
    ----------
    toolkit:
        Required (slice 1). Tuple of stage-primitive names available to
        find. Stored as a tuple so the stage is hashable.
    inputs_to_scan:
        Required (slice 1). Tuple of workspace paths/globs.
    output_artifacts:
        Required (slice 1). Tuple of artifact-descriptor dicts (each
        carries ``path`` and optional ``schema_ref``).
    purpose:
        Declared. One-sentence statement of what find produces.
    context_budget:
        ``warned`` in slice 1 (NFR-9 wires it). Mapping of ``{tokens: int}``.
    """

    toolkit: tuple[StagePrimitiveName, ...]
    inputs_to_scan: tuple[str, ...]
    output_artifacts: tuple[dict[str, Any], ...]
    purpose: str | None = None
    context_budget: dict[str, Any] | None = None


@dataclass(frozen=True)
class GenerateStage:
    """The ``spec.generate`` block (KIND_SCHEMA §8).

    All slice-1 fields are ``declared``. Slice 2 graduates
    ``target_file``.
    """

    target_file: str | None = None
    spec_ref: str | None = None
    inputs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    token_budget: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvaluateStage:
    """The ``spec.evaluate`` block (KIND_SCHEMA §9).

    All slice-1 fields are ``declared``. Slice 3 graduates several.
    """

    rubric_ref: str | None = None
    verdict_path: str | None = None
    blocking_criteria: tuple[str, ...] = ()
    verdict_schema_version: str | None = None
    token_budget: dict[str, Any] | None = None


@dataclass(frozen=True)
class DecideStage:
    """The ``spec.decide`` block (KIND_SCHEMA §10).

    All slice-1 fields are ``declared``. Slice 4 graduates several.
    ``on_max_iterations`` is restricted to the single value ``"stop"``
    in slice 1; future maturity may add additional values.
    """

    max_iterations: int | None = None
    on_max_iterations: str | None = None
    five_whys_iterations: int | None = None
    reason_class_routing: dict[str, Any] | None = None


@dataclass(frozen=True)
class KindSpecBody:
    """The ``spec`` block of a Kind YAML (KIND_SCHEMA §6).

    For four-stage Kinds (Goal, PostObjective, OutcomeTarget, ...) the
    body has up to four stages plus a few cross-cutting fields. For
    ChainKind the body is opaque at slice 1 (parsed but not compiled).
    """

    find: FindStage | None = None
    generate: GenerateStage | None = None
    evaluate: EvaluateStage | None = None
    decide: DecideStage | None = None
    nfr_overrides: dict[str, Any] | None = None
    toolkit: tuple[StagePrimitiveName, ...] | None = None
    max_iterations: int | None = None


@dataclass(frozen=True)
class KindSpec:
    """The top-level shape of a parsed Kind YAML (KIND_SCHEMA §4).

    Attributes
    ----------
    api_version:
        Required. ``{studio-slug}/{version}`` shape (KIND_SCHEMA §4).
    kind:
        Required. Concrete kind name (e.g., ``Goal``). No suffix.
    metadata:
        Required. See :class:`KindMetadata`.
    spec:
        Required. See :class:`KindSpecBody`.
    source_path:
        Origin path the parser was handed. Captured for error
        provenance and watchdog reporting. Not part of the schema.
    raw_declared_fields:
        Tuple of field paths that were populated at the ``declared``
        maturity tier. Drives the stale-field watchdog (NFR-18). The
        parser populates this on construction.
    """

    api_version: str
    kind: str
    metadata: KindMetadata
    spec: KindSpecBody
    source_path: str = ""
    raw_declared_fields: tuple[str, ...] = field(default_factory=tuple)
