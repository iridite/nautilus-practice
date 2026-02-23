"""
配置系统数据模型定义

使用Pydantic提供类型安全的配置验证和序列化。
与现有的config/definitions.py紧密集成，复用已有的数据结构。
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 项目根目录
project_root: Path = Path(__file__).parent.parent.resolve()


# ============================================================
# 交易工具配置
# ============================================================


class InstrumentType(Enum):
    """
    交易工具类型枚举

    Attributes:
        SPOT: 现货交易
        FUTURES: 期货合约
        SWAP: 永续合约
        PERP: 永续合约（别名）
        OPTION: 期权合约
    """

    SPOT = "SPOT"
    FUTURES = "FUTURES"
    SWAP = "SWAP"
    PERP = "PERP"
    OPTION = "OPTION"


class InstrumentConfig(BaseModel):
    """
    交易工具配置

    定义交易标的的基本信息，包括交易所、货币对、合约类型和杠杆。

    Attributes:
        type: 合约类型（默认为永续合约）
        venue_name: 交易所名称（OKX, BINANCE）
        base_currency: 基础货币（通常为 USDT）
        quote_currency: 报价货币（BTC, ETH 等）
        leverage: 杠杆倍数（默认为 1）
    """

    type: InstrumentType = InstrumentType.SWAP
    venue_name: str = "OKX"
    base_currency: str = "USDT"
    quote_currency: str = "ETH"
    leverage: int = 1

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def get_id_for(
        cls,
        venue_name: str,
        base_currency: str,
        quote_currency: str,
        inst_type: InstrumentType,
    ) -> str:
        """
        根据交易所和货币对生成标准化的 instrument_id

        Args:
            venue_name: 交易所名称（OKX, BINANCE）
            base_currency: 基础货币（USDT）
            quote_currency: 报价货币（BTC, ETH）
            inst_type: 合约类型（SPOT, SWAP, FUTURES）

        Returns:
            标准化的 instrument_id 字符串

        Raises:
            ValueError: 不支持的交易所
        """
        if venue_name == "OKX":
            return f"{quote_currency}-{base_currency}-{inst_type.value}.{venue_name}"
        elif venue_name == "BINANCE":
            if inst_type == InstrumentType.SPOT:
                return f"{quote_currency}{base_currency}.{venue_name}"
            elif inst_type in (InstrumentType.SWAP, InstrumentType.PERP):
                return f"{quote_currency}{base_currency}-PERP.{venue_name}"
            elif inst_type in (InstrumentType.FUTURES, InstrumentType.OPTION):
                return f"{quote_currency}{base_currency}-{inst_type.value}.{venue_name}"
        else:
            raise ValueError(f"Unsupported venue: {venue_name}")

    def get_symbol(self) -> str:
        """
        获取交易对符号

        Returns:
            交易对符号字符串（如 BTCUSDT）
        """
        return f"{self.quote_currency}{self.base_currency}"

    def get_json_path(self) -> Path:
        """
        获取合约定义 JSON 文件的路径

        Returns:
            合约定义文件的完整路径
        """
        return (
            project_root
            / "data"
            / "instrument"
            / self.venue_name.upper()
            / f"{self.instrument_id.split('.')[0]}.json"
        )

    @property
    def instrument_id(self) -> str:
        """
        获取标准化的 instrument_id

        Returns:
            标准化的交易标的标识符（如 BTC-USDT-SWAP.OKX）
        """
        return self.get_id_for(
            venue_name=self.venue_name,
            base_currency=self.base_currency,
            quote_currency=self.quote_currency,
            inst_type=self.type,
        )


# ============================================================
# 数据配置
# ============================================================


class DataConfig(BaseModel):
    """
    数据配置

    定义回测或实盘交易所需的市场数据配置。

    Attributes:
        csv_file_name: CSV 数据文件名
        bar_aggregation: K线聚合类型（默认为小时）
        bar_period: K线周期（默认为 1）
        price_type: 价格类型（默认为最新价）
        origination: 数据来源（默认为外部）
        instrument_id: 交易标的 ID（可选）
        label: 数据标签（默认为 main）
    """

    csv_file_name: str
    bar_aggregation: BarAggregation = BarAggregation.HOUR
    bar_period: int = 1
    price_type: PriceType = PriceType.LAST
    origination: str = "EXTERNAL"
    instrument_id: str | None = None
    label: str = "main"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def full_path(self) -> Path:
        """获取数据文件的完整路径"""
        return project_root / "data" / "raw" / self.csv_file_name

    @property
    def bar_type_str(self) -> str:
        """获取 bar_type 字符串表示（如 1-HOUR-LAST-EXTERNAL）"""
        return f"{self.bar_period}-{self.bar_aggregation.name}-{self.price_type.name}-{self.origination}"


# ============================================================
# 策略配置
# ============================================================


class LegacyStrategyConfig(BaseModel):
    """
    策略配置容器（遗留版本）

    用于配置策略的基本信息和参数。

    Attributes:
        name: 策略名称
        module_path: 策略模块路径
        config_class: 配置类名（可选，默认为 {name}Config）
        params: 策略参数字典
        trade_pair_list: 交易对列表（可选）
    """

    name: str
    module_path: str
    config_class: str | None = None
    params: Any = Field(default_factory=dict)
    trade_pair_list: list[str] | None = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def resolve_config_class(self) -> str:
        """
        解析策略配置类名

        如果未指定 config_class，则自动生成为 {name}Config。

        Returns:
            配置类名
        """
        if self.config_class:
            return self.config_class
        return f"{self.name.replace('Strategy', '')}Config"

    def _convert_params_to_dict(self) -> dict:
        """将params转换为字典"""
        if isinstance(self.params, dict):
            return self.params.copy()

        if hasattr(self.params, "__dict__"):
            return {k: v for k, v in self.params.__dict__.items() if not k.startswith("_")}

        try:
            from msgspec import structs

            return structs.asdict(self.params)
        except (ImportError, TypeError):
            return {}

    def _add_basic_params(self, p: dict, instrument_id: Any, leverage: int):
        """添加基础参数"""
        p["instrument_id"] = str(instrument_id)
        p["leverage"] = leverage

    def _add_main_bar_types(self, p: dict, feed_bar_types: Dict[str, Any]):
        """添加主要bar类型"""
        if "main" in feed_bar_types:
            bt = feed_bar_types["main"]
            p["bar_type"] = bt
            p["trade_bar_type"] = str(bt)

    def _add_trend_bar_type(self, p: dict, feed_bar_types: Dict[str, Any]):
        """添加趋势bar类型"""
        if "trend" in feed_bar_types:
            p["trend_bar_type"] = str(feed_bar_types["trend"])

    def _add_custom_bar_types(self, p: dict, feed_bar_types: Dict[str, Any]):
        """添加自定义bar类型"""
        for label, bt in feed_bar_types.items():
            if label not in ["main", "trend"]:
                p[f"{label}_bar_type"] = str(bt)

    def resolve_params(
        self,
        instrument_id: Any,
        leverage: int,
        feed_bar_types: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        解析并合并策略参数

        Args:
            instrument_id: 合约标识符
            leverage: 杠杆倍数
            feed_bar_types: 数据流的 bar 类型映射

        Returns:
            合并后的参数字典
        """
        p = self._convert_params_to_dict()
        self._add_basic_params(p, instrument_id, leverage)
        self._add_main_bar_types(p, feed_bar_types)
        self._add_trend_bar_type(p, feed_bar_types)
        self._add_custom_bar_types(p, feed_bar_types)
        return p


