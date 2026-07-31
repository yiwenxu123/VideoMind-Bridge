# A 级优秀优化计划

**基线 (2026-05-24):** Lint 125 条 / 覆盖 43.5% / 测试 152/152 通过 / Web ✅ GUI ✅

---

## 🔴 P0 — 必须完成 (A 级门槛)

### P0.1 修复剩余 40 条 lint 错误（手动审）

| 类型 | 数量 | 处理策略 |
|------|------|----------|
| `ARG002` 未用参数 | 13 | 添加 `_` 前缀或 `# noqa: ARG002`（保留接口签名兼容性） |
| `F841` 未用变量 | 5 | 删除赋值或用 `_` 替代 |
| `B007` 循环变量未用 | 6 | 将 `for x in ...` → `for _x in ...` |
| `SIM103` 简化条件返回 | 2 | 直接 return 布尔表达式 |
| `SIM108` 三元运算符 | 1 | if-else → 三元表达式 |
| `B005` 多字符 strip | 1 | 改用字符元组 `str.lstrip("- *:. ")` |
| `SIM115` 上下文管理器 | 1 | open 加 `with` 管理 |
| `C414` 冗余 list 调用 | 1 | 去掉 sorted 内的 list() |
| `F601` 重复字典 key | 1 | 删除重复的 `'｜'` |
| 测试文件 | 9 | 变量未用、参数未用等 |

### P0.2 测试覆盖 — 核心未覆盖模块

当前 0% 覆盖或极度不足的模块：

| 模块 | 行数 | 当前覆盖 | 目标 | 策略 |
|------|------|---------|------|------|
| `src/mcp/server.py` | 653 | **~0%** | 60%+ | MCP 工具函数的单元测试（Mock ContentRouter 和 ConfigManager）。9 个工具逐一测。 |
| `src/core/extractors/*` | ~500 | **<5%** | 50%+ | 提取器 should_try / supports / is_available 纯逻辑测试（无网络） |
| `src/exporters/*` | ~500 | **<10%** | 40%+ | Obsidian 导出、HTML 播放器、Webhook 导出逻辑 |
| `src/cli.py` | ~800 | **~0%** | 30%+ | CLI 参数解析、option 路由（不测实际网络） |
| `src/services/config_manager.py` | ~321 | **~10%** | 50%+ | 配置 CRUD、提取器 Key 管理、Obsidian 配置 |
| `src/services/downloaders/*` | ~280 | **~10%** | 40%+ | downloader 路由、URL pattern 解析、platforms 列表 |

---

## 🟡 P1 — 重要优化

### P1.1 测试覆盖 — 次要模块提升

| 模块 | 当前 | 目标 | 策略 |
|------|------|------|------|
| `src/utils/` (platform_utils, file_utils, media_utils) | ~20% | 60%+ | 路径解析、文件名清洗、媒体时长解析的纯函数测试 |
| `src/models/` | ~35% | 70%+ | 数据模型序列化/反序列化边界测试 |
| `src/services/` (task_database, ai_service) | ~30% | 50%+ | 数据库 CRUD、AI 服务 mock 测试 |

### P1.2 配置系统自动化测试

- ConfigManager CRUD 测试（set/get/list/delete）
- 配置文件持久化验证
- 提取器 Key 状态管理测试
- 默认配置生成测试

### P1.3 手册 lint 清理

- 部分 `ARG002` 参数是接口签名的一部分 → 加 `# noqa` 并注释意图
- `F841` 变量确认安全删除 → 影响界面逻辑的需保留

---

## 🔵 P2 — 长期提升

### P2.1 类型注解完整性（mypy 不报错）

当前 mypy 允许失败。目标：
- `src/core/` 先过 mypy
- 逐步扩展到 `src/utils/`、`src/models/`

### P2.2 文档补全

- `src/` 下所有模块加 module-level docstring
- 公共类/方法加 Google style docstring
- AGENTS.md 补充新增模块说明

### P2.3 CI 增强

- 覆盖阈值从 40% 逐步提升到 60%
- 新增 `mypy src/core/` 作为必过步骤
- 添加 benchmark 回归检测

---

## 📊 目标指标

| 指标 | 当前 | 目标 |
|------|------|------|
| Lint 通过率 | 125 条剩余 | **0 条** (P0.1) |
| 测试覆盖率 | 43.5% | **60%+** (P0.2+P1.1) |
| 测试通过率 | 152/152 | 维持 100% |
| mypy 核心模块 | 允许失败 | **必须通过** (P2.1) |
| Web/GUI 功能差 | 已对齐 | 保持 |
| CI 覆盖门限 | 40% | 60% (P2.3) |

## 🗓️ 执行顺序

```
Week 1: P0.1 (lint) + P0.2 (MCP tests)  → 覆盖 43.5% → 52%
Week 2: P0.2 (extractors + exporters)     → 覆盖 52% → 60%
Week 3: P1.1 + P1.2 (utils + config)      → 覆盖 60% → 65%+
Week 4: P2.x (type hints, docs, CI)       → 全模块达标
```

---

## 🎯 A 级打分配置

```
优秀 A:  覆盖 ≥ 60%, lint 0 条, 测试 100%, CI 全绿
良好 B+: 覆盖 ≥ 50%, lint < 10 条, 测试 100%, CI 无阻断
当前 B:  覆盖 43.5%, lint 125 条, 测试 100%, CI lint 未全清
```
