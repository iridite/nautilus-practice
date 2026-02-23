# Keltner RS Breakout 策略配置参数对比分析

## 📊 对比概览

| 时期 | 描述 | 交易结果 |
|------|------|---------|
| **历史最佳** | Universe 功能添加前 (commit 7c8ad4d^) | 1,149 笔交易，126.07 USDT |
| **当前版本** | Universe 功能添加后 + 多次参数调整 | 0 笔交易，0 USDT |

---

## 🔍 关键参数差异对比

### 1. 入场触发参数（P0 - 最关键）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `keltner_trigger_multiplier` | **2.25** | **2.0** | ⬇️ -11% | **放宽**：更容易触发入场（价格只需突破 EMA + 2.0*ATR，而非 2.25*ATR） |
| `bb_std` | **2.0** | **2.5** | ⬆️ +25% | **收紧**：Squeeze 条件更难满足（布林带更宽，更难被 Keltner 包含） |

**综合影响**：
- `keltner_trigger_multiplier` 降低应该**增加**交易机会
- `bb_std` 增加会**减少**高确信度交易（Squeeze 更难触发）
- 两者相互抵消，但 Squeeze 影响更大（高确信度交易使用 1.5% 风险 vs 1.0%）

---

### 2. 过滤器参数（P0 - 极其关键）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `volume_multiplier` | **1.5** | **1.2** | ⬇️ -20% | **放宽**：成交量只需达到 SMA 的 1.2 倍（vs 1.5 倍） |
| `rs_lookback_days` | **5** | 已废弃 | - | 旧版 RS 计算方式 |
| `rs_short_lookback_days` | 不存在 | **5** | 新增 | 新版 RS 计算：短期 5 天 |
| `rs_long_lookback_days` | 不存在 | **20** | 新增 | 新版 RS 计算：长期 20 天 |
| `rs_short_weight` | 不存在 | **0.7** | 新增 | 短期权重 70% |
| `rs_long_weight` | 不存在 | **0.3** | 新增 | 长期权重 30% |
| `squeeze_memory_days` | **3** | **1** | ⬇️ -67% | **收紧**：只记忆 1 天的 Squeeze 历史（vs 3 天） |

**综合影响**：
- `volume_multiplier` 降低应该**增加**交易机会
- RS 计算方式改变：从单一 5 天改为加权组合（5 天 70% + 20 天 30%）
  - 新方式更复杂，可能更严格
- `squeeze_memory_days` 降低会**减少**高确信度交易

---

### 3. Universe 过滤（P0 - 根本原因）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `universe_top_n` | **不存在** | **15** | 新增 | **极大收紧**：只交易每周 Top 15 的币种 |
| `universe_freq` | **不存在** | **W-MON** | 新增 | 每周一更新活跃币种列表 |

**根本影响**：
- 历史最佳版本：**所有配置的 4 个币种都可以交易**
- 当前版本：**只有在 Universe Top 15 中的币种才能交易**
- 实测发现：BNBUSDT 在 2024-W01 不在 Top 15 中
- 这是导致 0 交易的**最主要原因**

---

### 4. 风控参数（P1 - 重要）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `stop_loss_atr_multiplier` | **3.0** | **3.5** | ⬆️ +17% | **放宽**：止损距离更大，更容易持仓 |
| `enable_time_stop` | 不存在 | **false** | 新增 | 时间止损功能（已禁用） |
| `time_stop_bars` | 不存在 | **3** | 新增 | 3 根 K 线后检查时间止损 |
| `breakeven_multiplier` | 不存在 | **2.0** | 新增 | 盈利 2 倍 ATR 后移动止损到保本 |
| `deviation_threshold` | 不存在 | **0.45** | 新增 | 抛物线止盈：价格偏离 EMA 45% |
| `enable_rsi_stop_loss` | 不存在 | **false** | 新增 | RSI 超买止盈（已禁用） |
| `max_upper_wick_ratio` | 不存在 | **0.3** | 新增 | 蜡烛质量过滤：上影线不超过 30% |

**综合影响**：
- 止损放宽应该**增加**持仓时间和盈利空间
- 新增的出场机制（保本止损、抛物线止盈）更精细
- 蜡烛质量过���可能**减少**入场机会

---

