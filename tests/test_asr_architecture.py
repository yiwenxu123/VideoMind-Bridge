"""ASR 架构防回归测试（阶段 0 建立，阶段 1 更新为统一链契约）

约束：平台提取器只调 src.core.asr，不直接碰模型库、不 import 已删除的旧模块。
"""

from __future__ import annotations

import inspect

from src.core.asr import list_transcriber_names
from src.core.extractors import bilibili_extractor as bilibili_mod
from src.core.extractors import create_all_extractors, list_extractors
from src.core.extractors import tikhub_extractor as tikhub_mod
from src.core.extractors import ytdlp_asr_extractor as ytdlp_mod

_EXTRACTOR_MODULES = (bilibili_mod, tikhub_mod, ytdlp_mod)


def test_aliyun_asr_not_registered_as_extractor():
    """阿里云 ASR 是音频后端，不是 URL 提取器，不能参与路由。"""
    assert "aliyun_asr" not in list_extractors()
    names = [extractor.platform_name for extractor in create_all_extractors()]
    assert "aliyun_asr" not in names


def test_extractors_use_unified_asr_chain():
    for module in _EXTRACTOR_MODULES:
        source = inspect.getsource(module)
        assert "transcribe_with_chain" in source
        assert "_whisper_asr" not in source
        assert "_dashscope_asr" not in source
        assert "aliyun_asr_extractor" not in source


def test_extractors_do_not_touch_model_libraries():
    for module in _EXTRACTOR_MODULES:
        source = inspect.getsource(module)
        assert "WhisperModel(" not in source
        assert "from faster_whisper import" not in source


def test_asr_registry_exposes_expected_backends():
    names = list_transcriber_names()
    for expected in ("faster_whisper", "dashscope", "aliyun", "sensevoice"):
        assert expected in names, f"缺少 ASR 后端: {expected}"


def test_media_download_uses_shared_fetchers():
    """平台提取器不再自带 httpx/ffmpeg 下载实现，统一走 media 包。"""
    assert "HttpMediaFetcher" in inspect.getsource(bilibili_mod)
    assert "HttpMediaFetcher" in inspect.getsource(tikhub_mod)
    assert "YtDlpMediaFetcher" in inspect.getsource(ytdlp_mod)
