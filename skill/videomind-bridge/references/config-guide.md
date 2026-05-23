# 配置与环境变量

## 环境变量

### AI 服务 API Key（至少配置一个）

| 变量名 | 提供商 | 获取地址 | 推荐度 |
|--------|--------|----------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek | https://platform.deepseek.com | ⭐⭐⭐⭐⭐ |
| `ZHIPU_API_KEY` | 智谱AI | https://open.bigmodel.cn | ⭐⭐⭐⭐ |
| `MOONSHOT_API_KEY` | Moonshot | https://platform.moonshot.cn | ⭐⭐⭐ |
| `MINIMAX_API_KEY` | MiniMax | https://api.minimax.chat | ⭐⭐⭐ |
| `DOUBAO_API_KEY` | 豆包 | https://www.volcengine.com | ⭐⭐⭐ |

### 其他环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `VIDEOMIND_LOG_LEVEL` | `INFO` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像地址 |

## 配置文件

### 主配置文件路径

```
~/.config/VideoMind/config.yaml
```

### 配置文件结构

```yaml
ai:
  engine: deepseek
  model: deepseek-chat
  api_key: ""  # 建议通过环境变量设置
  temperature: 0.3
  max_tokens: 4096

download:
  output_dir: ~/Downloads/VideoMind
  video_quality: best
  keep_video: true

transcribe:
  whisper_model: small
  language: zh

export:
  obsidian:
    vault_path: ""
    subfolder: VideoMind
  local:
    output_path: ~/Downloads/VideoMind
    organize_by: date
  webhook:
    url: ""
    headers: {}
    timeout: 30

ui:
  theme: system
  language: zh_CN

performance:
  max_concurrent_exports: 3
  model_cache_size: 2
```

## API Key 安全管理

VideoMind Bridge 使用系统密钥环（macOS Keychain）安全存储 API Key：

1. **优先级**：环境变量 > 密钥环 > 配置文件
2. **自动迁移**：配置文件中的明文 API Key 会自动迁移到密钥环
3. **日志脱敏**：API Key 在日志中显示为 `sk-****1234`

## Ollama 本地模型

如果安装了 Ollama，可使用本地模型（无需 API Key）：

```bash
# 安装 Ollama
brew install ollama

# 拉取模型
ollama pull qwen2.5:7b

# 在配置中设置
# ai.engine: ollama
# ai.model: qwen2.5:7b
```
