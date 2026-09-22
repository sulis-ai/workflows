"""ExternalToolPort — dispatches an EXTERNAL-kind Tool's mechanism
(spec §4.3, §12.1, WP-04 Part 1).

§4.3's own table draws the line precisely: `CODE` — "A function the host
can call" — `ref` a `module:function` path the engine's own process can
import directly, checked by "unit tests"; `EXTERNAL` — "A service outside
Sulis, through a host adapter" — `ref` "an adapter id", an opaque string a
host-supplied adapter interprets however it likes, checked by "the
adapter's own contract tests". §12.1 puts both on the same side of the
dispatch-or-defer split ("`CODE`, `EXTERNAL` and deterministic `PROCESS`
steps ... are run by the engine before it answers") — the difference is
not in *shape* (both are `ref: <string>`, resolved and called before the
engine answers), only in what the string names and who is responsible for
the call actually working.

Kept a distinct Protocol from `CodeToolPort` rather than reused as a
second name for it, even though the method signature is identical: the
*compliance bar* differs (a `CODE` ref's contract is something this
engine's own test suite could in principle exercise; an `EXTERNAL` ref's
contract is entirely the host adapter's own) — a boundary worth keeping
visible in the type system, not just in a docstring, so a future reader
cannot accidentally wire a `CodeToolPort` stub where an `EXTERNAL` call
was meant, or vice versa. "Per adapter" is not "per-adapter-id port":
this single `ExternalToolPort.call(ref, ...)` is one port, one method —
a host's own adapter implementation is free to be a dispatch table keyed
on `ref` internally, or several concrete adapter classes composed behind
one facade; that routing is the host's own business, exactly as
`CodeToolPort`'s single `call(ref, ...)` already lets a host route
different `module:function` refs to entirely different Python functions
without the engine ever knowing or caring.

Error contract: reuses `code_tool.py`'s own `ToolTransientError`/
`ToolPermanentError` pair verbatim, not a second, parallel definition —
both dispatch kinds classify a Tool call's own failure by the SAME
mechanism (the Tool's own declared `errors[]`, §4.6), so `attempt_step`
(`engine/steps.py`) catches one pair regardless of which port raised it,
rather than two structurally-identical pairs from two modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity
from sulis_workflows.domain.ports.code_tool import (
    ToolPermanentError,
    ToolTransientError,
)

__all__ = [
    "ExternalToolPort",
    "StubExternalToolAdapter",
    "ToolPermanentError",
    "ToolTransientError",
]


@runtime_checkable
class ExternalToolPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic protocol for calling an `EXTERNAL` Tool's own
    opaque adapter-id `ref` (spec §4.3).

    ``call`` resolves ``ref`` (however the host's own adapter interprets
    it — a dispatch table, several composed adapter classes, anything)
    and invokes it with ``inputs``, returning the Tool's output mapping
    (field name -> value, matching the Tool's declared ``output``).
    Raises :class:`ToolTransientError` / :class:`ToolPermanentError` on
    failure, carrying the failure's error code — the identical contract
    `CodeToolPort.call` already has.
    """

    async def call(
        self,
        ref: str,
        inputs: dict[str, Any],
        *,
        platform_id: str,
        run_id: str,
    ) -> dict[str, Any]: ...


@dataclass
class StubExternalToolAdapter:
    """In-memory stub for unit-mode contract tests — mirrors
    `StubCodeToolAdapter`'s own shape exactly.

    ``responses`` seeds a ref -> output mapping, echoed exactly.
    ``raises`` seeds a ref -> exception raised instead of a response, so a
    test can drive the TRANSIENT/PERMANENT error paths without a real
    external service.
    """

    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    raises: dict[str, Exception] = field(default_factory=dict)
    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubExternalToolAdapter",
            port_name="ExternalToolPort",
        )

    @property
    def identity(self) -> AdapterIdentity:
        return self._identity

    async def call(
        self,
        ref: str,
        inputs: dict[str, Any],
        *,
        platform_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        self.observed_calls.append((platform_id, run_id))
        if ref in self.raises:
            raise self.raises[ref]
        if ref in self.responses:
            return self.responses[ref]
        return {"stub": True, "ref": ref, "inputs": inputs}
