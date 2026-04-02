const tokenInput = document.getElementById('api-token');
const refreshButton = document.getElementById('refresh-button');

function headers() {
  const token = tokenInput.value.trim();
  const result = {};
  if (token) {
    result['Authorization'] = `Bearer ${token}`;
  }
  return result;
}

async function fetchJson(path) {
  const response = await fetch(path, { headers: headers() });
  if (response.status === 401) {
    throw new Error('Unauthorized');
  }
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

async function refresh() {
  const [summary, sessions, incidents] = await Promise.all([
    fetchJson('/api/continuity/summary'),
    fetchJson('/api/continuity/sessions'),
    fetchJson('/api/continuity/incidents'),
  ]);
  document.getElementById('summary-json').textContent = JSON.stringify(summary, null, 2);
  document.getElementById('sessions-json').textContent = JSON.stringify(sessions, null, 2);
  document.getElementById('incidents-json').textContent = JSON.stringify(incidents, null, 2);
}

refreshButton.addEventListener('click', () => {
  refresh().catch((error) => {
    document.getElementById('summary-json').textContent = error.message;
  });
});

refresh().catch((error) => {
  document.getElementById('summary-json').textContent = error.message;
});
