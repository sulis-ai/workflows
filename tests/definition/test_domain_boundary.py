"""WP-01 A5: the domain package imports nothing from `sulis.` and no vendor SDK.

`sulis_workflows` is this library; `sulis.` (no trailing underscore) is the platform
namespace the ports-and-adapters principle (CLAUDE.md) forbids. "Vendor SDK" is this
repository's own term for a provider-specific client library — pyproject.toml's own
comment names the example (`anthropic`) — not a general-purpose, non-vendor standard
implementation such as `pyyaml` or `jsonschema`, the same class of dependency
`pydantic` already is for `sulis_workflows.domain.models` (see this PR's run record
for the citation backing that reading).
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_DIR = Path(__file__).parents[2] / "src" / "sulis_workflows" / "definition"

VENDOR_SDKS = {"anthropic", "openai", "google.generativeai", "cohere"}


def _imported_top_level_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_platform_or_vendor_sdk_imports_in_definition_package() -> None:
    py_files = list(PACKAGE_DIR.rglob("*.py"))
    assert py_files, "expected the definition package to contain Python modules"

    offending: dict[str, set[str]] = {}
    for path in py_files:
        names = _imported_top_level_names(path)
        bad = {
            n
            for n in names
            if n == "sulis" or n.startswith("sulis.") or n.split(".")[0] in VENDOR_SDKS
        }
        if bad:
            offending[str(path.relative_to(PACKAGE_DIR))] = bad

    assert not offending, f"platform or vendor-SDK imports found: {offending}"
