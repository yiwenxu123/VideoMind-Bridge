/**
 * VideoMind Bridge - 内容脚本
 * 在视频页面注入处理按钮
 */

(function() {
  'use strict';

  if (window.videomindInjected) return;
  window.videomindInjected = true;

  const DEFAULT_API_URL = 'http://127.0.0.1:8787';
  const STORAGE_KEY = 'videomind_config';
  let API_BASE_URL = DEFAULT_API_URL;

  async function loadConfig() {
    try {
      const result = await chrome.storage.local.get([STORAGE_KEY]);
      if (result[STORAGE_KEY] && result[STORAGE_KEY].apiBaseUrl) {
        API_BASE_URL = result[STORAGE_KEY].apiBaseUrl;
      }
    } catch (error) {
      console.log('[VideoMind] 加载配置失败:', error);
    }
  }

  function detectPlatform() {
    const hostname = window.location.hostname;
    if (hostname.includes('bilibili.com')) return 'bilibili';
    if (hostname.includes('youtube.com')) return 'youtube';
    if (hostname.includes('douyin.com')) return 'douyin';
    if (hostname.includes('xiaohongshu.com')) return 'xiaohongshu';
    return 'unknown';
  }

  function getVideoInfo() {
    const platform = detectPlatform();
    let url = window.location.href;
    let title = document.title;

    // 处理抖音 URL 格式差异（如 /jingxuan?modal_id=xxx → /video/xxx）
    if (platform === 'douyin') {
      const modalMatch = url.match(/modal_id=(\d+)/);
      const noteMatch = url.match(/\/note\/(\d+)/);
      const shareVideoMatch = url.match(/\/share\/video\/(\d+)/);
      const videoMatch = url.match(/\/video\/(\d+)/);
      const videoId = modalMatch?.[1] || noteMatch?.[1] || shareVideoMatch?.[1] || videoMatch?.[1];
      if (videoId && !videoMatch) {
        url = `https://www.douyin.com/video/${videoId}`;
      }
    }

    try {
      switch (platform) {
        case 'bilibili':
          const biliTitle = document.querySelector('h1.video-title, h1.title');
          if (biliTitle) title = biliTitle.textContent.trim();
          break;
        case 'youtube':
          const ytTitle = document.querySelector('h1.title.ytd-video-primary-info-renderer, h1.style-scope.ytd-watch-metadata');
          if (ytTitle) title = ytTitle.textContent.trim();
          break;
        case 'douyin':
          const dyTitle = document.querySelector('.title, [data-e2e="video-desc"]');
          if (dyTitle) title = dyTitle.textContent.trim();
          break;
        case 'xiaohongshu':
          const xhsTitle = document.querySelector('.title, .note-content');
          if (xhsTitle) title = xhsTitle.textContent.trim().substring(0, 50);
          break;
      }
    } catch (e) {
      console.log('[VideoMind] 获取标题失败', e);
    }

    return { platform, url, title };
  }

  function createProcessButton() {
    const existingBtn = document.getElementById('videomind-process-btn');
    if (existingBtn) return;

    const button = document.createElement('div');
    button.id = 'videomind-process-btn';
    button.innerHTML = `
      <span class="vm-icon">📝</span>
      <span class="vm-text">处理视频</span>
    `;

    button.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const videoInfo = getVideoInfo();

      button.classList.add('vm-processing');
      button.querySelector('.vm-text').textContent = '连接中...';

      // 通过 background service worker 进行网络请求（绕过 CSP/Private Network Access 限制）
      chrome.runtime.sendMessage({ type: 'HEALTH_CHECK' }, (response) => {
        if (!response || !response.success || !response.connected) {
          button.classList.remove('vm-processing');
          button.classList.add('vm-error');
          button.querySelector('.vm-text').textContent = '服务未运行';
          button.querySelector('.vm-icon').textContent = '❌';
          setTimeout(() => {
            button.classList.remove('vm-error');
            button.querySelector('.vm-text').textContent = '处理视频';
            button.querySelector('.vm-icon').textContent = '📝';
          }, 5000);
          return;
        }

        button.querySelector('.vm-text').textContent = '提交中...';

        chrome.runtime.sendMessage({
          type: 'PROCESS_VIDEO_CONTENT',
          videoInfo: {
            url: videoInfo.url,
            mode: 'full',
            targets: ['local', 'obsidian'],
            cookies_from_browser: 'chrome',
          }
        }, (response) => {
          if (response && response.success) {
            button.classList.remove('vm-processing');
            button.classList.add('vm-success');
            button.querySelector('.vm-text').textContent = '已提交';
            button.querySelector('.vm-icon').textContent = '✅';

            showNotification(`任务已创建: ${response.title || '视频处理'}`, 'success');

            chrome.storage.local.set({
              [`task_${response.taskId}`]: {
                id: response.taskId,
                url: videoInfo.url,
                title: response.title || videoInfo.title,
                platform: videoInfo.platform,
                status: 'pending',
                created_at: new Date().toISOString()
              }
            });

            setTimeout(() => {
              button.classList.remove('vm-success');
              button.querySelector('.vm-text').textContent = '处理视频';
              button.querySelector('.vm-icon').textContent = '📝';
            }, 8000);
          } else {
            button.classList.remove('vm-processing');
            button.classList.add('vm-error');
            button.querySelector('.vm-text').textContent = '失败';
            button.querySelector('.vm-icon').textContent = '❌';

            showNotification(`错误: ${(response && response.error) || '提交失败'}`, 'error');

            setTimeout(() => {
              button.classList.remove('vm-error');
              button.querySelector('.vm-text').textContent = '处理视频';
              button.querySelector('.vm-icon').textContent = '📝';
            }, 8000);
          }
        });
      });
    });

    document.body.appendChild(button);
  }

  function showNotification(message, type = 'success') {
    const existing = document.getElementById('videomind-notification');
    if (existing) existing.remove();

    const notification = document.createElement('div');
    notification.id = 'videomind-notification';
    notification.className = `vm-notification vm-${type}`;
    notification.innerHTML = `
      <span class="vm-notification-icon">${type === 'success' ? '✅' : '❌'}</span>
      <span class="vm-notification-text">${message}</span>
    `;

    document.body.appendChild(notification);

    requestAnimationFrame(() => {
      notification.classList.add('vm-show');
    });

    setTimeout(() => {
      notification.classList.remove('vm-show');
      setTimeout(() => notification.remove(), 300);
    }, 5000);
  }

  async function init() {
    await loadConfig();

    setTimeout(() => {
      createProcessButton();
    }, 1500);

    let lastUrl = location.href;
    new MutationObserver(() => {
      const url = location.href;
      if (url !== lastUrl) {
        lastUrl = url;
        setTimeout(() => {
          const existingBtn = document.getElementById('videomind-process-btn');
          if (existingBtn) existingBtn.remove();
          createProcessButton();
        }, 1500);
      }
    }).observe(document, { subtree: true, childList: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
