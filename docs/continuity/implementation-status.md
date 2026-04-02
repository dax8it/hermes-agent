# Total Recall / Continuity Implementation Status

_Auto-generated from `docs/continuity/implementation-ledger.json` and git continuity history._

This document is the concrete implementation log for Hermes continuity work.
It exists so progress is recorded in-repo, not only in chat history.

## Goal

Turn Total Recall from a paper/system framing into a measurable Hermes continuity subsystem with:
- deterministic checkpoints
- explicit verification and rehydration
- fail-closed protected transitions
- signed continuity anchors
- external memory trust boundaries
- benchmarkable continuity behavior
- operator-facing admin surfaces
- implementation tracking in repo artifacts

## Implemented slices

### 1. Continuity package + checkpoint flow
Commit: `b67644c5`

Landed:
- importable hermes_continuity package
- checkpoint generation, verify wrapper, rehydrate wrapper
- continuity config scaffold and derived state artifacts

Primary files:
- `hermes_continuity/checkpoint.py`
- `hermes_continuity/verify.py`
- `hermes_continuity/rehydrate.py`
- `scripts/continuity/hermes_checkpoint.py`
- `scripts/continuity/hermes_verify.py`
- `scripts/continuity/hermes_rehydrate.py`

### 2. Fail-closed compaction gate
Commit: `d2eaab57`

Landed:
- _compress_context() blocked by continuity verification
- compaction no longer proceeds on verification failure

Primary files:
- `run_agent.py`

### 3. Gateway + cron continuity receipts
Commit: `3141f30f`

Landed:
- gateway reset/auto-reset receipts
- cron stale/late continuity receipts
- latest continuity report artifacts

Primary files:
- `gateway/session.py`
- `cron/jobs.py`
- `hermes_continuity/receipts.py`

### 4. Behavioral benchmark harness
Commit: `c56b6840 + 88ed5990`

Landed:
- sandboxed continuity benchmark runner under bench/continuity
- CI-friendly benchmark smoke step
- isolated temporary HERMES_HOME scenarios

Primary files:
- `bench/continuity/run.py`
- `bench/continuity/cases.jsonl`
- `.github/workflows/tests.yml`

### 5. Signed continuity anchors
Commit: `73322178`

Landed:
- Ed25519 continuity keypair generation
- signed anchor artifacts
- anchor verification integrated into checkpoint verification

Primary files:
- `hermes_continuity/anchors.py`
- `hermes_continuity/checkpoint.py`
- `hermes_continuity/verify.py`

### 6. External memory inbox / quarantine / promote flow
Commit: `2b50884e + 4503f799 + 55300994`

Landed:
- external memory ingest path disabled by default
- quarantine/promote/reject flow
- pending-state recovery for split promotion failures
- admin surface for external memory review

Primary files:
- `hermes_continuity/external_memory.py`
- `scripts/continuity/hermes_external_memory.py`

### 7. Formal continuity admin commands
Commit: `af6240e4`

Landed:
- /continuity benchmark
- /continuity external list/show/promote/reject
- CLI and gateway dispatch wiring

Primary files:
- `hermes_continuity/admin.py`
- `hermes_cli/commands.py`
- `cli.py`
- `gateway/run.py`

### 8. Benchmark coverage for anchor and external-memory behaviors
Commit: `2f81b2bf + fef966d4`

Landed:
- benchmark cases for anchor signature tamper and anchored manifest tamper
- benchmark cases for external memory ingest/promote/recovery

Primary files:
- `bench/continuity/run.py`
- `bench/continuity/cases.jsonl`
- `tests/continuity/test_continuity_bench.py`

### 9. Provenance policy + automatic implementation doc maintenance
Commit: `d578e07c`

Landed:
- external-memory provenance allow/deny policy
- benchmark coverage for provenance-policy blocking
- generated implementation-status document driven by a ledger + git timeline
- git hook to refresh the working document automatically on continuity commits

