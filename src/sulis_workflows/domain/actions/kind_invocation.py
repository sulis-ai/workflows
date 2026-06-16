"""KindInvocationAction — input shape for a Kind invocation node.

WP-2 introduces this as a thin placeholder so the graph compiler can construct
the action when it encounters a ``kind_invocation`` node. The full action
machinery (authorization checks, KindHandler wiring, execution path
construction) lands with WP-KIND-HANDLER; this module defines only the stable
shape per TDD §3.4 so the compiler's dispatch branch has something concrete to
build.

Frozen dataclass per TDD §3.4 (not a Pydantic Action) — this is a transport
DTO carried *into* the handler, not a registered platform Action. When
WP-KIND-HANDLER lands it may promote this to the full Action contract; until
then the shape is intentionally minimal.

Fields mirror the Kind Schema (apiVersion + kind + metadata.name +
metadata.version) plus an optional ``content_brief_id`` for callers that
arrive via the ContentBrief path (WP-13) and an optional ``refs`` mapping
that the Kind compiler resolves before execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KindInvocationAction:
    """Input carried into ``KindHandler.handle`` from a ``kind_invocation``
    graph node.

    Attributes:
        api_version: e.g., ``"product-development/v1alpha1"``. Required.
        kind: e.g., ``"Goal"`` — no ``Kind`` or ``ContentKind`` suffix per
            KIND_SCHEMA.md KV-02. Required.
        metadata_name: Human-readable Kind name within its apiVersion namespace.
        metadata_version: Semver of the Kind YAML itself (not the schema).
        content_brief_id: Optional ContentBrief id when the invocation
            originates from ContentBrief dispatch (FR-15, WP-13). ``None``
            for direct invocations.
        refs: Optional cross-node wiring (e.g., ``{"input": "upstream.output"}``)
            carried through to the Kind compiler for reference resolution.
    """

    api_version: str
    kind: str
    metadata_name: str
    metadata_version: str
    content_brief_id: str | None = None
    refs: dict[str, str] = field(default_factory=dict)