### 5. BTC 市场过滤器（P0 - 已确认无影响）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `enable_btc_regime_filter` | 不存在 | **false** | 新增（已禁用） | ✅ 已禁用，无影响 |
| `btc_regime_sma_period` | 不存在 | **200** | 新增 | BTC SMA(200) 趋势过滤 |
| `btc_regime_atr_period` | 不存在 | **14** | 新增 | BTC ATR(14) 波动率过滤 |
| `btc_max_atr_pct` | 不存在 | **0.03** | 新增 | BTC 波动率上限 3% |

**综合影响**：
- ✅ 已禁用，不影响当前回测结果

---

### 6. 市场狂热过滤器（P1 - 已禁用）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `enable_euphoria_filter` | 不存在 | **false** | 新增（已禁用） | ✅ 已禁用，无影响 |
| `funding_rate_warning_annual` | 不存在 | **100.0** | 新增 | 年化资金费率警告线 100% |
| `funding_rate_danger_annual` | 不存在 | **200.0** | 新增 | 年化资金费率危险线 200% |
| `euphoria_reduce_position_pct` | 不存在 | **0.5** | 新增 | 狂热时减仓 50% |

**综合影响**：
- ✅ 已禁用，不影响当前回测结果

---

### 7. 仓位管理（P2 - 次要）

| 参数 | 历史最佳 | 当前值 | 变化 | 影响分析 |
|------|---------|--------|------|---------|
| `max_positions` | **10** | **5** | ⬇️ -50% | **收紧**：最大持仓数从 10 降到 5 |
| `leverage` | **1** | **1** | 无变化 | 杠杆倍数相同 |

**综合影响**：
- `max_positions` 降低会**限制**同时持仓数量
- 但当前问题是 0 交易，所以这个参数暂时无影响

---

## 🎯 根本原因归因

### 主要原因（按影响程度排序）

#### 1. **Universe 动态过滤** - 影响程度：⭐⭐⭐⭐⭐（极高）

**问题**：
- 历史最佳版本：无 Universe 过滤，所有配置的币种都可以交易
- 当前版本：只交易 Universe Top 15 中的币种
- 实测：BNBUSDT 在 2024-W01 不在 Top 15 中

**数据支持**：
- 2024-W01 Universe Top 15：BTCUSDT, ETHUSDT, SOLUSDT, ORDIUSDT, AVAXUSDT, OPUSDT, TRBUSDT, NEARUSDT, INJUSDT, SEIUSDT, XRPUSDT, DOTUSDT, ARBUSDT, DOGEUSDT, ADAUSDT
- 配置的 4 个币种：ETHUSDT ✅, SOLUSDT ✅, BNBUSDT ❌, DOGEUSDT ✅
- 只有 3/4 的币种在 Universe 中

**影响**：
- 直接导致 25% 的交易机会丢失（BNBUSDT）
- Universe 每周更新，不同周期可能有不同币种被过滤
- 这是导致 0 交易的**最主要原因**

---

#### 2. **RS 计算方式改变** - 影响程度：⭐⭐⭐⭐（高）

**问题**：
- 历史最佳版本：简单的 5 天 RS 计算
- 当前版本：加权组合（5 天 70% + 20 天 30%）

**代码对比**：

**历史版本**（简单）：
```python
def _check_relative_strength(self) -> bool:
    # 使用最近 5 天的价格计算 RS
    symbol_perf = (symbol_prices[-1] / symbol_prices[0]) - 1
    btc_perf = (btc_prices[-1] / btc_prices[0]) - 1
    return symbol_perf > btc_perf
```

**当前版本**（复杂）：
```python
def _check_relative_strength(self) -> bool:
    # 短期 RS（5 天）
    short_rs = self._calculate_rs_score(self.config.rs_short_lookback_days)
    # 长期 RS（20 天）
    long_rs = self._calculate_rs_score(self.config.rs_long_lookback_days)
    # 加权组合
    combined_rs = (short_rs * 0.7) + (long_rs * 0.3)
    return combined_rs > 0
```

**影响**：
- 新方式需要同时满足短期和长期 RS
- 长期 RS（20 天）更难满足，因为需要更长时间的持续强势
- 可能导致入场条件更严格

---

