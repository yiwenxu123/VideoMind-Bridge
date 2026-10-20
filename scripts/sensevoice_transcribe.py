#!/usr/bin/env python3
"""SenseVoice 语音转写（移植自内容运营agent api-server/scripts/sensevoice_transcribe.py）

用法: <python> sensevoice_transcribe.py <16k_mono_wav>
输入: 16000Hz 单声道 wav（上游 ffmpeg -ar 16000 -ac 1 产出）
输出: stdout 单行 JSON {"text": "..."}；诊断/错误全部走 stderr，exit 非 0 表示失败
策略: 30s 分块 decode（SenseVoice 单块上限，RTF≈0.011 实测，10 分钟音频约 7s）

依赖: pip install sherpa-onnx soundfile（推荐专用 venv，见 VMB_SENSEVOICE_PYTHON）
"""
import json
import os
import sys

DEFAULT_MODEL_DIR = os.path.expanduser("~/.cache/sherpa-onnx/sense-voice")
CHUNK_S = 30  # SenseVoice 单块上限 30s


def fail(msg: str, code: int = 1) -> None:
    print(f"[sensevoice] {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


def main() -> None:
    if len(sys.argv) < 2:
        fail("usage: sensevoice_transcribe.py <16k_mono_wav>", 2)
    wav_path = sys.argv[1]
    if not os.path.isfile(wav_path):
        fail(f"wav not found: {wav_path}")

    model_dir = os.environ.get("SENSEVOICE_MODEL_DIR", DEFAULT_MODEL_DIR)
    model = os.path.join(model_dir, "model.int8.onnx")
    tokens = os.path.join(model_dir, "tokens.txt")
    if not (os.path.isfile(model) and os.path.isfile(tokens)):
        fail(f"model files missing in {model_dir} (expect model.int8.onnx + tokens.txt)")

    try:
        import sherpa_onnx
        import soundfile as sf
    except ImportError as e:
        fail(f"missing dependency: {e}（VMB_SENSEVOICE_PYTHON 需指向装有 sherpa-onnx+soundfile 的解释器）")

    t0 = __import__("time").perf_counter()
    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=model,
        tokens=tokens,
        num_threads=4,
        use_itn=True,
        debug=False,
    )

    samples, sample_rate = sf.read(wav_path, dtype="float32")
    if len(samples) == 0:
        fail("empty audio")
    chunk_n = int(CHUNK_S * sample_rate)
    n_chunks = (len(samples) + chunk_n - 1) // chunk_n
    print(f"[sensevoice] {len(samples) / sample_rate:.1f}s @ {sample_rate}Hz, {n_chunks} chunks", file=sys.stderr, flush=True)

    texts = []
    for i in range(n_chunks):
        seg = samples[i * chunk_n : (i + 1) * chunk_n]
        stream = recognizer.create_stream()
        stream.accept_waveform(sample_rate, seg.tolist())
        recognizer.decode_stream(stream)
        texts.append(stream.result.text)

    text = "".join(texts).strip()
    print(f"[sensevoice] decoded in {__import__('time').perf_counter() - t0:.2f}s, {len(text)} chars", file=sys.stderr, flush=True)
    print(json.dumps({"text": text}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
