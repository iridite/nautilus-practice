# Utils 工具模块使用指南

本文档介绍 nautilus-practice 项目中新的 utils 工具模块架构，旨在消除代码重复，提供可复用的通用函数。

## 📖 概述

经过重构，项目的工具函数被重新组织成以下专门化模块：

```
utils/
├── __init__.py           # 统一导入接口
├── time_helpers.py       # 时间处理工具
├── network.py           # 网络重试工具
├── validation.py        # 数据验证工具
├── symbol_parser.py     # 符号解析工具
├── data_loader.py       # 数据加载工具
├── path_helpers.py      # 路径操作工具
├── config_helpers.py    # 配置解析工具
├── custom_data.py       # 自定义数据类型（未重构）
├── oi_funding_adapter.py # OI/Funding数据适配器（未重构）
└── instrument_loader.py  # 合约加载器（未重构）
```

## 🚀 快速开始

### 统一导入接口

最简单的使用方式是通过统一接口导入：

```python
# 推荐：通过统一接口导入常用函数
from utils import (
    get_ms_timestamp,
    retry_fetch, 
    check_data_exists,
    resolve_symbol_and_type,
    load_csv_with_time_detection,
    get_project_root,
    load_universe_symbols_from_file
)
```

### 直接模块导入

也可以直接从特定模块导入：

```python
# 直接从模块导入
from utils.time_helpers import get_ms_timestamp
from utils.network import retry_fetch
from utils.validation import check_data_exists
```

## 📚 模块详细说明

### 1. 时间处理工具 (`utils.time_helpers`)

**功能**: 统一的时间戳处理和转换

```python
from utils.time_helpers import get_ms_timestamp

# 将日期字符串转换为毫秒时间戳（UTC）
start_ms = get_ms_timestamp("2024-01-01")  # -> 1704067200000
end_ms = get_ms_timestamp("2024-12-31")    # -> 1735689600000
```

**函数列表**:
- `get_ms_timestamp(date_str: str) -> int`: 将 YYYY-MM-DD 格式字符串转为 UTC 毫秒时间戳

### 2. 网络重试工具 (`utils.network`)

**功能**: 带有智能重试机制的网络请求包装器

```python
from utils.network import retry_fetch
import ccxt

# 创建交易所实例
exchange = ccxt.binance()

# 带重试的API调用
ohlcv_data = retry_fetch(
    exchange.fetch_ohlcv,
    "BTC/USDT", 
    "1h",
    since=1704067200000,
    limit=1000,
    retries=3,
    delay=2
)
```

**特性**:
- ✅ 自动重试网络错误和交易所错误
- ✅ 智能延迟：API限速错误会使用更长的延迟
- ✅ 支持自定义重试次数和延迟时间
- ✅ 支持带参数和关键字参数的函数调用

**函数列表**:
- `retry_fetch(func, *args, retries=3, delay=5, **kwargs)`: 带重试机制的函数调用包装器

### 3. 数据验证工具 (`utils.validation`)

**功能**: 数据文件存在性和完整性验证

```python
from utils.validation import check_data_exists

# 检查单个符号的数据文件
missing_files = check_data_exists(
    symbols=["BTCUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    timeframe="1h",
    exchange="binance",
    base_dir=Path(".")
)

# 检查多个符号
missing_files = check_data_exists(
    symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    start_date="2024-01-01", 
    end_date="2024-12-31",
    timeframe="1h",
    exchange="binance",
    base_dir=Path("."),
    min_file_size_kb=10  # 最小文件大小要求
)

print(f"Missing files: {missing_files}")
```

**函数列表**:
- `check_data_exists(symbols, start_date, end_date, timeframe, exchange, base_dir, **kwargs)`: 检查数据文件存在性

### 4. 符号解析工具 (`utils.symbol_parser`)

**功能**: 交易对符号格式转换和时间周期解析

