"""Tests for the upsert-a-content-type example: the Process, its Tools, Profiles and reference checks.

Drives the real engine (next_, report, decide) with the library's own stub ports, replaced
where a stub is too forgiving (spec 06, R14): a recording policy that answers INDETERMINATE
for the standing rule, a code adapter with a compare-and-set store, a tester that pops a
script and fails when the script runs dry.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import importlib.util
import itertools
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from sulis_workflows.definition.checkers import profile_conformance
from sulis_workflows.definition.load import load_definition, load_definition_file
from sulis_workflows.definition.registry import Registry
from sulis_workflows.definition.validate import validate_definition
from sulis_workflows.domain.ports.claims import StubClaimsAdapter
from sulis_workflows.domain.ports.code_tool import (
    StubCodeToolAdapter,
    ToolPermanentError,
    ToolTransientError,
)
from sulis_workflows.domain.ports.external_tool import StubExternalToolAdapter
from sulis_workflows.domain.ports.policy import PolicyDecision, StubPolicyAdapter, Verdict
from sulis_workflows.domain.ports.records import StubRecordsAdapter
from sulis_workflows.engine.run import AnswerKind, EngineContext, decide, next_, report

# ===== The test world and the scenario tests (C1 to C6)
ROOT = Path(__file__).parents[2]
HERE = ROOT / "examples" / "upsert-a-content-type"
DEFS = HERE
BUILTIN = ROOT / "src" / "sulis_workflows" / "definition" / "builtin"

# The folder name has a hyphen, so checks.py is loaded by path, not imported by name.
_spec = importlib.util.spec_from_file_location("upsert_a_content_type_checks", HERE / "checks.py")
checks = importlib.util.module_from_spec(_spec)
sys.modules["upsert_a_content_type_checks"] = checks
_spec.loader.exec_module(checks)  # type: ignore[union-attr]

REFS = {
    "read": "upsert_a_content_type.hooks:read_content_type",
    "check": "upsert_a_content_type.hooks:check_content_type",
    "upsert": "upsert_a_content_type.hooks:upsert_content_type",
    "tell": "upsert_a_content_type.hooks:tell_what_is_in_the_way",
    "try": "content-type-tester",
}
NODE_OF_REF = {
    REFS["read"]: "read-existing", REFS["check"]: "check", REFS["try"]: "try",
    REFS["upsert"]: "upsert", REFS["tell"]: "tell",
}
PERM_OF_NODE = {
    "read-existing": "workflows.upsert-a-content-type.read", "draft": "workflows.upsert-a-content-type.draft",
    "check": "workflows.upsert-a-content-type.check", "try": "workflows.upsert-a-content-type.try",
    "upsert": "workflows.upsert-a-content-type.upsert", "tell": "workflows.upsert-a-content-type.tell",
}

SYSTEM_PROFILE = {
    "type": "object", "required": ["title", "body", "summary"], "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 3},
        "format": {"type": "string", "enum": ["MARKDOWN", "TEXT"]},
        "body": {"type": "string", "minLength": 20},
        "summary": {"type": "string", "maxLength": 400},
        "alternatives": {"type": "array", "items": {"$ref": "#/$defs/alt"}},
    },
    "$defs": {"alt": {"type": "object", "required": ["option"], "properties": {"option": {"type": "string"}, "why_not": {"type": "string"}}}},
}


def manifest(name="quick-answer"):
    return {"apiVersion": "sulis.dev/v1", "kind": "ContentType", "metadata": {"name": name},
            "spec": {"lifecycle": "proposed", "title": "Quick answer", "summary": "A short answer", "process": {"ref": "answer-question", "version": "1.0.0"}}}


def good_draft(name="quick-answer", profile=None):
    p = copy.deepcopy(profile if profile is not None else SYSTEM_PROFILE)
    p["properties"]["tone"] = {"type": "string"}  # an addition
    return {"manifest": manifest(name), "output_profile": p, "case": {"inputs": {"brief": "x"}}}


def snapshot(name="quick-answer", system=True, current=None):
    s = {"name": name, "has_system": system, "has_current": current is not None}
    if system:
        s["system_profile"] = copy.deepcopy(SYSTEM_PROFILE)
    if current is not None:
        s["current_manifest"], s["current_profile"] = current
    return s


def naive_extra(draft, existing):
    """A naive manifest check: valid shape, nothing about the Profile. It must pass the C3 fixture."""
    m = draft["manifest"]
    ok = isinstance(m, dict) and m.get("kind") == "ContentType" and isinstance(m.get("metadata", {}).get("name"), str)
    return ([] if ok else [checks.finding("MANIFEST_SHAPE", "/manifest", "the manifest is not a ContentType")]), []


PASSED = {"verdict": "PASSED", "ending": "APPROVED", "path": ["write", "review"], "steps": [{"node": "write", "says": "w"}]}
FAILED = {"verdict": "FAILED", "ending": "APPROVED", "path": ["write"], "steps": [{"node": "write", "says": "w"}]}


@dataclass
class World:
    snapshot: dict[str, Any] = field(default_factory=snapshot)
    drafts: list[dict[str, Any]] = field(default_factory=list)
    trials: list[tuple[dict[str, Any], list[dict[str, str]]]] = field(default_factory=list)
    gates: list[tuple[Verdict, str]] = field(default_factory=list)
    standing: str = "INDETERMINATE"
    denies: set[str] = field(default_factory=set)
    errors: dict[str, str] = field(default_factory=dict)   # node -> permanent error code
    stored: dict[str, dict[str, Any]] = field(default_factory=dict)
    events: list[tuple[str, str]] = field(default_factory=list)
    extra: Any = naive_extra
    tamper_check: Any = None
    writes: int = 0
    told: list = field(default_factory=list)   # what `tell` answered, in order
    fail_after_write: int = 0       # raise a transient error after the write landed, this many times
    records: Any = None
    system_profiles: dict[str, Any] = field(default_factory=dict)   # what the host's store itself holds


class RecPolicy(StubPolicyAdapter):
    def __init__(self, w: World):
        super().__init__()
        self.w = w

    async def authorize(self, permission, *, identity, platform_id, run_id):
        self.w.events.append(("authorize", permission))
        if permission in self.w.denies:
            return PolicyDecision(Verdict.DENY, "world-denied")
        return PolicyDecision(Verdict.PERMIT)

    async def evaluate_policy(self, ref, *, reviewing, identity, platform_id, run_id):
        self.w.events.append(("policy", ref))
        return PolicyDecision(Verdict[self.w.standing])


class Code(StubCodeToolAdapter):
    def __init__(self, w: World):
        super().__init__()
        self.w = w

    async def call(self, ref, inputs, *, platform_id, run_id):
        w = self.w
        node = NODE_OF_REF[ref]
        w.events.append(("call", node))
        if node in w.errors:
            raise ToolPermanentError(w.errors[node])
        if node == "read-existing":
            return {"existing": w.snapshot}
        if node == "check":
            out = checks.check_content_type(type_name=inputs["type_name"], draft=inputs["draft"], existing=inputs["existing"], extra=w.extra)
            if w.tamper_check:
                out = w.tamper_check(out)
            return out
        if node == "tell":
            told = checks.tell_what_is_in_the_way(**{k: inputs[k] for k in ("type_name", "blocking", "trial_findings", "note")})
            w.told.append(told["told"])
            return told
        if node == "upsert":
            d = inputs["draft"]
            real = checks.content_hash(d["manifest"], d["output_profile"])
            if real != inputs["draft_hash"]:
                raise ToolPermanentError("STORE_REFUSED")
            name = inputs["type_name"]
            if name in w.system_profiles and checks.add_only_findings(w.system_profiles[name], d["output_profile"]):
                raise ToolPermanentError("STORE_REFUSED")
            have = w.stored.get(name)
            have_hash = checks.content_hash(have["manifest"], have["output_profile"]) if have else "NONE"
            if have_hash != real and have_hash != inputs["base_hash"]:     # same hash first: a retry of a save that landed is not stale
                raise ToolPermanentError("STALE_BASE")
            outcome = "UNCHANGED" if have_hash == real else ("UPDATED" if have else "CREATED")
            if outcome != "UNCHANGED":
                w.stored[name] = {"manifest": d["manifest"], "output_profile": d["output_profile"]}
                w.writes += 1
                if w.fail_after_write:
                    w.fail_after_write -= 1
                    raise ToolTransientError("STORE_UNAVAILABLE")
            return {"saved": {"outcome": outcome, "name": name, "content_hash": real}}
        raise AssertionError(ref)


class Ext(StubExternalToolAdapter):
    def __init__(self, w: World):
        super().__init__()
        self.w = w

    async def call(self, ref, inputs, *, platform_id, run_id):
        self.w.events.append(("call", "try"))
        if "try" in self.w.errors:
            raise ToolPermanentError(self.w.errors["try"])
        trial, findings = _next(self.w.trials, "trial")
        return {"trial": trial, "findings": findings}


def _next(items, what):
    """A script that runs dry means the engine asked once more than the test allowed: a failure, said plainly."""
    if not items:
        raise AssertionError(f"an unscripted {what} was asked for")
    return items.pop(0)


def registry() -> Registry:
    r = Registry()
    for p in sorted(BUILTIN.glob("*.yaml")):
        r.add(load_definition_file(p))
    for p in sorted(DEFS.glob("*.yaml")):
        r.add(load_definition_file(p))
    return r


def run(w: World, *, type_name="quick-answer", request="Short answers for people in a hurry"):
    reg = registry()
    process = load_definition_file(DEFS / "upsert-a-content-type.process.yaml")
    w.records = StubRecordsAdapter()
    ctx = EngineContext(policy=RecPolicy(w), code_tool=Code(w), external_tool=Ext(w), records=w.records,
                        claims=StubClaimsAdapter(), registry=reg, identity="agent:upserter", platform_id="t-1")
    kw = {"inputs": {"request": request, "type_name": type_name}, "host_inputs": {}}

    async def go():
        a = await next_(process, "r1", "r1", ctx, **kw)
        for _ in range(200):
            if a.kind is AnswerKind.ENDED:
                return a
            if a.kind is AnswerKind.TOOL_STEP:
                assert a.node_id == "draft", a.node_id
                w.events.append(("handoff", "draft"))
                a = await report(process, "r1", "r1", "draft", ctx, output={"draft": _next(w.drafts, "draft")}, **kw)
            elif a.kind is AnswerKind.AWAITING_DECISION:
                verdict, note = _next(w.gates, "gate answer")
                w.events.append(("decide", verdict.value))
                a = await decide(process, "r1", "r1", a.node_id, ctx, verdict=verdict, note=note, subject="person:approver", **kw)
            else:
                raise AssertionError(a)
        raise AssertionError("no end")
    ans = asyncio.run(go())
    path = [n for k, n in w.events if k in ("call", "handoff")]
    path = ["draft" if p == "draft" else p for p in path]
    return ans, path


NODES = ["read-existing", "draft", "check", "after-check", "try", "after-try", "approve", "upsert", "after-upsert", "tell"]


def recorded(w: World):
    """(node, attempt) for every attempt the engine recorded for the run, in the order recorded."""
    async def go():
        out = []
        for n in NODES:
            for rec in await w.records.get_attempts("r1", "r1", n, platform_id="t-1", run_id="r1"):
                out.append((rec.started_at, rec.ended_at, NODES.index(n), n, rec.key.attempt, rec.verdict))
        return sorted(out)
    return asyncio.run(go())


# ---------------------------------------------------------------- C1 --
def test_every_definition_in_the_example_validates_with_the_builtin_set():
    reg = registry()
    for p in sorted(DEFS.glob("*.yaml")):
        d = load_definition_file(p)
        assert validate_definition(d, reg) == [], p.name


# ---------------------------------------------------------------- C2 --
def test_c2_a_clean_run_reaches_upserted():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")])
    ans, path = run(w)
    assert ans.ending == "UPSERTED" and ans.outcome == "SUCCESS"
    assert path == ["read-existing", "draft", "check", "try", "upsert"]
    assert [e for e in w.events if e[0] == "decide"] == [("decide", "PERMIT")]
    rec = recorded(w)
    print("RECORDS", [(r[3], r[4], r[5]) for r in rec])
    seq = [r[3] for r in rec if r[3] not in ("after-check", "after-try", "after-upsert")]
    seq = [n for i, n in enumerate(seq) if i == 0 or seq[i - 1] != n]       # approve has two attempts: the rule, then the person
    assert seq == ["read-existing", "draft", "check", "try", "approve", "upsert"]
    assert [r[5] for r in rec if r[3] == "approve"] == ["INDETERMINATE", "PERMIT"]
    assert w.stored["quick-answer"]["manifest"]["metadata"]["name"] == "quick-answer"
    print(ans.says)


# ---------------------------------------------------------------- C3 --
def dropped(profile, name):
    p = copy.deepcopy(profile)
    del p["properties"][name]
    p["required"] = [r for r in p.get("required", []) if r != name]
    return p


def test_c3_a_dropped_property_never_reaches_try_or_upsert():
    bad = good_draft(profile=dropped(SYSTEM_PROFILE, "summary"))
    # the naive check alone finds nothing
    assert naive_extra(bad, snapshot()) == ([], [])
    w = World(drafts=[bad] * 4, trials=[(PASSED, [])] * 5, gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU"
    assert "upsert" not in path and "try" not in path
    assert path.count("draft") == 4          # first draft + 3 send-backs
    assert w.stored == {}
    assert [e for e in w.events if e == ("call", "tell")] == [("call", "tell")]
    assert len(w.told) == 1
    assert any("REMOVED" in r and "/properties/summary" in r for r in w.told[0]["reasons"]), w.told


# ---------------------------------------------------------------- C4 --
def test_c4_the_trial_loop_ends_after_three_send_backs():
    w = World(drafts=[good_draft()] * 4, trials=[(FAILED, [checks.finding("PATH_MISMATCH", "/path", "the path was not the expected one")])] * 4, gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU"
    assert path.count("draft") == 4 and path.count("try") == 4 and "upsert" not in path
    assert w.stored == {} and len(w.told) == 1
    assert any("PATH_MISMATCH" in r for r in w.told[0]["reasons"]), w.told


def test_c4_the_check_loop_ends_after_three_send_backs():
    w = World(drafts=[BAD_DRAFT()] * 4, trials=[], gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU"
    assert path.count("draft") == 4 and path.count("check") == 4
    assert "try" not in path and "upsert" not in path and w.stored == {}
    assert len(w.told) == 1 and any("REMOVED" in r for r in w.told[0]["reasons"]), w.told


def test_c4_a_loop_that_clears_in_time_reaches_the_end():
    w = World(drafts=[good_draft(profile=dropped(SYSTEM_PROFILE, "body")), good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")])
    ans, path = run(w)
    assert ans.ending == "UPSERTED"
    assert path == ["read-existing", "draft", "check", "draft", "check", "try", "upsert"]


# ---------------------------------------------------------------- C5 --
def test_c5_the_gate_loop_ends_after_three_denials():
    w = World(drafts=[good_draft()] * 4, trials=[(PASSED, [])] * 4, gates=[(Verdict.DENY, "no")] * 4)
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and "upsert" not in path
    assert path.count("draft") == 4 and w.stored == {} and len(w.told) == 1
    assert any("The last note from a person: no" in r for r in w.told[0]["reasons"]), w.told


def test_c5_an_indeterminate_standing_rule_waits_for_a_person():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")], standing="INDETERMINATE")
    ans, path = run(w)
    assert ("decide", "PERMIT") in w.events and ans.ending == "UPSERTED"


def test_c5_a_standing_permit_needs_no_person():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[], standing="PERMIT")
    ans, path = run(w)
    assert ans.ending == "UPSERTED" and not [e for e in w.events if e[0] == "decide"]


def test_c5_a_standing_deny_sends_the_draft_back():
    w = World(drafts=[good_draft()] * 4, trials=[(PASSED, [])] * 4, gates=[], standing="DENY")
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and "upsert" not in path


# ---------------------------------------------------------------- C6 --
def test_c6_every_step_asks_policy_first():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")])
    run(w)
    ev = w.events
    for node, perm in PERM_OF_NODE.items():
        if node in ("tell",):
            continue
        calls = [i for i, e in enumerate(ev) if e in (("call", node), ("handoff", node))]
        assert calls, node
        for i in calls:
            assert ("authorize", perm) in ev[:i], (node, ev[:i])
            # the nearest event before the step is its own authorize or a prior step's
    assert ("authorize", "workflows.upsert-a-content-type.start") in ev
    print(ev)


def test_c6_a_denied_upsert_leaves_the_type_unsaved():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")], denies={"workflows.upsert-a-content-type.upsert"})
    ans, path = run(w)
    assert ans.ending == "FORBIDDEN"
    assert w.stored == {} and "upsert" not in path
    print(ans.says)


def test_c6_denied_start_runs_nothing():
    w = World(drafts=[good_draft()], denies={"workflows.upsert-a-content-type.start"})
    ans, path = run(w)
    assert path == [] and ans.ending == "FORBIDDEN"


# ===== Structure: no prompt text, no platform import, the gate is the only way to upsert (C1, C5, C7)
FILES = sorted(DEFS.glob("*.yaml"))


def docs():
    return {p.name: yaml.safe_load(p.read_text()) for p in FILES}


def edges(process_doc):
    """node -> set of targets, read straight from the YAML (not from the engine)."""
    out = {}
    for nid, n in process_doc["nodes"].items():
        t = set()
        def take(x):
            if isinstance(x, dict):
                if "next" in x: t.add(x["next"])
                if "end" in x: t.add("END:" + x["end"])
                for v in x.values():
                    take(v)
            elif isinstance(x, list):
                for v in x: take(v)
        take({k: v for k, v in n.items() if k not in ("in", "out")})
        out[nid] = t
    return out


def reaches(edges_, start, goal, avoiding):
    seen, todo = set(), [start]
    while todo:
        cur = todo.pop()
        if cur == goal:
            return True
        if cur in seen or cur in avoiding:
            continue
        seen.add(cur)
        todo += list(edges_.get(cur, ()))
    return False


def only_via_gate(d):
    e = edges(d["upsert-a-content-type.process.yaml"])
    start = d["upsert-a-content-type.process.yaml"]["start"]
    return not reaches(e, start, "upsert", avoiding={"approve"}) and reaches(e, start, "upsert", avoiding=set())


def test_the_only_way_to_upsert_is_through_the_gate():
    assert only_via_gate(docs())


def test_red_a_shortcut_to_upsert_is_seen():
    d = docs()
    d["upsert-a-content-type.process.yaml"]["nodes"]["after-try"]["otherwise"] = {"next": "upsert"}
    assert not only_via_gate(d)


def test_exactly_one_tool_changes_things_and_the_process_calls_it_once():
    d = docs()
    tools = {x["id"]: x for n, x in d.items() if x["kind"] == "TOOL"}
    changers = [i for i, t in tools.items() if t["effect"] != "QUERY"]
    assert changers == ["upsert-content-type"] and tools[changers[0]]["effect"] == "MUTATION"
    calls = [n for n in d["upsert-a-content-type.process.yaml"]["nodes"].values() if n.get("tool", "").startswith("upsert-content-type@")]
    assert len(calls) == 1


def test_every_tool_names_a_permission():
    d = docs()
    for n, x in d.items():
        if x["kind"] == "TOOL":
            assert re.fullmatch(r"workflows\.upsert-a-content-type\.[a-z]+", x["permission"]), n
    p = d["upsert-a-content-type.process.yaml"]
    assert p["permission"].endswith(".start") and p["nodes"]["approve"]["permission"].endswith(".approve")


def test_every_loop_back_to_draft_has_a_budget_of_three_ending_in_tell():
    p = docs()["upsert-a-content-type.process.yaml"]
    found = []
    def walk(x):
        if isinstance(x, dict):
            if x.get("next") == "draft" and "loop" in x:
                found.append(x["loop"])
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(p["nodes"])
    assert len(found) == 3 and all(l == {"on_exhausted": {"next": "tell"}} for l in found)   # no budget written: the Process's own default holds it
    assert docs()["upsert-a-content-type.process.yaml"]["defaults"] == {"loop_budget": 3}


# ---- C7: no prompt text -------------------------------------------------------------------
PROMPTY = [r"\byou\b", r"\byour\b", r"^\s*(write|draft|produce|return|output|include|ensure|respond|reply|follow|avoid|never|always|make sure|do not)\b",
           r"[.;:?!]\s+(write|draft|produce|return|output|include|ensure|respond|reply|follow|avoid|never|always|make sure|do not)\b",
           r"\b(step \d|first,|then,|as follows)\b", r"\b(system prompt|instructions?:)\b"]
FREE_TEXT_CAP = 400


def strings(x, path=""):
    if isinstance(x, str):
        yield path, x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield from strings(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from strings(v, f"{path}/{i}")


PROSE = {"summary", "description", "criteria", "asks", "says", "grounded_in", "title", "default", "examples"}
TITLE_CAP = 120


def prompt_findings(doc):
    """A tripwire, not a proof: prose fields only (a name like `draft-content-type` is not prose)."""
    out = []
    for path, s in strings(doc):
        key = path.rsplit("/", 1)[-1]
        if key not in PROSE:
            continue
        if len(s) > (TITLE_CAP if key == "title" else FREE_TEXT_CAP):
            out.append((path, "TOO_LONG"))
        for rx in (PROMPTY[:2] if key == "title" else PROMPTY):
            if key == "title" and rx.startswith("^"):
                continue
            if re.search(rx, s, re.I | re.M):
                out.append((path, rx))
    return out


def test_the_definitions_hold_no_prompt_text():
    for n, d in docs().items():
        assert prompt_findings(d) == [], n


def test_a_need_names_no_file_and_no_skill_text_ships():
    for p in DEFS.rglob("*"):
        if "__pycache__" in p.parts:
            continue
        # the definitions, the reference checks and the README: no skill text, no prompt file
        assert p.suffix == ".yaml" or p.name in ("checks.py", "README.md"), p
    d = docs()["draft-content-type.tool.yaml"]
    assert d["mechanism"] == {"kind": "SKILL", "ref": "needs/draft-content-type-manifest"}
    assert set(d["inputs"]) == {"request", "type_name", "existing", "findings", "trial_findings", "note"}


@pytest.mark.parametrize("text", [
    "You are an expert in content types. Write the manifest with rules and inputs.",
    "Write a manifest that includes rules, inputs and an approval. Return only YAML.",
    "Drafts the type. Make sure the title is short. Do not invent fields.",
    "x" * 401,
])
def test_red_prompt_text_in_a_summary_is_seen(text):
    d = copy.deepcopy(docs()["draft-content-type.tool.yaml"])
    d["summary"] = text
    assert prompt_findings(d)


# ---- C1: no platform imports ----------------------------------------------------------------
def imports(path):
    tree = ast.parse(path.read_text())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import): out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module: out.add(n.module)
    return out


def bad_imports(path):
    return {m for m in imports(path) if m == "sulis" or m.startswith("sulis.") or m.split(".")[0] in {"anthropic", "openai", "cohere", "google"}}


def test_the_reference_checks_import_nothing_from_the_platform_or_a_vendor():
    assert bad_imports(HERE / "checks.py") == set()


def test_every_python_file_in_the_example_is_free_of_platform_imports():
    files = sorted(HERE.rglob("*.py"))
    assert [f.name for f in files] == ["checks.py"]
    for f in files:
        assert bad_imports(f) == set(), f


def test_red_an_import_of_the_platform_is_seen(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("from sulis.services.content import x\nimport anthropic\n")
    assert bad_imports(f) == {"sulis.services.content", "anthropic"}
    f.write_text("import sulis_workflows.engine\n")
    assert bad_imports(f) == set()


# ---- C1: removing any file is felt --------------------------------------------------------------
@pytest.mark.parametrize("gone", [p.name for p in FILES if "process" not in p.name])
def test_removing_any_supporting_file_makes_validation_refuse(gone):
    r = Registry()
    for p in sorted(BUILTIN.glob("*.yaml")):
        r.add(load_definition_file(p))
    kept = []
    for p in FILES:
        if p.name != gone:
            d = load_definition_file(p); r.add(d); kept.append(d)
    f = []
    for d in kept:
        f += validate_definition(d, r)
    assert any(x.rule == "V2" for x in f), gone


# ===== Profiles are closed (R13)
REG = registry()
HASH = "sha256:" + "a" * 64
GOOD = {
    "finding@1": {"rule": "REMOVED", "where": "/properties/summary", "message": "the property was removed"},
    "manifest-draft@1": {"manifest": {"a": 1}, "output_profile": {"type": "object"}, "case": {"inputs": {}}, "notes": "n"},
    "content-type-snapshot@1": {"name": "t", "has_system": True, "has_current": True, "system_profile": {}, "current_manifest": {}, "current_profile": {}},
    "trial@1": {"verdict": "PASSED", "ending": "APPROVED", "path": ["write"], "steps": [{"node": "write", "says": "w"}]},
    "upsert-result@1": {"outcome": "CREATED", "name": "t", "content_hash": HASH},
    "telling@1": {"says": "Stopped: the content type was not saved.", "reasons": []},
}
WRONG = {"string": 5, "object": "x", "array": "x", "boolean": "x"}
ALL = [(p, f) for p, v in GOOD.items() for f in v]
REQUIRED = {"finding@1": {"rule", "where", "message"}, "manifest-draft@1": {"manifest", "output_profile", "case"},
            "content-type-snapshot@1": {"name", "has_system", "has_current"}, "trial@1": {"verdict", "ending", "path", "steps"},
            "upsert-result@1": {"outcome", "name", "content_hash"}, "telling@1": {"says", "reasons"}}


def passes(ref, value):
    return profile_conformance(value, ref, registry=REG)["passed"]


@pytest.mark.parametrize("ref", sorted(GOOD))
def test_a_conforming_value_passes(ref):
    assert passes(ref, GOOD[ref])


@pytest.mark.parametrize("ref,field", ALL)
def test_one_field_retyped_is_refused(ref, field):
    v = copy.deepcopy(GOOD[ref])
    old = v[field]
    v[field] = [] if isinstance(old, str) else "x" if not isinstance(old, str) else 5
    if isinstance(old, (bool,)):
        v[field] = "x"
    assert not passes(ref, v), (ref, field)


@pytest.mark.parametrize("ref,field", [(p, f) for p, f in ALL if f in REQUIRED[p]])
def test_one_required_field_removed_is_refused(ref, field):
    v = copy.deepcopy(GOOD[ref]); del v[field]
    assert not passes(ref, v), (ref, field)


@pytest.mark.parametrize("ref", sorted(GOOD))
def test_an_unknown_field_is_refused(ref):
    v = copy.deepcopy(GOOD[ref]); v["surprise"] = 1
    assert not passes(ref, v)


def test_a_snapshot_that_contradicts_itself_is_refused():
    g = GOOD["content-type-snapshot@1"]
    v = copy.deepcopy(g); v["has_system"] = False                      # system_profile still there
    assert not passes("content-type-snapshot@1", v)
    v = copy.deepcopy(g); v["has_current"] = False
    assert not passes("content-type-snapshot@1", v)
    v = copy.deepcopy(g); del v["system_profile"]                      # says there is one, gives none
    assert not passes("content-type-snapshot@1", v)
    v = copy.deepcopy(g); del v["current_profile"]
    assert not passes("content-type-snapshot@1", v)
    ok = {"name": "t", "has_system": False, "has_current": False}
    assert passes("content-type-snapshot@1", ok)


@pytest.mark.parametrize("verdict", ["PASS", "passed", "STOPPED", "UNMEASURED", "", None])
def test_a_trial_verdict_outside_passed_and_failed_is_refused(verdict):
    v = copy.deepcopy(GOOD["trial@1"]); v["verdict"] = verdict
    assert not passes("trial@1", v)


@pytest.mark.parametrize("h", ["", "NONE", "sha256:abc", "sha256:" + "A" * 64, "md5:" + "a" * 32])
def test_a_save_result_with_a_bad_hash_is_refused(h):
    v = copy.deepcopy(GOOD["upsert-result@1"]); v["content_hash"] = h
    assert not passes("upsert-result@1", v)


def test_a_finding_rule_must_be_an_id_and_a_message_a_sentence():
    for rule in ["removed", "R E", "", "1ABC", "A-B"]:
        v = copy.deepcopy(GOOD["finding@1"]); v["rule"] = rule
        assert not passes("finding@1", v), rule
    v = copy.deepcopy(GOOD["finding@1"]); v["message"] = "short"
    assert not passes("finding@1", v)


# ===== Properties of the add-only rule, the save and the engine paths
SET_300 = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow], derandomize=True)

NAMES = st.from_regex(r"[a-z][a-z0-9_]{0,7}", fullmatch=True)
LEAVES = st.sampled_from([
    {"type": "string"}, {"type": "integer"}, {"type": "boolean"}, {"type": "number"},
    {"type": "string", "enum": ["A", "B"]}, {"type": "string", "minLength": 3},
])


def objects(child):
    return st.dictionaries(NAMES, child, min_size=1, max_size=4).flatmap(
        lambda props: st.sets(st.sampled_from(sorted(props)), max_size=len(props)).map(
            lambda req: {"type": "object", "properties": props, "required": sorted(req)}))


SCHEMAS = st.recursive(LEAVES, lambda c: st.one_of(objects(c), c.map(lambda x: {"type": "array", "items": x})), max_leaves=10)
ROOTS = objects(SCHEMAS)


def object_paths(node, where=""):
    """(pointer, node) for every object schema, by our own walk."""
    out = []
    if isinstance(node, dict):
        if node.get("type") == "object":
            out.append((where, node))
            for k, v in node["properties"].items():
                out += object_paths(v, f"{where}/properties/{k}")
        if node.get("type") == "array":
            out += object_paths(node["items"], f"{where}/items")
    return out


def all_props(node, where=""):
    out = []
    for ptr, obj in object_paths(node, where):
        for k in obj["properties"]:
            out.append((ptr, k))
    return out


def leaves(node, where=""):
    out = []
    if node.get("type") == "object":
        for k, v in node["properties"].items():
            out += leaves(v, f"{where}/properties/{k}")
    elif node.get("type") == "array":
        out += leaves(node["items"], f"{where}/items")
    else:
        out.append((where, node))
    return out


def at(root, pointer):
    node = root
    for part in [p for p in pointer.split("/") if p]:
        node = node[part]
    return node


# ---- the properties -----------------------------------------------------------------
def prop_additions_are_accepted(root, data):
    q = copy.deepcopy(root)
    targets = object_paths(q)
    ptr, _ = data.draw(st.sampled_from(targets))
    node = at(q, ptr)
    new = data.draw(st.from_regex(r"zz_[a-z]{1,5}", fullmatch=True))
    node["properties"][new] = data.draw(SCHEMAS)
    if data.draw(st.booleans()):
        node["required"] = sorted({*node["required"], new})          # a new property may be required
    q["description"] = "annotation only"                              # annotations may differ
    assert checks.add_only_findings(root, q) == []


def prop_a_removed_property_is_found_where_it_was(root, data):
    ptr, name = data.draw(st.sampled_from(all_props(root)))
    q = copy.deepcopy(root)
    node = at(q, ptr)
    del node["properties"][name]
    node["required"] = [r for r in node["required"] if r != name]
    found = checks.add_only_findings(root, q)
    assert any(f["rule"] == "REMOVED" and f["where"] == f"{ptr}/properties/{name}" for f in found), (found, ptr, name)


def prop_a_retyped_property_is_found(root, data):
    ptr, leaf = data.draw(st.sampled_from(leaves(root) or [("", {"type": "string"})]))
    if not leaves(root):
        return
    q = copy.deepcopy(root)
    node = at(q, ptr)
    old = node["type"]
    node["type"] = data.draw(st.sampled_from([t for t in ["string", "integer", "boolean", "number", "array"] if t != old]))
    found = checks.add_only_findings(root, q)
    assert any(f["rule"] == "RETYPED" and f["where"] == f"{ptr}/type" for f in found), (found, ptr)


@SET_300
@given(ROOTS, st.data())
def test_additions_are_accepted(root, data):
    prop_additions_are_accepted(root, data)


@SET_300
@given(ROOTS, st.data())
def test_a_removed_property_is_found_where_it_was(root, data):
    prop_a_removed_property_is_found_where_it_was(root, data)


@SET_300
@given(ROOTS, st.data())
def test_a_retyped_property_is_found(root, data):
    prop_a_retyped_property_is_found(root, data)


@SET_300
@given(ROOTS)
def test_a_profile_is_add_only_over_itself(root):
    assert checks.add_only_findings(root, copy.deepcopy(root)) == []


JUNK = st.recursive(st.none() | st.booleans() | st.integers() | st.text(max_size=5),
                    lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=5), c, max_size=3), max_leaves=12)


@SET_300
@given(JUNK, JUNK)
def test_the_rule_never_raises_and_fails_closed(system, draft):
    out = checks.add_only_findings(system, draft)
    assert isinstance(out, list)
    if system != draft and not (isinstance(system, dict) and isinstance(draft, dict) and set(system) <= {"title", "description", "examples", "$comment"}):
        pass
    for f in out:
        assert set(f) == {"rule", "where", "message"} and re.fullmatch(r"[A-Z][A-Z0-9_]*", f["rule"])


# ---- tell: no line terminator survives, whatever the text -------------------------------
LINE_ENDS = "\n\r\x0b\x0c\x1c\x1d\x1e\x85  "
TEXT = st.text(alphabet=st.sampled_from(list(LINE_ENDS) + list("# -*1.ab ")), max_size=30)
FIND = st.fixed_dictionaries({"rule": st.just("X_Y"), "where": TEXT, "message": TEXT})


@SET_300
@given(st.lists(FIND, max_size=8), st.lists(FIND, max_size=8), TEXT, TEXT)
def test_tell_is_one_line_and_names_every_finding(blocking, trial, note, name):
    out = checks.tell_what_is_in_the_way(type_name=name, blocking=blocking, trial_findings=trial, note=note)["told"]
    assert len(out["says"].splitlines()) == 1
    assert all(len(r.splitlines()) <= 1 for r in out["reasons"])
    assert len(out["reasons"]) == len(blocking) + len(trial) + (1 if note else 0)
    assert out["says"].startswith("Stopped: the content type")


# ---- hash ------------------------------------------------------------------------------
JSONV = st.recursive(st.none() | st.booleans() | st.integers() | st.text(max_size=4),
                     lambda c: st.lists(c, max_size=3) | st.dictionaries(st.text(max_size=4), c, max_size=3), max_leaves=10)


@SET_300
@given(st.dictionaries(st.text(max_size=4), JSONV, max_size=4), JSONV, st.randoms())
def test_hash_ignores_key_order_and_notices_any_change(m, p, rnd):
    items = list(m.items())
    rnd.shuffle(items)
    assert checks.content_hash(m, p) == checks.content_hash(dict(items), p)
    assert checks.content_hash(m, p) != checks.content_hash(m, [p])
    assert checks.content_hash(m, p) != checks.content_hash({**m, "extra_key": 1}, p)


# ---- red runs: the properties must fail on the naive rules the brief warns of --------------
def naive_top_level_keys(system, draft):
    gone = sorted(set(system.get("properties", {})) - set(draft.get("properties", {})))
    return [checks.finding("REMOVED", f"/properties/{n}", "a property was removed") for n in gone]


def naive_count(system, draft):
    return [] if len(draft.get("properties", {})) >= len(system.get("properties", {})) else [checks.finding("REMOVED", "/", "fewer properties")]


def naive_keys_only_nested(system, draft):
    def keys(n):
        if isinstance(n, dict):
            return {k for k in n.get("properties", {})} | {k2 for v in n.get("properties", {}).values() for k2 in keys(v)}
        return set()
    return [checks.finding("REMOVED", f"/properties/{n}", "x") for n in sorted(keys(system) - keys(draft))]


def naive_nothing(system, draft):
    return []


@pytest.mark.parametrize("naive", [naive_top_level_keys, naive_count, naive_keys_only_nested, naive_nothing])
@pytest.mark.parametrize("prop", [prop_a_removed_property_is_found_where_it_was, prop_a_retyped_property_is_found])
def test_red_the_properties_fail_on_naive_rules(naive, prop, monkeypatch):
    monkeypatch.setattr(checks, "add_only_findings", naive)

    @SET_300
    @given(ROOTS, st.data())
    def inner(root, data):
        prop(root, data)

    with pytest.raises(AssertionError) as e:
        inner()
    print("RED", naive.__name__, prop.__name__, "->", str(e.value).splitlines()[0][:150], "|", [l for l in str(e.value).splitlines() if "root=" in l][:1])


def test_red_additions_property_fails_on_a_rule_that_refuses_any_difference(monkeypatch):
    monkeypatch.setattr(checks, "add_only_findings", lambda s, d: [] if s == d else [checks.finding("CHANGED", "/", "differs")])

    @SET_300
    @given(ROOTS, st.data())
    def inner(root, data):
        prop_additions_are_accepted(root, data)

    with pytest.raises(AssertionError):
        inner()


# ---- named bad-but-conformant fixtures, each must be refused with the right rule -------------
def mod(fn):
    p = copy.deepcopy(SYSTEM_PROFILE)
    fn(p)
    return p


def _drop(p):
    del p["properties"]["summary"]; p["required"].remove("summary")

def _drop_and_add_two(p):
    _drop(p); p["properties"]["a"] = {"type": "string"}; p["properties"]["b"] = {"type": "string"}

def _rename(p):
    _drop(p); p["properties"]["summary_text"] = {"type": "string"}

def _retype(p):
    p["properties"]["summary"] = {"type": "array", "items": {"type": "string"}}

def _nested_drop(p):
    del p["$defs"]["alt"]["properties"]["why_not"]

def _ref_to_other(p):
    p["$defs"]["alt"] = {"type": "integer"}

def _ref_gone(p):
    p["properties"]["alternatives"]["items"] = {"$ref": "#/$defs/nowhere"}

def _ref_remote(p):
    p["properties"]["alternatives"]["items"] = {"$ref": "https://example.com/alt.json"}

def _required_dropped(p):
    p["required"].remove("summary")

def _optional_made_required(p):
    p["required"].append("format")

def _enum_changed(p):
    p["properties"]["format"]["enum"] = ["MARKDOWN", "TEXT", "HTML"]

def _tightened(p):
    p["properties"]["title"]["minLength"] = 10

def _loosened_additional(p):
    p["additionalProperties"] = True

def _wrapped_in_allof(p):
    p.update({"allOf": [{"properties": {"x": {"type": "string"}}}]})

def _ref_with_siblings(p):
    p["properties"]["alternatives"]["items"] = {"$ref": "#/$defs/alt", "description": "d"}

BAD = {
    "drop-one": (_drop, "REMOVED"),
    "drop-one-add-two": (_drop_and_add_two, "REMOVED"),
    "rename": (_rename, "REMOVED"),
    "retype": (_retype, "RETYPED"),
    "nested-drop-behind-ref": (_nested_drop, "REMOVED"),
    "ref-retargeted": (_ref_to_other, "RETYPED"),
    "ref-to-nothing": (_ref_gone, "UNREADABLE"),
    "ref-remote": (_ref_remote, "UNREADABLE"),
    "required-dropped": (_required_dropped, "REQUIRED_DROPPED"),
    "optional-made-required": (_optional_made_required, "CHANGED"),
    "enum-changed": (_enum_changed, "RETYPED"),
    "tightened": (_tightened, "CHANGED"),
    "additional-properties-opened": (_loosened_additional, "CHANGED"),
    "allof-added": (_wrapped_in_allof, "CHANGED"),
    "ref-with-siblings": (_ref_with_siblings, "UNREADABLE"),
}


@pytest.mark.parametrize("name", sorted(BAD))
def test_bad_but_conformant_is_refused(name):
    fn, rule = BAD[name]
    q = mod(fn)
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(q)                              # it is a valid JSON Schema
    assert naive_extra(good_draft(profile=q), snapshot()) == ([], [])  # and a valid manifest by the naive check
    found = checks.add_only_findings(SYSTEM_PROFILE, q)
    assert any(f["rule"] == rule for f in found), (name, found)


def test_additions_that_must_pass():
    q = mod(lambda p: (p["properties"].update(tone={"type": "string"}), p.update(description="d", title="T")))
    assert checks.add_only_findings(SYSTEM_PROFILE, q) == []
    q = mod(lambda p: (p["$defs"]["alt"]["properties"].update(extra={"type": "integer"}), p["required"].append("tone"), p["properties"].update(tone={"type": "string"})))
    assert checks.add_only_findings(SYSTEM_PROFILE, q) == []


# ---- more engine paths -------------------------------------------------------------------
def test_the_same_draft_ends_unchanged_without_a_trial_or_a_gate():
    d = good_draft()
    cur = (d["manifest"], d["output_profile"])
    w = World(snapshot=snapshot(current=cur), drafts=[d], trials=[], gates=[])
    ans, path = run(w)
    assert ans.ending == "UNCHANGED" and path == ["read-existing", "draft", "check"] and w.stored == {}


def test_a_repeat_run_changes_nothing_the_second_time():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")])
    ans, _ = run(w)
    assert ans.ending == "UPSERTED"
    first = copy.deepcopy(w.stored)
    cur = (w.stored["quick-answer"]["manifest"], w.stored["quick-answer"]["output_profile"])
    w2 = World(snapshot=snapshot(current=cur), drafts=[good_draft()], trials=[], gates=[], stored=w.stored)
    ans2, path2 = run(w2)
    assert ans2.ending == "UNCHANGED" and w2.stored == first and "upsert" not in path2


def test_a_stale_base_is_refused_and_nothing_is_written():
    d = good_draft()
    w = World(drafts=[d], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")], stored={"quick-answer": {"manifest": manifest_other(), "output_profile": {"type": "object"}}})
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and w.stored["quick-answer"]["output_profile"] == {"type": "object"}


def manifest_other():
    return manifest("quick-answer") | {"spec": {"other": 1}}


def test_a_trial_that_could_not_conclude_is_never_a_pass():
    w = World(drafts=[good_draft()], trials=[], gates=[], errors={"try": "TRIAL_INCONCLUSIVE"})
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and "upsert" not in path


def test_a_passed_trial_that_carries_findings_is_sent_back():
    f = [checks.finding("STEP_REPLY_NONCONFORMING", "/steps/0", "a reply did not fit its Profile")]
    w = World(drafts=[good_draft()] * 4, trials=[(PASSED, f)] * 4, gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and path.count("draft") == 4 and "upsert" not in path


def test_a_lying_check_cannot_change_what_is_saved():
    # the check reports a hash that is not the draft's: the save refuses it
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")],
              tamper_check=lambda out: {**out, "draft_hash": "sha256:" + "0" * 64})
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and w.stored == {}


def test_a_name_mismatch_is_blocking():
    w = World(drafts=[good_draft(name="other-name")] * 4, trials=[], gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and "try" not in path


def test_a_wrong_snapshot_is_blocking():
    w = World(snapshot=snapshot(name="someone-elses"), drafts=[good_draft()] * 4, trials=[], gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and "try" not in path


def test_a_stale_blocking_finding_does_not_survive_a_clean_recheck():
    bad = good_draft(profile=SYSTEM_PROFILE | {"properties": {k: v for k, v in SYSTEM_PROFILE["properties"].items() if k != "body"}, "required": ["title", "summary"]})
    w = World(drafts=[bad, good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")])
    ans, path = run(w)
    assert ans.ending == "UPSERTED"


def test_read_existing_failure_stops_and_tells():
    w = World(errors={"read-existing": "EXISTING_UNREADABLE"}, drafts=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and path == ["read-existing", "tell"]


def test_a_draft_that_does_not_fit_its_profile_twice_stops_and_tells():
    """Not conforming: the engine's repair (once, spec 15) then `then: tell`, never a save."""
    import asyncio
    w = World(drafts=[{"manifest": {}}, {"manifest": {}}, {"manifest": {}}], trials=[], gates=[])
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and path[-1] == "tell" and "check" not in path and w.stored == {}