# ============================================================
# 回测配置
# ============================================================


class LogConfig(BaseModel):
    """
    日志配置

    控制日志输出级别和格式。

    Attributes:
        log_level: 控制台日志级别（默认 INFO）
        log_level_file: 文件日志级别（默认 DEBUG）
        log_colors: 是否启用彩色日志（默认 True）
        use_pyo3: 是否使用 PyO3 日志（默认 True）
        log_component_levels: 组件级别的日志配置
        log_components_only: 是否仅记录指定组件的日志（默认 False）
    """

    log_level: str = "INFO"
    log_level_file: str = "DEBUG"
    log_colors: bool = True
    use_pyo3: bool = True
    log_component_levels: Dict[str, str] = Field(default_factory=dict)
    log_components_only: bool = False


class BacktestConfig(BaseModel):
    """
    回测配置容器

    定义回测所需的所有配置，包括交易标的、策略、数据源等。

    Attributes:
        instrument: 单个交易标的配置（遗留字段）
        strategy: 策略配置
        instruments: 交易标的列表
        data_feeds: 数据源列表
        start_date: 回测开始日期（可选）
        end_date: 回测结束日期（可选）
        initial_balances: 初始资金列表（默认 10,000 USDT）
        output_html_report: 是否输出 HTML 报告（默认 False）
        logging: 日志配置（可选）
        data: 主数据配置（可选）
        aux_data: 辅助数据配置（可选）
    """

    instrument: InstrumentConfig
    strategy: LegacyStrategyConfig
    instruments: List[InstrumentConfig] = Field(default_factory=list)
    data_feeds: List[DataConfig] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    initial_balances: List[Money] = Field(default_factory=lambda: [Money("10_000", USDT)])
    output_html_report: bool = False
    logging: LogConfig | None = None
    data: DataConfig | None = None
    aux_data: DataConfig | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _migrate_instrument_to_instruments(self):
        """
        迁移单个 instrument 到 instruments 列表

        用于向后兼容旧配置格式。
        """
        if self.instrument and not self.instruments:
            self.instruments.append(self.instrument)

    def _add_main_data_feed(self):
        """添加主数据源到data_feeds"""
        if not self.data or self.data in self.data_feeds:
            return

        if self.data.label == "main":
            self.data.label = "main"
        self.data_feeds.insert(0, self.data)

    def _add_aux_data_feed(self):
        """添加辅助数据源到data_feeds"""
        if not self.aux_data or self.aux_data in self.data_feeds:
            return

        if self.aux_data.label == "main":
            self.aux_data.label = "trend"
        self.data_feeds.append(self.aux_data)

    def _set_default_data_feeds(self):
        """设置默认的data和aux_data"""
        if self.data_feeds and self.data is None:
            self.data = self.data_feeds[0]
        if len(self.data_feeds) > 1 and self.aux_data is None:
            self.aux_data = self.data_feeds[1]

    def model_post_init(self, __context):
        """Pydantic v2 post-initialization hook"""
        self._migrate_instrument_to_instruments()
        self._add_main_data_feed()
        self._add_aux_data_feed()
        self._set_default_data_feeds()


