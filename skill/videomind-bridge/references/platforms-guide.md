# 支持平台与下载器

## 平台支持矩阵

VideoMind Bridge 使用 **yt-dlp** 作为唯一下载器，支持 1000+ 平台：

| 平台 | 域名 | 视频下载 | 音频下载 | 备注 |
|------|------|----------|----------|------|
| Bilibili | bilibili.com, b23.tv | ✅ | ✅ | |
| YouTube | youtube.com, youtu.be | ✅ | ✅ | |
| 抖音 | douyin.com, v.douyin.com | ✅ | ✅ | 需要 Cookie |
| 小红书 | xiaohongshu.com | ✅ | ✅ | 需要 Cookie |
| 快手 | kuaishou.com | ✅ | ✅ | |
| TikTok | tiktok.com | ✅ | ✅ | |
| Twitter/X | twitter.com, x.com | ✅ | ✅ | |
| 微博 | weibo.com | ✅ | ✅ | |
| 知乎 | zhihu.com | ✅ | ✅ | |
| Instagram | instagram.com | ✅ | ✅ | 需要登录 |
| Vimeo | vimeo.com | ✅ | ✅ | |
| Reddit | reddit.com | ✅ | ✅ | |

## yt-dlp 安装

```bash
# macOS (brew)
brew install yt-dlp

# 或使用 pip
pip install yt-dlp

# 更新到最新版
brew upgrade yt-dlp
# 或
yt-dlp -U
```

## 国内平台 Cookie 配置

抖音、小红书等国内平台需要登录 Cookie 才能下载：

### 方法 1: 从浏览器自动获取

```bash
# 使用 Chrome 的 Cookie
yt-dlp --cookies-from-browser chrome "URL"

# 使用 Safari 的 Cookie
yt-dlp --cookies-from-browser safari "URL"

# 使用 Firefox 的 Cookie
yt-dlp --cookies-from-browser firefox "URL"
```

### 方法 2: 手动导出 Cookie

1. 浏览器登录目标平台
2. 使用浏览器扩展导出 Cookie（推荐：EditThisCookie、Cookie Editor）
3. 保存为 `cookies.txt` 文件（Netscape 格式）
4. 使用：

```bash
yt-dlp --cookies cookies.txt "URL"
```

## 常见下载问题

### 抖音/小红书下载失败

**错误**: `Fresh cookies are needed` 或 `unable to extract video data`

**解决**:
1. 确保已登录抖音/小红书网页版
2. 使用 `--cookies-from-browser chrome` 参数
3. 或手动导出 Cookie 文件

### YouTube 年龄限制

**错误**: `Sign in to confirm your age`

**解决**:
```bash
yt-dlp --cookies-from-browser chrome "URL"
```

### 视频质量不可用

某些平台可能不提供指定分辨率，yt-dlp 会自动回退到最佳可用质量。

### 下载速度慢

```bash
# 使用多线程下载
yt-dlp --concurrent-fragments 4 "URL"
```
