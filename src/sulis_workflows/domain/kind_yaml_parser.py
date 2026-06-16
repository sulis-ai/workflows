"""Canonical Kind YAML parser (WP-1).

The parser turns user-authored Kind YAML bytes/text into a typed
:class:`~sulis_workflows.domain.kind_spec.KindSpec` and validates
the document against the meta-schema declared in
``.specifications/kinds-and-tools/KIND_SCHEMA.md``.

It is the entry point of the Kind execution path (WP-3 onwards). Every
Kind-driven WP depends on it.

Design notes
------------

* **Safe by construction.** The parser uses ``yaml.safe_load`` via a
  bounded ``SafeLoader`` subclass — never ``yaml.load``. The classic
  ``!!python/object/apply:`` injection vector is refused at the loader
  level.

* **Bounds-consistent with the hashing primitive.** The 256 KiB input
  cap and the 1000-effective-alias-expansion cap are inherited from
  :mod:`sulis_workflows.domain.registry.hashing` (WP-AUTO-001 /
  SF-001). Authored YAML that the parser would refuse is also YAML the
  hash primitive would refuse — the two never disagree on hostile
  input.

* **Maturity-aware.** Per KIND_SCHEMA §2, every field carries a maturity
  tag (``required`` / ``warned`` / ``declared``). The parser raises on
  missing ``required`` fields, emits a warning event on missing
  ``warned`` fields, and accepts missing ``declared`` fields silently.

* **Closed top-level shape.** Unknown top-level fields raise. The
  ``traits`` field is recognised and rejected with a guidance-bearing
  error (KV-08).

* **Semver-validated.** ``metadata.version`` is parsed as semver
  per KIND_SCHEMA §5; non-conformant values raise.

The parser's instrumentation hookup is via :class:`ParserWarningSink`.
The in-memory sink ships with the parser; production use replaces it
with the observability port's sink (WP-8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

import yaml

from sulis_workflows.domain.kind_spec import (
    DecideStage,
    EvaluateStage,
    FindStage,
    GenerateStage,
    KindMetadata,
    KindSpec,
    KindSpecBody,
    Maturity,
)
from sulis_workflows.domain.yaml_input_limits import (
    MAX_YAML_INPUT_BYTES,
)

__all__ = [
    "InMemoryParserWarningSink",
    "KindYamlParser",
    "MAX_ANCHOR_EXPANSIONS",
    "MAX_YAML_INPUT_BYTES",
    "ParseError",
    "ParserWarningEvent",
    "ParserWarningSink",
    "StaleFieldReport",
    "UnknownTopLevelFieldError",
    "ValidationError",
]


# --- Bounds (consistent with hashing primitive's caps) ---------------------
#
# ``MAX_YAML_INPUT_BYTES`` is sourced from
# :mod:`sulis_workflows.domain.yaml_input_limits` — the single
# source of truth for the 256 KiB cap shared with the hashing primitive
# and the manifest-side ``yaml_parser`` adapter (WP-AUTO-014 Blue
# refactor). It is re-exported here for backwards compatibility with
# call sites that import directly from this module (e.g.
# :mod:`sulis.services.content.service_layer.kind_inputs_validator`).

# 1000 effective alias expansions. Same provenance as the byte cap —
# defence in depth against billion-laughs-style payloads.
MAX_ANCHOR_EXPANSIONS: int = 1000


# --- Semver pattern --------------------------------------------------------
#
# Reference: https://semver.org/spec/v2.0.0.html#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string
# Matches MAJOR.MINOR.PATCH plus optional pre-release / build metadata.
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


# --- apiVersion suffix → Maturity ------------------------------------------

_APIVERSION_MATURITY = {
    "v1alpha": Maturity.ALPHA,
    "v1beta": Maturity.BETA,
    "v1": Maturity.STABLE,
}


# --- Closed top-level shape ------------------------------------------------

_ALLOWED_TOP_LEVEL_FIELDS = frozenset({"apiVersion", "kind", "metadata", "spec"})
_ALLOWED_TOP_LEVEL_DECLARED = frozenset({"composes"})  # declared, accepted, unused
_REMOVED_TOP_LEVEL_FIELDS = frozenset({"traits"})


# --- Closed metadata shape -------------------------------------------------

_REQUIRED_METADATA_FIELDS = frozenset({"name", "version"})
_DECLARED_METADATA_FIELDS = frozenset({"description", "owner", "status"})


# --- Closed spec shape -----------------------------------------------------

_ALLOWED_SPEC_FIELDS = frozenset(
    {
        "find",
        "generate",
        "evaluate",
        "decide",
        "max_iterations",
        "nfr_overrides",
        "toolkit",
    }
)


# --- Closed stage shapes ---------------------------------------------------

_FIND_REQUIRED = ("toolkit", "inputs_to_scan", "output_artifacts")
_FIND_WARNED = ("context_budget",)
_FIND_DECLARED = ("purpose", "context")
_FIND_ALL = set(_FIND_REQUIRED) | set(_FIND_WARNED) | set(_FIND_DECLARED)


# --- Errors ----------------------------------------------------------------


class ParseError(Exception):
    """Raised on malformed YAML or missing required field.

    Attributes
    ----------
    field_path:
        Dotted path to the offending field (``"metadata.name"``,
        ``"spec.find.toolkit"``, etc.). Empty string when the failure
        is at the document level (e.g., garbage YAML).
    reason:
        Human-readable explanation.
    """

    def __init__(self, *, field_path: str, reason: str) -> None:
        self.field_path = field_path
        self.reason = reason
        if field_path:
            message = f"{reason} (field: {field_path})"
        else:
            message = reason
        super().__init__(message)


class ValidationError(Exception):
    """Raised on type or value-range violation of a present field.

    Distinct from :class:`ParseError` so consumers can differentiate
    "the field is missing" from "the field is the wrong type / value".
    """

    def __init__(self, *, field_path: str, reason: str) -> None:
        self.field_path = field_path
        self.reason = reason
        if field_path:
            message = f"{reason} (field: {field_path})"
        else:
            message = reason
        super().__init__(message)


class UnknownTopLevelFieldError(Exception):
    """Raised when an unknown top-level field appears.

    KindSpec is a closed shape — extension requires a meta-schema bump.
    """

    def __init__(self, *, field: str) -> None:
        self.field = field
        super().__init__(f"Unknown top-level field: {field!r}")


# --- Instrumentation -------------------------------------------------------


@dataclass(frozen=True)
class ParserWarningEvent:
    """Emitted when a ``warned``-maturity field is absent.

    Carries the dotted field path and a human-readable reason so the
    observability adapter (WP-8) can surface structured warnings.
    """

    field_path: str
    reason: str
    source_path: str = ""


class ParserWarningSink(Protocol):
    """Sink contract for parser warning events.

    Implementations MUST NOT raise on emit — the parser does not catch
    sink errors and a raise here would mask the underlying parse.
    """

    def emit(self, event: ParserWarningEvent) -> None: ...


class InMemoryParserWarningSink:
    """In-memory sink for tests and composition-root local development.

    Accumulates events in an ordered list. Production sinks publish to
    the observability port instead (WP-8).
    """

    def __init__(self) -> None:
        self._events: list[ParserWarningEvent] = []

    def emit(self, event: ParserWarningEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[ParserWarningEvent]:
        """Read-only view of accumulated events (caller must not mutate)."""
        return list(self._events)


# --- Stale-field watchdog --------------------------------------------------


@dataclass(frozen=True)
class StaleFieldReport:
    """One stale-field finding (NFR-18).

    A Kind whose ``declared``-tier field is populated but has not
    graduated to ``warned`` for longer than the configured threshold
    is reported here. The maintainer queue uses these to decide
    whether to graduate, drop, or document the field.
    """

    source_path: str
    field_path: str
    last_observed: datetime


# --- Bounded SafeLoader ----------------------------------------------------


class _BoundedSafeLoader(yaml.SafeLoader):
    """``yaml.SafeLoader`` subclass that caps effective alias expansion.

    Mirrors :class:`sulis_workflows.domain.registry.hashing._BoundedSafeLoader`
    — the two helpers are deliberately parallel so the parser and the
    hash primitive never disagree on what counts as hostile input.

    The cap is on the *expanded subtree size* charged against an alias,
    not the raw count of alias references, because the geometric blow-up
    in billion-laughs is in the expanded-tree walk that downstream
    consumers perform.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._effective_expansions: int = 0
        self._anchor_subtree_size: dict[str, int] = {}

    def compose_node(self, parent: Any, index: Any) -> Any:  # type: ignore[override]
        if self.check_event(yaml.events.AliasEvent):
            anchor = self.peek_event().anchor
            cost = self._anchor_subtree_size.get(anchor, 1)
            self._effective_expansions += cost
            if self._effective_expansions > MAX_ANCHOR_EXPANSIONS:
                raise ValueError(
                    f"Kind YAML alias expansion limit exceeded "
                    f"(> {MAX_ANCHOR_EXPANSIONS} effective nodes); "
                    f"refusing to parse"
                )
            return super().compose_node(parent, index)

        anchor = self.peek_event().anchor
        node = super().compose_node(parent, index)
        if anchor is not None and node is not None:
            self._anchor_subtree_size[anchor] = _subtree_size(node)
        return node


