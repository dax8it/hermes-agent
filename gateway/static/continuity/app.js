const POLL_INTERVAL_MS = 20000;
const REPORT_TARGETS = ['verify', 'rehydrate', 'gateway-reset', 'cron-continuity'];
const VERIFY_REPORT_PATH = '/api/continuity/report/verify';

const tokenInput = document.getElementById('api-token');
const refreshButton = document.getElementById('refresh-button');
const globalError = document.getElementById('global-error');
const lastUpdated = document.getElementById('last-updated');
const statusGrid = document.getElementById('status-grid');
const sessionsBody = document.getElementById('sessions-body');
const incidentSummary = document.getElementById('incident-summary');
const incidentList = document.getElementById('incident-list');
const reportsGrid = document.getElementById('reports-grid');
const benchmarkPanel = document.getElementById('benchmark-panel');

function authHeaders() {
  const token = tokenInput.value.trim();
  const result = {};
  if (token) {
    result.Authorization = `Bearer ${token}`;
  }
  return result;
}

async function fetchJson(path) {
  const response = await fetch(path, { headers: authHeaders() });
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

function renderStatusCards(summary) {
  const status = summary.status || {};
  const reports = summary.reports || {};
  const benchmark = summary.benchmark || {};
  const incidents = summary.incidents || {};

  const cards = [
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
    },
    {
      label: 'Rehydrate',
      value: (reports.rehydrate || {}).status || 'missing',
      meta: `Fresh: ${boolLabel(!(((reports.rehydrate || {}).freshness || {}).stale))}`,
      badge: (reports.rehydrate || {}).status || 'UNKNOWN',
    },
    {
      label: 'Benchmark',
      value: benchmark.status || 'UNKNOWN',
      meta: `${benchmark.passed_count || 0}/${benchmark.case_count || 0} cases passing`,
      badge: benchmark.status || 'UNKNOWN',
    },
    {
      label: 'Open incidents',
      value: String(incidents.open || 0),
      meta: `FAIL_CLOSED: ${incidents.fail_closed || 0} · DEGRADED: ${incidents.degraded || 0}`,
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
      </article>
    `)
    .join('');
}

function renderSessions(snapshot) {
  const rows = (snapshot.sessions || [])
    .map((item) => `
      <tr>
        <td>
          <div class="primary-cell">${item.session_key || '—'}</div>
          <div class="meta-text">${item.platform || '—'} · ${item.chat_type || '—'}</div>
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
          <article class="incident-item">
            <div class="incident-top">
              <span class="${badgeClassFromStatus(item.verdict)}">${item.verdict || 'UNKNOWN'}</span>
              <span class="meta-text">${item.transition_type || 'unknown transition'}</span>
            </div>
            <h3>${item.summary || 'No summary'}</h3>
            <p class="meta-text">${item.exact_blocker || item.incident_id || ''}</p>
          </article>
        `)
        .join('')
    : '<p class="meta-text">No incidents recorded.</p>';
}

function renderReports(reportPayloads) {
  reportsGrid.innerHTML = reportPayloads
    .map(({ target, data }) => {
      const payload = data.report || {};
      const freshness = payload.freshness || {};
      const inner = payload.payload || {};
      return `
        <article class="report-card">
          <div class="report-top">
            <h3>${target}</h3>
            <span class="${badgeClassFromStatus(payload.status)}">${payload.status || 'UNKNOWN'}</span>
          </div>
          <p class="meta-text">Fresh: ${freshness.stale ? 'STALE' : 'FRESH'}</p>
          <p class="meta-text">Generated: ${formatTimestamp(inner.generated_at || payload.generated_at)}</p>
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
    <details>
      <summary>Benchmark payload</summary>
      <pre>${JSON.stringify(benchmark, null, 2)}</pre>
    </details>
  `;
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

    renderStatusCards(summary.summary || {});
    renderSessions(sessions.sessions || {});
    renderIncidents(incidents.incidents || {});
    renderReports(reports);
    renderBenchmark(benchmark);
    lastUpdated.textContent = `Last updated ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    showError(error.message || String(error));
  } finally {
    setLoadingState(false);
  }
}

refreshButton.addEventListener('click', () => {
  refreshDashboard();
});

tokenInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    refreshDashboard();
  }
});

refreshDashboard();
setInterval(refreshDashboard, POLL_INTERVAL_MS);
