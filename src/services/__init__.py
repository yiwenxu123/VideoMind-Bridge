"""服务层模块

提供 v1 处理链服务: 下载 / 转录 / AI 摘要 / 导出编排。

注意: 曾存在一套 Protocol/ABC 假接口 (interfaces.py), 与真实实现签名不符,
已被删除。各服务直接使用具体类型 (DownloadService / TranscribeService /
AIService / ExportOrchestrator)。
"""
