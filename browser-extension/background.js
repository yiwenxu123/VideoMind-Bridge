/**
 * VideoMind Bridge - 浏览器扩展背景脚本
 * Manifest V3 Service Worker
 */

const DEFAULT_API_URL = 'http://127.0.0.1:8787';
const STORAGE_KEY = 'videomind_config';

/**
 * 获取 API 基础 URL
 */
async function getApiBaseUrl() {
    try {
        const result = await chrome.storage.local.get([STORAGE_KEY]);
        if (result[STORAGE_KEY] && result[STORAGE_KEY].apiBaseUrl) {
            return result[STORAGE_KEY].apiBaseUrl;
        }
    } catch (error) {
        console.error('获取配置失败:', error);
    }
    return DEFAULT_API_URL;
}

/**
 * 设置 API 基础 URL
 */
async function setApiBaseUrl(url) {
    try {
        const result = await chrome.storage.local.get([STORAGE_KEY]);
        const config = result[STORAGE_KEY] || {};
        config.apiBaseUrl = url;
        await chrome.storage.local.set({ [STORAGE_KEY]: config });
        return true;
    } catch (error) {
        console.error('保存配置失败:', error);
        return false;
    }
}

/**
 * 获取完整配置
 */
async function getConfig() {
    try {
        const result = await chrome.storage.local.get([STORAGE_KEY]);
        return result[STORAGE_KEY] || { apiBaseUrl: DEFAULT_API_URL };
    } catch (error) {
        console.error('获取配置失败:', error);
        return { apiBaseUrl: DEFAULT_API_URL };
    }
}

/**
 * 发送任务到 API 服务
 */
async function sendTaskToAPI(videoInfo) {
    const apiBaseUrl = await getApiBaseUrl();

    try {
        const body = {
            url: videoInfo.url,
            mode: videoInfo.mode || 'full',
            targets: videoInfo.targets || ['local', 'obsidian'],
        };

        if (videoInfo.cookies_from_browser) {
            body.cookies_from_browser = videoInfo.cookies_from_browser;
        }

        const response = await fetch(`${apiBaseUrl}/api/v1/tasks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(body)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('发送任务失败:', error);
        throw error;
    }
}

/**
 * 健康检查
 */
async function healthCheck() {
    const apiBaseUrl = await getApiBaseUrl();
    try {
        const response = await fetch(`${apiBaseUrl}/health`, {
            method: 'GET',
            signal: AbortSignal.timeout(5000)
        });
        return response.ok;
    } catch (error) {
        return false;
    }
}

/**
 * 获取 API 配置
 */
async function getAPIConfig() {
    const apiBaseUrl = await getApiBaseUrl();
    
    try {
        const response = await fetch(`${apiBaseUrl}/api/v1/config`);
        if (response.ok) {
            return await response.json();
        }
    } catch (error) {
        console.error('获取配置失败:', error);
    }
    return { ai_enabled: false };
}

/**
 * 测试 API 连接
 */
async function testApiConnection(url) {
    try {
        const response = await fetch(`${url}/health`, {
            method: 'GET',
            signal: AbortSignal.timeout(5000)
        });
        return response.ok;
    } catch (error) {
        console.error('API 连接测试失败:', error);
        return false;
    }
}

/**
 * 显示通知
 */
function showNotification(title, message) {
    chrome.notifications.create({
        type: 'basic',
        iconUrl: 'icons/icon128.png',
        title: title,
        message: message
    });
}

// 监听来自 popup 和 content script 的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'PROCESS_VIDEO') {
        sendTaskToAPI(message.videoInfo)
            .then(result => {
                showNotification('VideoMind Bridge', '任务已提交，处理中...');
                sendResponse({ success: true, taskId: result.id });
            })
            .catch(error => {
                showNotification('任务失败', error.message);
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    if (message.type === 'HEALTH_CHECK') {
        healthCheck()
            .then(ok => {
                sendResponse({ success: true, connected: ok });
            })
            .catch(error => {
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    if (message.type === 'PROCESS_VIDEO_CONTENT') {
        const info = message.videoInfo;
        sendTaskToAPI(info)
            .then(result => {
                sendResponse({ success: true, taskId: result.id, title: result.title });
            })
            .catch(error => {
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    if (message.type === 'CHECK_AI_STATUS') {
        getAPIConfig()
            .then(config => {
                sendResponse({ success: true, ai_enabled: config.ai_enabled });
            })
            .catch(error => {
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    if (message.type === 'GET_CONFIG') {
        getConfig()
            .then(config => {
                sendResponse({ success: true, config: config });
            })
            .catch(error => {
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    if (message.type === 'SET_API_URL') {
        setApiBaseUrl(message.url)
            .then(success => {
                sendResponse({ success: success });
            })
            .catch(error => {
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    if (message.type === 'TEST_API_CONNECTION') {
        testApiConnection(message.url)
            .then(connected => {
                sendResponse({ success: true, connected: connected });
            })
            .catch(error => {
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }
});

// WebSocket 连接管理
let ws = null;
let wsReconnectTimer = null;

async function connectWebSocket() {
    if (ws) {
        ws.close();
    }

    const apiBaseUrl = await getApiBaseUrl();
    const wsUrl = apiBaseUrl.replace('http', 'ws');

    try {
        ws = new WebSocket(`${wsUrl}/ws`);

        ws.onopen = () => {
            console.log('WebSocket 连接已建立');
            if (wsReconnectTimer) {
                clearTimeout(wsReconnectTimer);
                wsReconnectTimer = null;
            }
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'progress') {
                    showNotification(`处理中: ${data.progress}%`, data.current_step || '');
                } else if (data.status === 'completed') {
                    showNotification('完成', '视频处理已完成');
                } else if (data.status === 'failed') {
                    showNotification('错误', data.message || '处理失败');
                }
            } catch (e) {
                // 忽略解析错误
            }
        };

        ws.onerror = () => {
            console.log('WebSocket 连接错误');
        };

        ws.onclose = () => {
            console.log('WebSocket 连接已断开');
            ws = null;
            // 5秒后尝试重连
            if (!wsReconnectTimer) {
                wsReconnectTimer = setTimeout(() => {
                    wsReconnectTimer = null;
                    connectWebSocket();
                }, 5000);
            }
        };
    } catch (e) {
        console.log('WebSocket 连接失败:', e);
    }
}

// 扩展安装或更新时初始化
chrome.runtime.onInstalled.addListener(async (details) => {
    if (details.reason === 'install') {
        // 首次安装，设置默认配置
        await setApiBaseUrl(DEFAULT_API_URL);
        console.log('VideoMind Bridge 扩展已安装');
    } else if (details.reason === 'update') {
        console.log('VideoMind Bridge 扩展已更新');
    }
    
    // 启动 WebSocket 连接
    connectWebSocket();
});

// 启动时连接 WebSocket
connectWebSocket();
