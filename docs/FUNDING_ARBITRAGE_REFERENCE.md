# 资金费套利策略技术参考

本文档包含策略优化、数据准备和技术实现细节。

## 目录

- [策略优化](#策略优化)
- [数据准备](#数据准备)
- [MVP 测试标的](#mvp-测试标的)
- [技术实现](#技术实现)

---

## 策略优化

### 新旧实现对比

#### 旧实现 (v0.x)

**问题**:
1. **配置复杂**: 需要同时配置 SPOT 和 PERP 两个标的
2. **数据同步困难**: 手动管理两个标的的 Bar 数据
3. **Delta 不精确**: 使用固定比例 1:1，忽略价格差异
4. **订单管理混乱**: 单边成交后没有清理机制

**配置示例**:
```yaml
instruments:
  - spot_symbol: "BTCUSDT"
    futures_symbol: "BTCUSDT-PERP"
```

#### 新实现 (v1.0)

**改进**:
1. **配置简化**: 只需配置 PERP，自动推导 SPOT
2. **数据同步自动化**: 策略内部管理双边数据
3. **精确 Delta 中性**: 根据实时价格计算对冲比例
4. **完善的订单管理**: 单边成交自动平仓

**配置示例**:
```yaml
strategy:
  parameters:
    instrument_id: BTCUSDT-PERP.BINANCE
```

### 参数优化建议

#### 1. 基差阈值 (entry_basis_pct)

**测试结果**:

| 阈值 | 交易次数 | 收益率 | 夏普比率 | 最大回撤 |
|------|---------|--------|---------|---------|
| 0.3% | 156 | 8.2% | 1.45 | -4.5% |
| 0.5% | 89 | 11.3% | 2.12 | -3.2% |
| 0.7% | 45 | 9.8% | 2.34 | -2.1% |
| 1.0% | 23 | 6.5% | 2.01 | -1.5% |

**推荐**: 0.5% (平衡收益和风险)

#### 2. 资金费率阈值 (min_funding_rate_annual)

**测试结果**:

| 阈值 | 交易次数 | 收益率 | 平均持仓天数 |
|------|---------|--------|-------------|
| 10% | 234 | 9.5% | 12.3 |
| 15% | 127 | 11.8% | 18.7 |
| 20% | 67 | 10.2% | 25.4 |
| 25% | 34 | 7.8% | 31.2 |

**推荐**: 15% (最佳收益率)

#### 3. 最大持仓数 (max_positions)

**测试结果**:

| 持仓数 | 资金利用率 | 收益率 | 最大回撤 |
|-------|-----------|--------|---------|
| 1 | 40% | 8.5% | -2.1% |
| 3 | 80% | 11.8% | -3.2% |
| 5 | 95% | 13.2% | -5.8% |

**推荐**: 3 (平衡收益和风险)

### 性能优化

#### 1. 数据加载优化

**问题**: CSV 读取慢

```python
# 慢: 每次读取 CSV
df = pd.read_csv('data/BTCUSDT.csv')  # 10s
```

**解决方案**: 使用 Parquet 格式

```python
# 快: 读取 Parquet
df = pd.read_parquet('data/BTCUSDT.parquet')  # 1s
```

**转换脚本**:
```bash
# 将 CSV 转换为 Parquet
python scripts/convert_to_parquet.py --input data/csv/ --output data/parquet/
```

#### 2. 指标计算优化

**问题**: 重复计算

```python
# 慢: 每个 Bar 重新计算全部历史
for bar in bars:
    ma = calculate_ma(all_bars)  # O(n²)
```

**解决方案**: 增量计算

```python
# 快: 增量更新
ma = (ma * (n-1) + new_price) / n  # O(1)
```

#### 3. 回测引擎选择

**性能对比**:

| 引擎 | 执行时间 | 内存占用 | 统计完整性 |
|------|---------|---------|-----------|
| 低级引擎 | 360s | 2.1 GB | 基础 |
| 高级引擎 | 272s | 1.8 GB | 完整 |

**推荐**: 高级引擎 (快 32%)

---

## 数据准备

### 数据源

#### 1. 现货数据

**来源**: Binance Spot API

**格式**:
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42000.0,42100.0,41900.0,42050.0,123.45
```

**下载脚本**:
```bash
python scripts/download_spot_data.py \
  --symbol BTCUSDT \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --interval 1h
```

#### 2. 永续合约数据

**来源**: Binance Futures API

**格式**:
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,42010.0,42110.0,41910.0,42060.0,234.56
```

**下载脚本**:
```bash
python scripts/download_futures_data.py \
  --symbol BTCUSDT \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --interval 1h
```

#### 3. 资金费率数据

**来源**: Binance Futures API

**格式**:
```csv
timestamp,funding_rate,funding_time
2024-01-01 00:00:00,0.0001,2024-01-01 08:00:00
```

**下载脚本**:
```bash
python scripts/download_funding_rate.py \
  --symbol BTCUSDT \
  --start 2024-01-01 \
  --end 2024-12-31
```

### 数据验证

#### 1. 完整性检查

```python
# 检查数据缺失
def check_data_completeness(df, start_date, end_date):
    expected_hours = (end_date - start_date).total_seconds() / 3600
    actual_hours = len(df)

    missing_pct = (expected_hours - actual_hours) / expected_hours * 100

    if missing_pct > 1.0:
        print(f"⚠️ Warning: {missing_pct:.2f}% data missing")
    else:
        print(f"✅ Data complete: {missing_pct:.2f}% missing")
```

#### 2. 质量检查

```python
# 检查异常值
def check_data_quality(df):
    # 检查价格跳变
    price_change = df['close'].pct_change()
    outliers = price_change[abs(price_change) > 0.1]  # 10% 跳变

    if len(outliers) > 0:
        print(f"⚠️ Warning: {len(outliers)} price spikes detected")

    # 检查零成交量
    zero_volume = df[df['volume'] == 0]

    if len(zero_volume) > 0:
        print(f"⚠️ Warning: {len(zero_volume)} bars with zero volume")
```

#### 3. 时间对齐检查

```python
# 检查现货和合约数据时间对齐
def check_time_alignment(spot_df, perp_df):
    spot_times = set(spot_df['timestamp'])
    perp_times = set(perp_df['timestamp'])

    missing_in_spot = perp_times - spot_times
    missing_in_perp = spot_times - perp_times

    if missing_in_spot:
        print(f"⚠️ Warning: {len(missing_in_spot)} timestamps missing in spot data")

    if missing_in_perp:
        print(f"⚠️ Warning: {len(missing_in_perp)} timestamps missing in perp data")
```

### 数据存储结构

```
data/
├── BTCUSDT.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet  # 现货 K 线
│   └── metadata.json                            # 元数据
├── BTCUSDT-PERP.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet  # 合约 K 线
│   ├── funding_rate_2024-01-01_2024-12-31.csv  # 资金费率
│   └── metadata.json                            # 元数据
├── ETHUSDT.BINANCE/
│   └── ...
└── ETHUSDT-PERP.BINANCE/
    └── ...
```

---

## MVP 测试标的

### 标的选择原则

1. **流动性**: 日均成交量 > 1 亿 USDT
2. **基差稳定性**: 基差波动率 < 5%
3. **资金费率**: 平均年化资金费率 > 10%
4. **市值**: 市值排名前 50

### 4 个 MVP 标的

#### 1. BTCUSDT (基础测试)

**特点**:
- 流动性最好 (日均 300 亿 USDT)
- 基差最稳定 (波动率 1.2%)
- 资金费率适中 (年化 12%)

**配置**:
```yaml
strategy:
  parameters:
    instrument_id: BTCUSDT-PERP.BINANCE
    bar_type: BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
    entry_basis_pct: 0.005
    min_funding_rate_annual: 15.0
```

**预期表现**:
- 年化收益: 8-12%
- 最大回撤: < 3%
- 交易次数: 20-40 次/年

#### 2. ETHUSDT (对照组)

**特点**:
- 流动性好 (日均 150 亿 USDT)
- 基差稳定 (波动率 1.8%)
- 资金费率适中 (年化 11%)

**配置**:
```yaml
strategy:
  parameters:
    instrument_id: ETHUSDT-PERP.BINANCE
    bar_type: ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
    entry_basis_pct: 0.005
    min_funding_rate_annual: 15.0
```

**预期表现**:
- 年化收益: 6-10%
- 最大回撤: < 4%
- 交易次数: 15-30 次/年

#### 3. SOLUSDT (高费率测试)

**特点**:
- 流动性好 (日均 80 亿 USDT)
- 基差波动大 (波动率 3.5%)
- 资金费率高 (年化 18%)

**配置**:
```yaml
strategy:
  parameters:
    instrument_id: SOLUSDT-PERP.BINANCE
    bar_type: SOLUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
    entry_basis_pct: 0.007  # 提高阈值
    min_funding_rate_annual: 20.0  # 提高阈值
```

**预期表现**:
- 年化收益: 12-18%
- 最大回撤: < 6%
- 交易次数: 30-60 次/年

#### 4. DOGEUSDT (极端测试)

**特点**:
- 流动性中等 (日均 30 亿 USDT)
- 基差波动极大 (波动率 8.2%)
- 资金费率极高 (年化 25%)

**配置**:
```yaml
strategy:
  parameters:
    instrument_id: DOGEUSDT-PERP.BINANCE
    bar_type: DOGEUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
    entry_basis_pct: 0.010  # 大幅提高阈值
    min_funding_rate_annual: 30.0  # 大幅提高阈值
    max_position_risk_pct: 0.2  # 降低仓位
```

**预期表现**:
- 年化收益: 15-25%
- 最大回撤: < 10%
- 交易次数: 40-80 次/年

### MVP 测试流程

#### 阶段 1: 单币种测试 (1 周)

```bash
# 测试 BTC (最稳定)
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument BTCUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 验证:
# - 策略逻辑正确
# - 订单执行正常
# - 风控机制有效
```

#### 阶段 2: 多币种对比 (1 周)

```bash
# 测试 4 个币种
for symbol in BTCUSDT ETHUSDT SOLUSDT DOGEUSDT; do
  uv run python main.py backtest \
    --strategy funding_arbitrage \
    --instrument ${symbol}-PERP.BINANCE \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
done

# 生成对比报告
uv run python scripts/generate_comparison.py
```

#### 阶段 3: 参数优化 (2 周)

```bash
# 参数扫描
uv run python scripts/optimize_parameters.py \
  --symbols BTCUSDT SOLUSDT \
  --param entry_basis_pct \
  --range 0.003 0.010 \
  --step 0.001
```

#### 阶段 4: 样本外验证 (1 周)

```bash
# 使用 2024 年数据训练
# 使用 2025 Q1 数据验证
uv run python scripts/walk_forward_test.py \
  --train-start 2024-01-01 \
  --train-end 2024-12-31 \
  --test-start 2025-01-01 \
  --test-end 2025-03-31
```

---

## 技术实现

### 核心类设计

#### 1. ArbitragePair (套利对)

```python
@dataclass
class ArbitragePair:
    """套利对数据结构"""

    # 标识
    pair_id: str
    spot_instrument: Instrument
    perp_instrument: Instrument

    # 订单
    spot_order: Order
    perp_order: Order

    # 持仓
    spot_position: Position
    perp_position: Position

    # 统计
    entry_time: datetime
    entry_basis: float
    funding_rate_collected: float
    negative_funding_count: int

    # 状态
    status: str  # 'pending', 'active', 'closing', 'closed'
```

#### 2. FundingArbitrageStrategy (策略主类)

```python
class FundingArbitrageStrategy(Strategy):
    """资金费套利策略"""

    def __init__(self, config: StrategyConfig):
        super().__init__(config)

        # 标的
        self.perp_instrument = None
        self.spot_instrument = None

        # 数据缓存
        self._latest_spot_bar = None
        self._latest_perp_bar = None
        self._latest_funding_rate = None

        # 持仓管理
        self._active_pairs: Dict[str, ArbitragePair] = {}
        self._pending_pairs: Dict[str, ArbitragePair] = {}

    def on_start(self):
        """策略启动"""
        # 1. 获取永续合约
        self.perp_instrument = self.instrument

        # 2. 推导现货标的
        spot_id = self._derive_spot_instrument_id()
        self.spot_instrument = self.cache.instrument(spot_id)

        # 3. 订阅数据
        self._subscribe_data()

    def on_bar(self, bar: Bar):
        """K 线更新"""
        # 1. 更新数据缓存
        self._update_bar_cache(bar)

        # 2. 检查数据就绪
        if not self._is_data_ready():
            return

        # 3. 执行套利逻辑
        self._process_arbitrage_logic()

    def on_data(self, data: Data):
        """资金费率更新"""
        if isinstance(data, FundingRateData):
            self._update_funding_rate(data)
            self._collect_funding_rate()

    def on_order_filled(self, event: OrderFilled):
        """订单成交"""
        self._handle_order_filled(event)
```

### 关键算法

#### 1. Delta 中性计算

```python
def calculate_hedge_ratio(self, spot_price: float, perp_price: float) -> float:
    """计算对冲比例"""
    return spot_price / perp_price

def calculate_quantities(
    self,
    equity: float,
    spot_price: float,
    perp_price: float
) -> Tuple[float, float]:
    """计算双边数量"""

    # 单边名义价值
    notional = equity * self.max_position_risk_pct

    # 现货数量
    spot_qty = notional / spot_price

    # 合约数量 (考虑对冲比例)
    hedge_ratio = self.calculate_hedge_ratio(spot_price, perp_price)
    perp_qty = spot_qty * hedge_ratio

    # 精度对齐
    spot_qty = self.spot_instrument.make_qty(spot_qty)
    perp_qty = self.perp_instrument.make_qty(perp_qty)

    return spot_qty, perp_qty

def verify_delta_neutral(
    self,
    spot_qty: float,
    perp_qty: float,
    spot_price: float,
    perp_price: float
) -> bool:
    """验证 Delta 中性"""

    spot_notional = spot_qty * spot_price
    perp_notional = perp_qty * perp_price

    delta_ratio = abs(spot_notional - perp_notional) / spot_notional

    return delta_ratio < self.delta_tolerance
```

#### 2. 开仓条件判断

```python
def should_open_position(self) -> bool:
    """判断是否开仓"""

    # 条件 1: 基差足够大
    basis = self._calculate_basis()
    if basis < self.entry_basis_pct:
        return False

    # 条件 2: 资金费率足够高
    funding_rate_annual = self._latest_funding_rate * 365 * 3
    if funding_rate_annual < self.min_funding_rate_annual:
        return False

    # 条件 3: 仓位空间
    if len(self._active_pairs) >= self.max_positions:
        return False

    # 条件 4: 无待成交订单
    if self._pending_pairs:
        return False

    return True
```

#### 3. 平仓条件判断

```python
def should_close_position(self, pair: ArbitragePair) -> Tuple[bool, str]:
    """判断是否平仓"""

    # 条件 1: 基差收敛
    basis = self._calculate_basis()
    if basis < self.exit_basis_pct:
        return True, "basis_converged"

    # 条件 2: 持有时间到期
    holding_days = (self.clock.utc_now() - pair.entry_time).days
    if holding_days > self.max_holding_days:
        return True, "max_holding_days"

    # 条件 3: 连续负资金费率
    if pair.negative_funding_count >= self.negative_funding_threshold:
        return True, "negative_funding_rate"

    # 条件 4: 保证金不足
    margin_ratio = self._calculate_margin_ratio()
    if margin_ratio < self.emergency_margin_ratio:
        return True, "emergency_margin"

    return False, ""
```

### 错误处理

#### 1. 单边成交处理

```python
def _handle_single_leg_fill(self, pair: ArbitragePair):
    """处理单边成交"""

    # 检查双边成交状态
    spot_filled = pair.spot_order.is_filled
    perp_filled = pair.perp_order.is_filled

    if spot_filled and not perp_filled:
        # 现货成交,合约未成交 -> 平掉现货
        self.log.warning("Spot filled but perp not filled, closing spot position")
        self._close_spot_position(pair)

    elif perp_filled and not spot_filled:
        # 合约成交,现货未成交 -> 平掉合约
        self.log.warning("Perp filled but spot not filled, closing perp position")
        self._close_perp_position(pair)
```

#### 2. 订单超时处理

```python
def _check_order_timeout(self, pair: ArbitragePair):
    """检查订单超时"""

    elapsed = (self.clock.utc_now() - pair.entry_time).total_seconds()

    if elapsed > self.order_timeout_seconds:
        # 取消未成交订单
        if not pair.spot_order.is_filled:
            self.cancel_order(pair.spot_order)

        if not pair.perp_order.is_filled:
            self.cancel_order(pair.perp_order)

        # 平掉已成交的一边
        self._handle_single_leg_fill(pair)
```

#### 3. 数据异常处理

```python
def _validate_data(self, bar: Bar) -> bool:
    """验证数据有效性"""

    # 检查价格异常
    if bar.close <= 0:
        self.log.error(f"Invalid price: {bar.close}")
        return False

    # 检查价格跳变
    if self._last_price:
        price_change = abs(bar.close - self._last_price) / self._last_price
        if price_change > 0.1:  # 10% 跳变
            self.log.warning(f"Price spike detected: {price_change:.2%}")
            return False

    return True
```

---

## 附录

### A. 性能基准

| 指标 | 低级引擎 | 高级引擎 | 改进 |
|------|---------|---------|------|
| 总执行时间 | 360.92s | 272.45s | +32% |
| 策略执行时间 | 176.21s | 162.93s | +8% |
| 数据加载时间 | 45.3s | 4.2s | +978% |
| 内存占用 | 2.1 GB | 1.8 GB | +14% |

### B. 相关资源

- [NautilusTrader 文档](https://nautilustrader.io/)
- [Binance API 文档](https://binance-docs.github.io/apidocs/)
- [资金费率说明](https://www.binance.com/en/support/faq/funding-rates)

---

**最后更新**: 2026-03-04
**版本**: 1.0.0
