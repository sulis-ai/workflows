"""`Adapters` — the generic port bundle a runner injects into the engine.

One injection point for every port. A runner provides the adapters its placement needs
(a server runner: Firestore/GitHub/a real LLM; a client runner: a local store/claude/stubs;
tests: the `Stub*Adapter`s); the engine resolves each port by name via `require()`. New
ports add a field here — resolution stays uniform. Per DR-040 (one engine, many runners).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sulis_workflows.domain.ports import (
    CheckpointingPort,
    ContentStoragePort,
    LLMPort,
    ObservabilityPort,
    ToolDispatchPort,
)


class MissingAdapterError(RuntimeError):
    """A node needed a port the runner did not inject. Names the port + the fix."""


@dataclass(frozen=True)
class Adapters:
    """The set of port adapters injected at compile/run time. All optional — a runner
    supplies only what its workflows touch; the engine raises a clear error (not a crash)
    if a node needs one that's absent."""

    llm: LLMPort | None = None
    content_storage: ContentStoragePort | None = None
    checkpointing: CheckpointingPort | None = None
    tool_dispatch: ToolDispatchPort | None = None
    observability: ObservabilityPort | None = None

    def require(self, name: str) -> Any:
        """Return the named adapter, or raise `MissingAdapterError` with the fix."""
        adapter = getattr(self, name, None)
        if adapter is None:
            raise MissingAdapterError(
                f"this workflow needs the '{name}' port, but the runner injected no adapter "
                f"for it. Provide one: Adapters({name}=<your {name} adapter>)."
            )
        return adapter
