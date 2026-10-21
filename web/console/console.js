'use strict';

const TOKEN_KEY = 'vmb_console_token';
const state = {
  capabilities: null,
  metrics: null,
  sessions: null,
  currentTab: 'overview',
  loading: {},
};

const dom = {
  healthPill: document.getElementById('health-pill'),
  tokenButton: document.getElementById('token-button'),
  refreshButton: document.getElementById('refresh-button'),
  tabs: Array.from(document.querySelectorAll('.tab')),
  panels: Array.from(document.querySelectorAll('.panel')),
  toast: document.getElementById('toast'),
  tokenDialog: document.getElementById('token-dialog'),
  tokenInput: document.getElementById('token-input'),
  overviewError: document.getElementById('overview-error'),
  overviewCards: document.getElementById('overview-cards'),
  overviewPlatforms: document.getElementById('overview-platforms'),
  overviewExtractors: document.getElementById('overview-extractors'),
  overviewFlags: document.getElementById('overview-flags'),
  overviewUpdated: document.getElementById('overview-updated'),
  extractForm: document.getElementById('extract-form'),
  extractStatus: document.getElementById('extract-status'),
  extractResult: document.getElementById('extract-result'),
  extractResultTitle: document.getElementById('extract-result-title'),
  extractResultBadges: document.getElementById('extract-result-badges'),
  extractResultError: document.getElementById('extract-result-error'),
  extractResultContent: document.getElementById('extract-result-content'),
  extractArchiveResults: document.getElementById('extract-archive-results'),
  commentsDisabled: document.getElementById('comments-disabled'),
  commentsForm: document.getElementById('comments-form'),
  commentsStatus: document.getElementById('comments-status'),
  commentsMeta: document.getElementById('comments-meta'),
  commentsList: document.getElementById('comments-list'),
  commentsSubmit: document.getElementById('comments-submit'),
  sessionsStatus: document.getElementById('sessions-status'),
  sessionsTable: document.getElementById('sessions-table'),
  checkBilibili: document.getElementById('check-bilibili'),
  metricsSummary: document.getElementById('metrics-summary'),
  metricsTable: document.getElementById('metrics-table'),
  capabilityExtractors: document.getElementById('capability-extractors'),
  capabilityAsr: document.getElementById('capability-asr'),
  capabilityDiscovery: document.getElementById('capability-discovery'),
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function clear(node) {
  node.replaceChildren();
}

function append(parent, ...children) {
  for (const child of children) {
    if (child !== null && child !== undefined) parent.appendChild(child);
  }
  return parent;
}

function badge(label, tone = 'neutral') {
  return el('span', `badge badge-${tone}`, label);
}

function setText(node, value, fallback = '—') {
  node.textContent = value === null || value === undefined || value === '' ? fallback : String(value);
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '—';
}

function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN');
}

function formatCooldown(value) {
  const seconds = Number(value || 0);
  if (!Number.isFinite(seconds) || seconds <= 0) return '—';
  if (seconds < 60) return `${seconds}s`;
  return `${Math.ceil(seconds / 60)}m`;
}

function formatLatency(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return '—';
  return `${number.toFixed(number >= 100 ? 0 : 1)}ms`;
}

function setStatus(node, message, isError = false) {
  node.textContent = message || '';
  node.className = isError ? 'status-line status-error' : 'status-line';
}

function setBusy(button, busy, label) {
  if (busy) {
    button.dataset.originalText = button.textContent;
    button.textContent = label || '处理中...';
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

function showToast(message, isError = false) {
  dom.toast.textContent = message;
  dom.toast.className = isError ? 'toast is-error' : 'toast';
  dom.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    dom.toast.hidden = true;
  }, 4200);
}

function setHealth(ok, text) {
  dom.healthPill.textContent = text;
  dom.healthPill.className = ok ? 'pill pill-success' : 'pill pill-danger';
}

function circuitBadge(circuit) {
  return circuit === 'open' ? badge('熔断', 'danger') : badge('正常', 'success');
}

function availabilityBadge(available) {
  return available ? badge('可用', 'success') : badge('不可用', 'warning');
}

