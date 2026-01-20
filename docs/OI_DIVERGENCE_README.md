# OI Divergence Strategy - 持仓量背离策略

> **基于 NautilusTrader 框架的加密货币中频量化交易策略**

## 🎯 策略概述

OI Divergence 策略专门针对加密货币永续合约市场设计，核心思想是捕捉"杠杆驱动的假突破"机会。

### 核心 Alpha

当价格突破关键位置（阻力/支撑）但持仓量（Open Interest）反向下降时，意味着：
- 突破缺乏新增资金支持
- 老仓位平仓导致的假突破
- 高概率回归均值

结合**资金费率**作为情绪过滤器，进一步提高信号质量。

### 策略特点

| 特性 | 说明 |
|-----|------|
| **时间周期** | 1H (主执行) / 4H (趋势判断) |
| **适用市场** | Binance / OKX 永续合约 |
| **交易品种** | BTC, ETH, SOL 等高流动性币种 |
| **策略类型** | 均值回归 + 情绪过滤 |
| **持仓时间** | 4-24 小时 |
| **风险收益** | 中等风险，中等收益 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 使用 uv 安装项目依赖
uv sync
```

### 2. 下载数据（一键完成）

```bash
# 下载 OHLCV + Open Interest + Funding Rate 数据
uv run python scripts/prepare_oi_divergence_data.py
```

这会自动下载：
- ✅ OHLCV K线数据（1H, 4H）
- ✅ Open Interest 持仓量数据
- ✅ Funding Rate 资金费率数据

### 3. 运行回测

```bash
# 运行默认配置回测
uv run python backtest/backtest_oi_divergence.py
```

### 4. 查看结果

回测报告自动保存在 `output/oi_divergence/` 目录。

---

## 📁 项目文件结构

```
nautilus-practice/
├── strategy/
│   └── oi_divergence.py          # 策略核心实现
├── utils/
│   ├── custom_data.py             # 自定义数据类型（OI, Funding Rate）
│   ├── oi_funding_fetcher.py      # 数据获取工具
│   └── oi_funding_adapter.py      # 数据适配器（回测用）
├── backtest/
│   └── backtest_oi_divergence.py  # 回测脚本
├── scripts/
│   └── prepare_oi_divergence_data.py  # 数据准备脚本
├── tests/
│   └── test_oi_divergence.py      # 单元测试
├── config/
│   └── settings.py                # 策略配置（已添加 OI_DIVERGENCE_STRATEGY）
└── docs/
    ├── oi_divergence_strategy.md  # 详细文档
    └── OI_DIVERGENCE_README.md    # 本文件
```

---

## 🔧 核心组件说明

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

### 3. 策略实现 (`strategy/oi_divergence.py`)

```python
from strategy.oi_divergence import OIDivergence, OIDivergenceConfig

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

## 📊 策略逻辑详解

### 信号检测流程（以做空为例）

```
1. 计算区间
   ├── Resistance = max(High[过去48H])
   ├── Support = min(Low[过去48H])
   └── Midpoint = (Resistance + Support) / 2

2. 检测突破
   └── 价格突破 Resistance ✓

3. OI 背离检测
   ├── OI_baseline = avg(OI[过去12H])
   ├── OI_change = (current_OI - OI_baseline) / OI_baseline
   └── OI_change < -5% ✓

4. 情绪过滤
   └── funding_rate_annual > 30% ✓ (多头拥挤)

5. 回撤进入
   └── 价格回撤到 Resistance 下方 0.2% ✓

→ 触发做空信号
```

### 出场机制

| 出场类型 | 触发条件 | 说明 |
|---------|---------|------|
| **硬止损** | 价格反向突破 1% | 最高优先级，防止大额损失 |
| **止盈** | 价格回归 VWAP/Midpoint | 均值回归目标 |
| **时间止损** | 持仓超过 24 小时 | 避免资金占用过久 |

---

## 🎛️ 配置参数指南

### 核心参数

| 参数 | 默认值 | 说明 | 调优建议 |
|-----|-------|------|---------|
| `lookback_bars` | 48 | 计算支撑/阻力的回溯期 | 保守：72，激进：24 |
| `oi_decline_threshold` | 0.05 | OI 下降阈值 (5%) | 保守：0.08，激进：0.03 |
| `funding_rate_threshold_annual` | 30.0 | 年化资金费率阈值 | 保守：50.0，激进：20.0 |
| `stop_loss_pct` | 0.01 | 硬止损 (1%) | 保守：0.02，激进：0.005 |
| `time_stop_bars` | 24 | 时间止损 (24H) | 保守：48，激进：12 |

### 仓位管理

```python
# 方式 1: 固定仓位（推荐新手）
config = OIDivergenceConfig(
    trade_size=0.01,  # 每次固定 0.01 BTC
)

# 方式 2: 动态仓位 + 杠杆（经验丰富者）
config = OIDivergenceConfig(
    qty_percent=Decimal("0.1"),  # 账户净值的 10%
    leverage=3,  # 3倍杠杆
)
```

---

## 📖 使用示例

### 示例 1: 保守型配置

