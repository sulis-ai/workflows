"""Run-identity HMAC signing for Verdicts and checkpoints (ADR-206).

Engine-side integrity primitive. Two boundaries:

- **Verdict signing** at the evaluate stage-exit. Signature covers
  ``decision``, ``reason_class``, ``specific_feedback``,
  ``suggested_next_step``, the artifact content hash, the
  invocation's ``run_id``, and the bound :class:`AdapterIdentity`.
  The decide stage verifies before routing on the ``decision``
  field.
- **Checkpoint signing** at the checkpoint port's ``write()``.
  Signature covers iteration counter, terminal state, Verdict
  history (each Verdict carries its own nested signature), adapter
  identity, and workspace fingerprint. Resume verifies before
  re-entry.

Schema validation is a precondition for Verdict signing — a Verdict
failing FR-8 schema or the NR-01.1/2/3 internal-consistency rules is
refused without being signed and raises
:class:`VerdictSchemaViolation`. The signature thus carries an implicit
attestation of structural validity at the moment of production.

Algorithm
---------

HMAC-SHA-256 over canonicalised JSON, keyed by a process-local
:class:`SigningKey` produced via :func:`os.urandom(32)` at service
startup. The key never leaves the workflow service's process; a
restart rotates it.

Canonical JSON: ``json.dumps(obj, sort_keys=True,
separators=(",", ":"), ensure_ascii=True)``. Signature verification
uses :func:`hmac.compare_digest` to close the timing-oracle attack
named in the WP Notes.

This module sits in the workflow domain core: no SDK imports, no
environment reads, no infrastructure dependencies. The composition
root constructs one :class:`SigningKey` at startup and threads it
through both signers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from hmac import compare_digest
from typing import Any, Self

from sulis_workflows.domain.identity import AdapterIdentity

__all__ = [
    "CheckpointSignatureInvalid",
    "CheckpointSigner",
    "CheckpointState",
    "SignedCheckpoint",
    "SignedVerdict",
    "SigningKey",
    "Verdict",
    "VerdictSchemaViolation",
    "VerdictSignatureInvalid",
    "VerdictSigner",
]


# ---------------------------------------------------------------------------
# Key
# ---------------------------------------------------------------------------


_KEY_LEN = 32  # 32-byte HMAC-SHA-256 key (256-bit)


@dataclass(frozen=True)
class SigningKey:
    """Process-local signing key for engine-internal HMAC.

    Generated at workflow service startup via :func:`os.urandom(32)`.
    In-memory only — never persisted to disk, never logged, never
    emitted to instrumentation. A workflow-service restart rotates the
    key (per ADR-206 'restarted process generates a new key').

    Attributes:
        key_bytes: 32 random bytes. The dataclass's repr / str redact
            the value so the key cannot leak through logging.

    Invariants:
        - len(key_bytes) == 32
    """

    key_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if len(self.key_bytes) != _KEY_LEN:
            raise ValueError(
                f"SigningKey.key_bytes must be exactly {_KEY_LEN} bytes, got {len(self.key_bytes)}"
            )

    @classmethod
    def generate(cls) -> Self:
        """Produce a fresh signing key from :func:`os.urandom`.

        Two successive calls return distinct keys. The caller (the
        composition root) keeps the instance and discards it on
        process exit.
        """
        return cls(key_bytes=os.urandom(_KEY_LEN))

    def __repr__(self) -> str:  # pragma: no cover — leak-defence
        return "SigningKey(key_bytes=<redacted>)"

    def __str__(self) -> str:  # pragma: no cover — leak-defence
        return self.__repr__()


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


_VALID_DECISIONS: frozenset[str] = frozenset({"pass", "retry", "stop"})


@dataclass(frozen=True)
class Verdict:
    """The structural body of an evaluate-stage Verdict.

    Per ADR-202 + FR-8: every evaluate adapter returns a Verdict with
    the fields below. NR-01 internal-consistency rules:

    - NR-01.1: ``decision == "pass"`` MUST NOT carry ``reason_class``.
    - NR-01.2: ``decision in {"retry", "stop"}`` MUST carry both
      ``reason_class`` AND ``specific_feedback``.
    - NR-01.3: ``decision == "pass"`` requires non-empty
      ``target_file``.

    The schema validator (used by :class:`VerdictSigner.sign`) refuses
    a Verdict failing these rules without signing it.
    """

    decision: str
    reason_class: str | None
    specific_feedback: str | None
    suggested_next_step: str | None
    target_file: str


@dataclass(frozen=True)
class SignedVerdict:
    """A Verdict paired with the engine-side HMAC signature.

    Produced only by :class:`VerdictSigner.sign`. Consumers (the decide
    stage, the checkpoint signer) accept this type, not bare
    :class:`Verdict` — the typed API surface is the structural part of
    the contract.
    """

    verdict: Verdict
    signature: bytes


class VerdictSchemaViolation(Exception):
    """Raised when a Verdict fails FR-8 / NR-01 schema validation.

    Caught by the engine; emits ``verdict_schema_violation`` audit and
    routes to ``stopped_by_technical_fatal``. The Verdict is NOT signed.
    """


class VerdictSignatureInvalid(Exception):
    """Raised when a SignedVerdict's signature fails verification.

    Caught by the engine's decide stage; emits
    ``verdict_signature_invalid`` audit and routes to
    ``stopped_by_technical_fatal``.
    """


def _validate_verdict_schema(verdict: Verdict) -> None:
    """Apply FR-8 + NR-01 rules. Raises :class:`VerdictSchemaViolation` on failure.

    This is the gate that runs before signing. The signature thus
    carries an implicit attestation of structural validity.
    """
    if verdict.decision not in _VALID_DECISIONS:
        raise VerdictSchemaViolation(
            f"invalid decision {verdict.decision!r}; must be one of {sorted(_VALID_DECISIONS)}"
        )
    if verdict.decision == "pass":
        # NR-01.1
        if verdict.reason_class is not None:
            raise VerdictSchemaViolation(
                f"NR-01.1: decision=pass must not carry reason_class; got {verdict.reason_class!r}"
            )
        # NR-01.3 (path non-empty; existence + structural shape are
        # checked by the evaluate stage against the workspace, not here)
        if not verdict.target_file:
            raise VerdictSchemaViolation("NR-01.3: decision=pass requires non-empty target_file")
    else:
        # NR-01.2: retry / stop must carry both reason_class and specific_feedback
        if verdict.reason_class is None:
            raise VerdictSchemaViolation(
                f"NR-01.2: decision={verdict.decision} must carry reason_class"
            )
        if verdict.specific_feedback is None:
            raise VerdictSchemaViolation(
                f"NR-01.2: decision={verdict.decision} must carry specific_feedback"
            )


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckpointState:
    """Workflow checkpoint persisted by the checkpoint port.

    Carries the minimum state required to resume an interrupted Kind
    invocation: iteration counter, terminal state (None while
    in-flight), the Verdict history (each entry already signed by the
    evaluate stage), and the workspace fingerprint (Kind YAML
    mtime+content hash).
    """

    iteration_counter: int
    terminal_state: str | None
    verdict_history: tuple[SignedVerdict, ...]
    workspace_fingerprint: str


@dataclass(frozen=True)
class SignedCheckpoint:
    """A CheckpointState paired with the engine-side HMAC signature.

    Produced only by :class:`CheckpointSigner.sign`. The checkpoint
    port persists and reads :class:`SignedCheckpoint`; the engine
    verifies before re-entry.
    """

    state: CheckpointState
    signature: bytes


class CheckpointSignatureInvalid(Exception):
    """Raised when a SignedCheckpoint's signature fails verification.

    Caught by the engine's resume path; emits
    ``checkpoint_signature_invalid`` audit and refuses to resume,
    surfacing as ``stopped_by_technical_fatal``.
    """


# ---------------------------------------------------------------------------
# Canonical serialisation helpers
# ---------------------------------------------------------------------------


def _canonical_json(obj: Any) -> bytes:
    """Canonicalised JSON serialisation for HMAC input.

    Sorted keys, no whitespace variance, ASCII-escape non-ASCII so the
    byte representation is stable across platforms. Returns bytes so
    the caller passes them straight into HMAC.update().
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _adapter_identity_payload(identity: AdapterIdentity) -> dict[str, str]:
    """Stable JSON shape for AdapterIdentity in signature inputs.

    The signature must bind to the adapter's identity; we encode the
    three identity fields explicitly so future additions to
    :class:`AdapterIdentity` don't silently change signature inputs.
    """
    return {
        "adapter_class": identity.adapter_class,
        "config_fingerprint": identity.config_fingerprint,
        "port_name": identity.port_name,
    }


