"""
配置数据模型

定义回测系统使用的核心配置类。
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType

project_root: Path = Path(__file__).parent.parent.resolve()


class InstrumentType(Enum):
    """交易工具类型"""
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    SWAP = "SWAP"
    OPTION = "OPTION"


@dataclass
class InstrumentConfig:
    """交易工具配置"""
    type: InstrumentType = InstrumentType.SWAP
    venue_name: str = "OKX"
    base_currency: str = "USDT"
    quote_currency: str = "ETH"
    leverage: int = 1

    @classmethod
    def get_id_for(
        cls,
        venue_name: str,
        base_currency: str,
        quote_currency: str,
        inst_type: InstrumentType,
    ) -> str:
        if venue_name == "OKX":
            return f"{quote_currency}-{base_currency}-{inst_type.value}.{venue_name}"
        elif venue_name == "BINANCE":
            if inst_type == InstrumentType.SPOT:
                return f"{quote_currency}{base_currency}.{venue_name}"
            elif inst_type == InstrumentType.SWAP:
                return f"{quote_currency}{base_currency}-PERP.{venue_name}"
            elif inst_type in (InstrumentType.FUTURES, InstrumentType.OPTION):
                return f"{quote_currency}{base_currency}-{inst_type.value}.{venue_name}"
        else:
            raise ValueError(f"Unsupported venue: {venue_name}")

    def get_symbol(self) -> str:
        return f"{self.quote_currency}{self.base_currency}"

    def get_json_path(self) -> Path:
        return (
            project_root
            / "data"
            / "instrument"
            / self.venue_name.upper()
            / f"{self.instrument_id.split('.')[0]}.json"
        )

    @property
    def instrument_id(self) -> str:
        return self.get_id_for(
            venue_name=self.venue_name,
            base_currency=self.base_currency,
            quote_currency=self.quote_currency,
            inst_type=self.type,
        )


@dataclass
class DataConfig:
    """数据配置"""
    csv_file_name: str
    bar_aggregation: BarAggregation = BarAggregation.HOUR
    bar_period: int = 1
    price_type: PriceType = PriceType.LAST
    instrument_id: str | None = None
    label: str = "main"

    @property
    def full_path(self) -> Path:
        return project_root / "data" / "raw" / self.csv_file_name

    @property
    def bar_type_str(self) -> str:
        return f"{self.bar_period}-{self.bar_aggregation.name}-{self.price_type.name}-EXTERNAL"


@dataclass
class LegacyStrategyConfig:
    """策略配置容器"""
    name: str
    module_path: str
    config_class: str | None = None
    params: Any = field(default_factory=dict)
    trade_pair_list: list[str] | None = field(default_factory=list)

    def resolve_config_class(self) -> str:
        if self.config_class:
            return self.config_class
        return f"{self.name.replace('Strategy', '')}Config"

    def resolve_params(
        self,
        instrument_id: Any,
        leverage: int,
        feed_bar_types: Dict[str, Any],
    ) -> Dict[str, Any]:
        if isinstance(self.params, dict):
            p = self.params.copy()
        elif hasattr(self.params, "__dict__"):
            p = {k: v for k, v in self.params.__dict__.items() if not k.startswith("_")}
        else:
            try:
                from msgspec import structs
                p = structs.asdict(self.params)
            except (ImportError, TypeError):
                p = {}

        p["instrument_id"] = str(instrument_id)
        p["leverage"] = leverage

        if "main" in feed_bar_types:
            bt = feed_bar_types["main"]
            p["bar_type"] = bt
            p["trade_bar_type"] = str(bt)

        if "trend" in feed_bar_types:
            p["trend_bar_type"] = str(feed_bar_types["trend"])

        for label, bt in feed_bar_types.items():
            if label not in ["main", "trend"]:
                p[f"{label}_bar_type"] = str(bt)

        return p


@dataclass
class LogConfig:
    """日志配置"""
    log_level: str = "INFO"
    log_level_file: str = "DEBUG"
    log_colors: bool = True
    use_pyo3: bool = True
    log_component_levels: Dict[str, str] = field(default_factory=dict)
    log_components_only: bool = False


@dataclass
class BackTestConfig:
    """回测配置容器"""
    instrument: InstrumentConfig
    strategy: LegacyStrategyConfig
    instruments: List[InstrumentConfig] = field(default_factory=list)
    data_feeds: List[DataConfig] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    initial_balances: List[Money] = field(
        default_factory=lambda: [Money("10_000", USDT)]
    )
    output_html_report: bool = False
    logging: LogConfig | None = None
    data: DataConfig | None = None
    aux_data: DataConfig | None = None

    def __post_init__(self):
        if self.instrument and not self.instruments:
            self.instruments.append(self.instrument)

        if self.data and self.data not in self.data_feeds:
            if self.data.label == "main":
                self.data.label = "main"
            self.data_feeds.insert(0, self.data)

        if self.aux_data and self.aux_data not in self.data_feeds:
            if self.aux_data.label == "main":
                self.aux_data.label = "trend"
            self.data_feeds.append(self.aux_data)

        if self.data_feeds and self.data is None:
            self.data = self.data_feeds[0]
        if len(self.data_feeds) > 1 and self.aux_data is None:
            self.aux_data = self.data_feeds[1]
