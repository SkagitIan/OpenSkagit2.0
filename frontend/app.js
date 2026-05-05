const API_BASE = window.ENV_API_BASE || '';
const history = [];

function getApiKey() {
  return localStorage.getItem('civic_api_key') || '';
}

async function apiFetch(path, options = {}) {
  return fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': getApiKey(),
      ...(options.headers || {})
    }
  });
}

async function ask(question, notifyConfig) {
  const payload = { question, context: { county: 'skagit', state: 'wa' } };
  if (notifyConfig) payload.notify = notifyConfig;
  const initial = await apiFetch('/ask', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  if (!initial.ok) throw new Error(`Request failed: ${initial.status}`);
  const response = await initial.json();
  if (response.status === 'complete' || response.status === 'error') return response;
  const job = await pollJob(response.job_id);
  return job.result || response;
}

async function pollJob(jobId, maxAttempts = 20, intervalMs = 1000) {
  for (let i = 0; i < maxAttempts; i++) {
    const response = await apiFetch(`/job/${jobId}`);
    const data = await response.json();
    if (data.status === 'complete' || data.status === 'error') {
      return data;
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }
  throw new Error('Job timed out');
}

function renderConversation(items) {
  const root = document.getElementById('history');
  root.innerHTML = '';
  items.forEach(item => {
    const question = document.createElement('div');
    question.className = 'bubble user';
    question.textContent = item.question;
    root.appendChild(question);
    if (item.answer) {
      const answer = document.createElement('div');
      answer.className = 'bubble agent';
      answer.textContent = item.answer;
      root.appendChild(answer);
    }
  });
  root.scrollTop = root.scrollHeight;
}

function renderCaseFile(response, notifyConfigured = false) {
  const root = document.getElementById('case-content');
  if (!response) {
    root.className = 'empty-state';
    root.textContent = 'No case file loaded.';
    return;
  }
  const entity = detectEntity(response);
  root.className = 'case-content';
  root.innerHTML = `
    <div class="case-head">
      <div>
        <span class="label">Entity</span>
        <strong>${escapeHtml(entity || 'Unknown')}</strong>
      </div>
      <div class="case-actions">
        ${showConfidence(response.confidence || 'low')}
      </div>
    </div>
    <section>
      <h2>Evidence</h2>
      <div class="evidence-list"></div>
    </section>
    <section>
      <h2>Missing</h2>
      <ul class="missing-list"></ul>
    </section>
    <section>
      <h2>Sources</h2>
      <div class="sources">${(response.sources_queried || []).map(escapeHtml).join(', ') || 'None'}</div>
    </section>
  `;
  const actions = root.querySelector('.case-actions');
  if (response.case_file_id || response.id) {
    const caseFileId = response.case_file_id || response.id;
    actions.appendChild(renderShareButton(caseFileId));
    const exportButton = document.createElement('button');
    exportButton.type = 'button';
    exportButton.className = 'secondary-action';
    exportButton.textContent = 'Export';
    exportButton.onclick = () => exportCaseFile(caseFileId);
    actions.appendChild(exportButton);
  }
  if (notifyConfigured) {
    const notifyStatus = document.createElement('span');
    notifyStatus.className = 'notify-status';
    notifyStatus.textContent = 'Notification sent';
    actions.appendChild(notifyStatus);
  }
  const evidenceList = root.querySelector('.evidence-list');
  (response.evidence || []).forEach(item => evidenceList.appendChild(renderEvidenceCard(item)));
  if (!response.evidence || response.evidence.length === 0) {
    evidenceList.innerHTML = '<div class="empty-state">No evidence returned.</div>';
  }
  const missing = root.querySelector('.missing-list');
  (response.missing || []).forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    missing.appendChild(li);
  });
  if (!response.missing || response.missing.length === 0) {
    missing.innerHTML = '<li class="muted">No named gaps.</li>';
  }
}

function renderShareButton(caseFileId) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'secondary-action';
  btn.textContent = 'Copy link';
  btn.onclick = async () => {
    await navigator.clipboard.writeText(`${API_BASE}/case/${caseFileId}`);
    btn.textContent = 'Link copied';
    setTimeout(() => { btn.textContent = 'Copy link'; }, 2000);
  };
  return btn;
}