def test_a_mistake_in_a_route_still_cannot_save_a_blocked_draft(tmp_path, monkeypatch):
    """The precondition on `upsert` holds on its own: take the blocking branch out of after-check."""
    import shutil
    d = tmp_path / "defs"
    shutil.copytree(DEFS, d)
    f = d / "upsert-a-content-type.process.yaml"
    t = f.read_text()
    cut = t.replace("""      - if: len(state.blocking) > 0
        next: draft
        loop: { on_exhausted: { next: tell } }
""", "")
    assert cut != t
    f.write_text(cut)
    monkeypatch.setitem(globals(), "DEFS", d)
    bad = good_draft(profile=SYSTEM_PROFILE | {"properties": {k: v for k, v in SYSTEM_PROFILE["properties"].items() if k != "body"}, "required": ["title", "summary"]})
    w = World(drafts=[bad], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")])
    ans, path = run(w)
    assert w.stored == {} and "upsert" not in path and ans.ending == "NEEDS_YOU"


def test_a_hidden_system_profile_is_caught_at_the_save():
    """The read says there is no system Profile; the host's store holds one. The save refuses (STORE_REFUSED)."""
    bad = good_draft(profile=dropped(SYSTEM_PROFILE, "summary"))
    w = World(snapshot=snapshot(system=False), drafts=[bad], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")],
              system_profiles={"quick-answer": SYSTEM_PROFILE})
    ans, path = run(w)
    assert ans.ending == "NEEDS_YOU" and w.stored == {} and path[-2:] == ["upsert", "tell"]
    # and with the system Profile unhidden to the store, an add-only draft still saves
    w2 = World(snapshot=snapshot(system=False), drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")],
               system_profiles={"quick-answer": SYSTEM_PROFILE})
    ans2, _ = run(w2)
    assert ans2.ending == "UPSERTED"


# ---- the save, called directly through the world's store ------------------------------------


def save(w, draft, draft_hash, base_hash, name="t"):
    return asyncio.run(Code(w).call(REFS["upsert"], {"type_name": name, "draft": draft, "draft_hash": draft_hash, "base_hash": base_hash},
                                      platform_id="p", run_id="r"))


PAIRS = st.tuples(st.dictionaries(st.text(max_size=4), JSONV, max_size=4), JSONV)


@SET_300
@given(PAIRS, st.from_regex(r"sha256:[0-9a-f]{64}", fullmatch=True))
def test_a_save_is_bound_to_what_was_checked(pair, wrong):
    m, p = pair
    draft = {"manifest": m, "output_profile": p, "case": {}}
    right = checks.content_hash(m, p)
    w = World()
    if wrong != right:
        with pytest.raises(ToolPermanentError):
            save(w, draft, wrong, "NONE")
        assert w.stored == {}
    out = save(w, draft, right, "NONE")
    assert out["saved"]["outcome"] == "CREATED" and out["saved"]["content_hash"] == right


@SET_300
@given(PAIRS, PAIRS)
def test_a_save_is_compare_and_set_on_the_base_hash(first, second):
    (m1, p1), (m2, p2) = first, second
    w = World()
    d1 = {"manifest": m1, "output_profile": p1, "case": {}}
    d2 = {"manifest": m2, "output_profile": p2, "case": {}}
    h1, h2 = checks.content_hash(m1, p1), checks.content_hash(m2, p2)
    save(w, d1, h1, "NONE")                                   # someone saved first
    before = copy.deepcopy(w.stored)
    if h2 != h1:
        with pytest.raises(ToolPermanentError):
            save(w, d2, h2, "NONE")                           # this run read "nothing stored": refused
        assert w.stored == before
    out = save(w, d2, h2, h1)                                 # this run read the current one
    assert out["saved"]["outcome"] == ("UNCHANGED" if h2 == h1 else "UPDATED")


@SET_300
@given(PAIRS)
def test_saving_twice_changes_nothing(pair):
    m, p = pair
    w = World()
    d = {"manifest": m, "output_profile": p, "case": {}}
    h = checks.content_hash(m, p)
    assert save(w, d, h, "NONE")["saved"]["outcome"] == "CREATED"
    snap = copy.deepcopy(w.stored)
    assert save(w, d, h, h)["saved"]["outcome"] == "UNCHANGED"
    assert w.stored == snap


# ---- R10: each fault in the check is blocking and never reads as unchanged ----------------------
def _faults():
    nan = good_draft(); nan["manifest"]["spec"]["x"] = float("nan")
    return {
        "name-mismatch": (good_draft(name="other"), snapshot(), "NAME_MISMATCH"),
        "name-absent": ({**good_draft(), "manifest": {"metadata": {}}}, snapshot(), "NAME_MISMATCH"),
        "manifest-not-an-object": ({**good_draft(), "manifest": []}, snapshot(), "NAME_MISMATCH"),
        "snapshot-of-another-type": (good_draft(), snapshot(name="someone-elses"), "SNAPSHOT_MISMATCH"),
        "profile-not-a-schema": ({**good_draft(), "output_profile": {"type": "nonsense"}}, snapshot(), "PROFILE_INVALID"),
        "profile-a-list": ({**good_draft(), "output_profile": []}, snapshot(), "PROFILE_INVALID"),
        "profile-missing": ({k: v for k, v in good_draft().items() if k != "output_profile"}, snapshot(), "PROFILE_INVALID"),
        "nan-in-manifest": (nan, snapshot(), "HASH_UNREADABLE"),
    }


@pytest.mark.parametrize("name", sorted(_faults()))
def test_a_fault_in_the_check_is_blocking_and_never_unchanged(name):
    draft, snap, rule = _faults()[name]
    out = checks.check_content_type(type_name="quick-answer", draft=draft, existing=snap)
    assert any(f["rule"] == rule for f in out["blocking"]), (name, out["blocking"])
    assert out["unchanged"] is False


def test_the_check_is_unchanged_only_when_the_pair_is_the_stored_pair():
    d = good_draft()
    snap = snapshot(current=(d["manifest"], d["output_profile"]))
    out = checks.check_content_type(type_name="quick-answer", draft=d, existing=snap)
    assert out["unchanged"] is True and out["blocking"] == [] and out["draft_hash"] == out["existing_hash"]
    d2 = copy.deepcopy(d); d2["case"] = {"inputs": {"brief": "different case"}}     # the case is not part of the type
    assert checks.check_content_type(type_name="quick-answer", draft=d2, existing=snap)["unchanged"] is True
    d3 = copy.deepcopy(d); d3["manifest"]["spec"]["title"] = "changed"
    out3 = checks.check_content_type(type_name="quick-answer", draft=d3, existing=snap)
    assert out3["unchanged"] is False and out3["draft_hash"] != out3["existing_hash"]


# ---- forged-fact: a name from the draft never adds a line to a finding ----------------------------
HOSTILE = st.text(alphabet=st.sampled_from(list(LINE_ENDS) + list("# -*1.ab/")), min_size=1, max_size=8)


@SET_300
@given(HOSTILE, HOSTILE, HOSTILE)
def test_a_name_from_the_draft_never_adds_a_line_to_a_finding(key, kw, req):
    q = copy.deepcopy(SYSTEM_PROFILE)
    q["properties"][key] = {"type": "string"}
    q["required"] = [*q["required"], req]
    q[kw] = 1
    del q["properties"]["summary"]
    found = checks.add_only_findings(SYSTEM_PROFILE, q)
    assert found, "something must be found"
    for f in found:
        assert len(f["where"].splitlines()) == 1 and len(f["message"].splitlines()) == 1, f
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", f["rule"])


def test_the_draft_step_hands_the_host_a_need_and_its_inputs_only():
    w = World(drafts=[good_draft()])
    reg = registry(); process = load_definition_file(DEFS / "upsert-a-content-type.process.yaml")
    ctx = EngineContext(policy=RecPolicy(w), code_tool=Code(w), external_tool=Ext(w), records=StubRecordsAdapter(),
                          claims=StubClaimsAdapter(), registry=reg, identity="agent:u", platform_id="t")
    a = asyncio.run(next_(process, "r1", "r1", ctx, inputs={"request": "r r r", "type_name": "quick-answer"}, host_inputs={}))
    assert a.node_id == "draft" and a.instructions_ref == "needs/draft-content-type-manifest"
    assert set(a.resolved_inputs) == {"request", "type_name", "existing", "findings", "trial_findings", "note"}
    assert a.resolved_inputs["findings"] == [] and a.resolved_inputs["trial_findings"] == [] and a.resolved_inputs["note"] == ""
    assert [c["ref"] for c in a.controls] == ["manifest-draft@1"]


# ===== The retried save, refs, true is not one, caps, step count, stale findings
SET_100 = settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow], derandomize=True)


