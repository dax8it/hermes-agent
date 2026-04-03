# Continuity Control Panel

The continuity control panel is the Hermes-owned operator surface for Total Recall continuity state.
It exists so operators can inspect continuity health, session pressure, incidents, reports, benchmark status, and run a small set of guarded continuity actions without guessing at hidden state.
It also exposes a read-only derived Knowledge Plane so continuity operators can see coverage, lint, and contradiction health without treating that derived layer as canonical truth.

Route:
- `/continuity/`

Primary JSON endpoints:
- `GET /api/continuity/summary`
- `GET /api/continuity/sessions`
- `GET /api/continuity/knowledge`
- `GET /api/continuity/incidents`
- `GET /api/continuity/incidents/{incident_id}`
- `GET /api/continuity/report/{target}`
- `GET /api/continuity/benchmark`
- `GET /api/continuity/external/{state}`

Guarded action endpoints:
- `POST /api/continuity/actions/checkpoint`
- `POST /api/continuity/actions/verify`
- `POST /api/continuity/actions/rehydrate`
- `POST /api/continuity/actions/benchmark`
- `POST /api/continuity/actions/incident-note`
- `POST /api/continuity/actions/incident-resolve`

## What the panel shows

The current read-mostly control panel includes:
- Global continuity health
  - single-machine readiness status
  - latest checkpoint id
  - manifest/anchor freshness
  - verify/rehydrate status
  - benchmark status
  - incident counts
  - external-memory queue counts
- Agent session pressure
  - session id/key
  - model when available
  - token totals
  - context limit when resolvable
  - context used/remaining percentages when resolvable
  - current operator lane separated from other-profile and archived context
- Incident rail
  - open/resolved counts
  - FAIL_CLOSED / DEGRADED counts
  - recent incident summaries
  - resolved-history grouping plus readable resolution summaries
- Latest reports
  - single-machine-readiness
  - verify
  - rehydrate
  - gateway-reset
  - cron-continuity
  - knowledge-compile
  - knowledge-lint
  - knowledge-health
  - operator summary, subject metadata, remediation, freshness badges, and raw JSON expanders
- Knowledge Plane status
  - derived continuity article count
  - compile/lint/health status
  - thin-coverage and contradiction signals
  - source-coverage gaps across expected report targets
  - priority article list for grounded/high-importance items
  - watch list for stale or thin-coverage articles
  - informational only; not part of the fail-closed readiness gate on day one
- Benchmark panel
  - pass/fail
  - case counts
  - raw benchmark payload
- Guarded operator actions
  - checkpoint
  - verify
  - rehydrate
  - benchmark
  - incident note
  - incident resolve

## Browser/auth model

The static shell loads at `/continuity/` and then calls Hermes continuity JSON endpoints.

Auth rules:
- If the Hermes API server has a Bearer key configured, the JSON data/action routes require `Authorization: Bearer <token>`.
- The browser UI includes a token input and attaches that Bearer token to every continuity API request.
- If no API key is configured, continuity routes behave like the rest of the Hermes API server local operator surface.
- The static shell itself is just a UI shell; continuity data still comes from the JSON routes.

Related environment/config surface:
- `API_SERVER_ENABLED`
- `API_SERVER_HOST`
- `API_SERVER_PORT`
- `API_SERVER_KEY`
- `API_SERVER_CORS_ORIGINS`

Default local URL when the API server is enabled with defaults:
- `http://127.0.0.1:8642/continuity/`

Convenience commands:
- `/continuity panel`
- `/continuity open`

These print the continuity control-panel URL based on configured API-server host/port.

## Guarded actions and required request bodies

### Checkpoint
Route:
- `POST /api/continuity/actions/checkpoint`

Body:
```json
{ "session_id": "sess_...", "cwd": "/path/to/project" }
```

Notes:
- `session_id` is required
- `cwd` is optional
- the UI requires explicit session selection input; it does not guess

### Verify
Route:
- `POST /api/continuity/actions/verify`

Body:
```json
{}
```

### Rehydrate
Route:
- `POST /api/continuity/actions/rehydrate`

Body:
```json
{ "target_session_id": "sess_..." }
```