```python
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

### 示例 3: 多品种回测

```python
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

for symbol in symbols:
    config = OIDivergenceConfig(
        instrument_id=f"{symbol}.BINANCE",
        bar_type=f"{symbol}.BINANCE-1-HOUR-LAST",
        trade_size=0.01,
        # ... 其他参数 ...
    )
    
    strategy = OIDivergence(config=config)
    engine.add_strategy(strategy)
```

---

## 🧪 测试

### 运行单元测试

```bash
# 运行所有测试
uv run pytest tests/test_oi_divergence.py -v

# 运行特定测试
uv run pytest tests/test_oi_divergence.py::TestCustomData -v

# 查看测试覆盖率
uv run pytest tests/test_oi_divergence.py --cov=strategy --cov=utils
```

### 测试覆盖

- ✅ 自定义数据类型创建和验证
- ✅ 策略配置参数验证
- ✅ OI 背离检测逻辑
- ✅ 资金费率过滤逻辑
- ✅ 数据加载和对齐功能

---

## 📚 详细文档

完整文档请参考：[oi_divergence_strategy.md](./oi_divergence_strategy.md)

包含内容：
- 📖 策略原理详解
- 🔧 配置参数完整说明
- 📊 性能优化建议
- ❓ 常见问题解答
- ⚠️ 风险提示和风控建议

---

## 🛠️ 数据准备详解

### 自动化脚本（推荐）

```bash
# 下载单个币种数据
uv run python scripts/prepare_oi_divergence_data.py

# 下载多个币种数据
uv run python scripts/prepare_oi_divergence_data.py \
  --symbols BTCUSDT ETHUSDT SOLUSDT

# 指定日期范围
uv run python scripts/prepare_oi_divergence_data.py \
  --start 2024-06-01 \
  --end 2024-12-31

# 使用 OKX 交易所
uv run python scripts/prepare_oi_divergence_data.py \
  --exchange okx
```

### 数据文件结构

```
data/raw/BTCUSDT/
├── binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv      # OHLCV 数据
├── binance-BTCUSDT-4h-2024-01-01_2024-12-31.csv      # 趋势数据
├── binance-BTCUSDT-oi-1h-2024-01-01_2024-12-31.csv   # OI 数据
└── binance-BTCUSDT-funding-2024-01-01_2024-12-31.csv # Funding Rate 数据
```

---

## ⚙️ 高级功能

### 1. 数据对齐验证

```python
from utils.oi_funding_adapter import validate_data_alignment

validation = validate_data_alignment(
    oi_data=oi_data,
    funding_data=funding_data,
    bar_count=len(bars),
)

if not validation['valid']:
    print("警告：", validation['warnings'])
```

### 2. 自定义数据合并

```python
from utils.oi_funding_adapter import merge_custom_data_with_bars

merged_data = merge_custom_data_with_bars(
    oi_data=oi_data,
    funding_data=funding_data,
)

# 数据已按时间戳排序
engine.add_data(merged_data)
```

### 3. 参数优化

```python
from itertools import product

param_grid = {
    'oi_decline_threshold': [0.03, 0.05, 0.08],
    'stop_loss_pct': [0.005, 0.01, 0.02],
}

best_params = None
best_sharpe = -999

for params in product(*param_grid.values()):
    config = OIDivergenceConfig(
        oi_decline_threshold=params[0],
        stop_loss_pct=params[1],
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

## ⚠️ 重要风险提示

### 回测局限性
- ❌ 历史表现不代表未来收益
- ❌ 回测无法完全模拟滑点和延迟
- ❌ 过度拟合风险

### 实盘注意事项
1. **小资金测试**：先用 100-500 USDT 测试 1-2 周
2. **仓位控制**：单品种不超过账户 20%，总仓位不超过 50%
3. **严格止损**：永远不要取消或移动止损单
4. **监控告警**：设置异常交易和大额亏损告警
5. **定期复盘**：每周回顾策略表现，及时调整

### 数据质量
- ⚠️ OI 数据可能存在延迟（通常 1-5 分钟）
- ⚠️ Funding Rate 每 8 小时更新一次
- ⚠️ 交易所 API 限流可能导致数据缺失

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发环境设置

```bash
# 克隆仓库
git clone <repo-url>

# 安装依赖
uv sync

# 运行测试
uv run pytest tests/
```

### 代码规范
- 遵循 PEP8 规范
- 使用 Type Hints
- 添加完整的 Docstrings
- 编写单元测试

---

## 📞 支持与反馈

- **问题反馈**: GitHub Issues
- **功能建议**: GitHub Discussions
- **文档改进**: 提交 PR

---

## 📜 许可证

本项目仅供学习和研究使用。

---

## 🙏 致谢

- [NautilusTrader](https://nautilustrader.io/) - 强大的量化交易框架
- [CCXT](https://github.com/ccxt/ccxt) - 统一的交易所 API
- Binance & OKX - 提供高质量的市场数据

---

**免责声明**: 本策略仅供学习研究使用，不构成任何投资建议。量化交易存在风险，请谨慎使用。