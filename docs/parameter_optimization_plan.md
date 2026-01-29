# OI Divergence 策略参数调优方案

## 一、瓶颈分析

### 1.1 OI背离参数瓶颈

**当前配置**：
- `oi_lookback: 12` (12小时)
- `oi_decline_threshold: 0.05` (5%)

**统计分析**：
- 12小时内OI下降5%的概率：根据2026-01数据，最大跌幅仅-3.49%
- **结论**：该组合过于严苛，在正常市场环境下几乎不可能触发

**建议**：
- 短期优化：降至 `oi_decline_threshold: 0.02` (2%)
- 长期方案：使用滚动标准差的倍数（如 `-1.5σ`）替代固定阈值

### 1.2 资金费率瓶颈

**当前配置**：
- `funding_rate_threshold_annual: 30.0` (±30%)

**统计分析**：
- 2026-01数据范围：-22.72% 至 +10.95%
- **结论**：30%阈值仅在极端市场（如Luna崩盘）才会触发

**动态方案**：
```python
# 基于历史百分位数的动态阈值
funding_threshold = np.percentile(abs(funding_history), 80)  # 取80分位数
```

### 1.3 多重过滤器叠加效应

当前策略要求**同时满足**4个条件：
1. 突破支撑/阻力
2. OI背离 < -5%
3. 资金费率 > ±30%
4. 回撤进入

**概率计算**：
假设每个条件独立，触发概率 = P1 × P2 × P3 × P4
- 如果P2=0.01, P3=0.02，则总概率 < 0.0002 (万分之二)

---

## 二、参数测试表

| 参数名 | 当前值 | 建议测试范围 | 测试步长 | 测试目的 |
|--------|--------|--------------|----------|----------|
| `oi_decline_threshold` | 0.05 | 0.01 ~ 0.05 | 0.01 | 找到信号频率与质量的平衡点 |
| `oi_lookback` | 12 | 6, 12, 24, 48 | 倍数 | 评估时间窗口对背离检测的影响 |
| `funding_rate_threshold_annual` | 30.0 | 10, 15, 20, 25, 30 | 5 | 确定资金费率过滤的最优阈值 |
| `lookback_bars` | 48 | 24, 48, 96, 168 | 倍数 | 测试支撑/阻力计算周期 |
| `atr_stop_multiplier` | 2.0 | 1.5, 2.0, 2.5, 3.0 | 0.5 | 优化止损距离 |
| `breakout_reentry_pct` | 0.002 | 0.001, 0.002, 0.005 | - | 评估回撤进入的敏感度 |
| `use_funding_filter` | true | true, false | - | 量化资金费率过滤的价值 |

---

## 三、梯度测试设计

### 3.1 核心参数Grid Search

```python
param_grid = {
    'oi_decline_threshold': [0.01, 0.02, 0.03, 0.04, 0.05],
    'oi_lookback': [6, 12, 24],
    'funding_rate_threshold_annual': [10.0, 15.0, 20.0, 25.0, 30.0],
    'lookback_bars': [24, 48, 96],
    'atr_stop_multiplier': [1.5, 2.0, 2.5, 3.0]
}

# 总组合数：5 × 3 × 5 × 3 × 4 = 900 组
```

### 3.2 分阶段测试策略

**阶段1：单参数敏感性分析**（优先级最高）
- 固定其他参数，仅变动 `oi_decline_threshold`
- 目标：找到信号触发的临界点

**阶段2：双参数交互分析**
- 测试 `(oi_decline_threshold, funding_rate_threshold_annual)` 组合
- 目标：识别参数间的协同效应

**阶段3：全局优化**
- 使用贝叶斯优化或遗传算法
- 目标：在900组中找到Sharpe最优解

---

## 四、过滤器压力测试代码

### 4.1 顺序关闭过滤器

```python
# 在 strategy/oi_divergence_strategy.py 中添加测试模式

class OIDivergenceStrategyConfig(BaseStrategyConfig):
    # 新增：过滤器开关（用于压力测试）
    test_mode_disable_filters: list = []  # 例如：["funding", "oi", "reentry"]

# 在 _detect_short_signal 中修改：

def _detect_short_signal(self, bar, current_price, current_high):
    # ... 原有代码 ...
    
    # Condition 2: OI 背离
    if "oi" not in self.config.test_mode_disable_filters:
        oi_divergence = self._calculate_oi_divergence()
        if oi_divergence >= -self.config.oi_decline_threshold:
            self.log.info(f"[FILTERED] OI: {oi_divergence:.2%}")
            return False, details
    
    # Condition 3: 资金费率
    if "funding" not in self.config.test_mode_disable_filters:
        if self.current_funding_rate_annual <= self.config.funding_rate_threshold_annual:
            self.log.info(f"[FILTERED] Funding: {self.current_funding_rate_annual:.2f}%")
            return False, details
    
    # Condition 4: 回撤进入
    if "reentry" not in self.config.test_mode_disable_filters:
        if current_price >= reentry_threshold:
            return False, details
    
    return True, details
```

### 4.2 压力测试配置

```yaml
# config/yaml/strategies/oi_divergence_test.yaml

# 测试1：关闭资金费率过滤
test_mode_disable_filters: ["funding"]

# 测试2：关闭OI过滤
test_mode_disable_filters: ["oi"]

# 测试3：仅保留突破检测
test_mode_disable_filters: ["funding", "oi", "reentry"]
```

---

## 五、自动化参数优化代码

### 5.1 NautilusTrader参数扫描框架

