# land-change — brain

Source: plugins/sulis-brain/instances/land-change/workflow.jsonld
Purpose: Drive a to-be-verified change to its landed (integrated) state per the repo's own source-control flow, never letting a change reach the integration line without a green verdict on its synchronized final state.
Use cases: UC-IN-TYPED, UC-IN-OPTIONAL, UC-IN-AMBIENT, UC-OUT-MULTI, UC-ROUTE-EXPR, UC-ROUTE-DEFAULT, UC-OPTIONAL-BRANCH, UC-STOP-NAMED, UC-LOOP-BUDGET, UC-GATE-ROUTE, UC-FAILURE-MODES, UC-PRECONDITION, UC-CRITICALITY, UC-CAPABILITY, UC-TOOL-EFFECT, UC-SIDE-EFFECT-CLAIM, UC-MECHANISM, UC-TRIGGER, UC-CALL (as a callee)

## Steps
| Step | Mechanism | Does | Calls / tool |
|---|---|---|---|
| provision-workspace | deterministic | Fresh private copy of the repo → `workspace-ref` | needs `provision-workspace` → local-provision-workspace (subprocess `provision_workspace_cli`) |
| isolate-change | deterministic | Own line of work; resolves `integration-branch` from GitWorkflowProfile → `isolation-ref`, `integration-branch` | needs `isolate-change` → local-isolate-change (`git checkout -b`) |
| stage-change | deterministic | Stages the full change → `change-staged` | needs `stage-change` → local-stage-change (`git add -A`) |
| record-change | deterministic | Durable revision → `recorded-revision-ref` | needs `record-change` → local-record-change (`git commit`) |
| declare-release-intent | deterministic | Conditional: ensure release artifact (changeset / version intent) is present → `release-intent-ref` | needs `declare-release-intent` → local-declare-release-intent (`sulis-changeset write`) |
| stage-release-intent | deterministic | Conditional: stage that artifact → `release-intent-staged` | local-stage-release-intent (`git add -A`) |
| commit-release-intent | deterministic | Conditional: commit it (`--allow-empty`, idempotent) → `release-intent-committed` | local-commit-release-intent (`git commit --allow-empty`) |
| publish-change | deterministic | Publish the revision to the shared host → `published-ref` | local-publish-change (`git push -u origin --force`) |
| request-integration | deterministic | Conditional: open integration request → `integration-request-ref`, `review-decision` | local-request-integration (`gh pr create`) |
| synchronize-with-base | deterministic | Refresh base to integration-branch tip → `base-synchronized` | local-synchronize-with-base (`git {merge_strategy_cmd}`) |
| verify-change | deterministic | THE GATE: run standing suite on synchronized state → `verify-verdict` green/red | needs `run-standing-suite` → local-run-standing-suite (`{test_command}`) |
| integrate-change | deterministic | Merge onto integration-branch → `merge-result`, `final-outcome` | local-integrate-change (`gh pr merge --{merge_strategy}`) |

All tools are side-effects matched by `needs` → `provides` (no `tool_ref` on steps).

No parallel starts, fan-out or joins are declared: one initial step; every route set is exclusive. There are two merge points of exclusive routes, which an engine must not treat as joins: `publish-change` (from `record-change` or `commit-release-intent`) and `synchronize-with-base` (from `publish-change`, `request-integration`, or the cycle back from `integrate-change`).

## Routes as declared
- `provision-workspace -> isolate-change` → unconditional.
- `isolate-change -> stage-change` → unconditional.
- `stage-change -> record-change` → unconditional.
- `record-change -> declare-release-intent [if release_trigger in {changeset-release-on-merge, tag} — the release artifact must travel with the change]` → condition on GitWorkflowProfile `release_trigger` (not a state key; ambient).
- `record-change -> publish-change [if release_trigger == manual — no travelling artifact required]` → condition `release_trigger == manual`. No default for other values.
- `declare-release-intent -> stage-release-intent` → unconditional.
- `stage-release-intent -> commit-release-intent` → unconditional.
- `commit-release-intent -> publish-change` → unconditional.
- `publish-change -> request-integration [if flow_kind in {trunk-based-gitops, gitflow, github-flow, worktree-based} — named flows integrate via a request]` → condition on GitWorkflowProfile `flow_kind`.
- `publish-change -> synchronize-with-base [if flow_kind == other AND no review gate — direct integration]` → condition on `flow_kind` and a "review gate" value that no profile field or state key holds.
- `request-integration -> synchronize-with-base` → unconditional.
- `synchronize-with-base -> verify-change [base refreshed to integration_branch tip]` → condition `base-synchronized == true`.
- `synchronize-with-base -> [terminal:not-landed] [if the base diverged irreconcilably — BOUNCE to the EDIT discipline]` → condition `base-synchronized == false` (best reading) → terminal verdict `not-landed`.
- `verify-change -> integrate-change [if GREEN — eligible to land]` → condition `verify-verdict == green`.
- `verify-change -> [terminal:not-landed] [if RED — defect-driven; the un-green change does NOT reach the integration line; BOUNCE to the EDIT discipline]` → condition `verify-verdict == red` → terminal verdict `not-landed`.
- `integrate-change -> [terminal:landed] [merged onto integration_branch per merge_strategy; the change reaches landed/integrated]` → condition on `merge-result` (merged) → terminal verdict `landed`.
- `integrate-change -> synchronize-with-base [CYCLE-BACK: base moved / not mergeable — base-moved, NOT defect; re-synchronize then re-verify]` → loop on `merge-result` (not mergeable); budget UNSTATED; exhaustion outcome UNSTATED.
- `integrate-change -> [terminal:not-landed] [if the integration request was REJECTED in review — defect-driven; BOUNCE to the EDIT discipline]` → condition `review-decision == rejected` → terminal verdict `not-landed`.
- Failure mode context-profile-missing `routes_to: [terminal:blocked]` (not in transitions; bound to no step) → terminal verdict `blocked`.

