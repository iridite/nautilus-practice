from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType


class InstrumentType(Enum):
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    SWAP = "SWAP"
    OPTION = "OPTION"


@dataclass
class InstrumentConfig:
    type: InstrumentType = InstrumentType.SWAP
    venue_name: str = "OKX"
    base_currency: str = "ETH"
    quote_currency: str = "USDT"
    leverage: Optional[int] = None  # 用户设定的杠杆倍数

    @property
    def instrument_id(self) -> str:
        if self.venue_name == "OKX":
            return f"{self.quote_currency}-{self.base_currency}-{self.type.value}.{self.venue_name}"
        elif self.venue_name == "BINANCE":
            if self.type == InstrumentType.SPOT:
                return f"{self.quote_currency}{self.base_currency}.{self.venue_name}"
            elif self.type == InstrumentType.SWAP:
                return (
                    f"{self.quote_currency}{self.base_currency}-PERP.{self.venue_name}"
                )
            elif self.type == InstrumentType.FUTURES:
                return f"{self.quote_currency}{self.base_currency}-{self.type.value}.{self.venue_name}"
            elif self.type == InstrumentType.OPTION:
                return f"{self.quote_currency}{self.base_currency}-{self.type.value}.{self.venue_name}"
            else:
                raise ValueError(f"Unsupported instrument type: {self.type}")
        else:
            raise ValueError(f"Unsupported venue: {self.venue_name}")


@dataclass
class DataConfig:
    csv_file_name: str  # 在 data/raw 下的文件名
    bar_aggregation: BarAggregation = BarAggregation.HOUR
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
    module_path: str  # 策略模块路径，例如 "strategy.bmr"
    config_class: str  # 配置类名，例如 "BmrStrategyConfig"
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogConfig:
    log_level: str = "INFO"
    log_level_file: str = "DEBUG"
    log_colors: bool = True
    use_pyo3: bool = True
    log_component_levels: Dict[str, str] = field(default_factory=dict)
    log_components_only: bool = False


@dataclass
class MLConfig:
    # Feature Engineering & Labeling
    ema_period: int = 50
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    stop_loss_pct: float = 0.015
    take_profit_pct: float = 0.03
    horizon_bars: int = 24

    # Inference Control
    use_ai_filter: bool = False
    model_path: str = "data/models/lgbm_mtf_v1.joblib"  # 名称需要动态化
    min_prob_threshold: float = 0.60
    record_features: bool = False
    record_path: str = "data/record/features_log.csv"


@dataclass
class BackTestConfig:
    # 以下三个是回测必备的子集配置选项
    instrument: InstrumentConfig
    data: DataConfig
    strategy: StrategyConfig

    # 基础回测配置
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    initial_balances: List[Money] = field(
        default_factory=lambda: [Money("10_000", USDT)]
    )
    output_html_report: bool = False
    # TODO：尝试在这里控制回测的高级/低级引擎切换

    # 以下是可选的配置
    logging: LogConfig | None = None
    ml: MLConfig | None = None

    # Support for auxiliary data (e.g. for MTF strategy trend layer)
    aux_data: Optional[DataConfig] = None


@dataclass
class SandboxConfig:
    # Sandbox Configuration Options
    sandbox_mode: bool = False
    sandbox_balance: Money = Money("10_000", USDT)  # TODO: 需要注意多币种


@dataclass
class LiveConfig:
    # Live Configuration Options
    live_mode: bool = False
    live_balance: Money = Money("10_000", USDT)  # TODO: 需要注意多币种