# ============================================================
# 交易环境配置
# ============================================================


class TradingConfig(BaseModel):
    """交易环境配置"""

    venue: str = "BINANCE"
    instrument_type: str = "SWAP"
    initial_balance: Decimal = Decimal("100")
    currency: str = "USDT"

    # Timeframes
    main_timeframe: str = "1h"
    trend_timeframe: str = "4h"

    @field_validator("venue", mode="before")
    @classmethod
    def validate_venue(cls, v):
        """验证交易所名称是否支持"""
        supported_venues = ["BINANCE", "OKX"]
        if v.upper() not in supported_venues:
            raise ValueError(f"Venue must be one of {supported_venues}")
        return v.upper()

    @field_validator("instrument_type", mode="before")
    @classmethod
    def validate_instrument_type(cls, v):
        """验证合约类型是否有效"""
        valid_types = ["SPOT", "FUTURES", "SWAP", "OPTION", "PERP"]
        if v.upper() not in valid_types:
            raise ValueError(f"Instrument type must be one of {valid_types}")
        return v.upper()

    @field_validator("initial_balance", mode="before")
    @classmethod
    def validate_initial_balance(cls, v):
        """验证初始余额必须为正数"""
        if v <= 0:
            raise ValueError("Initial balance must be positive")
        return v

    @field_validator("main_timeframe", "trend_timeframe", mode="before")
    @classmethod
    def validate_timeframe(cls, v):
        """验证时间框架格式（如 1h, 4h, 1d）"""
        if not v or not isinstance(v, str):
            raise ValueError("Timeframe must be a non-empty string")
        if v[-1] not in ["m", "h", "d"]:
            raise ValueError("Timeframe must end with 'm', 'h', or 'd'")
        try:
            period = int(v[:-1]) if len(v) > 1 else 1
            if period <= 0:
                raise ValueError("Timeframe period must be positive")
        except ValueError:
            raise ValueError("Invalid timeframe format")
        return v