def _subtree_size(node: yaml.Node) -> int:
    """Return the expanded leaf count of a composed YAML node graph."""
    if isinstance(node, yaml.ScalarNode):
        return 1
    if isinstance(node, yaml.SequenceNode):
        return 1 + sum(_subtree_size(child) for child in node.value)
    if isinstance(node, yaml.MappingNode):
        return 1 + sum(_subtree_size(k) + _subtree_size(v) for k, v in node.value)
    return 1


# --- Parser ---------------------------------------------------------------


class KindYamlParser:
    """Parses Kind YAML text into a typed :class:`KindSpec`.

    Parameters
    ----------
    warning_sink:
        Optional. Sink for ``warned``-tier field absence events. When
        absent, warnings are discarded. Composition roots wire this to
        the observability port's sink (WP-8).
    """

    def __init__(self, warning_sink: ParserWarningSink | None = None) -> None:
        self._warning_sink = warning_sink

    async def parse(self, yaml_text: str, *, source_path: str) -> KindSpec:
        """Parse Kind YAML text into a typed :class:`KindSpec`.

        Parameters
        ----------
        yaml_text:
            Raw YAML text as authored on disk.
        source_path:
            Origin path. Used for error provenance and watchdog
            reporting. Not opened — the parser is given the bytes.

        Returns
        -------
        KindSpec
            Validated, typed Kind specification.

        Raises
        ------
        ParseError
            On malformed YAML, missing required fields, oversize input,
            or alias expansion above the cap.
        ValidationError
            On type or value-range violation of a present field.
        UnknownTopLevelFieldError
            On unknown top-level fields (KindSpec is closed).
        """
        # Size cap before any parsing. Bytes are the right unit because
        # the cap is consistent with the hashing primitive's cap (which
        # measures bytes).
        if len(yaml_text.encode("utf-8")) > MAX_YAML_INPUT_BYTES:
            raise ParseError(
                field_path="",
                reason=(
                    f"Kind YAML input size exceeds maximum of "
                    f"{MAX_YAML_INPUT_BYTES} bytes; refusing to parse"
                ),
            )

        document = self._load_yaml(yaml_text)
        declared_fields: list[str] = []
        return self._build_spec(document, source_path, declared_fields)

    async def watchdog_scan(
        self,
        kinds: list[tuple[KindSpec, datetime]],
        *,
        threshold_days: int = 180,
    ) -> list[StaleFieldReport]:
        """Report Kinds whose declared-tier fields are stale.

        Parameters
        ----------
        kinds:
            List of ``(spec, last_observed)`` pairs. ``last_observed``
            is the wall-clock time the spec was last seen on disk
            (mtime).
        threshold_days:
            Stale window. Declared-tier fields whose Kind has been
            observed only outside this window are reported.

        Returns
        -------
        list[StaleFieldReport]
            One report per (spec, field) pair that breaches the
            threshold. Empty when no Kinds are stale.
        """
        threshold = timedelta(days=threshold_days)
        now = datetime.now(tz=kinds[0][1].tzinfo if kinds else None)
        reports: list[StaleFieldReport] = []
        for spec, last_observed in kinds:
            if now - last_observed <= threshold:
                continue
            for field_path in spec.raw_declared_fields:
                reports.append(
                    StaleFieldReport(
                        source_path=spec.source_path,
                        field_path=field_path,
                        last_observed=last_observed,
                    )
                )
        return reports

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_yaml(self, yaml_text: str) -> dict[str, Any]:
        """``yaml.safe_load`` with bounded alias expansion + typed errors."""
        try:
            document = yaml.load(yaml_text, Loader=_BoundedSafeLoader)  # noqa: S506  # bounded SafeLoader subclass
        except yaml.YAMLError as exc:
            raise ParseError(field_path="", reason=f"Invalid YAML: {exc}") from exc
        except ValueError as exc:
            # The bounded loader raises ValueError on alias-expansion
            # overflow. Forward as a ParseError with a guidance message.
            raise ParseError(field_path="", reason=str(exc)) from exc

        if document is None:
            raise ParseError(field_path="", reason="Kind YAML is empty")
        if not isinstance(document, dict):
            raise ParseError(
                field_path="",
                reason=(f"Kind YAML root must be a mapping (got {type(document).__name__})"),
            )
        return document

    def _build_spec(
        self,
        document: dict[str, Any],
        source_path: str,
        declared_fields: list[str],
    ) -> KindSpec:
        """Validate the document tree and construct the typed shape."""
        self._reject_removed_fields(document)
        self._reject_unknown_top_level_fields(document)

        api_version = self._require(document, "apiVersion", str)
        kind = self._require(document, "kind", str)
        metadata = self._build_metadata(document.get("metadata"), api_version, declared_fields)
        spec_body = self._build_spec_body(
            document.get("spec"), source_path=source_path, declared_fields=declared_fields
        )

        return KindSpec(
            api_version=api_version,
            kind=kind,
            metadata=metadata,
            spec=spec_body,
            source_path=source_path,
            raw_declared_fields=tuple(declared_fields),
        )

    def _build_metadata(
        self,
        raw: Any,
        api_version: str,
        declared_fields: list[str],
    ) -> KindMetadata:
        if raw is None:
            raise ParseError(field_path="metadata", reason="metadata is required")
        if not isinstance(raw, dict):
            raise self._type_mismatch_error("metadata", "a mapping", raw)

        for unknown in raw.keys() - _REQUIRED_METADATA_FIELDS - _DECLARED_METADATA_FIELDS:
            raise UnknownTopLevelFieldError(field=f"metadata.{unknown}")

        name = self._require_nested(raw, "metadata", "name", str)
        version = self._require_nested(raw, "metadata", "version", str)
        self._validate_semver(version)

        description = self._optional_str(raw, "metadata", "description")
        owner = self._optional_str(raw, "metadata", "owner")
        status = self._optional_str(raw, "metadata", "status")

        # Track populated declared-tier fields for the watchdog.
        for key in ("description", "owner", "status"):
            if raw.get(key) not in (None, "", []):
                declared_fields.append(f"metadata.{key}")

        return KindMetadata(
            name=name,
            version=version,
            description=description,
            maturity=_derive_maturity(api_version),
            owner=owner,
            status=status,
        )

    def _build_spec_body(
        self,
        raw: Any,
        *,
        source_path: str,
        declared_fields: list[str],
    ) -> KindSpecBody:
        if raw is None:
            raise ParseError(field_path="spec", reason="spec is required")
        if not isinstance(raw, dict):
            raise self._type_mismatch_error("spec", "a mapping", raw)

        for unknown in raw.keys() - _ALLOWED_SPEC_FIELDS:
            raise UnknownTopLevelFieldError(field=f"spec.{unknown}")

        find = self._build_find_stage(raw.get("find"), declared_fields)
        generate = self._build_generate_stage(raw.get("generate"), declared_fields)
        evaluate = self._build_evaluate_stage(raw.get("evaluate"), declared_fields)
        decide = self._build_decide_stage(raw.get("decide"), declared_fields)

        max_iter = raw.get("max_iterations")
        if max_iter is not None and not isinstance(max_iter, int):
            raise self._type_mismatch_error("spec.max_iterations", "an integer", max_iter)

        return KindSpecBody(
            find=find,
            generate=generate,
            evaluate=evaluate,
            decide=decide,
            nfr_overrides=raw.get("nfr_overrides"),
            toolkit=_optional_tuple_of_str(raw, "spec.toolkit"),
            max_iterations=max_iter,
        )

    def _build_find_stage(self, raw: Any, declared_fields: list[str]) -> FindStage | None:
        if raw is None:
            # ``spec.find`` is required for slice 1 four-stage Kinds.
            # ChainKind escapes this requirement by having an opaque
            # spec at slice 1, but we don't try to discriminate here —
            # at slice 1 every concrete Kind documented has find.
            # See KIND_SCHEMA §6 maturity table.
            return None
        if not isinstance(raw, dict):
            raise self._type_mismatch_error("spec.find", "a mapping", raw)

        for unknown in raw.keys() - _FIND_ALL:
            raise UnknownTopLevelFieldError(field=f"spec.find.{unknown}")

        toolkit = self._require_tuple_of_str(raw, "spec.find.toolkit")
        inputs_to_scan = self._require_tuple_of_str(raw, "spec.find.inputs_to_scan")

        artifacts_raw = raw.get("output_artifacts")
        if artifacts_raw is None:
            raise ParseError(
                field_path="spec.find.output_artifacts",
                reason="spec.find.output_artifacts is required",
            )
        if not isinstance(artifacts_raw, list):
            raise self._type_mismatch_error("spec.find.output_artifacts", "a list", artifacts_raw)
        artifacts: tuple[dict[str, Any], ...] = tuple(
            self._normalise_artifact(entry, i) for i, entry in enumerate(artifacts_raw)
        )

        context_budget = raw.get("context_budget")
        if context_budget is None and self._warning_sink is not None:
            self._warning_sink.emit(
                ParserWarningEvent(
                    field_path="spec.find.context_budget",
                    reason=("context_budget absent; engine will apply NFR-9 default (8000 tokens)"),
                )
            )

        purpose = raw.get("purpose")
        if isinstance(purpose, str) and purpose.strip():
            declared_fields.append("spec.find.purpose")

        return FindStage(
            toolkit=toolkit,
            inputs_to_scan=inputs_to_scan,
            output_artifacts=artifacts,
            purpose=purpose if isinstance(purpose, str) else None,
            context_budget=context_budget,
        )

    def _build_generate_stage(self, raw: Any, declared_fields: list[str]) -> GenerateStage | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise self._type_mismatch_error("spec.generate", "a mapping", raw)

        declared_fields.append("spec.generate")
        return GenerateStage(
            target_file=self._optional_str(raw, "spec.generate", "target_file"),
            spec_ref=self._optional_str(raw, "spec.generate", "spec_ref"),
            inputs=_optional_tuple_of_str(raw, "spec.generate.inputs") or (),
            constraints=_optional_tuple_of_str(raw, "spec.generate.constraints") or (),
            token_budget=raw.get("token_budget"),
        )

    def _build_evaluate_stage(self, raw: Any, declared_fields: list[str]) -> EvaluateStage | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise self._type_mismatch_error("spec.evaluate", "a mapping", raw)

        declared_fields.append("spec.evaluate")
        return EvaluateStage(
            rubric_ref=self._optional_str(raw, "spec.evaluate", "rubric_ref"),
            verdict_path=self._optional_str(raw, "spec.evaluate", "verdict_path"),
            blocking_criteria=_optional_tuple_of_str(raw, "spec.evaluate.blocking_criteria") or (),
            verdict_schema_version=self._optional_str(
                raw, "spec.evaluate", "verdict_schema_version"
            ),
            token_budget=raw.get("token_budget"),
        )

    def _build_decide_stage(self, raw: Any, declared_fields: list[str]) -> DecideStage | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise self._type_mismatch_error("spec.decide", "a mapping", raw)

        declared_fields.append("spec.decide")
        max_iter = raw.get("max_iterations")
        if max_iter is not None and not isinstance(max_iter, int):
            raise self._type_mismatch_error("spec.decide.max_iterations", "an integer", max_iter)
        five_whys = raw.get("five_whys_iterations")
        if five_whys is not None and not isinstance(five_whys, int):
            raise self._type_mismatch_error(
                "spec.decide.five_whys_iterations", "an integer", five_whys
            )
        on_max = raw.get("on_max_iterations")
        if on_max is not None and on_max != "stop":
            raise ValidationError(
                field_path="spec.decide.on_max_iterations",
                reason=(
                    f"spec.decide.on_max_iterations must be 'stop' at slice 1 (got {on_max!r})"
                ),
            )

        return DecideStage(
            max_iterations=max_iter,
            on_max_iterations=on_max,
            five_whys_iterations=five_whys,
            reason_class_routing=raw.get("reason_class_routing"),
        )

    # -- Generic field helpers --
    #
    # The "must be {type} (got {observed})" pattern repeats in every
    # validation branch; :meth:`_type_mismatch_error` consolidates it so
    # the call sites read as intent ("this field must be a dict") rather
    # than as boilerplate.

    @staticmethod
    def _type_mismatch_error(field_path: str, expected: str, observed: Any) -> ValidationError:
        """Return a typed mismatch error for a field with the wrong type."""
        return ValidationError(
            field_path=field_path,
            reason=(f"{field_path} must be {expected} (got {type(observed).__name__})"),
        )

    def _reject_unknown_top_level_fields(self, document: dict[str, Any]) -> None:
        allowed = _ALLOWED_TOP_LEVEL_FIELDS | _ALLOWED_TOP_LEVEL_DECLARED
        for key in document.keys():
            if key in _REMOVED_TOP_LEVEL_FIELDS:
                continue  # handled by _reject_removed_fields
            if key not in allowed:
                raise UnknownTopLevelFieldError(field=key)

    def _reject_removed_fields(self, document: dict[str, Any]) -> None:
        if "traits" in document:
            raise ValidationError(
                field_path="traits",
                reason=(
                    "'traits' was removed (turn 11); use 'spec.{stage}.context' "
                    "instead. See KIND_SCHEMA.md §4 for the migration path."
                ),
            )

    def _require(self, document: dict[str, Any], field_name: str, expected_type: type) -> Any:
        if field_name not in document:
            raise ParseError(
                field_path=field_name,
                reason=f"{field_name} is required",
            )
        value = document[field_name]
        if not isinstance(value, expected_type):
            raise self._type_mismatch_error(field_name, expected_type.__name__, value)
        return value

    def _require_nested(
        self,
        document: dict[str, Any],
        parent: str,
        field_name: str,
        expected_type: type,
    ) -> Any:
        if field_name not in document or document[field_name] is None:
            raise ParseError(
                field_path=f"{parent}.{field_name}",
                reason=f"{parent}.{field_name} is required",
            )
        value = document[field_name]
        if not isinstance(value, expected_type):
            raise self._type_mismatch_error(f"{parent}.{field_name}", expected_type.__name__, value)
        # Empty string is not a missing field — it's a value-range
        # violation. Reject as ValidationError so the test can
        # discriminate "missing" from "malformed".
        if expected_type is str and value == "":
            raise ValidationError(
                field_path=f"{parent}.{field_name}",
                reason=f"{parent}.{field_name} must not be empty",
            )
        return value

    def _require_tuple_of_str(self, document: dict[str, Any], field_path: str) -> tuple[str, ...]:
        # field_path is the FULL dotted path; the actual key is the
        # last segment.
        key = field_path.rsplit(".", 1)[-1]
        if key not in document:
            raise ParseError(
                field_path=field_path,
                reason=f"{field_path} is required",
            )
        value = document[key]
        return _coerce_tuple_of_str(value, field_path, self._type_mismatch_error)

    def _optional_str(self, document: dict[str, Any], parent: str, field_name: str) -> str | None:
        value = document.get(field_name)
        if value is None:
            return None
        if not isinstance(value, str):
            raise self._type_mismatch_error(f"{parent}.{field_name}", "a string", value)
        return value

    def _validate_semver(self, version: str) -> None:
        if not _SEMVER_RE.match(version):
            raise ValidationError(
                field_path="metadata.version",
                reason=(
                    f"metadata.version must be semver (got {version!r}); "
                    "see https://semver.org for the grammar"
                ),
            )

    def _normalise_artifact(self, entry: Any, index: int) -> dict[str, Any]:
        prefix = f"spec.find.output_artifacts[{index}]"
        if not isinstance(entry, dict):
            raise self._type_mismatch_error(prefix, "a mapping", entry)
        if "path" not in entry or not isinstance(entry["path"], str):
            raise ValidationError(
                field_path=f"{prefix}.path",
                reason=f"{prefix}.path is required and must be a string",
            )
        return dict(entry)


