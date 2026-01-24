# OI Divergence Strategy - 持仓量背离策略

> **基于 NautilusTrader 框架的加密货币中频量化交易策略**

## 📋 目录

- [策略概述](#策略概述)
- [快速开始](#快速开始)
- [核心逻辑](#核心逻辑)
- [数据要求](#数据要求)
- [配置参数](#配置参数)
- [策略配置示例](#策略配置示例)
- [核心组件说明](#核心组件说明)
- [性能优化建议](#性能优化建议)
- [常见问题](#常见问题)
- [风险提示](#风险提示)

---

## 策略概述

**OI Divergence 策略**专门针对加密货币永续合约市场设计，核心思想是捕捉"杠杆驱动的假突破"机会。

### 策略特点

| 特性 | 说明 |
|-----|------|
| **时间周期** | 1H (主执行) / 4H (趋势判断) |
| **适用市场** | Binance / OKX 永续合约 |
| **交易品种** | BTC, ETH, SOL 等高流动性币种 |
| **策略类型** | 均值回归 + 情绪过滤 |
| **持仓时间** | 4-24 小时 |
| **风险收益** | 中等风险，中等收益 |

### Alpha 来源

当价格突破关键位置（阻力/支撑）但持仓量（Open Interest）反向下降时，意味着：

1. **突破缺乏新增资金支持** - 新增资金没有进场，而是老仓位平仓
2. **杠杆清洗** - 高杠杆投机者被迫止损/获利了结  
3. **假突破概率高** - 价格可能回归均值

结合**资金费率**（Funding Rate）作为情绪过滤器，进一步提高信号质量：
- 资金费率极高 (>30% 年化) → 多头极度拥挤 → 适合做空
- 资金费率极低 (<-30% 年化) → 空头极度拥挤 → 适合做多

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 使用 uv 安装项目依赖
uv sync
```

### 2. 🆕 自动数据获取（推荐）

**新功能**: 系统现在支持全自动的OI和Funding Rate数据获取！

```bash
# 方法1: 使用主回测入口（自动检测和获取所有数据）
uv run python main.py backtest

# 方法2: 强制重新下载所有OI数据
uv run python main.py backtest --force-oi-fetch

# 方法3: 指定首选交易所
uv run python main.py backtest --oi-exchange binance

# 方法4: 查看OI策略示例
uv run python examples/oi_strategy_example.py
```

### 3. 传统数据准备方式（可选）

```bash
# 下载 OHLCV + Open Interest + Funding Rate 数据
uv run python scripts/prepare_oi_divergence_data.py

# 或指定多个币种
uv run python scripts/prepare_oi_divergence_data.py --symbols BTCUSDT ETHUSDT SOLUSDT

# 或指定日期范围
uv run python scripts/prepare_oi_divergence_data.py --start 2024-06-01 --end 2024-12-31

# 使用 OKX 交易所
uv run python scripts/prepare_oi_divergence_data.py --exchange okx
```

### 4. 运行回测

```bash
# 运行默认配置回测
uv run python backtest/backtest_oi_divergence.py
```

### 4. 查看结果

回测报告保存在 `output/oi_divergence/` 目录：
- `order_fills.csv` - 订单成交记录
- `positions.csv` - 持仓记录

---

## 核心逻辑

### 1. 信号检测（以做空为例）

#### 步骤 A: 计算区间
```
回溯期 = 过去 48 小时（可配置）
Resistance = max(High[过去48H])
Support = min(Low[过去48H])
Midpoint = (Resistance + Support) / 2
```

#### 步骤 B: 触发条件检查
```python
# 条件 1: 价格突破 Resistance
if bar.high > Resistance:
    
    # 条件 2: OI 背离检测
    OI_baseline = avg(OI[过去12小时])
    OI_change = (current_OI - OI_baseline) / OI_baseline
    
    if OI_change < -5%:  # OI 下降超过 5%
        
        # 条件 3: 资金费率过滤（可选）
        if funding_rate_annual > 30%:  # 多头极度拥挤
            
            # 条件 4: 回撤进入
            if bar.close < Resistance * (1 - 0.2%):
                → 做空信号触发
```

### 2. 入场执行

- **订单类型**: Market Order (市价单)
- **仓位大小**: 
  - 固定模式: `trade_size = 0.01 BTC`
  - 动态模式: `Qty = (Equity × qty_percent × leverage) / Price`
- **止损设置**: 突破价 + 1% (硬止损单)

### 3. 出场条件

| 出场类型 | 触发条件 | 优先级 |
|---------|---------|-------|
| **硬止损** | 价格反向突破 1% | 最高 |
| **止盈** | 价格回归 VWAP 或 Midpoint | 高 |
| **时间止损** | 持仓超过 24 小时 | 中 |

---

## 🆕 策略数据依赖声明

**新功能**: OI Divergence策略现在支持声明式数据依赖管理！

### 自动数据依赖声明

```python
from strategy.base import BaseStrategyConfig

class OIDivergenceConfig(BaseStrategyConfig):
    def __init__(self):
        super().__init__()
        
        # 声明必需的OI数据依赖
        self.add_data_dependency(
            data_type="oi",
            required=True,
            period="1h",
            exchange="binance",
            auto_fetch=True
        )
        
        # 声明必需的Funding Rate数据依赖
        self.add_data_dependency(
            data_type="funding",
            required=True,
            exchange="binance",
            auto_fetch=True
        )
        
        # 可选的4H OI数据（用于趋势确认）
        self.add_data_dependency(
            data_type="oi",
            required=False,
            period="4h",
            exchange="binance",
            auto_fetch=True
        )
```

### 在策略中检查数据依赖

```python
from strategy.oi_divergence_strategy import OIDivergence

class OIDivergence(BaseStrategy):
    def on_start(self):
        super().on_start()
        
        # 检查数据依赖状态
        if self.base_config.has_oi_dependency():
            self.log.info("Strategy requires OI data - will be auto-fetched")
        
        if self.base_config.has_funding_dependency():
            self.log.info("Strategy requires Funding Rate data - will be auto-fetched")
        
        # 获取数据需求摘要
        requirements = self.get_data_requirements()
        self.log.info(f"Data requirements: {requirements}")
```

### 自动数据获取流程

当运行 `uv run python main.py backtest` 时，系统会：

1. **检测策略数据需求**: 自动识别策略声明的OI和Funding Rate依赖
2. **验证数据完整性**: 检查本地数据文件是否存在和完整
3. **智能数据获取**: 仅下载缺失的数据，避免重复下载
4. **多交易所支持**: 主交易所失败时自动切换到备用交易所
5. **数据质量验证**: 自动验证下载数据的格式和完整性

---

## 数据要求

### 必需数据

1. **OHLCV K线数据** (标准)
   - 文件格式: `binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv`
   - 必需列: `timestamp, open, high, low, close, volume, datetime`

2. **Open Interest 数据** (核心)
   - 文件格式: `binance-BTCUSDT-oi-1h-2024-01-01_2024-12-31.csv`
   - 必需列: `timestamp, open_interest, open_interest_value, datetime`

3. **Funding Rate 数据** (情绪过滤)
   - 文件格式: `binance-BTCUSDT-funding-2024-01-01_2024-12-31.csv`
   - 必需列: `timestamp, funding_rate, funding_rate_annual, datetime`

### 数据文件结构

```
data/raw/BTCUSDT/
├── binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv      # OHLCV 数据
├── binance-BTCUSDT-4h-2024-01-01_2024-12-31.csv      # 趋势数据
├── binance-BTCUSDT-oi-1h-2024-01-01_2024-12-31.csv   # OI 数据
└── binance-BTCUSDT-funding-2024-01-01_2024-12-31.csv # Funding Rate 数据
```

### 数据同步要求

- **时间对齐**: OI 和 Funding Rate 数据必须与 OHLCV 时间戳对齐
- **时间容差**: ±1 小时内允许缺失，使用前向填充 (ffill)
- **最小数据量**: 至少 100 个 Bar 用于指标预热

---

## 配置参数

### 基础配置

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `instrument_id` | str | - | 合约标识符，如 "BTCUSDT.BINANCE" |
| `bar_type` | str | - | 主周期 Bar 类型，如 "BTCUSDT.BINANCE-1-HOUR-LAST" |
| `trend_bar_type` | str | None | 趋势周期 Bar 类型（可选） |

### 仓位管理配置

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `trade_size` | float | None | 固定下单量（如 0.01 BTC），优先级最高 |
| `qty_percent` | Decimal | None | 动态仓位比例（如 0.1 = 10% 账户净值） |
| `leverage` | int | 1 | 杠杆倍数，配合 qty_percent 使用 |

### 策略核心参数

| 参数 | 类型 | 默认值 | 说明 | 调优建议 |
|-----|------|-------|------|---------|
| `lookback_bars` | int | 48 | 计算支撑/阻力的回溯期 | 保守：72，激进：24 |
| `oi_lookback` | int | 12 | OI 移动平均周期（小时） | - |
| `oi_decline_threshold` | float | 0.05 | OI 下降阈值 (5%) | 保守：0.08，激进：0.03 |

### 过滤器参数

| 参数 | 类型 | 默认值 | 说明 | 调优建议 |
|-----|------|-------|------|---------|
| `use_funding_filter` | bool | True | 是否启用资金费率过滤 | - |
| `funding_rate_threshold_annual` | float | 30.0 | 年化资金费率阈值 | 保守：50.0，激进：20.0 |
| `breakout_reentry_pct` | float | 0.002 | 回撤进入阈值 (0.2%) | - |

### 出场参数

| 参数 | 类型 | 默认值 | 说明 | 调优建议 |
|-----|------|-------|------|---------|
| `tp_use_vwap` | bool | True | 止盈目标：True=VWAP, False=Midpoint | - |
| `vwap_period` | int | 48 | VWAP 计算周期（小时） | - |
| `stop_loss_pct` | float | 0.01 | 硬止损百分比 (1%) | 保守：0.02，激进：0.005 |
| `time_stop_bars` | int | 24 | 时间止损（小时） | 保守：48，激进：12 |

### 风控参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `max_positions` | int | 1 | 最大同时持仓数量 |
| `use_auto_sl` | bool | False | 是否启用自动止损管理（已有手动止损） |

---

## 策略配置示例

### 示例 1: 保守型配置

```python
from strategy.oi_divergence_strategy import OIDivergenceConfig

config = OIDivergenceConfig(
    instrument_id="BTCUSDT.BINANCE",
    bar_type="BTCUSDT.BINANCE-1-HOUR-LAST",
    
    # 小仓位
    trade_size=0.005,
    
    # 严格信号筛选
    lookback_bars=72,
    oi_decline_threshold=0.08,
    funding_rate_threshold_annual=50.0,
    
    # 宽松止损
    stop_loss_pct=0.02,
    time_stop_bars=48,
)
```

### 示例 2: 激进型配置

```python
config = OIDivergenceConfig(
    instrument_id="ETHUSDT.BINANCE",
    bar_type="ETHUSDT.BINANCE-1-HOUR-LAST",
    
    # 大仓位 + 杠杆
    qty_percent=Decimal("0.15"),
    leverage=5,
    
    # 宽松信号筛选
    lookback_bars=24,
    oi_decline_threshold=0.03,
    use_funding_filter=False,
    
    # 紧止损
    stop_loss_pct=0.005,
    time_stop_bars=12,
)
```

### 示例 3: 均衡型配置（推荐）

```python
config = OIDivergenceConfig(
    instrument_id="SOLUSDT.BINANCE",
    bar_type="SOLUSDT.BINANCE-1-HOUR-LAST",
    
    # 仓位：中等杠杆
    qty_percent=Decimal("0.1"),
    leverage=3,
    
    # 信号筛选：标准配置
    lookback_bars=48,
    oi_decline_threshold=0.05,
    funding_rate_threshold_annual=30.0,
    use_funding_filter=True,
    
    # 出场：平衡的风控
    stop_loss_pct=0.01,
    time_stop_bars=24,
    tp_use_vwap=True,
)
```

---

## 🔧 核心组件说明

### 项目文件结构

```
nautilus-practice/
├── strategy/
│   └── oi_divergence_strategy.py    # 策略核心实现
├── utils/
│   ├── custom_data.py               # 自定义数据类型（OI, Funding Rate）
│   ├── oi_funding_fetcher.py        # 数据获取工具
│   └── oi_funding_adapter.py        # 数据适配器（回测用）
├── backtest/
│   └── backtest_oi_divergence.py    # 回测脚本
├── scripts/
│   └── prepare_oi_divergence_data.py # 数据准备脚本
├── tests/
│   └── test_oi_divergence.py        # 单元测试
└── config/
    └── settings.py                  # 策略配置
```

### 1. 自定义数据类型 (`utils/custom_data.py`)

```python
from utils.custom_data import OpenInterestData, FundingRateData

# Open Interest 数据
oi_data = OpenInterestData(
    instrument_id=instrument_id,
    open_interest=Decimal("1000000"),
    ts_event=ts_event,
    ts_init=ts_init,
)

# Funding Rate 数据
funding_data = FundingRateData(
    instrument_id=instrument_id,
    funding_rate=Decimal("0.0001"),  # 0.01%
    next_funding_time=next_funding_time,
    ts_event=ts_event,
    ts_init=ts_init,
)

# 自动计算年化资金费率
print(funding_data.funding_rate_annual)  # 10.95%
```

### 2. 数据获取工具 (`utils/oi_funding_fetcher.py`)

支持从 Binance 和 OKX 交易所批量获取 OI 和 Funding Rate 历史数据：

```python
from utils.oi_funding_fetcher import batch_fetch_oi_and_funding

# 批量下载数据
results = batch_fetch_oi_and_funding(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    exchange_id="binance",
    oi_period="1h",
)
```

### 3. 策略实现 (`strategy/oi_divergence_strategy.py`)

```python
from strategy.oi_divergence_strategy import OIDivergence, OIDivergenceConfig

# 创建策略配置
config = OIDivergenceConfig(
    instrument_id="BTCUSDT.BINANCE",
    bar_type="BTCUSDT.BINANCE-1-HOUR-LAST",
    trade_size=0.01,  # 0.01 BTC
    lookback_bars=48,
    oi_decline_threshold=0.05,
    funding_rate_threshold_annual=30.0,
)

# 创建策略实例
strategy = OIDivergence(config=config)
```

---

## 性能优化建议

### 1. 数据层面

#### 数据缓存
```python
# 预加载数据到内存，避免重复读取
from utils.oi_funding_adapter import OIFundingDataLoader

loader = OIFundingDataLoader(PROJECT_ROOT)
custom_data_cache = {}

for symbol in symbols:
    custom_data_cache[symbol] = loader.load_all_custom_data(
        symbol=symbol,
        instrument_id=InstrumentId.from_str(f"{symbol}.BINANCE"),
        start_date=START_DATE,
        end_date=END_DATE,
    )
```

#### 数据验证
```python
from utils.oi_funding_adapter import validate_data_alignment

# 在回测前验证数据对齐
validation = validate_data_alignment(
    oi_data=custom_data['oi'],
    funding_data=custom_data['funding'],
    bar_count=len(bars),
)

if not validation['valid']:
    print("⚠️ 数据对齐问题：", validation['warnings'])
```

### 2. 策略层面

#### 减少日志输出
```python
# 在配置中减少日志频率
BacktestEngineConfig(
    bypass_logging=True,  # 跳过详细日志
    run_analysis=False,   # 快速模式
)
```

#### 指标预热
```python
# 确保足够的预热期
MIN_WARMUP_BARS = max(
    config.lookback_bars,
    config.vwap_period,
    config.oi_lookback,
) + 10  # 额外缓冲
```

### 3. 参数优化

#### 使用网格搜索
```python
from itertools import product

# 定义参数网格
param_grid = {
    'oi_decline_threshold': [0.03, 0.05, 0.08],
    'funding_rate_threshold_annual': [20.0, 30.0, 50.0],
    'stop_loss_pct': [0.005, 0.01, 0.02],
}

best_params = None
best_sharpe = -999

for params in product(*param_grid.values()):
    config = OIDivergenceConfig(
        oi_decline_threshold=params[0],
        funding_rate_threshold_annual=params[1],
        stop_loss_pct=params[2],
        # ... 其他参数 ...
    )
    
    engine = run_backtest(config)
    sharpe = calculate_sharpe(engine)
    
    if sharpe > best_sharpe:
        best_sharpe = sharpe
        best_params = params

print(f"最佳参数: {best_params}")
```

---

## 🆕 新增命令行参数

### OI数据自动获取参数

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--skip-oi-data` | 跳过OI数据检查和获取 | False | `uv run python main.py backtest --skip-oi-data` |
| `--force-oi-fetch` | 强制重新下载所有OI数据 | False | `uv run python main.py backtest --force-oi-fetch` |
| `--oi-exchange` | 指定首选交易所 | auto | `uv run python main.py backtest --oi-exchange binance` |
| `--max-retries` | 设置最大重试次数 | 3 | `uv run python main.py backtest --max-retries 5` |

### 使用示例

```bash
# 基本回测（自动获取所有数据）
uv run python main.py backtest

# 跳过OI数据，仅使用OHLCV数据进行回测
uv run python main.py backtest --skip-oi-data

# 强制重新下载所有OI数据
uv run python main.py backtest --force-oi-fetch

# 指定使用Binance交易所，最多重试5次
uv run python main.py backtest --oi-exchange binance --max-retries 5

# 组合使用多个参数
uv run python main.py backtest --oi-exchange okx --force-oi-fetch --max-retries 3
```

---

## 常见问题

### Q1: 为什么策略没有产生任何交易？

**可能原因：**
1. **数据缺失**：检查 OI 或 Funding Rate 数据是否完整
2. **信号过于严格**：尝试降低 `oi_decline_threshold` 或 `funding_rate_threshold_annual`
3. **市场环境不适合**：策略适用于高波动、高杠杆环境

**解决方案：**
```bash
# 检查数据文件
ls -lh data/raw/BTCUSDT/

# 强制重新获取数据
uv run python main.py backtest --force-oi-fetch

# 降低信号阈值
oi_decline_threshold=0.03  # 从 0.05 降到 0.03
use_funding_filter=False   # 暂时关闭资金费率过滤
```

### Q2: OI 数据和 OHLCV 数据时间不对齐怎么办？

**解决方案：**
```python
from utils.oi_funding_fetcher import align_oi_with_ohlcv

# 手动对齐数据
aligned_df = align_oi_with_ohlcv(
    oi_df=oi_data,
    ohlcv_df=ohlcv_data,
    method="ffill",  # 前向填充
)
```

### Q3: 🆕 自动OI数据获取失败怎么办？

**可能原因：**
1. **网络问题**：API请求超时或连接失败
2. **交易所限流**：请求频率过高被限制
3. **数据格式变化**：交易所API返回格式发生变化

**解决方案：**
```bash
# 增加重试次数
uv run python main.py backtest --max-retries 5

# 切换到备用交易所
uv run python main.py backtest --oi-exchange okx

# 跳过自动获取，使用手动准备的数据
uv run python main.py backtest --skip-oi-data

# 测试OI数据集成功能
uv run python test_oi_integration.py
```

### Q4: 回测速度太慢怎么办？

**优化建议：**
1. 减少数据量：使用更短的回测周期
2. 关闭详细日志：`bypass_logging=True`
3. 使用多进程：对多个币种并行回测
4. 升级硬件：使用 SSD 存储数据

### Q4: 如何在实盘中使用此策略？

**步骤：**
1. 修改数据源为实时数据流
2. 实现 OI 和 Funding Rate 的实时获取
3. 使用 NautilusTrader 的 Live Engine
4. 配置交易所 API 密钥

### Q5: 策略表现不佳怎么调优？

**调优思路：**
1. **增加过滤条件**：添加成交量、波动率等辅助指标
2. **优化出场**：使用追踪止损替代固定止损
3. **多品种分散**：同时交易 3-5 个品种降低单一品种风险
4. **时间过滤**：避开流动性差的时段（如周末）

---

## 🧪 测试

### 运行单元测试

```bash
# 运行所有测试
uv run python -m unittest tests/test_oi_divergence.py -v

# 运行特定测试
uv run python -m unittest tests.test_oi_divergence.TestCustomData -v

# 查看测试覆盖率（如果安装了coverage）
uv run python -m coverage run -m unittest tests/test_oi_divergence.py
uv run python -m coverage report --include="strategy/*,utils/*"
```

### 测试覆盖

- ✅ 自定义数据类型创建和验证
- ✅ 策略配置参数验证
- ✅ OI 背离检测逻辑
- ✅ 资金费率过滤逻辑
- ✅ 数据加载和对齐功能

---

## ⚠️ 风险提示

### 重要警告

1. **历史回测不代表未来收益**
   - 回测结果仅供参考，实盘可能存在滑点、延迟等问题
   - 过度拟合风险：参数过度优化可能导致实盘表现不佳

2. **杠杆风险**
   - 高杠杆会放大收益和损失
   - 建议新手使用 1-3 倍杠杆，经验丰富者不超过 5 倍

3. **市场环境依赖**
   - 策略在趋势市场中可能频繁止损
   - 适用于震荡市、高波动环境
   - 低波动期间可能长期无信号

4. **数据质量风险**
   - OI 和 Funding Rate 数据可能存在延迟或错误
   - 交易所 API 限流可能导致数据缺失

5. **技术风险**
   - 网络中断、系统故障可能导致无法及时止损
   - 建议设置硬件止损（交易所级别）

### 风控建议

1. **仓位管理**：单品种仓位不超过账户净值的 20%
2. **总仓位控制**：所有持仓合计不超过账户净值的 50%
3. **止损纪律**：严格执行止损，不人工干预
4. **资金分配**：使用不超过总资金 30% 的资金进行量化交易
5. **定期复盘**：每周/每月回顾策略表现，及时调整参数

### 实盘建议

1. **小资金测试**：先用 100-500 USDT 测试 1-2 周
2. **逐步增加**：确认策略稳定后再逐步增加资金
3. **监控告警**：设置异常交易、大额亏损的告警机制
4. **备用方案**：准备手动平仓的应急预案

---

## 总结

OI Divergence 策略是一个结合了**市场微观结构**（持仓量）和**情绪指标**（资金费率）的量化策略，核心优势在于：

✅ **逻辑清晰**：基于假突破和均值回归的经典理论  
✅ **参数可控**：风险收益可通过参数灵活调整  
✅ **数据丰富**：利用了传统策略未使用的 OI 数据  
✅ **适应性强**：可应用于多个币种和时间周期  

但也需要注意：

⚠️ **环境依赖**：策略在高波动、高杠杆环境下表现更好  
⚠️ **数据要求**：需要高质量的 OI 和 Funding Rate 数据  
⚠️ **风险控制**：必须严格执行止损和仓位管理  

**祝交易顺利！记住：风险管理永远是第一位的。**

---

## 相关资源

### 项目文档
- 📖 [主要README文档](../README.md)
- 📝 [代码开发规范](../AGENTS.md)
- 🆕 [OI数据使用指南](oi_data_usage_guide.md)
- 📋 [OI数据集成报告](AI%20Exec%20Reports/OI_DATA_INTEGRATION_REPORT.md)
- 🧪 [测试指南](../tests/)

### 示例和测试
- 💡 [OI策略示例](../examples/oi_strategy_example.py)
- 🧪 [OI数据集成测试](../test_oi_integration.py)
- 📊 [策略单元测试](../tests/test_oi_divergence.py)

### 外部资源
- [NautilusTrader 官方文档](https://nautilustrader.io/)
- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [OKX API 文档](https://www.okx.com/docs-v5/)

---

**免责声明**: 本策略仅供学习研究使用，不构成任何投资建议。量化交易存在风险，请谨慎使用。