## Scenarios
### S1 — Named flow with a changeset, green, approved
- Inputs: `change-ref = "feat/add-export"`, `git-workflow-profile-ref` → `{flow_kind: github-flow, release_trigger: changeset-release-on-merge, integration_branch: main, merge_strategy: squash}`, `execution-environment-ref` → local-venv
- Scripted: every step succeeds; synchronize → `base-synchronized = true`; verify → green; review-decision → approved; integrate → merged
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, declare-release-intent, stage-release-intent, commit-release-intent, publish-change, request-integration, synchronize-with-base, verify-change, integrate-change]
- Expect gates: [] (the review decision is an external input read by integrate-change; no gate step is declared)
- Expect terminal: landed

### S2 — Manual release, flow `other`, direct integration
- Inputs: profile `{flow_kind: other, release_trigger: manual, integration_branch: main}`, no review gate
- Scripted: synchronize → true; verify → green; integrate → merged (`review-decision = not-required`)
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, publish-change, synchronize-with-base, verify-change, integrate-change]
- Expect gates: []
- Expect terminal: landed

### S3 — Base diverged irreconcilably
- Inputs: as S1
- Scripted: synchronize-with-base → unresolvable conflict (`base-synchronized = false`)
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, declare-release-intent, stage-release-intent, commit-release-intent, publish-change, request-integration, synchronize-with-base]
- Expect gates: []
- Expect terminal: not-landed

### S4 — Verify red
- Inputs: profile `{flow_kind: gitflow, release_trigger: tag, integration_branch: develop}`
- Scripted: synchronize → true; verify-change → red
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, declare-release-intent, stage-release-intent, commit-release-intent, publish-change, request-integration, synchronize-with-base, verify-change]
- Expect gates: []
- Expect terminal: not-landed (integrate-change never runs)

### S5 — Review rejected
- Inputs: as S1
- Scripted: verify → green; `review-decision = rejected`
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, declare-release-intent, stage-release-intent, commit-release-intent, publish-change, request-integration, synchronize-with-base, verify-change, integrate-change]
- Expect gates: []
- Expect terminal: not-landed

### S6 — Base moved once, loop taken, then lands
- Inputs: as S1
- Scripted: verify → green; integrate pass 1 → not mergeable; synchronize → true; verify → green; integrate pass 2 → merged
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, declare-release-intent, stage-release-intent, commit-release-intent, publish-change, request-integration, synchronize-with-base, verify-change, integrate-change, synchronize-with-base, verify-change, integrate-change]
- Expect gates: []
- Expect terminal: landed

### S7 — Base keeps moving, loop exhausted
- Inputs: as S1, a busy integration branch
- Scripted: integrate-change → not mergeable on every pass; synchronize → true; verify → green each time
- Expect visited: [..., synchronize-with-base, verify-change, integrate-change] repeated up to an UNSTATED budget
- Expect gates: []
- Expect terminal: UNSTATED (no budget or exhaustion route declared; best reading `not-landed` or `blocked`)

### S8 — Re-verify red after base moved
- Inputs: as S1
- Scripted: integrate pass 1 → not mergeable; synchronize → true; verify → red
- Expect visited: [provision-workspace, isolate-change, stage-change, record-change, declare-release-intent, stage-release-intent, commit-release-intent, publish-change, request-integration, synchronize-with-base, verify-change, integrate-change, synchronize-with-base, verify-change]
- Expect gates: []
- Expect terminal: not-landed

### S9 — Profile missing
- Inputs: `git-workflow-profile-ref` does not resolve
- Scripted: provision-workspace cannot bind its mechanism (failure mode context-profile-missing)
- Expect visited: [provision-workspace] (best reading; the failure mode is bound to no step)
- Expect gates: []
- Expect terminal: blocked

## Ambiguities for the process owner
- Route conditions read `release_trigger`, `flow_kind` and "a review gate" from GitWorkflowProfile, which are not state keys. "Review gate" has no field anywhere (the step's own text calls this a known resolver-input gap).
- `flow_kind == other` WITH a review gate has no route out of publish-change. `release_trigger` values other than the three named have no route out of record-change.
- The integrate → synchronize cycle has no budget and no exhaustion route.
- `terminal:blocked` exists only in a failure mode's `routes_to` (a field outside the failure-mode schema) and the failure mode is not bound to any step.
- `review-decision` is written by request-integration at the moment the PR is opened, before any human could review. Waiting for the review is not modelled; there is no gate step, so the process either reads a stale value or blocks outside the definition.
- The integrate-change route conditions (merged / not mergeable / rejected) are prose on `merge-result`, whose shape is `dict?` with no declared fields.
- `synchronize-with-base`'s two routes (refreshed vs irreconcilable) are not stated in terms of `base-synchronized`; the mapping is my reading.
- `publish-change` reads `release-intent-committed` even on the manual path where it is never written; it is optional in the contract but not marked optional as a read.
- `integrate-change` is the only `terminal_steps` entry, yet `synchronize-with-base` and `verify-change` also end the run.
- Failure modes carry no `kind`, `recovery_strategy` or `blocks_progress`; only `routes_to`.
- "Keep-or-revert resolves to revert/abandon" on red: whether land-change undoes the published branch or PR (compensation) is unstated.
- Every tool is a side-effect (`git push --force`, `gh pr merge`) with no claim or idempotency declared except commit-release-intent's `--allow-empty`; re-running after a crash may double-push or double-merge.
