"""FileSystem SpecRepository adapter for production.

Loads DAG.yaml, OUTCOME.md, SEQUENCE.md, and step specs from the
methodology directory on disk. Uses YAML parsing for structured files
and raw text for markdown specs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class FileSystemSpecRepository:
    """Loads specs from the filesystem.

    Directory layout expected:
        base_path/
        ├── outcomes/utility/{outcome_id}/DAG.yaml
        ├── outcomes/utility/{outcome_id}/OUTCOME.md
        ├── delivery/product/outcomes/{outcome_id}/DAG.yaml
        ├── sequences/{sequence_id}/SEQUENCE.md
        └── ...

    The repository searches multiple sub-paths to find specs,
    since outcomes live in different directories (utility, framework,
    delivery/product, delivery/design).
    """

    OUTCOME_SEARCH_PATHS = [
        "outcomes/utility",
        "outcomes/framework",
        "outcomes/blueprint",
        "delivery/product/outcomes",
        "delivery/design/outcomes",
        "delivery/marketing/outcomes",
    ]

    SEQUENCE_SEARCH_PATHS = [
        "sequences",
        "delivery/product",
        "delivery/design",
    ]

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path)

    def load_dag(self, outcome_id: str) -> dict[str, Any]:
        """Load DAG.yaml for an outcome."""
        dag_path = self._find_outcome_file(outcome_id, "DAG.yaml")
        with open(dag_path) as f:
            result: dict[str, Any] = yaml.safe_load(f)
            return result

    def load_outcome(self, outcome_id: str) -> dict[str, Any]:
        """Load OUTCOME.md spec for an outcome.

        Returns a dict with 'content' key containing the raw markdown.
        """
        outcome_path = self._find_outcome_file(outcome_id, "OUTCOME.md")
        with open(outcome_path) as f:
            return {"content": f.read(), "path": str(outcome_path)}

    def load_sequence(self, sequence_id: str) -> dict[str, Any]:
        """Load SEQUENCE.md spec for a sequence.

        Looks for SEQUENCES.md in sequence directories and parses
        the outcomes list from it.
        """
        for search_path in self.SEQUENCE_SEARCH_PATHS:
            seq_dir = self._base / search_path / sequence_id
            for filename in ("SEQUENCE.md", "SEQUENCES.md"):
                seq_file = seq_dir / filename
                if seq_file.exists():
                    with open(seq_file) as f:
                        return {"content": f.read(), "path": str(seq_file)}

            # Also check for DAG.yaml in sequence directories
            dag_file = seq_dir / "DAG.yaml"
            if dag_file.exists():
                with open(dag_file) as f:
                    result: dict[str, Any] = yaml.safe_load(f)
                    return result

        raise KeyError(f"Sequence not found: {sequence_id}")

    def load_step_spec(self, spec_ref: str) -> dict[str, Any]:
        """Load a step specification by reference.

        spec_ref format: "OUTCOME.md#Step-N" or "outcome-id/step-name"
        """
        if "#" in spec_ref:
            # Format: "OUTCOME.md#Step-N" — relative to outcome
            parts = spec_ref.split("#", 1)
            return {"spec_ref": spec_ref, "section": parts[1]}

        if "/" in spec_ref:
            # Format: "outcome-id/step-name"
            outcome_id, step_name = spec_ref.split("/", 1)
            try:
                outcome = self.load_outcome(outcome_id)
                return {
                    "spec_ref": spec_ref,
                    "outcome_id": outcome_id,
                    "step_name": step_name,
                    "outcome_path": outcome.get("path"),
                }
            except KeyError:
                pass

        raise KeyError(f"Step spec not found: {spec_ref}")

    def _find_outcome_file(self, outcome_id: str, filename: str) -> Path:
        """Search outcome directories for a specific file."""
        for search_path in self.OUTCOME_SEARCH_PATHS:
            candidate = self._base / search_path / outcome_id / filename
            if candidate.exists():
                return candidate

        raise KeyError(
            f"{filename} not found for outcome '{outcome_id}'. "
            f"Searched: {', '.join(self.OUTCOME_SEARCH_PATHS)}"
        )
