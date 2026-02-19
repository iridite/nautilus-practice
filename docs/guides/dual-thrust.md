# Dual Thrust 策略使用指南

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

**Dual Thrust** 是一个经典的日内突破策略，由 Michael Chalek 在 20 世纪 80 年代开发。该策略基于前 N 天的价格范围计算动态通道，在价格突破通道时进行交易。

### 策略特点

- **类型**: 日内突破策略
- **适用市场**: 加密货币、期货、股票
- **持仓周期**: 日内（通常不过夜）
- **风险等级**: 中等
- **适合交易者**: 日内交易者、波段交易者

### 核心理念

Dual Thrust 策略的核心思想是：
1. 市场在突破前期价格范围时会产生趋势
2. 使用不对称的上下轨系数适应不同市场特性
3. 日内开仓，日内平仓（可配置）

---

## 核心逻辑

### 通道计算

基于前 N 天（lookback_period）的价格数据计算：

```
HH = Max(High[1:N])     # 最高价
LL = Min(Low[1:N])      # 最低价
HC = Max(Close[1:N])    # 最高收盘价
LC = Min(Close[1:N])    # 最低收盘价

Range = Max(HH - LC, HC - LL)

上轨 = Open + k1 × Range
下轨 = Open - k2 × Range
```

### 入场条件

1. **做多条件**
   - 当前价格 > 上轨
   - 无持仓或持有空头

2. **做空条件**
   - 当前价格 < 下轨
   - 无持仓或持有多头

### 出场条件

1. **多头止损**
   - 价格跌破下轨

2. **空头止损**
   - 价格突破上轨

3. **日内平仓**（可选）
   - 收盘前平掉所有持仓

---

## 参数配置

### 基础配置

```python
from strategy.dual_thrust import DualThrustConfig

config = DualThrustConfig()

# 标的和时间框架
config.symbol = "BTCUSDT"
config.timeframe = "1h"

# 策略参数
config.lookback_period = 4  # 回溯周期（天数）
config.k1 = 0.5             # 上轨系数
config.k2 = 0.5             # 下轨系数
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `lookback_period` | `int` | `4` | 回溯周期，计算 Range 的天数 |
| `k1` | `float` | `0.5` | 上轨系数，控制上轨距离 |
| `k2` | `float` | `0.5` | 下轨系数，控制下轨距离 |

### 参数调优建议

#### lookback_period（回溯周期）

- **短周期（2-3 天）**: 更敏感，交易频率高，适合高波动市场
- **中周期（4-5 天）**: 平衡，适合大多数市场
- **长周期（6-10 天）**: 更稳定，交易频率低，适合低波动市场

#### k1 和 k2（通道系数）

- **对称设置（k1 = k2）**: 适合双向波动市场
- **多头偏向（k1 < k2）**: 更容易做多，适合牛市
- **空头偏向（k1 > k2）**: 更容易做空，适合熊市

**常用组合**:
```python
# 保守配置（减少假突破）
config.k1 = 0.7
config.k2 = 0.7

# 标准配置
config.k1 = 0.5
config.k2 = 0.5

# 激进配置（增加交易频率）
config.k1 = 0.3
config.k2 = 0.3

# 牛市配置
config.k1 = 0.4
config.k2 = 0.6

# 熊市配置
config.k1 = 0.6
config.k2 = 0.4
```

---

## 使用示例

### 基本配置

```python
from strategy.dual_thrust import DualThrustStrategy, DualThrustConfig

# 创建配置
config = DualThrustConfig()
config.symbol = "BTCUSDT"
config.timeframe = "1h"

# 策略参数
config.lookback_period = 4
config.k1 = 0.5
config.k2 = 0.5

# 仓位管理
config.qty_percent = 0.1  # 使用 10% 账户权益
config.leverage = 2

# 创建策略实例
strategy = DualThrustStrategy(config)
```

### 日内交易配置

```python
config = DualThrustConfig()
config.symbol = "BTCUSDT"
config.timeframe = "15m"  # 15 分钟 K 线

# 短周期，快速反应
config.lookback_period = 2
config.k1 = 0.4
config.k2 = 0.4

# 较小仓位，频繁交易
config.qty_percent = 0.05
config.leverage = 3
```

### 波段交易配置

```python
config = DualThrustConfig()
config.symbol = "ETHUSDT"
config.timeframe = "4h"  # 4 小时 K 线

# 长周期，稳定信号
config.lookback_period = 6
config.k1 = 0.6
config.k2 = 0.6

