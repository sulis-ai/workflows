"""The v1 process-definition model: JSON Schemas, a loader and typed model classes.

Spec: docs/spec/process-definition.md. This package is the domain for the definition
format — it imports nothing from ``sulis.`` (the platform) and no vendor SDK; see
``tests/test_definition_domain_boundary.py`` (WP-01 A5).
"""

from __future__ import annotations
