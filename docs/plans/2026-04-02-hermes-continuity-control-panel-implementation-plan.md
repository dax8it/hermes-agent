# Hermes Continuity Control Panel Implementation Plan

> For Hermes: implement this in phases. Start with read-only continuity visibility, then add guarded operator actions. Do not start with destructive controls.

Date: 2026-04-02

Status update: the read-only panel and guarded continuity actions now exist in Hermes. This file is still useful as design history, but it should now be read as implementation history plus follow-up backlog, not as a greenfield plan.

Goal: add a Hermes-owned continuity control panel that shows agent/session context pressure, continuity health, freshness, incidents, receipts, benchmark status, and guarded manual actions for checkpoint / verify / rehydrate / benchmark.

Architecture: build a thin continuity dashboard backend on top of the existing `hermes_continuity` control-plane code, expose it through authenticated API routes in `gateway/platforms/api_server.py`, and serve a small static web UI from the same Hermes API server. Keep phase 1 read-only. Only after the read-only panel is stable should phase 2 add guarded operator actions. Because the existing OpenClaw Mission Control / Total Recall page at `127.0.0.1:8799` is not present in this repo, Hermes should own its own continuity panel implementation instead of depending on that external surface.

Tech Stack: aiohttp API server, vanilla HTML/CSS/JS static assets, `hermes_continuity.admin`, `gateway.session`, `agent/model_metadata.py`, existing continuity reports/incidents/bench artifacts.

## Current status snapshot

Implemented already:
- authenticated continuity API endpoints under `/api/continuity/*`
- Hermes-served panel assets under `/continuity/`
- read-only dashboard for health, sessions, incidents, reports, benchmark state, and external-memory queues
- guarded actions for checkpoint, verify, rehydrate, benchmark, incident note, and incident resolve
- same-origin action support from the Hermes-served panel
- operator-facing contract/docs for canonical `target_session_id`, source-session reuse, and stale-checkpoint remediation

Immediate next tasks from here:
- keep the rehydrate outcome contract obvious in the visible UI without requiring raw JSON inspection, and make it more prominent in summary/drill-down flow
- add easier report/incident drill-down from red summary cards
- add a browser/API smoke flow for checkpoint -> verify -> rehydrate including stale-custody remediation
- surface cron/gateway anomalies with tighter operator wording and links from summary cards into the relevant receipts/incidents

---

## Why this should exist now

The continuity subsystem is already real:
- deterministic checkpointing
- verify / rehydrate
- fail-closed compaction gate
- signed anchors
- incident lifecycle
- gateway / cron receipts
- missing / stale receipt detection
- freshness policy
- continuity benchmark
- operator docs

What is missing is operator leverage:
- one place to see what is green vs red
- one place to see context pressure per agent/session
- one place to inspect latest continuity artifacts and incidents
- one place to trigger safe continuity operations without hunting through CLI commands

That means the next step is not more hidden control-plane logic. It is a usable operator surface.

---

## Non-goals for v1

Do not include these in the first implementation slice:
- automatic destructive compaction buttons
- direct gateway session mutation buttons
- any action that bypasses existing fail-closed logic
- coupling to the external OpenClaw Mission Control codebase that is not in this repo
- live websocket/event-stream work unless the polling version proves insufficient

The first version should be:
- authenticated
- Hermes-owned
- read-only first
- safe-action second
- destructive-action later if ever

---

## Existing repo surfaces to reuse

### Continuity backend already present
- `hermes_continuity/admin.py`
- `hermes_continuity/checkpoint.py`
- `hermes_continuity/verify.py`
- `hermes_continuity/rehydrate.py`
- `hermes_continuity/guards.py`
- `hermes_continuity/incidents.py`
- `hermes_continuity/receipts.py`
- `hermes_continuity/external_memory.py`
- `hermes_continuity/freshness.py`

### Session / context-pressure inputs already present
- `gateway/session.py` — includes `SessionEntry.total_tokens`, token counters, session metadata
- `agent/model_metadata.py` — context-length resolution helpers

### Existing operator surfaces already present
- `cli.py` → `/continuity` dispatch
- `gateway/run.py` → `/continuity` command handling
- `hermes_cli/commands.py` → continuity slash command registry entry

### Existing HTTP surface to extend
- `gateway/platforms/api_server.py`
- `tests/gateway/test_api_server_jobs.py` gives the route-testing pattern to copy

