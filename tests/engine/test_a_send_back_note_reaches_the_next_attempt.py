"""A decider's note reaches the step the gate sends work back to (§7.6 `note_into`).

Written against the real engine: a DENY that loops back is only useful if the
reason travels with it. Before this, `note_into` was accepted by the schema, the
model and the validator, and then never written — so a person sent work back
with an instruction the next attempt never saw.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from sulis_workflows.definition.load import load_definition
from sulis_workflows.definition.registry import Registry
from sulis_workflows.domain.ports.claims import StubClaimsAdapter
from sulis_workflows.domain.ports.external_tool import StubExternalToolAdapter
from sulis_workflows.domain.ports.policy import StubPolicyAdapter, Verdict
from sulis_workflows.domain.ports.records import StubRecordsAdapter
from sulis_workflows.engine.run import AnswerKind, EngineContext, decide, next_, report

BUILTIN = (
    Path(__file__).parents[1] / "src" / "sulis_workflows" / "definition" / "builtin"
)

PROFILE = """
api_version: sulis.workflows/v1
kind: PROFILE
id: line
version: 1.0.0
title: A line of text
grounded_in: this test's own convention; no external standard defines a line
schema: { type: string, minLength: 3 }
checker: profile-conformance@1
"""

TOOL = """
api_version: sulis.workflows/v1
kind: TOOL
id: draft
version: 1.0.0
title: Draft it
inputs:
  ask: { type: string }
  note: { type: string, required: false, default: "" }
output:
  text: { type: "profile:line@1" }
controls: [ { profile: line@1 } ]
mechanism: { kind: SKILL, ref: skills/draft }
effect: QUERY
permission: notes.note.write
"""

PROCESS = """
api_version: sulis.workflows/v1
kind: PROCESS
id: note-travels
version: 1.0.0
title: The note travels
permission: notes.process.start
inputs: { ask: { type: string } }
state:
  text: { type: "profile:line@1", reducer: REPLACE }
  note: { type: string, reducer: REPLACE, default: "" }
start: draft
endings:
  DONE: { outcome: SUCCESS, says: "Approved." }
  DROPPED: { outcome: STOPPED, says: "Not approved." }
nodes:
  draft:
    type: STEP
    tool: draft@1
    in: { ask: inputs.ask, note: state.note }
    out: { text: state.text }
    next: review
  review:
    type: GATE
    kind: APPROVAL
    asks: "Good enough?"
    criteria: It answers the ask.
    reviewing: [state.text]
    permission: notes.note.approve
    deciders: [ { person: { permission: notes.note.approve } } ]
    note_into: state.note
    on:
      PERMIT: { end: DONE }
      DENY: { next: draft, loop: { budget: 2, on_exhausted: { end: DROPPED } } }
"""


def _ctx() -> EngineContext:
    registry = Registry()
    for path in sorted(BUILTIN.glob("*.yaml")):
        registry.add(load_definition(path.read_text(), fmt="yaml"))
    registry.add(load_definition(PROFILE, fmt="yaml"))
    registry.add(load_definition(TOOL, fmt="yaml"))
    return EngineContext(
        policy=StubPolicyAdapter(),
        code_tool=None,
        external_tool=StubExternalToolAdapter(),
        records=StubRecordsAdapter(),
        claims=StubClaimsAdapter(),
        registry=registry,
        identity="usr_reviewer",
        platform_id="plat_1",
    )


def test_a_send_back_note_reaches_the_next_attempt() -> None:
    async def run() -> None:
        process = load_definition(PROCESS, fmt="yaml")
        ctx = _ctx()
        kw = {"inputs": {"ask": "write the release note"}, "host_inputs": {}}

        answer = await next_(process, "run-1", "run-1", ctx, **kw)
        answer = await report(
            process,
            "run-1",
            "run-1",
            answer.node_id,
            ctx,
            output={"text": "first draft"},
            **kw,
        )
        assert answer.kind is AnswerKind.AWAITING_DECISION

        answer = await decide(
            process,
            "run-1",
            "run-1",
            answer.node_id,
            ctx,
            verdict=Verdict.DENY,
            note="mention the annual plans",
            subject="usr_reviewer",
            **kw,
        )

        assert answer.kind is AnswerKind.TOOL_STEP
        assert answer.resolved_inputs["note"] == "mention the annual plans"

    asyncio.run(run())