async function exportCaseFile(caseFileId) {
  const response = await apiFetch(`/export/${caseFileId}?format=markdown`);
  const text = await response.text();
  const blob = new Blob([text], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `case-${caseFileId}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

async function loadHistory() {
  if (!getApiKey()) {
    renderSavedCases([]);
    return;
  }
  try {
    const response = await apiFetch('/cases?limit=10');
    const data = await response.json();
    renderSavedCases(data.cases || []);
  } catch (error) {
    renderSavedCases([]);
  }
}

function buildNotifyConfig() {
  const email = document.getElementById('notify-email').value.trim();
  const webhook = document.getElementById('notify-webhook').value.trim();

  if (!email && !webhook) return null;

  const config = {};
  if (email) config.email = email;
  if (webhook) config.webhook = webhook;

  const confidence = [];
  if (document.getElementById('conf-high').checked) confidence.push('high');
  if (document.getElementById('conf-medium').checked) confidence.push('medium');
  if (document.getElementById('conf-low').checked) confidence.push('low');
  if (confidence.length > 0 && confidence.length < 3) {
    config.on_confidence = confidence;
  }

  return config;
}

function renderSavedCases(cases) {
  const root = document.getElementById('case-history-list');
  root.innerHTML = '';
  if (!cases.length) {
    root.innerHTML = '<div class="muted">No saved cases.</div>';
    return;
  }
  cases.forEach(item => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'history-case';
    button.innerHTML = `
      <span>${escapeHtml(truncate(item.question || '', 60))}</span>
      ${showConfidence(item.confidence || 'low')}
    `;
    button.onclick = async () => {
      const response = await apiFetch(`/case/${item.id}`);
      renderCaseFile(await response.json());
    };
    root.appendChild(button);
  });
}

function checkAuth() {
  if (!getApiKey()) {
    showApiKeyModal();
    return;
  }
  checkAdminAccess();
}

function showApiKeyModal() {
  document.getElementById('api-key-input').value = getApiKey();
  document.getElementById('api-key-modal').classList.remove('hidden');
}

function hideApiKeyModal() {
  document.getElementById('api-key-modal').classList.add('hidden');
}

async function loadTenantConfig() {
  try {
    const response = await fetch(`${API_BASE}/config`);
    if (!response.ok) return;
    const tenant = await response.json();
    document.title = tenant.display_name || 'Civic Intelligence';
    document.getElementById('tenant-title').textContent = tenant.display_name || 'Civic Intelligence';
    document.getElementById('tenant-tagline').textContent = tenant.tagline || '';
    if (tenant.primary_color) {
      document.documentElement.style.setProperty('--brand', tenant.primary_color);
    }
  } catch (error) {
    return;
  }
}

async function checkAdminAccess() {
  try {
    const response = await apiFetch('/admin/stats');
    document.getElementById('admin-link').classList.toggle('hidden', !response.ok);
  } catch (error) {
    document.getElementById('admin-link').classList.add('hidden');
  }
}

async function showAdminPanel() {
  document.querySelector('.panels').classList.add('admin-mode');
  document.getElementById('conversation').classList.remove('active-mobile');
  document.getElementById('case-file').classList.remove('active-mobile');
  document.getElementById('admin-panel').classList.add('active-mobile');
  document.getElementById('main-link').classList.remove('hidden');
  document.querySelectorAll('.tab').forEach(item => item.classList.remove('active'));
  await loadAdminPanel();
}

function showWorkspace() {
  document.querySelector('.panels').classList.remove('admin-mode');
  document.getElementById('admin-panel').classList.remove('active-mobile');
  document.getElementById('conversation').classList.add('active-mobile');
  document.getElementById('main-link').classList.add('hidden');
}

async function loadAdminPanel() {
  const root = document.getElementById('admin-content');
  root.innerHTML = '<div class="loading"><span class="spinner"></span><span>Loading admin data...</span></div>';
  try {
    const [statsResponse, sourcesResponse, auditResponse, queriesResponse] = await Promise.all([
      apiFetch('/admin/stats'),
      apiFetch('/admin/sources'),
      apiFetch('/admin/audit?limit=25'),
      apiFetch('/admin/queries?limit=25')
    ]);
    if (!statsResponse.ok || !sourcesResponse.ok || !auditResponse.ok || !queriesResponse.ok) {
      throw new Error('Admin access failed');
    }
    const stats = await statsResponse.json();
    const sources = await sourcesResponse.json();
    const audit = await auditResponse.json();
    const queries = await queriesResponse.json();
    root.innerHTML = `
      <section>
        <h2>Query Stats</h2>
        <div class="metric-grid">
          <div><span>Total queries</span><strong>${stats.total_queries}</strong></div>
          <div><span>High</span><strong>${stats.by_confidence.high || 0}</strong></div>
          <div><span>Medium</span><strong>${stats.by_confidence.medium || 0}</strong></div>
          <div><span>Low</span><strong>${stats.by_confidence.low || 0}</strong></div>
          <div><span>Avg response</span><strong>${stats.avg_duration_ms} ms</strong></div>
        </div>
        <div class="admin-list">${(stats.top_entities || []).map(item => `<span>${escapeHtml(item.entity)} (${item.count})</span>`).join('') || '<span>No entities yet</span>'}</div>
      </section>
      <section>
        <h2>Source Health</h2>
        ${renderTable(['Source', 'Type', 'Queries', 'Last used'], (sources.sources || []).map(item => [
          item.name, item.type, item.query_count, item.last_used || 'Never'
        ]))}
      </section>
      <section>
        <h2>Recent Audit Log</h2>
        ${renderTable(['Time', 'Entity', 'Question', 'Confidence', 'Duration'], (audit.entries || []).map(item => [
          item.created_at, item.entity || '', truncate(item.question || '', 90), item.confidence || '', `${item.duration_ms || 0} ms`
        ]))}
      </section>
      <section>
        <h2>Query Diagnostics</h2>
        <div id="query-diagnostics"></div>
      </section>
    `;
    renderQueryDiagnostics(queries.queries || []);
  } catch (error) {
    root.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
  }
}

function renderQueryDiagnostics(queries) {
  const root = document.getElementById('query-diagnostics');
  if (!root) return;
  if (!queries.length) {
    root.innerHTML = '<div class="empty-state">No query attempts logged.</div>';
    return;
  }
  root.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Source</th>
            <th>Domain</th>
            <th>Status</th>
            <th>Count</th>
            <th>Duration</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          ${queries.map(item => `
            <tr class="query-row" data-query-id="${escapeHtml(item.id)}">
              <td>${escapeHtml(item.created_at || '')}</td>
              <td>${escapeHtml(item.source_name || item.source_id || '')}</td>
              <td>${escapeHtml(item.domain || '')}</td>
              <td>${escapeHtml(item.status || '')}</td>
              <td>${escapeHtml(String(item.count ?? 0))}</td>
              <td>${escapeHtml(String(item.duration_ms ?? 0))} ms</td>
              <td>${escapeHtml(truncate(item.error || '', 90))}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
    <div id="query-detail" class="query-detail empty-state">Select a query row to inspect params, URLs, raw excerpt, and result preview.</div>
  `;
  root.querySelectorAll('.query-row').forEach(row => {
    row.addEventListener('click', () => loadQueryDetail(row.dataset.queryId));
  });
}

async function loadQueryDetail(queryId) {
  const detail = document.getElementById('query-detail');
  if (!detail) return;
  detail.className = 'query-detail loading';
  detail.innerHTML = '<span class="spinner"></span><span>Loading query detail...</span>';
  try {
    const response = await apiFetch(`/admin/queries/${queryId}`);
    if (!response.ok) throw new Error(`Query detail failed: ${response.status}`);
    const item = await response.json();
    detail.className = 'query-detail';
    detail.innerHTML = `
      <h3>${escapeHtml(item.source_name || item.source_id || 'Query')}</h3>
      <div class="fields">
        <div class="field"><span>Status</span><strong>${escapeHtml(item.status || '')}</strong></div>
        <div class="field"><span>Count</span><strong>${escapeHtml(String(item.count ?? 0))}</strong></div>
        <div class="field"><span>Duration</span><strong>${escapeHtml(String(item.duration_ms ?? 0))} ms</strong></div>
        <div class="field"><span>URL</span><strong>${escapeHtml(item.source_url || '')}</strong></div>
      </div>
      <details open>
        <summary>Error</summary>
        <pre>${escapeHtml(item.error || 'No error recorded.')}</pre>
      </details>
      <details>
        <summary>Query params</summary>
        <pre>${escapeHtml(JSON.stringify(item.query_params || {}, null, 2))}</pre>
      </details>
      <details>
        <summary>Source URLs</summary>
        <pre>${escapeHtml(JSON.stringify(item.source_urls || [], null, 2))}</pre>
      </details>
      <details>
        <summary>Raw excerpt</summary>
        <pre>${escapeHtml(item.raw_excerpt || '')}</pre>
      </details>
      <details>
        <summary>Result preview</summary>
        <pre>${escapeHtml(JSON.stringify(item.result || {}, null, 2))}</pre>
      </details>
    `;
  } catch (error) {
    detail.className = 'query-detail empty-state';
    detail.textContent = error.message;
  }
}

function renderTable(headers, rows) {
  if (!rows.length) return '<div class="empty-state">No records.</div>';
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map(item => `<th>${escapeHtml(item)}</th>`).join('')}</tr></thead>
        <tbody>
          ${rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(String(cell ?? ''))}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderEvidenceCard(item) {
  const card = document.createElement('article');
  card.className = 'evidence-card';
  const rows = displayEntries(item).map(([key, value]) => `
    <div class="field"><span>${escapeHtml(key)}</span><strong>${escapeHtml(String(value ?? ''))}</strong></div>
  `).join('');
  card.innerHTML = `
    <h3>${escapeHtml(item.source_name)}</h3>
    <div class="fields">${rows}</div>
    <details>
      <summary>Raw data</summary>
      <pre>${escapeHtml(JSON.stringify(item.data || {}, null, 2))}</pre>
    </details>
  `;
  return card;
}

function displayEntries(item) {
  const data = item.data || {};
  if (item.source_id === 'skagit_zoning') {
    return pickEntries(data, ['ZONING_LABEL', 'ZONING_CODE', 'LUD_ZONING', 'LUD', 'FEAT_TYPE', 'FEDERAL', 'OBJECTID']);
  }
  if (item.source_id === 'skagit_parcels') {
    return pickEntries(data, ['PARCELID', 'OwnerName', 'Acres', 'LandUse', 'AssessedValue', 'TaxableValue', 'TotalTaxes', 'TaxYear']);
  }
  return Object.entries(data).slice(0, 8);
}

function pickEntries(data, keys) {
  const picked = [];
  keys.forEach(key => {
    if (Object.prototype.hasOwnProperty.call(data, key)) picked.push([key, data[key]]);
  });
  return picked.length ? picked : Object.entries(data).slice(0, 8);
}

function showConfidence(level) {
  const normalized = ['high', 'medium', 'low'].includes(level) ? level : 'low';
  return `<span class="confidence ${normalized}">${normalized}</span>`;
}

function showLoading() {
  const root = document.getElementById('case-content');
  root.className = 'loading';
  root.innerHTML = '<span class="spinner"></span><span>Gathering evidence...</span>';
}

function detectEntity(response) {
  for (const item of response.evidence || []) {
    if (item.data?.PARCELID) return item.data.PARCELID;
    if (item.data?.ParcelID) return item.data.ParcelID;
  }
  const match = response.question.match(/\bP\d+\b/i);
  return match ? match[0].toUpperCase() : '';
}

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

function truncate(value, maxLength) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

document.getElementById('ask-form').addEventListener('submit', async event => {
  event.preventDefault();
  const input = document.getElementById('question');
  const question = input.value.trim();
  if (!question) return;
  const notifyConfig = buildNotifyConfig();
  history.push({ question, answer: '' });
  renderConversation(history);
  showLoading();
  try {
    const response = await ask(question, notifyConfig);
    history[history.length - 1].answer = response.answer || response.error || 'No answer returned.';
    renderConversation(history);
    renderCaseFile(response, Boolean(notifyConfig));
    loadHistory();
  } catch (error) {
    history[history.length - 1].answer = error.message;
    renderConversation(history);
    renderCaseFile({ question, confidence: 'low', evidence: [], missing: [error.message], sources_queried: [] });
  }
});

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelector('.panels').classList.remove('admin-mode');
    document.getElementById('admin-panel').classList.remove('active-mobile');
    document.getElementById('main-link').classList.add('hidden');
    document.querySelectorAll('.tab').forEach(item => item.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.panel').forEach(panel => panel.classList.remove('active-mobile'));
    document.getElementById(tab.dataset.panel).classList.add('active-mobile');
  });
});

document.getElementById('api-key-form').addEventListener('submit', event => {
  event.preventDefault();
  localStorage.setItem('civic_api_key', document.getElementById('api-key-input').value.trim());
  hideApiKeyModal();
  checkAdminAccess();
  loadHistory();
});

document.getElementById('change-key').addEventListener('click', showApiKeyModal);
document.getElementById('admin-link').addEventListener('click', showAdminPanel);
document.getElementById('main-link').addEventListener('click', showWorkspace);

document.getElementById('conversation').classList.add('active-mobile');
loadTenantConfig();
checkAuth();
loadHistory();
