## 优化目标
将AI引擎配置从海外模型（GPT、Claude）替换为2025年最新的国内模型

## 修正后的模型配置

### 引擎列表（移除海外模型，新增国内模型）

**移除：**
- Claude-3.5-Sonnet
- GPT-4
- GPT-3.5-Turbo

**新增（2025年最新）：**
1. **DeepSeek** - deepseek-chat, deepseek-reasoner
2. **智谱AI** - glm-4, glm-4-plus, glm-4-flash, glm-4-air
3. **Moonshot AI (Kimi)** - moonshot-v1-8k/32k/128k, kimi-latest
4. **MiniMax** - MiniMax-Text-01, abab6.5-chat
5. **豆包** - doubao-1.6-pro, doubao-1.6-lite, doubao-1.6-flash
6. **本地 Ollama** - 保持不变

### 各引擎默认模型（性价比最高）

| 引擎 | 默认模型 | 特点 |
|-----|---------|------|
| DeepSeek | deepseek-chat | 速度快、成本低、中文优秀 |
| 智谱AI | glm-4-flash | 免费，128K上下文 |
| Kimi | moonshot-v1-32k | 平衡性能和成本 |
| MiniMax | MiniMax-Text-01 | 400万超长上下文 |
| 豆包 | doubao-1.6-lite | 成本极低，速度快 |

### API 端点配置

- DeepSeek: `https://api.deepseek.com/v1`
- 智谱: `https://open.bigmodel.cn/api/paas/v4`
- Kimi: `https://api.moonshot.cn/v1`
- MiniMax: `https://api.minimax.chat/v1`
- 豆包: `https://ark.cn-beijing.volces.com/api/v3`

### 修改文件

1. **src/gui/widgets/ai_config.py**
   - 更新 engine_combo 选项列表
   - 更新 _on_engine_changed 方法中的模型映射
   - 更新默认模型选择

2. **src/services/ai_service.py** (可选)
   - 如需要适配不同API格式，添加对应的请求构造逻辑

## 预期效果
用户可以在AI配置中选择2025年最新的国内模型，无需翻墙，且成本更低。