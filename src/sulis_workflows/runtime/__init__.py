"""Runtime — the runner-facing surface: inject adapters, run a workflow.

A runner builds an `Adapters` bundle (the port implementations its placement needs) and
hands it to the engine; the engine resolves each port from the bundle. This is the single,
generic injection point for every port (DR-040 / docs/ports.md).
"""

from __future__ import annotations

from sulis_workflows.runtime.adapters import Adapters, MissingAdapterError

__all__ = ["Adapters", "MissingAdapterError"]
