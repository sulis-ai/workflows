"""Port for loading DAG and outcome specifications.

Defines the SpecRepository Protocol that the compiler uses to load
DAG.yaml, OUTCOME.md, SEQUENCE.md, and step specifications.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpecRepository(Protocol):
    """Port for loading DAG and outcome specifications.

    Memory adapter for tests; FileSystem adapter for production.
    """

    def load_dag(self, outcome_id: str) -> dict:
        """Load DAG.yaml for an outcome.

        Returns the parsed YAML as a dict.

        Raises:
            KeyError: If outcome_id not found.
        """
        ...

    def load_outcome(self, outcome_id: str) -> dict:
        """Load OUTCOME.md spec for an outcome.

        Returns parsed outcome metadata.

        Raises:
            KeyError: If outcome_id not found.
        """
        ...

    def load_sequence(self, sequence_id: str) -> dict:
        """Load SEQUENCE.md spec for a sequence.

        Returns parsed sequence definition.

        Raises:
            KeyError: If sequence_id not found.
        """
        ...

    def load_step_spec(self, spec_ref: str) -> dict:
        """Load a step specification by reference.

        Raises:
            KeyError: If spec_ref not found.
        """
        ...