function sourceBadge(source) {
  return source === 'none' ? badge('未配置', 'neutral') : badge(source || '未知', 'info');
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let body = options.body;
  if (body !== undefined && body !== null && typeof body !== 'string') {
    body = JSON.stringify(body);
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  }

  let response;
  try {
    response = await fetch(path, { ...options, headers, body });
  } catch (error) {
    throw new Error(`网络请求失败：${error.message}`);
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    if (response.status === 401) openTokenDialog();
    const detail = data && (data.detail || data.error || data.message);
    const message = typeof detail === 'string' ? detail : `HTTP ${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.payload = data;
    throw error;
  }
  return data;
}

function unwrap(result) {
  return result.status === 'fulfilled'
    ? { ok: true, value: result.value }
    : { ok: false, error: result.reason };
}

function emptyRow(columns, message) {
  const row = el('tr');
  const cell = el('td', 'muted', message);
  cell.colSpan = columns;
  row.appendChild(cell);
  return row;
}

function openTokenDialog() {
  dom.tokenInput.value = sessionStorage.getItem(TOKEN_KEY) || '';
  if (!dom.tokenDialog.open) dom.tokenDialog.showModal();
}

function updateTokenButton() {
  dom.tokenButton.textContent = sessionStorage.getItem(TOKEN_KEY) ? 'Token 已设置' : '设置 Token';
}

async function switchTab(name) {
  state.currentTab = name;
  dom.tabs.forEach((tab) => tab.classList.toggle('is-active', tab.dataset.tab === name));
  dom.panels.forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.hidden = !active;
    panel.classList.toggle('is-active', active);
  });
  await loadTab(name);
}

async function loadTab(name, force = false) {
  if (name === 'overview') return loadOverview(force);
  if (name === 'extract') return undefined;
  if (name === 'comments') return loadCommentsAvailability(force);
  if (name === 'sessions') return loadSessions(force);
  if (name === 'metrics') return loadMetrics(force);
  if (name === 'capabilities') return loadCapabilities(force);
  return undefined;
}

async function loadOverview() {
  dom.overviewError.hidden = true;
  const results = await Promise.allSettled([
    api('/health'),
    api('/api/v1/status'),
    api('/api/v1/capabilities'),
    api('/api/v1/metrics'),
    api('/api/v1/sessions'),
  ]);
  const [health, status, capabilities, metrics, sessions] = results.map(unwrap);

  setHealth(health.ok, health.ok ? `在线 · v${health.value.version || '?'}` : '离线');
  if (capabilities.ok) state.capabilities = capabilities.value;
  if (metrics.ok) state.metrics = metrics.value;
  if (sessions.ok) state.sessions = sessions.value;

  const errors = [health, status, capabilities, metrics, sessions]
    .filter((item) => !item.ok)
    .map((item) => item.error.message);
  if (errors.length) {
    dom.overviewError.textContent = `部分数据不可用：${errors.join('；')}`;
    dom.overviewError.hidden = false;
  }

  renderOverviewCards(
    health.ok ? health.value : null,
    status.ok ? status.value : null,
    capabilities.ok ? capabilities.value : null,
    metrics.ok ? metrics.value : null,
  );
  renderOverviewPlatforms(metrics.ok ? metrics.value : null);
  renderOverviewExtractors(capabilities.ok ? capabilities.value : null);
  renderOverviewFlags(capabilities.ok ? capabilities.value : null);
  dom.overviewUpdated.textContent = `更新于 ${new Date().toLocaleTimeString('zh-CN')}`;
}

function metricCard(label, value, hint) {
  const card = el('div', 'metric-card');
  append(card, el('div', 'label', label), el('div', 'value', value), el('div', 'hint', hint));
  return card;
}

function renderOverviewCards(health, status, capabilities, metrics) {
  clear(dom.overviewCards);
  const extractors = capabilities && capabilities.extractors ? capabilities.extractors : {};
  const names = Object.keys(extractors);
  const available = names.filter((name) => extractors[name]).length;
  const platforms = metrics && metrics.platforms ? metrics.platforms : {};
  const openCircuits = Object.values(platforms).filter((item) => item.circuit === 'open').length;
  const discovery = capabilities && capabilities.discovery ? capabilities.discovery : {};
  const commentsOn = Boolean(discovery.comments && discovery.comments.enabled);
  const creatorOn = Boolean(discovery.creator_feed && discovery.creator_feed.enabled);

  append(
    dom.overviewCards,
    metricCard('服务状态', health ? (health.status === 'healthy' ? '正常' : health.status) : '不可用', health ? `v${health.version || '?'}` : '无法连接 /health'),
    metricCard('任务统计', status ? formatNumber(status.active_tasks) : '—', status ? `排队 ${formatNumber(status.queued_tasks)} · 完成 ${formatNumber(status.completed_tasks)}` : '无法读取任务统计'),
    metricCard('提取器', names.length ? `${available}/${names.length}` : '—', names.length ? '已注册提取器可用数' : '未获取能力信息'),
    metricCard('平台健康', `${Object.keys(platforms).length} 个平台`, openCircuits ? `${openCircuits} 个平台熔断中` : '全部平台未熔断'),
    metricCard('评论采样', commentsOn ? '已开启' : '未开启', commentsOn ? '公开评论、限量样本' : 'VMB_ENABLE_COMMENTS=0 时不注册路由'),
    metricCard('Creator Feed', creatorOn ? '已开启' : '保持关闭', creatorOn ? '当前环境已启用' : '受平台风控限制，默认关闭'),
  );
}

function renderOverviewPlatforms(metrics) {
  clear(dom.overviewPlatforms);
  const platforms = metrics && metrics.platforms ? metrics.platforms : {};
  const names = Object.keys(platforms);
  if (!names.length) {
    dom.overviewPlatforms.appendChild(emptyRow(8, '暂无平台指标；首次平台请求后出现。'));
    return;
  }
  for (const name of names) {
    const item = platforms[name];
    const row = el('tr');
    const errorText = item.last_error_code
      ? `${item.last_error_code}${item.last_error_at ? ` · ${formatTime(item.last_error_at)}` : ''}`
      : '—';
    append(
      row,
      el('td', 'name', name),
      (() => { const cell = el('td'); cell.appendChild(circuitBadge(item.circuit)); return cell; })(),
      el('td', '', formatNumber(item.requests_total)),
      el('td', '', `${formatNumber(item.success_total)} / ${formatNumber(item.failure_total)}`),
      el('td', '', `${formatNumber(item.risk_control_total)} / ${formatNumber(item.rate_limited_total)}`),
      el('td', '', formatNumber(item.failure_streak)),
      el('td', '', formatCooldown(item.cooldown_remaining_s)),
      el('td', '', errorText),
    );
    dom.overviewPlatforms.appendChild(row);
  }
}

function renderOverviewExtractors(capabilities) {
  clear(dom.overviewExtractors);
  const extractors = capabilities && capabilities.extractors ? capabilities.extractors : {};
  const names = Object.keys(extractors);
  if (!names.length) {
    dom.overviewExtractors.appendChild(el('p', 'muted', '未获取提取器状态。'));
    return;
  }
  for (const name of names) {
    const row = el('div', 'stack-item');
    append(row, el('span', 'name', name), availabilityBadge(Boolean(extractors[name])));
    dom.overviewExtractors.appendChild(row);
  }
}

function renderOverviewFlags(capabilities) {
  clear(dom.overviewFlags);
  if (!capabilities) {
    dom.overviewFlags.appendChild(el('p', 'muted', '未获取能力信息。'));
    return;
  }
  const discovery = capabilities.discovery || {};
  const comments = discovery.comments || {};
  const creator = discovery.creator_feed || {};
  const items = [
    ['评论采样', comments.enabled ? '已开启' : '未开启', comments.enabled ? 'success' : 'neutral'],
    ['Creator Feed', creator.enabled ? '已开启' : '保持关闭', creator.enabled ? 'success' : 'warning'],
  ];
  for (const [label, value, tone] of items) {
    const row = el('div', 'stack-item');
    append(row, el('span', 'name', label), badge(value, tone));
    dom.overviewFlags.appendChild(row);
  }
  const platforms = Array.isArray(capabilities.platforms) ? capabilities.platforms : [];
  if (platforms.length) {
    const row = el('div', 'stack-item');
    append(row, el('span', 'name', '提取平台'), el('span', 'muted', platforms.join(' / ')));
    dom.overviewFlags.appendChild(row);
  }
}

async function loadSessions() {
  setStatus(dom.sessionsStatus, '正在读取会话状态...');
  try {
    const data = await api('/api/v1/sessions');
    state.sessions = data;
    renderSessions(data);
    setStatus(dom.sessionsStatus, '');
  } catch (error) {
    setStatus(dom.sessionsStatus, error.message, true);
    clear(dom.sessionsTable);
    dom.sessionsTable.appendChild(emptyRow(7, '会话数据不可用。'));
  }
}

function renderSessions(data) {
  clear(dom.sessionsTable);
  const sessions = data && Array.isArray(data.sessions) ? data.sessions : [];
  if (!sessions.length) {
    dom.sessionsTable.appendChild(emptyRow(7, '暂无会话数据。'));
    return;
  }
  for (const item of sessions) {
    const row = el('tr');
    const validTone = item.valid === true ? 'success' : item.valid === false ? 'danger' : 'neutral';
    const validText = item.valid === true ? '有效' : item.valid === false ? (item.error_code || '无效') : '未检查';
    const hint = item.warning || '—';
    append(
      row,
      el('td', 'name', item.platform),
      (() => { const cell = el('td'); cell.appendChild(badge(item.configured ? '已配置' : '未配置', item.configured ? 'success' : 'neutral')); return cell; })(),
      (() => { const cell = el('td'); cell.appendChild(sourceBadge(item.source)); return cell; })(),
      el('td', '', formatNumber(item.cookie_count)),
      el('td', '', item.expires_at ? formatTime(item.expires_at) : '—'),
      (() => { const cell = el('td'); cell.appendChild(badge(validText, validTone)); return cell; })(),
      el('td', '', hint),
    );
    dom.sessionsTable.appendChild(row);
  }
}

async function checkBilibiliSession() {
  setBusy(dom.checkBilibili, true, '检查中...');
  setStatus(dom.sessionsStatus, '正在检查 B站登录态...');
  try {
    const data = await api('/api/v1/sessions/bilibili/check', { method: 'POST' });
    mergeSessionStatus(data);
    const result = data.valid === true ? '有效' : (data.error_code || '无效');
    setStatus(dom.sessionsStatus, `检查完成：${result}`);
    showToast(`B站登录态：${result}`, data.valid !== true);
  } catch (error) {
    setStatus(dom.sessionsStatus, error.message, true);
  } finally {
    setBusy(dom.checkBilibili, false);
  }
}

function mergeSessionStatus(status) {
  if (!state.sessions || !Array.isArray(state.sessions.sessions)) {
    state.sessions = { schema_version: '1.0', sessions: [] };
  }
  const list = state.sessions.sessions;
  const index = list.findIndex((item) => item.platform === status.platform);
  if (index >= 0) list[index] = status;
  else list.push(status);
  renderSessions(state.sessions);
}

async function loadMetrics() {
  try {
    const data = await api('/api/v1/metrics');
    state.metrics = data;
    renderMetrics(data);
  } catch (error) {
    clear(dom.metricsSummary);
    clear(dom.metricsTable);
    dom.metricsTable.appendChild(emptyRow(13, `指标不可用：${error.message}`));
  }
}

function renderMetrics(data) {
  const platforms = data && data.platforms ? data.platforms : {};
  const names = Object.keys(platforms);
  const totals = names.reduce((acc, name) => {
    const item = platforms[name];
    acc.requests += Number(item.requests_total || 0);
    acc.success += Number(item.success_total || 0);
    acc.risk += Number(item.risk_control_total || 0);
    acc.open += item.circuit === 'open' ? 1 : 0;
    return acc;
  }, { requests: 0, success: 0, risk: 0, open: 0 });
  const successRate = totals.requests ? `${((totals.success / totals.requests) * 100).toFixed(1)}%` : '—';
  clear(dom.metricsSummary);
  append(
    dom.metricsSummary,
    metricCard('总请求', formatNumber(totals.requests), `覆盖 ${names.length} 个平台`),
    metricCard('成功率', successRate, `成功 ${formatNumber(totals.success)} 次`),
    metricCard('风控命中', formatNumber(totals.risk), 'HTTP 403/412 及响应体风控'),
    metricCard('熔断平台', formatNumber(totals.open), data.enabled ? '平台级熔断状态' : '节流总开关已关闭'),
  );

  clear(dom.metricsTable);
  if (!names.length) {
    dom.metricsTable.appendChild(emptyRow(13, '暂无平台指标。'));
    return;
  }
  for (const name of names) {
    const item = platforms[name];
    const row = el('tr');
    append(
      row,
      el('td', 'name', name),
      (() => { const cell = el('td'); cell.appendChild(circuitBadge(item.circuit)); return cell; })(),
      el('td', '', formatNumber(item.requests_total)),
      el('td', '', formatNumber(item.success_total)),
      el('td', '', formatNumber(item.failure_total)),
      el('td', '', formatNumber(item.retries_total)),
      el('td', '', formatNumber(item.risk_control_total)),
      el('td', '', formatNumber(item.rate_limited_total)),
      el('td', '', formatNumber(item.failure_streak)),
      el('td', '', formatCooldown(item.cooldown_remaining_s)),
      el('td', '', formatLatency(item.latency_ms_avg)),
      el('td', '', formatLatency(item.latency_ms_max)),
      el('td', '', item.last_error_code || '—'),
    );
    dom.metricsTable.appendChild(row);
  }
}

async function loadCapabilities() {
  try {
    const data = await api('/api/v1/capabilities');
    state.capabilities = data;
    renderCapabilities(data);
  } catch (error) {
    clear(dom.capabilityExtractors);
    clear(dom.capabilityAsr);
    clear(dom.capabilityDiscovery);
    dom.capabilityExtractors.appendChild(el('p', 'muted', `能力信息不可用：${error.message}`));
  }
}

function renderCapabilities(data) {
  clear(dom.capabilityExtractors);
  const extractors = data && data.extractors ? data.extractors : {};
  const names = Object.keys(extractors);
  if (!names.length) {
    dom.capabilityExtractors.appendChild(el('p', 'muted', '暂无提取器信息。'));
  } else {
    for (const name of names) {
      const row = el('div', 'stack-item');
      append(row, el('span', 'name', name), availabilityBadge(Boolean(extractors[name])));
      dom.capabilityExtractors.appendChild(row);
    }
  }

  clear(dom.capabilityAsr);
  const backends = data && data.asr && Array.isArray(data.asr.backends) ? data.asr.backends : [];
  if (!backends.length) {
    dom.capabilityAsr.appendChild(el('p', 'muted', '暂无 ASR 后端信息。'));
  } else {
    for (const backend of backends) {
      const row = el('div', 'stack-item');
      const left = el('div', 'stack');
      append(left, el('span', 'name', backend.name || 'unknown'), el('span', 'muted', (backend.languages || []).join(' / ') || '语言未知'));
      append(row, left, availabilityBadge(Boolean(backend.available)));
      dom.capabilityAsr.appendChild(row);
    }
  }

  clear(dom.capabilityDiscovery);
  const discovery = data && data.discovery ? data.discovery : {};
  const entries = [
    ['评论采样', discovery.comments],
    ['Creator Feed', discovery.creator_feed],
  ];
  for (const [label, value] of entries) {
    const row = el('div', 'stack-item');
    const detail = value && value.enabled
      ? `enabled · ${(value.platforms || []).join(' / ') || '平台未知'}`
      : '未启用';
    append(row, el('span', 'name', label), el('span', 'muted', detail));
    dom.capabilityDiscovery.appendChild(row);
  }
  if (!Object.keys(discovery).length) {
    dom.capabilityDiscovery.appendChild(el('p', 'muted', '当前没有启用的发现能力。'));
  }
}

function extractPayload(action) {
  const url = document.getElementById('extract-url').value.trim();
  if (!url) throw new Error('请先填写视频链接');
  const payload = {
    url,
    cost_tier: document.getElementById('extract-cost').value,
  };
  const asr = document.getElementById('extract-asr').value.trim();
  const language = document.getElementById('extract-language').value.trim();
  if (asr) payload.asr = asr;
  if (language) payload.asr_options = { language };
  if (action === 'archive') {
    const targets = [];
    if (document.getElementById('archive-local').checked) targets.push('local');
    if (document.getElementById('archive-obsidian').checked) targets.push('obsidian');
    if (!targets.length) throw new Error('至少选择一个归档目标');
    payload.targets = targets;
    const localOutput = document.getElementById('archive-local-output').value.trim();
    const obsidianVault = document.getElementById('archive-obsidian-vault').value.trim();
    if (localOutput) payload.local_output = localOutput;
    if (obsidianVault) payload.obsidian_vault = obsidianVault;
  }
  return payload;
}

function renderExtractResult(data, action) {
  const extract = action === 'archive' ? (data.extract || {}) : data;
  const success = Boolean(action === 'archive' ? data.success && extract : data.success);
  dom.extractResult.hidden = false;
  setText(dom.extractResultTitle, extract.title || (success ? '提取完成' : '提取失败'));

  clear(dom.extractResultBadges);
  const badges = [];
  if (extract.platform) badges.push([extract.platform, 'info']);
  if (extract.source) badges.push([extract.source, 'neutral']);
  if (extract.cost_tier) badges.push([`成本 ${extract.cost_tier}`, 'neutral']);
  if (extract.completeness) badges.push([`完整性 ${extract.completeness}`, extract.completeness === 'full' ? 'success' : 'warning']);
  if (extract.method) badges.push([extract.method, 'neutral']);
  if (extract.asr && extract.asr.provider) badges.push([`ASR ${extract.asr.provider}`, 'success']);
  if (action === 'archive') badges.push(['归档请求', data.success ? 'success' : 'warning']);
  for (const [label, tone] of badges) dom.extractResultBadges.appendChild(badge(label, tone));

  const errorMessage = data.error || extract.error || '';
  dom.extractResultError.textContent = errorMessage;
  dom.extractResultError.hidden = !errorMessage;

  const content = extract.content || '';
  dom.extractResultContent.textContent = content || (success ? '（提取结果没有正文）' : '（没有返回内容）');

  clear(dom.extractArchiveResults);
  if (action === 'archive' && Array.isArray(data.archive)) {
    for (const item of data.archive) {
      const row = el('div', 'stack-item');
      const detail = item.output_path || item.error || '';
      append(
        row,
        el('span', 'name', item.target || 'unknown'),
        el('span', 'muted', detail),
        item.success ? badge('成功', 'success') : badge('失败', 'danger'),
      );
      dom.extractArchiveResults.appendChild(row);
    }
  }
}

async function handleExtractSubmit(event) {
  event.preventDefault();
  const action = event.submitter && event.submitter.dataset.action === 'archive' ? 'archive' : 'extract';
  let payload;
  try {
    payload = extractPayload(action);
  } catch (error) {
    setStatus(dom.extractStatus, error.message, true);
    return;
  }
  const button = action === 'archive' ? document.getElementById('archive-submit') : document.getElementById('extract-submit');
  setBusy(button, true, action === 'archive' ? '归档中...' : '提取中...');
  setStatus(dom.extractStatus, action === 'archive' ? '正在提取并归档...' : '正在提取...');
  try {
    const endpoint = action === 'archive' ? '/api/v1/extract/archive' : '/api/v1/extract';
    const data = await api(endpoint, { method: 'POST', body: payload });
    renderExtractResult(data, action);
    const success = Boolean(action === 'archive' ? data.success : data.success);
    setStatus(dom.extractStatus, success ? '完成' : (data.error || '请求已返回失败'), !success);
    showToast(success ? '提取完成' : '提取失败', !success);
  } catch (error) {
    setStatus(dom.extractStatus, error.message, true);
    showToast(error.message, true);
  } finally {
    setBusy(button, false);
  }
}

function commentsPayload() {
  const url = document.getElementById('comments-url').value.trim();
  if (!url) throw new Error('请先填写视频链接');
  return {
    url,
    limit: Number(document.getElementById('comments-limit').value),
    sort: document.getElementById('comments-sort').value,
    include_replies: document.getElementById('comments-include-replies').checked,
    max_replies_per_thread: Number(document.getElementById('comments-replies-per-thread').value),
    include_author: document.getElementById('comments-include-author').checked,
    max_cost: 'cheap',
  };
}

async function loadCommentsAvailability(force = false) {
  try {
    const capabilities = force || !state.capabilities
      ? await api('/api/v1/capabilities')
      : state.capabilities;
    state.capabilities = capabilities;
    const comments = capabilities.discovery && capabilities.discovery.comments;
    if (!comments || !comments.enabled) {
      dom.commentsDisabled.textContent = '评论采样未开启：服务端需要设置 VMB_ENABLE_COMMENTS=1 并重启。';
      dom.commentsDisabled.hidden = false;
      dom.commentsSubmit.disabled = true;
    } else {
      dom.commentsDisabled.hidden = true;
      dom.commentsSubmit.disabled = false;
    }
  } catch (error) {
    dom.commentsDisabled.textContent = `无法读取评论开关：${error.message}`;
    dom.commentsDisabled.hidden = false;
    dom.commentsSubmit.disabled = true;
  }
}

function renderComments(data) {
  const success = Boolean(data && data.success);
  dom.commentsMeta.hidden = false;
  dom.commentsMeta.className = success ? 'notice' : 'notice notice-error';
  const warnings = data && Array.isArray(data.warnings) ? data.warnings : [];
  const parts = [
    success ? '采集成功' : `采集失败${data.error ? `：${data.error}` : ''}`,
    data.returned_count !== undefined ? `返回 ${data.returned_count} 条` : '',
    data.top_level_count !== undefined ? `一级 ${data.top_level_count} 条` : '',
    data.reply_count !== undefined ? `回复 ${data.reply_count} 条` : '',
    data.completeness ? `完整性 ${data.completeness}` : '',
    data.cached ? '命中缓存' : '',
    warnings.length ? `提示：${warnings.join(' / ')}` : '',
  ].filter(Boolean);
  dom.commentsMeta.textContent = parts.join(' · ');

  clear(dom.commentsList);
  const items = data && Array.isArray(data.items) ? data.items : [];
  if (!items.length) {
    dom.commentsList.appendChild(el('p', 'muted', success ? '没有返回评论。' : '没有可显示的评论。'));
    return;
  }
  for (const item of items) {
    const card = el('div', item.is_reply ? 'comment is-reply' : 'comment');
    const head = el('div', 'comment-head');
    append(head, badge(item.is_reply ? '回复' : '一级', item.is_reply ? 'info' : 'neutral'));
    if (item.author && item.author.display_name) append(head, el('span', '', item.author.display_name));
    append(head, el('span', '', `赞 ${formatNumber(item.likes)}`));
    if (item.created_at) append(head, el('span', '', formatTime(item.created_at)));
    if (item.truncated) append(head, badge('已截断', 'warning'));
    if (item.parent_id) append(head, el('span', 'muted', `parent ${item.parent_id}`));
    append(card, head, el('div', 'comment-text', item.text || '（空评论）'));
    dom.commentsList.appendChild(card);
  }
}

async function handleCommentsSubmit(event) {
  event.preventDefault();
  let payload;
  try {
    payload = commentsPayload();
  } catch (error) {
    setStatus(dom.commentsStatus, error.message, true);
    return;
  }
  setBusy(dom.commentsSubmit, true, '采集中...');
  setStatus(dom.commentsStatus, '正在采样公开评论...');
  try {
    const data = await api('/api/v1/comments', { method: 'POST', body: payload });
    renderComments(data);
    setStatus(dom.commentsStatus, data.success ? '采集完成' : (data.error || '采集失败'), !data.success);
    showToast(data.success ? '评论采样完成' : '评论采样失败', !data.success);
  } catch (error) {
    setStatus(dom.commentsStatus, error.message, true);
    showToast(error.message, true);
  } finally {
    setBusy(dom.commentsSubmit, false);
  }
}

dom.tabs.forEach((tab) => tab.addEventListener('click', () => switchTab(tab.dataset.tab)));
dom.refreshButton.addEventListener('click', () => loadTab(state.currentTab, true));
dom.tokenButton.addEventListener('click', openTokenDialog);
dom.tokenDialog.addEventListener('close', () => {
  dom.tokenInput.value = '';
});
document.getElementById('token-save').addEventListener('click', async () => {
  const value = dom.tokenInput.value.trim();
  if (value) sessionStorage.setItem(TOKEN_KEY, value);
  else sessionStorage.removeItem(TOKEN_KEY);
  dom.tokenDialog.close();
  updateTokenButton();
  await loadTab(state.currentTab, true);
});
document.getElementById('token-clear').addEventListener('click', async () => {
  sessionStorage.removeItem(TOKEN_KEY);
  dom.tokenDialog.close();
  updateTokenButton();
  await loadTab(state.currentTab, true);
});
dom.extractForm.addEventListener('submit', handleExtractSubmit);
dom.commentsForm.addEventListener('submit', handleCommentsSubmit);
dom.checkBilibili.addEventListener('click', checkBilibiliSession);

updateTokenButton();
switchTab('overview');
