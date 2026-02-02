已完成两个技术问题的调研和解答：

## 问题1：有字幕 vs 无字幕视频处理
- **当前脚本**：统一使用语音转录（faster-whisper），无论视频是否有字幕
- **原因**：Bilibili 字幕需要登录，当前未配置 cookies
- **建议优化**：优先下载平台字幕 → 无字幕时 fallback 到 AI 转录

## 问题2：ffmpeg 是否必须
- **结论**：本项目不需要系统级 ffmpeg
- **原因**：
  1. faster-whisper 使用 PyAV 库，已内置 FFmpeg 库
  2. yt-dlp 直接下载原始音频格式（m4a/webm），无需格式转换
- **当前脚本**：已移除 yt-dlp 的 ffmpeg 后处理，完全独立运行

## 关键验证结果
- faster-whisper audio.py 明确说明："FFmpeg does not need to be installed on the system"
- MVP 脚本成功运行，证明无 ffmpeg 依赖

如需继续开发完整应用，请告知。