# Process use-case catalogue

Every distinct thing a real Sulis process needs from its definition and the engine that runs it,
collected from the four places processes are defined today. This catalogue is the requirement the
`v1` process-definition format (`docs/spec/process-definition.md`) and the conformance suite
(`src/sulis_workflows/conformance/`) are measured against: every id here gets a spec rule, a schema
element and a conformance case.

**Sources** (abbreviations used in the tables):

| Code | Source | Where |
|---|---|---|
| BR | sulis-brain library workflows and foundation schemas | `sulis-ai/plugins` → `plugins/sulis-brain/instances/*`, `schemas/foundation/*` |
| FD | fd-product-architecture processes, tools and executor | `focaldata/fd-product-architecture` → `processes/*`, `tools/*`, `executor/*`, `spec/process-execution-semantics.md` |
| ME | platform methodology sequences and outcome graphs | `sulis-ai/platform` → `methodology/sequences/*`, `methodology/outcomes/*`, `methodology/standards/GRAPH_SCHEMA_SPECIFICATION.md` |
| CS | platform content service governed processes and the guided engine | `sulis-ai/platform` → `apps/api/sulis/services/content/workflows/*`, `apps/api/sulis/services/agents/service_layer/guided/*` |
| WL | this library | `src/sulis_workflows/*` |

**Status today** is how the need is met by the *best* current implementation: **run** (executed and
tested), **partial** (executed with known gaps), **declared** (in a schema or prose, not executed),
**absent**.

Ids are stable; never renumber. A need is only listed once, under the source that states it most
precisely; the others are cited.

---

## 1. Inputs, state and data flow

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-IN-TYPED | Typed run inputs | A process declares its inputs with type, required/optional and default; a run that is missing a required input is refused before any step runs. | FD `schemas/process.schema.json:480`, `executor/service_layer/runner.py:77-139`; BR `workflow.schema.json` `state_contract`, `runner/.../state_contract.py:9-34`; CS `processes.py` `inputs_for` | partial (FD, BR) |
| UC-IN-AMBIENT | Host-provided inputs | A process may read values the host supplies to every run (e.g. a topology index, governed sources) and must declare them, so an undeclared ambient read is a validation error. | FD `runner.py:142-160` (undeclared today) | partial, undeclared |
| UC-STATE-CHANNELS | State channels with reducers | Named state channels with a type, default and reducer (replace, merge, append, upsert-by-id), so parallel and repeated writes combine predictably. | ME `GRAPH_SCHEMA_SPECIFICATION.md:77-82,396-410`; FD `executor/state.py:141-490`; WL `compiler/dag_parser.py:24-51` (parsed, ignored), `compiler/state_factory.py:113-136` | declared (ME, WL); per-process Python (FD) |
| UC-IN-OPTIONAL | Optional reads | A step may declare a read optional; a missing optional read does not block the step and is visibly absent in its instructions. | CS `resolve_next.py` `_starved` (`?` suffix; optional values never reach the prompt); BR `state_contract` `?` | partial |
| UC-IN-FALLBACK | Ordered fallbacks | A read may name an ordered list of keys; the first non-empty one is used (e.g. `framed_question`, else `brief`). | FD `tool_step.py:118-134`, `grounded-inquiry.process.yaml` (`question: [framed_question, brief]`) | run (FD) |
| UC-OUT-MULTI | Several named outputs | One step writes several named keys (e.g. insights, verdicts, survivors, a counter). | FD `tool_step.py:85-106` (one output to several keys too); ME `writes`; CS/WL write one key per step | run (FD); absent (CS, WL) |
| UC-OUT-TYPED | Governed output types | A step output declared as a governed type is checked against that type's schema before it is recorded; a violation is refused with the violations listed. | CS `guided/service.py:54-68,511-532`; FD `produces` (validated only in bespoke nodes) | run (CS) |
| UC-OUT-REPAIR | Bounded repair | An output that fails its schema gets one bounded repair attempt with the violations before the step is refused. | planned in the approved engine plan; FD fidelity gates revise | absent |
| UC-OUT-MODE | Output destination | A process declares where its approved output goes: kept by the service (`stored`) or written to a branch and proposed as a pull request (`repository`); the first listed is the default. | CS `processes.py:31-37`, `brief_engine.py:202-206,493` | run (CS, in Python) |
| UC-HANDOFF | Handoff contracts | Between two steps or outcomes: required outputs, how they map to the next inputs, constraints passed on, and what happens when they are missing (`block`, `warn`, `skip`). | ME `sequences/new-feature/HANDOFF_CONTRACT.yaml:14-41`, `standards/HANDOFF_CONTRACT_STANDARD.md:94,109` | declared |
| UC-SEED-ARTIFACTS | Artifacts from earlier work | A run can start from files or records an earlier outcome produced (not only from a brief). | ME `GRAPH_SCHEMA_SPECIFICATION.md:57-73`; platform `sequence_execution_engine.py:1054-1136` | run (ME engine) |

