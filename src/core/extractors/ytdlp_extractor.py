"""yt-dlp 兜底提取器

使用 yt-dlp 获取字幕/元信息。三级降级:
1. 自动字幕 (--write-auto-sub)
2. 手动字幕 (--write-sub, --sub-lang all)
3. 纯元信息 (标题/描述/时长)

复用项目现有的 yt-dlp 依赖。
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ..models import CostTier, ExtractResult
from . import register_extractor
from .base import ContentExtractor

# yt-dlp 可执行路径
_YTDLP_CMD = "yt-dlp"

# 支持的平台
_SUPPORTED_PLATFORMS = [
    "youtube", "bilibili", "douyin", "xiaohongshu",
    "twitter", "x.com", "tiktok", "instagram", "ted",
]


class YtDlpExtractor(ContentExtractor):
    """yt-dlp 兜底提取器

    三级降级:
    1. 自动字幕 (auto-subs)
    2. 手动字幕 (manual subs)
    3. 纯元信息 (title/description/duration)
    """

    platform_name = "ytdlp"
    _cost_tier = CostTier.FREE

    # 匹配常见的视频 URL
    url_pattern = re.compile(
        r"(youtube\.com|youtu\.be|bilibili\.com|b23\.tv|"
        r"douyin\.com|iesdouyin\.com|xiaohongshu\.com|xhslink\.(?:com|cn)|"
        r"twitter\.com|x\.com|tiktok\.com|instagram\.com|ted\.com)"
    )

    def __init__(self) -> None:
        self._available: bool | None = None

    def is_available(self) -> bool:
        """检查 yt-dlp 是否可执行"""
        if self._available is not None:
            return self._available
        try:
            result = subprocess.run(
                [_YTDLP_CMD, "--version"],
                capture_output=True, text=True, timeout=10.0,
            )
            self._available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False
        return self._available

    def extract(self, url: str) -> ExtractResult:
        if not self.is_available():
            return ExtractResult(
                success=False, platform="ytdlp", title="", content="",
                source="ytdlp", url=url, cost_tier=CostTier.FREE,
                error="yt-dlp 未安装 (pip install yt-dlp)",
            )

        # 三级降级
        content, segments, language, metadata = self._try_extract(url)

        if not content and not metadata.get("title"):
            return ExtractResult(
                success=False, platform="ytdlp", title="", content="",
                source="ytdlp", url=url, cost_tier=CostTier.FREE,
                error=f"yt-dlp 无法提取任何内容: {url}",
            )

        title = metadata.get("title", "未知视频")
        duration = metadata.get("duration", 0)

        if not content:
            # 降级到纯元信息 (标记占位: 非完整内容, 路由层据此继续降级)
            content = (
                f"[{metadata.get('platform', '视频')}] {title}\n"
                f"时长: {duration}秒\n"
                f"描述: {metadata.get('description', '无')}\n"
            )
            return ExtractResult(
                success=True,
                platform=metadata.get("platform", "video"),
                title=title,
                content=content,
                source="ytdlp",
                url=url,
                cost_tier=CostTier.FREE,
                duration_seconds=float(duration),
                language=language,
                segments=segments,
                metadata=metadata,
                is_placeholder=True,
                error="yt-dlp 未找到字幕, 仅返回元信息 (标题/描述), 内容不完整",
            )

        return ExtractResult(
            success=True,
            platform=metadata.get("platform", "video"),
            title=title,
            content=content,
            source="ytdlp",
            url=url,
            cost_tier=CostTier.FREE,
            duration_seconds=float(duration),
            language=language,
            segments=segments,
            metadata=metadata,
        )

    def _try_extract(self, url: str) -> tuple[str, list, str | None, dict[str, Any]]:
        """三级降级提取

        Returns:
            (content_text, segments, language, metadata)
        """
        # 第一级: 自动字幕
        content, segments, lang, meta = self._extract_with_subs(url, auto=True)
        if content:
            return content, segments, lang, meta

        # 第二级: 手动字幕
        content, segments, lang, meta = self._extract_with_subs(url, auto=False)
        if content:
            return content, segments, lang, meta

        # 第三级: 纯元信息
        meta = self._extract_metadata(url)
        return "", [], None, meta

    def _extract_with_subs(
        self, url: str, auto: bool = True,
    ) -> tuple[str, list[dict[str, Any]], str | None, dict[str, Any]]:
        """下载并提取字幕"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_template = str(Path(tmp_dir) / "%(id)s.%(ext)s")

            cmd = [
                _YTDLP_CMD,
                "--skip-download",       # 只下载字幕
                "--print", "after_video:{}",  # JSON 输出元信息
                "--convert-subs", "srt",  # 统一转为 SRT
                url,
            ]

            if auto:
                cmd.extend(["--write-auto-sub", "--sub-langs", "all"])
            else:
                cmd.extend(["--write-sub", "--sub-langs", "all"])

            # 避免下载视频
            cmd.extend(["--output", output_template])

            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120.0,
                )

                if result.returncode != 0:
                    return "", [], None, {}

                # 解析元信息 (最后一行 JSON)
                lines = result.stdout.strip().split("\n")
                metadata = {}
                for line in reversed(lines):
                    line = line.strip()
                    if line and line.startswith("{"):
                        try:
                            metadata = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue

                # 查找字幕文件
                srt_files = list(Path(tmp_dir).glob("*.srt"))
                if not srt_files:
                    # 尝试 vtt
                    srt_files = list(Path(tmp_dir).glob("*.vtt"))

                if not srt_files:
                    return "", [], None, metadata

                # 读取字幕
                srt_path = srt_files[0]
                srt_text = srt_path.read_text(encoding="utf-8", errors="replace")

                # 解析字幕语言 (从文件名推断)
                lang = None
                for part in srt_path.stem.split("."):
                    if part in ("zh-Hans", "zh-CN", "zh", "en", "ja", "ko"):
                        lang = part
                        break

                # 提取纯文本 (去除时间轴)
                text_parts: list[str] = []
                segments: list[dict[str, Any]] = []

                for block in srt_text.strip().split("\n\n"):
                    lines_block = block.strip().split("\n")
                    if len(lines_block) >= 3:
                        # SRT: 序号 | 时间轴 | 文本
                        time_line = lines_block[1]
                        text = " ".join(lines_block[2:]).strip()
                        if text:
                            text_parts.append(text)
                            # 解析时间
                            time_match = re.match(
                                r"(\d+):(\d+):(\d+)[.,]\d+",
                                time_line,
                            )
                            start_sec = 0
                            if time_match:
                                h, m, s = map(int, time_match.groups())
                                start_sec = h * 3600 + m * 60 + s
                            segments.append({
                                "start": start_sec,
                                "text": text,
                            })

                full_text = "\n".join(text_parts)
                return full_text, segments, lang, metadata

            except (subprocess.TimeoutExpired, FileNotFoundError):
                return "", [], None, {}

    def _extract_metadata(self, url: str) -> dict[str, Any]:
        """只提取元信息 (不使用字幕)"""
        cmd = [
            _YTDLP_CMD,
            "--dump-json",
            "--skip-download",
            url,
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30.0,
            )
            if result.returncode == 0:
                line = result.stdout.strip().split("\n")[0]
                if line.startswith("{"):
                    return dict(json.loads(line))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return {}


register_extractor("ytdlp", YtDlpExtractor)