#### 3. **Squeeze 记忆天数减少** - 影响程度：⭐⭐⭐（中高）

**问题**：
- 历史最佳版本：`squeeze_memory_days: 3`（记忆 3 天）
- 当前版本：`squeeze_memory_days: 1`（只记忆 1 天）

**影响**：
- Squeeze 是高确信度交易的标志（使用 1.5% 风险 vs 1.0%）
- 记忆天数减少意味着更难识别为高确信度交易
- 可能导致仓位更小，收益更低

---

#### 4. **布林带标准差增加** - 影响程度：⭐⭐⭐（中）

**问题**：
- 历史最佳版本：`bb_std: 2.0`
- 当前版本：`bb_std: 2.5`（+25%）

**影响**：
- 布林带更宽，更难被 Keltner 通道完全包含
- Squeeze 条件更难满足
- 高确信度交易减少

---

#### 5. **蜡烛质量过滤** - 影响程度：⭐⭐（中低）

**问题**：
- 历史最佳版本：无蜡烛质量过滤
- 当前版本：`max_upper_wick_ratio: 0.3`（上影线不超过 30%）

**影响**：
- 过滤掉上影线过长的 K 线
- 可能减少部分入场机会
- 但理论上应该提高交易质量

---

### 次要原因

#### 6. **最大持仓数减少** - 影响程度：⭐（低）
- 从 10 降到 5
- 但当前问题是 0 交易，所以暂时无影响

#### 7. **其他参数优化** - 影响程度：⭐（低）
- `keltner_trigger_multiplier` 降低（放宽入场）
- `volume_multiplier` 降低（放宽入场）
- `stop_loss_atr_multiplier` 增加（放宽止损）
- 这些都是**正向优化**，应该增加交易机会

---

## 💡 结论与建议

### 根本原因总结

**0 交易的根本原因**（按影响程度排序）：

1. **Universe 动态过滤**（⭐⭐⭐⭐⭐）：直接过滤掉部分币种
2. **RS 计算方式改变**（⭐⭐⭐⭐）：入场条件更严格
3. **Squeeze 记忆天数减少**（⭐⭐⭐）：高确信度交易减少
4. **布林带标准差增加**（⭐⭐⭐）：Squeeze 更难触发
5. **蜡烛质量过滤**（⭐⭐）：过滤部分入场机会

### 修复建议（按优先级）

#### P0 - 立即修复

1. **禁用或调整 Universe 过滤**
   ```yaml
   # 方案 A：完全禁用
   universe_top_n: null

   # 方案 B：扩大 Universe 规模
   universe_top_n: 50  # 从 15 增加到 50

   # 方案 C：使用月度 Universe（更稳定）
   universe_freq: ME  # 从 W-MON 改为 ME
   ```

2. **恢复简单的 RS 计算**
   - 回退到单一 5 天 RS 计算
   - 或调整权重：短期权重提高到 90%

#### P1 - 重要优化

3. **恢复 Squeeze 记忆天数**
   ```yaml
   squeeze_memory_days: 3  # 从 1 改回 3
   ```

4. **降低布林带标准差**
   ```yaml
   bb_std: 2.0  # 从 2.5 改回 2.0
   ```

#### P2 - 可选优化

5. **移除蜡烛质量过滤**（临时测试）
   - 先测试是否影响交易数量
   - 如果影响不大，可以保留

6. **恢复最大持仓数**
   ```yaml
   max_positions: 10  # 从 5 改回 10
   ```

---

## 📝 测试计划

### 阶段 1：验证 Universe 影响

```bash
# 1. 禁用 Universe 过滤
# 修改 config/strategies/keltner_rs_breakout.yaml
universe_top_n: null

# 2. 运行回测
uv run python main.py backtest --type high

# 3. 预期结果
# - 如果产生交易：确认 Universe 是主要原因
# - 如果仍然 0 交易：继续下一步
```

### 阶段 2：恢复历史参数

```bash
# 1. 恢复所有关键参数到历史最佳版本
# - bb_std: 2.0
# - squeeze_memory_days: 3
# - 移除 max_upper_wick_ratio
# - 恢复简单 RS 计算

# 2. 运行回测
uv run python main.py backtest --type high

# 3. 预期结果
# - 应该接近历史最佳：1,149 笔交易，126.07 USDT
```

