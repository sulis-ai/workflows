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
# Annotation-only keywords: they describe and never constrain, so a draft may add or change them at any path (D-h).
# `default` is an annotation only where the system Profile has none at that node (a changed default changes what a
# consumer is handed); `$schema` only when it names the dialect the rules are written in.
ANNOTATIONS = frozenset({"title", "description", "examples", "$comment", "$id", "deprecated"})
DIALECT = "https://json-schema.org/draft/2020-12/schema"
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


def _both(a: Any, b: Any, root: Any, where: str, conflicts: list | None) -> Any:
    """Two schemas that must both hold for one place: merged when both are objects, else they must be equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        return _merge(a, b, root, where, conflicts)
    if not same(a, b) and conflicts is not None:
        conflicts.append(("schema", where))
    return a


def _merge(target: dict, siblings: dict, root: Any, where: str, conflicts: list | None) -> dict:
    """The target and its siblings together, as JSON Schema 2020-12 applies them (both must hold).

    `properties` and `required` are unions and a property both sides name is merged in turn; `items` is merged;
    an annotation on the sibling side wins; any other keyword both sides hold must be equal, else it is recorded as
    a conflict (the draft's schema contradicts itself there) and the target's value is kept.
    """
    def clash(kw: str, at: str) -> None:
        if conflicts is not None:
            conflicts.append((kw, at))

    out = dict(target)
    for k, v in siblings.items():
        if k in ANNOTATIONS or k in ("$defs", "definitions"):
            out[k] = v
        elif k == "properties" and isinstance(v, dict) and isinstance(out.get("properties", {}), dict):
            props = dict(out.get("properties", {}))
            for n, sv in v.items():
                here = f"{where}/properties/{n}"
                if n in props:
                    a = _resolve(props[n], root, here, conflicts)
                    b = _resolve(sv, root, here, conflicts)
                    props[n] = _both(a, b, root, here, conflicts)
                else:
                    props[n] = sv
            out["properties"] = props
        elif k == "required" and isinstance(v, list) and isinstance(out.get("required", []), list):
            out["required"] = sorted({*out.get("required", []), *v}, key=str)
        elif k == "items" and "items" in out and isinstance(v, (dict, bool)):
            a = _resolve(out["items"], root, f"{where}/items", conflicts)
            b = _resolve(v, root, f"{where}/items", conflicts)
            out["items"] = _both(a, b, root, f"{where}/items", conflicts)
        elif k in out:
            if not same(out[k], v):
                clash(k, where)
        else:
            out[k] = v
    return out


def _resolve(node: Any, root: Any, where: str, conflicts: list | None = None, seen: tuple[str, ...] = ()) -> Any:
    """Follow a local $ref (#/$defs/x or #/definitions/x), alone or with sibling keywords.

    Siblings are allowed by JSON Schema 2020-12 (the reference and its siblings all apply), so the schema judged is
    the target with the siblings merged over it. A sibling that disagrees with the target on a non-annotation keyword
    is recorded in `conflicts` (the draft's own schema contradicts itself there). A reference that is not local, does
    not resolve or goes round is unreadable.
    """
    while isinstance(node, dict) and ("$ref" in node or "$dynamicRef" in node):
        if "$dynamicRef" in node:  # resolved at run time by the validator: cannot be judged here
            raise _Unreadable(where, "a $dynamicRef cannot be followed")
        ref = node["$ref"]
        if not isinstance(ref, str) or not ref.startswith(("#/$defs/", "#/definitions/")) or ref in seen:
            raise _Unreadable(where, f"the reference {cap(repr(ref), QUOTE_CAP)} is not a local, non-circular one")
        key, _, name = ref[2:].partition("/")
        target = root.get(key, {}).get(name) if isinstance(root, dict) else None
        if target is None:
            raise _Unreadable(where, f"the reference {cap(repr(ref), QUOTE_CAP)} points at nothing")
        seen = (*seen, ref)
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        target = _resolve(target, root, where, conflicts, seen)
        if not isinstance(target, dict):
            if siblings:
                raise _Unreadable(where, "a reference to a boolean schema with siblings cannot be judged")
            return target
        node = _merge(target, siblings, root, where, conflicts)
    return node


def _walk(p: Any, q: Any, proot: Any, qroot: Any, where: str, out: list[Finding], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise _Unreadable(where, "the schema is nested too deep to judge")
    p = _resolve(p, proot, where)
    qc: list = []
    q = _resolve(q, qroot, where, qc)
    for kw, at in qc:                       # a sibling of a $ref that contradicts what the reference points at
        rule = "RETYPED" if kw in RETYPING else "CHANGED"
        out.append(finding(rule, f"{at}/{kw}", f"{cap(repr(kw), QUOTE_CAP)} beside a $ref at {cap(at or '/', QUOTE_CAP)} disagrees with what the reference points at"))
    if not isinstance(p, dict) or not isinstance(q, dict):
        if not same(p, q):
            out.append(finding("CHANGED", where, f"{where} is not the same as the system Profile's"))
        return
    for kw in sorted(set(p) - ANNOTATIONS - DESCENDS - {"$schema"}):
        if kw not in q:
            rule = "RETYPED" if kw in RETYPING else "CHANGED"
            out.append(finding(rule, f"{where}/{kw}", f"the system Profile's {kw!r} at {where or '/'} is missing"))
        elif not same(p[kw], q[kw]) and not _same_type_set(kw, p[kw], q[kw]):
            rule = "RETYPED" if kw in RETYPING else "CHANGED"
            out.append(finding(rule, f"{where}/{kw}", f"{kw!r} at {where or '/'} was changed from the system Profile's"))
    ps, qs = p.get("$schema", DIALECT), q.get("$schema", DIALECT)
    if not same(ps, qs):
        out.append(finding("CHANGED", f"{where}/$schema", f"the dialect at {cap(where or '/', QUOTE_CAP)} is not the system Profile's"))
    for kw in sorted(set(q) - set(p) - ANNOTATIONS - DESCENDS - {"default", "$schema"}):
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
    """Every $ref anywhere in the draft's Profile must be local, resolvable and alone in its object."""
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
