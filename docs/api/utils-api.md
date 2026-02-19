# Utils 模块 API 文档

本文档详细说明 `utils/` 模块的 API 接口，包括数据管理、工具函数和辅助类。

## 目录

- [数据管理模块](#数据管理模块)
- [工具函数](#工具函数)
- [自定义数据类型](#自定义数据类型)

---

## 数据管理模块

### DataManager

统一数据管理器，提供数据完整性检查、自动获取和验证功能。

#### 类定义

```python
from utils.data_management import DataManager

class DataManager:
    """统一数据管理器"""
    
    def __init__(self, base_dir: Path):
        """
        初始化数据管理器
        
        Parameters
        ----------
        base_dir : Path
            项目根目录
        """
```

#### 方法

##### `check_data_availability()`

检查数据可用性。

```python
def check_data_availability(
    self,
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str
) -> Tuple[List[str], List[str]]:
    """
    检查数据可用性
    
    Parameters
    ----------
    symbols : List[str]
        交易对列表，如 ["BTCUSDT", "ETHUSDT"]
    start_date : str
        开始日期，格式 "YYYY-MM-DD"
    end_date : str
        结束日期，格式 "YYYY-MM-DD"
    timeframe : str
        时间框架，如 "1h", "1d"
    exchange : str
        交易所名称，如 "binance"
    
    Returns
    -------
    Tuple[List[str], List[str]]
        (可用的交易对列表, 缺失的交易对列表)
    """
```

**示例**:
```python
from pathlib import Path
from utils.data_management import DataManager

manager = DataManager(Path("."))
available, missing = manager.check_data_availability(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    timeframe="1h",
    exchange="binance"
)

print(f"可用: {available}")
print(f"缺失: {missing}")
```

##### `fetch_missing_data()`

获取缺失数据。

```python
def fetch_missing_data(
    self,
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    max_retries: int = 3
) -> dict:
    """
    获取缺失数据
    
    Parameters
    ----------
    max_retries : int
        最大重试次数
    
    Returns
    -------
    dict
        {"success": int, "failed": int, "symbols": List[str]}
    """
```

##### `ensure_data_ready()`

确保数据就绪（检查 + 自动获取）。

```python
def ensure_data_ready(
    self,
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    auto_fetch: bool = True
) -> bool:
    """
    确保数据就绪
    
    Parameters
    ----------
    auto_fetch : bool
        是否自动获取缺失数据
    
    Returns
    -------
    bool
        是否所有数据就绪
    """
```

**示例**:
```python
manager = DataManager(Path("."))
ready = manager.ensure_data_ready(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    timeframe="1h",
    exchange="binance",
    auto_fetch=True
)

if ready:
    print("数据已就绪，可以开始回测")
else:
    print("数据获取失败")
```

---

### 数据获取函数

#### `batch_fetch_ohlcv()`

批量获取 OHLCV 数据。

```python
from utils.data_management import batch_fetch_ohlcv

def batch_fetch_ohlcv(
    symbols: List[str],
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange_id: str,
    base_dir: Path
) -> List[dict]:
    """
    批量获取 OHLCV 数据
    
    Parameters
    ----------
    symbols : List[str]
        交易对列表
    start_date : str
        开始日期 "YYYY-MM-DD"
    end_date : str
        结束日期 "YYYY-MM-DD"
    timeframe : str
        时间框架 "1h", "1d" 等
    exchange_id : str
        交易所 ID "binance", "okx" 等
    base_dir : Path
        项目根目录
    
    Returns
    -------
    List[dict]
        数据配置列表
    """
```

**示例**:
```python
from pathlib import Path
from utils.data_management import batch_fetch_ohlcv

configs = batch_fetch_ohlcv(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    timeframe="1h",
    exchange_id="binance",
    base_dir=Path(".")
)

print(f"成功获取 {len(configs)} 个数据文件")
```

#### `batch_fetch_oi_and_funding()`

批量获取 OI 和 Funding Rate 数据。

```python
from utils.data_management import batch_fetch_oi_and_funding

def batch_fetch_oi_and_funding(
    symbols: List[str],
    start_date: str,
    end_date: str,
    exchange_id: str,
    base_dir: Path,
    oi_period: str = "1h"
) -> dict:
    """
    批量获取 OI 和 Funding Rate 数据
    
    Parameters
    ----------
    oi_period : str
        OI 数据周期 "1h", "4h" 等
    
    Returns
    -------
    dict
        {"oi_files": List[Path], "funding_files": List[Path]}
    """
```

---

## 工具函数

### 时间处理 (time_helpers)

#### `get_ms_timestamp()`

获取毫秒级时间戳。

```python
from utils import get_ms_timestamp

def get_ms_timestamp(dt: datetime | str) -> int:
    """
    获取毫秒级时间戳
    
    Parameters
    ----------
    dt : datetime | str
        日期时间对象或字符串 "YYYY-MM-DD"
    
    Returns
    -------
    int
        毫秒级时间戳
    """
```

**示例**:
```python
from datetime import datetime
from utils import get_ms_timestamp

# 从 datetime 对象
ts = get_ms_timestamp(datetime(2024, 1, 1))

# 从字符串
ts = get_ms_timestamp("2024-01-01")

print(f"时间戳: {ts}")
```

---

### 网络请求 (network)

#### `retry_fetch()`

带重试的网络请求。

```python
from utils import retry_fetch

def retry_fetch(
    url: str,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    **kwargs
) -> requests.Response:
    """
    带重试的网络请求
    
    Parameters
    ----------
    url : str
        请求 URL
    max_retries : int
        最大重试次数
    delay : float
        初始延迟（秒）
    backoff : float
        延迟倍增因子
    **kwargs
        传递给 requests.get() 的参数
    
    Returns
    -------
    requests.Response
        响应对象
    
    Raises
    ------
    Exception
        所有重试失败后抛出异常
    """
```

**示例**:
```python
from utils import retry_fetch

try:
    response = retry_fetch(
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        max_retries=3,
        delay=1.0,
        backoff=2.0
    )
    data = response.json()
    print(f"BTC 价格: {data['price']}")
except Exception as e:
    print(f"请求失败: {e}")
```

---

### 数据验证 (validation)

#### `check_data_exists()`

检查数据文件是否存在。

```python
from utils import check_data_exists

def check_data_exists(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str,
    exchange: str,
    base_dir: Path
) -> Tuple[bool, Path | None]:
    """
    检查数据文件是否存在
    
    Returns
    -------
    Tuple[bool, Path | None]
        (是否存在, 文件路径)
    """
```

---

### 符号解析 (symbol_parser)

#### `resolve_symbol_and_type()`

解析交易对符号和类型。

```python
from utils import resolve_symbol_and_type

def resolve_symbol_and_type(
    symbol: str,
    exchange: str = "binance"
) -> Tuple[str, str]:
    """
    解析交易对符号和类型
    
    Parameters
    ----------
    symbol : str
        交易对符号，如 "BTCUSDT", "BTC-USDT-SWAP"
    exchange : str
        交易所名称
    
    Returns
    -------
    Tuple[str, str]
        (标准化符号, 类型) 如 ("BTCUSDT", "PERP")
    """
```

**示例**:
```python
from utils import resolve_symbol_and_type

# Binance 永续合约
symbol, type_ = resolve_symbol_and_type("BTCUSDT", "binance")
print(f"{symbol} - {type_}")  # BTCUSDT - PERP

# OKX 永续合约
symbol, type_ = resolve_symbol_and_type("BTC-USDT-SWAP", "okx")
print(f"{symbol} - {type_}")  # BTC-USDT - SWAP
```

#### `parse_timeframe()`

解析时间框架字符串。

```python
from utils import parse_timeframe

def parse_timeframe(timeframe: str) -> Tuple[int, str]:
    """
    解析时间框架字符串
    
    Parameters
    ----------
    timeframe : str
        时间框架，如 "1h", "1d", "15m"
    
    Returns
    -------
    Tuple[int, str]
        (数值, 单位) 如 (1, "h"), (15, "m")
    """
```

**示例**:
```python
from utils import parse_timeframe

value, unit = parse_timeframe("1h")
print(f"{value} {unit}")  # 1 h

value, unit = parse_timeframe("15m")
print(f"{value} {unit}")  # 15 m
```

---

### 路径操作 (path_helpers)

#### `get_project_root()`

获取项目根目录（带缓存）。

```python
from utils import get_project_root

def get_project_root() -> Path:
    """
    获取项目根目录
    
    Returns
    -------
    Path
        项目根目录路径
    """
```

**示例**:
```python
from utils import get_project_root

root = get_project_root()
data_dir = root / "data" / "raw"
print(f"数据目录: {data_dir}")
```

---

### 配置解析 (config_helpers)

#### `load_universe_symbols_from_file()`

从文件加载 Universe 交易对列表。

```python
from utils import load_universe_symbols_from_file

def load_universe_symbols_from_file(
    file_path: Path
) -> List[str]:
    """
    从文件加载 Universe 交易对列表
    
    Parameters
    ----------
    file_path : Path
        Universe 文件路径
    
    Returns
    -------
    List[str]
        交易对列表
    """
```

---

## 自定义数据类型

### FundingRateData

Funding Rate 数据类型。

```python
from utils.custom_data import FundingRateData
from nautilus_trader.model.data import CustomData

class FundingRateData(CustomData):
    """Funding Rate 数据"""
    
    def __init__(
        self,
        instrument_id: InstrumentId,
        funding_rate: float,
        funding_rate_annual: float,
        ts_event: int,
        ts_init: int
    ):
        """
        Parameters
        ----------
        instrument_id : InstrumentId
            标的 ID
        funding_rate : float
            资金费率（8小时）
        funding_rate_annual : float
            年化资金费率（%）
        ts_event : int
            事件时间戳（纳秒）
        ts_init : int
            初始化时间戳（纳秒）
        """
```

**使用示例**:

```python
from utils.custom_data import FundingRateData
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import DataType

# 订阅 Funding Rate 数据
funding_data_type = DataType(
    FundingRateData,
    metadata={"instrument_id": self.instrument.id}
)
self.subscribe_data(funding_data_type)

# 处理 Funding Rate 数据
def on_data(self, data: CustomData):
    if isinstance(data, FundingRateData):
        funding_rate = float(data.funding_rate)
        annual_rate = float(data.funding_rate_annual)
        self.log.info(f"Funding Rate: {funding_rate:.4%}, 年化: {annual_rate:.2f}%")
```

---

## 使用示例

### 完整的数据准备流程

```python
from pathlib import Path
from utils.data_management import DataManager

# 1. 初始化数据管理器
manager = DataManager(Path("."))

# 2. 定义回测参数
symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
start_date = "2024-01-01"
end_date = "2024-12-31"
timeframe = "1h"
exchange = "binance"

# 3. 检查数据可用性
available, missing = manager.check_data_availability(
    symbols, start_date, end_date, timeframe, exchange
)

print(f"可用数据: {len(available)} 个")
print(f"缺失数据: {len(missing)} 个")

# 4. 自动获取缺失数据
if missing:
    result = manager.fetch_missing_data(
        missing, start_date, end_date, timeframe, exchange
    )
    print(f"成功: {result['success']}, 失败: {result['failed']}")

# 5. 确保所有数据就绪
ready = manager.ensure_data_ready(
    symbols, start_date, end_date, timeframe, exchange, auto_fetch=True
)

if ready:
    print("✅ 数据准备完成，可以开始回测")
else:
    print("❌ 数据准备失败")
```

### 工具函数组合使用

```python
from pathlib import Path
from utils import (
    get_project_root,
    get_ms_timestamp,
    retry_fetch,
    resolve_symbol_and_type,
    parse_timeframe
)

# 获取项目路径
root = get_project_root()
data_dir = root / "data" / "raw"

# 解析交易对
symbol, type_ = resolve_symbol_and_type("BTCUSDT", "binance")
print(f"交易对: {symbol}, 类型: {type_}")

# 解析时间框架
value, unit = parse_timeframe("1h")
print(f"时间框架: {value}{unit}")

# 获取时间戳
ts = get_ms_timestamp("2024-01-01")
print(f"时间戳: {ts}")

# 网络请求（带重试）
try:
    response = retry_fetch(
        "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        max_retries=3
    )
    data = response.json()
    print(f"BTC 价格: {data['price']}")
except Exception as e:
    print(f"请求失败: {e}")
```

---

## 最佳实践

### 1. 使用统一导入接口

```python
# ✅ 推荐
from utils import get_project_root, retry_fetch, check_data_exists

# ❌ 不推荐
from utils.path_helpers import get_project_root
from utils.network import retry_fetch
from utils.validation import check_data_exists
```

### 2. 错误处理

```python
from utils import retry_fetch

try:
    response = retry_fetch(url, max_retries=3)
    data = response.json()
except Exception as e:
    logger.error(f"数据获取失败: {e}")
    # 降级处理
```

### 3. 路径操作

```python
from utils import get_project_root

# ✅ 使用 get_project_root()
root = get_project_root()
data_path = root / "data" / "raw" / "BTCUSDT.csv"

# ❌ 避免硬编码路径
data_path = Path("/home/user/project/data/raw/BTCUSDT.csv")
```

### 4. 数据管理

```python
from utils.data_management import DataManager

# 使用 DataManager 统一管理数据
manager = DataManager(get_project_root())

# 自动检查和获取
ready = manager.ensure_data_ready(
    symbols, start_date, end_date, timeframe, exchange
)
```

---

## 参考资料

- [项目 README](../../README.md)
- [Strategy API 文档](strategy-api.md)
- [部署指南](../deployment/deployment-guide.md)

---

**最后更新**: 2026-02-19
