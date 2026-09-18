# Process definition format — v1

**Status:** draft · **Decision:** sulis-ai/platform ADR-227 (accepted) · **Governed by:** sulis-ai/platform ADR-028 (decision vocabulary, accepted), ADR-022 (engine adoption and its authorization blocker, accepted) · **Requirement:** [`docs/use-cases/CATALOGUE.md`](../use-cases/CATALOGUE.md) (65 needs), proven against [`docs/use-cases/corpus.md`](../use-cases/corpus.md) (50 processes, 415 scenarios)

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119.

## 0. In one page

A process is built from **four primitives**:

| Primitive | What it is |
|---|---|
| **Tool** | A typed contract for one unit of work: typed **inputs**, the **controls** its output is held to, a typed **output**, and the **mechanism** that does the work (code, a skill, an agent, another process, a composite of Tools, an external service). |
| **Step** | Binds one Tool into a process: maps run state onto the Tool's inputs and its output back into state. A step has no behaviour of its own. |
| **Gateway** | A flow node between steps: choose a route, go round a loop, split and join parallel work, repeat for each item, or reach a decision by a policy, an agent or a person. |
| **Process** | Typed inputs and state, the steps and gateways, and its named endings. A Process can be a Tool's mechanism, which is how one process calls another. |

Seven rules hold everything together:

1. **The engine only acts on data.** Routes, limits, preconditions and endings are expressions over typed state. Prose is for people and agents to read.
2. **Permission is checked before anything runs.** Starting a run, invoking any Tool and accepting any decision are authorized through the host first; a refusal stops the step (§10.1).
3. **Every Tool has controls, and they are checked.** After each step the output is checked by the deterministic checker registered for each control; the result is routed on.
4. **A decision answers one question: may this proceed?** `PERMIT`, `DENY` or `INDETERMINATE`, per ADR-028, whoever decides — a policy, an agent or a person. Where the run goes next is separate data.
5. **Every loop is bounded.** The default is in §15; a process or a loop may set its own.
6. **Every state is a sentence.** Every ending, gate and answer the engine gives carries a sentence a person can act on.
7. **Supported means as designed.** A process is supported only when each of its corpus scenarios visits exactly the expected steps, gates and ending.

---

## 1. Documents, identity and versions

1.1 A definition is a YAML (or JSON) document with a header:

```yaml
api_version: sulis.workflows/v1
kind: PROCESS                  # PROFILE | TOOL | CONTROL | PROCESS
id: grounded-inquiry           # kebab-case, unique per kind
version: 1.2.0                 # Semantic Versioning 2.0.0
title: Grounded inquiry        # for people
summary: >-                    # for people; one or two sentences
  ...
```

1.2 A reference to another definition is `id@version`. `version` is a full `major.minor.patch` (an exact pin: `interrogate@1.0.0` matches only that version) or a partial `major[.minor]`, with or without a leading `^` (`interrogate@1`, `interrogate@^1.2`) — a partial reference resolves like a caret range of that precision (§18, D10, D11): the highest registered version whose leading components match. `^` only changes anything in front of a full three-component version, where it turns an exact pin into a compatible range; in front of a partial version it is redundant, which is why every reference elsewhere in this spec is written the short way (`frame-question@1`, not `frame-question@^1`). Resolution happens **once, when a run starts**, and the run records the exact versions it pinned. A run MUST NOT change definition versions while in flight. *(UC-VERSION)*

1.3 A published version is immutable. A change is a new version.

1.4 Every object is closed: an unknown field is a validation error, not silently ignored.

1.5 **Casing is not restated here.** Field names are `snake_case` in definitions (they are stored documents); every closed value is `SCREAMING_SNAKE_CASE`, following the wire enum convention that sulis-ai/platform ADR-028 adopted from the Focaldata data conventions. Where those change, this format follows them.

1.6 Every closed value set names the standard it comes from, or says plainly that it is this format's own convention (§16).

---

## 2. Types and state

### 2.1 Types

| Type | Meaning |
|---|---|
| `string`, `integer`, `number`, `boolean` | JSON primitives |
| `enum[A, B, C]` | one of the listed values |
| `list<T>` | an ordered list of `T` |
| `map<T>` | string keys to `T` |
| `profile:<id>@<version>` | a value conforming to a Profile (§3) |
| `any` | untyped; allowed only for host-provided inputs, and MUST NOT be read by an expression |

### 2.2 Run state

| Path | Holds | Written by |
|---|---|---|
| `inputs.<name>` | The run's declared inputs | The caller, once, at start |
| `host.<name>` | Declared host-provided values | The host, at start *(UC-IN-AMBIENT)* |
| `state.<channel>` | Declared state channels | Step output mappings |
| `steps.<node>` | The latest attempt: `.output.<name>`, `.verdict`, `.controls.<control>.passed`, `.attempt`, `.decided_by` | The engine |

A path that does not exist evaluates to *absent* (§8).

### 2.3 State channels *(UC-STATE-CHANNELS)*

```yaml
state:
  findings:   { type: "list<profile:finding@1>", reducer: APPEND }
  insights:   { type: "list<profile:insight@1>", reducer: UPSERT_BY_ID, key: id }
  confidence: { type: "enum[GROUNDED, PARTIAL, INSUFFICIENT]", reducer: REPLACE }
  notes:      { type: "list<string>", reducer: APPEND, default: [] }
```

Reducers: `REPLACE` (last write wins), `MERGE` (maps, shallow), `APPEND` (lists), `UPSERT_BY_ID` (lists of objects, replaced by `key`). A write that does not match the channel type is refused and recorded as a failed attempt.

---

## 3. Profile

A **Profile** is a named, versioned JSON Schema (2020-12) for a value that flows between Tools. Profiles are the type system.

```yaml
api_version: sulis.workflows/v1
kind: PROFILE
id: finding
version: 1.0.0
title: Finding
grounded_in: W3C PROV-O prov:wasDerivedFrom — every finding names its source
schema:
  type: object
  required: [id, claim, source]
  properties:
    id: { type: string }
    claim: { type: string, minLength: 10 }
    source: { type: string }
  additionalProperties: false
checker: profile-conformance@1
```

Declaring an output of a profile type holds that output to the profile: a Profile is also a control (§5).

---

## 4. Tool

### 4.1 Shape

```yaml
api_version: sulis.workflows/v1
kind: TOOL
id: interrogate
version: 1.0.0
title: Attack the claims, keep what survives
inputs:                                    # I
  candidates: { type: "list<profile:finding@1>" }
  question:   { type: string }
output:                                    # O — one or more named outputs
  insights: { type: "list<profile:insight@1>" }
  verdict:  { type: "enum[SURVIVED, DROPPED, REVISED]" }
controls:                                  # C — at least one
  - profile: insight@1
  - conventions: faithful-generation@1
mechanism:                                 # M
  kind: AGENTIC
  ref: skills/interrogate
  allowed_tools: [ground-citations@1]
effect: QUERY
errors:
  - { code: SOURCE_UNREACHABLE, class: TRANSIENT }
  - { code: BRIEF_UNANSWERABLE, class: PERMANENT }
```

### 4.2 Inputs and outputs *(UC-TOOL-TYPED-IO, UC-OUT-MULTI)*

- `inputs.<name>`: `type`, `required` (default `true`), `default`, `description`.
- `output.<name>`: `type`, `description`. A Tool MAY have several named outputs.

### 4.3 Mechanism kinds *(UC-TOOL-KINDS, UC-MECHANISM)*