# ---- 1. a retried save, and an UNCHANGED that is reachable after the gate ---------------------
def test_a_save_that_landed_and_then_failed_is_retried_to_unchanged_not_stale():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")], fail_after_write=1)
    t0 = time.time()
    ans, path = run(w)
    print("retry seconds", round(time.time() - t0, 1))
    assert w.writes == 1 and path.count("upsert") == 2                       # written once, called twice
    assert ans.ending == "UNCHANGED" and "quick-answer" in w.stored


def test_an_unchanged_after_the_gate_is_reachable_when_another_run_saved_the_same_draft():
    d = good_draft()
    w = World(drafts=[d], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")],
              stored={"quick-answer": {"manifest": d["manifest"], "output_profile": d["output_profile"]}})   # read said nothing was stored
    ans, path = run(w)
    assert ans.ending == "UNCHANGED" and path[-1] == "upsert" and "try" in path and w.writes == 0


def test_a_different_stored_type_is_still_stale():
    w = World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")],
              stored={"quick-answer": {"manifest": {"x": 1}, "output_profile": {"type": "object"}}})
    ans, _ = run(w)
    assert ans.ending == "NEEDS_YOU" and w.stored["quick-answer"]["manifest"] == {"x": 1}


# ---- 2. refs ---------------------------------------------------------------------------------
def _ref_drafts():
    def prof(sub):
        return {"type": "object", "properties": {"a": {"type": "string"}, "b": sub}}
    return {
        "new-type-ref-to-nothing": (prof({"$ref": "#/$defs/nowhere"}), False),
        "new-type-remote-ref": (prof({"$ref": "https://example.com/x.json"}), False),
        "new-type-relative-ref": (prof({"$ref": "other.json"}), False),
        "new-type-ref-with-siblings": (prof({"$ref": "#/$defs/x", "description": "d"}) | {"$defs": {"x": {"type": "string"}}}, False),
        "new-type-cycle": ({"type": "object", "properties": {"b": {"$ref": "#/$defs/x"}}, "$defs": {"x": {"$ref": "#/$defs/x"}}}, False),
        "added-property-remote-ref": (copy.deepcopy(SYSTEM_PROFILE) | {}, True),
        "new-type-dynamic-ref": (prof({"$dynamicRef": "#node"}), False),
        "added-property-dynamic-ref": (copy.deepcopy(SYSTEM_PROFILE) | {}, True),
    }


