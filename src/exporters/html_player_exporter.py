"""HTML 播放器导出器 - 生成本地可交互的播放器页面"""

import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

from .base import BaseExporter
from ..models.task import ExportContext, ExportResult, ExportTarget
from ..services.ai_service import Highlight


class HTMLPlayerExporter(BaseExporter):
    """
    HTML 播放器导出器

    生成独立的 HTML 文件，包含:
    - 视频播放器
    - 可点击的时间轴
    - 同步显示的字幕
    - 元数据展示

    特性:
    - 无需外部依赖，双击即可在浏览器打开
    - 点击时间轴跳转到对应位置
    - 点击字幕跳转到对应位置
    - 当前播放位置高亮对应时间轴和字幕
    """

    name = "HTML 播放器"
    icon = "🎬"

    def __init__(self):
        pass

    def validate_config(self) -> Tuple[bool, str]:
        """验证配置 - 此导出器无需特殊配置"""
        return True, ""

    def export(self, context: ExportContext) -> ExportResult:
        """
        生成 HTML 播放器页面

        输出文件:
        - player.html: 独立的播放器页面
        """
        output_dir: Optional[Path] = None
        if context.video_path:
            output_dir = context.video_path.parent
        elif context.audio_path:
            output_dir = context.audio_path.parent
        if not output_dir:
            return ExportResult(
                success=False,
                target=ExportTarget.LOCAL,
                error_msg="未找到输出目录"
            )

        # 生成文件名
        safe_title = self._sanitize_filename(context.video_metadata.title)
        player_path = output_dir / "player.html"

        # 准备数据
        video_filename = context.video_path.name if context.video_path else ""
        audio_filename = context.audio_path.name if context.audio_path else ""

        # 获取时间轴数据
        highlights = self._extract_highlights_from_context(context)

        # 获取字幕数据
        subtitles = self._extract_subtitles_from_context(context)

        # 生成 HTML 内容
        html_content = self._generate_html(
            metadata=context.video_metadata,
            video_filename=video_filename,
            audio_filename=audio_filename,
            highlights=highlights,
            subtitles=subtitles,
            summary=context.ai_summary or ""
        )

        # 写入文件
        player_path.write_text(html_content, encoding="utf-8")

        return ExportResult(
            success=True,
            target=ExportTarget.LOCAL,
            output_path=player_path,
            metadata={"type": "html_player"}
        )

    def _sanitize_filename(self, title: str) -> str:
        """安全化文件名"""
        illegal_chars = '<>:"/\\|?*'
        for char in illegal_chars:
            title = title.replace(char, '_')
        return title[:100] if title else "untitled"

    def _extract_highlights_from_context(self, context: ExportContext) -> List[Highlight]:
        """从 ExportContext 提取时间轴数据"""
        highlights_data = context.config.get("highlights", [])
        highlights = []
        for h in highlights_data:
            if isinstance(h, dict):
                highlights.append(Highlight(
                    time=h.get("time", "00:00:00"),
                    seconds=h.get("seconds", 0),
                    content=h.get("content", "")
                ))
        return highlights

    def _extract_subtitles_from_context(self, context: ExportContext) -> List[dict]:
        """从 ExportContext 提取字幕数据"""
        subtitles = []
        for seg in context.transcript_segments:
            subtitles.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "start_formatted": self._format_time(seg.start)
            })
        return subtitles

    @staticmethod
    def _format_time(seconds: float) -> str:
        """格式化为时间字符串 MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    def _generate_html(
        self,
        metadata,
        video_filename: str,
        audio_filename: str,
        highlights: List[Highlight],
        subtitles: List[dict],
        summary: str
    ) -> str:
        """生成完整的 HTML 播放器页面"""

        # 准备 JSON 数据
        highlights_json = json.dumps([
            {"time": h.time, "seconds": h.seconds, "content": h.content}
            for h in highlights
        ], ensure_ascii=False)

        subtitles_json = json.dumps(subtitles, ensure_ascii=False)

        # 对 HTML 中的动态内容进行转义，防止 XSS
        safe_title = html.escape(metadata.title)
        safe_author = html.escape(metadata.author)
        safe_platform = html.escape(metadata.platform)
        safe_summary = html.escape(summary)

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_title} - VideoMind Player</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #1a1a1a;
            color: #e0e0e0;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        /* 头部信息 */
        .header {{
            margin-bottom: 20px;
            padding-bottom: 20px;
            border-bottom: 1px solid #333;
        }}

        .title {{
            font-size: 24px;
            font-weight: 600;
            color: #fff;
            margin-bottom: 10px;
        }}

        .meta {{
            font-size: 14px;
            color: #888;
        }}

        .meta span {{
            margin-right: 20px;
        }}

        /* 视频区域 */
        .video-section {{
            margin-bottom: 20px;
        }}

        .video-container {{
            position: relative;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
        }}

        video {{
            width: 100%;
            height: auto;
            display: block;
        }}

        /* 内容网格 */
        .content-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}

        @media (max-width: 768px) {{
            .content-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        /* 卡片样式 */
        .card {{
            background: #252525;
            border-radius: 8px;
            padding: 20px;
        }}

        .card-title {{
            font-size: 16px;
            font-weight: 600;
            color: #fff;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #333;
        }}

        /* 摘要 */
        .summary {{
            font-size: 14px;
            color: #ccc;
            line-height: 1.8;
        }}

        /* 时间轴 */
        .highlights {{
            max-height: 400px;
            overflow-y: auto;
        }}

        .highlight-item {{
            display: flex;
            align-items: flex-start;
            padding: 12px;
            margin-bottom: 8px;
            background: #2a2a2a;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .highlight-item:hover {{
            background: #333;
        }}

        .highlight-item.active {{
            background: #0066cc;
        }}

        .highlight-time {{
            font-family: "SF Mono", Monaco, monospace;
            font-size: 13px;
            color: #4a9eff;
            min-width: 60px;
            margin-right: 12px;
        }}

        .highlight-item.active .highlight-time {{
            color: #fff;
        }}

        .highlight-content {{
            font-size: 14px;
            color: #e0e0e0;
            flex: 1;
        }}

        /* 字幕 */
        .subtitles {{
            max-height: 400px;
            overflow-y: auto;
        }}

        .subtitle-item {{
            display: flex;
            align-items: flex-start;
            padding: 10px 12px;
            margin-bottom: 4px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .subtitle-item:hover {{
            background: #2a2a2a;
        }}

        .subtitle-item.active {{
            background: #0066cc;
        }}

        .subtitle-time {{
            font-family: "SF Mono", Monaco, monospace;
            font-size: 12px;
            color: #666;
            min-width: 50px;
            margin-right: 10px;
        }}

        .subtitle-item.active .subtitle-time {{
            color: #fff;
        }}

        .subtitle-text {{
            font-size: 14px;
            color: #ccc;
            flex: 1;
        }}

        .subtitle-item.active .subtitle-text {{
            color: #fff;
        }}

        /* 提示 */
        .tips {{
            margin-top: 20px;
            padding: 15px;
            background: #1e3a5f;
            border-radius: 8px;
            font-size: 13px;
            color: #7eb8ff;
        }}

        .tips strong {{
            color: #fff;
        }}

        /* 滚动条 */
        ::-webkit-scrollbar {{
            width: 8px;
        }}

        ::-webkit-scrollbar-track {{
            background: #1a1a1a;
        }}

        ::-webkit-scrollbar-thumb {{
            background: #444;
            border-radius: 4px;
        }}

        ::-webkit-scrollbar-thumb:hover {{
            background: #555;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部信息 -->
        <div class="header">
            <h1 class="title">{safe_title}</h1>
            <div class="meta">
                <span>👤 {safe_author}</span>
                <span>⏱️ {metadata.duration // 60}分{metadata.duration % 60}秒</span>
                <span>📺 {safe_platform}</span>
            </div>
        </div>

        <!-- 视频播放器 -->
        <div class="video-section">
            <div class="video-container">
                <video id="videoPlayer" controls>
                    <source src="{video_filename}" type="video/mp4">
                    您的浏览器不支持视频播放。
                </video>
            </div>
        </div>

        <!-- 内容区域 -->
        <div class="content-grid">
            <!-- 左侧：摘要 + 时间轴 -->
            <div>
                <!-- 摘要 -->
                <div class="card" style="margin-bottom: 20px;">
                    <div class="card-title">📝 AI 摘要</div>
                    <div class="summary">{safe_summary or "暂无摘要"}</div>
                </div>

                <!-- 时间轴 -->
                <div class="card">
                    <div class="card-title">🎯 关键时间轴</div>
                    <div class="highlights" id="highlights">
                        <!-- 动态生成 -->
                    </div>
                </div>
            </div>

            <!-- 右侧：字幕 -->
            <div class="card">
                <div class="card-title">💬 字幕</div>
                <div class="subtitles" id="subtitles">
                    <!-- 动态生成 -->
                </div>
            </div>
        </div>

        <!-- 提示 -->
        <div class="tips">
            <strong>💡 使用提示：</strong><br>
            • 点击时间轴或字幕可跳转到对应位置<br>
            • 播放时当前时间轴和字幕会自动高亮<br>
            • 支持键盘快捷键：空格键播放/暂停，方向键快进/快退
        </div>
    </div>

    <script>
        // 数据
        const highlights = {highlights_json};
        const subtitles = {subtitles_json};

        // DOM 元素
        const video = document.getElementById('videoPlayer');
        const highlightsContainer = document.getElementById('highlights');
        const subtitlesContainer = document.getElementById('subtitles');

        // 生成时间轴
        function renderHighlights() {{
            highlightsContainer.innerHTML = highlights.map((h, index) => `
                <div class="highlight-item" data-time="${{h.seconds}}" data-index="${{index}}">
                    <span class="highlight-time">${{h.time}}</span>
                    <span class="highlight-content">${{h.content}}</span>
                </div>
            `).join('');

            // 绑定点击事件
            highlightsContainer.querySelectorAll('.highlight-item').forEach(item => {{
                item.addEventListener('click', () => {{
                    const time = parseFloat(item.dataset.time);
                    video.currentTime = time;
                    video.play();
                }});
            }});
        }}

        // 生成字幕
        function renderSubtitles() {{
            subtitlesContainer.innerHTML = subtitles.map((s, index) => `
                <div class="subtitle-item" data-start="${{s.start}}" data-end="${{s.end}}" data-index="${{index}}">
                    <span class="subtitle-time">${{s.start_formatted}}</span>
                    <span class="subtitle-text">${{s.text}}</span>
                </div>
            `).join('');

            // 绑定点击事件
            subtitlesContainer.querySelectorAll('.subtitle-item').forEach(item => {{
                item.addEventListener('click', () => {{
                    const start = parseFloat(item.dataset.start);
                    video.currentTime = start;
                    video.play();
                }});
            }});
        }}

        // 更新当前播放位置高亮
        function updateActiveItems() {{
            const currentTime = video.currentTime;

            // 更新时间轴高亮
            highlightsContainer.querySelectorAll('.highlight-item').forEach(item => {{
                item.classList.remove('active');
            }});

            // 找到当前时间对应的时间轴
            for (let i = highlights.length - 1; i >= 0; i--) {{
                if (currentTime >= highlights[i].seconds) {{
                    const activeItem = highlightsContainer.querySelector(`[data-index="${{i}}"]`);
                    if (activeItem) {{
                        activeItem.classList.add('active');
                        activeItem.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }}
                    break;
                }}
            }}

            // 更新字幕高亮
            subtitlesContainer.querySelectorAll('.subtitle-item').forEach(item => {{
                item.classList.remove('active');
                const start = parseFloat(item.dataset.start);
                const end = parseFloat(item.dataset.end);
                if (currentTime >= start && currentTime < end) {{
                    item.classList.add('active');
                    item.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            }});
        }}

        // 监听播放进度
        video.addEventListener('timeupdate', updateActiveItems);

        // 初始化
        renderHighlights();
        renderSubtitles();
    </script>
</body>
</html>"""

        return html_content