def _verdict_payload(verdict: Verdict) -> dict[str, str | None]:
    """Stable JSON shape for a Verdict in signature inputs."""
    return {
        "decision": verdict.decision,
        "reason_class": verdict.reason_class,
        "specific_feedback": verdict.specific_feedback,
        "suggested_next_step": verdict.suggested_next_step,
        "target_file": verdict.target_file,
    }


def _signed_verdict_payload(signed: SignedVerdict) -> dict[str, Any]:
    """Stable JSON shape for a SignedVerdict embedded in a checkpoint.

    The nested Verdict is captured by value + its 64-char-hex signature
    so the checkpoint signature transitively covers the Verdict history.
    """
    return {
        "verdict": _verdict_payload(signed.verdict),
        "signature_hex": signed.signature.hex(),
    }


def _hmac_sign(key: SigningKey, payload: bytes) -> bytes:
    """Compute HMAC-SHA-256 over ``payload`` keyed by ``key``."""
    return hmac.new(key.key_bytes, payload, hashlib.sha256).digest()


def _hmac_verify(key: SigningKey, payload: bytes, expected: bytes) -> bool:
    """Constant-time signature verification.

    Routes through :func:`hmac.compare_digest` (re-exported as
    :data:`compare_digest` for the unit-test monkey-patch surface)
    to close the timing-oracle attack named in the WP Notes.
    """
    computed = _hmac_sign(key, payload)
    return compare_digest(computed, expected)