# --- Module-level helpers --------------------------------------------------


def _derive_maturity(api_version: str) -> Maturity:
    """Derive :class:`Maturity` from the ``apiVersion`` version suffix."""
    if "/" not in api_version:
        return Maturity.ALPHA
    suffix = api_version.split("/", 1)[1]
    for prefix, maturity in _APIVERSION_MATURITY.items():
        if suffix.startswith(prefix):
            return maturity
    return Maturity.ALPHA


def _optional_tuple_of_str(container: dict[str, Any], field_path: str) -> tuple[str, ...] | None:
    """Read an optional list-of-strings field; return None when absent."""
    key = field_path.rsplit(".", 1)[-1]
    value = container.get(key)
    if value is None:
        return None
    return _coerce_tuple_of_str(value, field_path, _type_mismatch_module)


def _type_mismatch_module(field_path: str, expected: str, observed: Any) -> ValidationError:
    """Module-level form of :meth:`KindYamlParser._type_mismatch_error`.

    Lets shared helpers raise without holding a parser reference.
    """
    return ValidationError(
        field_path=field_path,
        reason=(f"{field_path} must be {expected} (got {type(observed).__name__})"),
    )


def _coerce_tuple_of_str(
    value: Any,
    field_path: str,
    type_mismatch: Any,
) -> tuple[str, ...]:
    """Validate a value is a list of strings and return it as a tuple.

    ``type_mismatch`` is a callable returning a :class:`ValidationError`
    so this helper can be used both inside :class:`KindYamlParser` (where
    the bound method is the natural source) and at module scope.
    """
    if not isinstance(value, list):
        raise type_mismatch(field_path, "a list of strings", value)
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise type_mismatch(f"{field_path}[{i}]", "a string", item)
    return tuple(value)
