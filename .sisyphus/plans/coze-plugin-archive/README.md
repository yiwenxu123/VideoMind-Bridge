# 自研 Coze 视频解析插件 — 部署与使用

用本项目 (VideoMind Bridge) 替代 coze 第三方视频解析插件, 已实测端到端打通:
B站视频 → 解析/下载音频 → 中转 URL → DashScope paraformer-v2 转录成功。

## 现状 (2026-08-01 已部署)

| 项 | 值 |
|----|----|
| 服务地址 | `http://<PUBLIC_IP>/vmb` (nginx 反代) |
| 服务端口 | 8787 (systemd: `videomind-api`) |
| 部署目录 | `/opt/videomind-bridge` (腾讯云) |
| 媒体目录 | `/var/lib/videomind/media` (音频 24h 自动清理) |
| 接口 | `POST /api/v1/parse` |

## 平台支持状态

| 平台 | 状态 | 说明 |
|------|------|------|
| B站 | ✅ 可用 | 官方 playurl API (绕开云 IP 412 风控), 无需 Cookie |
| 抖音 | ⚠️ 需 Cookie | 云 IP 风控, 需用户登录后导出 cookies.txt |
| 小红书 | ⚠️ 需 Cookie | 同上 |
| YouTube | ❌ 服务器不可达 | 腾讯云国内, 需要代理后可用 |

## 在 coze 中接入 (2 步)

1. **创建插件**: coze.cn → 插件 → 创建 → 粘贴 `docs/coze-plugin/openapi.yaml` (也可 URL 导入)
   - 鉴权: 可配置 Token (对应服务器 `VIDEOMIND_API_TOKEN`), 也可不配 (内网信任)
2. **替换工作流节点**: 原第三方解析插件 → 换成 VideoMind 插件
   - 输入 `url` → 输出 `voice_url` (音频直链)
   - 下游接你自己的 ASR 插件 (DashScope), 工作流其余部分不变

## 抖音/小红书 Cookie 配置 (一次性)

```bash
# Mac 本地 (Chrome 已登录抖音/小红书)
uv run yt-dlp --cookies-from-browser chrome --cookies /tmp/cookies.txt \
  --skip-download -o /dev/null "https://www.douyin.com"

# 上传服务器
scp /tmp/cookies.txt my-server:/opt/videomind-bridge/cookies.txt

# 重启服务 (自动加载)
ssh my-server "systemctl restart videomind-api"
```

之后调用时传 `cookies_file: "cookies.txt"` (相对服务器部署目录) 或省略 (VMB_COOKIES_FILE 环境变量)。

## 维护

| 事件 | 操作 |
|------|------|
| 平台改版导致解析失败 | `ssh my-server "cd /opt/videomind-bridge && uv sync -U"` → 重启服务 |
| 更新代码 | `rsync -az --delete --exclude .venv --exclude .git ... my-server:/opt/videomind-bridge/` |
| 查看日志 | `journalctl -u videomind-api -f` |
| 音频占空间 | 自动清理 (默认 24h), `VMB_AUDIO_MAX_AGE` 可调 |

## 本地开发调试

```bash
VMB_MEDIA_DIR=/tmp/vmb_media uv run python -m src.api  # 本地 8787
curl -X POST http://127.0.0.1:8787/api/v1/parse -H 'Content-Type: application/json' \
  -d '{"url": "https://www.bilibili.com/video/BV1p45v6kEJc"}'
```
