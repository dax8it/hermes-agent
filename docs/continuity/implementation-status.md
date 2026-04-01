# Total Recall / Continuity Implementation Status

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

## Completed slices

### 1. Continuity package + checkpoint flow
Commit:
- `b67644c5` feat(continuity): add total recall v0 checkpoint flow

Landed:
- importable `hermes_continuity` package
- checkpoint generation
- verify wrapper
- rehydrate wrapper
- continuity config scaffold
- derived state artifacts

Core files:
- `hermes_continuity/checkpoint.py`
- `hermes_continuity/verify.py`
- `hermes_continuity/rehydrate.py`
- `scripts/continuity/hermes_checkpoint.py`

### 2. Fail-closed compaction gate
Commit:
- `d2eaab57` feat(continuity): fail closed on compact when verify fails

Landed:
- `_compress_context()` protected by continuity verification
- compaction blocks on verification failure instead of proceeding optimistically

Primary integration point:
- `run_agent.py::_compress_context()`

### 3. Gateway + cron continuity receipts
Commit:
- `3141f30f` feat(continuity): add gateway and cron continuity receipts

Landed:
- gateway reset/auto-reset receipts
- cron stale/late continuity receipts
- latest continuity report artifacts

Primary files:
- `gateway/session.py`
- `cron/jobs.py`
- `hermes_continuity/receipts.py`

### 4. Behavioral benchmark harness
Commits:
- `c56b6840` feat(continuity): add behavioral benchmark smoke
- `88ed5990` fix(continuity): harden benchmark scenario isolation

Landed:
- sandboxed continuity benchmark runner under `bench/continuity/`
- CI-friendly benchmark smoke step
- isolated temporary `HERMES_HOME` benchmark scenarios

Primary files:
- `bench/continuity/run.py`
- `bench/continuity/cases.jsonl`
- `.github/workflows/tests.yml`

### 5. Signed continuity anchors
Commit:
- `73322178` feat(continuity): add anchor signature verification

Landed:
- Ed25519 continuity keypair generation
- signed anchor artifacts
- verification of signature, public-key digest, and anchored artifact digests
- anchor verification integrated into checkpoint verification

Primary files:
- `hermes_continuity/anchors.py`
- `hermes_continuity/checkpoint.py`
- `hermes_continuity/verify.py`

### 6. External memory inbox / quarantine / promote flow
Commits:
- `2b50884e` feat(continuity): add external memory inbox promotion flow
- `4503f799` feat(continuity): add external memory admin surface
- `55300994` fix(continuity): harden external promotion recovery

Landed:
- external memory ingest path disabled by default
- inbox + quarantine + promoted + rejected stores
- reviewer-gated promote/reject path
- tamper detection before promotion
- `PROMOTION_PENDING` recovery path
- CLI script admin surface for external memory review

Primary files:
- `hermes_continuity/external_memory.py`
- `scripts/continuity/hermes_external_memory.py`

### 7. Formal continuity admin commands
Commit:
- `af6240e4` feat(continuity): expose continuity admin commands

Landed:
- `/continuity benchmark`
- `/continuity external list [STATE]`
- `/continuity external show <candidate_id>`
- `/continuity external promote <candidate_id> <reviewer>`
- `/continuity external reject <candidate_id> <reviewer> <reason>`
- command available through CLI and gateway dispatch

Primary files:
- `hermes_continuity/admin.py`
- `hermes_cli/commands.py`
- `cli.py`
- `gateway/run.py`

## Benchmark coverage status

Current benchmark harness file:
- `bench/continuity/run.py`

Current behavioral cases:
- `checkpoint_verify_pass`
- `verify_detects_mutation`
- `anchor_signature_tamper`
- `anchor_manifest_tamper`
- `rehydrate_fail_closed`
- `gateway_auto_reset_receipt`
- `cron_stale_fast_forward_receipt`
- `external_memory_ingest_quarantine`
- `external_memory_promote`
- `external_memory_recovery`

## Latest verified status

Most recent commands to verify continuity state:
- `python bench/continuity/run.py`
- `python -m pytest tests/continuity -q`
- `python -m pytest tests/test_cli_continuity_command.py tests/gateway/test_continuity_command.py tests/hermes_cli/test_commands.py -q`

Expected current benchmark outcome after the latest benchmark update:
- `PASS`
- `10/10` behavioral cases passed

## What is now true in Hermes

Hermes now has:
- deterministic checkpoint creation
- verification before destructive transition continuation
- fail-closed compaction gating
- signed anchors over continuity artifacts
- gateway and cron continuity receipts
- external memory trust boundary with quarantine and reviewer promotion
- recovery path for split promotion failures
- operator/admin continuity command surface
- benchmarkable continuity behavior in sandboxed runs

## Remaining gaps

Still not complete / bullet-proof:
- broader benchmark coverage for more custody/freshness/provenance failure classes
- stronger provenance policy beyond source metadata + hashes
- richer user/operator reporting for continuity state over time
- possible first-class docs page for continuity operations and recovery playbooks
- more protected transitions beyond the current compaction/gateway/cron/external-memory surfaces

## Next recommended work

Near-term:
1. keep expanding the benchmark matrix when a new continuity control is added
2. add provenance policy rules for external imports
3. add richer continuity status/report surfaces
4. document operator runbooks for recovery and adjudication
