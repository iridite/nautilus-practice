# 资金费率套利策略 - 交易币对配置

## MVP 测试期标的池 (阶段一)

### 硬编码 4 个币对

在初期测试"双腿同时下单"和"Delta 中性对齐"时,**只使用以下 4 个标的**:

#### 1. BTCUSDT (比特币) - 主力测试标的
```yaml
instrument_id: BTCUSDT-PERP.BINANCE
bar_type: BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
```
- **用途**: 测试基础逻辑
- **特点**: 流动性最好,基差最稳定
- **优先级**: ⭐⭐⭐⭐⭐

#### 2. ETHUSDT (以太坊) - 大市值对照组
```yaml
instrument_id: ETHUSDT-PERP.BINANCE
bar_type: ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
```
- **用途**: 大市值对照组
- **特点**: 流动性好,费率适中
- **优先级**: ⭐⭐⭐⭐

#### 3. SOLUSDT (Solana) - 高费率测试
```yaml
instrument_id: SOLUSDT-PERP.BINANCE
bar_type: SOLUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
```
- **用途**: 测试高费率环境
- **特点**: 波动率和费率常年高于 BTC
- **优先级**: ⭐⭐⭐⭐

#### 4. DOGEUSDT (狗狗币) - 极端狂热测试
```yaml
instrument_id: DOGEUSDT-PERP.BINANCE
bar_type: DOGEUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
```
- **用途**: 测试极端狂热下的基差吃单
- **特点**: Meme 币代表,费率极易飙升
- **优先级**: ⭐⭐⭐

## 为什么选择这 4 个币对?

### 1. 流动性梯度覆盖

| 币对 | 24h 成交量 (估算) | 现货深度 | 合约深度 | 滑点风险 |
|------|------------------|---------|---------|---------|
| BTCUSDT | $30B+ | 极深 | 极深 | 极低 |
| ETHUSDT | $15B+ | 很深 | 很深 | 低 |
| SOLUSDT | $3B+ | 深 | 深 | 中 |
| DOGEUSDT | $2B+ | 中 | 中 | 中高 |

### 2. 费率特征差异

| 币对 | 平均资金费率 | 费率波动性 | 极端费率频率 |
|------|-------------|-----------|------------|
| BTCUSDT | 0.01% / 8h | 低 | 低 |
| ETHUSDT | 0.01% / 8h | 低 | 低 |
| SOLUSDT | 0.03% / 8h | 中 | 中 |
| DOGEUSDT | 0.05% / 8h | 高 | 高 |

### 3. 测试覆盖场景

- **BTCUSDT**: 稳定环境,验证基础逻辑
- **ETHUSDT**: 大市值币种,验证通用性
- **SOLUSDT**: 高费率环境,验证盈利能力
- **DOGEUSDT**: 极端狂热,验证风控能力

## 配置文件示例

### BTC 配置 (默认)
```yaml
# config/strategies/funding_arbitrage_btc.yaml
config_class: FundingArbitrageConfig
module_path: strategy.funding_arbitrage
name: FundingArbitrageStrategy
parameters:
  instrument_id: BTCUSDT-PERP.BINANCE
  bar_type: BTCUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
  entry_basis_pct: 0.005
  exit_basis_pct: 0.001
  min_funding_rate_annual: 15.0
  max_position_risk_pct: 0.4
  max_positions: 3
```

### ETH 配置
```yaml
# config/strategies/funding_arbitrage_eth.yaml
config_class: FundingArbitrageConfig
module_path: strategy.funding_arbitrage
name: FundingArbitrageStrategy
parameters:
  instrument_id: ETHUSDT-PERP.BINANCE
  bar_type: ETHUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
  entry_basis_pct: 0.005
  exit_basis_pct: 0.001
  min_funding_rate_annual: 15.0
  max_position_risk_pct: 0.4
  max_positions: 3
```

### SOL 配置
```yaml
# config/strategies/funding_arbitrage_sol.yaml
config_class: FundingArbitrageConfig
module_path: strategy.funding_arbitrage
name: FundingArbitrageStrategy
parameters:
  instrument_id: SOLUSDT-PERP.BINANCE
  bar_type: SOLUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
  entry_basis_pct: 0.005
  exit_basis_pct: 0.001
  min_funding_rate_annual: 20.0  # SOL 费率更高,提高阈值
  max_position_risk_pct: 0.3     # 降低仓位,控制风险
  max_positions: 3
```

