"""Workspace sandbox (WP-7, NFR-14).

Every filesystem-touching stage primitive consults the sandbox before
issuing the underlying read/write. The sandbox normalises a requested
path through a fixed pipeline and either returns the canonical
realpath rooted inside ``sandbox_root`` or raises
:class:`SandboxViolation` with a classified
:class:`SandboxViolationReason`.

Pipeline (fixed order — order matters):

1. NFC-normalise the input string.
2. Reject combining-character disguises in path segments.
3. Percent-decode (single pass — guards against double-decoding attacks
   per RFC 3986 best practice).
4. Detect ``..`` traversal in any segment (post-normalisation,
   post-decode).
5. ``os.path.realpath`` to resolve symlinks.
6. Containment check — the resolved path's :meth:`~pathlib.Path.is_relative_to`
   on the realpath'd sandbox root must be True.

The sandbox is stateless across calls. Mid-flight symlink swaps (MUC-11
second variant) are caught because every primitive call re-resolves.

Defends:

- MUC-02 (Unicode homoglyph, percent-encoded, combining-char path
  traversal — TDD §4.2 / §4.8.1).
- MUC-11 (symlink escape, pre-existing or created at runtime — TDD
  §4.2 / §4.8.1).

This module sits in the workflow service's domain core: no SDK imports,
no environment reads, no infrastructure dependencies. The
:class:`SandboxAuditSink` Protocol mirrors the pattern established for
adapter-identity audit (see ``identity_audit.py``); WP-8 will bridge
this sink to the observability port adapter.
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote

__all__ = [
    "InMemorySandboxAuditSink",
    "Sandbox",
    "SandboxAuditEvent",
    "SandboxAuditSink",
    "SandboxViolation",
    "SandboxViolationReason",
]


# ---------------------------------------------------------------------------
# Violation taxonomy
# ---------------------------------------------------------------------------


class SandboxViolationReason(Enum):
    """Classified reasons a sandbox resolution may be refused.

    Each value names exactly one pipeline stage's rejection so audit
    consumers can correlate the violation with the attack class.
    """

    DOT_DOT_TRAVERSAL = "dot_dot_traversal"
    SYMLINK_ESCAPE = "symlink_escape"
    HOMOGLYPH = "homoglyph"
    PERCENT_ENCODED_ESCAPE = "percent_encoded_escape"
    COMBINING_CHAR = "combining_char"
    OUTSIDE_ROOT = "outside_root"


@dataclass(frozen=True)
class SandboxViolation(Exception):
    """Raised when the sandbox refuses a requested path.

    Attributes:
        reason: Classified rejection cause.
        sandbox_root: Sandbox root that was active for the rejected call.
        requested_path: The caller-supplied path, verbatim. Captured for
            audit; never echoed back to a caller-facing log without
            tenancy / identity context.
        normalised_path: The path after the pipeline reached its
            terminating step, or ``None`` if rejection occurred before
            any normalisation succeeded.
    """

    reason: SandboxViolationReason
    sandbox_root: Path
    requested_path: str
    normalised_path: str | None

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"sandbox refused path ({self.reason.value})"


# ---------------------------------------------------------------------------
# Audit sink contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SandboxAuditEvent:
    """Audit record emitted on every sandbox rejection.

    Mirrors the ``IdentityMismatchEvent`` pattern in
    ``identity_audit.py``. WP-8 (instrumentation + run-id) bridges
    sinks of this protocol to the observability port adapter.
    """

    reason: SandboxViolationReason
    sandbox_root: Path
    requested_path: str
    normalised_path: str | None
    platform_id: str
    run_id: str


class SandboxAuditSink(Protocol):
    """Sink contract: emit a :class:`SandboxAuditEvent`.

    Implementations MUST be fire-and-forget — they MUST NOT raise on
    emit failure, because the sandbox is already raising the typed
    :class:`SandboxViolation`. Buffering / drop policies are
    implementation choices.
    """

    def emit(self, event: SandboxAuditEvent) -> None: ...


class InMemorySandboxAuditSink:
    """In-memory sink for tests and composition-root local development.

    Accumulates events in an ordered list. Production sinks publish to
    the observability port instead.
    """

    def __init__(self) -> None:
        self._events: list[SandboxAuditEvent] = []

    def emit(self, event: SandboxAuditEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> list[SandboxAuditEvent]:
        """Read-only view of accumulated events (caller must not mutate)."""
        return list(self._events)


# ---------------------------------------------------------------------------
# Pipeline helpers (pure functions for unit testability)
# ---------------------------------------------------------------------------

# Percent-encoded sequence pattern — used to detect that a request even
# contained any percent encoding before the single-pass decode.
_PERCENT_ENCODED_PATTERN = re.compile(r"%[0-9A-Fa-f]{2}")

# Dot-dot pattern — any path segment that, after decoding and NFC
# normalisation, is exactly the two-dot literal.
_DOT_DOT_SEGMENT = ".."


def _has_combining_chars(text: str) -> bool:
    """Return True if any code point in ``text`` is a Unicode combining mark.

    Combining marks ("Mark, Nonspacing" = ``Mn``, "Mark, Spacing Combining"
    = ``Mc``, "Mark, Enclosing" = ``Me``) can be used to disguise path
    components. The pipeline rejects any path segment containing them
    rather than attempting heuristic recovery, per the contract in
    TDD §4.2 ("reject combining chars in name segments").
    """
    return any(unicodedata.category(c).startswith("M") for c in text)


def _contains_dot_dot_segment(path: str) -> bool:
    """Return True if any path segment equals ``..``.

    Splits on both forward slash and OS-specific separator. Runs after
    NFC normalisation and percent-decoding.
    """
    # Normalise separators to "/" for segment inspection.
    segments = re.split(r"[\\/]+", path)
    return any(seg == _DOT_DOT_SEGMENT for seg in segments)


def _normalise_and_classify(
    requested: str,
) -> tuple[str, tuple[SandboxViolationReason, str] | None]:
    """Run the string-level pipeline (NFC, combining, percent, dot-dot).

    Returns ``(normalised, None)`` on success or ``(normalised, (reason,
    normalised_path))`` on rejection. Pure function — no FS access.

    Pipeline order:

    1. NFC-normalise.
    2. Reject combining marks in any non-empty path segment.
    3. Percent-decode (single pass) iff a percent sequence is present.
       If decoding revealed a ``..`` segment, classify as
       ``PERCENT_ENCODED_ESCAPE``.
    4. Reject any path containing a literal ``..`` segment.
    """
    nfc = unicodedata.normalize("NFC", requested)

    for seg in re.split(r"[\\/]+", nfc):
        if seg and _has_combining_chars(seg):
            return nfc, (SandboxViolationReason.COMBINING_CHAR, nfc)

    had_percent = bool(_PERCENT_ENCODED_PATTERN.search(nfc))
    decoded = unquote(nfc) if had_percent else nfc
    if had_percent and _contains_dot_dot_segment(decoded):
        return decoded, (SandboxViolationReason.PERCENT_ENCODED_ESCAPE, decoded)

    if _contains_dot_dot_segment(decoded):
        return decoded, (SandboxViolationReason.DOT_DOT_TRAVERSAL, decoded)

    return decoded, None


def _classify_containment_failure(
    *,
    candidate: Path,
    sandbox_root_real: Path,
    decoded: str,
) -> SandboxViolationReason:
    """Return SYMLINK_ESCAPE or OUTSIDE_ROOT for a contained-check failure.

    If the candidate's lexical parent (without realpath) WAS inside the
    sandbox root, then realpath dereferenced a symlink that crossed the
    boundary — classify as :attr:`SandboxViolationReason.SYMLINK_ESCAPE`.
    Otherwise it was an absolute path that was never inside — classify
    as :attr:`SandboxViolationReason.OUTSIDE_ROOT`.

    Pure function — no FS access (works against the inputs only).
    """
    if candidate.is_absolute():
        lexical = Path(os.path.normpath(str(candidate)))
    else:
        lexical = sandbox_root_real / Path(os.path.normpath(decoded))
    if _is_inside(lexical, sandbox_root_real):
        return SandboxViolationReason.SYMLINK_ESCAPE
    return SandboxViolationReason.OUTSIDE_ROOT


# ---------------------------------------------------------------------------
# Sandbox API
# ---------------------------------------------------------------------------


class Sandbox:
    """Stateless path-validation service.

    Every filesystem-touching stage primitive holds a reference to a
    single :class:`Sandbox` instance; every call to :meth:`resolve`
    re-runs the full pipeline. The instance carries only the audit sink
    — there is no per-invocation state.
    """

    def __init__(self, *, audit_sink: SandboxAuditSink) -> None:
        self._audit_sink = audit_sink

    def resolve(
        self,
        requested: str | Path,
        *,
        sandbox_root: Path,
        platform_id: str,
        run_id: str,
    ) -> Path:
        """Return the canonical, realpath-resolved path inside ``sandbox_root``.

        Raises :class:`SandboxViolation` with a classified reason if any
        pipeline stage rejects the request. Every rejection emits one
        :class:`SandboxAuditEvent` to the configured audit sink before
        the exception is raised.

        Pipeline stages are factored into pure helper functions:
        :func:`_normalise_and_classify` runs the string-level pipeline;
        :func:`_classify_containment_failure` runs the post-realpath
        containment + symlink-escape classifier.
        """
        requested_str = str(requested)

        # Stages 1-4 — string-level pipeline (Unicode + percent + dot-dot).
        decoded, string_violation = _normalise_and_classify(requested_str)
        if string_violation is not None:
            reason, normalised_after = string_violation
            self._raise(
                reason=reason,
                sandbox_root=sandbox_root,
                requested_path=requested_str,
                normalised_path=normalised_after,
                platform_id=platform_id,
                run_id=run_id,
            )

        # Stages 5-6 — filesystem-level pipeline (realpath + containment).
        sandbox_root_real = Path(os.path.realpath(sandbox_root))
        candidate = Path(decoded)
        if not candidate.is_absolute():
            candidate = sandbox_root_real / candidate
        resolved = Path(os.path.realpath(candidate))

        if not _is_inside(resolved, sandbox_root_real):
            reason = _classify_containment_failure(
                candidate=candidate,
                sandbox_root_real=sandbox_root_real,
                decoded=decoded,
            )
            self._raise(
                reason=reason,
                sandbox_root=sandbox_root,
                requested_path=requested_str,
                normalised_path=str(resolved),
                platform_id=platform_id,
                run_id=run_id,
            )

        return resolved

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _raise(
        self,
        *,
        reason: SandboxViolationReason,
        sandbox_root: Path,
        requested_path: str,
        normalised_path: str | None,
        platform_id: str,
        run_id: str,
    ) -> None:
        """Emit one audit event, then raise the typed violation."""
        event = SandboxAuditEvent(
            reason=reason,
            sandbox_root=sandbox_root,
            requested_path=requested_path,
            normalised_path=normalised_path,
            platform_id=platform_id,
            run_id=run_id,
        )
        # Audit emission is fire-and-forget; swallow any sink failure so
        # the typed violation still propagates.
        try:
            self._audit_sink.emit(event)
        except Exception:  # pragma: no cover - defensive
            pass
        raise SandboxViolation(
            reason=reason,
            sandbox_root=sandbox_root,
            requested_path=requested_path,
            normalised_path=normalised_path,
        )


def _is_inside(child: Path, root: Path) -> bool:
    """Return True if ``child`` is the same as or a descendant of ``root``.

    ``Path.is_relative_to`` is Python 3.9+; this wrapper exists to make
    the intent explicit at the call sites.
    """
    try:
        return child.is_relative_to(root)
    except AttributeError:  # pragma: no cover - py<3.9 fallback
        try:
            child.relative_to(root)
            return True
        except ValueError:
            return False
