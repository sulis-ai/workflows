"""Stub IdentifiedAdapter implementations (WP-ARMOR-01 baseline).

Per the WP-ARMOR-01 Definition of Done:
  - "Stub adapters (one per port) ship with .identity populated; concrete
    adapters are wired by their respective WPs"

These stubs make the contract test green on the WP-ARMOR-01 baseline.
Concrete adapters (Anthropic, Claude Code, GitHub, filesystem, stage
primitives, CloudRun, CLI, SQLite checkpointer, PubSub observability) land
in WP-5, WP-6, WP-MIG-1, WP-MIG-2, WP-MIG-5 and replace their respective
stubs in the contract-test registry.

The stubs intentionally do not implement any port-level behaviour. They
exist to expose a stable :attr:`identity` for the engine guard to verify.
"""

from __future__ import annotations

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    compute_config_fingerprint,
)

__all__ = [
    "StubContentStorageAdapter",
    "StubLLMAdapter",
]


class _StubBase:
    """Common identity scaffolding for stub adapters."""

    _PORT: str = ""
    _CLASS: str = ""
    _CONFIG: dict[str, object] = {}

    def __init__(self) -> None:
        self._identity = AdapterIdentity(
            adapter_class=self._CLASS,
            config_fingerprint=compute_config_fingerprint(self._CONFIG),
            port_name=self._PORT,
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity


class StubLLMAdapter(_StubBase):
    """LLMPort stub. Replaced by AnthropicAdapter / ClaudeCodeAdapter in WP-MIG-1."""

    _PORT = "LLMPort"
    _CLASS = "StubLLMAdapter"
    _CONFIG = {"model": "stub-llm", "behaviour": "noop"}


class StubContentStorageAdapter(_StubBase):
    """ContentStoragePort stub. Replaced by GitHubAdapter / FilesystemAdapter in WP-MIG-2."""

    _PORT = "ContentStoragePort"
    _CLASS = "StubContentStorageAdapter"
    _CONFIG = {"backend": "stub", "behaviour": "noop"}
