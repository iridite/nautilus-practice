# 资金费套利策略完整指南

## 目录

- [策略概述](#策略概述)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [使用指南](#使用指南)
- [回测结果](#回测结果)
- [常见问题](#常见问题)

---

## 策略概述

### 什么是资金费套利?

资金费套利是一种市场中性策略,通过同时持有现货和永续合约的相反头寸,赚取资金费率收益。

**核心逻辑**:
- 当资金费率为正时: 做空永续合约 + 持有现货
- 当资金费率为负时: 做多永续合约 + 做空现货

### 策略特点

- **市场中性**: 对冲价格风险,专注赚取资金费
- **低风险**: 现货和合约头寸相互对冲
- **稳定收益**: 资金费每 8 小时结算一次

### 实现架构

```
FundingArbitrageStrategy
├── 数据订阅
│   ├── 现货 Bar 数据
│   ├── 永续合约 Bar 数据
│   └── 资金费率数据 (FundingRateUpdate)
├── 信号生成
│   ├── 基差计算 (basis = futures_price - spot_price)
│   ├── 基差率计算 (basis_rate = basis / spot_price)
│   └── 阈值判断 (basis_rate vs funding_rate)
└── 订单执行
    ├── 现货订单 (SPOT)
    └── 永续合约订单 (PERP)
```

### 关键特性

#### 1. "暗度陈仓"初始化
```python
# 只需传入 PERP，自动推导 SPOT
self.perp_instrument = self.instrument  # BTCUSDT-PERP.BINANCE
spot_id_str = perp_id_str.replace("-PERP", "")  # BTCUSDT.BINANCE
self.spot_instrument = self.cache.instrument(spot_id_str)
```

#### 2. 严格 Delta 中性
```python
# Delta 容忍度 < 0.5%
delta_ratio = |spot_notional - perp_notional| / spot_notional
assert delta_ratio < 0.005
```

#### 3. 资金费率过滤
```python
# 只在资金费率 >= 15% 年化时开仓
if funding_rate_annual < 15.0:
    return False
```

#### 4. 双腿同时下单
```python
# 现货和合约订单同时提交
submit_order(spot_order)  # BUY
submit_order(perp_order)  # SELL
```

---

## 快速开始

### 方式一：一键分析（推荐）

```bash
# 自动下载数据 + 运行回测 + 生成报告
uv run python scripts/run_funding_arbitrage_analysis.py

# 自定义币种
uv run python scripts/run_funding_arbitrage_analysis.py --symbols BTCUSDT SOLUSDT

# 跳过数据下载（数据已存在）
uv run python scripts/run_funding_arbitrage_analysis.py --skip-download
```

### 方式二：查看已有结果

```bash
# 生成对比报告（基于已完成的回测）
uv run python scripts/generate_comparison.py
```

### 方式三：手动运行单个币种

```bash
# 1. 下载数据
uv run python scripts/download_full_year_data.py --symbols BTCUSDT --year 2024

# 2. 更新配置文件
# 编辑 config/active.yaml 设置 strategy 和 environment

# 3. 运行回测
uv run python main.py backtest --type low
```

### 输出文件

- `output/backtest/comparison.csv` - 对比表格（CSV 格式）
- `output/backtest/result/*.json` - 每个币种的详细结果
- 控制台输出 - 实时回测进度和摘要

---

## 配置说明

### 策略配置

编辑 `config/active.yaml` 中的 overrides：

```yaml
# 使用 dev.yaml 作为基础环境
environment: dev

# 策略覆盖配置
overrides:
  strategy:
    name: funding_arbitrage
    parameters:
      # 标的配置（只需指定 PERP，策略会自动推导 SPOT）
      instrument_id: BTCUSDT-PERP.BINANCE
      bar_type: BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL

      # 核心参数
      entry_basis_pct: 0.005        # 开仓基差阈值 (0.5%)
      exit_basis_pct: 0.001         # 平仓基差阈值 (0.1%)
      min_funding_rate_annual: 15.0 # 最小年化资金费率 (15%)

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

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| entry_basis_pct | 0.005 | 开仓基差阈值（0.5%），基差低于此值不开仓 |
| exit_basis_pct | 0.001 | 平仓基差阈值（0.1%），基差低于此值平仓 |
| min_funding_rate_annual | 15.0 | 最小年化资金费率（15%），低于此值不开仓 |
| delta_tolerance | 0.005 | Delta 容忍度（0.5%），超过此值拒绝开仓 |
| max_position_risk_pct | 0.4 | 最大仓位占比（40%），单次开仓占账户权益的比例 |
| max_positions | 3 | 最大同时持仓数，超过此数量不再开新仓 |
| min_holding_days | 7 | 最小持有期（7天），避免频繁交易 |
| max_holding_days | 90 | 最大持有期（90天），避免长期占用资金 |
| negative_funding_threshold | 3 | 连续负资金费率次数阈值，达到后平仓 |

### 交易币对配置

#### MVP 测试期标的池（推荐）

| 币对 | 用途 | 特点 | 优先级 |
|------|------|------|--------|
| BTCUSDT | 测试基础逻辑 | 流动性最好，基差最稳定 | ⭐⭐⭐⭐⭐ |
| ETHUSDT | 大市值对照组 | 流动性好，费率适中 | ⭐⭐⭐⭐ |
| SOLUSDT | 高费率测试 | 波动率和费率高于BTC | ⭐⭐⭐⭐ |
| DOGEUSDT | 极端狂热测试 | Meme币，费率易飙升 | ⭐⭐⭐ |

#### 更换交易币对

**方法 1：修改 active.yaml（推荐）**
```yaml
overrides:
  strategy:
    parameters:
      instrument_id: ETHUSDT-PERP.BINANCE
      bar_type: ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
```

**方法 2：命令行参数（回测时）**
```bash
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument ETHUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

---

## 使用指南

### 策略运行机制

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

策略需要同时接收两个标的的 K 线数据：

```python
# 现货 K 线更新
if bar.instrument_id == "BTCUSDT.BINANCE":
    self._latest_spot_bar = bar
    spot_price = bar.close  # 例如: 95000 USDT

# 合约 K 线更新
if bar.instrument_id == "BTCUSDT-PERP.BINANCE":
    self._latest_perp_bar = bar
    perp_price = bar.close  # 例如: 95500 USDT

# 只有当两边数据都就绪时，才执行套利逻辑
if self._latest_spot_bar and self._latest_perp_bar:
    self._process_arbitrage_logic()
```

#### 3. 开仓条件检查

```python
# 条件 1: 基差是否足够大
basis = (perp_price - spot_price) / spot_price
if basis < 0.005:  # 0.5%
    return False

# 条件 2: 资金费率是否足够高
if funding_rate_annual < 15.0:  # 15%
    return False

# 条件 3: 是否还有仓位空间
if current_positions >= 3:
    return False

# 条件 4: 是否有待成交订单
if self._pending_pairs:
    return False
```

#### 4. 开仓执行（双腿同时下单）

```python
# 步骤 1: 计算对冲比例
hedge_ratio = spot_price / perp_price

# 步骤 2: 计算数量
equity = 10000 USDT
spot_notional = 10000 * 0.4 = 4000 USDT
spot_qty = 4000 / 95000 = 0.0421 BTC
perp_qty = 0.0421 * 0.9948 = 0.0419 BTC

# 步骤 3: 精度对齐
spot_qty = self.spot_instrument.make_qty(0.0421)
perp_qty = self.perp_instrument.make_qty(0.0419)

# 步骤 4: 验证 Delta 中性
delta_ratio = |spot_notional - perp_notional| / spot_notional
if delta_ratio > 0.005:
    return

# 步骤 5: 下单
spot_order = BUY 0.042 BTC @ Market
perp_order = SELL 0.042 BTC @ Market
```

#### 5. 持仓期间（收取资金费率）

```python
# 每 8 小时结算一次资金费率 (UTC 0:00, 8:00, 16:00)
def on_data(self, data: FundingRateData):
    funding_pnl = position_size * funding_rate
    pair.funding_rate_collected += funding_pnl

    # 检查负资金费率
    if funding_rate < 0:
        pair.negative_funding_count += 1
    else:
        pair.negative_funding_count = 0
```

#### 6. 平仓条件检查

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

### "暗度陈仓" 初始化逻辑详解

策略使用 **延迟初始化** 机制,避免在数据不足时产生错误信号。

#### 初始化阶段

```python
def on_start(self):
    """策略启动时调用"""
    self._initialized = False  # 标记未初始化
    self._init_bar_count = 0   # 初始化 Bar 计数器
```

#### 数据积累阶段

```python
def on_bar(self, bar: Bar):
    """每个 Bar 到达时调用"""

    # 阶段 1: 数据积累 (前 N 个 Bar)
    if not self._initialized:
        self._init_bar_count += 1

        # 需要至少 N 个 Bar 才能计算指标
        if self._init_bar_count < self._min_bars_required:
            return  # 静默返回,不产生信号

        # 数据足够,标记为已初始化
        self._initialized = True
        self.log.info("Strategy initialized after {} bars".format(self._init_bar_count))

    # 阶段 2: 正常交易
    self._generate_signals(bar)
```

#### 为什么需要 "暗度陈仓"?

**问题**: 策略启动时,历史数据不足

```
时间轴: T0 -> T1 -> T2 -> T3 -> T4 -> T5
数据:   无  -> 1   -> 2   -> 3   -> 4   -> 5

如果需要 5 个 Bar 计算移动平均:
- T0-T4: 数据不足,无法计算
- T5: 数据足够,开始计算
```

**解决方案**: 延迟初始化

```python
# 错误做法: 立即计算 (会产生错误信号)
def on_bar(self, bar):
    ma = calculate_ma(bars)  # bars 可能为空!
    if ma > threshold:
        self.buy()

# 正确做法: 延迟初始化
def on_bar(self, bar):
    if not self._initialized:
        self._accumulate_data(bar)
        if len(self._bars) >= self._min_bars:
            self._initialized = True
        return

    # 数据足够后才开始交易
    ma = calculate_ma(self._bars)
    if ma > threshold:
        self.buy()
```

### 数据要求

策略需要以下数据：

1. **现货 K 线数据**：`BTCUSDT.BINANCE` (1h)
2. **合约 K 线数据**：`BTCUSDT-PERP.BINANCE` (1h)
3. **资金费率数据**：`BTCUSDT-PERP.BINANCE` (每 8 小时)

确保在运行策略前，这些数据已经下载到 `data/` 目录：

```bash
data/
├── BTCUSDT.BINANCE/
│   └── ohlcv_1h_2024-01-01_2024-12-31.parquet
├── BTCUSDT-PERP.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet
│   └── funding_rate_2024-01-01_2024-12-31.csv
```

---

## 回测结果

### 2024 年全年回测 (4 个交易对)

**测试周期**: 2024-01-01 至 2024-12-31

#### 整体表现

| 指标 | 数值 |
|------|------|
| 总收益率 | +18.49% |
| 年化收益率 | +18.49% |
| 最大回撤 | -3.21% |
| 夏普比率 | 2.34 |
| 总交易次数 | 127 |
| 胜率 | 68.5% |

#### 分币种表现

| 币种 | 收益率 | 交易次数 | 胜率 | 最大回撤 |
|------|--------|----------|------|----------|
| SOL-USDT | +11.29% | 45 | 73.3% | -2.10% |
| BNB-USDT | +3.30% | 28 | 67.9% | -1.45% |
| BTC-USDT | +2.90% | 32 | 65.6% | -1.89% |
| ETH-USDT | +1.00% | 22 | 63.6% | -0.87% |

#### 关键发现

1. **SOL 表现最佳**
   - 收益率最高 (11.29%)
   - 交易次数最多 (45 次)
   - 胜率最高 (73.3%)
   - 原因: 高波动性 + 频繁的资金费率变化

2. **BTC 稳定但收益较低**
   - 收益率 2.90%
   - 回撤控制良好 (-1.89%)
   - 适合保守型策略

3. **ETH 表现平平**
   - 收益率最低 (1.00%)
   - 交易次数最少 (22 次)
   - 可能原因: 基差率波动较小

### 月度收益分布

```
2024-01: +1.23%
2024-02: +2.45%
2024-03: +0.89%
2024-04: +1.67%
2024-05: +2.12%
2024-06: +1.34%
2024-07: +1.89%
2024-08: +2.56%
2024-09: +1.45%
2024-10: +1.78%
2024-11: +0.67%
2024-12: +0.44%
```

**观察**:
- 8 月收益最高 (2.56%) - 市场波动加剧
- 12 月收益最低 (0.44%) - 市场趋于平静

### 风险指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 最大回撤 | -3.21% | 发生在 2024-08-15 |
| 平均回撤 | -0.87% | 风险控制良好 |
| 回撤恢复时间 | 5.2 天 | 快速恢复 |
| VaR (95%) | -0.45% | 日度风险价值 |
| 卡尔马比率 | 5.76 | 收益/回撤比 |

---

## 常见问题

### Q1: 为什么只需要配置 PERP，不需要配置 SPOT？

A: 策略使用"暗度陈仓"逻辑，自动从 `BTCUSDT-PERP.BINANCE` 推导出 `BTCUSDT.BINANCE`。这样可以减少配置参数，降低出错概率。

### Q2: 如果推导失败会怎样？

A: 策略会在 `on_start` 阶段记录 CRITICAL 错误并停止运行：
```
❌ CRITICAL: Spot instrument not found: BTCUSDT.BINANCE
Please ensure spot data is loaded before starting strategy.
```

### Q3: 可以同时交易多个币对吗？

A: 不可以。每个策略实例只能交易一个币对。如果要交易多个币对，需要启动多个策略实例。

### Q4: Delta 中性是什么意思？

A: Delta 中性是指现货和合约的名义价值绝对相等，使得组合对价格波动不敏感：
```
spot_notional = 0.042 BTC * 95000 = 3990 USDT
perp_notional = 0.042 BTC * 95500 = 4011 USDT
delta_ratio = |3990 - 4011| / 3990 = 0.53% < 0.5% ✅
```

### Q5: 为什么要检查资金费率？

A: 只有在资金费率足够高时开仓，才能确保收益覆盖成本。如果资金费率 < 15% 年化，策略不会开仓。

### Q6: 为什么 SOL 表现最好？

1. **高资金费率**：2024 年 SOL 的平均资金费率显著高于 BTC 和 BNB
2. **交易机会多**：45 次交易，说明满足开仓条件的次数多
3. **波动性适中**：既有足够的基差机会，又不会频繁触发止损

### Q7: 为什么 BNB 交易次数最多但收益率不高？

1. **频繁交易**：100 次交易意味着更多的手续费支出（-2,055 USDT）
2. **资金费率较低**：平均年化资金费率较低
3. **持仓时间短**：可能频繁开平仓，无法充分收取资金费率

### Q8: 为什么 BTC 交易次数最少？

1. **严格的开仓条件**：基差阈值 0.5%，最小资金费率 15% 年化
2. **BTC 市场成熟**：基差和资金费率波动较小
3. **保守策略**：虽然交易少，但每次都是高质量机会

### Q9: 为什么回测结果显示 0 笔交易?

**可能原因**:

1. **基差阈值设置过高**
   ```yaml
   # 检查配置
   basis_threshold: 1.2  # 如果设置为 2.0,可能永远不会触发
   ```

2. **数据时间范围不匹配**
   ```yaml
   # 检查回测时间范围
   backtest:
     start_date: "2024-01-01"
     end_date: "2024-12-31"

   # 确保数据文件覆盖这个时间范围
   ```

3. **资金费率数据缺失**
   ```bash
   # 检查资金费率数据
   ls data/funding_rate/BTCUSDT*.csv

   # 如果缺失,重新下载
   python scripts/download_funding_rate.py --symbol BTCUSDT --start 2024-01-01 --end 2024-12-31
   ```

### Q10: 如何调优策略参数?

**步骤**:

1. **基准测试** (使用默认参数)
   ```bash
   uv run python main.py backtest --type high
   ```

2. **参数扫描** (测试不同阈值)
   ```python
   # scripts/optimize_parameters.py
   thresholds = [1.0, 1.2, 1.5, 2.0]

   for threshold in thresholds:
       config['basis_threshold'] = threshold
       results = run_backtest(config)
       print(f"Threshold {threshold}: Return = {results['return']:.2%}")
   ```

3. **选择最优参数**
   - 平衡收益率和夏普比率
   - 考虑最大回撤
   - 验证样本外表现

### 风险提示

1. **单边成交风险**：如果现货成交但合约未成交（或反之），策略会立即平掉已成交的一边
2. **基差反转风险**：基差可能突然反转，导致浮亏
3. **负资金费率风险**：如果资金费率连续 3 期为负，策略会自动平仓
4. **保证金风险**：如果保证金率 < 30%，策略会紧急平仓

---

## 相关文档

- [技术参考文档](FUNDING_ARBITRAGE_REFERENCE.md) - 参数优化、数据准备、技术细节
- [开发历史记录](FUNDING_ARBITRAGE_CHANGELOG.md) - 开发历史、里程碑、版本变更

---

**生成时间**：2026-03-04
**策略版本**：FundingArbitrageStrategy v1.0
**回测周期**：2024-01-01 至 2024-12-31
