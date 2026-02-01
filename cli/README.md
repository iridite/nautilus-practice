# CLI 模块

命令行接口模块，提供回测执行、数据管理和文件清理功能。

## 模块结构

```
cli/
├── __init__.py          # 模块导出
├── commands.py          # CLI 命令实现
├── file_cleanup.py      # 文件清理工具
└── README.md           # 本文档
```

## 核心功能

### 1. 回测命令 (`commands.py`)

**`run_backtest(args, adapter, base_dir)`**
- 执行回测（高级/低级引擎）
- 自动触发文件清理

**`check_and_fetch_strategy_data(args, adapter, base_dir, universe_symbols)`**
- 检查策略数据依赖
- 自动下载缺失的 Funding Rate 数据

**`update_instrument_definitions(adapter, base_dir, universe_symbols)`**
- 更新交易标的定义文件

### 2. 文件清理 (`file_cleanup.py`)

支持两种清理模式：

**基于文件数量**
- `cleanup_directory()` - 清理单个目录
- `auto_cleanup()` - 批量清理配置目录

**基于时间轮转**
- `cleanup_by_age()` - 按时间清理日志
- `auto_cleanup_by_age()` - 自动日志轮转
- 支持压缩（7天后）和删除（30天后）

## 使用示例

### 在 main.py 中使用

```python
from cli import run_backtest, check_and_fetch_strategy_data

# 检查数据依赖
check_and_fetch_strategy_data(args, adapter, base_dir, universe_symbols)

# 执行回测
run_backtest(args, adapter, base_dir)
```

### 配置文件清理策略

```yaml
# config/environments/dev.yaml
file_cleanup:
  enabled: true
  use_time_rotation: true
  keep_days: 7
  delete_days: 30
  target_dirs:
    - "log"
    - "output"
```

## 配置参数

### 文件清理配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用清理 |
| `use_time_rotation` | bool | false | 使用时间轮转模式 |
| `keep_days` | int | 7 | 保留最近N天日志 |
| `delete_days` | int | 30 | 删除超过N天日志 |
| `max_files_per_dir` | int | 100 | 每目录最大文件数 |
| `target_dirs` | list | ["log", "output"] | 清理目标目录 |

## 注意事项

1. 文件清理在每次回测后自动执行
2. 时间轮转模式会压缩旧日志（.log.gz）
3. 删除操作不可逆，请谨慎配置 `delete_days`
4. 生产环境建议保留更长时间（14-60天）

## 相关文档

- [项目架构指南](../AGENTS.md)
- [配置系统文档](../docs/config_system.md)
- [优化分析报告](../docs/optimization/optimization_analysis_2026-02-01.md)