# VideoMind Bridge — Windows 部署与架构收敛记录

> 记录日期：2026-08-18 · 目标机：Windows 10 (DESKTOP-S4877G0) · ZeroTier: `10.207.251.86`
> 本文档是 Windows 服务器部署、本次修复、架构收敛的完整存档，含维护手册。

---

## 1. 当前架构总览

```
Windows 10 长期挂机 (10.207.251.86) — 执行工作站
├─ VideoMindAPI (8787, SYSTEM+onstart)  视频内容提取服务【本会话部署·核心】
├─ intel-pipeline 计划任务              银发产业情报 (0:00/0:30/1:00/12:00/12:30)
├─ PocketBase (8090)                    数据后端
├─ n8n (5678, 保留)                    流程自动化（当前空转待用）
├─ ZeroTier (9993)                      三端组网（Mac/腾讯云/Windows 同内网）
├─ AweSun 向日葵 (5800/5900)            远程管理
└─ ~~OpenClaw~~                         已停用（进程已停 + 自启已禁用，数据保留 415MB）
```

**三端分工**：Mac(开发+浏览器登录态兜底) / 腾讯云(24/7 agent 中枢 hermes+数据) / Windows(**执行**：视频提取/流水线)。

---

## 2. Windows 部署详情

### 2.1 环境
| 项 | 值 |
|---|---|
| OS | Windows 10 (19045) x64 |
| Python | 3.12.9 (`C:\Users\yihong123\AppData\Local\Programs\Python\Python312`) |
| uv | 0.11.3 |
| ffmpeg | `C:\tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin`（未入系统 PATH，由启动脚本注入） |
| 项目目录 | `C:\services\videomind`（venv: `.venv`, python3.12） |
| Git 远端 | `ssh://git@ssh.github.com:443/yiwenxu123/VideoMind-Bridge.git` |

### 2.2 部署与更新
```bash
# 首次/更新：从 Mac 打包源码（git archive 不含 venv）管道传到 Windows
cd /Users/yiwenxu123/Projects/VideoMind Bridge
git archive HEAD --format=tar | ssh my-windows "mkdir C:\\services\\videomind 2>nul & tar -xf - -C C:\\services\\videomind"

# Windows 装依赖
ssh my-windows "cd /d C:\\services\\videomind && uv sync --python 3.12 --no-dev"
```
> 已修复 `_resolve_ytdlp` 跨平台：Windows venv 可执行目录是 `Scripts`（非 Unix `bin`）。

### 2.3 服务：VideoMindAPI（计划任务）
- 任务名：`VideoMindAPI`，**SYSTEM 身份 + onstart**（开机即启，不依赖登录）
- 启动脚本：`C:\services\videomind\start_api.bat`
```bat
@echo off
set PATH=C:\tools\ffmpeg\ffmpeg-master-latest-win64-gpl\bin;%PATH%
set VIDEOMIND_API_TOKEN=<TOKEN>
set DOUYIN_COOKIES_FILE=C:\services\videomind\cookies\douyin.txt
set VMB_COOKIES_FILE=C:\services\videomind\cookies\douyin.txt
cd /d C:\services\videomind
start /b .venv\Scripts\python.exe -m src.api --host 0.0.0.0 --port 8787 > C:\services\videomind\api.log 2>&1
```
- 管理命令：
```cmd
schtasks /run /tn VideoMindAPI            # 启动
schtasks /end /tn VideoMindAPI            # 停止(需再杀端口)
for /f "tokens=5" %a in ('netstat -ano ^| findstr :8787 ^| findstr LISTENING') do taskkill /F /PID %a
```
> ⚠️ `start /b` 启动的进程随 SSH 会话断开即死。**必须用计划任务/Start-Process 拉起**（独立会话）。

### 2.4 鉴权与入口
- Token：保存在 `start_api.bat`（`VIDEOMIND_API_TOKEN`）
- Swagger：`http://10.207.251.86:8787/docs`
- 数据存储：keyring 在 SSH 会话不可用（CredRead 1312 无害报错）→ **云 key 一律用环境变量**；本地 whisper 免费链路无需任何 key

---

## 3. 抖音登录态（cookies）

- 位置：`C:\services\videomind\cookies\douyin.txt`（Netscape 格式，62 条，含真实登录态）
- 用法：`VMB_COOKIES_FILE`（yt-dlp `--cookies`，服务器场景）优先于 `VMB_COOKIES_BROWSER`（浏览器，桌面场景）
- **有效期数月，过期后重新导出覆盖即可**；频繁过期可上 B2（Playwright 持久化会话自动重登）
- 来源：`www.douyin.com` 用 "Get cookies.txt LOCALLY" 扩展导出

---

## 4. 本次会话完成的修复（已全部 commit+push 到 GitHub）

