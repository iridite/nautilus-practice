# 数据需求配置设计方案

## 问题背景

当前项目存在以下问题：
1. `main.py` 的 `override_symbol_config()` 会动态修改环境配置文件
2. 不同策略对数据的需求不同（时间周期、现货/期货、自定义数据）
3. 配置分散在多个地方，难以维护

## 设计目标

1. **声明式配置**：每个策略在自己的配置文件中声明数据需求
2. **类型安全**：使用 Pydantic 验证数据需求配置
3. **灵活性**：支持多种数据类型（Bar、Funding Rate、OI 等）
4. **向后兼容**：不破坏现有配置

## 方案设计

### 1. 策略配置中的数据需求声明

每个策略配置文件添加 `data_requirements` 字段：

```yaml
# config/strategies/keltner_rs_breakout.yaml
name: KeltnerRSBreakoutStrategy
module_path: strategy.keltner_rs_breakout
config_class: KeltnerRSBreakoutConfig

# 数据需求声明（新增）
data_requirements:
  # 主数据源
  primary:
    type: bar                    # 数据类型：bar / funding_rate / oi
    aggregation: DAY             # K线聚合：DAY / HOUR / MINUTE
    period: 1                    # 周期：1 / 4 / 15 等
    price_type: LAST             # 价格类型：LAST / MID / BID / ASK
    instrument_type: PERP        # 标的类型：PERP / SPOT / FUTURES

  # 辅助数据源（可选）
  auxiliary:
    - name: btc_benchmark        # 数据源名称
      type: bar
      aggregation: DAY
      period: 1
      symbol: BTCUSDT            # 固定符号（不随 Universe 变化）
      instrument_type: PERP

parameters:
  # 策略参数...
```

### 2. 期现套利策略的数据需求

```yaml
# config/strategies/spot_futures_arbitrage.yaml
name: SpotFuturesArbitrageStrategy
module_path: strategy.spot_futures_arbitrage
config_class: SpotFuturesArbitrageConfig

# 数据需求声明
data_requirements:
  # 现货数据
  primary:
    type: bar
    aggregation: HOUR
    period: 1
    instrument_type: SPOT        # 现货

  # 期货数据（必需）
  auxiliary:
    - name: perp_data
      type: bar
      aggregation: HOUR
      period: 1
      instrument_type: PERP      # 永续合约
      symbol_suffix: "-PERP"     # 符号后缀

    - name: funding_rate
      type: funding_rate         # 资金费率数据
      instrument_type: PERP

parameters:
  # 策略参数...
```

### 3. 资金费套利策略的数据需求

```yaml
# config/strategies/funding_arbitrage.yaml
name: FundingArbitrageStrategy
module_path: strategy.funding_arbitrage
config_class: FundingArbitrageConfig

# 数据需求声明
data_requirements:
  # 永续合约数据
  primary:
    type: bar
    aggregation: HOUR
    period: 1
    instrument_type: PERP

  # 资金费率数据（必需）
  auxiliary:
    - name: funding_rate
      type: funding_rate
      instrument_type: PERP
      required: true             # 标记为必需

    - name: spot_fallback       # 现货回退（可选）
      type: bar
      aggregation: HOUR
      period: 1
      instrument_type: SPOT
      required: false

parameters:
  # 策略参数...
```

## 数据类型定义

### DataRequirement Schema

```python
# core/schemas.py

from enum import Enum
from pydantic import BaseModel, Field

class DataType(str, Enum):
    """数据类型枚举"""
    BAR = "bar"                      # K线数据
    FUNDING_RATE = "funding_rate"    # 资金费率
    OPEN_INTEREST = "open_interest"  # 持仓量
    ORDERBOOK = "orderbook"          # 订单簿
    TRADE = "trade"                  # 逐笔成交

class InstrumentType(str, Enum):
    """标的类型枚举"""
    SPOT = "SPOT"                    # 现货
    PERP = "PERP"                    # 永续合约
    FUTURES = "FUTURES"              # 期货
    SWAP = "SWAP"                    # 掉期

class DataRequirementConfig(BaseModel):
    """单个数据需求配置"""
    name: str | None = None          # 数据源名称（auxiliary 必需）
    type: DataType                   # 数据类型
    aggregation: BarAggregation | None = None  # K线聚合（仅 bar 类型）
    period: int = 1                  # 周期
    price_type: PriceType = PriceType.LAST
    instrument_type: InstrumentType = InstrumentType.PERP
    symbol: str | None = None        # 固定符号（可选）
    symbol_suffix: str | None = None # 符号后缀（可选）
    required: bool = True            # 是否必需

class StrategyDataRequirements(BaseModel):
    """策略数据需求配置"""
    primary: DataRequirementConfig   # 主数据源
    auxiliary: list[DataRequirementConfig] = Field(default_factory=list)
```