Primary files:
- `hermes_continuity/external_memory.py`
- `docs/continuity/implementation-ledger.json`
- `docs/continuity/implementation-status.md`
- `scripts/continuity/update_implementation_status.py`
- `.githooks/pre-commit`

### 10. Richer provenance policy controls
Commit: `9efb86e3`

Landed:
- trusted source profiles for external-memory imports
- workspace allowlist enforcement for external-memory imports
- evidence-required policy by source kind
- promotion re-checks the richer provenance policy
- benchmark scenario upgraded to exercise richer provenance denials

Primary files:
- `hermes_continuity/external_memory.py`
- `hermes_cli/config.py`
- `bench/continuity/run.py`
- `tests/continuity/test_external_memory.py`
- `tests/continuity/test_continuity_bench.py`

### 11. Continuity status/report UX
Commit: `a111d4d1`

Landed:
- /continuity status summary over manifests, anchors, latest reports, and external-memory queues
- /continuity report access to latest continuity artifacts
- formatted status/report output for CLI and gateway surfaces

Primary files:
- `hermes_continuity/admin.py`
- `tests/continuity/test_continuity_admin.py`
- `tests/gateway/test_continuity_command.py`

### 12. Incident logging and postmortem artifacts
Commit: `0b448f6f`

Landed:
- continuity incident JSON + markdown artifacts
- incident list/show/create admin surface
- incident artifact format doc for postmortems
- runbook/adjudication docs linked to the incident artifact workflow

Primary files:
- `hermes_continuity/incidents.py`
- `hermes_continuity/admin.py`
- `docs/continuity/incident-artifact-format.md`
- `docs/continuity/recovery-playbook.md`
- `docs/continuity/adjudication.md`
- `tests/continuity/test_continuity_incidents.py`
- `tests/continuity/test_continuity_admin.py`

### 13. Incident lifecycle updates and fail-closed stubs
Commit: `48150505`

Landed:
- incident timeline append command and helper
- auto-created or reused fail-closed incident stubs for verification failures
- auto-created or reused fail-closed incident stubs for rehydrate failures
- compaction gate now creates fail-closed incident stubs when blocked

Primary files:
- `hermes_continuity/incidents.py`
- `hermes_continuity/admin.py`
- `hermes_continuity/verify.py`
- `hermes_continuity/rehydrate.py`
- `hermes_continuity/guards.py`
- `docs/continuity/incident-artifact-format.md`
- `tests/continuity/test_continuity_incidents.py`
- `tests/continuity/test_continuity_admin.py`

### 14. Incident resolution and note workflow
Commit: `1b74c0fd`

Landed:
- explicit incident OPEN/RESOLVED state
- incident note and resolve commands
- resolution summary and resolved_at fields in artifacts
- incident listings/show output now expose lifecycle state

Primary files:
- `hermes_continuity/incidents.py`
- `hermes_continuity/admin.py`
- `docs/continuity/incident-artifact-format.md`
- `docs/continuity/recovery-playbook.md`
- `docs/continuity/adjudication.md`
- `tests/continuity/test_continuity_incidents.py`
- `tests/continuity/test_continuity_admin.py`

### 15. External-memory incident auto-stubs
Commit: `9b0d13d6`

Landed:
- blocked external-memory promotion failures auto-create fail-closed incidents
- recovery-required external-memory promotions auto-create degraded incidents
- repeated external-memory promotion failures reuse the latest matching open incident
- incident docs now describe external-memory incident lifecycle coverage

Primary files:
- `hermes_continuity/external_memory.py`
- `hermes_continuity/incidents.py`
- `docs/continuity/incident-artifact-format.md`
- `docs/continuity/recovery-playbook.md`
- `tests/continuity/test_external_memory.py`

### 16. Gateway/cron anomaly incident auto-stubs
Commit: `de39746b`