```python
# scripts/optimize_parameters.py

import itertools
import pandas as pd
from pathlib import Path
from typing import Dict, List
from nautilus_trader.backtest.engine import BacktestEngine
from config.settings import build_backtest_config

def run_parameter_sweep(
    param_grid: Dict[str, List],
    base_config_path: str = "config/yaml/strategies/oi_divergence.yaml"
) -> pd.DataFrame:
    """
    执行参数网格搜索
    
    Returns:
        DataFrame with columns: [params, sharpe, total_trades, win_rate, expectancy]
    """
    results = []
    
    # 生成所有参数组合
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(itertools.product(*param_values))
    
    print(f"Total combinations to test: {len(combinations)}")
    
    for i, combo in enumerate(combinations):
        params = dict(zip(param_names, combo))
        
        print(f"\n[{i+1}/{len(combinations)}] Testing: {params}")
        
        # 动态修改配置
        config = build_backtest_config()
        for key, value in params.items():
            setattr(config.strategy.params, key, value)
        
        # 运行回测
        try:
            engine = BacktestEngine(config=config)
            engine.run()
            
            # 提取指标
            report = engine.trader.generate_account_report()
            
            results.append({
                **params,
                'sharpe_ratio': report.sharpe_ratio or 0,
                'total_trades': report.total_orders,
                'win_rate': report.win_rate or 0,
                'expectancy': report.expectancy or 0,
                'total_pnl': report.total_pnl or 0
            })
            
        except Exception as e:
            print(f"Error: {e}")
            results.append({**params, 'sharpe_ratio': -999, 'error': str(e)})
    
    df = pd.DataFrame(results)
    df.to_csv('output/parameter_optimization_results.csv', index=False)
    
    return df


def analyze_robustness(df: pd.DataFrame, param_name: str):
    """
    分析参数鲁棒性（平原 vs 孤岛）
    
    平原特征：参数变化时Sharpe变化小
    孤岛特征：参数微调导致Sharpe剧烈波动
    """
    grouped = df.groupby(param_name)['sharpe_ratio'].agg(['mean', 'std'])
    
    # 计算稳定性指标
    grouped['stability'] = grouped['mean'] / (grouped['std'] + 1e-6)
    
    print(f"\n=== {param_name} 鲁棒性分析 ===")
    print(grouped.sort_values('stability', ascending=False))
    
    return grouped


# 使用示例
if __name__ == "__main__":
    # 阶段1：单参数敏感性测试
    param_grid_stage1 = {
        'oi_decline_threshold': [0.01, 0.02, 0.03, 0.04, 0.05],
        'oi_lookback': [12],  # 固定
        'funding_rate_threshold_annual': [30.0],  # 固定
        'lookback_bars': [48],  # 固定
        'atr_stop_multiplier': [2.0]  # 固定
    }
    
    df = run_parameter_sweep(param_grid_stage1)
    
    # 分析鲁棒性
    analyze_robustness(df, 'oi_decline_threshold')
    
    # 找出最优参数
    best = df.loc[df['sharpe_ratio'].idxmax()]
    print(f"\n最优参数组合：\n{best}")
```

### 5.2 并行化优化（可选）

```python
from concurrent.futures import ProcessPoolExecutor

def run_single_backtest(params: dict) -> dict:
    """单次回测（用于并行执行）"""
    # ... 回测逻辑 ...
    return result

# 并行执行
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(run_single_backtest, param_combinations))
```

---

## 六、鲁棒性评价标准

### 6.1 判断标准

**过拟合孤岛特征**：
- Sharpe在某个参数值达到峰值（如3.5），但±10%变化后骤降至<1.0
- 交易次数极少（<10次）
- 参数曲线呈现"尖峰"形态

**稳健平原特征**：
- Sharpe在一定参数范围内保持稳定（如2.0±0.3）
- 交易次数适中（30-100次）
- 参数曲线呈现"平台"形态

### 6.2 量化指标

```python
def calculate_robustness_score(df: pd.DataFrame, param_name: str) -> float:
    """
    计算参数鲁棒性得分（0-100）
    
    得分越高 = 越稳健
    """
    grouped = df.groupby(param_name)['sharpe_ratio']
    
    # 指标1：Sharpe均值
    mean_sharpe = grouped.mean().mean()
    
    # 指标2：Sharpe标准差（越小越好）
    std_sharpe = grouped.std().mean()
    
    # 指标3：交易频率稳定性
    trade_stability = df.groupby(param_name)['total_trades'].std().mean()
    
    # 综合得分
    score = (mean_sharpe * 30) - (std_sharpe * 20) - (trade_stability * 0.1)
    
    return max(0, min(100, score * 10))
```

---

## 七、立即行动建议

### 优先级1：快速验证（1小时内）

```yaml
# config/yaml/strategies/oi_divergence_quick_test.yaml
parameters:
  oi_decline_threshold: 0.02        # 5% → 2%
  funding_rate_threshold_annual: 15.0  # 30% → 15%
  use_funding_filter: false         # 临时关闭
```

运行：
```bash
uv run main.py backtest --type high
```

**预期结果**：应该能看到信号触发

### 优先级2：系统化测试（1天）

```bash
# 运行参数优化脚本
uv run python scripts/optimize_parameters.py

# 分析结果
uv run python scripts/analyze_optimization_results.py
```

### 优先级3：生产部署（1周）

- 选择鲁棒性得分>80的参数组合
- 在多个币种上验证
- 进行walk-forward测试

---

## 八、关键发现总结

1. **当前参数过于保守**：5% OI阈值 + 30%资金费率 = 信号消失
2. **建议立即调整**：
   - `oi_decline_threshold: 0.02`
   - `funding_rate_threshold_annual: 15.0`
3. **长期优化方向**：
   - 使用动态阈值（百分位数/标准差）
   - 实现过滤器"OR"逻辑而非"AND"
   - 添加市场状态自适应机制
