const API = '/api/v1';
const WS_URL = `ws://${location.host}/ws`;

let ws = null;
let tasks = {};

// ===== API =====

async function fetchJSON(url, options = {}) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || resp.statusText);
  }
  return resp.json();
}

async function createTask(url, mode, targets, allowDowngrade = false) {
  return fetchJSON(`${API}/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, mode, targets, allow_downgrade: allowDowngrade }),
  });
}

async function checkAIAvailable() {
  try {
    const settings = await fetchJSON(`${API}/settings`);
    return settings.ai_api_key_configured;
  } catch (e) {
    return false;
  }
}

async function getTasks() {
  return fetchJSON(`${API}/tasks`);
}

async function getTask(id) {
  return fetchJSON(`${API}/tasks/${id}`);
}

async function cancelTask(id) {
  return fetchJSON(`${API}/tasks/${id}/cancel`, { method: 'POST' });
}

async function deleteTask(id) {
  return fetchJSON(`${API}/tasks/${id}`, { method: 'DELETE' });
}

async function getStatus() {
  return fetchJSON(`${API}/status`);
}

async function extractContent(url) {
  const resp = await fetch(`${API}/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return resp.json();
}

// ===== WebSocket =====

function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    document.getElementById('system-status').textContent = '已连接';
    Object.keys(tasks).forEach(id => subscribeTask(id));
  };
  ws.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.task_id) {
      tasks[data.task_id] = { ...tasks[data.task_id], ...data };
      renderTask(data.task_id);
    }
  };
  ws.onclose = () => {
    document.getElementById('system-status').textContent = '连接断开，重连中...';
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => ws.close();
}

function subscribeTask(id) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'subscribe', task_id: id }));
  }
}

// ===== UI =====

function getSelectedMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function getSelectedTargets() {
  return [...document.querySelectorAll('input[name="target"]:checked')]
    .map(el => el.value);
}

function getURLs() {
  const text = document.getElementById('url-input').value.trim();
  if (!text) return [];
  return text.split('\n')
    .map(l => l.trim())
    .filter(l => l && (l.startsWith('http://') || l.startsWith('https://')));
}

function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function renderTask(id) {
  const task = tasks[id];
  if (!task) return;

  let el = document.getElementById(`task-${id}`);
  if (!el) {
    el = document.createElement('div');
    el.id = `task-${id}`;
    el.className = 'task-item';
    document.getElementById('task-list').prepend(el);
    const empty = document.querySelector('#task-list .empty-state');
    if (empty) empty.remove();
  }

  const statusClass = {
    completed: 'status-completed',
    failed: 'status-failed',
    cancelled: 'status-completed',
  }[task.status] || 'status-processing';

  const statusText = {
    pending: '等待中',
    downloading: '下载中',
    transcribing: '转录中',
    ai_processing: 'AI处理中',
    exporting: '导出中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    paused: '已暂停',
  }[task.status] || task.status;

  el.innerHTML = `
    <div class="task-header">
      <span class="task-title">${task.title || task.url}</span>
      <span class="task-platform">${task.platform || ''}</span>
    </div>
    <div class="task-progress-bar">
      <div class="task-progress-fill" style="width:${task.progress || 0}%"></div>
    </div>
    <div class="task-step">
      <span class="${statusClass}">${statusText}</span>
      <span>${Math.round(task.progress || 0)}%</span>
    </div>
    <div class="task-step" style="margin-top:2px">
      <span>${task.current_step || ''}</span>
    </div>
    ${task.status === 'completed' && task.summary ? `<div style="margin-top:8px;padding:8px;background:#f9f9f9;border-radius:4px;font-size:12px">${task.summary.substring(0, 200)}...</div>` : ''}
    ${task.error_msg ? `<div style="margin-top:4px;font-size:11px;color:var(--danger)">${task.error_msg}</div>` : ''}
    <div class="task-actions">
      ${['pending','downloading','transcribing','ai_processing','exporting'].includes(task.status)
        ? `<button class="btn-cancel" onclick="handleCancel('${id}')">取消</button>` : ''}
      ${['completed','failed','cancelled'].includes(task.status)
        ? `<button class="btn-delete" onclick="handleDelete('${id}')">删除</button>` : ''}
    </div>
  `;
}

function renderHistory(tasks) {
  const list = document.getElementById('history-list');
  if (!tasks.length) {
    list.innerHTML = '<p class="empty-state">暂无历史记录</p>';
    return;
  }
  list.innerHTML = tasks.map(t => `
    <div class="task-item">
      <div class="task-header">
        <span class="task-title">${t.title || t.url}</span>
        <span class="task-platform">${t.platform || ''}</span>
      </div>
      <div class="task-step">
        <span class="${t.status === 'completed' ? 'status-completed' : t.status === 'failed' ? 'status-failed' : ''}">${t.status}</span>
        <span>${new Date(t.created_at).toLocaleString('zh-CN')}</span>
      </div>
    </div>
  `).join('');
}

async function loadHistory() {
  try {
    const data = await getTasks();
    renderHistory(data.tasks || []);
  } catch (e) {
    toast('加载历史记录失败', 'error');
  }
}