```python
from utils.symbol_parser import resolve_symbol_and_type, parse_timeframe
from nautilus_trader.model.enums import BarAggregation

# 符号格式解析
ccxt_symbol, market_type = resolve_symbol_and_type("BTCUSDT")
print(f"CCXT符号: {ccxt_symbol}")  # -> "BTC/USDT:USDT" 
print(f"市场类型: {market_type}")  # -> "swap"

# 现货交易对
ccxt_symbol, market_type = resolve_symbol_and_type("BTC/USDT")
print(f"CCXT符号: {ccxt_symbol}")  # -> "BTC/USDT"
print(f"市场类型: {market_type}")  # -> "spot"

# 时间周期解析
aggregation, period = parse_timeframe("1h")
print(f"聚合类型: {aggregation}")  # -> BarAggregation.HOUR
print(f"周期: {period}")           # -> 1

aggregation, period = parse_timeframe("15m")
print(f"聚合类型: {aggregation}")  # -> BarAggregation.MINUTE  
print(f"周期: {period}")           # -> 15
```

**函数列表**:
- `resolve_symbol_and_type(input_symbol: str) -> tuple[str, str]`: 解析符号格式
- `parse_timeframe(timeframe: str) -> tuple[BarAggregation, int]`: 解析时间周期

### 5. 数据加载工具 (`utils.data_loader`)

**功能**: 统一的CSV数据加载，支持智能时间列检测

```python
from utils.data_loader import load_csv_with_time_detection

# 自动检测时间列（datetime 或 timestamp）
df = load_csv_with_time_detection("data/raw/BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv")

# 指定时间列名
df = load_csv_with_time_detection(
    "data/raw/BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv",
    time_column="timestamp"
)

print(f"数据行数: {len(df)}")
print(f"时间列类型: {df.dtypes['timestamp']}")  # datetime64[ns]
```

**特性**:
- ✅ 自动检测 `datetime` 和 `timestamp` 列
- ✅ 混合时间格式处理
- ✅ 自动时间格式转换
- ✅ 错误处理和日志记录

**函数列表**:
- `load_csv_with_time_detection(file_path, time_column=None) -> pd.DataFrame`: 加载CSV并处理时间列

### 6. 路径操作工具 (`utils.path_helpers`)

**功能**: 项目路径管理和文件系统操作

```python
from utils.path_helpers import get_project_root

# 获取项目根目录（自动检测pyproject.toml等标志文件）
project_root = get_project_root()
print(f"项目根目录: {project_root}")

# 构建相对于项目根目录的路径
data_dir = project_root / "data" / "raw"
config_file = project_root / "config" / "settings.py"
```

**函数列表**:
- `get_project_root() -> Path`: 获取项目根目录路径

### 7. 配置解析工具 (`utils.config_helpers`)

**功能**: Universe文件解析和配置处理

```python
from utils.config_helpers import load_universe_symbols_from_file

# 解析Universe文件
symbols = load_universe_symbols_from_file("data/top/universe_crypto_top10.txt")
print(f"加载的符号: {symbols}")  # -> ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', ...]

# 文件格式支持：
# 1. 简单格式：每行一个符号
# 2. 注释格式：支持 # 开头的注释
# 3. 混合格式：符号和描述混合
```

**支持的文件格式**:

```text
# Universe文件示例
BTCUSDT     # Bitcoin
ETHUSDT     # Ethereum  
SOLUSDT     # Solana
ADAUSDT     # Cardano
```

**函数列表**:
- `load_universe_symbols_from_file(file_path: Path | str) -> List[str]`: 从文件加载符号列表

## 🔄 迁移指南

### 从旧代码迁移到新工具模块

**之前的代码**:
```python
# 旧的重复代码模式
def get_ms_timestamp(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt = dt.replace(tzinfo=timezone.utc)  
    return int(dt.timestamp() * 1000)

def retry_fetch(func, *args, retries=3, delay=5, **kwargs):
    # 重复实现...
    pass

# 每个文件都重复这些函数
```

**现在的代码**:
```python
# 新的统一导入
from utils import get_ms_timestamp, retry_fetch

# 直接使用，无需重复定义
start_ms = get_ms_timestamp("2024-01-01")
data = retry_fetch(exchange.fetch_ohlcv, symbol, timeframe)
```

### 具体迁移步骤

1. **移除重复函数定义**:
   ```python
   # 删除文件中的重复函数实现
   # def get_ms_timestamp(...): pass  # 删除这些
   # def retry_fetch(...): pass       # 删除这些
   ```

2. **更新导入语句**:
   ```python
   # 旧导入
   # from some_local_file import get_ms_timestamp
   
   # 新导入
   from utils import get_ms_timestamp, retry_fetch
   ```