---

## Proposed user-visible surface

### New routes

Serve these from the Hermes API server:

Read-only routes:
- `GET /api/continuity/summary`
- `GET /api/continuity/sessions`
- `GET /api/continuity/incidents`
- `GET /api/continuity/incidents/{incident_id}`
- `GET /api/continuity/report/{target}`
- `GET /api/continuity/benchmark`
- `GET /api/continuity/external/{state}`

Safe action routes:
- `POST /api/continuity/actions/checkpoint`
- `POST /api/continuity/actions/verify`
- `POST /api/continuity/actions/rehydrate`
- `POST /api/continuity/actions/benchmark`
- `POST /api/continuity/actions/incident-note`
- `POST /api/continuity/actions/incident-resolve`

Static UI routes:
- `GET /continuity/`
- `GET /continuity/app.js`
- `GET /continuity/styles.css`

Browser auth contract for the static panel:
- the panel loads as an unauthenticated static shell with a token input, similar to the existing external mission-control UI pattern already observed on `127.0.0.1:8799`
- all data and action requests send `Authorization: Bearer <token>` to Hermes-owned continuity routes
- only the JSON data/action routes are protected; the static HTML/CSS/JS shell is allowed to load without data
- document the inherited API-server behavior clearly: if no API key is configured, continuity routes behave like the rest of the Hermes API server and are effectively open to the local operator surface
- record this explicitly in `docs/continuity/control-panel.md` so there is no ambiguity about browser flow or no-key behavior

### Dashboard sections

1. Global continuity health
- latest checkpoint id
- manifest freshness
- anchor freshness
- latest verify status
- latest rehydrate status
- latest gateway receipt status/freshness
- latest cron receipt status/freshness
- benchmark status and case count
- open incident counts by verdict

2. Agents / sessions
- session id
- platform / chat type
- total tokens
- context used %
- context remaining %
- last update time
- latest continuity state summary if available

3. Incident rail
- open incidents first
- verdict badge
- transition type
- exact blocker
- created / resolved times

4. Artifact panel
- latest verify report
- latest rehydrate report
- latest gateway receipt
- latest cron receipt
- freshness badges on all of them

5. Safe actions panel
- Run checkpoint now
- Run verify now
- Run rehydrate now
- Run benchmark now
- Add incident note
- Resolve incident

These actions must be authenticated and logged.

---

## Data model for the dashboard

Create a dedicated continuity dashboard aggregation layer instead of making the UI stitch together raw CLI text.

Suggested new module:
- Create: `hermes_continuity/dashboard.py`

Suggested functions:

```python
from typing import Any, Dict


def build_continuity_summary() -> Dict[str, Any]:
    ...


def build_continuity_sessions_snapshot() -> Dict[str, Any]:
    ...


def build_continuity_incident_snapshot() -> Dict[str, Any]:
    ...
```

### Summary payload shape

```python
{
    "generated_at": "2026-04-02T00:00:00Z",
    "status": {
        "checkpoint_id": "ckpt_...",
        "manifest": {"exists": True, "stale": False, "age_sec": 120},
        "anchor": {"exists": True, "stale": False, "age_sec": 120},
    },
    "reports": {
        "verify": {"status": "PASS", "stale": False, "path": "..."},
        "rehydrate": {"status": "PASS", "stale": False, "path": "..."},
        "gateway-reset": {"status": "PASS", "stale": False, "path": "..."},
        "cron-continuity": {"status": "PASS", "stale": False, "path": "..."},
    },
    "benchmark": {
        "status": "PASS",
        "passed_count": 18,
        "case_count": 18,
    },
    "incidents": {
        "open": 2,
        "fail_closed": 0,
        "degraded": 2,
    },
    "external_memory": {
        "QUARANTINED": 0,
        "PENDING": 1,
        "PROMOTED": 4,
        "REJECTED": 0,
    },
}
```

### Session snapshot payload shape

```python
{
    "generated_at": "2026-04-02T00:00:00Z",
    "sessions": [
        {
            "session_key": "agent:main:telegram:dm:123",
            "session_id": "20260401_...",
            "platform": "telegram",
            "chat_type": "dm",
            "model": "gpt-5.4",
            "total_tokens": 42103,
            "context_limit": 128000,
            "context_used_pct": 0.329,
            "context_remaining_pct": 0.671,
            "updated_at": "...",
        }
    ]
}
```