## 配置加载流程

### 1. ConfigLoader 增强

```python
# core/loader.py

class ConfigLoader:
    def load_strategy_config(self, strategy_name: str) -> StrategyConfig:
        """加载策略配置（包含数据需求）"""
        yaml_data = self._load_yaml(f"strategies/{strategy_name}.yaml")

        # 解析数据需求
        data_reqs = None
        if "data_requirements" in yaml_data:
            data_reqs = StrategyDataRequirements(**yaml_data["data_requirements"])

        return StrategyConfig(
            name=yaml_data["name"],
            module_path=yaml_data["module_path"],
            config_class=yaml_data.get("config_class"),
            parameters=yaml_data.get("parameters", {}),
            data_requirements=data_reqs  # 新增字段
        )
```

### 2. ConfigAdapter 数据源生成

```python
# core/adapter.py

class ConfigAdapter:
    def generate_data_feeds(
        self,
        strategy_config: StrategyConfig,
        symbols: list[str]  # 从 Universe 获取
    ) -> list[DataConfig]:
        """根据策略数据需求生成数据源配置"""

        if not strategy_config.data_requirements:
            # 向后兼容：使用默认配置
            return self._generate_default_data_feeds(symbols)

        data_feeds = []
        reqs = strategy_config.data_requirements

        # 为每个 symbol 生成主数据源
        for symbol in symbols:
            feed = self._create_data_feed(
                symbol=symbol,
                requirement=reqs.primary,
                start_date=self.env_config.backtest.start_date,
                end_date=self.env_config.backtest.end_date
            )
            data_feeds.append(feed)

        # 生成辅助数据源
        for aux_req in reqs.auxiliary:
            if aux_req.symbol:
                # 固定符号（如 BTC benchmark）
                feed = self._create_data_feed(
                    symbol=aux_req.symbol,
                    requirement=aux_req,
                    start_date=self.env_config.backtest.start_date,
                    end_date=self.env_config.backtest.end_date
                )
                data_feeds.append(feed)
            else:
                # 为每个 symbol 生成辅助数据
                for symbol in symbols:
                    feed = self._create_data_feed(
                        symbol=symbol,
                        requirement=aux_req,
                        start_date=self.env_config.backtest.start_date,
                        end_date=self.env_config.backtest.end_date
                    )
                    data_feeds.append(feed)

        return data_feeds

    def _create_data_feed(
        self,
        symbol: str,
        requirement: DataRequirementConfig,
        start_date: str,
        end_date: str
    ) -> DataConfig:
        """创建单个数据源配置"""

        # 构建 instrument_id
        if requirement.instrument_type == InstrumentType.SPOT:
            instrument_id = f"{symbol}.{self.env_config.trading.venue}"
        elif requirement.instrument_type == InstrumentType.PERP:
            instrument_id = f"{symbol}-PERP.{self.env_config.trading.venue}"
        else:
            instrument_id = f"{symbol}-{requirement.instrument_type.value}.{self.env_config.trading.venue}"

        # 构建 CSV 文件名
        if requirement.type == DataType.BAR:
            agg_str = requirement.aggregation.name.lower()
            csv_file = f"{symbol}/binance-{symbol}-{requirement.period}{agg_str}-{start_date}_{end_date}.csv"
        elif requirement.type == DataType.FUNDING_RATE:
            csv_file = f"{symbol}/binance-{symbol}-funding_rate-{start_date}_{end_date}.csv"
        else:
            raise ValueError(f"Unsupported data type: {requirement.type}")

        return DataConfig(
            instrument_id=instrument_id,
            bar_aggregation=requirement.aggregation,
            bar_period=requirement.period,
            price_type=requirement.price_type,
            origination="EXTERNAL",
            csv_file_name=csv_file,
            label=requirement.name or "main"
        )
```

## 使用示例

### 1. Keltner RS Breakout（单一数据源）

```yaml
# config/strategies/keltner_rs_breakout.yaml
data_requirements:
  primary:
    type: bar
    aggregation: DAY
    period: 1
    instrument_type: PERP
  auxiliary:
    - name: btc_benchmark
      type: bar
      aggregation: DAY
      period: 1
      symbol: BTCUSDT
      instrument_type: PERP
```

