const state = {
  activeTab: 'docs',
  status: null,
  plan: [],
  tree: null,
  artifacts: [],
  documents: {},
  files: [],
  taskRuns: [],
  liveTaskRuns: {},
  stages: {},
  agents: {},
};

const stageOrder = ['intake', 'research', 'report'];
const agentOrder = ['calibrate', 'strategy', 'decompose', 'execute', 'verify', 'evaluate', 'collect', 'writer', 'reviewer', 'polish'];

const stageLabels = {
  intake: 'Intake',
  research: 'Research',
  report: 'Report',
};

const agentLabels = {
  calibrate: 'Calibrate',
  strategy: 'Strategy',
  decompose: 'Decompose',
  execute: 'Execute',
  verify: 'Verify',
  evaluate: 'Evaluate',
  collect: 'Collect',
  writer: 'Writer',
  reviewer: 'Reviewer',
  polish: 'Polish',
};

const agentStage = {
  calibrate: 'intake',
  strategy: 'research',
  decompose: 'research',
  execute: 'research',
  verify: 'research',
  evaluate: 'research',
  collect: 'report',
  writer: 'report',
  reviewer: 'report',
  polish: 'report',
};

const docs = [
  'source.md',
  'competition.json',
  'task.md',
  'calibration.md',
  'strategy.md',
  'evaluation.json',
  'results_summary.md',
  'report_context.md',
  'paper.md',
  'report_review.json',
  'paper_polished.md',
];