# 较大仓位，持有时间长
config.qty_percent = 0.15
config.leverage = 2
```

### 多空不对称配置

```python
# 牛市配置（更容易做多）
config = DualThrustConfig()
config.symbol = "BTCUSDT"
config.timeframe = "1h"

config.lookback_period = 4
config.k1 = 0.4  # 更低的上轨，更容易突破做多
config.k2 = 0.6  # 更高的下轨，不容易做空

config.qty_percent = 0.1
config.leverage = 2
```

---

## 回测示例

### 单币种回测

```python
from pathlib import Path
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.identifiers import Venue
from strategy.dual_thrust import DualThrustStrategy, DualThrustConfig

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
data_path = Path("data/raw/BTCUSDT_1h_2024-01-01_2024-12-31.csv")
engine.add_data_from_csv(data_path)

# 4. 配置策略
config = DualThrustConfig()
config.instrument_id = "BTCUSDT-PERP.BINANCE"
config.bar_type = "BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"

config.lookback_period = 4
config.k1 = 0.5
config.k2 = 0.5
config.qty_percent = 0.1
config.leverage = 2

# 5. 添加策略
strategy = DualThrustStrategy(config)
engine.add_strategy(strategy)

# 6. 运行回测
engine.run()

# 7. 查看结果
print(engine.trader.generate_account_report(venue))
print(engine.trader.generate_order_fills_report())
```

### 参数优化回测

```python
from itertools import product
import pandas as pd

# 定义参数网格
lookback_periods = [2, 3, 4, 5, 6]
k1_values = [0.3, 0.4, 0.5, 0.6, 0.7]
k2_values = [0.3, 0.4, 0.5, 0.6, 0.7]

results = []

for lookback, k1, k2 in product(lookback_periods, k1_values, k2_values):
    # 创建新引擎
    engine = BacktestEngine()
    
    # 配置引擎（省略详细代码）
    venue = Venue("BINANCE")
    engine.add_venue(
        venue=venue,
        oms_type="NETTING",
        account_type="MARGIN",
        base_currency="USDT",
        starting_balances=["100000 USDT"]
    )
    
    # 加载数据
    data_path = Path("data/raw/BTCUSDT_1h_2024-01-01_2024-12-31.csv")
    engine.add_data_from_csv(data_path)
    
    # 配置策略
    config = DualThrustConfig()
    config.instrument_id = "BTCUSDT-PERP.BINANCE"
    config.bar_type = "BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL"
    config.lookback_period = lookback
    config.k1 = k1
    config.k2 = k2
    config.qty_percent = 0.1
    
    strategy = DualThrustStrategy(config)
    engine.add_strategy(strategy)
    
    # 运行回测
    engine.run()
    
    # 提取结果
    account = engine.trader.generate_account_report(venue)
    results.append({
        'lookback': lookback,
        'k1': k1,
        'k2': k2,
        'total_pnl': account.total_pnl,
        'sharpe_ratio': account.sharpe_ratio,
        'max_drawdown': account.max_drawdown,
        'win_rate': account.win_rate
    })

# 转换为 DataFrame 并分析
df = pd.DataFrame(results)
df = df.sort_values('sharpe_ratio', ascending=False)

print("Top 10 参数组合:")
print(df.head(10))

# 保存结果
df.to_csv("output/dual_thrust_optimization.csv", index=False)
```

### 多时间框架回测

```python
# 测试不同时间框架的表现
timeframes = ["15m", "1h", "4h", "1d"]
results = {}

for tf in timeframes:
    engine = BacktestEngine()
    # ... 配置引擎 ...
    
    config = DualThrustConfig()
    config.timeframe = tf
    config.lookback_period = 4
    config.k1 = 0.5
    config.k2 = 0.5
    
    strategy = DualThrustStrategy(config)
    engine.add_strategy(strategy)
    engine.run()
    
    account = engine.trader.generate_account_report(venue)
    results[tf] = {
        'pnl': account.total_pnl,
        'sharpe': account.sharpe_ratio,
        'trades': account.total_trades
    }

# 比较结果
for tf, metrics in results.items():
    print(f"{tf}: PnL={metrics['pnl']:.2f}, Sharpe={metrics['sharpe']:.2f}, Trades={metrics['trades']}")
