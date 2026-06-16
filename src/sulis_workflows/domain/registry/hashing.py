"""Canonical Kind-YAML hashing (ADR-208, WP-ARMOR-03).

The content hash carried in :class:`~sulis_workflows.domain.registry.kind_resolver.ResolvedAtCreation`
is computed over a *canonical* form of the Kind YAML so cosmetic edits
(adding comments, reordering keys, adding blank lines) do not trip drift
detection. The canonical form is:

1. Parse the bytes via ``yaml.safe_load``. Comments do not survive the
   parse — they're already dropped.
2. Re-emit as canonical JSON: ``sort_keys=True``, no whitespace variance,
   ASCII-escaped non-ASCII. Key order is normalised at every nesting
   level.
3. SHA-256 over the resulting UTF-8 bytes. Hex-encoded for storage on
   the ContentBrief.

This shares the spirit of ``signing._canonical_json`` (the WP-ARMOR-02
helper for HMAC inputs) but operates on parsed YAML rather than the raw
bytes the engine produces internally. The two helpers are deliberately
parallel: signing canonicalises the data the engine produced; this
module canonicalises the data the operator authored.

A YAML whose root node is not a mapping is not a valid Kind document
and is refused with :class:`ValueError` before hashing.

**Resource bounds (WP-AUTO-001, SF-001).** Operator-supplied YAML may
cross a tenant boundary once WP-10 wires this primitive to
``sulis apply -f <user-supplied-yaml>``. Two complementary bounds are
enforced before the canonical hash is computed:

1. :data:`MAX_YAML_INPUT_BYTES` (256 KiB) — refused before
   ``yaml.safe_load`` is called. A 1 MiB legitimate Kind hashes in
   ~275 ms today; 256 KiB leaves ample headroom.
2. :data:`MAX_ANCHOR_EXPANSIONS` (1000) — a ``SafeLoader`` subclass
   counts alias expansions during parsing and refuses past the
   threshold. Defence in depth: a <256 KiB document can still encode
   a problematic alias graph (the classic billion-laughs vector).

Both bounds raise :class:`ValueError`.

See: ADR-208 'Content-hash computation is deterministic'.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import yaml

from sulis_workflows.domain.yaml_input_limits import (
    MAX_YAML_INPUT_BYTES,
)

__all__ = [
    "MAX_ANCHOR_EXPANSIONS",
    "MAX_YAML_INPUT_BYTES",
    "canonical_kind_hash",
]


# ``MAX_YAML_INPUT_BYTES`` is now sourced from
# :mod:`sulis_workflows.domain.yaml_input_limits` — the single
# source of truth for the 256 KiB cap shared with the Kind-yaml-parser
# primitive and the manifest-side ``yaml_parser`` adapter (WP-AUTO-014
# Blue refactor). It is re-exported from this module for backwards
# compatibility with existing call sites (``from
# sulis_workflows.domain.registry.hashing import
# MAX_YAML_INPUT_BYTES``).


# 1000 alias expansions. A billion-laughs payload trips this within the
# first level of nested alias resolution; benign uses (sharing repeated
# literals across a Kind) sit two orders of magnitude below.
MAX_ANCHOR_EXPANSIONS: int = 1000


class _BoundedSafeLoader(yaml.SafeLoader):
    """``yaml.SafeLoader`` subclass that caps *effective* alias expansion.

    The billion-laughs vector is not the number of alias references — it
    is the geometric blow-up of the *expanded* node count. PyYAML's
    composer caches the anchored node and returns the same instance on
    each alias, so the in-memory node graph stays small; but downstream
    consumers (here, ``json.dumps`` over the loaded dict) walk the graph
    as a tree and serialise each reference separately. That walk is
    where a 372-byte input produces a 469 MB output (per SF-001).

    To bound the cost defensively at parse time, this loader tracks the
    *expanded subtree size* of every anchored node. When an alias is
    resolved, the size of the referenced subtree is added to a running
    counter. Once the counter crosses :data:`MAX_ANCHOR_EXPANSIONS` the
    loader raises :class:`ValueError` and parsing aborts — long before
    ``json.dumps`` is reached.

    Anchored nodes that are never referenced contribute nothing to the
    counter; benign uses (sharing a small literal across a few sites)
    sit two orders of magnitude below the cap.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Running tally of expanded-tree weight contributed by aliases.
        self._effective_expansions: int = 0
        # Per-anchor subtree size, populated as each anchored node finishes
        # composing. Sized as expanded-leaf-count (so a list of N references
        # to an anchored subtree of size S contributes N * S).
        self._anchor_subtree_size: dict[str, int] = {}

    def compose_node(self, parent: Any, index: Any) -> Any:  # type: ignore[override]
        # Alias event: charge the cached anchor's subtree size against
        # the budget, then resolve via the base implementation. The size
        # is necessarily known by now (anchors must be defined before
        # alias references in valid YAML — PyYAML enforces this).
        if self.check_event(yaml.events.AliasEvent):
            anchor = self.peek_event().anchor
            cost = self._anchor_subtree_size.get(anchor, 1)
            self._effective_expansions += cost
            if self._effective_expansions > MAX_ANCHOR_EXPANSIONS:
                raise ValueError(
                    f"Kind YAML alias expansion limit exceeded "
                    f"(> {MAX_ANCHOR_EXPANSIONS} effective nodes); "
                    f"refusing to parse"
                )
            return super().compose_node(parent, index)

        # Non-alias node: compose normally, then if it's anchored, record
        # its expanded subtree size for any later aliases that reference it.
        anchor = self.peek_event().anchor
        node = super().compose_node(parent, index)
        if anchor is not None and node is not None:
            self._anchor_subtree_size[anchor] = _subtree_size(node)
        return node