Implementation note: derive `context_limit` using the same model metadata helpers used elsewhere instead of inventing a second context-length table.

---

# Implementation tasks

## Task 1: Add a continuity dashboard aggregation module

**Objective:** Create a stable structured data layer for the UI and API instead of formatting CLI strings.

**Files:**
- Create: `hermes_continuity/dashboard.py`
- Modify: `hermes_continuity/__init__.py`
- Test: `tests/continuity/test_continuity_dashboard.py`

**Step 1: Write failing tests for summary aggregation**

Add tests that assert:
- summary includes checkpoint / manifest / anchor fields
- report freshness is surfaced
- incident counts are aggregated
- benchmark summary is included

**Step 2: Run test to verify failure**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/continuity/test_continuity_dashboard.py -q`

Expected: FAIL — module/functions do not exist yet.

**Step 3: Implement `build_continuity_summary()`**

Use:
- `continuity_status_snapshot()` from `hermes_continuity.incidents`
- `list_continuity_incidents()`
- benchmark loader pattern already used in `hermes_continuity.admin`

Keep output structured JSON, not human-formatted strings.

**Step 4: Implement incident aggregation helpers**

Count:
- open incidents
- resolved incidents
- open `FAIL_CLOSED`
- open `DEGRADED_CONTINUE`
- open `UNSAFE_PASS`

**Step 5: Export the new helpers from `hermes_continuity/__init__.py`**

**Step 6: Run tests to verify pass**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/continuity/test_continuity_dashboard.py -q`

**Step 7: Commit**

```bash
git add hermes_continuity/dashboard.py hermes_continuity/__init__.py tests/continuity/test_continuity_dashboard.py
git commit -m "feat(continuity): add dashboard summary helpers"
```

---

## Task 2: Add session/context-pressure aggregation

**Objective:** Show per-session context pressure without inventing fake percentages.

**Files:**
- Modify: `hermes_continuity/dashboard.py`
- Maybe modify: `gateway/session.py` only if a safe listing helper is genuinely missing
- Maybe modify: `agent/model_metadata.py` only if a tiny helper wrapper is genuinely missing
- Test: `tests/continuity/test_continuity_dashboard.py`

**Step 1: Write failing tests for session snapshot payload**

Test should assert:
- `total_tokens` appears
- `context_limit` appears
- `context_used_pct` and `context_remaining_pct` are derived correctly

**Step 2: Run the failing test**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/continuity/test_continuity_dashboard.py -q`

**Step 3: Implement `build_continuity_sessions_snapshot()`**

Data sources:
- active gateway sessions from `gateway/session.py`
- model context resolution from `agent/model_metadata.py`

Prefer implementing this slice entirely inside `hermes_continuity/dashboard.py` first. Only touch `gateway/session.py` or `agent/model_metadata.py` if a real missing helper forces it.

Rules:
- use real model metadata or documented fallback behavior from `model_metadata.py`
- if model is unknown, surface `context_limit=null` and percentage fields as `null`
- do not make up precision when model resolution fails

**Step 4: Run tests to verify pass**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/continuity/test_continuity_dashboard.py -q`

**Step 5: Commit**

```bash
git add hermes_continuity/dashboard.py tests/continuity/test_continuity_dashboard.py gateway/session.py agent/model_metadata.py
git commit -m "feat(continuity): add session context pressure snapshot"
```

---

## Task 3: Add authenticated continuity API endpoints

**Objective:** Expose dashboard data through the existing Hermes API server.

**Files:**
- Modify: `gateway/platforms/api_server.py`
- Test: `tests/gateway/test_api_server_continuity.py`

**Step 1: Create API tests using the jobs API test pattern**

Copy the testing style from:
- `tests/gateway/test_api_server_jobs.py`

Add tests for:
- `GET /api/continuity/summary`
- `GET /api/continuity/sessions`
- `GET /api/continuity/incidents`
- `GET /api/continuity/incidents/{incident_id}`
- `GET /api/continuity/report/verify`
- `GET /api/continuity/benchmark`
- `GET /api/continuity/external/QUARANTINED`
- auth required path

**Step 2: Run tests to verify failure**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_continuity.py -q`

**Step 3: Add handlers to `api_server.py`**

Suggested handlers:

```python
async def _handle_continuity_summary(self, request):
    ...

