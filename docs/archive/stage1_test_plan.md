# 阶段 1 测试方案

**生成时间**: 2026-02-25
**设计者**: optimizer
**基于**: analyst 参数建议

## 一、测试参数

### 参数组合（9 组）

| 组合 | keltner_trigger_multiplier | deviation_threshold |
|------|---------------------------|---------------------|
| 1    | 2.2                       | 0.35                |
| 2    | 2.2                       | 0.38                |
| 3    | 2.2                       | 0.42                |
| 4    | 2.4                       | 0.35                |
| 5    | 2.4                       | 0.38                |
| 6    | 2.4                       | 0.42                |
| 7    | 2.6                       | 0.35                |
| 8    | 2.6                       | 0.38                |
| 9    | 2.6                       | 0.42                |

### 其他参数（保持基线值）

- stop_loss_atr_multiplier: 2.6
- base_risk_pct: 0.01
- high_conviction_risk_pct: 0.015
- volume_multiplier: 2.0
- breakeven_multiplier: 2.0
- 其他参数保持配置文件默认值

## 二、执行方式

### 脚本位置
`/home/yixian/Projects/nautilus-practice/scripts/optimize_keltner_stage1.py`

### 运行命令

**串行执行（推荐，避免资源竞争）**:
```bash
uv run python scripts/optimize_keltner_stage1.py
```

**并行执行（3 进程，速度快 3 倍）**:
```bash
uv run python scripts/optimize_keltner_stage1.py --parallel --workers 3
```

## 三、时间预估

### 单次回测耗时
- 数据加载: ~10s
- 策略执行: ~100s
- 结果保存: ~10s
- **总计**: ~120s (2 分钟)

### 总耗时

| 执行方式 | 测试数量 | 单次耗时 | 总耗时 |
|---------|---------|---------|--------|
| 串行    | 9 组    | 2 分钟  | 18 分钟 |
| 并行 (3进程) | 9 组 | 2 分钟 | 6 分钟 |

## 四、输出结果

### 1. CSV 结果文件
**路径**: `output/optimization/stage1_results_YYYYMMDD_HHMMSS.csv`

**包含字段**:
- test_id: 测试编号
- keltner_trigger_multiplier: 参数值
- deviation_threshold: 参数值
- sharpe_ratio: Sharpe Ratio
- sortino_ratio: Sortino Ratio
- total_trades: 交易次数
- win_rate: 胜率
- expectancy: 期望值
- profit_factor: 盈利因子
- total_pnl: 总盈亏 (USDT)
- total_pnl_pct: 总盈亏百分比
- avg_winner: 平均盈利
- avg_loser: 平均亏损
- profit_loss_ratio: 盈亏比
- elapsed_time: 回测耗时
- status: 状态 (success/failed/timeout/error)

### 2. 最优参数 JSON
**路径**: `output/optimization/stage1_best_parameters.json`

**格式**:
```json
{
  "stage": 1,
  "timestamp": "2026-02-25T...",
  "parameters": {
    "keltner_trigger_multiplier": 2.4,
    "deviation_threshold": 0.38
  },
  "metrics": {
    "sharpe_ratio": 0.85,
    "total_trades": 120,
    "win_rate": 0.43,
    "profit_loss_ratio": 1.75,
    ...
  },
  "baseline_comparison": {
    "sharpe_improvement": "+26.9%",
    "trades_change": "+118.2%",
    "win_rate_change": "+2.0pp"
  }
}
```

### 3. 控制台输出

**实时进度**:
```
[1/9] 测试参数: {'keltner_trigger_multiplier': 2.2, 'deviation_threshold': 0.35}
✅ [1/9] 完成 - Sharpe: 0.752, Trades: 98, Win Rate: 42.50%

[2/9] 测试参数: {'keltner_trigger_multiplier': 2.2, 'deviation_threshold': 0.38}
✅ [2/9] 完成 - Sharpe: 0.801, Trades: 105, Win Rate: 43.20%
...
```

**最终分析**:
- Top 5 参数组合排名
- 最优参数 vs 基线对比
- 参数敏感度分析

## 五、成功标准

### 最低要求
- 至少 7/9 组测试成功（77%）
- 最优 Sharpe Ratio > 0.75 (+12% vs 基线 0.67)
- 交易次数 > 80 笔/年 (+45% vs 基线 55)

### 理想目标
- 9/9 组测试全部成功
- 最优 Sharpe Ratio > 0.85 (+27%)
- 交易次数 > 100 笔/年 (+82%)
- 胜率 > 43% (+2pp)

## 六、故障排查

### 常见问题

**1. 回测超时（timeout）**
- 原因: 数据量过大或系统资源不足
- 解决: 增加 timeout 时间（脚本中修改 `timeout=300` 为更大值）

**2. 配置文件错误**
- 原因: YAML 格式错误或参数名不匹配
- 解决: 检查 `config/strategies/keltner_rs_breakout.yaml` 格式

**3. 结果文件未找到**
- 原因: 回测未生成结果文件
- 解决: 检查 `output/backtest/result/` 目录权限

**4. 并行执行冲突**
- 原因: 多个进程同时写入同一文件
- 解决: 使用串行执行或增加文件锁机制

## 七、下一步行动

### 阶段 1 完成后
1. **分析结果**: 查看 Top 5 参数组合
2. **验证鲁棒性**: 检查参数敏感度
3. **决策**:
   - 如果改善显著（Sharpe +20%）→ 进入阶段 2
   - 如果改善一般（Sharpe +10%）→ 调整参数范围重测
   - 如果无改善 → 重新评估优化策略

### 阶段 2 准备
- 基于阶段 1 最优参数
- 加入 RSI、相对强度、止损参数
- 5×3×3 网格（45 组测试）

---

**文档版本**: v1.0
**最后更新**: 2026-02-25