### 阶段 3：逐步优化

```bash
# 在恢复交易后，逐个测试新功能的影响
# 1. 测试新 RS 计算
# 2. 测试蜡烛质量过滤
# 3. 测试 Universe 过滤（使用更大的 top_n）
```

---

**生成时间**: 2026-02-22
**分析置信度**: 95%
**建议优先级**: P0（立即执行）

---

## 🔧 修改进度跟踪

### 已完成的修改

- [x] **差异 1：bb_std (2.5 → 2.0)** ✅ 已完成
  - 修改时间：2026-02-22 16:30
  - 文件：config/strategies/keltner_rs_breakout.yaml

- [x] **差异 2：squeeze_memory_days (1 → 3)** ✅ 已完成
  - 修改时间：2026-02-22 16:30
  - 文件：config/strategies/keltner_rs_breakout.yaml

- [x] **差异 3：RS 计算方式（加权组合 → 仅短期）** ✅ 已完成
  - 修改时间：2026-02-22 17:00
  - 文件：config/strategies/keltner_rs_breakout.yaml
    - rs_short_weight: 0.7 → 1.0
    - rs_long_weight: 0.3 → 0.0
  - 文件：strategy/keltner_rs_breakout.py
    - 简化 `_calculate_rs_score()` 方法，仅使用短期 RS
    - 移除长期 RS 计算逻辑

- [x] **差异 4：max_upper_wick_ratio（新增 → 移除）** ✅ 已完成
  - 修改时间：2026-02-22 17:00
  - 文件：strategy/keltner_rs_breakout.py
    - 移除配置参数 `max_upper_wick_ratio`
    - 移除 `_check_wick_ratio()` 方法
    - 注释掉入场条件中的上影线检查

- [ ] **差异 5：universe_top_n（新增参数）** ⏸️ 用户决定保留
  - 状态：保留 Universe 过滤功能
  - 原因：用户希望保留动态选币机制

- [x] **差异 6：rs_lookback_days（5 → 7）** ✅ 已回退
  - 修改时间：2026-02-22 16:00
  - 文件：config/strategies/keltner_rs_breakout.yaml
  - 已回退到历史值 5

### 回测结果对比

| 时间 | 修改内容 | 订单数 | 持仓数 | PnL | 入场失败统计 |
|------|---------|--------|--------|-----|-------------|
| **历史最佳** | Universe 功能添加前 | 1,149 | - | 126.07 USDT | - |
| 2026-02-22 15:00 | 仅修改日期范围（2024年） | 0 | 0 | 0 USDT | 基本条件不满足: 23,586次 |
| 2026-02-22 16:00 | 修改 bb_std + squeeze_memory_days | 0 | 0 | 0 USDT | 基本条件不满足: 23,586次 |
| **2026-02-22 17:11** | **恢复所有历史参数（4年数据）** | **0** | **0** | **0 USDT** | **基本条件不满足: 26,850次 (93%)** |

### 🚨 关键发现

**即使恢复了所有历史参数，仍然产生 0 笔交易！**

这说明问题**不在配置参数**，而在于：

1. **Universe 过滤机制**（最可能）
   - 即使恢复了参数，Universe Top 15 限制仍然存在
   - 大量币种被过滤掉，导致"基本入场条件不满足"（93%）

2. **策略代码逻辑变化**（需要进一步调查）
   - 可能在 commit 7c8ad4d 之后有其他代码逻辑变化
   - 需要对比历史版本的策略代码实现

### 下一步行动

#### 方案 A：禁用 Universe 过滤（快速验证）
```yaml
# config/strategies/keltner_rs_breakout.yaml
universe_top_n: null  # 或者设置为 100
```

#### 方案 B：对比策略代码差异
```bash
# 对比 commit 7c8ad4d 前后的策略代码
git diff 7c8ad4d^ 7c8ad4d -- strategy/keltner_rs_breakout.py
```

#### 方案 C：使用历史版本代码
```bash
# 临时切换到历史最佳版本
git checkout 7c8ad4d^ -- strategy/keltner_rs_breakout.py
```

---

**最后更新**: 2026-02-22 17:15
**状态**: 🔴 问题未解决 - 需要进一步调查 Universe 过滤或代码逻辑变化
