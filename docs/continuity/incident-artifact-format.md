# Continuity Incident Artifact Format

This document defines the standard artifact shape for continuity incidents and postmortems in Hermes.

## Purpose

Every meaningful continuity incident should leave behind a durable artifact so the system has a record of:
- what failed
- what transition was involved
- whether protected transitions were blocked
- which verdict was issued
- what was inspected and what was done next

This closes the loop from:
- detect
- block
- recover
- adjudicate
- record

## Storage

Artifacts are written under:
- `<HERMES_HOME>/continuity/incidents/incident_<timestamp>.json`
- `<HERMES_HOME>/continuity/incidents/incident_<timestamp>.md`

Convenience pointers:
- `<HERMES_HOME>/continuity/incidents/latest.json`
- `<HERMES_HOME>/continuity/incidents/latest.md`

## Canonical JSON fields

Required top-level fields:
- `schema_version`
- `incident_id`
- `created_at`
- `verdict`
- `incident_state`
- `transition_type`
- `protected_transitions_blocked`
- `failure_planes`
- `summary`
- `exact_blocker`
- `exact_remediation`
- `resolved_at`
- `resolution_summary`
- `commands_run`
- `artifacts_inspected`
- `status_snapshot`
- `timeline`

### Field guidance

#### verdict
One of:
- `PASS`
- `FAIL_CLOSED`
- `UNSAFE_PASS`
- `DEGRADED_CONTINUE`

#### incident_state
One of:
- `OPEN`
- `RESOLVED`

#### transition_type
Examples:
- `compaction`
- `rehydrate`
- `gateway_reset`
- `cron_continuity`
- `external_memory_promotion`
- `operator_claim`

#### failure_planes
Zero or more of:
- `integrity`
- `custody`
- `freshness`
- `rehydrate`
- `gate_coverage`
- `external_memory`
- `retrieval`

#### status_snapshot
A point-in-time snapshot of current continuity state at incident creation.
It should include at least:
- checkpoint id if present
- manifest/anchor presence
- latest report surface statuses
- external-memory queue counts

#### timeline
Ordered entries recording incident lifecycle events.
Minimum useful first event:
- `incident_created`

## Markdown companion

Every JSON artifact should have a markdown companion for humans.
It should include:
- incident id
- verdict
- transition type
- summary
- blocker
- remediation
- commands run
- artifacts inspected
- timeline

## Example JSON skeleton

```json
{
  "schema_version": "hermes-continuity-incident-v0",
  "incident_id": "incident_2026-04-01T19-30-00Z",
  "created_at": "2026-04-01T19:30:00Z",
  "verdict": "FAIL_CLOSED",
  "incident_state": "OPEN",
  "transition_type": "compaction",
  "protected_transitions_blocked": true,
  "failure_planes": ["integrity", "custody"],
  "summary": "Anchor verification failed before compaction.",
  "exact_blocker": "Invalid continuity anchor signature",
  "exact_remediation": "Regenerate checkpoint and anchor from known-good state",
  "resolved_at": null,
  "resolution_summary": "",
  "commands_run": [
    "python scripts/continuity/hermes_verify.py"
  ],
  "artifacts_inspected": [
    "<HERMES_HOME>/continuity/reports/verify-latest.json"
  ],
  "status_snapshot": {},
  "timeline": [
    {
      "at": "2026-04-01T19:30:00Z",
      "event": "incident_created",
      "detail": "Anchor verification failed before compaction."
    }
  ]
}
```

## Minimal operator policy

Create an incident artifact when:
- a protected transition failed closed
- a protected transition should have failed closed but executed anyway
- you need a durable postmortem for a continuity incident
- you are making an operator-facing adjudication call

## Current command surface

Hermes-facing commands:
- `/continuity incident list`
- `/continuity incident show <incident_id>`
- `/continuity incident create <verdict> <transition_type> <blocked:true|false> <failure_planes_csv> <summary>`
- `/continuity incident append <incident_id> <event> <detail>`
- `/continuity incident note <incident_id> <detail>`
- `/continuity incident resolve <incident_id> <resolution_summary>`

## Current lifecycle behavior

- operators can create and append timeline events to incident artifacts
- operators can add plain notes and explicitly resolve incidents
- important fail-closed paths now auto-create or update incident stubs for verification, rehydrate, and blocked external-memory promotion failures
- partial external-memory promotion failures that require recovery now create degraded incident stubs
- repeated observations of the same open incident append timeline entries instead of blindly creating duplicate incidents

## Future extension ideas

Possible additions later:
- link incidents to benchmark failures automatically
- attach specific report payload excerpts
- generate incident bundles for export/sharing
