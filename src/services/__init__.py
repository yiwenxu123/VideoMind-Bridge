"""服务层模块（2026-11-25 A2 之后）

只剩三件事：
- `config_manager`：配置与密钥（keyring → env 兜底）
- `local_media`：本地路径白名单（`/api/v1/parse` 用）
- `export_orchestrator`：并发导出编排（archiver 复用）

v1 的 DownloadService / TranscribeService / AIService / TaskDatabase / TimeEstimator
随 v1 流水线一并删除；转写能力现在走 `src/core/asr/` 的降级链。
"""