"""faster-whisper 适配器（逻辑迁移自 extractors/_whisper_asr.py）

本地 CPU int8 转写，零 key；模型懒加载并缓存为进程级单例。
模型获取三级兜底：① HF 本地缓存 ② HF 在线下载（可配 HF_ENDPOINT 镜像）
③ ModelScope 镜像下载（国内网络，免依赖 huggingface CDN）。
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any

from ...models import CostTier
from ..base import Transcriber
from ..registry import register_transcriber
from ..types import (
    AsrEmpty,
    AsrFailed,
    AsrUnavailable,
    Capabilities,
    MediaRef,
    Segment,
    TranscribeOptions,
    Transcript,
)

_MODEL: Any = None
_MODEL_SIZE: str = ""

# ModelScope 镜像 (Systran 官方镜像, 与 HF 文件一致)
_MODELSCOPE_BASE = (
    "https://modelscope.cn/models/Systran/faster-whisper-{size}/resolve/master/{file}"
)
_MODELSCOPE_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
# 模型缓存目录 (ModelScope 兜底下载位置)
_MODELSCOPE_CACHE = Path.home() / ".cache" / "videomind"


def _whisper_importable() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _hf_cache_complete(model_size: str) -> bool:
    """HF 本地缓存是否已包含完整模型 (model.bin 有效)。"""
    try:
        from huggingface_hub import snapshot_download

        path = snapshot_download(
            f"Systran/faster-whisper-{model_size}", local_files_only=True,
        )
        model_bin = Path(path) / "model.bin"
        return model_bin.exists() and model_bin.stat().st_size > 1_000_000
    except Exception:
        return False


def _modelscope_model_dir(model_size: str) -> str:
    """从 ModelScope 下载模型到本地目录 (与 HF 缓存同构), 返回目录路径。"""
    cache_dir = _MODELSCOPE_CACHE / f"whisper-{model_size}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    for fname in _MODELSCOPE_FILES:
        target = cache_dir / fname
        if target.exists() and target.stat().st_size > 0:
            continue
        url = _MODELSCOPE_BASE.format(size=model_size, file=fname)
        try:
            urllib.request.urlretrieve(url, target)  # 跟随重定向
        except Exception as e:
            raise RuntimeError(f"ModelScope 下载失败 {fname}: {e}") from e
        if not target.exists() or target.stat().st_size == 0:
            raise RuntimeError(f"ModelScope 下载为空: {fname}")
    return str(cache_dir)


def _resolve_model_ref(model_size: str) -> str:
    """解析模型引用: HF 缓存 → HF 在线 → ModelScope, 返回可加载的引用。"""
    repo = f"Systran/faster-whisper-{model_size}"

    # ① HF 本地缓存完整 → 直接用 repo id (faster-whisper 走缓存, 零网络)
    if _hf_cache_complete(model_size):
        return repo

    # ② HF 在线下载 (支持 HF_ENDPOINT 镜像)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo)
        return repo
    except Exception:
        pass

    # ③ ModelScope 镜像兜底 (国内网络 HF CDN 不可达时)
    return _modelscope_model_dir(model_size)


def run_whisper(
    audio_path: Path,
    language: str | None = "zh",
    model_size: str = "base",
) -> tuple[str, list[dict] | None]:
    """使用 faster-whisper 本地转写音频（模型单例懒加载）。

    Returns:
        (text, segments): 转录文本与时间轴分段, 无分段时为 None

    Raises:
        ImportError: faster-whisper 未安装
        RuntimeError: 转写失败
    """
    global _MODEL, _MODEL_SIZE

    from faster_whisper import WhisperModel

    if _MODEL is None or model_size != _MODEL_SIZE:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        model_ref = _resolve_model_ref(model_size)
        _MODEL = WhisperModel(model_ref, device="cpu", compute_type="int8")
        _MODEL_SIZE = model_size

    segments_iter, _info = _MODEL.transcribe(str(audio_path), language=language)

    text_parts: list[str] = []
    segment_list: list[dict] = []
    for seg in segments_iter:
        text_parts.append(seg.text)
        segment_list.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        })

    text = " ".join(text_parts).strip()
    return text, (segment_list or None)


class FasterWhisperTranscriber(Transcriber):
    """本地 faster-whisper 后端（默认主链路，零 key）"""

    name = "faster_whisper"

    def _model_size(self) -> str:
        return str(self.config.get("model") or os.getenv("VMB_WHISPER_MODEL", "base"))

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=self.name,
            available=_whisper_importable(),
            languages=["auto", "zh", "en", "ja", "ko", "yue"],
            timestamps=True,
            cost_tier=CostTier.CHEAP,
            model=self._model_size(),
            notes="本地 CPU int8，模型懒加载；VMB_WHISPER_MODEL 可换尺寸",
        )

    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        if not _whisper_importable():
            raise AsrUnavailable("faster-whisper 未安装（pip install faster-whisper）")
        audio_path = media.require_path()
        model_size = self._model_size()
        language = options.language or os.getenv("VMB_ASR_LANGUAGE", "") or None
        try:
            text, raw_segments = run_whisper(audio_path, language=language, model_size=model_size)
        except ImportError as exc:
            raise AsrUnavailable("faster-whisper 未安装") from exc
        except Exception as exc:
            raise AsrFailed(f"faster-whisper 转写失败: {exc}") from exc

        if not text:
            raise AsrEmpty("faster-whisper 返回空转录")

        segments = [
            Segment(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                text=str(item.get("text", "")),
            )
            for item in (raw_segments or [])
        ]
        return Transcript(
            text=text,
            provider="faster-whisper",
            model=model_size,
            language=language or "auto",
            segments=segments or None,
            cost_tier=CostTier.CHEAP,
        )


register_transcriber("faster_whisper", FasterWhisperTranscriber)
