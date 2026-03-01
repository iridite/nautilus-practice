# 资金费率套利策略 - MVP 测试配置

## 阶段一: 硬编码标的池 (4个币对)

在初期测试"双腿同时下单"和"Delta 中性对齐"时,只使用以下 4 个标的:

### 1. BTCUSDT (比特币)
- **用途**: 测试基础逻辑
- **特点**: 流动性最好,基差最稳定
- **配置**: `instrument_id: BTCUSDT-PERP.BINANCE`

### 2. ETHUSDT (以太坊)
- **用途**: 大市值对照组
- **特点**: 流动性好,费率适中
- **配置**: `instrument_id: ETHUSDT-PERP.BINANCE`

### 3. SOLUSDT (Solana)
- **用途**: 测试高费率环境
- **特点**: 波动率和费率常年高于 BTC
- **配置**: `instrument_id: SOLUSDT-PERP.BINANCE`

### 4. DOGEUSDT (狗狗币)
- **用途**: 测试极端狂热下的基差吃单
- **特点**: Meme 币代表,费率极易飙升
- **配置**: `instrument_id: DOGEUSDT-PERP.BINANCE`

## 数据要求

确保以下数据已下载:

```
data/
├── BTCUSDT.BINANCE/
│   └── ohlcv_1h_2024-01-01_2024-12-31.parquet
├── BTCUSDT-PERP.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet
│   └── funding_rate_2024-01-01_2024-12-31.csv
├── ETHUSDT.BINANCE/
│   └── ohlcv_1h_2024-01-01_2024-12-31.parquet
├── ETHUSDT-PERP.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet
│   └── funding_rate_2024-01-01_2024-12-31.csv
├── SOLUSDT.BINANCE/
│   └── ohlcv_1h_2024-01-01_2024-12-31.parquet
├── SOLUSDT-PERP.BINANCE/
│   ├── ohlcv_1h_2024-01-01_2024-12-31.parquet
│   └── funding_rate_2024-01-01_2024-12-31.csv
├── DOGEUSDT.BINANCE/
│   └── ohlcv_1h_2024-01-01_2024-12-31.parquet
└── DOGEUSDT-PERP.BINANCE/
    ├── ohlcv_1h_2024-01-01_2024-12-31.parquet
    └── funding_rate_2024-01-01_2024-12-31.csv
```

## 测试流程

### 1. 单币对测试 (BTC)

```bash
# 测试基础逻辑
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument BTCUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

**验证点**:
- ✅ 双腿订单同时提交
- ✅ Delta 中性验证通过 (< 0.5%)
- ✅ 资金费率正确收取
- ✅ 基差收敛时正确平仓
- ✅ 无单边成交失败

### 2. 多币对对比测试

```bash
# 测试 ETH (大市值对照组)
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument ETHUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 测试 SOL (高费率环境)
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument SOLUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31

# 测试 DOGE (极端狂热)
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument DOGEUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

**对比指标**:
- 开仓次数
- 平均持仓时长
- 资金费率收益
- 基差收益
- 总收益率
- 最大回撤
- Sharpe 比率

### 3. 验收标准

只有当以下条件**全部满足**时,才能进入阶段二:

- [ ] 4 个币对的回测全部通过
- [ ] Delta 中性验证通过率 > 99%
- [ ] 无单边成交失败 (或失败后正确处理)
- [ ] 资金费率收益 > 0
- [ ] 基差收益 > 0
- [ ] 总收益率 > 10% (年化)
- [ ] 最大回撤 < 10%
- [ ] Sharpe 比率 > 1.0

## 阶段二: 动态标的池 (待实现)

### 标的筛选条件

1. **"双腿俱全"硬性门槛**
   - 必须同时存在 SPOT 和 PERP 市场
   - 缺腿直接踢出 Universe

2. **剔除低流动性山寨币**
   - 只在市值或成交量排名前 10-15 的币种中套利
   - 避免滑点吃光基差利润

3. **从"RS 轮动"改为"资金费率轮动"**
   - 实时监控所有币种的年化资金费率
   - 优先在费率最高 (年化 > 30%) 且基差达标的标的上执行

### 实现方式

```python
# 未来实现 (阶段二)
class FundingRateUniverseManager:
    """资金费率动态标的池管理器"""

    def select_top_funding_pairs(
        self,
        min_funding_rate_annual: float = 30.0,
        min_basis_pct: float = 0.005,
        top_n: int = 5
    ) -> list[str]:
        """
        选择资金费率最高的标的

        筛选条件:
        1. 双腿俱全 (SPOT + PERP)
        2. 市值排名前 15
        3. 年化资金费率 > 30%
        4. 基差 > 0.5%

        返回: ["BTCUSDT-PERP", "ETHUSDT-PERP", ...]
        """
        pass
```

## 当前状态

✅ **阶段一**: 已完成基础架构
- 策略文件: `strategy/funding_arbitrage.py`
- 配置文件: `config/strategies/funding_arbitrage.yaml`
- 测试文件: `tests/test_spot_futures_arbitrage.py` (20/20 通过)

⏳ **待完成**:
1. 下载 4 个币对的历史数据
2. 运行回测验证
3. 确认无单边成交失败
4. 达到验收标准后进入阶段二

❌ **阶段二**: 未开始
- 动态标的池管理器
- 资金费率轮动逻辑
- Universe 筛选条件

## 注意事项

### 为什么不立即引入 Universe?

1. **多腿并发风险**: 小币种的现货精度问题或盘口深度不够,容易导致对冲失败
2. **单边敞口风险**: 某个币种的 SPOT 或 PERP 数据缺失,导致"单腿裸奔"
3. **调试困难**: 15 个币种同时运行,很难定位问题
4. **资源浪费**: 在基础逻辑未跑通前,引入 Universe 是过度设计

### MVP 测试期的目标

**唯一目标**: 确保"双腿同时下单"和"Delta 中性对齐"的逻辑**绝对不会出现单边敞口**

只有当这个目标达成后,才能考虑引入动态标的池。

## 下一步行动

1. **下载数据**: 确保 4 个币对的 SPOT + PERP + Funding Rate 数据完备
2. **运行回测**: 逐个测试 BTC, ETH, SOL, DOGE
3. **验证结果**: 检查 Delta 中性、资金费率收益、基差收益
4. **修复 Bug**: 如果出现单边成交失败,立即修复
5. **达标后**: 进入阶段二,实现动态标的池