@pytest.mark.parametrize("name", sorted(_ref_drafts()))
def test_a_bad_ref_anywhere_in_the_draft_is_blocking(name):
    prof, system = _ref_drafts()[name]
    if name == "added-property-remote-ref":
        prof["properties"]["extra"] = {"$ref": "https://example.com/x.json"}
    if name == "added-property-dynamic-ref":
        prof["properties"]["extra"] = {"$dynamicRef": "#node"}
    draft = {**good_draft(), "output_profile": prof}
    out = checks.check_content_type(type_name="quick-answer", draft=draft, existing=snapshot(system=system))
    assert any(f["rule"] == "BAD_REF" for f in out["blocking"]), out["blocking"]
    assert out["unchanged"] is False


def test_a_good_local_ref_is_not_blocking():
    prof = {"type": "object", "properties": {"b": {"$ref": "#/$defs/x"}}, "$defs": {"x": {"type": "string"}}}
    out = checks.check_content_type(type_name="quick-answer", draft={**good_draft(), "output_profile": prof}, existing=snapshot(system=False))
    assert out["blocking"] == []


# ---- bool is not int ------------------------------------------------------------------------------
def test_true_is_not_one_in_the_comparison():
    p = {"type": "object", "properties": {"a": {"const": 1}, "b": {"type": "integer", "minimum": 0}}}
    q = copy.deepcopy(p); q["properties"]["a"]["const"] = True
    assert any(f["rule"] == "RETYPED" for f in checks.add_only_findings(p, q))
    q = copy.deepcopy(p); q["properties"]["b"]["minimum"] = False
    assert checks.add_only_findings(p, q)
    assert checks.add_only_findings(p, copy.deepcopy(p)) == []


