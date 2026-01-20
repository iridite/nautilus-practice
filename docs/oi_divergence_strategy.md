# OI Divergence (持仓量背离) 策略文档

## 📋 目录

- [策略概述](#策略概述)
- [核心逻辑](#核心逻辑)
- [数据要求](#数据要求)
- [配置参数](#配置参数)
- [快速开始](#快速开始)
- [完整使用流程](#完整使用流程)
- [策略配置示例](#策略配置示例)
- [性能优化建议](#性能优化建议)
- [常见问题](#常见问题)
- [风险提示](#风险提示)

---

## 策略概述

**OI Divergence 策略**是一个专门针对加密货币永续合约市场设计的中频交易策略，核心思想是捕捉"杠杆驱动的假突破"机会。

### 策略特点

- **时间周期**: 1H (主执行周期) / 4H (趋势判断，可选)
- **适用市场**: Binance / OKX 永续合约
- **交易品种**: 市值前 50 的流动性品种 (BTC, ETH, SOL 等)
- **策略类型**: 均值回归 + 情绪过滤
- **持仓时间**: 通常 4-24 小时

### Alpha 来源

当价格突破关键阻力/支撑位，但持仓量（Open Interest）反向下降时，意味着：

1. **突破动力不足**: 新增资金没有进场，而是老仓位平仓
2. **杠杆清洗**: 高杠杆投机者被迫止损/获利了结
3. **假突破概率高**: 价格可能回归均值

结合**资金费率**（Funding Rate）作为情绪过滤器，可以进一步提高信号质量：
- 资金费率极高 (>30% 年化) → 多头极度拥挤 → 适合做空
- 资金费率极低 (<-30% 年化) → 空头极度拥挤 → 适合做多

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

策略使用多重出场机制：

| 出场类型 | 触发条件 | 优先级 |
|---------|---------|-------|
| **硬止损** | 价格反向突破 1% | 最高 |
| **止盈** | 价格回归 VWAP 或 Midpoint | 高 |
| **时间止损** | 持仓超过 24 小时 | 中 |

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

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `lookback_bars` | int | 48 | 计算 Resistance/Support 的回溯周期（小时） |
| `oi_lookback` | int | 12 | OI 移动平均周期（小时） |
| `oi_decline_threshold` | float | 0.05 | OI 下降阈值（5% = 0.05） |

### 过滤器参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `use_funding_filter` | bool | True | 是否启用资金费率过滤 |
| `funding_rate_threshold_annual` | float | 30.0 | 年化资金费率阈值（百分比） |

### 入场参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `breakout_reentry_pct` | float | 0.002 | 回撤进入阈值（0.2% = 0.002） |

### 出场参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `tp_use_vwap` | bool | True | 止盈目标：True=VWAP, False=Midpoint |
| `vwap_period` | int | 48 | VWAP 计算周期（小时） |
| `stop_loss_pct` | float | 0.01 | 硬止损百分比（1% = 0.01） |
| `time_stop_bars` | int | 24 | 时间止损：持仓超过 N 个 Bar 强制平仓 |

### 风控参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `max_positions` | int | 1 | 最大同时持仓数量 |
| `use_auto_sl` | bool | False | 是否启用自动止损管理（已有手动止损） |

---

## 快速开始

### 1. 安装依赖

```bash
# 确保已安装 uv 包管理器
uv sync
```

### 2. 下载数据

```bash
# 一键下载所有必需数据（OHLCV + OI + Funding Rate）
uv run python scripts/prepare_oi_divergence_data.py

# 或指定多个币种
uv run python scripts/prepare_oi_divergence_data.py --symbols BTCUSDT ETHUSDT SOLUSDT

# 或指定日期范围
uv run python scripts/prepare_oi_divergence_data.py --start 2024-06-01 --end 2024-12-31
```

### 3. 运行回测

```bash
# 运行默认配置回测
uv run python backtest/backtest_oi_divergence.py
```

### 4. 查看结果

回测报告保存在 `output/oi_divergence/` 目录：
- `order_fills.csv` - 订单成交记录
- `positions.csv` - 持仓记录

---

## 完整使用流程

### 步骤 1: 准备数据

#### 方法 A: 使用自动化脚本（推荐）

```bash
uv run python scripts/prepare_oi_divergence_data.py \
  --symbols BTCUSDT ETHUSDT \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --exchange binance \
  --oi-period 1h
```

#### 方法 B: 手动分步下载

```python
from utils.data_retrival import batch_fetch_ohlcv
from utils.oi_funding_fetcher import batch_fetch_oi_and_funding
from pathlib import Path

# 1. 下载 OHLCV 数据
batch_fetch_ohlcv(
    symbols=["BTCUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    timeframe="1h",
    exchange_id="binance",
    base_dir=Path("."),
)

# 2. 下载 OI 和 Funding Rate 数据
batch_fetch_oi_and_funding(
    symbols=["BTCUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31",
    exchange_id="binance",
    base_dir=Path("."),
    oi_period="1h",
)
```

### 步骤 2: 配置策略

编辑 `config/settings.py`：

```python
from strategy.oi_divergence import OIDivergenceConfig

OI_DIVERGENCE_STRATEGY = StrategyConfig(
    name="OIDivergenceStrategy",
    module_path="strategy.oi_divergence",
    params=OIDivergenceConfig(
        # 基础配置
        instrument_id="BTCUSDT.BINANCE",
        bar_type="BTCUSDT.BINANCE-1-HOUR-LAST",
        
        # 仓位管理
        trade_size=0.01,  # 固定 0.01 BTC
        # 或使用动态仓位：
        # qty_percent=Decimal("0.1"),
        # leverage=3,
        
        # 策略参数
        lookback_bars=48,
        oi_decline_threshold=0.05,
        funding_rate_threshold_annual=30.0,
        
        # 出场参数
        stop_loss_pct=0.01,
        time_stop_bars=24,
    ),
)
```

### 步骤 3: 运行回测

```python
# backtest/backtest_oi_divergence.py
from pathlib import Path
from nautilus_trader.backtest.engine import BacktestEngine
from strategy.oi_divergence import OIDivergence

# ... 省略引擎配置 ...

# 创建策略实例
strategy = OIDivergence(config=strategy_config)
engine.add_strategy(strategy)

# 运行回测
engine.run()

# 查看结果
print(engine.trader.generate_account_report(venue))
```

### 步骤 4: 分析结果

```python
# 获取性能指标
order_fills = engine.trader.generate_order_fills_report()
positions = engine.trader.generate_positions_report()

# 计算关键指标
total_trades = len(positions)
winning_trades = len(positions[positions['realized_pnl'] > 0])
win_rate = winning_trades / total_trades if total_trades > 0 else 0

print(f"Total Trades: {total_trades}")
print(f"Win Rate: {win_rate:.1%}")
print(f"Avg PnL: {positions['realized_pnl'].mean():.2f}")
```

---

## 策略配置示例

### 示例 1: 保守型配置（低频交易）

```python
OIDivergenceConfig(
    instrument_id="BTCUSDT.BINANCE",
    bar_type="BTCUSDT.BINANCE-1-HOUR-LAST",
    
    # 仓位：固定小仓位
    trade_size=0.005,  # 0.005 BTC
    
    # 信号筛选：更严格
    lookback_bars=72,  # 3天回溯期
    oi_decline_threshold=0.08,  # OI 需下降 8%
    funding_rate_threshold_annual=50.0,  # 极端情绪
    
    # 出场：更宽松的止损
    stop_loss_pct=0.02,  # 2% 止损
    time_stop_bars=48,  # 48 小时时间止损
)
```

### 示例 2: 激进型配置（高频交易）

```python
OIDivergenceConfig(
    instrument_id="ETHUSDT.BINANCE",
    bar_type="ETHUSDT.BINANCE-1-HOUR-LAST",
    
    # 仓位：动态 + 杠杆
    qty_percent=Decimal("0.15"),  # 15% 账户净值
    leverage=5,  # 5倍杠杆
    
    # 信号筛选：更宽松
    lookback_bars=24,  # 1天回溯期
    oi_decline_threshold=0.03,  # OI 下降 3% 即可
    use_funding_filter=False,  # 不使用资金费率过滤
    
    # 出场：更紧的止损
    stop_loss_pct=0.005,  # 0.5% 止损
    time_stop_bars=12,  # 12 小时时间止损
)
```

### 示例 3: 均衡型配置（推荐）

```python
OIDivergenceConfig(
    instrument_id="SOLUSDT.BINANCE",
    bar_type="SOLUSDT.BINANCE-1-HOUR-LAST",
    
    # 仓位：中等杠杆
    qty_percent=Decimal("0.1"),  # 10% 账户净值
    leverage=3,  # 3倍杠杆
    
    # 信号筛选：标准配置
    lookback_bars=48,
    oi_decline_threshold=0.05,
    funding_rate_threshold_annual=30.0,
    use_funding_filter=True,
    
    # 出场：平衡的风控
    stop_loss_pct=0.01,  # 1% 止损
    time_stop_bars=24,  # 24 小时时间止损
    tp_use_vwap=True,
)
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

# 遍历参数组合
results = []
for params in product(*param_grid.values()):
    config = OIDivergenceConfig(
        oi_decline_threshold=params[0],
        funding_rate_threshold_annual=params[1],
        stop_loss_pct=params[2],
        # ... 其他参数 ...
    )
    # 运行回测并记录结果
    engine = run_backtest(config)
    results.append({
        'params': params,
        'sharpe': calculate_sharpe(engine),
    })
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

### Q3: 回测速度太慢怎么办？

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

```python
# 示例：实时数据适配
from nautilus_trader.live.node import TradingNode

# 配置实时节点
config = TradingNodeConfig(
    data_clients={
        "BINANCE": BinanceDataClientConfig(
            # ... API 配置 ...
        )
    },
    # ... 其他配置 ...
)
```

### Q5: 策略表现不佳怎么调优？

**调优思路：**
1. **增加过滤条件**：添加成交量、波动率等辅助指标
2. **优化出场**：使用追踪止损替代固定止损
3. **多品种分散**：同时交易 3-5 个品种降低单一品种风险
4. **时间过滤**：避开流动性差的时段（如周末）

---

## 风险提示

### ⚠️ 重要警告

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

### 📋 风控建议

1. **仓位管理**：单品种仓位不超过账户净值的 20%
2. **总仓位控制**：所有持仓合计不超过账户净值的 50%
3. **止损纪律**：严格执行止损，不人工干预
4. **资金分配**：使用不超过总资金 30% 的资金进行量化交易
5. **定期复盘**：每周/每月回顾策略表现，及时调整参数

### 🔧 实盘建议

1. **小资金测试**：先用小资金（如 100 USDT）测试 1-2 周
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

## 附录

### 相关文档
- [NautilusTrader 官方文档](https://nautilustrader.io/)
- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [OKX API 文档](https://www.okx.com/docs-v5/)

### 联系支持
- GitHub Issues: [提交问题](https://github.com/your-repo/issues)
- 策略讨论群：（待添加）

### 版本历史
- v1.0.0 (2025-01-XX): 初始版本发布