| `kind` | What does the work | Deterministic | `ref` names | Verified by |
|---|---|---|---|---|
| `CODE` | A function the host can call | yes | `module:function` | Exact output on examples |
| `SKILL` | A model following written instructions, one hand-off, no further steps | no | a skill document | Conformance to its controls |
| `AGENTIC` | An agent led step by step through an automated sequence, with bounded discretion (`allowed_tools`) at the points the sequence allows it — not free choice of route (D17) | no | a skill/agent definition (today: always a single step; a declared multi-step sequence is a deferred extension of this same kind, D17) | Conformance to its controls |
| `PROCESS` | Another, independently-versioned Process, run as a child (§9) | as the child | `process-id@version` | The child's corpus scenarios |
| `TOOL` | A composite: child Tools in order over shared values (`composes`) | as its children | — | Its children |
| `EXTERNAL` | A service outside Sulis, through a host adapter | per adapter | an adapter id | The adapter's contract tests |

`composes` lists `{ tool, inputs, output }` per child. `allowed_tools` belongs to the mechanism; the policy allowing the Tool to hold that set is a control.

`AGENTIC` and `PROCESS` both surface their inner hand-offs through the top-level run at a nested `scope` (§9.3's "every answer names the scope and definition it belongs to, at any depth" already covers both, not only a called Process) — a step whose mechanism is `AGENTIC` is not opaque to the caller the way a `CODE` dispatch is. What distinguishes them is not who drives the steps (the same top-level caller drives both) but what is being run: `PROCESS` calls a separately authored, separately versioned artifact with its own identity, endings and corpus scenarios; `AGENTIC` leads the agent through a sequence that belongs only to this one Tool, with no identity of its own and no `result.outputs`/`result.endings` translation to perform, since it is not a governed Process and simply produces this Tool's own declared `output` directly.

These kinds follow fd-product-architecture ADR-0074's mechanism vocabulary (read on its published step-contract page); they are that register's own convention, not an external standard.

### 4.4 Controls *(UC-TOOL-CONTROLS, UC-OUT-TYPED, UC-FIDELITY)*

- A Tool MUST declare at least one control.
- A control is `profile: <id@v>`, or a reference to a CONTROL document (§5): `conventions:`, `fitness:` or `policy:`.
- Every control MUST resolve at validation **and** at run start; one that does not **refuses to run**.
- Every non-policy control MUST have a registered checker (§5.2).
- A `SKILL` or `AGENTIC` Tool MUST have at least one non-policy control: its output varies, so without a checkable bar it cannot be evaluated.

### 4.5 Effect *(UC-TOOL-EFFECT, UC-SIDE-EFFECT-CLAIM)*

`QUERY` reads only; `MUTATION` changes Sulis-held state; `SIDE_EFFECT` changes something outside Sulis. A `MUTATION` or `SIDE_EFFECT` step is claimed before it runs (§12.3).

### 4.6 Errors *(UC-RETRY, UC-FAILURE-MODES)*

`errors[]` lists expected codes as `TRANSIENT` or `PERMANENT`. An unlisted error is `PERMANENT`.

---

## 5. Control

### 5.1 Shape

```yaml
api_version: sulis.workflows/v1
kind: CONTROL
id: faithful-generation
version: 1.0.0
type: CONVENTIONS              # CONVENTIONS | FITNESS | POLICY
title: Recommendations are entailed by the insights they cite
applies_to: output.insights
checker: check-entailment@1
grounded_in: Ji et al., "Survey of Hallucination in Natural Language Generation", arXiv:2202.03629 (intrinsic/extrinsic)
```

- `CONVENTIONS` — rules the content must follow.
- `FITNESS` — a measured threshold, with `severity: ERROR | WARNING` (a two-value subset of RFC 5424 §6.2.1 severities) and a `threshold`:
  ```yaml
  threshold: { metric: coverage_ratio, op: GTE, value: 0.8 }
  ```
  `metric` names what the checker measures — the checker Tool registered for this control (§5.2) interprets it, the same way it interprets `applies_to`. `op` is one of `GTE | GT | LTE | LT | EQ`. This shape is this format's own convention (§16, D8) — no external standard defines a generic fitness-threshold shape to adopt instead.
- `POLICY` — who or what may do or permit something; evaluated by the host's `PolicyPort` (§10.1), not by a checker.

### 5.2 Checkers

A checker is a `CODE` Tool that declares what it checks and returns `profile:control-result@1` — `{ control, passed, findings: [ { path, message, severity } ] }`:

```yaml
kind: TOOL
id: profile-conformance
mechanism: { kind: CODE, ref: sulis_workflows.checkers:profile_conformance }
checker_for: { control: PROFILE }
inputs:  { value: { type: any }, control: { type: string } }
output:  { result: { type: "profile:control-result@1" } }
controls: [ { profile: control-result@1 } ]
examples:
  - { name: conforming finding passes, inputs: { ... }, expect: { result: { passed: true } } }
  - { name: finding without a source fails, inputs: { ... }, expect: { result: { passed: false } } }
```

- A checker MUST ship at least one example that **passes** and at least one that **fails**. A checker that has only ever been shown passing values would also pass a checker that returns `passed: true` unconditionally.
- Checkers are built before the Tools they grade: a checker is the evaluation of every non-deterministic Tool that names its control.

---

## 6. Process

```yaml
api_version: sulis.workflows/v1
kind: PROCESS
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: "profile:brief@1" }
host_inputs:
  topology_index: { type: any }
state: { ... }
defaults: { loop_budget: 10 }            # any setting in §15 may be overridden here
start: frame
nodes: { ... }
endings:
  COMPLETE:     { outcome: SUCCESS, says: "Done: recommendations are signed off." }
  INSUFFICIENT: { outcome: SUCCESS, says: "Stopped honestly: the evidence does not support an answer." }
  DROPPED:      { outcome: SUCCESS, says: "Nothing survived review, so there is nothing to recommend." }
  DENIED:       { outcome: STOPPED, says: "Stopped: the recommendations were not approved." }
triggers: [ ... ]
skip_policy: STRICT                      # STRICT | ADVISORY
```

- **Endings** *(UC-STOP-NAMED, UC-STOP-HONEST)*: every ending is named, has an `outcome` (`SUCCESS`, `STOPPED` — ended on purpose, a person may need to act — or `FAILURE`), and a `says` sentence. An honest `INSUFFICIENT` is a `SUCCESS`.
- The engine adds four endings every process has, each with its own sentence: `ESCALATED` (a limit ran out with no route), `FAILED` (a permanent error with no route), `FORBIDDEN` (a permission was refused, §10.1), `CANCELLED` (a person stopped the run).
- **Skip policy** *(UC-EXEC-POLICY, UC-CRITICALITY)*: `STRICT` — only declared routes run. `ADVISORY` — a person with permission MAY skip a step whose `criticality` is `TRIVIAL`, recording a reason. `STANDARD` and `CRITICAL` steps are never skipped. The default is in §15. A `STEP` MAY declare `skip_permission: <host permission string>` (ADR-024's grammar, same shape as D12-D14); absent means the engine refuses every skip of that step, `ADVISORY` or not (D15) — skip authority is per-step, distinct from the Tool's own dispatch `permission` (§10.1). This field is named `skip_policy`, not `execution_policy` (D16): every run is driven step by step by whatever agent calls `next()`/`report()` (§12.1) regardless of this setting, so "guided" describes that whole engine, not this one field — `skip_policy` only ever governs whether a `TRIVIAL` step may be skipped.

---

## 7. Nodes

Every node has an `id` (its key in `nodes`) and a `type`: `STEP`, `ROUTE`, `PARALLEL`, `JOIN`, `FOR_EACH`, `GATE`. A node leaves by `next: <node-id>` or `end: <ENDING>`.

### 7.1 Step

```yaml
nodes:
  interrogate:
    type: STEP
    tool: interrogate@1
    in:
      candidates: state.findings
      question: [state.framed_question, inputs.brief.question]
    out:
      insights: state.insights
      verdict: state.interrogation_verdict
    precondition: len(state.findings) > 0
    criticality: CRITICAL
    on_control_fail: { repair: 1, then: { end: FAILED } }
    on_error: { BRIEF_UNANSWERABLE: { end: INSUFFICIENT } }
    next: after-interrogate
```

- `in` *(UC-IN-OPTIONAL, UC-IN-FALLBACK)*: every required Tool input MUST be mapped, to a path or an ordered list of paths (the first present, non-empty value is used). Each path is type-checked against the input.
- `out`: maps Tool outputs to channels. Unmapped outputs are still recorded under `steps.<id>.output`.
- `precondition` *(UC-PRECONDITION)*: when false, the step does not run and the run takes `on_precondition_false`. A step marked `destructive: true` MUST have a precondition.
- `retry` applies to `TRANSIENT` errors only, and MAY override the format default (§15):
  ```yaml
  retry: { max: 5, backoff_seconds: 4 }
  ```
  `max` is the greatest number of additional attempts; `backoff_seconds` is the starting delay before exponential backoff. `defaults.retry` (§6) takes the same shape. This format's own convention (§16, D9) — no external retry-policy standard is adopted, since the established ones (e.g. AWS SDK retry configuration, gRPC service config) are transport/SDK-specific, not a document-format concern. `on_error` routes by error code. `on_control_fail` is in §10.2. `on_forbidden` is in §10.1. Defaults for all of these are in §15.
- A step MUST NOT carry instructions; they belong to the Tool's mechanism.

### 7.2 Route *(UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-VERDICT-ROUTE, UC-PATHS)*

```yaml
  after-interrogate:
    type: ROUTE
    when:
      - if: state.interrogation_verdict == "SURVIVED"
        next: converge
      - if: state.interrogation_verdict == "REVISED"
        next: gather
        loop: { budget: 2, on_exhausted: { next: converge } }
        invalidates: [synthesise]
      - if: state.interrogation_verdict == "DROPPED"
        end: DROPPED
```

- Options are evaluated in order; the first true one is taken.
- A route MUST have `otherwise`, unless every option tests one enum-typed path for equality and together they cover every value — as above, which the validator proves.
- A judgement ("is there a context gap?") is a step whose Tool returns a typed verdict, followed by a route on it. There is no separate decide node.

### 7.3 Loops *(UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-TERMINATES-WHEN, UC-COMPENSATE)*

A **loop** is any route, gate route or `on_control_fail` route whose target can reach the node it leaves from. The validator detects every loop.

- Every loop is bounded: `loop.budget`, else the process's `defaults.loop_budget`, else the format default (§15). The budget is the most times the loop may be taken in one run scope.
- Each loop has its own counter (default name `<from>-><to>`), rebuilt from durable records so it survives a crash.
- `on_exhausted` is a route; its default is in §15.
- `counts`: `PASSES` (every time taken) or `FAILURES` (only when taken because a check failed). Default in §15.
- `invalidates`: nodes whose recorded outputs stop counting when the loop is taken, so later steps cannot read superseded work.

### 7.4 Parallel and join *(UC-PARALLEL, UC-JOIN)*

```yaml
  lenses:    { type: PARALLEL, branches: [market-lens, customer-lens, coherence-lens], join: lens-join }
  lens-join: { type: JOIN, policy: ALL_SUCCESS, next: lead-lens }   # ALL_SUCCESS | ANY_SUCCESS | ALL_COMPLETE
```

Every branch start is handed out. The join runs **exactly once**, when its policy is met or can no longer be (then `on_join_failed`). Two branches writing one `REPLACE` channel is refused.

### 7.5 For each *(UC-FOREACH)*

```yaml
  per-sub-brief:
    type: FOR_EACH
    over: state.sub_briefs
    as: sub_brief
    do: run-sub-inquiry
    max_concurrency: 4
    collect: { output: insights, into: state.insights }
    join: ALL_COMPLETE
    next: synthesise
```

`over` MUST be list-typed. Each item runs in an isolated scope; `collect` writes through the channel's reducer.

### 7.6 Gate — reaching a decision

A gate is where something must be decided before the run continues. **ADR-028 governs the decision vocabulary; this section applies it and does not restate its reasoning.**

```yaml
  sign-off:
    type: GATE
    kind: APPROVAL                         # APPROVAL | INPUT; absent means APPROVAL; anything else is refused
    asks: "Can these recommendations go ahead as work?"
    criteria: Every recommendation rests on a surviving insight and serves the brief's outcome.
    reviewing: [state.recommendations, state.confidence]
    deciders:
      - policy: grounded-inquiry-sign-off@1
      - agent: review-recommendations@1
      - person: { permission: agents.recommendation.approve }
    person_required_when: state.confidence == "INSUFFICIENT"
    note_into: state.notes
    on:
      PERMIT: { next: decompose-to-work }
      DENY:   { next: recommend, loop: { budget: 3 } }
```

**Verdicts** *(UC-GATE-VOCAB, UC-GATE-ROUTE)*:

| Verdict | Means | Routes |
|---|---|---|
| `PERMIT` | May proceed | MUST have a route: `next` to continue, or `next` + a different step to resubmit |
| `DENY` | May not proceed as it stands | MUST have a route: `next` to an earlier node (**send back** — a loop, §7.3), `end: <ENDING>` (**halt**), or `call: <process>@v` then `end` (**hand off**, UC-GATE-HANDOFF) |
| `INDETERMINATE` | Not this decider's call | MUST NOT have a route. It passes the decision to the next decider; after the last, the gate stays open for a person with the gate's permission (**pause**, UC-REFUSAL-MODE) |

**Deciders** *(UC-APPROVAL-AUTO, UC-GATE-KINDS)* are asked in order; the first `PERMIT` or `DENY` decides:

| Decider | Decides by | Declared as |
|---|---|---|
| `policy` | The host's `PolicyPort` evaluates the policy (trust earned, thresholds, grants) | `policy: <control-id@v>` |
| `agent` | A `SKILL` or `AGENTIC` Tool that receives `criteria` and the `reviewing` values and returns `profile:decision@1` — `{ verdict, rationale, evidence: [ { path, claim } ] }` | `agent: <tool-id@v>` |
| `person` | A person holding the named permission or role, through the host's decision surface | `person: { permission: <host permission> }` or `{ role: <host role> }` |

- A gate MAY declare `permission: <host permission string>` (ADR-024's grammar, same shape as a Tool's, §10.1, D12). If `deciders` is absent, the gate is decided by a person holding the gate's permission; that permission is this field. It is also who may decide the gate once every declared decider has answered `INDETERMINATE` (the **pause** state above) when the last decider is not itself a `person` (D13).
- A decider that cannot run, or gives a verdict outside its `may` list (the three ADR-028 verdicts themselves — no decider kind may answer with a fourth value), counts as `INDETERMINATE` rather than erroring (D13).
- `person_required_when`: while true, deciders before the first `person` are still asked and recorded, but only a person's verdict counts.
- **An agent decision is checked before it counts.** `decision@1`'s checker requires every `evidence[].path` to be one of the gate's `reviewing` paths and to resolve to a value in the run; a decision whose evidence cites nothing reviewed, or fails its controls, counts as `INDETERMINATE`. An agent that returns `PERMIT` with no grounded evidence cannot pass.
- **No deciding on your own work** (ANSI INCITS 359-2004, static separation of duty — *known, not re-read*): an agent decider MUST NOT be the Tool or agent session that produced a value in `reviewing`; the engine treats its verdict as `INDETERMINATE`.
- `kind: INPUT`: the decider gives an answer of `answer_type`, written through `answer_into`; `on` has `ANSWERED` and the decision passes on `INDETERMINATE` as above.
- **Provenance** *(UC-GATE-AUDIT)*: from every decider asked, the engine records the verdict, `decided_by` (`POLICY:<id>`, `AGENT:<tool>@<v>` and its session, or `PERSON:<subject>`), the rationale or note, the evidence, the time, and which asking of the gate it was.
- Permission strings are the host's (for the platform, ADR-024's `<service>.<resource>.<verb>` grammar); the format carries them opaquely and the host validates them at publish.

---

## 8. Expressions

Expressions appear in `if`, `precondition`, `person_required_when` and fitness thresholds. They are pure.

```
expr     := or
or       := and ( "or" and )*
and      := not ( "and" not )*
not      := "not" not | cmp
cmp      := value ( ( "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" ) value )?
value    := path | literal | "exists(" path ")" | "len(" path ")" | "(" expr ")"
path     := ident ( "." ident | "[" integer "]" )*
literal  := string | number | "true" | "false" | "null" | "[" literal ( "," literal )* "]"
```

- Every path is type-checked; **an expression that cannot be evaluated is refused.**
- `exists(p)` is true when `p` is present and not null. Comparing an absent value is false, never an error.
- Comparing an enum path with a value outside the enum is refused.

This grammar is this format's own convention; no external expression standard was adopted, because the candidates carry function calls and I/O this format forbids.

---

## 9. Calling a process *(UC-CALL, UC-CALL-RESULT, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES)*

### 9.1 As a Tool

```yaml
kind: TOOL
id: run-grounded-inquiry
inputs: { brief: { type: "profile:brief@1" } }
output:
  recommendations: { type: "list<profile:recommendation@1>" }
  ending: { type: "enum[COMPLETE, INSUFFICIENT, DROPPED, DENIED, ESCALATED, FAILED, FORBIDDEN, CANCELLED]" }
controls: [ { profile: recommendation@1 } ]
mechanism:
  kind: PROCESS
  ref: grounded-inquiry@1
  inputs: { brief: brief }
  result:
    outputs: { recommendations: state.recommendations }
    endings:
      COMPLETE: COMPLETE
      INSUFFICIENT: INSUFFICIENT
      DROPPED: DROPPED
      DENIED: DENIED
      ESCALATED: ESCALATED
      FAILED: FAILED
      FORBIDDEN: FORBIDDEN
      CANCELLED: CANCELLED
effect: QUERY
```

- `result.endings` MUST map every ending the child can reach, including the engine's four. The calling step MUST route every value of `ending`. Either gap is refused — the defence against parents and children disagreeing about result names.
- `path` MAY name the option the child's first route must take; otherwise the child decides.

### 9.2 Depth

Depth counts calls on the current chain. At the depth limit (§15) no further call is made and the step takes `on_depth_exhausted`. A process that can reach itself MUST declare `on_depth_exhausted`.

### 9.3 Nesting and gates

Every answer names the scope and definition it belongs to, at any depth. A gate in a child is surfaced through the top-level run and decided by the child's own deciders; a parent never decides a child's gate implicitly.

---

## 10. At run time: permission, then controls

### 10.1 Permission first

Before the engine starts a run, dispatches any Tool, or accepts any decision, it asks the host's `PolicyPort` whether the acting identity (the person, the agent session, or the service acting for the run) holds the required permission. The run carries that identity; the engine never runs a step without one.

- A Process MAY declare `permission: <host permission string>` (ADR-024's grammar, same shape as D12/D13), checked once before the engine starts a run of it. Absent means the engine refuses to start the run, not that starting is unchecked (D14).
- A Tool MAY declare `permission: <host permission string>` (ADR-024's grammar, carried opaquely, same shape as a gate decider's `person.permission`, §7.6). When present, the engine checks it via `PolicyPort` before every dispatch of that Tool. A Tool with no `permission` declared refuses to dispatch — the same fail-closed treatment §4.4 already gives an unresolved control, not a silent skip (D12).
- A refusal records the attempt as `FORBIDDEN` and takes `on_forbidden` (default in §15). It is never retried.
- This is the seam sulis-ai/platform ADR-022 found missing: the platform's in-app engine enforces an action's declared permission before dispatch and the published engine does not, so adopting it without this port would remove a privilege check. The port is part of the engine contract, not an option.

### 10.2 Controls after every step *(UC-TOOL-CONTROLS, UC-OUT-TYPED, UC-OUT-REPAIR)*

1. The Tool returns its output, or an error (§7.1).
2. Each output is checked against its type.
3. Each non-policy control's checker runs and returns a `control-result`.
4. All passed: the output is recorded, mapped into state, and the step leaves by `next`.
5. Any failed: the output is recorded **with its failed results** and is **not** mapped into state; the step takes `on_control_fail` — up to `repair` further invocations with the failures as input, then `then` (defaults in §15). A `then` that goes back is a loop.

---

## 11. Triggers *(UC-TRIGGER)*

```yaml
triggers:
  - { kind: TIMER, rrule: "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9" }
  - { kind: EVENT, event: instruction.confirmed, inputs: { brief: event.instruction } }
  - { kind: STATE_ENTRY, process: land-change@1, ending: COMPLETE }
  - { kind: WEBHOOK, adapter: github, event: pull_request.opened }
  - { kind: BRANCH_PUSH, repository: host.repository, branch: main }
```

The library validates triggers; the host fires them through its `TriggerPort` and must hold permission to start the run (§10.1). Timer rules use iCalendar RRULE (RFC 5545 §3.3.10).

---

## 12. Engine semantics

### 12.1 Driving a run *(UC-RESUME)*

- `next(run, scope)` answers with one of: `TOOL_STEP` (a non-deterministic step for the caller's agent session: resolved inputs, instructions ref, controls), `DECISION_STEP` (a gate whose current decider is an agent; reported like a tool step), `AWAITING_DECISION` (a gate whose current decider is a person), `STEP_RUNNING` (claimed by another caller), or `ENDED`. Every answer carries a `says` sentence. `CODE`, `EXTERNAL` and deterministic `PROCESS` steps and policy deciders are run by the engine before it answers.
- `report(run, scope, node, output | error)` records the attempt, checks controls, and answers with `next`.
- `decide(run, scope, gate, verdict, note)` records a person's decision (identity from the caller) and answers with `next`.

Starting and resuming are the same call. Nothing is held in memory between calls.

### 12.2 Records

Every attempt of every node is one write-once record keyed by `(run, scope, node, attempt)`: inputs used, output, control results, verdict or error, who or what performed it (W3C PROV-O `prov:wasAssociatedWith`, *known, not re-read*), and start and end times. The engine numbers attempts. Loop counters, retry counts and progress are derived from records.

### 12.3 Claims *(UC-SIDE-EFFECT-CLAIM, UC-LEASE)*

Before a `MUTATION` or `SIDE_EFFECT` step runs, the engine writes an in-progress claim with a lease, under the same write-once guard. A running step renews its lease. A second caller is told `STEP_RUNNING`. An expired claim MAY be taken over, and the takeover is logged as "may already have run". Lease length is a host setting.

### 12.4 Failures *(UC-RETRY, UC-FAILURE-MODES)*

`TRANSIENT` errors retry within `retry`; `PERMANENT` errors take `on_error`, else end `FAILED`. A failure that needs a person is a gate, not a note.

### 12.5 Observers

Observers are notified only after the record is durable; an observer failure MUST NOT fail the run.

---

## 13. Templates

Each template expands into the four primitives before validation; `sulis-workflows expand` shows the result. They add no semantics of their own.

| Template | Expands to | Catalogue |
|---|---|---|
| `revise_loop` | step → gate whose `DENY` sends back to the step | UC-GATE-SENDBACK |
| `control_repair` | step with `on_control_fail` repair and a route | UC-OUT-REPAIR |
| `verification_spiral` | verify step (FITNESS controls per dimension) → route: pass, loop back, or irreducible blocker → `end` | UC-SPIRAL |
| `lens_triad` | PARALLEL lens steps → JOIN `ALL_COMPLETE` → lead-lens step → route on the composite verdict | UC-LENS-TRIAD |
| `sequence_with_gates` | process-call steps in order, a gate after each marked `gate_after`, tail calls after the final gate, optional calls behind a flag route | UC-SEQUENCE, UC-OPTIONAL-BRANCH |
| `honest_stop` | route on a confidence verdict to `end: INSUFFICIENT` | UC-STOP-HONEST |
| `handoff_contract` | route after a step checking required outputs exist: `BLOCK` → `end`, `WARN` → record and continue, `SKIP` → continue | UC-HANDOFF |

---

## 14. Validation

A definition is valid only when every rule holds. Each rule has a conformance case that includes a definition that must be **refused**.

| Rule | Refuses |
|---|---|
| V1 schema | unknown fields; wrong types; values not in `SCREAMING_SNAKE_CASE` |
| V2 references | any `id@version` that does not resolve |
| V3 controls | a Tool with no control; a non-policy control with no checker; a `SKILL`/`AGENTIC` Tool with only policy controls; a checker without both a passing and a failing example |
| V4 mappings | an unmapped required input; a type mismatch in `in`, `out` or `collect` |
| V5 expressions | an unparseable expression; an untyped path; an enum compared with a value outside it |
| V6 routes | a route without `otherwise` that is not proven exhaustive |
| V7 reachability | an unreachable node; a node with no way to end |
| V8 loops | a budget that is not a positive integer |
| V9 gates | a `PERMIT` or `DENY` with no route; an `INDETERMINATE` with a route; an unknown `kind`; an agent decider not returning `decision@1`; an agent decider that could review its own output; `person_required_when` with no `person` decider; a gate with no `asks` |
| V10 calls | a child ending not mapped; a call ending not routed; a self-reachable call without `on_depth_exhausted` |
| V11 parallel | two branches writing one `REPLACE` channel; a join not reachable from every branch |
| V12 for-each | `over` not list-typed |
| V13 side effects | a `destructive` step with no precondition |
| V14 endings | an `end` naming an undeclared ending; an ending with no `says` |
| V15 grounding | a closed value set with no `grounded_in` |

---

## 15. Defaults

**This table is the only place defaults are stated.** Every other section refers here.

| Setting | Default | Override |
|---|---|---|
| Loop budget (passes per loop, per scope) — applies to every loop, including send-backs at gates | **10** | `defaults.loop_budget`; `loop.budget` |
| Loop counts | `PASSES` | `loop.counts` |
| When a loop runs out | `end: ESCALATED` | `loop.on_exhausted` |
| Repairs after a failed control | 1 | `defaults.repair_budget`; `on_control_fail.repair` |
| After repairs run out | `end: FAILED` | `on_control_fail.then` |
| Retries for `TRANSIENT` errors | 3, exponential backoff from 2 s | `defaults.retry`; `step.retry` (shape: §7.1) |
| Unrouted `PERMANENT` error | `end: FAILED` | `step.on_error` |
| Permission refused | `end: FORBIDDEN` | `step.on_forbidden` |
| Call depth | 4 | `defaults.max_depth` |
| Depth reached | `end: ESCALATED` | `on_depth_exhausted` (required for self-reachable calls) |
| Precondition false | `end: ESCALATED` | `on_precondition_false` |
| Join policy | `ALL_SUCCESS` | `join.policy` |
| Join cannot be met | `end: FAILED` | `on_join_failed` |
| For-each concurrency | 1 | `max_concurrency` |
| Step criticality | `STANDARD` | `criticality` |
| Skip policy | `STRICT` | `skip_policy` |
| Gate kind | `APPROVAL` (ADR-028) | `kind` |
| Gate deciders | a person holding the gate's permission | `deciders` |

**No default** exists for a route's `otherwise`, a gate's `PERMIT`/`DENY` routes, a call's ending mapping, an ending's `says` or a gate's `asks` — those are an author's decisions.

---

## 16. What this format rests on

Tags: **VERIFIED** — read in this work; **KNOWN** — precisely nameable, not re-read in this work; **OWN** — this format's convention, no external standard applies.

| Part | Source | Tag |
|---|---|---|
| Decision vocabulary and its semantics | sulis-ai/platform ADR-028 (accepted), which adopts OASIS XACML 3.0 decisions via fd-product-architecture `schemas/process.schema.json` `$defs/approval_gate` | VERIFIED (ADR-028); XACML itself KNOWN — ADR-028 records it was not read |
| Enum and field casing | sulis-ai/platform ADR-028; Focaldata `conventions/data.conventions.yaml` (enums, casing) | VERIFIED |
| Permission seam in the engine | sulis-ai/platform ADR-022 (accepted), "Why the swap is deferred" | VERIFIED |
| Permission strings | sulis-ai/platform ADR-024 (proposed) — host grammar, carried opaquely | VERIFIED (status: proposed) |
| Tool as inputs, controls, output, mechanism | IDEF0, FIPS PUB 183; fd-product-architecture ADR-0074 step contract (its published page) | FIPS 183 KNOWN; ADR-0074 page VERIFIED |
| Mechanism kinds | fd-product-architecture's own vocabulary, adopted | VERIFIED (page); OWN (no external standard) |
| Gateways, parallel, join | BPMN 2.0 (ISO/IEC 19510:2013) | KNOWN |
| Separation of duty for deciders | ANSI INCITS 359-2004 (RBAC), static separation of duty | KNOWN |
| Records, who did what | W3C PROV-O | KNOWN |
| Profiles | JSON Schema 2020-12 | KNOWN |
| Versions | Semantic Versioning 2.0.0 | KNOWN |
| Fitness severity | RFC 5424 §6.2.1 (two-value subset) | KNOWN |
| Timer triggers | RFC 5545 §3.3.10 RRULE | KNOWN |
| Normative keywords | RFC 2119 | KNOWN |
| Expression grammar, endings, templates, validation rules, defaults | this format | OWN |
| FITNESS control threshold shape (`metric`/`op`/`value`) | this format (D8) | OWN |
| `retry` override shape (`max`/`backoff_seconds`) | this format (D9) | OWN |
| Caret-range (`^`) reference semantics (§1.2) | node-semver (github.com/npm/node-semver), "Caret Ranges" (D10) | KNOWN — not part of Semantic Versioning 2.0.0 itself, which defines version precedence and format but no range syntax |
| Accessibility of any surface that shows these states | WCAG 2.2 SC 1.4.1 (use of colour) — the `says`/`asks` sentences exist so no surface has to rely on colour | KNOWN; applies to host UIs |

---

## 17. Catalogue coverage

| Catalogue id | Section |
|---|---|
| UC-IN-TYPED, UC-IN-AMBIENT | 2.2, 6 |
| UC-STATE-CHANNELS | 2.3 |
| UC-IN-OPTIONAL, UC-IN-FALLBACK | 7.1 |
| UC-OUT-MULTI, UC-TOOL-TYPED-IO | 4.2 |
| UC-OUT-TYPED, UC-TOOL-CONTROLS, UC-FIDELITY | 3, 4.4, 5, 10.2 |
| UC-OUT-REPAIR | 10.2, 13 |
| UC-OUT-MODE | a `SIDE_EFFECT` Tool (e.g. propose a change) selected by a route on an input |
| UC-HANDOFF | 13 |
| UC-SEED-ARTIFACTS | 6 (inputs typed as artifact profiles) |
| UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-DECIDE, UC-PATHS, UC-VERDICT-ROUTE | 7.2 |
| UC-PREPHASE | 7.1 (a step before the first route) |
| UC-STOP-NAMED, UC-STOP-HONEST | 6, 13 |
| UC-LOOP-BUDGET, UC-LOOP-MANY, UC-LOOP-WHILE, UC-TERMINATES-WHEN, UC-COMPENSATE | 7.3 |
| UC-OPTIONAL-BRANCH, UC-CYCLE-POLICY | 7.2 (route on a flag; route on `steps.<node>.attempt`) |
| UC-PARALLEL, UC-JOIN | 7.4 |
| UC-FOREACH | 7.5 |
| UC-CALL, UC-CALL-RESULT, UC-CALL-DEPTH, UC-CALL-PATH, UC-CALL-NESTING, UC-CALL-GATES | 9 |
| UC-SEQUENCE, UC-EXEC-POLICY, UC-CRITICALITY | 13, 6 |
| UC-GATE-KINDS, UC-GATE-VOCAB, UC-GATE-ROUTE, UC-GATE-SENDBACK, UC-GATE-HANDOFF, UC-REFUSAL-MODE, UC-APPROVAL-AUTO, UC-GATE-CRITERIA, UC-GATE-AUDIT | 7.6 |
| UC-RETRY, UC-FAILURE-MODES | 7.1, 12.4 |
| UC-PRECONDITION | 7.1 |
| UC-SIDE-EFFECT-CLAIM, UC-LEASE, UC-RESUME | 12 |
| UC-TOOL-RUNNER | V2 (a mechanism `ref` that does not resolve) |
| UC-TOOL-KINDS, UC-TOOL-EFFECT, UC-MECHANISM | 4.3, 4.5 |
| UC-CAPABILITY | the host's Tool registry resolving `id@version`; no capability matching in the format |
| UC-SPIRAL, UC-LENS-TRIAD | 13 |
| UC-TRIGGER | 11 |
| UC-VERSION | 1.2 |

---

## 18. Decisions taken in this draft

Recorded in MADR form (context, options, outcome, consequences) so each can be audited and reversed.

**D1 — One loop default of 10, everywhere.** *Context:* the principal set 10 as the default loop size. *Options:* 10 everywhere; 10 with lower defaults inside templates such as `revise_loop`. *Outcome:* 10 everywhere, including send-backs at gates. A second default in templates would state a convention twice and let the two drift. *Consequences:* a person or agent could be sent back up to 10 times unless the author sets less; authors of revise loops SHOULD set a budget. *Reversal:* change one value in §15 before any process is converted — minutes; after conversion, a re-validation of converted processes.

**D2 — `STRICT` by default; `ADVISORY` may skip only `TRIVIAL` steps.** *Context:* methodology sequences allow deviation; fail closed. *Options:* allow skipping `STANDARD` steps with a reason; allow only `TRIVIAL`. *Outcome:* only `TRIVIAL`, by a person with permission, with a recorded reason. Skipping `STANDARD` work with a reason is the bad-but-conformant path — a reason field is always fillable. *Reversal:* one rule; widening later is additive. (Renamed from `GUIDED` by D16.)

**D3 — Claim lease length is a host setting.** *Context:* how long a running step holds its claim depends on how the host runs sessions. *Outcome:* not in the format. *Reversal:* adding a field later is additive.

**D4 — `INDETERMINATE` passes the decision on and never routes.** *Context:* ADR-028 (accepted) defines it as "not my call" and refuses it with a step. *Outcome:* the format follows ADR-028; "pause on refusal" is expressed as `INDETERMINATE` reaching the last decider. *Reversal:* governed by ADR-028; change there first.

**D5 — Permission is checked by the engine before every start, dispatch and decision.** *Context:* ADR-022 found the published engine lacks the permission check the platform's engine performs. *Outcome:* a `PolicyPort` call is part of the engine contract. *Reversal:* removing it would reintroduce the privilege gap ADR-022 describes; not reversible safely.

**D6 — Every ending, gate and engine answer carries a sentence.** *Context:* states a person acts on must read as sentences, and never by colour alone (WCAG 2.2 SC 1.4.1). *Outcome:* `says` on endings and answers, `asks` on gates, refused when missing. *Reversal:* additive to relax; costly to add after processes are converted.

**D7 — Agent decisions and checkers must be able to fail.** *Context:* an agent that always permits, or a checker that always passes, would satisfy a naive check. *Outcome:* agent decisions must cite reviewed evidence that resolves; checkers must ship failing examples. *Reversal:* relaxing is a one-line rule change; not recommended.

**D8 — FITNESS threshold shape is `{ metric, op, value }`.** *Context:* §5.1 named FITNESS as "a measured threshold" without ever giving the field(s) that carry it — a gap found while building the v1 JSON Schemas (WP-01). *Options:* leave `threshold` untyped (accepts anything, refuses nothing — fails closed on nothing); a single numeric `threshold: 0.8` field with the comparison implied (ambiguous: GTE? GT?); `{ metric, op, value }` naming what is measured, how, and against what. *Outcome:* `{ metric, op, value }`, `op` a closed `GTE | GT | LTE | LT | EQ` set — consistent with how this format already names comparisons in kind (`ROUTE` expressions, §8) rather than leaving them implicit. *Consequences:* a checker Tool for a FITNESS control reads `control.threshold` the same way it reads `applies_to`; existing FITNESS controls authored before this decision (none yet exist in this repo's fixtures) are unaffected. *Reversal:* additive — a two-way door; changing the shape means updating `control.v1.schema.json` and any FITNESS control definitions, not a migration.

**D9 — `retry` override shape is `{ max, backoff_seconds }`.** *Context:* §15 named the retry default ("3, exponential backoff from 2 s") and its override points (`defaults.retry`, `step.retry`) without giving their field shape — the same class of gap as D8, found at the same time. *Options:* leave `retry` untyped; adopt an external retry-policy standard (rejected — AWS SDK and gRPC service-config retry shapes are transport/SDK-specific, not something a document format should couple to); `{ max, backoff_seconds }`, naming exactly the two numbers §15's own default already states. *Outcome:* `{ max, backoff_seconds }`; `step.retry` and `defaults.retry` (§6) share the shape, so the override and the default it overrides are stated the same way. *Consequences:* none yet — no process definition in this repository overrides retry today. *Reversal:* additive — a two-way door, same cost as D8.

**D10 — Caret-range references resolve by node-semver's caret semantics.** *Context:* §1.2 gives one example (`^1.2`) of a caret-range reference but never states the range semantics precisely — WP-01's registry (step 2) has to resolve one to an exact version, so the rule needs to be exact, not just illustrated. *Options:* invent a bespoke range rule; adopt node-semver's caret semantics (the convention the `^` syntax is drawn from — SemVer 2.0.0 itself defines only version precedence and format, no range syntax). *Outcome:* node-semver's caret rule verbatim, including its zero-major special cases (`^0.2.3`, `^0.0.3`), because the version numbers this format's own definitions carry (§1.1, `version: 1.2.0`) are themselves plain SemVer 2.0.0 and node-semver is the widely-used convention for ranges over exactly that version grammar — inventing a different rule over the same numbers would be a gratuitous divergence from the nearest fitting convention. *Consequences:* a definition versioned below `1.0.0` gets node-semver's narrower zero-major treatment, which authors coming from npm or Cargo will already expect. *Reversal:* changing the range algorithm is a two-way door local to `registry.py`; no reference in this repository's fixtures yet depends on the zero-major special cases.

**D11 — A bare (non-`^`) partial reference (`interrogate@1`) resolves exactly like a caret range of the same precision, not as an error and not as an implicit `.0.0` pin.** *Context:* every worked reference in this spec — Appendix A included — is written the short way (`frame-question@1`, `insight@1`, `grounded-inquiry-sign-off@1`), never `@1.0.0` and never `@^1`; §1.2 as first drafted only defined the caret form, which would have made every one of the spec's own examples an invalid reference (WP-01's registry work, building the first real resolver against these examples, is what surfaced this). *Options:* refuse any reference that isn't a full three-component version or an explicit `^`-prefixed one (rejected — invalidates every reference this spec itself has ever shown); treat a bare partial reference as shorthand for `major.minor.0` or `major.0.0` exactly (rejected — silently picks the *lowest* matching version even when a newer compatible one is registered, the opposite of what a reference author almost always wants, and inconsistent with how `^` is defined to behave at the same precision); treat it identically to a caret range of the same precision (adopted). *Outcome:* the `^` sigil only changes behaviour in front of a full three-component version (exact pin vs. compatible range); in front of a partial version it is redundant, so this spec's authors have always been free to omit it. *Consequences:* `interrogate@1` and `interrogate@^1` are now defined to mean exactly the same thing; a reference author who wants a true single-version pin must write all three components. *Reversal:* two-way door, local to `registry.py`'s `Registry.resolve` (the branch between "exact pin" and "range resolve" moves from "no `^`" to "fewer than three components"); every reference in this repository's fixtures is already written the short way, so no fixture needs to change if this is reversed to the opposite convention (require `^` and treat bare partial as pin-to-zero) — only the resolution result would.

**D12 — A Tool's dispatch permission is an optional, opaque `permission` field; absent means refuse to dispatch, not "no check needed."** *Context:* §10.1 requires the engine to check permission "before it ... dispatches any Tool" but, as first drafted, named no field carrying which permission a given Tool's dispatch requires — a gap found while building WP-02's engine (the `PolicyPort` call has to name *something* to check). *Options:* derive a permission string automatically from the Tool's own id (rejected — invents a naming scheme ADR-024 reserves to the host, and two hosts would derive two different strings from the same Tool); make `permission` a required field on every Tool now, enforced by the JSON Schema (rejected for this draft — would invalidate every Tool fixture already written against v1, a large, unrelated blast radius for a field this decision can add without it); an optional field that, when absent, means the dispatch proceeds unchecked (rejected — silently defeats §10.1's own "before it dispatches any Tool," the bad-but-conformant path this format's own principles ask every rule to defeat). *Outcome:* `permission` is optional in the schema (so no existing fixture needs to change), but the *engine* treats its absence as a refusal to dispatch, mirroring §4.4's existing rule that a Tool with an unresolved control refuses to run. *Consequences:* every Tool that should actually run needs `permission` declared; a future draft should tighten this to a schema-level requirement (a new validator rule, V-something) once real Tool fixtures exist to migrate. *Reversal:* two-way door — tightening `permission` to schema-required is additive once fixtures are updated; the engine-side refusal-on-absence rule is local to `engine/steps.py` and can be relaxed in one place.

**D13 — A gate's own `permission` is likewise an optional, opaque field (mirroring D12); a decider's "`may` list" is exactly the three ADR-028 verdicts.** *Context:* two related gaps found while building WP-02's GATE execution (step 4). First, §7.6 twice refers to "the gate's permission" (deciding a gate with no `deciders` declared; deciding a gate once every decider has answered `INDETERMINATE` and the last is not a `person`) without GATE ever declaring a `permission` field, the same shape of gap as D12's. Second, §7.6 says a decider "gives a verdict outside its `may` list" counts as `INDETERMINATE`, but no `may` field or list is defined anywhere for any decider kind. *Options, first gap:* the same three considered for D12, with the same reasoning; adopted the same outcome for consistency ("hold conventions once" — two gates of the same shape should not get two different answers). *Options, second gap:* invent a new per-decider `may:` field naming which verdicts that decider is allowed to give (rejected — no worked example in the spec ever shows such a field, and inventing new schema surface from a single, isolated phrase risks guessing wrong about what was meant); read `may list` as referring to the fixed, already-existing ADR-028 vocabulary itself — i.e. the phrase is reinforcing that a decider's raw answer must be one of `PERMIT`/`DENY`/`INDETERMINATE` and nothing else, not introducing a new declared field (adopted — the reading that adds no new schema surface and is consistent with `decision@1`'s own verdict already being drawn from that same enum). *Outcome:* GATE gains an optional `permission` field, engine-refused-when-absent exactly as D12; "outside its `may` list" means "not one of PERMIT/DENY/INDETERMINATE." *Consequences:* a gate with no `deciders` and no `permission` cannot be decided by anyone until `permission` is added — the same fail-closed shape D12 already accepted for Tools. *Reversal:* two-way door for both halves, local to `model.py`'s `GateNode` and `engine/gates.py`'s `may`-list check respectively.

**D14 — A Process's own `permission`, checked once before the engine starts a run, is the third and final field of this shape (D12, D13).** *Context:* §10.1 requires the engine to check permission "before it starts a run" but, like D12/D13's fields, named no place a Process declares which permission that is — found while building WP-02's `next()` (step 5), the first code that actually has to start a run rather than dispatch a step or a gate already inside one. *Options:* the same three considered for D12/D13. *Outcome:* the same answer, for the same reason: `permission` is optional on Process, and the engine refuses to start a run of a Process that has none, rather than starting it unchecked. *Consequences:* every real Process needs `permission` declared before any run can start, same as D12/D13's Tools and Gates. *Reversal:* two-way door, additive, local to `model.py`'s `Process` and `engine/run.py`'s start-of-run check.

**D15 — A `STEP`'s skip authority under `ADVISORY` skip policy is its own field, `skip_permission`, distinct from the Tool's dispatch `permission` (D12).** *Context:* §6 says `ADVISORY` (then named `GUIDED`) lets "a person with permission" skip a `TRIVIAL` step, but names no field carrying which permission — the same shape of gap as D12-D14, found while building the engine's own support for this policy (a capability the engine had validated and stored since WP-01 but never acted on at runtime until now). *Options:* reuse the Tool's own `permission` (D12) for skip authority too: rejected — dispatching a Tool and overriding the process's own declared flow are different privileges a host may reasonably grant to different roles (e.g. anyone who may run a step at all, versus only a supervisor who may skip one), and collapsing them removes a distinction a host may need; the same three options D12-D14 considered for a fresh field, with the same reasoning. *Outcome:* `STEP` gains an optional `skip_permission`; absent means the engine refuses every skip of that step (fail closed, same shape as D12-D14), whether or not the policy is `ADVISORY`. *Consequences:* a `TRIVIAL` step is only actually skippable once its author declares `skip_permission`; an `ADVISORY` process with no such declarations behaves identically to `STRICT` in practice, which is the safe default. *Reversal:* two-way door, additive, local to `model.py`'s `StepNode` and `engine/run.py`'s skip path.

**D16 — `execution_policy`/`GUIDED` renamed to `skip_policy`/`ADVISORY`.** *Context:* the principal's own working definition of "guided" is a different, unrelated concept already true of the whole engine — an agent calling `next()`/`report()` to get the current step and record its outcome, one step at a time, as opposed to a session (the deprecated `compiler/` path) that runs a process internally in one go. That property holds for every run under this v1 format regardless of `execution_policy`/D2's setting, so naming the skip-a-`TRIVIAL`-step setting `GUIDED` collided with a more fundamental, already-true meaning of the same word. *Options:* keep the field name and only rename the value (`GUIDED` → something else, field stays `execution_policy`): rejected — the field name itself is what invites the confusion, since "execution policy" reads as governing how the process is run in general, not narrowly whether a step may be skipped. Rename only in prose/docs, keep `execution_policy`/`GUIDED` in the machine format: rejected — the two channels would then disagree, and any process definition or fixture written against the docs would fail to validate. *Outcome:* field renamed to `skip_policy`; enum value renamed `GUIDED` → `ADVISORY` (paired with `STRICT`, both describing the same axis — how strictly the declared flow is followed); `STRICT` unchanged. *Consequences:* every prior reference to `execution_policy: GUIDED` across the spec, schema, model and engine is updated in the same change (D2, D15, §15's defaults table, `StepNode`/`Process` fields, `skip()`'s guard clauses); no process definitions exist yet outside this repository's own fixtures, so there is no external migration. *Reversal:* two-way door — a field/enum rename, no semantic change to what is or is not skippable.

**D17 — `AGENTIC` means an agent led step by step through an automated sequence, not free choice of route; distinguished from `PROCESS` by having no identity of its own, not by who drives it. PROPOSED — the table correction below is settled; the multi-step authoring grammar it points to is explicitly deferred, not decided, and nothing in this repository implements it yet.** *Context:* building the engine's `TOOL_STEP` hand-off (closing its own gap against §12.1, same session) raised the question of what `AGENTIC` actually hands an agent, which exposed that this table's prior wording — "free to choose its route within `allowed_tools`" — was never what the principal meant by the word: their own working model is an agent *led* through a declared, automated sequence, the same step-by-step hand-off discipline as the outer run, not given free rein. Checking that reading against the rest of the spec found it already fits: §9.3 ("every answer names the scope and definition it belongs to, at any depth... a gate in a child is surfaced through the top-level run") already generalizes past `PROCESS` calls to any nested scope, so an `AGENTIC` sub-sequence surfacing its own hand-offs to the same top-level caller needs no new mechanic invented, only correct wording. *Options:* leave `AGENTIC` meaning free route choice and introduce a new mechanism kind for a led sequence: rejected — a seventh kind duplicates most of what `AGENTIC` already is (non-deterministic, controls-checked, `allowed_tools`-capable) for one behavioural difference, and ADR-0074's own vocabulary (§4.3's grounding) is the register of kinds this format already commits to holding to, not extending on a single Tool's say-so. Merge `AGENTIC` into `PROCESS` entirely, since both now surface nested hand-offs the same way: rejected — collapses a real distinction (an independently versioned, independently governed artifact with its own corpus scenarios, vs. a sequence with no identity of its own belonging to exactly one Tool) that authors need, and would force every simple, single-step `AGENTIC` Tool already in this repository's own corpus (`grounded-recon`, `interrogate`, `recommend`, `review-recommendations`, Appendix A) to be rewritten as a separately versioned child Process for no behavioural gain. Design the full multi-step authoring grammar (an inline node graph in the mechanism block, or something else) in this same pass: rejected — no fixture or corpus scenario yet exercises a multi-step `AGENTIC` Tool, so inventing its concrete shape now would be exactly the speculative guess this format's own working practice (`docs/runs/`, this session repeatedly) refuses to make without something real to check it against; "adopt the cheap seam now, defer the expensive guess" (CLAUDE.md). *Outcome:* the table description of `AGENTIC` is corrected now (this is wording, not new schema — no fixture changes, no validator changes, nothing to migrate); every existing single-step `AGENTIC` Tool remains valid as the trivial case of a one-step "sequence." The concrete authoring grammar for a genuine multi-step sequence is left undecided, to be settled against a real corpus scenario that needs one. *Consequences:* until that follow-up is settled, `AGENTIC` and `SKILL` remain operationally identical in this engine (both hand off once, as `TOOL_STEP`, per the current WP-02 implementation) — the distinction drawn here is conceptual and forward-looking, not yet load-bearing in code. *Reversal:* two-way door — a corrected table description commits nothing that a later, differently-shaped authoring grammar would need to unwind.

---

## Appendix A — grounded inquiry, single path, in v1

Tools and Profiles are referenced, not shown.

```yaml
api_version: sulis.workflows/v1
kind: PROCESS
id: grounded-inquiry
version: 1.0.0
title: Grounded inquiry
inputs:
  brief: { type: "profile:brief@1" }
host_inputs:
  topology_index: { type: any }
state:
  framed_question: { type: string, reducer: REPLACE }
  path:            { type: "enum[SINGLE, RECURSIVE]", reducer: REPLACE }
  findings:        { type: "list<profile:finding@1>", reducer: APPEND }
  insights:        { type: "list<profile:insight@1>", reducer: UPSERT_BY_ID, key: id }
  verdict:         { type: "enum[SURVIVED, DROPPED, REVISED]", reducer: REPLACE }
  confidence:      { type: "enum[GROUNDED, PARTIAL, INSUFFICIENT]", reducer: REPLACE }
  conclusion:      { type: "profile:conclusion@1", reducer: REPLACE }
  recommendations: { type: "list<profile:recommendation@1>", reducer: REPLACE }
  fidelity:        { type: "enum[ENTAILED, DROPPED, REVISED]", reducer: REPLACE }
  notes:           { type: "list<string>", reducer: APPEND, default: [] }
start: frame
endings:
  COMPLETE:     { outcome: SUCCESS, says: "Done: the recommendations are signed off." }
  INSUFFICIENT: { outcome: SUCCESS, says: "Stopped honestly: the evidence does not support an answer." }
  DROPPED:      { outcome: SUCCESS, says: "Nothing survived review, so there is nothing to recommend." }
  DENIED:       { outcome: STOPPED, says: "Stopped: the recommendations were not approved." }
nodes:
  frame:
    { type: STEP, tool: frame-question@1, in: { brief: inputs.brief },
      out: { framed_question: state.framed_question }, next: classify }
  classify:
    { type: STEP, tool: classify-inquiry@1, in: { question: state.framed_question },
      out: { path: state.path }, next: choose-path }
  choose-path:
    type: ROUTE
    when:
      - { if: state.path == "SINGLE", next: gather }
      - { if: state.path == "RECURSIVE", next: decompose }    # recursive path not shown
  gather:
    { type: STEP, tool: grounded-recon@1,
      in: { question: [state.framed_question, inputs.brief.question], topology_index: host.topology_index },
      out: { findings: state.findings }, next: interrogate }
  interrogate:
    { type: STEP, tool: interrogate@1,
      in: { candidates: state.findings, question: state.framed_question },
      out: { insights: state.insights, verdict: state.verdict }, next: after-interrogate }
  after-interrogate:
    type: ROUTE
    when:
      - { if: state.verdict == "SURVIVED", next: converge }
      - { if: state.verdict == "REVISED", next: gather, loop: { budget: 2, on_exhausted: { next: converge } } }
      - { if: state.verdict == "DROPPED", end: DROPPED }
  converge:
    { type: STEP, tool: converge-confidence@1, in: { insights: state.insights },
      out: { confidence: state.confidence }, next: conclude }
  conclude:
    { type: STEP, tool: conclude@1, in: { insights: state.insights, confidence: state.confidence },
      out: { conclusion: state.conclusion }, next: honest-stop }
  honest-stop:
    type: ROUTE
    when:
      - { if: state.confidence == "INSUFFICIENT", end: INSUFFICIENT }
    otherwise: { next: recommend }
  recommend:
    { type: STEP, tool: recommend@1, in: { insights: state.insights, brief: inputs.brief },
      out: { recommendations: state.recommendations }, next: check-fidelity }
  check-fidelity:
    { type: STEP, tool: check-recommendation-fidelity@1,
      in: { recommendations: state.recommendations, insights: state.insights },
      out: { recommendations: state.recommendations, verdict: state.fidelity }, next: after-fidelity }
  after-fidelity:
    type: ROUTE
    when:
      - { if: state.fidelity == "ENTAILED", next: sign-off }
      - { if: state.fidelity == "REVISED", next: recommend, loop: { budget: 2, on_exhausted: { end: DROPPED } } }
      - { if: state.fidelity == "DROPPED", end: DROPPED }
  sign-off:
    type: GATE
    kind: APPROVAL
    asks: "Can these recommendations go ahead as work?"
    criteria: Every recommendation rests on a surviving insight and serves the brief's outcome.
    reviewing: [state.conclusion, state.recommendations, state.confidence]
    deciders:
      - policy: grounded-inquiry-sign-off@1
      - agent: review-recommendations@1
      - person: { permission: agents.recommendation.approve }
    person_required_when: state.confidence == "INSUFFICIENT"
    note_into: state.notes
    on:
      PERMIT: { end: COMPLETE }
      DENY:   { next: gather }        # send back; loop budget from §15
```

Against the corpus walk of the platform's current engine: one path runs, not both; the revise and fidelity loops stop at 2; sign-off is asked of the policy, then an agent reviewer, then a person; an agent cannot permit without grounded evidence; a denial sends back within the default budget; `INSUFFICIENT` ends honestly; no condition is prose; every output is checked before it reaches state; every ending reads as a sentence.