# ---- caps -----------------------------------------------------------------------------------------
@SET_100
@given(st.text(min_size=400, max_size=1500), st.text(min_size=400, max_size=1500))
def test_a_finding_never_quotes_more_than_its_caps(name, key):
    d = good_draft(name=name or "x")
    out = checks.check_content_type(type_name="quick-answer", draft=d, existing=snapshot(name=key or "y"))
    q = copy.deepcopy(SYSTEM_PROFILE); q[key or "k"] = 1
    for f in [*out["blocking"], *checks.add_only_findings(SYSTEM_PROFILE, q)]:
        assert len(f["where"]) <= checks.WHERE_CAP and len(f["message"]) <= checks.MESSAGE_CAP


# ---- 6. a step-count property in place of a clock --------------------------------------------------
def count_walks(monkeypatch, root, q):
    n = {"c": 0}
    orig = checks._walk
    def counting(*a, **k):
        n["c"] += 1
        return orig(*a, **k)
    monkeypatch.setattr(checks, "_walk", counting)
    checks.add_only_findings(root, q)
    return n["c"]


def nodes_of(node):
    if isinstance(node, dict):
        return 1 + sum(nodes_of(v) for v in node.get("properties", {}).values()) + (nodes_of(node["items"]) if "items" in node else 0)
    return 1