Landed:
- gateway receipt/reporting failures auto-create degraded incidents
- cron receipt/reporting failures auto-create degraded incidents
- gateway and cron tests now assert anomaly incident creation
- incident docs now describe gateway/cron anomaly coverage

Primary files:
- `hermes_continuity/receipts.py`
- `gateway/session.py`
- `cron/jobs.py`
- `docs/continuity/incident-artifact-format.md`
- `docs/continuity/recovery-playbook.md`
- `tests/gateway/test_total_recall_gateway_resume.py`
- `tests/cron/test_total_recall_cron_resume.py`

### 17. Benchmark expansion for anomaly and missing-artifact classes
Commit: `9b9b7e5a`

Landed:
- benchmark case for missing anchor artifact verification failure
- benchmark case for gateway receipt anomaly incident creation
- benchmark case for cron receipt anomaly incident creation
- benchmark matrix expanded to cover more of the continuity threat model

Primary files:
- `bench/continuity/run.py`
- `bench/continuity/cases.jsonl`
- `tests/continuity/test_continuity_bench.py`

### 18. Missing expected receipt detection
Commit: `84398b3a`

Landed:
- explicit detection for expected-but-missing gateway reset receipts
- explicit detection for expected-but-missing cron continuity receipts
- benchmark cases for missing expected gateway/cron receipts
- tests assert missing receipt detection creates degraded incidents

Primary files:
- `hermes_continuity/receipts.py`
- `bench/continuity/run.py`
- `bench/continuity/cases.jsonl`
- `tests/gateway/test_total_recall_gateway_resume.py`
- `tests/cron/test_total_recall_cron_resume.py`
- `tests/continuity/test_continuity_bench.py`

### 19. Freshness-policy hardening for receipts and reports
Commit: `current slice (see git timeline below)`

Landed:
- configurable checkpoint/report freshness thresholds
- gateway/cron expected receipt detection now treats stale receipts as freshness failures
- continuity status/report surfaces now expose freshness state
- benchmark cases for stale gateway/cron receipt detection

Primary files:
- `hermes_continuity/freshness.py`
- `hermes_continuity/receipts.py`
- `hermes_continuity/admin.py`
- `hermes_continuity/incidents.py`
- `hermes_cli/config.py`
- `bench/continuity/run.py`
- `bench/continuity/cases.jsonl`
- `tests/continuity/test_continuity_admin.py`
- `tests/continuity/test_continuity_bench.py`
- `tests/gateway/test_total_recall_gateway_resume.py`
- `tests/cron/test_total_recall_cron_resume.py`

### 20. Operator recovery runbooks and adjudication guidance
Commit: `846b148c`

Landed:
- operator recovery playbook for continuity incidents
- verdict/adjudication guide for PASS, FAIL_CLOSED, UNSAFE_PASS, and DEGRADED_CONTINUE
- recovery and adjudication docs linked into the continuity workflow

Primary files:
- `docs/continuity/recovery-playbook.md`
- `docs/continuity/adjudication.md`
- `docs/continuity/implementation-ledger.json`
- `docs/continuity/implementation-status.md`

## Benchmark coverage status

Current behavioral case count: `18`