```

---

## 实盘部署

### 部署前检查

1. **环境准备**
   ```bash
   # 检查依赖
   uv sync
   
   # 运行测试
   uv run python -m unittest tests/test_dual_thrust.py -v
   ```

2. **回测验证**
   ```bash
   # 使用最近数据回测
   uv run python main.py backtest \
       --strategy dual_thrust \
       --symbol BTCUSDT \
       --start-date 2024-11-01 \
       --end-date 2024-12-31
   ```

3. **配置文件**
   ```bash
   # 创建实盘配置
   cp config/strategies/dual_thrust_backtest.yaml \
      config/strategies/dual_thrust_live.yaml
   
   # 编辑配置
   vim config/strategies/dual_thrust_live.yaml
   ```

### 实盘配置

```yaml
# config/strategies/dual_thrust_live.yaml

strategy:
  class: DualThrustStrategy
  config:
    # 标的配置
    symbol: "BTCUSDT"
    timeframe: "1h"
    
    # 策略参数
    lookback_period: 4
    k1: 0.5
    k2: 0.5
    
    # 仓位管理
    qty_percent: 0.1
    leverage: 2
    max_positions: 1
    
    # 风控
    use_auto_sl: true
    stop_loss_pct: 0.03  # 3% 固定止损

# 交易所配置
exchange:
  name: "binance"
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  testnet: false

# 风控配置
risk:
  max_daily_loss: 0.05      # 5% 日最大亏损
  max_drawdown: 0.15        # 15% 最大回撤
  emergency_stop: true
```

### 启动实盘

```bash
# 启动实盘交易
uv run python main.py live --config config/strategies/dual_thrust_live.yaml

# 后台运行
nohup uv run python main.py live \
    --config config/strategies/dual_thrust_live.yaml \
    > logs/dual_thrust_live.log 2>&1 &

# 查看进程
ps aux | grep "main.py live"
```

### 监控和管理

```bash
# 查看实时日志
tail -f logs/dual_thrust_live.log

# 查看持仓
uv run python cli/commands.py positions

# 查看今日交易
uv run python cli/commands.py trades --today

# 紧急停止
uv run python cli/commands.py stop --strategy dual_thrust
```

### 注意事项

1. **时间框架选择**
   - 15m/1h: 适合日内交易，需要频繁监控
   - 4h/1d: 适合波段交易，监控压力小

2. **仓位管理**
   - 建议单次仓位 ≤ 10% 账户权益
   - 使用杠杆时更要谨慎
   - 设置固定止损保护

3. **市场适应性**
   - 趋势市场表现好
   - 震荡市场容易假突破
   - 根据市场调整 k1/k2

4. **风险控制**
   - 设置日最大亏损
   - 启用紧急停止
   - 定期检查策略表现

5. **数据质量**
   - 确保数据源稳定
   - 监控数据延迟
   - 处理数据缺失

---

## 常见问题

### Q1: 策略频繁开平仓怎么办？

**原因**: k1/k2 系数过小，通道过窄

**解决方案**:
```python
# 增大系数，扩宽通道
config.k1 = 0.7
config.k2 = 0.7

# 或增加回溯周期
config.lookback_period = 6
```

### Q2: 策略长期不开仓怎么办？

**原因**: k1/k2 系数过大，通道过宽

**解决方案**:
```python
# 减小系数，收窄通道
config.k1 = 0.3
config.k2 = 0.3

# 或减少回溯周期
config.lookback_period = 2
```

### Q3: 如何处理假突破？

**方法 1: 增加确认条件**
```python
class EnhancedDualThrust(DualThrustStrategy):
    def on_bar(self, bar: Bar):
        super().on_bar(bar)
        
        # 添加成交量确认
        if self.volume_sma is not None:
            if bar.volume < self.volume_sma * 1.5:
                return  # 成交量不足，不交易
```

**方法 2: 调整参数**
```python
# 使用更保守的系数
config.k1 = 0.6
config.k2 = 0.6