| Commit | 修复 |
|---|---|
| `c007b5d` | 小红书新短链域名 xhslink.cn（三个提取器 URL 匹配/短链解析） |
| `40610bf` | VMB_COOKIES_BROWSER 浏览器登录态下载 |
| `65d7f4c` | api /extract 放行 CHEAP 本地 whisper（原 FREE 挡住无字幕/抖音兜底） |
| `eaabb8e` | VMB_COOKIES_FILE 服务器 cookies.txt 登录态 |
| `c5c8102` | 抖音文案过短(<120)自动降级 ASR，避免只返回标题 |
| `0dfc93c` | `_resolve_ytdlp` 兼容 Windows venv Scripts 目录 |
| 更早 `1c76b51` | 本地 faster-whisper 默认 ASR + yt-dlp/ffmpeg 路径解析 + 下载免转码 |

**已实测**（Mac→Windows 调用）：B站 897 字全文 / 抖音 982 字全文 / 小红书 67+ 字文案，均走本地 whisper 免费链路。

---

## 5. Windows 架构收敛（OpenClaw 停用 / 调度去重）

### 5.1 发现：两套重复调度
- **Hermes**（腾讯云 `/opt/data/cron/jobs.json`）：三账号选题每日 3:00（content-theme-finder，已跑 129 次）✅ 主
- **OpenClaw**（Windows cron）：panduola 采集 6:00 + 银发 8:00/14:00 → **已全部禁用**（重复）🔴
- **intel-pipeline 系统计划任务**：银发 fetch/filter/report（0:00-1:00、12:00-12:30）✅ 主

### 5.2 OpenClaw 停用记录（2026-08-18）
- 原因：7 agent 中 3 个飞书群会话最后活跃 2026-04 中下旬（>3.5 个月无人用）；近 2 周全部活动=已禁用的 cron；18789 零依赖连接
- 已做：杀 gateway(18789)+ClawPanel(3000)；禁用 `"OpenClaw Gateway"` 计划任务；删 `~/.openclaw/browser`(872MB)；`npm uninstall -g openclaw`(370MB)
- **保留**：`~/.openclaw`(415MB：agents/credentials/skills/cron)；计划任务处于禁用未删除
- **恢复路径**：`schtasks /change /tn "OpenClaw Gateway" /enable` + Start-Process 拉起 gateway.cmd + `npm i -g openclaw`（版本 2026.5.27，凭据需在 gateway.cmd 的 env 中配置）

### 5.3 n8n
- 核查：workflow_entity=0 / execution=0 / 日志"0 drafts, 0 published" → **当前空转**（~290MB）
- 决策：**保留待用**（独立 `n8n-start` 计划任务）
- 70 条 MCP registry 注册残留，无生效工作流

---

## 6. 多 Agent 接入指南

```bash
# 通用 REST 入口（任何 agent）
curl -s -X POST http://10.207.251.86:8787/api/v1/extract \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <VIDEOMIND_API_TOKEN>" \
  -d '{"url":"<B站/抖音/小红书/YouTube链接>"}'
```

| Agent | 接入方式 | 状态 |
|---|---|---|
| DeepSeek Harness | Host Tool 封装 REST（推荐）/ MCP | 可做 |
| hermes | hermes-cli 工具集 curl | 可接 |
| n8n | HTTP Request 节点 / webhook 中转飞书 | 天然支持 |
| OpenClaw | 恢复后配 HTTP 工具 | 需先恢复 |

**已修复的 API 端点**：`GET /health`（无鉴权）、`GET /api/v1/status`、`POST /api/v1/extract`（CHEAP 放行）

---

## 7. 维护手册速查

| 场景 | 命令 |
|---|---|
| 重启服务 | `schtasks /end /tn VideoMindAPI` → 杀 8787 → `schtasks /run /tn VideoMindAPI` |
| 看日志 | `type C:\services\videomind\api.log`（或尾部） |
| 换 token | 改 `start_api.bat` 的 `VIDEOMIND_API_TOKEN` → 重启服务 |
| 换 cookies | 覆盖 `cookies\douyin.txt` → 重启服务 |
| 更新代码 | git archive 传输 → `uv sync` → 重启服务 |
| 抖音报 Fresh cookies | 浏览器登录 → 重导 cookies.txt |
| OpenClaw 恢复 | 见 5.2 |
| 防火墙 | 内网走 ZeroTier 无需配置；公网暴露需先设 token+HTTPS，勿裸奔 0.0.0.0 |

---

## 8. DSH 插件 Token 安全化（2026-08-18）

`extract_video`（@dsh-external/dsh-videomind-extractor）**不再硬编码 token**，
改为从 DSH 启动环境读取。

- 读取：`process.env.VIDEOMIND_API_TOKEN || process.env.VMB_API_TOKEN`
- 已持久化配置（本机）：
  - `/Users/yiwenxu123/.dsh/profiles/web/.env`（DSH boot 会加载）
  - `~/.zshrc`（终端启动的 DSH 生效）
- **生效方式**：重启 DSH 进程后自动可用（env 为进程级；改后需重启/重载插件）
- 未配置时工具返回明确错误提示，不泄露任何凭据
- 插件目录（`/Users/yiwenxu123/Projects/测试/dsh-videomind-extractor`）现已 **git clean、可安全同步/提交**，不含秘钥
