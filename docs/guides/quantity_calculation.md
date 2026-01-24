# 下单量计算逻辑说明 (Quantity Calculation)

本文档旨在解释策略在回测与实盘中如何确定最终的下单数量（Quantity），以及相关的优先级和风控逻辑。

## 1. 核心计算公式

策略默认采用**动态仓位管理**模式，计算公式如下：

$$TargetNotional = AccountTotalEquity \times QtyPercent \times Leverage$$
$$OrderQuantity = \frac{TargetNotional}{CurrentPrice}$$

其中：
- **AccountTotalEquity**: 账户总权益（包含未实现盈亏）。
- **QtyPercent**: 仓位占用比例（例如 0.1 代表使用 10% 的资金）。
- **Leverage**: 杠杆倍数。
- **CurrentPrice**: 当前资产价格。

## 2. 杠杆 (Leverage) 优先级

为了满足合约交易的灵活性，杠杆的来源按以下优先级确定：

1.  **策略动态推荐 (Highest)**: 
    - 策略通过执行 `recommend_leverage()` 方法返回的数值。
    - 适用于根据波动率（VIX）或信号强度动态调整杠杆。
2.  **策略配置 (Medium)**: 
    - 在 `settings.py` 的 `StrategyConfig.params` 中设定的 `leverage` 参数。
3.  **标的默认配置 (Lowest)**: 
    - 在 `settings.py` 的 `InstrumentConfig` 中设定的 `leverage`。

**自动保护机制**：
程序会自动查询交易所返回的 `instrument.max_leverage`，如果计算出的杠杆超过交易所上限，将自动向下取整至交易所允许的最大值。

## 3. 下单量保护 (Fallback Mechanism)

如果在计算动态仓位时发生异常（例如账户余额读取失败或价格为零），系统会触发 **Fallback 保护逻辑**：

- **Fallback Value**: 使用 `settings.py` 中定义的 `trade_size`。
- **触发警告**: 日志中会输出 `[WARN]` 提示正在使用固定下单量。

## 4. 精度处理

计算出的原始下单量（Raw Quantity）会经过 `instrument.make_qty()` 处理，以符合交易所的以下规范：
- **Lot Size**: 最小交易单位（如 BTC 的 0.0001）。
- **Precision**: 小数位精度。
- **Min/Max Quantity**: 交易所规定的最大最小下单量限制。

## 5. 日志查看

在回测输出中，你可以看到详细的计算分解日志：

```text
Qty Calculation: Balance=1000.0, Pct=0.1, Lev=3, TargetNotional=300.0 -> Qty=0.112
```

通过这行日志，你可以清晰地回溯每一笔订单背后的资金分配逻辑。