# Continuity Adjudication Guide

This guide defines how to classify incidents after the raw technical state has been inspected.
The goal is to avoid vague post-hoc language and produce a stable decision rule.

## Allowed verdicts

- `PASS`
- `FAIL_CLOSED`
- `UNSAFE_PASS`
- `DEGRADED_CONTINUE`

## Definitions

### PASS
Use when:
- continuity controls behaved as expected
- integrity/custody/freshness/rehydrate checks that matter for this transition all passed
- protected transitions may continue safely

Typical examples:
- verify passes after checkpoint creation
- benchmark scenario passes
- external-memory promotion succeeds with valid provenance and receipts

### FAIL_CLOSED
Use when:
- a required continuity control failed and the system correctly blocked
- a protected transition has not yet continued past the failed control
- the right next action is repair/recovery, not continuation

Typical examples:
- verify fails and compaction stops
- rehydrate refuses to restore from invalid state
- external-memory promotion is denied by provenance policy before canonical memory is mutated
- anchor signature is invalid and no protected transition continues

### UNSAFE_PASS
Use when:
- a protected transition already executed
- the continuity state should have failed closed before that action
- the system effectively allowed unsafe continuation

Typical examples:
- canonical memory mutated from an external candidate that should have been denied by policy
- a destructive transition executed despite invalid verification or missing required receipt
- a gateway/cron/external-memory action completed without its expected guard semantics

### DEGRADED_CONTINUE
Use sparingly.
Use only when:
- the work is non-protected
- you explicitly state the degraded dependency
- you explicitly state the risk
- you are not claiming continuity is healthy

Typical examples:
- reporting UX is stale, but no protected transition depends on it yet
- a non-authoritative helper artifact is missing while canonical verification remains intact

## Decision tree

1. Did a required continuity control fail?
- No -> candidate for `PASS`
- Yes -> continue

2. Did the system block the protected transition before continuation?
- Yes -> `FAIL_CLOSED`
- No -> continue

3. Did a protected transition actually execute anyway?
- Yes -> `UNSAFE_PASS`
- No -> continue

4. Is the work explicitly non-protected and risk-disclosed?
- Yes -> `DEGRADED_CONTINUE`
- No -> `FAIL_CLOSED`

## Failure-plane hints

### Integrity failures
Default verdict:
- usually `FAIL_CLOSED`
- `UNSAFE_PASS` if a protected transition already ran on invalid artifacts

### Custody failures
Default verdict:
- `FAIL_CLOSED`
- escalate quickly
- custody ambiguity should not be hand-waved into `DEGRADED_CONTINUE`

### Freshness failures
Default verdict:
- `FAIL_CLOSED` if freshness is required for the protected transition
- `DEGRADED_CONTINUE` only for explicitly non-protected work

### Rehydrate failures
Default verdict:
- `FAIL_CLOSED`
- `UNSAFE_PASS` if the system proceeded using reconstructed state that should have been rejected

### Gate coverage failures
Default verdict:
- `UNSAFE_PASS` if action executed without the required gate
- otherwise `FAIL_CLOSED`

### External-memory provenance failures
Default verdict:
- `FAIL_CLOSED` when denied before canonical mutation
- `UNSAFE_PASS` if policy should have denied import but canonical memory was already mutated

## Adjudication examples

### Example 1: Anchor tamper detected before compaction continues
- verify fails due to invalid anchor signature
- compaction is blocked
Verdict:
- `FAIL_CLOSED`

### Example 2: External-memory candidate denied by trust policy before promotion
- candidate is quarantined
- promotion denied because source agent/profile is untrusted
- no canonical memory mutation occurred
Verdict:
- `FAIL_CLOSED`

### Example 3: External-memory candidate promoted even though policy should have denied it
- policy required evidence/trusted workspace
- system still wrote to MEMORY.md
Verdict:
- `UNSAFE_PASS`

### Example 4: Benchmark report missing but no protected action depends on it yet
- latest benchmark output missing
- verify/anchor state still valid
- operator is only gathering information
Verdict:
- potentially `DEGRADED_CONTINUE`
- only if the operator explicitly notes the missing artifact and limits work to non-protected activity

### Example 5: All controls pass and receipts match expected transition
Verdict:
- `PASS`

## Minimal incident record

For every adjudicated incident, record:
- timestamp
- transition type
- failure plane(s)
- verdict
- whether protected transitions were blocked
- commands run
- artifacts inspected
- exact blocker/remediation
- incident state (`OPEN` or `RESOLVED`)
- resolution summary when closed

Use the continuity incident artifact format documented in:
- `docs/continuity/incident-artifact-format.md`

## Anti-patterns

Do not say:
- “memory looked okay”
- “probably fine”
- “seems coherent enough”
- “we can just continue and fix later”

Instead say:
- `PASS`
- `FAIL_CLOSED`
- `UNSAFE_PASS`
- `DEGRADED_CONTINUE`
with explicit evidence.
