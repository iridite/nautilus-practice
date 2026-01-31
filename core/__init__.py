"""
配置系统统一入口

基于 YAML + Pydantic 的配置管理系统。
"""

# 异常类
# 配置适配器
from .adapter import ConfigAdapter
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
from .models import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
    LogConfig,
    project_root,
)

# Pydantic 模型
from .schemas import (
    ActiveConfig,
    BacktestPeriodConfig,
    EnvironmentConfig,
    StrategyConfig,
    TradingConfig,
)
from .settings import (
    build_backtest_config,
    create_data_config,
    get_adapter,
    get_available_environments,
    get_available_strategies,
    print_config_summary,
    reload_config,
    run_file_cleanup,
    validate_config,
)

__all__ = [
    # 异常类
    "ConfigError",
    "ConfigValidationError",
    "ConfigLoadError",
    "UniverseParseError",
    "InstrumentConfigError",
    # 访问接口
    "create_data_config",
    "build_backtest_config",
    "reload_config",
    "get_available_environments",
    "get_available_strategies",
    "validate_config",
    "print_config_summary",
    "get_adapter",
    "run_file_cleanup",
    # 配置模型
    "BackTestConfig",
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