### DOGE 配置
```yaml
# config/strategies/funding_arbitrage_doge.yaml
config_class: FundingArbitrageConfig
module_path: strategy.funding_arbitrage
name: FundingArbitrageStrategy
parameters:
  instrument_id: DOGEUSDT-PERP.BINANCE
  bar_type: DOGEUSDT-PERP.BINANCE-1-HOUR-LAST-EXTERNAL
  entry_basis_pct: 0.008         # DOGE 滑点大,提高阈值
  exit_basis_pct: 0.002
  min_funding_rate_annual: 25.0  # DOGE 费率波动大,提高阈值
  max_position_risk_pct: 0.2     # 进一步降低仓位
  max_positions: 2               # 减少持仓数
```

## 数据准备清单

### 必需数据文件

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

### 数据下载命令 (示例)

```bash
# 下载 BTC 数据
uv run python scripts/download_data.py \
  --symbols BTCUSDT BTCUSDT-PERP \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --data-types ohlcv funding_rate

# 下载 ETH 数据
uv run python scripts/download_data.py \
  --symbols ETHUSDT ETHUSDT-PERP \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --data-types ohlcv funding_rate

# 下载 SOL 数据
uv run python scripts/download_data.py \
  --symbols SOLUSDT SOLUSDT-PERP \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --data-types ohlcv funding_rate

# 下载 DOGE 数据
uv run python scripts/download_data.py \
  --symbols DOGEUSDT DOGEUSDT-PERP \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --data-types ohlcv funding_rate
```

## 回测执行顺序

### 第 1 步: BTC 基础测试
```bash
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument BTCUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

**验证点**:
- ✅ 策略正常启动
- ✅ 双腿订单同时提交
- ✅ Delta 中性验证通过
- ✅ 资金费率正确收取
- ✅ 无单边成交失败

### 第 2 步: ETH 对照测试
```bash
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument ETHUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

**对比指标**:
- 开仓次数 vs BTC
- 资金费率收益 vs BTC
- 总收益率 vs BTC

### 第 3 步: SOL 高费率测试
```bash
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument SOLUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

**预期结果**:
- 资金费率收益 > BTC
- 开仓次数 > BTC
- 波动率 > BTC

### 第 4 步: DOGE 极端测试
```bash
uv run python main.py backtest \
  --strategy funding_arbitrage \
  --instrument DOGEUSDT-PERP.BINANCE \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

**风险检查**:
- 滑点损失是否可控
- 单边成交失败是否正确处理
- 极端费率下是否正常运行

## 阶段二: 动态标的池 (未来)

### 扩展标的候选

当阶段一验收通过后,可以考虑扩展到以下币对:

**Tier 1 (市值前 10)**:
- BNBUSDT
- XRPUSDT
- ADAUSDT

**Tier 2 (高费率币种)**:
- AVAXUSDT
- MATICUSDT
- LINKUSDT

**Tier 3 (Meme 币)**:
- SHIBUSDT
- PEPEUSDT

### 动态轮动逻辑

```python
# 未来实现
def select_top_funding_pairs(self, top_n: int = 5) -> list[str]:
    """
    从候选池中选择资金费率最高的 N 个币对

    筛选条件:
    1. 双腿俱全 (SPOT + PERP)
    2. 市值排名前 15
    3. 年化资金费率 > 30%
    4. 基差 > 0.5%
    5. 24h 成交量 > $500M

    返回: ["SOLUSDT-PERP", "DOGEUSDT-PERP", ...]
    """
    pass
```

## 总结

### 当前状态

✅ **已确定交易币对**:
1. BTCUSDT (主力)
2. ETHUSDT (对照)
3. SOLUSDT (高费率)
4. DOGEUSDT (极端)

✅ **配置文件**: 已更新 `config/strategies/funding_arbitrage.yaml`

⏳ **待完成**:
1. 下载 4 个币对的历史数据
2. 创建 4 个独立配置文件 (可选)
3. 运行回测验证
4. 达到验收标准

### 下一步行动

1. **确认数据**: 检查 `data/` 目录是否有这 4 个币对的数据
2. **运行回测**: 按顺序测试 BTC → ETH → SOL → DOGE
3. **验证结果**: 确保无单边成交失败
4. **进入阶段二**: 实现动态标的池
