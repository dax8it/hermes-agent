# Continuity Recovery Playbook

This is the operator runbook for continuity incidents in Hermes.
Use it when `/continuity status` is red, `/continuity report ...` shows a failure, or a protected transition should have been blocked.

This file is the canonical operator runbook for continuity v0.
If another doc disagrees with this one about verify / rehydrate behavior, this file wins.

## Core rule

If continuity is not proven, protected transitions stay blocked.
Do not substitute a coherent story for a verified state.

Protected transitions currently include at least:
- compaction / context mutation
- gateway session reset paths when continuity artifacts matter
- cron catch-up / stale recovery decisions
- external-memory promotion into canonical memory
- operator-facing claims that continuity is healthy
- irreversible writes that depend on reconstructed state

## Operator checklist

1. Capture the incident envelope.
   - failing command or trigger
   - timestamp
   - active profile / `HERMES_HOME`
   - workspace
   - suspected protected transition
   - whether the system already executed an action that should have been blocked

2. Get current continuity state.
   - `/continuity status`
   - `/continuity report verify`
   - `/continuity report rehydrate`
   - `/continuity report gateway-reset`
   - `/continuity report cron-continuity`
   - `/continuity external list QUARANTINED`
   - `/continuity external list PENDING`
   - `/continuity panel` when you want the control-panel URL for the Hermes continuity dashboard

3. Classify the failure plane.
   - integrity
   - custody
   - freshness
   - rehydrate
   - gate coverage
   - external-memory provenance / recovery

4. Apply the smallest correct recovery.

5. Re-run verification.
   - `python scripts/continuity/hermes_verify.py`
   - `python bench/continuity/run.py`
   - re-check `/continuity status`

6. Issue a formal verdict.
   - `PASS`
   - `FAIL_CLOSED`
   - `UNSAFE_PASS`
   - `DEGRADED_CONTINUE`

7. Record the incident if it was meaningful.
   - create a continuity incident artifact
   - preserve commands run, artifacts inspected, blocker, remediation, and verdict

## Canonical operator flow

### Happy path

1. Create a checkpoint from the current truth.
   - `python scripts/continuity/hermes_checkpoint.py --session-id <sid> --cwd <workspace>`
2. Verify the checkpoint custody.
   - `python scripts/continuity/hermes_verify.py`
   - or `/continuity report verify`
3. Rehydrate using canonical `target_session_id`.
   - new continuation session:
     - `python scripts/continuity/hermes_rehydrate.py --target-session-id <new_sid>`
   - source-session reuse:
     - `python scripts/continuity/hermes_rehydrate.py --target-session-id <active_checkpoint_source_sid>`
4. Confirm the rehydrate outcome.
   - `resulting_session_created=true` means a new continuation session was materialized
   - `resulting_session_created=false` with `reuse_mode: source_session` means the checkpoint source session was intentionally reused
5. Re-run:
   - `/continuity report rehydrate`
   - `python bench/continuity/run.py`

### Canonical naming contract

- The canonical operator-facing name is `target_session_id`.
- Preferred CLI flag:
  - `--target-session-id`
- Legacy CLI alias still accepted:
  - `--session-id`
- API/control-panel request body:
  - `{ "target_session_id": "..." }`

### Stale live checkpoint remediation

If verify or rehydrate says checkpoint custody no longer matches live profile state:

1. Treat it as correct fail-closed behavior.
2. Create a fresh checkpoint from current truth.
3. Re-run verify.
4. Re-run rehydrate using the `target_session_id` you actually want.

This is the normal remediation when the live session or continuity-owned files moved after the checkpoint was created.

## Recovery procedures by failure mode

### A. Verify report failed
Symptoms:
- `/continuity report verify` shows `FAIL`
- anchor mismatch, manifest digest mismatch, or memory digest mismatch

Action:
1. Stop protected transitions.
2. Inspect latest checkpoint artifacts:
   - `continuity/manifests/latest.json`
   - `continuity/anchors/latest.json`
3. Determine whether the failure is from:
   - expected mutation after checkpoint
   - anchor tamper / artifact tamper
   - stale or missing files
4. If the state is legitimately stale but not maliciously tampered:
   - regenerate checkpoint from current truth
   - re-run verify
5. If anchor custody or artifact tamper is suspected:
   - classify `FAIL_CLOSED`
   - do not promote/continue until trust is re-established

Operator truth:
- digest mismatch on continuity-owned files often means the live checkpoint is stale relative to current state
- the right fix is usually a fresh checkpoint, not forcing rehydrate through

### B. Rehydrate failed closed
Symptoms:
- `/continuity report rehydrate` shows `FAIL`
- target session not created
- verification error bubbles into rehydrate

Action:
1. Treat this as correct behavior unless proven otherwise.
2. Fix the underlying verify failure first.
3. Re-run rehydrate only after verify is green.
4. If rehydrate still fails with verify passing, classify as rehydrate-plane failure and inspect session reconstruction assumptions.

Operator truth:
- source-session reuse is valid when `target_session_id` matches the checkpoint source session
- successful source-session reuse should be visible as `reuse_mode: source_session`
- if rehydrate fails because checkpoint custody is stale, the remediation is: fresh checkpoint -> verify -> rehydrate

