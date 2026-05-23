"""AI 服务实现 - 支持 DeepSeek 和 Ollama"""

import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

import httpx
from jinja2 import Template

from ..models.task import Highlight
from .prompt_template import get_prompt_template_manager, PromptTemplate
from ..utils import get_logger
from ..utils.exceptions import AIError

logger = get_logger(__name__)


@dataclass
class SummaryResult:
    """摘要结果"""
    title: str
    summary: str  # 一句话总结
    highlights: List[Highlight] = field(default_factory=list)  # 结构化时间轴


class AIService:
    """AI 摘要服务 - 支持多种国内模型"""

    # 默认配置
    DEFAULT_MODEL = "deepseek-chat"
    DEFAULT_TEMPERATURE = 0.7
    DEFAULT_MAX_TOKENS = 2000
    DEFAULT_TIMEOUT = 120.0

    # 重试配置
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # 初始重试延迟（秒）
    RETRY_BACKOFF = 2.0  # 指数退避因子

    # 引擎默认 API 端点
    DEFAULT_ENDPOINTS = {
        "deepseek": "https://api.deepseek.com/v1",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "moonshot": "https://api.moonshot.cn/v1",
        "minimax": "https://api.minimax.chat/v1",
        "doubao": "https://ark.cn-beijing.volces.com/api/v3",
        "ollama": "http://localhost:11434/v1",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        mock: bool = False,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        初始化 AI 服务

        Args:
            api_key: API 密钥，优先级：传入参数 > 环境变量
            base_url: API 基础 URL，默认根据模型自动选择
            mock: 是否使用模拟模式（不调用真实 API）
            model: 模型名称，默认 deepseek-chat
            temperature: 温度参数，默认 0.7
            max_tokens: 最大 token 数，默认 2000
        """
        self.model = model or self.DEFAULT_MODEL
        self.mock = mock
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else self.DEFAULT_MAX_TOKENS

        # 根据模型自动选择 API 端点
        if base_url:
            self.base_url = base_url
        else:
            self.base_url = self._get_default_endpoint(self.model)

        # 根据端点选择 API Key 环境变量
        self.api_key = api_key or self._get_api_key_from_env()

        if not self.mock and not self.api_key:
            raise ValueError(
                f"API Key 未配置，请设置对应环境变量或使用 mock=True 参数进行测试"
            )

        # 创建 HTTP 客户端（带连接池）
        self._client: Optional[httpx.Client] = None

    def _mask_api_key(self, api_key: Optional[str]) -> str:
        """
        对 API Key 进行脱敏处理，用于日志输出

        Args:
            api_key: 原始 API Key

        Returns:
            str: 脱敏后的 API Key（如 sk-****1234）
        """
        if not api_key:
            return "未设置"
        if len(api_key) <= 8:
            return "****"
        # 显示前4位和后4位，中间用****代替
        return f"{api_key[:4]}****{api_key[-4:]}"

    def _get_default_endpoint(self, model: str) -> str:
        """根据模型名称获取默认 API 端点"""
        model_lower = model.lower()
        if "glm" in model_lower:
            return self.DEFAULT_ENDPOINTS["zhipu"]
        elif "moonshot" in model_lower or "kimi" in model_lower:
            return self.DEFAULT_ENDPOINTS["moonshot"]
        elif "minimax" in model_lower or "minmax" in model_lower or "abab" in model_lower:
            return self.DEFAULT_ENDPOINTS["minimax"]
        elif "doubao" in model_lower:
            return self.DEFAULT_ENDPOINTS["doubao"]
        elif "llama" in model_lower or "mistral" in model_lower or "qwen" in model_lower:
            return self.DEFAULT_ENDPOINTS["ollama"]
        else:
            return self.DEFAULT_ENDPOINTS["deepseek"]

    def _get_api_key_from_env(self) -> Optional[str]:
        """从环境变量获取 API Key"""
        # 尝试多个可能的环境变量
        env_vars = [
            "DEEPSEEK_API_KEY",
            "ZHIPU_API_KEY",
            "MOONSHOT_API_KEY",
            "MINIMAX_API_KEY",
            "DOUBAO_API_KEY",
        ]
        for var in env_vars:
            key = os.getenv(var)
            if key:
                return key
        return None

    def _get_client(self) -> httpx.Client:
        """获取或创建 HTTP 客户端（带连接池）"""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(
                    connect=30.0,
                    read=self.DEFAULT_TIMEOUT,
                    write=30.0,
                    pool=10.0
                ),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
            logger.debug("创建 HTTP 客户端（带连接池和超时配置）")
        return self._client

    def close(self) -> None:
        """关闭 HTTP 客户端，释放连接"""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.debug("关闭 HTTP 客户端")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()
        return False

    def summarize(
        self,
        transcript: str,
        prompt_template: Optional[str] = None,
        template_id: Optional[str] = None,
        title: str = "",
        max_tokens: int = 4000
    ) -> SummaryResult:
        """
        生成视频摘要（包含结构化时间轴）

        Args:
            transcript: 转录文本（带时间戳格式）
            prompt_template: Prompt 模板字符串（Jinja2 语法，优先级高于 template_id）
            template_id: Prompt 模板 ID，从模板管理器获取
            title: 视频标题
            max_tokens: 最大 token 数

        Returns:
            SummaryResult: 结构化摘要结果，包含时间轴要点
        """
        if self.mock:
            return self._mock_summarize(transcript, title)

        # 获取 Prompt 模板
        if prompt_template is not None:
            # 直接使用传入的模板字符串
            template_content = prompt_template
        elif template_id is not None:
            # 从模板管理器获取
            manager = get_prompt_template_manager()
            template_obj = manager.get_template(template_id)
            if template_obj:
                template_content = template_obj.template
            else:
                # 模板不存在，使用默认
                template_content = self._default_prompt()
        else:
            # 使用默认模板
            template_content = self._default_prompt()

        # 渲染模板
        template = Template(template_content)

        # 截断文本（粗略估计：1 token ≈ 4 字符）
        max_chars = max_tokens * 4
        truncated_transcript = transcript[:max_chars]
        if len(transcript) > max_chars:
            truncated_transcript += "\n\n[内容已截断...]"

        prompt = template.render(
            title=title,
            transcript=truncated_transcript
        )

        # 调用 API
        response = self._call_llm(prompt)

        # 解析结果
        return self._parse_response(response, title)

    def _call_llm(self, prompt: str) -> str:
        """调用 LLM API（带重试机制）"""
        # 清理 API Key，移除换行符和空格
        api_key = self.api_key.strip() if self.api_key else None
        if not api_key:
            raise ValueError("API Key 未设置")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的视频内容分析师，擅长提取关键信息并生成结构化摘要。你必须严格按照要求的格式输出，包含具体的时间戳。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        # 带指数退避的重试机制
        last_exception = None
        for attempt in range(self.MAX_RETRIES):
            try:
                client = self._get_client()
                response = client.post(
                    "/chat/completions",
                    headers=headers,
                    json=data,
                )
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                logger.debug(f"API 调用成功（第 {attempt + 1} 次尝试）")
                return content

            except httpx.HTTPStatusError as e:
                # HTTP 错误（4xx, 5xx）
                last_exception = e
                if e.response.status_code >= 500:
                    # 服务器错误，可以重试
                    logger.warning(f"API 服务器错误（{e.response.status_code}），第 {attempt + 1} 次尝试失败，准备重试...")
                else:
                    # 客户端错误，不重试
                    logger.error(f"API 客户端错误（{e.response.status_code}）: {e}")
                    raise

            except httpx.NetworkError as e:
                # 网络错误，可以重试
                last_exception = e
                logger.warning(f"网络错误，第 {attempt + 1} 次尝试失败，准备重试...")

            except httpx.TimeoutException as e:
                # 超时，可以重试
                last_exception = e
                logger.warning(f"请求超时，第 {attempt + 1} 次尝试失败，准备重试...")

            except Exception as e:
                # 其他错误，记录后重试
                last_exception = e
                logger.warning(f"API 调用失败，第 {attempt + 1} 次尝试: {e}")

            # 计算退避延迟
            if attempt < self.MAX_RETRIES - 1:
                delay = self.RETRY_DELAY * (self.RETRY_BACKOFF ** attempt)
                logger.info(f"等待 {delay:.1f} 秒后重试...")
                time.sleep(delay)

        # 所有重试都失败了
        logger.error(f"API 调用在 {self.MAX_RETRIES} 次尝试后仍然失败")
        raise AIError(
            f"API 调用失败（已重试 {self.MAX_RETRIES} 次）: {last_exception}",
            error_code="GENERATION_FAILED",
            details={"retries": self.MAX_RETRIES, "last_error": str(last_exception)}
        ) from last_exception

    def test_connection(self) -> tuple[bool, str]:
        """
        测试 API 连接是否正常

        Returns:
            tuple[bool, str]: (是否成功, 错误信息/成功消息)
        """
        if self.mock:
            return True, "模拟模式，无需测试"

        if not self.api_key:
            return False, "API Key 未配置"

        try:
            # 发送简单的测试请求
            headers = {
                "Authorization": f"Bearer {self.api_key.strip()}",
                "Content-Type": "application/json"
            }

            data = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": "你好"}
                ],
                "max_tokens": 10
            }

            client = self._get_client()
            response = client.post(
                "/chat/completions",
                headers=headers,
                json=data,
                timeout=30.0
            )
            response.raise_for_status()

            logger.info(f"API 连接测试成功: {self.model}")
            return True, "连接成功"

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP 错误 {e.response.status_code}"
            if e.response.status_code == 401:
                error_msg = "API Key 无效或已过期"
            elif e.response.status_code == 429:
                error_msg = "请求过于频繁，请稍后再试"
            elif e.response.status_code >= 500:
                error_msg = "服务器错误，请稍后再试"
            logger.error(f"API 连接测试失败: {error_msg}")
            return False, error_msg

        except httpx.NetworkError:
            error_msg = "网络连接失败，请检查网络设置"
            logger.error(f"API 连接测试失败: {error_msg}")
            return False, error_msg

        except httpx.TimeoutException:
            error_msg = "连接超时，请检查网络或稍后重试"
            logger.error(f"API 连接测试失败: {error_msg}")
            return False, error_msg

        except Exception as e:
            error_msg = f"连接失败: {str(e)}"
            logger.error(f"API 连接测试失败: {error_msg}")
            return False, error_msg

    def _parse_response(self, response: str, title: str) -> SummaryResult:
        """解析 LLM 响应为结构化数据（包含时间轴）"""
        lines = response.strip().split("\n")

        extracted_title = title
        summary = ""
        highlights: List[Highlight] = []

        current_section = None
        current_time = ""
        current_content = ""

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检测章节
            if line.startswith("# "):
                current_section = "title"
                extracted_title = line.replace("# ", "").strip()
            elif line.startswith("## 一句话总结") or "一句话总结" in line:
                current_section = "summary"
            elif line.startswith("## 关键时间轴") or "关键时间轴" in line or "时间轴" in line:
                current_section = "highlights"
            elif line.startswith("-") or line.startswith("*"):
                # 列表项
                if current_section == "summary":
                    summary = line.lstrip("- *").strip()
                elif current_section == "highlights":
                    # 解析时间戳和要点
                    highlight = self._parse_highlight_line(line)
                    if highlight:
                        highlights.append(highlight)
            elif "时间:" in line or "Time:" in line:
                # 时间行
                current_time = self._extract_time(line)
            elif "内容:" in line or "Content:" in line:
                # 内容行
                current_content = line.split(":", 1)[1].strip()
                if current_time and current_content:
                    seconds = self._time_to_seconds(current_time)
                    highlights.append(Highlight(
                        time=current_time,
                        seconds=seconds,
                        content=current_content
                    ))
                    current_time = ""
                    current_content = ""
            else:
                # 普通文本
                if current_section == "summary" and not summary:
                    summary = line

        # 如果解析失败，使用原始响应作为总结
        if not summary:
            summary = response[:200] + "..." if len(response) > 200 else response

        # 如果没有提取到时间轴，从转录文本中生成一些默认的
        if not highlights:
            highlights = self._generate_default_highlights()

        return SummaryResult(
            title=extracted_title or title,
            summary=summary,
            highlights=highlights
        )

    def _parse_highlight_line(self, line: str) -> Optional[Highlight]:
        """解析单行要点，提取时间戳和内容"""
        # 尝试匹配 [00:05:23] 或 00:05:23 格式
        time_pattern = r"\[?(\d{1,2}:\d{2}:\d{2})\]?"
        match = re.search(time_pattern, line)

        if match:
            time_str = match.group(1)
            seconds = self._time_to_seconds(time_str)

            # 提取内容（去掉时间戳部分）
            content = re.sub(time_pattern, "", line)
            content = content.lstrip("- *:. ").strip()

            if content:
                return Highlight(time=time_str, seconds=seconds, content=content)

        return None

    def _extract_time(self, line: str) -> str:
        """从行中提取时间"""
        match = re.search(r"(\d{1,2}:\d{2}:\d{2})", line)
        return match.group(1) if match else "00:00:00"

    def _time_to_seconds(self, time_str: str) -> int:
        """将时间字符串转换为秒数"""
        parts = time_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        return 0

    def _generate_default_highlights(self) -> List[Highlight]:
        """生成默认时间轴（当 AI 没有返回时）"""
        return [
            Highlight(time="00:00:00", seconds=0, content="视频开始"),
        ]

    def _mock_summarize(self, transcript: str, title: str) -> SummaryResult:
        """模拟摘要（用于测试）"""
        return SummaryResult(
            title=title or "测试视频标题",
            summary="这是一个测试摘要，展示了 AI 服务的基本功能。在实际使用中，这里会显示真实的 AI 生成的内容总结。",
            highlights=[
                Highlight(time="00:01:30", seconds=90, content="介绍知识管理的核心理念"),
                Highlight(time="00:03:45", seconds=225, content="演示如何建立双向链接"),
                Highlight(time="00:05:20", seconds=320, content="讲解标签系统的使用方法"),
                Highlight(time="00:08:15", seconds=495, content="分享实际应用案例"),
                Highlight(time="00:12:30", seconds=750, content="总结与行动建议"),
            ]
        )

    def _default_prompt(self) -> str:
        """默认 Prompt 模板"""
        return """请分析以下视频转录内容，生成结构化摘要和时间轴。

视频标题: {{title}}

转录内容:
{{transcript}}

请按以下格式输出：

# {{title}}

## 一句话总结
[用一句话概括视频核心内容]

## 关键时间轴
从转录文本中提取 5-8 个关键时间点，格式如下：

- [00:05:23] 要点1内容
- [00:08:15] 要点2内容
- [00:12:30] 要点3内容
...

要求：
1. 每个要点必须包含具体时间戳 [HH:MM:SS] 格式
2. 时间戳要精确到秒
3. 要点要覆盖视频的核心内容
4. 语言简洁明了
"""


