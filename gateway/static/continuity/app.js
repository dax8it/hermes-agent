const POLL_INTERVAL_MS = 20000;
const REPORT_TARGETS = ['single-machine-readiness', 'verify', 'rehydrate', 'gateway-reset', 'cron-continuity'];
const VERIFY_REPORT_PATH = '/api/continuity/report/verify';

const tokenInput = document.getElementById('api-token');
const refreshButton = document.getElementById('refresh-button');
const globalError = document.getElementById('global-error');
const lastUpdated = document.getElementById('last-updated');
const heroReadiness = document.getElementById('hero-readiness');
const heroMetrics = document.getElementById('hero-metrics');
const sessionOverview = document.getElementById('session-overview');
const statusGrid = document.getElementById('status-grid');
const sessionsBody = document.getElementById('sessions-body');
const incidentSummary = document.getElementById('incident-summary');
const incidentList = document.getElementById('incident-list');
const incidentDetail = document.getElementById('incident-detail');
const incidentDetailContent = document.getElementById('incident-detail-content');
const reportsGrid = document.getElementById('reports-grid');
const benchmarkPanel = document.getElementById('benchmark-panel');
const actionSummary = document.getElementById('action-summary');
const actionResult = document.getElementById('action-result');
const smokeFlowStatus = document.getElementById('smoke-flow-status');
const checkpointForm = document.getElementById('checkpoint-form');
const verifyForm = document.getElementById('verify-form');
const rehydrateForm = document.getElementById('rehydrate-form');
const benchmarkForm = document.getElementById('benchmark-form');
const incidentNoteForm = document.getElementById('incident-note-form');
const incidentResolveForm = document.getElementById('incident-resolve-form');
const rehydrateSubmitButton = rehydrateForm.querySelector('button[type="submit"]');

const latestActionState = {
  checkpoint: null,
  verify: null,
  rehydrate: null,
};

function authHeaders() {
  const token = tokenInput.value.trim();
  const result = {};
  if (token) {
    result.Authorization = `Bearer ${token}`;
  }
  return result;
}

async function parseResponse(response) {
  if (response.status === 401) {
    throw new Error('Unauthorized. Add a valid Bearer token.');
  }
  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = payload.error ? ` ${JSON.stringify(payload.error)}` : '';
    } catch (error) {
      detail = '';
    }
    throw new Error(`Request failed: ${response.status}.${detail}`);
  }
  return response.json();
}

async function fetchJson(path) {
  const response = await fetch(path, { headers: authHeaders() });
  return parseResponse(response);
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify(body || {}),
  });
  return parseResponse(response);
}

function setLoadingState(isLoading) {
  refreshButton.disabled = isLoading;
  refreshButton.textContent = isLoading ? 'Refreshing…' : 'Refresh';
}

function showError(message) {
  globalError.textContent = message;
  globalError.classList.remove('hidden');
}

function clearError() {
  globalError.textContent = '';
  globalError.classList.add('hidden');
}

function badgeClassFromStatus(status) {
  const normalized = String(status || 'UNKNOWN').toUpperCase();
  if (normalized.includes('FAIL') || normalized.includes('ERROR') || normalized.includes('STALE')) {
    return 'badge danger';
  }
  if (normalized.includes('DEGRADED') || normalized.includes('WARN')) {
    return 'badge warning';
  }
  return 'badge ok';
}

function sanitizeDomId(value) {
  return String(value || 'unknown').replace(/[^a-zA-Z0-9_-]+/g, '-');
}

function reportElementId(target) {
  return `report-card-${sanitizeDomId(target)}`;
}

function incidentElementId(incidentId) {
  return `incident-${sanitizeDomId(incidentId)}`;
}

function incidentDetailElementId(incidentId) {
  return `incident-detail-${sanitizeDomId(incidentId)}`;
}

function boolLabel(value) {
  return value ? 'Yes' : 'No';
}