# 测试代码
if __name__ == "__main__":
    import sys
    from pathlib import Path
    from uuid import uuid4

    from ..models.task import VideoMetadata, ExportContext, TranscriptSegment

    # 创建测试上下文
    context = ExportContext(
        task_id=uuid4(),
        video_metadata=VideoMetadata(
            title="测试视频标题",
            author="测试UP主",
            duration=180,
            platform="bilibili",
            url="https://test.com/video"
        ),
        video_path=Path("./test_video.mp4"),
        audio_path=Path("./test_audio.m4a"),
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="这是第一句字幕"),
            TranscriptSegment(start=5, end=10, text="这是第二句字幕"),
            TranscriptSegment(start=90, end=95, text="这是1分30秒的字幕"),
        ],
        ai_summary="这是一个测试视频的摘要内容。",
        config={
            "highlights": [
                {"time": "00:01:30", "seconds": 90, "content": "介绍知识管理的核心理念"},
                {"time": "00:03:45", "seconds": 225, "content": "演示如何建立双向链接"},
            ]
        }
    )

    # 测试导出
    exporter = HTMLPlayerExporter()
    result = exporter.export(context)

    print(f"导出结果: {'成功' if result.success else '失败'}")
    if result.success:
        print(f"播放器路径: {result.output_path}")
