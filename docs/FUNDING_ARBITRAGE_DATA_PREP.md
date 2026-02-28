# 资金费率套利策略 - 数据准备指南

## ✅ 当前状态

### 已完成
1. ✅ 策略代码实现 (`strategy/funding_arbitrage.py`)
2. ✅ 配置文件 (`config/strategies/funding_arbitrage.yaml`)
3. ✅ 测试通过 (20/20)
4. ✅ PR已创建 (#60)
5. ✅ 文档完善 (4个文档)

### 数据加载器现状
- ✅ **现货数据**: `BinanceFetcher` 支持 (utils/data_management/data_fetcher.py)
- ✅ **资金费率数据**: `OIFundingDataLoader` 支持 (utils/oi_funding_adapter.py)
- ⚠️ **永续合约数据**: 需要确认是否支持

## ⚠️ 待完成: 数据准备

### 问题分析

当前的 `BinanceFetcher` 使用 Binance 公开 API:
```python
BASE_URL = "https://api.binance.com"
endpoint = "/api/v3/klines"  # 现货K线接口
```

**问题**: 这个接口只能获取现货数据,无法获取永续合约数据。

### 解决方案

需要修改 `BinanceFetcher` 以支持永续合约数据获取:

#### 方案 1: 扩展 BinanceFetcher (推荐)

```python
class BinanceFetcher:
    """Binance公开API获取器 - 支持现货和永续合约"""

    SPOT_BASE_URL = "https://api.binance.com"        # 现货API
    FUTURES_BASE_URL = "https://fapi.binance.com"    # 永续合约API

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
        market_type: str = "spot"  # 新增参数: "spot" 或 "futures"
    ) -> pd.DataFrame:
        """
        获取OHLCV数据

        Args:
            symbol: 交易对 (如 BTCUSDT)
            timeframe: 时间周期
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            limit: 最多返回条数(最大1000)
            market_type: 市场类型 ("spot" 或 "futures")
        """
        # 根据市场类型选择API端点
        if market_type == "futures":
            base_url = self.FUTURES_BASE_URL
            endpoint = "/fapi/v1/klines"  # 永续合约K线接口
        else:
            base_url = self.SPOT_BASE_URL
            endpoint = "/api/v3/klines"   # 现货K线接口

        interval = self.INTERVAL_MAP.get(timeframe, "1h")

        params = {
            "symbol": symbol.replace("/", ""),
            "interval": interval,
            "limit": min(limit, 1000),
        }

        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        resp = self.session.get(f"{base_url}{endpoint}", params=params, timeout=10)
        resp.raise_for_status()

        # ... 后续处理相同
```

#### 方案 2: 使用 CCXT (备选)

CCXT 库已经支持现货和永续合约:

```python
import ccxt

exchange = ccxt.binance({
    'enableRateLimit': True,
})

# 获取现货数据
spot_ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h')

# 获取永续合约数据
futures_ohlcv = exchange.fetch_ohlcv('BTC/USDT:USDT', '1h')
```

### 资金费率数据获取

需要添加资金费率数据下载功能:

```python
class BinanceFetcher:
    def fetch_funding_rate(
        self,
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        获取资金费率数据

        Args:
            symbol: 交易对 (如 BTCUSDT)
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            limit: 最多返回条数(最大1000)
        """
        params = {
            "symbol": symbol.replace("/", ""),
            "limit": min(limit, 1000),
        }

        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        # Binance 永续合约资金费率接口
        resp = self.session.get(
            f"{self.FUTURES_BASE_URL}/fapi/v1/fundingRate",
            params=params,
            timeout=10
        )
        resp.raise_for_status()

        data = resp.json()
        df = pd.DataFrame(data)

        # 转换数据格式
        df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms")
        df["funding_rate"] = df["fundingRate"].astype(float)
        df["funding_rate_annual"] = df["funding_rate"] * 3 * 365 * 100  # 年化百分比

        return df[["timestamp", "funding_rate", "funding_rate_annual"]]
```

## 📋 数据下载清单

### MVP 测试期需要的数据

#### 1. BTCUSDT
```bash
# 现货数据
data/raw/BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv

# 永续合约数据
data/raw/BTCUSDT-PERP/binance-BTCUSDT-PERP-1h-2024-01-01_2024-12-31.csv

# 资金费率数据
data/raw/BTCUSDT-PERP/binance-BTCUSDT-PERP-funding_rate-2024-01-01_2024-12-31.csv
```

#### 2. ETHUSDT
```bash
data/raw/ETHUSDT/binance-ETHUSDT-1h-2024-01-01_2024-12-31.csv
data/raw/ETHUSDT-PERP/binance-ETHUSDT-PERP-1h-2024-01-01_2024-12-31.csv
data/raw/ETHUSDT-PERP/binance-ETHUSDT-PERP-funding_rate-2024-01-01_2024-12-31.csv
```

#### 3. SOLUSDT
```bash
data/raw/SOLUSDT/binance-SOLUSDT-1h-2024-01-01_2024-12-31.csv
data/raw/SOLUSDT-PERP/binance-SOLUSDT-PERP-1h-2024-01-01_2024-12-31.csv
data/raw/SOLUSDT-PERP/binance-SOLUSDT-PERP-funding_rate-2024-01-01_2024-12-31.csv
```

#### 4. DOGEUSDT
```bash
data/raw/DOGEUSDT/binance-DOGEUSDT-1h-2024-01-01_2024-12-31.csv
data/raw/DOGEUSDT-PERP/binance-DOGEUSDT-PERP-1h-2024-01-01_2024-12-31.csv
data/raw/DOGEUSDT-PERP/binance-DOGEUSDT-PERP-funding_rate-2024-01-01_2024-12-31.csv
```

## 🚀 下一步行动

### 1. 修改数据获取器 (优先级: P0)

**文件**: `utils/data_management/data_fetcher.py`

**任务**:
- [ ] 添加 `FUTURES_BASE_URL = "https://fapi.binance.com"`
- [ ] 在 `fetch_ohlcv()` 中添加 `market_type` 参数
- [ ] 根据 `market_type` 选择不同的 API 端点
- [ ] 添加 `fetch_funding_rate()` 方法

### 2. 创建数据下载脚本 (优先级: P0)

**文件**: `scripts/download_arbitrage_data.py` (新建)

```python
"""
下载资金费率套利策略所需的数据

用法:
    uv run python scripts/download_arbitrage_data.py --symbols BTCUSDT ETHUSDT SOLUSDT DOGEUSDT
"""

from utils.data_management.data_fetcher import BinanceFetcher

def download_pair_data(symbol: str, start_date: str, end_date: str):
    """下载单个币对的现货、合约和资金费率数据"""
    fetcher = BinanceFetcher()

    # 1. 下载现货数据
    spot_data = fetcher.fetch_ohlcv(
        symbol=symbol,
        timeframe="1h",
        market_type="spot",
        # ... 时间参数
    )
    spot_data.to_csv(f"data/raw/{symbol}/binance-{symbol}-1h-{start_date}_{end_date}.csv")

    # 2. 下载永续合约数据
    futures_data = fetcher.fetch_ohlcv(
        symbol=symbol,
        timeframe="1h",
        market_type="futures",
        # ... 时间参数
    )
    futures_data.to_csv(f"data/raw/{symbol}-PERP/binance-{symbol}-PERP-1h-{start_date}_{end_date}.csv")

    # 3. 下载资金费率数据
    funding_data = fetcher.fetch_funding_rate(
        symbol=symbol,
        # ... 时间参数
    )
    funding_data.to_csv(f"data/raw/{symbol}-PERP/binance-{symbol}-PERP-funding_rate-{start_date}_{end_date}.csv")
```

### 3. 下载数据 (优先级: P0)

```bash
# 下载 MVP 测试期的 4 个币对数据
uv run python scripts/download_arbitrage_data.py \
  --symbols BTCUSDT ETHUSDT SOLUSDT DOGEUSDT \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

### 4. 运行回测验证 (优先级: P1)

```bash
# 测试 BTC
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument BTCUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 测试 ETH
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument ETHUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 测试 SOL
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument SOLUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 测试 DOGE
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument DOGEUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

## 📝 注意事项

### Binance API 限制

1. **现货API**: `https://api.binance.com`
   - 权重限制: 1200/分钟
   - 单次最多返回: 1000条

2. **永续合约API**: `https://fapi.binance.com`
   - 权重限制: 2400/分钟
   - 单次最多返回: 1000条

3. **资金费率API**: `https://fapi.binance.com/fapi/v1/fundingRate`
   - 权重限制: 1
   - 单次最多返回: 1000条
   - 结算时间: UTC 0:00, 8:00, 16:00

### 数据格式要求

#### 现货/合约 OHLCV
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42000.0,42500.0,41800.0,42300.0,1234.56
```

#### 资金费率
```csv
timestamp,funding_rate,funding_rate_annual
2024-01-01 00:00:00,0.0001,10.95
2024-01-01 08:00:00,0.0002,21.90
2024-01-01 16:00:00,0.0001,10.95
```

## 🎯 验收标准

数据准备完成的标志:

- [ ] 4个币对的现货数据已下载
- [ ] 4个币对的永续合约数据已下载
- [ ] 4个币对的资金费率数据已下载
- [ ] 数据格式正确,无缺失
- [ ] 数据时间范围覆盖 2024-01-01 至 2024-12-31
- [ ] 回测能够正常运行,无数据加载错误

## 📚 相关文档

- [策略使用说明](FUNDING_ARBITRAGE_USAGE.md)
- [MVP测试协议](FUNDING_ARBITRAGE_MVP.md)
- [交易币对规范](FUNDING_ARBITRAGE_PAIRS.md)
- [优化报告](FUNDING_ARBITRAGE_OPTIMIZATION.md)

## 🔗 相关链接

- PR: https://github.com/iridite/nautilus-practice/pull/60
- Binance API文档: https://binance-docs.github.io/apidocs/
- Binance Futures API: https://binance-docs.github.io/apidocs/futures/en/
