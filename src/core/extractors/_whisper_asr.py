"""faster-whisper 本地转写共享调用（bilibili/tikhub/ytdlp_asr 复用）

模型懒加载并缓存为进程级单例, 避免重复加载。
模型获取三级兜底: ① HF 本地缓存 ② HF 在线下载 (可配 HF_ENDPOINT 镜像)
③ ModelScope 镜像下载 (国内网络, 免依赖 huggingface CDN)。
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from typing import Any

_MODEL: Any = None
_MODEL_SIZE: str = ""

# ModelScope 镜像 (Systran 官方镜像, 与 HF 文件一致)
_MODELSCOPE_BASE = (
    "https://modelscope.cn/models/Systran/faster-whisper-{size}/resolve/master/{file}"
)
_MODELSCOPE_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
# 模型缓存目录 (ModelScope 兜底下载位置)
_MODELSCOPE_CACHE = Path.home() / ".cache" / "videomind"


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
    """解析模型引用: HF 缓存 → HF 在线 → ModelScope, 返回 faster-whisper 可加载的引用。

    Returns:
        优先返回 repo id (命中 HF 缓存时), 否则返回本地目录路径。
    """
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


def transcribe_local(
    audio_path: Path,
    language: str = "zh",
    model_size: str = "base",
) -> tuple[str, list[dict] | None]:
    """使用 faster-whisper 本地转写音频。

    Returns:
        (text, segments): 转录文本与时间轴分段, 无分段时为 None

    Raises:
        ImportError: faster-whisper 未安装
        RuntimeError: 转写失败
    """
    global _MODEL, _MODEL_SIZE

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise ImportError("faster-whisper 未安装 (pip install faster-whisper)")

    if _MODEL is None or model_size != _MODEL_SIZE:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        model_ref = _resolve_model_ref(model_size)
        _MODEL = WhisperModel(model_ref, device="cpu", compute_type="int8")
        _MODEL_SIZE = model_size

    segments_iter, info = _MODEL.transcribe(str(audio_path), language=language)

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