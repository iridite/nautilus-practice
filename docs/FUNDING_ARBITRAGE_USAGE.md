# 资金费率套利策略使用说明

## 策略运行机制详解

### 核心原理

这是一个 **Delta 中性资金费率套利策略**,通过以下方式获利:

1. **做多现货 (SPOT)** + **做空永续合约 (PERP)** = Delta 中性组合
2. 收取永续合约的**正资金费率**收益 (每 8 小时结算一次)
3. 当基差收敛时平仓,获取**基差收益**

### 交易币对

**当前配置**: `BTCUSDT-PERP.BINANCE` (比特币永续合约)

策略会自动推导出对应的现货标的:
- **输入**: `BTCUSDT-PERP.BINANCE` (永续合约)
- **自动推导**: `BTCUSDT.BINANCE` (现货)

### 运行流程

#### 1. 初始化阶段 (on_start)

```python
# 步骤 1: 获取传入的永续合约
self.perp_instrument = self.instrument  # BTCUSDT-PERP.BINANCE

# 步骤 2: 暗度陈仓 - 自动推导现货标的
perp_id_str = "BTCUSDT-PERP.BINANCE"
spot_id_str = perp_id_str.replace("-PERP", "")  # "BTCUSDT.BINANCE"
self.spot_instrument = self.cache.instrument(spot_id_str)

# 步骤 3: 订阅双边数据
self.subscribe_bars(spot_bar_type)  # 订阅现货 K 线
self.subscribe_bars(perp_bar_type)  # 订阅合约 K 线
self.subscribe_data(funding_data_type)  # 订阅资金费率
```

#### 2. 数据同步 (on_bar)

策略需要同时接收两个标的的 K 线数据:

```python
# 现货 K 线更新
if bar.instrument_id == "BTCUSDT.BINANCE":
    self._latest_spot_bar = bar
    spot_price = bar.close  # 例如: 95000 USDT

# 合约 K 线更新
if bar.instrument_id == "BTCUSDT-PERP.BINANCE":
    self._latest_perp_bar = bar
    perp_price = bar.close  # 例如: 95500 USDT

# 只有当两边数据都就绪时,才执行套利逻辑
if self._latest_spot_bar and self._latest_perp_bar:
    self._process_arbitrage_logic()
```

#### 3. 开仓条件检查

策略会检查以下条件:

```python
# 条件 1: 基差是否足够大
basis = (perp_price - spot_price) / spot_price
# 例如: (95500 - 95000) / 95000 = 0.00526 = 0.526%

if basis < 0.005:  # 0.5%
    return False  # 基差太小,不开仓

# 条件 2: 资金费率是否足够高
if funding_rate_annual < 15.0:  # 15%
    return False  # 资金费率太低,不开仓

# 条件 3: 是否还有仓位空间
if current_positions >= 3:
    return False  # 已达到最大持仓数

# 条件 4: 是否有待成交订单
if self._pending_pairs:
    return False  # 有待成交订单,等待完成
```

#### 4. 开仓执行 (双腿同时下单)

```python
# 步骤 1: 计算对冲比例
hedge_ratio = spot_price / perp_price
# 例如: 95000 / 95500 = 0.9948

# 步骤 2: 计算数量
equity = 10000 USDT  # 账户权益
spot_notional = 10000 * 0.4 = 4000 USDT  # 40% 仓位
spot_qty = 4000 / 95000 = 0.0421 BTC
perp_qty = 0.0421 * 0.9948 = 0.0419 BTC

# 步骤 3: 精度对齐
spot_qty = self.spot_instrument.make_qty(0.0421)  # 0.042 BTC (对齐到交易所精度)
perp_qty = self.perp_instrument.make_qty(0.0419)  # 0.042 BTC

# 步骤 4: 验证 Delta 中性
spot_notional_actual = 0.042 * 95000 = 3990 USDT
perp_notional_actual = 0.042 * 95500 = 4011 USDT
delta_ratio = |3990 - 4011| / 3990 = 0.0053 = 0.53%

if delta_ratio > 0.005:  # 0.5%
    return  # Delta 不中性,放弃开仓

# 步骤 5: 下单
spot_order = BUY 0.042 BTC @ Market  # 做多现货
perp_order = SELL 0.042 BTC @ Market  # 做空合约

# 步骤 6: 记��待配对订单
self._pending_pairs[pair_id] = {
    spot_order_id: "xxx",
    perp_order_id: "yyy",
    submit_time: now
}
```

