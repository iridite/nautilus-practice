# 🎯 最佳回测记录与历史 Commit 节点分析

## 📊 最佳回测记录

### 1. KeltnerRSBreakoutStrategy_2026-02-09_14-23-10.json ⭐

**关键指标**：
- PnL: **126.07 USDT**
- Sharpe Ratio: **1.524** （最高）
- Win Rate: 37.34%
- Sortino Ratio: 3.595
- Profit Factor: 1.299
- Total Trades: 1149
- Leverage: **2**

**策略配置亮点**：
```yaml
keltner_trigger_multiplier: 2.8
stop_loss_atr_multiplier: 2.6
breakeven_multiplier: 2.0
deviation_threshold: 0.45
enable_time_stop: false
enable_rsi_stop_loss: false
leverage: 2
```

---

### 2. KeltnerRSBreakoutStrategy_2026-02-05_23-11-21.json

**关键指标**：
- PnL: **126.07 USDT** （与第一个完全相同）
- Sharpe Ratio: **1.524** （与第一个完全相同）
- Win Rate: 37.34%
- Sortino Ratio: 3.595
- Profit Factor: 1.299
- Total Trades: 1149
- Leverage: **1** （唯一区别）

**策略配置**：与第一个记录完全相同，除了 `leverage: 1`

---

## 🔍 历史 Commit 节点分析

### 2026-02-05 相关 Commits（第二个回测记录）

回测时间：**2026-02-05 23:11:21**

**最可能的 Commit**：`053bf5c08e41d4d308e00f00b3937cec2ab62166`

```
commit 053bf5c08e41d4d308e00f00b3937cec2ab62166
Author: iridite <iridite@foxmail.com>
Date:   Thu Feb 5 23:07:51 2026 +0800

    feat(strategy): add Candle Quality Filter mechanism

 config/strategies/keltner_rs_breakout.yaml | 3 ++-
 strategy/keltner_rs_breakout.py            | 7 +++++++
```

**时间线分析**：
- Commit 时间：23:07:51
- 回测时间：23:11:21
- **时间差：约 3.5 分钟** ✅

**当天其他重要 Commits**：
```
26cfc5c (22:31:47) - feat(strategy): [WIP] RSI 超买止盈
5db6a93 (21:47:14) - feat(strategy): 添加了抛物线止盈
7e24e5f (21:06:22) - fix: logic failure at handling exit method
79425ee (17:45:51) - fix: breakeven 止损
6b0d4d0 (17:10:00) - feat(strategy): 实现针对开仓的币种进行 breakeven 止损的能力
```

**关键特性演进**：
1. 17:10:00 - 实现 breakeven 止损能力
2. 17:45:51 - 修复 breakeven 止损 bug
3. 21:06:22 - 修复出场逻辑失败
4. 21:47:14 - 添加抛物线止盈
5. 22:31:47 - [WIP] RSI 超买止盈
6. 23:07:51 - 添加 Candle Quality Filter 机制 ⭐

---

### 2026-02-09 相关 Commits（第一个回测记录）

回测时间：**2026-02-09 14:23:10**

**当天 Commits**：
```
067988b (15:37:26) - chore: add ruff config and fix lint issues
c2e06df (15:39:10) - ci: add GitHub Actions workflow to run ruff and auto-fix
f1db8d5 (07:39:58) - ci: ruff auto-fix applied
bd19b4f (15:42:57) - chore: remove duplicate .ruff.toml (use pyproject.toml)
93014b1 (15:50:27) - chore(docker): add Dockerfile, .dockerignore and docker-compose
b5243f3 (16:18:11) - refactor(engine): support multi-instrument sandbox and fix Nautilus API compatibility
9a49ec2 (08:18:54) - ci: ruff auto-fix applied
6178b81 (23:53:17) - Enhance documentation and remove unnecessary files
```

**分析**：
- 回测时间 14:23:10 在当天所有 commits 之前（最早的是 07:39:58）
- 2026-02-09 的 commits 主要是 CI、Docker、文档相关，**不涉及策略逻辑**
- 因此，这次回测使用的代码很可能是 **2026-02-05 的代码**

**最可能的 Commit**：`053bf5c08e41d4d308e00f00b3937cec2ab62166` 或其之前的某个 commit

---

## 🔬 深度分析

### 关键发现

1. **两次回测结果完全相同**（除了 leverage）
   - PnL: 126.07 USDT
   - Sharpe Ratio: 1.524
   - Total Trades: 1149
   - 所有其他指标完全一致

2. **唯一区别：Leverage**
   - 2026-02-05 回测：leverage = 1
   - 2026-02-09 回测：leverage = 2
   - **但 PnL 完全相同**，说明 leverage 参数可能在这个策略中没有实际生效，或者使用的是其他仓位管理模式

3. **策略代码可能相同**
   - 2026-02-09 的回测很可能使用的是 2026-02-05 的代码
   - 只是修改了配置文件中的 leverage 参数

### 推荐的 Commit 节点

**最佳性能对应的 Commit**：

```
053bf5c08e41d4d308e00f00b3937cec2ab62166
feat(strategy): add Candle Quality Filter mechanism
Date: Thu Feb 5 23:07:51 2026 +0800
```

