"""Shared YAML input bounds for the Kind / manifest entry surfaces.

Three boundaries today receive operator-authored YAML and MUST defend
against alias-bomb and oversize-input DoS vectors:

1. The workflow-side canonical Kind hash primitive
   (:mod:`sulis_workflows.domain.registry.hashing`) — hashes
   Kind YAML for registry identity (WP-AUTO-001 / SF-001).
2. The Kind-yaml-parser primitive
   (:mod:`sulis_workflows.domain.kind_yaml_parser`) — parses
   Kind YAML for catalogue / registry intake.
3. The manifest YAML parser
   (:mod:`sulis.services.manifest.adapters.yaml_parser`) — parses
   apply-mode manifests including slice-1 Kind shapes (WP-AUTO-013 /
   SF-015).

This module is the single source of truth for the 256 KiB byte cap.
Before WP-AUTO-014, each boundary defined the same constant locally
under slightly different names (``MAX_YAML_INPUT_BYTES`` in two
places). The extraction here eliminates the drift risk and gives a
single editable point for the cap.

Rationale for 256 KiB:
- A 1 MiB Kind YAML hashes in ~275 ms (SF-001 measurement); 256 KiB
  leaves ample headroom for any realistic operator input while
  bounding the cost of a hostile single-shot submission.
- The same bound at all three boundaries gives operators a consistent
  authoring contract — if a Kind YAML applies via /apply, it will
  also hash and parse via the workflow registry path.
"""

from __future__ import annotations

__all__ = ["MAX_YAML_INPUT_BYTES"]


# 256 KiB. The bound is enforced *before* any YAML loader runs (PyYAML's
# alias expander runs before downstream resource / depth limits, so the
# size cap is the first line of defence against billion-laughs vectors).
MAX_YAML_INPUT_BYTES: int = 256 * 1024
