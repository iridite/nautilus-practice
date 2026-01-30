"""
配置系统统一入口

基于 YAML + Pydantic 的配置管理系统。
"""

# 主要访问接口
from .settings import (
    build_backtest_config,
    create_data_config,
    get_adapter,
    get_available_environments,
    get_available_strategies,
    get_end_date,
    get_initial_balances,
    get_main_timeframe,
    get_primary_symbol,
    get_start_date,
    get_trend_timeframe,
    get_venue,
    print_config_summary,
    reload_config,
    run_file_cleanup,
    validate_config,
)

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

# 配置适配器
from .adapter import ConfigAdapter

# Pydantic 模型
from .schemas import (
    ActiveConfig,
    BacktestConfig,
    EnvironmentConfig,
    StrategyConfig,
    TradingConfig,
)

# 配置加载器
from .loader import ConfigLoader

__all__ = [
    # 访问接口
    "get_venue",
    "get_start_date",
    "get_end_date",
    "get_initial_balances",
    "get_main_timeframe",
    "get_trend_timeframe",
    "get_primary_symbol",
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
    "BacktestConfig",
    "EnvironmentConfig",
    "StrategyConfig",
    "TradingConfig",
    # 加载器
    "ConfigLoader",
]