## 2. Flow: routes, stops and loops

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-ROUTE-EXPR | Conditional routes | A step's next step is chosen by a condition evaluated against run state, not by prose. | BR 77 conditional transitions in prose; ME `edges[].condition` strings; FD `gate.on_verdict`; WL `route_decider` (key lookup) | partial (WL, FD bespoke); prose (BR, ME) |
| UC-ROUTE-DEFAULT | No silent default | A conditional route set has an explicit default or is exhaustive; an unmatched value never silently takes the first route. | FD spec §1 (no default path) vs bespoke classifiers defaulting; WL `nodes/routing.py:24-25` (silent first route) | absent |
| UC-DECIDE | Decide-then-route steps | An agent or tool step whose output selects the route (a classifier), e.g. choosing complex/complicated/clear. | FD `entry_decision` (`nodes_prose.py:92,123`; `entry_decision.tool_ref` in CC); WL `route_decider` | run (bespoke FD, WL) |
| UC-PATHS | Alternative paths | A process has several named paths, and exactly one runs per entry decision. | FD `paths[]` (grounded-inquiry, recursive-refinement, conformance-convergence) | run (bespoke FD) |
| UC-PREPHASE | A phase before the decision | A step that always runs before the path choice and whose output the decision reads (framing the question). | FD `framing` (`compile.py:510-600`) | run (FD, GI only) |
| UC-VERDICT-ROUTE | Verdict routing with a vocabulary | A step returns a verdict from a declared vocabulary (survived/dropped/revised, entailed/dropped/revised) and each verdict has a route. | FD `gate.on_verdict` (`compile.py:137-174,220-233`), `interrogate.py:90-103` | run (bespoke FD) |
| UC-STOP-NAMED | Named terminal verdicts | A run ends with one of several named outcomes (complete, blocked, escalated, synthesised, no-go…), not just "done". | BR 30+ `[terminal:<verdict>]` names; ME `exit_reason`; FD `stopped` reasons; CS `derive_recipe_verdict.py` | partial (CS, via transition text) |
| UC-STOP-HONEST | Honest stop | A process can stop because the evidence does not support an answer (`insufficient`), recording why, and that stop is a success of the process, not a failure. | FD `confidence_verdict` insufficient (`compile.py:198-206`, `authorization.py:69`); ME irreducible blockers | run (FD) |
| UC-LOOP-BUDGET | Bounded loops | A loop back to an earlier step carries a budget (max passes or failures) and what happens when it runs out (route or verdict); the count survives a crash. | ME `loop:{max_iterations}`, `while.max_iterations`; FD `MAX_REVISE`, `MAX_DECOMPOSE` in Python (`guards.py:14-21`); CS `meta_spiral.py` (one loop); BR `self_heal_budget.py` | partial (CS one loop; FD hardcoded) |
| UC-LOOP-MANY | Several loops per process | Each loop has its own counter and budget (13 BR workflows loop, 6 more than once; research-synthesis has 5). | BR `instances/research-synthesis/workflow.jsonld`; FD three counters | absent (CS supports one) |
| UC-LOOP-WHILE | Check-first loops | Repeat a body while a condition holds, with a required maximum and exit reason. | ME `GRAPH_SCHEMA_SPECIFICATION.md:246-264`; WL `while` (inert) | declared |
| UC-TERMINATES-WHEN | Measured termination | A recursive path ends when a measured condition holds (every leaf atomic, every insight survived). | FD `terminates_when` (declared, never evaluated; `guards.py:29,42` test-only) | declared |
| UC-OPTIONAL-BRANCH | Opt-in branches | A branch that only runs when a flag asks for it (e.g. publish requested). | BR `instances/change-lifecycle/workflow.jsonld:55-70` | prose |
| UC-CYCLE-POLICY | Per-cycle policy | Something that changes per loop pass (e.g. rotate the model provider each cycle). | BR `change-lifecycle` | prose |