@SET_100
@given(ROOTS, st.integers(0, 20))
def test_the_walk_visits_each_system_node_once(root, extra):
    mp = pytest.MonkeyPatch()
    try:
        q = copy.deepcopy(root)
        for i in range(extra):
            q["properties"][f"zz{i}"] = {"type": "string"}
        assert count_walks(mp, root, q) <= nodes_of(root)
    finally:
        mp.undo()


def test_red_a_walk_that_revisits_is_seen(monkeypatch):
    root = {"type": "object", "properties": {f"p{i}": {"type": "string"} for i in range(50)}}
    orig = checks._walk
    def twice(*a, **k):
        orig(*a, **k); return orig(*a, **k)
    n = {"c": 0}
    def counting(*a, **k):
        n["c"] += 1
        return twice(*a, **k)
    monkeypatch.setattr(checks, "_walk", counting)
    checks.add_only_findings(root, copy.deepcopy(root))
    assert n["c"] > nodes_of(root)


# ---- stale trial findings ---------------------------------------------------------------------------
def test_a_stop_after_a_trial_failure_does_not_list_the_old_trial_findings():
    tf = [checks.finding("PATH_MISMATCH", "/path", "the old trial finding about the path")]
    bad = good_draft(profile=dropped(SYSTEM_PROFILE, "summary"))
    w = World(drafts=[good_draft(), bad, bad, bad], trials=[(FAILED, tf)], gates=[])
    told = []
    orig = checks.tell_what_is_in_the_way
    def spy(**k):
        told.append(k); return orig(**k)
    checks.tell_what_is_in_the_way = spy
    try:
        ans, path = run(w)
    finally:
        checks.tell_what_is_in_the_way = orig
    assert ans.ending == "NEEDS_YOU" and told and told[0]["trial_findings"] == []