# 使用更长的回溯周期
config.lookback_period = 5
```

### Q4: 如何优化参数？

**步骤**:

1. **历史回测**
   ```bash
   uv run python scripts/optimize_dual_thrust.py \
       --symbol BTCUSDT \
       --start-date 2024-01-01 \
       --end-date 2024-12-31
   ```

2. **参数网格搜索**
   ```python
   # 见上文"参数优化回测"示例
   ```

3. **样本外验证**
   ```python
   # 训练集: 2024-01-01 到 2024-09-30
   # 测试集: 2024-10-01 到 2024-12-31
   ```

4. **滚动优化**
   ```python
   # 每月重新优化参数
   # 使用最近 6 个月数据
   ```

### Q5: 不同市场如何调整？

**牛市**:
```python
config.k1 = 0.4  # 更容易做多
config.k2 = 0.6  # 不容易做空
```

**熊市**:
```python
config.k1 = 0.6  # 不容易做多
config.k2 = 0.4  # 更容易做空
```

**震荡市**:
```python
config.k1 = 0.7  # 减少假突破
config.k2 = 0.7
config.lookback_period = 6  # 更稳定的通道
```

**趋势市**:
```python
config.k1 = 0.3  # 快速捕捉趋势
config.k2 = 0.3
config.lookback_period = 3  # 更敏感的通道
```

### Q6: 如何结合其他指标？

**示例: 添加 RSI 过滤**
```python
from nautilus_trader.indicators import RelativeStrengthIndex

class DualThrustWithRSI(DualThrustStrategy):
    def __init__(self, config):
        super().__init__(config)
        self.rsi = RelativeStrengthIndex(period=14)
    
    def on_bar(self, bar: Bar):
        # 更新 RSI
        self.rsi.handle_bar(bar)
        
        # 原始逻辑
        super().on_bar(bar)
    
    def _should_enter_long(self, bar: Bar) -> bool:
        # 添加 RSI 过滤
        if self.rsi.value > 70:  # 超买，不做多
            return False
        return super()._should_enter_long(bar)
    
    def _should_enter_short(self, bar: Bar) -> bool:
        # 添加 RSI 过滤
        if self.rsi.value < 30:  # 超卖，不做空
            return False
        return super()._should_enter_short(bar)
```

### Q7: 如何处理滑点和手续费？

**回测时考虑成本**:
```python
# 在回测引擎中设置
engine.add_venue(
    venue=venue,
    oms_type="NETTING",
    account_type="MARGIN",
    base_currency="USDT",
    starting_balances=["100000 USDT"],
    # 设置手续费
    maker_fee=0.0002,  # 0.02% Maker
    taker_fee=0.0004,  # 0.04% Taker
)

# 考虑滑点
# 在策略中使用限价单而非市价单
order = self.order_factory.limit(
    instrument_id=self.instrument.id,
    order_side=OrderSide.BUY,
    quantity=qty,
    price=self.instrument.make_price(bar.close * 1.001)  # 0.1% 滑点
)
```

---

## 进阶主题

### 多币种组合

```python
# 同时交易多个币种
symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

for symbol in symbols:
    config = DualThrustConfig()
    config.symbol = symbol
    config.lookback_period = 4
    config.k1 = 0.5
    config.k2 = 0.5
    config.qty_percent = 0.05  # 每个币种 5%
    
    strategy = DualThrustStrategy(config)
    engine.add_strategy(strategy)
```

### 动态参数调整

```python
class AdaptiveDualThrust(DualThrustStrategy):
    """根据市场波动率动态调整参数"""
    
    def on_bar(self, bar: Bar):
        # 计算波动率
        if len(self.closes) >= 20:
            volatility = np.std(self.closes[-20:]) / np.mean(self.closes[-20:])
            
            # 高波动: 扩宽通道
            if volatility > 0.05:
                self.k1 = 0.7
                self.k2 = 0.7
            # 低波动: 收窄通道
            else:
                self.k1 = 0.4
                self.k2 = 0.4
        
        super().on_bar(bar)
```

### 机器学习增强

```python
import joblib

class MLEnhancedDualThrust(DualThrustStrategy):
    """使用 ML 模型预测突破有效性"""
    
    def __init__(self, config):
        super().__init__(config)
        self.ml_model = joblib.load("models/breakout_classifier.pkl")
    
    def _should_enter_long(self, bar: Bar) -> bool:
        # 提取特征
        features = self._extract_features(bar)
        
        # ML 预测
        prediction = self.ml_model.predict_proba([features])[0][1]
        
        # 结合传统信号和 ML 预测
        traditional_signal = super()._should_enter_long(bar)
        return traditional_signal and prediction > 0.6
```

---

## 参考资料

- [Strategy API 文档](../api/strategy-api.md)
- [部署指南](../deployment/deployment-guide.md)
- [项目 README](../../README.md)
- [Dual Thrust 原始论文](https://www.google.com/search?q=dual+thrust+strategy+michael+chalek)

---

**最后更新**: 2026-02-19
**策略版本**: v2.1
**作者**: Nautilus Practice Team
