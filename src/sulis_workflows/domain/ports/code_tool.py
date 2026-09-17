"""CodeToolPort — dispatches a CODE-kind Tool's mechanism (spec §4.3, §12.1, WP-02).

§4.3: `CODE` = "A function the host can call", deterministic, `ref` names
`module:function`. §12.1: "CODE, EXTERNAL and deterministic PROCESS steps
... are run by the engine before it answers" — unlike `SKILL`/`AGENTIC`
mechanisms, which are non-deterministic and are handed to the caller's
agent session as a `TOOL_STEP` instead of run here (that hand-off is
`next()`'s job, WP-02 step 5, not this port's).

This is deliberately a different port from the deprecated compiler's
``ToolDispatchPort`` (domain/ports/tool_dispatch.py). That port is scoped
to that engine's workspace-primitive stage system (``read_file``/``glob``/
``ripgrep``) and requires a mandatory ``sandbox_root`` — a workspace
concept a CODE Tool's ``module:function`` ref has no use for. Reusing it
here would force an unrelated concept onto every CODE Tool call, so this
format gets its own, narrower port instead of bending that one to fit.

Error contract: raise :class:`ToolTransientError` / :class:`ToolPermanentError`,
both carrying the Tool's own declared error ``code`` (§4.6 / §7.1's
``on_error`` routes by code) rather than the bare Transient/PermanentPortError
the other ports use — the engine needs the code, not just the class, to
route correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sulis_workflows.domain.errors import PermanentPortError, TransientPortError
from sulis_workflows.domain.identity import (
    AdapterIdentity,
    IdentifiedAdapter,
)
from sulis_workflows.domain.ports.base import stub_identity

__all__ = [
    "CodeToolPort",
    "StubCodeToolAdapter",
    "ToolPermanentError",
    "ToolTransientError",
]


class ToolTransientError(TransientPortError):
    """A CODE Tool call failed with a code its own ``errors[]`` classes TRANSIENT."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class ToolPermanentError(PermanentPortError):
    """A CODE Tool call failed with a code classed PERMANENT, or an undeclared
    code — §4.6: "An unlisted error is PERMANENT."."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


@runtime_checkable
class CodeToolPort(IdentifiedAdapter, Protocol):
    """Adapter-agnostic protocol for calling a CODE Tool's ``module:function`` ref.

    ``call`` resolves ``ref`` and invokes it with ``inputs``, returning the
    Tool's output mapping (field name -> value, matching the Tool's declared
    ``output``). Raises :class:`ToolTransientError` / :class:`ToolPermanentError`
    on failure, carrying the failure's error code.
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
class StubCodeToolAdapter:
    """In-memory stub for unit-mode contract tests.

    ``responses`` seeds a ref -> output mapping, echoed exactly.
    ``raises`` seeds a ref -> exception raised instead of a response, so a
    test can drive the TRANSIENT/PERMANENT error paths without a real
    dotted-path import.
    """

    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    raises: dict[str, Exception] = field(default_factory=dict)
    observed_calls: list[tuple[str, str]] = field(default_factory=list)
    _identity: AdapterIdentity = field(init=False)

    def __post_init__(self) -> None:
        self._identity = stub_identity(
            adapter_class="StubCodeToolAdapter",
            port_name="CodeToolPort",
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