# ---------------------------------------------------------------------------
# Verdict signer
# ---------------------------------------------------------------------------


class VerdictSigner:
    """HMAC-SHA-256 signer for evaluate-stage Verdicts.

    One instance per workflow-service process. Constructed at the
    composition root from the same :class:`SigningKey` used by
    :class:`CheckpointSigner`.
    """

    def __init__(self, key: SigningKey) -> None:
        self._key = key

    def _payload(
        self,
        verdict: Verdict,
        *,
        run_id: str,
        artifact_content_hash: str,
        adapter_identity: AdapterIdentity,
    ) -> bytes:
        return _canonical_json(
            {
                "kind": "verdict",
                "verdict": _verdict_payload(verdict),
                "run_id": run_id,
                "artifact_content_hash": artifact_content_hash,
                "adapter_identity": _adapter_identity_payload(adapter_identity),
            }
        )

    def sign(
        self,
        verdict: Verdict,
        *,
        run_id: str,
        artifact_content_hash: str,
        adapter_identity: AdapterIdentity,
    ) -> SignedVerdict:
        """Validate schema, then HMAC-sign and wrap in :class:`SignedVerdict`.

        Raises:
            VerdictSchemaViolation: if ``verdict`` fails FR-8 / NR-01.
        """
        _validate_verdict_schema(verdict)
        payload = self._payload(
            verdict,
            run_id=run_id,
            artifact_content_hash=artifact_content_hash,
            adapter_identity=adapter_identity,
        )
        signature = _hmac_sign(self._key, payload)
        return SignedVerdict(verdict=verdict, signature=signature)

    def verify(
        self,
        signed: SignedVerdict,
        *,
        run_id: str,
        artifact_content_hash: str,
        adapter_identity: AdapterIdentity,
    ) -> Verdict:
        """Verify ``signed`` and return the inner :class:`Verdict`.

        Raises:
            VerdictSignatureInvalid: if the signature does not match.
            TypeError: if ``signed`` is not a :class:`SignedVerdict`
                (runtime guard against bare-Verdict callers; mypy
                catches this at type-check time but the runtime guard
                exists for defence in depth).
        """
        if not isinstance(signed, SignedVerdict):
            raise TypeError(
                f"VerdictSigner.verify expects a SignedVerdict; got {type(signed).__name__}"
            )
        payload = self._payload(
            signed.verdict,
            run_id=run_id,
            artifact_content_hash=artifact_content_hash,
            adapter_identity=adapter_identity,
        )
        if not _hmac_verify(self._key, payload, signed.signature):
            raise VerdictSignatureInvalid("verdict signature failed verification")
        return signed.verdict


# ---------------------------------------------------------------------------
# Checkpoint signer
# ---------------------------------------------------------------------------


class CheckpointSigner:
    """HMAC-SHA-256 signer for workflow checkpoints.

    One instance per workflow-service process. Shares the
    :class:`SigningKey` with :class:`VerdictSigner`.
    """

    def __init__(self, key: SigningKey) -> None:
        self._key = key

    def _payload(
        self,
        state: CheckpointState,
        *,
        adapter_identity: AdapterIdentity,
    ) -> bytes:
        return _canonical_json(
            {
                "kind": "checkpoint",
                "iteration_counter": state.iteration_counter,
                "terminal_state": state.terminal_state,
                "verdict_history": [_signed_verdict_payload(sv) for sv in state.verdict_history],
                "workspace_fingerprint": state.workspace_fingerprint,
                "adapter_identity": _adapter_identity_payload(adapter_identity),
            }
        )

    def sign(
        self,
        state: CheckpointState,
        *,
        adapter_identity: AdapterIdentity,
    ) -> SignedCheckpoint:
        """HMAC-sign and wrap in :class:`SignedCheckpoint`."""
        payload = self._payload(state, adapter_identity=adapter_identity)
        signature = _hmac_sign(self._key, payload)
        return SignedCheckpoint(state=state, signature=signature)

    def verify(
        self,
        signed: SignedCheckpoint,
        *,
        adapter_identity: AdapterIdentity,
    ) -> CheckpointState:
        """Verify ``signed`` and return the inner :class:`CheckpointState`.

        Raises:
            CheckpointSignatureInvalid: if the signature does not match.
        """
        if not isinstance(signed, SignedCheckpoint):
            raise TypeError(
                f"CheckpointSigner.verify expects a SignedCheckpoint; got {type(signed).__name__}"
            )
        payload = self._payload(signed.state, adapter_identity=adapter_identity)
        if not _hmac_verify(self._key, payload, signed.signature):
            raise CheckpointSignatureInvalid("checkpoint signature failed verification")
        return signed.state
