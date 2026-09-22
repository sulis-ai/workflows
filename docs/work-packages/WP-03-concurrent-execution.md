# WP-03 — Concurrent execution: PARALLEL, JOIN, FOR_EACH

**Follows:** WP-02 (execution engine) — explicitly deferred there ("PARALLEL/JOIN/FOR_EACH ...
remain out of scope, genuinely deferred to WP-03").
**Spec:** `docs/spec/process-definition.md` §7.4 (parallel and join), §7.5 (for each), §9.3
(nesting and gates — the pattern this work package reuses). **Needs:** WP-02 unmodified
(`engine/run.py`'s `_drive_scope`, `_advance_process_call`, and the `result.outputs`/`_evaluate`
machinery §9.1 already built are reused directly, not rebuilt).

## Why this shape

This format's own engine has no background execution: `next()`/`report()`/`decide()` are the only
entry points, each call reconstructs the run's position from durable records and returns
(`engine/run.py`'s own module docstring — "nothing held in memory between calls"). There is
nowhere for literal concurrent execution to live inside the engine process itself. WP-02 already
solved the adjacent problem — a process calling another process (§9) — by treating the callee as
an independently-drivable **nested scope**, addressed by its own `scope` string, whose current
position is reconstructed by the same `_drive_scope` replay on every call; a hand-off from inside
it bubbles up to the caller untouched (§9.3, already built and tested).

A `PARALLEL` branch or a `FOR_EACH` item is the same shape one level down: not a separate,
independently-versioned Process (no `ref`, no `permission` of its own — `branches`/`do` name node
ids inside the *same* process's own `nodes:` map), but otherwise identical to a nested scope —
its own durable attempt history, its own current position, its own hand-offs. Reusing
`_drive_scope` directly (parameterised by a different `start` node and a different scope suffix)
rather than inventing a second execution mechanism is the two-way door: nothing about §9's own
tested behaviour changes, and this work package is additive.

**Convention, not standard:** the spec's own `join: { policy: ALL_SUCCESS | ANY_SUCCESS |
ALL_COMPLETE }` and `FOR_EACH`'s `max_concurrency`/`collect` vocabulary already mirrors AWS Step
Functions' `Parallel` and `Map` states closely enough that this is worth naming directly — not as
an adopted standard (Step Functions is one vendor's platform, not a W3C/IETF specification), but
as the closest documented prior art for "named branches feeding one join policy" and "iterate a
list with a bounded number of open items," so this design borrows its vocabulary's *meaning*
(what `ALL_SUCCESS` etc. count as) without adopting anything vendor-specific into the domain.

## A spec gap found while designing this, resolved here

Building `examples/recursive-refinement/` (which uses `FOR_EACH`, structurally, even though this
engine cannot run it yet) found that neither the spec nor the validator (`V12`) says how the `as:`
binding is exposed to the item's own isolated scope. The only usable option under the current
model — writing it into a `state.<name>` channel the whole process must declare — works but is
awkward: it pollutes the parent's own state namespace with a value that is only ever meaningful
inside one item's own isolated scope, and collides if two different `FOR_EACH`/`PARALLEL`
constructs want to reuse the same binding name.

**Proposed resolution:** a new `item.*` run-state namespace, parallel to `inputs.*`/`state.*`/
`host.*`/`steps.*`, populated only inside a `FOR_EACH` item's own isolated scope, holding exactly
one path — `item.value` (the current element) — plus `item.index` (its position in `over`, for
authors who need it, e.g. to build a per-item id). `as:` then names what to call it locally in the
item's own node graph is unnecessary — a fixed name (`item.value`) is simpler and matches how
`inputs.*`/`state.*` etc. are themselves fixed names, not author-chosen ones; `as:` narrows to
documentation-only (what the spec's own example calls the binding in prose) or is dropped in
favour of always referring to `item.value` directly. This is a genuine, small spec clarification —
flagged here for the PR that implements it to carry as its own decision entry, not decided
unilaterally in this document.

## Outcome

A validated `Process` containing `PARALLEL`, `JOIN` and `FOR_EACH` nodes runs through the same
`next(run, scope)`/`report(...)`/`decide(...)` contract as every other node kind: each branch or
item is reachable as its own nested scope (`{scope}/{node_id}.branch[{i}]` for a `PARALLEL`
branch, `{scope}/{node_id}.item[{i}]` for a `FOR_EACH` item), its hand-offs bubble up exactly as
a nested `PROCESS` call's already do, and a `JOIN` node (reached either directly after a
`PARALLEL`, or synthesised as `FOR_EACH`'s own `join:` field) evaluates its policy by reading each
branch/item's own durable ending — never by holding branch state in memory.

## Scope

1. **`domain/ports` — no new port.** Branches and items dispatch through the exact same
   `PolicyPort`/`CodeToolPort`/`RecordsPort`/`ClaimsPort` machinery every other node already uses;
   nothing about *what* a branch does is different, only *how many of them exist* and *how their
   outcomes combine*.
2. **`engine/run.py` — `_advance_parallel`, `_advance_join`, `_advance_for_each`** (mirroring the
   existing `_advance_step`/`_advance_route`/`_advance_gate`/`_advance_process_call` shape):
   - `_advance_parallel`: for each `branch` in `node.branches`, compute its own scope suffix and
     call `_drive_scope` with `scope_def.start` overridden to that branch's own node id. A branch
     that returns a non-`ENDED` answer (a hand-off) is surfaced to the caller with its own `scope`
     — exactly §9.3's rule, applied one level down. `_drive_scope` itself needs no change: it
     already takes an explicit `start` via the `scope_def` it's given; a `PARALLEL` node's own
     branches share the *parent's* `scope_def.nodes` (they are not a separate Process), so the
     `_ScopeDef` passed in only needs its own `start` overridden per branch, not a whole new node
     map.
   - `_advance_join`: once every branch this JOIN's own `branches` (read from the preceding
     `PARALLEL` node, resolved via the call graph the same way `v10_calls`'s own `_build_call_graph`
     resolves reachability) has reached `ENDED`, evaluate `policy` against each branch's own
     `outcome` (`SUCCESS`/`STOPPED`/`FAILURE`, the same three values every `Ending` already
     carries): `ALL_SUCCESS` requires every branch's outcome to be `SUCCESS`; `ANY_SUCCESS`
     requires at least one; `ALL_COMPLETE` requires only that every branch reached *some* ending,
     regardless of outcome. Not yet met (a branch still mid-flight) returns whatever hand-off that
     branch itself produced, exactly as `_advance_parallel` would; met and satisfied routes via
     `next`/`end`; met and unsatisfied routes via `on_join_failed`.
   - `_advance_for_each`: for each element of `over` (a list, `V12`-checked already), the same
     nested-scope treatment as a `PARALLEL` branch, with the isolated scope's own `run_state`
     gaining the new `item.value`/`item.index` paths (above) before driving `node.do`. `collect`
     writes each item's own mapped output field into `into`'s own channel using that channel's
     already-declared reducer (`APPEND` is the natural fit; `V4`-style mapping-type checking
     applies exactly as it does to any other `out:` mapping). `join` (a `FOR_EACH`'s own policy
     field, same three values) governs whether the whole `FOR_EACH` is done, the same way
     `_advance_join` decides for a `PARALLEL`.
   - `max_concurrency`: **not a concurrency primitive the engine enforces** — there is nothing in
     this engine to enforce it against, since nothing runs unless a caller calls `next()`/
     `report()`. It is a *throttle on how many items this call is willing to newly offer as a
     pending hand-off at once*: `_advance_for_each` opens (dispatches for the first time) at most
     `max_concurrency` items that have not yet started, even if more of `over` remains, holding
     the rest back until an open item reaches `ENDED`. A caller free to run its own hand-offs
     however it likes (sequentially, or via its own `asyncio.gather` across several `report()`
     calls) sees this only as "the engine won't hand me item 5 until one of items 1-4 finishes" —
     genuine backpressure, not fake concurrency.
3. **`definition/validate.py` — new checks** (numbered informally, actual rule numbers assigned in
   the implementing PR): a `JOIN` node not reachable from exactly one `PARALLEL`'s own `join:`
   field (ambiguous which branch set it joins); a `PARALLEL` branch or `FOR_EACH`'s `do` naming a
   node id that does not exist (an extension of the existing `V2`/`V7` reference/reachability
   checks to these two node kinds, which `_all_targets` — `validate.py`'s own reachability walker
   — already partially covers per the code read for this design, at `ParallelNode`/`ForEachNode`'s
   own branches above).
4. **Depth (§9.2) is unaffected.** A `PARALLEL` branch or `FOR_EACH` item is not a process call —
   it shares the parent's own `depth` — so `on_depth_exhausted` and `max_depth` mean nothing here
   directly; a branch or item that *itself* calls another process still increments depth normally,
   unchanged from WP-02.

## Out of scope

Triggers (§11), templates (§13), observers (§12.5) — unchanged from WP-02, still deferred.
Any change to `compiler/`. Literal, engine-managed concurrent dispatch (explicitly rejected above
— out of scope by design, not by omission).

## Acceptance criteria

Each is a test.

- **A1.** A `PARALLEL` with 3 branches, driven one `report()` at a time, reaches a `JOIN` with
  `policy: ALL_SUCCESS` only once every branch has independently reached a `SUCCESS` ending —
  proven by an intermediate `next()`/`report()` call still returning a pending branch's own
  hand-off, not a premature join result.
- **A2.** The same 3-branch `PARALLEL`, one branch ending `FAILURE`, with `policy: ALL_SUCCESS`
  routes via `on_join_failed` once the other two also finish, never silently treating the failed
  branch as if it had succeeded.
- **A3.** `policy: ANY_SUCCESS` with one branch `SUCCESS` and two still pending returns the pending
  branches' own hand-offs — it does not short-circuit to the join result the moment one branch
  succeeds, since a real "any" join still has to observe the others reach *an* ending (`ALL_COMPLETE`-shaped observation) before it can be sure no *other* signal like `on_join_failed` applies; confirms the exact wording decided in the implementing PR.
- **A4.** A `FOR_EACH` over a 5-item list with `max_concurrency: 2` offers exactly 2 items' own
  hand-offs on the first `next()` call, and only offers a 3rd once one of the first 2 is reported
  complete.
- **A5.** `collect: { output: x, into: state.xs }` accumulates every item's own mapped `x` value
  into `state.xs`, in an order a test can assert on (either completion order or `over`'s own
  index order — the implementing PR's own decision, recorded there).
- **A6.** A `PARALLEL` branch that itself calls another `PROCESS` (§9) increments depth normally
  and can hit `on_depth_exhausted` exactly as an un-nested call would — proving branches don't
  accidentally reset or double-count depth.
- **A7.** `pytest`, `ruff` and `mypy` pass on Python 3.10–3.12 in CI for every new/changed module.

## Suggested PR sequence

1. `PARALLEL` + `JOIN` (A1-A3) — fixed branch count, no `item.*` namespace needed yet; the
   simpler case, proving the nested-scope reuse pattern before adding `FOR_EACH`'s own dynamic
   count and `collect`.
2. `FOR_EACH` (A4-A5) — `item.*` namespace, `max_concurrency` throttling, `collect`.
3. Depth interaction (A6) + validator checks (item 3 above).

Each PR carries its own principal summary and run record (see `CLAUDE.md`).

## If the spec is wrong or silent

The `as:`/`item.*` resolution above is a proposed clarification, not yet adopted spec text — the
implementing PR is where it becomes a real decision (with its own Dn entry), once a working
implementation has actually tested it against a real fixture, not merely designed on paper.
`max_concurrency`'s "throttles pending offers, not literal concurrency" reading is this work
package's own considered position, for the same reason: propose it in the first implementing PR,
do not treat it as decided until code and a test back it.
