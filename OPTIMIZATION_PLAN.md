# VideoMind Bridge 项目优化方案

## 一、项目现状分析

### 1.1 现有优势
- ✅ 多平台支持（9个提取器：抖音、B站、小红书、YouTube、Coze、yt-dlp、tikhub、Apify、阿里云ASR）
- ✅ 智能路由（成本感知、自动降级）
- ✅ 内容预筛（规则引擎分级评估）
- ✅ 多种使用方式（CLI、GUI、MCP Server、API）
- ✅ 插件化提取器架构
- ✅ 零Cookie提取方案

### 1.2 主要问题
- ❌ **抖音功能不完整**：只提取文案（页面解析），不下载视频，无语音识别
- ❌ **抖音稳定性**：依赖页面HTML解析，接口变化可能导致提取失败
- ❌ **代码复杂度高**：9个提取器+多种使用方式，结构混乱
- ❌ **依赖管理混乱**：多个Python环境（.venv / uv），依赖冲突风险
- ❌ **测试覆盖不足**：核心功能缺乏自动化测试
- ❌ **文档滞后**：代码更新快，文档未及时更新

### 1.3 与 douyin-mcp-server 的互补分析

| 维度 | VideoMind Bridge (当前) | douyin-mcp-server | 整合后 |
|------|------------------------|-------------------|--------|
| **视频下载** | ❌ | ✅ 无水印下载 | ✅ |
| **语音识别** | ❌ 无 | ✅ 阿里云ASR | ✅ |
| **抖音稳定性** | ⚠️ 页面解析 | ✅ 移动端API | ✅ |
| **多平台支持** | ✅ 9个提取器 | ❌ 仅抖音 | ✅ |
| **智能路由** | ✅ | ❌ | ✅ |

## 二、架构优化方案

### 2.1 新目录结构

```
src/
├── __init__.py
├── cli.py                    # 命令行入口
├── main.py                   # 应用入口
├── core/                     # 核心业务逻辑
│   ├── __init__.py
│   ├── models.py             # 数据模型（保留现有）
│   ├── router.py             # 智能路由（保留现有）
│   ├── prescreener.py        # 内容预筛（保留现有）
│   └── pipeline.py           # 【新增】处理流水线编排
├── extractors/               # 提取器（保留现有结构）
│   ├── __init__.py
│   ├── base.py               # 基类（保留现有）
│   ├── bilibili_extractor.py # 【简化】只保留核心逻辑
│   ├── douyin_extractor.py   # 【重构】整合douyin-mcp-server
│   ├── xiaohongshu_extractor.py
│   ├── youtube_extractor.py
│   └── ...                   # 其他提取器
├── processors/               # 【新增】内容处理器
│   ├── __init__.py
│   ├── transcriber.py        # 语音转录（整合阿里云ASR）
│   ├── downloader.py         # 下载管理（整合yt-dlp）
│   └── formatter.py          # 格式化（保留现有）
├── services/                 # 【整合】服务层
│   ├── __init__.py
│   ├── config_manager.py     # 配置管理（统一配置来源）
│   └── ai_service.py         # AI服务
├── outputs/                  # 输出目标（保留现有）
├── api/                      # API服务（保留现有）
├── gui/                      # GUI（保留现有）
├── mcp/                      # MCP服务器（保留现有）
└── utils/                    # 工具函数（保留现有）
```

**核心变化**：
1. **新增 `processors/` 模块**：将下载、转录等通用处理逻辑从提取器中抽离
2. **简化提取器**：提取器只负责获取原始数据，处理交给处理器
3. **新增 `pipeline.py`**：编排完整处理流程

### 2.2 提取器接口优化

#### 当前接口（仅提取文案）
```python
class ContentExtractor(ABC):
    @abstractmethod
    def extract(self, url: str) -> ExtractResult:
        """从URL提取文案内容"""
        ...
```

#### 优化后接口（支持视频下载）
```python
class ContentExtractor(ABC):
    """内容提取器抽象基类"""
    
    @abstractmethod
    def extract(self, url: str) -> ExtractResult:
        """从URL提取内容（文案/元数据）"""
        ...
    
    def download(self, url: str, output_dir: str) -> dict | None:
        """下载视频文件（可选实现）
        
        返回: {"video_path": "xxx.mp4", "audio_path": "xxx.mp3", ...}
        """
        return None
    
    def transcribe(self, audio_path: str) -> str:
        """转录音频为文字（可选实现）"""
        return ""
```

### 2.3 抖音提取器重构（核心改动）

#### 整合 douyin-mcp-server 的关键代码

将 douyin-mcp-server 中的 `DouyinProcessor` 类整合进 `douyin_extractor.py`：

