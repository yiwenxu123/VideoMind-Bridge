# VideoMind Bridge 浏览器扩展

浏览器扩展，让你在视频页面一键处理视频到 VideoMind Bridge。

## 功能特性

- 🎯 **一键处理** - 在视频页面点击浮动按钮即可提交处理
- 📱 **多平台支持** - 支持 B站、YouTube、抖音、小红书
- 🔔 **实时通知** - 提交成功/失败即时显示通知
- 📋 **任务管理** - 扩展弹窗查看最近任务列表
- 🔄 **自动检测** - 自动检测页面视频并显示处理按钮
- ⚙️ **可配置** - 支持自定义 API 服务地址

## 快速开始

### 1. 启动 API 服务

在使用扩展前，必须先启动 VideoMind Bridge 的 API 服务：

```bash
cd "/Users/yiwenxu123/Projects/VideoMind Bridge"

# 方式一：使用 main.py（推荐）
python main.py --api

# 方式二：指定端口
python main.py --api --port 9000

# 方式三：直接启动模块
python -m src.api
```

服务启动后会监听 `http://127.0.0.1:8787`（默认端口）

### 2. 安装浏览器扩展

#### Chrome / Edge

1. 打开 Chrome 扩展管理页面：`chrome://extensions/`
2. 开启右上角的"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择 `browser-extension` 文件夹
5. 扩展图标会出现在工具栏

#### Firefox

1. 打开 Firefox 扩展调试页面：`about:debugging`
2. 点击"此 Firefox"
3. 点击"临时载入附加组件"
4. 选择 `browser-extension/manifest.json`

### 3. 使用扩展

#### 方法一：页面浮动按钮

1. 打开任意支持平台的视频页面
2. 等待页面加载完成（约1.5秒）
3. 右下角会出现蓝色"📝 处理视频"按钮
4. 点击按钮提交处理
5. 等待处理完成通知

#### 方法二：扩展弹窗

1. 点击浏览器工具栏的扩展图标
2. 查看当前页面信息和服务状态
3. 选择处理模式（完整处理/仅下载/仅转录）
4. 点击"开始处理"按钮
5. 查看最近任务列表和进度

## 配置 API 地址

如果 API 服务运行在非默认端口，可以通过浏览器控制台配置：

```javascript
// 打开浏览器控制台（F12），执行以下命令
chrome.storage.local.set({
  videomind_config: {
    apiBaseUrl: 'http://127.0.0.1:9000'
  }
});

// 验证配置
chrome.storage.local.get(['videomind_config'], (result) => {
  console.log('当前配置:', result);
});
```

或者通过 background.js 的消息接口：

```javascript
// 在控制台执行
chrome.runtime.sendMessage(
  { type: 'SET_API_URL', url: 'http://127.0.0.1:9000' },
  (response) => console.log('配置结果:', response)
);
```

## 工作流程

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   浏览器扩展     │────▶│  VideoMind API   │────▶│   任务处理器     │
│  (content.js)   │     │  (127.0.0.1:8787)│     │  (task_manager) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                                               │
        │                                               ▼
        │                                        ┌─────────────────┐
        │                                        │   下载视频      │
        │                                        │   语音转录      │
        │                                        │   AI摘要生成    │
        │                                        │   导出文件      │
        │                                        └─────────────────┘
        │                                               │
        └◀──────────────────────────────────────────────┘
                    WebSocket 实时进度推送
```

## 文件说明

```
browser-extension/
├── manifest.json      # 扩展配置文件（Manifest V3）
├── content.js         # 内容脚本（注入视频页面）
├── content.css        # 内容脚本样式
├── popup.html         # 扩展弹窗页面
├── popup.js           # 弹窗逻辑
├── background.js      # 后台服务（Service Worker）
├── icons/             # 扩展图标
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md          # 使用说明
```

## 支持的网站

| 平台 | URL 模式 | 状态 |
|------|---------|------|
| Bilibili | `*.bilibili.com/video/*` | ✅ 支持 |
| YouTube | `*.youtube.com/watch*` | ✅ 支持 |
| 抖音 | `*.douyin.com/video/*` | ✅ 支持 |
| 小红书 | `*.xiaohongshu.com/explore/*` | ✅ 支持 |

## 处理模式说明

| 模式 | 说明 | 输出 |
|------|------|------|
| 完整处理 | 下载 → 转录 → AI摘要 → 导出 | 摘要文件 + 带播放器页面 |
| 仅下载 | 只下载视频和音频 | 视频文件 + 音频文件 |
| 仅转录 | 下载音频 → 转录 | 字幕文件（SRT/TXT） |

## 常见问题

### Q: 扩展显示"无法连接到服务"

**A:** 请确保：
1. 已运行 `python main.py --api` 启动 API 服务
2. 服务监听在正确的端口（默认 8787）
3. 浏览器没有阻止本地连接
4. 检查防火墙设置

### Q: 视频页面没有显示处理按钮

**A:** 
1. 刷新页面等待 1-2 秒
2. 检查 URL 是否在支持列表中
3. 查看浏览器控制台是否有错误
4. 确认扩展已正确加载

### Q: 提交任务后没有反应

**A:**
1. 检查 API 服务是否正常运行
2. 查看浏览器控制台的网络请求
3. 确认视频链接格式正确
4. 检查 API 服务日志

### Q: 如何修改 API 服务端口

**A:**
1. 启动服务时指定端口：`python main.py --api --port 9000`
2. 在扩展中配置新地址（见上方"配置 API 地址"）

### Q: AI 摘要功能显示"需要 AI Key"

**A:**
1. 在 VideoMind Bridge GUI 中配置 AI API Key
2. 或设置环境变量 `DEEPSEEK_API_KEY`
3. 配置后重启 API 服务

## 开发计划

- [ ] 添加 Firefox 正式版支持
- [ ] 添加 Safari 扩展支持
- [ ] 支持更多视频平台
- [ ] 添加批量处理功能
- [ ] 添加任务进度实时显示
- [ ] 添加扩展内设置页面

## 技术细节

### API 通信

扩展通过 `fetch` API 与本地服务通信：

```javascript
// 健康检查
fetch('http://127.0.0.1:8787/health')

// 创建任务
fetch('http://127.0.0.1:8787/api/v1/tasks', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    url: '视频链接',
    mode: 'full',
    targets: ['local', 'obsidian']
  })
})

// 获取任务列表
fetch('http://127.0.0.1:8787/api/v1/tasks')

// WebSocket 进度订阅
const ws = new WebSocket('ws://127.0.0.1:8787/ws');
ws.send(JSON.stringify({ action: 'subscribe', task_id: 'xxx' }));
```

### 安全说明

- 扩展只访问本地服务地址（`127.0.0.1`/`localhost`）
- 不收集任何用户数据
- 不修改视频页面核心功能
- API Key 存储在本地密钥环中，不上传

### Manifest V3 说明

本扩展使用 Manifest V3 规范：
- 使用 Service Worker 替代 Background Page
- 使用 `chrome.storage.local` 存储配置
- 权限最小化原则

## 许可证

MIT License
