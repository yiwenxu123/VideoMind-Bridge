"""ASR 架构防回归测试（阶段 0.6）

锁定阶段 0 收敛后的结构约束，避免后续改造又把 ASR 实现散回提取器里。
"""

from __future__ import annotations

import inspect
from unittest import mock

from src.core.extractors import create_all_extractors, list_extractors
from src.core.extractors import tikhub_extractor as tikhub_mod
from src.core.extractors import ytdlp_asr_extractor as ytdlp_mod


def test_aliyun_asr_not_registered_as_extractor():
    """阿里云 ASR 需要先下载音频，不能作为 URL 提取器参与路由。"""
    assert "aliyun_asr" not in list_extractors()
    names = [extractor.platform_name for extractor in create_all_extractors()]
    assert "aliyun_asr" not in names


def test_tikhub_has_no_direct_whisper_model():
    """TikHub 必须复用共享转写实现，不能自行实例化模型。"""
    source = inspect.getsource(tikhub_mod)
    assert "WhisperModel(" not in source
    assert "from faster_whisper import" not in source
    assert "shared_transcribe_local" in source


def test_ytdlp_asr_does_not_touch_credentials_at_construction():
    """构造提取器时不应读取阿里云密钥；只有真正走云端降级时才懒加载。"""
    with mock.patch.object(ytdlp_mod.AliyunASRExtractor, "_resolve_api_key") as resolve:
        ytdlp_mod.YtDlpASRExtractor()
    resolve.assert_not_called()
