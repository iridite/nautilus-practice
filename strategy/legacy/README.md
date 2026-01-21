# Legacy Strategy Implementations

这个文件夹存放已被替换的旧版策略实现，保留作为参考和学习用途。

## 📚 文件说明

### `oi_divergence.py` (已废弃)

**状态**: ⚠️ Legacy - 已被 `oi_divergence_strategy.py` 替代

**原因**:
- 新版本 (`oi_divergence_strategy.py`) 已通过回测验证
- 新版本增加了风控增强功能（ATR动态止损、动态仓位、滑点监控）
- 新版本日志系统更完善，代码规范更好

**对比**:
| 维度 | 旧版 | 新版v3.0 |
|------|------|----------|
| 代码行数 | 599行 | 1249行 |
| ATR动态止损 | ❌ | ✅ |
| ATR动态仓位 | ❌ | ✅ |
| 滑点监控 | ❌ | ✅ |
| 信号强度计算 | ❌ | ✅ |
| 回测验证 | ❌ | ✅ |

**保留价值**:
- ✅ 代码更简洁（599行），便于理解核心逻辑
- ✅ 适合教学和快速原型验证
- ✅ 核心Alpha逻辑与新版完全一致

**使用建议**:
- 🚫 **不建议用于生产环境**
- ✅ 可用于学习OI背离策略的核心逻辑
- ✅ 可作为简化版参考实现

---

## 🔄 迁移到新版本

如果你的代码引用了旧版策略，请按以下步骤迁移：

### 1. 更新导入语句

```python
# 旧版 ❌
from strategy.oi_divergence import OIDivergence, OIDivergenceConfig

# 新版 ✅
from strategy.oi_divergence_strategy import OIDivergenceStrategy, OIDivergenceStrategyConfig
```

### 2. 更新配置参数

```python
# 旧版配置 ❌
config = OIDivergenceConfig(
    lookback_bars=48,
    stop_loss_pct=0.01,
)

# 新版配置 ✅
config = OIDivergenceStrategyConfig(
    lookback_bars=48,
    stop_loss_pct=0.01,  # 仅作为后备，建议启用ATR
    # 🔥 新增风控参数
    use_atr_stop=True,
    atr_period=14,
    atr_stop_multiplier=2.0,
    use_atr_position_sizing=True,
    max_position_risk_pct=0.1,
)
```

### 3. 更新策略实例化

```python
# 旧版 ❌
strategy = OIDivergence(config)

# 新版 ✅
strategy = OIDivergenceStrategy(config)
```

---

## 📖 相关文档

- 新版策略文档: `strategy/OI_DIVERGENCE_STRATEGY_README.md`
- 实现验证报告: `strategy/QUANTDEV_IMPLEMENTATION_REPORT.md`
- 研究报告: `docs/RESEARCH_ALPHA.md`
- 项目状态: `CURRENT_STATUS.md`

---

**最后更新**: 2026-01-21  
**维护状态**: 仅保留作为参考，不再更新
