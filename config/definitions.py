from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType


class InstrumentType(Enum):
    # This is a okx-type based instrument type
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    SWAP = "SWAP"
    OPTION = "OPTION"


@dataclass
class InstrumentConfig:
    type: InstrumentType = InstrumentType.SWAP
    venue_name: str = "OKX"
    base_currency: str = "USDT"  # 是基于 USDT 进行的币对的交易
    quote_currency: str = "ETH"  # 而 quote 是被或者说参考 USDT 而衍生出的交易币价格
    leverage: int = 1  # 默认设定的杠杆倍数

    @classmethod
    def get_id_for(
        cls,
        venue_name: str,
        base_currency: str,
        quote_currency: str,
        inst_type: InstrumentType,
    ) -> str:
        """
        根据交易所、基准货币、报价货币和类型生成标准的 Instrument ID。
        """
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
                raise ValueError(f"Unsupported instrument type: {inst_type}")
        else:
            raise ValueError(f"Unsupported venue: {venue_name}")

    def get_symbol(self) -> str:
        return f"{self.quote_currency}{self.base_currency}"

    def get_json_path(self) -> Path:
        """
        获取标的定义 JSON 文件的绝对路径。
        通过相对于本文件的路径定位项目根目录，确保在任何工作目录下运行都能稳定定位。
        """
        # 定位项目根目录 (nautilus-practice/)
        project_root = Path(__file__).parent.parent.resolve()
        # 这里的路径逻辑：data/instrument/交易所/符号.json
        # 增加 .json 后缀并指向 instrument 子目录以确保准确性
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
    csv_file_name: str  # 在 data/raw 下的文件名
    bar_aggregation: BarAggregation = BarAggregation.HOUR
    bar_period: int = 1
    price_type: PriceType = PriceType.LAST
    instrument_id: Optional[str] = None  # 可选：指定该数据对应的 InstrumentID
    label: str = "main"  # 数据标签 (如 "main", "trend", "benchmark")

    @property
    def bar_type_str(self) -> str:
        # 这是一个辅助属性，用于生成 Nautilus 需要的 bar type 字符串
        # 具体的 instrument ID 需要在运行时结合 InstrumentConfig 生成
        return f"{self.bar_period}-{self.bar_aggregation.name}-{self.price_type.name}-EXTERNAL"
        # 大部分的数据都是由外部直接导入的，所以直接写 ‘external’


@dataclass
class StrategyConfig:
    """
    策略配置容器。
    优化设计：支持自动推断配置类，并集中管理参数解析逻辑，减少引擎层的重复代码。
    """

    name: str  # 策略类名 (例如 "RSSqueezeStrategy" 或 "RS_Squeeze")
    module_path: str  # 模块路径 (例如 "strategy.rs_squeeze")
    config_class: Optional[str] = None  # 可选：配置类名 (不填则自动推断为 {name}Config)

    # 策略特定的私有参数。支持 dict 或 dataclass 对象以获得更好的 IDE 支持
    params: Any = field(default_factory=dict)

    # 兼容性/扩展字段
    trade_pair_list: Optional[List[str]] = field(default_factory=list)

    def resolve_config_class(self) -> str:
        """获取配置类名，支持从策略名自动推断"""
        if self.config_class:
            return self.config_class
        # 自动推断逻辑: RS_Squeeze -> RS_SqueezeConfig
        return f"{self.name.replace('Strategy', '')}Config"

    def resolve_params(
        self,
        instrument_id: Any,
        leverage: int,
        feed_bar_types: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        集中解析最终传递给策略的参数字典。
        统一处理 Instrument ID、杠杆以及多周期数据标签的注入，解决引擎层逻辑分散的问题。
        """
        # 1. 基础参数解析 (支持 dict, dataclass 或 msgspec Struct)
        if isinstance(self.params, dict):
            p = self.params.copy()
        elif hasattr(self.params, "__dict__"):
            # Dataclass 或普通对象: 提取对象属性 (排除私有属性)
            p = {k: v for k, v in self.params.__dict__.items() if not k.startswith("_")}
        else:
            # 尝试处理 msgspec.Struct (Nautilus 核心配置类通常使用 msgspec)
            try:
                from msgspec import structs

                p = structs.asdict(self.params)
            except (ImportError, TypeError):
                p = {}

        # 2. 注入核心系统变量
        p["instrument_id"] = str(instrument_id)
        p["leverage"] = leverage

        # 3. 注入数据流对应的 BarType (基于 Label 约定)
        if "main" in feed_bar_types:
            bt = feed_bar_types["main"]
            # 兼容不同引擎对 bar_type 的类型要求 (Object vs Str)
            p["bar_type"] = bt
            p["trade_bar_type"] = str(bt)

        if "trend" in feed_bar_types:
            p["trend_bar_type"] = str(feed_bar_types["trend"])

        # 4. 自动注入其他辅助标签 (如 label="benchmark" -> benchmark_bar_type)
        for label, bt in feed_bar_types.items():
            if label not in ["main", "trend"]:
                p[f"{label}_bar_type"] = str(bt)

        return p


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
    strategy: StrategyConfig
    # 扩展数据配置：支持灵活的多数据源供给 (更优雅的设计)
    # 通过 DataConfig.label 区分用途 (如 "main", "trend", "benchmark")
    data_feeds: List[DataConfig] = field(default_factory=list)

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

    # Deprecated
    ## Support for auxiliary data (e.g. for MTF strategy trend layer)
    data: Optional[DataConfig] = None
    aux_data: Optional[DataConfig] = None

    def __post_init__(self):
        """
        同步兼容性字段到 data_feeds 列表，支持多数据供给框架。
        """
        # 将 data 加入 data_feeds
        if self.data and self.data not in self.data_feeds:
            if self.data.label == "main":
                self.data.label = "main"
            self.data_feeds.insert(0, self.data)

        # 将 aux_data 加入 data_feeds
        if self.aux_data and self.aux_data not in self.data_feeds:
            # 如果没指定标签，默认设为 trend
            if self.aux_data.label == "main":
                self.aux_data.label = "trend"
            self.data_feeds.append(self.aux_data)

        # 反向补全 (如果用户只用了 data_feeds)
        if self.data_feeds and self.data is None:
            self.data = self.data_feeds[0]
        if len(self.data_feeds) > 1 and self.aux_data is None:
            self.aux_data = self.data_feeds[1]


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
