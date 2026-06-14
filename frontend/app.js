const state = {
  activeTab: 'docs',
  status: null,
  plan: [],
  tree: null,
  artifacts: [],
};

const docs = [
  'source.md',
  'competition.json',
  'task.md',
  'calibration.md',
  'strategy.md',
  'evaluation.json',
  'results_summary.md',
];

const stepMap = {
  intake: 'intake',
  strategy: 'strategy',
  decompose: 'decompose',
  execute: 'execute',
  verify: 'verify',
  evaluate: 'evaluate',
  report: 'report',
};

const el = (id) => document.getElementById(id);

function api(path, options) {
  return fetch(path, options).then(async (res) => {
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch {
        // keep fallback
      }
      throw new Error(detail);
    }
    return res.json();
  });
}

function appendLog(event) {
  const log = el('log');
  const row = document.createElement('div');
  row.className = `log-entry ${event.status || ''}`;
  const title = [
    event.type || event.stage || 'event',
    event.phase ? `/${event.phase}` : '',
    event.task_id ? ` task ${event.task_id}` : '',
    event.status ? ` ${event.status}` : '',
  ].join('');
  const meta = document.createElement('div');
  meta.className = 'meta';
  meta.textContent = new Date().toLocaleTimeString() + '  ' + title;
  row.appendChild(meta);

  const text = document.createElement('div');
  text.textContent = event.error || event.message || JSON.stringify(stripLarge(event), null, 2);
  row.appendChild(text);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function stripLarge(event) {
  const clone = { ...event };
  delete clone.task;
  delete clone.verification;
  return clone;
}

function updateSteps(event) {
  const key = event.phase || event.stage;
  const step = stepMap[key];
  if (!step) return;
  const node = document.querySelector(`[data-step="${step}"]`);
  if (!node) return;
  node.classList.remove('active', 'done', 'failed');
  if (event.status === 'running') node.classList.add('active');
  if (event.status === 'completed') node.classList.add('done');
  if (event.status === 'failed') node.classList.add('failed');
}

async function refreshStatus() {
  try {
    const runtime = await api('/api/runtime/status');
    const pill = el('runtime-pill');
    pill.textContent = runtime.connected
      ? `${runtime.sandbox_provider || 'local'}: connected`
      : `runtime: ${runtime.error || 'offline'}`;
    pill.className = `pill ${runtime.connected ? 'ok' : 'bad'}`;
  } catch {
    el('runtime-pill').textContent = 'runtime: offline';
    el('runtime-pill').className = 'pill bad';
  }

  try {
    state.status = await api('/api/pipeline/status');
    renderSummary();
  } catch {
    // no active server state yet
  }
}

async function refreshSession() {
  await refreshStatus();
  try {
    state.plan = await api('/api/session/plan/list');
  } catch {
    state.plan = [];
  }
  try {
    state.tree = await api('/api/session/plan/tree');
  } catch {
    state.tree = null;
  }
  try {
    state.artifacts = await api('/api/session/artifacts');
  } catch {
    state.artifacts = [];
  }
  renderTab();
}

function renderSummary() {
  const box = el('summary');
  const s = state.status;
  if (!s || !s.session_id) {
    box.textContent = 'No active session.';
    return;
  }
  el('session-label').textContent = s.session_id;
  const stageText = (s.stages || []).map((stage) => `${stage.name}: ${stage.state}`).join(' | ');
  box.textContent = `${s.running ? 'Running' : 'Idle'} · ${s.session_id} · ${stageText}`;
}

function renderTab() {
  const box = el('tab-content');
  box.textContent = '';
  if (state.activeTab === 'docs') renderDocs(box);
  if (state.activeTab === 'plan') renderPlan(box);
  if (state.activeTab === 'tasks') renderTasks(box);
  if (state.activeTab === 'artifacts') renderArtifacts(box);
}

function renderDocs(box) {
  for (const name of docs) {
    const item = itemNode(name, 'Open document');
    item.onclick = () => openDocument(name);
    box.appendChild(item);
  }
}

function renderPlan(box) {
  if (!state.plan.length) {
    box.textContent = 'No plan yet.';
    return;
  }
  for (const task of state.plan) {
    const item = itemNode(`[${task.id}] ${task.title || 'Task'}`, task.description || '');
    item.onclick = () => openText(`Task ${task.id}`, 'json', JSON.stringify(task, null, 2));
    box.appendChild(item);
  }
}

function renderTasks(box) {
  if (!state.plan.length) {
    box.textContent = 'No tasks yet.';
    return;
  }
  for (const task of state.plan) {
    const item = itemNode(`[${task.id}] ${task.title || 'Task'}`, task.artifact || '');
    item.onclick = () => openTask(task.id);
    box.appendChild(item);
  }
}

function renderArtifacts(box) {
  if (!state.artifacts.length) {
    box.textContent = 'No artifacts yet.';
    return;
  }
  for (const artifact of state.artifacts) {
    const item = itemNode(artifact.path, `${artifact.size_bytes} bytes`);
    item.onclick = () => window.open(`/api/session/artifacts/${artifact.path.replace(/^artifacts\//, '')}`, '_blank');
    box.appendChild(item);
  }
}

function itemNode(title, subtitle) {
  const item = document.createElement('div');
  item.className = 'item';
  item.textContent = title;
  const small = document.createElement('small');
  small.textContent = subtitle || '';
  item.appendChild(small);
  return item;
}

async function openDocument(name) {
  const data = await api(`/api/session/documents/${encodeURIComponent(name)}`);
  openText(name, name.endsWith('.json') ? 'json' : 'markdown', data.content);
}

async function openTask(taskId) {
  const data = await api(`/api/session/tasks/${encodeURIComponent(taskId)}`);
  openText(`Task ${taskId}`, 'markdown', data.content);
}

function openText(title, kind, content) {
  el('viewer-title').textContent = title;
  const body = el('viewer-body');
  if (kind === 'markdown' && window.marked) {
    body.innerHTML = marked.parse(content || '');
  } else {
    const pre = document.createElement('pre');
    pre.textContent = content || '';
    body.textContent = '';
    body.appendChild(pre);
  }
  el('viewer').showModal();
}

function connectSSE() {
  const source = new EventSource('/api/events');
  source.onmessage = async (event) => {
    const data = JSON.parse(event.data);
    appendLog(data);
    updateSteps(data);
    if (data.status === 'completed' || data.type === 'pipeline.completed') {
      await refreshSession();
    }
    if (data.type === 'pipeline.completed' || data.type === 'pipeline.failed') {
      el('start-btn').disabled = false;
    }
  };
  source.onerror = () => {
    appendLog({ type: 'sse', status: 'failed', message: 'SSE disconnected; browser will retry.' });
  };
}

async function startPipeline(event) {
  event.preventDefault();
  const input = el('source-input').value.trim();
  if (!input) return;
  el('start-btn').disabled = true;
  try {
    await api('/api/pipeline/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input }),
    });
    appendLog({ type: 'ui', status: 'completed', message: 'Pipeline started.' });
  } catch (error) {
    appendLog({ type: 'ui', status: 'failed', message: error.message });
    el('start-btn').disabled = false;
  }
}

function initTabs() {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((node) => node.classList.remove('active'));
      tab.classList.add('active');
      state.activeTab = tab.dataset.tab;
      renderTab();
    });
  }
}

el('input-bar').addEventListener('submit', startPipeline);
el('refresh-btn').addEventListener('click', refreshSession);
el('viewer-close').addEventListener('click', () => el('viewer').close());

initTabs();
connectSSE();
refreshSession();
setInterval(refreshStatus, 15000);
