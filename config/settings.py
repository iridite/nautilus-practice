"""
新配置系统主接口

基于YAML + Pydantic的现代化配置管理系统。
完全替换原有的settings.py，不再保持向后兼容。
"""

from typing import List

from nautilus_trader.model import Money

from .definitions import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
)

# 导入新配置系统
from .manager import ConfigManager

# ==========================================
# 全局配置管理器
# ==========================================

# 创建全局配置管理器实例
config_manager = ConfigManager()

# ==========================================
# 配置访问接口
# ==========================================


def get_venue() -> str:
    """获取交易所名称"""
    return config_manager.VENUE


def get_instrument_type() -> InstrumentType:
    """获取交易工具类型"""
    return config_manager.INSTRUMENT_TYPE


def get_start_date() -> str:
    """获取回测开始日期"""
    return config_manager.START_DATE


def get_end_date() -> str:
    """获取回测结束日期"""
    return config_manager.END_DATE


def get_initial_balances() -> List[Money]:
    """获取初始余额"""
    return config_manager.INITIAL_BALANCES


def get_main_timeframe() -> str:
    """获取主时间框架"""
    return config_manager.MAIN_TIMEFRAME


def get_trend_timeframe() -> str:
    """获取趋势时间框架"""
    return config_manager.TREND_TIMEFRAME


def get_primary_symbol() -> str:
    """获取主要交易对"""
    return config_manager.PRIMARY_SYMBOL


def get_active_strategy() -> LegacyStrategyConfig:
    """获取当前活跃策略"""
    return config_manager.ACTIVE_STRATEGY


# ==========================================
# 配置构建函数
# ==========================================


def create_data_config(symbol: str, timeframe: str, label: str = "main") -> DataConfig:
    """
    创建数据配置

    Args:
        symbol: 交易对符号
        timeframe: 时间框架
        label: 数据标签

    Returns:
        DataConfig: 数据配置对象
    """
    return config_manager.create_data_cfg(symbol, timeframe, label)


def create_instrument_config(symbol: str) -> InstrumentConfig:
    """
    创建交易工具配置

    Args:
        symbol: 交易对符号

    Returns:
        InstrumentConfig: 交易工具配置
    """
    return config_manager.create_instrument_cfg(symbol)


def load_universe_symbols(universe_file: str) -> set:
    """
    从Universe文件加载交易对符号

    Args:
        universe_file: Universe文件路径

    Returns:
        set: 交易对符号集合
    """
    return config_manager.load_universe_symbols(universe_file)


def build_backtest_config() -> BackTestConfig:
    """
    构建完整的回测配置

    Returns:
        BackTestConfig: 回测配置对象
    """
    return config_manager.build_config()


# ==========================================
# 配置管理功能
# ==========================================


def switch_environment(env_name: str):
    """
    切换环境配置

    Args:
        env_name: 环境名称 (dev, prod, test等)
    """
    config_manager.switch_environment(env_name)
    print(f"✅ 已切换到环境: {env_name}")


def switch_strategy(strategy_name: str):
    """
    切换策略配置

    Args:
        strategy_name: 策略名称
    """
    config_manager.switch_strategy(strategy_name)
    print(f"✅ 已切换到策略: {strategy_name}")


def reload_config():
    """重新加载所有配置"""
    config_manager.reload()
    print("✅ 配置重新加载完成!")


def get_available_environments() -> List[str]:
    """获取可用的环境列表"""
    return config_manager.get_available_environments()


def get_available_strategies() -> List[str]:
    """获取可用的策略列表"""
    return config_manager.get_available_strategies()


def validate_config() -> dict:
    """
    验证当前配置

    Returns:
        dict: 验证报告
    """
    return config_manager.validate_all_configs()


def print_config_summary():
    """打印配置摘要"""
    print("📋 当前配置摘要:")
    print(f"  环境: {config_manager.active_config.environment}")
    print(f"  策略: {config_manager.active_config.strategy}")
    print(f"  交易所: {get_venue()}")
    print(f"  主要交易对: {get_primary_symbol()}")
    print(f"  日期范围: {get_start_date()} 到 {get_end_date()}")
    print(f"  初始余额: {get_initial_balances()[0]}")
    print(f"  时间框架: {get_main_timeframe()} (主), {get_trend_timeframe()} (趋势)")


def get_config_info() -> dict:
    """
    获取配置系统信息

    Returns:
        dict: 配置系统信息
    """
    return {
        "version": "2.0.0",
        "type": "YAML + Pydantic",
        "config_dir": str(config_manager.paths.config_root),
        "environments": get_available_environments(),
        "strategies": get_available_strategies(),
        "current_environment": config_manager.active_config.environment,
        "current_strategy": config_manager.active_config.strategy,
    }


# ==========================================
# 配置对象访问（用于需要直接访问配置对象的场景）
# ==========================================


def get_environment_config():
    """获取环境配置对象"""
    return config_manager.env_config


def get_strategy_config():
    """获取策略配置对象"""
    return config_manager.strategy_config


def get_active_config():
    """获取活跃配置对象"""
    return config_manager.active_config


def get_config_manager() -> ConfigManager:
    """获取配置管理器实例"""
    return config_manager


# ==========================================
# 初始化和启动信息
# ==========================================


def _print_startup_info():
    """打印启动信息"""
    try:
        print("🔧 配置系统已加载")
        print(f"   环境: {config_manager.active_config.environment}")
        print(f"   策略: {config_manager.active_config.strategy}")
        print(f"   配置目录: {config_manager.paths.config_root}")
    except Exception as e:
        print(f"⚠️ 配置系统警告: {e}")


# 模块加载时打印启动信息
if __name__ != "__main__":
    _print_startup_info()

# ==========================================
# 导出接口
# ==========================================

__all__ = [
    # 配置访问函数
    "get_venue",
    "get_instrument_type",
    "get_start_date",
    "get_end_date",
    "get_initial_balances",
    "get_main_timeframe",
    "get_trend_timeframe",
    "get_primary_symbol",
    "get_active_strategy",
    # 配置构建函数
    "create_data_config",
    "create_instrument_config",
    "load_universe_symbols",
    "build_backtest_config",
    # 配置管理函数
    "switch_environment",
    "switch_strategy",
    "reload_config",
    "get_available_environments",
    "get_available_strategies",
    "validate_config",
    "print_config_summary",
    "get_config_info",
    # 配置对象访问
    "get_environment_config",
    "get_strategy_config",
    "get_active_config",
    "get_config_manager",
]
