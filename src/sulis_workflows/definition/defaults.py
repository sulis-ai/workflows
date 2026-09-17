"""The single table of format defaults — spec docs/spec/process-definition.md §15.

"Hold conventions once. Defaults live only in spec §15. Cite, don't restate."
(CLAUDE.md). Every other module that needs one of these values imports it from here
rather than repeating the number; a later PR's ``explain`` command (WP-01 A4) reads
the same constants so the default it prints is never allowed to drift from this file.
"""

from __future__ import annotations

__all__ = [
    "CONTROL_FAIL_THEN",
    "ENGINE_ENDINGS",
    "ENGINE_ENDING_SENTENCES",
    "EXECUTION_POLICY",
    "FOR_EACH_CONCURRENCY",
    "GATE_DECIDERS",
    "GATE_KIND",
    "JOIN_POLICY",
    "LOOP_BUDGET",
    "LOOP_COUNTS",
    "LOOP_ON_EXHAUSTED",
    "MAX_DEPTH",
    "ON_DEPTH_EXHAUSTED",
    "ON_ERROR",
    "ON_FORBIDDEN",
    "ON_JOIN_FAILED",
    "ON_PRECONDITION_FALSE",
    "REPAIR_BUDGET",
    "RETRY_BACKOFF_SECONDS",
    "RETRY_MAX",
    "STEP_CRITICALITY",
]

# Loop budget (passes per loop, per scope) — every loop, including gate send-backs (D1).
LOOP_BUDGET = 10
LOOP_COUNTS = "PASSES"
LOOP_ON_EXHAUSTED = "ESCALATED"  # end: ESCALATED

# Repairs after a failed control.
REPAIR_BUDGET = 1
CONTROL_FAIL_THEN = "FAILED"  # end: FAILED

# Retries for TRANSIENT errors.
RETRY_MAX = 3
RETRY_BACKOFF_SECONDS = 2.0  # exponential backoff starting here

ON_ERROR = "FAILED"  # unrouted PERMANENT error -> end: FAILED
ON_FORBIDDEN = "FORBIDDEN"  # permission refused -> end: FORBIDDEN

MAX_DEPTH = 4
ON_DEPTH_EXHAUSTED = "ESCALATED"

ON_PRECONDITION_FALSE = "ESCALATED"

JOIN_POLICY = "ALL_SUCCESS"
ON_JOIN_FAILED = "FAILED"

FOR_EACH_CONCURRENCY = 1

STEP_CRITICALITY = "STANDARD"
EXECUTION_POLICY = "STRICT"

GATE_KIND = "APPROVAL"
GATE_DECIDERS = (
    "PERSON"  # a person holding the gate's permission, when deciders is absent
)

# The four endings the engine adds to every process (spec §6).
ENGINE_ENDINGS = ("ESCALATED", "FAILED", "FORBIDDEN", "CANCELLED")

# §6 describes each engine ending in parentheses but states no literal `says`
# text; every state must carry a sentence (D6), so these quote that
# description directly rather than inventing new wording.
ENGINE_ENDING_SENTENCES = {
    "ESCALATED": "A limit ran out with no route.",
    "FAILED": "A permanent error had no route.",
    "FORBIDDEN": "A permission was refused.",
    "CANCELLED": "A person stopped the run.",
}