## 3. Parallel work and composition

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-PARALLEL | Static parallel branches | Several steps become ready together and are all handed out; parallel starts are allowed. | BR `initial_steps` (several), 7 workflows with fan-out; ME `fan_out`; WL fan-out via `Send` | partial (WL); serialised (CS) |
| UC-JOIN | Join policies | A step after parallel branches waits according to a policy: all succeeded, any succeeded, all finished; it runs once. | ME `SEQUENCE_GUIDE.md:792-850`; WL joins run once per superstep (defect) | declared (ME); defective (WL) |
| UC-FOREACH | For each item | Run a step or sub-process once per item of a runtime list, with isolated state, a concurrency limit and merged results. | FD sub-briefs `Send` (`compile.py:608`, `dispatch.py:205-251`); ME `for_each` (max nesting 2); WL `for_each` (inert) | bespoke (FD); declared (ME, WL) |
| UC-CALL | Call another process | A step runs another process with input/output mapping and waits for it; the child's steps are recorded under its own scope. | BR `workflow_dispatch` tools; FD `methodology_ref kind: process`; CS `run_subworkflow`; ME sub-outcomes | run (CS, BR); partial (FD) |
| UC-CALL-RESULT | Child result contract | A call declares how each of the child's terminal verdicts and outputs maps onto the parent's state, and the parent routes every verdict the child can end with; a child verdict the parent does not route is a validation error. | Corpus scenarios: critical-thinking's verdicts vs architect, author-a-discipline and dna-mint; prove and request-review vs change-lifecycle (BR); grounded-inquiry → conformance-convergence (FD) | absent |
| UC-CALL-DEPTH | Bounded recursion | A process that calls itself (directly or through others) has a depth limit; at the limit it takes a declared non-recursive path. | FD `max_depth=4` (`guards.py:24`, router forces non-recursive path `compile.py:130,701`); CS none (unbounded, measured 6 levels deep) | run (FD); absent (CS) |
| UC-CALL-PATH | Caller chooses the child's path | A call may force which path the child takes, or let the child decide. | FD `methodology_ref.path` (ignored today) | declared |
| UC-CALL-NESTING | Deep nesting | Calls nest three or more levels and every answer names the scope it belongs to. | CS `_dispatch_subworkflow` overwrites the inner scope (defect found in the corpus walk) | defective |
| UC-CALL-GATES | Child gates surface | A human decision inside a child process reaches the person and resumes the child; nested runs do not silently auto-approve. | FD nested `auto_sign_off=True` (`dispatch.py:120`); WL child gates orphaned; CS gates posted with platform id (fixed in A0) | partial |
| UC-SEQUENCE | Sequences of outcomes | An ordered chain of outcomes with a person's gate after some, optional steps and tail outcomes that run after the final gate. | ME `SEQUENCE.yaml:13-69`, `CREATING_SEQUENCES.md:302-308,782-829`; platform `sequence_execution_engine.py:343,548-579` | run (ME engine) |
| UC-EXEC-POLICY | Deviation policy | Whether a run may skip or reorder steps: strict, guided or custom. | ME `CREATING_SEQUENCES.md:302-308` | declared |