async function loadStatus() {
  try {
    const status = await getStatus();
    document.getElementById('system-status').textContent =
      `${status.active_tasks} 活跃任务`;
  } catch (e) {
    document.getElementById('system-status').textContent = 'API 未连接';
  }
}

// ===== Events =====

document.getElementById('start-btn').addEventListener('click', async () => {
  const urls = getURLs();
  if (!urls.length) {
    toast('请输入有效的视频链接', 'warning');
    return;
  }

  const mode = getSelectedMode();
  const targets = getSelectedTargets();
  const btn = document.getElementById('start-btn');

  // 完整处理模式下检查 AI 配置
  if (mode === 'full') {
    const aiOk = await checkAIAvailable();
    if (!aiOk) {
      const downgrade = confirm(
        '⚠️ AI 服务未配置，无法进行完整处理。\n\n'
        + '是否降级为「转录存档」模式（跳过 AI 摘要）？\n'
        + '「确定」= 降级处理  「取消」= 前往设置'
      );
      if (!downgrade) {
        window.location.href = '/static/settings.html';
        return;
      }
      // 用户选择降级
      btn.disabled = true;
      btn.textContent = '处理中...';
      try {
        for (const url of urls) {
          const task = await createTask(url, mode, targets, true);
          tasks[task.id] = task;
          renderTask(task.id);
          subscribeTask(task.id);
        }
        toast(`⚠️ 已降级处理 ${urls.length} 个任务（跳过 AI 摘要）`);
        document.getElementById('url-input').value = '';
      } catch (e) {
        toast(e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = '▶ 完整处理';
      }
      return;
    }
  }

  btn.disabled = true;
  btn.textContent = '处理中...';

  try {
    for (const url of urls) {
      const task = await createTask(url, mode, targets);
      tasks[task.id] = task;
      renderTask(task.id);
      subscribeTask(task.id);
    }
    toast(`已提交 ${urls.length} 个任务`);
    document.getElementById('url-input').value = '';
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ 完整处理';
  }
});

document.getElementById('extract-btn').addEventListener('click', async () => {
  const urls = getURLs();
  if (!urls.length) {
    toast('请输入有效的视频链接', 'warning');
    return;
  }

  const btn = document.getElementById('extract-btn');
  const resultDiv = document.getElementById('extract-result');
  const contentDiv = document.getElementById('extract-content');
  
  btn.disabled = true;
  btn.textContent = '提取中...';
  resultDiv.style.display = 'block';
  contentDiv.innerHTML = '<p class="empty-state">正在提取内容...</p>';

  try {
    const url = urls[0];
    const result = await extractContent(url);
    
    if (result.success) {
      contentDiv.innerHTML = `
        <div style="margin-bottom:12px">
          <strong style="font-size:16px">${result.title || '未知标题'}</strong>
          <span class="task-platform">${result.platform}</span>
          ${result.language ? `<span class="task-platform">${result.language}</span>` : ''}
          ${result.duration_seconds ? `<span class="task-platform">${Math.round(result.duration_seconds/60)}分钟</span>` : ''}
        </div>
        <div style="background:#f9f9f9;padding:12px;border-radius:6px;font-size:13px;line-height:1.6;white-space:pre-wrap">${result.content || '无内容'}</div>
        <div style="margin-top:8px;font-size:12px;color:#888">
          来源: ${result.source} | 成本: ${result.cost_tier}
        </div>
      `;
      toast('提取成功');
    } else {
      contentDiv.innerHTML = `<p style="color:var(--danger)">${result.error || '提取失败'}</p>`;
      toast(result.error || '提取失败', 'error');
    }
  } catch (e) {
    contentDiv.innerHTML = `<p style="color:var(--danger)">${e.message}</p>`;
    toast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ 快速提取';
  }
});

document.getElementById('paste-btn').addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    document.getElementById('url-input').value = text;
  } catch (e) {
    toast('无法读取剪贴板', 'warning');
  }
});

document.getElementById('clear-btn').addEventListener('click', () => {
  document.getElementById('url-input').value = '';
});

document.getElementById('refresh-btn').addEventListener('click', loadHistory);

// Mode card selection
document.querySelectorAll('.mode-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.mode-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    card.querySelector('input[type="radio"]').checked = true;
  });
});

// Target toggle
document.querySelectorAll('input[name="mode"]').forEach(radio => {
  radio.addEventListener('change', (e) => {
    const obsidian = document.querySelector('input[value="obsidian"]');
    if (e.target.value !== 'full') {
      obsidian.checked = false;
      obsidian.disabled = true;
    } else {
      obsidian.disabled = false;
    }
  });
});

async function handleCancel(id) {
  try {
    await cancelTask(id);
    toast('任务已取消');
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function handleDelete(id) {
  try {
    await deleteTask(id);
    delete tasks[id];
    const el = document.getElementById(`task-${id}`);
    if (el) el.remove();
    toast('任务已删除');
  } catch (e) {
    toast(e.message, 'error');
  }
}

// ===== Init =====

connectWS();
loadHistory();
loadStatus();
setInterval(loadStatus, 10000);
setInterval(loadHistory, 30000);
