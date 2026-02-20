# 统一异常体系使用指南

**更新日期**: 2026-02-20
**状态**: ✅ 已完成

---

## 📋 概述

Nautilus Practice 项目已实现统一的异常体系，所有异常类集中在 `core/exceptions.py` 中定义，提供清晰的异常层次结构和一致的错误处理接口。

---

## 🏗️ 异常层次结构

```
NautilusPracticeError (基类)
├── ConfigError (配置相关)
│   ├── ConfigValidationError
│   ├── ConfigLoadError
│   ├── UniverseParseError
│   └── InstrumentConfigError
├── DataError (数据相关)
│   ├── DataValidationError
│   ├── DataLoadError
│   ├── DataFetchError
│   ├── TimeColumnError
│   └── CatalogError
├── BacktestError (回测相关)
│   ├── BacktestEngineError
│   ├── InstrumentLoadError
│   ├── StrategyConfigError
│   ├── CustomDataError
│   ├── ResultProcessingError
│   └── ValidationError
├── ParsingError (解析相关)
│   ├── SymbolParsingError
│   └── TimeframeParsingError
└── PreflightError (运行时相关)
```

---

## 🚀 使用方法

### 1. 导入异常类

**推荐方式**（从核心模块导入）：

```python
from core.exceptions import (
    DataLoadError,
    ConfigValidationError,
    BacktestEngineError,
    SymbolParsingError,
)
```

**向后兼容方式**（仍然支持，但不推荐）：

```python
# 这些导入仍然有效，但会重定向到 core.exceptions
from backtest.exceptions import BacktestEngineError
from utils.exceptions import DataValidationError
```

### 2. 抛出异常

#### 基本用法

```python
from core.exceptions import DataLoadError

def load_data(file_path: str):
    if not os.path.exists(file_path):
        raise DataLoadError(
            f"数据文件不存在: {file_path}",
            file_path=file_path
        )
```

#### 带异常链的用法

```python
from core.exceptions import DataFetchError

def fetch_data(symbol: str, exchange: str):
    try:
        data = exchange_api.fetch(symbol)
    except Exception as e:
        raise DataFetchError(
            f"从 {exchange} 获取 {symbol} 数据失败",
            source=exchange,
            cause=e  # 保留原始异常
        )
```

#### 带字段信息的用法

```python
from core.exceptions import ConfigValidationError

def validate_config(config: dict):
    if config.get('leverage', 0) > 100:
        raise ConfigValidationError(
            "杠杆倍数不能超过100",
            field="leverage",
            value=config['leverage']
        )
```

### 3. 捕获异常

#### 捕获特定异常

```python
from core.exceptions import DataLoadError, DataFetchError

try:
    data = load_data(file_path)
except DataLoadError as e:
    logger.error(f"数据加载失败: {e}")
    # 错误信息会自动包含 file_path
except DataFetchError as e:
    logger.error(f"数据获取失败: {e}")
    # 错误信息会自动包含 source 和 cause
```

#### 捕获异常类别

```python
from core.exceptions import DataError, ConfigError

try:
    process_data()
except DataError as e:
    # 捕获所有数据相关异常
    logger.error(f"数据处理错误: {e}")
except ConfigError as e:
    # 捕获所有配置相关异常
    logger.error(f"配置错误: {e}")
```

#### 捕获所有项目异常

```python
from core.exceptions import NautilusPracticeError

try:
    run_backtest()
except NautilusPracticeError as e:
    # 捕获所有项目自定义异常
    logger.error(f"回测失败: {e}")
    if e.cause:
        logger.debug(f"原始错误: {e.cause}")
```

---

## 📚 异常类详解

### 配置相关异常

#### ConfigError
配置系统基础异常，所有配置相关异常的父类。

#### ConfigValidationError
配置验证错误，用于参数验证失败、类型错误、值范围错误等。

```python
raise ConfigValidationError(
    "无效的回测日期范围",
    field="end_date",
    value="2024-01-01"
)
# 输出: 无效的回测日期范围 (field: end_date=2024-01-01)
```

#### ConfigLoadError
配置加载错误，用于文件不存在、格式错误、解析失败等。

#### UniverseParseError
Universe 解析错误，用于交易标的池配置解析失败。

#### InstrumentConfigError
标的配置错误，用于交易标的配置处理失败。

### 数据相关异常

#### DataError
数据处理基础异常，所有数据相关异常的父类。

#### DataValidationError
数据验证异常，用于数据质量、格式、完整性验证失败。

```python
raise DataValidationError(
    "缺少必需的时间列",
    field_name="timestamp"
)
# 输出: 缺少必需的时间列 (field: timestamp)
```

#### DataLoadError
数据加载异常，用于加载 OHLCV、OI、Funding Rate 等数据失败。

```python
raise DataLoadError(
    "CSV 文件格式错误",
    file_path="/data/BTCUSDT.csv"
)
# 输出: CSV 文件格式错误 (file: /data/BTCUSDT.csv)
```

#### DataFetchError
数据获取异常，用于从交易所或其他数据源获取数据失败。

```python
raise DataFetchError(
    "API 请求超时",
    source="binance",
    cause=TimeoutError("Request timeout")
)
# 输出: API 请求超时 (source: binance) (caused by: Request timeout)
```

#### TimeColumnError
时间列检测错误，用于 CSV 文件时间列检测或处理失败。

