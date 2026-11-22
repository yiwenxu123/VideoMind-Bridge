"""yt-dlp 可执行文件解析（单一入口）。

## 为什么需要单独一个模块

`pyproject.toml` 声明了 `yt-dlp>=2026.7.4`，venv 里也装了对应版本，但代码实际执行的是
**PATH 里的另一个 yt-dlp**。实测本机情况：

| 位置 | 版本 |
|---|---|
| `pyproject.toml` 声明 | `>=2026.7.4` |
| `.venv/bin/yt-dlp`（装了没人用） | `2026.07.04` |
| `/opt/homebrew/bin/yt-dlp`（真正在跑） | `2026.03.13` ← 旧了 4 个月 |

抖音正是最需要跟版的 extractor（平台改版频繁），而它在跑最旧的那份。
根因是解析顺序把 PATH 排在 venv 前面。

## 现在的优先级

1. `VMB_YTDLP_BIN` —— 显式覆盖，给调试和非常规部署留逃生口
2. **项目 venv** —— 与 `pyproject.toml` 声明一致，可复现
3. PATH
4. `~/.local/bin`

venv 优先的理由：项目声明了版本下限，就应该跑项目自己装的那份；让全局安装悄悄
顶替项目依赖，是"版本漂移"类故障最常见的来源。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

YTDLP_CMD = "yt-dlp"


def _venv_candidates() -> list[Path]:
    # src/utils/ytdlp_bin.py → parents[2] 是项目根
    venv_root = Path(__file__).resolve().parents[2] / ".venv"
    return [
        venv_root / sub / name
        for sub in ("bin", "Scripts")
        for name in (YTDLP_CMD, YTDLP_CMD + ".exe")
    ]


def resolve_ytdlp() -> str | None:
    """返回 yt-dlp 可执行文件路径；找不到返回 None。

    纯本地解析，不执行子进程，因此可在任何上下文安全调用。
    """
    override = os.getenv("VMB_YTDLP_BIN", "").strip()
    if override:
        return override

    for candidate in _venv_candidates():
        if candidate.exists():
            return str(candidate)

    found = shutil.which(YTDLP_CMD)
    if found:
        return found

    local = Path.home() / ".local" / "bin" / YTDLP_CMD
    if local.exists():
        return str(local)

    return None


def ytdlp_command() -> str:
    """给 subprocess 用的命令名/路径；解析不到时退回字面量，让调用方报"未安装"。"""
    return resolve_ytdlp() or YTDLP_CMD
