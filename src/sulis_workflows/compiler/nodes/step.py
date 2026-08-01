"""Step node factory — the most common node type in OFM DAGs.

A step node loads its spec at execution time. When the spec names a `primitive`
(`read_file` / `glob` / `ripgrep`), the node DISPATCHES it through the injected
`ToolDispatchPort` — real workspace work, not a marker — and writes the result into
`step_outputs[node_id]`. When the spec names no primitive (or none is loadable),
the node records the spec it resolved (the pre-dispatch fallback) so non-tool steps
still compile + run. This is the step-node sibling of the content node's `LLMPort`
shape (DR-040): the engine depends on the Protocol; the runner injects the adapter.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sulis_workflows._tracing import span_context
from sulis_workflows.compiler.metrics import get_compiler_metrics
from sulis_workflows.compiler.ports.spec_repository import SpecRepository
from sulis_workflows.domain.engine_cache import WorkspacePath
from sulis_workflows.domain.ports.tool_dispatch import ToolDispatchPort
from sulis_workflows.runtime.adapters import MissingAdapterError

logger = logging.getLogger(__name__)


def make_step_node(
    node_id: str,
    spec_ref: str,
    spec_repo: SpecRepository,
    *,
    tool_dispatch: ToolDispatchPort | None = None,
    sandbox_root: str | None = None,
    platform_id: str = "",
    run_id: str = "",
) -> Any:
    """Create a step node callable for LangGraph.

    Returns an async function (state) -> dict that:
    1. Loads the step spec from the repository.
    2. If the spec names a `primitive`, dispatches it via the injected
       `tool_dispatch` port and writes the result to `step_outputs[node_id]`.
    3. Otherwise records the resolved spec (pre-dispatch fallback).

    Args:
        node_id: this node's id (recorded in `completed_nodes`).
        spec_ref: the step spec to load (empty → no spec).
        spec_repo: where step specs are loaded from.
        tool_dispatch: the injected `ToolDispatchPort` (None until a primitive needs it).
        sandbox_root: the path-traversal boundary every dispatch carries (NFR-14).
        platform_id / run_id: tenancy keys threaded to every port call.
    """

    async def step_fn(state: dict) -> dict:
        metrics = get_compiler_metrics()

        with span_context(
            "compiler.node.step",
            attributes={"node_id": node_id, "spec_ref": spec_ref},
        ):
            start = time.monotonic()
            logger.info("Node execution start: %s", node_id)

            spec: dict[str, Any] | None = None
            if spec_ref:
                try:
                    spec = spec_repo.load_step_spec(spec_ref)
                except KeyError:
                    spec = None

            primitive = (spec or {}).get("primitive")
            if primitive:
                # Tenancy (NFR-11/21): the live execution's identity reaches every port
                # call. Factory args win if set; else derive from the running state.
                meta = state.get("metadata") or {}
                eff_platform_id = platform_id or str(meta.get("platform_id", ""))
                eff_run_id = run_id or str(state.get("execution_id", ""))
                output: dict[str, Any] = await _dispatch_primitive(
                    node_id=node_id,
                    primitive=str(primitive),
                    args=(spec or {}).get("args") or {},
                    tool_dispatch=tool_dispatch,
                    sandbox_root=sandbox_root,
                    platform_id=eff_platform_id,
                    run_id=eff_run_id,
                    step_outputs=state.get("step_outputs"),
                )
            else:
                # Pre-dispatch fallback: record the spec we resolved (no tool work).
                output = {"spec_ref": spec_ref, "spec": spec}

            elapsed_ms = (time.monotonic() - start) * 1000
            metrics.record_node_execution_time(node_id, "step", elapsed_ms)
            logger.info("Node execution end: %s (%.1fms)", node_id, elapsed_ms)

            return {
                "completed_nodes": [node_id],
                "step_outputs": {node_id: output},
            }

    step_fn.__name__ = f"step_{node_id}"
    return step_fn


async def _dispatch_primitive(
    *,
    node_id: str,
    primitive: str,
    args: dict,
    tool_dispatch: ToolDispatchPort | None,
    sandbox_root: str | None,
    platform_id: str,
    run_id: str,
    step_outputs: dict | None = None,
) -> dict[str, Any]:
    """Dispatch a step's tool primitive via the injected `ToolDispatchPort`.

    Returns a plain-dict result (JSON-friendly, lands in `step_outputs`). A primitive
    with no injected port / no sandbox raises a clear `MissingAdapterError`; an unknown
    primitive raises `ValueError`. Never a silent no-op.
    """
    if tool_dispatch is None:
        raise MissingAdapterError(
            f"step '{node_id}' dispatches the '{primitive}' primitive, but the runner "
            "injected no adapter for the 'tool_dispatch' port. "
            "Provide one: Adapters(tool_dispatch=<your tool-dispatch adapter>)."
        )
    if sandbox_root is None:
        raise MissingAdapterError(
            f"step '{node_id}' dispatches the '{primitive}' primitive, but no 'sandbox_root' "
            "was set. Set it on the bundle: Adapters(tool_dispatch=…, sandbox_root='/path')."
        )

    tenancy: dict[str, Any] = {
        "sandbox_root": WorkspacePath(sandbox_root),
        "platform_id": platform_id,
        "run_id": run_id,
    }

    if primitive == "read_file":
        result = await tool_dispatch.read_file(
            WorkspacePath(str(args["path"])),
            offset=int(args.get("offset", 0)),
            limit=args.get("limit"),
            **tenancy,
        )
        return {
            "primitive": primitive,
            "content": result.content,
            "total_lines": result.total_lines,
            "more_available": result.more_available,
        }

    if primitive == "glob":
        paths = await tool_dispatch.glob(str(args["pattern"]), **tenancy)
        return {"primitive": primitive, "paths": [str(p) for p in paths]}

    if primitive == "ripgrep":
        matches = await tool_dispatch.ripgrep(
            str(args["pattern"]),
            [WorkspacePath(str(p)) for p in args.get("paths", [])],
            **tenancy,
        )
        return {
            "primitive": primitive,
            "matches": [
                {"path": str(m.path), "line": m.line, "column": m.column, "text": m.text}
                for m in matches
            ],
        }

    # Beyond the typed workspace trio: delegate to the adapter's generic `invoke`. The
    # engine stays transport-agnostic — the adapter owns how a richer primitive (subprocess,
    # http_call, …) actually executes. An adapter that doesn't implement it fails loud.
    invoke = getattr(tool_dispatch, "invoke", None)
    if invoke is None:
        raise ValueError(
            f"step '{node_id}': primitive '{primitive}' is beyond the workspace trio "
            "(read_file/glob/ripgrep) and the injected tool-dispatch adapter has no 'invoke' "
            "method to handle it."
        )
    return await invoke(primitive, args, step_outputs=step_outputs, **tenancy)