function formatPct(value) {
  if (value === null || value === undefined) {
    return '—';
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatTimestamp(value) {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatSessionOutcome(outcome) {
  if (!outcome || !outcome.mode) {
    return 'Session outcome: unknown';
  }
  const parts = [outcome.label || outcome.mode];
  if (outcome.reuse_mode) {
    parts.push(`reuse_mode=${outcome.reuse_mode}`);
  }
  if (outcome.resulting_session_id) {
    parts.push(`resulting=${outcome.resulting_session_id}`);
  }
  return parts.join(' · ');
}

function shortId(value) {
  if (!value) {
    return '—';
  }
  return String(value).length > 18 ? `${String(value).slice(0, 18)}…` : String(value);
}

function describeFreshness(report) {
  const freshness = report.freshness || {};
  if (!report.status) {
    return 'Missing';
  }
  return freshness.stale ? 'Stale' : 'Fresh';
}

function hottestSession(snapshot) {
  const sessions = snapshot.sessions || [];
  return sessions.reduce((best, item) => {
    if (!best) {
      return item;
    }
    return (item.context_used_pct || 0) > (best.context_used_pct || 0) ? item : best;
  }, null);
}

function pressureClass(value) {
  if (value === null || value === undefined) {
    return 'pressure unknown';
  }
  if (value >= 0.8) {
    return 'pressure high';
  }
  if (value >= 0.6) {
    return 'pressure medium';
  }
  return 'pressure low';
}

function buildDrilldownButton(label, targetSelector, options = {}) {
  if (!targetSelector) {
    return '';
  }
  const attrs = [
    `type="button"`,
    `class="drilldown-link${options.compact ? ' inline-drilldown' : ' status-card-action'}"`,
    `data-drilldown-target="${targetSelector}"`,
  ];
  if (options.fillCheckpointSessionId) {
    attrs.push(`data-fill-checkpoint-session-id="${options.fillCheckpointSessionId}"`);
  }
  if (options.incidentDetailId) {
    attrs.push(`data-incident-detail-id="${options.incidentDetailId}"`);
  }
  return `<button ${attrs.join(' ')}>${label}</button>`;
}

function buildStatusCardAction(label, targetSelector, options = {}) {
  return buildDrilldownButton(label, targetSelector, options);
}

function highlightDrilldownTarget(target) {
  if (!target) {
    return;
  }
  target.classList.add('drilldown-focus');
  window.setTimeout(() => {
    target.classList.remove('drilldown-focus');
  }, 1800);
}

function transitionTypeForReport(target) {
  if (target === 'verify') {
    return 'verification';
  }
  if (target === 'rehydrate') {
    return 'rehydrate';
  }
  if (target === 'gateway-reset') {
    return 'gateway_reset';
  }
  if (target === 'cron-continuity') {
    return 'cron_continuity';
  }
  return null;
}

function resolveReportIncidentId(target, report, incidentsSnapshot) {
  const payload = report.payload || {};
  if (payload.incident?.incident_id) {
    return payload.incident.incident_id;
  }
  if (payload.incident_id) {
    return payload.incident_id;
  }
  const transitionType = transitionTypeForReport(target);
  if (!transitionType) {
    return null;
  }
  const recent = (incidentsSnapshot || {}).recent || [];
  const match = recent.find((item) => item.transition_type === transitionType);
  return match?.incident_id || null;
}

function reportIncidentIdForUi(target, report, incidentsSnapshot) {
  const payload = report.payload || {};
  if (payload.incident?.incident_id || payload.incident_id) {
    return resolveReportIncidentId(target, report, incidentsSnapshot);
  }
  const status = String(report.status || payload.status || '').toUpperCase();
  if (status.includes('FAIL') || status.includes('ERROR') || status.includes('DEGRADED')) {
    return resolveReportIncidentId(target, report, incidentsSnapshot);
  }
  return null;
}

function renderIncidentDetail(detail) {
  if (!detail) {
    incidentDetail.classList.add('hidden');
    incidentDetailContent.innerHTML = '<p class="meta-text">Select a failing report or incident to inspect the matching continuity incident detail.</p>';
    return;
  }
  const payload = detail.payload || {};
  const commandsRun = (payload.commands_run || []).map((item) => `<li><code>${item}</code></li>`).join('');
  const artifacts = (payload.artifacts_inspected || []).map((item) => `<li><code>${item}</code></li>`).join('');
  incidentDetail.classList.remove('hidden');
  incidentDetail.id = incidentDetailElementId(detail.incident_id || payload.incident_id || 'selected');
  incidentDetailContent.innerHTML = `
    <div class="incident-top">
      <span class="${badgeClassFromStatus(payload.verdict)}">${payload.verdict || detail.status || 'UNKNOWN'}</span>
      <span class="meta-text">${payload.transition_type || 'unknown transition'} · ${payload.incident_state || 'UNKNOWN'}</span>
    </div>
    <div class="incident-detail-copy">
      <h4>${payload.summary || 'Incident detail unavailable'}</h4>
      <p class="meta-text">Incident ID: ${detail.incident_id || payload.incident_id || '—'}</p>
      ${payload.exact_blocker ? `<p class="meta-text">Blocker: ${payload.exact_blocker}</p>` : ''}
      ${payload.exact_remediation ? `<p class="meta-text">Remediation: ${payload.exact_remediation}</p>` : ''}
      ${detail.path ? `<p class="meta-text">Artifact: ${detail.path}</p>` : ''}
      ${commandsRun ? `<div><p class="meta-text">Commands run</p><ul>${commandsRun}</ul></div>` : ''}
      ${artifacts ? `<div><p class="meta-text">Artifacts inspected</p><ul>${artifacts}</ul></div>` : ''}
    </div>
    <details>
      <summary>Incident JSON</summary>
      <pre>${JSON.stringify(detail, null, 2)}</pre>
    </details>
  `;
}

function renderMissionHero(summary, sessionsSnapshot, incidentsSnapshot, reportPayloads) {
  const readiness = summary.readiness || {};
  const reports = Object.fromEntries(reportPayloads.map(({ target, data }) => [target, data.report || {}]));
  const sessionCount = sessionsSnapshot.session_count || (sessionsSnapshot.sessions || []).length || 0;
  const hottest = hottestSession(sessionsSnapshot);
  const hotPct = hottest?.context_used_pct || sessionsSnapshot.highest_context_used_pct || 0;
  const benchmark = summary.benchmark || {};
  const checkpointId = (summary.status || {}).checkpoint_id;
  const openIncidents = (summary.incidents || {}).open || 0;
  const readinessStatus = readiness.status || (summary.reports || {})['single-machine-readiness']?.status || 'UNKNOWN';
  const verifyPayload = (reports.verify || {}).payload || {};
  const rehydratePayload = (reports.rehydrate || {}).payload || {};

  heroReadiness.innerHTML = `
    <span class="${badgeClassFromStatus(readinessStatus)}">${readinessStatus}</span>
    <p class="meta-text">${readiness.operator_summary || 'Continuity readiness has not been reported yet.'}</p>
  `;

  heroMetrics.innerHTML = `
    <article class="hero-metric">
      <p class="eyebrow">Active Sessions</p>
      <h2>${sessionCount}</h2>
      <p class="meta-text">${sessionCount ? 'Live sessions visible to the dashboard.' : 'No active sessions detected.'}</p>
    </article>
    <article class="hero-metric">
      <p class="eyebrow">Hottest Session</p>
      <h2>${formatPct(hotPct)}</h2>
      <p class="meta-text">${hottest ? shortId(hottest.session_id) : 'Context pressure is within guardrails.'}</p>
    </article>
    <article class="hero-metric">
      <p class="eyebrow">Open Incidents</p>
      <h2>${openIncidents}</h2>
      <p class="meta-text">${openIncidents ? 'Operator attention is required in the incident rail.' : 'No open continuity incidents.'}</p>
    </article>
    <article class="hero-metric">
      <p class="eyebrow">Benchmark</p>
      <h2>${benchmark.passed_count || 0}/${benchmark.case_count || 0}</h2>
      <p class="meta-text">${benchmark.status || 'UNKNOWN'} · Checkpoint ${shortId(checkpointId)}</p>
    </article>
  `;

  if ((reports.verify || {}).status || (reports.rehydrate || {}).status) {
    heroMetrics.insertAdjacentHTML(
      'beforeend',
      `
        <article class="hero-metric">
          <p class="eyebrow">Verify / Rehydrate</p>
          <h2>${verifyPayload.status || (reports.verify || {}).status || '—'} / ${rehydratePayload.status || (reports.rehydrate || {}).status || '—'}</h2>
          <p class="meta-text">${describeFreshness(reports.verify || {})} verify · ${describeFreshness(reports.rehydrate || {})} rehydrate</p>
        </article>
      `,
    );
  }
}

async function loadIncidentDetail(incidentId) {
  if (!incidentId) {
    renderIncidentDetail(null);
    return null;
  }
  const payload = await fetchJson(`/api/continuity/incidents/${incidentId}`);
  renderIncidentDetail(payload.incident || null);
  return payload.incident || null;
}

function renderStatusCards(summary, reportPayloads, incidentsSnapshot) {
  const status = summary.status || {};
  const reports = summary.reports || {};
  const benchmark = summary.benchmark || {};
  const incidents = summary.incidents || {};
  const readiness = summary.readiness || {};
  const recentIncidentId = incidents.open > 0 ? ((incidentsSnapshot || {}).recent || [])[0]?.incident_id : null;
  const reportMap = Object.fromEntries(reportPayloads.map(({ target, data }) => [target, data.report || {}]));
  const verifyIncidentId = resolveReportIncidentId('verify', reportMap.verify || {}, incidentsSnapshot);
  const rehydrateIncidentId = resolveReportIncidentId('rehydrate', reportMap.rehydrate || {}, incidentsSnapshot);

  const cards = [
    {
      label: 'Readiness',
      value: readiness.status || (reports['single-machine-readiness'] || {}).status || 'missing',
      meta: readiness.operator_summary || 'Single-machine readiness has not been reported yet.',
      badge: readiness.status || (reports['single-machine-readiness'] || {}).status || 'UNKNOWN',
      action: buildStatusCardAction('Open readiness report', `#${reportElementId('single-machine-readiness')}`),
    },
    {
      label: 'Checkpoint',
      value: status.checkpoint_id || 'missing',
      meta: `Manifest fresh: ${boolLabel(!(status.manifest || {}).stale)} · Anchor fresh: ${boolLabel(!(status.anchor || {}).stale)}`,
    },
    {
      label: 'Verify',
      value: (reports.verify || {}).status || 'missing',
      meta: `Fresh: ${boolLabel(!(((reports.verify || {}).freshness || {}).stale))}`,
      badge: (reports.verify || {}).status || 'UNKNOWN',
      action: String((reports.verify || {}).status || '').toUpperCase().includes('FAIL') && verifyIncidentId
        ? buildStatusCardAction('Open verify incident', '#incident-detail', { incidentDetailId: verifyIncidentId })
        : buildStatusCardAction('Open verify report', `#${reportElementId('verify')}`),
    },
    {
      label: 'Rehydrate',
      value: (reports.rehydrate || {}).status || 'missing',
      meta: `Fresh: ${boolLabel(!(((reports.rehydrate || {}).freshness || {}).stale))}`,
      badge: (reports.rehydrate || {}).status || 'UNKNOWN',
      action: String((reports.rehydrate || {}).status || '').toUpperCase().includes('FAIL') && rehydrateIncidentId
        ? buildStatusCardAction('Open rehydrate incident', '#incident-detail', { incidentDetailId: rehydrateIncidentId })
        : buildStatusCardAction('Open rehydrate report', `#${reportElementId('rehydrate')}`),
    },
    {
      label: 'Benchmark',
      value: benchmark.status || 'UNKNOWN',
      meta: `${benchmark.passed_count || 0}/${benchmark.case_count || 0} cases passing`,
      badge: benchmark.status || 'UNKNOWN',
      action: buildStatusCardAction('Open benchmark', '#benchmark-panel'),
    },
    {
      label: 'Open incidents',
      value: String(incidents.open || 0),
      meta: `FAIL_CLOSED: ${incidents.fail_closed || 0} · DEGRADED: ${incidents.degraded || 0}`,
      action: buildStatusCardAction(
        recentIncidentId ? 'Open latest incident' : 'Open incident rail',
        recentIncidentId ? '#incident-detail' : '#incident-list',
        recentIncidentId ? { incidentDetailId: recentIncidentId } : {},
      ),
    },
    {
      label: 'External memory',
      value: String((summary.external_memory || {}).PENDING || 0),
      meta: `Quarantined: ${(summary.external_memory || {}).QUARANTINED || 0} · Promoted: ${(summary.external_memory || {}).PROMOTED || 0}`,
    },
  ];

  statusGrid.innerHTML = cards
    .map((card) => `
      <article class="status-card">
        <div class="status-card-top">
          <p class="status-label">${card.label}</p>
          ${card.badge ? `<span class="${badgeClassFromStatus(card.badge)}">${card.badge}</span>` : ''}
        </div>
        <h3>${card.value}</h3>
        <p class="meta-text">${card.meta}</p>
        ${card.action || ''}
      </article>
    `)
    .join('');
}

function renderSessions(snapshot) {
  const sessions = snapshot.sessions || [];
  const highest = hottestSession(snapshot);
  const highestPct = highest?.context_used_pct || snapshot.highest_context_used_pct || 0;
  const operatorMove = highestPct >= 0.75
    ? 'Checkpoint hot session'
    : highest
      ? 'Monitor live rail'
      : 'Monitor rail';
  const operatorCopy = highestPct >= 0.75
    ? 'Use the quick checkpoint action in the hottest row below.'
    : highest
      ? 'The hottest session is healthy. Use its quick action when preparing a new checkpoint.'
      : 'Run a fresh checkpoint before a long operator sequence.';

  sessionOverview.innerHTML = `
    <div class="session-overview-grid">
      <article class="session-overview-item">
        <p class="eyebrow">Visible sessions</p>
        <strong>${snapshot.session_count || sessions.length || 0}</strong>
        <p class="meta-text">Live session keys currently exposed to Mission Control.</p>
      </article>
      <article class="session-overview-item">
        <p class="eyebrow">Highest pressure</p>
        <strong>${formatPct(highestPct)}</strong>
        <p class="meta-text">${highest ? shortId(highest.session_id) : 'No active session pressure yet.'}</p>
      </article>
      <article class="session-overview-item">
        <p class="eyebrow">Primary model</p>
        <strong>${highest?.model || sessions[0]?.model || '—'}</strong>
        <p class="meta-text">${highest?.platform || sessions[0]?.platform || 'No active runtime detected.'}</p>
      </article>
      <article class="session-overview-item">
        <p class="eyebrow">Operator move</p>
        <strong>${operatorMove}</strong>
        <p class="meta-text">${operatorCopy}</p>
      </article>
    </div>
  `;

  const rows = (snapshot.sessions || [])
    .map((item) => `
      <tr>
        <td>
          <div class="primary-cell">${item.session_key || '—'}</div>
          <div class="meta-text">${item.platform || '—'} · ${item.chat_type || '—'}</div>
          <div class="session-actions">
            <button
              type="button"
              class="drilldown-link inline-drilldown"
              data-drilldown-target="#checkpoint-form"
              data-fill-checkpoint-session-id="${item.session_id || ''}"
            >Use for checkpoint</button>
          </div>
        </td>
        <td>${item.model || '—'}</td>
        <td>${item.total_tokens ?? '—'}</td>
        <td>${item.context_limit ?? '—'}</td>
        <td><span class="${pressureClass(item.context_used_pct)}">${formatPct(item.context_used_pct)}</span></td>
        <td>${formatPct(item.context_remaining_pct)}</td>
        <td>${formatTimestamp(item.updated_at)}</td>
      </tr>
    `)
    .join('');
  sessionsBody.innerHTML = rows || '<tr><td colspan="7" class="meta-text">No active sessions found.</td></tr>';
}

function renderIncidents(snapshot) {
  incidentSummary.innerHTML = `
    <div class="pill-row">
      <span class="badge danger">FAIL_CLOSED ${snapshot.fail_closed || 0}</span>
      <span class="badge warning">DEGRADED ${snapshot.degraded || 0}</span>
      <span class="badge ok">OPEN ${snapshot.open || 0}</span>
      <span class="badge">RESOLVED ${snapshot.resolved || 0}</span>
    </div>
  `;

  const recent = snapshot.recent || [];
  incidentList.innerHTML = recent.length
    ? recent
        .map((item) => `
          <article class="incident-item" id="${incidentElementId(item.incident_id)}" data-incident-id="${item.incident_id || ''}">
            <div class="incident-top">
              <span class="${badgeClassFromStatus(item.verdict)}">${item.verdict || 'UNKNOWN'}</span>
              <span class="meta-text">${item.transition_type || 'unknown transition'}</span>
            </div>
            <h3>${item.summary || 'No summary'}</h3>
            <p class="meta-text">${item.exact_blocker || item.incident_id || ''}</p>
            ${buildDrilldownButton('Inspect incident detail', '#incident-detail', { incidentDetailId: item.incident_id, compact: true })}
          </article>
        `)
        .join('')
    : '<p class="meta-text">No incidents recorded.</p>';
}

function renderReports(reportPayloads, incidentsSnapshot) {
  reportsGrid.innerHTML = reportPayloads
    .map(({ target, data }) => {
      const payload = data.report || {};
      const freshness = payload.freshness || {};
      const inner = payload.payload || {};
      const incidentId = reportIncidentIdForUi(target, payload, incidentsSnapshot);
      const checkpointFreshness = inner.checkpoint_freshness || {};
      const remediation = inner.remediation || [];
      const subject = inner.subject || {};
      const subjectBits = [
        subject.session_key,
        subject.old_session_id && `old=${subject.old_session_id}`,
        subject.new_session_id && `new=${subject.new_session_id}`,
        subject.job_id && `job=${subject.job_id}`,
        subject.event_class && `class=${subject.event_class}`,
      ].filter(Boolean);
      return `
        <article class="report-card" id="${reportElementId(target)}" data-report-target="${target}">
          <div class="report-top">
            <h3>${target}</h3>
            <span class="${badgeClassFromStatus(payload.status)}">${payload.status || 'UNKNOWN'}</span>
          </div>
          <p class="meta-text">Fresh: ${freshness.stale ? 'STALE' : 'FRESH'}</p>
          ${inner.operator_summary ? `<p class="meta-text">${inner.operator_summary}</p>` : ''}
          <p class="meta-text">Generated: ${formatTimestamp(inner.generated_at || payload.generated_at)}</p>
          ${payload.path ? `<p class="meta-text">Artifact: ${payload.path}</p>` : ''}
          ${checkpointFreshness.generated_at ? `<p class="meta-text">Checkpoint: ${checkpointFreshness.stale ? 'STALE' : 'FRESH'} · ${formatTimestamp(checkpointFreshness.generated_at)}</p>` : ''}
          ${target === 'rehydrate' && inner.target_session_contract ? `<p class="meta-text">Canonical target field: ${inner.target_session_contract.canonical_name || 'target_session_id'} · CLI: ${inner.target_session_contract.cli_flag || '--target-session-id'}</p>` : ''}
          ${target === 'rehydrate' && inner.session_outcome ? `<p class="meta-text">${formatSessionOutcome(inner.session_outcome)}</p>` : ''}
          ${subjectBits.length ? `<p class="meta-text">Subject: ${subjectBits.join(' · ')}</p>` : ''}
          ${remediation.length ? `<p class="meta-text">Remediation: ${remediation.join(' ')}</p>` : ''}
          ${target === 'verify' && inner.failure_class === 'stale_live_checkpoint' ? `<button type="button" class="drilldown-link" data-drilldown-target="#checkpoint-form">Fresh checkpoint required</button>` : ''}
          ${target === 'rehydrate' ? `<button type="button" class="drilldown-link" data-drilldown-target="#rehydrate-form">Open rehydrate action</button>` : ''}
          ${incidentId ? buildDrilldownButton('Open matching incident', '#incident-detail', { incidentDetailId: incidentId, compact: true }) : ''}
          <details>
            <summary>Raw JSON</summary>
            <pre>${JSON.stringify(payload, null, 2)}</pre>
          </details>
        </article>
      `;
    })
    .join('');
}

function renderBenchmark(payload) {
  const benchmark = payload.benchmark || {};
  benchmarkPanel.innerHTML = `
    <div class="benchmark-header">
      <span class="${badgeClassFromStatus(benchmark.status)}">${benchmark.status || 'UNKNOWN'}</span>
      <p class="meta-text">${benchmark.passed_count || 0}/${benchmark.case_count || 0} cases passing</p>
    </div>
    <p class="meta-text">${benchmark.failed_count ? `${benchmark.failed_count} cases are failing and need operator review.` : 'Benchmark is green across the current continuity matrix.'}</p>
    <details>
      <summary>Benchmark payload</summary>
      <pre>${JSON.stringify(benchmark, null, 2)}</pre>
    </details>
  `;
}

function currentSmokeState(reportPayloads) {
  const reports = Object.fromEntries(reportPayloads.map(({ target, data }) => [target, data.report || {}]));
  const verify = latestActionState.verify || (reports.verify || {}).payload || {};
  const rehydrate = latestActionState.rehydrate || (reports.rehydrate || {}).payload || {};
  const checkpoint = latestActionState.checkpoint || {
    status: (verify.checkpoint_id || rehydrate.checkpoint_id) ? 'PASS' : null,
    checkpoint_id: verify.checkpoint_id || rehydrate.checkpoint_id || null,
  };
  const verifyStatus = String(verify.status || '').toUpperCase();
  const rehydrateStatus = String(rehydrate.status || '').toUpperCase();
  const staleVerify = verify.failure_class === 'stale_live_checkpoint';
  const canRehydrate = verifyStatus === 'PASS';
  const checkpointReady = Boolean(checkpoint?.checkpoint_id);

  return {
    checkpoint,
    verify,
    rehydrate,
    staleVerify,
    canRehydrate,
    checkpointReady,
    nextAction: staleVerify
      ? 'checkpoint'
      : verifyStatus === 'PASS' && rehydrateStatus === 'PASS'
        ? 'complete'
        : checkpointReady && verifyStatus !== 'PASS'
        ? 'verify'
        : canRehydrate && rehydrateStatus !== 'PASS'
          ? 'rehydrate'
          : 'checkpoint',
  };
}

function renderSmokeFlowStatus(reportPayloads) {
  const smoke = currentSmokeState(reportPayloads);
  const verifyStatus = smoke.verify.status || 'NOT RUN';
  const rehydrateStatus = smoke.rehydrate.status || 'NOT RUN';
  const checkpointId = smoke.checkpoint?.result?.checkpoint_id || smoke.checkpoint?.checkpoint_id || smoke.verify.checkpoint_id || smoke.rehydrate.checkpoint_id || 'pending';
  const checkpointStatus = smoke.checkpoint?.result?.status || smoke.checkpoint?.status || (checkpointId !== 'pending' ? 'PASS' : 'PENDING');
  const verifyDetail = smoke.staleVerify
    ? 'Verify failed closed with stale_live_checkpoint. Create a fresh checkpoint before rehydrate.'
    : smoke.verify.operator_summary || (verifyStatus === 'PASS' ? 'Verify is green.' : 'Run verify after checkpoint.');
  const rehydrateDetail = smoke.rehydrate.session_outcome
    ? formatSessionOutcome(smoke.rehydrate.session_outcome)
    : (smoke.canRehydrate ? 'Rehydrate is unlocked. Use canonical target_session_id.' : 'Rehydrate is locked until verify passes.');
  const nextTarget = smoke.nextAction === 'complete'
    ? '#action-summary'
    : smoke.nextAction === 'verify'
      ? '#verify-form'
      : smoke.nextAction === 'rehydrate'
        ? '#rehydrate-form'
        : '#checkpoint-form';
  const nextLabel = smoke.nextAction === 'complete'
    ? 'Smoke flow complete'
    : smoke.nextAction === 'verify'
      ? 'Next: run verify'
      : smoke.nextAction === 'rehydrate'
        ? 'Next: run rehydrate'
        : smoke.staleVerify
          ? 'Remediation: fresh checkpoint'
          : 'Next: run checkpoint';

  smokeFlowStatus.innerHTML = `
    <article class="smoke-step">
      <div class="smoke-step-top">
        <h4>Checkpoint</h4>
        <span class="${badgeClassFromStatus(checkpointStatus)}">${checkpointId !== 'pending' ? checkpointStatus : 'PENDING'}</span>
      </div>
      <p class="meta-text">Latest checkpoint: ${checkpointId}</p>
    </article>
    <article class="smoke-step">
      <div class="smoke-step-top">
        <h4>Verify</h4>
        <span class="${badgeClassFromStatus(verifyStatus)}">${verifyStatus}</span>
      </div>
      <p class="meta-text">${verifyDetail}</p>
    </article>
    <article class="smoke-step">
      <div class="smoke-step-top">
        <h4>Rehydrate</h4>
        <span class="${badgeClassFromStatus(rehydrateStatus)}">${rehydrateStatus}</span>
      </div>
      <p class="meta-text">${rehydrateDetail}</p>
    </article>
    <div class="toolbar-row">
      <button type="button" class="drilldown-link" data-drilldown-target="${nextTarget}">${nextLabel}</button>
    </div>
  `;

  rehydrateSubmitButton.disabled = !smoke.canRehydrate;
  rehydrateSubmitButton.title = smoke.canRehydrate
    ? ''
    : (smoke.staleVerify
      ? 'Verify is stale_live_checkpoint. Create a fresh checkpoint and rerun verify first.'
      : 'Run verify successfully before rehydrate.');
}

function renderActionSummary(summary, reportPayloads) {
  const reports = Object.fromEntries(reportPayloads.map(({ target, data }) => [target, data.report || {}]));
  const verifyPayload = (reports.verify || {}).payload || {};
  const rehydratePayload = (reports.rehydrate || {}).payload || {};
  const verifyStatus = (reports.verify || {}).status || 'UNKNOWN';
  const rehydrateStatus = (reports.rehydrate || {}).status || 'UNKNOWN';
  const readinessStatus = ((summary.readiness || {}).status) || 'UNKNOWN';
  const remediation = [
    ...((verifyPayload.remediation || [])),
    ...((rehydratePayload.remediation || [])),
  ];
  const staleCheckpointHint = remediation.some((item) => String(item).includes('fresh checkpoint'))
    ? 'stale_live_checkpoint remediation is active: create a fresh checkpoint before rehydrate.'
    : 'If verify or rehydrate reports stale_live_checkpoint, stop and create a fresh checkpoint before rehydrate.';
  const smoke = currentSmokeState(reportPayloads);
  const nextStep = smoke.nextAction === 'complete'
    ? 'Smoke flow is currently green.'
    : smoke.nextAction === 'verify'
      ? 'Checkpoint is present; verify should run next.'
      : smoke.nextAction === 'rehydrate'
        ? 'Verify is green; rehydrate is the next guarded action.'
        : smoke.staleVerify
          ? 'Checkpoint must be rerun before verify/rehydrate can continue.'
          : 'Start with a source-session checkpoint.';

  actionSummary.innerHTML = `
    <h3>Operator action summary</h3>
    <p class="meta-text">Readiness: <span class="${badgeClassFromStatus(readinessStatus)}">${readinessStatus}</span></p>
    <p class="meta-text">Verify: <span class="${badgeClassFromStatus(verifyStatus)}">${verifyStatus}</span> · Rehydrate: <span class="${badgeClassFromStatus(rehydrateStatus)}">${rehydrateStatus}</span></p>
    <p class="meta-text">${nextStep}</p>
    <p class="meta-text">${staleCheckpointHint}</p>
  `;
}

function bindDrilldownLinks() {
  document.querySelectorAll('[data-drilldown-target]').forEach((button) => {
    if (button.dataset.drilldownBound === 'true') {
      return;
    }
    button.dataset.drilldownBound = 'true';
    button.addEventListener('click', async () => {
      const target = document.querySelector(button.dataset.drilldownTarget);
      if (!target) {
        return;
      }
      if (button.dataset.fillCheckpointSessionId) {
        document.getElementById('checkpoint-session-id').value = button.dataset.fillCheckpointSessionId;
      }
      if (button.dataset.incidentDetailId) {
        await loadIncidentDetail(button.dataset.incidentDetailId);
      }
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      const focusable = target.querySelector('input, textarea, button');
      if (focusable) {
        focusable.focus();
      }
      highlightDrilldownTarget(target);
    });
  });
}

async function refreshDashboard() {
  setLoadingState(true);
  clearError();
  try {
    const reportRequests = REPORT_TARGETS.map((target) =>
      fetchJson(`/api/continuity/report/${target}`).then((data) => ({ target, data }))
    );
    const [summary, sessions, incidents, benchmark, ...reports] = await Promise.all([
      fetchJson('/api/continuity/summary'),
      fetchJson('/api/continuity/sessions'),
      fetchJson('/api/continuity/incidents'),
      fetchJson('/api/continuity/benchmark'),
      ...reportRequests,
    ]);

    renderMissionHero(summary.summary || {}, sessions.sessions || {}, incidents.incidents || {}, reports);
    renderStatusCards(summary.summary || {}, reports, incidents.incidents || {});
    renderSessions(sessions.sessions || {});
    renderIncidents(incidents.incidents || {});
    renderReports(reports, incidents.incidents || {});
    renderBenchmark(benchmark);
    renderActionSummary(summary.summary || {}, reports);
    renderSmokeFlowStatus(reports);
    bindDrilldownLinks();
    lastUpdated.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    showError(error.message || String(error));
  } finally {
    setLoadingState(false);
  }
}

async function runAction(path, body, actionName) {
  const payload = await postJson(path, body);
  if (actionName && latestActionState[actionName] !== undefined) {
    latestActionState[actionName] = payload.action?.result || payload.action || null;
  }
  actionResult.textContent = JSON.stringify(payload.action || payload, null, 2);
  await refreshDashboard();
}

checkpointForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runAction('/api/continuity/actions/checkpoint', {
    session_id: document.getElementById('checkpoint-session-id').value.trim(),
    cwd: document.getElementById('checkpoint-cwd').value.trim(),
  }, 'checkpoint').catch((error) => {
    actionResult.textContent = error.message;
  });
});

verifyForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runAction('/api/continuity/actions/verify', {}, 'verify').catch((error) => {
    actionResult.textContent = error.message;
  });
});

rehydrateForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runAction('/api/continuity/actions/rehydrate', {
    target_session_id: document.getElementById('rehydrate-session-id').value.trim(),
  }, 'rehydrate').catch((error) => {
    actionResult.textContent = error.message;
  });
});

benchmarkForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runAction('/api/continuity/actions/benchmark', {}).catch((error) => {
    actionResult.textContent = error.message;
  });
});

incidentNoteForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runAction('/api/continuity/actions/incident-note', {
    incident_id: document.getElementById('incident-note-id').value.trim(),
    note: document.getElementById('incident-note-text').value.trim(),
  }).catch((error) => {
    actionResult.textContent = error.message;
  });
});

incidentResolveForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  await runAction('/api/continuity/actions/incident-resolve', {
    incident_id: document.getElementById('incident-resolve-id').value.trim(),
    resolution_summary: document.getElementById('incident-resolve-text').value.trim(),
  }).catch((error) => {
    actionResult.textContent = error.message;
  });
});

refreshButton.addEventListener('click', () => {
  refreshDashboard();
});

tokenInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    refreshDashboard();
  }
});

bindDrilldownLinks();
refreshDashboard();
setInterval(refreshDashboard, POLL_INTERVAL_MS);
