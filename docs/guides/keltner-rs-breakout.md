# Keltner RS Breakout 策略使用指南

## 目录

- [策略概述](#策略概述)
- [核心逻辑](#核心逻辑)
- [参数配置](#参数配置)
- [使用示例](#使用示例)
- [回测示例](#回测示例)
- [实盘部署](#实盘部署)
- [常见问题](#常见问题)

---

## 策略概述

**Keltner RS Breakout (KRB)** 是一个中频趋势跟踪策略，基于 Keltner 通道突破和相对强度（Relative Strength）过滤。

### 策略特点

- **类型**: 中频趋势跟踪
- **适用市场**: 加密货币永续合约
- **持仓周期**: 数天到数周
- **风险等级**: 中等
- **适合交易者**: 有一定经验的趋势交易者

### 核心理念

策略实现 "Breathing Trend"（呼吸趋势）哲学：
1. 使用静态 Keltner 通道识别趋势
2. 双层过滤机制确保交易强势资产
3. 波动率倒数模型动态调整仓位
4. Chandelier Exit 跟踪止损保护利润

---

## 核心逻辑

### 入场条件（全部满足）

1. **Squeeze 状态判定**（可选）
   - 布林带收窄进入 1.5× ATR Keltner 通道
   - Squeeze 状态下提高仓位（高确信度）

2. **Universe 过滤**（Layer 1）
   - 币种在活跃 Universe 池中
   - 基于历史成交量动态筛选
   - 定期更新（月度/周度/双周）

3. **BTC 市场状态过滤**
   - BTC 价格 > SMA(200)（牛市结构）
   - BTC ATR% < 3%（波动率未极端放大）

4. **趋势过滤**
   - 价格 > SMA(200)（多头趋势）

5. **相对强度过滤**（Layer 2）
   - RS = 0.4 × RS(5d) + 0.6 × RS(20d)
   - RS > 0（跑赢 BTC）

6. **成交量过滤**
   - 成交量 > 1.5 × SMA(Vol, 20)

7. **突破触发**
   - 收盘价 > EMA(20) + 2.25 × ATR(20)

8. **K 线形态过滤**
   - 上影线比例 < 30%（避免骗线）

### 仓位计算

使用波动率倒数模型：

```
止损距离 = ATR × 止损倍数（2.0）
风险金额 = 账户权益 × 风险百分比（1.0% 或 1.5%）
仓位数量 = 风险金额 / 止损距离
```

- **普通确信度**: 风险 1.0%
- **高确信度**（Squeeze）: 风险 1.5%

### 出场条件（任一触发）

1. **Chandelier Exit**（主要）
   - 止损价 = 最高价 - 2.0 × ATR
   - 动态跟踪最高价

2. **时间止损**
   - 持仓 3 根 K 线后
   - 最高价未突破成本区 + 1%
   - 防止横盘消耗

3. **保本止损**
   - 浮盈达到 1.0 × ATR 时激活
   - 止损移至开仓价 + 0.2%（覆盖手续费）

4. **抛物线止盈**
   - 价格偏离 EMA > 40%
   - 防止极端回撤

5. **RSI 超买止盈**（可选）
   - RSI > 85 后回落至 85 以下
   - 极端情绪指标

6. **市场狂热减仓**
   - Funding Rate 年化 > 100%（警告）
   - Funding Rate 年化 > 200%（危险，减仓 50%）

---

## 参数配置

### 基础配置

```python
from strategy.keltner_rs_breakout import KeltnerRSBreakoutConfig

config = KeltnerRSBreakoutConfig()

# 标的和时间框架
config.symbol = "ETHUSDT"
config.timeframe = "1d"
config.btc_symbol = "BTCUSDT"

# 指标参数
config.ema_period = 20
config.atr_period = 20
config.sma_period = 200
config.volume_period = 20
```

### 通道参数

```python
# Keltner 通道
config.keltner_base_multiplier = 1.5    # Squeeze 判定基准
config.keltner_trigger_multiplier = 2.25  # 突破触发倍数
```

### 风控参数

```python
# 仓位风险
config.base_risk_pct = 0.01              # 普通确信度风险 1%
config.high_conviction_risk_pct = 0.015  # 高确信度风险 1.5%

# 止损参数
config.stop_loss_atr_multiplier = 2.0    # Chandelier Exit 倍数
config.enable_time_stop = True           # 启用时间止损
config.time_stop_bars = 3                # 时间止损 K 线数
config.breakeven_multiplier = 1.0        # 保本触发倍数
config.deviation_threshold = 0.40        # 抛物线止盈阈值 40%

# K 线形态
config.max_upper_wick_ratio = 0.3        # 最大上影线比例 30%
```

### 过滤器参数

```python
# 相对强度
config.rs_short_lookback_days = 5        # RS 短期回溯
config.rs_long_lookback_days = 20        # RS 长期回溯
config.rs_short_weight = 0.4             # RS 短期权重
config.rs_long_weight = 0.6              # RS 长期权重

# 成交量
config.volume_multiplier = 1.5           # 成交量倍数

# BTC 市场状态
config.enable_btc_regime_filter = True
config.btc_regime_sma_period = 200
config.btc_max_atr_pct = 0.03            # 3%

# 市场狂热度
config.enable_euphoria_filter = True
config.funding_rate_warning_annual = 100.0   # 年化 100%
config.funding_rate_danger_annual = 200.0    # 年化 200%
config.euphoria_reduce_position_pct = 0.5    # 减仓 50%
```

### Universe 参数

```python
# Universe 动态管理
config.universe_top_n = 50               # Universe 规模
config.universe_freq = "ME"              # 更新周期（ME=月度）
```

---

## 使用示例

### 基本配置

```python
from strategy.keltner_rs_breakout import KeltnerRSBreakoutStrategy, KeltnerRSBreakoutConfig

# 创建配置
config = KeltnerRSBreakoutConfig()
config.symbol = "ETHUSDT"
config.timeframe = "1d"
config.btc_symbol = "BTCUSDT"

# 仓位管理（使用 ATR 风险模式）
config.use_atr_position_sizing = True
config.base_risk_pct = 0.01
config.high_conviction_risk_pct = 0.015
config.leverage = 2

# Universe 配置
config.universe_top_n = 50
config.universe_freq = "ME"

# 创建策略实例
strategy = KeltnerRSBreakoutStrategy(config)
```

### 保守配置（降低风险）

```python
config = KeltnerRSBreakoutConfig()
config.symbol = "BTCUSDT"
config.timeframe = "1d"

# 降低风险
config.base_risk_pct = 0.005             # 0.5%
config.high_conviction_risk_pct = 0.01   # 1.0%
config.leverage = 1

# 更严格的过滤
config.volume_multiplier = 2.0           # 2× 成交量
config.btc_max_atr_pct = 0.02            # 2% ATR

# 更紧的止损
config.stop_loss_atr_multiplier = 1.5    # 1.5× ATR
config.deviation_threshold = 0.30        # 30% 偏离
```

### 激进配置（提高收益）

```python
config = KeltnerRSBreakoutConfig()
config.symbol = "SOLUSDT"
config.timeframe = "1d"

# 提高风险
config.base_risk_pct = 0.015             # 1.5%
config.high_conviction_risk_pct = 0.02   # 2.0%
config.leverage = 3

# 放宽过滤
config.volume_multiplier = 1.2           # 1.2× 成交量
config.keltner_trigger_multiplier = 2.0  # 降低突破阈值

# 更宽的止损
config.stop_loss_atr_multiplier = 2.5    # 2.5× ATR
config.deviation_threshold = 0.50        # 50% 偏离
```

---

## 回测示例

### 单币种回测

```python
from pathlib import Path
from datetime import datetime
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.identifiers import Venue
from strategy.keltner_rs_breakout import KeltnerRSBreakoutStrategy, KeltnerRSBreakoutConfig

# 1. 创建回测引擎
engine = BacktestEngine()

# 2. 添加 Venue
venue = Venue("BINANCE")
engine.add_venue(
    venue=venue,
    oms_type="NETTING",
    account_type="MARGIN",
    base_currency="USDT",
    starting_balances=["100000 USDT"]
)

# 3. 加载数据
# 假设数据已准备好在 data/raw/ 目录
data_path = Path("data/raw/ETHUSDT_1d_2024-01-01_2024-12-31.csv")
engine.add_data_from_csv(data_path)

# 4. 配置策略
config = KeltnerRSBreakoutConfig()
config.instrument_id = "ETHUSDT-PERP.BINANCE"
config.bar_type = "ETHUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL"
config.btc_instrument_id = "BTCUSDT-PERP.BINANCE"

config.use_atr_position_sizing = True
config.base_risk_pct = 0.01
config.leverage = 2

# 5. 添加策略
strategy = KeltnerRSBreakoutStrategy(config)
engine.add_strategy(strategy)

# 6. 运行回测
engine.run()

# 7. 查看结果
print(engine.trader.generate_account_report(venue))
print(engine.trader.generate_order_fills_report())
```

### 多币种回测

```python
# 配置多个策略实例
symbols = ["ETHUSDT", "BNBUSDT", "SOLUSDT"]

for symbol in symbols:
    config = KeltnerRSBreakoutConfig()
    config.instrument_id = f"{symbol}-PERP.BINANCE"
    config.bar_type = f"{symbol}-PERP.BINANCE-1-DAY-LAST-EXTERNAL"
    config.btc_instrument_id = "BTCUSDT-PERP.BINANCE"
    
    # 每个币种独立风险
    config.base_risk_pct = 0.01
    config.max_positions = 1
    
    strategy = KeltnerRSBreakoutStrategy(config)
    engine.add_strategy(strategy)

engine.run()
```

### 参数优化回测

```python
from itertools import product

# 定义参数网格
risk_levels = [0.005, 0.01, 0.015]
stop_multipliers = [1.5, 2.0, 2.5]
trigger_multipliers = [2.0, 2.25, 2.5]

results = []

for risk, stop, trigger in product(risk_levels, stop_multipliers, trigger_multipliers):
    # 创建新引擎
    engine = BacktestEngine()
    # ... 配置引擎 ...
    
    # 配置策略
    config = KeltnerRSBreakoutConfig()
    config.base_risk_pct = risk
    config.stop_loss_atr_multiplier = stop
    config.keltner_trigger_multiplier = trigger
    
    strategy = KeltnerRSBreakoutStrategy(config)
    engine.add_strategy(strategy)
    
    # 运行回测
    engine.run()
    
    # 记录结果
    account = engine.trader.generate_account_report(venue)
    results.append({
        'risk': risk,
        'stop': stop,
        'trigger': trigger,
        'pnl': account.total_pnl,
        'sharpe': account.sharpe_ratio
    })

# 找出最佳参数
best = max(results, key=lambda x: x['sharpe'])
print(f"最佳参数: {best}")
```

---

## 实盘部署

### 部署前检查

1. **环境准备**
   ```bash
   # 检查 Python 版本
   python --version  # >= 3.12.12
   
   # 安装依赖
   uv sync
   
   # 运行测试
   uv run python -m unittest discover -s tests
   ```

2. **数据准备**
   ```bash
   # 生成 Universe
   uv run python scripts/generate_universe.py
   
   # 获取历史数据
   uv run python main.py backtest  # 自动下载数据
   ```

3. **配置文件**
   ```bash
   # 复制环境配置
   cp .env.example .env
   
   # 编辑配置，添加 API Key
   vim .env
   ```

### 实盘配置

```python
# config/strategies/keltner_rs_live.yaml

strategy:
  class: KeltnerRSBreakoutStrategy
  config:
    # 标的配置
    symbol: "ETHUSDT"
    timeframe: "1d"
    btc_symbol: "BTCUSDT"
    
    # 仓位管理
    use_atr_position_sizing: true
    base_risk_pct: 0.01
    high_conviction_risk_pct: 0.015
    leverage: 2
    max_positions: 1
    
    # 风控参数
    stop_loss_atr_multiplier: 2.0
    enable_time_stop: true
    time_stop_bars: 3
    breakeven_multiplier: 1.0
    deviation_threshold: 0.40
    
    # 过滤器
    enable_btc_regime_filter: true
    enable_euphoria_filter: true
    funding_rate_warning_annual: 100.0
    funding_rate_danger_annual: 200.0
    
    # Universe
    universe_top_n: 50
    universe_freq: "ME"

# 交易所配置
exchange:
  name: "binance"
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  testnet: false

# 风控配置
risk:
  max_daily_loss: 0.05      # 5% 日最大亏损
  max_drawdown: 0.20        # 20% 最大回撤
  emergency_stop: true      # 启用紧急停止
```

### 启动实盘

```bash
# 启动实盘交易
uv run python main.py live --config config/strategies/keltner_rs_live.yaml

# 后台运行
nohup uv run python main.py live --config config/strategies/keltner_rs_live.yaml > live.log 2>&1 &
```

### 监控和日志

```bash
# 查看实时日志
tail -f live.log

# 查看持仓
uv run python cli/commands.py positions

# 查看订单
uv run python cli/commands.py orders

# 查看账户
uv run python cli/commands.py account
```

### 注意事项

1. **资金管理**
   - 建议初始资金 > 10,000 USDT
   - 单币种风险 1-2%
   - 总持仓不超过账户 30%

2. **风险控制**
   - 设置日最大亏损限制
   - 启用紧急停止机制
   - 定期检查持仓和订单

3. **数据监控**
   - 确保数据源稳定
   - 监控 Funding Rate 数据
   - 定期更新 Universe

4. **异常处理**
   - 网络断线自动重连
   - API 限流自动重试
   - 订单失败告警通知

5. **定期维护**
   - 每周检查策略表现
   - 每月更新 Universe
   - 季度参数优化

---

## 常见问题

### Q1: 策略为什么不开仓？

**可能原因**:
1. Universe 过滤：币种不在活跃池中
2. BTC 市场状态：BTC 未处于牛市结构或波动率过高
3. 相对强度：币种未跑赢 BTC
4. 成交量不足：未达到 1.5× 均量
5. 未突破触发价：价格未突破 EMA + 2.25× ATR

**排查方法**:
```python
# 在策略中添加调试日志
self.log.info(f"Universe 活跃: {self._is_symbol_active()}")
self.log.info(f"BTC 市场状态: {self._check_btc_market_regime()}")
self.log.info(f"RS 分数: {self._calculate_rs_score()}")
self.log.info(f"成交量: {volume}, 均量: {self.volume_sma}")
```

### Q2: 如何调整仓位大小？

**方法 1: 调整风险百分比**
```python
config.base_risk_pct = 0.005  # 降低至 0.5%
config.high_conviction_risk_pct = 0.01  # 降低至 1.0%
```

**方法 2: 调整杠杆**
```python
config.leverage = 1  # 降低杠杆
```

**方法 3: 调整止损距离**
```python
config.stop_loss_atr_multiplier = 1.5  # 更紧的止损 = 更大仓位
```

### Q3: 如何优化策略表现？

**参数优化方向**:

1. **提高胜率**
   - 提高 `keltner_trigger_multiplier`（更严格的突破）
   - 提高 `volume_multiplier`（更强的成交量确认）
   - 降低 `btc_max_atr_pct`（更稳定的市场环境）

2. **提高盈亏比**
   - 提高 `stop_loss_atr_multiplier`（更宽的止损）
   - 提高 `deviation_threshold`（更晚的止盈）
   - 禁用 `enable_time_stop`（避免过早离场）

3. **提高交易频率**
   - 降低 `keltner_trigger_multiplier`（更容易突破）
   - 降低 `volume_multiplier`（放宽成交量要求）
   - 扩大 `universe_top_n`（更多交易机会）

### Q4: Funding Rate 过高怎么办？

策略内置市场狂热度过滤：

- **警告状态**（年化 > 100%）：停止开新仓
- **危险状态**（年化 > 200%）：自动减仓 50%

**手动干预**:
```python
# 调整阈值
config.funding_rate_warning_annual = 80.0   # 更保守
config.funding_rate_danger_annual = 150.0

# 调整减仓比例
config.euphoria_reduce_position_pct = 0.7   # 减仓 70%
```

### Q5: 如何处理回撤？

**策略内置保护机制**:

1. **保本止损**: 浮盈达到 1× ATR 后移至成本价
2. **Chandelier Exit**: 动态跟踪止损
3. **抛物线止盈**: 偏离 EMA 40% 时止盈
4. **时间止损**: 3 根 K 线无动能时离场

**额外保护**:
```python
# 启用自动止损
config.use_auto_sl = True
config.stop_loss_pct = 0.05  # 5% 固定止损

# 限制最大持仓
config.max_positions = 1

# 降低风险
config.base_risk_pct = 0.005  # 0.5%
```

### Q6: Universe 如何更新？

**自动更新**:
```python
# 配置更新周期
config.universe_freq = "ME"      # 月度更新
config.universe_freq = "W-MON"   # 周度更新（每周一）
config.universe_freq = "2W-MON"  # 双周更新
```

**手动更新**:
```bash
# 重新生成 Universe
uv run python scripts/generate_universe.py \
    --top-n 50 \
    --freq ME \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
```

### Q7: 如何回测历史表现？

```bash
# 快速回测
uv run python main.py backtest

# 指定参数回测
uv run python main.py backtest \
    --symbol ETHUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --risk 0.01

# 查看回测报告
cat output/backtest/report_ETHUSDT_20240101_20241231.txt
```

---

## 进阶主题

### 多币种组合

```python
# 配置币种池
symbols = ["ETHUSDT", "BNBUSDT", "SOLUSDT", "AVAXUSDT"]

# 为每个币种创建独立策略
for symbol in symbols:
    config = KeltnerRSBreakoutConfig()
    config.symbol = symbol
    config.base_risk_pct = 0.01 / len(symbols)  # 分散风险
    config.max_positions = 1
    
    strategy = KeltnerRSBreakoutStrategy(config)
    engine.add_strategy(strategy)
```

### 动态参数调整

```python
class AdaptiveKeltnerStrategy(KeltnerRSBreakoutStrategy):
    """自适应参数的 Keltner 策略"""
    
    def on_bar(self, bar: Bar):
        # 根据市场波动率调整参数
        if self.atr is not None:
            atr_pct = self.atr / float(bar.close)
            
            if atr_pct > 0.05:  # 高波动
                self.config.stop_loss_atr_multiplier = 2.5
                self.config.keltner_trigger_multiplier = 2.5
            else:  # 低波动
                self.config.stop_loss_atr_multiplier = 2.0
                self.config.keltner_trigger_multiplier = 2.0
        
        super().on_bar(bar)
```

### 机器学习增强

```python
# 使用 ML 模型预测 RS 分数
import joblib

class MLEnhancedKeltnerStrategy(KeltnerRSBreakoutStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.ml_model = joblib.load("models/rs_predictor.pkl")
    
    def _check_relative_strength(self) -> bool:
        # 使用 ML 模型增强 RS 判断
        features = self._extract_features()
        rs_prediction = self.ml_model.predict([features])[0]
        
        # 结合传统 RS 和 ML 预测
        traditional_rs = super()._check_relative_strength()
        return traditional_rs and rs_prediction > 0.5
```

---

## 参考资料

- [Strategy API 文档](../api/strategy-api.md)
- [部署指南](../deployment/deployment-guide.md)
- [项目 README](../../README.md)
- [NautilusTrader 文档](https://nautilustrader.io/)

---

**最后更新**: 2026-02-19
**策略版本**: v2.1
**作者**: Nautilus Practice Team
