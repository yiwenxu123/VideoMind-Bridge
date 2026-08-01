"""视频源地址解析服务 (替代 Coze 第三方解析插件)

职责: yt-dlp 解析直链 → 下载音频 → 中转目录, 输出无防盗链的公网可访问 URL。
DashScope 等云端 ASR 可从该 URL 直接拉取音频。

环境变量:
- VMB_MEDIA_DIR: 音频中转目录 (默认 ~/.videomind/media)
- VMB_AUDIO_MAX_AGE: 音频保留时长秒数 (默认 86400 = 24h)
- VMB_FFMPEG_PATH: ffmpeg 路径 (默认 PATH 查找)
"""

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEDIA_TTL_SECONDS = int(os.environ.get("VMB_AUDIO_MAX_AGE", str(24 * 3600)))
_FFMPEG_PATH = os.environ.get("VMB_FFMPEG_PATH", "ffmpeg")


def get_media_dir() -> Path:
    """音频中转目录"""
    override = os.environ.get("VMB_MEDIA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("VMB_DATA_DIR", str(Path.home() / ".videomind"))
    return Path(base) / "media"


def cleanup_stale_files(media_dir: Path | None = None) -> int:
    """清理过期音频文件, 返回删除数量"""
    media_dir = media_dir or get_media_dir()
    if not media_dir.is_dir():
        return 0
    now = time.time()
    removed = 0
    for f in media_dir.iterdir():
        try:
            if f.is_file() and now - f.stat().st_mtime > _MEDIA_TTL_SECONDS:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info(f"清理过期音频 {removed} 个")
    return removed


def _find_ffmpeg() -> str | None:
    if shutil.which(_FFMPEG_PATH):
        return _FFMPEG_PATH
    return None


def _normalize_to_m4a(src: Path, dst: Path) -> bool:
    """非 m4a 格式用 ffmpeg 转码为 m4a (DashScope 兼容)"""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False
    result = subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-vn", "-acodec", "aac",
         "-b:a", "128k", str(dst)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        logger.warning(f"ffmpeg 转码失败: {result.stderr[-300:]}")
        return False
    return True


_ASR_FRIENDLY_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".amr", ".flac"}

# B站 CDN 下载必须携带的防盗链头
_BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}