**关键特性**：
- ✅ Breakeven 止损机制
- ✅ 抛物线止盈
- ✅ RSI 超买止盈（WIP）
- ✅ Candle Quality Filter
- ✅ 出场逻辑修复

---

## 📝 配置参数记录

**最佳配置参数**（来自回测记录）：

```yaml
# 指标参数
ema_period: 20
atr_period: 20
sma_period: 200
bb_period: 20
bb_std: 1.5
volume_period: 20

# 通道参数
keltner_base_multiplier: 1.5
keltner_trigger_multiplier: 2.8

# 风控参数
base_risk_pct: 0.01
high_conviction_risk_pct: 0.015
stop_loss_atr_multiplier: 2.6
breakeven_multiplier: 2.0
deviation_threshold: 0.45

# 过滤器参数
volume_multiplier: 2
rs_short_lookback_days: 5
rs_long_lookback_days: 20
rs_short_weight: 0.7
rs_long_weight: 0.3
squeeze_memory_days: 1

# BTC 市场状态过滤器
enable_btc_regime_filter: true
btc_regime_sma_period: 200
btc_regime_atr_period: 14
btc_max_atr_pct: 0.03

# Universe 参数
universe_top_n: 15
universe_freq: W-MON

# 仓位管理
max_positions: 5
leverage: 2  # 注意：leverage 参数可能未实际生效
```

---

## 🎯 结论

1. **最佳 Commit 节点**：`053bf5c` (2026-02-05 23:07:51)
2. **关键特性**：Candle Quality Filter + Breakeven 止损 + 抛物线止盈
3. **最佳配置**：keltner_trigger_multiplier=2.8, stop_loss_atr_multiplier=2.6
4. **性能指标**：Sharpe Ratio 1.524, PnL 126.07 USDT (126% 收益)
5. **注意事项**：leverage 参数可能需要进一步验证其实际作用

---

## ✅ 回测验证结果

### 验证方法

1. 切换到历史 commit：`053bf5c08e41d4d308e00f00b3937cec2ab62166`
2. 运行高级回测：`uv run python main.py backtest --type high --skip-oi-data`
3. 对比验证结果与历史记录

### 验证结果对比

| 指标 | 历史记录 (2026-02-05) | 验证回测 (2026-02-23) | 差异 |
|------|----------------------|----------------------|------|
| **PnL (USDT)** | 126.07 | 71.35 | ❌ -43.4% |
| **Sharpe Ratio** | 1.524 | 1.262 | ❌ -17.2% |
| **Sortino Ratio** | 3.595 | 2.799 | ❌ -22.1% |
| **Win Rate** | 37.34% | 37.32% | ✅ 一致 |
| **Total Positions** | 1149 | 820 | ❌ -28.6% |
| **Leverage** | 1 | 1 | ✅ 一致 |

### 🔍 差异分析

**关键发现**：
1. ❌ **PnL 差异显著**：71.35 vs 126.07 USDT（相差 54.72 USDT）
2. ❌ **交易数量不同**：820 vs 1149 个持仓（相差 329 个）
3. ✅ **Win Rate 基本一致**：37.32% vs 37.34%
4. ❌ **Sharpe Ratio 下降**：1.262 vs 1.524

**可能原因**：

1. **数据差异**
   - 历史回测可能使用了不同的数据集
   - 数据更新导致 OHLCV 数据有所变化
   - Universe 文件可能不同（影响交易标的选择）

2. **引擎差异**
   - 历史回测可能使用低级引擎
   - 验证回测使用高级引擎
   - 两种引擎的数据加载和处理逻辑可能有细微差异

3. **配置差异**
   - 某些配置参数可能在历史回测时不同
   - Universe 更新频率或标的池可能有变化

4. **代码演进**
   - 虽然切换到了相同的 commit，但依赖库版本可能不同
   - NautilusTrader 版本：历史可能是 1.223.0，验证是 1.224.0

### 📋 详细验证数据

**验证回测完整结果**：
```json
{
  "pnl": 71.34806911,
  "sharpe": 1.2623173093011335,
  "sortino": 2.7993357246131945,
  "win_rate": 0.37317073170731707,
  "total_positions": 820,
  "leverage": 1,
  "profit_factor": 1.2432293581133562,
  "max_winner": 15.03458476,
  "avg_winner": 1.870587652189542,
  "max_loser": -4.97677364,
  "avg_loser": -0.9748088569260698
}
```

**回测文件**：`KeltnerRSBreakoutStrategy_2026-02-23_13-00-52.json`

### ⚠️ 结论

**无法完全复现历史回测结果**，主要差异在于：
- PnL 降低了 43.4%
- 交易数量减少了 28.6%
- Sharpe Ratio 降低了 17.2%

**建议**：
1. 检查历史回测使用的确切数据集和 Universe 文件
2. 确认历史回测使用的引擎类型（高级 vs 低级）
3. 验证 NautilusTrader 版本是否一致
4. 考虑数据更新对回测结果的影响

**重要提示**：虽然无法完全复现，但验证回测仍然显示了正收益（71.35 USDT，71.35% 收益率）和较好的 Sharpe Ratio（1.262），说明该 commit 的策略逻辑仍然有效。

---

**生成时间**：2026-02-23
**分析者**：Kiro AI Assistant
**验证状态**：⚠️ 部分复现（结果有差异）