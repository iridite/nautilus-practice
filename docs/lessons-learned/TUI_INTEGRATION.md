# TUI 集成经验

本文档记录 TUI (Terminal User Interface) 集成的详细实现和经验。

## 问题

回测过程缺乏实时反馈，用户不知道数据准备进度，输出混乱（logger、print()、进度条混在一起）。

## 解决方案

集成 Rich TUI 终端界面，提供清晰的进度显示和日志管理。

## 核心实现

### 1. TUI-aware Logging 配置 (`utils/logging_config.py`)

- `TUILogHandler`: 自定义 logging.Handler，将所有 logger 输出重定向到 TUI
- 动态切换：TUI 活跃时使用 TUILogHandler，停止后切换到标准 stderr
- 支持 `force_standard` 参数强制使用标准 logging

```python
from utils.logging_config import setup_logging

# 程序启动时配置（TUI 模式）
setup_logging(level=logging.INFO)

# TUI 停止后切换到标准输出
setup_logging(level=logging.INFO, force_standard=True)
```

### 2. TUI 生命周期管理 (`backtest/tui_manager.py`)

- `start()`: 启动 Rich Live Display
- `stop()`: 停止 TUI 并清空终端
- `is_active()`: 检查 TUI 是否活跃
- `get_stats_summary()`: 获取统计信息摘要

### 3. 输出冲突解决

**问题 A**: NautilusTrader 库使用 `print()` 输出，与 Rich Live Display 冲突。

**解决方案**: 在 Rich Progress 显示期间重定向 `sys.stdout` 到 `StringIO`：

```python
import io
original_stdout = sys.stdout
sys.stdout = io.StringIO()

try:
    with Live(console=console, refresh_per_second=4) as live:
        # Rich Progress 显示
        pass
finally:
    sys.stdout = original_stdout
```

**问题 B**: Coverage 警告、进度信息、NautilusTrader 输出混在一起。

**解决方案**: 实施静默模式 + 统一警告输出：

```python
# _check_parquet_coverage 添加 silent 参数
def _check_parquet_coverage(..., silent: bool = False) -> Tuple[bool, float, Optional[str]]:
    if not silent:
        logger.warning(...)  # 立即输出
    else:
        return (is_ok, coverage_pct, warning_msg)  # 返回警告信息

# 收集警告，统一输出
warnings = []
for feed in data_feeds:
    is_ok, pct, warning = _process_data_feed(..., silent=True)
    if warning:
        warnings.append(warning)

# 处理完成后统一输出
if warnings:
    sys.stderr.write("\n⚠️  Data Coverage Issues:\n")
    for warning in warnings:
        sys.stderr.write(f"  - {warning}\n")
```

## 生命周期流程

```
T0: 程序启动 (main.py)
    └─> setup_logging() → TUI 模式（logger → TUI）

T1: TUI 启动 (main.py)
    └─> with tui: → Rich Live Display 启动

T2: 数据准备阶段 (cli/commands.py)
    └─> tui.start_phase("Starting Backtest")
    └─> 显示进度、统计、日志

T3: TUI 停止 (cli/commands.py)
    └─> tui.stop() → 清空终端，_is_active = False

T4: Logging 切换 (cli/commands.py)
    └─> setup_logging(force_standard=True) → logger → stderr

T5: 数据处理总结 (cli/commands.py)
    └─> 输出格式化的统计信息
    └─> 暂停 1.5 秒让用户阅读

T6: 回测引擎 (engine_high.py)
    └─> 检查 tui.is_active() = False
    └─> 使用传统日志模式（静默模式 + 统一警告）

T7: Cleanup (cli/commands.py)
    └─> 使用标准 logging 输出

T8: 程序退出 (main.py)
    └─> __exit__() → tui.stop()（安全的重复调用）
```

## 预期输出效果

**TUI 模式（数据准备阶段）**:
```
┌─ Starting Backtest ─────────────────────────────────────┐
│ Progress: ████████████████████ 100%                     │
│                                                          │
│ Stats:                                                   │
│   fetched: 150                                           │
│   cached: 100                                            │
│   skipped: 16                                            │
│                                                          │
│ Logs:                                                    │
│   [INFO] Fetching BTCUSDT...                            │
│   [INFO] Complete: 266/266 symbols                      │
└──────────────────────────────────────────────────────────┘
```

**标准输出（数据导入阶段）**:
```
Processing data feeds: 266/266 (100%)

⚠️  Data Coverage Issues:
  - 0GUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL: 7.2% (critically low)
  - 1000BONKUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL: 52.7% (partial)

✅ Data import complete. Created 266 data configs.
```

## 关键经验

1. **清晰的生命周期管理**
   - TUI 在数据准备阶段活跃
   - 数据导入阶段自动切换到标准输出
   - 回测引擎阶段使用传统日志

2. **智能输出路由**
   - TUI 活跃时：logger → TUI
   - TUI 停止后：logger → stderr
   - 自动检测 TTY 环境

3. **输出冲突解决**
   - 抑制 NautilusTrader 的 print() 噪音
   - 收集警告统一输出，避免混乱
   - Flush 进度条流畅显示

4. **防御性编程**
   - 支持重复调用 `stop()`
   - try-finally 确保资源恢复
   - 状态标志正确维护

5. **用户体验优化**
   - TUI 停止后清空终端
   - 显示格式化的数据处理总结
   - 添加暂停让用户阅读关键信息

## 相关文件

- `utils/logging_config.py` (新增)
- `backtest/tui_manager.py`
- `backtest/engine_high.py`
- `cli/commands.py`
- `main.py`
- `utils/data_management/data_retrieval.py`