#### 5. 持仓期间 (收取资金费率)

```python
# 每 8 小时结算一次资金费率 (UTC 0:00, 8:00, 16:00)
def on_data(self, data: FundingRateData):
    # 例如: funding_rate = 0.01% (正资金费率)
    # 做空合约收取资金费率
    funding_pnl = 0.042 BTC * 0.0001 = 0.0000042 BTC
    # 约等于: 0.0000042 * 95500 = 0.40 USDT

    # 累计收益
    pair.funding_rate_collected += 0.40 USDT

    # 检查负资金费率
    if funding_rate < 0:
        pair.negative_funding_count += 1
    else:
        pair.negative_funding_count = 0
```

#### 6. 平仓条件检查

策略会检查以下平仓条件:

```python
# 条件 1: 基差收敛
if basis < 0.001:  # 0.1%
    close_position("basis_converged")

# 条件 2: 持有时间到期
if holding_days > 90:
    close_position("max_holding_days")

# 条件 3: 连续负资金费率
if negative_funding_count >= 3:
    close_position("negative_funding_rate")
```

#### 7. 平仓执行 (双腿同时下单)

```python
# 步骤 1: 获取持仓
spot_position = cache.positions_open(BTCUSDT.BINANCE)[0]
perp_position = cache.positions_open(BTCUSDT-PERP.BINANCE)[0]

# 步骤 2: 下单平仓
spot_close_order = SELL 0.042 BTC @ Market  # 平掉现货多头
perp_close_order = BUY 0.042 BTC @ Market   # 平掉合约空头

# 步骤 3: 计算收益
holding_days = 30 天
funding_collected = 12.5 USDT  # 累计资金费率收益
basis_pnl = (exit_basis - entry_basis) * notional
total_pnl = funding_collected + basis_pnl
```

### 配置参数说明

```yaml
# config/strategies/funding_arbitrage.yaml

# 标的配置 (只需指定 PERP,策略会自动推导 SPOT)
instrument_id: BTCUSDT-PERP.BINANCE  # 永续合约标的
bar_type: BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL  # K线类型

# 核心参数
entry_basis_pct: 0.005        # 开仓基差阈值 (0.5%)
exit_basis_pct: 0.001         # 平仓基差阈值 (0.1%)
min_funding_rate_annual: 15.0 # 最小要求年化资金费率 (15%)

# Delta 管理
delta_tolerance: 0.005        # Delta 容忍度 (0.5%)

# 仓位管理
max_position_risk_pct: 0.4    # 最大仓位占比 (40%)
max_positions: 3              # 最大同时持仓数

# 持仓管理
min_holding_days: 7           # 最小持有期（7天）
max_holding_days: 90          # 最大持有期（90天）

# 资金费率管理
negative_funding_threshold: 3 # 连续负资金费率次数阈值

# 风控参数
min_margin_ratio: 0.5         # 最小保证金率（50%）
emergency_margin_ratio: 0.3   # 紧急保证金率（30%）

# 订单超时
order_timeout_seconds: 5.0    # 订单超时时间（5秒）
```

### 如何更换交易币对

#### 方法 1: 修改配置文件 (推荐)

```yaml
# 交易 ETH
instrument_id: ETHUSDT-PERP.BINANCE
bar_type: ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL

# 交易 SOL
instrument_id: SOLUSDT-PERP.BINANCE
bar_type: SOLUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
```

#### 方法 2: 使用简化配置