def _subtree_size(node: yaml.Node) -> int:
    """Return the expanded leaf count of a composed YAML node graph.

    For an anchor referenced N times in N alias positions, the
    serialised-as-tree cost is N × ``_subtree_size(anchor_node)``. This
    function computes the per-reference cost.

    Sequences and mappings recurse over their children, summing each
    child's size; scalars count as 1.
    """
    if isinstance(node, yaml.ScalarNode):
        return 1
    if isinstance(node, yaml.SequenceNode):
        return 1 + sum(_subtree_size(child) for child in node.value)
    if isinstance(node, yaml.MappingNode):
        return 1 + sum(_subtree_size(k) + _subtree_size(v) for k, v in node.value)
    return 1


def canonical_kind_hash(yaml_bytes: bytes) -> str:
    """SHA-256 hex digest over the canonical form of a Kind YAML.

    Parameters
    ----------
    yaml_bytes:
        Raw UTF-8-encoded Kind YAML bytes as authored on disk.

    Returns
    -------
    str
        64-character lowercase hex SHA-256 digest. Stable across
        whitespace, key-order, and comment changes; sensitive to any
        change in field values.

    Raises
    ------
    ValueError
        - If ``len(yaml_bytes) > MAX_YAML_INPUT_BYTES``.
        - If alias expansions during parsing exceed
          :data:`MAX_ANCHOR_EXPANSIONS`.
        - If the YAML does not parse to a mapping at the root (Kind
          documents always have a mapping root: ``apiVersion``, ``kind``,
          ``metadata``, ``spec``).
    """
    if len(yaml_bytes) > MAX_YAML_INPUT_BYTES:
        raise ValueError(
            f"Kind YAML input size {len(yaml_bytes)} bytes exceeds maximum "
            f"of {MAX_YAML_INPUT_BYTES} bytes; refusing to parse"
        )

    parsed = yaml.load(yaml_bytes, Loader=_BoundedSafeLoader)  # noqa: S506  # bounded SafeLoader subclass
    if not isinstance(parsed, dict):
        raise ValueError(f"Kind YAML root must be a mapping (got {type(parsed).__name__})")

    canonical = _canonical_json_bytes(parsed)
    return hashlib.sha256(canonical).hexdigest()


def _canonical_json_bytes(obj: Any) -> bytes:
    """Stable byte serialisation: sorted keys, no whitespace, ASCII-safe."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
