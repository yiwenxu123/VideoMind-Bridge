#!/usr/bin/env python3
"""ASR 后端基准：同一批音频对比 CER/WER、RTF、耗时与成本。

用法:
  # 单文件
  python scripts/bench_asr.py --audio sample.wav --reference "参考文本" \
      --backends faster_whisper,sensevoice

  # 清单（YAML 数组）
  python scripts/bench_asr.py --manifest benchmarks/asr/manifest.yaml \
      --backends faster_whisper,sensevoice,dashscope --json

清单格式:
  - id: sample-01
    audio: /abs/path/sample-01.wav
    reference: "参考文本"
    language: zh
    tags: [口播, bgm]

依赖: 基础依赖即可；`jiwer` 可选（未安装时只输出耗时/RTF）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.asr import (  # noqa: E402
    MediaRef,
    TranscribeOptions,
    create_transcriber,
    list_transcriber_names,
)


@dataclass
class Entry:
    id: str
    audio: Path
    reference: str = ""
    language: str | None = None
    tags: list[str] = field(default_factory=list)


def _load_manifest(path: Path) -> list[Entry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(data, list):
        raise ValueError("manifest 必须是 YAML 数组")
    entries: list[Entry] = []
    for index, raw in enumerate(data):
        if not isinstance(raw, dict) or not raw.get("audio"):
            raise ValueError(f"manifest 第 {index + 1} 条缺少 audio")
        audio = Path(str(raw["audio"])).expanduser()
        if not audio.is_absolute():
            audio = (path.parent / audio).resolve()
        entries.append(
            Entry(
                id=str(raw.get("id") or audio.stem),
                audio=audio,
                reference=str(raw.get("reference") or ""),
                language=raw.get("language"),
                tags=list(raw.get("tags") or []),
            )
        )
    return entries


def _probe_duration(audio: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(audio),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def _score(reference: str, hypothesis: str) -> dict[str, float] | None:
    if not reference.strip():
        return None
    try:
        import jiwer
    except ImportError:
        return None
    ref = " ".join(reference.split())
    hyp = " ".join(hypothesis.split())
    return {"cer": float(jiwer.cer(ref, hyp)), "wer": float(jiwer.wer(ref, hyp))}


def _run_backend(name: str, entry: Entry, duration: float | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "backend": name,
        "entry": entry.id,
        "available": False,
        "ok": False,
        "chars": 0,
        "segments": 0,
        "elapsed_seconds": None,
        "rtf": None,
        "provider": "",
        "model": "",
        "cost_tier": "",
        "cer": None,
        "wer": None,
        "error": None,
    }
    try:
        backend = create_transcriber(name)
        caps = backend.capabilities()
        row["available"] = caps.available
        row["model"] = caps.model
        row["cost_tier"] = caps.cost_tier.value
        if not caps.available:
            row["error"] = caps.notes or "后端不可用"
            return row

        started = time.perf_counter()
        transcript = backend.transcribe(
            MediaRef(path=entry.audio),
            TranscribeOptions(language=entry.language),
        )
        elapsed = time.perf_counter() - started
        row.update(
            {
                "ok": bool(transcript.text.strip()),
                "chars": len(transcript.text),
                "segments": len(transcript.segments or []),
                "elapsed_seconds": round(elapsed, 3),
                "provider": transcript.provider,
                "model": transcript.model or row["model"],
                "error": None,
            }
        )
        if duration and duration > 0:
            row["rtf"] = round(elapsed / duration, 4)
        score = _score(entry.reference, transcript.text)
        if score:
            row.update(score)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def _print_table(rows: list[dict[str, Any]]) -> None:
    headers = ["backend", "entry", "ok", "chars", "elapsed", "rtf", "cer", "wer", "model"]
    print(" | ".join(headers))
    print(" | ".join("---" for _ in headers))
    for r in rows:
        print(
            " | ".join(
                [
                    str(r["backend"]),
                    str(r["entry"]),
                    "yes" if r["ok"] else "no",
                    str(r["chars"]),
                    f"{r['elapsed_seconds']:.2f}s" if r["elapsed_seconds"] is not None else "-",
                    f"{r['rtf']:.3f}" if r["rtf"] is not None else "-",
                    f"{r['cer']:.3f}" if r["cer"] is not None else "-",
                    f"{r['wer']:.3f}" if r["wer"] is not None else "-",
                    str(r["model"] or "-"),
                ]
            )
        )
        if r["error"]:
            print(f"  ! {r['backend']}: {r['error']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ASR 后端基准")
    parser.add_argument("--audio", help="单个音频文件")
    parser.add_argument("--reference", default="", help="参考文本（配合 --audio）")
    parser.add_argument("--language", default=None, help="语言提示（如 zh / en / auto）")
    parser.add_argument("--manifest", help="YAML 清单路径")
    parser.add_argument(
        "--backends",
        default="faster_whisper,sensevoice",
        help=f"逗号分隔的后端列表（已注册: {', '.join(list_transcriber_names())}）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--output", help="同时写入 JSON 文件")
    args = parser.parse_args(argv)

    if args.manifest:
        entries = _load_manifest(Path(args.manifest).expanduser())
    elif args.audio:
        audio = Path(args.audio).expanduser()
        entries = [
            Entry(
                id=audio.stem,
                audio=audio,
                reference=args.reference,
                language=args.language,
            )
        ]
    else:
        parser.error("需要 --audio 或 --manifest")

    backends = [name.strip() for name in args.backends.split(",") if name.strip()]
    rows: list[dict[str, Any]] = []
    for entry in entries:
        if not entry.audio.is_file():
            rows.append(
                {
                    "backend": "-", "entry": entry.id, "ok": False, "chars": 0,
                    "segments": 0, "elapsed_seconds": None, "rtf": None,
                    "provider": "", "model": "", "cost_tier": "",
                    "cer": None, "wer": None, "error": f"音频不存在: {entry.audio}",
                }
            )
            continue
        duration = _probe_duration(entry.audio)
        for backend in backends:
            rows.append(_run_backend(backend, entry, duration))

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        _print_table(rows)

    if args.output:
        Path(args.output).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return 0 if any(row["ok"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
