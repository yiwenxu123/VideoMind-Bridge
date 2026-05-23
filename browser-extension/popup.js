/**
 * VideoMind Bridge - Popup 脚本
 */

(function() {
    'use strict';

    const DEFAULT_API_URL = 'http://127.0.0.1:8787';
    const STORAGE_KEY = 'videomind_config';
    let API_BASE_URL = DEFAULT_API_URL;
    let WS_URL = 'ws://127.0.0.1:8787/ws';
    let currentMode = 'full';
    let aiEnabled = false;
    let ws = null;
    let currentTaskId = null;

    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const pageUrl = document.getElementById('page-url');
    const processBtn = document.getElementById('process-btn');
    const taskList = document.getElementById('task-list');
    const modeOptions = document.querySelectorAll('.mode-option');

    function log(msg, data) {
        console.log('[VideoMind]', msg, data || '');
    }

    async function loadConfig() {
        try {
            const result = await chrome.storage.local.get([STORAGE_KEY]);
            if (result[STORAGE_KEY] && result[STORAGE_KEY].apiBaseUrl) {
                API_BASE_URL = result[STORAGE_KEY].apiBaseUrl;
                WS_URL = API_BASE_URL.replace('http', 'ws') + '/ws';
            }
        } catch (error) {
            log('加载配置失败:', error);
        }
    }

    async function saveConfig(url) {
        try {
            const result = await chrome.storage.local.get([STORAGE_KEY]);
            const config = result[STORAGE_KEY] || {};
            config.apiBaseUrl = url;
            await chrome.storage.local.set({ [STORAGE_KEY]: config });
            API_BASE_URL = url;
            WS_URL = url.replace('http', 'ws') + '/ws';
        } catch (error) {
            log('保存配置失败:', error);
        }
    }

    function connectWebSocket() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            return;
        }

        try {
            ws = new WebSocket(WS_URL);

            ws.onopen = function() {
                log('WebSocket 连接成功');
                if (currentTaskId) {
                    subscribeToTask(currentTaskId);
                }
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                log('WebSocket 消息:', data);
                handleWebSocketMessage(data);
            };

            ws.onclose = function() {
                log('WebSocket 连接关闭');
                ws = null;
            };

            ws.onerror = function(error) {
                log('WebSocket 错误:', error);
            };
        } catch (error) {
            log('WebSocket 连接失败:', error);
        }
    }

    function subscribeToTask(taskId) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                action: 'subscribe',
                task_id: taskId
            }));
            log('已订阅任务:', taskId);
        }
    }

    function handleWebSocketMessage(data) {
        if (data.type === 'subscribed') {
            log('订阅成功:', data.task_id);
            return;
        }

        if (data.task_id && data.progress !== undefined) {
            updateTaskProgress(data.task_id, data.progress, data.current_step, data.status);
        }
    }

    function updateTaskProgress(taskId, progress, step, status) {
        const taskItem = document.querySelector(`.task-item[data-task-id="${taskId}"]`);
        if (taskItem) {
            const statusEl = taskItem.querySelector('.task-status');
            if (statusEl) {
                statusEl.textContent = `${getStatusText(status)} ${Math.round(progress)}%`;
                statusEl.className = `task-status ${status}`;
            }
        }
        
        if (status === 'completed' || status === 'failed') {
            setTimeout(loadRecentTasks, 500);
        }
    }

    async function checkAPIService() {
        try {
            const response = await fetch(`${API_BASE_URL}/health`, {
                signal: AbortSignal.timeout(5000)
            });
            if (response.ok) {
                statusDot.classList.remove('disconnected');
                statusDot.classList.add('connected');
                statusText.textContent = '服务已就绪';
                log('API 服务连接成功');
                return true;
            }
        } catch (error) {
            statusDot.classList.remove('connected');
            statusDot.classList.add('disconnected');
            statusText.textContent = '服务未运行';
            log('API 服务连接失败:', error);
        }
        return false;
    }

    async function checkAIEnabled() {
        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/config`);
            if (response.ok) {
                const config = await response.json();
                aiEnabled = config.ai_enabled || false;
                updateModeOptions();
                log('AI 状态:', aiEnabled ? '已启用' : '未启用');
                return aiEnabled;
            }
        } catch (error) {
            log('检查 AI 配置失败:', error);
        }
        return false;
    }

    function updateModeOptions() {
        const fullOption = document.querySelector('.mode-option[data-mode="full"]');
        const checkmark = fullOption.querySelector('.mode-check');
        
        if (!aiEnabled) {
            fullOption.classList.add('disabled');
            fullOption.classList.remove('active');
            checkmark.textContent = '🔒';
            if (currentMode === 'full') {
                currentMode = 'transcribe';
                document.querySelector('.mode-option[data-mode="transcribe"]').classList.add('active');
                document.querySelector('.mode-option[data-mode="transcribe"] .mode-check').textContent = '✓';
            }
        } else {
            fullOption.classList.remove('disabled');
        }
    }

    async function getCurrentPageInfo() {
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab && tab.url) {
                pageUrl.textContent = tab.url;
                processBtn.disabled = false;
                log('当前页面:', tab.url);
            }
        } catch (error) {
            pageUrl.textContent = '无法访问当前页面';
            processBtn.disabled = true;
            log('获取页面信息失败:', error);
        }
    }

    async function processCurrentVideo() {
        log('开始处理视频, 模式:', currentMode);
        
        try {
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tab || !tab.url) {
                alert('无法获取当前页面 URL');
                return;
            }

            processBtn.disabled = true;
            processBtn.classList.add('processing');
            processBtn.innerHTML = '<span>处理中...</span>';

            const videoInfo = {
                url: tab.url,
                platform: detectPlatform(tab.url),
                options: {
                    mode: currentMode
                }
            };
            
            log('发送任务请求:', videoInfo);

            const response = await fetch(`${API_BASE_URL}/api/v1/tasks`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url: videoInfo.url,
                    mode: currentMode === 'full' ? 'full' : 
                          currentMode === 'download' ? 'download_only' : 'transcribe_only',
                    targets: ['local', 'obsidian'],
                    cookies_from_browser: 'chrome',
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}`);
            }

            const result = await response.json();
            log('API 响应:', JSON.stringify(result));
            log('任务创建成功, ID:', result.id);
            
            currentTaskId = result.id;
            
            connectWebSocket();
            subscribeToTask(result.id);
            
            processBtn.innerHTML = '<span>✅ 已提交</span>';
            setTimeout(() => {
                processBtn.innerHTML = '<span>开始处理</span>';
            }, 3000);
            
            loadRecentTasks();

        } catch (error) {
            log('处理失败:', error);
            alert('处理失败: ' + error.message);
        } finally {
            processBtn.disabled = false;
            processBtn.classList.remove('processing');
            processBtn.innerHTML = '<span>开始处理</span>';
        }
    }

    function detectPlatform(url) {
        if (url.includes('bilibili.com')) return 'bilibili';
        if (url.includes('youtube.com')) return 'youtube';
        if (url.includes('douyin.com')) return 'douyin';
        if (url.includes('xiaohongshu.com')) return 'xiaohongshu';
        return 'unknown';
    }

    async function loadRecentTasks() {
        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/tasks`);
            if (response.ok) {
                const tasks = await response.json();
                renderTaskList(tasks);
                log('加载任务列表:', tasks.length, '个任务');
            }
        } catch (error) {
            log('加载任务失败:', error);
        }
    }

    function renderTaskList(tasks) {
        if (!tasks || tasks.length === 0) {
            taskList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">📋</div>
                    <p>暂无任务</p>
                    <small>处理视频后将显示在此</small>
                </div>
            `;
            return;
        }

        const taskHTML = tasks.slice(0, 6).map(task => `
            <div class="task-item" data-task-id="${task.id}">
                <div class="task-info">
                    <div class="task-url">${task.url}</div>
                    <div class="task-time">${formatTime(task.created_at)}</div>
                </div>
                <span class="task-status ${task.status}">${getStatusText(task.status)}</span>
            </div>
        `).join('');

        taskList.innerHTML = taskHTML;
    }

    function getStatusText(status) {
        const statusMap = {
            'pending': '等待',
            'processing': '处理中',
            'completed': '完成',
            'failed': '失败'
        };
        return statusMap[status] || status;
    }

    function formatTime(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;

        if (diff < 60000) {
            return '刚刚';
        } else if (diff < 3600000) {
            return `${Math.floor(diff / 60000)} 分钟前`;
        } else if (diff < 86400000) {
            return `${Math.floor(diff / 3600000)} 小时前`;
        } else {
            return date.toLocaleDateString('zh-CN');
        }
    }

    modeOptions.forEach(option => {
        option.addEventListener('click', function() {
            if (this.classList.contains('disabled')) {
                log('该模式已禁用，需要 AI Key');
                return;
            }
            
            modeOptions.forEach(opt => {
                opt.classList.remove('active');
                opt.querySelector('.mode-check').textContent = '';
            });
            
            this.classList.add('active');
            this.querySelector('.mode-check').textContent = '✓';
            currentMode = this.dataset.mode;
            log('切换模式:', currentMode);
        });
    });

    processBtn.addEventListener('click', processCurrentVideo);

    async function init() {
        log('初始化...');
        await loadConfig();
        await checkAPIService();
        await checkAIEnabled();
        await getCurrentPageInfo();
        await loadRecentTasks();
        
        connectWebSocket();
        
        setInterval(loadRecentTasks, 5000);
        
        log('初始化完成');
    }

    init();
})();
