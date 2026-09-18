"""evaluate_route / check_loop_budget — spec §7.2 (routes) and §7.3 (loop
budgets), WP-02 step 3.

The one defect this engine must never repeat: compiler/nodes/routing.py
(the deprecated path) silently defaults to the first route when nothing
matches. A route that reaches runtime with no match and no `otherwise`
must be refused, not guessed.
"""

from __future__ import annotations

from sulis_workflows.definition import defaults as fmt_defaults
from sulis_workflows.definition.model import (
    LoopSpec,
    RouteNode,
    RouteOption,
    RouteTarget,
)
from sulis_workflows.engine.routes import (
    LoopBudgetOutcome,
    RouteOutcome,
    check_loop_budget,
    evaluate_route,
)


def _route(*options: RouteOption, otherwise: RouteTarget | None = None) -> RouteNode:
    return RouteNode(id="after-interrogate", when=tuple(options), otherwise=otherwise)


def test_first_true_option_wins_even_when_a_later_one_would_also_match():
    node = _route(
        RouteOption(if_='state.verdict == "A"', next="a"),
        RouteOption(
            if_='state.verdict == "A"', next="b"
        ),  # would also match; must not be taken
    )
    decision = evaluate_route(node, {"state": {"verdict": "A"}})
    assert decision.outcome is RouteOutcome.MATCHED
    assert decision.matched_index == 0
    assert decision.target.next == "a"


def test_second_option_taken_when_first_is_false():
    node = _route(
        RouteOption(if_='state.verdict == "A"', next="a"),
        RouteOption(if_='state.verdict == "B"', next="b"),
    )
    decision = evaluate_route(node, {"state": {"verdict": "B"}})
    assert decision.outcome is RouteOutcome.MATCHED
    assert decision.matched_index == 1
    assert decision.target.next == "b"


def test_otherwise_taken_when_nothing_matches():
    node = _route(
        RouteOption(if_='state.verdict == "A"', next="a"),
        otherwise=RouteTarget(next="fallback"),
    )
    decision = evaluate_route(node, {"state": {"verdict": "Z"}})
    assert decision.outcome is RouteOutcome.OTHERWISE
    assert decision.target.next == "fallback"


def test_no_match_and_no_otherwise_is_refused_not_defaulted_to_first_option():
    # A bad-but-conformant fixture that bypasses V6's exhaustiveness proof —
    # the exact shape compiler/nodes/routing.py gets wrong today.
    node = _route(
        RouteOption(if_='state.verdict == "A"', next="a"),
        RouteOption(if_='state.verdict == "B"', next="b"),
    )
    decision = evaluate_route(node, {"state": {"verdict": "Z"}})
    assert decision.outcome is RouteOutcome.REFUSED
    assert decision.target is None
    assert decision.rationale


def test_a_loop_spec_carries_through_on_the_matched_option():
    node = _route(
        RouteOption(
            if_='state.verdict == "REVISED"', next="gather", loop=LoopSpec(budget=2)
        ),
    )
    decision = evaluate_route(node, {"state": {"verdict": "REVISED"}})
    assert decision.target.loop == LoopSpec(budget=2)


def test_loop_within_budget():
    decision = check_loop_budget(
        LoopSpec(budget=3), taken_count=1, process_default_budget=None
    )
    assert decision.outcome is LoopBudgetOutcome.WITHIN_BUDGET
    assert decision.budget == 3


def test_loop_exhausted_at_budget():
    decision = check_loop_budget(
        LoopSpec(budget=2), taken_count=2, process_default_budget=None
    )
    assert decision.outcome is LoopBudgetOutcome.EXHAUSTED


def test_loop_budget_falls_back_to_process_default_when_unset_on_the_loop():
    decision = check_loop_budget(
        LoopSpec(budget=None), taken_count=4, process_default_budget=5
    )
    assert decision.outcome is LoopBudgetOutcome.WITHIN_BUDGET
    assert decision.budget == 5


def test_loop_budget_falls_back_to_format_default_when_nothing_else_is_set():
    decision = check_loop_budget(
        LoopSpec(budget=None), taken_count=9, process_default_budget=None
    )
    assert decision.budget == fmt_defaults.LOOP_BUDGET  # 10
    assert decision.outcome is LoopBudgetOutcome.WITHIN_BUDGET
    decision = check_loop_budget(
        LoopSpec(budget=None), taken_count=10, process_default_budget=None
    )
    assert decision.outcome is LoopBudgetOutcome.EXHAUSTED


def test_exhausted_loop_resolves_its_own_declared_on_exhausted_route():
    loop = LoopSpec(budget=1, on_exhausted=RouteTarget(next="converge"))
    decision = check_loop_budget(loop, taken_count=1, process_default_budget=None)
    assert decision.on_exhausted == RouteTarget(next="converge")


def test_exhausted_loop_with_no_declared_on_exhausted_uses_the_format_default():
    # spec S15: on_exhausted defaults to `end: ESCALATED`.
    loop = LoopSpec(budget=1)
    decision = check_loop_budget(loop, taken_count=1, process_default_budget=None)
    assert decision.on_exhausted == RouteTarget(end=fmt_defaults.LOOP_ON_EXHAUSTED)


def test_a_route_option_with_no_loop_spec_at_all_still_has_a_budget():
    # A loop is any route whose target can reach the node it leaves from —
    # reachability is next()/report()'s job (step 5); this module is handed
    # loop=None for a route the caller has determined is not a loop, and simply
    # never gets called in that case. When it IS called with loop=None (the
    # route declared no `loop:` block at all despite being a loop), the format
    # default still applies (S7.3: "else the format default").
    decision = check_loop_budget(None, taken_count=3, process_default_budget=None)
    assert decision.budget == fmt_defaults.LOOP_BUDGET
    assert decision.on_exhausted == RouteTarget(end=fmt_defaults.LOOP_ON_EXHAUSTED)
