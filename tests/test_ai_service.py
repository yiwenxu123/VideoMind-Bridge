"""AI 服务测试"""

import os
import pytest
from pathlib import Path
import sys

from src.services.ai_service import AIService


TEST_TRANSCRIPT = """
[00:00:00] 大家好，今天我们来讨论知识管理的方法论
[00:01:30] 首先，我们需要理解什么是第二大脑
[00:03:45] 其次，建立知识管理系统的重要性
[00:05:20] 接下来讲解标签系统的使用方法
[00:08:15] 分享一些实际应用案例
[00:12:30] 最后总结与行动建议
"""


class TestAIServiceMock:
    """AI 服务 Mock 模式测试"""
    
    def test_mock_mode_initialization(self):
        """测试 Mock 模式初始化"""
        service = AIService(mock=True)
        assert service.mock is True
        assert service.api_key is None
    
    def test_mock_summarize(self):
        """测试 Mock 模式摘要生成"""
        service = AIService(mock=True)
        
        result = service.summarize(
            transcript=TEST_TRANSCRIPT,
            title="知识管理方法论"
        )
        
        assert result is not None
        assert result.title == "知识管理方法论"
        assert result.summary is not None
        assert len(result.summary) > 0
        assert len(result.highlights) > 0
    
    def test_mock_summarize_highlights_format(self):
        """测试 Mock 模式时间轴格式"""
        service = AIService(mock=True)
        
        result = service.summarize(
            transcript=TEST_TRANSCRIPT,
            title="测试视频"
        )
        
        for highlight in result.highlights:
            assert highlight.time is not None
            assert highlight.seconds >= 0
            assert highlight.content is not None
            assert len(highlight.content) > 0
    
    def test_mock_context_manager(self):
        """测试上下文管理器"""
        with AIService(mock=True) as service:
            result = service.summarize(
                transcript=TEST_TRANSCRIPT,
                title="测试"
            )
            assert result is not None


class TestAIServiceConnection:
    """AI 服务连接测试"""
    
    def test_connection_test_mock_mode(self):
        """测试 Mock 模式连接测试"""
        service = AIService(mock=True)
        success, message = service.test_connection()
        assert success is True
        assert "模拟模式" in message or "mock" in message.lower()


@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="需要设置 DEEPSEEK_API_KEY 环境变量"
)
class TestAIServiceRealAPI:
    """AI 服务真实 API 测试（需要有效的 API Key）"""

    def _check_key_valid(self, service):
        """检查 API Key 是否有效，无效则跳过"""
        try:
            success, message = service.test_connection()
            if not success:
                pytest.skip(f"API Key 无效: {message}")
        except Exception as e:
            if "401" in str(e) or "Unauthorized" in str(e).lower():
                pytest.skip(f"API Key 无效 (401): {e}")
    
    def test_real_api_summarize(self):
        """测试真实 API 摘要生成"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        service = AIService(api_key=api_key)
        self._check_key_valid(service)
        
        result = service.summarize(
            transcript=TEST_TRANSCRIPT,
            title="知识管理方法论"
        )
        
        assert result is not None
        assert result.title is not None
        assert result.summary is not None
        assert len(result.summary) > 0
    
    def test_real_api_connection(self):
        """测试真实 API 连接"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        service = AIService(api_key=api_key)
        self._check_key_valid(service)
        
        success, message = service.test_connection()
        assert success is True


class TestAIServiceParsing:
    """AI 服务响应解析测试"""
    
    def test_parse_highlight_line(self):
        """测试时间轴解析"""
        service = AIService(mock=True)
        
        highlight = service._parse_highlight_line("- [00:05:23] 测试要点内容")
        assert highlight is not None
        assert highlight.time == "00:05:23"
        assert highlight.seconds == 323
        assert "测试要点内容" in highlight.content
    
    def test_parse_highlight_line_without_brackets(self):
        """测试无括号时间轴解析"""
        service = AIService(mock=True)
        
        highlight = service._parse_highlight_line("- 00:01:30 另一个测试要点")
        assert highlight is not None
        assert highlight.time == "00:01:30"
        assert highlight.seconds == 90
    
    def test_time_to_seconds(self):
        """测试时间转换"""
        service = AIService(mock=True)
        
        assert service._time_to_seconds("00:00:30") == 30
        assert service._time_to_seconds("00:01:30") == 90
        assert service._time_to_seconds("01:00:00") == 3600
        assert service._time_to_seconds("01:30:45") == 5445


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