```python
# src/extractors/douyin_extractor.py 的增强版

class DouyinExtractor(ContentExtractor):
    """增强版抖音提取器（整合视频下载 + 语音识别）"""
    
    platform_name = "douyin"
    _cost_tier = CostTier.PAID  # 需要阿里云ASR，属于付费服务
    
    def __init__(self):
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)
        # 整合 douyin-mcp-server 的配置
        self.aliyun_token = os.getenv('ALIYUN_TOKEN')
        self.aliyun_appkey = os.getenv('ALIYUN_APPKEY')
        self.access_key_id = os.getenv('ALIYUN_ACCESS_KEY_ID')
        self.access_key_secret = os.getenv('ALIYUN_ACCESS_KEY_SECRET')
    
    def extract(self, url: str) -> ExtractResult:
        """提取抖音视频内容（文案 + 元数据）"""
        try:
            # 1. 解析链接获取视频信息
            video_info = self._parse_share_url(url)
            
            # 2. 从页面提取文案（快速返回）
            content = self._extract_description_from_html(video_info)
            
            return ExtractResult(
                success=True,
                platform="douyin",
                title=video_info["title"],
                content=content or "",
                source="douyin_page",
                url=url,
                cost_tier=CostTier.FREE,  # 页面解析免费
                metadata={"video_id": video_info["video_id"]},
            )
        except Exception as e:
            return ExtractResult(
                success=False, platform="douyin", title="", content="",
                source="douyin", url=url, cost_tier=CostTier.FREE,
                error=f"抖音提取失败: {e}",
            )
    
    def download(self, url: str, output_dir: str) -> dict | None:
        """下载抖音视频（整合 douyin-mcp-server 逻辑）"""
        try:
            # 1. 获取视频信息
            video_info = self._parse_share_url(url)
            
            # 2. 下载视频文件
            filepath = self._download_video(video_info["url"], 
                                            output_dir, 
                                            video_info["video_id"])
            
            return {
                "video_path": str(filepath),
                "video_id": video_info["video_id"],
                "title": video_info["title"],
            }
        except Exception as e:
            print(f"下载失败: {e}")
            return None
    
    def _parse_share_url(self, url: str) -> dict:
        """解析抖音分享链接获取视频信息（douyin-mcp-server 核心逻辑）"""
        # 从 douyin_downloader.py 的 parse_share_url 移植
        # 使用 iesdouyin 移动端 API
        share_url = self._resolve_share_url(url)
        response = self._client.get(share_url)
        # ... 解析逻辑
        return {"url": video_url, "title": title, "video_id": video_id}
    
    def _download_video(self, video_url: str, output_dir: str, video_id: str) -> Path:
        """下载视频文件（douyin-mcp-server 核心逻辑）"""
        response = requests.get(video_url, stream=True)
        filepath = Path(output_dir) / f"{video_id}.mp4"
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return filepath
```

#### 新增阿里云语音识别服务

```python
# src/processors/transcriber.py

class AliyunTranscriber:
    """阿里云语音识别处理器"""
    
    def __init__(self, config: dict):
        self.access_key_id = config.get('access_key_id')
        self.access_key_secret = config.get('access_key_secret')
        self.appkey = config.get('appkey')
    
    def transcribe(self, audio_path: str) -> str:
        """将音频文件转录为文字"""
        # 1. 获取Token
        token = self._get_token()
        
        # 2. 转换音频为PCM格式
        pcm_path = self._convert_to_pcm(audio_path)
        
        # 3. 调用阿里云一句话识别API
        text = self._call_asr_api(token, pcm_path)
        
        return text
    
    def _get_token(self) -> str:
        """获取阿里云Token"""
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
        client = AcsClient(self.access_key_id, self.access_key_secret, 'cn-shanghai')
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')
        response = client.do_action_with_exception(request)
        result = json.loads(response.decode())
        return result['Token']['Id']
```

### 2.4 处理流水线（Pipeline）

```python
# src/core/pipeline.py

class VideoProcessingPipeline:
    """视频处理流水线"""
    
    def __init__(self, config: dict):
        self.config = config
        self.extractors = self._init_extractors()
        self.transcriber = self._init_transcriber()
    
    def process(self, url: str, options: dict = None) -> dict:
        """完整处理流程"""
        # 1. 平台识别
        platform = self._identify_platform(url)
        
        # 2. 内容预筛（快速评估价值）
        prescreen_result = self._prescreen(url, platform)
        if not self._should_proceed(prescreen_result):
            return {"skip": True, "grade": prescreen_result.grade}
        
        # 3. 提取内容
        extractor = self._get_extractor(platform)
        extract_result = extractor.extract(url)
        
        # 4. 下载视频（可选）
        download_result = None
        if options.get('download', True):
            download_result = extractor.download(url, options.get('output_dir'))
        
        # 5. 语音转录（如果内容为空且有视频）
        transcript = extract_result.content
        if not transcript and download_result:
            audio_path = self._extract_audio(download_result['video_path'])
            transcript = self.transcriber.transcribe(audio_path)
        
        # 6. 返回结果
        return {
            "success": True,
            "platform": platform,
            "title": extract_result.title,
            "content": transcript,
            "video_path": download_result.get('video_path') if download_result else None,
        }
```