## 4. People in the loop

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-GATE-KINDS | Approval vs input | A human step either asks for a verdict (approval) or for an answer that becomes the step's output (input). | CS `guided/human_gate.py:28-78` | run (CS) |
| UC-GATE-VOCAB | One decision vocabulary | Decisions use one vocabulary across sources: approve, send back, reject, indeterminate (PERMIT/DENY/INDETERMINATE, APPROVED/REJECTED, REVISE/REJECT map onto it). | CS PERMIT/DENY/INDETERMINATE; ME APPROVED/REJECTED, `on_failure: REVISE|REJECT` | inconsistent |
| UC-GATE-ROUTE | Every decision routed | Each decision has a declared route or terminal verdict; a decision is never recorded and then ignored. | WL gates record and never route (`nodes/gate.py:28-59`, GV-05); CS send-back loop only | partial (CS); absent (WL) |
| UC-GATE-SENDBACK | Send back within a budget | A send-back returns to a declared step with the person's note, within a redo budget; with none left the run waits on a person. | CS `service.py:273-286,347-397` (A0 fix); ME Type B loopbacks | run (CS) |
| UC-GATE-HANDOFF | Send back elsewhere | A send-back may end this process and start another (e.g. an outcome review raising a new instruction). | CS `outcome_review_workflow.py:14-17,79` | run (CS, in Python) |
| UC-REFUSAL-MODE | Halt or pause on refusal | A refused approval either halts the run with a recorded reason or pauses it for later. | FD `approval_gate.on_refusal` (declared, never read; SD declares halt and pauses) | declared |
| UC-APPROVAL-AUTO | Policy-based auto-approval | An approval may resolve automatically when the host's policy says the subject is trusted for this permission; never when the evidence is insufficient; who decided and why is recorded. | FD `domain/authorization.py:36-131` (trust tier, threshold, human approvals keyed by `<process>:<step>`) | run (FD) |
| UC-GATE-CRITERIA | Criteria shown to the person | A gate carries the criteria the person judges against and the inputs being reviewed. | ME `gates.criteria[]`; CS gate notices show reviewed inputs | partial |
| UC-GATE-AUDIT | Who decided | Every decision records who decided, when, the note and the basis (human or policy). | CS `decide` records `decided_by`; FD `trust_basis` | run |

## 5. Failure, safety and side effects

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-RETRY | Retry within a budget | A failed step is retried up to a budget (with backoff for transient errors) and then escalated; a later success is recorded. | CS `record_step_result.py`, `resolve_next.py` (A0); WL `node_retry.py:39-63` (transient/permanent); BR `self_heal_budget.py` | run (CS, WL) |
| UC-FAILURE-MODES | Failure modes with recovery | A step names its expected failures and a recovery strategy for each: retry, compensate, escalate, abort, fallback, manual review; whether it blocks progress. | BR `failuremode.schema.json`, `instances/*/failuremodes.jsonld` (`routes_to` used but not in schema) | declared |
| UC-COMPENSATE | Undo on redo | When a loop sends work back, earlier results that depended on it are invalidated or undone. | BR `meta_spiral.py:252-287` `invalidate_delivery` | run (BR, one case) |
| UC-PRECONDITION | Preconditions | A step declares a condition that must hold before it runs; a destructive step must have one. | FD `precondition`, `destructive` (not evaluated; spec §6); BR `preconditions` (prose) | declared |
| UC-CRITICALITY | Criticality | A step is critical (never skipped, blocks), standard (blocks unless justified) or trivial (warns only). | ME `CREATING_OUTCOMES.md` criticality; BR `criticality` | declared |
| UC-SIDE-EFFECT-CLAIM | Side effects run once | A step with side effects is claimed before it runs; a second caller is told it is running; a stale claim can be taken over and that is logged. | CS `record_step_result.py`, `resolve_next.py:828-845` (A0); BR `change_claim`/`workflow_run_claim` leases (`runtime.py:361-506`) | run (CS, BR) |
| UC-LEASE | Leases for long work | A long step renews its claim while it runs, so it is not taken over after a fixed window. | BR claim TTL + reclaim; CS fixed 15-minute stale window | partial |
| UC-RESUME | Resume from records | Starting and resuming a run are the same operation, rebuilt from durable per-attempt records; nothing is held in memory between calls. | CS `resolve_next.py:1-11`; FD cached nested runs (`dispatch.py:150-158`) | run (CS) |
| UC-TOOL-RUNNER | No silent tool no-ops | A tool step whose tool has no runner is a validation error, not a silent success. | Corpus walk: 14 BR tool steps (`python_import`) silently "completed" | defective |

