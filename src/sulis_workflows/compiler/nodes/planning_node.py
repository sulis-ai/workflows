"""Planning node — structured decision-making for recursive spiral OODA.

Planning nodes bridge content nodes (LLM judgment) and process nodes
(deterministic). They parse structured JSON output from an LLM that
evaluates current state, decides what's still needed, and emits work
(search queries). Combined with a search executor, they form the
recursive spiral: wide uncertainty → broad queries → narrower uncertainty
→ targeted queries → sufficient → exit.

Three factories:
- make_planning_parser() — extracts status/queries from LLM JSON output
- make_search_executor() — runs emitted queries via injectable search_fn
- make_plan_route_decision() — routes based on planning status strings
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def make_planning_parser(
    output_key: str,
    status_key: str,
    queries_key: str,
    iterations_key: str,
) -> Callable:
    """Create a process node that parses structured JSON from a planning LLM call.

    Extracts `status` ("sufficient" or "need_more") and `queries` (list of
    search strings) from the LLM's JSON response. Increments the iteration
    counter on each invocation.

    Handles malformed JSON gracefully: defaults to "need_more" with empty
    queries, allowing the route decision node to handle the fallback.

    Args:
        output_key: State field containing raw LLM JSON output.
        status_key: State field to write the parsed status.
        queries_key: State field to write the parsed queries (JSON list).
        iterations_key: State field for the iteration counter (incremented).

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def parser_fn(state: dict) -> dict:
        raw = state.get(output_key, "")
        iterations = state.get(iterations_key, 0)

        status = "need_more"
        queries: list[str] = []

        if raw:
            # Try to extract JSON from the response — LLM may wrap it in markdown
            json_str = raw.strip()
            if "```" in json_str:
                # Extract content between code fences
                parts = json_str.split("```")
                for part in parts[1::2]:  # odd-indexed parts are inside fences
                    candidate = part.strip()
                    if candidate.startswith("json"):
                        candidate = candidate[4:].strip()
                    if candidate.startswith("{"):
                        json_str = candidate
                        break
            try:
                parsed = json.loads(json_str)
                status = parsed.get("status", "need_more")
                queries = parsed.get("queries", [])
            except (json.JSONDecodeError, AttributeError):
                logger.warning(
                    "Planning parser: malformed JSON from LLM, "
                    "defaulting to need_more with empty queries"
                )

        queries_json = json.dumps(queries)

        logger.info(
            "Planning parser: status=%s, queries=%d, iteration=%d",
            status,
            len(queries),
            iterations + 1,
        )

        return {
            status_key: status,
            queries_key: queries_json,
            iterations_key: iterations + 1,
        }

    parser_fn.__name__ = f"parse_{output_key}"
    return parser_fn


def make_search_executor(
    queries_key: str,
    results_key: str,
    evidence_key: str,
    search_fn: Callable[[str], str],
) -> Callable:
    """Create a process node that executes search queries and accumulates results.

    Reads queries from state (JSON list), calls the injectable search_fn for
    each, and appends the results to the accumulated evidence. Evidence grows
    across iterations — each invocation adds to the existing body.

    Args:
        queries_key: State field containing JSON list of query strings.
        results_key: State field to write this iteration's search results.
        evidence_key: State field for accumulated evidence (appended to).
        search_fn: Callable that takes a query string and returns results.
            For unit tests: ``lambda q: f"Mock result for: {q}"``
            For integration: real search or richer mock.

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def executor_fn(state: dict) -> dict:
        queries_json = state.get(queries_key, "[]")
        existing_evidence = state.get(evidence_key, "")

        try:
            queries = json.loads(queries_json)
        except (json.JSONDecodeError, TypeError):
            queries = []

        results_parts: list[str] = []
        for query in queries:
            result = search_fn(query)
            results_parts.append(f"### Query: {query}\n\n{result}\n")

        iteration_results = "\n".join(results_parts)

        # Accumulate evidence across iterations
        if existing_evidence:
            accumulated = f"{existing_evidence}\n\n---\n\n{iteration_results}"
        else:
            accumulated = iteration_results

        logger.info(
            "Search executor: ran %d queries, evidence now %d chars",
            len(queries),
            len(accumulated),
        )

        return {
            results_key: iteration_results,
            evidence_key: accumulated,
        }

    executor_fn.__name__ = f"execute_{queries_key}"
    return executor_fn


def make_plan_route_decision(
    status_key: str,
    iterations_key: str,
    route_key: str,
    *,
    queries_key: str = "search_queries",
    max_iterations: int = 5,
) -> Callable:
    """Create a route decision node adapted for planning status strings.

    Unlike ``make_route_decision`` (which checks a boolean valid_key), this
    factory handles the planning-specific semantics:
    - ``"sufficient"`` → proceed
    - Max iterations reached → forced proceed
    - Empty queries after first iteration → proceed (avoids infinite loop)
    - Otherwise → retry (trigger another search round)

    Args:
        status_key: State field containing ``"sufficient"`` or ``"need_more"``.
        iterations_key: State field containing the iteration counter.
        route_key: State field to write ``"proceed"`` or ``"retry"``.
        queries_key: State field containing the JSON query list.
        max_iterations: Maximum planning iterations before forced proceed.

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def decision_fn(state: dict) -> dict:
        status = state.get(status_key, "need_more")
        iterations = state.get(iterations_key, 0)
        queries = state.get(queries_key, "[]")

        if status == "sufficient":
            return {route_key: "proceed"}

        if iterations >= max_iterations:
            return {route_key: "proceed"}

        # No queries emitted (malformed JSON fallback) → proceed to avoid infinite loop
        try:
            parsed_queries = json.loads(queries) if queries else []
        except (json.JSONDecodeError, TypeError):
            parsed_queries = []
        if not parsed_queries and iterations > 0:
            return {route_key: "proceed"}

        return {route_key: "retry"}

    decision_fn.__name__ = f"decide_{route_key}"
    return decision_fn
