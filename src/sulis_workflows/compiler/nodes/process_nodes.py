"""Process nodes — deterministic prompt assembly and output verification.

Process nodes handle the mechanical work in a compiled execution graph:
assembling prompts from lens definitions + prior state, and verifying that
LLM outputs meet structural requirements. No LLM calls — pure functions.
"""

from __future__ import annotations

from collections.abc import Callable


def make_context_assembler(
    lens_text: str,
    input_keys: list[str],
    output_key: str,
) -> Callable:
    """Create a process node that assembles a prompt from lens + state inputs.

    Args:
        lens_text: The lens definition text (instructions for the LLM).
        input_keys: State fields to include as context in the prompt.
        output_key: State field to write the assembled prompt into.

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def assembler_fn(state: dict) -> dict:
        sections = [
            "# Lens Instructions\n",
            lens_text.strip(),
            "\n\n# Context\n",
        ]
        for key in input_keys:
            value = state.get(key, "")
            if value:
                sections.append(f"\n## {key}\n\n{value}\n")

        prompt = "\n".join(sections)
        return {output_key: prompt}

    assembler_fn.__name__ = f"assemble_{output_key}"
    return assembler_fn


def make_output_verifier(
    input_key: str,
    output_key: str,
    *,
    min_length: int = 100,
) -> Callable:
    """Create a process node that verifies structural requirements of LLM output.

    Args:
        input_key: State field containing the LLM output to verify.
        output_key: State field to write the boolean verification result.
        min_length: Minimum character length for the output to pass.

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def verifier_fn(state: dict) -> dict:
        output = state.get(input_key, "")

        if not output:
            return {output_key: False}

        if len(output) < min_length:
            return {output_key: False}

        return {output_key: True}

    verifier_fn.__name__ = f"verify_{input_key}"
    return verifier_fn


def make_route_decision(
    valid_key: str,
    attempts_key: str,
    route_key: str,
    *,
    max_retries: int = 2,
) -> Callable:
    """Create a process node that decides whether to proceed or retry.

    Implements the Decide phase of the OODA loop. Reads the verification
    result and attempt count, then writes a route decision to state.

    Args:
        valid_key: State field containing the boolean verification result.
        attempts_key: State field containing the current attempt count.
        route_key: State field to write the route decision ("proceed" or "retry").
        max_retries: Maximum number of retries before forced proceed.

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def decision_fn(state: dict) -> dict:
        valid = state.get(valid_key, False)
        attempts = state.get(attempts_key, 0)

        if valid:
            return {route_key: "proceed"}

        if attempts >= max_retries:
            return {route_key: "proceed"}

        return {route_key: "retry"}

    decision_fn.__name__ = f"decide_{route_key}"
    return decision_fn


def make_prompt_refiner(
    prompt_key: str,
    failed_output_key: str,
    attempts_key: str,
) -> Callable:
    """Create a process node that refines a prompt after a failed verification.

    Implements the Act phase of the OODA loop. Takes the original prompt and
    the insufficient output, then produces a refined prompt that instructs the
    LLM to improve its response. Increments the attempt counter.

    Args:
        prompt_key: State field containing the prompt to refine (read + overwrite).
        failed_output_key: State field containing the LLM output that failed verification.
        attempts_key: State field for the attempt counter (incremented).

    Returns:
        An async callable suitable for LangGraph function nodes.
    """

    async def refiner_fn(state: dict) -> dict:
        original_prompt = state.get(prompt_key, "")
        previous_output = state.get(failed_output_key, "")
        attempts = state.get(attempts_key, 0)

        # Truncate previous output to avoid prompt bloat on repeated retries
        preview = previous_output[:500]
        if len(previous_output) > 500:
            preview += "\n[...truncated]"

        refined = (
            f"{original_prompt}\n\n"
            f"# Revision Required (attempt {attempts + 1})\n\n"
            f"Your previous response was insufficient — it was either too short, "
            f"missing required sections, or lacked the structured analysis requested. "
            f"Review your previous output below and produce a more thorough, "
            f"complete analysis that addresses all requirements.\n\n"
            f"## Previous Output\n\n{preview}"
        )

        return {prompt_key: refined, attempts_key: attempts + 1}

    refiner_fn.__name__ = f"refine_{prompt_key}"
    return refiner_fn
