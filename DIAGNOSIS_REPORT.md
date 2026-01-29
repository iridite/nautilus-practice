# 回测无交易信号诊断报告

## 核心问题

**Binance API限制：OI历史数据不可用**

测试结果显示：
- Binance `fapiDataGetOpenInterestHist` API只返回最近数据（2026-01-29）
- 无论是否使用`startTime`参数，都无法获取2025年9月的历史OI数据
- API错误：`{"msg":"parameter 'startTime' is invalid.","code":-1130}`

## 根本原因

1. **Binance API限制**：持仓量历史数据仅保留有限时间（约30天）
2. **回测期间过旧**：2025-09-01至2025-12-31的数据已超出API保留期
3. **策略强依赖OI**：OI背离是核心入场条件，无OI数据=无交易信号

## 解决方案

### 方案1：调整回测时间到近期（推荐）

```yaml
# config/yaml/active.yaml
backtest:
  start_date: "2026-01-01"  # 使用最近30天内的数据
  end_date: "2026-01-29"
```

**优点**：
- 可获取真实OI数据
- 验证策略完整逻辑
- 测试所有风控功能

**缺点**：
- 回测周期较短
- 样本量有限

### 方案2：使用OKX交易所数据

OKX可能保留更长的历史数据：

```python
# main.py:839
fetch_results = batch_fetch_oi_and_funding(
    symbols=[primary_symbol],
    start_date=get_start_date(),
    end_date=get_end_date(),
    exchange_id="okx",  # 改用OKX
    base_dir=BASE_DIR,
    oi_period="1h"
)
```

### 方案3：策略降级运行（不推荐）

修改策略使OI为可选：

```python
# strategy/oi_divergence_strategy.py:1050
def _is_ready(self) -> bool:
    oi_ready = True  # 临时禁用OI依赖检查
    return (
        len(self.bars_main) >= self.config.lookback_bars
        and self.vwap_sma.initialized
        and atr_ready
    )
```

**警告**：这会改变策略核心逻辑，回测结果不可靠。

### 方案4：使用模拟OI数据（仅用于测试）

生成合成OI数据用于框架测试：

```python
# 基于价格和成交量估算OI
estimated_oi = volume * price * correlation_factor
```

## 建议执行步骤

**立即行动（方案1）**：

1. 修改回测配置使用近期数据
```bash
# 编辑 config/yaml/active.yaml
start_date: "2026-01-01"
end_date: "2026-01-29"
```

2. 清理旧数据
```bash
rm -f data/raw/SOLUSDT/*oi*2025*.csv
```

3. 重新运行回测
```bash
uv run main.py backtest --type high
```

4. 验证OI数据加载和信号生成

**长期方案**：

1. 实现多交易所OI数据源（Binance + OKX）
2. 添加OI数据缓存机制
3. 考虑使用付费数据源获取长期历史OI数据
4. 实现策略的OI-optional模式用于无OI数据场景

## 技术细节

### Binance API测试结果
```
无startTime参数: 返回最新3条记录（2026-01-29 12:00:00）
带startTime参数: API错误 -1130 "parameter 'startTime' is invalid"
```

### 数据可用性
- OHLCV: ✅ 完整（Parquet格式，99.2%覆盖率）
- Funding Rate: ✅ 可用（2025-09-01起）
- Open Interest: ❌ 仅最近30天

### 策略影响
当前配置下，入场信号需要：
1. 突破支撑/阻力 ✅
2. OI背离 < -5% ❌ (无数据)
3. 资金费率 > ±30% ✅
4. 回撤0.2%进入 ✅

缺少OI数据导致条件2永远不满足，阻止所有交易信号。