## 6. Verification and review patterns

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-SPIRAL | Verification spiral | Verify against scored dimensions with thresholds, an independent scorer and irreducible blockers; fail closed; loop within a maximum. | ME `CREATING_OUTCOMES.md:541-611`, `research-synthesis/GRAPH.yaml:334-353`; BR `ooda-spiral` | declared (ME); prose (BR) |
| UC-LENS-TRIAD | Multi-lens review | Three independent lens reviews and a lead lens produce a composite verdict with sign-offs. | ME `CREATING_OUTCOMES.md:91-129,420-429`, `research-synthesis/GRAPH.yaml:196-291`; BR research-synthesis `lens-sign-off` | declared |
| UC-FIDELITY | Faithfulness check | A check that generated content is entailed by the evidence it cites; drift is dropped or revised. | FD `check-recommendation-fidelity` (`recommendation_fidelity.py:146-164`) | run (FD) |

## 7. Tools, capabilities and triggers

| Id | Need | Required behaviour | Sources | Status today |
|---|---|---|---|---|
| UC-TOOL-KINDS | Tool mechanisms | A tool is code, an agent skill (free to choose its own route), a skill (instructions only), a composite of child tools with per-child mappings, or a process. | FD `tool.schema.json:78-146`, `tool_loader.py:474-525` | run (FD) |
| UC-TOOL-EFFECT | Side-effect kind | A tool declares query, mutation or side-effect, which decides whether a claim is needed. | BR `tool.schema.json` `kind` | declared |
| UC-CAPABILITY | Capability matching | A step names the capability it needs; a tool that provides it is chosen (local vs API transport). | BR `needs`/`provides`; platform `entity_compiler.py` local-vs-API selection | partial |
| UC-MECHANISM | Who does the step | Each step says whether code, an agent, a person, or a mix does it. | BR/CS `mechanism`; ME `execution`/`primitive` | run (CS) |
| UC-TRIGGER | Triggers | A process can start on a timer, an event, a state change, a webhook or a branch push; the host schedules, the definition declares. | BR `trigger.schema.json` | declared |
| UC-VERSION | Versioned definitions | A run pins the definition version it started on; a new version never changes a run in flight. | FD `execution_semantics_version` (`registry.yaml:14`) | partial |

---

## What this catalogue deliberately does not include

- **Studio catalogue metadata** (names, owners, marketing copy): not execution.
- **fd's register governance checks** (`scripts/check_*.py`): they check definitions in that repository, and are a pattern the library validator follows rather than a runtime need.
- **Model choice and prompts inside an agent step**: the host's concern; a step declares instructions and the mechanism.

## Maintenance

A new process that needs something not listed here adds an id (next free in its section) with its
source, before the format or engine changes to support it.
