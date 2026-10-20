"""ASR 适配器注册入口

导入即触发各适配器向 registry 注册。适配器模块本身保持轻量：
模型加载在 transcribe() 内、密钥读取在 capabilities()/transcribe() 内。
"""

from . import aliyun, dashscope, faster_whisper, sensevoice  # noqa: F401