def _parse_bilibili_playurl(url: str) -> dict[str, Any] | None:
    """B站官方 playurl API 解析音频直链

    绕开云服务器 IP 在 yt-dlp 场景下的 412 风控 (api.bilibili.com 不受影响)。
    返回 {audio_url, title, duration} 或 None。
    """

    from ..core.extractors.bilibili_extractor import BilibiliExtractor

    ex = BilibiliExtractor()
    bvid = ex._resolve_video_id(url)
    if not bvid:
        return None

    try:
        params = {"bvid": bvid}
        signed = ex._wbi_sign(params, ex._get_wbi_key())
        resp = ex._client.get(
            "https://api.bilibili.com/x/web-interface/view", params=signed
        )
        data = resp.json()
        if data.get("code") != 0:
            return None
        vdata = data.get("data", {})
        cid = vdata.get("cid")
        if not cid:
            pages = vdata.get("pages") or []
            cid = pages[0].get("cid") if pages else None
        if not cid:
            return None

        play_params = {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
        signed = ex._wbi_sign(play_params, ex._get_wbi_key())
        resp2 = ex._client.get(
            "https://api.bilibili.com/x/player/playurl", params=signed
        )
        pdata = resp2.json()
        if pdata.get("code") != 0:
            return None
        dash = pdata.get("data", {}).get("dash") or {}
        audios = dash.get("audio") or []
        if not audios:
            return None

        audios.sort(key=lambda a: a.get("bandwidth", 0), reverse=True)
        best = audios[0]
        audio_url = best.get("baseUrl") or best.get("base_url") or best.get("url")
        if not audio_url:
            return None
        return {
            "audio_url": audio_url,
            "title": vdata.get("title", ""),
            "duration": vdata.get("duration", 0),
            "platform": "bilibili",
            "ext": ".m4s",
        }
    except Exception as e:
        logger.warning(f"B站 playurl 解析失败: {e}")
        return None


def _download_to_media(url: str, media_dir: Path, name_prefix: str,
                       headers: dict[str, str] | None = None) -> Path | None:
    """下载文件到中转目录, 返回最终文件路径"""
    import httpx

    media_dir.mkdir(parents=True, exist_ok=True)
    final_name = f"{name_prefix}-{int(time.time())}"
    tmp_path = media_dir / f"{final_name}.part"
    try:
        with httpx.stream(
            "GET", url, headers=headers, timeout=120.0,
            follow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        if tmp_path.stat().st_size < 1024:
            tmp_path.unlink(missing_ok=True)
            return None
        # 按 content-type 推断扩展名
        if "mp3" in content_type:
            ext = ".mp3"
        elif "wav" in content_type or "x-wav" in content_type:
            ext = ".wav"
        elif "aac" in content_type:
            ext = ".aac"
        else:
            ext = ".m4a"
        final_path = media_dir / f"{final_name}{ext}"
        tmp_path.rename(final_path)
        return final_path
    except Exception as e:
        logger.warning(f"中转下载失败 {url[:80]}: {e}")
        tmp_path.unlink(missing_ok=True)
        return None


def parse_audio_source(url: str, cookie_browser: str | None = None,
                       cookies_file: str | None = None) -> dict[str, Any]:
    """解析并下载视频音频到中转目录

    Args:
        url: 视频链接 (B站/抖音/小红书/YouTube 等)
        cookie_browser: 浏览器名 (chrome/safari/firefox), 可选
        cookies_file: cookies.txt 路径, 可选

    Returns:
        {
            "success": bool,
            "path": "/media/xxx.m4a" (相对路径, 供服务端拼公网 URL),
            "title": 视频标题,
            "duration": 时长(秒),
            "platform": 平台,
            "ext": 音频扩展名,
            "error": 失败原因 (仅失败时),
        }
    """
    import yt_dlp

    cleanup_stale_files()

    # B站专用: 官方 playurl API (绕开云 IP 412 风控)
    if "bilibili.com" in url or "b23.tv" in url:
        bili = _parse_bilibili_playurl(url)
        if bili and bili.get("audio_url"):
            media_dir = get_media_dir()
            prefix = hashlib.sha1(url.encode()).hexdigest()[:10]
            final_path = _download_to_media(
                bili["audio_url"], media_dir, prefix, headers=_BILI_HEADERS
            )
            if final_path:
                logger.info(
                    f"B站 playurl 中转完成: {final_path} ({final_path.stat().st_size} bytes)"
                )
                return {
                    "success": True,
                    "path": f"/media/{final_path.name}",
                    "title": bili.get("title", ""),
                    "duration": bili.get("duration", 0),
                    "platform": "bilibili",
                    "ext": final_path.suffix,
                    "size_bytes": final_path.stat().st_size,
                }
        logger.warning("B站 playurl 失败, 回退 yt-dlp")

    ydl_opts: dict[str, Any] = {
        "format": "ba/b",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    if cookie_browser:
        ydl_opts["cookiesfrombrowser"] = (cookie_browser,)
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "") or ""
            duration = float(info.get("duration") or 0)
            platform = (info.get("extractor_key") or "").lower()

            media_dir = get_media_dir()
            media_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                tmp_path = tmp_dir / "audio.%(ext)s"
                ydl_opts["outtmpl"] = str(tmp_path)
                ydl_opts["restrictfilenames"] = True
                with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                    ydl2.download([url])

                files = list(tmp_dir.iterdir())
                if not files:
                    return {"success": False, "error": "yt-dlp 未下载到任何文件", "url": url}
                src = files[0]

                final_name = f"{hashlib.sha1(url.encode()).hexdigest()[:10]}-{int(time.time())}"
                if src.suffix in _ASR_FRIENDLY_EXTS:
                    ext = src.suffix
                    final_path = media_dir / f"{final_name}{ext}"
                    shutil.move(str(src), str(final_path))
                else:
                    converted = media_dir / f"{final_name}.m4a"
                    if _normalize_to_m4a(src, converted):
                        ext = ".m4a"
                        final_path = converted
                    else:
                        logger.warning(
                            f"音频格式 {src.suffix} 不支持且无 ffmpeg, 原样保留"
                        )
                        ext = src.suffix
                        final_path = media_dir / f"{final_name}{ext}"
                        shutil.move(str(src), str(final_path))

            logger.info(f"音频中转完成: {final_path} ({final_path.stat().st_size} bytes)")
            return {
                "success": True,
                "path": f"/media/{final_path.name}",
                "title": title,
                "duration": duration,
                "platform": platform,
                "ext": ext,
                "size_bytes": final_path.stat().st_size,
            }

    except Exception as e:
        logger.error(f"音频解析失败 {url}: {e}")
        return {"success": False, "error": str(e), "url": url}