async def _handle_continuity_sessions(self, request):
    ...

async def _handle_continuity_incidents(self, request):
    ...

async def _handle_continuity_incident_detail(self, request):
    ...

async def _handle_continuity_external_state(self, request):
    ...

async def _handle_continuity_report(self, request):
    ...

async def _handle_continuity_benchmark(self, request):
    ...
```

Implementation rules:
- use the existing API auth check pattern
- return JSON only
- never shell out for summary/status when in-process helpers already exist
- report 400 for unknown report targets

**Step 4: Register the routes**

Add route registration near the existing `/api/jobs` routes.
Every new continuity API route must call the same auth check pattern already used by the jobs API.

**Step 5: Run tests to verify pass**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_continuity.py -q`

**Step 6: Commit**

```bash
git add gateway/platforms/api_server.py tests/gateway/test_api_server_continuity.py
git commit -m "feat(api): add continuity dashboard endpoints"
```

---

## Task 4: Add static continuity dashboard asset serving

**Objective:** Serve a real web panel from Hermes itself instead of relying on the external Mission Control code.

**Files:**
- Create: `gateway/static/continuity/index.html`
- Create: `gateway/static/continuity/app.js`
- Create: `gateway/static/continuity/styles.css`
- Modify: `gateway/platforms/api_server.py`
- Test: `tests/gateway/test_api_server_continuity.py`

**Step 1: Add tests for static route delivery**

Tests should assert:
- `GET /continuity/` returns HTML
- `GET /continuity/app.js` returns JS
- `GET /continuity/styles.css` returns CSS

**Step 2: Run failing tests**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_continuity.py -q`

**Step 3: Add static-file route handlers**

Do not assume `add_static()` is already wired.
If needed, implement explicit handlers that read files from `gateway/static/continuity/`.
Keep the static shell loadable without data, but require the same Bearer-token auth gate on all continuity JSON data/action routes; do not expose protected continuity data anonymously.

**Step 4: Create minimal UI shell**

The initial HTML should have sections for:
- global continuity health
- sessions/context pressure
- incidents
- latest reports
- benchmark
- safe actions

The JS should fetch only the new Hermes continuity endpoints.
It must attach the operator-supplied Bearer token on every API request and handle 401s explicitly in the UI.

**Step 5: Run tests to verify pass**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/gateway/test_api_server_continuity.py -q`

**Step 6: Commit**

```bash
git add gateway/static/continuity/index.html gateway/static/continuity/app.js gateway/static/continuity/styles.css gateway/platforms/api_server.py tests/gateway/test_api_server_continuity.py
git commit -m "feat(api): serve continuity dashboard assets"
```

---

## Task 5: Implement the read-only continuity dashboard UI

**Objective:** Make the first usable continuity cockpit.

**Files:**
- Modify: `gateway/static/continuity/index.html`
- Modify: `gateway/static/continuity/app.js`
- Modify: `gateway/static/continuity/styles.css`

**Step 1: Render global health cards**

Show:
- checkpoint id
- manifest freshness
- anchor freshness
- verify status
- rehydrate status
- benchmark status
- open incident count

**Step 2: Render session/context pressure table**

Columns:
- session key
- session id
- model
- total tokens
- context limit
- used %
- updated at

Use color bands for pressure:
- < 60% green
- 60–80% yellow
- > 80% red

**Step 3: Render incident rail**

Show open incidents first.
Include:
- verdict
- transition type
- summary
- blocker
- created_at
- resolved_at if present

**Step 4: Render latest report cards**

For each report target:
- existence
- status
- freshness
- generated_at
- quick raw JSON expand

**Step 5: Render benchmark section**

Show:
- pass/fail
- cases passed / total
- failing scenarios if any

**Step 6: Add refresh behavior**

Initial version should use manual refresh + periodic polling every 15–30 seconds.
Do not add websocket complexity in v1.

**Step 7: Manual smoke test**

Run the API server locally, open `/continuity/`, and verify the panel renders with real continuity data.

**Step 8: Commit**

```bash
git add gateway/static/continuity/index.html gateway/static/continuity/app.js gateway/static/continuity/styles.css
git commit -m "feat(ui): add read-only continuity dashboard"
```

---

## Task 6: Add guarded operator actions

