from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, List
from nautilus_trader.model.enums import BarAggregation, PriceType

@dataclass
class InstrumentConfig:
    venue: str
    symbol: str
    step_size: Decimal = Decimal("0.01")
    lot_size: Decimal = Decimal("0.01")
    
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
    initial_balance: str = "10000 USDT"
    
@dataclass
class GlobalConfig:
    instrument: InstrumentConfig
    data: DataConfig
    strategy: StrategyConfig
    backtest: BacktestConfig
    
    # 可以在这里添加 Sandbox 或 Live 的配置
