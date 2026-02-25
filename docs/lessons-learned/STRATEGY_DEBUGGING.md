# 策略调试与诊断经验

本文档记录策略调试、零交易诊断和过滤器优化的经验。

## 1. 零交易诊断系统 (2026-02-21)

### 问题

Keltner RS Breakout 策略回测产生 0 交易，需要系统化的诊断方法。

### 根本原因

**非代码错误，而是过滤器设计问题**:
- Universe 动态选择（每周只选 15 个币种）
- 8 个严格过滤器串联
- 多个独立过滤器的组合概率是乘法关系
- 结果：100% 信号被拦截

### 诊断结果

**主要拦截器**:
- Not in Universe: 87-96% (动态 Universe 覆盖率低)
- BTC Regime: 3-13% (BTC 市场状态过滤)
- 两者合计：100% 拦截

### 解决方案

#### 1. 过滤器统计系统

在策略中添加 `filter_stats` 字典跟踪每个过滤器：

```python
def __init__(self):
    self.filter_stats = {
        "total_bars": 0,
        "not_in_universe": 0,
        "btc_regime": 0,
        "price_below_sma": 0,
        "rs_weak": 0,
        "volume_low": 0,
        "keltner_no_breakout": 0,
        "wick_ratio": 0,
        "passed_all": 0,
    }
```

#### 2. 详细 Debug 日志

为每个过滤器添加详细日志，显示拦截原因和数值：

```python
if not self._is_symbol_active():
    self.filter_stats["not_in_universe"] += 1
    self.log.debug(f"[{symbol}] ❌ Not in Universe")
    return False

if not self.rs_calculator.is_strong(threshold=RS_THRESHOLD):
    self.filter_stats["rs_weak"] += 1
    rs_value = self.rs_calculator.calculate_rs()
    self.log.debug(f"[{symbol}] ❌ RS not strong: {rs_value}")
    return False
```

#### 3. 自动警告系统

在 `on_stop()` 中输出统计报告，使用 ERROR 级别确保始终显示：

```python
def _log_filter_statistics(self):
    total = self.filter_stats["total_bars"]
    if total == 0:
        return

    self.log.info(f"\n{'='*60}")
    self.log.info("Filter Statistics Summary")
    self.log.info(f"{'='*60}")

    for key, count in self.filter_stats.items():
        if key == "total_bars":
            continue
        pct = (count / total) * 100
        self.log.info(f"  {key:20s}: {count:6d} ({pct:5.1f}%)")

    # 检测 100% 拦截
    if self.filter_stats["passed_all"] == 0:
        blockers = [(k, v) for k, v in self.filter_stats.items()
                    if k not in ("total_bars", "passed_all") and v > 0]
        blockers.sort(key=lambda x: x[1], reverse=True)

        main_blockers = [f"{k} ({v/total*100:.1f}%)"
                        for k, v in blockers if v/total > 0.1]

        self.log.error(
            f"\n⚠️  [{self.instrument.id.symbol.value}] "
            f"100% of signals blocked by filters - no trades generated\n"
            f"   Main blockers: {', '.join(main_blockers)}\n"
            f"   Consider: adjusting filter thresholds or increasing universe_top_n"
        )
```

### 调整建议

基于诊断结果的优化方向：

1. **增加 Universe 覆盖率**
   - `universe_top_n: 15 → 30`
   - `universe_rebalance_freq: "W-MON" → "2D"` 或 `"D"`

2. **放宽 BTC Regime 过滤器**
   - `btc_max_atr_pct: 0.03 → 0.05`
   - 或暂时禁用测试：`enable_btc_regime_filter: false`

3. **调整其他过滤器阈值**
   - RS threshold: 降低相对强度要求
   - Volume surge: 降低成交量倍数要求
   - Keltner multiplier: 调整突破阈值

### 关键经验

1. **过滤器组合效应**
   - 多个独立过滤器的通过概率是乘法关系
   - 8 个过滤器，每个 90% 通过率 → 总通过率 43%
   - 需要量化每个过滤器的影响

2. **Universe 动态选择的陷阱**
   - 每周只选 15 个币种 → 87-96% 信号被拦截
   - 需要平衡 Universe 大小和选择频率

3. **诊断系统的重要性**
   - 详细日志 + 统计 + 自动警告
   - 快速定位问题，避免盲目调参

4. **日志配置的影响**
   - `components_only: true` 会过滤策略实例日志
   - DEBUG 级别日志对诊断至关重要
   - ERROR 级别警告确保关键信���始终显示

## 2. NautilusTrader 多标的策略机制

### 关键发现

**每个策略实例只能交易一个标的**:
- `universe_top_n: 15` 会创建 15 个独立策略实例
- 每个实例有自己的 `instrument.id`
- Universe 过滤器检查当前实例的标的是否在 Universe 中

### 架构影响

```python
# 错误理解：一个策略实例交易 15 个标的
strategy = KeltnerRSBreakoutStrategy(universe_top_n=15)

# 实际情况：创建 15 个独立实例
for symbol in universe:
    strategy_instance = KeltnerRSBreakoutStrategy(
        instrument=symbol,
        universe_top_n=15
    )
```

### 设计建议

1. **Universe 大小要合理**
   - 太小：大部分信号被 "Not in Universe" 拦截
   - 太大：分散资金，单个仓位太小

2. **更新频率要匹配策略周期**
   - 日线策略：每日或每 2 天更新
   - 周线策略：每周更新

3. **过滤器要考虑 Universe 机制**
   - Universe 本身就是一个强过滤器
   - 其他过滤器应该更宽松

## 3. 数据周期匹配的重要性

### 问题

使用 1h 数据运行日线策略会将所有指标时间尺度压缩 24 倍。

### 示例

```yaml
# 策略配置
timeframe: "1d"
keltner_period: 20  # 20 天

# 如果使用 1h 数据
# 实际计算：20 小时 = 0.83 天（错误！）
```

### 解决方案

**严格匹配数据周期和策略配置**:
- 策略使用 `1d` → 数据必须是 `1d`
- 策略使用 `1h` → 数据必须是 `1h`

### 验证方法

在数据准备阶段检查：

```python
if strategy_config.timeframe != data_config.bar_type.spec().timedelta:
    raise ValueError(
        f"Strategy timeframe {strategy_config.timeframe} "
        f"does not match data timeframe {data_config.bar_type}"
    )
```

## 相关文件

- `strategy/keltner_rs_breakout.py` (过滤器统计系统)
- `config/strategies/keltner_rs_breakout.yaml` (策略配置)
- `config/environments/dev.yaml` (日志配置)
- `docs/lessons-learned/STRATEGY_DEBUGGING.md` (本文档)
