# Bug 分析：参数优化时所有测试产生 0 笔交易

## 问题现象
在进行 Keltner RS Breakout 策略参数优化时，无论如何调整参数（keltner_trigger_multiplier, deviation_threshold, enable_btc_regime_filter），所有回测都产生 0 笔交易。

## 调查过程

### 1. 初步假设（已排除）
- ❌ 参数过于保守（keltner_trigger_multiplier=2.6 太高）
- ❌ BTC regime filter 过于严格
- ❌ 多个过滤器组合导致通过率过低

### 2. 极端测试
使用极端激进的参数配置：
```yaml
keltner_trigger_multiplier: 1.5  # 从 2.6 降到 1.5
deviation_threshold: 0.25        # 从 0.42 降到 0.25
enable_btc_regime_filter: false  # 禁用 BTC filter
```
结果：仍然 0 笔交易

### 3. 日志分析
启用 DEBUG 日志后发现拦截统计（2024-02-10）：
- 89 个币种：`❌ Not in Universe`（正常，因为 universe_top_n=15）
- 7 个币种：`❌ RS not strong: None`（关键��题）

被 RS 拦截的币种包括：
- BTCUSDT
- ETHUSDT
- BNBUSDT
- AVAXUSDT
- DOGEUSDT
- ARBUSDT
- API3USDT

这些都是 Universe 中的活跃币种，但 RS 计算返回 `None`。

### 4. 根本原因定位

#### 问题 1：BTCUSDT 的 RS 为何是 None？
策略配置：
```yaml
btc_symbol: BTCUSDT
```

对于 BTCUSDT 策略实例：
- `self.instrument.id` = BTCUSDT-PERP.BINANCE
- `self.btc_instrument_id` = BTCUSDT-PERP.BINANCE（相同！）

在 `on_bar` 方法中（strategy/keltner_rs_breakout.py:571-579）：
```python
def on_bar(self, bar: Bar) -> None:
    if bar.bar_type.instrument_id == self.instrument.id:
        self._process_main_instrument_bar(bar)  # ✅ 执行这里
    elif bar.bar_type.instrument_id == self.btc_instrument_id:
        self._process_btc_bar(bar)              # ❌ 永远不会执行
        return
    else:
        return
```

**Bug：当主标的是 BTCUSDT 时，`elif` 分支永远不会执行，导致 `_process_btc_bar` 从未被调用，`rs_calculator.update_benchmark_price()` 从未更新，RS 计算返回 `None`。**

#### 问题 2：其他币种的 RS 为何也是 None？
需要进一步调查：
- 是否 BTC bar 没有正确广播给所有策略实例？
- 是否 RS 计算器的历史数据不足（需要 20 天）？
- 是否回测引擎的 bar 分发逻辑有问题？

## 影响范围
- **所有包含 BTCUSDT 的回测都会失败**（RS 为 None）
- **可能影响其他币种的 RS 计算**（如果 BTC bar 分发有问题）
- **导致参数优化完全无效**（0 笔交易无法评估参数效果）

## 解决方案（待实施）

### 方案 1：修复 on_bar 逻辑
```python
def on_bar(self, bar: Bar) -> None:
    # 先处理 BTC bar（如果是）
    if bar.bar_type.instrument_id == self.btc_instrument_id:
        self._process_btc_bar(bar)
        # 如果主标的不是 BTC，直接返回
        if bar.bar_type.instrument_id != self.instrument.id:
            return

    # 处理主标的 bar
    if bar.bar_type.instrument_id == self.instrument.id:
        self._process_main_instrument_bar(bar)
        # ... 后续逻辑
```

### 方案 2：特殊处理 BTCUSDT
```python
def on_bar(self, bar: Bar) -> None:
    is_main_instrument = bar.bar_type.instrument_id == self.instrument.id
    is_btc_instrument = bar.bar_type.instrument_id == self.btc_instrument_id

    if is_btc_instrument:
        self._process_btc_bar(bar)

    if is_main_instrument:
        self._process_main_instrument_bar(bar)
        # ... 后续逻辑
    elif not is_btc_instrument:
        return
```

### 方案 3：排除 BTCUSDT
在 Universe 或策略配置中排除 BTCUSDT，因为它作为 benchmark 不应该被交易。

## 下一步行动
1. ✅ 记录 bug 分析到文档
2. ⏳ 选择并实施修复方案
3. ⏳ 验证修复后的回测结果
4. ⏳ 重新运行参数优化
5. ⏳ 检查其他币种的 RS 计算是否正常

## 时间线
- 2026-02-25 23:42: 发现所有测试 0 笔交易
- 2026-02-25 23:50: 定位到 RS 为 None 的问题
- 2026-02-25 23:55: 找到 BTCUSDT on_bar 逻辑 bug
