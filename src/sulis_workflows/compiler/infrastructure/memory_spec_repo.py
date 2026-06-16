"""In-memory SpecRepository for testing.

Stores fixtures as dicts passed via constructor. Each fixture category
(dags, outcomes, sequences, steps) is optional.
"""

from __future__ import annotations


class MemorySpecRepository:
    """In-memory SpecRepository for testing."""

    def __init__(
        self,
        dags: dict[str, dict] | None = None,
        outcomes: dict[str, dict] | None = None,
        sequences: dict[str, dict] | None = None,
        steps: dict[str, dict] | None = None,
    ) -> None:
        self._dags = dags or {}
        self._outcomes = outcomes or {}
        self._sequences = sequences or {}
        self._steps = steps or {}

    def load_dag(self, outcome_id: str) -> dict:
        try:
            return self._dags[outcome_id]
        except KeyError:
            raise KeyError(f"DAG not found for outcome: {outcome_id}")

    def load_outcome(self, outcome_id: str) -> dict:
        try:
            return self._outcomes[outcome_id]
        except KeyError:
            raise KeyError(f"Outcome not found: {outcome_id}")

    def load_sequence(self, sequence_id: str) -> dict:
        try:
            return self._sequences[sequence_id]
        except KeyError:
            raise KeyError(f"Sequence not found: {sequence_id}")

    def load_step_spec(self, spec_ref: str) -> dict:
        try:
            return self._steps[spec_ref]
        except KeyError:
            raise KeyError(f"Step spec not found: {spec_ref}")