const stepMap = {
  intake: 'intake',
  calibrate: 'intake',
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

function resetRunState() {
  state.stages = Object.fromEntries(stageOrder.map((name) => [
    name,
    { name, state: 'pending', detail: '' },
  ]));
  state.agents = Object.fromEntries(agentOrder.map((name) => [
    name,
    { name, state: 'pending', detail: '', taskId: '' },
  ]));
  document.querySelectorAll('[data-step]').forEach((node) => {
    node.classList.remove('active', 'done', 'failed');
  });
  renderRunState();
}

function clearSessionView() {
  state.status = null;
  state.plan = [];
  state.tree = null;
  state.artifacts = [];
  state.documents = {};
  state.files = [];
  state.taskRuns = [];
  state.liveTaskRuns = {};
  el('session-label').textContent = '';
  el('summary').textContent = 'Starting new session.';
  renderTab();
}

function syncStageStatus(stages) {
  if (!Array.isArray(stages)) return;
  for (const stage of stages) {
    if (!stage.name || !state.stages[stage.name]) continue;
    state.stages[stage.name] = {
      ...state.stages[stage.name],
      state: stage.state || state.stages[stage.name].state,
      detail: stage.error || '',
    };
  }
  renderRunState();
}

function updateRunState(event) {
  if (event.type === 'pipeline.started') {
    resetRunState();
    return;
  }

  if (event.type === 'pipeline.completed') {
    for (const name of stageOrder) {
      if (state.stages[name]?.state !== 'failed') {
        state.stages[name].state = 'completed';
      }
    }
    renderRunState();
    return;
  }

  if (event.type === 'pipeline.failed') {
    const active = stageOrder.find((name) => state.stages[name]?.state === 'running');
    if (active) {
      state.stages[active].state = 'failed';
      state.stages[active].detail = event.error || '';
    }
    renderRunState();
    return;
  }

  if (event.stage && !event.phase && state.stages[event.stage]) {
    state.stages[event.stage] = {
      ...state.stages[event.stage],
      state: normalizeStatus(event.status),
      detail: event.error || '',
    };
  }

  if (event.phase) {
    updateTaskRunEvent(event);
    const agentName = event.phase;
    if (agentName === 'kaggle') {
      renderRunState();
      return;
    }
    if (!state.agents[agentName]) {
      state.agents[agentName] = { name: agentName, state: 'pending', detail: '', taskId: '' };
      if (!agentOrder.includes(agentName)) agentOrder.push(agentName);
    }
    state.agents[agentName] = {
      ...state.agents[agentName],
      state: normalizeStatus(event.status),
      detail: agentDetail(event),
      taskId: event.task_id || state.agents[agentName].taskId || '',
    };

    const parentStage = agentStage[agentName] || event.stage;
    if (parentStage && state.stages[parentStage] && state.stages[parentStage].state === 'pending') {
      state.stages[parentStage].state = 'running';
    }
  }

  renderRunState();
}

function updateTaskRunEvent(event) {
  if (!event.task_id && !event.task_ids?.length) return;
  const taskIds = event.task_ids?.length ? event.task_ids : [event.task_id];
  for (const taskId of taskIds) {
    if (!taskId) continue;
    const current = state.liveTaskRuns[taskId] || {};
    const next = { ...current, task_id: taskId };
    if (event.batch) next.batch = event.batch;
    if (event.attempt) next.current_attempt = event.attempt;
    if (event.max_attempts) next.max_attempts = event.max_attempts;
    if (event.phase) next.phase = event.phase;
    if (event.status) next.event_status = event.status;
    if (event.workspace) next.workspace = event.workspace;
    if (event.review) next.review = event.review;
    if (event.verification) next.verification = event.verification;
    if (event.child_ids) next.redecompose_children = event.child_ids;
    if (event.status === 'retrying') next.retrying = true;
    if (event.status === 'redecomposing' || event.status === 'redecomposed') next.recompose = true;
    state.liveTaskRuns[taskId] = next;
  }
  if (state.activeTab === 'tasks') renderTab();
}

function normalizeStatus(status) {
  if (status === 'batch_running' || status === 'retrying' || status === 'redecomposing') return 'running';
  if (status === 'batch_completed' || status === 'redecomposed') return 'completed';
  return status || 'pending';
}

function agentDetail(event) {
  const parts = [];
  if (event.status === 'batch_running' || event.status === 'batch_completed') {
    parts.push(`batch ${event.batch}`);
  }
  if (event.task_id) parts.push(`task ${event.task_id}`);
  if (event.task_ids?.length) parts.push(`tasks ${event.task_ids.join(', ')}`);
  if (event.attempt) {
    const max = event.max_attempts ? `/${event.max_attempts}` : '';
    parts.push(`attempt ${event.attempt}${max}`);
  }
  if (event.status === 'redecomposing') parts.push('redecompose');
  if (event.child_ids?.length) parts.push(`children ${event.child_ids.join(', ')}`);
  if (event.error) parts.push(event.error);
  return parts.join(' / ');
}

function renderRunState() {
  renderStatusList(el('stage-status-list'), stageOrder, state.stages, stageLabels);
  renderStatusList(el('agent-status-list'), agentOrder, state.agents, agentLabels);
}

function renderStatusList(container, order, source, labels) {
  if (!container) return;
  container.textContent = '';
  for (const name of order) {
    const item = source[name] || { name, state: 'pending', detail: '' };
    const normalized = normalizeStatus(item.state);
    const row = document.createElement('div');
    row.className = `status-node ${normalized}`;

    const dot = document.createElement('span');
    dot.className = 'status-dot';
    row.appendChild(dot);

    const body = document.createElement('div');
    body.className = 'status-body';

    const title = document.createElement('div');
    title.className = 'status-name';
    title.textContent = labels[name] || name;
    body.appendChild(title);

    const detail = document.createElement('small');
    detail.textContent = item.detail || normalized;
    body.appendChild(detail);
    row.appendChild(body);

    const badge = document.createElement('span');
    badge.className = 'status-badge';
    badge.textContent = normalized;
    row.appendChild(badge);

    container.appendChild(row);
  }
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
      ? `${runtime.runtime || 'runtime'} / ${runtime.sandbox_provider || 'local'}`
      : `${runtime.runtime || 'runtime'}: ${runtime.error || 'offline'}`;
    pill.className = `pill ${runtime.connected && runtime.runtime !== 'mock' ? 'ok' : 'bad'}`;
  } catch {
    el('runtime-pill').textContent = 'runtime: offline';
    el('runtime-pill').className = 'pill bad';
  }

  try {
    state.status = await api('/api/pipeline/status');
    syncStageStatus(state.status.stages);
    renderSummary();
  } catch {
    // no active server state yet
  }
}

