"""SKETCH of examples/upsert-a-content-type/checks.py. Never pushed to the library.

The reference implementation of the two computed Tools of the Process (check and tell)
and the add-only rule. Pure: the standard library and jsonschema only, no I/O, no clock,
no `sulis.` import. Hosts bind their own checks behind the same refs.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

Finding = dict[str, str]
Extra = Callable[[dict[str, Any], dict[str, Any]], "tuple[list[Finding], list[Finding]]"]

# Words in a JSON Schema that describe and never constrain (2020-12 core/meta-data vocabularies).
ANNOTATIONS = frozenset({"title", "description", "examples", "$comment"})
# Keywords whose change retypes a property; any other changed keyword is CHANGED.
RETYPING = frozenset({"type", "enum", "const", "format"})
# Keywords the walk descends into. Every other keyword must be equal, or it is a finding.
DESCENDS = frozenset({"properties", "items", "required", "$defs", "definitions"})
MAX_DEPTH = 64
# An empty value is "not present" to a step mapping (spec 7.1), so "nothing stored" needs a word.
NO_BASE = "NONE"


_LINE_ENDS = "\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"


def one_line(text: str) -> str:
    """Every character str.splitlines() ends a line at becomes a space."""
    return "".join(" " if ch in _LINE_ENDS else ch for ch in text)


WHERE_CAP, MESSAGE_CAP, QUOTE_CAP = 200, 300, 60


def cap(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def finding(rule: str, where: str, message: str) -> Finding:
    # where and message can carry a name from the draft: neutralised here, once, for every finding.
    return {"rule": rule, "where": cap(one_line(where), WHERE_CAP) or "/", "message": cap(one_line(message), MESSAGE_CAP)}


def same(a: Any, b: Any) -> bool:
    """JSON equality where true is not 1 (Python's == says it is)."""
    try:
        return canonical(a) == canonical(b)
    except (ValueError, TypeError):
        return False


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def content_hash(manifest: Any, output_profile: Any) -> str:
    body = canonical({"manifest": manifest, "output_profile": output_profile})
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


class _Unreadable(Exception):
    def __init__(self, where: str, why: str) -> None:
        super().__init__(why)
        self.where, self.why = where, why


def _resolve(node: Any, root: Any, where: str, seen: tuple[str, ...] = ()) -> Any:
    """Follow a local $ref (#/$defs/x or #/definitions/x). Anything else is unreadable."""
    while isinstance(node, dict) and ("$ref" in node or "$dynamicRef" in node):
        if "$dynamicRef" in node:  # resolved at run time by the validator: cannot be judged here
            raise _Unreadable(where, "a $dynamicRef cannot be followed")
        ref = node["$ref"]
        if len(node) != 1:
            raise _Unreadable(where, f"a $ref with other keywords beside it ({ref!r}) cannot be judged")
        if not isinstance(ref, str) or not ref.startswith(("#/$defs/", "#/definitions/")) or ref in seen:
            raise _Unreadable(where, f"the reference {ref!r} is not a local, non-circular one")
        key, _, name = ref[2:].partition("/")
        target = root.get(key, {}).get(name) if isinstance(root, dict) else None
        if target is None:
            raise _Unreadable(where, f"the reference {ref!r} points at nothing")
        seen = (*seen, ref)
        node = target
    return node


def _walk(p: Any, q: Any, proot: Any, qroot: Any, where: str, out: list[Finding], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise _Unreadable(where, "the schema is nested too deep to judge")
    p = _resolve(p, proot, where)
    q = _resolve(q, qroot, where)
    if not isinstance(p, dict) or not isinstance(q, dict):
        if not same(p, q):
            out.append(finding("CHANGED", where, f"{where} is not the same as the system Profile's"))
        return
    for kw in sorted(set(p) - ANNOTATIONS - DESCENDS):
        if kw not in q:
            rule = "RETYPED" if kw in RETYPING else "CHANGED"
            out.append(finding(rule, f"{where}/{kw}", f"the system Profile's {kw!r} at {where or '/'} is missing"))
        elif not same(p[kw], q[kw]) and not _same_type_set(kw, p[kw], q[kw]):
            rule = "RETYPED" if kw in RETYPING else "CHANGED"
            out.append(finding(rule, f"{where}/{kw}", f"{kw!r} at {where or '/'} was changed from the system Profile's"))
    for kw in sorted(set(q) - set(p) - ANNOTATIONS - DESCENDS):
        out.append(finding("CHANGED", f"{where}/{kw}", f"{cap(repr(kw), QUOTE_CAP)} was added at {cap(where or '/', QUOTE_CAP)}; only properties may be added"))
    # properties: every system property stays, with the same schema; new ones are the addition
    pp, qp = p.get("properties"), q.get("properties")
    if pp is not None:
        if not isinstance(qp, dict):
            out.append(finding("REMOVED", f"{where}/properties", f"every property under {where or '/'} was removed"))
            qp = {}
        for name in sorted(pp):
            here = f"{where}/properties/{name}"
            if name not in qp:
                out.append(finding("REMOVED", here, f"the system Profile's property {name!r} was removed"))
            else:
                _walk(pp[name], qp[name], proot, qroot, here, out, depth + 1)
    elif qp is not None and p.get("type") != "object":
        out.append(finding("CHANGED", f"{where}/properties", f"properties were added where the system Profile is not an object"))
    # required: nothing the system Profile required may be dropped; only new properties may become required
    preq, qreq = set(p.get("required", [])), set(q.get("required", []))
    for name in sorted(preq - qreq):
        out.append(finding("REQUIRED_DROPPED", f"{where}/required", f"{cap(repr(name), QUOTE_CAP)} was required by the system Profile and is not now"))
    new_names = set(qp or {}) - set(pp or {})
    for name in sorted((qreq - preq) - new_names):
        out.append(finding("CHANGED", f"{where}/required", f"{cap(repr(name), QUOTE_CAP)} was optional in the system Profile and is now required"))
    # items
    if "items" in p:
        if "items" not in q:
            out.append(finding("REMOVED", f"{where}/items", "the system Profile's items schema was removed"))
        else:
            _walk(p["items"], q["items"], proot, qroot, f"{where}/items", out, depth + 1)
    elif "items" in q:
        out.append(finding("CHANGED", f"{where}/items", "an items schema was added where the system Profile has none"))


def _same_type_set(kw: str, a: Any, b: Any) -> bool:
    if kw != "type":
        return False
    as_set = lambda v: {v} if isinstance(v, str) else set(v) if isinstance(v, list) else None  # noqa: E731
    return as_set(a) is not None and as_set(a) == as_set(b)


def ref_findings(profile: Any) -> list[Finding]:
    """Every $ref anywhere in the draft's Profile must be local, resolvable and alone in its object; a $dynamicRef is refused."""
    out: list[Finding] = []

    def walk(node: Any, where: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            out.append(finding("BAD_REF", where or "/", "the schema is nested too deep to follow its references"))
            return
        if isinstance(node, dict):
            if "$ref" in node or "$dynamicRef" in node:
                try:
                    _resolve(node, profile, where)
                except _Unreadable as e:
                    out.append(finding("BAD_REF", where or "/", e.why))
                    return
            for k, v in node.items():
                walk(v, f"{where}/{k}", depth + 1)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}/{i}", depth + 1)

    walk(profile, "", 0)
    return out


def add_only_findings(system_profile: Any, draft_profile: Any) -> list[Finding]:
    """The add-only rule. [] means the draft is the system Profile plus additions, nothing else."""
    out: list[Finding] = []
    try:
        _walk(system_profile, draft_profile, system_profile, draft_profile, "", out, 0)
    except _Unreadable as e:
        out.append(finding("UNREADABLE", e.where or "/", e.why))
    except (TypeError, AttributeError, KeyError) as e:  # a malformed schema fails closed, never raises
        out.append(finding("UNREADABLE", "/", f"the schema could not be read ({type(e).__name__})"))
    return out


def check_content_type(
    *, type_name: str, draft: dict[str, Any], existing: dict[str, Any], extra: Extra | None = None
) -> dict[str, Any]:
    blocking: list[Finding] = []
    advisory: list[Finding] = []
    manifest, profile = draft.get("manifest"), draft.get("output_profile")
    named = manifest.get("metadata", {}).get("name") if isinstance(manifest, dict) and isinstance(manifest.get("metadata"), dict) else None
    if named != type_name:
        blocking.append(finding("NAME_MISMATCH", "/manifest/metadata/name", f"the draft is named {cap(repr(named), QUOTE_CAP)}, not {cap(repr(type_name), QUOTE_CAP)}"))
    if existing.get("name") != type_name:
        blocking.append(finding("SNAPSHOT_MISMATCH", "/existing/name", f"the stored type read is {cap(repr(existing.get('name')), QUOTE_CAP)}, not {cap(repr(type_name), QUOTE_CAP)}"))
    try:
        Draft202012Validator.check_schema(profile)
    except SchemaError as e:
        blocking.append(finding("PROFILE_INVALID", "/output_profile", f"the output Profile is not a JSON Schema: {cap(e.message, QUOTE_CAP)}"))
    else:
        blocking.extend(ref_findings(profile))
        if existing.get("has_system"):
            blocking.extend(add_only_findings(existing.get("system_profile"), profile))
    if extra is not None:
        more_block, more_adv = extra(draft, existing)
        blocking.extend(more_block)
        advisory.extend(more_adv)
    try:
        draft_hash = content_hash(manifest, profile)
        existing_hash = content_hash(existing["current_manifest"], existing["current_profile"]) if existing.get("has_current") else NO_BASE
    except (ValueError, TypeError, KeyError):
        blocking.append(finding("HASH_UNREADABLE", "/", "the draft or the stored type holds a value that is not plain JSON"))
        draft_hash, existing_hash = "NONE", "NONE"
    unchanged = existing_hash != NO_BASE and draft_hash != "" and draft_hash == existing_hash and not blocking
    # trial_findings is always [] here: a new draft has had no trial yet, so the last trial's findings must not outlive it (R11)
    return {"blocking": blocking, "advisory": advisory, "unchanged": unchanged,
            "draft_hash": draft_hash, "existing_hash": existing_hash, "trial_findings": []}


def tell_what_is_in_the_way(*, type_name: str, blocking: list[Finding], trial_findings: list[Finding], note: str) -> dict[str, Any]:
    reasons = [one_line(f"{f['rule']} at {f['where']}: {f['message']}") for f in (*blocking, *trial_findings)]
    if note:
        reasons.append(one_line(f"The last note from a person: {note}"))
    head = f"Stopped: the content type {one_line(type_name)!r} was not saved."
    if reasons:
        shown = "; ".join(reasons[:5]) + (f"; and {len(reasons) - 5} more" if len(reasons) > 5 else "")
        says = f"{head} What is in the way: {shown}."
    else:
        says = f"{head} A step could not finish; the run's record says which step and why."
    return {"told": {"says": says, "reasons": reasons}}
