# CLI 参考（2026-11-25，A2 之后）

> 入口：`uv run python -m src.cli`（必须以项目根为 cwd）。
> **v1 的 `--mode` / `--model` / `--mock` / `--targets` / `--timeout` 等参数已删除**，
> 传了会直接被 argparse 拒绝（这是有意的：不要让老脚本「看起来还能跑」）。

## 三种输入

| 输入 | 行为 |
|---|---|
| 远程 URL | 走 v2 引擎：成本感知路由 → 提取（无字幕则 ASR 兜底） |
| 本地文件路径 | **只做转写**：ffmpeg 转 16k wav → ASR 降级链（没有下载、没有 AI 摘要） |
| 不带参数 | 打印用法并退出码 2（没有隐式默认模式） |

## 常用命令

```bash
# 提取正文（JSON 便于 Agent 消费）
uv run python -m src.cli "URL" --json

# 智能模式：先预筛，再按推荐成本档提取
uv run python -m src.cli "URL" --smart --json

# 只做零网络预筛（不下载）
uv run python -m src.cli "URL" --prescreen-only --json

# 提取即归档
uv run python -m src.cli "URL" --archive obsidian,local \
  --obsidian-vault /path/to/vault --json

# 本地文件（手动下载的视频）→ 转写
uv run python -m src.cli ~/Downloads/manual.mp4 --json

# 指定 ASR 链（严格按顺序，失败即失败）
uv run python -m src.cli "URL" --asr-chain sensevoice,faster_whisper --json

# 首发只试某个后端（失败后继续默认链）
uv run python -m src.cli "URL" --asr dashscope --json

# 能力发现
uv run python -m src.cli --list-extractors
uv run python -m src.cli --list-asr

# 提取器 Key 管理
uv run python -m src.cli --config-list
uv run python -m src.cli --config-set tikhub <key>
```

## 参数速查

| 参数 | 说明 |
|---|---|
| `--prescreen` / `-p` | 启用内容预筛 |
| `--smart` / `-s` | 预筛 + 成本感知提取（等价 `--prescreen --cost-tier free`）|
| `--prescreen-only` | 只预筛，不提取 |
| `--cost-tier` | 可接受的最高成本档：`free/cheap/paid/expensive/premium` |
| `--archive` | 提取即归档目标：`obsidian,local,html_player` |
| `--asr` / `--asr-chain` / `--asr-language` | ASR 后端选择与语言提示 |
| `--json` / `--quiet` / `--output-dir` | 输出形态与本地归档目录 |
| `--list-extractors` / `--list-asr` | 能力发现 |
| `--config-list` / `--config-set` | 提取器 Key 管理 |

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 成功（`success=true`） |
| 1 | 提取/转写失败（有 `error`/`error_code`） |
| 2 | 用法错误（缺 URL、非法参数、文件不存在） |
