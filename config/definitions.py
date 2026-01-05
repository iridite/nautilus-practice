from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, List
from nautilus_trader.model.enums import BarAggregation, PriceType
from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT

@dataclass
class InstrumentConfig:
    venue: str
    symbol: str
    step_size: Decimal = Decimal("0.01")
    lot_size: Decimal = Decimal("0.01")

    price_precision: int = 2
    size_precision: int = 3
    base_currency: str = "ETH"
    quote_currency: str = "USDT"
    
    @property
    def instrument_id(self) -> str:
        return f"{self.symbol}.{self.venue}"

@dataclass
class DataConfig:
    csv_file_name: str  # 在 data/raw 下的文件名
    bar_aggregation: BarAggregation = BarAggregation.MINUTE
    bar_period: int = 1
    price_type: PriceType = PriceType.LAST
    
    @property
    def bar_type_str(self) -> str:
        # 这是一个辅助属性，用于生成 Nautilus 需要的 bar type 字符串
        # 具体的 instrument ID 需要在运行时结合 InstrumentConfig 生成
        return f"{self.bar_period}-{self.bar_aggregation.name}-{self.price_type.name}-EXTERNAL"

@dataclass
class StrategyConfig:
    name: str  # 策略类名，例如 "BmrStrategy"
    module_path: str # 策略模块路径，例如 "strategy.bmr"
    config_class: str # 配置类名，例如 "BmrStrategyConfig"
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BacktestConfig:
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_balance: List[Money] = field(
        default_factory=lambda: [Money("10_000", USDT)]
    )
@dataclass
class LogConfig:
    log_level: str = "INFO"
    log_level_file: str = "DEBUG"
    log_colors: bool = True
    use_pyo3: bool = True

@dataclass
class GlobalConfig:
    instrument: InstrumentConfig
    data: DataConfig
    strategy: StrategyConfig
    backtest: BacktestConfig
    logging: LogConfig
    
    # 可以在这里添加 Sandbox 或 Live 的配置
