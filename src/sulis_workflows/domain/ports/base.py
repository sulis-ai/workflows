"""Cross-port base definitions for the workflow domain ports.

Two roles:

1. Re-export :class:`IdentifiedAdapter` so adapter authors have a
   canonical import path under the ``ports/`` package even though the
   declaration lives next to its peer types in :mod:`identity`. There
   is a single source of truth (the declaration); this module is only
   an alias.

2. Expose :func:`stub_identity` — a tiny helper that the in-memory
   stub adapters under this package use to build their
   :class:`AdapterIdentity`. Keeps the four (currently five) stub
   construction sites identical, so a future change to the identity
   shape lands in one place.

Per WP-ARMOR-01 Definition of Done:
  - "IdentifiedAdapter protocol consolidated as the single source of truth
    for the contract (no duplicate definitions)"

The cross-port concern (every adapter must expose ``.identity``) is named
in this module so port-specific files (``llm.py``, ``content_storage.py``,
``tool_dispatch.py``, ``execution_runtime.py``, ``checkpointing.py``)
extending :class:`IdentifiedAdapter` import from one place.
"""

from __future__ import annotations

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
    compute_config_fingerprint,
)

__all__ = ["IdentifiedAdapter", "stub_identity"]


def stub_identity(adapter_class: str, port_name: str) -> AdapterIdentity:
    """Build a deterministic :class:`AdapterIdentity` for an in-memory
    stub adapter.

    Centralises the construction every stub does. The fingerprint
    is seeded from a sentinel ``{"stub": True}`` dict so all stubs
    share the same fingerprint per ``adapter_class`` + ``port_name``
    pair — useful when an integration test wants to assert "an
    in-memory stub is bound to this port".

    Args:
        adapter_class: The stub's class name. The string value
            is carried verbatim into the identity.
        port_name: The port the stub satisfies (e.g. ``"LLMPort"``).

    Returns:
        A frozen :class:`AdapterIdentity`.
    """
    return AdapterIdentity(
        adapter_class=adapter_class,
        config_fingerprint=compute_config_fingerprint({"stub": True}),
        port_name=port_name,
    )