- `checkpoint_verify_pass` — checkpoint then verify succeeds in a clean sandbox
- `verify_detects_mutation` — verification fails after canonical memory mutation
- `anchor_signature_tamper` — verification fails when the continuity anchor signature is tampered
- `anchor_manifest_tamper` — verification fails when a signed manifest artifact is tampered after anchoring
- `missing_anchor_artifact` — verification fails when the continuity anchor artifact is missing
- `rehydrate_fail_closed` — rehydrate fails closed when verification breaks
- `gateway_auto_reset_receipt` — gateway auto-reset writes a continuity receipt
- `gateway_receipt_anomaly_incident` — gateway receipt/reporting failure creates a degraded continuity incident
- `gateway_missing_expected_receipt` — missing expected gateway receipt is detected and logged as a degraded continuity incident
- `gateway_stale_receipt_detection` — stale gateway receipt is detected and logged as a degraded continuity incident
- `cron_stale_fast_forward_receipt` — cron stale catch-up writes a continuity receipt
- `cron_receipt_anomaly_incident` — cron receipt/reporting failure creates a degraded continuity incident
- `cron_missing_expected_receipt` — missing expected cron receipt is detected and logged as a degraded continuity incident
- `cron_stale_receipt_detection` — stale cron receipt is detected and logged as a degraded continuity incident
- `external_memory_ingest_quarantine` — external memory candidate is quarantined and listable
- `external_memory_promote` — external memory candidate is promoted into canonical memory
- `external_memory_provenance_policy` — external memory ingest is blocked by provenance policy for untrusted agent/profile, disallowed workspace, and missing evidence
- `external_memory_recovery` — external memory promotion recovers cleanly after archive failure

## Auto-discovered continuity git timeline

- `b67644c5` — feat(continuity): add total recall v0 checkpoint flow
- `d2eaab57` — feat(continuity): fail closed on compact when verify fails
- `3141f30f` — feat(continuity): add gateway and cron continuity receipts
- `c56b6840` — feat(continuity): add behavioral benchmark smoke
- `88ed5990` — fix(continuity): harden benchmark scenario isolation
- `73322178` — feat(continuity): add anchor signature verification
- `2b50884e` — feat(continuity): add external memory inbox promotion flow
- `4503f799` — feat(continuity): add external memory admin surface
- `55300994` — fix(continuity): harden external promotion recovery
- `fef966d4` — test(continuity): cover external memory behaviors
- `af6240e4` — feat(continuity): expose continuity admin commands
- `2f81b2bf` — test(continuity): cover anchor tamper behaviors
- `d578e07c` — feat(continuity): add provenance policy and doc automation
- `9efb86e3` — feat(continuity): enrich provenance policy controls
- `a111d4d1` — feat(continuity): add status and report surfaces
- `846b148c` — docs(continuity): add operator runbooks
- `0b448f6f` — feat(continuity): add incident postmortem artifacts
- `48150505` — feat(continuity): add incident lifecycle hooks
- `1b74c0fd` — feat(continuity): add incident resolution flow
- `9b0d13d6` — feat(continuity): add external promotion incident stubs
- `de39746b` — feat(continuity): add gateway cron anomaly incidents
- `9b9b7e5a` — test(continuity): expand anomaly benchmark coverage
- `84398b3a` — feat(continuity): detect missing expected receipts
- `5f35200b` — feat(continuity): harden freshness policy
- `c3034919` — docs(continuity): add verify and rehydrate scripts to inventory
- `5afaf94c` — docs: add continuity control panel implementation plan
- `d583c8c9` — feat(continuity): add dashboard summary helpers
- `5499a1dc` — feat(continuity): add session context snapshot
- `51dc4df8` — feat(api): add continuity dashboard endpoints
- `ea9cc663` — feat(api): serve continuity dashboard assets
- `77a270b6` — feat(ui): add read-only continuity dashboard

## What is now true in Hermes

- deterministic checkpoint creation
- verification before destructive transition continuation
- fail-closed compaction gating
- signed anchors over continuity artifacts
- gateway and cron continuity receipts
- external-memory quarantine, promotion, rejection, and recovery handling
- provenance policy enforcement for external-memory imports
- operator/admin continuity command surface
- benchmarkable continuity behavior in sandboxed runs
- in-repo implementation tracking that can be regenerated automatically

## Remaining gaps

- broader benchmark coverage for more freshness/custody/provenance failure classes
- richer user/operator reporting for continuity state over time
- possible first-class docs page for continuity operations and recovery playbooks
- more protected transitions beyond the current compaction/gateway/cron/external-memory surfaces

