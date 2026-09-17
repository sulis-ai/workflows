"""Load a v1 definition document: parse (YAML or JSON), validate against its JSON
Schema (spec §1.4 closed objects, §1.5 casing — rule V1), and build the typed model.

No ``sulis.`` import, no vendor SDK beyond ``pyyaml`` and ``jsonschema`` — both already
either a repo dependency (pyyaml) or the same class of general-purpose, non-vendor
validation library as ``pydantic``, which domain code elsewhere in this repository
already depends on (see the run record for this PR for the citation).
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema.validators import Draft202012Validator

from sulis_workflows.definition import model
from sulis_workflows.definition.errors import DefinitionError
from sulis_workflows.domain.yaml_input_limits import MAX_YAML_INPUT_BYTES

__all__ = ["load_definition", "load_definition_file", "DefinitionError"]

_SCHEMA_DIR = Path(__file__).parent / "schema"

_SCHEMA_BY_KIND = {
    "PROFILE": "profile.v1.schema.json",
    "TOOL": "tool.v1.schema.json",
    "CONTROL": "control.v1.schema.json",
    "PROCESS": "process.v1.schema.json",
}


class _StrictBoolLoader(yaml.SafeLoader):
    """YAML 1.2 Core Schema boolean resolution, not YAML 1.1's.

    PyYAML's ``SafeLoader`` follows YAML 1.1: bare ``on``/``off``/``yes``/``no`` (in any
    case) resolve to booleans. The v1 format uses ``on:`` as a normal mapping key on
    every GATE node (spec §7.6) — under the default loader ``on:`` silently becomes the
    boolean key ``True`` and every gate route disappears without any error. This loader
    keeps ``true``/``false`` (and their capitalisations) as booleans and nothing else,
    which is also the YAML 1.2 Core Schema's rule and matches every other value in this
    format already being written in ``SCREAMING_SNAKE_CASE`` rather than bare words.
    """


_StrictBoolLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StrictBoolLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


@functools.lru_cache(maxsize=None)
def _schema(kind: str) -> dict[str, Any]:
    path = _SCHEMA_DIR / _SCHEMA_BY_KIND[kind]
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _parse(text: str, *, fmt: str) -> Any:
    if fmt == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise DefinitionError(f"not valid JSON: {exc}", rule="V1") from exc
    try:
        return yaml.load(text, Loader=_StrictBoolLoader)
    except yaml.YAMLError as exc:
        raise DefinitionError(f"not valid YAML: {exc}", rule="V1") from exc


def _format_finding(error) -> str:  # jsonschema.exceptions.ValidationError
    location = "/".join(str(p) for p in error.absolute_path) or "(document root)"
    return f"{location}: {error.message}"


def load_definition(text: str, *, fmt: str = "yaml") -> model.Definition:
    """Parse and validate a definition document already read into memory.

    ``fmt`` is ``"yaml"`` (default; also parses JSON, which is a YAML subset) or
    ``"json"``. Raises :class:`DefinitionError` (rule ``V1``) naming the schema path
    and every violation found, for anything the schema refuses: an unknown field, a
    wrong type, a value not in ``SCREAMING_SNAKE_CASE`` where the format closes it.
    """

    size = len(text.encode("utf-8"))
    if size > MAX_YAML_INPUT_BYTES:
        raise DefinitionError(
            f"document is {size} bytes, over the {MAX_YAML_INPUT_BYTES}-byte input limit",
            rule="V1",
        )

    doc = _parse(text, fmt=fmt)
    if not isinstance(doc, dict):
        raise DefinitionError("a definition document must be a mapping at the top level", rule="V1")

    kind = doc.get("kind")
    if kind not in _SCHEMA_BY_KIND:
        raise DefinitionError(
            f"'kind' must be one of {sorted(_SCHEMA_BY_KIND)}, got {kind!r}",
            rule="V1",
        )

    schema_path = str(_SCHEMA_DIR / _SCHEMA_BY_KIND[kind])
    validator = Draft202012Validator(_schema(kind))
    findings = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    if findings:
        message = "; ".join(_format_finding(e) for e in findings)
        raise DefinitionError(message, rule="V1", schema_path=schema_path)

    return model.build(doc)


def load_definition_file(path: str | Path) -> model.Definition:
    """Read and load a definition document from disk. Format is inferred from the
    extension (``.json`` -> JSON; anything else -> YAML, which also parses JSON)."""

    path = Path(path)
    fmt = "json" if path.suffix == ".json" else "yaml"
    text = path.read_text(encoding="utf-8")
    try:
        return load_definition(text, fmt=fmt)
    except DefinitionError as exc:
        raise DefinitionError(
            f"{path}: {exc.message}", rule=exc.rule, schema_path=exc.schema_path, node=exc.node
        ) from exc