### 2.5 配置管理统一

#### 配置文件层次
```
~/.env              # 全局环境变量（敏感信息：API密钥）
./config.yaml       # 项目配置文件（非敏感设置）
./.env              # 本地环境变量覆盖（可选）
```

#### 环境变量规范
```env
# 阿里云语音识别（必配）
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
ALIYUN_APPKEY=your_app_key

# 硅基流动（可选，阿里云失败时回退）
SILICONFLOW_API_KEY=your_key

# AI模型（可选，用于摘要生成）
DEEPSEEK_API_KEY=your_key
OPENAI_API_KEY=your_key

# 输出目标（可选）
OBSIDIAN_VAULT_PATH=/path/to/vault
NOTION_API_KEY=your_key
```

#### 配置加载优先级
1. 命令行参数（最高优先级）
2. 环境变量
3. 项目配置文件 (`config.yaml`)
4. 全局环境变量 (`~/.env`)
5. 默认值（最低优先级）

## 三、分阶段实施计划

### 第一阶段：核心重构（预计1-2天）

1. **目录结构调整**
   - 创建 `processors/` 目录
   - 将下载和转录逻辑从提取器中抽离
   - 创建 `pipeline.py` 编排流程

2. **抖音提取器增强**
   - 整合 douyin-mcp-server 的 `parse_share_url` 逻辑
   - 添加视频下载功能
   - 添加音频提取功能
   - 添加阿里云语音识别调用

3. **配置管理统一**
   - 创建配置加载模块
   - 统一环境变量命名规范
   - 添加配置验证

### 第二阶段：功能完善（预计1-2天）

1. **依赖管理**
   - 更新 `pyproject.toml`
   - 锁定依赖版本
   - 清理冗余依赖

2. **测试覆盖**
   - 为抖音提取器编写单元测试
   - 为下载功能编写测试
   - 为语音识别编写测试

3. **错误处理**
   - 完善异常处理
   - 添加重试机制
   - 统一错误提示格式

### 第三阶段：优化收尾（预计1天）

1. **文档更新**
   - 更新 README
   - 添加配置说明
   - 添加使用示例

2. **性能优化**
   - 优化下载速度
   - 优化语音识别流程
   - 添加进度显示

3. **兼容性测试**
   - 测试抖音提取功能
   - 测试其他平台兼容性
   - 测试 MCP Server 集成

## 四、预期收益

### 功能层面
- ✅ 抖音视频下载功能（无水印）
- ✅ 完整的语音转文字流程
- ✅ 更稳定的抖音内容提取
- ✅ 统一的配置管理

### 代码层面
- ✅ 清晰的模块职责划分
- ✅ 降低提取器复杂度
- ✅ 提高代码复用性
- ✅ 便于后续扩展

### 用户体验
- ✅ 一次配置，全平台可用
- ✅ 更清晰的使用指南
- ✅ 更稳定的性能
- ✅ 更好的错误提示

## 五、风险评估

### 技术风险
| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 抖音接口变化 | 高 | 高 | 监控更新，及时调整 |
| 阿里云Token过期 | 中 | 中 | 自动刷新Token |
| 依赖冲突 | 低 | 中 | 使用虚拟环境隔离 |
| 长视频处理慢 | 中 | 低 | 分段处理，异步执行 |

### 实施风险
| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 重构引入Bug | 中 | 中 | 渐进式重构，充分测试 |
| 功能缺失 | 低 | 低 | 保留旧代码作为回退 |
| 时间超支 | 中 | 低 | 优先核心功能 |

## 六、结论

### 该方案的核心价值

1. **填补抖音功能空白**：将 douyin-mcp-server 下载+ASR能力整合进来
2. **降低维护成本**：统一架构，减少重复代码
3. **提高稳定性**：从页面解析升级到移动端API
4. **保留扩展性**：插件化架构，易于添加新平台

### 建议行动

1. **立即开始第一阶段**：目录结构调整 + 抖音提取器增强
2. **同步测试**：每完成一个模块立即测试
3. **保持回退**：保留旧版本代码，直到新版本验证通过

**这个方案不是大拆大建，而是有策略地增强核心能力**。目前 VideoMind Bridge 的架构基础很好，只需要在抖音这个单点上注入 douyin-mcp-server 的成熟能力，其他平台可以平滑保持现有实现。
