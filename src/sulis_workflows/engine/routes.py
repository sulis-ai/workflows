"""ROUTE execution — spec §7.2 (route evaluation) and §7.3 (loop budgets), WP-02 step 3.

Reachability (which routes are loops — "any route ... whose target can
reach the node it leaves from", §7.3) and the durable counters themselves
("each loop has its own counter ... rebuilt from durable records") are
`next()`/`report()`'s job (WP-02 step 5), which has the whole Process
graph and `RecordsPort` available. This module is a pure function of what
it is handed: the route and run state for `evaluate_route`, and — for a
target the caller has already determined is a loop — how many times it
has been taken this run scope for `check_loop_budget`. Neither function
does any I/O.

The one defect this format's engine must never repeat: the deprecated
compiler's ``compiler/nodes/routing.py`` silently defaults to the first
route when nothing matches ("Default to first route if no match"). A
route reaching runtime with no match and no ``otherwise`` is refused here,
never guessed — V6 is a validation-time proof of exhaustiveness, not a
runtime guarantee against a bad-but-conformant document that bypassed it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sulis_workflows.definition import defaults as fmt_defaults
from sulis_workflows.definition.expressions import evaluate, parse
from sulis_workflows.definition.model import LoopSpec, RouteNode, RouteTarget

__all__ = [
    "LoopBudgetDecision",
    "LoopBudgetOutcome",
    "RouteDecision",
    "RouteOutcome",
    "check_loop_budget",
    "evaluate_route",
]


class RouteOutcome(str, Enum):
    MATCHED = "MATCHED"
    OTHERWISE = "OTHERWISE"
    REFUSED = "REFUSED"


@dataclass(frozen=True)
class RouteDecision:
    outcome: RouteOutcome
    target: RouteTarget | None = None
    matched_index: int | None = None
    rationale: str | None = None


def evaluate_route(node: RouteNode, run_state: Mapping[str, Any]) -> RouteDecision:
    """§7.2: "Options are evaluated in order; the first true one is taken.\""""
    for index, option in enumerate(node.when):
        if evaluate(parse(option.if_), run_state):
            return RouteDecision(
                outcome=RouteOutcome.MATCHED,
                target=RouteTarget(
                    next=option.next,
                    end=option.end,
                    call=option.call,
                    loop=option.loop,
                    invalidates=option.invalidates,
                ),
                matched_index=index,
            )
    if node.otherwise is not None:
        return RouteDecision(outcome=RouteOutcome.OTHERWISE, target=node.otherwise)
    return RouteDecision(
        outcome=RouteOutcome.REFUSED,
        rationale=(
            f"route {node.id!r}: no `when` option matched and no `otherwise` is "
            "declared — refusing rather than defaulting to the first option."
        ),
    )


class LoopBudgetOutcome(str, Enum):
    WITHIN_BUDGET = "WITHIN_BUDGET"
    EXHAUSTED = "EXHAUSTED"


@dataclass(frozen=True)
class LoopBudgetDecision:
    outcome: LoopBudgetOutcome
    budget: int
    taken_count: int
    on_exhausted: RouteTarget


def check_loop_budget(
    loop: LoopSpec | None,
    *,
    taken_count: int,
    process_default_budget: int | None,
) -> LoopBudgetDecision:
    """§7.3: "Every loop is bounded: `loop.budget`, else the process's
    `defaults.loop_budget`, else the format default (§15)."

    ``taken_count`` is how many times this loop has already been taken in
    this run scope, as derived from durable records by the caller.
    ``on_exhausted`` always resolves to a concrete :class:`RouteTarget` —
    the loop's own declaration if it has one, else the format default
    (`end: ESCALATED`, §15) — so the caller never needs to know that
    default itself (CLAUDE.md: "hold conventions once").
    """
    budget = (
        loop.budget
        if loop is not None and loop.budget is not None
        else process_default_budget
        if process_default_budget is not None
        else fmt_defaults.LOOP_BUDGET
    )
    on_exhausted = (
        loop.on_exhausted
        if loop is not None and loop.on_exhausted is not None
        else RouteTarget(end=fmt_defaults.LOOP_ON_EXHAUSTED)
    )
    outcome = (
        LoopBudgetOutcome.EXHAUSTED
        if taken_count >= budget
        else LoopBudgetOutcome.WITHIN_BUDGET
    )
    return LoopBudgetDecision(
        outcome=outcome,
        budget=budget,
        taken_count=taken_count,
        on_exhausted=on_exhausted,
    )
