"""Bilibili 内容提取器

使用 WBI 签名 + Bilibili 官方字幕 API, 零 Cookie 直接提取。
参考: keepongo/video-subtitle 的 WBI 签名实现。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from ..models import CostTier, ExtractResult
from . import register_extractor
from ._dashscope_asr import transcribe_audio_url
from ._whisper_asr import transcribe_local
from .base import ContentExtractor

# Bilibili WBI 签名常量和密钥池
MIXIN_KEY_ENC_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 37, 12, 52, 56, 7,
    0, 16, 22, 38, 59, 55, 11, 61, 34, 40, 26, 17, 51, 41, 60, 39,
    20, 13, 48, 6, 36, 24, 44, 25, 21, 4, 54, 57, 30, 1,
]

# 默认 WBI 密钥 (当 API 获取失败时使用)
_FALLBACK_WBI_KEY = "ea1db124afe2e5b2"

_BV_RE = re.compile(r"/(BV\w+)")
_EP_RE = re.compile(r"/(EP\w+)")
_SS_RE = re.compile(r"/(SS\w+)")
_B23_RE = re.compile(r"b23\.tv/(\w+)")


class BilibiliExtractor(ContentExtractor):
    """Bilibili 内容提取器"""

    platform_name = "bilibili"
    _cost_tier = CostTier.FREE
    url_pattern = re.compile(r"(bilibili\.com|b23\.tv)")

    def __init__(self) -> None:
        self._wbi_key: str | None = None
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com",
            },
        )

    def is_available(self) -> bool:
        """Bilibili 提取器始终可用 (无需 Cookie/Token)"""
        return True

    def extract(self, url: str) -> ExtractResult:
        try:
            bvid = self._resolve_video_id(url)
            if not bvid:
                return ExtractResult(
                    success=False, platform="bilibili", title="", content="",
                    source="bilibili", url=url, cost_tier=CostTier.FREE,
                    error=f"无法从 URL 解析视频 ID: {url}",
                )

            # 1. 获取视频信息 (标题、时长等)
            info = self._get_video_info(bvid)
            title = info.get("title", "")
            duration = info.get("duration", 0)

            # 2. 获取字幕
            subtitle_content, segments, language = self._get_subtitle(bvid)

            if not subtitle_content:
                # 无字幕: 尝试 playurl 音频直链 + DashScope ASR (绕 yt-dlp 网页 412 风控)
                asr_result = self._try_audio_asr_fallback(url, bvid, title, duration)
                if asr_result is not None:
                    return asr_result

                return ExtractResult(
                    success=False,
                    platform="bilibili",
                    title=title,
                    content=f"[Bilibili 视频] {title}\n时长: {duration}秒\n"
                            f"无可用字幕。请使用 yt-dlp 或 Whisper 提取音频转录。",
                    source="bilibili",
                    url=url,
                    cost_tier=CostTier.FREE,
                    duration_seconds=float(duration),
                    language="zh",
                    metadata={"bvid": bvid, "video_info": info},
                    error="无可用字幕 (视频可能无 CC 字幕, 或需要登录 Cookie 才能访问字幕接口)",
                )

            return ExtractResult(
                success=True,
                platform="bilibili",
                title=title,
                content=subtitle_content,
                source="bilibili",
                url=url,
                cost_tier=CostTier.FREE,
                duration_seconds=float(duration),
                language=language or "zh",
                segments=segments,
                metadata={"bvid": bvid, "video_info": info},
            )

        except httpx.HTTPStatusError as e:
            return ExtractResult(
                success=False, platform="bilibili", title="", content="",
                source="bilibili", url=url, cost_tier=CostTier.FREE,
                error=f"Bilibili API 错误: HTTP {e.response.status_code}",
            )
        except Exception as e:
            return ExtractResult(
                success=False, platform="bilibili", title="", content="",
                source="bilibili", url=url, cost_tier=CostTier.FREE,
                error=f"Bilibili 提取失败: {e}",
            )

    def get_playurl_audio_urls(self, url: str) -> dict[str, Any] | None:
        """B站官方 playurl API 解析音频直链。

        绕开云服务器 IP 在 yt-dlp 场景下的 412 风控 (api.bilibili.com 不受影响)。
        返回 {audio_urls, title, duration} 或 None。audio_urls 为所有候选 CDN URL
        (baseUrl + backupUrl, 去重), 由调用方逐个尝试下载。
        """
        bvid = self._resolve_video_id(url)
        if not bvid:
            return None

        try:
            params = {"bvid": bvid}
            signed = self._wbi_sign(params, self._get_wbi_key())
            resp = self._client.get(
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
            signed = self._wbi_sign(play_params, self._get_wbi_key())
            resp2 = self._client.get(
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
            candidates: list[str] = []
            for a in audios:
                for k in ("baseUrl", "base_url", "url"):
                    if a.get(k):
                        candidates.append(a[k])
                for b in (a.get("backupUrl") or a.get("backup_url") or []):
                    candidates.append(b)
            seen: set[str] = set()
            audio_urls = []
            for u in candidates:
                if u not in seen:
                    seen.add(u)
                    audio_urls.append(u)
            if not audio_urls:
                return None
            return {
                "audio_urls": audio_urls,
                "title": vdata.get("title", ""),
                "duration": vdata.get("duration", 0),
                "platform": "bilibili",
                "ext": ".m4s",
            }
        except Exception:
            return None

    def _try_audio_asr_fallback(
        self, url: str, bvid: str, title: str, duration: float,
    ) -> ExtractResult | None:
        """无字幕时: playurl 音频直链下载 + 转码 + ASR 转写。

        ASR 优先级: 本地 faster-whisper (稳定免费) → DashScope 异步 (公网 URL)。
        返回成功结果; 任一步失败返回 None (交由上层走原无字幕分支/降级链)。
        """
        playurl = self.get_playurl_audio_urls(url)
        if not playurl or not playurl.get("audio_urls"):
            return None

        audio_urls = playurl["audio_urls"]
        for audio_url in audio_urls:
            audio_path = self._download_audio(audio_url)
            if audio_path is None:
                continue
            try:
                # 本地 whisper (PyAV) 可直接解码 .m4s/.m4a, 免 ffmpeg 转码
                try:
                    text, segments = transcribe_local(audio_path, language="zh")
                    provider = "faster_whisper"
                    audio_path.unlink(missing_ok=True)
                except ImportError:
                    # 本地 whisper 未安装 → 转 mp3 走 DashScope 异步 (需公网 URL)
                    mp3_path = self._transcode_to_mp3(audio_path)
                    audio_path.unlink(missing_ok=True)
                    if mp3_path is None:
                        continue
                    try:
                        text, segments = self._transcribe_via_dashscope(mp3_path)
                        provider = "dashscope_asr"
                    finally:
                        mp3_path.unlink(missing_ok=True)
                if not text:
                    continue
                return ExtractResult(
                    success=True,
                    platform="bilibili",
                    title=title or playurl.get("title", ""),
                    content=text,
                    source="bilibili_asr",
                    url=url,
                    cost_tier=CostTier.FREE,
                    duration_seconds=float(duration or playurl.get("duration", 0)),
                    language="zh",
                    segments=segments,
                    metadata={
                        "bvid": bvid,
                        "api_provider": provider,
                        "model": "base" if provider == "faster_whisper" else "paraformer-v2",
                    },
                )
            except Exception:
                audio_path.unlink(missing_ok=True)
                continue
        return None

    def _transcribe_via_dashscope(
        self, mp3_path: Path,
    ) -> tuple[str, list[dict] | None]:
        """DashScope 异步转写: 拷贝到媒体目录 → 公网 URL → 异步任务轮询。"""
        dashscope_key = self._resolve_api_key("dashscope_key")
        if not dashscope_key:
            raise RuntimeError("dashscope_key 未配置")

        media_dir = os.getenv("VMB_MEDIA_DIR", "")
        public_url = os.getenv("VMB_PUBLIC_URL", "")
        if not media_dir or not public_url:
            raise RuntimeError("VMB_MEDIA_DIR/VMB_PUBLIC_URL 未配置")

        dst = Path(media_dir) / f"bili_asr_{int(time.time() * 1000)}.mp3"
        try:
            shutil.copy2(mp3_path, dst)
            return transcribe_audio_url(
                f"{public_url.rstrip('/')}/media/{dst.name}", dashscope_key
            )
        finally:
            dst.unlink(missing_ok=True)

    @staticmethod
    def _transcode_to_mp3(src: Path, timeout: float = 180.0) -> Path | None:
        """ffmpeg 转码为 mp3 (DashScope 同步 ASR 不识别 .m4s 容器)"""
        import shutil
        import subprocess

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            # PATH 缺失时探测常见安装路径
            for p in (
                "/opt/homebrew/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/usr/bin/ffmpeg",
            ):
                if Path(p).exists():
                    ffmpeg = p
                    break
        if ffmpeg is None:
            return None
        dst = src.with_suffix(".mp3")
        try:
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", str(src), "-vn", "-acodec", "libmp3lame",
                 "-b:a", "128k", str(dst)],
                capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0 or not dst.exists() or dst.stat().st_size < 1000:
                dst.unlink(missing_ok=True)
                return None
            return dst
        except Exception:
            dst.unlink(missing_ok=True)
            return None

    def _download_audio(self, audio_url: str, timeout: float = 300.0) -> Path | None:
        """下载音频直链到临时文件 (限 150MB 防御)。

        B 站 CDN 防盗链: 需携带 Referer/UA, 否则返回 403。
        """
        try:
            import tempfile

            tmp = Path(tempfile.gettempdir()) / f"vmb_bili_{int(time.time() * 1000)}.m4s"
            headers = {
                "Referer": "https://www.bilibili.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
            with self._client.stream("GET", audio_url, timeout=timeout, headers=headers) as resp:
                resp.raise_for_status()
                total = 0
                with open(tmp, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        total += len(chunk)
                        if total > 150 * 1024 * 1024:
                            tmp.unlink(missing_ok=True)
                            return None
                        f.write(chunk)
            if total < 1000:
                tmp.unlink(missing_ok=True)
                return None
            return tmp
        except Exception:
            return None

    def _get_wbi_key(self) -> str:
        """获取 WBI 签名密钥"""
        if self._wbi_key is not None:
            return self._wbi_key

        try:
            resp = self._client.get("https://api.bilibili.com/x/web-interface/nav")
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("isLogin") is not None:
                img_url: str = data["data"]["wbi_img"]["img_url"]
                sub_url: str = data["data"]["wbi_img"]["sub_url"]
                img_key = img_url.rsplit("/", 1)[1].split(".")[0]
                sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
                self._wbi_key = self._mixin_key(img_key + sub_key)
            else:
                self._wbi_key = _FALLBACK_WBI_KEY
        except Exception:
            self._wbi_key = _FALLBACK_WBI_KEY

        return self._wbi_key

    @staticmethod
    def _mixin_key(orig: str) -> str:
        """WBI mixin key 计算"""
        return "".join(orig[i] for i in MIXIN_KEY_ENC_TABLE if i < len(orig))[:32]

    @staticmethod
    def _wbi_sign(params: dict[str, str], wbi_key: str) -> dict[str, str]:
        """对参数字典进行 WBI 签名"""
        params["wts"] = str(int(time.time()))
        sorted_params = sorted(params.items())
        query = urllib.parse.urlencode(sorted_params)
        sign_str = query + wbi_key
        params["w_rid"] = hashlib.md5(sign_str.encode()).hexdigest()
        return params

    def _resolve_video_id(self, url: str) -> str | None:
        """解析视频 ID (支持 BV/EP/SS/短链接)"""
        # 短链接
        if "b23.tv" in url:
            m = _B23_RE.search(url)
            if m:
                resolved = self._resolve_b23_url(url)
                if resolved:
                    return self._resolve_video_id(resolved)
            return None

        # BV / EP / SS
        for pattern in [_BV_RE, _EP_RE, _SS_RE]:
            m = pattern.search(url)
            if m:
                return m.group(1)
        return None

    def _resolve_b23_url(self, url: str) -> str | None:
        """解析 b23.tv 短链接"""
        try:
            resp = self._client.get(url, follow_redirects=True)
            return str(resp.url)
        except Exception:
            return None

    def _get_video_info(self, bvid: str) -> dict[str, Any]:
        """获取视频元信息"""
        params = {"bvid": bvid}
        signed = self._wbi_sign(params, self._get_wbi_key())
        resp = self._client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params=signed,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Bilibili API 返回错误: {data.get('message', 'unknown')}")

        vdata = data["data"]
        return {
            "title": vdata.get("title", ""),
            "duration": vdata.get("duration", 0),
            "author": vdata.get("owner", {}).get("name", ""),
            "description": vdata.get("desc", ""),
            "aid": vdata.get("aid"),
        }

    def _get_subtitle(self, bvid: str) -> tuple[str, list, str | None]:
        """获取字幕内容"""
        params = {"bvid": bvid}
        signed = self._wbi_sign(params, self._get_wbi_key())
        resp = self._client.get(
            "https://api.bilibili.com/x/web-interface/view",
            params=signed,
        )
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(
                f"Bilibili 字幕 API 返回错误: {data.get('message', 'unknown')} (code={data.get('code')})"
            )

        player_info = data.get("data", {})
        subtitle_list = player_info.get("subtitle", {}).get("subtitles", [])

        if not subtitle_list:
            return "", [], None

        # 优先选择中文字幕
        subtitle_url = None
        lang = None
        for sub in subtitle_list:
            if sub.get("lan_doc", "").lower() in ("中文", "chinese", "zh-cn", "zh"):
                subtitle_url = sub.get("subtitle_url", "")
                lang = sub.get("lan", "zh")
                break

        if not subtitle_url:
            subtitle_url = subtitle_list[0].get("subtitle_url", "")
            lang = subtitle_list[0].get("lan", "zh")

        if not subtitle_url:
            return "", [], None

        # 完整的字幕 JSON URL
        if subtitle_url.startswith("//") or subtitle_url.startswith("/"):
            subtitle_url = "https:" + subtitle_url

        sub_resp = self._client.get(subtitle_url)
        sub_data = sub_resp.json()

        # 提取字幕文本和片段
        text_parts: list[str] = []
        segments: list[dict[str, Any]] = []
        for item in sub_data.get("body", []):
            text = item.get("content", "")
            if text:
                text_parts.append(text)
                segments.append({
                    "start": item.get("from", 0),
                    "end": item.get("to", 0),
                    "text": text,
                })

        return "\n".join(text_parts), segments, lang


register_extractor("bilibili", BilibiliExtractor)