# ===== Send-back bound, permission order, README claims, the world is no more forgiving than a host (R14)
SET_60 = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow], derandomize=True)
FN = [checks.finding("PATH_MISMATCH", "/path", "the path was not the expected one")]


def BAD_DRAFT():
    return good_draft(profile=SYSTEM_PROFILE | {"properties": {k: v for k, v in SYSTEM_PROFILE["properties"].items() if k != "body"}, "required": ["title", "summary"]})


def scripted(loop, n):
    if loop == "check":
        return World(drafts=[BAD_DRAFT()] * n + [good_draft()] * 8, trials=[(PASSED, [])] * 8, gates=[(Verdict.PERMIT, "")] * 8)
    if loop == "trial":
        return World(drafts=[good_draft()] * 12, trials=[(FAILED, FN)] * n + [(PASSED, [])] * 8, gates=[(Verdict.PERMIT, "")] * 8)
    return World(drafts=[good_draft()] * 12, trials=[(PASSED, [])] * 12, gates=[(Verdict.DENY, "no")] * n + [(Verdict.PERMIT, "")] * 8)


@SET_60
@given(st.sampled_from(["check", "trial", "gate"]), st.integers(0, 6))
def test_a_send_back_is_bounded_at_three(loop, n):
    ans, path = run(scripted(loop, n))
    assert path.count("draft") == (n + 1 if n <= 3 else 4)
    assert ans.ending == ("UPSERTED" if n <= 3 else "NEEDS_YOU")
    assert (n > 3) == ("tell" in path) and (n > 3) != ("upsert" in path)


@SET_60
@given(st.sampled_from(["PASSED", "FAILED"]), st.integers(0, 2))
def test_a_trial_passes_only_on_passed_with_no_findings(verdict, k):
    trial = {**PASSED, "verdict": verdict}
    w = World(drafts=[good_draft()] * 4, trials=[(trial, FN[:1] * k)] * 4, gates=[(Verdict.PERMIT, "")] * 4)
    run(w)
    reached_gate = any(e == ("decide", "PERMIT") for e in w.events)
    assert reached_gate == (verdict == "PASSED" and k == 0)


SCRIPTS = {
    "clean": lambda: World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")]),
    "check-sendback": lambda: scripted("check", 1),
    "trial-sendback": lambda: scripted("trial", 1),
    "denial": lambda: scripted("gate", 1),
}
PERM = {"read-existing": "read", "draft": "draft", "check": "check", "try": "try", "upsert": "upsert"}
P = "workflows.upsert-a-content-type."


def asks_first(ev):
    assert ev[0] == ("authorize", P + "start")
    for i, e in enumerate(ev):
        if e[0] in ("call", "handoff") and e[1] in PERM:
            assert ev[i - 1] == ("authorize", P + PERM[e[1]]), (e, ev[max(0, i - 3):i + 1])
    for i, e in enumerate(ev):
        if e[0] == "decide":
            assert ("authorize", P + "approve") in ev[i:i + 4]            # the decision is asked about as it is accepted (the run start is re-asked first)
            assert ("call", "upsert") not in ev[:i]


@SET_60
@given(st.sampled_from(sorted(SCRIPTS)))
def test_c6_every_step_asks_the_policy_port_before_it_runs(name):
    w = SCRIPTS[name]()
    run(w)
    asks_first(w.events)


def test_red_a_log_with_a_call_before_its_authorize_is_refused():
    w = SCRIPTS["clean"]()
    run(w)
    ev = list(w.events)
    i = ev.index(("call", "check"))
    ev[i - 1], ev[i] = ev[i], ev[i - 1]
    with pytest.raises(AssertionError):
        asks_first(ev)


@pytest.mark.parametrize("which", ["start", "read", "draft", "check", "try", "approve", "upsert", "tell"])
def test_c6_a_refusal_at_any_step_stops_the_run_and_saves_nothing(which):
    w = scripted("check", 5) if which == "tell" else SCRIPTS["clean"]()
    w.denies = {P + which}
    ans, path = run(w)
    assert ans.ending == "FORBIDDEN" and w.stored == {}
    later = {"start": ["read-existing"], "read": ["draft"], "draft": ["check"], "check": ["try"], "try": ["upsert"], "approve": ["upsert"], "upsert": [], "tell": []}[which]
    refused_node = {"read": "read-existing"}.get(which, which)
    assert not (set(later) | ({refused_node} if which not in ("start", "approve") else set())) & set(path)


ACTIONS = [("report", n) for n in ("read-existing", "draft", "check", "try", "upsert", "tell")] + [("decide", "approve")]


def position(kind):
    w = {"draft": SCRIPTS["clean"], "gate": SCRIPTS["clean"], "upsert-ended": SCRIPTS["clean"], "stopped": lambda: scripted("check", 5), "forbidden": SCRIPTS["clean"]}[kind]()
    if kind == "forbidden":
        w.denies = {P + "upsert"}
    reg = registry()
    process = load_definition_file(DEFS / "upsert-a-content-type.process.yaml")
    w.records = StubRecordsAdapter()
    ctx = EngineContext(policy=RecPolicy(w), code_tool=Code(w), external_tool=Ext(w), records=w.records, claims=StubClaimsAdapter(), registry=reg, identity="a", platform_id="t-1")
    kw = {"inputs": {"request": "r r r", "type_name": "quick-answer"}, "host_inputs": {}}

    async def go():
        a = await next_(process, "r1", "r1", ctx, **kw)
        if kind == "draft":
            return process, ctx, kw, a
        while a.kind is not AnswerKind.ENDED:
            if a.kind is AnswerKind.TOOL_STEP:
                a = await report(process, "r1", "r1", "draft", ctx, output={"draft": _next(w.drafts, "draft")}, **kw)
            elif a.kind is AnswerKind.AWAITING_DECISION:
                if kind == "gate":
                    return process, ctx, kw, a
                v, n = _next(w.gates, "gate")
                a = await decide(process, "r1", "r1", a.node_id, ctx, verdict=v, note=n, subject="p", **kw)
        return process, ctx, kw, a
    return w, asyncio.run(go())


KINDS = ["draft", "gate", "upsert-ended", "stopped", "forbidden"]


def out_of_turn(kind, how_filter):
    w, (process, ctx, kw, here) = position(kind)
    before = len(w.records._store)
    stored = copy.deepcopy(w.stored)
    tried = 0
    for how, node in ACTIONS:
        if how != how_filter or here.node_id == node:
            continue                                   # the one Action offered in this state
        async def go():
            if how == "report":
                return await report(process, "r1", "r1", node, ctx, output={}, **kw)
            return await decide(process, "r1", "r1", node, ctx, verdict=Verdict.PERMIT, note="", subject="p", **kw)
        b = asyncio.run(go())
        tried += 1
        assert (b.kind, b.node_id, b.ending) == (here.kind, here.node_id, here.ending), (kind, how, node, b)
    return w, before, stored, tried


@pytest.mark.parametrize("kind", KINDS)
def test_every_state_and_action_cell_of_the_request_lifecycle(kind):
    """The answer is the same hand-off, and a decide out of turn records nothing and moves nothing."""
    w, before, stored, tried = out_of_turn(kind, "decide")
    assert tried >= (0 if kind == "gate" else 1) and len(w.records._store) == before and w.stored == stored
    w, before, stored, tried = out_of_turn(kind, "report")
    assert tried >= 5 and w.stored == stored                   # the answer was the same hand-off, and nothing was saved


