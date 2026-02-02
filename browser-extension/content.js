/**
 * VideoMind Bridge - 内容脚本
 * 在视频页面注入处理按钮
 */

(function() {
  'use strict';

  // 防止重复注入
  if (window.videomindInjected) return;
  window.videomindInjected = true;

  const API_BASE_URL = 'http://127.0.0.1:8787';

  // 平台检测
  function detectPlatform() {
    const hostname = window.location.hostname;
    if (hostname.includes('bilibili.com')) return 'bilibili';
    if (hostname.includes('youtube.com')) return 'youtube';
    if (hostname.includes('douyin.com')) return 'douyin';
    if (hostname.includes('xiaohongshu.com')) return 'xiaohongshu';
    return 'unknown';
  }

  // 获取视频信息
  function getVideoInfo() {
    const platform = detectPlatform();
    const url = window.location.href;
    let title = document.title;

    // 尝试获取更准确的标题
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
      console.log('VideoMind: 获取标题失败', e);
    }

    return { platform, url, title };
  }

  // 创建处理按钮
  function createProcessButton() {
    const existingBtn = document.getElementById('videomind-process-btn');
    if (existingBtn) return;

    const button = document.createElement('div');
    button.id = 'videomind-process-btn';
    button.innerHTML = `
      <span class="vm-icon">📝</span>
      <span class="vm-text">处理视频</span>
    `;

    // 点击事件
    button.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();

      const videoInfo = getVideoInfo();

      // 检查API服务是否可用
      try {
        const healthCheck = await fetch(`${API_BASE_URL}/health`, {
          method: 'GET',
          signal: AbortSignal.timeout(3000)
        });

        if (!healthCheck.ok) {
          showNotification('VideoMind服务未启动，请先运行: python -m src.api', 'error');
          return;
        }
      } catch (error) {
        showNotification('无法连接到VideoMind服务，请确保服务已启动', 'error');
        return;
      }

      // 更新按钮状态
      button.classList.add('vm-processing');
      button.querySelector('.vm-text').textContent = '提交中...';

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/tasks`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            url: videoInfo.url,
            mode: 'full',
            targets: ['local', 'obsidian']
          })
        });

        const data = await response.json();

        if (response.ok) {
          button.classList.remove('vm-processing');
          button.classList.add('vm-success');
          button.querySelector('.vm-text').textContent = '已提交';
          button.querySelector('.vm-icon').textContent = '✅';

          showNotification(`任务已创建: ${data.title || '视频处理'}`, 'success');

          // 存储任务信息
          chrome.storage.local.set({
            [`task_${data.id}`]: {
              id: data.id,
              url: videoInfo.url,
              title: data.title || videoInfo.title,
              platform: videoInfo.platform,
              status: data.status,
              created_at: new Date().toISOString()
            }
          });

          // 3秒后恢复按钮
          setTimeout(() => {
            button.classList.remove('vm-success');
            button.querySelector('.vm-text').textContent = '处理视频';
            button.querySelector('.vm-icon').textContent = '📝';
          }, 3000);
        } else {
          throw new Error(data.detail || '提交失败');
        }
      } catch (error) {
        button.classList.remove('vm-processing');
        button.classList.add('vm-error');
        button.querySelector('.vm-text').textContent = '失败';
        button.querySelector('.vm-icon').textContent = '❌';

        showNotification(`错误: ${error.message}`, 'error');

        setTimeout(() => {
          button.classList.remove('vm-error');
          button.querySelector('.vm-text').textContent = '处理视频';
          button.querySelector('.vm-icon').textContent = '📝';
        }, 3000);
      }
    });

    document.body.appendChild(button);
  }

  // 显示通知
  function showNotification(message, type = 'success') {
    // 移除现有通知
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

    // 动画进入
    requestAnimationFrame(() => {
      notification.classList.add('vm-show');
    });

    // 5秒后自动移除
    setTimeout(() => {
      notification.classList.remove('vm-show');
      setTimeout(() => notification.remove(), 300);
    }, 5000);
  }

  // 初始化
  function init() {
    // 延迟注入，等待页面加载完成
    setTimeout(() => {
      createProcessButton();
    }, 1500);

    // 监听URL变化（SPA页面）
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

  // 页面加载完成后初始化
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