**生成的数据源**（假设 Universe = [ETHUSDT, SOLUSDT]）：
```python
[
    DataConfig(instrument_id="ETHUSDT-PERP.BINANCE", aggregation=DAY, period=1, ...),
    DataConfig(instrument_id="SOLUSDT-PERP.BINANCE", aggregation=DAY, period=1, ...),
    DataConfig(instrument_id="BTCUSDT-PERP.BINANCE", aggregation=DAY, period=1, label="btc_benchmark"),
]
```

### 2. 期现套利（多标的类型）

```yaml
# config/strategies/spot_futures_arbitrage.yaml
data_requirements:
  primary:
    type: bar
    aggregation: HOUR
    period: 1
    instrument_type: SPOT
  auxiliary:
    - name: perp_data
      type: bar
      aggregation: HOUR
      period: 1
      instrument_type: PERP
    - name: funding_rate
      type: funding_rate
      instrument_type: PERP
```

**生成的数据源**（假设 symbols = [BTCUSDT]）：
```python
[
    # 现货数据
    DataConfig(instrument_id="BTCUSDT.BINANCE", aggregation=HOUR, period=1, label="main"),
    # 期货数据
    DataConfig(instrument_id="BTCUSDT-PERP.BINANCE", aggregation=HOUR, period=1, label="perp_data"),
    # 资金费率数据
    DataConfig(instrument_id="BTCUSDT-PERP.BINANCE", type=FUNDING_RATE, label="funding_rate"),
]
```

## 迁移路径

### 阶段 1：添加数据需求配置（不破坏现有功能）

1. 在 `core/schemas.py` 添加数据需求相关类
2. 在策略配置文件中添加 `data_requirements` 字段（可选）
3. `ConfigAdapter` 优先使用 `data_requirements`，回退到现有逻辑

### 阶段 2：迁移现有策略

1. 为 `keltner_rs_breakout.yaml` 添加数据需求配置
2. 为 `spot_futures_arbitrage.yaml` 添加数据需求配置
3. 为 `funding_arbitrage.yaml` 添加数据需求配置

### 阶段 3：移除遗留代码

1. 删除 `main.py` 中的 `override_symbol_config()` 函数
2. 删除环境配置中的硬编码 `data_feeds`
3. 更新文档

## 优势

1. ✅ **声明式配置**：数据需求一目了然
2. ✅ **类型安全**：Pydantic 验证，减少配置错误
3. ✅ **灵活性**：支持多种数据类型和标的类型
4. ✅ **可维护性**：配置集中在策略文件中
5. ✅ **向后兼容**：不破坏现有配置
6. ✅ **可扩展性**：易于添加新的数据类型

## 示例：完整的策略配置

```yaml
# config/strategies/advanced_arbitrage.yaml
name: AdvancedArbitrageStrategy
module_path: strategy.advanced_arbitrage
config_class: AdvancedArbitrageConfig

# 数据需求声明
data_requirements:
  # 主数据源：现货 1h K线
  primary:
    type: bar
    aggregation: HOUR
    period: 1
    instrument_type: SPOT

  # 辅助数据源
  auxiliary:
    # 永续合约 1h K线
    - name: perp_1h
      type: bar
      aggregation: HOUR
      period: 1
      instrument_type: PERP

    # 永续合约 5m K线（用于精细化入场）
    - name: perp_5m
      type: bar
      aggregation: MINUTE
      period: 5
      instrument_type: PERP

    # 资金费率
    - name: funding_rate
      type: funding_rate
      instrument_type: PERP
      required: true

    # 持仓量（可选）
    - name: open_interest
      type: open_interest
      instrument_type: PERP
      required: false

    # BTC 基准（固定符号）
    - name: btc_benchmark
      type: bar
      aggregation: HOUR
      period: 1
      symbol: BTCUSDT
      instrument_type: PERP

parameters:
  # 策略参数...
  entry_basis_annual: 15.0
  exit_basis_annual: 5.0
  # ...
```

## 总结

这个设计方案：
- 将数据需求声明式地写在策略配置中
- 支持多种数据类型和标的类型
- 自动生成数据源配置，无需手动维护
- 向后兼容，不破坏现有功能
- 易于扩展和维护

建议优先实现阶段 1，然后逐步迁移现有策略。
