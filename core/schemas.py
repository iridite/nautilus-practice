"""
配置系统数据模型定义

使用Pydantic提供类型安全的配置验证和序列化。
与现有的config/definitions.py紧密集成，复用已有的数据结构。
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator, validator

# 项目根目录
project_root: Path = Path(__file__).parent.parent.resolve()


class TradingConfig(BaseModel):
    """交易环境配置"""

    venue: str = "BINANCE"
    instrument_type: str = "SWAP"
    initial_balance: Decimal = Decimal("100")
    currency: str = "USDT"

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


class TimeframesConfig(BaseModel):
    """时间框架配置"""

    main: str = "1h"
    trend: str = "4h"

    @validator("main", "trend")
    def validate_timeframe(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Timeframe must be a non-empty string")

        # 验证时间框架格式 (如 1m, 5m, 1h, 4h, 1d)
        if v[-1] not in ["m", "h", "d"]:
            raise ValueError("Timeframe must end with 'm', 'h', or 'd'")

        try:
            period = int(v[:-1]) if len(v) > 1 else 1
            if period <= 0:
                raise ValueError("Timeframe period must be positive")
        except ValueError:
            raise ValueError("Invalid timeframe format")

        return v


class BacktestConfig(BaseModel):
    """回测配置"""

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


class StrategyParametersConfig(BaseModel):
    """策略参数基础配置"""

    # 基础仓位参数
    qty_percent: Optional[Decimal] = Decimal("0.1")
    leverage: Optional[int] = 1
    max_positions: Optional[int] = 1

    # 风险管理参数
    stop_loss_pct: Optional[Decimal] = None
    use_atr_stop: Optional[bool] = False
    atr_period: Optional[int] = 14
    atr_stop_multiplier: Optional[Decimal] = Decimal("2.0")

    # 滑点控制
    max_slippage_pct: Optional[Decimal] = Decimal("0.005")
    enable_slippage_alert: Optional[bool] = True

    # 日志控制
    enable_signal_logging: Optional[bool] = True
    enable_quality_check: Optional[bool] = True

    @validator("leverage")
    def validate_leverage(cls, v):
        if v is not None and not (1 <= v <= 100):
            raise ValueError("Leverage must be between 1 and 100")
        return v

    @validator("qty_percent")
    def validate_position_size(cls, v):
        if v is not None and not (0 < v <= 1):
            raise ValueError("Position size must be between 0 and 1")
        return v

    @validator("max_positions")
    def validate_max_positions(cls, v):
        if v is not None and v < 1:
            raise ValueError("Max positions must be at least 1")
        return v


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


class EnvironmentConfig(BaseModel):
    """环境配置"""

    extends: Optional[str] = None  # 继承的父配置文件
    trading: TradingConfig = Field(default_factory=TradingConfig)
    timeframes: TimeframesConfig = Field(default_factory=TimeframesConfig)
    backtest: BacktestConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    file_cleanup: FileCleanupConfig = Field(default_factory=FileCleanupConfig)
    sandbox: Optional[SandboxConfig] = None

    class Config:
        # 允许额外字段，用于扩展配置
        extra = "allow"


class ActiveConfig(BaseModel):
    """当前活跃配置选择"""

    environment: str = "dev"
    strategy: str
    primary_symbol: str = "BTCUSDT"
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


class ConfigValidationError(Exception):
    """配置验证错误"""

    def __init__(self, message: str, field: Optional[str] = None, value: Any = None):
        self.message = message
        self.field = field
        self.value = value
        super().__init__(self.message)


class ConfigPaths:
    """配置文件路径管理"""

    def __init__(self, config_root: Optional[Path] = None):
        self.config_root = config_root or (project_root / "config_yaml")
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
    "TradingConfig",
    "TimeframesConfig",
    "BacktestConfig",
    "LoggingConfig",
    "FileCleanupConfig",
    "StrategyParametersConfig",
    "StrategyConfig",
    "SandboxConfig",
    "EnvironmentConfig",
    "ActiveConfig",
    "ConfigValidationError",
    "ConfigPaths",
]
