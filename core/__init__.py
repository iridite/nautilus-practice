"""
配置系统统一入口

基于 YAML + Pydantic 的配置管理系统。
"""

# 异常类
# 配置适配器
from .adapter import ConfigAdapter, get_adapter
from .exceptions import (
    ConfigError,
    ConfigLoadError,
    ConfigValidationError,
    InstrumentConfigError,
    UniverseParseError,
)

# 配置加载器
from .loader import ConfigLoader

# 配置模型
# Pydantic 模型
from .schemas import (
    ActiveConfig,
    BacktestConfig,
    BacktestPeriodConfig,
    DataConfig,
    EnvironmentConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
    LogConfig,
    StrategyConfig,
    TradingConfig,
    project_root,
)

__all__ = [
    # 异常类
    "ConfigError",
    "ConfigValidationError",
    "ConfigLoadError",
    "UniverseParseError",
    "InstrumentConfigError",
    # 访问接口
    "get_adapter",
    # 配置模型
    "BacktestConfig",
    "DataConfig",
    "InstrumentConfig",
    "InstrumentType",
    "LegacyStrategyConfig",
    "LogConfig",
    "project_root",
    # 适配器
    "ConfigAdapter",
    # Pydantic 模型
    "ActiveConfig",
    "BacktestPeriodConfig",
    "EnvironmentConfig",
    "StrategyConfig",
    "TradingConfig",
    # 加载器
    "ConfigLoader",
]
