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
from pydantic import BaseModel, ConfigDict, Field, model_validator, validator

# 项目根目录
project_root: Path = Path(__file__).parent.parent.resolve()


# ============================================================
# 交易工具配置
# ============================================================

class InstrumentType(Enum):
    """交易工具类型"""
    SPOT = "SPOT"
    FUTURES = "FUTURES"
    SWAP = "SWAP"
    OPTION = "OPTION"


class InstrumentConfig(BaseModel):
    """交易工具配置"""
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


# ============================================================
# 数据配置
# ============================================================

class DataConfig(BaseModel):
    """数据配置"""
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
        return project_root / "data" / "raw" / self.csv_file_name

    @property
    def bar_type_str(self) -> str:
        return f"{self.bar_period}-{self.bar_aggregation.name}-{self.price_type.name}-{self.origination}"


# ============================================================
# 策略配置
# ============================================================

class LegacyStrategyConfig(BaseModel):
    """策略配置容器"""
    name: str
    module_path: str
    config_class: str | None = None
    params: Any = Field(default_factory=dict)
    trade_pair_list: list[str] | None = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

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


# ============================================================
# 回测配置
# ============================================================

class LogConfig(BaseModel):
    """日志配置"""
    log_level: str = "INFO"
    log_level_file: str = "DEBUG"
    log_colors: bool = True
    use_pyo3: bool = True
    log_component_levels: Dict[str, str] = Field(default_factory=dict)
    log_components_only: bool = False


class BacktestConfig(BaseModel):
    """回测配置容器"""
    instrument: InstrumentConfig
    strategy: LegacyStrategyConfig
    instruments: List[InstrumentConfig] = Field(default_factory=list)
    data_feeds: List[DataConfig] = Field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    initial_balances: List[Money] = Field(
        default_factory=lambda: [Money("10_000", USDT)]
    )
    output_html_report: bool = False
    logging: LogConfig | None = None
    data: DataConfig | None = None
    aux_data: DataConfig | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context):
        """Pydantic v2 post-initialization hook"""
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

    @validator("venue")
    def validate_venue(cls, v):
        supported_venues = ["BINANCE", "OKX"]
        if v.upper() not in supported_venues:
            raise ValueError(f"Venue must be one of {supported_venues}")
        return v.upper()

    @validator("instrument_type")
    def validate_instrument_type(cls, v):
        valid_types = ["SPOT", "FUTURES", "SWAP", "OPTION"]
        if v.upper() not in valid_types:
            raise ValueError(f"Instrument type must be one of {valid_types}")
        return v.upper()

    @validator("initial_balance")
    def validate_initial_balance(cls, v):
        if v <= 0:
            raise ValueError("Initial balance must be positive")
        return v

    @validator("main_timeframe", "trend_timeframe")
    def validate_timeframe(cls, v):
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

    @validator("start_date", "end_date")
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        return v

    @model_validator(mode="after")
    def validate_date_range(self):
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

    @validator("level", "file_level")
    def validate_log_level(cls, v):
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

    @validator("max_files_per_dir")
    def validate_max_files(cls, v):
        if v < 1:
            raise ValueError("max_files_per_dir must be at least 1")
        return v

    @validator("target_dirs")
    def validate_target_dirs(cls, v):
        if not v:
            raise ValueError("target_dirs cannot be empty")
        return v

    @validator("keep_days")
    def validate_keep_days(cls, v):
        if v < 1:
            raise ValueError("keep_days must be at least 1")
        return v

    @validator("delete_days")
    def validate_delete_days(cls, v, values):
        if v < 1:
            raise ValueError("delete_days must be at least 1")
        if "keep_days" in values and v < values["keep_days"]:
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

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Strategy name cannot be empty")
        return v.strip()

    @validator("module_path")
    def validate_module_path(cls, v):
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

    @validator("venue")
    def validate_venue(cls, v):
        supported = ["OKX", "BINANCE"]
        if v.upper() not in supported:
            raise ValueError(f"Venue must be one of {supported}")
        return v.upper()

    @validator("instrument_ids")
    def validate_instruments(cls, v):
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

    @validator("venue")
    def validate_venue(cls, v):
        supported = ["OKX", "BINANCE"]
        if v.upper() not in supported:
            raise ValueError(f"Venue must be one of {supported}")
        return v.upper()

    @validator("instrument_ids")
    def validate_instruments(cls, v):
        if not v:
            raise ValueError("At least one instrument_id is required")
        return v


# ============================================================
# 环境和路径配置
# ============================================================

class EnvironmentConfig(BaseModel):
    """环境配置"""

    extends: Optional[str] = None  # 继承的父配置文件
    trading: TradingConfig = Field(default_factory=TradingConfig)
    backtest: BacktestPeriodConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    file_cleanup: FileCleanupConfig = Field(default_factory=FileCleanupConfig)
    sandbox: Optional[SandboxConfig] = None
    live: Optional[LiveConfig] = None

    class Config:
        # 允许额外字段，用于扩展配置
        extra = "allow"


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

    @validator("environment")
    def validate_environment(cls, v):
        if not v or not v.strip():
            raise ValueError("Environment cannot be empty")
        return v.strip()

    @validator("strategy")
    def validate_strategy(cls, v):
        if not v or not v.strip():
            raise ValueError("Strategy cannot be empty")
        return v.strip()

    @validator("primary_symbol")
    def validate_primary_symbol(cls, v):
        if not v or not v.strip():
            raise ValueError("Primary symbol cannot be empty")
        # 基础格式验证
        if not v.endswith("USDT"):
            raise ValueError("Primary symbol must end with 'USDT'")
        return v.strip().upper()

    @validator("timeframe")
    def validate_timeframe(cls, v):
        if v is None:
            return v
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

    @validator("price_type")
    def validate_price_type(cls, v):
        if v is None:
            return v
        valid_types = ["LAST", "MID", "BID", "ASK"]
        if v.upper() not in valid_types:
            raise ValueError(f"Price type must be one of {valid_types}")
        return v.upper()

    @validator("origination")
    def validate_origination(cls, v):
        if v is None:
            return v
        valid_types = ["EXTERNAL", "INTERNAL"]
        if v.upper() not in valid_types:
            raise ValueError(f"Origination must be one of {valid_types}")
        return v.upper()





class ConfigPaths:
    """配置文件路径管理"""

    def __init__(self, config_root: Optional[Path] = None):
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