#### CatalogError
数据目录异常，用于 Parquet 数据目录操作失败。

```python
raise CatalogError(
    "无法创建数据目录",
    catalog_path="/data/catalog"
)
# 输出: 无法创建数据目录 (catalog: /data/catalog)
```

### 回测相关异常

#### BacktestError
回测系统基础异常，所有回测相关异常的父类。

#### BacktestEngineError
回测引擎异常，用于回测引擎运行过程中的通用错误。

#### InstrumentLoadError
标的加载异常，用于加载交易标的信息失败。

```python
raise InstrumentLoadError(
    "标的定义文件不存在",
    instrument_id="BTCUSDT-PERP.BINANCE"
)
# 输出: 标的定义文件不存在 (instrument: BTCUSDT-PERP.BINANCE)
```

#### StrategyConfigError
策略配置异常，用于策略配置处理失败。

```python
raise StrategyConfigError(
    "策略参数验证失败",
    strategy_name="OIDivergence"
)
# 输出: 策略参数验证失败 (strategy: OIDivergence)
```

#### CustomDataError
自定义数据异常，用于处理 OI、Funding Rate 等自定义数据失败。

```python
raise CustomDataError(
    "OI 数据时间范围不匹配",
    data_type="oi"
)
# 输出: OI 数据时间范围不匹配 (data_type: oi)
```

#### ResultProcessingError
结果处理异常，用于处理回测结果失败。

#### ValidationError
验证异常，用于验证配置、数据、参数失败。

```python
raise ValidationError(
    "无效的仓位大小",
    field_name="position_size",
    field_value="0.5"
)
# 输出: 无效的仓位大小 (field: position_size=0.5)
```

### 解析相关异常

#### ParsingError
解析处理基础异常，所有解析相关异常的父类。

#### SymbolParsingError
符号解析错误，用于交易对符号解析失败。

```python
raise SymbolParsingError("无法解析符号格式: INVALID")
```

#### TimeframeParsingError
时间周期解析错误，用于时间周期格式解析失败。

```python
raise TimeframeParsingError("不支持的时间周期: 7d")
```

### 运行时相关异常

#### PreflightError
预检查异常，用于沙盒环境预检查发现阻塞性问题。

```python
problems = ["API key 未配置", "数据目录不存在"]
raise PreflightError(problems)
# 输出:
# Preflight failed with the following problems:
# - API key 未配置
# - 数据目录不存在
```

---

## 🔄 迁移指南

### 旧代码迁移

如果你的代码使用了旧的异常导入方式，不需要立即修改，但建议逐步迁移：

**旧方式**:
```python
from backtest.exceptions import BacktestEngineError
from utils.exceptions import DataValidationError
```

**新方式**:
```python
from core.exceptions import BacktestEngineError, DataValidationError
```

### 自定义异常

如果需要添加新的异常类，应该：

1. 在 `core/exceptions.py` 中定义
2. 继承合适的基类
3. 添加到 `__all__` 导出列表

```python
# 在 core/exceptions.py 中添加
class MyCustomError(DataError):
    """自定义数据错误"""

    def __init__(self, message: str, custom_field: str | None = None):
        super().__init__(message)
        self.custom_field = custom_field
```

---

## ✅ 最佳实践

### 1. 选择合适的异常类

- 配置问题 → `ConfigError` 及其子类
- 数据问题 → `DataError` 及其子类
- 回测问题 → `BacktestError` 及其子类
- 解析问题 → `ParsingError` 及其子类

### 2. 提供详细的错误信息

```python
# ❌ 不好
raise DataLoadError("加载失败")

# ✅ 好
raise DataLoadError(
    f"无法加载 {symbol} 的数据: 文件格式不正确",
    file_path=file_path
)
```

### 3. 保留异常链

```python
# ✅ 好 - 保留原始异常
try:
    data = api.fetch()
except RequestException as e:
    raise DataFetchError("API 请求失败", source="binance", cause=e)
```

### 4. 使用类型注解

```python
from core.exceptions import DataLoadError

def load_data(path: str) -> pd.DataFrame:
    """
    加载数据

    Raises
    ------
    DataLoadError
        当文件不存在或格式错误时
    """
    ...
```

---

## 📊 测试验证

所有 268 个测试用例已通过，验证了：

- ✅ 异常层次结构正确
- ✅ 向后兼容导入正常工作
- ✅ 异常功能（file_path、source、cause 等）正常
- ✅ 异常链追踪正常
- ✅ 所有模块正确使用新异常系统

---

## 🔗 相关文件

- **核心定义**: `core/exceptions.py` (565 行)
- **向后兼容**:
  - `backtest/exceptions.py` (重导出)
  - `utils/exceptions.py` (重导出)
- **使用示例**:
  - `backtest/engine_low.py`
  - `backtest/engine_high.py`
  - `utils/data_management/data_loader.py`
  - `utils/symbol_parser.py`
  - `sandbox/preflight.py`

---

## 📝 总结

统一异常体系的优势：

1. **清晰的层次结构** - 易于理解和使用
2. **一致的接口** - 所有异常都支持 `cause` 参数
3. **丰富的上下文** - 自动包含 file_path、source 等信息
4. **向后兼容** - 旧代码无需修改即可工作
5. **易于维护** - 集中管理，避免重复定义

---

**版本**: v1.0
**作者**: Nautilus Practice Team
**最后更新**: 2026-02-20
