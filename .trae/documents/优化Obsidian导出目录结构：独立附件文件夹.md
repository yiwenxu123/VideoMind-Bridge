## 方案 A 实施计划

### 目标
优化 Obsidian 导出目录结构：
- 笔记文件（.md）→ `00 Inbox/Videos/`
- 视频附件 → `00 Inbox/Videos/Attachments/`

### 具体修改

#### 1. 修改 ObsidianExporter

**目录结构变更**：
```
Vault/
├── 00 Inbox/
│   └── Videos/
│       ├── 视频标题.md              # 笔记文件
│       └── Attachments/
│           ├── 视频标题.mp4         # 视频文件（符号链接或复制）
│           ├── 视频标题.m4a         # 音频文件（可选）
│           └── 视频标题.srt         # 字幕文件（可选）
```

**代码修改**：
1. 创建 `Attachments/` 子目录
2. 将视频文件放入 Attachments
3. 修改 Markdown 中的链接路径为 `[[Attachments/视频.mp4#t=00:04:15|00:04:15]]`
4. 可选：同时复制字幕文件到 Attachments

#### 2. 修改 _format_highlights 方法
- 使用相对路径 `Attachments/视频.mp4`
- 保持 Media Extended 兼容的格式

#### 3. 保持符号链接机制
- 优先使用符号链接（不占用额外空间）
- 失败则回退到复制

### 预期效果
- Obsidian 文件列表只显示 `.md` 笔记
- 视频文件隐藏在 `Attachments/` 中
- Media Extended 仍可正常播放（支持子目录路径）
- 目录结构更清晰，符合笔记管理最佳实践