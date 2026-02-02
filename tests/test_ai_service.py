"""AI 服务测试"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.ai_service import AIService


def test_mock_mode():
    """测试 Mock 模式"""
    print("=== 测试 Mock 模式 ===")
    service = AIService(mock=True)

    test_transcript = """
[00:00:00] 大家好，今天我们来讨论知识管理的方法论
[00:01:30] 首先，我们需要理解什么是第二大脑
[00:03:45] 其次，建立知识管理系统的重要性
[00:05:20] 接下来讲解标签系统的使用方法
[00:08:15] 分享一些实际应用案例
[00:12:30] 最后总结与行动建议
"""

    result = service.summarize(
        transcript=test_transcript,
        title="知识管理方法论"
    )

    print(f"标题: {result.title}")
    print(f"总结: {result.summary}")
    print("\n关键时间轴:")
    for h in result.highlights:
        print(f"  [{h.time}] ({h.seconds}s) - {h.content}")

    return True


def test_real_api():
    """测试真实 API（如果有 key）"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("\n跳过真实 API 测试（未设置 DEEPSEEK_API_KEY）")
        return False

    print("\n=== 测试真实 API ===")
    service = AIService(api_key=api_key)

    test_transcript = """
[00:00:00] 大家好，今天我们来讨论知识管理的方法论
[00:01:30] 首先，我们需要理解什么是第二大脑
[00:03:45] 其次，建立知识管理系统的重要性
[00:05:20] 接下来讲解标签系统的使用方法
[00:08:15] 分享一些实际应用案例
[00:12:30] 最后总结与行动建议
"""

    result = service.summarize(
        transcript=test_transcript,
        title="知识管理方法论"
    )
    print(f"标题: {result.title}")
    print(f"总结: {result.summary}")
    print("\n关键时间轴:")
    for h in result.highlights:
        print(f"  [{h.time}] ({h.seconds}s) - {h.content}")

    return True


if __name__ == "__main__":
    test_mock_mode()
    test_real_api()