### C. Anchor/signature failure
Symptoms:
- invalid anchor signature
- anchor file missing
- public-key digest mismatch
- anchored artifact digest mismatch

Action:
1. Block all protected transitions.
2. Determine whether this is:
   - missing artifact from bad state migration
   - legitimate checkpoint supersession
   - actual tamper / custody break
3. If custody is uncertain, escalate immediately.
4. If the state simply needs a new authoritative checkpoint:
   - regenerate checkpoint and anchor from known-good current state
   - re-run verify and benchmark

### D. Gateway reset receipt anomaly
Symptoms:
- gateway reset happened but latest receipt is missing
- reason / old_session_id / new_session_id inconsistent with expectations
- continuity incident auto-created for gateway receipt/reporting failure

Action:
1. Inspect `/continuity report gateway-reset`.
2. If missing, classify gate-coverage or reporting failure.
3. If stale, classify freshness + gate-coverage failure.
4. Run missing/stale receipt detection when you know the expected reset context.
5. Confirm whether reset occurred automatically or manually.
6. If a protected transition relied on reset continuity and no receipt exists, prefer `FAIL_CLOSED` until reconstructed.

### E. Cron continuity anomaly
Symptoms:
- stale fast-forward / late catch-up happened without expected receipt
- unexpected next_run_at mutation
- continuity incident auto-created for cron receipt/reporting failure

Action:
1. Inspect `/continuity report cron-continuity`.
2. Run missing/stale receipt detection when you know the expected cron event/job context.
3. Confirm whether the receipt is missing, stale, or mismatched.
4. Confirm whether the job was:
   - late but inside grace
   - stale and correctly fast-forwarded
   - incorrectly fired / incorrectly skipped
5. If a protected cron transition executed without auditable continuity info, classify potential `UNSAFE_PASS`.

### F. External-memory quarantine or promotion failure
Symptoms:
- candidate stuck in `QUARANTINED`
- candidate stuck in `PENDING`
- promotion blocked by policy
- promotion recovery required
- continuity incident auto-created for external-memory promotion failure/recovery path

Action:
1. Inspect queues:
   - `/continuity external list QUARANTINED`
   - `/continuity external list PENDING`
2. Inspect candidate:
   - `/continuity external show <candidate_id>`
3. If quarantined by provenance policy:
   - fix policy or reject candidate
   - do not bypass with manual memory write
4. If pending after partial success:
   - retry promote through the admin surface
   - confirm no duplicate canonical memory entry was created
5. If candidate is invalid or temporary:
   - reject it and record the reason

## Control panel use in recovery

The control panel is the fastest operator view when you need:
- a one-screen health read on checkpoint/report freshness
- session pressure by active agent/session
- recent incidents and benchmark state
- safe manual verify/checkpoint/rehydrate/benchmark actions

Use `/continuity panel` (or `/continuity open`) to print the continuity dashboard URL.
The detailed panel contract lives in `docs/continuity/control-panel.md`.

## Recovery command set

Canonical commands:
- `python scripts/continuity/hermes_checkpoint.py --session-id <sid> --cwd <workspace>`
- `python scripts/continuity/hermes_verify.py`
- `python scripts/continuity/hermes_rehydrate.py --target-session-id <sid>`
- `python bench/continuity/run.py`
- `python scripts/continuity/hermes_external_memory.py list --state QUARANTINED`
- `python scripts/continuity/hermes_external_memory.py list --state PENDING`

Hermes-facing commands:
- `/continuity status`
- `/continuity report verify`
- `/continuity report rehydrate`
- `/continuity report gateway-reset`
- `/continuity report cron-continuity`
- `/continuity report external-memory-promotion`
- `/continuity external list QUARANTINED`
- `/continuity external list PENDING`
- `/continuity external show <candidate_id>`
- `/continuity external promote <candidate_id> <reviewer>`
- `/continuity external reject <candidate_id> <reviewer> <reason>`
- `/continuity incident create <verdict> <transition_type> <blocked:true|false> <failure_planes_csv> <summary>`
- `/continuity incident append <incident_id> <event> <detail>`
- `/continuity incident note <incident_id> <detail>`
- `/continuity incident resolve <incident_id> <resolution_summary>`
- `/continuity incident list`
- `/continuity incident show <incident_id>`
- `/continuity panel`
- `/continuity open`

## Escalation conditions

Escalate immediately when:
- anchor custody is broken or ambiguous
- key material drift cannot be explained by a legitimate reset/rebootstrap
- a protected transition already executed and should have been blocked
- canonical artifacts disagree and no clear authority exists
- continuity reports are missing across multiple surfaces at once

## Exit criteria

Recovery is complete only when:
- verify is green or intentionally fail-closed with documented blocker
- benchmark is green for the relevant path
- pending/quarantined external state is resolved or explicitly parked
- operator verdict is recorded as `PASS`, `FAIL_CLOSED`, `UNSAFE_PASS`, or `DEGRADED_CONTINUE`