class BacktestPeriodConfig(BaseModel):
    """回测周期配置"""

    start_date: str
    end_date: str

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date_format(cls, v):
        """验证日期格式为 YYYY-MM-DD"""
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def validate_date_range(self):
        """验证开始日期必须早于结束日期"""
        start = self.start_date
        end = self.end_date

        if start and end:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")

            if start_dt >= end_dt:
                raise ValueError("start_date must be before end_date")

        return self


# ============================================================
# 日志和文件管理配置
# ============================================================


class LoggingConfig(BaseModel):
    """日志配置"""

    level: str = "INFO"
    file_level: str = "DEBUG"
    components: Dict[str, str] = Field(default_factory=dict)
    components_only: bool = True

    @field_validator("level", "file_level", mode="before")
    @classmethod
    def validate_log_level(cls, v):
        """验证日志级别是否有效"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()


class FileCleanupConfig(BaseModel):
    """文件清理配置"""

    max_files_per_dir: int = 100
    enabled: bool = True
    target_dirs: List[str] = Field(default_factory=lambda: ["log", "output"])

    # 时间轮转参数
    use_time_rotation: bool = False
    keep_days: int = 7
    delete_days: int = 30

    @field_validator("max_files_per_dir", mode="before")
    @classmethod
    def validate_max_files(cls, v):
        """验证最大文件数必须至少为 1"""
        if v < 1:
            raise ValueError("max_files_per_dir must be at least 1")
        return v

    @field_validator("target_dirs", mode="before")
    @classmethod
    def validate_target_dirs(cls, v):
        """验证目标目录列表不能为空"""
        if not v:
            raise ValueError("target_dirs cannot be empty")
        return v

    @field_validator("keep_days", mode="before")
    @classmethod
    def validate_keep_days(cls, v):
        """验证保留天数必须至少为 1"""
        if v < 1:
            raise ValueError("keep_days must be at least 1")
        return v

    @field_validator("delete_days", mode="before")
    @classmethod
    def validate_delete_days(cls, v, info):
        """验证删除天数必须大于等于保留天数"""
        if v < 1:
            raise ValueError("delete_days must be at least 1")
        # Pydantic V2: 使用 info.data 访问其他字段
        if info.data and "keep_days" in info.data and v < info.data["keep_days"]:
            raise ValueError("delete_days must be >= keep_days")
        return v


# ============================================================
# 其他配置类
# ============================================================


class StrategyConfig(BaseModel):
    """策略配置"""

    name: str
    module_path: str
    config_class: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, v):
        """验证策略名称不能为空"""
        if not v or not v.strip():
            raise ValueError("Strategy name cannot be empty")
        return v.strip()

    @field_validator("module_path", mode="before")
    @classmethod
    def validate_module_path(cls, v):
        """验证模块路径不能为空"""
        if not v or not v.strip():
            raise ValueError("Module path cannot be empty")
        return v.strip()


class SandboxConfig(BaseModel):
    """Sandbox实时交易配置"""

    # 交易所配置
    venue: str = "OKX"
    is_testnet: bool = True

    # 标的配置
    instrument_ids: List[str] = Field(default_factory=list)

    # 账户配置
    initial_balance: Optional[Decimal] = None

    # API配置
    api_key_env: str = "OKX_API_KEY"
    api_secret_env: str = "OKX_API_SECRET"
    api_passphrase_env: str = "OKX_API_PASSPHRASE"

    # 执行引擎配置
    reconciliation: bool = True
    reconciliation_lookback_mins: int = 1440
    filter_position_reports: bool = True

    # 缓存配置
    flush_cache_on_start: bool = False

    # 超时配置（秒）
    timeout_connection: float = 10.0
    timeout_reconciliation: float = 10.0
    timeout_portfolio: float = 10.0
    timeout_disconnection: float = 10.0
    timeout_post_stop: float = 5.0

    # When True, allow missing instrument json files during sandbox preflight.
    # Missing instrument files will be treated as warnings rather than blocking
    # errors. This is convenient for local development where the data/instrument
    # directory may not be populated. Default is False (strict validation).
    allow_missing_instruments: bool = False

    @field_validator("venue", mode="before")
    @classmethod
    def validate_venue(cls, v):
        """验证交易所名称是否支持"""
        supported = ["OKX", "BINANCE"]
        if v.upper() not in supported:
            raise ValueError(f"Venue must be one of {supported}")
        return v.upper()

    @field_validator("instrument_ids", mode="before")
    @classmethod
    def validate_instruments(cls, v):
        """验证至少需要一个合约标识符"""
        if not v:
            raise ValueError("At least one instrument_id is required")
        return v


class LiveConfig(BaseModel):
    """Live实盘交易配置"""

    # 交易所配置
    venue: str = "BINANCE"

    # 标的配置
    instrument_ids: List[str] = Field(default_factory=list)

    # 账户配置
    initial_balance: Optional[Decimal] = None

    # API配置
    api_key_env: str = "BINANCE_API_KEY"
    api_secret_env: str = "BINANCE_API_SECRET"
    api_passphrase_env: str = ""

    # 执行引擎配置
    reconciliation: bool = True
    reconciliation_lookback_mins: int = 1440
    filter_position_reports: bool = True

    # 缓存配置
    flush_cache_on_start: bool = False

    @field_validator("venue", mode="before")
    @classmethod
    def validate_venue(cls, v):
        """验证交易所名称是否支持"""
        supported = ["OKX", "BINANCE"]
        if v.upper() not in supported:
            raise ValueError(f"Venue must be one of {supported}")
        return v.upper()

    @field_validator("instrument_ids", mode="before")
    @classmethod
    def validate_instruments(cls, v):
        """验证至少需要一个合约标识符"""
        if not v:
            raise ValueError("At least one instrument_id is required")
        return v


# ============================================================
# 环境和路径配置
# ============================================================


class EnvironmentConfig(BaseModel):
    """环境配置"""

    model_config = ConfigDict(extra="allow")

    extends: Optional[str] = None  # 继承的父配置文件
    trading: TradingConfig = Field(default_factory=TradingConfig)
    backtest: BacktestPeriodConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    file_cleanup: FileCleanupConfig = Field(default_factory=FileCleanupConfig)
    sandbox: Optional[SandboxConfig] = None
    live: Optional[LiveConfig] = None


class ActiveConfig(BaseModel):
    """当前活跃配置选择"""

    environment: str = "dev"
    strategy: str
    primary_symbol: str = "BTCUSDT"

    # 数据加载参数（可选，用于覆盖策略配置）
    timeframe: Optional[str] = None
    price_type: Optional[str] = None
    origination: Optional[str] = None

    overrides: Optional[Dict[str, Any]] = None

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v):
        """验证环境名称不能为空"""
        if not v or not v.strip():
            raise ValueError("Environment cannot be empty")
        return v.strip()

    @field_validator("strategy", mode="before")
    @classmethod
    def validate_strategy(cls, v):
        """验证策略名称不能为空"""
        if not v or not v.strip():
            raise ValueError("Strategy cannot be empty")
        return v.strip()

    @field_validator("primary_symbol", mode="before")
    @classmethod
    def validate_primary_symbol(cls, v):
        """验证主交易标的格式（必须以 USDT 结尾）"""
        if not v or not v.strip():
            raise ValueError("Primary symbol cannot be empty")
        # 先转换为大写再验证
        v_upper = v.strip().upper()
        if not v_upper.endswith("USDT"):
            raise ValueError("Primary symbol must end with 'USDT'")
        return v_upper

    @field_validator("timeframe", mode="before")
    @classmethod
    def validate_timeframe(cls, v):
        """验证时间框架格式（可选）"""
        if v is None:
            return v

        if not v or not isinstance(v, str):
            raise ValueError("Timeframe must be a non-empty string")

        if v[-1] not in ["m", "h", "d"]:
            raise ValueError("Timeframe must end with 'm', 'h', or 'd'")

        cls._validate_timeframe_period(v)
        return v

    @classmethod
    def _validate_timeframe_period(cls, v: str):
        """验证时间周期数值"""
        try:
            period = int(v[:-1]) if len(v) > 1 else 1
            if period <= 0:
                raise ValueError("Timeframe period must be positive")
        except ValueError:
            raise ValueError("Invalid timeframe format")

    @field_validator("price_type", mode="before")
    @classmethod
    def validate_price_type(cls, v):
        """验证价格类型是否有效（可选）"""
        if v is None:
            return v
        valid_types = ["LAST", "MID", "BID", "ASK"]
        if v.upper() not in valid_types:
            raise ValueError(f"Price type must be one of {valid_types}")
        return v.upper()

    @field_validator("origination", mode="before")
    @classmethod
    def validate_origination(cls, v):
        """验证数据来源是否有效（可选）"""
        if v is None:
            return v
        valid_types = ["EXTERNAL", "INTERNAL"]
        if v.upper() not in valid_types:
            raise ValueError(f"Origination must be one of {valid_types}")
        return v.upper()


class ConfigPaths:
    """配置文件路径管理"""

    def __init__(self, config_root: Optional[Path] = None):
        """
        初始化配置路径管理器

        Args:
            config_root: 配置文件根目录，默认为项目根目录下的 config 文件夹
        """
        self.config_root = config_root or (project_root / "config")
        self.yaml_dir = self.config_root
        self.environments_dir = self.yaml_dir / "environments"
        self.strategies_dir = self.yaml_dir / "strategies"
        self.active_file = self.yaml_dir / "active.yaml"

    def get_environment_file(self, env_name: str) -> Path:
        """获取环境配置文件路径"""
        return self.environments_dir / f"{env_name}.yaml"

    def get_strategy_file(self, strategy_name: str) -> Path:
        """获取策略配置文件路径"""
        return self.strategies_dir / f"{strategy_name}.yaml"

    def ensure_directories(self):
        """确保配置目录存在"""
        self.yaml_dir.mkdir(parents=True, exist_ok=True)
        self.environments_dir.mkdir(parents=True, exist_ok=True)
        self.strategies_dir.mkdir(parents=True, exist_ok=True)

    def list_environments(self) -> List[str]:
        """列出所有可用的环境配置"""
        if not self.environments_dir.exists():
            return []

        env_files = self.environments_dir.glob("*.yaml")
        return [f.stem for f in env_files if f.is_file()]

    def list_strategies(self) -> List[str]:
        """列出所有可用的策略配置"""
        if not self.strategies_dir.exists():
            return []

        strategy_files = self.strategies_dir.glob("*.yaml")
        return [f.stem for f in strategy_files if f.is_file()]


# 导出主要类和函数
__all__ = [
    "InstrumentType",
    "InstrumentConfig",
    "DataConfig",
    "LegacyStrategyConfig",
    "LogConfig",
    "BacktestConfig",
    "TradingConfig",
    "BacktestPeriodConfig",
    "LoggingConfig",
    "FileCleanupConfig",
    "StrategyConfig",
    "SandboxConfig",
    "EnvironmentConfig",
    "ActiveConfig",
    "ConfigPaths",
    "project_root",
]
