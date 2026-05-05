const API_BASE = window.ENV_API_BASE || 'http://localhost:8000';
const history = [];

async function ask(question, notifyConfig) {
  const payload = { question, context: { county: 'skagit', state: 'wa' } };
  if (notifyConfig) payload.notify = notifyConfig;
  const initial = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
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
    const response = await fetch(`${API_BASE}/job/${jobId}`);
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
  const response = await fetch(`${API_BASE}/export/${caseFileId}?format=markdown`);
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
  try {
    const response = await fetch(`${API_BASE}/cases?limit=10`);
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
      const response = await fetch(`${API_BASE}/case/${item.id}`);
      renderCaseFile(await response.json());
    };
    root.appendChild(button);
  });
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
    document.querySelectorAll('.tab').forEach(item => item.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.panel').forEach(panel => panel.classList.remove('active-mobile'));
    document.getElementById(tab.dataset.panel).classList.add('active-mobile');
  });
});

document.getElementById('conversation').classList.add('active-mobile');
loadHistory();