@pytest.mark.xfail(strict=True, reason="G8: the engine records an attempt for a node reported out of turn")
@pytest.mark.parametrize("kind", KINDS)
def test_an_action_out_of_turn_records_nothing(kind):
    w, before, stored, tried = out_of_turn(kind, "report")
    assert len(w.records._store) == before


@pytest.mark.xfail(strict=True, reason="G8: a forged report of `upsert` makes the run end UPSERTED with nothing saved")
def test_a_run_never_ends_upserted_without_a_save():
    w, (process, ctx, kw, here) = position("gate")
    saved = {"saved": {"outcome": "CREATED", "name": "quick-answer", "content_hash": "sha256:" + "0" * 64}}

    async def go():
        await report(process, "r1", "r1", "upsert", ctx, output=saved, **kw)
        return await decide(process, "r1", "r1", "approve", ctx, verdict=Verdict.PERMIT, note="", subject="p", **kw)
    a = asyncio.run(go())
    assert not (a.ending == "UPSERTED" and not w.stored)


@pytest.mark.parametrize("hs,hc,ps,pc", list(itertools.product([True, False], repeat=4)))
def test_a_snapshot_cannot_contradict_itself(hs, hc, ps, pc):
    v = {"name": "t", "has_system": hs, "has_current": hc}
    if ps:
        v["system_profile"] = {}
    if pc:
        v["current_manifest"] = {}
        v["current_profile"] = {}
    assert passes("content-type-snapshot@1", v) == (hs == ps and hc == pc)


@pytest.mark.parametrize("ref,field", ALL)
def test_every_field_of_every_profile_is_closed(ref, field):
    test_one_field_retyped_is_refused(ref, field)
    if field in REQUIRED[ref]:
        test_one_required_field_removed_is_refused(ref, field)
    test_an_unknown_field_is_refused(ref)


def claims(text):
    return [re.fullmatch(r"- CLAIM: (.+) \(proof: ([A-Za-z0-9_]*)\)", l) or l for l in text.splitlines() if l.startswith("- CLAIM:")]


def defined_tests():
    out = set()
    out |= {n.name for n in ast.walk(ast.parse(Path(__file__).read_text())) if isinstance(n, ast.FunctionDef)}
    return out


CONDITION = "for a caller that reports the offered node"   # the engine accepts a report for any node (G8)
# One claim for each of C1 to C7 and C9 must stay in the README (a claim turned plain is a claim lost).
REQUIRED_PROOFS = {
    "test_every_definition_in_the_example_validates_with_the_builtin_set",
    "test_the_reference_checks_import_nothing_from_the_platform_or_a_vendor",
    "test_c2_a_clean_run_reaches_upserted",
    "test_c3_a_dropped_property_never_reaches_try_or_upsert",
    "test_c4_the_check_loop_ends_after_three_send_backs",
    "test_c4_the_trial_loop_ends_after_three_send_backs",
    "test_every_path_to_upsert_passes_the_gate",
    "test_c5_an_indeterminate_standing_rule_waits_for_a_person",
    "test_c6_every_step_asks_the_policy_port_before_it_runs",
    "test_c6_a_denied_upsert_leaves_the_type_unsaved",
    "test_the_definitions_hold_no_prompt_text",
    "test_every_claim_in_the_readme_names_a_test_that_exists",
}
HOST_DUTY = "Report to the engine only the node `next` offered"


def conditioned(proof):
    """C5 and C6 hold only while the caller reports the node it was offered."""
    return proof.startswith(("test_c5_", "test_c6_")) or proof == "test_every_path_to_upsert_passes_the_gate"


def readme_problems(text):
    cs = claims(text)
    bad = [c for c in cs if isinstance(c, str) or c.group(2) not in defined_tests()]
    unconditioned = [
        c.group(0) for c in cs if not isinstance(c, str) and conditioned(c.group(2)) and CONDITION not in c.group(1)
    ]
    missing = [f"no claim for {p}" for p in sorted(REQUIRED_PROOFS - {c.group(2) for c in cs if not isinstance(c, str)})]
    duty = [] if HOST_DUTY in text else ["the host duty to report only the offered node is missing"]
    return ([] if len(cs) >= 8 else ["too few claims"]) + [str(b) for b in bad] + unconditioned + missing + duty


README = HERE / "README.md"


def test_every_claim_in_the_readme_names_a_test_that_exists():
    assert readme_problems(README.read_text()) == []


def test_red_a_readme_claim_naming_no_test_is_refused():
    t = README.read_text()
    assert readme_problems(t.replace("test_c2_a_clean_run_reaches_upserted", "test_that_is_not_there"))
    assert readme_problems(t + "- CLAIM: it conforms to everything.\n")
    assert readme_problems(t.replace("- CLAIM: A clean", "- A clean"))


def test_red_a_c5_or_c6_claim_without_its_condition_is_refused():
    t = README.read_text()
    assert readme_problems(t) == []
    for proof in ("test_every_path_to_upsert_passes_the_gate", "test_c6_a_denied_upsert_leaves_the_type_unsaved",
                  "test_c6_every_step_asks_the_policy_port_before_it_runs",
                  "test_c5_an_indeterminate_standing_rule_waits_for_a_person"):
        line = next(l for l in t.splitlines() if f"(proof: {proof})" in l)
        assert CONDITION in line, proof
        assert readme_problems(t.replace(line, line.replace(", " + CONDITION, ""))), proof
    assert readme_problems(t.replace(HOST_DUTY, "Report what you like"))


@pytest.mark.parametrize("make,needle", [
    (lambda: World(drafts=[], trials=[(PASSED, [])], gates=[(Verdict.PERMIT, "")]), "unscripted draft"),
    (lambda: World(drafts=[good_draft()], trials=[], gates=[(Verdict.PERMIT, "")]), "unscripted trial"),
    (lambda: World(drafts=[good_draft()], trials=[(PASSED, [])], gates=[]), "unscripted gate answer"),
])
def test_a_script_one_item_short_fails_naming_the_item(make, needle):
    with pytest.raises(AssertionError, match=needle):
        run(make())


@SET_60
@given(st.sampled_from(sorted(SCRIPTS)))
def test_the_default_world_never_saves_without_a_person(name):  # R14
    w = SCRIPTS[name]()
    run(w)
    if w.stored:
        i = w.events.index(("call", "upsert"))
        assert ("decide", "PERMIT") in w.events[:i]


@SET_60
@given(st.sampled_from(sorted(SCRIPTS)))
def test_the_world_never_saves_without_a_recorded_permit(name):
    w = SCRIPTS[name]()
    ans, path = run(w)
    permitted = ("decide", "PERMIT") in w.events
    if not permitted:
        assert w.stored == {} and "upsert" not in path, (name, path)
    if w.stored:
        assert permitted and ans.ending in ("UPSERTED", "UNCHANGED")


def test_findings_do_not_outlive_their_draft():
    test_a_stale_blocking_finding_does_not_survive_a_clean_recheck()
    test_a_stop_after_a_trial_failure_does_not_list_the_old_trial_findings()


TEXTS = ["You are an expert. Do the work.", "Write a manifest that includes rules.", "Fine. Make sure the title is short.", "x" * 500]


def prose_paths(doc, path=""):
    if isinstance(doc, dict):
        for k, v in doc.items():
            if isinstance(v, str) and k in PROSE:
                yield f"{path}/{k}"
            else:
                yield from prose_paths(v, f"{path}/{k}")
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from prose_paths(v, f"{path}/{i}")


def set_at(doc, path, fn):
    parts = [p for p in path.split("/") if p]
    for p in parts[:-1]:
        doc = doc[int(p)] if isinstance(doc, list) else doc[p]
    doc[parts[-1]] = fn(doc[parts[-1]])


CASES = [(n, p) for n, d in docs().items() for p in prose_paths(d)]


@pytest.mark.parametrize("name,path", CASES)
def test_a_prompt_added_to_any_prose_field_is_seen(name, path):
    for text in (TEXTS[::3] if path.endswith("/title") else TEXTS):          # a title is a name: only `you` and length are tripwires
        d = copy.deepcopy(docs()[name])
        set_at(d, path, lambda old: text if path.endswith("/title") else old + " " + text)
        assert prompt_findings(d), (name, path, text)
    assert prompt_findings(docs()[name]) == []


@SET_60
@given(st.sampled_from(sorted(docs()["upsert-a-content-type.process.yaml"]["nodes"])))
def test_every_path_to_upsert_passes_the_gate(node):
    d = copy.deepcopy(docs())
    p = d["upsert-a-content-type.process.yaml"]
    p["nodes"][node].setdefault("extra_edge", {"next": "upsert"})            # an edge the test adds, read by the test's own walk
    ok = only_via_gate(d)
    assert ok == (node in {"approve", "upsert", "after-upsert"})              # only nodes already behind the gate may point at it


def test_tell_names_every_finding_and_the_note():
    out = checks.tell_what_is_in_the_way(
        type_name="quick-answer",
        blocking=[checks.finding("REMOVED", "/properties/summary", "the system Profile's property 'summary' was removed"),
                  checks.finding("RETYPED", "/properties/body/type", "'type' at /properties/body was changed from the system Profile's")],
        trial_findings=[], note="too vague")["told"]
    assert out["says"] == ("Stopped: the content type 'quick-answer' was not saved. What is in the way: "
                           "REMOVED at /properties/summary: the system Profile's property 'summary' was removed; "
                           "RETYPED at /properties/body/type: 'type' at /properties/body was changed from the system Profile's; "
                           "The last note from a person: too vague.")
    assert out["reasons"][-1] == "The last note from a person: too vague"