async function refreshSession() {
  await refreshStatus();
  try {
    const documents = await api('/api/session/documents');
    state.documents = Object.fromEntries(documents.map((doc) => [doc.name, doc]));
  } catch {
    state.documents = {};
  }
  try {
    state.files = await api('/api/session/files');
  } catch {
    state.files = [];
  }
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
  try {
    state.taskRuns = await api('/api/session/task-runs');
  } catch {
    state.taskRuns = [];
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
  box.textContent = `${s.running ? 'Running' : 'Idle'} / ${s.session_id} / ${stageText}`;
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
  if (!state.files.length) {
    for (const name of docs) {
      const doc = state.documents[name] || { exists: false, size_bytes: 0 };
      const subtitle = doc.exists ? `${doc.size_bytes} bytes` : 'Not generated yet';
      const item = itemNode(name, subtitle, { exists: doc.exists });
      item.onclick = () => openDocument(name);
      box.appendChild(item);
    }
    return;
  }
  box.appendChild(fileTreeNode(buildFileTree(state.files)));
}

function renderPlan(box) {
  if (!state.plan.length) {
    box.textContent = 'No plan yet.';
    return;
  }
  for (const task of state.plan) {
    const item = itemNode(`[${task.id}] ${task.title || 'Task'}`, task.description || '', {
      exists: task.status === 'completed',
      failed: task.status === 'failed',
    });
    item.onclick = () => openText(`Task ${task.id}`, 'json', JSON.stringify(task, null, 2));
    box.appendChild(item);
  }
}

function renderTasks(box) {
  const runs = state.taskRuns.length ? state.taskRuns : state.plan.map(fallbackTaskRun);
  if (!runs.length) {
    box.textContent = 'No tasks yet.';
    return;
  }
  for (const run of runs) {
    box.appendChild(taskNode(run));
  }
}

function renderArtifacts(box) {
  if (!state.artifacts.length) {
    box.textContent = 'No artifacts yet.';
    return;
  }
  for (const artifact of state.artifacts) {
    const item = itemNode(artifact.path, `${artifact.size_bytes} bytes`, { exists: true });
    item.onclick = () => openFile(artifact.path);
    box.appendChild(item);
  }
}

function fallbackTaskRun(task) {
  const safe = safeId(task.id);
  return {
    task_id: String(task.id),
    safe_id: safe,
    title: task.title || 'Task',
    description: task.description || '',
    status: task.status || 'pending',
    dependencies: task.dependencies || [],
    parent: task.parent || '',
    artifact: task.artifact || '',
    workspace: '',
    attempt_count: 0,
    verification: {},
    redecompose_children: [],
    files: {
      output: fileExists(`tasks/${safe}.md`) ? `tasks/${safe}.md` : '',
      output_attempts: state.files.filter((file) => file.path.startsWith(`tasks/${safe}.attempt_`)),
      verification: fileExists(`verifications/${safe}.json`) ? `verifications/${safe}.json` : '',
      verification_attempts: state.files.filter((file) => file.path.startsWith(`verifications/${safe}.attempt_`)),
      artifacts: state.files.filter((file) => file.path.startsWith(`artifacts/${safe}/`)),
      expected_artifact: task.artifact || '',
    },
  };
}

function taskNode(run) {
  const live = state.liveTaskRuns[run.task_id] || {};
  const safe = run.safe_id || safeId(run.task_id);
  const files = state.files || [];
  const runFiles = run.files || {};
  const outputPath = runFiles.output || `tasks/${safe}.md`;
  const verificationPath = runFiles.verification || `verifications/${safe}.json`;
  const outputAttempts = runFiles.output_attempts || files.filter((file) => file.path.startsWith(`tasks/${safe}.attempt_`));
  const verificationAttempts = runFiles.verification_attempts || files.filter((file) => file.path.startsWith(`verifications/${safe}.attempt_`));
  const artifacts = runFiles.artifacts || files.filter((file) => file.path.startsWith(`artifacts/${safe}/`));
  const verification = live.verification || run.verification || {};
  const liveStatus = normalizeStatus(live.event_status);
  const status = liveStatus === 'running' ? 'running' : run.status;
  const phase = live.phase || (verification.pass !== undefined ? 'verify' : 'execute');
  const attemptCount = Math.max(
    Number(run.attempt_count || 0),
    outputAttempts.length,
    verificationAttempts.length,
    Number(live.current_attempt || 0),
  );
  const maxAttempts = live.max_attempts || '';
  const children = live.redecompose_children || run.redecompose_children || [];

  const card = document.createElement('div');
  card.className = `task-card ${status === 'completed' ? 'exists' : ''} ${status === 'failed' ? 'failed' : ''} ${status === 'running' ? 'running' : ''}`;

  const header = document.createElement('div');
  header.className = 'task-card-head';
  const title = document.createElement('div');
  title.className = 'task-card-title';
  title.textContent = `[${run.task_id}] ${run.title || 'Task'}`;
  header.appendChild(title);

  const badge = document.createElement('span');
  badge.className = 'task-card-badge';
  badge.textContent = status || 'pending';
  header.appendChild(badge);
  card.appendChild(header);

  const desc = document.createElement('div');
  desc.className = 'task-card-desc';
  desc.textContent = run.description || run.artifact || '';
  card.appendChild(desc);

  const meta = document.createElement('div');
  meta.className = 'task-run-meta';
  meta.appendChild(metaPill('phase', phase));
  meta.appendChild(metaPill('batch', live.batch || '-'));
  meta.appendChild(metaPill('attempts', maxAttempts ? `${attemptCount}/${maxAttempts}` : String(attemptCount || 0)));
  meta.appendChild(metaPill('verify', verifyLabel(verification)));
  if (live.workspace || run.workspace) meta.appendChild(metaPill('workspace', live.workspace || run.workspace));
  if (live.retrying) meta.appendChild(metaPill('retry', 'active'));
  if (verification.redecompose || live.recompose || children.length) meta.appendChild(metaPill('redecompose', children.length ? children.join(', ') : 'true'));
  card.appendChild(meta);

  const review = live.review || verification.review || '';
  if (review) {
    const reviewBox = document.createElement('div');
    reviewBox.className = 'task-review';
    reviewBox.textContent = review;
    card.appendChild(reviewBox);
  }

  if (children.length) {
    const childBox = document.createElement('div');
    childBox.className = 'task-children';
    childBox.textContent = `Children: ${children.join(', ')}`;
    card.appendChild(childBox);
  }

  const links = document.createElement('div');
  links.className = 'task-file-list';
  links.appendChild(fileLink('Output', outputPath || `tasks/${safe}.md`, Boolean(outputPath) && fileExists(outputPath)));
  for (const file of outputAttempts) links.appendChild(fileLink('Output attempt', file.path, true));
  links.appendChild(fileLink('Verification', verificationPath || `verifications/${safe}.json`, Boolean(verificationPath) && fileExists(verificationPath)));
  for (const file of verificationAttempts) links.appendChild(fileLink('Verify attempt', file.path, true));
  if (artifacts.length) {
    for (const file of artifacts) links.appendChild(fileLink('Artifact', file.path, true));
  } else if (run.artifact) {
    links.appendChild(fileLink('Expected artifact', run.artifact, fileExists(run.artifact)));
  }
  card.appendChild(links);
  return card;
}

function metaPill(label, value) {
  const pill = document.createElement('span');
  pill.className = 'task-meta-pill';
  pill.textContent = `${label}: ${value}`;
  return pill;
}

function verifyLabel(verification) {
  if (!verification || verification.pass === undefined) return '-';
  return verification.pass ? 'passed' : 'failed';
}

function fileLink(label, path, exists) {
  const row = document.createElement('button');
  row.type = 'button';
  row.className = `file-link ${exists ? 'exists' : ''}`;
  row.disabled = !exists;
  const labelNode = document.createElement('span');
  labelNode.textContent = label;
  row.appendChild(labelNode);
  const pathNode = document.createElement('strong');
  pathNode.textContent = path;
  row.appendChild(pathNode);
  if (exists) row.onclick = () => openFile(path);
  return row;
}

function buildFileTree(files) {
  const root = { name: 'session', path: '', type: 'directory', children: [] };
  for (const file of files) {
    const parts = file.path.split('/');
    let node = root;
    let currentPath = '';
    for (const part of parts.slice(0, -1)) {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      let child = node.children.find((item) => item.type === 'directory' && item.name === part);
      if (!child) {
        child = { name: part, path: currentPath, type: 'directory', children: [] };
        node.children.push(child);
      }
      node = child;
    }
    node.children.push({ ...file, type: 'file' });
  }
  sortTree(root);
  return root;
}

function sortTree(node) {
  if (!node.children) return;
  node.children.sort((a, b) => {
    if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  for (const child of node.children) sortTree(child);
}

function fileTreeNode(node, depth = 0) {
  const wrap = document.createElement('div');
  wrap.className = depth === 0 ? 'file-tree' : 'file-tree-branch';

  for (const child of node.children || []) {
    if (child.type === 'directory') {
      const details = document.createElement('details');
      details.className = 'file-folder';
      details.open = depth < 1 && child.name !== 'workspaces';
      const summary = document.createElement('summary');
      summary.textContent = child.name;
      details.appendChild(summary);
      details.appendChild(fileTreeNode(child, depth + 1));
      wrap.appendChild(details);
      continue;
    }

    const item = itemNode(child.name, `${child.kind} / ${child.size_bytes} bytes`, { exists: true });
    item.classList.add('file-item');
    item.style.setProperty('--depth', depth);
    item.onclick = () => openFile(child.path);
    wrap.appendChild(item);
  }
  return wrap;
}

function fileExists(path) {
  return state.files.some((file) => file.path === path);
}

function safeId(value) {
  return String(value).replace(/[^a-zA-Z0-9._-]+/g, '_').replace(/^[._]+|[._]+$/g, '') || 'task';
}

function itemNode(title, subtitle, options = {}) {
  const item = document.createElement('div');
  item.className = `item ${options.exists ? 'exists' : ''} ${options.failed ? 'failed' : ''}`;

  const head = document.createElement('div');
  head.className = 'item-head';

  const dot = document.createElement('span');
  dot.className = 'item-dot';
  head.appendChild(dot);

  const label = document.createElement('span');
  label.className = 'item-label';
  label.textContent = title;
  head.appendChild(label);
  item.appendChild(head);

  const small = document.createElement('small');
  small.textContent = subtitle || '';
  item.appendChild(small);
  return item;
}

async function openDocument(name) {
  const data = await api(`/api/session/documents/${encodePath(name)}`);
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

async function openFile(path) {
  const data = await api(`/api/session/documents/${encodePath(path)}`);
  const kind = path.endsWith('.md') ? 'markdown' : 'json';
  openText(path, kind, data.content);
}

function encodePath(path) {
  return String(path).split('/').map(encodeURIComponent).join('/');
}

function connectSSE() {
  const source = new EventSource('/api/events');
  source.onmessage = async (event) => {
    const data = JSON.parse(event.data);
    appendLog(data);
    updateSteps(data);
    updateRunState(data);
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
  el('log').textContent = '';
  resetRunState();
  clearSessionView();
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
resetRunState();
connectSSE();
refreshSession();
setInterval(refreshStatus, 15000);