```yaml
# 只需指定 symbol 和 timeframe,其他自动生成
symbol: ETHUSDT-PERP
timeframe: 1h
price_type: LAST
origination: EXTERNAL
```

#### 方法 3: 命令行参数 (回测时)

```bash
# 回测 BTC
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument BTCUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 回测 ETH
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument ETHUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

### 数据要求

策略需要以下数据:

1. **现货 K 线数据**: `BTCUSDT.BINANCE` (1h)
2. **合约 K 线数据**: `BTCUSDT-PERP.BINANCE` (1h)
3. **资金费率数据**: `BTCUSDT-PERP.BINANCE` (每 8 小时)

确保在运行策略前,这些数据已经下载到 `data/` 目录:

```bash
data/
├── BTCUSDT.BINANCE/
│   └── ohlcv_1h_2024-01-01_2024-12-31.parquet
├── BTCUSDT-PERP.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet
│   └── funding_rate_2024-01-01_2024-12-31.csv
```

### 风险提示

1. **单边成交风险**: 如果现货成交但合约未成交(或反之),策略会立即平掉已成交的一边
2. **基差反转风险**: 基差可能突然反转,导致浮亏
3. **负资金费率风险**: 如果资金费率连续 3 期为负,策略会自动平仓
4. **保证金风险**: 如果保证金率 < 30%,策略会紧急平仓

### 预期收益

假设:
- 入场基差: 0.5%
- 平仓基差: 0.1%
- 平均资金费率: 0.01% / 8h = 0.03% / day = 10.95% / year
- 持有期: 30 天

**收益计算**:
- 基差收益: 0.5% - 0.1% = 0.4%
- 资金费率收益: 0.03% * 30 = 0.9%
- 总收益: 0.4% + 0.9% = 1.3% (30 天)
- 年化收益: 1.3% * 12 = 15.6%

**实际收益会受以下因素影响**:
- 滑点: 0.2% (单边)
- 手续费: 0.3% (Taker)
- 资金费率波动
- 基差波动

### 常见问题

#### Q1: 为什么只需要配置 PERP,不需要配置 SPOT?

A: 策略使用"暗度陈仓"逻辑,自动从 `BTCUSDT-PERP.BINANCE` 推导出 `BTCUSDT.BINANCE`��这样可以减少配置参数,降低出错概率。

#### Q2: 如果推导失败会怎样?

A: 策略会在 `on_start` 阶段记录 CRITICAL 错误并停止运行:
```
❌ CRITICAL: Spot instrument not found: BTCUSDT.BINANCE
Please ensure spot data is loaded before starting strategy.
```

#### Q3: 可以同时交易多个币对吗?

A: 不可以。每个策略实例只能交易一个币对。如果要交易多个币对,需要启动多个策略实例。

#### Q4: Delta 中性是什么意思?

A: Delta 中性是指现货和合约的名义价值绝对相等,使得组合对价格波动不敏感:
```
spot_notional = 0.042 BTC * 95000 = 3990 USDT
perp_notional = 0.042 BTC * 95500 = 4011 USDT
delta_ratio = |3990 - 4011| / 3990 = 0.53% < 0.5% ✅
```

#### Q5: 为什么要检查资金费率?

A: 只有在资金费率足够高时开仓,才能确保收益覆盖成本。如果资金费率 < 15% 年化,策略不会开仓。

### 总结

这个策略的核心优势:

1. ✅ **自动推导标的**: 只需配置 PERP,自动推导 SPOT
2. ✅ **Delta 中性**: 不受价格波动影响
3. ✅ **收取资金费率**: 每 8 小时结算一次
4. ✅ **基差收益**: 基差收敛时平仓获利
5. ✅ **风险可控**: 多重平仓条件,单边成交失败处理
6. ✅ **配置灵活**: 支持多种配置方式

**当前交易币对**: `BTCUSDT` (比特币)
**可更换为**: `ETHUSDT`, `SOLUSDT`, `BNBUSDT` 等任何支持永续合约的币对
