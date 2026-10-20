"""SenseVoice 适配器（子进程模式，阶段 1）

不在 VMB 基础依赖里塞 sherpa-onnx：用外部解释器调用
src/core/asr/scripts/sensevoice_transcribe.py，契约与内容运营agent 已验证的路径一致——
stdout 最后一行 JSON {"text": ...}，诊断走 stderr，exit 非 0 即失败。

输入需 16k 单声道 wav；非 wav 输入会先用 ffmpeg 转码（SenseVoice 输入规格）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ...media import MediaTranscodeError, to_16k_mono_wav
from ...models import CostTier
from ..base import Transcriber
from ..registry import register_transcriber
from ..types import (
    AsrEmpty,
    AsrFailed,
    AsrUnavailable,
    Capabilities,
    MediaRef,
    TranscribeOptions,
    Transcript,
)

DEFAULT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sensevoice_transcribe.py"
DEFAULT_MODEL_DIR = Path.home() / ".cache" / "sherpa-onnx" / "sense-voice"
DEFAULT_PYTHON = Path.home() / ".cache" / "sensevoice" / "venv" / "bin" / "python"
ALT_PYTHON = Path.home() / ".cache" / "sherpa-onnx" / "venv" / "bin" / "python"


def _resolve_python() -> str:
    env_python = os.getenv("VMB_SENSEVOICE_PYTHON", "").strip()
    if env_python:
        return env_python
    for candidate in (DEFAULT_PYTHON, ALT_PYTHON):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _resolve_script() -> Path:
    env_script = os.getenv("VMB_SENSEVOICE_SCRIPT", "").strip()
    if env_script:
        return Path(env_script)
    return DEFAULT_SCRIPT


def _resolve_model_dir() -> Path:
    env_dir = os.getenv("VMB_SENSEVOICE_MODEL_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return DEFAULT_MODEL_DIR


def _model_ready(model_dir: Path) -> bool:
    return (model_dir / "model.int8.onnx").is_file() and (model_dir / "tokens.txt").is_file()


def _ensure_wav(audio_path: Path) -> tuple[Path, Path | None]:
    """返回 (16k 单声道 wav, 需清理的临时文件)。"""
    if audio_path.suffix.lower() == ".wav":
        return audio_path, None
    dst = Path(f"{audio_path}.sensevoice16k.wav")
    try:
        to_16k_mono_wav(audio_path, dst)
    except MediaTranscodeError as exc:
        raise AsrFailed(f"SenseVoice 需要 16k wav，转码失败: {exc}") from exc
    return dst, dst


class SenseVoiceTranscriber(Transcriber):
    """SenseVoice-Small 后端（子进程 + 可选专用 venv）"""

    name = "sensevoice"

    def _timeout(self) -> float:
        raw = self.config.get("timeout", os.getenv("VMB_SENSEVOICE_TIMEOUT", "600"))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 600.0

    def capabilities(self) -> Capabilities:
        script = _resolve_script()
        python = _resolve_python()
        model_dir = _resolve_model_dir()
        missing: list[str] = []
        if not script.is_file():
            missing.append(f"脚本缺失({script})")
        if not Path(python).exists():
            missing.append(f"解释器缺失({python})")
        if not _model_ready(model_dir):
            missing.append(f"模型缺失({model_dir})")
        notes = "; ".join(missing) if missing else "子进程调用，需 sherpa-onnx+soundfile"
        return Capabilities(
            name=self.name,
            available=not missing,
            languages=["auto", "zh", "en", "ja", "ko", "yue"],
            timestamps=False,
            cost_tier=CostTier.CHEAP,
            model="sensevoice-small",
            notes=notes,
        )

    def transcribe(self, media: MediaRef, options: TranscribeOptions) -> Transcript:
        script = _resolve_script()
        if not script.is_file():
            raise AsrUnavailable(f"SenseVoice 脚本不存在: {script}")
        python = _resolve_python()
        if not Path(python).exists():
            raise AsrUnavailable(f"SenseVoice 解释器不存在: {python}")
        model_dir = _resolve_model_dir()
        if not _model_ready(model_dir):
            raise AsrUnavailable(
                f"SenseVoice 模型缺失: {model_dir}（需要 model.int8.onnx + tokens.txt）"
            )

        audio_path = media.require_path()
        wav_path, cleanup = _ensure_wav(audio_path)
        try:
            env = {**os.environ, "SENSEVOICE_MODEL_DIR": str(model_dir)}
            try:
                proc = subprocess.run(
                    [python, str(script), str(wav_path)],
                    capture_output=True,
                    text=True,
                    timeout=self._timeout(),
                    env=env,
                )
            except subprocess.TimeoutExpired as exc:
                raise AsrFailed(f"SenseVoice 转写超时（>{self._timeout():.0f}s）") from exc
            except Exception as exc:
                raise AsrFailed(f"SenseVoice 子进程调用失败: {exc}") from exc
        finally:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)

        if proc.returncode != 0:
            stderr_tail = (proc.stderr or "").strip().splitlines()[-1:] or [""]
            raise AsrFailed(f"SenseVoice 转写失败: {stderr_tail[0][:200]}")

        lines = [line for line in (proc.stdout or "").strip().splitlines() if line.strip()]
        if not lines:
            raise AsrFailed("SenseVoice 无输出")
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise AsrFailed(f"SenseVoice 输出不可解析: {lines[-1][:120]}") from exc

        text = str(payload.get("text") or "").strip()
        if not text:
            raise AsrEmpty("SenseVoice 返回空转录")

        return Transcript(
            text=text,
            provider="sensevoice",
            model="sensevoice-small",
            language=options.language or "auto",
            segments=None,
            cost_tier=CostTier.CHEAP,
            metadata={"model_dir": str(_resolve_model_dir())},
        )


register_transcriber("sensevoice", SenseVoiceTranscriber)
