# MainWindow 重构详细计划

## 重构目标
将 1057 行的 MainWindow 拆分为多个职责单一的组件，提高代码可维护性和可测试性。

## 重构后架构
```
src/gui/
├── main_window.py              # 主窗口（~300行）
├── controllers/
│   ├── __init__.py
│   ├── task_controller.py      # 任务管理（~300行）
│   └── config_controller.py    # 配置管理（~100行）
└── components/
    ├── __init__.py
    ├── tray_manager.py         # 托盘管理（~100行）
    └── menu_manager.py         # 菜单管理（~80行）
```

## 详细阶段计划

### 阶段 0：准备和备份（15 分钟）
1. 创建目录结构
2. 备份 main_window.py
3. 验证环境

### 阶段 1：提取 TrayManager（30 分钟）
- 提取托盘相关方法
- 测试托盘功能完整

### 阶段 2：提取 MenuManager（25 分钟）
- 提取菜单相关方法
- 测试菜单功能完整

### 阶段 3：提取 ConfigController（40 分钟）
- 提取配置管理相关方法
- 测试配置加载/保存

### 阶段 4：提取 TaskController（60 分钟）
- 提取任务管理相关方法
- 测试任务处理完整流程

### 阶段 5：清理 MainWindow（35 分钟）
- 简化主窗口代码
- 更新信号连接

### 阶段 6：最终测试（30 分钟）
- 完整功能测试
- 边界情况测试

## 时间估算
总计约 **4 小时**（含测试）

## 风险控制
- 每个阶段独立提交
- 可随时回滚
- 严格测试后进入下一阶段