Notes:
- `target_session_id` is required
- `target_session_id` is the canonical operator-facing name across the panel, API, and docs
- the UI requires explicit target-session-id input; it does not infer one silently
- reusing the checkpoint source session ID is valid and should appear in the resulting report as `reuse_mode: source_session`

### Benchmark
Route:
- `POST /api/continuity/actions/benchmark`

Body:
```json
{}
```

### Incident note
Route:
- `POST /api/continuity/actions/incident-note`

Body:
```json
{ "incident_id": "incident_...", "note": "Operator note" }
```

### Incident resolve
Route:
- `POST /api/continuity/actions/incident-resolve`

Body:
```json
{ "incident_id": "incident_...", "resolution_summary": "What fixed it" }
```

## Safety contract

Allowed in the current panel:
- checkpoint generation
- verification
- rehydration
- benchmark runs
- incident note/resolve workflow

Intentionally not exposed as a panel action:
- direct compaction trigger
- arbitrary session reset trigger
- direct canonical-memory mutation outside the reviewed continuity paths
- anything that bypasses fail-closed continuity checks

Core rule:
- if continuity is not proven, protected transitions stay blocked

The control panel is an operator surface, not a bypass surface.

## Operational guidance

Use the panel when you need a quick answer to:
- what is red right now?
- which session is near context pressure?
- are reports stale or missing?
- do we have open FAIL_CLOSED / DEGRADED incidents?
- did benchmark regress?
- can I run verify / benchmark / checkpoint now without dropping into manual commands?

Use the CLI/gateway commands when you need exact text output or automation-friendly command flows:
- `/continuity status`
- `/continuity report single-machine-readiness`
- `/continuity report verify`
- `/continuity report rehydrate`
- `/continuity report gateway-reset`
- `/continuity report cron-continuity`
- `/continuity report knowledge-health`
- `/continuity incident list`
- `/continuity incident show <incident_id>`
- `/continuity external list QUARANTINED`

Canonical operator flow:
- The source of truth for the happy path and failure path is `docs/continuity/recovery-playbook.md`.
- The panel should surface the same contract:
  - verify proves checkpoint custody
  - rehydrate uses canonical `target_session_id`
  - source-session reuse is valid and operator-visible
  - stale checkpoint failures should tell the operator to create a fresh checkpoint, then rerun verify and rehydrate

## Immediate follow-up tasks

Single-machine one-human-many-agents continuity is now fully exercised on the live `filippo` profile, including a fresh `cron-continuity` receipt (`stale_fast_forward`, `PASS`). The control-panel smoke path is now available in both layers:

- API smoke coverage lives in `tests/gateway/test_api_server_continuity.py`, including the stale-checkpoint remediation sequence.
- Browser smoke automation lives in `scripts/continuity/panel_browser_smoke.sh` and drives the actual panel through:
  - checkpoint -> verify -> rehydrate
  - stale-checkpoint remediation (fresh checkpoint -> verify -> rehydrate)

The remaining work here is polish:

- Keep direct drill-down flow from a red summary card into the matching report and incident sharp and readable as the panel evolves.

Keep the panel opinionated about safety:
- no silent target inference
- no bypass actions
- no hiding fail-closed outcomes behind generic success/failure banners
- stale event receipts may self-heal into fresh maintenance heartbeats when verify and rehydrate are already healthy; this should read as "no recent event needed attention," not as reconstructed history

## Verification expectations

When modifying the control panel, at minimum re-run:
- `python scripts/continuity/verify_single_machine_readiness.py`
- `python -m pytest -o addopts='' tests/continuity -q`
- `python -m pytest -o addopts='' tests/gateway/test_api_server_continuity.py tests/gateway/test_continuity_command.py tests/hermes_cli/test_commands.py -q`
- `scripts/continuity/panel_browser_smoke.sh http://127.0.0.1:8642/continuity/`
- `python bench/continuity/run.py`

And manually verify:
- `/continuity/` loads
- summary cards render
- session pressure table renders
- incidents render
- report cards render
- benchmark renders
- guarded actions return explicit results
- auth failures are explicit, not silent