**Objective:** Add safe manual triggers for continuity operations without exposing destructive controls.

**Files:**
- Create: `hermes_continuity/actions.py`
- Modify: `gateway/platforms/api_server.py`
- Modify: `gateway/static/continuity/app.js`
- Test: `tests/continuity/test_continuity_actions.py`
- Test: `tests/gateway/test_api_server_continuity.py`

**Step 1: Write failing tests for safe actions**

Test these actions:
- checkpoint now
- verify now
- rehydrate now
- benchmark now
- incident note
- incident resolve

**Step 2: Run failing tests**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/continuity/test_continuity_actions.py tests/gateway/test_api_server_continuity.py -q`

**Step 3: Implement `hermes_continuity/actions.py`**

Suggested functions:

```python
def run_checkpoint_action(session_id: str, cwd: str | None = None) -> dict: ...
def run_verify_action() -> dict: ...
def run_rehydrate_action(target_session_id: str) -> dict: ...
def run_benchmark_action() -> dict: ...
def add_incident_note_action(incident_id: str, note: str) -> dict: ...
def resolve_incident_action(incident_id: str, resolution_summary: str) -> dict: ...
```

Rules:
- call existing continuity modules directly where practical
- return structured payloads, not formatted text
- record failures through existing incident/report paths
- do not expose compaction or anything that bypasses fail-closed protections

**Step 4: Add authenticated POST endpoints**

Suggested routes:
- `POST /api/continuity/actions/checkpoint`
- `POST /api/continuity/actions/verify`
- `POST /api/continuity/actions/rehydrate`
- `POST /api/continuity/actions/benchmark`
- `POST /api/continuity/actions/incident-note`
- `POST /api/continuity/actions/incident-resolve`

Required request-body contracts:
- checkpoint: `{ "session_id": "...", "cwd": "..." }`
- verify: `{}`
- rehydrate: `{ "target_session_id": "..." }`
- benchmark: `{}`
- incident-note: `{ "incident_id": "...", "note": "..." }`
- incident-resolve: `{ "incident_id": "...", "resolution_summary": "..." }`

**Step 5: Add UI controls**

UI requirements:
- explicit button labels
- disabled state while running
- result panel with last action output
- no hidden auto-runs
- checkpoint action requires an explicit session picker and optional cwd field
- rehydrate action requires an explicit target-session-id field; never infer this silently

**Step 6: Run tests to verify pass**

Run:
`source venv/bin/activate && python -m pytest -o addopts='' tests/continuity/test_continuity_actions.py tests/gateway/test_api_server_continuity.py -q`

**Step 7: Commit**

```bash
git add hermes_continuity/actions.py gateway/platforms/api_server.py gateway/static/continuity/app.js tests/continuity/test_continuity_actions.py tests/gateway/test_api_server_continuity.py
git commit -m "feat(continuity): add guarded dashboard actions"
```

---

## Task 7: Expand slash-command and help surface deliberately

**Objective:** Keep CLI/gateway continuity surfaces coherent with the new panel.

**Files:**
- Modify: `hermes_cli/commands.py`
- Modify: `cli.py`
- Modify: `gateway/run.py`
- Test: `tests/test_cli_continuity_command.py`
- Test: `tests/gateway/test_continuity_command.py`

**Step 1: Decide the command contract**

Recommended additions:
- `/continuity status`
- `/continuity report ...`
- `/continuity incident ...`
- optionally `/continuity open` or `/continuity panel` to print the dashboard URL if API server mode is enabled

Do not overload `/continuity` with browser-only assumptions if the API server is not running.

**Step 2: Update the command registry/help text**

The current continuity command registry still understates the real subcommand surface.
Update it to reflect status/report/incident support clearly.

**Step 3: Add/adjust tests**

Verify:
- help output includes the richer continuity surface
- command dispatch remains intact
- gateway formatting stays coherent

**Step 4: Commit**

```bash
git add hermes_cli/commands.py cli.py gateway/run.py tests/test_cli_continuity_command.py tests/gateway/test_continuity_command.py
git commit -m "docs(cli): align continuity command surface with dashboard"
```

---

## Task 8: Final docs and verification

**Objective:** Document the panel as a first-class Hermes operator surface.

**Files:**
- Modify: `docs/continuity/recovery-playbook.md`
- Modify: `docs/continuity/implementation-ledger.json`
- Modify: `docs/continuity/implementation-status.md`
- Create: `docs/continuity/control-panel.md`

**Step 1: Add operator doc for the panel**

Document:
- what the panel shows
- which routes exist
- which actions are safe
- which actions are intentionally excluded
- auth expectations

**Step 2: Update continuity implementation tracking**

Add the control panel slice to:
- implementation ledger
- generated implementation status

Explicitly run:
`python scripts/continuity/update_implementation_status.py`

and commit the regenerated `docs/continuity/implementation-status.md`.

**Step 3: Run the full focused verification slice**

Run:
```bash
source venv/bin/activate
python -m pytest -o addopts='' tests/continuity -q
python -m pytest -o addopts='' tests/gateway/test_continuity_command.py tests/gateway/test_api_server_continuity.py tests/test_cli_continuity_command.py -q
python bench/continuity/run.py
```

**Step 4: Manual verification**

Run the Hermes API server and verify:
- `/continuity/` loads
- summary cards populate
- session pressure renders
- incidents render
- safe actions work
- action failures are explicit and logged

**Step 5: Commit**

```bash
git add docs/continuity/control-panel.md docs/continuity/recovery-playbook.md docs/continuity/implementation-ledger.json docs/continuity/implementation-status.md
git commit -m "docs(continuity): document control panel"
```

---

## Endpoint contract for v1

### `GET /api/continuity/summary`
Returns:
- overall continuity summary
- freshness states
- incident counts
- benchmark summary

### `GET /api/continuity/sessions`
Returns:
- active sessions
- token usage
- context pressure

### `GET /api/continuity/incidents`
Returns:
- recent incidents
- supports `?state=OPEN|RESOLVED` later if needed

### `GET /api/continuity/report/{target}`
Targets:
- verify
- rehydrate
- gateway-reset
- cron-continuity
- external-memory-ingest
- external-memory-promotion
- external-memory-review

### `POST /api/continuity/actions/*`
All action responses should include:
- `ok`
- `action`
- `started_at`
- `finished_at`
- `result`
- `errors`

---

## Safety model

### Allowed in v1
- checkpoint
- verify
- rehydrate
- benchmark
- incident note / resolve

### Not allowed in v1
- compaction trigger
- arbitrary session reset trigger
- any direct memory mutation beyond already-existing reviewed continuity paths
- any action that bypasses fail-closed verification

### Auth
Reuse the existing API-server auth model. Do not expose these routes anonymously.

---

## Suggested implementation order

1. dashboard aggregation helpers
2. session/context pressure snapshot
3. continuity API endpoints
4. static asset serving
5. read-only dashboard UI
6. guarded operator actions
7. slash/help alignment
8. docs and final verification

This order keeps value high and risk low.

---

## Acceptance criteria

This feature is done when all of the following are true:

- Hermes serves `/continuity/` itself
- the panel renders real continuity data from Hermes-owned endpoints
- status, freshness, incidents, reports, benchmark, and session pressure are visible
- safe actions run from the panel and return explicit results
- the panel does not expose destructive continuity bypasses
- focused continuity/gateway tests pass
- `python bench/continuity/run.py` still passes
- continuity docs and implementation ledger/status are updated

---

## Recommended first execution slice

If implementing immediately, start with:
- Task 1
- Task 2
- Task 3
- Task 4
- Task 5

That gets Hermes to a read-only operator continuity cockpit fast.
Then decide whether phase-2 safe actions are worth adding immediately.

---

## Risks and mitigations

1. Risk: fake context percentages
- Mitigation: derive from real `SessionEntry.total_tokens` plus `model_metadata.py`; if unavailable, return null.

2. Risk: UI grows into a second control plane with weak safety
- Mitigation: keep v1 read-only; only add explicitly safe actions.

3. Risk: coupling to external Mission Control code not in this repo
- Mitigation: Hermes owns its own UI and API routes.

4. Risk: stale artifacts shown as healthy
- Mitigation: every report card and summary item must display freshness.

5. Risk: hidden auth gaps
- Mitigation: use the same auth checks as `/api/jobs`.

---

## Final recommendation

Build this now.
But build it as:
- Hermes-owned
- read-only first
- safe-action second
- destructive-action never by default

That is the clean productization layer on top of the continuity implementation that already exists.
