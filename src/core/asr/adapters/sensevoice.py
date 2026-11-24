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

# 子进程探测超时：import sherpa_onnx 实测约 0.2s，留足冷启动余量即可。
_PROBE_TIMEOUT_S = 10.0
# 解释器路径 -> (是否可用, 诊断信息)。capabilities() 会被 /api/v1/capabilities 反复调用，
# 而探测要起子进程，因此每个解释器在进程生命周期内只探一次。
_RUNTIME_PROBE_CACHE: dict[str, tuple[bool, str]] = {}


def _probe_runtime(python: str) -> tuple[bool, str]:
    """验证该解释器**真的**能 import sherpa_onnx + soundfile。

    2026-11-24：此前只检查三样文件是否存在。换机器后 _resolve_python 找不到专用 venv
    会回落到 sys.executable，而主 venv 没有 sherpa-onnx —— 于是 capabilities 报
    available=true，真跑转写才失败。这里用一次子进程把「可运行」变成可验证的事实，
    失败时把原因带进 notes，便于直接定位（见 scripts/install_sensevoice.sh）。
    """
    cached = _RUNTIME_PROBE_CACHE.get(python)
    if cached is not None:
        return cached
    try:
        proc = subprocess.run(
            [python, "-c", "import sherpa_onnx, soundfile"],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_S,
        )
        if proc.returncode == 0:
            result: tuple[bool, str] = (True, "")
        else:
            lines = [line for line in (proc.stderr or proc.stdout or "").splitlines() if line.strip()]
            detail = lines[-1][:200] if lines else f"退出码 {proc.returncode}"
            result = (False, detail)
    except (OSError, subprocess.SubprocessError) as exc:
        result = (False, str(exc)[:200])
    _RUNTIME_PROBE_CACHE[python] = result
    return result


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
        # 三样文件齐了还不算可用：解释器可能没装 sherpa-onnx。真探一次，结果带进 notes。
        if not missing:
            probe_ok, probe_detail = _probe_runtime(python)
            if not probe_ok:
                missing.append(f"解释器缺少 sherpa-onnx/soundfile({probe_detail})")
        if missing:
            notes = "; ".join(missing)
        else:
            notes = "子进程调用，已确认解释器可 import sherpa-onnx+soundfile"
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