3. **验证功能**:
   - 运行单元测试确保功能正常
   - 检查函数签名是否兼容

## 📋 最佳实践

### 1. 导入规范

**推荐**: 使用统一接口导入常用函数
```python
from utils import get_ms_timestamp, retry_fetch, check_data_exists
```

**备选**: 需要特定功能时直接导入模块
```python
from utils.network import retry_fetch
from utils.time_helpers import get_ms_timestamp
```

### 2. 错误处理

所有工具函数都包含适当的错误处理：

```python
from utils import load_csv_with_time_detection

try:
    df = load_csv_with_time_detection("path/to/data.csv")
except FileNotFoundError:
    print("数据文件不存在")
except Exception as e:
    print(f"加载数据时出错: {e}")
```

### 3. 路径处理

始终使用 `get_project_root()` 来处理相对路径：

```python
from utils import get_project_root

# 好的做法
base_dir = get_project_root()
data_path = base_dir / "data" / "raw" / "BTCUSDT" / "data.csv"

# 避免硬编码路径
# data_path = "/home/user/project/data/raw/BTCUSDT/data.csv"  # ❌
```

### 4. 重试机制使用

对于网络请求，合理设置重试参数：

```python
from utils import retry_fetch

# 对于稳定的API，使用较少重试
data = retry_fetch(func, retries=2, delay=1)

# 对于不稳定的API，使用更多重试
data = retry_fetch(func, retries=5, delay=3)
```

## ⚠️ 注意事项

1. **时区处理**: `get_ms_timestamp` 始终返回 UTC 时间戳
2. **文件路径**: 使用 `Path` 对象而不是字符串来处理文件路径
3. **错误处理**: 所有工具函数都有适当的错误处理，但仍需要在调用处处理异常
4. **性能**: 工具函数已经过优化，但在高频调用时仍需注意性能

## 🧪 测试

每个工具模块都有对应的单元测试：

```bash
# 运行所有工具模块测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行特定模块测试  
uv run python -m unittest tests.test_time_helpers -v
uv run python -m unittest tests.test_network -v
uv run python -m unittest tests.test_validation -v
```

## 📈 性能优化

### 缓存机制

`get_project_root()` 函数内置了缓存机制，多次调用不会重复搜索：

```python
# 第一次调用会搜索项目根目录
root1 = get_project_root()  # 执行搜索

# 后续调用直接返回缓存结果
root2 = get_project_root()  # 从缓存返回
```

### 批量操作

`check_data_exists` 支持批量检查，比逐个检查效率更高：

```python
# 好的做法：批量检查
missing = check_data_exists(["BTCUSDT", "ETHUSDT", "SOLUSDT"], ...)

# 避免：逐个检查
# for symbol in symbols:
#     missing = check_data_exists([symbol], ...)  # ❌ 效率低
```

## 🔧 扩展开发

### 添加新的工具函数

1. **选择合适的模块**: 根据功能选择现有模块或创建新模块
2. **遵循命名约定**: 使用 `snake_case` 命名函数
3. **添加类型注解**: 所有函数都需要完整的类型注解
4. **编写文档字符串**: 详细说明参数和返回值
5. **创建单元测试**: 确保新功能有相应的测试覆盖
6. **更新统一接口**: 在 `utils/__init__.py` 中导出新函数

### 示例：添加新工具函数

```python
# utils/time_helpers.py
def format_timestamp(timestamp_ms: int, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    将毫秒时间戳格式化为可读字符串
    
    Parameters
    ----------
    timestamp_ms : int
        毫秒时间戳
    format_str : str
        时间格式字符串
        
    Returns
    -------
    str
        格式化后的时间字符串
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return dt.strftime(format_str)
```

```python
# utils/__init__.py  
from .time_helpers import get_ms_timestamp, format_timestamp  # 添加新函数

__all__ = [
    "get_ms_timestamp",
    "format_timestamp",  # 导出新函数
    # ... 其他函数
]
```

## 📞 支持

如果在使用工具模块时遇到问题：

1. **检查单元测试**: 查看 `tests/test_*.py` 文件中的使用示例
2. **查看源代码**: 所有工具函数都有详细的文档字符串
3. **运行测试**: 使用单元测试验证功能是否正常

---

**版本**: v1.0  
**更新时间**: 2024-01-22  
**作者**: Roo AI Assistant